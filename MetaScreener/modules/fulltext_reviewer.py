import sqlite3, fitz, logging, os, re
from config import Config

class FulltextReviewer:
    def __init__(self):
        self.db_path = Config.DB_PATH

    def get_included_papers(self):
        """Returns all papers that were included during screening."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT id, title, authors, year, doi, pmid, pdf_path, fulltext_decision, fulltext_reason 
                FROM papers 
                WHERE screening_decision = 'include' AND is_duplicate = 0
                ORDER BY id ASC
            """)
            rows = cur.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logging.error(f"Error fetching included papers: {e}")
            return []

    def get_pending_fulltext(self):
        """Returns included papers that haven't had a full-text decision yet."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT id, title, authors, year, doi, pmid, pdf_path, fulltext_decision, fulltext_reason 
                FROM papers 
                WHERE screening_decision = 'include' AND is_duplicate = 0 
                AND (fulltext_decision = 'pending' OR fulltext_decision IS NULL)
                ORDER BY id ASC
            """)
            rows = cur.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logging.error(f"Error fetching pending fulltext papers: {e}")
            return []

    def save_fulltext_decision(self, paper_id, decision, reason=""):
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("""
                UPDATE papers 
                SET fulltext_decision = ?, fulltext_reason = ? 
                WHERE id = ?
            """, (decision, reason, paper_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Error saving fulltext decision: {e}")
            return False

    def attach_pdf(self, paper_id, pdf_path):
        # Validate before storing: must exist, be a file, and have .pdf extension
        if not pdf_path:
            logging.error("attach_pdf: empty path provided")
            return False
        if not os.path.isfile(pdf_path):
            logging.error(f"attach_pdf: path does not exist or is not a file: '{pdf_path}'")
            return False
        if os.path.splitext(pdf_path)[1].lower() != ".pdf":
            logging.error(f"attach_pdf: file is not a PDF: '{pdf_path}'")
            return False
        # Resolve to absolute path to prevent relative-path traversal issues
        abs_path = os.path.abspath(pdf_path)
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("""
                UPDATE papers
                SET pdf_path = ?
                WHERE id = ?
            """, (abs_path, paper_id))
            conn.commit()
            conn.close()
            return True
        except sqlite3.Error as e:
            logging.error(f"Error attaching PDF: {e}")
            return False

    def extract_text_from_pdf(self, pdf_path):
        if not pdf_path or not os.path.isfile(pdf_path):
            return ""
        if os.path.splitext(pdf_path)[1].lower() != ".pdf":
            logging.warning(f"extract_text_from_pdf: not a PDF file: '{pdf_path}'")
            return ""
        try:
            doc = fitz.open(pdf_path)
            text_parts = []
            for i, page in enumerate(doc):
                page_text = page.get_text()
                text_parts.append(f"\n\n--- Page {i+1} ---\n\n{page_text}")
            doc.close()
            return "".join(text_parts)
        except Exception as e:
            logging.error(f"Error extracting text from PDF {pdf_path}: {e}")
            return ""

    def get_fulltext_stats(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            # Total included from screening
            cur.execute("SELECT COUNT(*) FROM papers WHERE screening_decision = 'include' AND is_duplicate = 0")
            total_included = cur.fetchone()[0]
            
            # PDFs attached
            cur.execute("SELECT COUNT(*) FROM papers WHERE screening_decision = 'include' AND is_duplicate = 0 AND pdf_path IS NOT NULL AND pdf_path != ''")
            pdf_attached = cur.fetchone()[0]
            
            # Pending full-text review
            cur.execute("""
                SELECT COUNT(*) FROM papers 
                WHERE screening_decision = 'include' AND is_duplicate = 0 
                AND (fulltext_decision = 'pending' OR fulltext_decision IS NULL)
            """)
            pending_review = cur.fetchone()[0]
            
            # Full-text included
            cur.execute("SELECT COUNT(*) FROM papers WHERE screening_decision = 'include' AND is_duplicate = 0 AND fulltext_decision = 'include'")
            ft_included = cur.fetchone()[0]
            
            # Full-text excluded
            cur.execute("SELECT COUNT(*) FROM papers WHERE screening_decision = 'include' AND is_duplicate = 0 AND fulltext_decision = 'exclude'")
            ft_excluded = cur.fetchone()[0]
            
            conn.close()
            return {
                "total_included": total_included,
                "pdf_attached": pdf_attached,
                "pending_review": pending_review,
                "ft_included": ft_included,
                "ft_excluded": ft_excluded
            }
        except Exception as e:
            logging.error(f"Error getting fulltext stats: {e}")
            return {
                "total_included": 0,
                "pdf_attached": 0,
                "pending_review": 0,
                "ft_included": 0,
                "ft_excluded": 0
            }

    def bulk_attach_pdfs(self, folder_path):
        if not os.path.exists(folder_path):
            return {"attached": 0, "not_found": 0}
            
        papers = self.get_included_papers()
        if not papers:
            return {"attached": 0, "not_found": 0}
            
        pdf_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".pdf")]
        
        attached_count = 0
        not_found_count = 0
        
        for p in papers:
            paper_id = p["id"]
            title = p.get("title", "")
            doi = p.get("doi", "")
            
            found_path = None
            
            # 1. Match by DOI
            if doi:
                clean_doi = re.sub(r'[^a-zA-Z0-9]', '', doi).lower()
                for f in pdf_files:
                    if clean_doi in re.sub(r'[^a-zA-Z0-9]', '', f).lower():
                        found_path = os.path.join(folder_path, f)
                        break
            
            # 2. Match by Title first 40 chars
            if not found_path and title:
                # Clean title: lowercase, replace spaces with underscores, remove special chars
                clean_title = re.sub(r'[^a-z0-9\s]', '', title.lower())
                clean_title_underscore = clean_title.replace(' ', '_')
                search_term = clean_title[:40].lower()
                
                for f in pdf_files:
                    clean_f = re.sub(r'[^a-z0-9]', '', f.lower())
                    if re.sub(r'[^a-z0-9]', '', search_term) in clean_f:
                        found_path = os.path.join(folder_path, f)
                        break
            
            if found_path:
                self.attach_pdf(paper_id, found_path)
                attached_count += 1
            else:
                not_found_count += 1
                
        return {"attached": attached_count, "not_found": not_found_count}

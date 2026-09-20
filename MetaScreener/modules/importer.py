import rispy
import bibtexparser
import csv
import os
import sqlite3
import logging
from config import Config

_ALLOWED_EXTENSIONS = {".ris", ".bib", ".csv", ".txt"}
_MAX_FILE_SIZE_MB = 50
_MAX_FILE_BYTES = _MAX_FILE_SIZE_MB * 1024 * 1024

class PaperImporter:
    def __init__(self):
        self.db_path = Config.DB_PATH

    def _validate_file(self, filepath: str) -> str | None:
        """Return an error string if the file fails validation, else None."""
        _, ext = os.path.splitext(filepath)
        if ext.lower() not in _ALLOWED_EXTENSIONS:
            return f"Unsupported file type: '{ext}'. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}"
        try:
            size = os.path.getsize(filepath)
        except OSError:
            return "Cannot access file"
        if size > _MAX_FILE_BYTES:
            return f"File too large ({size // (1024*1024)} MB). Maximum is {_MAX_FILE_SIZE_MB} MB."
        if size == 0:
            return "File is empty"
        return None

    def detect_format(self, filepath):
        """Detect reference format — logs only structural signals, never file content."""
        ext = os.path.splitext(filepath)[1].lower()
        try:
            try:
                with open(filepath, encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(filepath, encoding="latin-1") as f:
                    content = f.read()
        except OSError:
            content = ""

        signals = {
            "extension": ext,
            "contains_PMID": "PMID-" in content or "PMID =" in content,
            "contains_TI": "TI  -" in content or "TI - " in content,
            "contains_ER": "ER  -" in content or "ER\n" in content,
            "contains_FAU": "FAU -" in content,
            "contains_VR1": "VR 1.0" in content,
            "contains_FN": "FN Clarivate" in content or "FN Thomson" in content,
            "contains_Embase": "Embase" in content or "EMBASE" in content,
        }
        # Log only structural signals — never file content
        logging.debug(f"Format detection signals for '{os.path.basename(filepath)}': {signals}")
        return signals, content  # return content so import_file reuses it

    def import_file(self, filepath):
        error = self._validate_file(filepath)
        if error:
            return {"imported": 0, "skipped": 0, "errors": [error]}

        _, ext = os.path.splitext(filepath)
        ext = ext.lower()
        _, content = self.detect_format(filepath)

        if ext == '.ris':
            papers = self._parse_ris(filepath)
        elif ext == '.bib':
            papers = self._parse_bibtex(filepath)
        elif ext == '.csv':
            papers = self._parse_csv(filepath)
        elif ext == '.txt':
            first_line = content.splitlines()[0] if content.strip() else ""
            if ',' in first_line and any(k in first_line.lower() for k in ['title', 'author', 'doi', 'year']):
                papers = self._parse_csv(filepath)
            else:
                papers = self._parse_txt(filepath)
        else:
            return {"imported": 0, "skipped": 0, "errors": ["Unsupported file format"]}

        return self._save_to_db(papers, filepath)

    def _parse_ris(self, filepath):
        papers = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                entries = rispy.load(f)
                for entry in entries:
                    title = entry.get("title", entry.get("primary_title", ""))
                    if not title:
                        title = entry.get("ti", entry.get("TI", entry.get("bt", entry.get("BT", ""))))
                        
                    abstract = entry.get("abstract", entry.get("notes", ""))
                    if not abstract:
                        abstract = entry.get("ab", entry.get("AB", ""))
                        
                    year = entry.get("year", entry.get("publication_year", ""))
                    if not year:
                        year = entry.get("y1", entry.get("Y1", ""))
                    year = year[:4] if year else ""
                    
                    doi = entry.get("doi", entry.get("m3", ""))
                    if not doi:
                        doi = entry.get("ur", entry.get("UR", ""))

                    paper = {
                        "title": title,
                        "abstract": abstract,
                        "authors": "; ".join(entry.get("authors", [])),
                        "year": year,
                        "doi": doi,
                        "pmid": entry.get("accession_number", "")
                    }
                    papers.append(paper)
        except Exception as e:
            logging.error(f"Error parsing RIS file {filepath}: {e}")
        return papers

    def _parse_bibtex(self, filepath):
        papers = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                parser = bibtexparser.bparser.BibTexParser(common_strings=True)
                bib_database = bibtexparser.load(f, parser=parser)
                for entry in bib_database.entries:
                    paper = {
                        "title": entry.get("title", ""),
                        "abstract": entry.get("abstract", ""),
                        "authors": entry.get("author", "").replace(" and ", "; "),
                        "year": entry.get("year", "")[:4],
                        "doi": entry.get("doi", ""),
                        "pmid": entry.get("pmid", "")
                    }
                    papers.append(paper)
        except Exception as e:
            logging.error(f"Error parsing BibTeX file {filepath}: {e}")
        return papers

    def _parse_csv(self, filepath):
        papers = []
        try:
            with open(filepath, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    return []
                
                # Create case-insensitive mappings
                fields = {f.lower(): f for f in reader.fieldnames}
                
                title_keys = ['title', 'ti']
                abstract_keys = ['abstract', 'ab']
                author_keys = ['authors', 'author', 'au', 'author full names']
                year_keys = ['year', 'py', 'publication year']
                doi_keys = ['doi', 'do']
                pmid_keys = ['pmid', 'pubmed id']

                def get_val(row, possible_keys):
                    for k in possible_keys:
                        if k in fields:
                            return row[fields[k]]
                    return ""

                for row in reader:
                    paper = {
                        "title": get_val(row, title_keys),
                        "abstract": get_val(row, abstract_keys),
                        "authors": get_val(row, author_keys),
                        "year": get_val(row, year_keys)[:4],
                        "doi": get_val(row, doi_keys),
                        "pmid": get_val(row, pmid_keys)
                    }
                    papers.append(paper)
        except Exception as e:
            logging.error(f"Error parsing CSV file {filepath}: {e}")
        return papers

    def _parse_txt(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(filepath, 'r', encoding='latin-1') as f:
                    content = f.read()
            except Exception as e:
                logging.error(f"Error reading TXT file {filepath} with latin-1: {e}")
                return []
        except Exception as e:
            logging.error(f"Error reading TXT file {filepath}: {e}")
            return []

        if not content.strip():
            return []
            
        first_non_empty = next((line for line in content.splitlines() if line.strip()), "")

        if "SEARCH QUERY" in content and "RECORD " in content and "TITLE" in content and "AUTHOR NAMES" in content:
            return self._parse_embase_txt(content)

        if first_non_empty.strip() == "Scopus" or content.startswith("Scopus\n") or ("EXPORT DATE:" in content and "AUTHOR FULL NAMES:" in content):
            return self._parse_scopus_txt(content)

        if "Title,Authors" in first_non_empty or "Authors,Title" in first_non_empty or '"Title","Author"' in first_non_empty or "Title,Author" in first_non_empty:
            return self._parse_csv(filepath)

        if "<records>" in content or "<?xml" in content:
            logging.warning("XML format detected — not yet supported. Please export as RIS or CSV instead.")
            return []

        first_5_lines = "\n".join(content.splitlines()[:5])
        if ("Embase" in first_5_lines or "EMBASE" in first_5_lines) and ("TI  -" in content or "AB  -" in content):
            return self._parse_pubmed_medline(content)
        
        if "<TI>" in content or "<AB>" in content:
            logging.warning("Embase XML detected — export as RIS instead")
            return []

        if "PMID-" in content or "FAU -" in content or "TI  -" in content:
            return self._parse_pubmed_medline(content)
        elif ("PT J" in content or "AU " in content) and "TI " in content:
            return self._parse_pubmed_medline(content)
        elif "ER  -" in content or content.lstrip().startswith("TY  -") or content.lstrip().startswith("TY -"):
            try:
                entries = rispy.loads(content)
                papers = []
                for entry in entries:
                    papers.append({
                        "title": entry.get("title", entry.get("primary_title", "")),
                        "abstract": entry.get("abstract", entry.get("notes", "")),
                        "authors": "; ".join(entry.get("authors", [])),
                        "year": entry.get("year", entry.get("publication_year", ""))[:4] if entry.get("year", entry.get("publication_year", "")) else "",
                        "doi": entry.get("doi", entry.get("m3", "")),
                        "pmid": entry.get("accession_number", "")
                    })
                return papers
            except Exception as e:
                logging.error(f"Error parsing RIS inside TXT file {filepath}: {e}")
                return []
        elif "VR 1.0" in content or "FN Clarivate" in content or "FN Thomson Reuters" in content:
            return self._parse_wos(content)
        else:
            try:
                entries = rispy.loads(content)
                papers = []
                for entry in entries:
                    paper = {
                        "title": entry.get("title", entry.get("primary_title", "")),
                        "abstract": entry.get("abstract", entry.get("notes", "")),
                        "authors": "; ".join(entry.get("authors", [])),
                        "year": entry.get("year", entry.get("publication_year", ""))[:4] if entry.get("year", entry.get("publication_year", "")) else "",
                        "doi": entry.get("doi", entry.get("m3", "")),
                        "pmid": entry.get("accession_number", "")
                    }
                    papers.append(paper)
                return papers
            except Exception:
                logging.warning(f"TXT format not recognized for file: {filepath}")
                return []

    def _clean_authors(self, raw):
        import re
        raw = raw.strip()
        raw = re.sub(r'\(\d+\)', '', raw).strip()
        if ';' in raw:
            return raw
        elif ',' in raw:
            return raw
        return raw

    def _parse_pubmed_medline(self, content):
        papers = []
        import re
        content = content.replace('\r', '')
        records = re.split(r'\n\s*\n', content)
        
        for record in records:
            if not record.strip():
                continue
            title = ""
            abstract = ""
            authors = []
            year = ""
            doi = ""
            pmid = ""
            
            lines = record.split('\n')
            is_hyphen_format = any('-' in line for line in lines[:5])
            
            current_tag = None
            for line in lines:
                if not line.strip():
                    continue
                
                if line.startswith(' ') and current_tag:
                    val = line.strip()
                    if current_tag == "TI":
                        title += " " + val
                    elif current_tag == "AB":
                        abstract += " " + val
                    continue
                
                if '-' in line and is_hyphen_format:
                    parts = line.split('-', 1)
                    tag = parts[0].strip()
                    val = parts[1].strip()
                else:
                    parts = line.split(' ', 1)
                    tag = parts[0].strip()
                    val = parts[1].strip() if len(parts) > 1 else ""
                
                current_tag = tag
                
                if tag == "TI":
                    title = val
                elif tag == "AB":
                    abstract = val
                elif tag in ["FAU", "AU"]:
                    authors.append(val)
                elif tag == "DP" or tag == "PY":
                    year = val[:4]
                elif tag == "AID" or tag == "DI":
                    if "[doi]" in val:
                        doi = val.replace("[doi]", "").strip()
                    elif tag == "DI":
                        doi = val.strip()
                elif tag == "PMID":
                    pmid = val
                    
            if title or abstract:
                papers.append({
                    "title": title.strip(),
                    "abstract": abstract.strip(),
                    "authors": "; ".join(authors),
                    "year": year,
                    "doi": doi,
                    "pmid": pmid
                })
        return papers

    def _parse_embase_txt(self, content):
        papers = []
        import re
        lines = content.splitlines()
        
        # Find first RECORD
        start_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("RECORD "):
                start_idx = i
                break
                
        if start_idx == 0 and not lines[0].startswith("RECORD "):
            logging.warning("No RECORD separator found in Embase TXT")
            return []
            
        record_blocks = []
        current_block = []
        for line in lines[start_idx:]:
            if line.startswith("RECORD ") and current_block:
                record_blocks.append(current_block)
                current_block = [line]
            else:
                current_block.append(line)
        if current_block:
            record_blocks.append(current_block)
            
        for block in record_blocks:
            current_field = None
            fields = {}
            for line in block:
                # Field Header (ALL CAPS, no leading space)
                if line and not line.startswith(" ") and line.isupper():
                    current_field = line.strip()
                    fields[current_field] = []
                elif current_field and line.startswith("  "):
                    fields[current_field].append(line.strip())
                    
            # Join field lines
            for k in fields:
                fields[k] = " ".join(fields[k]).strip()
                
            title = fields.get("TITLE", "")
            if not title:
                continue
                
            abstract = fields.get("ABSTRACT", "")
            raw_authors = fields.get("AUTHOR NAMES", "")
            if raw_authors:
                cleaned_authors = [a.strip() for a in raw_authors.split(";")]
                raw_authors = "; ".join(cleaned_authors)
            authors = self._clean_authors(raw_authors)
            
            year = fields.get("PUBLICATION YEAR", "")[:4]
            doi = fields.get("DOI", "").strip()
            if not doi:
                source = fields.get("SOURCE", "")
                doi_match = re.search(r'doi\.org/(.*?)(?:\s|$)', source)
                if doi_match:
                    doi = doi_match.group(1)
            
            pmid = fields.get("PMID", "").strip()
            
            papers.append({
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "year": year,
                "doi": doi,
                "pmid": pmid
            })
            
        logging.info(f"Parsed {len(papers)} records from Embase TXT")
        if len(papers) == 0:
            # Log only the record count and file size — never file content
            logging.warning("Zero records parsed from Embase TXT file (check format)")
        return papers

    def _parse_scopus_txt(self, content):
        papers = []
        import re
        
        content = content.replace('\r', '')
        blocks = re.split(r'\n\n+', content)
        
        for block in blocks:
            if "Scopus" in block and "EXPORT DATE:" in block:
                continue
                
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue
                
            authors_line = lines[0]
            authors = self._clean_authors(authors_line)
            
            title = ""
            year = ""
            doi = ""
            abstract = ""
            
            title_idx = -1
            for i, line in enumerate(lines):
                if line.startswith("AUTHOR FULL NAMES:"):
                    # Title should be the next non-digit plain text line
                    for j in range(i + 1, len(lines)):
                        test_line = lines[j]
                        if not re.match(r'^[\d; ]+$', test_line) and not test_line.startswith("http") and not test_line.startswith("DOI:"):
                            title = test_line
                            title_idx = j
                            break
                    break
                    
            if not title or title.startswith("http") or re.match(r'^[\d; ]+$', title):
                continue
                
            for line in lines:
                year_match = re.search(r'\((\d{4})\)', line)
                if year_match:
                    year = year_match.group(1)
                    
                if line.startswith("DOI: "):
                    doi = line[5:].strip()
                    
                if line.startswith("ABSTRACT: "):
                    abstract = line[10:].strip()
            
            papers.append({
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "year": year,
                "doi": doi,
                "pmid": ""
            })
            
        logging.info(f"Parsed {len(papers)} records from Scopus TXT")
        if len(papers) == 0:
            logging.warning("Zero records parsed from Scopus TXT file (check format)")
        return papers

    def _parse_wos(self, content):
        papers = []
        import re
        content = content.replace('\r', '')
        records = re.split(r'\nER\b', content)
        
        for record in records:
            if not record.strip():
                continue
            title = ""
            abstract = ""
            authors = []
            year = ""
            doi = ""
            
            lines = record.split('\n')
            current_tag = None
            
            for line in lines:
                if len(line) < 2:
                    continue
                
                tag = line[:2]
                val = line[3:].strip() if len(line) > 2 else ""
                
                if tag != "  ":
                    current_tag = tag
                else:
                    val = line.strip()
                    
                if current_tag == "TI":
                    title = title + " " + val if title else val
                elif current_tag == "AB":
                    abstract = abstract + " " + val if abstract else val
                elif current_tag == "AU":
                    if tag == "AU":
                        authors.append(val)
                    else:
                        if authors:
                            authors[-1] += " " + val
                        else:
                            authors.append(val)
                elif current_tag == "PY" and tag == "PY":
                    year = val[:4]
                elif current_tag == "DI" and tag == "DI":
                    doi = val

            if title or abstract:
                papers.append({
                    "title": title.strip(),
                    "abstract": abstract.strip(),
                    "authors": "; ".join(authors),
                    "year": year,
                    "doi": doi,
                    "pmid": ""
                })
        return papers

    # Maximum field lengths — prevent memory exhaustion from crafted imports
    _MAX_TITLE    = 2_000
    _MAX_ABSTRACT = 100_000
    _MAX_AUTHORS  = 5_000
    _MAX_MISC     = 500

    @staticmethod
    def _safe_year(raw: str) -> str:
        """Return a 4-digit year string, or empty string if invalid."""
        import re
        if not raw:
            return ""
        m = re.search(r'\b(1[5-9]\d\d|20\d\d)\b', str(raw))
        return m.group(1) if m else ""

    def _save_to_db(self, papers, source_file):
        imported = 0
        skipped = 0
        errors = []
        # Store only the filename — never expose full OS paths in the DB (C6)
        safe_source = os.path.basename(str(source_file))

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            for paper in papers:
                # --- Length-cap all fields (M2) ---
                title    = (paper.get("title",    "") or "").strip()[:self._MAX_TITLE]
                abstract = (paper.get("abstract", "") or "").strip()[:self._MAX_ABSTRACT]
                authors  = (paper.get("authors",  "") or "").strip()[:self._MAX_AUTHORS]
                year     = self._safe_year(paper.get("year", ""))  # validated (M5)
                doi      = (paper.get("doi",  "") or "").strip()[:self._MAX_MISC]
                pmid     = (paper.get("pmid", "") or "").strip()[:self._MAX_MISC]

                if not title:
                    skipped += 1
                    continue

                if doi:
                    cursor.execute("SELECT id FROM papers WHERE doi=?", (doi,))
                    if cursor.fetchone():
                        skipped += 1
                        continue

                cursor.execute("SELECT id FROM papers WHERE title=?", (title,))
                if cursor.fetchone():
                    skipped += 1
                    continue

                cursor.execute(
                    "INSERT INTO papers (title, abstract, authors, year, doi, pmid, source_file) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (title, abstract, authors, year, doi, pmid, safe_source),
                )
                imported += 1

            conn.commit()
        except sqlite3.Error as e:
            logging.error(f"DB error in _save_to_db: {e}")
            errors.append(f"Database error: {e}")
        finally:
            conn.close()   # always close — fix for C2

        return {"imported": imported, "skipped": skipped, "errors": errors}

    def get_all_papers(self):
        papers = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM papers ORDER BY id DESC")
            rows = cursor.fetchall()
            for row in rows:
                papers.append(dict(row))
            conn.close()
        except sqlite3.Error as e:
            logging.error(f"Error fetching papers: {e}")
        return papers

    def get_stats(self):
        stats = {
            "total": 0,
            "pending": 0,
            "included": 0,
            "excluded": 0,
            "uncertain": 0
        }
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM papers")
            stats["total"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT screening_decision, COUNT(*) FROM papers GROUP BY screening_decision")
            for row in cursor.fetchall():
                decision = row[0]
                count = row[1]
                if decision == 'pending':
                    stats["pending"] = count
                elif decision == 'include':
                    stats["included"] = count
                elif decision == 'exclude':
                    stats["excluded"] = count
                elif decision == 'uncertain':
                    stats["uncertain"] = count
                    
            conn.close()
        except sqlite3.Error as e:
            logging.error(f"Error fetching stats: {e}")
            
        return stats

    def get_abstract_coverage(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM papers")
        total = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM papers "
            "WHERE abstract IS NOT NULL AND abstract != '' AND length(trim(abstract)) > 10"
        )
        with_abstract = cur.fetchone()[0]
        cur.execute(
            "SELECT source_file, COUNT(*) as total, "
            "SUM(CASE WHEN abstract IS NOT NULL AND abstract != '' "
            "AND length(trim(abstract)) > 10 THEN 1 ELSE 0 END) as has_abstract "
            "FROM papers GROUP BY source_file"
        )
        by_source = [
            {
                "source": row[0],
                "total": row[1],
                "with_abstract": row[2],
                "pct": round(row[2] / row[1] * 100, 1) if row[1] > 0 else 0
            }
            for row in cur.fetchall()
        ]
        conn.close()
        return {
            "total": total,
            "with_abstract": with_abstract,
            "without_abstract": total - with_abstract,
            "coverage_pct": round(with_abstract / total * 100, 1) if total > 0 else 0,
            "by_source": by_source
        }

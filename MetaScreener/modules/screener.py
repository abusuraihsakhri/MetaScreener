import sqlite3, logging
from config import Config
from modules.ollama_client import Screener as AIScreener

class ScreeningManager:
    def __init__(self):
        self.db_path = Config.DB_PATH
        self.ai = AIScreener()

    def get_pending_papers(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id, title, abstract, authors, year, doi, pmid FROM papers WHERE is_duplicate = 0 AND screening_decision = 'pending'")
        rows = cur.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_screened_papers(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id, title, abstract, authors, year, doi, pmid, screening_decision, screening_reason, screening_confidence FROM papers WHERE is_duplicate = 0 AND screening_decision != 'pending'")
        rows = cur.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def save_decision(self, paper_id, decision, reason="", confidence=None):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("UPDATE papers SET screening_decision = ?, screening_reason = ?, screening_confidence = ? WHERE id = ?", (decision, reason, confidence, paper_id))
        conn.commit()
        conn.close()

    def get_screening_stats(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate = 0")
        total_unique = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate = 0 AND screening_decision = 'pending'")
        pending = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate = 0 AND screening_decision = 'include'")
        included = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate = 0 AND screening_decision = 'exclude'")
        excluded = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate = 0 AND screening_decision = 'uncertain'")
        uncertain = cur.fetchone()[0]
        
        conn.close()
        
        progress_pct = 0.0
        handled = included + excluded + uncertain
        if total_unique > 0:
            progress_pct = round(handled / total_unique * 100, 1)
            
        return {
            "total_unique": total_unique,
            "pending": pending,
            "included": included,
            "excluded": excluded,
            "uncertain": uncertain,
            "progress_pct": progress_pct
        }

    def undo_last_decision(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # In SQLite, rowid increases unless explicitly disabled.
        # However, to be safer, we'd need a timestamp.
        # Since we don't have one, we'll use rowid or a subquery.
        # The prompt says "most recently updated paper where screening_decision != 'pending' ORDER BY rowid DESC LIMIT 1"
        cur.execute("SELECT * FROM papers WHERE is_duplicate = 0 AND screening_decision != 'pending' ORDER BY rowid DESC LIMIT 1")
        row = cur.fetchone()
        
        if row:
            paper_id = row["id"]
            cur.execute("UPDATE papers SET screening_decision = 'pending', screening_reason = '', screening_confidence = NULL WHERE id = ?", (paper_id,))
            conn.commit()
            paper_dict = dict(row)
            conn.close()
            return paper_dict
        
        conn.close()
        return None

    def bulk_ai_screen(self, progress_callback=None):
        pending = self.get_pending_papers()
        if not pending:
            return
            
        results = self.ai.screen_batch(pending, progress_callback)
        for res in results:
            self.save_decision(
                res["paper_id"], 
                res.get("decision", "uncertain"), 
                res.get("reason", ""), 
                res.get("confidence")
            )

    def debug_paper_data(self, paper_id):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return {"error": f"Paper ID {paper_id} not found in database"}
        data = dict(row)
        return {
            "id": data.get("id"),
            "title": data.get("title", ""),
            "title_length": len(data.get("title", "") or ""),
            "abstract": data.get("abstract", ""),
            "abstract_length": len(data.get("abstract", "") or ""),
            "abstract_is_null": data.get("abstract") is None,
            "abstract_is_empty": (data.get("abstract") or "").strip() == "",
            "authors": data.get("authors", ""),
            "year": data.get("year", ""),
            "doi": data.get("doi", ""),
            "source_file": data.get("source_file", ""),
        }

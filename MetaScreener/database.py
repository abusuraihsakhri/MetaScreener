import sqlite3
import logging
from config import Config


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe multi-process writes
    conn.execute("PRAGMA foreign_keys=ON")    # enforce FK constraints
    conn.execute("PRAGMA synchronous=NORMAL") # balance safety vs speed
    return conn


def init_db():
    conn = _get_conn()
    try:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            abstract TEXT,
            authors TEXT,
            year TEXT,
            doi TEXT,
            pmid TEXT,
            source_file TEXT,
            is_duplicate INTEGER DEFAULT 0,
            screening_decision TEXT DEFAULT 'pending',
            screening_reason TEXT,
            screening_confidence INTEGER,
            fulltext_decision TEXT DEFAULT 'pending',
            fulltext_reason TEXT,
            pdf_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS extraction (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER,
            field_name TEXT,
            field_value TEXT,
            ai_suggested INTEGER DEFAULT 0,
            human_verified INTEGER DEFAULT 0,
            FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
        )
        """)

        # Indexes for common query patterns
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_decision ON papers(screening_decision)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_duplicate ON papers(is_duplicate)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_extraction_paper ON extraction(paper_id)")

        conn.commit()
        logging.info("Database initialised with WAL mode and FK enforcement")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()

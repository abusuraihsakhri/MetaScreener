import sqlite3
import logging
from contextlib import contextmanager
from config import Config


@contextmanager
def get_db():
    """Context manager yielding a row-factory connection that auto-closes."""
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
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
        );

        CREATE TABLE IF NOT EXISTS extraction (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER,
            field_name TEXT,
            field_value TEXT,
            ai_suggested INTEGER DEFAULT 0,
            human_verified INTEGER DEFAULT 0,
            FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_papers_decision
            ON papers(screening_decision);
        CREATE INDEX IF NOT EXISTS idx_papers_duplicate
            ON papers(is_duplicate);
        CREATE INDEX IF NOT EXISTS idx_extraction_paper
            ON extraction(paper_id);
        """)
    logging.info("Database initialised")

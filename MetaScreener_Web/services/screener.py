from services.database import get_db
from services.ai_client import screen_abstract


def get_stats() -> dict:
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate=0").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate=0 AND screening_decision='pending'").fetchone()[0]
        included = conn.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate=0 AND screening_decision='include'").fetchone()[0]
        excluded = conn.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate=0 AND screening_decision='exclude'").fetchone()[0]
        uncertain = conn.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate=0 AND screening_decision='uncertain'").fetchone()[0]
    handled = included + excluded + uncertain
    progress = round(handled / total * 100, 1) if total else 0.0
    return {
        "total": total, "pending": pending, "included": included,
        "excluded": excluded, "uncertain": uncertain, "progress": progress,
    }


def get_pending_papers() -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, abstract, authors, year, doi, pmid "
            "FROM papers WHERE is_duplicate=0 AND screening_decision='pending' ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def get_paper(paper_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()
    return dict(row) if row else None


def get_all_papers(decision_filter: str = None) -> list:
    with get_db() as conn:
        if decision_filter:
            rows = conn.execute(
                "SELECT id, title, abstract, authors, year, doi, pmid, screening_decision, screening_confidence "
                "FROM papers WHERE is_duplicate=0 AND screening_decision=? ORDER BY id",
                (decision_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, abstract, authors, year, doi, pmid, screening_decision, screening_confidence "
                "FROM papers WHERE is_duplicate=0 ORDER BY id"
            ).fetchall()
    return [dict(r) for r in rows]


def save_decision(paper_id: int, decision: str, reason: str = "", confidence: int = None):
    if decision not in ("include", "exclude", "uncertain", "pending"):
        raise ValueError(f"Invalid decision: {decision}")
    with get_db() as conn:
        conn.execute(
            "UPDATE papers SET screening_decision=?, screening_reason=?, screening_confidence=? WHERE id=?",
            (decision, reason, confidence, paper_id),
        )


def ai_screen_paper(paper_id: int) -> dict:
    paper = get_paper(paper_id)
    if not paper:
        raise ValueError(f"Paper {paper_id} not found")
    result = screen_abstract(paper["title"], paper["abstract"])
    save_decision(paper_id, result["decision"], result.get("reason", ""), result.get("confidence"))
    return result


def undo_last() -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM papers WHERE is_duplicate=0 AND screening_decision!='pending' "
            "ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE papers SET screening_decision='pending', screening_reason='', screening_confidence=NULL WHERE id=?",
                (row["id"],),
            )
            return dict(row)
    return None

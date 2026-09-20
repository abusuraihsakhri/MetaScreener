"""
File import service — parses RIS, BibTeX, CSV, TXT reference files.
Security: no file content is logged; size limit enforced by Flask config.
"""
import csv
import io
import logging
import os
import re

from services.database import get_db


ALLOWED_EXTENSIONS = {"ris", "bib", "csv", "txt"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _safe_read(filepath: str) -> str:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(filepath, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return ""


def import_file(filepath: str, original_filename: str) -> dict:
    ext = os.path.splitext(original_filename)[1].lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        return {"imported": 0, "skipped": 0, "errors": ["Unsupported file format"]}

    if ext == "ris":
        papers = _parse_ris(filepath)
    elif ext == "bib":
        papers = _parse_bibtex(filepath)
    elif ext == "csv":
        papers = _parse_csv(filepath)
    elif ext == "txt":
        content = _safe_read(filepath)
        first = content.splitlines()[0] if content.strip() else ""
        if "," in first and any(k in first.lower() for k in ("title", "author", "doi", "year")):
            papers = _parse_csv(filepath)
        else:
            papers = _parse_txt(content)
    else:
        return {"imported": 0, "skipped": 0, "errors": ["Unsupported format"]}

    return _save_to_db(papers, original_filename)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_ris(filepath: str) -> list:
    import rispy
    papers = []
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            entries = rispy.load(f)
        for e in entries:
            title = e.get("title") or e.get("primary_title") or ""
            abstract = e.get("abstract") or ""
            authors_list = e.get("authors") or e.get("first_authors") or []
            authors = "; ".join(authors_list) if isinstance(authors_list, list) else str(authors_list)
            year = str(e.get("year") or e.get("publication_year") or "")
            doi = e.get("doi") or ""
            pmid = e.get("pmid") or e.get("accession_number") or ""
            if title:
                papers.append({"title": title, "abstract": abstract, "authors": authors,
                               "year": year, "doi": doi, "pmid": pmid})
    except Exception as exc:
        logging.error(f"RIS parse error: {exc}")
    return papers


def _parse_bibtex(filepath: str) -> list:
    import bibtexparser
    papers = []
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            db = bibtexparser.load(f)
        for e in db.entries:
            title = e.get("title", "").strip("{}")
            abstract = e.get("abstract", "")
            authors = e.get("author", "")
            year = e.get("year", "")
            doi = e.get("doi", "")
            pmid = e.get("pmid", "")
            if title:
                papers.append({"title": title, "abstract": abstract, "authors": authors,
                               "year": year, "doi": doi, "pmid": pmid})
    except Exception as exc:
        logging.error(f"BibTeX parse error: {exc}")
    return papers


def _parse_csv(filepath: str) -> list:
    papers = []
    content = _safe_read(filepath)
    try:
        reader = csv.DictReader(io.StringIO(content))
        col_map = {c.lower().strip(): c for c in (reader.fieldnames or [])}

        def get(row, *keys):
            for k in keys:
                for variant in (k, k.capitalize(), k.upper()):
                    if variant in row:
                        v = row[variant]
                        if v:
                            return str(v).strip()
            return ""

        for row in reader:
            title = get(row, "title", "article_title", "TI")
            if not title:
                continue
            papers.append({
                "title": title,
                "abstract": get(row, "abstract", "AB", "summary"),
                "authors": get(row, "authors", "author", "AU"),
                "year": get(row, "year", "publication_year", "PY", "date"),
                "doi": get(row, "doi", "DOI"),
                "pmid": get(row, "pmid", "PMID", "pubmed_id"),
            })
    except Exception as exc:
        logging.error(f"CSV parse error: {exc}")
    return papers


def _parse_txt(content: str) -> list:
    """Generic PubMed/Embase/WoS text format parser."""
    papers = []
    current: dict = {}
    field_map = {
        "TI": "title", "AB": "abstract", "AU": "authors",
        "FAU": "authors", "DP": "year", "PY": "year",
        "AID": "doi", "PMID": "pmid", "DO": "doi",
    }

    for line in content.splitlines():
        if "  - " in line:
            tag, _, value = line.partition("  - ")
            tag = tag.strip()
            value = value.strip()
            if tag == "ER":
                if current.get("title"):
                    papers.append(current)
                current = {}
            elif tag in field_map:
                key = field_map[tag]
                if key in current and current[key]:
                    current[key] += "; " + value if key == "authors" else " " + value
                else:
                    current[key] = value

    if current.get("title"):
        papers.append(current)
    return papers


# ---------------------------------------------------------------------------
# DB save
# ---------------------------------------------------------------------------

def _save_to_db(papers: list, source_file: str) -> dict:
    imported = skipped = 0
    errors = []

    with get_db() as conn:
        for p in papers:
            title = (p.get("title") or "").strip()
            if not title:
                skipped += 1
                continue
            doi = (p.get("doi") or "").strip().lower()
            pmid = (p.get("pmid") or "").strip()

            # Duplicate check
            if doi:
                row = conn.execute("SELECT id FROM papers WHERE doi = ? LIMIT 1", (doi,)).fetchone()
                if row:
                    skipped += 1
                    continue
            if pmid:
                row = conn.execute("SELECT id FROM papers WHERE pmid = ? LIMIT 1", (pmid,)).fetchone()
                if row:
                    skipped += 1
                    continue

            try:
                conn.execute(
                    """INSERT INTO papers (title, abstract, authors, year, doi, pmid, source_file)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        title,
                        (p.get("abstract") or "").strip(),
                        (p.get("authors") or "").strip(),
                        (p.get("year") or "").strip(),
                        doi,
                        pmid,
                        os.path.basename(source_file),
                    ),
                )
                imported += 1
            except Exception as exc:
                logging.error(f"DB insert error: {exc}")
                errors.append(str(exc))

    return {"imported": imported, "skipped": skipped, "errors": errors}

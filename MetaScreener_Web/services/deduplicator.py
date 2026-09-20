import logging
from rapidfuzz import fuzz
from services.database import get_db


TITLE_THRESHOLD = 92


def _all_papers() -> list:
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, title, doi, pmid, abstract, authors FROM papers WHERE is_duplicate=0"
        ).fetchall()]


def find_duplicates() -> list:
    """Return groups of duplicate papers using 4 detection methods."""
    papers = _all_papers()
    groups: list[set] = []

    # PMID exact
    pmid_map: dict = {}
    for p in papers:
        v = str(p.get("pmid") or "").strip()
        if v:
            pmid_map.setdefault(v, []).append(p["id"])
    for ids in pmid_map.values():
        if len(ids) > 1:
            groups.append(set(ids))

    # DOI exact
    doi_map: dict = {}
    for p in papers:
        v = str(p.get("doi") or "").strip().lower().replace("https://doi.org/", "")
        if v:
            doi_map.setdefault(v, []).append(p["id"])
    for ids in doi_map.values():
        if len(ids) > 1:
            groups.append(set(ids))

    # Title exact (normalised)
    def norm(t):
        import re
        return re.sub(r"\s+", " ", (t or "").lower().strip())

    title_map: dict = {}
    for p in papers:
        v = norm(p.get("title") or "")
        if v:
            title_map.setdefault(v, []).append(p["id"])
    for ids in title_map.values():
        if len(ids) > 1:
            groups.append(set(ids))

    # Title fuzzy
    titles = [(p["id"], norm(p.get("title") or "")) for p in papers]
    for i in range(len(titles)):
        for j in range(i + 1, len(titles)):
            if fuzz.token_sort_ratio(titles[i][1], titles[j][1]) >= TITLE_THRESHOLD:
                groups.append({titles[i][0], titles[j][0]})

    # Union-find merge
    parent = {p["id"]: p["id"] for p in papers}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for g in groups:
        lst = list(g)
        for k in lst[1:]:
            union(lst[0], k)

    clusters: dict = {}
    for p in papers:
        root = find(p["id"])
        clusters.setdefault(root, []).append(p)

    paper_by_id = {p["id"]: p for p in papers}
    result = []
    for root, members in clusters.items():
        if len(members) > 1:
            best = max(members, key=lambda p: sum(
                1 for k in ("title", "abstract", "doi", "pmid")
                if str(p.get(k) or "").strip()
            ))
            result.append({"papers": members, "keep_id": best["id"]})

    return result


def resolve_duplicates(keep_ids: list[int]):
    """Mark all papers in duplicate groups as duplicate except the kept ones."""
    dupes = find_duplicates()
    mark_duplicate = []
    for group in dupes:
        for p in group["papers"]:
            if p["id"] not in keep_ids:
                mark_duplicate.append(p["id"])

    if not mark_duplicate:
        return 0

    with get_db() as conn:
        conn.executemany(
            "UPDATE papers SET is_duplicate=1 WHERE id=?",
            [(pid,) for pid in mark_duplicate],
        )
    return len(mark_duplicate)


def get_stats() -> dict:
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        dupes = conn.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate=1").fetchone()[0]
    return {"total": total, "duplicates": dupes, "unique": total - dupes}

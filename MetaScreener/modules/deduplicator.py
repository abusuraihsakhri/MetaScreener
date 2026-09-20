import sqlite3
import logging
from rapidfuzz import fuzz
from config import Config
from PyQt6.QtCore import QThread, pyqtSignal

class Deduplicator:
    def __init__(self):
        self.db_path = Config.DB_PATH
        self.title_threshold = 92
        
    def get_non_duplicate_papers(self):
        papers = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM papers WHERE is_duplicate = 0")
            for row in cursor.fetchall():
                papers.append(dict(row))
            conn.close()
        except sqlite3.Error as e:
            logging.error(f"DB Error get_non_duplicate_papers: {e}")
        return papers
        
    def find_by_pmid(self):
        papers = self.get_non_duplicate_papers()
        pmid_groups = {}
        for p in papers:
            pmid = str(p.get("pmid", "")).strip()
            if pmid:
                pmid_groups.setdefault(pmid, []).append(p)
                
        results = []
        for pmid, group in pmid_groups.items():
            if len(group) > 1:
                best_keep = max(group, key=lambda p: sum(1 for k in ['title', 'abstract', 'doi', 'pmid'] if str(p.get(k, '')).strip() != ''))
                results.append({
                    "papers": group,
                    "similarity_score": 100,
                    "match_method": "PMID exact match",
                    "suggested_keep": best_keep
                })
        return results

    def find_by_doi(self):
        papers = self.get_non_duplicate_papers()
        doi_groups = {}
        for p in papers:
            doi = str(p.get("doi", "")).strip().lower()
            if doi:
                if doi.startswith("https://doi.org/"):
                    doi = doi[16:]
                doi_groups.setdefault(doi, []).append(p)
                
        results = []
        for doi, group in doi_groups.items():
            if len(group) > 1:
                best_keep = max(group, key=lambda p: sum(1 for k in ['title', 'abstract', 'doi', 'pmid'] if str(p.get(k, '')).strip() != ''))
                results.append({
                    "papers": group,
                    "similarity_score": 100,
                    "match_method": "DOI exact match",
                    "suggested_keep": best_keep
                })
        return results

    def find_by_title_exact(self):
        papers = self.get_non_duplicate_papers()
        title_groups = {}
        import re
        for p in papers:
            title = str(p.get("title", "")).strip().lower()
            if title:
                normalized = re.sub(r'[^\w\s]', '', title).strip()
                title_groups.setdefault(normalized, []).append(p)
                
        results = []
        for title, group in title_groups.items():
            if len(group) > 1:
                best_keep = max(group, key=lambda p: sum(1 for k in ['title', 'abstract', 'doi', 'pmid'] if str(p.get(k, '')).strip() != ''))
                results.append({
                    "papers": group,
                    "similarity_score": 100,
                    "match_method": "Title exact match",
                    "suggested_keep": best_keep
                })
        return results

    def find_by_title_fuzzy(self, threshold=None, progress_callback=None):
        if threshold is None:
            threshold = self.title_threshold
        papers = self.get_non_duplicate_papers()
        total_papers = len(papers)

        parent = {p['id']: p['id'] for p in papers}

        def find(i):
            # Iterative path compression — avoids RecursionError on large chains (C3)
            root = i
            while parent[root] != root:
                root = parent[root]
            while parent[i] != root:
                parent[i], i = root, parent[i]
            return root

        def union(i, j):
            root_i = find(i)
            root_j = find(j)
            if root_i != root_j:
                parent[root_i] = root_j
                
        comparisons = total_papers * (total_papers - 1) // 2
        current = 0
        
        for i in range(total_papers):
            title_a = str(papers[i].get('title', '')).lower()
            if not title_a:
                continue
            for j in range(i + 1, total_papers):
                current += 1
                if progress_callback and current % 100 == 0:
                    progress_callback(current, comparisons)
                
                title_b = str(papers[j].get('title', '')).lower()
                if not title_b:
                    continue
                    
                score = fuzz.token_sort_ratio(title_a, title_b)
                if score >= threshold:
                    union(papers[i]['id'], papers[j]['id'])

            if progress_callback and i % 10 == 0:
                progress_callback(current, comparisons)

        if progress_callback:
            progress_callback(comparisons, comparisons)

        groups = {} 
        for p in papers:
            root = find(p['id'])
            if root not in groups:
                groups[root] = []
            groups[root].append(p)
            
        results = []
        for root, group_papers in groups.items():
            if len(group_papers) > 1:
                max_score = 0
                for i in range(len(group_papers)):
                    for j in range(i+1, len(group_papers)):
                        sc = fuzz.token_sort_ratio(
                            str(group_papers[i].get('title', '')).lower(), 
                            str(group_papers[j].get('title', '')).lower()
                        )
                        if sc > max_score:
                            max_score = sc
                            
                best_keep = max(group_papers, key=lambda p: sum(1 for k in ['title', 'abstract', 'doi', 'pmid'] if str(p.get(k, '')).strip() != ''))
                        
                results.append({
                    "papers": group_papers,
                    "similarity_score": max_score,
                    "match_method": f"Title fuzzy {int(max_score)}%",
                    "suggested_keep": best_keep
                })
                
        return results

    def find_all_duplicates(self, methods, fuzzy_threshold=92, progress_callback=None):
        all_groups = []
        if "pmid" in methods:
            all_groups.extend(self.find_by_pmid())
        if "doi" in methods:
            all_groups.extend(self.find_by_doi())
        if "title_exact" in methods:
            all_groups.extend(self.find_by_title_exact())
        if "title_fuzzy" in methods:
            all_groups.extend(self.find_by_title_fuzzy(threshold=fuzzy_threshold, progress_callback=progress_callback))
            
        # Merge overlapping groups
        parent = {}
        for group in all_groups:
            for p in group["papers"]:
                if p["id"] not in parent:
                    parent[p["id"]] = p["id"]

        def find(i):
            # Iterative path compression — avoids RecursionError on large chains (C3)
            root = i
            while parent.get(root, root) != root:
                root = parent[root]
            while parent.get(i, i) != root:
                parent[i], i = root, parent[i]
            return root

        def union(i, j):
            root_i = find(i)
            root_j = find(j)
            if root_i != root_j:
                parent[root_i] = root_j
                
        for group in all_groups:
            papers = group["papers"]
            if not papers: continue
            first_id = papers[0]["id"]
            for p in papers[1:]:
                union(first_id, p["id"])
                
        merged = {}
        paper_lookup = {}
        method_lookup = {}
        score_lookup = {}
        
        for group in all_groups:
            for p in group["papers"]:
                paper_lookup[p["id"]] = p
            root = find(group["papers"][0]["id"])
            method_lookup.setdefault(root, set()).add(group["match_method"])
            score_lookup[root] = max(score_lookup.get(root, 0), group["similarity_score"])
            
        for pid in parent.keys():
            root = find(pid)
            if root not in merged:
                merged[root] = []
            merged[root].append(paper_lookup[pid])
            
        final_results = []
        for root, group_papers in merged.items():
            if len(group_papers) > 1:
                methods_caught = list(method_lookup.get(root, set()))
                best_keep = max(group_papers, key=lambda p: sum(1 for k in ['title', 'abstract', 'doi', 'pmid'] if str(p.get(k, '')).strip() != ''))
                final_results.append({
                    "papers": group_papers,
                    "similarity_score": score_lookup.get(root, 100),
                    "match_methods": methods_caught,
                    "suggested_keep": best_keep
                })
                
        return final_results

    def build_similarity_matrix(self, max_papers=500):
        papers = self.get_non_duplicate_papers()
        truncated = False
        if len(papers) > max_papers:
            papers = papers[:max_papers]
            truncated = True
            
        headers = [{"id": p["id"], "title": str(p.get("title", ""))[:60]} for p in papers]
        scores = [[0 for _ in range(len(papers))] for _ in range(len(papers))]
        
        for i in range(len(papers)):
            title_a = str(papers[i].get('title', '')).lower()
            scores[i][i] = 100
            for j in range(i + 1, len(papers)):
                title_b = str(papers[j].get('title', '')).lower()
                sc = fuzz.token_sort_ratio(title_a, title_b)
                scores[i][j] = sc
                scores[j][i] = sc
                
        return {
            "papers": headers,
            "scores": scores,
            "truncated": truncated
        }

    def mark_as_duplicate(self, paper_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE papers SET is_duplicate = 1 WHERE id = ?", (paper_id,))
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logging.error(f"DB Error mark_as_duplicate: {e}")

    def mark_as_not_duplicate(self, paper_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE papers SET is_duplicate = 0 WHERE id = ?", (paper_id,))
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logging.error(f"DB Error mark_as_not_duplicate: {e}")

    def auto_resolve(self, duplicate_groups):
        resolved = 0
        kept = 0
        for group in duplicate_groups:
            keep_id = group["suggested_keep"]["id"]
            kept += 1
            for p in group["papers"]:
                if p["id"] != keep_id:
                    self.mark_as_duplicate(p["id"])
                    resolved += 1
                    
        return {"resolved": resolved, "kept": kept}

    def get_duplicate_stats(self):
        stats = {"total": 0, "unique": 0, "duplicates": 0}
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM papers")
            stats["total"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT is_duplicate, COUNT(*) FROM papers GROUP BY is_duplicate")
            for row in cursor.fetchall():
                val = row[0]
                count = row[1]
                if val == 1:
                    stats["duplicates"] = count
                elif val == 0:
                    stats["unique"] = count
                    
            conn.close()
        except sqlite3.Error as e:
            logging.error(f"DB Error get_duplicate_stats: {e}")
            
        return stats

class DuplicateSearchWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list)
    
    def __init__(self, deduplicator, methods, fuzzy_threshold):
        super().__init__()
        self.deduplicator = deduplicator
        self.methods = methods
        self.fuzzy_threshold = fuzzy_threshold
        
    def run(self):
        res = self.deduplicator.find_all_duplicates(
            methods=self.methods,
            fuzzy_threshold=self.fuzzy_threshold,
            progress_callback=lambda current, total: self.progress.emit(current, total)
        )
        self.finished.emit(res)

class SimilarityMatrixWorker(QThread):
    finished = pyqtSignal(dict)
    
    def __init__(self, deduplicator):
        super().__init__()
        self.deduplicator = deduplicator
        
    def run(self):
        res = self.deduplicator.build_similarity_matrix()
        self.finished.emit(res)

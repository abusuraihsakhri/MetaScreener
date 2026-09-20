import sqlite3
import os
try:
    import fitz  # PyMuPDF
except ImportError:
    # We will assume it's installed or user will install it.
    pass
from config import Config

class PRISMAGenerator:
    def __init__(self):
        self.db_path = Config.DB_PATH

    def get_prisma_numbers(self):
        numbers = {
            "identified_total": 0,
            "identified_by_db": {
                "PubMed": 0,
                "Embase": 0,
                "Scopus": 0,
                "WoS": 0,
                "Other": 0
            },
            "duplicates_removed": 0,
            "screened": 0,
            "excluded_screening": 0,
            "sought_retrieval": 0,
            "not_retrieved": 0,
            "assessed_eligibility": 0,
            "excluded_fulltext": 0,
            "included_final": 0
        }
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Total identified
            cursor.execute("SELECT COUNT(*) FROM papers")
            numbers["identified_total"] = cursor.fetchone()[0]
            
            # Identified by DB
            cursor.execute("SELECT source_file, COUNT(*) FROM papers GROUP BY source_file")
            rows = cursor.fetchall()
            for row in rows:
                source = str(row[0]).lower()
                count = row[1]
                if 'pubmed' in source:
                    numbers["identified_by_db"]["PubMed"] += count
                elif 'embase' in source:
                    numbers["identified_by_db"]["Embase"] += count
                elif 'scopus' in source:
                    numbers["identified_by_db"]["Scopus"] += count
                elif 'wos' in source or 'web of science' in source:
                    numbers["identified_by_db"]["WoS"] += count
                else:
                    numbers["identified_by_db"]["Other"] += count
            
            # Duplicates removed
            cursor.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate = 1")
            numbers["duplicates_removed"] = cursor.fetchone()[0]
            
            # Screened
            cursor.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate = 0")
            numbers["screened"] = cursor.fetchone()[0]
            
            # Excluded screening
            cursor.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate = 0 AND screening_decision = 'exclude'")
            numbers["excluded_screening"] = cursor.fetchone()[0]
            
            # Sought retrieval
            cursor.execute("SELECT COUNT(*) FROM papers WHERE is_duplicate = 0 AND screening_decision = 'include'")
            numbers["sought_retrieval"] = cursor.fetchone()[0]
            
            # Not retrieved
            cursor.execute("SELECT COUNT(*) FROM papers WHERE screening_decision = 'include' AND (pdf_path IS NULL OR pdf_path = '')")
            numbers["not_retrieved"] = cursor.fetchone()[0]
            
            # Assessed eligibility (fulltext_decision != 'pending')
            # Check if column exists first since it might be new
            cursor.execute("PRAGMA table_info(papers)")
            cols = [col[1] for col in cursor.fetchall()]
            
            if 'fulltext_decision' in cols:
                # "Assessed for eligibility" represents reports sought and successfully retrieved
                cursor.execute("SELECT COUNT(*) FROM papers WHERE screening_decision = 'include' AND pdf_path IS NOT NULL AND pdf_path != ''")
                numbers["assessed_eligibility"] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM papers WHERE fulltext_decision = 'exclude'")
                numbers["excluded_fulltext"] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM papers WHERE fulltext_decision = 'include'")
                numbers["included_final"] = cursor.fetchone()[0]
            
            conn.close()
        except Exception as e:
            print(f"Error getting PRISMA stats: {e}")
            
        return numbers

    def generate_prisma_image(self, output_path):
        nums = self.get_prisma_numbers()
        
        # Create a blank white page
        doc = fitz.open()
        page = doc.new_page(width=800, height=1000)
        
        # Style helper
        font_size = 10
        header_font_size = 11
        
        def draw_box(rect, text, fill_color=(1,1,1), is_header=False):
            # rect: (x, y, w, h)
            x, y, w, h = rect
            # Draw border
            shape = page.new_shape()
            r = fitz.Rect(x, y, x+w, y+h)
            shape.draw_rect(r)
            shape.finish(width=1.5, fill=fill_color, color=(0,0,0))
            shape.commit()
            
            # Draw text
            fsize = header_font_size if is_header else font_size
            font = "hebo" if is_header else "helv"
            
            # Multi-line text centering
            lines = text.split('\n')
            total_h = len(lines) * fsize * 1.2
            start_y = y + (h - total_h) / 2 + fsize
            
            for line in lines:
                tw = fitz.get_text_length(line, fontname=font, fontsize=fsize)
                tx = x + (w - tw) / 2
                page.insert_text((tx, start_y), line, fontname=font, fontsize=fsize, color=(0,0,0))
                start_y += fsize * 1.2

        def draw_arrow(start, end):
            # start, end: (x, y)
            shape = page.new_shape()
            shape.draw_line(fitz.Point(start), fitz.Point(end))
            shape.finish(width=1.2, color=(0.2, 0.2, 0.2))
            
            # Arrow head
            # very simple head
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            import math
            angle = math.atan2(dy, dx)
            head_len = 8
            p1 = (end[0] - head_len * math.cos(angle - math.pi/6), end[1] - head_len * math.sin(angle - math.pi/6))
            p2 = (end[0] - head_len * math.cos(angle + math.pi/6), end[1] - head_len * math.sin(angle + math.pi/6))
            shape.draw_line(fitz.Point(end), fitz.Point(p1))
            shape.draw_line(fitz.Point(end), fitz.Point(p2))
            shape.finish(width=1.2, color=(0.2, 0.2, 0.2))
            shape.commit()

        # Identification
        draw_box((20, 30, 760, 35), "Identification of studies via databases and registers", fill_color=(0.91, 0.91, 0.91), is_header=True)
        
        db_details = "\n".join([f"{k} (n={v})" for k, v in nums["identified_by_db"].items() if v > 0])
        box1_text = f"Records identified from databases\n(n = {nums['identified_total']})"
        if db_details:
             box1_text += f"\n{db_details}"
             
        draw_box((50, 80, 320, 100), box1_text)
        draw_box((430, 80, 320, 70), f"Duplicates removed\n(n = {nums['duplicates_removed']})")
        draw_arrow((370, 130), (430, 130)) # Arrow 1 to 2
        
        # Screening
        draw_box((20, 200, 760, 35), "Screening", fill_color=(0.91, 0.91, 0.91), is_header=True)
        draw_box((50, 250, 320, 70), f"Records screened\n(n = {nums['screened']})")
        draw_box((430, 250, 320, 70), f"Records excluded at screening\n(n = {nums['excluded_screening']})")
        draw_arrow((210, 180), (210, 250)) # Arrow 1 down to 3
        draw_arrow((370, 285), (430, 285)) # Arrow 3 right to 4
        
        draw_box((50, 380, 320, 70), f"Reports sought for retrieval\n(n = {nums['sought_retrieval']})")
        draw_box((430, 380, 320, 70), f"Reports not retrieved\n(n = {nums['not_retrieved']})")
        draw_arrow((210, 320), (210, 380)) # Arrow 3 down to 5
        draw_arrow((370, 415), (430, 415)) # Arrow 5 right to 6
        
        # Eligibility
        draw_box((20, 510, 760, 35), "Eligibility", fill_color=(0.91, 0.91, 0.91), is_header=True)
        draw_box((50, 560, 320, 70), f"Reports assessed for eligibility\n(n = {nums['assessed_eligibility']})")
        draw_box((430, 560, 320, 70), f"Reports excluded\n(n = {nums['excluded_fulltext']})")
        draw_arrow((210, 450), (210, 560)) # Arrow 5 down to 7
        draw_arrow((370, 595), (430, 595)) # Arrow 7 right to 8
        
        # Included
        draw_box((20, 690, 760, 35), "Included", fill_color=(0.91, 0.91, 0.91), is_header=True)
        draw_box((50, 740, 320, 80), f"Studies included in review\n(n = {nums['included_final']})")
        draw_arrow((210, 630), (210, 740)) # Arrow 7 down to 9
        
        # Section Labels on left margin (rotated)
        labels = [("Identification", 100), ("Screening", 300), ("Eligibility", 580), ("Included", 780)]
        for text, y in labels:
            page.insert_text((15, y), text, fontname="helv", fontsize=10, color=(0.4, 0.4, 0.4), rotate=90)
            
        # Save
        pix = page.get_pixmap(dpi=150)
        pix.save(output_path)
        doc.close()
        return output_path

    def generate_prisma_excel_sheet(self, workbook):
        nums = self.get_prisma_numbers()
        sheet = workbook.create_sheet("PRISMA Numbers")
        
        from openpyxl.styles import Font, PatternFill
        header_font = Font(bold=True)
        header_fill = PatternFill(start_color="DDEEFF", end_color="DDEEFF", fill_type="solid")
        
        headers = ["Stage", "Metric", "Count"]
        for col, h in enumerate(headers, 1):
            cell = sheet.cell(row=1, column=col, value=h)
            cell.font = header_font
            cell.fill = header_fill
            
        data = [
            ("Identification", "Total records identified", nums["identified_total"]),
            ("Identification", "PubMed", nums["identified_by_db"]["PubMed"]),
            ("Identification", "Embase", nums["identified_by_db"]["Embase"]),
            ("Identification", "Scopus", nums["identified_by_db"]["Scopus"]),
            ("Identification", "WoS", nums["identified_by_db"]["WoS"]),
            ("Identification", "Other", nums["identified_by_db"]["Other"]),
            ("Identification", "Duplicates removed", nums["duplicates_removed"]),
            ("Screening", "Total screened", nums["screened"]),
            ("Screening", "Excluded at screening", nums["excluded_screening"]),
            ("Identification", "Sought for retrieval", nums["sought_retrieval"]),
            ("Identification", "Not retrieved", nums["not_retrieved"]),
            ("Eligibility", "Assessed for eligibility", nums["assessed_eligibility"]),
            ("Eligibility", "Excluded at full-text", nums["excluded_fulltext"]),
            ("Included", "Final included", nums["included_final"])
        ]
        
        for row_idx, (stage, metric, val) in enumerate(data, 2):
            sheet.cell(row=row_idx, column=1, value=stage)
            sheet.cell(row=row_idx, column=2, value=metric)
            sheet.cell(row=row_idx, column=3, value=val)
            
        # Column width
        sheet.column_dimensions['A'].width = 15
        sheet.column_dimensions['B'].width = 30
        sheet.column_dimensions['C'].width = 10
        
        return workbook

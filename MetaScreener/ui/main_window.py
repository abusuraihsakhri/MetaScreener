import os
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QStackedWidget, QLabel, QFileDialog, 
                             QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
                             QProgressBar, QTreeWidget, QTreeWidgetItem, QRadioButton, QButtonGroup,
                             QCheckBox, QGroupBox, QSlider, QDialog, QTextEdit, QTextBrowser, QFrame, QListWidget, QGraphicsDropShadowEffect,
                             QSplitter, QSizePolicy, QScrollArea, QLineEdit, QGridLayout, QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QColor, QBrush, QAction, QKeySequence, QDesktopServices, QShortcut, QPixmap, QImage, QFont
from modules.ollama_client import OllamaStatusWorker
from modules.importer import PaperImporter
from modules.screener import ScreeningManager
from config import Config
from modules.prisma import PRISMAGenerator
from modules.exporter import Exporter
from modules.fulltext_reviewer import FulltextReviewer
import fitz
from PyQt6.QtGui import QImage, QPixmap

def make_pill(text, text_color, bg_color, min_width=90):
    p = QLabel(text)
    p.setFixedHeight(26)
    p.setMinimumWidth(min_width)
    p.setAlignment(Qt.AlignmentFlag.AlignCenter)
    p.setStyleSheet(f"background: {bg_color}; color: {text_color}; border-radius: 10px; padding: 0px 10px; font-weight: 600; font-size: 11px;")
    return p

class SimilarityMatrixDialog(QDialog):
    def __init__(self, deduplicator, parent=None):
        super().__init__(parent)
        self.deduplicator = deduplicator
        self.setWindowTitle("Similarity Matrix Viewer")
        self.resize(1000, 700)
        self.setStyleSheet("background-color: white;")
        layout = QVBoxLayout(self)
        
        info = QLabel("Showing similarity scores (%) between pairs of papers. Red cells indicate potential duplicates.")
        info.setStyleSheet("font-size: 14px; color: #666; margin-bottom: 10px;")
        layout.addWidget(info)
        
        self.table = QTableWidget()
        self.table.setStyleSheet("gridline-color: #E0E0E0; border: 1px solid #E0E0E0;")
        layout.addWidget(self.table)
        
        self.load_data()
        
    def load_data(self):
        papers = self.deduplicator.get_non_duplicate_papers()
        n = len(papers)
        if n > 150:
             QMessageBox.warning(self, "Large Dataset", f"Visualizing {n} papers. This may be slow.")
             
        self.table.setColumnCount(n)
        self.table.setRowCount(n)
        
        headers = [f"ID {p['id']}: {p['title'][:30]}..." for p in papers]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setVerticalHeaderLabels(headers)
        self.table.horizontalHeader().setDefaultSectionSize(60)
        self.table.verticalHeader().setDefaultSectionSize(40)
        
        from rapidfuzz import fuzz
        for i in range(n):
            for j in range(i, n):
                if i == j:
                    score = 100
                else:
                    score = fuzz.token_sort_ratio(papers[i]['title'], papers[j]['title'])
                
                item = QTableWidgetItem(f"{int(score)}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                if score >= 92:
                    item.setBackground(QBrush(QColor(231, 76, 60, 100))) # Transparent Red
                elif score >= 80:
                    item.setBackground(QBrush(QColor(241, 196, 15, 100))) # Transparent Yellow
                
                self.table.setItem(i, j, item)
                
                if i != j:
                    item2 = QTableWidgetItem(f"{int(score)}")
                    item2.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item2.setBackground(item.background())
                    self.table.setItem(j, i, item2)

class DropArea(QLabel):
    def __init__(self, main_window):
        super().__init__("Drag & drop reference files here\n(RIS, BibTeX, CSV, TXT) or click to browse")
        self.main_window = main_window
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(200)
        self.setObjectName("dropArea")
        self.setStyleSheet("""
            #dropArea {
                border: 2px dashed #C8C8D0;
                border-radius: 16px;
                background-color: #FFFFFF;
                color: #7f8c8d;
                font-size: 16px;
                font-weight: 500;
                padding: 40px;
            }
            #dropArea:hover {
                background-color: #F0F2FF;
                border-color: #4A6CF7;
                color: #4A6CF7;
            }
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
            self.setStyleSheet(self.styleSheet().replace("#C8C8D0", "#4A6CF7").replace("#FFFFFF", "#F0F2FF"))
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self.styleSheet().replace("#4A6CF7", "#C8C8D0").replace("#F0F2FF", "#FFFFFF"))

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet(self.styleSheet().replace("#4A6CF7", "#C8C8D0").replace("#F0F2FF", "#FFFFFF"))
        files = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if files:
            self.main_window.process_files(files)

    def mousePressEvent(self, event):
        self.main_window.browse_files()


class AIThread(QThread):
    finished = pyqtSignal(dict)
    def __init__(self, title, abstract):
        super().__init__()
        self.title = title
        self.abstract = abstract
    def run(self):
        try:
            from modules.ai_client import screen_abstract
            res = screen_abstract(self.title, self.abstract)
            self.finished.emit(res)
        except Exception as e:
            logging.error(f"AIThread crash: {e}")
            self.finished.emit({
                "decision": "uncertain",
                "confidence": 0,
                "reason": f"AI Thread Error: {str(e)}"
            })

class AutoExtractWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(int, int)
    error = pyqtSignal(str)

    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.cancelled = False

    def run(self):
        try:
            papers = self.manager.get_papers_for_extraction()
            total = len(papers)
            processed = failed = 0
            for i, paper in enumerate(papers):
                if self.cancelled:
                    break
                try:
                    self.manager.ai_extract_paper(paper.get("id"))
                    processed += 1
                except Exception as e:
                    logging.error(f"Extract failed for paper {paper.get('id')}: {e}")
                    failed += 1
                self.progress.emit(i + 1, total, paper.get("title","")[:60])
            self.finished.emit(processed, failed)
        except Exception as e:
            self.error.emit(str(e))

class BulkScreenWorker(QThread):
    progress = pyqtSignal(int, int, str, int, int, int)
    finished = pyqtSignal(int, int, int)
    error = pyqtSignal(str)

    def __init__(self, screening_manager):
        super().__init__()
        self.manager = screening_manager
        self.cancelled = False

    def run(self):
        try:
            papers = self.manager.get_pending_papers()
            total = len(papers)
            included = excluded = uncertain = 0
            for i, paper in enumerate(papers):
                if self.cancelled:
                    break
                try:
                    result = self.manager.ai.screen_abstract(
                        paper["title"], paper["abstract"]
                    )
                    decision = result.get("decision", "uncertain")
                    reason = result.get("reason", "")
                    try:
                        confidence = int(result.get("confidence", 0))
                    except:
                        confidence = 0
                        
                    self.manager.save_decision(
                        paper["id"], decision, reason, confidence
                    )
                    
                    if decision == "include": included += 1
                    elif decision == "exclude": excluded += 1
                    else: uncertain += 1
                    
                    self.progress.emit(i + 1, total, paper["title"][:60], included, excluded, uncertain)
                except Exception as loop_e:
                    logging.error(f"Error screening paper {paper.get('id')}: {loop_e}")
                    uncertain += 1
                    self.progress.emit(i + 1, total, f"ERROR: {paper.get('title', '')[:50]}", included, excluded, uncertain)
                
                import time
                time.sleep(0.3)
            self.finished.emit(included, excluded, uncertain)
        except Exception as e:
            self.error.emit(str(e))

class BulkProgressDialog(QDialog):
    def __init__(self, total, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bulk AI Screening in Progress")
        self.setFixedSize(500, 280)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, total)
        self.progress_bar.setFixedHeight(16)
        layout.addWidget(self.progress_bar)
        
        self.lbl_current = QLabel("Processing: Starting...")
        self.lbl_current.setStyleSheet("font-size: 13px; color: #1a1a2e;")
        self.lbl_current.setWordWrap(True)
        layout.addWidget(self.lbl_current)
        
        self.lbl_stats = QLabel("Included: 0 | Excluded: 0 | Uncertain: 0")
        self.lbl_stats.setStyleSheet("font-weight: bold; color: #4A6CF7;")
        layout.addWidget(self.lbl_stats)
        
        self.lbl_count = QLabel(f"0 of {total} papers complete")
        self.lbl_count.setStyleSheet("color: #888;")
        layout.addWidget(self.lbl_count)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedHeight(36)
        layout.addWidget(self.btn_cancel)

    def update_status(self, current, total, title, inc, exc, unc):
        self.progress_bar.setValue(current)
        self.lbl_current.setText(f"Processing: {title}")
        self.lbl_stats.setText(f"Included: {inc} | Excluded: {exc} | Uncertain: {unc}")
        self.lbl_count.setText(f"{current} of {total} papers complete")

class ScreeningPanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.manager = ScreeningManager()
        self.current_papers = []
        self.current_idx = -1
        self.history = []
        
        self.init_ui()
        self.load_pending()
        self.refresh_stats()

    def init_ui(self):
        # Main layout is vertical for the whole panel
        self.main_v_layout = QVBoxLayout(self)
        self.main_v_layout.setContentsMargins(0, 0, 0, 0)
        self.main_v_layout.setSpacing(0)

        # Section 1: Criteria Bar (Collapsible Redesign)
        self.criteria_box = QWidget()
        self.criteria_box.setStyleSheet("background: #FFFFFF; border-bottom: 1px solid #E8E8F0;")
        self.criteria_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        criteria_outer = QVBoxLayout(self.criteria_box)
        criteria_outer.setContentsMargins(16, 12, 16, 12)
        criteria_outer.setSpacing(8)

        # Header row
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        criteria_title = QLabel("Screening Criteria")
        criteria_title.setStyleSheet("font-size:14px; font-weight:700; color:#4A6CF7;")
        self.btn_hide_criteria = QPushButton("Hide ▲")
        self.btn_hide_criteria.setFixedSize(80, 28)
        self.btn_hide_criteria.setStyleSheet("""
            QPushButton { background: #F0F2FF; color: #4A6CF7; border: none; border-radius: 6px; font-size: 12px; font-weight: 600; }
            QPushButton:hover { background: #E0E5FF; }
        """)
        header_row.addWidget(criteria_title)
        header_row.addStretch()
        header_row.addWidget(self.btn_hide_criteria)
        criteria_outer.addLayout(header_row)

        # Collapsible content
        self.criteria_content = QWidget()
        criteria_content_layout = QVBoxLayout(self.criteria_content)
        criteria_content_layout.setContentsMargins(0, 4, 0, 0)
        criteria_content_layout.setSpacing(8)
        
        cols_row = QHBoxLayout()
        cols_row.setSpacing(12)
        
        # Inclusion
        inc_col = QVBoxLayout()
        inc_col.setSpacing(4)
        inc_label = QLabel("\u2713  Inclusion Criteria")
        inc_label.setStyleSheet("font-size:12px; font-weight:700; color:#1E8449;")
        self.txt_inc_criteria = QTextEdit()
        self.txt_inc_criteria.setFixedHeight(60)
        self.txt_inc_criteria.setPlaceholderText("e.g. human studies, RCTs, age > 18...")
        self.txt_inc_criteria.setPlainText(Config.INCLUSION_CRITERIA)
        self.txt_inc_criteria.setStyleSheet("""
            QTextEdit { border: 1.5px solid #2ECC71; border-radius: 8px; padding: 6px 10px; font-size: 13px; color: #1a1a2e; background: #FAFFFE; }
            QTextEdit:focus { border-color: #1E8449; }
        """)
        inc_col.addWidget(inc_label)
        inc_col.addWidget(self.txt_inc_criteria)
        
        # Exclusion
        exc_col = QVBoxLayout()
        exc_col.setSpacing(4)
        exc_label = QLabel("\u2717  Exclusion Criteria")
        exc_label.setStyleSheet("font-size:12px; font-weight:700; color:#C0392B;")
        self.txt_exc_criteria = QTextEdit()
        self.txt_exc_criteria.setFixedHeight(60)
        self.txt_exc_criteria.setPlaceholderText("e.g. animal studies, reviews, non-English...")
        self.txt_exc_criteria.setPlainText(Config.EXCLUSION_CRITERIA)
        self.txt_exc_criteria.setStyleSheet("""
            QTextEdit { border: 1.5px solid #E74C3C; border-radius: 8px; padding: 6px 10px; font-size: 13px; color: #1a1a2e; background: #FFFAFA; }
            QTextEdit:focus { border-color: #C0392B; }
        """)
        exc_col.addWidget(exc_label)
        exc_col.addWidget(self.txt_exc_criteria)
        
        cols_row.addLayout(inc_col)
        cols_row.addLayout(exc_col)
        criteria_content_layout.addLayout(cols_row)
        
        # Save row
        save_row = QHBoxLayout()
        save_row.setSpacing(10)
        self.btn_save_criteria = QPushButton("  Save Criteria")
        self.btn_save_criteria.setFixedSize(140, 34)
        self.btn_save_criteria.setStyleSheet("""
            QPushButton { background: #4A6CF7; color: white; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; padding-left: 8px; }
            QPushButton:hover { background: #3A5CE5; }
            QPushButton:pressed { background: #2A4CD5; }
        """)
        self.btn_save_criteria.clicked.connect(self.save_criteria)
        self.lbl_saved_status = QLabel("")
        self.lbl_saved_status.setStyleSheet("font-size:12px; color:#2ECC71; font-weight:600;")
        self.lbl_saved_status.setFixedHeight(34)
        save_row.addWidget(self.btn_save_criteria)
        save_row.addWidget(self.lbl_saved_status)
        save_row.addStretch()
        criteria_content_layout.addLayout(save_row)
        
        criteria_outer.addWidget(self.criteria_content)
        self.btn_hide_criteria.clicked.connect(self.toggle_criteria)
        self.main_v_layout.addWidget(self.criteria_box)

        # Section 2: Toolbar Row (Complete Redesign)
        self.toolbar = QWidget()
        self.toolbar.setFixedHeight(58)
        self.toolbar.setStyleSheet("background: #FFFFFF; border-bottom: 2px solid #E8E8F0;")
        toolbar_layout = QHBoxLayout(self.toolbar)
        toolbar_layout.setContentsMargins(16, 8, 16, 8)
        toolbar_layout.setSpacing(8)
        
        # Decision Buttons
        self.btn_include = QPushButton("\u2713   Include")
        self.btn_include.setFixedSize(118, 40)
        self.btn_include.setStyleSheet("""
            QPushButton { background: #2ECC71; color: white; border: none; border-radius: 10px; font-size: 14px; font-weight: 700; }
            QPushButton:hover { background: #27AE60; }
            QPushButton:pressed { background: #1E8449; }
        """)
        self.btn_include.clicked.connect(lambda: self.make_decision("include"))
        
        self.btn_exclude = QPushButton("\u2717   Exclude")
        self.btn_exclude.setFixedSize(118, 40)
        self.btn_exclude.setStyleSheet("""
            QPushButton { background: #E74C3C; color: white; border: none; border-radius: 10px; font-size: 14px; font-weight: 700; }
            QPushButton:hover { background: #C0392B; }
            QPushButton:pressed { background: #A93226; }
        """)
        self.btn_exclude.clicked.connect(lambda: self.make_decision("exclude"))
        
        self.btn_uncertain = QPushButton("?   Uncertain")
        self.btn_uncertain.setFixedSize(118, 40)
        self.btn_uncertain.setStyleSheet("""
            QPushButton { background: #F39C12; color: white; border: none; border-radius: 10px; font-size: 14px; font-weight: 700; }
            QPushButton:hover { background: #D68910; }
            QPushButton:pressed { background: #B7770D; }
        """)
        self.btn_uncertain.clicked.connect(lambda: self.make_decision("uncertain"))

        def make_vdivider():
            d = QFrame()
            d.setFrameShape(QFrame.Shape.VLine)
            d.setFixedSize(1, 36)
            d.setStyleSheet("background: #E0E0E0; border: none;")
            return d

        reason_label = QLabel("Reason:")
        reason_label.setFixedWidth(54)
        reason_label.setStyleSheet("font-size:12px; color:#888; font-weight:500;")
        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText("Optional reason for this decision...")
        self.reason_input.setFixedHeight(36)
        self.reason_input.setMinimumWidth(160)
        self.reason_input.setMaximumWidth(280)
        self.reason_input.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.reason_input.setStyleSheet("""
            QLineEdit { border: 1.5px solid #E0E0E0; border-radius: 8px; padding: 4px 10px; font-size: 13px; color: #1a1a2e; background: #F9F9FB; }
            QLineEdit:focus { border-color: #4A6CF7; background: white; }
        """)

        self.btn_show_criteria = QPushButton("Show Criteria \u25bc")
        self.btn_show_criteria.setFixedSize(130, 32)
        self.btn_show_criteria.setStyleSheet("font-size: 13px; color: #4A6CF7;")
        self.btn_show_criteria.setFlat(True)
        self.btn_show_criteria.setVisible(False)
        self.btn_show_criteria.clicked.connect(self.toggle_criteria)

        # Stat pills
        def create_pill(text, text_color, bg_color):
            p = QLabel(text)
            p.setFixedHeight(26)
            p.setMinimumWidth(75)
            p.setAlignment(Qt.AlignmentFlag.AlignCenter)
            p.setStyleSheet(f"background: {bg_color}; color: {text_color}; border-radius: 10px; padding: 0px 8px; font-weight: 600; font-size: 11px;")
            return p

        self.pill_pending = create_pill("Pending: 0", "#555555", "#F0F0F5")
        self.pill_included = create_pill("Included: 0", "#1E8449", "#E8F8F0")
        self.pill_excluded = create_pill("Excluded: 0", "#C0392B", "#FDECEA")
        self.pill_uncertain = create_pill("Uncertain: 0", "#B7770D", "#FEF5E7")
        self.pill_progress = create_pill("0%", "#4A6CF7", "#EEF2FF")

        self.btn_show_screened = QPushButton("Show Screened \u25b6")
        self.btn_show_screened.setFixedSize(120, 36)
        self.btn_show_screened.setStyleSheet("""
            QPushButton { background: white; color: #555; border: 1.5px solid #D0D0DA; border-radius: 8px; font-size: 12px; font-weight: 500; }
            QPushButton:hover { border-color: #4A6CF7; color: #4A6CF7; }
        """)
        self.btn_show_screened.clicked.connect(self.show_screened_dialog)

        self.btn_bulk_ai_toolbar = QPushButton("Bulk AI \u25b6")
        self.btn_bulk_ai_toolbar.setFixedSize(96, 36)
        self.btn_bulk_ai_toolbar.setStyleSheet("""
            QPushButton { background: #4A6CF7; color: white; border: none; border-radius: 8px; font-size: 12px; font-weight: 700; }
            QPushButton:hover { background: #3A5CE5; }
        """)
        self.btn_bulk_ai_toolbar.clicked.connect(self.run_bulk_ai_screening)

        toolbar_layout.addWidget(self.btn_include)
        toolbar_layout.addWidget(self.btn_exclude)
        toolbar_layout.addWidget(self.btn_uncertain)
        toolbar_layout.addWidget(make_vdivider())
        toolbar_layout.addWidget(reason_label)
        toolbar_layout.addWidget(self.reason_input)
        toolbar_layout.addWidget(self.btn_show_criteria)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.pill_pending)
        toolbar_layout.addWidget(self.pill_included)
        toolbar_layout.addWidget(self.pill_excluded)
        toolbar_layout.addWidget(self.pill_uncertain)
        toolbar_layout.addWidget(self.pill_progress)
        toolbar_layout.addWidget(make_vdivider())
        toolbar_layout.addWidget(self.btn_show_screened)
        toolbar_layout.addWidget(self.btn_bulk_ai_toolbar)
        
        self.main_v_layout.addWidget(self.toolbar)

        # Section 3: Main Content Area (Splitter)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(4)
        self.splitter.setStyleSheet("QSplitter::handle { background: #E8E8F0; }")
        self.splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Left Panel (Paper Display)
        self.left_card = QWidget()
        self.left_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.left_card.setStyleSheet("background:white; border-right: 1px solid #E0E0E0;")
        left_layout = QVBoxLayout(self.left_card)
        left_layout.setContentsMargins(24, 16, 24, 16)
        left_layout.setSpacing(8)
        
        top_right_layout = QHBoxLayout()
        self.debug_btn = QPushButton("Debug")
        self.debug_btn.setFixedSize(58, 22)
        self.debug_btn.setStyleSheet("""
            QPushButton {
                background: #F5F5FA;
                color: #888;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { color: #4A6CF7; border-color: #4A6CF7; }
        """)
        self.debug_btn.clicked.connect(self.show_debug_dialog)
        
        self.counter_label = QLabel("Paper 0 of 0")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.counter_label.setStyleSheet("font-size:12px; color:#aaa;")
        self.counter_label.setFixedHeight(18)
        
        top_right_layout.addStretch()
        top_right_layout.addWidget(self.debug_btn)
        top_right_layout.addWidget(self.counter_label)
        left_layout.addLayout(top_right_layout)
        
        self.title_label = QLabel("Title")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size:17px; font-weight:700; color:#1a1a2e;")
        self.title_label.setMinimumHeight(48)
        self.title_label.setMaximumHeight(80)
        left_layout.addWidget(self.title_label)
        
        self.authors_label = QLabel("Authors")
        self.authors_label.setStyleSheet("font-size:13px; color:#666; font-style:italic;")
        self.authors_label.setFixedHeight(22)
        left_layout.addWidget(self.authors_label)
        
        self.doi_label = QLabel("DOI")
        self.doi_label.setOpenExternalLinks(True)
        self.doi_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.doi_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #4A6CF7;
                text-decoration: none;
                padding: 2px 0px;
            }
            QLabel:hover {
                color: #2A4CD5;
                text-decoration: underline;
            }
        """)
        self.doi_label.setFixedHeight(22)
        self.doi_label.setCursor(Qt.CursorShape.PointingHandCursor)
        left_layout.addWidget(self.doi_label)
        
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#E0E0E0;")
        sep.setFixedHeight(1)
        left_layout.addWidget(sep)
        
        abs_label_hdr = QLabel("Abstract")
        abs_label_hdr.setStyleSheet("font-size:12px; font-weight:700; color:#aaa; margin-top:4px;")
        abs_label_hdr.setFixedHeight(20)
        left_layout.addWidget(abs_label_hdr)
        
        self.abstract_edit = QTextBrowser()
        self.abstract_edit.setOpenExternalLinks(True)
        self.abstract_edit.setFrameShape(QFrame.Shape.NoFrame)
        self.abstract_edit.setStyleSheet("""
            QTextBrowser {
                background: transparent;
                border: none;
                font-size: 14px;
                color: #1a1a2e;
                line-height: 1.7;
                padding: 0px;
            }
        """)
        self.abstract_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.abstract_edit.setMinimumHeight(300)
        left_layout.addWidget(self.abstract_edit, stretch=1)
        
        self.splitter.addWidget(self.left_card)
        
        # Right Panel (AI suggestion panel only)
        self.right_scroll = QScrollArea()
        self.right_scroll.setWidgetResizable(True)
        self.right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.right_scroll.setMinimumWidth(300)
        self.right_scroll.setMaximumWidth(420)
        self.right_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.right_scroll.setStyleSheet("background:#FAFAFA; border-left: 1px solid #E0E0E0;")
        
        right_widget = QWidget()
        right_widget.setStyleSheet("background:#FAFAFA;")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)
        
        hints = QLabel("I = Include    E = Exclude    U = Uncertain    Z = Undo")
        hints.setStyleSheet("font-size:11px; color:#aaa; background:#F0F0F5; border-radius:6px; padding:6px;")
        hints.setWordWrap(True)
        right_layout.addWidget(hints)
        
        ai_header = QLabel("AI Suggestion")
        ai_header.setStyleSheet("font-size:14px; font-weight:700; color:#1a1a2e;")
        right_layout.addWidget(ai_header)
        
        self.ai_result_box = QLabel("No suggestion yet")
        self.ai_result_box.setWordWrap(True)
        self.ai_result_box.setMinimumHeight(100)
        self.ai_result_box.setStyleSheet("background:#F5F6FA; border-radius:8px; padding:12px; font-size:13px; color:#555;")
        right_layout.addWidget(self.ai_result_box)
        
        self.btn_get_ai = QPushButton("Get AI Suggestion")
        self.btn_get_ai.setFixedHeight(38)
        self.btn_get_ai.setStyleSheet("border:1.5px solid #4A6CF7; color:#4A6CF7; border-radius:8px; font-size:13px; background:white;")
        self.btn_get_ai.clicked.connect(self.get_ai_suggestion)
        right_layout.addWidget(self.btn_get_ai)
        
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color:#E0E0E0;")
        right_layout.addWidget(sep2)
        
        bulk_header = QLabel("Bulk AI Screening")
        bulk_header.setStyleSheet("font-size:14px; font-weight:700; color:#1a1a2e;")
        right_layout.addWidget(bulk_header)
        
        self.lbl_bulk_pending = QLabel("0 papers pending")
        self.lbl_bulk_pending.setStyleSheet("font-size:12px; color:#888;")
        right_layout.addWidget(self.lbl_bulk_pending)
        
        self.btn_bulk_ai = QPushButton("Bulk AI Screen All Pending")
        self.btn_bulk_ai.setFixedHeight(44)
        self.btn_bulk_ai.setStyleSheet("background:#4A6CF7; color:white; font-size:14px; font-weight:700; border-radius:8px; border:none;")
        self.btn_bulk_ai.setObjectName("primary")
        self.btn_bulk_ai.clicked.connect(self.run_bulk_ai_screening)
        right_layout.addWidget(self.btn_bulk_ai)
        
        # Debug Log Section (Collapsible)
        self.btn_toggle_debug = QPushButton("Show Debug Log")
        self.btn_toggle_debug.setFixedHeight(24)
        self.btn_toggle_debug.setFlat(True)
        self.btn_toggle_debug.setCheckable(True)
        self.btn_toggle_debug.setStyleSheet("color: #aaa; font-size: 11px; text-align: left; padding: 0;")
        self.btn_toggle_debug.clicked.connect(self.toggle_debug_log)
        right_layout.addWidget(self.btn_toggle_debug)

        self.txt_debug_log = QTextEdit()
        self.txt_debug_log.setReadOnly(True)
        self.txt_debug_log.setVisible(False)
        self.txt_debug_log.setFixedHeight(120)
        self.txt_debug_log.setStyleSheet("""
            QTextEdit { 
                background: #f8f8fb; 
                border: 1px solid #E8E8F0; 
                border-radius: 6px; 
                font-family: 'Consolas', monospace; 
                font-size: 11px; 
                color: #666; 
            }
        """)
        right_layout.addWidget(self.txt_debug_log)

        right_layout.addStretch(1)
        self.right_scroll.setWidget(right_widget)
        self.splitter.addWidget(self.right_scroll)
        
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        
        self.main_v_layout.addWidget(self.splitter, stretch=1)

        # Section 4: Navigation Bar (Complete Redesign)
        self.nav_bar = QWidget()
        self.nav_bar.setFixedHeight(60)
        self.nav_bar.setStyleSheet("background: #FFFFFF; border-top: 2px solid #E8E8F0;")
        nav_layout = QHBoxLayout(self.nav_bar)
        nav_layout.setContentsMargins(20, 10, 20, 10)
        nav_layout.setSpacing(8)
        
        nav_btn_style = """
            QPushButton { background: white; color: #1a1a2e; border: 1.5px solid #D0D0DA; border-radius: 8px; font-size: 13px; font-weight: 500; padding: 0px 12px; }
            QPushButton:hover { background: #EEF2FF; border-color: #4A6CF7; color: #4A6CF7; }
            QPushButton:pressed { background: #D6E4FF; }
            QPushButton:disabled { color: #bbb; border-color: #E8E8F0; background: #FAFAFA; }
        """
        
        self.btn_prev = QPushButton("\u2190 Previous")
        self.btn_prev.setFixedSize(112, 38)
        self.btn_prev.setStyleSheet(nav_btn_style)
        self.btn_prev.clicked.connect(self.go_prev)
        
        self.btn_undo = QPushButton("\u21a9 Undo")
        self.btn_undo.setFixedSize(90, 38)
        self.btn_undo.setStyleSheet(nav_btn_style)
        self.btn_undo.clicked.connect(self.undo_last)
        
        self.nav_counter = QLabel("0 / 0")
        self.nav_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nav_counter.setStyleSheet("""
            font-size: 15px; font-weight: 700; color: #1a1a2e; background: #F5F6FA; border-radius: 8px; padding: 4px 20px;
        """)
        self.nav_counter.setMinimumWidth(120)
        self.nav_counter.setFixedHeight(38)
        
        self.btn_skip = QPushButton("Skip \u2192")
        self.btn_skip.setFixedSize(82, 38)
        self.btn_skip.setStyleSheet(nav_btn_style)
        self.btn_skip.clicked.connect(self.go_next)
        
        self.btn_next = QPushButton("Next \u2192")
        self.btn_next.setFixedSize(112, 38)
        self.btn_next.setStyleSheet("""
            QPushButton { background: #4A6CF7; color: white; border: none; border-radius: 8px; font-size: 13px; font-weight: 700; padding: 0px 12px; }
            QPushButton:hover { background: #3A5CE5; }
            QPushButton:pressed { background: #2A4CD5; }
            QPushButton:disabled { background: #C0C8F8; }
        """)
        self.btn_next.clicked.connect(self.go_next)
        
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_undo)
        nav_layout.addStretch()
        nav_layout.addWidget(self.nav_counter)
        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_skip)
        nav_layout.addWidget(self.btn_next)
        
        self.main_v_layout.addWidget(self.nav_bar)

        self.main_v_layout.addWidget(self.nav_bar)
        
        # We need self.lbl_ai_decision, self.ai_conf_bar, self.lbl_ai_reason for compat with existing logic
        self.lbl_ai_decision = QLabel()
        self.ai_conf_bar = QProgressBar()
        self.lbl_ai_reason = QLabel()
        self.lbl_ai_decision.setVisible(False)
        self.ai_conf_bar.setVisible(False)
        self.lbl_ai_reason.setVisible(False)

        # Shortcuts
        self.setup_shortcuts()
        
    def setup_shortcuts(self):
        QShortcut(QKeySequence("I"), self).activated.connect(lambda: self.make_decision("include"))
        QShortcut(QKeySequence("E"), self).activated.connect(lambda: self.make_decision("exclude"))
        QShortcut(QKeySequence("U"), self).activated.connect(lambda: self.make_decision("uncertain"))
        QShortcut(QKeySequence("Z"), self).activated.connect(self.undo_last)
        QShortcut(QKeySequence("Space"), self).activated.connect(self.go_next)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self).activated.connect(self.go_next)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self).activated.connect(self.go_prev)

    def save_criteria(self):
        Config.INCLUSION_CRITERIA = self.txt_inc_criteria.toPlainText().strip()
        Config.EXCLUSION_CRITERIA = self.txt_exc_criteria.toPlainText().strip()
        Config.save()
        self.lbl_saved_status.setText("\u2713 Saved")
        QTimer.singleShot(2000, lambda: self.lbl_saved_status.setText(""))

    def toggle_criteria(self):
        visible = self.criteria_content.isVisible()
        self.criteria_content.setVisible(not visible)
        self.btn_hide_criteria.setText("Show \u25bc" if visible else "Hide \u25b2")
        self.btn_show_criteria.setVisible(visible) # Sync with toolbar button if needed
        self.criteria_box.setMaximumHeight(48 if visible else 16777215)

    def create_pill(self, text, color):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"background: {color}22; color: {color}; border-radius: 10px; padding: 3px 12px; font-weight: 600; font-size: 13px;")
        return lbl

    def load_pending(self):
        self.current_papers = self.manager.get_pending_papers()
        if self.current_papers:
            self.current_idx = 0
            self.show_paper(self.current_papers[0])
        else:
            self.current_idx = -1
            self.show_empty()

    def show_paper(self, paper):
        self.load_paper(paper)

    def load_paper(self, paper):
        self.current_paper = paper
        title = paper.get("title", "No title available")
        self.title_label.setText(title)
        
        # Get abstract from paper dict
        abstract = paper.get("abstract", None)

        # If abstract is None or empty in the dict,
        # re-query the database directly to double check
        if not abstract or not str(abstract).strip():
            try:
                import sqlite3
                from config import Config
                conn = sqlite3.connect(Config.DB_PATH)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT abstract FROM papers WHERE id = ?",
                    (paper.get("id"),)
                )
                row = cur.fetchone()
                conn.close()
                if row and row["abstract"] and str(row["abstract"]).strip():
                    abstract = row["abstract"]
                    logging.info(
                        f"Abstract recovered from DB for paper {paper.get('id')}"
                    )
                else:
                    abstract = None
            except Exception as e:
                logging.error(f"Abstract DB re-query failed: {e}")
                abstract = None

        # Set display text
        if abstract and str(abstract).strip() and str(abstract).strip().lower() != "nan":
            self.abstract_edit.setHtml(f'<div style="line-height:1.7;">{str(abstract).strip()}</div>')
            self.abstract_edit.setStyleSheet("""
                QTextBrowser {
                    background: transparent;
                    border: none;
                    font-size: 14px;
                    color: #1a1a2e;
                    padding: 0px;
                }
            """)
        else:
            self.abstract_edit.setPlainText("")
            self.abstract_edit.setHtml("""
                <p style="color:#E74C3C; font-size:13px; font-family:Segoe UI;">
                    ⚠ No abstract available for this paper.
                </p>
                <p style="color:#aaa; font-size:12px; font-family:Segoe UI;">
                    This may be because:
                    <br>• The source database did not include an abstract
                    <br>• The abstract field was not parsed from the import file
                    <br>• The paper is a conference abstract with no full text
                    <br><br>Click <b>Debug</b> above to inspect the raw database record.
                </p>
            """)
            logging.warning(
                f"No abstract for paper ID {paper.get('id')} "
                f"title: {paper.get('title','')[:60]}"
            )

        self.abstract_edit.verticalScrollBar().setValue(0)
        self.abstract_edit.setVisible(True)
        
        authors = paper.get("authors", "Unknown authors")
        year = paper.get("year", "")
        self.authors_label.setText(f"{authors}  |  {year}")
        doi = paper.get("doi", "").strip()
        if doi:
            if doi.startswith("http"):
                url = doi
            else:
                url = f"https://doi.org/{doi}"
            self.doi_label.setText(
                f'<a href="{url}" style="color:#4A6CF7; text-decoration:none;">'
                f'DOI: {doi}</a>'
            )
        else:
            self.doi_label.setText('<span style="color:#aaa; font-size:12px;">No DOI available</span>')
        self.counter_label.setText(
            f"Paper {self.current_idx + 1} of {len(self.current_papers)}"
        )
        self.nav_counter.setText(
            f"{self.current_idx + 1} / {len(self.current_papers)}"
        )
        self.ai_result_box.setText("No suggestion yet")
        self.ai_result_box.setStyleSheet(
            "background:#F5F6FA; border-radius:8px; padding:12px; font-size:13px; color:#555;"
        )
        self.reason_input.clear()

    def show_debug_dialog(self):
        if not hasattr(self, 'current_paper') or not self.current_paper:
            return
            
        paper_id = self.current_paper.get("id")
        data = self.manager.debug_paper_data(paper_id)
        
        dlg = QDialog()
        dlg.setWindowTitle(f"Paper Debug — ID {data.get('id')}")
        dlg.setMinimumSize(600, 400)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        def row(label, value, warn=False):
            color = "#E74C3C" if warn else "#1a1a2e"
            return f'<tr><td style="color:#888; padding:4px 12px 4px 0; font-size:13px;">{label}</td><td style="color:{color}; font-size:13px;">{value}</td></tr>'

        abstract = data.get("abstract", "") or ""
        abstract_warn = len(abstract.strip()) == 0

        html = f"""
        <table style="font-family: Segoe UI; border-collapse: collapse;">
            {row("Paper ID", data.get("id"))}
            {row("Title length", f"{data.get('title_length')} chars")}
            {row("Abstract length", f"{data.get('abstract_length')} chars", warn=abstract_warn)}
            {row("Abstract is NULL", str(data.get('abstract_is_null')), warn=data.get('abstract_is_null'))}
            {row("Abstract is empty", str(data.get('abstract_is_empty')), warn=data.get('abstract_is_empty'))}
            {row("Source file", data.get('source_file', 'unknown'))}
            {row("DOI", data.get('doi', 'none'))}
            {row("Year", data.get('year', 'none'))}
        </table>
        <hr style="border:1px solid #E0E0E0; margin: 12px 0;">
        <p style="font-size:12px; font-weight:700; color:#888; font-family:Segoe UI;">ABSTRACT CONTENT:</p>
        <p style="font-size:13px; color:#1a1a2e; font-family:Segoe UI; line-height:1.6; background:#F9F9FB; padding:12px; border-radius:8px;">
            {abstract[:1000] if abstract.strip() else '<span style="color:#E74C3C;">⚠ Abstract field is empty or NULL in the database</span>'}
        </p>
        """

        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(html)
        text.setStyleSheet("border: 1px solid #E0E0E0; border-radius: 8px; background: white;")

        close_btn = QPushButton("Close")
        close_btn.setFixedSize(100, 36)
        close_btn.setStyleSheet("border:1.5px solid #D0D0DA; border-radius:8px; font-size:13px;")
        close_btn.clicked.connect(dlg.accept)

        layout.addWidget(text)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def show_empty(self):
        self.title_label.setText("All papers screened!")
        self.authors_label.setText("")
        self.doi_label.setText("")
        self.abstract_edit.setPlainText("No pending papers found in the database. Use the Import module to add more references.")
        self.counter_label.setText("0 of 0")
        self.nav_counter.setText("0 / 0")

    def make_decision(self, decision):
        if self.current_idx == -1 or not self.current_papers: return
        paper = self.current_papers[self.current_idx]
        reason = self.reason_input.text()
        
        # Get AI confidence if visible
        conf = None
        if hasattr(self, 'last_ai_result') and self.last_ai_result and self.last_ai_result.get("paper_id") == paper["id"]:
            conf = self.last_ai_result.get("confidence")

        self.manager.save_decision(paper["id"], decision, reason, conf)
        self.history.append(paper["id"])
        
        self.refresh_stats()
        self.main_window.data_changed.emit()
        self.go_next()

    def refresh_stats(self):
        stats = self.manager.get_screening_stats()
        self.pill_pending.setText(f"Pending: {stats['pending']}")
        self.pill_included.setText(f"Included: {stats['included']}")
        self.pill_excluded.setText(f"Excluded: {stats['excluded']}")
        self.pill_uncertain.setText(f"Uncertain: {stats['uncertain']}")
        self.pill_progress.setText(f"Progress: {stats['progress_pct']}%")
        self.lbl_bulk_pending.setText(f"{stats['pending']} papers pending")

    def show_screened_dialog(self):
        try:
            from modules.screener import ScreeningManager
            
            dlg = QDialog(self)
            dlg.setWindowTitle("Screened Papers")
            dlg.setMinimumSize(900, 650)
            dlg.setStyleSheet("""
                QDialog { background: #F5F6FA; font-family: Segoe UI; }
            """)
            
            layout = QVBoxLayout(dlg)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(12)
            
            # Title
            title_lbl = QLabel("Screened Papers")
            title_lbl.setStyleSheet("font-size:20px; font-weight:700; color:#1a1a2e;")
            layout.addWidget(title_lbl)
            
            # Filter row
            filter_row = QHBoxLayout()
            filter_row.setSpacing(8)
            
            def make_filter(text, fg, bg):
                b = QPushButton(text)
                b.setCheckable(True)
                b.setChecked(True)
                b.setFixedHeight(32)
                b.setStyleSheet(f"""
                    QPushButton {{ background:{bg}; color:{fg}; border:1.5px solid {fg}44; border-radius:8px; font-size:12px; font-weight:600; padding:0px 12px; }}
                    QPushButton:!checked {{ background:#F0F0F5; color:#bbb; border-color:#E0E0E0; }}
                """)
                return b
                
            f_inc = make_filter("\u2713 Included", "#1E8449", "#E8F8F0")
            f_exc = make_filter("\u2717 Excluded", "#C0392B", "#FDECEA")
            f_unc = make_filter("? Uncertain", "#B7770D", "#FEF5E7")
            
            search_box = QLineEdit()
            search_box.setPlaceholderText("Search by title or authors...")
            search_box.setFixedHeight(32)
            search_box.setStyleSheet("""
                QLineEdit { border:1.5px solid #E0E0E0; border-radius:8px; padding:4px 12px; font-size:13px; background:white; }
                QLineEdit:focus { border-color:#4A6CF7; }
            """)
            
            count_lbl = QLabel("")
            count_lbl.setStyleSheet("font-size:12px; color:#888;")
            count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
            filter_row.addWidget(f_inc)
            filter_row.addWidget(f_exc)
            filter_row.addWidget(f_unc)
            filter_row.addWidget(search_box, stretch=1)
            filter_row.addWidget(count_lbl)
            layout.addLayout(filter_row)
            
            # Table
            table = QTableWidget()
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["Decision", "Title", "Authors", "Year", "Reason"])
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.setAlternatingRowColors(True)
            table.verticalHeader().setVisible(False)
            table.setShowGrid(False)
            table.horizontalHeader().setStretchLastSection(True)
            table.setColumnWidth(0, 100)
            table.setColumnWidth(1, 340)
            table.setColumnWidth(2, 160)
            table.setColumnWidth(3, 60)
            table.setStyleSheet("""
                QTableWidget { background:white; border:1px solid #E8E8F0; border-radius:10px; font-size:13px; gridline-color: transparent; }
                QTableWidget::item { padding:8px; }
                QTableWidget::item:selected { background:#EEF2FF; color:#1a1a2e; }
                QHeaderView::section { background:#F0F2FF; color:#4A6CF7; font-weight:700; font-size:12px; padding:8px; border:none; border-bottom:2px solid #E0E0E0; }
            """)
            layout.addWidget(table, stretch=1)
            
            # Bottom row
            bottom_row = QHBoxLayout()
            
            export_btn = QPushButton("Export to Excel")
            export_btn.setFixedSize(140, 36)
            export_btn.setStyleSheet("""
                QPushButton { background:#4A6CF7; color:white; border:none; border-radius:8px; font-size:13px; font-weight:600; }
                QPushButton:hover { background:#3A5CE5; }
            """)
            # Export handler not provided in snippet, but we can call parent's export if available
            
            close_btn = QPushButton("Close")
            close_btn.setFixedSize(100, 36)
            close_btn.setStyleSheet("""
                QPushButton { background:white; color:#1a1a2e; border:1.5px solid #D0D0DA; border-radius:8px; font-size:13px; }
                QPushButton:hover { border-color:#4A6CF7; color:#4A6CF7; }
            """)
            close_btn.clicked.connect(dlg.accept)
            
            bottom_row.addWidget(export_btn)
            bottom_row.addStretch()
            bottom_row.addWidget(close_btn)
            layout.addLayout(bottom_row)
            
            def populate_table():
                try:
                    manager = ScreeningManager()
                    all_papers = manager.get_screened_papers()
                    
                    filtered = []
                    for p in all_papers:
                        d = p.get("screening_decision", "")
                        if d == "include" and f_inc.isChecked(): filtered.append(p)
                        elif d == "exclude" and f_exc.isChecked(): filtered.append(p)
                        elif d == "uncertain" and f_unc.isChecked(): filtered.append(p)
                        
                    search = search_box.text().strip().lower()
                    if search:
                        filtered = [p for p in filtered if search in p.get("title", "").lower() or search in p.get("authors", "").lower()]
                        
                    table.setRowCount(0)
                    decision_colors = {
                        "include": ("#1E8449", "#E8F8F0"),
                        "exclude": ("#C0392B", "#FDECEA"),
                        "uncertain": ("#B7770D", "#FEF5E7"),
                    }
                    
                    for row_idx, paper in enumerate(filtered):
                        table.insertRow(row_idx)
                        decision = paper.get("screening_decision", "")
                        fg, bg = decision_colors.get(decision, ("#555", "#F5F5FA"))
                        
                        # Decision
                        dec_item = QTableWidgetItem(decision.upper())
                        dec_item.setForeground(QColor(fg))
                        dec_item.setBackground(QColor(bg))
                        dec_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        dec_item.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
                        table.setItem(row_idx, 0, dec_item)
                        
                        # Title
                        table.setItem(row_idx, 1, QTableWidgetItem(paper.get("title", "")))
                        
                        # Authors
                        authors = paper.get("authors", "")
                        if len(authors) > 40: authors = authors[:40] + "..."
                        table.setItem(row_idx, 2, QTableWidgetItem(authors))
                        
                        # Year
                        table.setItem(row_idx, 3, QTableWidgetItem(str(paper.get("year", ""))))
                        
                        # Reason
                        table.setItem(row_idx, 4, QTableWidgetItem(paper.get("screening_reason", "") or ""))
                        
                        table.setRowHeight(row_idx, 40)
                        
                    count_lbl.setText(f"{len(filtered)} shown \u00b7 {len(all_papers)} total")
                except Exception as e:
                    logging.error(f"populate_table error: {e}")
                    
            f_inc.clicked.connect(populate_table)
            f_exc.clicked.connect(populate_table)
            f_unc.clicked.connect(populate_table)
            search_box.textChanged.connect(populate_table)
            
            def on_double_click(row, col):
                try:
                    title = table.item(row, 1).text()
                    # Find paper in parent's current list if possible, or reload from DB
                    # The prompt uses 'self.papers', but in this class it's 'self.current_papers'
                    for i, p in enumerate(self.current_papers):
                        if p.get("title") == title:
                            self.current_idx = i
                            self.show_paper(p)
                            dlg.accept()
                            return
                    # Fallback: find in screened papers (which might not be in the current_papers list if they were already excluded)
                    all_sc = manager.get_screened_papers()
                    for p in all_sc:
                         if p.get("title") == title:
                             # Add it back or just show it? 
                             # The easiest is just show_paper but that won't update current_idx correctly in the main flow
                             self.show_paper(p)
                             dlg.accept()
                             return
                except Exception as e:
                    logging.error(f"Double click match error: {e}")
                    
            table.cellDoubleClicked.connect(on_double_click)
            populate_table()
            dlg.exec()
            
        except Exception as e:
            logging.error(f"show_screened_dialog crash: {e}")
            QMessageBox.critical(self, "Error", f"Could not open screened papers: {e}")

    def go_next(self):
        if self.current_idx < len(self.current_papers) - 1:
            self.current_idx += 1
            self.show_paper(self.current_papers[self.current_idx])
        else:
            self.load_pending()

    def go_prev(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self.show_paper(self.current_papers[self.current_idx])

    def undo_last(self):
        paper = self.manager.undo_last_decision()
        if paper:
            self.load_pending()
            self.refresh_stats()
            self.main_window.data_changed.emit()

    def open_current_doi(self):
        doi = self.doi_label.property("url")
        if doi:
            if not doi.startswith("http"):
                doi = f"https://doi.org/{doi}"
            QDesktopServices.openUrl(QUrl(doi))

    def get_ai_suggestion(self):
        if self.current_idx == -1: return
        paper = self.current_papers[self.current_idx]
        self.btn_get_ai.setEnabled(False)
        self.btn_get_ai.setText("Asking AI...")
        
        self.ai_thread = AIThread(paper["title"], paper["abstract"])
        self.ai_thread.finished.connect(self.on_ai_suggestion_ready)
        self.ai_thread.start()

    def on_ai_suggestion_ready(self, result):
        try:
            self.btn_get_ai.setEnabled(True)
            self.btn_get_ai.setText("Get AI Suggestion")
            
            if not result or not isinstance(result, dict):
                result = {"decision": "uncertain", "confidence": 0, "reason": "AI returned empty response"}
                
            # Verify if this result is still for the current paper to avoid race conditions
            current_id = self.current_paper["id"] if hasattr(self, 'current_paper') and self.current_paper else None
            result_paper_id = result.get("paper_id")
            
            # If we tracked paper_id in thread, we can check it. 
            # If not, we just update the UI but use the stored paper_id for logging.
            self.last_ai_result = result
            self.last_ai_result["paper_id"] = current_id or "unknown"
        
            decision = result.get("decision", "uncertain")
            reason = result.get("reason", "No reason provided.")
            conf = result.get("confidence", 0)

            color = "#999999"
            if decision == "include": color = "#2ECC71"
            elif decision == "exclude": color = "#E74C3C"
            elif decision == "uncertain": color = "#F39C12"

            # New layout uses a single combined label
            self.ai_result_box.setText(f"<b>{decision.upper()}</b> ({conf}% confidence)<br/><br/>{reason}")
            self.ai_result_box.setStyleSheet(f"background: {color}15; border-radius: 8px; padding: 10px; color: #1a1a2e; font-size: 13px; border: 1px solid {color}33;")
            
            # Keep hidden logic for compatibility
            self.lbl_ai_decision.setStyleSheet(f"color: {color}; font-weight: bold; border: none; font-size: 15px;")
            self.ai_conf_bar.setValue(conf)
            self.ai_conf_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; }}")
            self.lbl_ai_reason.setText(reason)
            self.log_ai_result(self.current_paper["id"] if hasattr(self, 'current_paper') and self.current_paper else "unknown", result)
        except Exception as e:
            logging.error(f"Error updating AI suggestion UI: {e}")
            self.ai_result_box.setText(f"Error displaying suggestion: {e}")
            self.btn_get_ai.setEnabled(True)
            self.btn_get_ai.setText("Get AI Suggestion")

    def clear_ai_box(self):
        self.ai_result_box.setText("No suggestion yet")
        self.ai_result_box.setStyleSheet("background:#F5F6FA; border-radius:8px; padding:12px; font-size:13px; color:#555; border: 1px solid #E0E0E0;")
        self.lbl_ai_decision.setText("No suggestion yet")
        self.lbl_ai_decision.setStyleSheet("color: #999; font-weight: bold; border: none;")
        self.ai_conf_bar.setValue(0)
        self.lbl_ai_reason.setText("")
        self.last_ai_result = None

    def toggle_debug_log(self, checked):
        self.txt_debug_log.setVisible(checked)
        self.btn_toggle_debug.setText("Hide Debug Log" if checked else "Show Debug Log")

    def log_ai_result(self, paper_id, result):
        decision = result.get("decision", "uncertain")
        confidence = result.get("confidence", 0)
        reason = result.get("reason", "")
        
        if decision == "uncertain" and confidence == 0 and "not valid JSON" in reason:
             prefix = f"[Paper ID: {paper_id}] ERROR: "
        elif "did not respond" in reason:
             prefix = f"[Paper ID: {paper_id}] ERROR: "
        else:
             prefix = f"[Paper ID: {paper_id}] "
             
        msg = f"{prefix}Decision: {decision} | Confidence: {confidence}% | Reason: {reason}"
        
        # Limit log size to prevent GUI lag
        current_text = self.txt_debug_log.toPlainText()
        lines = current_text.splitlines()
        if len(lines) > 500:
            self.txt_debug_log.setPlainText("\n".join(lines[-400:]))
            
        self.txt_debug_log.append(msg)
        # Scroll to bottom
        self.txt_debug_log.verticalScrollBar().setValue(self.txt_debug_log.verticalScrollBar().maximum())

    def run_bulk_ai_screening(self):
        stats = self.manager.get_screening_stats()
        pending_count = stats["pending"]
        if pending_count == 0:
            QMessageBox.information(self, "No pending papers", "All papers have already been screened.")
            return
            
        est_min = round(pending_count * 7 / 60, 1)
        confirm = QMessageBox.question(self, "Bulk AI Screen", 
            f"This will screen all {pending_count} pending papers using Mistral 7B via Ollama.\n\n"
            f"Estimated time: {est_min} minutes\n\n"
            f"Make sure your inclusion/exclusion criteria are saved before starting.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
        if confirm == QMessageBox.StandardButton.Yes:
            self.btn_bulk_ai.setEnabled(False)
            self.bulk_dialog = BulkProgressDialog(pending_count, self)
            self.bulk_worker = BulkScreenWorker(self.manager)
            
            self.bulk_worker.progress.connect(self.bulk_dialog.update_status)
            self.bulk_worker.progress.connect(lambda cur, tot, title, inc, exc, unc: self.log_ai_result("BULK", {"decision": "progress", "confidence": int(cur/tot*100), "reason": f"Processing {title}"}))
            self.bulk_worker.finished.connect(self.on_bulk_finished)
            self.bulk_worker.error.connect(self.on_bulk_error)
            
            self.bulk_dialog.btn_cancel.clicked.connect(self.cancel_bulk)
            
            self.bulk_dialog.show()
            self.bulk_worker.start()

    def cancel_bulk(self):
        if hasattr(self, 'bulk_worker'):
            self.bulk_worker.cancelled = True
            self.bulk_dialog.btn_cancel.setText("Stopping...")
            self.bulk_dialog.btn_cancel.setEnabled(False)

    def on_bulk_finished(self, inc, exc, unc):
        self.bulk_dialog.close()
        total = inc + exc + unc
        QMessageBox.information(self, "Bulk Screening Complete", 
            f"Bulk screening complete!\n\nIncluded: {inc}\nExcluded: {exc}\nUncertain: {unc}\n\nTotal processed: {total} papers")
        
        self.refresh_stats()
        self.load_pending()
        self.main_window.data_changed.emit()
        self.btn_bulk_ai.setEnabled(True)

    def on_bulk_error(self, error_msg):
        self.bulk_dialog.close()
        QMessageBox.critical(
            self, "Bulk Screening Error", 
            f"An error occurred during bulk screening:\n\n{error_msg}\n\nCheck metascreener.log for details."
        )
        self.btn_bulk_ai.setEnabled(True)
        self.refresh_stats()
class AISummaryWorker(QThread):
    finished = pyqtSignal(str)
    
    def run(self):
        from modules.exporter import Exporter
        res = Exporter().generate_ai_summary_text()
        self.finished.emit(res)

class ExportPanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.prisma_temp_path = os.path.join(os.path.dirname(Config.DB_PATH), "temp_prisma.png")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 30)
        layout.setSpacing(20)

        title = QLabel("Export Results")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #1a1a2e; border-bottom: 2px solid #EAEAEA; padding-bottom: 12px; margin-bottom: 10px;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(24)

        # Card 1: PRISMA
        prisma_card = self.create_card("\ud83d\udcca PRISMA Flow Diagram", "Generate the PRISMA 2020 flow diagram as a PNG image based on your current screening progress.")
        p_layout = QVBoxLayout(prisma_card)
        p_layout.setContentsMargins(24, 70, 24, 24)
        
        preview_h = QHBoxLayout()
        self.prisma_preview = QLabel("No diagram generated")
        self.prisma_preview.setFixedSize(300, 400)
        self.prisma_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prisma_preview.setStyleSheet("border: 2px dashed #D0D0DA; background: #FAFAFA; color: #888; border-radius: 8px; font-weight: bold;")
        preview_h.addWidget(self.prisma_preview)
        
        btn_v = QVBoxLayout()
        self.btn_gen_prisma = QPushButton("\u26a1 Generate PRISMA Diagram")
        self.btn_gen_prisma.setFixedHeight(44)
        self.btn_gen_prisma.setStyleSheet("QPushButton { background: #4A6CF7; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 20px; } QPushButton:hover { background: #3A5CE5; }")
        self.btn_gen_prisma.clicked.connect(self.generate_prisma)
        
        self.btn_save_prisma = QPushButton("\ud83d\udcbe Save as PNG")
        self.btn_save_prisma.setFixedHeight(44)
        self.btn_save_prisma.setEnabled(False)
        self.btn_save_prisma.setStyleSheet("QPushButton { background: white; color: #2c3e50; border: 2px solid #D0D0DA; border-radius: 8px; font-size: 14px; font-weight: bold; padding: 0px 20px; } QPushButton:hover { background: #F8F9FA; border-color: #4A6CF7; color: #4A6CF7; } QPushButton:disabled { color: #bbb; border-color: #E8E8F0; background: #FAFAFA; }")
        self.btn_save_prisma.clicked.connect(self.save_prisma_as)
        
        btn_v.addWidget(self.btn_gen_prisma)
        btn_v.addSpacing(10)
        btn_v.addWidget(self.btn_save_prisma)
        btn_v.addStretch()
        preview_h.addSpacing(30)
        preview_h.addLayout(btn_v)
        preview_h.addStretch()
        
        p_layout.addLayout(preview_h)
        container_layout.addWidget(prisma_card)

        # Card 2: Excel
        excel_card = self.create_card("\ud83d\udcc4 Excel Export", "Export all screening data, extraction fields, and PRISMA numbers to a formatted Excel file.")
        e_layout = QVBoxLayout(excel_card)
        e_layout.setContentsMargins(24, 70, 24, 24)
        
        grid = QGridLayout()
        grid.setSpacing(15)
        
        chk_style = "QCheckBox { font-size: 14px; color: #2c3e50; font-weight: 500; } QCheckBox::indicator { width: 18px; height: 18px; }"
        self.chk_all = QCheckBox("All papers with screening decisions")
        self.chk_inc = QCheckBox("Included papers only")
        self.chk_exc = QCheckBox("Excluded papers with reasons")
        self.chk_ext = QCheckBox("Extraction data")
        self.chk_pri = QCheckBox("PRISMA numbers sheet")
        
        for chk in [self.chk_all, self.chk_inc, self.chk_exc, self.chk_ext, self.chk_pri]:
            chk.setChecked(True)
            chk.setStyleSheet(chk_style)
            
        grid.addWidget(self.chk_all, 0, 0)
        grid.addWidget(self.chk_inc, 0, 1)
        grid.addWidget(self.chk_exc, 1, 0)
        grid.addWidget(self.chk_ext, 1, 1)
        grid.addWidget(self.chk_pri, 2, 0)
        
        e_layout.addLayout(grid)
        e_layout.addSpacing(20)
        
        self.btn_export_excel = QPushButton("\ud83d\udce4 Export to Excel")
        self.btn_export_excel.setFixedHeight(48)
        self.btn_export_excel.setFixedWidth(240)
        self.btn_export_excel.setStyleSheet("QPushButton { background: #2ECC71; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 15px; padding: 0 20px; } QPushButton:hover { background: #27AE60; }")
        self.btn_export_excel.clicked.connect(self.export_excel)
        e_layout.addWidget(self.btn_export_excel)
        container_layout.addWidget(excel_card)

        # Card 3: Summary
        summary_card = self.create_card("\ud83d\udcc3 Summary Report", "Generate a text summary or let AI write an executive overview of your progress.")
        s_layout = QVBoxLayout(summary_card)
        s_layout.setContentsMargins(24, 70, 24, 24)
        s_layout.setSpacing(15)
        
        h_row = QHBoxLayout()
        btn_style_outline = "QPushButton { background: white; color: #2c3e50; border: 2px solid #D0D0DA; border-radius: 8px; font-size: 14px; font-weight: bold; padding: 0px 20px; } QPushButton:hover { background: #F8F9FA; border-color: #4A6CF7; color: #4A6CF7; } QPushButton:disabled { color: #bbb; border-color: #E8E8F0; background: #FAFAFA; }"
        
        self.btn_gen_report = QPushButton("Generate Standard Report")
        self.btn_gen_report.setFixedHeight(44)
        self.btn_gen_report.setStyleSheet(btn_style_outline)
        self.btn_gen_report.clicked.connect(self.generate_report)
        
        self.btn_gen_ai_report = QPushButton("\u2728 Generate AI Executive Summary")
        self.btn_gen_ai_report.setFixedHeight(44)
        self.btn_gen_ai_report.setStyleSheet("QPushButton { background: white; color: #4A6CF7; border: 2px solid #4A6CF7; border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 20px; } QPushButton:hover { background: #EEF2FF; } QPushButton:disabled { color: #888; border-color: #E8E8F0; }")
        self.btn_gen_ai_report.clicked.connect(self.generate_ai_report)
        
        self.btn_copy_report = QPushButton("\ud83d\udccb Copy to Clipboard")
        self.btn_copy_report.setFixedHeight(44)
        self.btn_copy_report.setStyleSheet(btn_style_outline)
        self.btn_copy_report.clicked.connect(self.copy_report)
        self.btn_copy_report.setEnabled(False)
        
        h_row.addWidget(self.btn_gen_report)
        h_row.addSpacing(10)
        h_row.addWidget(self.btn_gen_ai_report)
        h_row.addStretch()
        h_row.addWidget(self.btn_copy_report)
        s_layout.addLayout(h_row)
        
        self.txt_report = QTextEdit()
        self.txt_report.setReadOnly(True)
        self.txt_report.setMinimumHeight(200)
        self.txt_report.setStyleSheet("font-family: inherit; font-size: 14px; color: #2c3e50; background: #F8F9FA; border: 1px solid #EAEAEA; border-radius: 8px; padding: 12px; line-height: 1.5;")
        s_layout.addWidget(self.txt_report)
        container_layout.addWidget(summary_card)

        scroll.setWidget(container)
        layout.addWidget(scroll)

    def create_card(self, title_text, desc_text):
        card = QFrame()
        card.setStyleSheet("QFrame { background: white; border: 1px solid #EAEAEA; border-radius: 12px; }")
        
        title_lbl = QLabel(title_text, card)
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #1a1a2e; border: none; background: transparent;")
        title_lbl.move(24, 20)
        
        desc_lbl = QLabel(desc_text, card)
        desc_lbl.setStyleSheet("font-size: 14px; color: #7f8c8d; border: none; background: transparent;")
        desc_lbl.move(24, 45)
        
        return card

    def generate_prisma(self):
        try:
            gen = PRISMAGenerator()
            gen.generate_prisma_image(self.prisma_temp_path)
            pix = QPixmap(self.prisma_temp_path)
            self.prisma_preview.setPixmap(pix.scaled(300, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.btn_save_prisma.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not generate PRISMA diagram:\n{e}")

    def save_prisma_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save PRISMA Diagram", "PRISMA_Diagram.png", "Images (*.png)")
        if path:
            import shutil
            shutil.copy(self.prisma_temp_path, path)
            QMessageBox.information(self, "Success", "PRISMA diagram saved successfully.")

    def export_excel(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export to Excel", "MetaScreener_Export.xlsx", "Excel Files (*.xlsx)")
        if path:
            exp = Exporter()
            res = exp.export_to_excel(
                path,
                include_all=self.chk_all.isChecked(),
                include_only=self.chk_inc.isChecked(),
                include_excluded=self.chk_exc.isChecked(),
                include_extraction=self.chk_ext.isChecked(),
                include_prisma=self.chk_pri.isChecked()
            )
            if res.get("success"):
                QMessageBox.information(self, "Success", f"Data exported successfully to:\n{path}")
            else:
                QMessageBox.critical(self, "Error", f"Export failed:\n{res.get('error')}")

    def generate_report(self):
        exp = Exporter()
        report = exp.generate_summary_text()
        self.txt_report.setText(report)
        self.btn_copy_report.setEnabled(True)

    def generate_ai_report(self):
        self.btn_gen_ai_report.setEnabled(False)
        self.btn_gen_ai_report.setText("\u23f3 Generating...")
        self.txt_report.setText("Requesting executive summary from AI... Please wait.")
        self.btn_copy_report.setEnabled(False)
        
        self.ai_worker = AISummaryWorker()
        self.ai_worker.finished.connect(self.on_ai_summary_done)
        self.ai_worker.start()

    def on_ai_summary_done(self, report):
        self.txt_report.setText(report)
        self.btn_copy_report.setEnabled(True)
        self.btn_gen_ai_report.setEnabled(True)
        self.btn_gen_ai_report.setText("\u2728 Generate AI Executive Summary")

    def copy_report(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.txt_report.toPlainText())
        QMessageBox.information(self, "Copied", "Report copied to clipboard.")


class FulltextPanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.reviewer = FulltextReviewer()
        self.ft_papers = []
        self.current_ft_index = 0
        self.current_ft_paper = None
        self.pdf_doc = None
        self.zoom_factor = 1.0
        self.current_pdf_page = 0
        self.total_pages = 0
        
        self.init_ui()
        self.load_ft_papers()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Toolbar
        self.toolbar = QWidget()
        self.toolbar.setFixedHeight(75)
        self.toolbar.setStyleSheet("background: #FFFFFF; border-bottom: 2px solid #E8E8F0;")
        toolbar_layout = QHBoxLayout(self.toolbar)
        toolbar_layout.setContentsMargins(20, 10, 20, 10)
        toolbar_layout.setSpacing(15)

        btn_style_template = """
            QPushButton {{ background: {bg}; color: white; border: none; border-radius: 8px; font-size: 14px; font-weight: bold; padding: 0 15px; }}
            QPushButton:hover {{ background: {hover}; }}
        """

        self.btn_include = QPushButton("\u2705 Include")
        self.btn_include.setFixedSize(140, 44)
        self.btn_include.setStyleSheet(btn_style_template.format(bg="#2ECC71", hover="#27AE60"))
        self.btn_include.clicked.connect(lambda: self.ft_make_decision("include"))

        self.btn_exclude = QPushButton("\u274c Exclude")
        self.btn_exclude.setFixedSize(140, 44)
        self.btn_exclude.setStyleSheet(btn_style_template.format(bg="#E74C3C", hover="#C0392B"))
        self.btn_exclude.clicked.connect(lambda: self.ft_make_decision("exclude"))

        self.btn_uncertain = QPushButton("\u2754 Uncertain")
        self.btn_uncertain.setFixedSize(140, 44)
        self.btn_uncertain.setStyleSheet(btn_style_template.format(bg="#F39C12", hover="#D68910"))
        self.btn_uncertain.clicked.connect(lambda: self.ft_make_decision("uncertain"))

        def make_vdivider():
            d = QFrame()
            d.setFrameShape(QFrame.Shape.VLine)
            d.setFixedSize(1, 44)
            d.setStyleSheet("background: #E0E0E0; border: none;")
            return d

        toolbar_layout.addWidget(self.btn_include)
        toolbar_layout.addWidget(self.btn_exclude)
        toolbar_layout.addWidget(self.btn_uncertain)
        toolbar_layout.addWidget(make_vdivider())
        
        # Stats pills
        stats_w = QWidget()
        stats_w.setStyleSheet("background: #F8F9FA; border-radius: 12px; border: 1px solid #EAEAEA;")
        s_layout = QHBoxLayout(stats_w)
        s_layout.setContentsMargins(10, 5, 10, 5)
        s_layout.setSpacing(10)
        
        self.pill_review = make_pill("Review: 0", "#4A6CF7", "#EEF2FF", 90)
        self.pill_pdf = make_pill("PDF: 0", "#1E8449", "#E8F8F0", 90)
        self.pill_ft_inc = make_pill("Inc: 0", "#1E8449", "#E8F8F0", 90)
        self.pill_ft_exc = make_pill("Exc: 0", "#C0392B", "#FDECEA", 90)

        s_layout.addWidget(self.pill_review)
        s_layout.addWidget(self.pill_pdf)
        s_layout.addWidget(self.pill_ft_inc)
        s_layout.addWidget(self.pill_ft_exc)

        toolbar_layout.addStretch()
        toolbar_layout.addWidget(stats_w)
        toolbar_layout.addWidget(make_vdivider())

        self.btn_attach_folder = QPushButton("\ud83d\udcc2 Attach PDF Folder")
        self.btn_attach_folder.setFixedHeight(44)
        self.btn_attach_folder.setStyleSheet("""
            QPushButton { background: #F8F9FA; color: #34495e; border: 1px solid #D0D0DA; border-radius: 8px; font-weight: 600; font-size: 13px; padding: 0 20px; }
            QPushButton:hover { background: #E8E8F0; }
        """)
        self.btn_attach_folder.clicked.connect(self.attach_pdf_folder)
        toolbar_layout.addWidget(self.btn_attach_folder)

        self.main_layout.addWidget(self.toolbar)

        # Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.splitter.setHandleWidth(4)
        self.splitter.setStyleSheet("QSplitter::handle { background: #E8E8F0; }")

        # Left Panel (PDF Viewer)
        self.left_card = QWidget()
        self.left_card.setStyleSheet("background: white; border-right: 1px solid #E0E0E0;")
        left_layout = QVBoxLayout(self.left_card)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        pdf_toolbar = QWidget()
        pdf_toolbar.setFixedHeight(56)
        pdf_toolbar.setStyleSheet("background:#F8F9FA; border-bottom:1px solid #E8E8F0;")
        pdf_tb_layout = QHBoxLayout(pdf_toolbar)
        pdf_tb_layout.setContentsMargins(16, 8, 16, 8)
        pdf_tb_layout.setSpacing(12)

        self.pdf_title_label = QLabel("No paper selected")
        self.pdf_title_label.setStyleSheet("font-size:14px; font-weight:bold; color:#2c3e50;")

        nav_btn_style = """
            QPushButton { border: 1px solid #D0D0DA; border-radius: 6px; font-size: 16px; background: white; color: #333; }
            QPushButton:hover { background: #EEF2FF; border-color: #4A6CF7; color: #4A6CF7; }
        """

        self.page_prev_btn = QPushButton("\u2039")
        self.page_prev_btn.setFixedSize(32, 32)
        self.page_prev_btn.setStyleSheet(nav_btn_style)
        self.page_prev_btn.clicked.connect(self.prev_page)

        self.page_label = QLabel("Page 1 / 1")
        self.page_label.setStyleSheet("font-size:13px; font-weight: 500; color:#555; min-width:80px;")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.page_next_btn = QPushButton("\u203a")
        self.page_next_btn.setFixedSize(32, 32)
        self.page_next_btn.setStyleSheet(nav_btn_style)
        self.page_next_btn.clicked.connect(self.next_page)

        self.zoom_out_btn = QPushButton("\uff0d")
        self.zoom_out_btn.setFixedSize(32, 32)
        self.zoom_out_btn.setStyleSheet(nav_btn_style)
        self.zoom_out_btn.clicked.connect(self.zoom_out)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet("font-size:13px; font-weight: 500; color:#555; min-width:45px;")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.zoom_in_btn = QPushButton("\uff0b")
        self.zoom_in_btn.setFixedSize(32, 32)
        self.zoom_in_btn.setStyleSheet(nav_btn_style)
        self.zoom_in_btn.clicked.connect(self.zoom_in)

        self.attach_pdf_btn = QPushButton("\ud83d\udcce Attach PDF")
        self.attach_pdf_btn.setFixedHeight(36)
        self.attach_pdf_btn.setStyleSheet("""
            QPushButton { background: #4A6CF7; color: white; border: none; border-radius: 8px; font-size: 13px; font-weight: bold; padding: 0 16px; }
            QPushButton:hover { background: #3A5CE5; }
        """)
        self.attach_pdf_btn.clicked.connect(self.attach_pdf_for_paper)

        pdf_tb_layout.addWidget(self.pdf_title_label, stretch=1)
        pdf_tb_layout.addWidget(self.page_prev_btn)
        pdf_tb_layout.addWidget(self.page_label)
        pdf_tb_layout.addWidget(self.page_next_btn)
        pdf_tb_layout.addSpacing(10)
        pdf_tb_layout.addWidget(self.zoom_out_btn)
        pdf_tb_layout.addWidget(self.zoom_label)
        pdf_tb_layout.addWidget(self.zoom_in_btn)
        pdf_tb_layout.addSpacing(10)
        pdf_tb_layout.addWidget(self.attach_pdf_btn)

        left_layout.addWidget(pdf_toolbar)

        self.pdf_scroll = QScrollArea()
        self.pdf_scroll.setWidgetResizable(True)
        self.pdf_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.pdf_scroll.setStyleSheet("background: #E8E8EC;")

        self.pdf_container = QWidget()
        self.pdf_container.setStyleSheet("background: #E8E8EC;")
        self.pdf_container_layout = QVBoxLayout(self.pdf_container)
        self.pdf_container_layout.setContentsMargins(20, 20, 20, 20)
        self.pdf_container_layout.setSpacing(12)
        self.pdf_container_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self.no_pdf_widget = QWidget()
        no_pdf_layout = QVBoxLayout(self.no_pdf_widget)
        no_pdf_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        no_pdf_icon = QLabel("\ud83d\udcc4")
        no_pdf_icon.setStyleSheet("font-size:48px;")
        no_pdf_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        no_pdf_title = QLabel("No PDF attached")
        no_pdf_title.setStyleSheet("font-size:16px; font-weight:700; color:#888; margin-top:12px;")
        no_pdf_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        no_pdf_sub = QLabel("Click 'Attach PDF' to link a PDF file to this paper\nor use 'Attach PDF Folder' to auto-match a folder of PDFs")
        no_pdf_sub.setStyleSheet("font-size:13px; color:#aaa; margin-top:8px;")
        no_pdf_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        no_pdf_sub.setWordWrap(True)

        self.no_pdf_attach_btn = QPushButton("\ud83d\udcce  Attach PDF for this paper")
        self.no_pdf_attach_btn.setFixedSize(240, 44)
        self.no_pdf_attach_btn.setStyleSheet("""
            QPushButton { background: #4A6CF7; color: white; border: none; border-radius: 10px; font-size: 14px; font-weight: 600; margin-top: 16px; }
            QPushButton:hover { background: #3A5CE5; }
        """)
        self.no_pdf_attach_btn.clicked.connect(self.attach_pdf_for_paper)

        no_pdf_layout.addStretch()
        no_pdf_layout.addWidget(no_pdf_icon)
        no_pdf_layout.addWidget(no_pdf_title)
        no_pdf_layout.addWidget(no_pdf_sub)
        no_pdf_layout.addWidget(self.no_pdf_attach_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        no_pdf_layout.addStretch()

        self.pdf_container_layout.addWidget(self.no_pdf_widget)
        self.pdf_scroll.setWidget(self.pdf_container)
        left_layout.addWidget(self.pdf_scroll, stretch=1)

        self.splitter.addWidget(self.left_card)

        # Right Panel
        self.right_scroll = QScrollArea()
        self.right_scroll.setWidgetResizable(True)
        self.right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.right_scroll.setMinimumWidth(340)
        self.right_scroll.setMaximumWidth(450)
        self.right_scroll.setStyleSheet("background:#FAFAFA; border-left:1px solid #E0E0E0;")

        right_widget = QWidget()
        right_widget.setStyleSheet("background:#FAFAFA;")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(16)

        meta_card = QFrame()
        meta_card.setStyleSheet("QFrame { background: #FFFFFF; border-radius: 12px; border: 1px solid #EAEAEA; }")
        meta_layout = QVBoxLayout(meta_card)
        meta_layout.setContentsMargins(20, 20, 20, 20)
        meta_layout.setSpacing(10)

        self.ft_title_label = QLabel("Select a paper")
        self.ft_title_label.setWordWrap(True)
        self.ft_title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #1a1a2e;")
        self.ft_title_label.setMinimumHeight(40)

        self.ft_authors_label = QLabel("")
        self.ft_authors_label.setStyleSheet("font-size: 13px; color: #7f8c8d; font-style: italic;")
        self.ft_authors_label.setWordWrap(True)

        self.ft_year_doi_label = QLabel("")
        self.ft_year_doi_label.setOpenExternalLinks(True)
        self.ft_year_doi_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.ft_year_doi_label.setStyleSheet("""
            QLabel { font-size: 12px; color: #4A6CF7; text-decoration: none; }
            QLabel:hover { color: #2A4CD5; text-decoration: underline; }
        """)

        self.ft_screen_decision_label = QLabel("")
        self.ft_screen_decision_label.setStyleSheet("font-size: 12px; color: #888;")

        meta_layout.addWidget(self.ft_title_label)
        meta_layout.addWidget(self.ft_authors_label)
        meta_layout.addWidget(self.ft_year_doi_label)
        meta_layout.addWidget(self.ft_screen_decision_label)
        right_layout.addWidget(meta_card)

        hints = QLabel("I = Include    E = Exclude    U = Uncertain    Z = Undo")
        hints.setStyleSheet("font-size: 12px; font-weight: 500; color: #7f8c8d; background: #F5F6FA; border: 1px solid #EAEAEA; border-radius: 8px; padding: 10px;")
        hints.setWordWrap(True)
        hints.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(hints)

        self.excl_reason_label = QLabel("Reason for exclusion:")
        self.excl_reason_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #C0392B;")
        self.excl_reason_label.setVisible(False)

        self.excl_reason_combo = QComboBox()
        self.excl_reason_combo.addItems([
            "Wrong population", "Wrong intervention", "Wrong outcome", "Wrong study design",
            "Duplicate", "Full text not available", "Other",
        ])
        self.excl_reason_combo.setFixedHeight(44)
        input_style = "border: 1.5px solid #E74C3C; border-radius: 8px; padding: 5px 10px; font-size: 14px; background: white;"
        self.excl_reason_combo.setStyleSheet(f"QComboBox {{ {input_style} }} QComboBox:focus {{ border-color: #C0392B; }}")
        self.excl_reason_combo.setVisible(False)
        self.excl_reason_combo.currentTextChanged.connect(self.on_excl_reason_changed)

        self.excl_other_input = QLineEdit()
        self.excl_other_input.setPlaceholderText("Specify other reason...")
        self.excl_other_input.setFixedHeight(44)
        self.excl_other_input.setVisible(False)
        self.excl_other_input.setStyleSheet(f"QLineEdit {{ {input_style} }} QLineEdit:focus {{ border-color: #C0392B; }}")

        right_layout.addWidget(self.excl_reason_label)
        right_layout.addWidget(self.excl_reason_combo)
        right_layout.addWidget(self.excl_other_input)

        ai_header = QLabel("\u2728 AI Suggestion")
        ai_header.setStyleSheet("font-size: 15px; font-weight: bold; color: #1a1a2e; margin-top: 10px;")
        right_layout.addWidget(ai_header)

        self.ft_ai_result = QLabel("No suggestion yet")
        self.ft_ai_result.setWordWrap(True)
        self.ft_ai_result.setMinimumHeight(100)
        self.ft_ai_result.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.ft_ai_result.setStyleSheet("background: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 12px; padding: 16px; font-size: 13px; color: #2c3e50;")
        right_layout.addWidget(self.ft_ai_result)

        self.ft_get_ai_btn = QPushButton("\u26a1 Get AI Suggestion")
        self.ft_get_ai_btn.setFixedHeight(44)
        self.ft_get_ai_btn.setStyleSheet("""
            QPushButton { background: white; color: #4A6CF7; border: 2px solid #4A6CF7; border-radius: 8px; font-size: 14px; font-weight: bold; padding: 0 16px; margin-top: 5px; }
            QPushButton:hover { background: #EEF2FF; }
        """)
        self.ft_get_ai_btn.clicked.connect(self.ft_get_ai_suggestion)
        right_layout.addWidget(self.ft_get_ai_btn)

        right_layout.addStretch(1)
        self.right_scroll.setWidget(right_widget)
        self.splitter.addWidget(self.right_scroll)

        self.main_layout.addWidget(self.splitter, stretch=1)

        # Nav Bar
        self.nav_bar = QWidget()
        self.nav_bar.setFixedHeight(75)
        self.nav_bar.setStyleSheet("background:white; border-top:2px solid #E8E8F0;")
        nav_layout = QHBoxLayout(self.nav_bar)
        nav_layout.setContentsMargins(24, 12, 24, 12)
        nav_layout.setSpacing(15)

        nav_btn_style = """
            QPushButton { background: white; color: #2c3e50; border: 2px solid #D0D0DA; border-radius: 8px; font-size: 14px; font-weight: bold; padding: 0px 20px; }
            QPushButton:hover { background: #F8F9FA; border-color: #4A6CF7; color: #4A6CF7; }
            QPushButton:pressed { background: #EEF2FF; }
            QPushButton:disabled { color: #bbb; border-color: #E8E8F0; background: #FAFAFA; }
        """

        self.btn_prev = QPushButton("\u2190 Previous")
        self.btn_prev.setFixedHeight(44)
        self.btn_prev.setStyleSheet(nav_btn_style)
        self.btn_prev.clicked.connect(self.go_prev)

        self.btn_undo = QPushButton("\u21a9 Undo")
        self.btn_undo.setFixedHeight(44)
        self.btn_undo.setStyleSheet(nav_btn_style)
        self.btn_undo.clicked.connect(self.undo_last)

        self.nav_counter = QLabel("0 / 0")
        self.nav_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nav_counter.setStyleSheet("font-size:16px; font-weight:bold; color:#1a1a2e; background:#F5F6FA; border: 1px solid #EAEAEA; border-radius:8px; padding:4px 20px;")
        self.nav_counter.setFixedHeight(44)
        self.nav_counter.setMinimumWidth(120)

        self.btn_skip = QPushButton("Skip \u2192")
        self.btn_skip.setFixedHeight(44)
        self.btn_skip.setStyleSheet(nav_btn_style)
        self.btn_skip.clicked.connect(self.go_next)

        self.btn_next = QPushButton("Next \u2192")
        self.btn_next.setFixedHeight(44)
        self.btn_next.setStyleSheet("""
            QPushButton { background:#4A6CF7; color:white; border:none; border-radius:8px; font-size:14px; font-weight:bold; padding: 0px 30px; }
            QPushButton:hover { background: #3A5CE5; }
        """)
        self.btn_next.clicked.connect(self.go_next)

        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_undo)
        nav_layout.addStretch()
        nav_layout.addWidget(self.nav_counter)
        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_skip)
        nav_layout.addWidget(self.btn_next)

        self.main_layout.addWidget(self.nav_bar)

    def on_excl_reason_changed(self, text):
        self.excl_other_input.setVisible(text == "Other")

    def load_ft_papers(self):
        self.ft_papers = self.reviewer.get_included_papers()
        if self.ft_papers:
            self.show_paper(0)
        else:
            self.current_ft_index = -1
            self.current_ft_paper = None
            self.show_empty()
        self.update_stats()

    def show_paper(self, index):
        if not self.ft_papers or index < 0 or index >= len(self.ft_papers):
            return
        
        self.current_ft_index = index
        paper = self.ft_papers[index]
        self.current_ft_paper = paper

        self.ft_title_label.setText(paper.get("title", "No title"))
        self.ft_authors_label.setText(paper.get("authors", ""))
        doi = paper.get('doi', '').strip()
        if doi:
            if doi.startswith("http"):
                url = doi
            else:
                url = f"https://doi.org/{doi}"
            doi_html = f'<a href="{url}" style="color:#4A6CF7; text-decoration:none;">DOI: {doi}</a>'
        else:
            doi_html = '<span style="color:#aaa;">No DOI available</span>'
            
        self.ft_year_doi_label.setText(
            f"{paper.get('year','')}  |  {doi_html}"
        )
        self.ft_screen_decision_label.setText(f"Screened: included  |  Full-text: {paper.get('fulltext_decision','pending')}")
        self.pdf_title_label.setText(paper.get("title","")[:70])
        self.nav_counter.setText(f"{index+1} / {len(self.ft_papers)}")

        self.ft_ai_result.setText("No suggestion yet")
        self.ft_ai_result.setStyleSheet("background:#F5F6FA; border-radius:8px; padding:12px; font-size:13px; color:#555;")
        self.excl_reason_label.setVisible(False)
        self.excl_reason_combo.setVisible(False)
        self.excl_other_input.setVisible(False)

        pdf_path = paper.get("pdf_path", "")
        if pdf_path and os.path.exists(pdf_path):
            self.load_pdf(pdf_path)
        else:
            if self.pdf_doc:
                self.pdf_doc.close()
                self.pdf_doc = None
            self.no_pdf_widget.setVisible(True)
            self.clear_pdf_container()

    def show_empty(self):
        self.ft_title_label.setText("No papers included from screening yet")
        self.nav_counter.setText("0 / 0")
        self.pdf_title_label.setText("No paper selected")
        self.clear_pdf_container()
        self.no_pdf_widget.setVisible(True)

    def clear_pdf_container(self):
        for i in reversed(range(self.pdf_container_layout.count())):
            item = self.pdf_container_layout.itemAt(i)
            if item:
                w = item.widget()
                if w and w != self.no_pdf_widget:
                    w.deleteLater()

    def load_pdf(self, pdf_path):
        try:
            if self.pdf_doc:
                self.pdf_doc.close()
            self.pdf_doc = fitz.open(pdf_path)
            self.current_pdf_page = 0
            self.total_pages = len(self.pdf_doc)
            self.render_pdf_page(0)
        except Exception as e:
            logging.error(f"PDF load error: {e}")
            self.show_no_pdf_placeholder()

    def render_pdf_page(self, page_num):
        if self.pdf_doc is None: return
        self.clear_pdf_container()
        self.no_pdf_widget.setVisible(False)

        page = self.pdf_doc[page_num]
        mat = fitz.Matrix(self.zoom_factor * 1.5, self.zoom_factor * 1.5)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("ppm")

        qimg = QImage.fromData(img_data)
        pixmap = QPixmap.fromImage(qimg)

        page_label_widget = QLabel()
        page_label_widget.setPixmap(pixmap)
        page_label_widget.setStyleSheet("background:white; border-radius:4px;")
        page_label_widget.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.pdf_container_layout.addWidget(page_label_widget)
        self.page_label.setText(f"Page {page_num + 1} / {self.total_pages}")
        self.pdf_scroll.verticalScrollBar().setValue(0)

    def show_no_pdf_placeholder(self):
        self.clear_pdf_container()
        self.no_pdf_widget.setVisible(True)

    def zoom_in(self):
        self.zoom_factor = min(self.zoom_factor + 0.2, 3.0)
        self.zoom_label.setText(f"{int(self.zoom_factor * 100)}%")
        self.render_pdf_page(self.current_pdf_page)

    def zoom_out(self):
        self.zoom_factor = max(self.zoom_factor - 0.2, 0.4)
        self.zoom_label.setText(f"{int(self.zoom_factor * 100)}%")
        self.render_pdf_page(self.current_pdf_page)

    def next_page(self):
        if self.pdf_doc and self.current_pdf_page < self.total_pages - 1:
            self.current_pdf_page += 1
            self.render_pdf_page(self.current_pdf_page)

    def prev_page(self):
        if self.pdf_doc and self.current_pdf_page > 0:
            self.current_pdf_page -= 1
            self.render_pdf_page(self.current_pdf_page)

    def ft_get_ai_suggestion(self):
        if not self.current_ft_paper: return
        self.ft_get_ai_btn.setEnabled(False)
        self.ft_get_ai_btn.setText("Asking AI...")
        
        # Screen panel uses thread-based AI, we do same here
        self.ai_thread = AIThread(self.current_ft_paper["title"], self.current_ft_paper["abstract"])
        self.ai_thread.finished.connect(self.on_ft_ai_ready)
        self.ai_thread.start()

    def on_ft_ai_ready(self, result):
        self.ft_get_ai_btn.setEnabled(True)
        self.ft_get_ai_btn.setText("Get AI Suggestion")
        
        decision = result.get("decision", "uncertain")
        reason = result.get("reason", "No reason provided.")
        conf = result.get("confidence", 0)

        color = "#999999"
        if decision == "include": color = "#2ECC71"
        elif decision == "exclude": color = "#E74C3C"
        
        self.ft_ai_result.setText(f"<b>{decision.upper()}</b> ({conf}% confidence)<br/><br/>{reason}")
        self.ft_ai_result.setStyleSheet(f"background: {color}15; border-radius: 8px; padding: 12px; font-size: 13px; color: #1a1a2e; border: 1px solid {color}33;")

    def go_next(self):
        if self.current_ft_index < len(self.ft_papers) - 1:
            self.show_paper(self.current_ft_index + 1)

    def go_prev(self):
        if self.current_ft_index > 0:
            self.show_paper(self.current_ft_index - 1)

    def undo_last(self):
        if self.current_ft_paper:
            self.reviewer.save_fulltext_decision(self.current_ft_paper["id"], "pending", "")
            self.load_ft_papers()

    def ft_make_decision(self, decision):
        if not self.current_ft_paper: return
        reason = ""
        if decision == "exclude":
            if not self.excl_reason_combo.isVisible():
                self.excl_reason_label.setVisible(True)
                self.excl_reason_combo.setVisible(True)
                return # Give user chance to pick reason
            r = self.excl_reason_combo.currentText()
            if r == "Other":
                r = self.excl_other_input.text()
            reason = r
        
        self.reviewer.save_fulltext_decision(self.current_ft_paper["id"], decision, reason)
        self.update_stats()
        self.main_window.data_changed.emit()
        self.go_next()

    def update_stats(self):
        stats = self.reviewer.get_fulltext_stats()
        self.pill_review.setText(f"For Review: {stats['pending_review']}")
        self.pill_pdf.setText(f"PDF Attached: {stats['pdf_attached']}")
        self.pill_ft_inc.setText(f"FT Included: {stats['ft_included']}")
        self.pill_ft_exc.setText(f"FT Excluded: {stats['ft_excluded']}")

    def attach_pdf_for_paper(self):
        if not self.current_ft_paper: return
        path, _ = QFileDialog.getOpenFileName(self, "Select PDF", "", "PDF Files (*.pdf)")
        if path:
            self.reviewer.attach_pdf(self.current_ft_paper["id"], path)
            self.ft_papers[self.current_ft_index]["pdf_path"] = path
            self.load_pdf(path)
            self.update_stats()

    def attach_pdf_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select PDF Folder")
        if folder:
            result = self.reviewer.bulk_attach_pdfs(folder)
            QMessageBox.information(self, "PDF Folder Attached", 
                f"Matched and attached: {result['attached']} PDFs\nNot found: {result['not_found']} papers")
            self.load_ft_papers()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        total = self.splitter.width()
        if total > 0:
            self.splitter.setSizes([int(total * 0.72), int(total * 0.28)])

    def keyPressEvent(self, event):
        if not self.isVisible(): return
        key = event.key()
        if key == Qt.Key.Key_I: self.ft_make_decision("include")
        elif key == Qt.Key.Key_E: self.ft_make_decision("exclude")
        elif key == Qt.Key.Key_U: self.ft_make_decision("uncertain")
        elif key == Qt.Key.Key_Z: self.undo_last()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Space): self.go_next()
        elif key == Qt.Key.Key_Left: self.go_prev()
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    data_changed = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MetaScreener — Systematic Review Assistant")
        self.resize(1200, 800)
        
        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(200)
        self.sidebar.setStyleSheet("background-color: #FFFFFF; border-right: 2px solid #E8E8F0;")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(8)
        
        # Sidebar Logo
        logo_container = QWidget()
        logo_container.setFixedHeight(60)
        logo_container.setStyleSheet("border-bottom: 1px solid #E8E8F0;")
        logo_layout = QVBoxLayout(logo_container)
        logo_lbl = QLabel("MetaScreener")
        logo_lbl.setStyleSheet("font-size: 17px; font-weight: bold; color: #4A6CF7; padding-left: 20px; border: none;")
        logo_layout.addWidget(logo_lbl)
        sidebar_layout.addWidget(logo_container)
        sidebar_layout.addSpacing(10)
        
        nav_buttons = [
            "Dashboard", "Import", "Deduplicate", 
            "Screen", "Full-text", "Extract", "Export"
        ]
        
        self.stack = QStackedWidget()
        self.buttons = []
        
        for i, name in enumerate(nav_buttons):
            btn = QPushButton(name)
            btn.setFixedHeight(52)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 0px 20px;
                    border: none;
                    font-size: 15px;
                    font-family: Segoe UI;
                    background-color: #FFFFFF;
                    color: #1a1a2e;
                }
                QPushButton:hover {
                    background-color: #F0F2FF;
                }
                QPushButton:checked {
                    background-color: #EEF2FF;
                    border-left: 4px solid #4A6CF7;
                    color: #4A6CF7;
                    font-weight: 600;
                }
            """)
            btn.setCheckable(True)
            if i == 0:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, index=i: self.switch_page(index))
            sidebar_layout.addWidget(btn)
            self.buttons.append(btn)
            
            if name == "Dashboard":
                page = QWidget()
                page_layout = QVBoxLayout(page)
                
                title = QLabel("Dashboard")
                title.setStyleSheet("font-size: 22px; font-weight: 700; color: #1a1a2e; border-bottom: 2px solid #E8E8F0; padding-bottom: 10px; margin-bottom: 20px;")
                page_layout.addWidget(title)
                cards_grid = QGridLayout()
                cards_grid.setSpacing(16)
                cards_grid.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.stat_cards = {}
                labels = ["Total Papers", "Pending", "Included", "Excluded", "Uncertain", "Duplicates", "FT Included", "FT Excluded"]
                colors = ["#34495e", "#f39c12", "#27ae60", "#e74c3c", "#95a5a6", "#8e44ad", "#27ae60", "#e74c3c"]
                
                for i, (label_str, color) in enumerate(zip(labels, colors)):
                    card = QWidget()
                    card.setFixedSize(180, 120)
                    card.setStyleSheet(f"""
                        background-color: #FFFFFF;
                        border-radius: 12px;
                        border-top: 4px solid {color};
                    """)
                    
                    from PyQt6.QtWidgets import QGraphicsDropShadowEffect
                    from PyQt6.QtGui import QColor
                    shadow = QGraphicsDropShadowEffect()
                    shadow.setBlurRadius(15)
                    shadow.setColor(QColor(0, 0, 0, 20))
                    shadow.setOffset(0, 4)
                    card.setGraphicsEffect(shadow)
                    
                    c_layout = QVBoxLayout(card)
                    c_layout.addStretch()
                    
                    val_lbl = QLabel("0")
                    val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    val_lbl.setStyleSheet(f"font-size: 32px; font-weight: 700; color: {color}; border: none; background: transparent;")
                    
                    txt_lbl = QLabel(label_str)
                    txt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    txt_lbl.setStyleSheet("font-size: 13px; color: #888888; border: none; background: transparent; margin-top: 6px;")
                    
                    c_layout.addWidget(val_lbl)
                    c_layout.addWidget(txt_lbl)
                    c_layout.addStretch()
                    
                    cards_grid.addWidget(card, i // 4, i % 4)
                    self.stat_cards[label_str] = val_lbl
                
                page_layout.addLayout(cards_grid)
                
                btn_row = QHBoxLayout()
                btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
                
                refresh_btn = QPushButton("Refresh")
                refresh_btn.setFixedWidth(120)
                refresh_btn.setStyleSheet("padding: 8px; background-color: #FFFFFF; border-radius: 8px; border: 1.5px solid #C8C8D0;")
                refresh_btn.clicked.connect(self.refresh_dashboard)
                
                start_screening_btn = QPushButton("Start Screening")
                start_screening_btn.setFixedWidth(160)
                start_screening_btn.setObjectName("primary")
                start_screening_btn.clicked.connect(lambda: self.switch_page(3)) # Index 3 is Screen
                
                go_ft_btn = QPushButton("Go to Full-text Review")
                go_ft_btn.setFixedWidth(180)
                go_ft_btn.clicked.connect(lambda: self.switch_page(4))
                
                btn_row.addWidget(refresh_btn)
                btn_row.addSpacing(10)
                btn_row.addWidget(start_screening_btn)
                btn_row.addSpacing(10)
                btn_row.addWidget(go_ft_btn)
                page_layout.addLayout(btn_row)
                
                page_layout.addStretch()
                self.stack.addWidget(page)
                
            elif name == "Import":
                page = QWidget()
                page_layout = QVBoxLayout(page)
                
                lbl = QLabel("Import References")
                lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #1a1a2e; border-bottom: 2px solid #E8E8F0; padding-bottom: 10px; margin-bottom: 20px;")
                page_layout.addWidget(lbl)
                
                self.drop_area = DropArea(self)
                page_layout.addWidget(self.drop_area)
                
                self.import_summary_lbl = QLabel("Imported: 0 | Skipped (duplicates): 0 | Errors: 0")
                self.import_summary_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #27ae60; margin-top: 10px;")
                page_layout.addWidget(self.import_summary_lbl)
                
                self.log_box = QTextEdit()
                self.log_box.setReadOnly(True)
                self.log_box.setFixedHeight(120)
                self.log_box.setStyleSheet("font-family: monospace; font-size: 12px; background-color: #f8f9fa;")
                page_layout.addWidget(self.log_box)
                
                self.papers_table = QTableWidget()
                self.papers_table.setColumnCount(5)
                self.papers_table.setHorizontalHeaderLabels(["Title", "Authors", "Year", "DOI", "Source File"])
                self.papers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                self.papers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                self.papers_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
                self.papers_table.setAlternatingRowColors(True)
                page_layout.addWidget(self.papers_table)
                
                bottom_layout = QHBoxLayout()
                self.total_papers_lbl = QLabel("Total in database: 0 papers")
                self.total_papers_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #34495e;")
                
                clear_btn = QPushButton("\u26a0\ufe0f Clear Database / Start New Review")
                clear_btn.setStyleSheet("padding: 8px 15px; background-color: #e74c3c; color: white; border-radius: 4px; border: none;")
                clear_btn.clicked.connect(self.clear_all_papers)
                
                bottom_layout.addWidget(self.total_papers_lbl)
                bottom_layout.addStretch()
                bottom_layout.addWidget(clear_btn)
                
                page_layout.addLayout(bottom_layout)
                
                # Abstract Coverage Section
                self.coverage_group = QGroupBox("Abstract Coverage")
                self.coverage_group.setStyleSheet("""
                    QGroupBox {
                        font-weight: bold;
                        border: 1px solid #E0E0E0;
                        border-radius: 6px;
                        margin-top: 10px;
                        padding-top: 15px;
                        background: #FAFAFA;
                    }
                    QGroupBox::title {
                        subcontrol-origin: margin;
                        subcontrol-position: top left;
                        padding: 0 5px;
                        color: #1a1a2e;
                    }
                """)
                coverage_layout = QVBoxLayout(self.coverage_group)
                
                self.coverage_lbl = QLabel("0% of imported papers have abstracts (0 of 0 total)")
                self.coverage_lbl.setStyleSheet("font-size: 13px; color: #555;")
                coverage_layout.addWidget(self.coverage_lbl)
                
                self.coverage_table = QTableWidget()
                self.coverage_table.setColumnCount(4)
                self.coverage_table.setHorizontalHeaderLabels(["Source File", "Total Papers", "With Abstract", "Coverage %"])
                self.coverage_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                self.coverage_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                self.coverage_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
                self.coverage_table.setFixedHeight(120)
                coverage_layout.addWidget(self.coverage_table)
                
                coverage_btn_row = QHBoxLayout()
                self.btn_reimport_missing = QPushButton("Re-import Missing Abstracts")
                self.btn_reimport_missing.setStyleSheet("padding: 6px 15px; background-color: #f39c12; color: white; border-radius: 4px; border: none;")
                # Note: Click handler logic for re-import will be added to the class separately
                self.btn_reimport_missing.clicked.connect(self.reimport_abstracts)
                coverage_btn_row.addStretch()
                coverage_btn_row.addWidget(self.btn_reimport_missing)
                coverage_layout.addLayout(coverage_btn_row)
                
                page_layout.addWidget(self.coverage_group)
                
                self.stack.addWidget(page)
                
            elif name == "Deduplicate":
                page = QWidget()
                page_layout = QVBoxLayout(page)
                
                lbl = QLabel("Deduplication")
                lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #1a1a2e; border-bottom: 2px solid #E8E8F0; padding-bottom: 10px; margin-bottom: 20px;")
                page_layout.addWidget(lbl)
                
                top_layout = QHBoxLayout()
                
                # Replace top bar with detection methods panel
                method_group = QGroupBox("Detection methods")
                method_layout = QVBoxLayout(method_group)
                method_layout.setContentsMargins(20, 20, 20, 20)
                method_layout.setSpacing(12)
                
                self.chk_pmid = QCheckBox("PMID exact")
                self.chk_pmid.setChecked(True)
                self.chk_pmid.setStyleSheet("spacing: 16px;")
                
                self.chk_doi = QCheckBox("DOI exact")
                self.chk_doi.setChecked(True)
                self.chk_doi.setStyleSheet("spacing: 16px;")
                
                self.chk_title_exact = QCheckBox("Title exact")
                self.chk_title_exact.setChecked(True)
                self.chk_title_exact.setStyleSheet("spacing: 16px;")
                
                self.chk_title_fuzzy = QCheckBox("Title fuzzy")
                self.chk_title_fuzzy.setChecked(True)
                self.chk_title_fuzzy.setStyleSheet("spacing: 16px;")
                
                slider_row = QHBoxLayout()
                slider_label = QLabel("Fuzzy threshold:")
                slider_label.setStyleSheet("font-size: 15px;")
                
                self.slider_fuzzy = QSlider(Qt.Orientation.Horizontal)
                self.slider_fuzzy.setRange(70, 99)
                self.slider_fuzzy.setValue(92)
                self.slider_fuzzy.setMinimumWidth(300)
                
                self.lbl_fuzzy_val = QLabel("92%")
                self.lbl_fuzzy_val.setStyleSheet("font-size: 15px; font-weight: bold; color: #4A6CF7;")
                
                self.slider_fuzzy.valueChanged.connect(lambda val: self.lbl_fuzzy_val.setText(f"{val}%"))
                self.chk_title_fuzzy.toggled.connect(self.slider_fuzzy.setEnabled)
                
                slider_row.addWidget(slider_label)
                slider_row.addWidget(self.slider_fuzzy)
                slider_row.addWidget(self.lbl_fuzzy_val)
                slider_row.addStretch()
                
                method_layout.addWidget(self.chk_pmid)
                method_layout.addWidget(self.chk_doi)
                method_layout.addWidget(self.chk_title_exact)
                method_layout.addWidget(self.chk_title_fuzzy)
                method_layout.addLayout(slider_row)
                
                top_layout.addWidget(method_group)
                
                actions_layout = QVBoxLayout()
                actions_layout.setSpacing(10)
                self.btn_find_dupes = QPushButton("Run Deduplication")
                self.btn_view_matrix = QPushButton("View Similarity Matrix")
                
                for btn in [self.btn_find_dupes, self.btn_view_matrix]:
                    btn.setMinimumWidth(180)
                    btn.setFixedHeight(40)
                
                actions_layout.addWidget(self.btn_find_dupes)
                actions_layout.addWidget(self.btn_view_matrix)
                actions_layout.addStretch()
                top_layout.addLayout(actions_layout)
                
                lbl_layout = QVBoxLayout()
                self.lbl_dupe_stats = QLabel("Total: 0 | Unique: 0 | Duplicates: 0")
                self.lbl_dupe_stats.setStyleSheet("font-weight: bold; font-size: 15px; color: #1a1a2e;")
                lbl_layout.addWidget(self.lbl_dupe_stats)
                
                self.dupe_progress = QProgressBar()
                self.dupe_progress.setVisible(False)
                
                btns_h = QHBoxLayout()
                self.btn_auto_resolve = QPushButton("Auto-resolve All")
                self.btn_mark_reviewed = QPushButton("Mark All Reviewed as Duplicate")
                
                for btn in [self.btn_auto_resolve, self.btn_mark_reviewed]:
                    btn.setMinimumWidth(180)
                    btn.setFixedHeight(40)
                    
                btns_h.addWidget(self.btn_auto_resolve)
                btns_h.addWidget(self.btn_mark_reviewed)
                btns_h.addStretch()
                
                lbl_layout.addLayout(btns_h)
                lbl_layout.addWidget(self.dupe_progress)
                top_layout.addLayout(lbl_layout)
                
                page_layout.addLayout(top_layout)
                
                self.dupe_tree = QTreeWidget()
                self.dupe_tree.setColumnCount(8)
                self.dupe_tree.setHeaderLabels(["Keep", "Title", "Authors", "Year", "DOI", "Source", "Similarity", "Method"])
                self.dupe_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
                page_layout.addWidget(self.dupe_tree)
                
                self.lbl_dupe_summary_bar = QLabel("Found by PMID only: 0 | DOI only: 0 | Title only: 0 | Multiple methods: 0")
                self.lbl_dupe_summary_bar.setStyleSheet("font-weight: bold; font-size: 12px; color: #7f8c8d; margin-top: 5px; margin-bottom: 5px;")
                page_layout.addWidget(self.lbl_dupe_summary_bar)
                
                bottom_layout = QHBoxLayout()
                self.lbl_dupe_groups_found = QLabel("0 duplicate groups found")
                self.lbl_dupe_groups_found.setStyleSheet("font-size: 14px; color: #888;")
                
                self.btn_apply_dupe_decisions = QPushButton("Apply Decisions")
                self.btn_show_all_dupes = QPushButton("Show All Duplicates")
                
                bottom_layout.addWidget(self.lbl_dupe_groups_found)
                bottom_layout.addStretch()
                bottom_layout.addWidget(self.btn_apply_dupe_decisions)
                bottom_layout.addWidget(self.btn_show_all_dupes)
                
                page_layout.addLayout(bottom_layout)
                self.stack.addWidget(page)
                
                self.btn_find_dupes.clicked.connect(self.start_duplicate_search)
                self.btn_view_matrix.clicked.connect(self.view_similarity_matrix)
                self.btn_auto_resolve.clicked.connect(self.auto_resolve_duplicates)
                self.btn_mark_reviewed.clicked.connect(self.apply_dupe_decisions)
                self.btn_apply_dupe_decisions.clicked.connect(self.apply_dupe_decisions)
                self.btn_show_all_dupes.clicked.connect(self.toggle_show_all_dupes)
                
            elif name == "Screen":
                self.screen_panel = ScreeningPanel(self)
                self.stack.addWidget(self.screen_panel)
                self.data_changed.connect(self.screen_panel.refresh_stats)
                self.data_changed.connect(self.screen_panel.load_pending)
            elif name == "Full-text":
                self.fulltext_panel = FulltextPanel(self)
                self.stack.addWidget(self.fulltext_panel)
                self.data_changed.connect(self.fulltext_panel.update_stats)
                self.data_changed.connect(self.fulltext_panel.load_ft_papers)
            elif name == "Extract":
                self.extract_panel = ExtractionPanel(self)
                self.stack.addWidget(self.extract_panel)
                self.data_changed.connect(self.extract_panel.populate_paper_list)
                self.data_changed.connect(self.extract_panel.update_extract_stats)
            elif name == "Export":
                self.export_panel = ExportPanel(self)
                self.stack.addWidget(self.export_panel)
            
        sidebar_layout.addStretch()
        
        # Add sidebar and stack to main layout
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.stack)
        
        # Status Bar
        from config import Config as _Cfg
        _Cfg.load()
        _provider = getattr(_Cfg, "AI_PROVIDER", "ollama") or "ollama"
        self.statusBar().showMessage(f"AI Provider: {_provider} — checking connection…")

        # Start AI provider status check worker
        self.ollama_worker = OllamaStatusWorker()
        self.ollama_worker.status_ready.connect(self.update_ollama_status)
        self.ollama_worker.start()
        
        # Connect data change signal to dashboard refresh
        self.data_changed.connect(self.refresh_dashboard)

    def update_ollama_status(self, connected, model_name):
        from config import Config as _Cfg
        from modules.ai_client import PROVIDER_LABELS
        _Cfg.load()
        provider_key = getattr(_Cfg, "AI_PROVIDER", "ollama") or "ollama"
        provider_label = PROVIDER_LABELS.get(provider_key, provider_key)
        if connected:
            model_str = model_name or "unknown model"
            self.statusBar().showMessage(f"{provider_label} \u2014 Connected \u00b7 {model_str}")
            self.statusBar().setStyleSheet("color: #2ECC71;")
        else:
            if provider_key == "ollama":
                hint = " \u2014 start Ollama or switch provider in Settings"
            else:
                hint = " \u2014 check API key in Settings"
            self.statusBar().showMessage(f"{provider_label}: Not connected{hint}")
            self.statusBar().setStyleSheet("color: #E74C3C;")

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.buttons):
            btn.setChecked(i == index)
            
        if self.buttons[index].text() == "Dashboard":
            self.refresh_dashboard()
        elif self.buttons[index].text() == "Import":
            self.refresh_papers_table()
        elif self.buttons[index].text() == "Deduplicate":
            self.refresh_dupe_stats()

    def browse_files(self):
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, "Select Reference Files", "", "Reference files (*.ris *.bib *.csv *.txt)"
        )
        if filepaths:
            self.process_files(filepaths)

    def process_files(self, filepaths):
        importer = PaperImporter()
        total_imp = 0
        total_skip = 0
        total_err = 0
        
        for fp in filepaths:
            import os
            filename = os.path.basename(fp)
            ext = os.path.splitext(fp)[1].lower()
            
            res = importer.import_file(fp)
            
            n = res.get("imported", 0)
            s = res.get("skipped", 0)
            
            total_imp += n
            total_skip += s
            total_err += len(res.get("errors", []))
            
            log_text = f"File: {filename}  |  Imported: {n}  |  Skipped: {s}  |  Format detected: {ext}"
            self.log_box.append(log_text)
            if n == 0:
                self.log_box.append("WARNING: 0 records imported. Check log for format detection details.")
            
        self.import_summary_lbl.setText(f"Imported: {total_imp} | Skipped (duplicates): {total_skip} | Errors: {total_err}")
        self.refresh_papers_table()
        self.data_changed.emit()

    def refresh_papers_table(self):
        importer = PaperImporter()
        papers = sorted(importer.get_all_papers(), key=lambda x: x['id'], reverse=True)
        self.total_papers_lbl.setText(f"Total in database: {len(papers)} papers")
        
        self.papers_table.setRowCount(len(papers))
        for row, p in enumerate(papers):
            self.papers_table.setItem(row, 0, QTableWidgetItem(p.get('title', "")))
            self.papers_table.setItem(row, 1, QTableWidgetItem(p.get('authors', "")))
            self.papers_table.setItem(row, 2, QTableWidgetItem(str(p.get('year', ""))))
            self.papers_table.setItem(row, 3, QTableWidgetItem(p.get('doi', "")))
            self.papers_table.setItem(row, 4, QTableWidgetItem(p.get('source_file', "")))
        
        self.refresh_abstract_coverage()
        
    def refresh_abstract_coverage(self):
        importer = PaperImporter()
        cov = importer.get_abstract_coverage()
        self.coverage_lbl.setText(f"{cov['coverage_pct']}% of imported papers have abstracts ({cov['with_abstract']} of {cov['total']} total)")
        
        sources = cov.get("by_source", [])
        self.coverage_table.setRowCount(len(sources))
        
        for row, src in enumerate(sources):
            # Items
            itm_src = QTableWidgetItem(src["source"])
            itm_total = QTableWidgetItem(str(src["total"]))
            itm_abs = QTableWidgetItem(str(src["with_abstract"]))
            itm_pct = QTableWidgetItem(f"{src['pct']}%")
            
            # Align center for numbers
            itm_total.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            itm_abs.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            itm_pct.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Colors
            pct = src["pct"]
            bg_color = None
            if pct == 0:
                bg_color = QColor("#FDECEA") # Red
            elif pct < 50:
                bg_color = QColor("#FEF5E7") # Orange
                
            if bg_color:
                itm_src.setBackground(bg_color)
                itm_total.setBackground(bg_color)
                itm_abs.setBackground(bg_color)
                itm_pct.setBackground(bg_color)
                
            self.coverage_table.setItem(row, 0, itm_src)
            self.coverage_table.setItem(row, 1, itm_total)
            self.coverage_table.setItem(row, 2, itm_abs)
            self.coverage_table.setItem(row, 3, itm_pct)

    def reimport_abstracts(self):
        filepaths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Files to Re-import",
            "",
            "Supported Formats (*.ris *.bib *.csv *.txt);;All Files (*.*)"
        )
        for path in filepaths:
            self.process_import(path)

    def clear_all_papers(self):
        reply = QMessageBox.question(
            self, 'Confirm Deep Clear',
            'Are you sure you want to delete ALL papers and extracted data from the database?\n\nThis will completely reset the system for a new review and cannot be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            import sqlite3
            from config import Config
            conn = sqlite3.connect(Config.DB_PATH)
            cur = conn.cursor()
            cur.execute("DELETE FROM papers")
            
            # Check if extraction table exists safely before deleting
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='extraction'")
            if cur.fetchone():
                cur.execute("DELETE FROM extraction")
                
            conn.commit()
            conn.close()
            
            self.refresh_papers_table()
            self.data_changed.emit()
            self.import_summary_lbl.setText("Imported: 0 | Skipped (duplicates): 0 | Errors: 0")
            self.log_box.clear()
            self.refresh_dashboard()

    def refresh_dashboard(self):
        importer = PaperImporter()
        stats = importer.get_stats()
        
        self.stat_cards["Total Papers"].setText(str(stats["total"]))
        self.stat_cards["Pending"].setText(str(stats["pending"]))
        self.stat_cards["Included"].setText(str(stats["included"]))
        self.stat_cards["Excluded"].setText(str(stats["excluded"]))
        self.stat_cards["Uncertain"].setText(str(stats["uncertain"]))
        
        from modules.deduplicator import Deduplicator
        dupe_stats = Deduplicator().get_duplicate_stats()
        self.stat_cards["Duplicates"].setText(str(dupe_stats["duplicates"]))

        # Optional: Add FT stats if cards exist
        ft_stats = FulltextReviewer().get_fulltext_stats()
        if "FT Included" in self.stat_cards:
            self.stat_cards["FT Included"].setText(str(ft_stats["ft_included"]))
        if "FT Excluded" in self.stat_cards:
            self.stat_cards["FT Excluded"].setText(str(ft_stats["ft_excluded"]))

    def refresh_dupe_stats(self):
        from modules.deduplicator import Deduplicator
        stats = Deduplicator().get_duplicate_stats()
        self.lbl_dupe_stats.setText(f"Total: {stats['total']} | Unique: {stats['unique']} | Duplicates: {stats['duplicates']}")

    def view_similarity_matrix(self):
        from modules.deduplicator import Deduplicator
        dialog = SimilarityMatrixDialog(Deduplicator(), self)
        dialog.exec()

    def start_duplicate_search(self):
        methods = []
        if self.chk_pmid.isChecked(): methods.append("pmid")
        if self.chk_doi.isChecked(): methods.append("doi")
        if self.chk_title_exact.isChecked(): methods.append("title_exact")
        if self.chk_title_fuzzy.isChecked(): methods.append("title_fuzzy")
        
        fuzzy_threshold = self.slider_fuzzy.value()
        
        from modules.deduplicator import Deduplicator, DuplicateSearchWorker
        self.dupe_progress.setVisible(True)
        self.dupe_progress.setValue(0)
        self.btn_find_dupes.setEnabled(False)
        self.dupe_worker = DuplicateSearchWorker(Deduplicator(), methods=methods, fuzzy_threshold=fuzzy_threshold)
        self.dupe_worker.progress.connect(self.update_dupe_progress)
        self.dupe_worker.finished.connect(self.on_duplicate_search_finished)
        self.dupe_worker.start()

    def update_dupe_progress(self, current, total):
        self.dupe_progress.setMaximum(max(total, 1))
        self.dupe_progress.setValue(current)

    def on_duplicate_search_finished(self, duplicate_groups):
        self.btn_find_dupes.setEnabled(True)
        self.dupe_progress.setVisible(False)
        self.duplicate_groups = duplicate_groups
        self.lbl_dupe_groups_found.setText(f"{len(duplicate_groups)} duplicate groups found")
        self.populate_duplicate_tree(duplicate_groups)

    def populate_duplicate_tree(self, duplicate_groups):
        self.dupe_tree.clear()
        self.is_showing_all_dupes = False
        self.btn_show_all_dupes.setText("Show All Duplicates")
        self.dupe_tree.setColumnCount(8)
        self.dupe_tree.setHeaderLabels(["Keep", "Title", "Authors", "Year", "DOI", "Source", "Similarity", "Method"])
        
        pmid_only = 0
        doi_only = 0
        title_only = 0
        multiple = 0
        
        for group in duplicate_groups:
            papers = group["papers"]
            sim = group["similarity_score"]
            methods = group.get("match_methods", [])
            method_str = ", ".join(methods)
            
            if len(methods) > 1:
                multiple += 1
            elif methods and "PMID" in methods[0]:
                pmid_only += 1
            elif methods and "DOI" in methods[0]:
                doi_only += 1
            elif methods and "Title" in methods[0]:
                title_only += 1
            
            parent = QTreeWidgetItem(self.dupe_tree)
            parent.setText(1, f"Group — {int(sim)}% similar — {len(papers)} papers — [{method_str}]")
            parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            parent.setCheckState(0, Qt.CheckState.Checked)
            parent.setExpanded(True)
            
            bg = QButtonGroup(self.dupe_tree)
            keep_id = group["suggested_keep"]["id"]
            parent.setData(0, Qt.ItemDataRole.UserRole, [])
            
            for p in papers:
                child = QTreeWidgetItem(parent)
                child.setText(1, p.get("title", ""))
                child.setText(2, p.get("authors", ""))
                child.setText(3, str(p.get("year", "")))
                child.setText(4, p.get("doi", ""))
                child.setText(5, p.get("source_file", ""))
                child.setText(6, f"{int(sim)}%")
                
                # Apply method badge color logic to the method column text based on match format
                if "PMID" in method_str:
                    child.setForeground(7, QBrush(QColor(41, 128, 185))) # blue
                elif "DOI" in method_str:
                    child.setForeground(7, QBrush(QColor(39, 174, 96))) # green
                elif "exact" in method_str:
                    child.setForeground(7, QBrush(QColor(211, 84, 0))) # orange
                else:
                    child.setForeground(7, QBrush(QColor(142, 68, 173))) # purple
                    
                child.setText(7, method_str)
                child.setData(0, Qt.ItemDataRole.UserRole, p["id"])
                
                rb = QRadioButton()
                bg.addButton(rb)
                self.dupe_tree.setItemWidget(child, 0, rb)
                
                rg_list = parent.data(0, Qt.ItemDataRole.UserRole)
                rg_list.append((p["id"], rb))
                parent.setData(0, Qt.ItemDataRole.UserRole, rg_list)
                
                if p["id"] == keep_id:
                    rb.setChecked(True)
                    for i in range(1, 8):
                        child.setBackground(i, QBrush(QColor(200, 255, 200)))
                else:
                    for i in range(1, 8):
                        child.setBackground(i, QBrush(QColor(255, 200, 200)))
                        
        self.lbl_dupe_summary_bar.setText(f"Found by PMID only: {pmid_only} | DOI only: {doi_only} | Title only: {title_only} | Multiple methods: {multiple}")

    def auto_resolve_duplicates(self):
        if not hasattr(self, 'duplicate_groups') or not self.duplicate_groups:
            return
        reply = QMessageBox.question(
            self, 'Auto-resolve All',
            'This will keep the most complete record from each duplicate group and mark the rest. Continue?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            from modules.deduplicator import Deduplicator
            dedup = Deduplicator()
            dedup.auto_resolve(self.duplicate_groups)
            self.refresh_dupe_stats()
            self.data_changed.emit()
            self.dupe_tree.clear()
            self.duplicate_groups = []
            self.lbl_dupe_groups_found.setText("0 duplicate groups found")

    def apply_dupe_decisions(self):
        if hasattr(self, 'is_showing_all_dupes') and self.is_showing_all_dupes:
            return
            
        from modules.deduplicator import Deduplicator
        dedup = Deduplicator()
        
        root = self.dupe_tree.invisibleRootItem()
        groups_to_remove = []
        
        records_kept = 0
        records_marked = 0
        
        for i in range(root.childCount()):
            parent = root.child(i)
            if parent.checkState(0) == Qt.CheckState.Checked:
                rg_list = parent.data(0, Qt.ItemDataRole.UserRole)
                if rg_list:
                    kept_id = None
                    for pid, rb in rg_list:
                        if rb.isChecked():
                            kept_id = pid
                            break
                    
                    if kept_id is not None:
                        for pid, rb in rg_list:
                            if pid != kept_id:
                                dedup.mark_as_duplicate(pid)
                                records_marked += 1
                            else:
                                records_kept += 1
                        groups_to_remove.append(parent)
                        
        for g in groups_to_remove:
            root.removeChild(g)
            
        self.refresh_dupe_stats()
        self.data_changed.emit()
        
        final_stats = dedup.get_duplicate_stats()
        pending_review = final_stats['unique']
        
        QMessageBox.information(
            self, 'Deduplication Complete',
            f'Deduplication complete.\nKept: {records_kept} papers.\nMarked as duplicate: {records_marked} papers.\nReady for screening: {pending_review} papers.'
        )

    def toggle_show_all_dupes(self):
        if not hasattr(self, 'is_showing_all_dupes') or not self.is_showing_all_dupes:
            self.show_all_duplicates()
        else:
            if hasattr(self, 'duplicate_groups'):
                self.populate_duplicate_tree(self.duplicate_groups)
            else:
                self.populate_duplicate_tree([])

    def show_all_duplicates(self):
        self.is_showing_all_dupes = True
        self.btn_show_all_dupes.setText("Back to Groups")
        self.dupe_tree.clear()
        
        self.dupe_tree.setColumnCount(6)
        self.dupe_tree.setHeaderLabels(["Action", "Title", "Authors", "Year", "DOI", "Source"])
        
        import sqlite3
        from config import Config
        try:
            conn = sqlite3.connect(Config.DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM papers WHERE is_duplicate = 1")
            for row in cursor.fetchall():
                child = QTreeWidgetItem(self.dupe_tree)
                child.setText(1, row["title"])
                child.setText(2, row["authors"])
                child.setText(3, str(row["year"]))
                child.setText(4, row["doi"])
                child.setText(5, row["source_file"])
                
                unmark_btn = QPushButton("Unmark")
                pid = row["id"]
                unmark_btn.clicked.connect(lambda ch, idx=pid, item=child: self.unmark_duplicate(idx, item))
                self.dupe_tree.setItemWidget(child, 0, unmark_btn)
                
            conn.close()
        except:
            pass

    def unmark_duplicate(self, pid, item):
        from modules.deduplicator import Deduplicator
        Deduplicator().mark_as_not_duplicate(pid)
        root = self.dupe_tree.invisibleRootItem()
        root.removeChild(item)
        self.refresh_dupe_stats()
        self.refresh_dashboard()

class FieldManagerDialog(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Manage Extraction Fields")
        self.setFixedSize(600, 500)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        lbl = QLabel("Extraction Fields")
        lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #4A6CF7;")
        layout.addWidget(lbl)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name", "Label", "Type", "Options (comma-separated)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 100)
        layout.addWidget(self.table)
        
        self.load_fields()
        
        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Field")
        add_btn.clicked.connect(self.add_field)
        save_btn = QPushButton("Save & Close")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self.save_and_close)
        
        btn_row.addWidget(add_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def load_fields(self):
        fields = self.manager.fields
        self.table.setRowCount(len(fields))
        for i, f in enumerate(fields):
            self.table.setItem(i, 0, QTableWidgetItem(f["name"]))
            self.table.setItem(i, 1, QTableWidgetItem(f["label"]))
            
            combo = QComboBox()
            combo.addItems(["text", "number", "select", "textarea"])
            combo.setCurrentText(f.get("type", "text"))
            self.table.setCellWidget(i, 2, combo)

            opts = ", ".join(f.get("options", [])) if "options" in f else ""
            self.table.setItem(i, 3, QTableWidgetItem(opts))

    def add_field(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem("new_field"))
        self.table.setItem(row, 1, QTableWidgetItem("New Field Label"))
        combo = QComboBox()
        combo.addItems(["text", "number", "select", "textarea"])
        self.table.setCellWidget(row, 2, combo)
        self.table.setItem(row, 3, QTableWidgetItem(""))

    def save_and_close(self):
        new_fields = []
        for i in range(self.table.rowCount()):
            name = self.table.item(i, 0).text().strip()
            label = self.table.item(i, 1).text().strip()
            type_ = self.table.cellWidget(i, 2).currentText()
            
            opt_str = ""
            if self.table.item(i, 3):
                opt_str = self.table.item(i, 3).text().strip()

            if name and label:
                field_def = {"name": name, "label": label, "type": type_}
                if type_ == "select" and opt_str:
                    field_def["options"] = [x.strip() for x in opt_str.split(",") if x.strip()]
                new_fields.append(field_def)
        
        self.manager.save_fields(new_fields)
        self.accept()

class ExtractionPanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        from modules.extractor import ExtractionManager
        self.manager = ExtractionManager()
        self.papers = []
        self.current_paper = None
        self.field_widgets = {}
        self.init_ui()
        self.populate_paper_list()
        self.update_extract_stats()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(75)
        toolbar.setStyleSheet("background: white; border-bottom: 2px solid #E8E8F0;")
        t_layout = QHBoxLayout(toolbar)
        t_layout.setContentsMargins(20, 10, 20, 10)
        t_layout.setSpacing(15)
        
        self.btn_auto_extract = QPushButton("\u2728 Auto-extract All")
        self.btn_auto_extract.setFixedHeight(40)
        self.btn_auto_extract.setStyleSheet("""
            QPushButton { background: #4A6CF7; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 20px; }
            QPushButton:hover { background: #3A5CE5; }
        """)
        self.btn_auto_extract.clicked.connect(self.run_auto_extract)
        
        self.btn_extract_this = QPushButton("\u26a1 Extract This Paper")
        self.btn_extract_this.setFixedHeight(40)
        self.btn_extract_this.setStyleSheet("""
            QPushButton { background: white; color: #4A6CF7; border: 2px solid #4A6CF7; border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 20px; }
            QPushButton:hover { background: #EEF2FF; }
            QPushButton:disabled { color: #aaa; border-color: #ddd; }
        """)
        self.btn_extract_this.clicked.connect(self.extract_current_paper)
        
        self.btn_manage_fields = QPushButton("\u2699\ufe0f Manage Fields")
        self.btn_manage_fields.setFixedHeight(40)
        self.btn_manage_fields.setStyleSheet("""
            QPushButton { background: #F8F9FA; color: #34495e; border: 1px solid #D0D0DA; border-radius: 8px; font-weight: 600; font-size: 13px; padding: 0 15px; }
            QPushButton:hover { background: #E8E8F0; }
        """)
        self.btn_manage_fields.clicked.connect(self.open_manage_fields)
        
        self.btn_export_ext = QPushButton("\ud83d\udce4 Export Excel")
        self.btn_export_ext.setFixedHeight(40)
        self.btn_export_ext.setStyleSheet("""
            QPushButton { background: #27ae60; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 13px; padding: 0 15px; }
            QPushButton:hover { background: #219653; }
        """)
        self.btn_export_ext.clicked.connect(self.export_excel)

        t_layout.addWidget(self.btn_auto_extract)
        t_layout.addWidget(self.btn_extract_this)
        t_layout.addWidget(self.btn_manage_fields)
        t_layout.addStretch()
        
        stats_w = QWidget()
        stats_w.setStyleSheet("background: #F8F9FA; border-radius: 15px; border: 1px solid #EAEAEA;")
        s_layout = QHBoxLayout(stats_w)
        s_layout.setContentsMargins(10, 5, 10, 5)
        s_layout.setSpacing(10)
        
        self.stat_pill_total = make_pill("Total: 0", "#4A6CF7", "#EEF2FF")
        self.stat_pill_done = make_pill("Complete: 0", "#1E8449", "#E8F8F0")
        self.stat_pill_unverified = make_pill("Unverified: 0", "#D68910", "#FEF5E7")
        
        s_layout.addWidget(self.stat_pill_total)
        s_layout.addWidget(self.stat_pill_done)
        s_layout.addWidget(self.stat_pill_unverified)
        
        t_layout.addWidget(stats_w)
        t_layout.addSpacing(15)
        t_layout.addWidget(self.btn_export_ext)
        
        layout.addWidget(toolbar)

        # Main Area
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background: #E8E8F0; width: 2px; }")
        
        # Left: Paper List
        list_container = QWidget()
        list_container.setStyleSheet("background: #F8F9FA;")
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(15, 15, 15, 15)
        list_layout.setSpacing(10)
        
        list_lbl = QLabel("Included Papers")
        list_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #2c3e50; margin-bottom: 5px;")
        list_layout.addWidget(list_lbl)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("\ud83d\udd0d Search papers...")
        self.search_input.setFixedHeight(40)
        self.search_input.setStyleSheet("""
            QLineEdit { border: 1px solid #D0D0DA; border-radius: 8px; padding: 0 15px; font-size: 13px; background: white; }
            QLineEdit:focus { border-color: #4A6CF7; }
        """)
        self.search_input.textChanged.connect(self.populate_paper_list)
        list_layout.addWidget(self.search_input)
        
        self.paper_list = QListWidget()
        self.paper_list.setStyleSheet("""
            QListWidget { border: none; background: transparent; padding: 5px; }
            QListWidget::item { background: white; border: 1px solid #E0E0E0; border-radius: 8px; margin-bottom: 8px; }
            QListWidget::item:selected { border: 2px solid #4A6CF7; background: #EEF2FF; }
        """)
        self.paper_list.itemClicked.connect(self.on_paper_selected)
        list_layout.addWidget(self.paper_list)
        
        splitter.addWidget(list_container)
        
        # Right: Extraction Form
        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.form_scroll.setStyleSheet("QScrollArea { background: white; }")
        
        self.form_container = QWidget()
        self.form_container.setStyleSheet("background: white;")
        self.form_layout = QVBoxLayout(self.form_container)
        self.form_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.form_layout.setContentsMargins(40, 30, 40, 40)
        self.form_layout.setSpacing(20)
        
        self.form_scroll.setWidget(self.form_container)
        splitter.addWidget(self.form_scroll)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setHandleWidth(1)
        layout.addWidget(splitter)

    def populate_paper_list(self):
        self.papers = self.manager.get_papers_for_extraction()
        search_text = self.search_input.text().lower()
        
        self.paper_list.clear()
        for p in self.papers:
            if search_text and search_text not in p["title"].lower():
                continue
                
            from PyQt6.QtWidgets import QListWidgetItem
            l_item = QListWidgetItem(self.paper_list)
            l_item.setData(Qt.ItemDataRole.UserRole, p["id"])
            
            # Custom widget for status badge
            widget = QWidget()
            w_layout = QHBoxLayout(widget)
            w_layout.setContentsMargins(15, 12, 15, 12)
            
            text_v = QVBoxLayout()
            text_v.setSpacing(2)
            title = QLabel(p["title"][:70] + ("..." if len(p["title"]) > 70 else ""))
            title.setStyleSheet("font-weight: 600; font-size: 13px; color: #2c3e50;")
            year = QLabel(f"{p['year'] or 'N/A'}")
            year.setStyleSheet("font-size: 12px; color: #7f8c8d;")
            text_v.addWidget(title)
            text_v.addWidget(year)
            
            w_layout.addLayout(text_v)
            w_layout.addStretch()
            
            # Status Badge logic
            ext_data = p.get("extracted", {})
            verified_count = sum(1 for f in ext_data.values() if f.get("human_verified"))
            all_fields_cnt = len(self.manager.fields)
            
            if verified_count >= all_fields_cnt and all_fields_cnt > 0:
                badge = make_pill("\u2714\ufe0f Done", "#1E8449", "#E8F8F0", 65)
            elif any(f.get("ai_suggested") and not f.get("human_verified") for f in ext_data.values()):
                badge = make_pill("\u26a0\ufe0f Verify", "#D68910", "#FEF5E7", 65)
            elif verified_count > 0:
                badge = make_pill("\u25f4\ufe0f Partial", "#4A6CF7", "#EEF2FF", 65)
            else:
                badge = make_pill("\u23f3 Pending", "#7f8c8d", "#F2F4F4", 65)
                
            w_layout.addWidget(badge)
            l_item.setSizeHint(widget.sizeHint())
            self.paper_list.setItemWidget(l_item, widget)

    def on_paper_selected(self, item):
        pid = item.data(Qt.ItemDataRole.UserRole)
        for p in self.papers:
            if p["id"] == pid:
                self.current_paper = p
                self.load_paper_into_form(p)
                break

    def load_paper_into_form(self, paper):
        # Clear form
        for i in reversed(range(self.form_layout.count())): 
            w = self.form_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
            
        self.field_widgets = {}
        
        # Main Card for the form
        card = QFrame()
        card.setStyleSheet("QFrame { background: #FFFFFF; border-radius: 12px; border: 1px solid #EAEAEA; }")
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 30, 30, 30)
        card_layout.setSpacing(25)
        
        # Paper Header
        header = QLabel(paper["title"])
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #1a1a2e;")
        header.setWordWrap(True)
        card_layout.addWidget(header)
        
        # Meta info
        meta = QLabel(f"{paper.get('authors', 'Unknown')} \u2022 {paper.get('year', 'Unknown')}")
        meta.setStyleSheet("font-size: 14px; color: #7f8c8d; margin-bottom: 5px;")
        card_layout.addWidget(meta)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #E8E8F0;")
        sep.setFixedHeight(1)
        card_layout.addWidget(sep)
        
        ext_data = self.manager.get_extraction_for_paper(paper["id"])
        
        fields_layout = QVBoxLayout()
        fields_layout.setSpacing(24)
        
        for field in self.manager.fields:
            field_container = QWidget()
            f_layout = QVBoxLayout(field_container)
            f_layout.setContentsMargins(0, 0, 0, 0)
            f_layout.setSpacing(10)
            
            label_row = QHBoxLayout()
            label = QLabel(field["label"])
            label.setStyleSheet("font-weight: 600; font-size: 14px; color: #2c3e50;")
            label_row.addWidget(label)
            
            data = ext_data.get(field["name"], {})
            is_ai = data.get("ai_suggested", False)
            is_verified = data.get("human_verified", False)
            
            if is_ai and not is_verified:
                ai_badge = QLabel("\u2728 AI Suggested")
                ai_badge.setStyleSheet("color: #D68910; font-size: 11px; font-weight: bold; background: #FEF5E7; padding: 4px 8px; border-radius: 6px; border: 1px solid #FAD7A1;")
                label_row.addWidget(ai_badge)
            
            label_row.addStretch()
            
            verify_chk = QCheckBox("Mark as Verified")
            verify_chk.setStyleSheet("QCheckBox { font-weight: 500; color: #27ae60; font-size: 13px; }")
            verify_chk.setChecked(is_verified)
            label_row.addWidget(verify_chk)
            
            f_layout.addLayout(label_row)
            
            # Value input
            val = data.get("field_value", "")
            input_style = """
                border: 1.5px solid #D0D0DA; 
                border-radius: 8px; 
                padding: 10px; 
                font-size: 14px; 
                color: #1a1a2e;
                background: white;
            """
            
            if is_ai and not is_verified:
                input_style += "border-color: #F5B041; background: #FFFCF5;"
                
            input_focus = "border-color: #4A6CF7; background: #FFFFFF;"
            
            if field["type"] == "select":
                widget = QComboBox()
                widget.addItems([""] + field.get("options", []))
                widget.setCurrentText(str(val))
                widget.setStyleSheet(f"QComboBox {{ {input_style} }} QComboBox:focus {{ {input_focus} }}")
                widget.setFixedHeight(44)
            elif field["type"] == "textarea":
                widget = QTextEdit()
                widget.setPlainText(str(val))
                widget.setFixedHeight(100)
                widget.setStyleSheet(f"QTextEdit {{ {input_style} }} QTextEdit:focus {{ {input_focus} }}")
            else:
                widget = QLineEdit()
                widget.setText(str(val))
                widget.setFixedHeight(44)
                widget.setStyleSheet(f"QLineEdit {{ {input_style} }} QLineEdit:focus {{ {input_focus} }}")
                
            f_layout.addWidget(widget)
            fields_layout.addWidget(field_container)
            self.field_widgets[field["name"]] = {"input": widget, "verify": verify_chk}

        card_layout.addLayout(fields_layout)
        self.form_layout.addWidget(card)

        # Footer actions
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 10, 0, 0)
        
        save_btn = QPushButton("Save Extraction")
        save_btn.setFixedHeight(44)
        save_btn.setStyleSheet("""
            QPushButton { background: #4A6CF7; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 30px; }
            QPushButton:hover { background: #3A5CE5; }
        """)
        save_btn.clicked.connect(self.save_current_extraction)
        
        verify_all_btn = QPushButton("\u2714\ufe0f Mark All Verified")
        verify_all_btn.setFixedHeight(44)
        verify_all_btn.setStyleSheet("""
            QPushButton { background: white; color: #27ae60; border: 2px solid #27ae60; border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 20px; }
            QPushButton:hover { background: #E8F8F0; }
        """)
        verify_all_btn.clicked.connect(self.mark_all_verified)
        
        actions.addStretch()
        actions.addWidget(verify_all_btn)
        actions.addWidget(save_btn)
        
        self.form_layout.addLayout(actions)
        self.form_layout.addStretch()

    def save_current_extraction(self):
        if not self.current_paper: return
        
        for name, widgets in self.field_widgets.items():
            widget = widgets["input"]
            if isinstance(widget, QComboBox): val = widget.currentText()
            elif isinstance(widget, QTextEdit): val = widget.toPlainText().strip()
            else: val = widget.text().strip()
            
            verified = widgets["verify"].isChecked()
            # If changed manually or verified, it's no longer AI-only
            self.manager.save_field_value(self.current_paper["id"], name, val, ai_suggested=False, human_verified=verified)
            
        self.populate_paper_list()
        self.update_extract_stats()
        QMessageBox.information(self, "Saved", "Extraction data saved.")

    def mark_all_verified(self):
        for widgets in self.field_widgets.values():
            widgets["verify"].setChecked(True)
        self.save_current_extraction()

    def extract_current_paper(self):
        if not self.current_paper: return
        self.btn_extract_this.setEnabled(False)
        self.btn_extract_this.setText("Extracting...")
        
        try:
            self.manager.ai_extract_paper(self.current_paper["id"])
            self.load_paper_into_form(self.current_paper)
            self.populate_paper_list()
            self.update_extract_stats()
        finally:
            self.btn_extract_this.setEnabled(True)
            self.btn_extract_this.setText("Extract This Paper")

    def run_auto_extract(self):
        papers = self.manager.get_papers_for_extraction()
        if not papers:
            QMessageBox.information(self, "No Papers", "No included papers found for extraction.")
            return
            
        confirm = QMessageBox.question(self, "Auto-extract", 
            f"Run AI extraction for all {len(papers)} papers?\nThis will overwrite unverified suggestions.")
        if confirm == QMessageBox.StandardButton.Yes:
            self.bulk_worker = AutoExtractWorker(self.manager)
            self.bulk_dialog = BulkProgressDialog(len(papers), self)
            self.bulk_dialog.setWindowTitle("Auto-extracting Data...")
            
            self.bulk_worker.progress.connect(lambda cur, tot, title: self.bulk_dialog.update_status(cur, tot, title, 0, 0, 0))
            self.bulk_worker.finished.connect(self.on_auto_extract_finished)
            self.bulk_worker.start()
            self.bulk_dialog.exec()

    def on_auto_extract_finished(self, proc, fail):
        self.populate_paper_list()
        self.update_extract_stats()
        QMessageBox.information(self, "Finished", f"Processed {proc} papers. Failed: {fail}")

    def open_manage_fields(self):
        dlg = FieldManagerDialog(self.manager, self)
        if dlg.exec():
            # Reload list and form to reflect field changes
            self.populate_paper_list()
            if self.current_paper:
                self.load_paper_into_form(self.current_paper)

    def export_excel(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Extraction", "Extraction_Results.xlsx", "Excel Files (*.xlsx)")
        if path:
            try:
                self.manager.export_to_excel(path)
                QMessageBox.information(self, "Success", f"Exported to {path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Export failed: {e}")

    def update_extract_stats(self):
        stats = self.manager.get_extraction_stats()
        self.stat_pill_total.setText(f"Total: {stats['total_for_extraction']}")
        self.stat_pill_done.setText(f"Complete: {stats['fully_extracted']}")
        self.stat_pill_unverified.setText(f"Unverified: {stats['ai_suggested_unverified']}")

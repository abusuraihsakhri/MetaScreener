import logging
import logging.handlers

_log_handler = logging.handlers.RotatingFileHandler(
    "metascreener.log",
    maxBytes=5 * 1024 * 1024,  # 5 MB per file
    backupCount=3,
    encoding="utf-8",
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        _log_handler,
        logging.StreamHandler(),
    ],
)
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QAction
from database import init_db
from ui.main_window import MainWindow
from ui.settings_dialog import SettingsDialog

def main():
    # Initialize database
    init_db()
    
    from config import Config
    Config.load()
    
    app = QApplication(sys.argv)
    
    app.setStyleSheet("""
    QMainWindow, QDialog, QWidget {
        background-color: #F5F6FA;
        color: #1a1a2e;
        font-family: Segoe UI;
        font-size: 15px;
    }
    QLabel {
        font-size: 15px;
        color: #1a1a2e;
    }
    QCheckBox {
        font-size: 15px;
        color: #1a1a2e;
        spacing: 10px;
        padding: 4px;
    }
    QCheckBox::indicator {
        width: 20px;
        height: 20px;
        border-radius: 4px;
        border: 2px solid #C0C0CC;
        background-color: #FFFFFF;
    }
    QCheckBox::indicator:checked {
        background-color: #4A6CF7;
        border-color: #4A6CF7;
        image: none;
    }
    QCheckBox::indicator:hover {
        border-color: #4A6CF7;
    }
    QRadioButton {
        font-size: 15px;
        color: #1a1a2e;
        spacing: 10px;
        padding: 4px;
    }
    QRadioButton::indicator {
        width: 20px;
        height: 20px;
        border-radius: 10px;
        border: 2px solid #C0C0CC;
        background-color: #FFFFFF;
    }
    QRadioButton::indicator:checked {
        background-color: #4A6CF7;
        border-color: #4A6CF7;
    }
    QListWidget, QTreeWidget, QTableWidget {
        background-color: #FFFFFF;
        border: 1px solid #E0E0E0;
        border-radius: 10px;
        color: #1a1a2e;
        font-size: 14px;
        alternate-background-color: #F9F9FB;
        gridline-color: #F0F0F5;
    }
    QTreeWidget::item, QTableWidget::item {
        padding: 8px 6px;
        min-height: 32px;
    }
    QTreeWidget::item:selected, QTableWidget::item:selected,
    QListWidget::item:selected {
        background-color: #D6E4FF;
        color: #1a1a2e;
    }
    QPushButton {
        background-color: #FFFFFF;
        border: 1.5px solid #C8C8D0;
        border-radius: 8px;
        padding: 8px 20px;
        color: #1a1a2e;
        font-size: 14px;
        font-weight: 500;
        min-height: 36px;
    }
    QPushButton:hover {
        background-color: #EEF2FF;
        border-color: #4A6CF7;
        color: #4A6CF7;
    }
    QPushButton:pressed {
        background-color: #D6E4FF;
    }
    QPushButton#primary {
        background-color: #4A6CF7;
        color: #FFFFFF;
        border: none;
        font-size: 14px;
        font-weight: 600;
    }
    QPushButton#primary:hover {
        background-color: #3A5CE5;
    }
    QLineEdit, QTextEdit, QPlainTextEdit {
        background-color: #FFFFFF;
        border: 1.5px solid #E0E0E0;
        border-radius: 8px;
        padding: 8px 10px;
        color: #1a1a2e;
        font-size: 14px;
    }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border-color: #4A6CF7;
    }
    QGroupBox {
        border: 1.5px solid #E0E0E0;
        border-radius: 10px;
        margin-top: 16px;
        padding: 16px 12px 12px 12px;
        font-size: 14px;
        font-weight: 600;
        color: #1a1a2e;
        background-color: #FFFFFF;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 6px;
        color: #4A6CF7;
        font-size: 14px;
        font-weight: 700;
    }
    QSlider::groove:horizontal {
        height: 6px;
        background: #E0E0E0;
        border-radius: 3px;
    }
    QSlider::handle:horizontal {
        background: #4A6CF7;
        border: none;
        width: 18px;
        height: 18px;
        border-radius: 9px;
        margin: -6px 0;
    }
    QSlider::sub-page:horizontal {
        background: #4A6CF7;
        border-radius: 3px;
    }
    QProgressBar {
        border: 1px solid #E0E0E0;
        border-radius: 6px;
        background-color: #F0F0F5;
        height: 12px;
        font-size: 11px;
        color: #555;
    }
    QProgressBar::chunk {
        background-color: #4A6CF7;
        border-radius: 6px;
    }
    QHeaderView::section {
        background-color: #F0F2FF;
        border: none;
        border-bottom: 2px solid #E0E0E0;
        border-right: 1px solid #E8E8F0;
        padding: 10px 12px;
        font-size: 13px;
        font-weight: 700;
        color: #4A6CF7;
    }
    QScrollBar:vertical {
        background: #F5F6FA;
        width: 10px;
        border-radius: 5px;
        margin: 0;
    }
    QScrollBar::handle:vertical {
        background: #C8C8D0;
        border-radius: 5px;
        min-height: 30px;
    }
    QScrollBar::handle:vertical:hover {
        background: #4A6CF7;
    }
    QScrollBar:horizontal {
        background: #F5F6FA;
        height: 10px;
        border-radius: 5px;
    }
    QScrollBar::handle:horizontal {
        background: #C8C8D0;
        border-radius: 5px;
    }
    QStatusBar {
        background-color: #FFFFFF;
        border-top: 1px solid #E0E0E0;
        color: #555;
        font-size: 13px;
        padding: 4px 8px;
    }
    QMenuBar {
        background-color: #FFFFFF;
        border-bottom: 1px solid #E0E0E0;
        font-size: 14px;
        padding: 2px;
    }
    QMenuBar::item {
        padding: 6px 12px;
        border-radius: 4px;
    }
    QMenuBar::item:selected {
        background-color: #EEF2FF;
        color: #4A6CF7;
    }
    QMenu {
        background-color: #FFFFFF;
        border: 1px solid #E0E0E0;
        border-radius: 8px;
        font-size: 14px;
        padding: 4px;
    }
    QMenu::item {
        padding: 8px 24px;
        border-radius: 4px;
    }
    QMenu::item:selected {
        background-color: #EEF2FF;
        color: #4A6CF7;
    }
    QTabWidget::pane {
        border: 1px solid #E0E0E0;
        border-radius: 8px;
        background: #FFFFFF;
    }
    QTabBar::tab {
        background: #F5F6FA;
        border: 1px solid #E0E0E0;
        padding: 8px 20px;
        font-size: 14px;
        border-radius: 6px 6px 0 0;
        margin-right: 2px;
    }
    QTabBar::tab:selected {
        background: #FFFFFF;
        color: #4A6CF7;
        border-bottom-color: #FFFFFF;
        font-weight: 600;
    }
    QComboBox {
        background-color: #FFFFFF;
        border: 1.5px solid #E0E0E0;
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 14px;
        min-height: 36px;
    }
    QComboBox:focus {
        border-color: #4A6CF7;
    }
    QComboBox::drop-down {
        border: none;
        width: 24px;
    }
    QToolTip {
        background-color: #1a1a2e;
        color: #FFFFFF;
        border: none;
        border-radius: 4px;
        padding: 6px 10px;
        font-size: 13px;
    }
""")
    
    window = MainWindow()
    
    # Add Settings to menu bar
    menu_bar = window.menuBar()
    
    file_menu = menu_bar.addMenu("File")
    
    settings_action = QAction("Settings", window)
    settings_action.triggered.connect(lambda: SettingsDialog(window).exec())
    file_menu.addAction(settings_action)
    
    exit_action = QAction("Exit", window)
    exit_action.triggered.connect(window.close)
    file_menu.addAction(exit_action)
    
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        logging.critical(f"FATAL APPLICATION CRASH:\n{traceback.format_exc()}")
        # Optional: Show a message box if QApplication exists
        try:
            from PyQt6.QtWidgets import QMessageBox, QApplication
            if QApplication.instance():
                QMessageBox.critical(None, "Fatal Error", f"The application has crashed.\n\nError: {e}\n\nSee metascreener.log for details.")
        except:
            pass
        sys.exit(1)

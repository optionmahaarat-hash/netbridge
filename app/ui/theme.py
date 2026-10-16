"""NetBridge look: deep navy-black with electric blue and a warm amber edge, taken from the app icon.

One stylesheet for every window and dialog (main app and Lite). `build_qss()` is plain text (testable without Qt);
`apply(app)` sets the Fusion style, a matching dark palette (so native parts such as check boxes and combo arrows are
drawn light on dark) and the stylesheet.
"""

# ---- colours (from assets/logo.png)
BG0 = "#060A12"        # window background, darkest
BG1 = "#0A1120"        # panels
CARD = "#0F1A30"       # buttons, inputs, list
CARD2 = "#15254A"      # hover / selected row base
LINE = "#1E3358"       # thin borders
BLUE = "#2B8CFF"       # brand blue
CYAN = "#35C6FF"       # highlight of the blue gradient
TEXT = "#E8F0FF"       # main text (the silver-white of the "Net")
MUTED = "#8EA2C4"
AMBER = "#FFB020"      # the orange edge of the icon
GREEN = "#2ED39A"
RED = "#F0566A"

FONT = '"Segoe UI Variable", "Segoe UI", "Vazirmatn", Tahoma, sans-serif'

GRAD_BLUE = f"qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {BLUE},stop:1 {CYAN})"
GRAD_BLUE_HOVER = "qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #4A9DFF,stop:1 #63D3FF)"
GRAD_AMBER = f"qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #E8890C,stop:1 {AMBER})"
GRAD_GREEN = f"qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #12A87A,stop:1 {GREEN})"
GRAD_RED = f"qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #D43A52,stop:1 {RED})"
GRAD_BG = f"qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {BG0},stop:1 #0B1630)"


def big_button(grad, radius=16, size=22):
    """The main round-cornered action button of Lite (connect / cancel / disconnect)."""
    return (f"QPushButton{{background:{grad};color:#04101F;font-size:{size}px;font-weight:800;"
            f"border:1px solid rgba(255,255,255,0.25);border-radius:{radius}px}}"
            f"QPushButton:hover{{border:1px solid rgba(255,255,255,0.55)}}"
            f"QPushButton:disabled{{background:{LINE};color:{MUTED};border:1px solid {LINE}}}")


def build_qss():
    return f"""
* {{ font-family: {FONT}; font-size: 13px; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {GRAD_BG}; }}
QWidget#central, QSplitter, QStackedWidget {{ background: transparent; }}
QLabel {{ background: transparent; }}
QToolTip {{ background: {CARD2}; color: {TEXT}; border: 1px solid {BLUE}; padding: 4px 8px; border-radius: 6px; }}

QPushButton {{
    background: {CARD}; color: {TEXT}; border: 1px solid {LINE}; border-radius: 9px; padding: 7px 14px;
}}
QPushButton:hover {{ background: {CARD2}; border: 1px solid {BLUE}; }}
QPushButton:pressed {{ background: {BG1}; border: 1px solid {CYAN}; }}
QPushButton:disabled {{ color: {MUTED}; background: {BG1}; border: 1px solid {BG1}; }}
QPushButton#primary {{
    background: {GRAD_BLUE}; color: #04101F; font-weight: 700; border: 1px solid rgba(255,255,255,0.28); border-radius: 11px; padding: 9px 16px;
}}
QPushButton#primary:hover {{ background: {GRAD_BLUE_HOVER}; border: 1px solid rgba(255,255,255,0.6); }}
QPushButton#primary:disabled {{ background: {LINE}; color: {MUTED}; border: 1px solid {LINE}; }}
QPushButton#danger {{ border: 1px solid #5A2B38; color: #FF9AA8; }}
QPushButton#danger:hover {{ background: #2A1219; border: 1px solid {RED}; }}
QPushButton::menu-indicator {{ image: none; }}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
    background: {CARD}; border: 1px solid {LINE}; border-radius: 8px; padding: 6px 9px;
    selection-background-color: {BLUE}; selection-color: #04101F;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {BLUE}; }}
QComboBox {{ padding-right: 4px; }}
QComboBox QAbstractItemView {{
    background: {CARD}; border: 1px solid {BLUE}; selection-background-color: {CARD2}; selection-color: {TEXT}; outline: 0;
}}

QListWidget, QListView, QTreeView, QTableView {{
    background: {BG1}; border: 1px solid {LINE}; border-radius: 12px; padding: 4px; outline: 0;
    alternate-background-color: {CARD};
}}
QListWidget::item {{ padding: 8px 10px; margin: 2px 0; border-radius: 8px; border-left: 3px solid transparent; }}
QListWidget::item:hover {{ background: {CARD}; }}
QListWidget::item:selected {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {CARD2},stop:1 {BG1}); border-left: 3px solid {AMBER}; color: {TEXT};
}}
QHeaderView::section {{ background: {CARD}; color: {MUTED}; border: none; border-bottom: 1px solid {LINE}; padding: 6px; }}

QTextEdit {{ border-radius: 12px; }}
QGroupBox {{ border: 1px solid {LINE}; border-radius: 12px; margin-top: 14px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {CYAN}; }}

QMenu {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {CARD2}; color: {TEXT}; }}
QMenu::separator {{ height: 1px; background: {LINE}; margin: 5px 8px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {BLUE}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {LINE}; border-radius: 4px; min-width: 28px; }}
QScrollBar::handle:horizontal:hover {{ background: {BLUE}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; border: none; width: 0; height: 0; }}

QSplitter::handle {{ background: {LINE}; width: 1px; }}
QProgressBar {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 7px; text-align: center; height: 14px; }}
QProgressBar::chunk {{ background: {GRAD_BLUE}; border-radius: 6px; }}
QTabWidget::pane {{ border: 1px solid {LINE}; border-radius: 10px; }}
QTabBar::tab {{ background: {CARD}; padding: 7px 16px; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 3px; }}
QTabBar::tab:selected {{ background: {CARD2}; border-bottom: 2px solid {AMBER}; }}
QMessageBox {{ background: {BG1}; }}

QLabel#brand {{ font-size: 24px; }}
QLabel#muted {{ color: {MUTED}; }}
QFrame#card {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 12px; }}
"""


def apply(app):
    """Fusion + dark palette + stylesheet. Safe to call once per QApplication."""
    from PySide6.QtGui import QColor, QPalette
    app.setStyle("Fusion")
    p = QPalette()
    for role, col in [(QPalette.Window, BG1), (QPalette.WindowText, TEXT), (QPalette.Base, CARD), (QPalette.AlternateBase, BG1),
                      (QPalette.Text, TEXT), (QPalette.Button, CARD), (QPalette.ButtonText, TEXT), (QPalette.ToolTipBase, CARD2),
                      (QPalette.ToolTipText, TEXT), (QPalette.Highlight, BLUE), (QPalette.HighlightedText, "#04101F"),
                      (QPalette.Link, CYAN), (QPalette.PlaceholderText, MUTED), (QPalette.BrightText, "#FFFFFF")]:
        p.setColor(role, QColor(col))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(MUTED))
    app.setPalette(p)
    app.setStyleSheet(build_qss())


BRAND_HTML = (f"<span style='font-size:24px;font-weight:800;color:{TEXT}'>Net</span>"
              f"<span style='font-size:24px;font-weight:800;color:{CYAN}'>Bridge</span>")

"""장시간 사용을 위한 낮은 채도·높은 대비 테마."""

from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication, QWidget

BG = "#F4F1EA"
SURFACE = "#FFFcf7"
SURFACE_2 = "#EFEAE2"
INK = "#2B3238"
INK_MUTED = "#5B646E"
LINE = "#D8D1C6"
TEAL = "#3C7380"
TEAL_DEEP = "#2F5E69"
TEAL_SOFT = "#D7E6E9"
URGENT = "#C44536"
OK = "#3F6F52"
WARN = "#A56B24"
VIDEO_BG = "#1E2328"


def app_font() -> QFont:
    font = QFont()
    for family in (
        "Noto Sans CJK KR",
        "Noto Sans KR",
        "Malgun Gothic",
        "Apple SD Gothic Neo",
        "WenQuanYi Micro Hei",
        "Pretendard",
        "Segoe UI",
        "sans-serif",
    ):
        font.setFamily(family)
        if QFont(family).exactMatch() or family in ("sans-serif", "Segoe UI"):
            break
    font.setPointSize(11)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return font


def stylesheet() -> str:
    return f"""
    QWidget {{
        background: {BG};
        color: {INK};
        font-size: 14px;
    }}
    QMainWindow, QDialog {{
        background: {BG};
    }}
    QLabel {{
        background: transparent;
    }}
    QLabel#appTitle {{
        font-size: 20px;
        font-weight: 700;
        color: {TEAL_DEEP};
        letter-spacing: 0.5px;
    }}
    QLabel#sectionTitle {{
        font-size: 16px;
        font-weight: 700;
        color: {INK};
    }}
    QLabel#muted, QLabel[role="muted"] {{
        color: {INK_MUTED};
        font-size: 13px;
    }}
    QLabel#clock {{
        font-size: 14px;
        color: {INK};
        font-weight: 600;
    }}
    QFrame#topBar, QFrame#sideBar, QFrame#messageBar, QFrame#card {{
        background: {SURFACE};
        border: 1px solid {LINE};
    }}
    QFrame#topBar {{
        border-top: none;
        border-left: none;
        border-right: none;
    }}
    QFrame#sideBar {{
        border-top: none;
        border-bottom: none;
        border-left: none;
    }}
    QFrame#messageBar {{
        border-bottom: none;
        border-left: none;
        border-right: none;
    }}
    QFrame#demoBanner {{
        background: {TEAL_SOFT};
        border: 1px solid {TEAL};
        color: {TEAL_DEEP};
    }}
    QPushButton {{
        background: {SURFACE};
        border: 1px solid {LINE};
        border-radius: 8px;
        padding: 8px 16px;
        min-height: 40px;
        font-size: 14px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: {SURFACE_2};
        border-color: {TEAL};
    }}
    QPushButton:focus {{
        border: 2px solid {TEAL};
        padding: 7px 15px;
    }}
    QPushButton:disabled {{
        color: #9AA3AB;
        background: {SURFACE_2};
    }}
    QPushButton[kind="primary"] {{
        background: {TEAL};
        color: #FFFFFF;
        border: 1px solid {TEAL_DEEP};
    }}
    QPushButton[kind="primary"]:hover {{
        background: {TEAL_DEEP};
    }}
    QPushButton[kind="danger"] {{
        background: {SURFACE};
        color: {URGENT};
        border: 1px solid {URGENT};
    }}
    QPushButton[kind="nav"] {{
        text-align: left;
        padding-left: 16px;
        border: none;
        border-radius: 8px;
        min-height: 44px;
        background: transparent;
        font-size: 15px;
    }}
    QPushButton[kind="nav"]:hover {{
        background: {TEAL_SOFT};
    }}
    QPushButton[kind="nav"]:checked {{
        background: {TEAL};
        color: #FFFFFF;
    }}
    QLineEdit, QComboBox, QPlainTextEdit, QSpinBox, QTextEdit {{
        background: #FFFFFF;
        border: 1px solid {LINE};
        border-radius: 8px;
        padding: 8px 10px;
        min-height: 38px;
        selection-background-color: {TEAL_SOFT};
    }}
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus {{
        border: 2px solid {TEAL};
    }}
    QComboBox::drop-down {{
        width: 28px;
        border: none;
    }}
    QListWidget, QTableWidget, QTreeWidget {{
        background: #FFFFFF;
        border: 1px solid {LINE};
        border-radius: 8px;
        alternate-background-color: {SURFACE_2};
        outline: none;
    }}
    QListWidget::item {{
        padding: 8px 10px;
        min-height: 28px;
    }}
    QListWidget::item:selected {{
        background: {TEAL_SOFT};
        color: {INK};
    }}
    QListWidget::item:focus {{
        border: 1px solid {TEAL};
    }}
    QHeaderView::section {{
        background: {SURFACE_2};
        padding: 8px;
        border: none;
        border-right: 1px solid {LINE};
        font-weight: 600;
    }}
    QSlider::groove:horizontal {{
        height: 6px;
        background: {LINE};
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        width: 16px;
        height: 16px;
        margin: -6px 0;
        border-radius: 8px;
        background: {TEAL};
    }}
    QCheckBox {{
        spacing: 8px;
        min-height: 28px;
    }}
    QScrollBar:vertical {{
        width: 12px;
        background: {SURFACE_2};
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: #C4BDB3;
        min-height: 32px;
        border-radius: 6px;
    }}
    QToolTip {{
        background: {INK};
        color: #FFFFFF;
        border: none;
        padding: 6px 8px;
        font-size: 13px;
    }}
    QTabWidget::pane {{
        border: 1px solid {LINE};
        border-radius: 8px;
        background: {SURFACE};
    }}
    """


def apply_theme(app: QApplication) -> None:
    app.setFont(app_font())
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(INK))
    pal.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE_2))
    pal.setColor(QPalette.ColorRole.Text, QColor(INK))
    pal.setColor(QPalette.ColorRole.Button, QColor(SURFACE))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(INK))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(TEAL))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(INK))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(INK_MUTED))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet())


def set_kind(widget: QWidget, kind: str) -> None:
    widget.setProperty("kind", kind)
    widget.style().unpolish(widget)
    widget.style().polish(widget)

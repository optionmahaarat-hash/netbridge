import re

from app.ui import theme


def test_qss_is_balanced_and_complete():
    q = theme.build_qss()
    assert q.count("{") == q.count("}")
    for sel in ("QPushButton#primary", "QListWidget::item:selected", "QMenu", "QScrollBar:vertical", "QLineEdit"):
        assert sel in q
    assert "None" not in q and "{{" not in q and "}}" not in q


def test_every_colour_is_valid_hex_and_used():
    cols = [getattr(theme, n) for n in ("BG0", "BG1", "CARD", "CARD2", "LINE", "BLUE", "CYAN", "TEXT", "MUTED", "AMBER", "GREEN", "RED")]
    assert all(re.fullmatch(r"#[0-9A-Fa-f]{6}", c) for c in cols)
    q = theme.build_qss()
    for c in (theme.BLUE, theme.CARD, theme.LINE, theme.AMBER):
        assert c in q


def test_big_button_covers_states():
    s = theme.big_button(theme.GRAD_AMBER)
    assert s.count("{") == s.count("}") and ":hover" in s and ":disabled" in s and theme.GRAD_AMBER in s


def test_brand_html_has_both_words():
    assert "Net" in theme.BRAND_HTML and "Bridge" in theme.BRAND_HTML

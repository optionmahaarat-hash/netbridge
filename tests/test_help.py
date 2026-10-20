import py_compile
from app.ui import help_text


def test_help_has_every_feature_and_google_steps():
    keys = [t[0] for t in help_text.TOPICS]
    assert len(keys) == len(set(keys))
    for k in ("start", "free", "worker", "tgproxy", "gscript", "warp", "tor", "psiphon", "bypass", "routing", "exit"):
        assert k in keys
    html = help_text.topic("gscript")[2]
    for must in ("Code.gs", "/exec", "Anyone", "Install certificate", "Start", "wrong secret key"):
        assert must in html
    assert all(t[2].strip().startswith("<h3>") for t in help_text.TOPICS)


def test_ui_files_compile():
    for f in ("app/ui/main_window.py", "app/ui/gscript_dialog.py", "app/ui/tg_dialog.py", "app/ui/tor_bridges_dialog.py", "app/ui/help_dialog.py"):
        py_compile.compile(f, doraise=True)

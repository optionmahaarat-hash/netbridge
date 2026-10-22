from pathlib import Path
from app.core import lantern


def test_find_looks_in_the_usual_folders_and_returns_none_when_absent():
    env = {"LOCALAPPDATA": "/u/AppData/Local", "ProgramFiles": "/pf"}
    assert lantern.find(env, exists=lambda p: False) is None
    want = Path("/pf") / "Lantern" / "lantern.exe"
    assert lantern.find(env, exists=lambda p: p == want) == want
    assert lantern.find({}, exists=lambda p: True) is None            # no known folders -> nothing to look in


def test_local_appdata_is_tried_before_program_files():
    env = {"LOCALAPPDATA": "/l", "ProgramFiles": "/pf"}
    got = lantern.find(env, exists=lambda p: p.name == "lantern.exe")
    assert str(got).replace("\\", "/").startswith("/l/")


def test_launch_starts_the_program_detached_without_a_shell():
    seen = {}
    lantern.launch(Path("/pf/Lantern/lantern.exe"), popen=lambda args, **kw: seen.update(args=args, kw=kw))
    assert seen["args"] == [str(Path("/pf/Lantern/lantern.exe"))] and "shell" not in seen["kw"]

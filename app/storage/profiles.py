import sys
from pathlib import Path

from app.storage.atomic import read_json, write_json_atomic

DATA = Path("data/profiles.json")
SEED = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets" / "seed_profiles.json"


def _seed():
    """First run of the INSTALLED program only: start with the servers bundled in the installer (never overwrites an existing list)."""
    if not getattr(sys, "frozen", False) or DATA.exists() or not SEED.exists():
        return
    seed = read_json(SEED, [])
    if isinstance(seed, list):
        seed = [p for p in seed if isinstance(p, dict)]
        if seed:
            write_json_atomic(DATA, seed)


def load_profiles():
    DATA.parent.mkdir(parents=True, exist_ok=True)
    _seed()
    data = read_json(DATA, [])
    if not isinstance(data, list):
        return []
    return [p for p in data if isinstance(p, dict)]


def save_profiles(profiles):
    write_json_atomic(DATA, profiles)

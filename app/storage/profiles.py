from pathlib import Path

from app.storage.atomic import read_json, write_json_atomic

DATA = Path("data/profiles.json")


def load_profiles():
    DATA.parent.mkdir(parents=True, exist_ok=True)
    data = read_json(DATA, [])
    if not isinstance(data, list):
        return []
    return [p for p in data if isinstance(p, dict)]


def save_profiles(profiles):
    write_json_atomic(DATA, profiles)

import json
import os
from datetime import date

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PARAMS_PATH  = os.path.join(PROJECT_ROOT, "sortie-sante", "params.json")
DEFAULTS     = {
    "fc_max": 185,
    "fc_repos": 51,
    # Paramètres course (SaintéLyon Express)
    "race_date": "2026-11-28",
    "race_km": 45.0,
    "race_dplus_m": 1200,
}


def load() -> dict:
    if os.path.exists(PARAMS_PATH):
        with open(PARAMS_PATH) as f:
            return {**DEFAULTS, **json.load(f)}
    return DEFAULTS.copy()


def save(fc_max: int, fc_repos: int):
    """Enregistre FC max / FC repos en conservant les autres paramètres du fichier."""
    os.makedirs(os.path.dirname(PARAMS_PATH), exist_ok=True)
    current = {}
    if os.path.exists(PARAMS_PATH):
        with open(PARAMS_PATH) as f:
            current = json.load(f)
    current.update({"fc_max": fc_max, "fc_repos": fc_repos})
    with open(PARAMS_PATH, "w") as f:
        json.dump(current, f)


def race(cfg: dict | None = None) -> dict:
    """Paramètres course : date (datetime.date), km, dplus_m, ratio m D+/km."""
    cfg = cfg or load()
    km = float(cfg["race_km"])
    dplus = int(cfg["race_dplus_m"])
    return {
        "date": date.fromisoformat(str(cfg["race_date"])),
        "km": km,
        "dplus_m": dplus,
        "ratio": dplus / km if km else 0.0,
    }

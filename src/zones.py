import json
import os

from src.detail_parser import workout_filename

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DETAILS_DIR  = os.path.join(PROJECT_ROOT, "details")

ZONE_NAMES  = ["Z1", "Z2", "Z3", "Z4", "Z5"]
ZONE_COLORS = {
    "Z1": "#2ecc71", "Z2": "#3498db", "Z3": "#f39c12",
    "Z4": "#e74c3c", "Z5": "#8e44ad",
}
_BOUNDS = [0.60, 0.70, 0.80, 0.90]   # Karvonen %FCR pour Z1–Z4


def zone_limits(fc_repos: int, fc_max: int) -> dict[str, float]:
    """Retourne les BPM de chaque borne de zone (méthode Karvonen)."""
    fcr = fc_max - fc_repos
    bounds = [fc_repos + b * fcr for b in _BOUNDS]
    return {
        "Z1": f"< {bounds[0]:.0f} bpm",
        "Z2": f"{bounds[0]:.0f}–{bounds[1]:.0f} bpm",
        "Z3": f"{bounds[1]:.0f}–{bounds[2]:.0f} bpm",
        "Z4": f"{bounds[2]:.0f}–{bounds[3]:.0f} bpm",
        "Z5": f"> {bounds[3]:.0f} bpm",
    }


def _zone(bpm: float, fc_repos: int, fc_max: int) -> str:
    fcr = fc_max - fc_repos
    if fcr <= 0:
        return "Z1"
    r = (bpm - fc_repos) / fcr
    for bound, name in zip(_BOUNDS, ZONE_NAMES):
        if r < bound:
            return name
    return "Z5"


def zone_times(detail: dict, fc_repos: int, fc_max: int) -> dict[str, float]:
    """Retourne les minutes par zone depuis les échantillons FC horodatés."""
    samples = sorted(detail.get("hr_samples", []), key=lambda x: x["ts"])
    t = {z: 0.0 for z in ZONE_NAMES}
    for i in range(len(samples) - 1):
        interval = samples[i + 1]["ts"] - samples[i]["ts"]
        if 0 < interval <= 300:   # ignore les pauses > 5 min
            t[_zone(samples[i]["bpm"], fc_repos, fc_max)] += interval / 60.0
    return t


def load_detail(date: str, heure: str, wtype: str) -> dict | None:
    path = os.path.join(DETAILS_DIR, f"{workout_filename(date, heure, wtype)}.json")
    return json.load(open(path)) if os.path.exists(path) else None


def zones_for_workouts(workouts_df, fc_repos: int, fc_max: int) -> list[dict]:
    """
    Pour chaque séance du dataframe, charge le fichier détail et calcule les zones.
    Retourne une liste de dict avec semaine, date, type, Z1..Z5 (min), total_avec_fc.
    """
    rows = []
    for _, row in workouts_df.iterrows():
        detail = load_detail(str(row["date"]), str(row["heure"]), str(row["type"]))
        if not detail or detail.get("hr_count", 0) < 10:
            continue
        zt = zone_times(detail, fc_repos, fc_max)
        total = sum(zt.values())
        if total < 1:
            continue
        rows.append({
            "semaine": str(row.get("semaine", "")),
            "date":    str(row["date"]),
            "type":    str(row["type"]),
            **zt,
            "total_fc_min": total,
        })
    return rows

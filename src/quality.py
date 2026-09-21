import json
import os
from datetime import datetime

import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DEFAULT_DIR = os.path.join(PROJECT_ROOT, "sortie-sante")

TYPES_COURSE = {"Course", "Rando", "TrailRunning", "Hiking"}


def generate(data_dir: str = _DEFAULT_DIR) -> dict:
    wk = pd.read_csv(os.path.join(data_dir, "workouts.csv"), sep=";")
    daily = pd.read_csv(os.path.join(data_dir, "daily.csv"), sep=";", parse_dates=["date"])
    weekly = pd.read_csv(os.path.join(data_dir, "weekly.csv"), sep=";")

    report: dict = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_seances": len(wk),
        "total_jours": len(daily),
        "total_semaines": len(weekly),
        "doublons": [],
        "suspects": [],
        "couverture": {},
        "semaines_sans_seance": [],
    }

    # Doublons : même type, départ à moins de 10 min d'écart
    wk["_dt"] = pd.to_datetime(wk["date"].astype(str) + " " + wk["heure"].astype(str))
    wk_s = wk.sort_values("_dt").reset_index(drop=True)
    for i in range(len(wk_s) - 1):
        r1, r2 = wk_s.iloc[i], wk_s.iloc[i + 1]
        if r1["type"] == r2["type"]:
            gap = (r2["_dt"] - r1["_dt"]).total_seconds()
            if 0 < gap < 600:
                report["doublons"].append({
                    "session_1": f"{r1['date']} {r1['heure']} {r1['type']}",
                    "session_2": f"{r2['date']} {r2['heure']} {r2['type']}",
                    "ecart_min": round(gap / 60, 1),
                })

    # Séances suspectes
    for _, r in wk.iterrows():
        raisons = []
        if pd.notna(r.get("duree_min")) and float(r["duree_min"]) < 2:
            raisons.append(f"durée {r['duree_min']} min")
        fc = r.get("fc_moy")
        if pd.notna(fc):
            if float(fc) > 220:
                raisons.append(f"FC moy {fc} bpm (> 220)")
            elif float(fc) < 30:
                raisons.append(f"FC moy {fc} bpm (< 30)")
        km = r.get("km")
        if pd.notna(km) and str(r["type"]) in TYPES_COURSE and float(km) > 80:
            raisons.append(f"distance {km} km")
        if raisons:
            report["suspects"].append({
                "session": f"{r['date']} {r['heure']} {r['type']}",
                "source": r.get("source", ""),
                "raisons": raisons,
            })

    # Couverture des métriques journalières
    n = len(daily)
    for col, label in [
        ("fc_repos", "FC repos"), ("hrv", "HRV"),
        ("sommeil_h", "Sommeil"), ("poids", "Poids"), ("vo2max", "VO2max"),
    ]:
        if col in daily.columns:
            k = int(daily[col].notna().sum())
            report["couverture"][label] = {
                "jours": k, "total": n,
                "pct": round(100 * k / n, 1) if n else 0,
            }

    # Semaines sans aucune séance
    if "seances" in weekly.columns:
        for _, r in weekly.iterrows():
            if int(r.get("seances", 0)) == 0:
                report["semaines_sans_seance"].append(str(r["semaine"]))

    with open(os.path.join(data_dir, "quality_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report


def load(data_dir: str = _DEFAULT_DIR) -> dict | None:
    path = os.path.join(data_dir, "quality_report.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None

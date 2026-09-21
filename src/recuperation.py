"""Helpers pour l'analyse de récupération croisée."""
import os

import pandas as pd

from src import drift, zones, config, journal

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TYPES_COURSE = {"Course", "Rando", "TrailRunning", "Hiking"}


def baselines(daily: pd.DataFrame) -> dict:
    """Médiane + percentiles 25/75 sur la période complète."""
    out = {}
    for col in ["hrv", "fc_repos", "sommeil_h"]:
        if col not in daily.columns:
            continue
        vals = daily[col].dropna()
        if vals.empty:
            continue
        out[col] = {
            "median": round(float(vals.median()), 1),
            "p25":    round(float(vals.quantile(0.25)), 1),
            "p75":    round(float(vals.quantile(0.75)), 1),
            "n":      int(len(vals)),
        }
    return out


def rolling_weekly(daily: pd.DataFrame, window: int = 7) -> pd.DataFrame:
    """Ajoute des moyennes glissantes 7 j pour HRV, FC repos, sommeil."""
    d = daily.set_index("date").sort_index()
    for col in ["hrv", "fc_repos", "sommeil_h"]:
        if col in d.columns:
            d[f"{col}_r7"] = d[col].rolling(window, min_periods=3).mean()
    return d.reset_index()


def long_run_drifts(workouts: pd.DataFrame, min_dur: float = 60) -> pd.DataFrame:
    """Drift cardiaque pour toutes les sorties longues Course/Rando."""
    cfg = config.load()
    long = workouts[
        workouts["type"].isin(TYPES_COURSE)
        & (pd.to_numeric(workouts["duree_min"], errors="coerce").fillna(0) > min_dur)
    ]
    rows = []
    for _, row in long.iterrows():
        detail = zones.load_detail(str(row["date"]), str(row["heure"]), str(row["type"]))
        if not detail or detail.get("hr_count", 0) < 30:
            continue
        res = drift.analyse(detail["hr_samples"])
        if res:
            rows.append({
                "date":      str(row["date"]),
                "type":      str(row["type"]),
                "duree_min": float(row["duree_min"]),
                "km":        float(row["km"]) if pd.notna(row.get("km")) else None,
                "dplus_m":   float(row["dplus_m"]) if pd.notna(row.get("dplus_m")) else None,
                "fc_moy":    float(row["fc_moy"]) if pd.notna(row.get("fc_moy")) else None,
                **res,
            })
    return pd.DataFrame(rows)


def pace_z2z3_trend(workouts: pd.DataFrame) -> pd.DataFrame:
    """Séances Course Z2/Z3 avec allure → tendance de progression."""
    courses = workouts[
        workouts["type"].isin(TYPES_COURSE)
        & workouts["allure_min_km"].notna()
        & workouts["zone"].isin(["Z2", "Z3"])
        & (pd.to_numeric(workouts["km"], errors="coerce").fillna(0) >= 5)
    ].copy()
    if courses.empty:
        return pd.DataFrame()
    courses["pace_sec"] = courses["allure_min_km"].apply(
        lambda x: int(str(x).split(":")[0]) * 60 + int(str(x).split(":")[1])
        if isinstance(x, str) and ":" in str(x) else None
    )
    return courses[
        ["date", "km", "dplus_m", "allure_min_km", "pace_sec", "fc_moy", "zone"]
    ].dropna(subset=["pace_sec"]).sort_values("date")


def weekly_rpe(workouts: pd.DataFrame) -> pd.DataFrame:
    """RPE moyen et charge RPE par semaine depuis le journal."""
    entries = journal.load()
    rows = []
    for _, w in workouts.iterrows():
        wid = journal.workout_id(str(w["date"]), str(w["heure"]), str(w["type"]))
        rpe = entries.get(wid, {}).get("rpe")
        rows.append({"semaine": str(w.get("semaine", "")), "rpe": rpe,
                     "dur_min": float(w.get("duree_min") or 0)})
    df = pd.DataFrame(rows)
    agg = df.groupby("semaine").agg(
        rpe_moy  =("rpe",     "mean"),
        n_rpe    =("rpe",     "count"),
        n_seances=("dur_min", "count"),
    ).reset_index()
    return agg

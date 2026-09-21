import math

import pandas as pd

from src import journal, config


def trimp(dur_min: float, fc_moy: float, fc_repos: int, fc_max: int) -> float:
    """TRIMP Banister (y=1.92 — homme). Retourne 0.0 si données insuffisantes."""
    if not (dur_min and fc_moy and fc_max > fc_repos):
        return 0.0
    d = max(0.0, min((fc_moy - fc_repos) / (fc_max - fc_repos), 1.0))
    return dur_min * d * 0.64 * math.exp(1.92 * d)


def weekly_load(workouts: pd.DataFrame) -> pd.DataFrame:
    """
    Retourne un DataFrame par semaine avec :
    - charge_trimp : TRIMP cumulé (0 si pas de FC)
    - charge_rpe   : sum(durée × RPE), NaN si aucune séance de la semaine n'a de RPE
    - n_rpe        : nombre de séances avec RPE renseigné
    - sortie_longue: durée max de la semaine (min)
    """
    cfg = config.load()
    fc_max, fc_repos = cfg["fc_max"], cfg["fc_repos"]
    entries = journal.load()

    rows = []
    for _, w in workouts.iterrows():
        wid  = journal.workout_id(str(w["date"]), str(w["heure"]), str(w["type"]))
        rpe  = entries.get(wid, {}).get("rpe")
        dur  = float(w.get("duree_min") or 0)
        fc   = float(w.get("fc_moy")    or 0)
        rows.append({
            "semaine":       str(w.get("semaine", "")),
            "dur_min":       dur,
            "charge_trimp":  trimp(dur, fc, fc_repos, fc_max),
            "charge_rpe":    dur * rpe if rpe is not None else float("nan"),
            "has_rpe":       rpe is not None,
            "sortie_longue": dur,
        })

    df = pd.DataFrame(rows)
    agg = (
        df.groupby("semaine")
          .agg(
              charge_trimp  =("charge_trimp",  "sum"),
              charge_rpe    =("charge_rpe",    "sum"),
              n_rpe         =("has_rpe",        "sum"),
              sortie_longue =("sortie_longue",  "max"),
          )
          .reset_index()
    )
    agg.loc[agg["n_rpe"] == 0, "charge_rpe"] = float("nan")
    return agg

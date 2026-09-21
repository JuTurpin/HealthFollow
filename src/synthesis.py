"""Calcul de la synthèse récupération / charge / forme pour la page Home."""
import datetime
import math

import pandas as pd


def pmc_block(workouts_full: pd.DataFrame) -> pd.DataFrame:
    """
    Performance Management Chart.
    Retourne un DataFrame daily avec : date, trimp, ctl, atl, tsb.
    Calcule sur tout l'historique pour des valeurs CTL/ATL correctes.
    """
    from src import config
    from src.charge import trimp as calc_trimp

    cfg = config.load()
    fc_max, fc_repos = cfg["fc_max"], cfg["fc_repos"]

    wf = workouts_full.copy()
    wf["date"] = pd.to_datetime(wf["date"])
    wf["trimp_val"] = wf.apply(
        lambda r: calc_trimp(
            float(r.get("duree_min") or 0),
            float(r.get("fc_moy") or 0),
            fc_repos, fc_max,
        ),
        axis=1,
    )

    daily_trimp = wf.groupby("date")["trimp_val"].sum().reset_index()
    daily_trimp.columns = ["date", "trimp"]

    if daily_trimp.empty:
        return pd.DataFrame(columns=["date", "trimp", "ctl", "atl", "tsb"])

    date_range = pd.date_range(
        daily_trimp["date"].min(),
        pd.Timestamp.now().normalize(),
        freq="D",
    )
    df = daily_trimp.set_index("date").reindex(date_range, fill_value=0.0).reset_index()
    df.columns = ["date", "trimp"]

    # Classic PMC exponential smoothing: α = 1/τ
    df["ctl"] = df["trimp"].ewm(alpha=1 / 42, adjust=False).mean()
    df["atl"] = df["trimp"].ewm(alpha=1 / 7,  adjust=False).mean()
    df["tsb"] = df["ctl"] - df["atl"]

    return df


def _safe_mean(series: pd.Series) -> float | None:
    v = pd.to_numeric(series, errors="coerce").dropna()
    return float(v.mean()) if not v.empty else None


def recovery_block(daily: pd.DataFrame, baselines: dict) -> dict:
    """
    Analyse la récupération des 7 derniers jours vs baselines personnelles.
    Retourne : status ('green'|'orange'|'red'), métriques, observation.
    """
    now = pd.Timestamp.now()
    d7  = daily[daily["date"] >= now - pd.Timedelta(days=7)]

    hrv_7  = _safe_mean(d7["hrv"])        if "hrv"       in d7.columns else None
    fc_7   = _safe_mean(d7["fc_repos"])   if "fc_repos"  in d7.columns else None
    sl_7   = _safe_mean(d7["sommeil_h"])  if "sommeil_h" in d7.columns else None

    hrv_b = baselines.get("hrv",      {})
    fc_b  = baselines.get("fc_repos", {})
    sl_b  = baselines.get("sommeil_h",{})

    signals = []   # 0 = ok, 1 = attention, 2 = alerte

    # HRV
    hrv_delta_pct = None
    if hrv_7 is not None and hrv_b:
        hrv_delta_pct = (hrv_7 - hrv_b["median"]) / hrv_b["median"] * 100
        if hrv_7 < hrv_b["p25"]:
            signals.append(2)
        elif hrv_7 < hrv_b["median"]:
            signals.append(1)
        else:
            signals.append(0)

    # FC repos
    fc_delta = None
    if fc_7 is not None and fc_b:
        fc_delta = fc_7 - fc_b["median"]
        if fc_7 > fc_b["p75"]:
            signals.append(2)
        elif fc_7 > fc_b["median"]:
            signals.append(1)
        else:
            signals.append(0)

    # Sommeil
    sl_delta = None
    if sl_7 is not None and sl_b:
        sl_delta = sl_7 - sl_b["median"]
        if sl_7 < 6.0:
            signals.append(2)
        elif sl_7 < 7.0:
            signals.append(1)
        else:
            signals.append(0)

    if not signals:
        status = "grey"
        obs = "Données insuffisantes — importez un export récent."
    elif max(signals) == 2:
        status = "red"
        parts = []
        if hrv_7 is not None and hrv_b and hrv_7 < hrv_b["p25"]:
            parts.append(f"HRV nettement sous le P25 ({hrv_7:.0f} vs {hrv_b['p25']} ms)")
        if fc_7 is not None and fc_b and fc_7 > fc_b["p75"]:
            parts.append(f"FC repos élevée ({fc_7:.0f} bpm)")
        if sl_7 is not None and sl_7 < 6.0:
            parts.append(f"Sommeil très court ({sl_7:.1f} h)")
        obs = " · ".join(parts) + " — prévoir une journée de récupération."
    elif max(signals) == 1:
        status = "orange"
        parts = []
        if hrv_delta_pct is not None and hrv_delta_pct < 0:
            parts.append(f"HRV légèrement sous la référence ({hrv_7:.0f} ms)")
        if fc_delta is not None and fc_delta > 0:
            parts.append(f"FC repos légèrement haute ({fc_7:.0f} bpm)")
        if sl_7 is not None and sl_7 < 7.0:
            parts.append(f"Sommeil un peu court ({sl_7:.1f} h)")
        obs = " · ".join(parts) + " — surveiller la charge de la semaine."
    else:
        status = "green"
        parts = []
        if hrv_7 is not None:
            parts.append(f"HRV {hrv_7:.0f} ms")
        if sl_7 is not None:
            parts.append(f"sommeil {sl_7:.1f} h")
        obs = ("Tous les indicateurs au-dessus de la référence — " if parts else "") + \
              "récupération optimale."

    return {
        "status": status,
        "hrv_7": hrv_7, "hrv_delta_pct": hrv_delta_pct, "hrv_ref": hrv_b.get("median"),
        "fc_7":  fc_7,  "fc_delta":      fc_delta,       "fc_ref":  fc_b.get("median"),
        "sl_7":  sl_7,  "sl_delta":      sl_delta,       "sl_ref":  sl_b.get("median"),
        "observation": obs,
    }


def charge_block(workouts: pd.DataFrame) -> dict:
    """
    Charge de la semaine en cours vs moyenne des 4 semaines précédentes.
    """
    from src.charge import weekly_load

    today = datetime.date.today()
    iso_year, iso_week, _ = today.isocalendar()
    sem_courante = f"{iso_year}-W{iso_week:02d}"

    wl = weekly_load(workouts)

    trimp_now  = 0.0
    n_seances  = 0
    if not wl.empty:
        row_now = wl[wl["semaine"] == sem_courante]
        trimp_now = float(row_now["charge_trimp"].iloc[0]) if not row_now.empty else 0.0

    # Séances cette semaine
    lundi = today - datetime.timedelta(days=today.weekday())
    wk_this = workouts[pd.to_datetime(workouts["date"]) >= pd.Timestamp(lundi)]
    n_seances = len(wk_this)

    # Moyenne 4 semaines précédentes (avec activité)
    past = wl[wl["semaine"] < sem_courante].tail(4)
    past_actif = past[past["charge_trimp"] > 0]
    trimp_avg  = float(past_actif["charge_trimp"].mean()) if not past_actif.empty else None

    ratio = trimp_now / trimp_avg if trimp_avg and trimp_avg > 0 else None

    # Status
    if trimp_now == 0:
        status = "grey"
        obs = "Aucune séance enregistrée cette semaine."
    elif ratio is None:
        status = "green"
        obs = f"{trimp_now:.0f} TRIMP cette semaine (pas de référence passée)."
    elif ratio > 1.5:
        status = "red"
        obs = f"Semaine très chargée ({trimp_now:.0f} TRIMP, +{(ratio-1)*100:.0f}% vs moy). Veillez à la récupération."
    elif ratio > 1.2:
        status = "orange"
        obs = f"Semaine chargée ({trimp_now:.0f} TRIMP, +{(ratio-1)*100:.0f}% vs moy). À surveiller."
    elif ratio < 0.5:
        status = "orange"
        obs = f"Semaine très légère ({trimp_now:.0f} TRIMP). Semaine de récupération ?"
    else:
        status = "green"
        obs = f"Charge normale ({trimp_now:.0f} TRIMP, {ratio*100:.0f}% de la moyenne des 4 dernières semaines)."

    return {
        "status": status,
        "trimp_now": trimp_now,
        "trimp_avg": trimp_avg,
        "ratio": ratio,
        "n_seances": n_seances,
        "semaine": sem_courante,
        "observation": obs,
    }


def forme_block(daily: pd.DataFrame, workouts: pd.DataFrame) -> dict:
    """
    Tendance HRV 7j vs 7j précédents + dernière sortie longue (drift).
    """
    now = pd.Timestamp.now()
    d7   = daily[daily["date"] >= now - pd.Timedelta(days=7)]
    d714 = daily[(daily["date"] >= now - pd.Timedelta(days=14)) & (daily["date"] < now - pd.Timedelta(days=7))]

    hrv_7   = _safe_mean(d7["hrv"])   if "hrv" in d7.columns   else None
    hrv_714 = _safe_mean(d714["hrv"]) if "hrv" in d714.columns else None

    hrv_trend      = None
    hrv_trend_pct  = None
    if hrv_7 is not None and hrv_714 is not None and hrv_714 > 0:
        hrv_trend_pct = (hrv_7 - hrv_714) / hrv_714 * 100
        hrv_trend = "up" if hrv_trend_pct > 3 else ("down" if hrv_trend_pct < -3 else "flat")

    # Dernière sortie longue : drift depuis details/
    from src import zones
    TYPES_COURSE = {"Course", "Rando", "TrailRunning", "Hiking"}
    long_runs = workouts[
        workouts["type"].isin(TYPES_COURSE) &
        (pd.to_numeric(workouts["duree_min"], errors="coerce").fillna(0) > 60)
    ].sort_values("date", ascending=False)

    last_drift = None
    last_drift_date = None
    if not long_runs.empty:
        from src import drift as drift_mod
        for _, row in long_runs.head(5).iterrows():
            detail = zones.load_detail(str(row["date"]), str(row["heure"]), str(row["type"]))
            if detail and detail.get("hr_count", 0) >= 30:
                res = drift_mod.analyse(detail["hr_samples"])
                if res:
                    last_drift = res["drift_pct"]
                    last_drift_date = str(row["date"])
                    break

    # Status
    signals = []
    if hrv_trend == "up":   signals.append(0)
    elif hrv_trend == "down": signals.append(2 if hrv_trend_pct < -8 else 1)
    elif hrv_trend == "flat": signals.append(0)

    if last_drift is not None:
        if abs(last_drift) < 5:   signals.append(0)
        elif abs(last_drift) < 10: signals.append(1)
        else:                       signals.append(2)

    if not signals:
        status = "grey"
        obs = "Pas encore assez de données sur 14 jours."
    elif max(signals) == 2:
        status = "red"
        parts = []
        if hrv_trend == "down":
            parts.append(f"HRV en baisse ({hrv_trend_pct:+.0f}% sur 7 j)")
        if last_drift is not None and abs(last_drift) >= 10:
            parts.append(f"drift élevé lors de la dernière longue ({last_drift:+.1f}%)")
        obs = " · ".join(parts) + " — signe de fatigue accumulée."
    elif max(signals) == 1:
        status = "orange"
        parts = []
        if hrv_trend == "down":
            parts.append(f"HRV légèrement en baisse ({hrv_trend_pct:+.0f}% sur 7 j)")
        if last_drift is not None and abs(last_drift) >= 5:
            parts.append(f"drift modéré ({last_drift:+.1f}%)")
        obs = " · ".join(parts) + "."
    else:
        status = "green"
        parts = []
        if hrv_trend == "up":
            parts.append(f"HRV en hausse ({hrv_trend_pct:+.0f}% sur 7 j)")
        elif hrv_trend == "flat" and hrv_7 is not None:
            parts.append(f"HRV stable ({hrv_7:.0f} ms)")
        if last_drift is not None:
            parts.append(f"drift OK ({last_drift:+.1f}%)" if last_drift is not None else "")
        obs = " · ".join(p for p in parts if p) + " — forme en bonne voie."

    return {
        "status": status,
        "hrv_7": hrv_7, "hrv_714": hrv_714, "hrv_trend": hrv_trend, "hrv_trend_pct": hrv_trend_pct,
        "last_drift": last_drift, "last_drift_date": last_drift_date,
        "observation": obs,
    }

"""
Export « bilan coach » : pack de fichiers hebdomadaire (digest.md + CSV).

Module sans Streamlit : uniquement des fonctions qui prennent des DataFrames /
dicts et renvoient des DataFrames, du texte ou des octets. Les lectures disque
(CSV, détails, journal) sont faites par l'appelant (pages/12_Export_bilan.py).

Le digest décrit, il n'interprète pas.

Confidentialité : aucune latitude / longitude, aucun nom de source ou d'appareil
ne sort de ce module. Les traces GPS ne servent qu'à calculer distances,
altitudes et pentes.
"""
import csv
import io
import math
import re
import unicodedata
import zipfile
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from sainteylon_health import (
    cumul_denivele, lisser_altitudes, pace, semaine_avant_course,
)
from src import charge, drift, journal, recuperation, synthesis, zones

# ── Seuils (modifiables) ──────────────────────────────────────────────────────
V_ARRET_KMH          = 1.0    # < : arrêt / pause
V_MARCHE_KMH         = 7.0    # < : marche ; au-dessus : course
PENTE_MONTEE_PCT     = 5.0    # portions en montée pour la vitesse ascensionnelle
SEUIL_DENIVELE_M     = 1.0    # seuil de cumul D+/D− (comme gpx_gain)
LISSAGE_ALT_K        = 5      # demi-fenêtre de lissage altitude (points)
LISSAGE_VITESSE_N    = 5      # fenêtre (segments) pour vitesse et pente
GPS_TROU_S           = 300    # segment GPS plus long : pause (compté en arrêt)
FC_TROU_S            = 60     # intervalle FC plus long : trou de FC
FC_MIN_ECHANTILLONS  = 10     # en dessous : pas de FC détaillée
DERIVE_FENETRE_MIN   = 20     # dérive « 20 premières / 20 dernières minutes »
DECOUPLAGE_MIN_DUREE = 40     # découplage calculé à partir de 40 min
TRIMP_COUVERTURE_MIN = 90.0   # % de FC présente pour un TRIMP « echantillons »
FC_MANQUANTE_ALERTE  = 10.0   # % de FC manquante signalé en anomalie
SPLIT_MIN_KM         = 0.1    # dernier split partiel ignoré en dessous
TENDANCE_SEMAINES    = 8

# Prévu vs réalisé
TOL_DUREE_PCT        = 20.0   # écart de durée toléré
TOL_DPLUS_PCT        = 30.0   # D+ réalisé ≥ (100 − tol) % de la cible
CIBLE_FC_MIN_PCT     = 70.0   # % du temps dans la cible FC pour être conforme

NA = "NA"
JOURS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]

FAMILLES_TYPE = {
    "Course": "course", "TrailRunning": "course", "Running": "course",
    "Rando": "marche", "Hiking": "marche", "Marche": "marche", "Walking": "marche",
    "Velo": "velo", "Velo indoor": "velo", "Cycling": "velo", "IndoorCycle": "velo",
    "Tennis": "tennis",
    "Renfo fonctionnel": "renfo", "Muscu": "renfo", "Gainage": "renfo", "HIIT": "renfo",
    "Yoga": "mobilite", "Mobilite": "mobilite", "Retour au calme": "mobilite",
}
# Ordre significatif : premier mot-clé trouvé
FAMILLES_MOTS = [
    ("repos",    ["repos", "off", "rest"]),
    ("marche",   ["rando", "marche", "randonnee", "hike"]),
    ("velo",     ["velo", "zwift", "home trainer", "vtt", "cyclisme", "bike"]),
    ("tennis",   ["tennis"]),
    ("renfo",    ["renfo", "muscu", "gainage", "ppg", "core", "hiit", "force"]),
    ("mobilite", ["yoga", "mobilite", "etirement", "stretching"]),
    ("course",   ["course", "footing", "trail", "sortie longue", "fractionne", "cotes",
                  "seuil", "vma", "run", "endurance", "ef", "sl", "tempo"]),
]

SEANCES_COLS = [
    "workout_id", "date", "heure_debut", "heure_fin", "type",
    "duree_min", "km", "dplus_m", "dminus_m", "allure_min_km",
    "fc_moy_bpm", "fc_max_bpm",
    "t_z1_min", "t_z2_min", "t_z3_min", "t_z4_min", "t_z5_min",
    "pct_z1", "pct_z2", "pct_z3", "pct_z4", "pct_z5", "t_sans_fc_min",
    "fc_20_premieres_bpm", "fc_20_dernieres_bpm", "derive_bpm",
    "derive_tiers_pct", "decouplage_pct",
    "t_course_min", "t_marche_min", "t_arret_min", "vitesse_asc_mh",
    "trimp", "trimp_source", "charge_rpe",
    "nocturne", "pct_fc_manquante",
    "rpe", "objectif", "facteur_limitant", "douleurs", "terrain", "meteo", "notes",
]
SPLITS_COLS = [
    "workout_id", "km_index", "duree_s", "allure_min_km", "fc_moy_bpm",
    "dplus_m", "dminus_m", "pente_moy_pct", "altitude_moy_m", "mode",
]
DAILY_RENOMMAGE = {
    "fc_repos": "fc_repos_bpm", "hrv": "hrv_ms", "poids": "poids_kg",
    "masse_grasse": "masse_grasse_frac", "masse_maigre": "masse_maigre_kg",
    "vo2max": "vo2max_ml_kg_min", "freq_resp": "freq_resp_rpm",
    "fc_marche": "fc_marche_bpm",
}
TENDANCE_COLS = [
    "semaine", "s_moins", "lundi", "km", "dplus_m", "dplus_par_km_m",
    "pct_z1_z2_course", "trimp", "sortie_longue_min",
    "fc_repos_bpm", "hrv_ms", "sommeil_h", "rpe_moy",
]
PVR_COLS = [
    "jour", "seance_prevue", "duree_cible", "dplus_cible", "fc_cible",
    "seance_realisee", "duree_reelle", "dplus_reel", "pct_temps_dans_cible",
    "statut_propose",
]


# ══════════════════════════════════════════════════════════════════════════════
# Petits utilitaires
# ══════════════════════════════════════════════════════════════════════════════
def _num(v) -> float | None:
    """Convertit en float ; None si absent / vide / NaN."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _r(v, n=1):
    v = _num(v)
    return None if v is None else round(v, n)


def _txt(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip()
    return s or None


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower()


def _md(v, suffixe="") -> str:
    """Valeur pour le digest : NA si absente."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return NA
    if isinstance(v, float):
        v = f"{v:.0f}" if (abs(v) >= 100 or v.is_integer()) else f"{v:.1f}"
    return f"{v}{suffixe}"


def hm(minutes) -> str:
    """Minutes → « 1h05 »."""
    m = _num(minutes)
    if m is None:
        return NA
    h, mn = divmod(int(round(m)), 60)
    return f"{h}h{mn:02d}"


def allure(km, duree_min) -> str | None:
    """Allure m:ss/km (réutilise sainteylon_health.pace)."""
    km, d = _num(km), _num(duree_min)
    if not km or not d:
        return None
    return pace(km, d * 60) or None


# ══════════════════════════════════════════════════════════════════════════════
# Semaines
# ══════════════════════════════════════════════════════════════════════════════
def periode_calcul(lundi: date) -> tuple[date, date]:
    """Séances nécessaires à l'export : tendance 8 semaines et charge 28 jours."""
    dim = lundi + timedelta(days=6)
    return min(lundi - timedelta(weeks=TENDANCE_SEMAINES - 1), dim - timedelta(days=27)), dim


def lundi_de(d: date) -> date:
    return d - timedelta(days=d.weekday())


def iso_tag(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def s_moins(lundi: date, race_date: date) -> int:
    """Compte à rebours en semaines jusqu'à la semaine de course (S-0)."""
    return semaine_avant_course(lundi, race_date)


def libelle_semaine(lundi: date, race_date: date) -> str:
    dim = lundi + timedelta(days=6)
    return (f"S-{s_moins(lundi, race_date):02d} · {iso_tag(lundi)} · "
            f"{lundi:%d/%m} → {dim:%d/%m}")


def derniere_semaine_complete(today: date) -> date:
    """Lundi de la dernière semaine lundi → dimanche entièrement écoulée."""
    return lundi_de(today) - timedelta(days=7)


def semaines_relatives(today: date, decalage: int, nombre: int) -> list[date]:
    """
    Lundis des `nombre` semaines se terminant `decalage` semaines avant la semaine en cours
    (0 = semaine en cours, 1 = semaine précédente…), du plus ancien au plus récent.
    """
    if decalage < 0 or nombre < 1:
        raise ValueError("decalage >= 0 et nombre >= 1")
    ref = lundi_de(today)
    return [ref - timedelta(weeks=decalage + i) for i in range(nombre - 1, -1, -1)]


def _dates_col(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df["date"]).dt.date


def seances_periode(workouts: pd.DataFrame, debut: date, fin: date) -> pd.DataFrame:
    if workouts.empty:
        return workouts.copy()
    d = _dates_col(workouts)
    out = workouts[(d >= debut) & (d <= fin)].copy()
    out["date"] = _dates_col(out).astype(str)
    return out.sort_values(["date", "heure"]).reset_index(drop=True)


def wid_de(row) -> str:
    return journal.workout_id(str(row["date"]), str(row["heure"]), str(row["type"]))


# ══════════════════════════════════════════════════════════════════════════════
# FC
# ══════════════════════════════════════════════════════════════════════════════
def fenetre_seance(row) -> tuple[float, float]:
    """(ts début, ts fin) de la séance, en secondes epoch (heure locale naïve)."""
    t0 = datetime.strptime(f"{row['date']} {row['heure']}", "%Y-%m-%d %H:%M").timestamp()
    return t0, t0 + (_num(row.get("duree_min")) or 0) * 60


def echantillons_seance(detail: dict | None, t0: float, t1: float) -> list[dict]:
    """Échantillons FC limités à la fenêtre de la séance (le détail inclut ±2 min)."""
    if not detail:
        return []
    return sorted((s for s in detail.get("hr_samples") or [] if t0 <= s["ts"] <= t1),
                  key=lambda s: s["ts"])


def stats_fc(samples: list[dict], duree_min: float | None, fc_repos: int, fc_max: int,
             detail_present: bool) -> dict:
    """Temps en zones, part de FC manquante et TRIMP par échantillon."""
    out = {f"t_z{i}_min": None for i in range(1, 6)}
    out.update({f"pct_z{i}": None for i in range(1, 6)})
    out.update(t_sans_fc_min=None, pct_fc_manquante=None, trimp_ech=None, avec_fc=False)
    duree = _num(duree_min) or 0.0
    if not detail_present:
        return out
    if len(samples) < FC_MIN_ECHANTILLONS:
        out["t_sans_fc_min"] = round(duree, 1)
        out["pct_fc_manquante"] = 100.0 if duree else None
        return out
    zt = zones.zone_times({"hr_samples": samples}, fc_repos, fc_max, max_gap_s=FC_TROU_S)
    total = sum(zt.values())
    for i, z in enumerate(zones.ZONE_NAMES, 1):
        out[f"t_z{i}_min"] = round(zt[z], 1)
        out[f"pct_z{i}"] = round(100 * zt[z] / total, 1) if total else None
    sans = max(0.0, duree - total)
    out["t_sans_fc_min"] = round(sans, 1)
    out["pct_fc_manquante"] = round(100 * sans / duree, 1) if duree else None
    out["trimp_ech"] = charge.trimp_echantillons(samples, fc_repos, fc_max, max_gap_s=FC_TROU_S)
    out["avec_fc"] = True
    return out


def pct_temps_dans_cible(samples: list[dict], lo: float | None, hi: float | None) -> float | None:
    """% du temps (avec FC) passé dans [lo, hi]. None si pas de cible ou pas de FC."""
    if (lo is None and hi is None) or len(samples) < FC_MIN_ECHANTILLONS:
        return None
    dans = total = 0.0
    for a, b in zip(samples, samples[1:]):
        dt = b["ts"] - a["ts"]
        if 0 < dt <= FC_TROU_S:
            total += dt
            if (lo is None or a["bpm"] >= lo) and (hi is None or a["bpm"] <= hi):
                dans += dt
    return round(100 * dans / total, 1) if total else None


# ══════════════════════════════════════════════════════════════════════════════
# GPS (sans jamais exposer lat/lon)
# ══════════════════════════════════════════════════════════════════════════════
def haversine_m(lat1, lon1, lat2, lon2):
    """Distance en mètres (accepte des tableaux numpy)."""
    r = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _rolling_sum(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).rolling(n, center=True, min_periods=1).sum().to_numpy()


def segments_gps(detail: dict | None) -> pd.DataFrame | None:
    """
    Segments entre points GPS consécutifs : ts0, ts1, dt_s, dist_m, dele_m,
    ele0_m, ele1_m, v_kmh (lissée), pente_pct (lissée), mode.
    Les coordonnées ne sont utilisées que pour la distance et ne sont pas renvoyées.
    """
    if not detail:
        return None
    pts = [p for p in detail.get("gps_track") or []
           if p.get("ts") is not None and p.get("lat") is not None and p.get("lon") is not None]
    pts.sort(key=lambda p: p["ts"])
    dedup = []
    for p in pts:
        if not dedup or p["ts"] > dedup[-1]["ts"]:
            dedup.append(p)
    if len(dedup) < 2:
        return None

    ts  = np.array([p["ts"] for p in dedup], dtype=float)
    lat = np.array([p["lat"] for p in dedup], dtype=float)
    lon = np.array([p["lon"] for p in dedup], dtype=float)
    ele = pd.Series([_num(p.get("ele")) for p in dedup], dtype=float)
    a_ele = ele.notna().sum() >= 3
    if a_ele:
        ele = ele.interpolate(limit_direction="both")
        ele_s = np.array(lisser_altitudes(ele.tolist(), LISSAGE_ALT_K))
    else:
        ele_s = np.full(len(ts), np.nan)

    dist = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
    dt = np.diff(ts)
    dele = np.diff(ele_s)
    del lat, lon

    trou = dt > GPS_TROU_S
    dt_mob = np.where(trou, 0.0, dt)
    d_mob = np.where(trou, 0.0, dist)
    sd, st_ = _rolling_sum(d_mob, LISSAGE_VITESSE_N), _rolling_sum(dt_mob, LISSAGE_VITESSE_N)
    v = np.where(st_ > 0, sd / np.where(st_ > 0, st_, 1) * 3.6, 0.0)
    se = _rolling_sum(np.nan_to_num(dele), LISSAGE_VITESSE_N)
    pente = np.where(sd > 1, 100 * se / np.where(sd > 1, sd, 1), 0.0)
    if not a_ele:
        pente = np.full(len(dt), np.nan)

    mode = np.where(trou | (v < V_ARRET_KMH), "arret",
                    np.where(v < V_MARCHE_KMH, "marche", "course"))
    return pd.DataFrame({
        "ts0": ts[:-1], "ts1": ts[1:], "dt_s": dt, "dist_m": dist,
        "dele_m": dele, "ele0_m": ele_s[:-1], "ele1_m": ele_s[1:],
        "v_kmh": v, "pente_pct": pente, "mode": mode,
    })


def denivele_gps(seg: pd.DataFrame | None) -> tuple[float | None, float | None]:
    """(D+, D−) en m sur l'altitude lissée, seuil SEUIL_DENIVELE_M (comme gpx_gain)."""
    if seg is None or seg["ele0_m"].isna().all():
        return None, None
    eles = [seg["ele0_m"].iloc[0]] + seg["ele1_m"].tolist()
    g, p = cumul_denivele(eles, SEUIL_DENIVELE_M)
    return round(g), round(p)


def temps_par_mode(seg: pd.DataFrame | None) -> dict:
    if seg is None:
        return {"t_course_min": None, "t_marche_min": None, "t_arret_min": None}
    t = seg.groupby("mode")["dt_s"].sum()
    return {f"t_{m}_min": round(float(t.get(m, 0.0)) / 60, 1)
            for m in ("course", "marche", "arret")}


def vitesse_ascensionnelle(seg: pd.DataFrame | None) -> float | None:
    """D+ cumulé ÷ temps en montée (pente > PENTE_MONTEE_PCT, hors arrêts), en m/h."""
    if seg is None or seg["pente_pct"].isna().all():
        return None
    m = seg[(seg["pente_pct"] > PENTE_MONTEE_PCT) & (seg["mode"] != "arret")]
    t = m["dt_s"].sum()
    if t <= 0:
        return None
    return round(float(m["dele_m"].clip(lower=0).sum()) / (t / 3600))


def _fc_interp(ts: np.ndarray, samples: list[dict]) -> np.ndarray | None:
    if len(samples) < FC_MIN_ECHANTILLONS:
        return None
    hts = np.array([s["ts"] for s in samples], dtype=float)
    hb = np.array([s["bpm"] for s in samples], dtype=float)
    out = np.interp(ts, hts, hb)
    out[(ts < hts[0]) | (ts > hts[-1])] = np.nan
    return out


def decouplage(seg: pd.DataFrame | None, samples: list[dict], duree_min) -> float | None:
    """
    Découplage Pa:HR = (vitesse/FC 1re moitié ÷ vitesse/FC 2e moitié − 1) × 100.
    Hors pauses (vitesse < V_ARRET_KMH), séances ≥ DECOUPLAGE_MIN_DUREE min avec GPS.
    """
    if seg is None or (_num(duree_min) or 0) < DECOUPLAGE_MIN_DUREE:
        return None
    mob = seg[seg["mode"] != "arret"].copy()
    if mob.empty:
        return None
    hr = _fc_interp(((mob["ts0"] + mob["ts1"]) / 2).to_numpy(), samples)
    if hr is None:
        return None
    mob["hr"] = hr
    mob = mob.dropna(subset=["hr"])
    if len(mob) < 4:
        return None
    cum = mob["dt_s"].cumsum()
    moitie = cum.iloc[-1] / 2
    ratios = []
    for part in (mob[cum <= moitie], mob[cum > moitie]):
        hr_t = (part["hr"] * part["dt_s"]).sum()
        if hr_t <= 0 or part["dist_m"].sum() <= 0:
            return None
        ratios.append(part["dist_m"].sum() / hr_t)   # (Σd/Σt) / (Σhr·t/Σt)
    return round((ratios[0] / ratios[1] - 1) * 100, 1)


def splits(seg: pd.DataFrame | None, samples: list[dict], wid: str) -> list[dict]:
    """Une ligne par km (dernier km partiel conservé s'il fait ≥ SPLIT_MIN_KM)."""
    if seg is None:
        return []
    s = seg.copy()
    debut = s["dist_m"].cumsum() - s["dist_m"]
    s["km"] = (debut // 1000).astype(int) + 1
    hts = np.array([x["ts"] for x in samples], dtype=float)
    hb = np.array([x["bpm"] for x in samples], dtype=float)
    rows = []
    for k, g in s.groupby("km"):
        d_km = g["dist_m"].sum() / 1000
        if d_km < SPLIT_MIN_KM:
            continue
        dur = float(g["dt_s"].sum())
        t0, t1 = g["ts0"].iloc[0], g["ts1"].iloc[-1]
        fc = None
        if len(samples) >= FC_MIN_ECHANTILLONS:
            m = (hts >= t0) & (hts <= t1)
            fc = round(float(hb[m].mean())) if m.any() else None
        if g["ele0_m"].isna().all():
            dp = dm = pente = alt = None
        else:
            eles = [g["ele0_m"].iloc[0]] + g["ele1_m"].tolist()
            dp, dm = (round(x) for x in cumul_denivele(eles, SEUIL_DENIVELE_M))
            pente = round(100 * (eles[-1] - eles[0]) / (d_km * 1000), 1)
            alt = round(float(np.mean(eles)))
        tm = g.groupby("mode")["dt_s"].sum()
        mode = "course" if tm.get("course", 0) >= tm.get("marche", 0) else "marche"
        rows.append({
            "workout_id": wid, "km_index": int(k), "duree_s": round(dur),
            "allure_min_km": allure(d_km, dur / 60), "fc_moy_bpm": fc,
            "dplus_m": dp, "dminus_m": dm, "pente_moy_pct": pente,
            "altitude_moy_m": alt, "mode": mode, "_dist_km": d_km,
        })
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# Séances
# ══════════════════════════════════════════════════════════════════════════════
def analyser_seance(row, detail: dict | None, entry: dict | None, cfg: dict) -> tuple[dict, list[dict]]:
    """Ligne de seances.csv + splits d'une séance."""
    fc_repos, fc_max = int(cfg["fc_repos"]), int(cfg["fc_max"])
    wid = wid_de(row)
    t0, t1 = fenetre_seance(row)
    duree = _num(row.get("duree_min"))
    samples = echantillons_seance(detail, t0, t1)
    fc = stats_fc(samples, duree, fc_repos, fc_max, detail is not None)
    seg = segments_gps(detail)
    dplus_gps, dminus_gps = denivele_gps(seg)

    d20 = drift.derive_debut_fin(samples, DERIVE_FENETRE_MIN) if fc["avec_fc"] else {}
    tiers = drift.analyse(samples) if fc["avec_fc"] else {}

    fc_moy = _num(row.get("fc_moy"))
    if fc["trimp_ech"] is not None and (fc["pct_fc_manquante"] or 0) <= 100 - TRIMP_COUVERTURE_MIN:
        trimp, source = fc["trimp_ech"], "echantillons"
    elif fc_moy and duree:
        trimp, source = charge.trimp(duree, fc_moy, fc_repos, fc_max), "fc_moy"
    else:
        trimp, source = None, None

    entry = entry or {}
    rpe = _num(entry.get("rpe"))
    km = _num(row.get("km"))
    dplus = _num(row.get("dplus_m"))
    if dplus is None:
        dplus = dplus_gps
    d_fin = datetime.fromtimestamp(t1)

    ligne = {
        "workout_id": wid, "date": str(row["date"]), "heure_debut": str(row["heure"]),
        "heure_fin": d_fin.strftime("%H:%M"), "type": str(row["type"]),
        "duree_min": _r(duree), "km": _r(km, 2), "dplus_m": _r(dplus, 0),
        "dminus_m": dminus_gps, "allure_min_km": allure(km, duree),
        "fc_moy_bpm": _r(fc_moy, 0), "fc_max_bpm": _r(row.get("fc_max"), 0),
        **{k: fc[k] for k in fc if k.startswith(("t_z", "pct_z"))},
        "t_sans_fc_min": fc["t_sans_fc_min"],
        "fc_20_premieres_bpm": d20.get("fc_debut"), "fc_20_dernieres_bpm": d20.get("fc_fin"),
        "derive_bpm": d20.get("derive_bpm"), "derive_tiers_pct": tiers.get("drift_pct"),
        "decouplage_pct": decouplage(seg, samples, duree),
        **temps_par_mode(seg), "vitesse_asc_mh": vitesse_ascensionnelle(seg),
        "trimp": _r(trimp), "trimp_source": source,
        "charge_rpe": _r(duree * rpe) if (duree and rpe is not None) else None,
        "nocturne": _txt(row.get("nocturne")),
        "pct_fc_manquante": fc["pct_fc_manquante"],
        "rpe": rpe if rpe is None else int(rpe),
        "objectif": _txt(entry.get("objectif")),
        "facteur_limitant": _txt(entry.get("facteur_limitant")),
        "douleurs": _txt(entry.get("douleurs")), "terrain": _txt(entry.get("terrain")),
        "meteo": None if entry.get("meteo") in (None, "—") else _txt(entry.get("meteo")),
        "notes": _txt(entry.get("notes")),
        # colonnes internes (non exportées)
        "_avec_fc": fc["avec_fc"], "_avec_gps": seg is not None,
        "_journal": bool(entry), "_samples": samples, "_famille": famille_type(row["type"]),
    }
    return ligne, splits(seg, samples, wid)


def tableau_seances(workouts: pd.DataFrame, details: dict, entries: dict,
                    cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(séances, splits) pour toutes les séances du DataFrame."""
    lignes, sp = [], []
    for _, row in workouts.iterrows():
        wid = wid_de(row)
        l, s = analyser_seance(row, details.get(wid), entries.get(wid), cfg)
        lignes.append(l)
        sp.extend(s)
    seances = pd.DataFrame(lignes) if lignes else pd.DataFrame(columns=SEANCES_COLS)
    return seances, pd.DataFrame(sp, columns=SPLITS_COLS + ["_dist_km"])


# ══════════════════════════════════════════════════════════════════════════════
# Jours, charge, tendance
# ══════════════════════════════════════════════════════════════════════════════
def tableau_jours(daily: pd.DataFrame, lundi: date, seances: pd.DataFrame,
                  pmc: pd.DataFrame) -> pd.DataFrame:
    jours = [lundi + timedelta(days=i) for i in range(7)]
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    roll = recuperation.rolling_weekly(d)
    roll["date"] = roll["date"].dt.date
    base = pd.DataFrame({"date": jours})
    out = base.merge(roll, on="date", how="left")
    out = out.rename(columns={"hrv_r7": "hrv_r7", "fc_repos_r7": "fc_repos_r7",
                              "sommeil_h_r7": "sommeil_r7"})
    for c in ("hrv_r7", "fc_repos_r7", "sommeil_r7"):
        if c not in out.columns:
            out[c] = None
        out[c] = out[c].astype(float).round(1)
    # TRIMP du jour : 0 sans séance ; NA si une séance du jour n'a pas de TRIMP
    tj = []
    for j in jours:
        s = seances[seances["date"] == j.isoformat()] if not seances.empty else seances
        if s.empty:
            tj.append(0.0)
        elif s["trimp"].isna().any():
            tj.append(None)
        else:
            tj.append(round(float(s["trimp"].sum()), 1))
    out["trimp_jour"] = tj
    p = pmc.copy()
    if not p.empty:
        p["date"] = pd.to_datetime(p["date"]).dt.date
        p = p[["date", "atl", "ctl", "tsb"]]
        out = out.merge(p, on="date", how="left")
    else:
        out[["atl", "ctl", "tsb"]] = None
    for c in ("atl", "ctl", "tsb"):
        out[c] = out[c].astype(float).round(1)
    out = out.rename(columns=DAILY_RENOMMAGE)
    out["date"] = out["date"].astype(str)
    return out


def tableau_tendance(lundi: date, seances_8s: pd.DataFrame, weekly: pd.DataFrame,
                     race_date: date) -> pd.DataFrame:
    """Les TENDANCE_SEMAINES semaines se terminant par la semaine exportée."""
    rows = []
    wk = weekly.copy()
    if not wk.empty:
        wk["semaine"] = wk["semaine"].astype(str)
    for i in range(TENDANCE_SEMAINES - 1, -1, -1):
        l = lundi - timedelta(weeks=i)
        tag = iso_tag(l)
        dim = l + timedelta(days=6)
        s = seances_8s[(seances_8s["date"] >= l.isoformat()) & (seances_8s["date"] <= dim.isoformat())] \
            if not seances_8s.empty else seances_8s
        w = wk[wk["semaine"] == tag] if not wk.empty else wk
        w = w.iloc[0] if len(w) else {}
        course = s[s["type"].isin(journal.TYPES_COURSE)] if not s.empty else s
        z12 = ztot = 0.0
        for _, c in course.iterrows():
            if c["_avec_fc"]:
                zs = [c[f"t_z{k}_min"] or 0 for k in range(1, 6)]
                z12 += zs[0] + zs[1]
                ztot += sum(zs)
        if s.empty:
            trimp = 0.0
        else:
            t = s["trimp"].dropna()
            trimp = round(float(t.sum()), 1) if not t.empty else None
        rpes = s["rpe"].dropna() if not s.empty else pd.Series(dtype=float)
        km = _num(w.get("km_course")) if len(w) else None
        dplus = _num(w.get("dplus_m")) if len(w) else None
        rows.append({
            "semaine": tag, "s_moins": s_moins(l, race_date), "lundi": l.isoformat(),
            "km": _r(km), "dplus_m": _r(dplus, 0),
            "dplus_par_km_m": round(dplus / km, 1) if (km and dplus is not None) else None,
            "pct_z1_z2_course": round(100 * z12 / ztot, 1) if ztot else None,
            "trimp": trimp,
            "sortie_longue_min": _r(course["duree_min"].max()) if not course.empty else None,
            "fc_repos_bpm": _r(w.get("fc_repos_moy")) if len(w) else None,
            "hrv_ms": _r(w.get("hrv_moy")) if len(w) else None,
            "sommeil_h": _r(w.get("sommeil_moy_h"), 2) if len(w) else None,
            "rpe_moy": round(float(rpes.mean()), 1) if not rpes.empty else None,
        })
    return pd.DataFrame(rows, columns=TENDANCE_COLS)


def bloc_charge(lundi: date, seances_8s: pd.DataFrame, pmc: pd.DataFrame) -> dict:
    """TRIMP semaine (course / total), ATL/CTL/TSB au dimanche, ratio 7 j / moyenne 28 j."""
    dim = lundi + timedelta(days=6)
    s = seances_8s
    sem = s[(s["date"] >= lundi.isoformat()) & (s["date"] <= dim.isoformat())] if not s.empty else s
    t_tot = float(sem["trimp"].dropna().sum()) if not sem.empty else 0.0
    t_course = float(sem[sem["type"].isin(journal.TYPES_COURSE)]["trimp"].dropna().sum()) \
        if not sem.empty else 0.0
    debut28 = dim - timedelta(days=27)
    s28 = s[(s["date"] >= debut28.isoformat()) & (s["date"] <= dim.isoformat())] if not s.empty else s
    t28 = float(s28["trimp"].dropna().sum()) if not s28.empty else 0.0
    ratio = round(t_tot / (t28 / 4), 2) if t28 > 0 else None
    atl = ctl = tsb = None
    if not pmc.empty:
        p = pmc[pd.to_datetime(pmc["date"]).dt.date == dim]
        if not p.empty:
            atl, ctl, tsb = (round(float(p.iloc[0][c]), 1) for c in ("atl", "ctl", "tsb"))
    return {
        "trimp_course": round(t_course), "trimp_total": round(t_tot),
        "atl": atl, "ctl": ctl, "tsb": tsb, "ratio_7_28": ratio,
        "sans_trimp": int(sem["trimp"].isna().sum()) if not sem.empty else 0,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Planning (planning-hebdo.md) — lecture seule
# ══════════════════════════════════════════════════════════════════════════════
def famille_type(wtype: str) -> str:
    return FAMILLES_TYPE.get(str(wtype), "autre")


def famille_texte(txt: str) -> str:
    t = _sans_accents(txt or "")
    for fam, mots in FAMILLES_MOTS:
        for m in mots:
            if re.search(rf"(?<![a-z]){re.escape(m)}(?![a-z])", t):
                return fam
    return "autre"


def parser_duree_min(txt: str) -> float | None:
    """« 1h30 », « 45 min », « 45' », « 1h15-1h30 » (moyenne), « 2 h » → minutes."""
    t = _sans_accents(txt or "").replace(" ", "")
    vals = []
    for h, m, mn in re.findall(r"(\d+)h(\d{0,2})|(\d+)(?:min|mn|'|$|-|–)", t):
        if h:
            vals.append(int(h) * 60 + (int(m) if m else 0))
        elif mn:
            vals.append(int(mn))
    return round(sum(vals) / len(vals), 1) if vals else None


def parser_dplus(txt: str) -> float | None:
    nums = [int(n) for n in re.findall(r"\d+", txt or "")]
    return round(sum(nums) / len(nums)) if nums else None


def parser_cible_fc(txt: str, fc_repos: int, fc_max: int) -> tuple[float | None, float | None]:
    """
    Cible FC → (bpm min, bpm max). Formes reconnues : « 135-145 », « 120–140 »,
    « ≤ 150 », « <= 131 », « < 131 », « ≥ 120 », « Z1/Z2 », « Z2 », « Z1-Z2 ».
    """
    t = (txt or "").strip()
    bornes = zones.zone_bounds(fc_repos, fc_max)
    m = re.search(r"Z([1-5])(?:\s*(?:/|-|–|à|a)\s*Z?([1-5]))?", t, re.I)
    if m:
        z1, z2 = int(m.group(1)), int(m.group(2) or m.group(1))
        z1, z2 = min(z1, z2), max(z1, z2)
        lo = None if z1 == 1 else round(bornes[z1 - 2])
        hi = None if z2 == 5 else round(bornes[z2 - 1])
        return lo, hi
    m = re.search(r"(\d{2,3})\s*[-–à]\s*(\d{2,3})", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return min(a, b), max(a, b)
    m = re.search(r"(≤|<=|<|max)\s*(\d{2,3})", t, re.I)
    if m:
        return None, int(m.group(2))
    m = re.search(r"(≥|>=|>|min)\s*(\d{2,3})", t, re.I)
    if m:
        return int(m.group(2)), None
    return None, None


def _cellules(ligne: str) -> list[str]:
    l = ligne.strip()
    if l.startswith("|"):
        l = l[1:]
    if l.endswith("|"):
        l = l[:-1]
    return [c.strip() for c in l.split("|")]


def _jour_idx(txt: str) -> int | None:
    t = _sans_accents(txt or "")
    for i, j in enumerate(JOURS):
        if re.search(rf"(?<![a-z]){j}", t):
            return i
    return None


def parser_planning(md: str, fc_repos: int, fc_max: int) -> list[dict]:
    """
    Lit le tableau Markdown sous « ## Semaine en cours » :
    Jour | Séance | Durée | D+ | Cible FC | Intention | Statut.
    Ne modifie rien : le texte est seulement lu.
    """
    lignes = (md or "").splitlines()
    debut = None
    for i, l in enumerate(lignes):
        if re.match(r"^\s*##\s+semaine en cours", _sans_accents(l)):
            debut = i + 1
            break
    if debut is None:
        return []
    table = []
    for l in lignes[debut:]:
        if re.match(r"^\s*#{1,2}\s", l):
            break
        if l.strip().startswith("|"):
            table.append(l)
        elif table and l.strip():
            break
    if len(table) < 2:
        return []
    entete = [_sans_accents(c) for c in _cellules(table[0])]

    def col(*noms):
        for n in noms:
            for i, c in enumerate(entete):
                if c.startswith(n):
                    return i
        return None

    idx = {
        "jour": col("jour"), "seance": col("seance"), "duree": col("duree"),
        "dplus": col("d+", "denivele"), "fc": col("cible"), "intention": col("intention"),
        "statut": col("statut"),
    }
    rows = []
    for l in table[1:]:
        cells = _cellules(l)
        if all(re.fullmatch(r":?-{2,}:?", c) or not c for c in cells):
            continue

        def get(k):
            i = idx[k]
            v = cells[i] if i is not None and i < len(cells) else ""
            return "" if re.fullmatch(r"[-—–\s]*", v) else v

        jour = get("jour")
        if not jour and not get("seance"):
            continue
        fc_txt = get("fc")
        lo, hi = parser_cible_fc(fc_txt, fc_repos, fc_max)
        rows.append({
            "jour": jour, "jour_idx": _jour_idx(jour), "seance": get("seance"),
            "duree_min": parser_duree_min(get("duree")), "dplus_m": parser_dplus(get("dplus")),
            "fc_cible": fc_txt, "fc_lo": lo, "fc_hi": hi,
            "intention": get("intention"), "statut": get("statut"),
            "famille": famille_texte(get("seance")),
        })
    return rows


def prevu_vs_realise(planning: list[dict], seances: pd.DataFrame, lundi: date) -> pd.DataFrame:
    """Apparie prévu / réalisé : même jour (± 1), même famille d'activité."""
    dispo = []
    for i, s in seances.iterrows():
        j = (date.fromisoformat(s["date"]) - lundi).days
        dispo.append({"i": i, "jour_idx": j, "famille": s["_famille"], "pris": False})
    rows = []

    def realise(s):
        return f"{JOURS[(date.fromisoformat(s['date']) - lundi).days]} {s['heure_debut']} {s['type']}"

    plan = sorted(planning, key=lambda x: (x["jour_idx"] is None, x["jour_idx"] or 0))
    # Appariement en deux passes : même jour d'abord, puis ± 1 jour
    choix = {}
    for ecart in (0, 1):
        for k, p in enumerate(plan):
            if k in choix or p["famille"] == "repos" or p["jour_idx"] is None:
                continue
            cands = [d for d in dispo if not d["pris"] and d["famille"] == p["famille"]
                     and abs(d["jour_idx"] - p["jour_idx"]) == ecart]
            if cands:
                cands.sort(key=lambda d: abs((_num(seances.loc[d["i"], "duree_min"]) or 0)
                                             - (p["duree_min"] or 0)))
                cands[0]["pris"] = True
                choix[k] = cands[0]

    for k, p in enumerate(plan):
        base = {
            "jour": p["jour"], "seance_prevue": p["seance"] or None,
            "duree_cible": p["duree_min"], "dplus_cible": p["dplus_m"],
            "fc_cible": p["fc_cible"] or None,
        }
        if p["famille"] == "repos":
            autres = [d for d in dispo if d["jour_idx"] == p["jour_idx"]
                      and d["famille"] not in ("marche", "mobilite")]
            rows.append({**base, "seance_realisee": None, "duree_reelle": None,
                         "dplus_reel": None, "pct_temps_dans_cible": None,
                         "statut_propose": "🔄" if autres else "✅", "_repos": True})
            continue
        if k not in choix:
            rows.append({**base, "seance_realisee": None, "duree_reelle": None,
                         "dplus_reel": None, "pct_temps_dans_cible": None,
                         "statut_propose": "❌", "_repos": False})
            continue
        s = seances.loc[choix[k]["i"]]
        pct = pct_temps_dans_cible(s["_samples"], p["fc_lo"], p["fc_hi"])
        ok = True
        duree = _num(s["duree_min"])
        if p["duree_min"] and duree is not None:
            ok &= abs(duree - p["duree_min"]) <= TOL_DUREE_PCT / 100 * p["duree_min"]
        if p["dplus_m"] and _num(s["dplus_m"]) is not None:
            ok &= _num(s["dplus_m"]) >= (1 - TOL_DPLUS_PCT / 100) * p["dplus_m"]
        if pct is not None:
            ok &= pct >= CIBLE_FC_MIN_PCT
        rows.append({**base, "seance_realisee": realise(s), "duree_reelle": duree,
                     "dplus_reel": _num(s["dplus_m"]), "pct_temps_dans_cible": pct,
                     "statut_propose": "✅" if ok else "🔄", "_repos": False})
    for d in dispo:
        if not d["pris"]:
            s = seances.loc[d["i"]]
            rows.append({"jour": JOURS[d["jour_idx"]], "seance_prevue": None, "duree_cible": None,
                         "dplus_cible": None, "fc_cible": None, "seance_realisee": realise(s),
                         "duree_reelle": s["duree_min"], "dplus_reel": _num(s["dplus_m"]),
                         "pct_temps_dans_cible": None, "statut_propose": "hors_plan",
                         "_repos": False})
    return pd.DataFrame(rows, columns=PVR_COLS + ["_repos"])


# ══════════════════════════════════════════════════════════════════════════════
# CSV
# ══════════════════════════════════════════════════════════════════════════════
def _cellule_csv(v) -> str:
    """Valeur CSV : absente → NA ; flottant entier → entier ; sinon arrondi à 2 décimales."""
    if v is None or v is pd.NA or v is pd.NaT:
        return NA
    if isinstance(v, (bool, np.bool_)):
        return "oui" if v else "non"
    if isinstance(v, (float, np.floating)):
        if math.isnan(v):
            return NA
        v = round(float(v), 2)
        return str(int(v)) if v.is_integer() else str(v)
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    s = str(v).strip()
    return s if s else NA


def vers_csv(df: pd.DataFrame, colonnes: list[str]) -> str:
    """CSV `;`, UTF-8, dates ISO, donnée absente → NA (jamais vide, jamais 0 par défaut)."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(colonnes)
    out = df.reindex(columns=colonnes)
    for row in out.itertuples(index=False, name=None):
        w.writerow([_cellule_csv(v) for v in row])
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# Digest
# ══════════════════════════════════════════════════════════════════════════════
def _table_md(entete: list[str], lignes: list[list]) -> list[str]:
    out = ["| " + " | ".join(entete) + " |", "|" + "---|" * len(entete)]
    for l in lignes:
        out.append("| " + " | ".join(_md(v) if not isinstance(v, str) else (v or NA)
                                     for v in l) + " |")
    return out


def _zone_moy(fc, cfg) -> str:
    fc = _num(fc)
    if fc is None:
        return NA
    return zones._zone(fc, int(cfg["fc_repos"]), int(cfg["fc_max"]))


def _jour_heure(s) -> str:
    j = JOURS[date.fromisoformat(s["date"]).weekday()]
    return f"{j} {s['heure_debut']}"


def _pct_somme(s, ks) -> float | None:
    vals = [s[f"pct_z{k}"] for k in ks]
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in vals):
        return None
    return round(sum(vals), 1)


def _resume_splits(sp: pd.DataFrame) -> list[str]:
    """Splits regroupés par 5 km : allure, FC moy, D+/D−."""
    if sp.empty:
        return ["Splits : NA (pas de GPS)"]
    out = []
    sp = sp.copy()
    sp["bloc"] = (sp["km_index"] - 1) // 5
    for _, g in sp.groupby("bloc"):
        d_km = g["_dist_km"].sum()
        dur = g["duree_s"].sum()
        fc = g["fc_moy_bpm"].dropna()
        dp = g["dplus_m"].dropna()
        dm = g["dminus_m"].dropna()
        out.append(
            f"km {g['km_index'].min()}–{g['km_index'].max()} : "
            f"{allure(d_km, dur / 60) or NA}/km · FC {round(fc.mean()) if not fc.empty else NA} · "
            f"+{int(dp.sum()) if not dp.empty else NA}/−{int(dm.sum()) if not dm.empty else NA} m · "
            f"marche {int((g['mode'] == 'marche').sum())} km"
        )
    return out


def digest(ctx: dict) -> str:
    lundi, dim = ctx["lundi"], ctx["lundi"] + timedelta(days=6)
    cfg, race = ctx["cfg"], ctx["race"]
    se, jours_df, tend = ctx["seances"], ctx["jours"], ctx["tendance"]
    w = ctx["weekly_row"]
    sxx = s_moins(lundi, race["date"])
    b = zones.zone_bounds(int(cfg["fc_repos"]), int(cfg["fc_max"]))
    n = len(se)
    n_fc = int(se["_avec_fc"].sum()) if n else 0
    n_gps = int(se["_avec_gps"].sum()) if n else 0
    n_j = int(se["_journal"].sum()) if n else 0

    L = [f"# Bilan S-{sxx:02d} ({lundi:%d/%m} → {dim:%d/%m/%Y}) — HealthFollow",
         f"Paramètres : Karvonen, FCM {cfg['fc_max']}, FC repos {cfg['fc_repos']} → "
         f"Z1 <{b[0]:.0f} · Z2 {b[0]:.0f}-{b[1]:.0f} · Z3 {b[1]:.0f}-{b[2]:.0f} · "
         f"Z4 {b[2]:.0f}-{b[3]:.0f} · Z5 >{b[3]:.0f} bpm",
         f"Course : {race['date']:%d/%m/%Y} · {race['km']:g} km · {race['dplus_m']} m D+",
         f"Données : passe 2 {'complète' if ctx['passe2_complete'] else 'partielle'}, "
         f"{n_fc}/{n} séances avec FC détaillée, {n_gps}/{n} avec GPS, {n_j}/{n} avec journal",
         "", "## Résumé (format protocole)", "```",
         f"Semaine : S-{sxx:02d} ({lundi:%d/%m} au {dim:%d/%m/%Y})"]
    km = _num(w.get("km_course"))
    dplus = _num(w.get("dplus_m"))
    L.append(f"Volume : {_md(km)} km / {_md(dplus)} m D+ / {hm(w.get('temps_course_min'))} "
             f"(toutes activités : {hm(w.get('temps_total_min'))})")
    L.append("Séances réalisées :")
    for _, s in se.iterrows():
        L.append(f"  - {_jour_heure(s)} | {s['type']} | {hm(s['duree_min'])} | "
                 f"{_md(s['km'], ' km')} | {_md(s['dplus_m'], ' m D+')} | "
                 f"{(_txt(s['allure_min_km']) or NA) + ('/km' if _txt(s['allure_min_km']) else '')} | "
                 f"{_md(s['fc_moy_bpm'], ' bpm')} ({_zone_moy(s['fc_moy_bpm'], cfg)}) | "
                 f"RPE {_md(s['rpe'])}/10" + (" | NOCTURNE" if s["nocturne"] == "oui" else ""))
    if not n:
        L.append("  (aucune séance enregistrée)")
    pvr = ctx.get("pvr")
    if pvr is not None:
        nr = pvr[pvr["statut_propose"] == "❌"]
        L.append("Séances prévues non réalisées : " + (
            "; ".join(f"{r['jour']} {r['seance_prevue']}" for _, r in nr.iterrows()) or "aucune"))
    else:
        L.append("Séances prévues non réalisées : à compléter")
    d = jours_df
    L.append(f"FC repos moyenne : {_md(_r(d['fc_repos_bpm'].mean()) if 'fc_repos_bpm' in d else None)}"
             f"    HRV moyenne : {_md(_r(d['hrv_ms'].mean()) if 'hrv_ms' in d else None)}")
    sl = _num(d["sommeil_h"].mean()) if "sommeil_h" in d else None
    L.append(f"Sommeil moyen : {hm(sl * 60) if sl is not None else NA}")
    notes = [f"{_jour_heure(s)} : {s['notes']}" for _, s in se.iterrows() if _txt(s["notes"])]
    L.append("Ressenti général : " + (" / ".join(notes) if notes else "à compléter"))
    dl = [f"{_jour_heure(s)} : {s['douleurs']}" for _, s in se.iterrows() if _txt(s["douleurs"])]
    L.append("Douleurs / signaux : " + (" / ".join(dl) if dl else "à compléter"))
    L.append("```")

    # Séances (détail)
    L += ["", "## Séances (détail)"]
    if n:
        L += _table_md(
            ["jour", "type", "durée", "km", "D+", "D−", "allure", "FC moy", "FC max",
             "%Z1-Z2", "%Z3", "%Z4-Z5", "dérive 20/20 (bpm)", "découplage %", "nuit", "RPE",
             "objectif", "facteur limitant"],
            [[_jour_heure(s), s["type"], hm(s["duree_min"]), s["km"], s["dplus_m"], s["dminus_m"],
              s["allure_min_km"], s["fc_moy_bpm"], s["fc_max_bpm"], _pct_somme(s, (1, 2)),
              s["pct_z3"], _pct_somme(s, (4, 5)), s["derive_bpm"], s["decouplage_pct"],
              s["nocturne"], s["rpe"], s["objectif"], s["facteur_limitant"]]
             for _, s in se.iterrows()])
    else:
        L.append("Aucune séance.")

    # Sortie longue
    L += ["", "## Sortie longue de la semaine"]
    longues = se[se["type"].isin(journal.TYPES_COURSE)] if n else se
    if longues.empty:
        L.append("Aucune course / rando cette semaine.")
    else:
        s = longues.loc[longues["duree_min"].astype(float).idxmax()]
        L.append(f"{_jour_heure(s)} · {s['type']} · {hm(s['duree_min'])} · {_md(s['km'], ' km')} · "
                 f"{_md(s['dplus_m'], ' m D+')} / {_md(s['dminus_m'], ' m D−')}")
        L.append(f"- FC moy 20 premières min : {_md(s['fc_20_premieres_bpm'])} · "
                 f"20 dernières min : {_md(s['fc_20_dernieres_bpm'])} · "
                 f"écart : {_md(s['derive_bpm'], ' bpm')} (dérive par tiers : "
                 f"{_md(s['derive_tiers_pct'], ' %')})")
        L.append(f"- Découplage Pa:HR : {_md(s['decouplage_pct'], ' %')}")
        L.append(f"- Temps course / marche / arrêt : {_md(s['t_course_min'], ' min')} / "
                 f"{_md(s['t_marche_min'], ' min')} / {_md(s['t_arret_min'], ' min')}")
        L.append(f"- Vitesse ascensionnelle en montée (> {PENTE_MONTEE_PCT:g} %) : "
                 f"{_md(s['vitesse_asc_mh'], ' m/h')}")
        sp = ctx["splits"]
        L += ["- " + x for x in _resume_splits(sp[sp["workout_id"] == s["workout_id"]])]

    # Prévu vs réalisé
    if pvr is not None:
        L += ["", "## Prévu vs réalisé"]
        L += _table_md(PVR_COLS, [[r[c] for c in PVR_COLS] for _, r in pvr.iterrows()])
        prevus = pvr[(pvr["statut_propose"] != "hors_plan") & (~pvr["_repos"].astype(bool))]
        ok = int((prevus["statut_propose"] == "✅").sum())
        L.append(f"\n{ok}/{len(prevus)} séances conformes à l'intention "
                 f"(statut proposé, à valider ; tolérances : durée ±{TOL_DUREE_PCT:g} %, "
                 f"D+ ≥ {100 - TOL_DPLUS_PCT:g} % de la cible, ≥ {CIBLE_FC_MIN_PCT:g} % du temps "
                 f"dans la cible FC)")

    # Charge
    c = ctx["charge"]
    L += ["", "## Charge",
          f"- TRIMP semaine : course {c['trimp_course']} / total {c['trimp_total']}"
          + (f" ({c['sans_trimp']} séance(s) sans TRIMP)" if c["sans_trimp"] else ""),
          f"- ATL {_md(c['atl'])} · CTL {_md(c['ctl'])} · TSB {_md(c['tsb'])} (au {dim:%d/%m}, "
          "TRIMP sur FC moyenne)",
          f"- Ratio charge 7 j / moyenne hebdo 28 j : {_md(c['ratio_7_28'])}"]

    # Récupération
    L += ["", "## Récupération (7 jours)"]
    L += _table_md(["jour", "FC repos", "HRV", "sommeil (h)", "fréq. resp."],
                   [[f"{JOURS[i]} {date.fromisoformat(r['date']):%d/%m}", _r(r.get("fc_repos_bpm")),
                     _r(r.get("hrv_ms")), _r(r.get("sommeil_h"), 2), _r(r.get("freq_resp_rpm"))]
                    for i, (_, r) in enumerate(d.iterrows())])
    bl = ctx["baselines"]
    L.append("")
    for col, cle, lib in (("fc_repos_bpm", "fc_repos", "FC repos"), ("hrv_ms", "hrv", "HRV"),
                          ("sommeil_h", "sommeil_h", "Sommeil (h)")):
        moy = _r(d[col].mean(), 2 if cle == "sommeil_h" else 1) if col in d else None
        ref = bl.get(cle, {})
        L.append(f"- {lib} : moyenne semaine {_md(moy)} · médiane de référence "
                 f"{_md(ref.get('median'))} (P25 {_md(ref.get('p25'))} – P75 {_md(ref.get('p75'))}, "
                 f"n = {_md(ref.get('n'))})")

    # Tendance
    L += ["", f"## Tendance {TENDANCE_SEMAINES} semaines"]
    L += _table_md(["semaine", "km", "D+", "m D+/km", "%Z1-Z2 course", "TRIMP",
                    "sortie la plus longue (min)", "FC repos", "HRV", "sommeil", "RPE moy"],
                   [[f"S-{r['s_moins']:02d} {r['semaine']}", r["km"], r["dplus_m"],
                     r["dplus_par_km_m"], r["pct_z1_z2_course"], r["trimp"],
                     r["sortie_longue_min"], r["fc_repos_bpm"], r["hrv_ms"],
                     r["sommeil_h"], r["rpe_moy"]] for _, r in tend.iterrows()])

    # Nuit / ravito
    L += ["", "## Nuit / ravitaillement de la semaine"]
    nr = ctx["nuit_ravito"]
    if nr:
        for wid_lbl, champs in nr:
            L.append(f"- {wid_lbl} : " + " · ".join(f"{k} = {v}" for k, v in champs.items()))
    else:
        L.append("Aucun champ nuit / ravitaillement renseigné.")

    # Anomalies
    L += ["", "## Anomalies (factuelles)"]
    L += [f"- {a}" for a in ctx["anomalies"]] or ["- aucune détectée"]
    L += ["", f"_Généré le {ctx['genere_le']:%d/%m/%Y %H:%M} · seuils : arrêt < {V_ARRET_KMH:g} km/h, "
          f"marche < {V_MARCHE_KMH:g} km/h, trou FC > {FC_TROU_S} s_"]
    return "\n".join(L) + "\n"


def nuit_ravito(seances: pd.DataFrame, entries: dict) -> list[tuple[str, dict]]:
    out = []
    for _, s in seances.iterrows():
        e = entries.get(s["workout_id"], {})
        champs = {k: e[k] for k in journal.CHAMPS_NUIT + journal.CHAMPS_RAVITO
                  if e.get(k) not in (None, "", "—")}
        if champs:
            out.append((f"{_jour_heure(s)} {s['type']}", champs))
    return out


def anomalies(lundi: date, seances: pd.DataFrame, jours_df: pd.DataFrame,
              quality_report: dict | None, today: date) -> list[str]:
    dim = lundi + timedelta(days=6)
    out = []
    dans = lambda txt: lundi.isoformat() <= str(txt)[:10] <= dim.isoformat()
    qr = quality_report or {}
    for d in qr.get("doublons", []):
        if dans(d.get("session_1", "")):
            out.append(f"Doublon probable : {d['session_1']} / {d['session_2']} "
                       f"(écart {d.get('ecart_min')} min)")
    for s in qr.get("suspects", []):
        if dans(s.get("session", "")):
            out.append(f"Séance suspecte : {s['session']} ({', '.join(s.get('raisons', []))})")
    for _, s in seances.iterrows():
        lib = f"{_jour_heure(s)} {s['type']}"
        p = _num(s["pct_fc_manquante"])
        if p is not None and p > FC_MANQUANTE_ALERTE:
            out.append(f"FC manquante {p:.0f} % : {lib}")
        if not s["_avec_fc"] and p is None:
            out.append(f"Pas de fichier détail (passe 2) : {lib}")
        if not s["_journal"]:
            out.append(f"Sans journal : {lib}")
    passes = jours_df[jours_df["date"] <= today.isoformat()]
    for col, lib in (("hrv_ms", "HRV"), ("sommeil_h", "sommeil")):
        if col in passes:
            manq = passes[passes[col].isna()]["date"].tolist()
        else:
            manq = passes["date"].tolist()
        if manq:
            out.append(f"Jours sans {lib} : " + ", ".join(
                f"{JOURS[date.fromisoformat(x).weekday()]} {date.fromisoformat(x):%d/%m}" for x in manq))
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Pack
# ══════════════════════════════════════════════════════════════════════════════
def nom_pack(lundi: date, race_date: date) -> str:
    return f"bilan_S-{s_moins(lundi, race_date):02d}_{iso_tag(lundi)}"


def construire_pack(lundi: date, workouts: pd.DataFrame, daily: pd.DataFrame,
                    weekly: pd.DataFrame, details: dict, entries: dict, cfg: dict,
                    race: dict, quality_report: dict | None = None,
                    planning_md: str | None = None, passe2_complete: bool = True,
                    now: datetime | None = None) -> dict:
    """
    Construit le pack complet.
    workouts / daily / weekly : CSV de la passe 1 non filtrés.
    details : {workout_id: dict détail passe 2} (absent → séance sans détail).
    entries : journal.load().
    Retourne {"nom", "fichiers": {nom: str}, "digest", "seances", "sans_journal"}.
    """
    now = now or datetime.now()
    debut_calcul, dim = periode_calcul(lundi)
    wk_8 = seances_periode(workouts, debut_calcul, dim)
    se_8, splits_8 = tableau_seances(wk_8, details, entries, cfg)
    if se_8.empty:
        se_8 = pd.DataFrame(columns=SEANCES_COLS + ["_avec_fc", "_avec_gps", "_journal",
                                                    "_samples", "_famille"])
    se = se_8[(se_8["date"] >= lundi.isoformat()) & (se_8["date"] <= dim.isoformat())] \
        .reset_index(drop=True)
    sp = splits_8[splits_8["workout_id"].isin(se["workout_id"])].reset_index(drop=True)

    pmc = synthesis.pmc_block(workouts, cfg) if not workouts.empty else pd.DataFrame()
    jours_df = tableau_jours(daily, lundi, se, pmc)
    tend = tableau_tendance(lundi, se_8, weekly, race["date"])
    ch = bloc_charge(lundi, se_8, pmc)

    wkly = weekly.copy()
    wrow = {}
    if not wkly.empty:
        r = wkly[wkly["semaine"].astype(str) == iso_tag(lundi)]
        if not r.empty:
            wrow = r.iloc[0].to_dict()

    pvr = None
    if planning_md:
        plan = parser_planning(planning_md, int(cfg["fc_repos"]), int(cfg["fc_max"]))
        pvr = prevu_vs_realise(plan, se, lundi)

    d2 = daily.copy()
    d2["date"] = pd.to_datetime(d2["date"])
    ctx = {
        "lundi": lundi, "cfg": cfg, "race": race, "seances": se, "splits": sp,
        "jours": jours_df, "tendance": tend, "charge": ch, "weekly_row": wrow,
        "pvr": pvr, "passe2_complete": passe2_complete,
        "baselines": recuperation.baselines(d2),
        "nuit_ravito": nuit_ravito(se, entries),
        "anomalies": anomalies(lundi, se, jours_df, quality_report, now.date()),
        "genere_le": now,
    }
    fichiers = {
        "digest.md": digest(ctx),
        "seances.csv": vers_csv(se, SEANCES_COLS),
        "splits.csv": vers_csv(sp, SPLITS_COLS),
        "jours.csv": vers_csv(jours_df, ["date"] + [c for c in jours_df.columns if c != "date"]),
        "tendance.csv": vers_csv(tend, TENDANCE_COLS),
    }
    if pvr is not None:
        fichiers["prevu_vs_realise.csv"] = vers_csv(pvr, PVR_COLS)
    return {
        "nom": nom_pack(lundi, race["date"]),
        "fichiers": fichiers,
        "digest": fichiers["digest.md"],
        "seances": se,
        "sans_journal": [f"{_jour_heure(s)} {s['type']}" for _, s in se.iterrows() if not s["_journal"]],
    }


def nom_multi(packs: list[dict]) -> str:
    """Nom du zip : celui du pack si une seule semaine, sinon la plage couverte."""
    if len(packs) == 1:
        return packs[0]["nom"]
    a, b = packs[0]["nom"].split("_")[1:], packs[-1]["nom"].split("_")[1:]
    return f"bilan_{a[0]}_a_{b[0]}_{a[1]}_{b[1]}"


def fichiers_multi(packs: list[dict]) -> dict[str, str]:
    """Une semaine : fichiers à la racine. Plusieurs : un sous-dossier par semaine."""
    if len(packs) == 1:
        return dict(packs[0]["fichiers"])
    return {f"{p['nom']}/{nom}": contenu for p in packs for nom, contenu in p["fichiers"].items()}


def zip_pack(fichiers: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nom, contenu in fichiers.items():
            z.writestr(nom, contenu.encode("utf-8"))
    return buf.getvalue()

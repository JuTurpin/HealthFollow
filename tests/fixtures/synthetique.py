"""
Jeu de données synthétique pour les tests et la vérification de la page.

Génère, dans un dossier racine donné, la même arborescence que l'application :
  sortie-sante/{workouts,daily,weekly}.csv  (écrits par sainteylon_health.export_csv)
  details/<id>.json                          (même format que detail_parser)
  journal.json
  data/.details_progress

Usage :
    python -m tests.fixtures.synthetique <racine>     # ex. . pour la vérif Streamlit
Les coordonnées GPS sont fictives (ligne droite autour d'un point arbitraire).
"""
import json
import math
import os
import random
import sys
from datetime import date, datetime, timedelta

import sainteylon_health as sh

LAT0, LON0 = 45.123456, 4.654321   # point fictif
FIN = date(2026, 10, 11)            # dimanche
SEMAINES = 10


def _wid(start: datetime, label: str) -> str:
    return f"{start:%Y-%m-%d}_{start:%H%M}_{label}"


def trace(start: datetime, dur_min: float, v_kmh: float, denivele: float = 80.0,
          pause_min: tuple[float, float] | None = None, step_s: int = 5,
          v_fin_kmh: float | None = None) -> list[dict]:
    """Trace GPS rectiligne (vers le nord) ; altitude sinusoïdale ; pause optionnelle."""
    pts, dist = [], 0.0
    n = int(dur_min * 60 / step_s)
    for i in range(n + 1):
        t = i * step_s
        en_pause = pause_min and pause_min[0] * 60 <= t < pause_min[1] * 60
        v = v_kmh if v_fin_kmh is None else v_kmh + (v_fin_kmh - v_kmh) * i / n
        if i and not en_pause:
            dist += v / 3.6 * step_s
        ele = 300 + denivele / 2 * math.sin(2 * math.pi * dist / 4000)
        pts.append({
            "ts": int(start.timestamp()) + t,
            "lat": LAT0 + dist / 111_195.0, "lon": LON0,
            "ele": round(ele, 2),
        })
    return pts


def fc(start: datetime, dur_min: float, bpm0: float, bpm1: float, step_s: int = 5,
       trou_min: tuple[float, float] | None = None) -> list[dict]:
    """FC linéaire bpm0 → bpm1 ; trou optionnel (aucun échantillon)."""
    out = []
    n = int(dur_min * 60 / step_s)
    for i in range(n + 1):
        t = i * step_s
        if trou_min and trou_min[0] * 60 <= t < trou_min[1] * 60:
            continue
        out.append({"ts": int(start.timestamp()) + t, "bpm": int(round(bpm0 + (bpm1 - bpm0) * i / n))})
    return out


def generer(racine: str, seed: int = 7) -> dict:
    rnd = random.Random(seed)
    data_dir = os.path.join(racine, "sortie-sante")
    det_dir = os.path.join(racine, "details")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(det_dir, exist_ok=True)
    os.makedirs(os.path.join(racine, "data"), exist_ok=True)

    lundi0 = FIN - timedelta(days=FIN.weekday()) - timedelta(weeks=SEMAINES - 1)
    workouts, details, journal = [], {}, {}
    records = {"fc_repos": [], "hrv": [], "freq_resp": [], "poids": []}
    sleep = []

    for k in range(SEMAINES):
        lundi = lundi0 + timedelta(weeks=k)
        progression = 1 + 0.08 * k
        plan = [
            (1, "18:30", "Running", 50, 10.0, 140),               # mardi footing
            (2, "12:15", "FunctionalStrengthTraining", 40, None, 110),
            (3, "19:30", "Running", 60, 9.5, 150),                # jeudi nocturne
            (5, "08:00", "Hiking" if k % 3 == 2 else "Running", 100 * progression, 8.0, 138),
            (6, "10:00", "Tennis", 75, None, 135),
        ]
        for jour, heure, atype, dur, v, bpm in plan:
            start = datetime.strptime(f"{lundi + timedelta(days=jour)} {heure}", "%Y-%m-%d %H:%M")
            if start.date() > FIN:
                continue
            label = sh.ACTIVITY_FR.get(atype, atype)
            wid = _wid(start, label)
            gps = []
            dist_km = None
            if v:
                long = jour == 5
                v_eff = 5.0 if atype == "Hiking" else v
                gps = trace(start, dur, v_eff, denivele=120 if long else 40,
                            pause_min=(30, 33) if long else None,
                            v_fin_kmh=v_eff * 0.9 if long else None)
                dist_km = round((gps[-1]["lat"] - LAT0) * 111.195, 2)
            trou = (20, 30) if (k == SEMAINES - 1 and jour == 3) else None
            hr = fc(start, dur, bpm - 8, bpm + 10, trou_min=trou)
            if not (k == SEMAINES - 1 and jour == 2):          # un renfo sans détail
                details[wid] = {"workout_id": wid, "parsed_at": "2026-10-11T20:00:00",
                                "hr_samples": hr, "hr_count": len(hr),
                                "gps_track": gps, "gps_count": len(gps)}
            workouts.append({
                "start": start, "end": start + timedelta(minutes=dur), "type": atype,
                "dur_s": dur * 60, "dist_km": dist_km,
                "denivele": (round(120 * dist_km / 4) if jour == 5 else round(40 * dist_km / 4))
                            if dist_km else None,
                "hr_avg": sum(h["bpm"] for h in hr) / len(hr), "hr_max": max(h["bpm"] for h in hr),
                "kcal": dur * 10, "source": "Apple Watch de Test",
            })
            if not (k == SEMAINES - 1 and jour == 6):          # tennis sans journal
                e = {"workout_id": wid, "date": f"{start:%Y-%m-%d}", "heure": heure, "type": label,
                     "objectif": "Sortie longue" if jour == 5 else "Endurance",
                     "rpe": 6 if jour == 5 else 4, "facteur_limitant": "Jambes" if jour == 5 else "Aucun",
                     "douleurs": "mollet gauche 2/10" if (jour == 5 and k == SEMAINES - 1) else "",
                     "terrain": "Trail" if v else None, "meteo": "Beau",
                     "notes": "bonnes sensations" if jour == 1 else ""}
                if jour == 3:
                    e.update({"frontale": "Moyenne", "confort_nuit": 7, "sommeil_avant_h": 7.5,
                              "aliments": "1 gel", "glucides_g_h": 30, "tolerance_digestive": 8})
                journal[wid] = e

        for j in range(7):
            d = lundi + timedelta(days=j)
            if d > FIN:
                continue
            t = datetime.combine(d, datetime.min.time()) + timedelta(hours=7)
            records["fc_repos"].append((t, 50 + rnd.randint(-2, 3), "w"))
            if not (k == SEMAINES - 1 and j == 3):              # un jour sans HRV
                records["hrv"].append((t, 55 + rnd.randint(-8, 8), "w"))
            records["freq_resp"].append((t, 14 + rnd.random(), "w"))
            if j == 0:
                records["poids"].append((t, 72.0, "w"))
            if not (k == SEMAINES - 1 and j == 5):              # une nuit sans sommeil
                fin_nuit = t - timedelta(minutes=30)
                sleep.append((fin_nuit - timedelta(hours=7, minutes=rnd.randint(-40, 40)), fin_nuit))

    workouts.sort(key=lambda w: w["start"])
    jours = sh.daily_series(records, sleep)
    sem = sh.weekly_series(workouts, jours)
    sh.export_csv(data_dir, workouts, jours, sem, sh.RACE_DATE)

    for wid, d in details.items():
        with open(os.path.join(det_dir, f"{wid}.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)
    with open(os.path.join(racine, "journal.json"), "w", encoding="utf-8") as f:
        json.dump(journal, f, ensure_ascii=False, indent=2)
    with open(os.path.join(racine, "data", ".details_progress"), "w") as f:
        json.dump({"done": len(details), "total": len(details), "status": "done"}, f)
    return {"details": details, "journal": journal, "data_dir": data_dir}


PLANNING_MD = """# Planning hebdo

## Contexte
Bloc spécifique.

## Semaine en cours

| Jour | Séance | Durée | D+ | Cible FC | Intention | Statut |
|---|---|---|---|---|---|---|
| Lun | Repos | — | — | — | Récupérer | |
| Mar 06/10 | Footing EF | 50 min | 50 m | 135-145 | Aisance | |
| Mer | Renfo PPG | 40' | — | — | Gainage | |
| Jeu | Footing nocturne frontale | 1h | 50 | ≤ 150 | Test frontale | |
| Ven | Fractionné côtes | 45 min | 200 m | ≤ 131 | Puissance | |
| Sam | Sortie longue trail | 1h45-2h15 | 400 m | Z1/Z2 | Tenue | |
| Dim | Vélo Zwift | 1h | — | 120-140 | Récup active | |

## Semaine suivante

| Jour | Séance | Durée | D+ | Cible FC | Intention | Statut |
|---|---|---|---|---|---|---|
| Lun | Repos | — | — | — | | |
"""


if __name__ == "__main__":
    racine = sys.argv[1] if len(sys.argv) > 1 else "."
    generer(racine)
    with open(os.path.join(racine, "planning-hebdo-exemple.md"), "w", encoding="utf-8") as f:
        f.write(PLANNING_MD)
    print(f"Jeu synthétique écrit dans {os.path.abspath(racine)}")

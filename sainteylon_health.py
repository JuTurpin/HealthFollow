#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sainteylon_health.py — extraction des donnees utiles d'un export Sante iPhone
pour la preparation SainteLyon.

Entree  : export.zip (ou le dossier apple_health_export deja decompresse)
Sorties : - un digest hebdo au format du protocole, pret a coller
          - workouts.csv  : une ligne par seance
          - daily.csv     : FC repos / HRV / sommeil / poids par jour
          - weekly.csv    : volume, D+, temps, charge par semaine ISO

Usage :
    python3 sainteylon_health.py export.zip                  # derniere semaine complete
    python3 sainteylon_health.py export.zip --week 2026-W37
    python3 sainteylon_health.py export.zip --weeks-back 4   # 4 dernieres semaines
    python3 sainteylon_health.py export.zip --all --outdir ./sortie
    python3 sainteylon_health.py export.zip --no-gpx         # ignore les traces GPS (plus rapide)

Aucune dependance externe : stdlib uniquement.
"""

import argparse
import csv
import os
import re
import sys
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from xml.etree import ElementTree as ET

# --------------------------------------------------------------------------
# Parametres personnels (modifiables ici ou en ligne de commande)
# --------------------------------------------------------------------------
FC_MAX = 185
FC_REPOS = 51
RACE_DATE = date(2026, 11, 28)  # SainteLyon Express — depart 28/11/2026 23h00

# Types de seances qui comptent dans le volume "course"
RUN_TYPES = {"Running", "TrailRunning", "Hiking"}

ACTIVITY_FR = {
    "Running": "Course",
    "Hiking": "Rando",
    "Cycling": "Velo",
    "IndoorCycle": "Velo indoor",
    "FunctionalStrengthTraining": "Renfo fonctionnel",
    "TraditionalStrengthTraining": "Muscu",
    "CoreTraining": "Gainage",
    "HighIntensityIntervalTraining": "HIIT",
    "Tennis": "Tennis",
    "Walking": "Marche",
    "Yoga": "Yoga",
    "Flexibility": "Mobilite",
    "Cooldown": "Retour au calme",
    "Other": "Autre",
}

REC = {
    "HKQuantityTypeIdentifierRestingHeartRate": "fc_repos",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv",
    "HKQuantityTypeIdentifierVO2Max": "vo2max",
    "HKQuantityTypeIdentifierBodyMass": "poids",
    "HKQuantityTypeIdentifierBodyFatPercentage": "masse_grasse",
    "HKQuantityTypeIdentifierLeanBodyMass": "masse_maigre",
    "HKQuantityTypeIdentifierRespiratoryRate": "freq_resp",
    "HKQuantityTypeIdentifierWalkingHeartRateAverage": "fc_marche",
}

SLEEP_ASLEEP = {
    "HKCategoryValueSleepAnalysisAsleepUnspecified",
    "HKCategoryValueSleepAnalysisAsleepCore",
    "HKCategoryValueSleepAnalysisAsleepDeep",
    "HKCategoryValueSleepAnalysisAsleepREM",
}

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------
def parse_dt(s):
    """'2026-05-26 08:46:00 +0200' -> datetime naif (heure locale de l'export)."""
    if not s:
        return None
    m = DATE_RE.match(s)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def iso_week(d):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_bounds(tag):
    """'2026-W37' -> (lundi, dimanche)"""
    y, w = tag.split("-W")
    monday = date.fromisocalendar(int(y), int(w), 1)
    return monday, monday + timedelta(days=6)


def semaine_avant_course(monday, race=RACE_DATE):
    """Numero de semaine restante avant la course (S-XX)."""
    race_monday = race - timedelta(days=race.weekday())
    return max(0, (race_monday - monday).days // 7)


def hms(seconds):
    seconds = int(round(seconds))
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h}h{m:02d}" if h else f"{m}min{s:02d}"


def pace(dist_km, sec):
    if not dist_km or dist_km < 0.2 or not sec:
        return ""
    p = sec / 60.0 / dist_km
    return f"{int(p)}:{int(round((p - int(p)) * 60)):02d}"


def pct_fcmax(bpm):
    return round(100.0 * bpm / FC_MAX) if bpm else None


def zone_karvonen(bpm):
    """Zone FC 1-5 methode Karvonen (reserve cardiaque)."""
    if not bpm:
        return ""
    r = (bpm - FC_REPOS) / float(FC_MAX - FC_REPOS)
    for limite, z in ((0.60, 1), (0.70, 2), (0.80, 3), (0.90, 4)):
        if r < limite:
            return f"Z{z}"
    return "Z5"


def merge_intervals(intervals):
    """Fusionne des (debut, fin) qui se chevauchent -> duree totale en secondes."""
    if not intervals:
        return 0.0
    intervals = sorted(intervals)
    total = 0.0
    cs, ce = intervals[0]
    for s, e in intervals[1:]:
        if s <= ce:
            ce = max(ce, e)
        else:
            total += (ce - cs).total_seconds()
            cs, ce = s, e
    total += (ce - cs).total_seconds()
    return total


# --------------------------------------------------------------------------
# Lecture de l'export
# --------------------------------------------------------------------------
class Export:
    """Acces uniforme a un export.zip ou a un dossier decompresse."""

    def __init__(self, path):
        self.path = path
        self.zip = None
        if os.path.isdir(path):
            self.root = path
            if os.path.isdir(os.path.join(path, "apple_health_export")):
                self.root = os.path.join(path, "apple_health_export")
        elif zipfile.is_zipfile(path):
            self.zip = zipfile.ZipFile(path)
        else:
            sys.exit(f"[!] {path} n'est ni un dossier ni un zip lisible.")

    def open_xml(self):
        if self.zip:
            name = next(
                (n for n in self.zip.namelist()
                 if n.endswith("export.xml") and "cda" not in n.lower()), None)
            if not name:
                sys.exit("[!] export.xml introuvable dans l'archive.")
            return self.zip.open(name)
        p = os.path.join(self.root, "export.xml")
        if not os.path.exists(p):
            sys.exit(f"[!] {p} introuvable.")
        return open(p, "rb")

    def gpx_files(self):
        if self.zip:
            return [n for n in self.zip.namelist() if n.lower().endswith(".gpx")]
        d = os.path.join(self.root, "workout-routes")
        if not os.path.isdir(d):
            return []
        return [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(".gpx")]

    def read_gpx(self, name):
        if self.zip:
            return self.zip.read(name)
        with open(name, "rb") as f:
            return f.read()


def parse_export(exp, since=None, verbose=True):
    """Streaming iterparse : tient sur des export.xml de plusieurs centaines de Mo."""
    workouts, records, sleep = [], defaultdict(list), []
    seen_records = set()
    depth = 0
    n = 0

    with exp.open_xml() as fh:
        ctx = ET.iterparse(fh, events=("start", "end"))
        _, root = next(ctx)
        for event, elem in ctx:
            if event == "start":
                depth += 1
                continue
            depth -= 1
            tag = elem.tag

            if tag == "Record":
                rtype = elem.get("type")
                start = parse_dt(elem.get("startDate"))
                if start and (since is None or start.date() >= since):
                    if rtype in REC:
                        key = (rtype, elem.get("startDate"), elem.get("value"))
                        if key not in seen_records:   # dedoublonnage multi-sources
                            seen_records.add(key)
                            v = to_float(elem.get("value"))
                            if v is not None:
                                records[REC[rtype]].append((start, v, elem.get("sourceName", "")))
                    elif rtype == "HKCategoryTypeIdentifierSleepAnalysis":
                        end = parse_dt(elem.get("endDate"))
                        if end and elem.get("value") in SLEEP_ASLEEP:
                            sleep.append((start, end))

            elif tag == "Workout":
                w = read_workout(elem)
                if w and (since is None or w["start"].date() >= since):
                    workouts.append(w)

            if depth == 0:
                n += 1
                elem.clear()
                root.clear()
                if verbose and n % 200000 == 0:
                    print(f"    ... {n} elements lus", file=sys.stderr)

    return workouts, records, sleep


def read_workout(elem):
    start = parse_dt(elem.get("startDate"))
    end = parse_dt(elem.get("endDate"))
    if not start:
        return None

    atype = (elem.get("workoutActivityType") or "").replace("HKWorkoutActivityType", "")
    dur = to_float(elem.get("duration")) or 0.0
    if (elem.get("durationUnit") or "min") == "min":
        dur_s = dur * 60
    elif elem.get("durationUnit") == "sec":
        dur_s = dur
    else:
        dur_s = dur * 3600
    if not dur_s and end:
        dur_s = (end - start).total_seconds()

    dist = to_float(elem.get("totalDistance"))  # anciens exports
    if dist and (elem.get("totalDistanceUnit") or "km") == "m":
        dist /= 1000.0
    energy = to_float(elem.get("totalEnergyBurned"))
    hr_avg = hr_max = None
    denivele = None

    for child in elem:
        if child.tag == "MetadataEntry":
            k, v = child.get("key"), child.get("value") or ""
            if k == "HKElevationAscended":
                num = to_float(v.split()[0])
                if num is not None:
                    denivele = num / 100.0 if "cm" in v else num  # Apple stocke en cm
        elif child.tag == "WorkoutStatistics":
            t = child.get("type") or ""
            if t.endswith("HeartRate"):
                hr_avg = to_float(child.get("average")) or hr_avg
                hr_max = to_float(child.get("maximum")) or hr_max
            elif "Distance" in t:
                s = to_float(child.get("sum"))
                if s is not None:
                    dist = s / 1000.0 if child.get("unit") == "m" else s
            elif "EnergyBurned" in t and "Active" in t:
                energy = to_float(child.get("sum")) or energy

    return {
        "start": start, "end": end, "type": atype, "dur_s": dur_s,
        "dist_km": dist, "denivele": denivele, "hr_avg": hr_avg,
        "hr_max": hr_max, "kcal": energy,
        "source": elem.get("sourceName", ""),
    }


def dedupe_workouts(ws):
    """iPhone + Watch enregistrent parfois la meme seance : on garde la plus riche."""
    best = {}
    for w in sorted(ws, key=lambda x: x["start"]):
        key = (w["type"], w["start"].replace(second=0, microsecond=0).isoformat()[:15])
        score = (w["hr_avg"] is not None) * 2 + (w["dist_km"] is not None) + (w["denivele"] is not None)
        if key not in best or score > best[key][0]:
            best[key] = (score, w)
    return sorted((w for _, w in best.values()), key=lambda x: x["start"])


# --------------------------------------------------------------------------
# D+ depuis les traces GPX (fallback quand HKElevationAscended est absent)
# --------------------------------------------------------------------------
def gpx_gain(data, seuil=1.0):
    """D+ cumule avec lissage : on ignore les micro-variations sous `seuil` metres."""
    eles = [to_float(e.text) for e in ET.fromstring(data).iter()
            if e.tag.endswith("}ele") or e.tag == "ele"]
    eles = [e for e in eles if e is not None]
    if len(eles) < 3:
        return None, None
    # moyenne glissante sur 5 points pour attenuer le bruit barometrique
    k = 5
    lisse = [sum(eles[max(0, i - k):i + k + 1]) / len(eles[max(0, i - k):i + k + 1])
             for i in range(len(eles))]
    gain = 0.0
    ref = lisse[0]
    for e in lisse[1:]:
        if e - ref >= seuil:
            gain += e - ref
            ref = e
        elif e < ref:
            ref = e
    return round(gain), None


def gpx_start_time(name):
    m = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{1,2})\.(\d{2})(am|pm)", os.path.basename(name), re.I)
    if not m:
        return None
    d, h, mi, ap = m.groups()
    h = int(h) % 12 + (12 if ap.lower() == "pm" else 0)
    return datetime.strptime(f"{d} {h:02d}:{mi}", "%Y-%m-%d %H:%M")


def enrich_with_gpx(exp, workouts, verbose=True):
    files = exp.gpx_files()
    if not files:
        return
    besoin = [w for w in workouts if w["denivele"] is None and w["type"] in RUN_TYPES]
    if not besoin:
        return
    if verbose:
        print(f"[*] {len(besoin)} seance(s) sans D+ : lecture des traces GPX...", file=sys.stderr)
    index = [(gpx_start_time(f), f) for f in files]
    index = [(t, f) for t, f in index if t]
    for w in besoin:
        cand = min(index, key=lambda tf: abs((tf[0] - w["start"]).total_seconds()), default=None)
        if cand and abs((cand[0] - w["start"]).total_seconds()) <= 900:
            try:
                g, _ = gpx_gain(exp.read_gpx(cand[1]))
                if g is not None:
                    w["denivele"] = g
                    w["source_dplus"] = "gpx"
            except ET.ParseError:
                pass


# --------------------------------------------------------------------------
# Agregations
# --------------------------------------------------------------------------
def daily_series(records, sleep):
    jours = defaultdict(dict)
    for cle, vals in records.items():
        par_jour = defaultdict(list)
        for dt, v, _ in vals:
            par_jour[dt.date()].append(v)
        for d, vs in par_jour.items():
            jours[d][cle] = round(sum(vs) / len(vs), 2)

    # sommeil : rattache a la nuit se terminant ce matin-la
    nuits = defaultdict(list)
    for s, e in sleep:
        nuits[(e - timedelta(hours=18)).date() + timedelta(days=1)].append((s, e))
    for d, iv in nuits.items():
        jours[d]["sommeil_h"] = round(merge_intervals(iv) / 3600.0, 2)
    return jours


def weekly_series(workouts, jours):
    sem = defaultdict(lambda: {
        "km": 0.0, "dplus": 0.0, "sec": 0.0, "seances": 0, "seances_course": 0,
        "km_course": 0.0, "sec_course": 0.0, "nocturnes": 0,
        "fc_repos": [], "hrv": [], "sommeil": [],
    })
    for w in workouts:
        s = sem[iso_week(w["start"].date())]
        s["seances"] += 1
        s["sec"] += w["dur_s"]
        s["dplus"] += w["denivele"] or 0
        s["km"] += w["dist_km"] or 0
        if w["type"] in RUN_TYPES:
            s["seances_course"] += 1
            s["km_course"] += w["dist_km"] or 0
            s["sec_course"] += w["dur_s"]
            if w["start"].hour >= 19 or w["start"].hour < 7:
                s["nocturnes"] += 1
    for d, v in jours.items():
        s = sem[iso_week(d)]
        for src, dst in (("fc_repos", "fc_repos"), ("hrv", "hrv"), ("sommeil_h", "sommeil")):
            if src in v:
                s[dst].append(v[src])
    for s in sem.values():
        for k in ("fc_repos", "hrv", "sommeil"):
            s[k + "_moy"] = round(sum(s[k]) / len(s[k]), 1) if s[k] else None
    return sem


# --------------------------------------------------------------------------
# Sorties
# --------------------------------------------------------------------------
def digest_markdown(tag, workouts, jours, sem, race_date):
    lundi, dimanche = week_bounds(tag)
    s = sem.get(tag)
    ws = [w for w in workouts if lundi <= w["start"].date() <= dimanche]
    sxx = semaine_avant_course(lundi, race_date)

    out = []
    out.append("```")
    out.append(f"Semaine : S-{sxx:02d} ({lundi.strftime('%d/%m')} au {dimanche.strftime('%d/%m/%Y')})")
    if s:
        out.append(f"Volume : {s['km_course']:.1f} km / {int(s['dplus'])} m D+ / {hms(s['sec_course'])} "
                   f"(toutes activites : {hms(s['sec'])})")
    else:
        out.append("Volume : 0 km / 0 m D+ / 0h00")
    out.append("Seances realisees :")
    for w in ws:
        lbl = ACTIVITY_FR.get(w["type"], w["type"])
        j = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"][w["start"].weekday()]
        bits = [f"  - {j} {w['start'].strftime('%H:%M')} | {lbl}", hms(w["dur_s"])]
        bits.append(f"{w['dist_km']:.1f} km" if w["dist_km"] else "-")
        bits.append(f"{int(w['denivele'])} m D+" if w["denivele"] else "- m D+")
        if w["type"] in RUN_TYPES:
            p = pace(w["dist_km"], w["dur_s"])
            bits.append(f"{p}/km" if p else "-")
        elif w["dist_km"] and w["dur_s"]:
            bits.append(f"{w['dist_km'] / (w['dur_s'] / 3600):.1f} km/h")
        else:
            bits.append("-")
        if w["hr_avg"]:
            bits.append(f"{int(w['hr_avg'])} bpm ({pct_fcmax(w['hr_avg'])}% FCM, {zone_karvonen(w['hr_avg'])})")
        else:
            bits.append("- bpm")
        bits.append("RPE ?/10")
        if w["start"].hour >= 19 or w["start"].hour < 7:
            bits.append("NOCTURNE")
        out.append(" | ".join(bits))
    if not ws:
        out.append("  (aucune seance enregistree)")
    out.append("Seances prevues non realisees : [a completer]")
    fc = s["fc_repos_moy"] if s else None
    hrv = s["hrv_moy"] if s else None
    som = s["sommeil_moy"] if s else None
    out.append(f"FC repos moyenne : {fc if fc else '-'}    HRV moyenne : {hrv if hrv else '-'}")
    out.append(f"Sommeil moyen : {hms(som * 3600) if som else '-'}")
    out.append("Ressenti general (texte libre) : ")
    out.append("Douleurs / signaux : ")
    out.append("```")

    # tendance 4 semaines
    tags = sorted(t for t in sem if t <= tag)[-4:]
    if len(tags) > 1:
        out.append("")
        out.append("**Tendance 4 semaines**")
        out.append("")
        out.append("| Semaine | km course | D+ | m D+/km | Temps total | Seances | Nuit | FC repos | HRV | Sommeil |")
        out.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for t in tags:
            x = sem[t]
            ratio = f"{x['dplus'] / x['km_course']:.0f}" if x["km_course"] else "-"
            out.append(
                f"| {t} (S-{semaine_avant_course(week_bounds(t)[0], race_date):02d}) "
                f"| {x['km_course']:.1f} | {int(x['dplus'])} | {ratio} "
                f"| {hms(x['sec'])} | {x['seances']} | {x['nocturnes']} "
                f"| {x['fc_repos_moy'] or '-'} | {x['hrv_moy'] or '-'} "
                f"| {hms(x['sommeil_moy'] * 3600) if x['sommeil_moy'] else '-'} |")
    return "\n".join(out)


def write_csv(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def export_csv(outdir, workouts, jours, sem, race_date):
    os.makedirs(outdir, exist_ok=True)

    rows = []
    for w in workouts:
        rows.append({
            "date": w["start"].date().isoformat(),
            "heure": w["start"].strftime("%H:%M"),
            "semaine": iso_week(w["start"].date()),
            "type": ACTIVITY_FR.get(w["type"], w["type"]),
            "duree_min": round(w["dur_s"] / 60, 1),
            "km": round(w["dist_km"], 2) if w["dist_km"] else "",
            "dplus_m": int(w["denivele"]) if w["denivele"] else "",
            "allure_min_km": pace(w["dist_km"], w["dur_s"]) if w["type"] in RUN_TYPES else "",
            "vitesse_km_h": round(w["dist_km"] / (w["dur_s"] / 3600), 1)
                            if w["dist_km"] and w["dur_s"] and w["type"] not in RUN_TYPES else "",
            "fc_moy": int(w["hr_avg"]) if w["hr_avg"] else "",
            "fc_max": int(w["hr_max"]) if w["hr_max"] else "",
            "pct_fcmax": pct_fcmax(w["hr_avg"]) or "",
            "zone": zone_karvonen(w["hr_avg"]),
            "kcal": int(w["kcal"]) if w["kcal"] else "",
            "nocturne": "oui" if (w["start"].hour >= 19 or w["start"].hour < 7) else "non",
            "source": w["source"],
        })
    write_csv(os.path.join(outdir, "workouts.csv"), rows, list(rows[0].keys()) if rows else ["date"])

    dcols = ["date", "fc_repos", "hrv", "sommeil_h", "poids", "masse_grasse",
             "masse_maigre", "vo2max", "freq_resp", "fc_marche"]
    drows = [dict(date=d.isoformat(), **v) for d, v in sorted(jours.items())]
    write_csv(os.path.join(outdir, "daily.csv"), drows, dcols)

    wrows = []
    for t in sorted(sem):
        x = sem[t]
        wrows.append({
            "semaine": t,
            "s_moins": semaine_avant_course(week_bounds(t)[0], race_date),
            "lundi": week_bounds(t)[0].isoformat(),
            "km_course": round(x["km_course"], 1),
            "dplus_m": int(x["dplus"]),
            "temps_course_min": round(x["sec_course"] / 60),
            "temps_total_min": round(x["sec"] / 60),
            "seances": x["seances"],
            "seances_course": x["seances_course"],
            "sorties_nocturnes": x["nocturnes"],
            "dplus_par_km": round(x["dplus"] / x["km_course"], 1) if x["km_course"] else "",
            "fc_repos_moy": x["fc_repos_moy"] or "",
            "hrv_moy": x["hrv_moy"] or "",
            "sommeil_moy_h": x["sommeil_moy"] or "",
        })
    write_csv(os.path.join(outdir, "weekly.csv"), wrows,
              list(wrows[0].keys()) if wrows else ["semaine"])
    return len(rows), len(drows), len(wrows)


# --------------------------------------------------------------------------
def main():
    global FC_MAX, FC_REPOS
    ap = argparse.ArgumentParser(description="Extraction Sante iPhone -> digest SainteLyon")
    ap.add_argument("export", help="export.zip ou dossier apple_health_export")
    ap.add_argument("--week", help="semaine ISO, ex 2026-W37 (defaut : derniere semaine complete)")
    ap.add_argument("--weeks-back", type=int, help="genere les N dernieres semaines")
    ap.add_argument("--all", action="store_true", help="digest de toutes les semaines")
    ap.add_argument("--since", help="ne lire que depuis cette date (AAAA-MM-JJ) — accelere beaucoup")
    ap.add_argument("--outdir", default="./sortie-sante")
    ap.add_argument("--no-gpx", action="store_true", help="ne pas ouvrir les traces GPS")
    ap.add_argument("--race-date", default=RACE_DATE.isoformat())
    ap.add_argument("--fcmax", type=int, default=FC_MAX)
    ap.add_argument("--fcrepos", type=int, default=FC_REPOS)
    a = ap.parse_args()

    FC_MAX, FC_REPOS = a.fcmax, a.fcrepos
    race = date.fromisoformat(a.race_date)
    since = date.fromisoformat(a.since) if a.since else None

    exp = Export(a.export)
    print("[*] Lecture de export.xml (peut prendre 1-3 min sur un gros export)...", file=sys.stderr)
    workouts, records, sleep = parse_export(exp, since)
    workouts = dedupe_workouts(workouts)
    if not a.no_gpx:
        enrich_with_gpx(exp, workouts)

    jours = daily_series(records, sleep)
    sem = weekly_series(workouts, jours)
    if not sem:
        sys.exit("[!] Aucune donnee exploitable trouvee.")

    n1, n2, n3 = export_csv(a.outdir, workouts, jours, sem, race)
    print(f"[*] {n1} seances, {n2} jours, {n3} semaines -> {a.outdir}/", file=sys.stderr)

    tags = sorted(sem)
    if a.all:
        cibles = tags
    elif a.week:
        cibles = [a.week]
    elif a.weeks_back:
        cibles = tags[-a.weeks_back:]
    else:
        courante = iso_week(date.today())
        cibles = [t for t in tags if t != courante][-1:] or tags[-1:]

    blocs = []
    for t in cibles:
        if t not in sem:
            print(f"[!] semaine {t} absente des donnees", file=sys.stderr)
            continue
        blocs.append(digest_markdown(t, workouts, jours, sem, race))
    texte = "\n\n---\n\n".join(blocs)
    print(texte)
    with open(os.path.join(a.outdir, "digest.md"), "w", encoding="utf-8") as f:
        f.write(texte + "\n")
    print(f"\n[*] digest.md ecrit dans {a.outdir}/", file=sys.stderr)


if __name__ == "__main__":
    main()

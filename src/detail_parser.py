#!/usr/bin/env python3
"""
Passe 2 — extraction FC horodatée + trace GPS par séance.
Lit   : data/last_export.zip  +  sortie-sante/workouts.csv
Écrit : details/{fname}.json  +  data/.details_progress
"""
import csv
import json
import os
import re
import zipfile
from datetime import datetime
from xml.etree import ElementTree as ET

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR     = os.path.join(PROJECT_ROOT, "sortie-sante")
DETAILS_DIR  = os.path.join(PROJECT_ROOT, "details")
EXPORT_PATH  = os.path.join(PROJECT_ROOT, "data", "last_export.zip")
PROGRESS     = os.path.join(PROJECT_ROOT, "data", ".details_progress")

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
GPX_RE  = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{1,2})\.(\d{2})(am|pm)", re.I)


def _dt(s):
    if not s:
        return None
    m = DATE_RE.match(s)
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") if m else None


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def workout_filename(date: str, heure: str, wtype: str) -> str:
    raw = f"{date}_{heure.replace(':', '')}_{wtype}"
    return raw.replace(" ", "_").replace("/", "-")


def _write_progress(done: int, total: int, status: str = "running"):
    with open(PROGRESS, "w") as f:
        json.dump({"done": done, "total": total, "status": status}, f)


def read_progress() -> dict:
    if os.path.exists(PROGRESS):
        with open(PROGRESS) as f:
            return json.load(f)
    return {}


def _parse_gpx(data: bytes) -> list[dict]:
    samples = []
    try:
        root = ET.fromstring(data)
        for trkpt in root.iter():
            if not trkpt.tag.endswith("trkpt"):
                continue
            lat, lon = _f(trkpt.get("lat")), _f(trkpt.get("lon"))
            ele = ts = None
            for child in trkpt:
                tag = child.tag.split("}")[-1]
                if tag == "ele":
                    ele = _f(child.text)
                elif tag == "time" and child.text:
                    try:
                        ts = int(datetime.fromisoformat(
                            child.text.replace("Z", "+00:00")).timestamp())
                    except ValueError:
                        pass
            if lat is not None and lon is not None:
                samples.append({"ts": ts, "lat": lat, "lon": lon, "ele": ele})
    except ET.ParseError:
        pass
    return samples


def main():
    os.makedirs(DETAILS_DIR, exist_ok=True)

    if not os.path.exists(os.path.join(DATA_DIR, "workouts.csv")) or not os.path.exists(EXPORT_PATH):
        _write_progress(0, 0, "error")
        return

    with open(os.path.join(DATA_DIR, "workouts.csv"), encoding="utf-8") as f:
        workouts = list(csv.DictReader(f, delimiter=";"))

    windows = []
    for w in workouts:
        fname = workout_filename(w["date"], w["heure"], w["type"])
        out = os.path.join(DETAILS_DIR, f"{fname}.json")
        if os.path.exists(out):
            continue
        try:
            dt_start = datetime.strptime(f"{w['date']} {w['heure']}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        dur_s = (_f(w.get("duree_min")) or 0) * 60
        windows.append({
            "fname": fname, "out": out,
            "wid": f"{w['date']}_{w['heure'].replace(':', '')}_{w['type']}",
            "ts0": dt_start.timestamp() - 120,
            "ts1": dt_start.timestamp() + dur_s + 120,
            "hr": [],
        })

    if not windows:
        _write_progress(0, 0, "done")
        return

    _write_progress(0, len(windows))
    windows.sort(key=lambda x: x["ts0"])
    ts_min, ts_max = windows[0]["ts0"], windows[-1]["ts1"]

    with zipfile.ZipFile(EXPORT_PATH) as z:
        # ── HR samples ────────────────────────────────────────────────────────
        xml_name = next(
            (n for n in z.namelist() if n.endswith("export.xml") and "cda" not in n.lower()),
            None,
        )
        if not xml_name:
            _write_progress(0, len(windows), "error")
            return

        with z.open(xml_name) as fh:
            for _, elem in ET.iterparse(fh, events=("end",)):
                if elem.tag != "Record":
                    elem.clear()
                    continue
                if elem.get("type") != "HKQuantityTypeIdentifierHeartRate":
                    elem.clear()
                    continue
                dt = _dt(elem.get("startDate"))
                if not dt:
                    elem.clear()
                    continue
                ts = dt.timestamp()
                if ts < ts_min or ts > ts_max:
                    elem.clear()
                    continue
                bpm = _f(elem.get("value"))
                if bpm:
                    for w in windows:
                        if w["ts0"] <= ts <= w["ts1"]:
                            w["hr"].append({"ts": int(ts), "bpm": int(bpm)})
                elem.clear()

        # ── GPX index ────────────────────────────────────────────────────────
        gpx_index = []
        for name in z.namelist():
            if not name.lower().endswith(".gpx"):
                continue
            m = GPX_RE.search(os.path.basename(name))
            if not m:
                continue
            d, h, mi, ap = m.groups()
            h = int(h) % 12 + (12 if ap.lower() == "pm" else 0)
            try:
                gt = datetime.strptime(f"{d} {h:02d}:{mi}", "%Y-%m-%d %H:%M").timestamp()
                gpx_index.append((gt, name))
            except ValueError:
                pass

        # ── Écriture des fichiers détail ──────────────────────────────────────
        for i, w in enumerate(windows):
            gps = []
            if gpx_index:
                best = min(gpx_index, key=lambda x: abs(x[0] - (w["ts0"] + 120)))
                if abs(best[0] - (w["ts0"] + 120)) <= 900:
                    gps = _parse_gpx(z.read(best[1]))

            with open(w["out"], "w", encoding="utf-8") as f:
                json.dump({
                    "workout_id": w["wid"],
                    "parsed_at": datetime.now().isoformat(timespec="seconds"),
                    "hr_samples": sorted(w["hr"], key=lambda x: x["ts"]),
                    "hr_count": len(w["hr"]),
                    "gps_track": gps,
                    "gps_count": len(gps),
                }, f, ensure_ascii=False)

            _write_progress(i + 1, len(windows))

    _write_progress(len(windows), len(windows), "done")


if __name__ == "__main__":
    main()

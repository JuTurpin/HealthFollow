"""Tests de l'export bilan coach — python -m unittest"""
import csv
import glob
import io
import json
import os
import re
import shutil
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timedelta

import pandas as pd

from src import bilan_export as be
from src import charge, config, drift, zones
from tests.fixtures import synthetique as fx

CFG = {**config.DEFAULTS, "fc_max": 185, "fc_repos": 51}
RACE = config.race(CFG)
T0 = datetime(2026, 10, 6, 18, 30)


def hr_const(segments, start=T0, step=5):
    """segments : [(minutes, bpm), …] → échantillons FC consécutifs."""
    out, t = [], int(start.timestamp())
    for minutes, bpm in segments:
        for _ in range(int(minutes * 60 / step)):
            out.append({"ts": t, "bpm": bpm})
            t += step
    out.append({"ts": t, "bpm": segments[-1][1]})
    return out


def gps(segments, start=T0, step=5, ele0=300.0):
    """segments : [(minutes, km/h, pente %), …] → trace GPS rectiligne vers le nord."""
    pts, t, dist, ele = [], int(start.timestamp()), 0.0, ele0
    pts.append({"ts": t, "lat": fx.LAT0, "lon": fx.LON0, "ele": ele})
    for minutes, v, pente in segments:
        for _ in range(int(minutes * 60 / step)):
            d = v / 3.6 * step
            dist += d
            ele += d * pente / 100
            t += step
            pts.append({"ts": t, "lat": fx.LAT0 + dist / 111_195.0, "lon": fx.LON0, "ele": ele})
    return pts


def _json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class TestSemaines(unittest.TestCase):
    def test_s_moins(self):
        self.assertEqual(be.s_moins(date(2026, 10, 5), RACE["date"]), 7)
        self.assertEqual(be.s_moins(date(2026, 11, 23), RACE["date"]), 0)

    def test_libelle(self):
        self.assertEqual(be.libelle_semaine(date(2026, 10, 5), RACE["date"]),
                         "S-07 · 2026-W41 · 05/10 → 11/10")

    def test_derniere_semaine_complete(self):
        self.assertEqual(be.derniere_semaine_complete(date(2026, 10, 11)), date(2026, 9, 28))
        self.assertEqual(be.derniere_semaine_complete(date(2026, 10, 12)), date(2026, 10, 5))

    def test_iso_tag_vs_strftime_W(self):
        # %W (ancien bilan) se trompe d'une semaine en 2026 ; iso_tag suit la norme ISO
        self.assertEqual(be.iso_tag(date(2026, 10, 5)), "2026-W41")
        self.assertEqual(date(2026, 10, 5).strftime("%Y-W%W"), "2026-W40")


class TestZones(unittest.TestCase):
    def test_temps_en_zones(self):
        b = zones.zone_bounds(51, 185)   # 131.4 / 144.8 / 158.2 / 171.6
        samples = hr_const([(10, 120), (20, 140), (5, 150), (5, 165), (2, 180)])
        zt = zones.zone_times({"hr_samples": samples}, 51, 185)
        self.assertAlmostEqual(zt["Z1"], 10, places=1)
        self.assertAlmostEqual(zt["Z2"], 20, places=1)
        self.assertAlmostEqual(zt["Z3"], 5, places=1)
        self.assertAlmostEqual(zt["Z4"], 5, places=1)
        self.assertAlmostEqual(zt["Z5"], 2, places=1)
        self.assertLess(b[0], 140)

    def test_trou_fc_non_compte(self):
        samples = hr_const([(10, 140)])
        trou = [{"ts": samples[-1]["ts"] + 120, "bpm": 140}] + \
               [{"ts": samples[-1]["ts"] + 120 + 5 * i, "bpm": 140} for i in range(1, 121)]
        st = be.stats_fc(samples + trou, 22, 51, 185, True)
        self.assertAlmostEqual(st["t_z2_min"], 20, places=1)
        self.assertAlmostEqual(st["t_sans_fc_min"], 2, places=1)
        self.assertAlmostEqual(st["pct_fc_manquante"], 9.1, places=1)


class TestDerive(unittest.TestCase):
    def test_20_20(self):
        samples = hr_const([(20, 130), (30, 140), (20, 150)])
        d = drift.derive_debut_fin(samples, 20)
        self.assertAlmostEqual(d["fc_debut"], 130, delta=0.5)
        self.assertAlmostEqual(d["fc_fin"], 150, delta=0.5)
        self.assertAlmostEqual(d["derive_bpm"], 20, delta=0.5)
        # le calcul par tiers reste disponible à côté
        self.assertIn("drift_pct", drift.analyse(samples))

    def test_trop_court(self):
        self.assertEqual(drift.derive_debut_fin(hr_const([(35, 140)]), 20), {})


class TestGPS(unittest.TestCase):
    def test_decouplage(self):
        # vitesse constante 10 km/h, FC 140 puis 154 : (154/140 − 1) × 100 = 10 %
        tr = gps([(30, 10, 0), (30, 10, 0)])
        hr = hr_const([(30, 140), (30, 154)])
        seg = be.segments_gps({"gps_track": tr})
        self.assertAlmostEqual(be.decouplage(seg, hr, 60), 10.0, delta=0.6)

    def test_decouplage_hors_pauses(self):
        # une pause de 10 min (FC basse) au milieu ne doit pas changer le résultat
        tr = gps([(30, 10, 0), (10, 0, 0), (30, 10, 0)])
        hr = hr_const([(30, 140), (10, 100), (30, 140)])
        seg = be.segments_gps({"gps_track": tr})
        self.assertAlmostEqual(be.decouplage(seg, hr, 70), 0.0, delta=0.6)

    def test_decouplage_conditions(self):
        tr = gps([(30, 10, 0)])
        hr = hr_const([(30, 140)])
        self.assertIsNone(be.decouplage(be.segments_gps({"gps_track": tr}), hr, 30))  # < 40 min
        self.assertIsNone(be.decouplage(None, hr, 60))                               # sans GPS

    def test_dminus_et_splits(self):
        # 1,5 km à +4 % puis 1,5 km à −4 % à 10 km/h : D+ ≈ D− ≈ 60 m, 3 splits à 6:00
        tr = gps([(9, 10, 4), (9, 10, -4)])
        seg = be.segments_gps({"gps_track": tr})
        dp, dm = be.denivele_gps(seg)
        self.assertAlmostEqual(dp, 60, delta=3)
        self.assertAlmostEqual(dm, 60, delta=3)
        sp = be.splits(seg, hr_const([(18, 140)]), "w")
        self.assertEqual([s["km_index"] for s in sp], [1, 2, 3])
        self.assertEqual(sp[0]["allure_min_km"], "6:00")
        self.assertEqual(sp[0]["fc_moy_bpm"], 140)
        self.assertGreater(sp[0]["pente_moy_pct"], 3)
        self.assertLess(sp[2]["pente_moy_pct"], -3)
        self.assertEqual(sum(s["dplus_m"] for s in sp), dp)
        for s in sp:
            self.assertFalse(any(k in s for k in ("lat", "lon")))

    def test_marche_course_arret(self):
        tr = gps([(10, 10, 0), (10, 5, 0), (5, 0, 0), (10, 10, 0)])
        t = be.temps_par_mode(be.segments_gps({"gps_track": tr}))
        self.assertAlmostEqual(t["t_course_min"], 20, delta=0.5)
        self.assertAlmostEqual(t["t_marche_min"], 10, delta=0.5)
        self.assertAlmostEqual(t["t_arret_min"], 5, delta=0.5)
        self.assertEqual(be.V_ARRET_KMH, 1.0)
        self.assertEqual(be.V_MARCHE_KMH, 7.0)

    def test_vitesse_ascensionnelle(self):
        # montée à 10 % à 6 km/h : 600 m/h ; le plat ne compte pas
        tr = gps([(10, 10, 0), (20, 6, 10), (10, 10, 0)])
        v = be.vitesse_ascensionnelle(be.segments_gps({"gps_track": tr}))
        self.assertAlmostEqual(v, 600, delta=30)


class TestTrimp(unittest.TestCase):
    def test_echantillons_vs_moyenne(self):
        samples = hr_const([(60, 140)])
        self.assertAlmostEqual(charge.trimp_echantillons(samples, 51, 185),
                               charge.trimp(60, 140, 51, 185), delta=0.5)

    def test_source(self):
        row = {"date": "2026-10-06", "heure": "18:30", "type": "Course", "duree_min": 60,
               "km": None, "dplus_m": None, "fc_moy": 140, "fc_max": 150, "nocturne": "non"}
        l, _ = be.analyser_seance(row, {"hr_samples": hr_const([(60, 140)]), "gps_track": []}, {}, CFG)
        self.assertEqual(l["trimp_source"], "echantillons")
        l, _ = be.analyser_seance(row, None, {}, CFG)
        self.assertEqual(l["trimp_source"], "fc_moy")


class TestPlanning(unittest.TestCase):
    def test_parseur(self):
        rows = be.parser_planning(fx.PLANNING_MD, 51, 185)
        self.assertEqual(len(rows), 7)          # seulement « Semaine en cours »
        self.assertEqual([r["jour_idx"] for r in rows], list(range(7)))
        b = zones.zone_bounds(51, 185)
        cibles = {r["fc_cible"]: (r["fc_lo"], r["fc_hi"]) for r in rows if r["fc_cible"]}
        self.assertEqual(cibles["135-145"], (135, 145))
        self.assertEqual(cibles["≤ 150"], (None, 150))
        self.assertEqual(cibles["≤ 131"], (None, 131))
        self.assertEqual(cibles["Z1/Z2"], (None, round(b[1])))
        self.assertEqual(cibles["120-140"], (120, 140))
        self.assertEqual([r["famille"] for r in rows],
                         ["repos", "course", "renfo", "course", "course", "course", "velo"])
        self.assertEqual(rows[1]["duree_min"], 50)
        self.assertEqual(rows[2]["duree_min"], 40)
        self.assertEqual(rows[3]["duree_min"], 60)
        self.assertEqual(rows[5]["duree_min"], 120)
        self.assertEqual(rows[5]["dplus_m"], 400)

    def test_cibles_isolees(self):
        self.assertEqual(be.parser_cible_fc("<= 131", 51, 185), (None, 131))
        self.assertEqual(be.parser_cible_fc("120–140 bpm", 51, 185), (120, 140))
        self.assertEqual(be.parser_cible_fc("—", 51, 185), (None, None))

    def test_sans_section(self):
        self.assertEqual(be.parser_planning("# rien\n| a | b |\n|---|---|\n| 1 | 2 |", 51, 185), [])


class TestPack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        fx.generer(cls.tmp)
        d = os.path.join(cls.tmp, "sortie-sante")
        cls.wk = pd.read_csv(os.path.join(d, "workouts.csv"), sep=";")
        cls.daily = pd.read_csv(os.path.join(d, "daily.csv"), sep=";")
        cls.weekly = pd.read_csv(os.path.join(d, "weekly.csv"), sep=";")
        cls.details = {d["workout_id"]: d for d in
                       (_json(p) for p in glob.glob(os.path.join(cls.tmp, "details", "*.json")))}
        cls.journal = _json(os.path.join(cls.tmp, "journal.json"))
        cls.planning_path = os.path.join(cls.tmp, "planning-hebdo.md")
        with open(cls.planning_path, "w", encoding="utf-8") as f:
            f.write(fx.PLANNING_MD)
        with open(cls.planning_path, "rb") as f:
            cls.planning_avant = f.read()
        cls.pack = be.construire_pack(
            date(2026, 10, 5), cls.wk, cls.daily, cls.weekly, cls.details, cls.journal,
            CFG, RACE, planning_md=cls.planning_avant.decode("utf-8"),
            now=datetime(2026, 10, 11, 21, 0))
        cls.zip = be.zip_pack(cls.pack["fichiers"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def _zip(self):
        return zipfile.ZipFile(io.BytesIO(self.zip))

    def test_contenu_et_taille(self):
        self.assertEqual(self.pack["nom"], "bilan_S-07_2026-W41")
        self.assertEqual(set(self._zip().namelist()),
                         {"digest.md", "seances.csv", "splits.csv", "jours.csv",
                          "tendance.csv", "prevu_vs_realise.csv"})
        self.assertLess(len(self.zip), 150 * 1024)

    def test_aucune_lat_lon(self):
        motif_col = re.compile(r"(^|_)(lat|lon|lng)(_|$)|latitude|longitude", re.I)
        coords = {f"{fx.LAT0:.3f}", f"{fx.LON0:.3f}", "45.12", "4.65"}
        z = self._zip()
        for nom in z.namelist():
            texte = z.read(nom).decode("utf-8")
            self.assertIsNone(re.search(r"\b(lat|lon|lng|latitude|longitude)\b", texte, re.I), nom)
            for c in coords:
                self.assertNotIn(c, texte, f"{nom} contient {c}")
            if nom.endswith(".csv"):
                for col in next(csv.reader(io.StringIO(texte), delimiter=";")):
                    self.assertIsNone(motif_col.search(col), f"{nom}:{col}")
            self.assertNotIn("Apple Watch de Test", texte)     # nom de source / appareil

    def test_na_jamais_vide(self):
        z = self._zip()
        for nom in z.namelist():
            if not nom.endswith(".csv"):
                continue
            lignes = list(csv.reader(io.StringIO(z.read(nom).decode("utf-8")), delimiter=";"))
            for l in lignes[1:]:
                self.assertEqual(len(l), len(lignes[0]), nom)
                for v in l:
                    self.assertNotEqual(v.strip(), "", f"cellule vide dans {nom}")

    def test_na_different_de_zero(self):
        se = pd.read_csv(io.StringIO(self.pack["fichiers"]["seances.csv"]), sep=";",
                         keep_default_na=False, dtype=str)
        sans_detail = se[se["type"] == "Renfo fonctionnel"].iloc[-1]   # pas de fichier détail
        self.assertEqual(sans_detail["t_z1_min"], "NA")
        self.assertEqual(sans_detail["dminus_m"], "NA")
        self.assertEqual(sans_detail["km"], "NA")
        course = se[se["workout_id"] == "2026-10-06_1830_Course"].iloc[0]
        self.assertEqual(course["t_z5_min"], "0")       # vraie valeur nulle
        self.assertEqual(course["t_z1_min"], "0")
        self.assertEqual(course["pct_fc_manquante"], "0")
        self.assertEqual(be.vers_csv(pd.DataFrame({"a": [None, 0, 0.0, "", float("nan")]}), ["a"]),
                         "a\nNA\n0\n0\nNA\nNA\n")

    def test_seances_toutes_activites(self):
        se = self.pack["seances"]
        self.assertEqual(sorted(se["type"].unique()), ["Course", "Renfo fonctionnel", "Tennis"])
        self.assertEqual(self.pack["sans_journal"], ["dim 10:00 Tennis"])
        self.assertEqual(list(se.columns[:len(be.SEANCES_COLS)]), be.SEANCES_COLS)

    def test_jours_et_tendance(self):
        jours = pd.read_csv(io.StringIO(self.pack["fichiers"]["jours.csv"]), sep=";")
        self.assertEqual(len(jours), 7)
        for c in ("hrv_r7", "fc_repos_r7", "sommeil_r7", "trimp_jour", "atl", "ctl", "tsb"):
            self.assertIn(c, jours.columns)
        tend = pd.read_csv(io.StringIO(self.pack["fichiers"]["tendance.csv"]), sep=";")
        self.assertEqual(len(tend), 8)
        self.assertEqual(tend["semaine"].iloc[-1], "2026-W41")
        self.assertEqual(list(tend.columns), be.TENDANCE_COLS)

    def test_digest(self):
        d = self.pack["digest"]
        self.assertTrue(d.startswith("# Bilan S-07 (05/10 → 11/10/2026) — HealthFollow"))
        for titre in ("## Résumé (format protocole)", "## Séances (détail)",
                      "## Sortie longue de la semaine", "## Prévu vs réalisé", "## Charge",
                      "## Récupération (7 jours)", "## Tendance 8 semaines",
                      "## Nuit / ravitaillement de la semaine", "## Anomalies (factuelles)"):
            self.assertIn(titre, d)
        self.assertIn("Sans journal : dim 10:00 Tennis", d)
        # descriptif, pas d'interprétation
        for mot in ("fatigu", "bonne semaine", "bravo", "excellent", "attention"):
            self.assertNotIn(mot, d.lower().replace("fatigue_j1", ""))

    def test_prevu_vs_realise(self):
        pvr = pd.read_csv(io.StringIO(self.pack["fichiers"]["prevu_vs_realise.csv"]), sep=";",
                          keep_default_na=False, dtype=str)
        self.assertEqual(list(pvr.columns), be.PVR_COLS)
        statuts = dict(zip(pvr["seance_prevue"], pvr["statut_propose"]))
        self.assertEqual(statuts["Renfo PPG"], "✅")
        self.assertEqual(statuts["Fractionné côtes"], "❌")
        self.assertEqual(statuts["Vélo Zwift"], "❌")
        self.assertIn("hors_plan", pvr["statut_propose"].tolist())
        sl = pvr[pvr["seance_prevue"] == "Sortie longue trail"].iloc[0]
        self.assertEqual(sl["seance_realisee"], "sam 08:00 Course")

    def test_planning_non_modifie(self):
        with open(self.planning_path, "rb") as f:
            self.assertEqual(f.read(), self.planning_avant)

    def test_sans_planning(self):
        p = be.construire_pack(date(2026, 10, 5), self.wk, self.daily, self.weekly, self.details,
                               self.journal, CFG, RACE, now=datetime(2026, 10, 11, 21, 0))
        self.assertNotIn("prevu_vs_realise.csv", p["fichiers"])
        self.assertIn("Séances prévues non réalisées : à compléter", p["digest"])

    def test_semaine_vide(self):
        p = be.construire_pack(date(2026, 6, 1), self.wk, self.daily, self.weekly, {}, {},
                               CFG, RACE, now=datetime(2026, 10, 11, 21, 0))
        self.assertIn("(aucune séance enregistrée)", p["digest"])
        self.assertEqual(p["fichiers"]["seances.csv"].count("\n"), 1)


if __name__ == "__main__":
    unittest.main()

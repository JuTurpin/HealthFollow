"""Tests du parser Apple Health (passes 1 et 2) — python -m unittest"""
import unittest
from datetime import date, datetime, timedelta

import sainteylon_health as sh
from src import detail_parser as dp

GPX = b"""<?xml version="1.0"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
  <trkpt lat="45.1" lon="4.6"><ele>300</ele><time>2026-10-06T16:30:00Z</time></trkpt>
  <trkpt lat="45.2" lon="4.7"><ele>%s</ele><time>2026-10-06T16:30:05Z</time></trkpt>
  <trkpt lat="45.3" lon="4.8"><ele>310</ele></trkpt>
  <trkpt lon="4.9"><ele>320</ele></trkpt>
</trkseg></trk></gpx>"""


class TestUtilitaires(unittest.TestCase):
    def test_parse_dt(self):
        self.assertEqual(sh.parse_dt("2026-05-26 08:46:00 +0200"), datetime(2026, 5, 26, 8, 46))
        self.assertIsNone(sh.parse_dt(""))
        self.assertIsNone(sh.parse_dt("26/05/2026"))

    def test_to_float(self):
        self.assertEqual(sh.to_float("12.5"), 12.5)
        self.assertIsNone(sh.to_float(None))
        self.assertIsNone(sh.to_float("abc"))

    def test_semaines_iso(self):
        self.assertEqual(sh.iso_week(date(2026, 1, 1)), "2026-W01")
        self.assertEqual(sh.iso_week(date(2027, 1, 1)), "2026-W53")   # 2026 a 53 semaines ISO
        self.assertEqual(sh.week_bounds("2026-W41"), (date(2026, 10, 5), date(2026, 10, 11)))

    def test_semaine_avant_course(self):
        course = date(2026, 11, 28)
        self.assertEqual(sh.semaine_avant_course(date(2026, 11, 23), course), 0)
        self.assertEqual(sh.semaine_avant_course(date(2026, 10, 5), course), 7)
        self.assertEqual(sh.semaine_avant_course(date(2026, 12, 7), course), 0)   # jamais négatif

    def test_hms_et_allure(self):
        self.assertEqual(sh.hms(3725), "1h02")
        self.assertEqual(sh.hms(125), "2min05")
        self.assertEqual(sh.pace(10, 3000), "5:00")
        self.assertEqual(sh.pace(10, 3330), "5:33")
        self.assertEqual(sh.pace(0.1, 60), "")
        self.assertEqual(sh.pace(None, 60), "")

    def test_zone_karvonen(self):
        self.assertEqual(sh.zone_karvonen(None), "")
        self.assertEqual(sh.zone_karvonen(120), "Z1")
        self.assertEqual(sh.zone_karvonen(140), "Z2")
        self.assertEqual(sh.zone_karvonen(180), "Z5")

    def test_merge_intervals(self):
        t = datetime(2026, 10, 5, 23, 0)
        h = lambda n: t + timedelta(hours=n)
        self.assertEqual(sh.merge_intervals([]), 0.0)
        # chevauchement (0-2, 1-3) + intervalle disjoint (5-6) → 4 h
        self.assertEqual(sh.merge_intervals([(h(5), h(6)), (h(0), h(2)), (h(1), h(3))]), 4 * 3600)


class TestDedoublonnage(unittest.TestCase):
    def _w(self, minute, hr=None, km=None, dplus=None, wtype="Running"):
        return {"type": wtype, "start": datetime(2026, 10, 6, 18, minute, 30),
                "hr_avg": hr, "dist_km": km, "denivele": dplus}

    def test_garde_la_plus_riche(self):
        watch, iphone = self._w(30, hr=140, km=10), self._w(30, km=10)
        res = sh.dedupe_workouts([iphone, watch])
        self.assertEqual(res, [watch])

    def test_types_differents_conserves(self):
        res = sh.dedupe_workouts([self._w(30), self._w(30, wtype="Cycling")])
        self.assertEqual(len(res), 2)


class TestDenivele(unittest.TestCase):
    def test_lissage_conserve_constante(self):
        self.assertEqual(sh.lisser_altitudes([300.0] * 10), [300.0] * 10)

    def test_cumul_montee_descente(self):
        alt = [0, 10, 20, 15, 5, 25]
        self.assertEqual(sh.cumul_denivele(alt), (40, 15))
        self.assertEqual(sh.cumul_denivele([]), (0.0, 0.0))

    def test_bruit_sous_le_seuil(self):
        self.assertEqual(sh.cumul_denivele([100, 100.5, 100, 100.5, 100], seuil=1.0), (0.0, 0.0))

    def test_gpx_gain(self):
        # montée régulière de 0 à 100 m puis descente à 50 m, 1 point par mètre
        alt = list(range(0, 101)) + list(range(99, 49, -1))
        pts = "".join(f'<trkpt lat="45" lon="4"><ele>{e}</ele></trkpt>' for e in alt)
        gain, perte = sh.gpx_gain(f'<gpx xmlns="http://www.topografix.com/GPX/1/1">{pts}</gpx>'.encode())
        # le lissage ±5 points rabote les extrêmes (départ ≈ 2.5 m, sommet ≈ 97 m)
        self.assertAlmostEqual(gain, 100, delta=8)
        self.assertAlmostEqual(perte, 50, delta=8)
        self.assertEqual(sh.gpx_gain(b"<gpx><ele>1</ele></gpx>"), (None, None))

    def test_gpx_start_time(self):
        self.assertEqual(sh.gpx_start_time("route_2026-10-06_6.30pm.gpx"), datetime(2026, 10, 6, 18, 30))
        self.assertEqual(sh.gpx_start_time("route_2026-10-06_12.05am.gpx"), datetime(2026, 10, 6, 0, 5))
        self.assertIsNone(sh.gpx_start_time("trace.gpx"))


class TestDetailParser(unittest.TestCase):
    def test_workout_filename(self):
        self.assertEqual(dp.workout_filename("2026-10-06", "18:30", "Course à pied"),
                         "2026-10-06_1830_Course_à_pied")
        self.assertEqual(dp.workout_filename("2026-10-06", "18:30", "A/B"), "2026-10-06_1830_A-B")

    def test_parse_gpx(self):
        pts = dp._parse_gpx(GPX % b"305")
        self.assertEqual(len(pts), 3)                        # le point sans lat est ignoré
        self.assertEqual(pts[0], {"ts": int(datetime.fromisoformat("2026-10-06T16:30:00+00:00").timestamp()),
                                  "lat": 45.1, "lon": 4.6, "ele": 300.0})
        self.assertIsNone(pts[2]["ts"])                      # pas de <time>

    def test_parse_gpx_invalide(self):
        self.assertEqual(dp._parse_gpx(b"<gpx><pas ferme"), [])


if __name__ == "__main__":
    unittest.main()

"""Tests des calculs physiologiques (TRIMP, zones Karvonen, drift) — python -m unittest"""
import math
import unittest

from src import charge, drift, zones


def hr(segments, t0=1_760_000_000, step=5):
    """segments : [(minutes, bpm), …] → échantillons FC consécutifs."""
    out, t = [], t0
    for minutes, bpm in segments:
        for _ in range(int(minutes * 60 / step)):
            out.append({"ts": t, "bpm": bpm})
            t += step
    out.append({"ts": t, "bpm": segments[-1][1]})
    return out


class TestTrimp(unittest.TestCase):
    def test_formule_banister(self):
        d = (140 - 51) / (185 - 51)
        self.assertAlmostEqual(charge.trimp(60, 140, 51, 185),
                               60 * d * 0.64 * math.exp(1.92 * d))

    def test_donnees_insuffisantes(self):
        self.assertEqual(charge.trimp(0, 140, 51, 185), 0.0)
        self.assertEqual(charge.trimp(60, 0, 51, 185), 0.0)
        self.assertEqual(charge.trimp(60, None, 51, 185), 0.0)
        self.assertEqual(charge.trimp(60, 140, 185, 185), 0.0)   # FC réserve nulle

    def test_fraction_bornee(self):
        # FC sous le repos → 0 ; FC au-dessus du max → plafonnée à FC max
        self.assertEqual(charge.trimp(60, 40, 51, 185), 0.0)
        self.assertAlmostEqual(charge.trimp(60, 200, 51, 185), charge.trimp(60, 185, 51, 185))

    def test_croissant_avec_intensite(self):
        vals = [charge.trimp(60, bpm, 51, 185) for bpm in (110, 130, 150, 170)]
        self.assertEqual(vals, sorted(vals))

    def test_echantillons_trou_ignore(self):
        a = hr([(30, 140)])
        b = hr([(30, 140)], t0=a[-1]["ts"] + 3600)   # 1 h de trou
        self.assertAlmostEqual(charge.trimp_echantillons(a + b, 51, 185),
                               2 * charge.trimp_echantillons(a, 51, 185), places=6)

    def test_echantillons_ordre_indifferent(self):
        s = hr([(10, 130), (10, 160)])
        self.assertAlmostEqual(charge.trimp_echantillons(list(reversed(s)), 51, 185),
                               charge.trimp_echantillons(s, 51, 185))

    def test_echantillons_vides(self):
        self.assertEqual(charge.trimp_echantillons([], 51, 185), 0.0)
        self.assertEqual(charge.trimp_echantillons([{"ts": 0, "bpm": 140}], 51, 185), 0.0)


class TestZones(unittest.TestCase):
    def test_bornes_karvonen(self):
        b = zones.zone_bounds(51, 185)
        for v, attendu in zip(b, (131.4, 144.8, 158.2, 171.6)):
            self.assertAlmostEqual(v, attendu)

    def test_libelles(self):
        lim = zones.zone_limits(51, 185)
        self.assertEqual(lim["Z1"], "< 131 bpm")
        self.assertEqual(lim["Z3"], "145–158 bpm")
        self.assertEqual(lim["Z5"], "> 172 bpm")

    def test_zone_aux_bornes(self):
        # bornes 131.4 / 144.8 / 158.2 / 171.6 — les BPM mesurés sont entiers
        self.assertEqual(zones._zone(131, 51, 185), "Z1")
        self.assertEqual(zones._zone(132, 51, 185), "Z2")
        self.assertEqual(zones._zone(171, 51, 185), "Z4")
        self.assertEqual(zones._zone(172, 51, 185), "Z5")
        self.assertEqual(zones._zone(250, 51, 185), "Z5")

    def test_reserve_nulle(self):
        self.assertEqual(zones._zone(150, 185, 185), "Z1")

    def test_detail_sans_fc(self):
        self.assertEqual(sum(zones.zone_times({}, 51, 185).values()), 0)


class TestDrift(unittest.TestCase):
    def test_tiers(self):
        r = drift.analyse(hr([(20, 130), (20, 140), (20, 143)]))
        self.assertAlmostEqual(r["hr_first"], 130, delta=0.5)
        self.assertAlmostEqual(r["hr_mid"], 140, delta=0.5)
        self.assertAlmostEqual(r["hr_last"], 143, delta=0.5)
        self.assertAlmostEqual(r["drift_pct"], 10.0, delta=0.5)
        self.assertEqual(r["hr_min"], 130)
        self.assertEqual(r["hr_max"], 143)
        self.assertAlmostEqual(r["dur_min"], 60, delta=0.1)

    def test_insuffisant(self):
        self.assertEqual(drift.analyse(hr([(1, 140)])[:20]), {})   # < 30 échantillons
        self.assertEqual(drift.analyse(hr([(15, 140)])), {})       # < 20 min

    def test_derive_debut_fin_vide(self):
        self.assertEqual(drift.derive_debut_fin([]), {})

    def test_time_series(self):
        x, raw, smooth = drift.time_series(hr([(1, 100), (1, 200)]), smooth_n=4)
        self.assertEqual(len(x), len(raw))
        self.assertEqual(len(raw), len(smooth))
        self.assertEqual(x[0], 0)
        self.assertAlmostEqual(x[-1], 2.0)
        self.assertEqual(smooth[0], 100)          # loin de la transition
        self.assertTrue(100 < smooth[12] < 200)   # lissé autour de la transition

    def test_time_series_vide(self):
        self.assertEqual(drift.time_series([]), ([], [], []))


if __name__ == "__main__":
    unittest.main()

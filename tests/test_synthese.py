"""Tests synthèse, récupération et persistance locale — python -m unittest

Les modules journal / config / quality écrivent dans le dépôt (journal.json,
sortie-sante/) : chaque test redirige ces chemins vers un dossier temporaire
pour ne jamais toucher aux données réelles.
"""
import json
import math
import os
import shutil
import tempfile
import unittest
from unittest import mock

import pandas as pd

from src import charge, config, journal, quality, recuperation, synthesis


class DossierTemporaire(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        for cible, nom in ((journal, "JOURNAL_PATH"), (config, "PARAMS_PATH")):
            p = mock.patch.object(cible, nom, os.path.join(self.tmp, nom.lower() + ".json"))
            p.start()
            self.addCleanup(p.stop)


def jours(valeurs: dict, n: int = 14) -> pd.DataFrame:
    """DataFrame journalier se terminant aujourd'hui ; valeurs : {col: valeur ou liste}."""
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=n, freq="D")
    return pd.DataFrame({"date": dates, **{k: v if isinstance(v, list) else [v] * n
                                            for k, v in valeurs.items()}})


class TestJournal(DossierTemporaire):
    def test_workout_id(self):
        self.assertEqual(journal.workout_id("2026-10-06", "18:30", "Course"), "2026-10-06_1830_Course")

    def test_vide_sans_fichier(self):
        self.assertEqual(journal.load(), {})
        self.assertIsNone(journal.get_entry("x"))

    def test_save_conserve_created_at(self):
        journal.save_entry("w1", {"rpe": 5})
        cree = journal.get_entry("w1")["created_at"]
        with mock.patch.object(journal, "datetime") as dt:
            dt.now.return_value.isoformat.return_value = "2099-01-01T00:00:00"
            journal.save_entry("w1", {"rpe": 7})
        e = journal.get_entry("w1")
        self.assertEqual((e["rpe"], e["workout_id"]), (7, "w1"))
        self.assertEqual(e["created_at"], cree)
        self.assertEqual(e["updated_at"], "2099-01-01T00:00:00")

    def test_accents_preserves(self):
        journal.save_entry("w1", {"notes": "côte raide, ravito OK"})
        with open(journal.JOURNAL_PATH, encoding="utf-8") as f:
            self.assertIn("côte", f.read())

    def test_seances_sans_entree(self):
        journal.save_entry("2026-10-06_1830_Course", {"rpe": 5})
        wk = pd.DataFrame([{"date": "2026-10-06", "heure": "18:30", "type": "Course"},
                           {"date": "2026-10-07", "heure": "07:00", "type": "Vélo"}])
        manquantes = journal.sessions_missing_entry(wk)
        self.assertEqual([m["type"] for m in manquantes], ["Vélo"])


class TestConfig(DossierTemporaire):
    def test_defauts(self):
        self.assertEqual(config.load(), config.DEFAULTS)
        self.assertIsNot(config.load(), config.DEFAULTS)   # copie, pas l'original

    def test_save_conserve_autres_parametres(self):
        with open(config.PARAMS_PATH, "w") as f:
            json.dump({"race_km": 80}, f)
        config.save(190, 48)
        cfg = config.load()
        self.assertEqual((cfg["fc_max"], cfg["fc_repos"], cfg["race_km"]), (190, 48, 80))

    def test_race(self):
        r = config.race({**config.DEFAULTS, "race_km": 50, "race_dplus_m": 2000})
        self.assertEqual(r["ratio"], 40)
        self.assertEqual(config.race({**config.DEFAULTS, "race_km": 0})["ratio"], 0.0)


class TestQualite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        pd.DataFrame([
            {"date": "2026-10-06", "heure": "18:30", "type": "Course", "duree_min": 60, "fc_moy": 140, "km": 10},
            {"date": "2026-10-06", "heure": "18:35", "type": "Course", "duree_min": 58, "fc_moy": 141, "km": 10},
            {"date": "2026-10-07", "heure": "07:00", "type": "Course", "duree_min": 1, "fc_moy": 250, "km": 95},
        ]).to_csv(os.path.join(self.tmp, "workouts.csv"), sep=";", index=False)
        pd.DataFrame({"date": ["2026-10-06", "2026-10-07"], "hrv": [50, None]}) \
          .to_csv(os.path.join(self.tmp, "daily.csv"), sep=";", index=False)
        pd.DataFrame({"semaine": ["2026-W41", "2026-W42"], "seances": [3, 0]}) \
          .to_csv(os.path.join(self.tmp, "weekly.csv"), sep=";", index=False)

    def test_rapport(self):
        r = quality.generate(self.tmp)
        self.assertEqual(len(r["doublons"]), 1)
        self.assertEqual(r["doublons"][0]["ecart_min"], 5.0)
        self.assertEqual(len(r["suspects"]), 1)
        self.assertEqual(len(r["suspects"][0]["raisons"]), 3)   # durée, FC, distance
        self.assertEqual(r["couverture"]["HRV"], {"jours": 1, "total": 2, "pct": 50.0})
        self.assertEqual(r["semaines_sans_seance"], ["2026-W42"])
        self.assertEqual(quality.load(self.tmp)["doublons"], r["doublons"])

    def test_load_absent(self):
        self.assertIsNone(quality.load(self.tmp))


class TestRecuperation(unittest.TestCase):
    def test_baselines(self):
        b = recuperation.baselines(pd.DataFrame({"hrv": [40, 50, 60, None, 70],
                                                 "sommeil_h": [None] * 5}))
        self.assertEqual(b["hrv"], {"median": 55.0, "p25": 47.5, "p75": 62.5, "n": 4})
        self.assertNotIn("sommeil_h", b)   # colonne vide
        self.assertNotIn("fc_repos", b)    # colonne absente

    def test_rolling_min_periods(self):
        d = recuperation.rolling_weekly(jours({"hrv": [10.0, 20, 30, 40, 50]}, n=5))
        self.assertTrue(d["hrv_r7"].iloc[:2].isna().all())
        self.assertEqual(d["hrv_r7"].iloc[2], 20)
        self.assertEqual(d["hrv_r7"].iloc[4], 30)

    def test_allure_z2z3(self):
        wk = pd.DataFrame([
            {"date": "2026-10-08", "type": "Course", "km": 10, "dplus_m": 50, "allure_min_km": "5:30", "fc_moy": 140, "zone": "Z2"},
            {"date": "2026-10-06", "type": "Course", "km": 8, "dplus_m": 40, "allure_min_km": "6:00", "fc_moy": 138, "zone": "Z3"},
            {"date": "2026-10-07", "type": "Course", "km": 3, "dplus_m": 0, "allure_min_km": "5:00", "fc_moy": 140, "zone": "Z2"},
            {"date": "2026-10-09", "type": "Course", "km": 12, "dplus_m": 0, "allure_min_km": "4:30", "fc_moy": 170, "zone": "Z4"},
            {"date": "2026-10-10", "type": "Vélo", "km": 40, "dplus_m": 0, "allure_min_km": "2:00", "fc_moy": 130, "zone": "Z2"},
        ])
        r = recuperation.pace_z2z3_trend(wk)
        self.assertEqual(list(r["date"]), ["2026-10-06", "2026-10-08"])
        self.assertEqual(list(r["pace_sec"]), [360, 330])


class TestCharge(DossierTemporaire):
    def test_weekly_load(self):
        journal.save_entry("2026-10-06_1830_Course", {"rpe": 6})
        wk = pd.DataFrame([
            {"date": "2026-10-06", "heure": "18:30", "type": "Course", "duree_min": 60, "fc_moy": 140, "semaine": "2026-W41"},
            {"date": "2026-10-08", "heure": "18:30", "type": "Course", "duree_min": 90, "fc_moy": 135, "semaine": "2026-W41"},
            {"date": "2026-10-13", "heure": "18:30", "type": "Renfo", "duree_min": 30, "fc_moy": None, "semaine": "2026-W42"},
        ])
        wl = charge.weekly_load(wk).set_index("semaine")
        cfg = config.DEFAULTS
        attendu = (charge.trimp(60, 140, cfg["fc_repos"], cfg["fc_max"])
                   + charge.trimp(90, 135, cfg["fc_repos"], cfg["fc_max"]))
        self.assertAlmostEqual(wl.loc["2026-W41", "charge_trimp"], attendu)
        self.assertEqual(wl.loc["2026-W41", "charge_rpe"], 360)   # seule la séance notée compte
        self.assertEqual(wl.loc["2026-W41", "n_rpe"], 1)
        self.assertEqual(wl.loc["2026-W41", "sortie_longue"], 90)
        self.assertEqual(wl.loc["2026-W42", "charge_trimp"], 0)
        self.assertTrue(math.isnan(wl.loc["2026-W42", "charge_rpe"]))   # NaN ≠ 0


class TestSynthese(unittest.TestCase):
    BASE = {"hrv": {"median": 50, "p25": 45, "p75": 55},
            "fc_repos": {"median": 50, "p25": 48, "p75": 52},
            "sommeil_h": {"median": 7.5, "p25": 7, "p75": 8}}

    def test_recuperation_verte(self):
        r = synthesis.recovery_block(jours({"hrv": 55, "fc_repos": 49, "sommeil_h": 8}), self.BASE)
        self.assertEqual(r["status"], "green")
        self.assertAlmostEqual(r["hrv_delta_pct"], 10)

    def test_recuperation_orange(self):
        r = synthesis.recovery_block(jours({"hrv": 48, "fc_repos": 49, "sommeil_h": 8}), self.BASE)
        self.assertEqual(r["status"], "orange")
        self.assertIn("HRV légèrement", r["observation"])

    def test_recuperation_rouge(self):
        r = synthesis.recovery_block(jours({"hrv": 50, "fc_repos": 49, "sommeil_h": 5.5}), self.BASE)
        self.assertEqual(r["status"], "red")
        self.assertIn("Sommeil très court", r["observation"])

    def test_recuperation_sans_donnees(self):
        self.assertEqual(synthesis.recovery_block(jours({"hrv": None}), {})["status"], "grey")

    def test_recuperation_ignore_vieux_jours(self):
        # 7 vieux jours catastrophiques + 7 jours récents bons → vert
        d = jours({"hrv": [20] * 7 + [55] * 7, "sommeil_h": [4] * 7 + [8] * 7})
        self.assertEqual(synthesis.recovery_block(d, self.BASE)["status"], "green")

    def test_pmc(self):
        debut = (pd.Timestamp.now().normalize() - pd.Timedelta(days=9)).strftime("%Y-%m-%d")
        wk = pd.DataFrame([{"date": debut, "duree_min": 60, "fc_moy": 140}])
        df = synthesis.pmc_block(wk, config.DEFAULTS)
        self.assertEqual(len(df), 10)                       # jusqu'à aujourd'hui inclus
        t = df["trimp"].iloc[0]
        self.assertAlmostEqual(df["ctl"].iloc[0], t)       # adjust=False : 1re valeur = TRIMP
        self.assertAlmostEqual(df["atl"].iloc[1], t * 6 / 7)
        self.assertAlmostEqual(df["ctl"].iloc[1], t * 41 / 42)
        self.assertTrue((df["tsb"] == df["ctl"] - df["atl"]).all())

    def test_pmc_vide(self):
        wk = pd.DataFrame(columns=["date", "duree_min", "fc_moy"])
        self.assertTrue(synthesis.pmc_block(wk, config.DEFAULTS).empty)


if __name__ == "__main__":
    unittest.main()

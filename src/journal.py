import json
import os
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
JOURNAL_PATH = os.path.join(PROJECT_ROOT, "journal.json")

OBJECTIFS = ["Endurance", "Sortie longue", "Fractionné", "Côtes", "Récupération",
             "Renforcement", "Échauffement", "Compétition", "Loisir", "Autre"]
FACTEURS = ["Aucun", "Souffle", "Jambes", "Énergie", "Douleur", "Digestion", "Terrain"]
TERRAINS = ["Route", "Chemin", "Trail", "Salle", "Piste", "Autre"]
METEOS = ["—", "Beau", "Nuageux", "Pluie", "Vent", "Chaud", "Froid"]

TYPES_COURSE = {"Course", "Rando", "TrailRunning", "Hiking"}

FRONTALES = ["—", "Petite", "Moyenne", "Puissante"]
TOLERANCE_DIGESTIVE = list(range(11))   # 0 (très mauvaise) → 10 (parfaite)

CHAMPS_NUIT = ["sommeil_avant_h", "frontale", "confort_nuit", "notes_nuit"]
CHAMPS_RAVITO = ["aliments", "boissons", "glucides_g_h",
                  "tolerance_digestive", "baisse_energie", "strategie_notes"]


def workout_id(date: str, heure: str, wtype: str) -> str:
    return f"{date}_{heure.replace(':', '')}_{wtype}"


def workout_filename(wid: str) -> str:
    return wid.replace(" ", "_").replace("/", "-")


def load() -> dict:
    if os.path.exists(JOURNAL_PATH):
        with open(JOURNAL_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _write(data: dict):
    with open(JOURNAL_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_entry(wid: str) -> dict | None:
    return load().get(wid)


def save_entry(wid: str, fields: dict):
    data = load()
    now = datetime.now().isoformat(timespec="seconds")
    fields["workout_id"] = wid
    fields["created_at"] = data[wid]["created_at"] if wid in data else now
    fields["updated_at"] = now
    data[wid] = fields
    _write(data)


def sessions_missing_entry(workouts_df) -> list[dict]:
    data = load()
    return [
        row.to_dict()
        for _, row in workouts_df.iterrows()
        if workout_id(str(row["date"]), str(row["heure"]), str(row["type"])) not in data
    ]

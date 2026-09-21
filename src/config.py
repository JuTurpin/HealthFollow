import json
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PARAMS_PATH  = os.path.join(PROJECT_ROOT, "sortie-sante", "params.json")
DEFAULTS     = {"fc_max": 185, "fc_repos": 51}


def load() -> dict:
    if os.path.exists(PARAMS_PATH):
        with open(PARAMS_PATH) as f:
            return {**DEFAULTS, **json.load(f)}
    return DEFAULTS.copy()


def save(fc_max: int, fc_repos: int):
    os.makedirs(os.path.dirname(PARAMS_PATH), exist_ok=True)
    with open(PARAMS_PATH, "w") as f:
        json.dump({"fc_max": fc_max, "fc_repos": fc_repos}, f)

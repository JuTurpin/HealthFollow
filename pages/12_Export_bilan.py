"""Export bilan coach — pack hebdomadaire (digest.md + CSV) à glisser dans la conversation."""
import os
import sys
from datetime import date

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.sidebar import render_import_sidebar, DATA_DIR
from src import bilan_export as be, config, journal, quality, zones
from src.detail_parser import read_progress

st.set_page_config(page_title="Export bilan coach", layout="wide")
st.title("Export bilan coach")

render_import_sidebar()
st.caption(
    "Le filtre « Période d'analyse » de la barre latérale ne s'applique pas à cette page : "
    "l'export lit tout l'historique pour que la tendance 8 semaines soit complète."
)

wk_path     = os.path.join(DATA_DIR, "workouts.csv")
daily_path  = os.path.join(DATA_DIR, "daily.csv")
weekly_path = os.path.join(DATA_DIR, "weekly.csv")
if not os.path.exists(wk_path):
    st.warning("Aucune donnée. Importez un export depuis l'accueil.")
    st.stop()

# Volontairement sans filter_period()
wk     = pd.read_csv(wk_path, sep=";")
daily  = pd.read_csv(daily_path, sep=";") if os.path.exists(daily_path) else pd.DataFrame(columns=["date"])
weekly = pd.read_csv(weekly_path, sep=";") if os.path.exists(weekly_path) else pd.DataFrame(columns=["semaine"])
cfg    = config.load()
race   = config.race(cfg)
today  = date.today()

# ── Sélecteur de semaine ──────────────────────────────────────────────────────
semaines = be.semaines_disponibles(wk, daily, today)
defaut = be.derniere_semaine_complete(today)
lundi = st.selectbox(
    "Semaine", semaines, index=semaines.index(defaut),
    format_func=lambda l: be.libelle_semaine(l, race["date"]),
    help="Par défaut : la dernière semaine complète (lundi → dimanche).",
)
sxx = be.s_moins(lundi, race["date"])

# ── État de la passe 2 ────────────────────────────────────────────────────────
progress = read_progress()
statut_p2 = progress.get("status")
passe2_en_cours = statut_p2 == "running"
passe2_complete = statut_p2 == "done"

if passe2_en_cours:
    st.warning(
        f"Analyse en cours — revenez dans quelques minutes "
        f"({progress.get('done', 0)}/{progress.get('total', '?')} séances détaillées)."
    )
elif statut_p2 == "error":
    st.warning("La passe 2 (FC détaillée / GPS) a échoué : l'export sera partiel "
               "(zones, dérive, splits marqués NA). Réimportez l'export pour la relancer.")
elif not progress:
    st.warning("La passe 2 (FC détaillée / GPS) n'a jamais tourné : l'export sera partiel.")


# ── Chargement des détails nécessaires (fenêtre de calcul seulement) ─────────
@st.cache_data(show_spinner=False)
def _detail(date_s: str, heure: str, wtype: str, _mtime: float) -> dict | None:
    return zones.load_detail(date_s, heure, wtype)


def _mtime(date_s, heure, wtype) -> float:
    from src.detail_parser import workout_filename
    p = os.path.join(zones.DETAILS_DIR, f"{workout_filename(date_s, heure, wtype)}.json")
    return os.path.getmtime(p) if os.path.exists(p) else 0.0


debut, fin = be.periode_calcul(lundi)
fenetre = be.seances_periode(wk, debut, fin)
details = {}
for _, r in fenetre.iterrows():
    args = (str(r["date"]), str(r["heure"]), str(r["type"]))
    d = _detail(*args, _mtime(*args))
    if d is not None:
        details[be.wid_de(r)] = d

# ── Planning (optionnel, lecture seule) ───────────────────────────────────────
planning = st.file_uploader(
    "planning-hebdo.md (optionnel) — active le prévu vs réalisé",
    type=["md", "markdown", "txt"],
    help="Le fichier est seulement lu, jamais modifié ni enregistré.",
)
planning_md = planning.getvalue().decode("utf-8", errors="replace") if planning else None

# ── Construction du pack ──────────────────────────────────────────────────────
qr = quality.load(DATA_DIR)
if qr is None:
    try:
        qr = quality.generate(DATA_DIR)
    except (OSError, KeyError, ValueError):
        qr = None

with st.spinner("Construction du pack…"):
    pack = be.construire_pack(
        lundi, wk, daily, weekly, details, journal.load(), cfg, race,
        quality_report=qr, planning_md=planning_md, passe2_complete=passe2_complete,
    )

if planning_md and "prevu_vs_realise.csv" in pack["fichiers"] \
        and pack["fichiers"]["prevu_vs_realise.csv"].count("\n") <= 1:
    st.warning("Aucun tableau trouvé sous « ## Semaine en cours » dans le planning fourni.")

if pack["sans_journal"]:
    st.warning(
        f"{len(pack['sans_journal'])} séance(s) de la semaine sans entrée dans le journal : "
        + ", ".join(pack["sans_journal"])
    )
    st.page_link("pages/5_Journal.py", label="Compléter dans le Journal", icon="📝")

se = pack["seances"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Séances", len(se))
c2.metric("Avec FC détaillée", f"{int(se['_avec_fc'].sum()) if len(se) else 0}/{len(se)}")
c3.metric("Avec GPS", f"{int(se['_avec_gps'].sum()) if len(se) else 0}/{len(se)}")
c4.metric("Avec journal", f"{int(se['_journal'].sum()) if len(se) else 0}/{len(se)}")

with st.expander("Aperçu du digest.md", expanded=False):
    st.markdown(pack["digest"])

zip_bytes = be.zip_pack(pack["fichiers"])
dossier = os.path.join(DATA_DIR, "bilans", f"S-{sxx:02d}")
nom_zip = f"{pack['nom']}.zip"


def _enregistrer(fichiers: dict, contenu_zip: bytes, dossier: str, nom_zip: str):
    os.makedirs(dossier, exist_ok=True)
    with open(os.path.join(dossier, nom_zip), "wb") as f:
        f.write(contenu_zip)
    for nom, texte in fichiers.items():
        with open(os.path.join(dossier, nom), "w", encoding="utf-8", newline="") as f:
            f.write(texte)
    st.session_state["bilan_enregistre"] = os.path.join(dossier, nom_zip)


st.download_button(
    "Télécharger le pack (.zip)",
    data=zip_bytes, file_name=nom_zip, mime="application/zip",
    type="primary", disabled=passe2_en_cours,
    on_click=_enregistrer, args=(pack["fichiers"], zip_bytes, dossier, nom_zip),
)
st.caption(
    f"{nom_zip} · {len(zip_bytes) / 1024:.0f} ko · "
    + " · ".join(pack["fichiers"].keys())
)
enregistre = st.session_state.get("bilan_enregistre")
if enregistre and os.path.exists(enregistre) and os.path.dirname(enregistre) == dossier:
    st.success(f"Pack enregistré sur le disque : `{enregistre}`")
else:
    st.caption(f"Au téléchargement, le pack est aussi enregistré dans `{dossier}/`.")

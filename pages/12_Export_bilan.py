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

# ── Sélection des semaines (relative à la semaine en cours) ──────────────────
c_dec, c_nb = st.columns(2)
decalage = c_dec.number_input(
    "Dernière semaine exportée (0 = semaine en cours)", min_value=0, max_value=104,
    value=1, step=1,
    help="Nombre de semaines avant la semaine en cours : 0 = semaine en cours, "
         "1 = semaine précédente (dernière semaine complète), 2 = celle d'avant…",
)
nombre = c_nb.number_input(
    "Nombre de semaines", min_value=1, max_value=12, value=1, step=1,
    help="Nombre de semaines exportées, en remontant à partir de la dernière. "
         "Chaque semaine a son propre bilan complet.",
)
lundis = be.semaines_relatives(today, int(decalage), int(nombre))
st.markdown("**Semaines exportées :** " + " · ".join(
    f"`{be.libelle_semaine(l, race['date'])}`" for l in lundis))
if int(decalage) == 0:
    st.info("La semaine en cours n'est pas terminée : son bilan est partiel.")

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


debut, fin = be.periode_calcul(lundis[0])[0], be.periode_calcul(lundis[-1])[1]
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

# Le planning ne décrit qu'une semaine (« Semaine en cours ») : il s'applique à la plus récente
entries = journal.load()
with st.spinner("Construction du pack…"):
    packs = [
        be.construire_pack(
            l, wk, daily, weekly, details, entries, cfg, race, quality_report=qr,
            planning_md=planning_md if l == lundis[-1] else None,
            passe2_complete=passe2_complete,
        )
        for l in lundis
    ]
if planning_md and len(lundis) > 1:
    st.caption(f"Le planning est appliqué à la semaine la plus récente ({packs[-1]['nom']}).")

if planning_md and packs[-1]["fichiers"].get("prevu_vs_realise.csv", "").count("\n") <= 1:
    st.warning("Aucun tableau trouvé sous « ## Semaine en cours » dans le planning fourni.")

sans_journal = [f"{p['nom'].split('_')[1]} · {s}" if len(packs) > 1 else s
                for p in packs for s in p["sans_journal"]]
if sans_journal:
    st.warning(
        f"{len(sans_journal)} séance(s) sans entrée dans le journal : " + ", ".join(sans_journal)
    )
    st.page_link("pages/5_Journal.py", label="Compléter dans le Journal", icon="📝")

se = pd.concat([p["seances"] for p in packs], ignore_index=True)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Séances", len(se))
c2.metric("Avec FC détaillée", f"{int(se['_avec_fc'].sum()) if len(se) else 0}/{len(se)}")
c3.metric("Avec GPS", f"{int(se['_avec_gps'].sum()) if len(se) else 0}/{len(se)}")
c4.metric("Avec journal", f"{int(se['_journal'].sum()) if len(se) else 0}/{len(se)}")

for p in packs:
    titre = "Aperçu du digest.md" + (f" — {p['nom']}" if len(packs) > 1 else "")
    with st.expander(titre, expanded=False):
        st.markdown(p["digest"])

fichiers = be.fichiers_multi(packs)
zip_bytes = be.zip_pack(fichiers)
nom_zip = f"{be.nom_multi(packs)}.zip"
bilans_dir = os.path.join(DATA_DIR, "bilans")
dossiers = [os.path.join(bilans_dir, p["nom"].split("_")[1]) for p in packs]   # bilans/S-XX


def _enregistrer(packs: list, contenu_zip: bytes, dossiers: list, nom_zip: str):
    for p, dossier in zip(packs, dossiers):
        os.makedirs(dossier, exist_ok=True)
        with open(os.path.join(dossier, f"{p['nom']}.zip"), "wb") as f:
            f.write(be.zip_pack(p["fichiers"]))
        for nom, texte in p["fichiers"].items():
            with open(os.path.join(dossier, nom), "w", encoding="utf-8", newline="") as f:
                f.write(texte)
    chemin = os.path.join(dossiers[0], nom_zip)
    if len(packs) > 1:   # zip groupé à côté des dossiers par semaine
        chemin = os.path.join(os.path.dirname(dossiers[0]), nom_zip)
        with open(chemin, "wb") as f:
            f.write(contenu_zip)
    st.session_state["bilan_enregistre"] = {"zip": chemin, "dossiers": dossiers}


st.download_button(
    "Télécharger le pack (.zip)",
    data=zip_bytes, file_name=nom_zip, mime="application/zip",
    type="primary", disabled=passe2_en_cours,
    on_click=_enregistrer, args=(packs, zip_bytes, dossiers, nom_zip),
)
st.caption(
    f"{nom_zip} · {len(zip_bytes) / 1024:.0f} ko · "
    + (" · ".join(fichiers.keys()) if len(packs) == 1
       else f"{len(packs)} dossiers ({', '.join(p['nom'] for p in packs)})")
)
enregistre = st.session_state.get("bilan_enregistre")
if enregistre and enregistre.get("dossiers") == dossiers and os.path.exists(enregistre["zip"]):
    st.success("Pack enregistré sur le disque : `" + enregistre["zip"] + "`"
               + ("" if len(packs) == 1 else
                  " (détail par semaine dans " + ", ".join(f"`{d}/`" for d in dossiers) + ")"))
else:
    st.caption("Au téléchargement, le pack est aussi enregistré dans "
               + ", ".join(f"`{d}/`" for d in dossiers) + ".")

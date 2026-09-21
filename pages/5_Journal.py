import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.sidebar import render_import_sidebar, DATA_DIR, filter_period
from src import journal
st.set_page_config(page_title="Journal", layout="wide")
st.title("Journal des séances")

render_import_sidebar()

workouts_path = os.path.join(DATA_DIR, "workouts.csv")
if not os.path.exists(workouts_path):
    st.warning("Aucune donnée. Importez un export depuis l'accueil.")
    st.stop()

wk = filter_period(pd.read_csv(workouts_path, sep=";"))
wk["date"] = pd.to_datetime(wk["date"])
wk_sorted = wk.sort_values("date", ascending=False).reset_index(drop=True)

all_entries = journal.load()

# ── Filtres ────────────────────────────────────────────────────────────────────
col_f1, col_f2, col_f3 = st.columns(3)
filter_status = col_f1.selectbox("Statut", ["Toutes", "Sans entrée", "Renseignées"])
types_dispo   = ["Tous"] + sorted(wk["type"].unique().tolist())
filter_type   = col_f2.selectbox("Type", types_dispo)
filter_search = col_f3.text_input("Recherche (notes, douleurs…)", placeholder="genou, fatigue…")

# Applique les filtres
df = wk_sorted.copy()
if filter_type != "Tous":
    df = df[df["type"] == filter_type]

wids = [journal.workout_id(str(r["date"].date()), str(r["heure"]), str(r["type"])) for _, r in df.iterrows()]
has_entry = [w in all_entries for w in wids]

if filter_status == "Sans entrée":
    df = df[[h is False for h in has_entry]].reset_index(drop=True)
    wids = [w for w, h in zip(wids, has_entry) if not h]
elif filter_status == "Renseignées":
    df = df[[h is True for h in has_entry]].reset_index(drop=True)
    wids = [w for w, h in zip(wids, has_entry) if h]

if filter_search:
    q = filter_search.lower()
    mask = []
    for wid in wids:
        entry = all_entries.get(wid, {})
        text = " ".join(str(v) for v in [entry.get("notes", ""), entry.get("douleurs", ""),
                                          entry.get("facteur_limitant", ""), entry.get("objectif", "")])
        mask.append(q in text.lower())
    df = df[[m for m in mask]].reset_index(drop=True) if len(mask) == len(df) else df
    wids = [w for w, m in zip(wids, mask) if m]

n_total   = len(wk)
n_remplis = sum(1 for _, r in wk.iterrows()
                if journal.workout_id(str(r["date"].date() if hasattr(r["date"], "date") else r["date"]),
                                      str(r["heure"]), str(r["type"])) in all_entries)
st.caption(f"{n_remplis}/{n_total} séances renseignées ({100*n_remplis//n_total if n_total else 0} %)")

st.divider()

# ── Liste des séances ─────────────────────────────────────────────────────────
if df.empty:
    st.info("Aucune séance ne correspond aux filtres.")
    st.stop()

for idx, (_, row) in enumerate(df.iterrows()):
    if idx >= len(wids):
        break
    wid   = wids[idx]
    entry = all_entries.get(wid)

    date_str = row["date"].strftime("%a %d/%m/%Y") if hasattr(row["date"], "strftime") else str(row["date"])
    label    = f"{date_str} {row['heure']} — **{row['type']}**"
    if pd.notna(row.get("duree_min")):
        label += f" — {row['duree_min']:.0f} min"
    if pd.notna(row.get("km")):
        label += f" — {float(row['km']):.1f} km"
    if entry:
        rpe = entry.get("rpe")
        label += f" — RPE {rpe}/10" if rpe is not None else ""
    badge = "✓" if entry else "○"

    with st.expander(f"{badge} {label}", expanded=False):
        is_run  = str(row["type"]) in journal.TYPES_COURSE
        is_long = pd.notna(row.get("duree_min")) and float(row["duree_min"]) > 90
        is_nuit = str(row.get("nocturne", "")) == "oui"

        with st.form(key=f"form_{wid}"):
            c1, c2 = st.columns(2)
            objectif = c1.selectbox(
                "Objectif", journal.OBJECTIFS,
                index=journal.OBJECTIFS.index(entry["objectif"])
                      if entry and entry.get("objectif") in journal.OBJECTIFS else 0,
                key=f"o_{wid}",
            )
            rpe = c2.select_slider(
                "RPE (0–10)", options=list(range(11)),
                value=entry.get("rpe", 5) if entry else 5,
                key=f"r_{wid}",
            )

            c3, c4 = st.columns(2)
            facteur = c3.selectbox(
                "Facteur limitant", journal.FACTEURS,
                index=journal.FACTEURS.index(entry["facteur_limitant"])
                      if entry and entry.get("facteur_limitant") in journal.FACTEURS else 0,
                key=f"f_{wid}",
            )
            terrain_val = entry.get("terrain") if entry else None
            terrain = c4.selectbox(
                "Terrain", journal.TERRAINS,
                index=journal.TERRAINS.index(terrain_val)
                      if terrain_val in journal.TERRAINS else 0,
                key=f"t_{wid}",
            ) if is_run else None

            meteo_val = entry.get("meteo") if entry else "—"
            meteo = st.selectbox(
                "Météo", journal.METEOS,
                index=journal.METEOS.index(meteo_val)
                      if meteo_val in journal.METEOS else 0,
                key=f"m_{wid}",
            )

            douleurs = st.text_input(
                "Douleurs (localisation + intensité 0–10)",
                value=entry.get("douleurs", "") if entry else "",
                key=f"d_{wid}",
                placeholder="ex : genou droit — 3/10",
            )

            if is_long:
                cl1, cl2 = st.columns(2)
                fatigue_j1 = cl1.select_slider(
                    "Fatigue J+1 (0–10)", options=list(range(11)),
                    value=entry.get("fatigue_j1") or 0 if entry else 0,
                    key=f"fj1_{wid}",
                )
                jambes_j1 = cl2.select_slider(
                    "État jambes J+1 (0–10)", options=list(range(11)),
                    value=entry.get("jambes_j1") or 0 if entry else 0,
                    key=f"jj1_{wid}",
                )
            else:
                fatigue_j1 = jambes_j1 = None

            notes = st.text_area(
                "Notes", value=entry.get("notes", "") if entry else "",
                key=f"n_{wid}", height=80,
            )

            # ── Nuit & ravitaillement (séances nocturnes uniquement) ──────────
            sommeil_avant_h = frontale = confort_nuit = notes_nuit = None
            aliments = boissons = strategie_notes = None
            glucides_g_h = None
            tolerance_dig = None
            baisse_energie = None

            if is_nuit:
                st.markdown("**Conditions nuit**")
                cn1, cn2, cn3 = st.columns(3)
                sommeil_avant_h = cn1.number_input(
                    "Sommeil avant (h)", min_value=0.0, max_value=24.0, step=0.5,
                    value=float(entry.get("sommeil_avant_h") or 0) if entry else 0.0,
                    key=f"sah_{wid}",
                )
                frontale_val = entry.get("frontale", "—") if entry else "—"
                frontale = cn2.selectbox(
                    "Frontale", journal.FRONTALES,
                    index=journal.FRONTALES.index(frontale_val)
                          if frontale_val in journal.FRONTALES else 0,
                    key=f"fr_{wid}",
                )
                confort_nuit = cn3.select_slider(
                    "Confort nuit (0–10)", options=list(range(11)),
                    value=entry.get("confort_nuit") or 5 if entry else 5,
                    key=f"cn_{wid}",
                )
                notes_nuit = st.text_input(
                    "Notes nuit", value=entry.get("notes_nuit", "") if entry else "",
                    key=f"nn_{wid}", placeholder="visibilité, froid, navigation…",
                )

                st.markdown("**Ravitaillement**")
                cr1, cr2, cr3 = st.columns(3)
                aliments = cr1.text_input(
                    "Aliments", value=entry.get("aliments", "") if entry else "",
                    key=f"al_{wid}", placeholder="gels, barres, fruit sec…",
                )
                boissons = cr2.text_input(
                    "Boissons", value=entry.get("boissons", "") if entry else "",
                    key=f"bo_{wid}", placeholder="eau, boisson isotonique…",
                )
                glucides_g_h = cr3.number_input(
                    "Glucides (g/h)", min_value=0, max_value=200, step=5,
                    value=int(entry.get("glucides_g_h") or 0) if entry else 0,
                    key=f"gu_{wid}",
                )
                cr4, cr5 = st.columns(2)
                tolerance_dig = cr4.select_slider(
                    "Tolérance digestive (0–10)", options=list(range(11)),
                    value=entry.get("tolerance_digestive") or 7 if entry else 7,
                    key=f"td_{wid}",
                )
                baisse_energie = cr5.checkbox(
                    "Baisse d'énergie ressentie",
                    value=bool(entry.get("baisse_energie")) if entry else False,
                    key=f"be_{wid}",
                )
                strategie_notes = st.text_input(
                    "Notes stratégie ravito",
                    value=entry.get("strategie_notes", "") if entry else "",
                    key=f"sn_{wid}",
                )

            if st.form_submit_button("Enregistrer", type="primary"):
                fields = {
                    "date": str(row["date"].date() if hasattr(row["date"], "date") else row["date"]),
                    "heure": str(row["heure"]), "type": str(row["type"]),
                    "objectif": objectif, "rpe": rpe,
                    "facteur_limitant": facteur, "douleurs": douleurs,
                    "terrain": terrain, "meteo": meteo,
                    "fatigue_j1": fatigue_j1, "jambes_j1": jambes_j1,
                    "notes": notes,
                }
                if is_nuit:
                    fields.update({
                        "sommeil_avant_h": sommeil_avant_h or None,
                        "frontale": frontale if frontale != "—" else None,
                        "confort_nuit": confort_nuit,
                        "notes_nuit": notes_nuit or None,
                        "aliments": aliments or None,
                        "boissons": boissons or None,
                        "glucides_g_h": glucides_g_h or None,
                        "tolerance_digestive": tolerance_dig,
                        "baisse_energie": baisse_energie,
                        "strategie_notes": strategie_notes or None,
                    })
                journal.save_entry(wid, fields)
                st.success("Entrée sauvegardée.")
                st.rerun()

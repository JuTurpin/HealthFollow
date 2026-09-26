import os
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.sidebar import render_import_sidebar, DATA_DIR, filter_period
from src.help_texts import chart_header
from src.help_texts import H_VOL_CHARGE, H_CHARGE_HEB, H_REPARTITION
from src import charge, config

st.set_page_config(page_title="Charge & Régularité", layout="wide")
st.title("Charge & Régularité")

render_import_sidebar()

wk_path     = os.path.join(DATA_DIR, "workouts.csv")
weekly_path = os.path.join(DATA_DIR, "weekly.csv")
if not os.path.exists(wk_path):
    st.warning("Aucune donnée. Importez un export depuis l'accueil.")
    st.stop()

workouts = filter_period(pd.read_csv(wk_path,     sep=";"))
weekly   = filter_period(pd.read_csv(weekly_path, sep=";"), col="lundi")
cfg      = config.load()

weekly_sel = weekly[weekly["seances"] > 0].copy()
wk_sel     = workouts.copy()
load_df     = charge.weekly_load(wk_sel)
merged      = weekly_sel.merge(load_df, on="semaine", how="left")

# ── KPIs ─────────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Semaines avec séances", len(weekly_sel))
c2.metric("km course total", f"{weekly_sel['km_course'].sum():.0f}")
c3.metric("D+ total", f"{weekly_sel['dplus_m'].sum():.0f} m")
c4.metric("TRIMP total", f"{merged['charge_trimp'].sum():.0f}")
n_rpe = int(merged["n_rpe"].sum()) if "n_rpe" in merged else 0
n_tot = len(wk_sel)
c5.metric("RPE renseigné", f"{n_rpe}/{n_tot} séances")

st.divider()

# ── Volume & charge côte à côte ───────────────────────────────────────────────
col_vol, col_charge = st.columns(2)

with col_vol:
    chart_header("Volume hebdomadaire", H_VOL_CHARGE)
    fig = go.Figure()
    fig.add_bar(x=weekly_sel["semaine"], y=weekly_sel["km_course"],
                name="km course", marker_color="#0068c9")
    fig.add_scatter(x=weekly_sel["semaine"],
                    y=weekly_sel["temps_total_min"] / 60,
                    name="Temps total (h)", mode="lines+markers",
                    yaxis="y2", line=dict(color="#f39c12", width=2))
    fig.update_layout(
        yaxis=dict(title="km course"),
        yaxis2=dict(title="h", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=1.1),
        height=320, margin=dict(t=10, b=0),
    )
    st.plotly_chart(fig, width="stretch")

with col_charge:
    chart_header("Charge hebdomadaire", H_CHARGE_HEB)
    fig2 = go.Figure()
    fig2.add_bar(x=merged["semaine"], y=merged["charge_trimp"],
                 name="TRIMP (FC)", marker_color="#3498db", opacity=0.85)
    rpe_vals = merged["charge_rpe"].dropna()
    if not rpe_vals.empty:
        fig2.add_scatter(x=merged["semaine"], y=merged["charge_rpe"],
                         name="Charge RPE (dur × RPE)", mode="markers",
                         marker=dict(size=9, color="#e74c3c", symbol="diamond"))
    fig2.update_layout(
        yaxis_title="TRIMP / Charge RPE",
        legend=dict(orientation="h", y=1.1),
        height=320, margin=dict(t=10, b=0),
    )
    st.plotly_chart(fig2, width="stretch")

# ── Répartition des types d'activités ────────────────────────────────────────
chart_header("Répartition par type d'activité (temps en min)", H_REPARTITION)
type_week = (
    wk_sel.groupby(["semaine", "type"])["duree_min"]
    .sum()
    .reset_index()
)
if not type_week.empty:
    fig3 = px.bar(type_week, x="semaine", y="duree_min", color="type",
                  labels={"duree_min": "Minutes", "semaine": "Semaine", "type": "Type"},
                  color_discrete_sequence=px.colors.qualitative.Set2)
    fig3.update_layout(height=300, margin=dict(t=10, b=0),
                       legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig3, width="stretch")

# ── Tableau récapitulatif ─────────────────────────────────────────────────────
st.subheader("Tableau de bord par semaine")

def fmt_h(min_val):
    if pd.isna(min_val) or min_val == 0:
        return "—"
    h, m = divmod(int(min_val), 60)
    return f"{h}h{m:02d}" if h else f"{m}min"

table = merged[[
    "semaine", "s_moins", "km_course", "dplus_m", "seances",
    "sorties_nocturnes", "sortie_longue", "charge_trimp", "charge_rpe",
    "fc_repos_moy", "hrv_moy", "sommeil_moy_h",
]].copy()
table["sortie_longue"] = table["sortie_longue"].apply(fmt_h)
table["charge_trimp"]  = table["charge_trimp"].apply(lambda x: f"{x:.0f}" if pd.notna(x) and x > 0 else "—")
table["charge_rpe"]    = table["charge_rpe"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "—")
table = table.rename(columns={
    "semaine": "Semaine", "s_moins": "S−", "km_course": "km course",
    "dplus_m": "D+ (m)", "seances": "Séances", "sorties_nocturnes": "Nuit",
    "sortie_longue": "+ longue", "charge_trimp": "TRIMP",
    "charge_rpe": "Charge RPE", "fc_repos_moy": "FC repos",
    "hrv_moy": "HRV", "sommeil_moy_h": "Sommeil (h)",
})
st.dataframe(
    table.sort_values("Semaine", ascending=False),
    width="stretch", hide_index=True,
)

st.caption(
    f"TRIMP : méthode Banister (FC max {cfg['fc_max']} bpm, FC repos {cfg['fc_repos']} bpm). "
    "Charge RPE : durée (min) × RPE — disponible uniquement pour les séances renseignées dans Journal."
)

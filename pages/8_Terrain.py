"""Préparation terrain — D+, ratio ascensionnel, progression vers SaintExpress."""
import os
import sys
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.sidebar import render_import_sidebar, DATA_DIR, filter_period
from src.help_texts import chart_header
from src.help_texts import H_DPLUS_HEB, H_RATIO_DPLUS, H_SORTIE_LONGUE

st.set_page_config(page_title="Terrain", layout="wide")
st.title("Préparation terrain")

render_import_sidebar()

wk_path     = os.path.join(DATA_DIR, "workouts.csv")
weekly_path = os.path.join(DATA_DIR, "weekly.csv")
if not os.path.exists(wk_path):
    st.warning("Aucune donnée. Importez un export depuis l'accueil.")
    st.stop()

wk     = filter_period(pd.read_csv(wk_path,     sep=";"))
weekly = filter_period(pd.read_csv(weekly_path, sep=";"), col="lundi")

TYPES_COURSE = {"Course", "Rando", "TrailRunning", "Hiking"}

# ── Paramètres course ─────────────────────────────────────────────────────────
with st.expander("Paramètres SaintExpress", expanded=False):
    c1, c2, c3 = st.columns(3)
    race_km    = c1.number_input("Distance course (km)",   value=45.0, step=0.5)
    race_dplus = c2.number_input("D+ cible (m)",           value=1200, step=50)
    race_date  = c3.date_input("Date de départ",           value=date(2026, 11, 28))

race_ratio = race_dplus / race_km  # m D+/km cible

st.divider()

# ── KPIs globaux ──────────────────────────────────────────────────────────────
runs = wk[wk["type"].isin(TYPES_COURSE)].copy()
runs["dplus_m"] = pd.to_numeric(runs["dplus_m"], errors="coerce").fillna(0)
runs["km"]      = pd.to_numeric(runs["km"],      errors="coerce")

total_dplus = runs["dplus_m"].sum()
total_km    = runs["km"].sum(skipna=True)
jours_rest  = (race_date - date.today()).days

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("D+ total accumulé",    f"{total_dplus:,.0f} m")
c2.metric("km course totaux",     f"{total_km:.0f} km")
c3.metric("Ratio D+/km global",   f"{total_dplus/total_km:.1f} m/km" if total_km > 0 else "—",
          delta=f"Cible {race_ratio:.1f} m/km")
c4.metric("Jours avant la course", jours_rest)
c5.metric("Séances course/rando",  len(runs))

st.divider()

# ── D+ hebdomadaire (course/rando) ────────────────────────────────────────────
chart_header("D+ hebdomadaire — course & rando", H_DPLUS_HEB)

weekly_active = weekly[weekly["seances"] > 0].copy()
weekly_active["dplus_m"] = pd.to_numeric(weekly_active["dplus_m"], errors="coerce").fillna(0)
weekly_active["km_course"] = pd.to_numeric(weekly_active["km_course"], errors="coerce").fillna(0)
weekly_active["ratio_dplus_km"] = (
    weekly_active["dplus_m"] / weekly_active["km_course"]
).replace([float("inf")], 0).fillna(0)

# N'afficher que les semaines avec km_course > 0
w_run = weekly_active[weekly_active["km_course"] > 0].tail(24)

fig = go.Figure()
fig.add_bar(x=w_run["semaine"], y=w_run["dplus_m"],
            name="D+ (m)", marker_color="#e74c3c", opacity=0.8)
fig.add_scatter(x=w_run["semaine"], y=w_run["km_course"],
                name="km course", mode="lines+markers",
                yaxis="y2", line=dict(color="#0068c9", width=2))
fig.update_layout(
    yaxis=dict(title="D+ (m)"),
    yaxis2=dict(title="km course", overlaying="y", side="right", showgrid=False),
    legend=dict(orientation="h", y=1.1),
    height=320, margin=dict(t=10, b=0),
)
st.plotly_chart(fig, use_container_width=True)

# ── Ratio D+/km vs cible course ───────────────────────────────────────────────
chart_header(f"Ratio D+/km par semaine vs cible course ({race_ratio:.1f} m/km)", H_RATIO_DPLUS)
fig2 = go.Figure()
fig2.add_bar(
    x=w_run["semaine"], y=w_run["ratio_dplus_km"],
    marker_color=[
        "#2ecc71" if v >= race_ratio * 0.8
        else ("#f39c12" if v >= race_ratio * 0.4 else "#bdc3c7")
        for v in w_run["ratio_dplus_km"]
    ],
    name="D+/km",
)
fig2.add_hline(y=race_ratio, line_dash="dash", line_color="#e74c3c",
               annotation_text=f"Cible {race_ratio:.1f} m/km", annotation_position="top right")
fig2.update_layout(height=260, margin=dict(t=10, b=0), yaxis_title="m D+/km", showlegend=False)
st.plotly_chart(fig2, use_container_width=True)

# ── Progression de la sortie longue ──────────────────────────────────────────
chart_header("Progression de la sortie longue (course/rando)", H_SORTIE_LONGUE)

# Sortie la plus longue par semaine
runs["semaine"] = runs["semaine"].astype(str)
longue_sem = (
    runs.sort_values("km", ascending=False)
        .groupby("semaine")
        .first()
        .reset_index()[["semaine", "km", "dplus_m", "duree_min"]]
)
longue_sem = longue_sem[longue_sem["semaine"].isin(w_run["semaine"])].copy()
longue_sem["km"] = pd.to_numeric(longue_sem["km"], errors="coerce").fillna(0)

fig3 = go.Figure()
fig3.add_bar(x=longue_sem["semaine"], y=longue_sem["km"],
             name="km", marker_color="#0068c9", opacity=0.8)
fig3.add_scatter(x=longue_sem["semaine"], y=longue_sem["dplus_m"],
                 name="D+", mode="lines+markers",
                 yaxis="y2", line=dict(color="#e74c3c", width=2))
fig3.add_hline(y=race_km, line_dash="dot", line_color="#0068c9",
               annotation_text=f"Race {race_km:.0f} km", annotation_position="top right")
fig3.update_layout(
    yaxis=dict(title="km"),
    yaxis2=dict(title="D+ (m)", overlaying="y", side="right", showgrid=False),
    legend=dict(orientation="h", y=1.1),
    height=300, margin=dict(t=10, b=0),
)
st.plotly_chart(fig3, use_container_width=True)

# ── Top séances D+ ────────────────────────────────────────────────────────────
st.subheader("Séances avec le plus de D+")
top_dplus = (
    runs[runs["dplus_m"] > 0]
    .sort_values("dplus_m", ascending=False)
    .head(15)[["date", "heure", "type", "duree_min", "km", "dplus_m",
               "allure_min_km", "fc_moy", "zone"]]
)
if top_dplus.empty:
    st.info("Aucune séance avec D+ enregistré.")
else:
    st.dataframe(top_dplus, use_container_width=True, hide_index=True)

# ── Note GPS ─────────────────────────────────────────────────────────────────
st.caption(
    "Le D+ provient des métadonnées Apple Health (baromètre Apple Watch). "
    "Séances sans D+ enregistré : source externe (TennisKeeper, Zwift, etc.) "
    "ou activité sans dénivelé."
)

import os
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.sidebar import render_import_sidebar, DATA_DIR, filter_period
from src import config, zones
from src.help_texts import chart_header
from src.help_texts import H_VOL_HRV, H_ZONES_TOTAL, H_ZONES_SEM, H_PROGRESSION_COURSE

st.set_page_config(page_title="Activité", layout="wide")
st.title("Activité physique")

render_import_sidebar()

workouts_path = os.path.join(DATA_DIR, "workouts.csv")
weekly_path   = os.path.join(DATA_DIR, "weekly.csv")
if not os.path.exists(workouts_path):
    st.warning("Aucune donnée. Importez un export depuis l'accueil.")
    st.stop()

wk     = filter_period(pd.read_csv(workouts_path, sep=";"))
wk["date"] = pd.to_datetime(wk["date"])
weekly = filter_period(pd.read_csv(weekly_path, sep=";"), col="lundi")
cfg    = config.load()

# ── Volume hebdomadaire ───────────────────────────────────────────────────────
chart_header("Volume hebdomadaire", H_VOL_HRV)
weekly_actif = weekly[weekly["seances"] > 0]
fig = go.Figure()
fig.add_bar(x=weekly_actif["semaine"], y=weekly_actif["km_course"],
            name="km course", marker_color="#0068c9")
fig.add_scatter(x=weekly_actif["semaine"], y=weekly_actif["hrv_moy"],
                name="HRV", mode="lines+markers",
                yaxis="y2", line=dict(color="#ff7f0e", width=2))
fig.update_layout(
    yaxis=dict(title="km course"),
    yaxis2=dict(title="HRV", overlaying="y", side="right", showgrid=False),
    legend=dict(orientation="h", y=1.1),
    height=320, margin=dict(t=10, b=0),
)
st.plotly_chart(fig, use_container_width=True)

col1, col2 = st.columns(2)

# ── Répartition par type ──────────────────────────────────────────────────────
with col1:
    st.subheader("Répartition par type")
    by_type = wk.groupby("type")["duree_min"].sum().reset_index()
    fig2 = px.pie(by_type, names="type", values="duree_min",
                  color_discrete_sequence=px.colors.qualitative.Set2)
    fig2.update_layout(height=320, margin=dict(t=20, b=0))
    st.plotly_chart(fig2, use_container_width=True)

# ── Temps réels en zones (FC horodatée) ───────────────────────────────────────
with col2:
    chart_header("Zones FC réelles", H_ZONES_TOTAL)

    @st.cache_data(show_spinner="Calcul des zones…")
    def _zone_data(wk_hash: str):
        return zones.zones_for_workouts(wk, cfg["fc_repos"], cfg["fc_max"])

    zone_rows = _zone_data(str(len(wk)) + wk["date"].astype(str).sum())
    limits    = zones.zone_limits(cfg["fc_repos"], cfg["fc_max"])

    if not zone_rows:
        st.info("Analyse de détail en cours — revenez dans quelques minutes.")
    else:
        zdf = pd.DataFrame(zone_rows)
        totaux = {z: zdf[z].sum() for z in zones.ZONE_NAMES}
        total  = sum(totaux.values())
        coverage = len(zdf)

        fig3 = go.Figure(go.Bar(
            x=zones.ZONE_NAMES,
            y=[totaux[z] for z in zones.ZONE_NAMES],
            marker_color=[zones.ZONE_COLORS[z] for z in zones.ZONE_NAMES],
            text=[f"{totaux[z]:.0f} min" for z in zones.ZONE_NAMES],
            textposition="outside",
        ))
        fig3.update_layout(height=300, margin=dict(t=30, b=0), showlegend=False,
                           yaxis_title="Minutes totales")
        st.plotly_chart(fig3, use_container_width=True)
        st.caption(
            f"{coverage}/{len(wk)} séances avec FC détaillée. "
            + " · ".join(f"{z} {v}" for z, v in limits.items())
        )

# ── Zones par semaine (stacked bar) ──────────────────────────────────────────
if zone_rows:
    chart_header("Temps en zones par semaine (FC horodatée)", H_ZONES_SEM)
    zdf_sem = pd.DataFrame(zone_rows).groupby("semaine")[zones.ZONE_NAMES].sum().reset_index()
    # Filtre sur les semaines avec activité
    zdf_sem = zdf_sem[zdf_sem["semaine"].isin(weekly_actif["semaine"])]

    fig5 = go.Figure()
    for z in zones.ZONE_NAMES:
        fig5.add_bar(x=zdf_sem["semaine"], y=zdf_sem[z],
                     name=z, marker_color=zones.ZONE_COLORS[z])
    fig5.update_layout(
        barmode="stack", height=300, margin=dict(t=10, b=0),
        yaxis_title="Minutes", legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig5, use_container_width=True)

# ── Progression course ────────────────────────────────────────────────────────
courses = wk[wk["type"] == "Course"].copy()
if not courses.empty:
    chart_header("Progression course — allure vs FC moy", H_PROGRESSION_COURSE)
    courses["pace_sec"] = courses["allure_min_km"].apply(
        lambda x: int(str(x).split(":")[0]) * 60 + int(str(x).split(":")[1])
        if isinstance(x, str) and ":" in str(x) else None
    )
    fig4 = go.Figure()
    fig4.add_scatter(
        x=courses["date"], y=courses["pace_sec"],
        mode="markers+lines", name="Allure (s/km)",
        marker=dict(size=7, color=courses["fc_moy"],
                    colorscale="RdYlGn_r", showscale=True,
                    colorbar=dict(title="FC moy")),
        line=dict(color="rgba(0,0,0,0.15)"),
    )
    fig4.update_yaxes(
        autorange="reversed",
        tickvals=[300, 360, 420, 480, 540, 600],
        ticktext=["5:00", "6:00", "7:00", "8:00", "9:00", "10:00"],
    )
    fig4.update_layout(height=320, margin=dict(t=10, b=0),
                       xaxis_title="Date", yaxis_title="Allure (min/km)")
    st.plotly_chart(fig4, use_container_width=True)

# ── Tableau séances ───────────────────────────────────────────────────────────
st.subheader("Toutes les séances")
cols = ["date", "heure", "type", "duree_min", "km", "dplus_m",
        "allure_min_km", "vitesse_km_h", "fc_moy", "fc_max", "zone", "kcal", "nocturne"]
st.dataframe(wk[cols].sort_values("date", ascending=False),
             use_container_width=True, hide_index=True)

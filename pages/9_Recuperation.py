"""Récupération croisée — HRV, FC repos, sommeil, charge, ressenti."""
import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.sidebar import render_import_sidebar, DATA_DIR, filter_period
from src import recuperation, charge, config
from src.help_texts import chart_header
from src.help_texts import H_HRV_ROLL, H_SOMMEIL_ROLL, H_CHARGE_HRV, H_RPE_HEB, H_DRIFT_LONG

st.set_page_config(page_title="Récupération", layout="wide")
st.title("Récupération")

render_import_sidebar()

daily_path   = os.path.join(DATA_DIR, "daily.csv")
weekly_path  = os.path.join(DATA_DIR, "weekly.csv")
wk_path      = os.path.join(DATA_DIR, "workouts.csv")

if not os.path.exists(daily_path):
    st.warning("Aucune donnée. Importez un export depuis l'accueil.")
    st.stop()

daily_full = pd.read_csv(daily_path, sep=";")
daily_full["date"] = pd.to_datetime(daily_full["date"])
for col in ["hrv", "fc_repos", "sommeil_h"]:
    if col in daily_full.columns:
        daily_full[col] = pd.to_numeric(daily_full[col], errors="coerce")

# Données filtrées sur la période sélectionnée dans la sidebar
daily  = filter_period(daily_full.copy())
weekly = filter_period(pd.read_csv(weekly_path, sep=";"), col="lundi")
wk     = filter_period(pd.read_csv(wk_path,     sep=";"))
cfg    = config.load()

# ── Baselines personnelles (calculées sur l'historique complet) ────────────────
st.subheader("Références personnelles (historique complet)")
bases = recuperation.baselines(daily_full)

if not bases:
    st.info("Données insuffisantes pour calculer les références (HRV, FC repos, sommeil).")
else:
    cols = st.columns(len(bases))
    labels = {"hrv": "HRV (ms)", "fc_repos": "FC repos (bpm)", "sommeil_h": "Sommeil (h)"}
    for i, (col_name, stats) in enumerate(bases.items()):
        lbl = labels.get(col_name, col_name)
        cols[i].metric(
            lbl,
            f"{stats['median']}",
            help=f"P25 : {stats['p25']} · P75 : {stats['p75']} · n={stats['n']}",
        )
        cols[i].caption(f"P25 {stats['p25']} — P75 {stats['p75']}  ({stats['n']} jours)")

st.divider()

# ── Moyennes glissantes 7 j ────────────────────────────────────────────────────
daily_roll = recuperation.rolling_weekly(daily.copy())

chart_header("HRV et FC de repos — moyennes glissantes 7 j", H_HRV_ROLL)

hrv_avail = "hrv_r7" in daily_roll.columns and daily_roll["hrv_r7"].notna().any()
fc_avail  = "fc_repos_r7" in daily_roll.columns and daily_roll["fc_repos_r7"].notna().any()

if not hrv_avail and not fc_avail:
    st.info("Pas assez de données HRV / FC repos sur la période sélectionnée.")
else:
    fig = go.Figure()
    if hrv_avail:
        fig.add_scatter(
            x=daily_roll["date"], y=daily_roll["hrv"],
            mode="markers", name="HRV brut",
            marker=dict(color="rgba(255,127,14,0.25)", size=4),
        )
        fig.add_scatter(
            x=daily_roll["date"], y=daily_roll["hrv_r7"],
            mode="lines", name="HRV moy 7 j",
            line=dict(color="#ff7f0e", width=2),
        )
        if bases.get("hrv"):
            fig.add_hline(
                y=bases["hrv"]["median"], line_dash="dot", line_color="#ff7f0e",
                annotation_text=f"Référence {bases['hrv']['median']}", opacity=0.6,
            )
    if fc_avail:
        fig.add_scatter(
            x=daily_roll["date"], y=daily_roll["fc_repos"],
            mode="markers", name="FC repos brut",
            marker=dict(color="rgba(214,39,40,0.2)", size=4),
            yaxis="y2",
        )
        fig.add_scatter(
            x=daily_roll["date"], y=daily_roll["fc_repos_r7"],
            mode="lines", name="FC repos moy 7 j",
            line=dict(color="#d62728", width=2),
            yaxis="y2",
        )
        if bases.get("fc_repos"):
            fig.add_hline(
                y=bases["fc_repos"]["median"], line_dash="dot", line_color="#d62728",
                opacity=0.6, yref="y2",
                annotation_text=f"Réf {bases['fc_repos']['median']}",
            )
    fig.update_layout(
        yaxis=dict(title="HRV (ms)"),
        yaxis2=dict(title="FC repos (bpm)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=1.1),
        height=320, margin=dict(t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Sommeil ────────────────────────────────────────────────────────────────────
chart_header("Sommeil — moyenne glissante 7 j", H_SOMMEIL_ROLL)

if "sommeil_h_r7" not in daily_roll.columns or daily_roll["sommeil_h_r7"].notna().sum() < 3:
    st.info("Données sommeil insuffisantes sur la période.")
else:
    fig_s = go.Figure()
    fig_s.add_bar(
        x=daily_roll["date"], y=daily_roll["sommeil_h"],
        name="Sommeil nuit", marker_color="rgba(31,119,180,0.25)",
    )
    fig_s.add_scatter(
        x=daily_roll["date"], y=daily_roll["sommeil_h_r7"],
        mode="lines", name="Moy 7 j",
        line=dict(color="#1f77b4", width=2),
    )
    if bases.get("sommeil_h"):
        fig_s.add_hline(
            y=bases["sommeil_h"]["median"], line_dash="dot", line_color="#1f77b4",
            annotation_text=f"Réf {bases['sommeil_h']['median']} h", opacity=0.6,
        )
    fig_s.update_layout(
        height=260, margin=dict(t=10, b=0),
        yaxis_title="Heures",
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_s, use_container_width=True)

st.divider()

# ── Charge TRIMP + HRV hebdo ───────────────────────────────────────────────────
chart_header("Charge TRIMP vs HRV hebdo", H_CHARGE_HRV)

wk_load = charge.weekly_load(wk)
wk_hrv  = weekly[weekly["hrv_moy"].notna()][["semaine", "hrv_moy"]].copy()
wk_hrv["hrv_moy"] = pd.to_numeric(wk_hrv["hrv_moy"], errors="coerce")

merged = pd.merge(wk_load, wk_hrv, on="semaine", how="left")
merged = merged[merged["charge_trimp"] > 0]

if merged.empty:
    st.info("Données insuffisantes pour croiser charge et HRV.")
else:
    fig_c = go.Figure()
    fig_c.add_bar(
        x=merged["semaine"], y=merged["charge_trimp"],
        name="Charge TRIMP", marker_color="rgba(214,39,40,0.6)",
    )
    fig_c.add_scatter(
        x=merged["semaine"], y=merged["hrv_moy"],
        mode="lines+markers", name="HRV moy (semaine)",
        yaxis="y2", line=dict(color="#ff7f0e", width=2),
        marker=dict(size=6),
    )
    if bases.get("hrv"):
        fig_c.add_hline(
            y=bases["hrv"]["median"], line_dash="dot", line_color="#ff7f0e",
            opacity=0.5, yref="y2",
        )
    fig_c.update_layout(
        yaxis=dict(title="Charge TRIMP"),
        yaxis2=dict(title="HRV (ms)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=1.1),
        height=300, margin=dict(t=10, b=0),
    )
    st.plotly_chart(fig_c, use_container_width=True)

st.divider()

# ── RPE hebdo ──────────────────────────────────────────────────────────────────
chart_header("RPE hebdomadaire", H_RPE_HEB)

rpe_df = recuperation.weekly_rpe(wk)
rpe_df = rpe_df[rpe_df["n_rpe"] > 0]

if rpe_df.empty:
    st.info("Aucune donnée RPE dans le journal pour la période sélectionnée.")
else:
    fig_r = go.Figure()
    fig_r.add_bar(
        x=rpe_df["semaine"], y=rpe_df["rpe_moy"],
        marker_color=[
            "#2ecc71" if v <= 5 else ("#f39c12" if v <= 7 else "#e74c3c")
            for v in rpe_df["rpe_moy"]
        ],
        text=[f"{v:.1f} ({int(n)} séances)" for v, n in zip(rpe_df["rpe_moy"], rpe_df["n_rpe"])],
        textposition="outside",
        name="RPE moy",
    )
    fig_r.update_layout(
        height=240, margin=dict(t=10, b=0),
        yaxis=dict(title="RPE moyen", range=[0, 11]),
        showlegend=False,
    )
    st.plotly_chart(fig_r, use_container_width=True)

st.divider()

# ── Drift sorties longues ──────────────────────────────────────────────────────
chart_header("Drift cardiaque — sorties longues (> 60 min Course/Rando)", H_DRIFT_LONG)

@st.cache_data(show_spinner="Calcul des drifts…")
def _drifts(n: int):
    return recuperation.long_run_drifts(wk)

drifts_df = _drifts(len(wk))

if drifts_df.empty:
    st.info("Aucune sortie longue avec données FC suffisantes (> 60 min, min 30 samples, min 20 min de données).")
else:
    from src.sidebar import get_date_cutoff as _cutoff
    _co = _cutoff()
    if _co:
        drifts_df = drifts_df[drifts_df["date"] >= _co.strftime("%Y-%m-%d")]
    drifts_df = drifts_df.sort_values("date")

    if drifts_df.empty:
        st.info("Aucune sortie longue avec drift calculable sur la période.")
    else:
        fig_d = go.Figure()
        colors = [
            "#2ecc71" if abs(v) < 5 else ("#f39c12" if abs(v) < 10 else "#e74c3c")
            for v in drifts_df["drift_pct"]
        ]
        fig_d.add_bar(
            x=drifts_df["date"], y=drifts_df["drift_pct"],
            marker_color=colors, name="Drift %",
            text=[f"{v:+.1f}%" for v in drifts_df["drift_pct"]],
            textposition="outside",
        )
        fig_d.add_hline(y=0, line_color="gray", line_dash="dot")
        fig_d.add_hrect(y0=-5, y1=5, fillcolor="#2ecc71", opacity=0.07, line_width=0,
                        annotation_text="bonne tenue (<5%)", annotation_position="top right")
        fig_d.update_layout(
            height=280, margin=dict(t=10, b=0),
            yaxis_title="Drift %  (positif = fatigue)",
            showlegend=False,
        )
        st.plotly_chart(fig_d, use_container_width=True)

        detail_cols = ["date", "type", "duree_min", "km", "dplus_m",
                       "fc_moy", "hr_first", "hr_last", "drift_pct", "dur_min"]
        avail = [c for c in detail_cols if c in drifts_df.columns]
        st.dataframe(
            drifts_df[avail].sort_values("date", ascending=False),
            use_container_width=True, hide_index=True,
        )

st.caption(
    "HRV mesurée par Apple Watch (SDNN). FC repos = 1ère mesure matinale. "
    "Sommeil = durée totale nuit (données santé iPhone). "
    "Drift positif = la FC monte au fil de la séance (fatigue ou chaleur)."
)

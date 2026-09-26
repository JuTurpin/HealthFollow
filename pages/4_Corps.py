import os
import sys
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.sidebar import render_import_sidebar, DATA_DIR, filter_period
from src.help_texts import chart_header
from src.help_texts import H_POIDS, H_VO2

st.set_page_config(page_title="Corps", layout="wide")
st.title("Corps & métriques biologiques")

render_import_sidebar()

daily_path = os.path.join(DATA_DIR, "daily.csv")
if not os.path.exists(daily_path):
    st.warning("Aucune donnée. Importez un export depuis l'accueil.")
    st.stop()

daily = filter_period(pd.read_csv(daily_path, sep=";", parse_dates=["date"]))

# ── Poids ────────────────────────────────────────────────────────────────────
if "poids" in daily.columns and daily["poids"].notna().any():
    chart_header("Poids", H_POIDS)
    poids = daily.dropna(subset=["poids"])
    fig = go.Figure()
    fig.add_scatter(x=poids["date"], y=poids["poids"], mode="markers+lines",
                    name="Poids (kg)", line=dict(color="#0068c9"),
                    marker=dict(size=5))
    # Moyenne mobile 7j
    poids["ma7"] = poids["poids"].rolling(7, min_periods=1).mean()
    fig.add_scatter(x=poids["date"], y=poids["ma7"], mode="lines",
                    name="Moy. 7j", line=dict(color="#e74c3c", dash="dash", width=2))
    fig.update_layout(height=300, margin=dict(t=10, b=0),
                      yaxis_title="kg", legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, width="stretch")

    col1, col2, col3 = st.columns(3)
    col1.metric("Poids actuel", f"{poids['poids'].iloc[-1]:.1f} kg")
    delta = poids["poids"].iloc[-1] - poids["poids"].iloc[0]
    col2.metric("Évolution (période)", f"{delta:+.1f} kg")
    col3.metric("Min / Max", f"{poids['poids'].min():.1f} / {poids['poids'].max():.1f} kg")
else:
    st.info("Aucune donnée de poids dans cet export.")

st.divider()

col1, col2 = st.columns(2)

# ── VO2max ───────────────────────────────────────────────────────────────────
with col1:
    if "vo2max" in daily.columns and daily["vo2max"].notna().any():
        chart_header("VO2max", H_VO2)
        vo2 = daily.dropna(subset=["vo2max"])
        fig2 = px.line(vo2, x="date", y="vo2max",
                       labels={"vo2max": "mL/kg/min", "date": "Date"},
                       color_discrete_sequence=["#2ecc71"])
        fig2.update_layout(height=260, margin=dict(t=10, b=0))
        st.plotly_chart(fig2, width="stretch")
        st.metric("VO2max actuel", f"{vo2['vo2max'].iloc[-1]:.1f} mL/kg/min")
    else:
        st.info("Pas de données VO2max.")

# ── Masse grasse ─────────────────────────────────────────────────────────────
with col2:
    if "masse_grasse" in daily.columns and daily["masse_grasse"].notna().any():
        st.subheader("Masse grasse")
        mg = daily.dropna(subset=["masse_grasse"])
        mg["masse_grasse_pct"] = mg["masse_grasse"] * 100
        fig3 = px.line(mg, x="date", y="masse_grasse_pct",
                       labels={"masse_grasse_pct": "%", "date": "Date"},
                       color_discrete_sequence=["#f39c12"])
        fig3.update_layout(height=260, margin=dict(t=10, b=0))
        st.plotly_chart(fig3, width="stretch")
        st.metric("Masse grasse actuelle", f"{mg['masse_grasse_pct'].iloc[-1]:.1f} %")
    else:
        st.info("Pas de données masse grasse.")

# ── Tableau journalier ───────────────────────────────────────────────────────
st.subheader("Données journalières")
display_cols = [c for c in ["date", "poids", "masse_grasse", "masse_maigre", "vo2max",
                             "fc_repos", "hrv", "sommeil_h", "freq_resp", "fc_marche"]
                if c in daily.columns]
st.dataframe(
    daily[display_cols].sort_values("date", ascending=False).head(30),
    width="stretch", hide_index=True,
)

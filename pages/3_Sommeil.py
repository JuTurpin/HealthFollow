import os
import sys
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.sidebar import render_import_sidebar, DATA_DIR, filter_period
from src.help_texts import chart_header
from src.help_texts import H_SOMMEIL_NUIT, H_SOMMEIL_HEB, H_SOMMEIL_CORR

st.set_page_config(page_title="Sommeil", layout="wide")
st.title("Sommeil")

render_import_sidebar()

daily_path = os.path.join(DATA_DIR, "daily.csv")
weekly_path = os.path.join(DATA_DIR, "weekly.csv")
if not os.path.exists(daily_path):
    st.warning("Aucune donnée. Importez un export depuis l'accueil.")
    st.stop()

daily  = filter_period(pd.read_csv(daily_path,  sep=";", parse_dates=["date"]))
weekly = filter_period(pd.read_csv(weekly_path, sep=";"), col="lundi")

if "sommeil_h" not in daily.columns or daily["sommeil_h"].isna().all():
    st.info("Aucune donnée de sommeil dans cet export.")
    st.stop()

sleep = daily.dropna(subset=["sommeil_h"])

# ── Durée nuit par nuit ───────────────────────────────────────────────────────
chart_header("Durée de sommeil", H_SOMMEIL_NUIT)
fig = px.bar(sleep, x="date", y="sommeil_h",
             labels={"sommeil_h": "Heures", "date": "Nuit"},
             color="sommeil_h",
             color_continuous_scale=["#e74c3c", "#f39c12", "#2ecc71"],
             range_color=[5, 9])
fig.add_hline(y=7.5, line_dash="dot", line_color="gray", annotation_text="7h30 cible")
fig.update_layout(height=320, margin=dict(t=10, b=0), coloraxis_showscale=False)
st.plotly_chart(fig, width="stretch")

col1, col2 = st.columns(2)

# ── KPIs ────────────────────────────────────────────────────────────────────
with col1:
    moy = sleep["sommeil_h"].mean()
    moy_7d = sleep.tail(7)["sommeil_h"].mean()
    pct_ok = (sleep["sommeil_h"] >= 7).mean() * 100
    st.metric("Sommeil moyen", f"{moy:.1f} h", delta=f"{moy_7d - moy:+.1f} h (7j)")
    st.metric("Nuits ≥ 7h", f"{pct_ok:.0f} %")

# ── Sommeil hebdomadaire ──────────────────────────────────────────────────────
with col2:
    chart_header("Moyenne hebdomadaire", H_SOMMEIL_HEB)
    wk_sleep = weekly[["semaine", "sommeil_moy_h"]].dropna()
    if not wk_sleep.empty:
        fig2 = px.bar(wk_sleep, x="semaine", y="sommeil_moy_h",
                      color="sommeil_moy_h", color_continuous_scale=["#e74c3c", "#f39c12", "#2ecc71"],
                      range_color=[5, 9],
                      labels={"sommeil_moy_h": "h/nuit", "semaine": "Semaine"})
        fig2.add_hline(y=7.5, line_dash="dot", line_color="gray")
        fig2.update_layout(height=280, margin=dict(t=10, b=0), coloraxis_showscale=False)
        st.plotly_chart(fig2, width="stretch")

# ── Corrélation sommeil / HRV ──────────────────────────────────────────────
if "hrv" in daily.columns:
    chart_header("Corrélation sommeil → HRV (lendemain)", H_SOMMEIL_CORR)
    merged = daily[["date", "sommeil_h", "hrv"]].dropna()
    merged["hrv_j1"] = merged["hrv"].shift(-1)
    merged = merged.dropna(subset=["hrv_j1"])
    if len(merged) >= 5:
        import numpy as np
        x_vals = merged["sommeil_h"].values
        y_vals = merged["hrv_j1"].values
        coef   = np.polyfit(x_vals, y_vals, 1)
        x_line = np.linspace(x_vals.min(), x_vals.max(), 50)
        y_line = coef[0] * x_line + coef[1]

        fig3 = go.Figure()
        fig3.add_scatter(
            x=x_vals, y=y_vals,
            mode="markers", name="Observations",
            marker=dict(color="#0068c9", size=6, opacity=0.6),
        )
        fig3.add_scatter(
            x=x_line, y=y_line,
            mode="lines", name="Tendance",
            line=dict(color="#e74c3c", width=2, dash="dash"),
        )
        fig3.update_layout(
            height=300, margin=dict(t=10, b=0),
            xaxis_title="Sommeil nuit J (h)", yaxis_title="HRV lendemain (ms)",
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig3, width="stretch")
    else:
        st.caption("Pas assez de points pour la corrélation.")

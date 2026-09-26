import os
import sys
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.sidebar import render_import_sidebar, DATA_DIR, filter_period
from src.help_texts import chart_header
from src.help_texts import H_HRV_FC, H_HRV_BOX, H_FC_SEANCE

st.set_page_config(page_title="Cardiaque", layout="wide")
st.title("Cardiaque")

render_import_sidebar()

daily_path = os.path.join(DATA_DIR, "daily.csv")
workouts_path = os.path.join(DATA_DIR, "workouts.csv")
if not os.path.exists(daily_path):
    st.warning("Aucune donnée. Importez un export depuis l'accueil.")
    st.stop()

daily = filter_period(pd.read_csv(daily_path, sep=";", parse_dates=["date"]))
wk    = filter_period(pd.read_csv(workouts_path, sep=";"))

# ── HRV + FC repos ───────────────────────────────────────────────────────────
chart_header("HRV & FC de repos", H_HRV_FC)
fig = go.Figure()
if "hrv" in daily.columns:
    fig.add_scatter(x=daily["date"], y=daily["hrv"], mode="lines+markers",
                    name="HRV (ms)", line=dict(color="#0068c9", width=2),
                    marker=dict(size=4))
if "fc_repos" in daily.columns:
    fig.add_scatter(x=daily["date"], y=daily["fc_repos"], mode="lines+markers",
                    name="FC repos (bpm)", yaxis="y2",
                    line=dict(color="#e74c3c", width=2, dash="dot"),
                    marker=dict(size=4))

fig.update_layout(
    yaxis=dict(title="HRV (ms)", rangemode="tozero"),
    yaxis2=dict(title="FC repos (bpm)", overlaying="y", side="right", showgrid=False),
    legend=dict(orientation="h", y=1.1),
    height=350, margin=dict(t=10, b=0),
)
st.plotly_chart(fig, width="stretch")

col1, col2 = st.columns(2)

# ── KPIs ─────────────────────────────────────────────────────────────────────
with col1:
    d = daily.dropna(subset=["hrv"]) if "hrv" in daily.columns else pd.DataFrame()
    hrv_mean = d["hrv"].mean() if not d.empty else None
    hrv_7d = d.tail(7)["hrv"].mean() if not d.empty else None
    d2 = daily.dropna(subset=["fc_repos"]) if "fc_repos" in daily.columns else pd.DataFrame()
    fc_mean = d2["fc_repos"].mean() if not d2.empty else None

    st.metric("HRV moy. (période)", f"{hrv_mean:.0f} ms" if hrv_mean else "—",
              delta=f"{hrv_7d - hrv_mean:+.0f} ms (7j)" if hrv_mean and hrv_7d else None)
    st.metric("FC repos moy.", f"{fc_mean:.0f} bpm" if fc_mean else "—")

# ── HRV par semaine (boxplot) ─────────────────────────────────────────────────
with col2:
    if "hrv" in daily.columns:
        chart_header("HRV hebdomadaire", H_HRV_BOX)
        daily["semaine"] = daily["date"].dt.isocalendar().week.astype(str).str.zfill(2)
        daily["annee"] = daily["date"].dt.isocalendar().year.astype(str)
        daily["sem_label"] = daily["annee"] + "-W" + daily["semaine"]
        fig2 = px.box(daily.dropna(subset=["hrv"]), x="sem_label", y="hrv",
                      labels={"sem_label": "Semaine", "hrv": "HRV (ms)"},
                      color_discrete_sequence=["#0068c9"])
        fig2.update_layout(height=280, margin=dict(t=10, b=0))
        st.plotly_chart(fig2, width="stretch")

# ── FC moy séances ────────────────────────────────────────────────────────────
if "fc_moy" in wk.columns:
    chart_header("FC moyenne par séance", H_FC_SEANCE)
    wk["date"] = pd.to_datetime(wk["date"])
    wk_hr = wk.dropna(subset=["fc_moy"])
    if not wk_hr.empty:
        zone_colors = {"Z1": "#2ecc71", "Z2": "#3498db", "Z3": "#f39c12",
                       "Z4": "#e74c3c", "Z5": "#8e44ad"}
        fig3 = px.scatter(wk_hr, x="date", y="fc_moy", color="zone",
                          size="duree_min", hover_data=["type", "duree_min", "km"],
                          color_discrete_map=zone_colors,
                          labels={"fc_moy": "FC moy (bpm)", "date": "Date"})
        fig3.update_layout(height=300, margin=dict(t=10, b=0))
        st.plotly_chart(fig3, width="stretch")

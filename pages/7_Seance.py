"""Fiche séance — FC horodatée, zones réelles, drift cardiaque, comparables."""
import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.sidebar import render_import_sidebar, DATA_DIR, filter_period
from src import config, zones, drift, journal
from src.help_texts import chart_header
from src.help_texts import H_FC_TEMPS, H_ZONES_SEANCE, H_DRIFT

st.set_page_config(page_title="Fiche séance", layout="wide")
st.title("Fiche séance")

render_import_sidebar()

wk_path = os.path.join(DATA_DIR, "workouts.csv")
if not os.path.exists(wk_path):
    st.warning("Aucune donnée. Importez un export depuis l'accueil.")
    st.stop()

wk  = filter_period(pd.read_csv(wk_path, sep=";"))
cfg = config.load()

# ── Sélecteur ────────────────────────────────────────────────────────────────
col_f1, col_f2 = st.columns([1, 3])
types_dispo = ["Tous"] + sorted(wk["type"].unique())
filtre_type = col_f1.selectbox("Type", types_dispo)

wk_sel = wk if filtre_type == "Tous" else wk[wk["type"] == filtre_type]
wk_sel = wk_sel.sort_values("date", ascending=False).reset_index(drop=True)

def _label(row):
    lbl = f"{row['date']}  {row['heure']}  —  {row['type']}"
    if pd.notna(row.get("duree_min")):
        lbl += f"  {row['duree_min']:.0f} min"
    if pd.notna(row.get("km")):
        lbl += f"  {float(row['km']):.1f} km"
    if pd.notna(row.get("fc_moy")):
        lbl += f"  FC {row['fc_moy']:.0f}"
    return lbl

idx = col_f2.selectbox("Séance", range(len(wk_sel)),
                       format_func=lambda i: _label(wk_sel.iloc[i]))
row = wk_sel.iloc[idx]

# ── Chargement données de détail ──────────────────────────────────────────────
detail = zones.load_detail(str(row["date"]), str(row["heure"]), str(row["type"]))

# ── En-tête séance ───────────────────────────────────────────────────────────
st.divider()
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Date",       f"{row['date']}  {row['heure']}")
c2.metric("Type",       row["type"])
c3.metric("Durée",      f"{row['duree_min']:.0f} min" if pd.notna(row.get("duree_min")) else "—")
c4.metric("Distance",   f"{float(row['km']):.1f} km"  if pd.notna(row.get("km"))        else "—")
c5.metric("D+",         f"{int(row['dplus_m'])} m"    if pd.notna(row.get("dplus_m")) and row["dplus_m"] > 0 else "—")
c6.metric("FC moy",     f"{row['fc_moy']:.0f} bpm"    if pd.notna(row.get("fc_moy"))    else "—")

if detail is None or detail.get("hr_count", 0) < 10:
    st.info("Données FC horodatées non disponibles pour cette séance "
            "(source externe ou analyse incomplète).")
else:
    samples = detail["hr_samples"]
    x, raw, smooth = drift.time_series(samples, smooth_n=60)
    zt = zones.zone_times(detail, cfg["fc_repos"], cfg["fc_max"])

    # ── FC temps réel ─────────────────────────────────────────────────────────
    chart_header("Fréquence cardiaque au fil du temps", H_FC_TEMPS)
    limits = zones.zone_limits(cfg["fc_repos"], cfg["fc_max"])

    # Bandes de zones en arrière-plan
    zone_bpm_bounds = []
    fcr = cfg["fc_max"] - cfg["fc_repos"]
    for b in [0.0, 0.60, 0.70, 0.80, 0.90, 1.20]:
        zone_bpm_bounds.append(cfg["fc_repos"] + b * fcr)

    fig = go.Figure()
    for i, z in enumerate(zones.ZONE_NAMES):
        fig.add_hrect(
            y0=zone_bpm_bounds[i], y1=zone_bpm_bounds[i + 1],
            fillcolor=zones.ZONE_COLORS[z], opacity=0.07, line_width=0,
            annotation_text=z, annotation_position="left",
        )
    fig.add_scatter(x=x, y=raw,    mode="lines", name="FC brute",
                    line=dict(color="rgba(52,152,219,0.3)", width=1))
    fig.add_scatter(x=x, y=smooth, mode="lines", name="FC lissée (5 min)",
                    line=dict(color="#0068c9", width=2))

    # Marques des tiers si session longue
    dur_total = x[-1] if x else 0
    if dur_total > 20:
        for t in [dur_total / 3, 2 * dur_total / 3]:
            fig.add_vline(x=t, line_dash="dot", line_color="gray", opacity=0.5)

    fig.update_layout(
        height=320, margin=dict(t=10, b=0),
        xaxis_title="Minutes depuis le début",
        yaxis_title="bpm",
        legend=dict(orientation="h", y=1.08),
        yaxis=dict(range=[40, max(raw) + 10]),
    )
    st.plotly_chart(fig, width="stretch")

    # ── Zones réelles + drift ────────────────────────────────────────────────
    col_z, col_d = st.columns(2)

    with col_z:
        chart_header("Zones FC réelles", H_ZONES_SEANCE)
        total_z = sum(zt.values())
        if total_z > 0:
            fig2 = go.Figure(go.Bar(
                x=zones.ZONE_NAMES,
                y=[zt[z] for z in zones.ZONE_NAMES],
                marker_color=[zones.ZONE_COLORS[z] for z in zones.ZONE_NAMES],
                text=[f"{zt[z]:.0f} min ({100*zt[z]/total_z:.0f}%)" for z in zones.ZONE_NAMES],
                textposition="outside",
            ))
            fig2.update_layout(height=260, margin=dict(t=30, b=0),
                               showlegend=False, yaxis_title="Minutes")
            st.plotly_chart(fig2, width="stretch")
            st.caption(" · ".join(f"{z} {v}" for z, v in limits.items()))

    with col_d:
        drift_res = drift.analyse(samples)
        if drift_res:
            chart_header("Drift cardiaque (3 tiers)", H_DRIFT)
            tiers   = ["1er tiers", "2e tiers", "3e tiers"]
            vals    = [drift_res["hr_first"], drift_res.get("hr_mid"), drift_res["hr_last"]]
            colors  = ["#2ecc71", "#f39c12", "#e74c3c"]
            fig3 = go.Figure(go.Bar(
                x=tiers,
                y=[v for v in vals if v is not None],
                marker_color=colors[:len([v for v in vals if v is not None])],
                text=[f"{v:.0f} bpm" for v in vals if v is not None],
                textposition="outside",
            ))
            fig3.update_layout(height=260, margin=dict(t=30, b=0),
                               showlegend=False, yaxis_title="FC moy (bpm)")
            st.plotly_chart(fig3, width="stretch")

            drift_pct = drift_res["drift_pct"]
            color_drift = "normal" if abs(drift_pct) < 5 else ("inverse" if drift_pct > 0 else "off")
            st.metric(
                "Drift cardiaque",
                f"{drift_pct:+.1f} %",
                delta="bonne tenue" if abs(drift_pct) < 5
                      else ("fatigue accumulée" if drift_pct > 0 else "échauffement progressif"),
                delta_color=color_drift,
            )
            st.caption(
                f"FC globale {drift_res['hr_global']:.0f} bpm · "
                f"min {drift_res['hr_min']} · max {drift_res['hr_max']} · "
                f"{drift_res['dur_min']:.0f} min de données"
            )
        else:
            st.subheader("Drift cardiaque")
            st.info("Session trop courte pour l'analyse de drift (minimum 20 min de données FC).")

# ── Journal de la séance ──────────────────────────────────────────────────────
st.divider()
st.subheader("Journal")
wid   = journal.workout_id(str(row["date"]), str(row["heure"]), str(row["type"]))
entry = journal.get_entry(wid)
if entry:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Objectif",         entry.get("objectif", "—"))
    c2.metric("RPE",              f"{entry.get('rpe', '—')}/10")
    c3.metric("Facteur limitant", entry.get("facteur_limitant", "—"))
    c4.metric("Terrain",          entry.get("terrain") or "—")
    if entry.get("douleurs"):
        st.caption(f"Douleurs : {entry['douleurs']}")
    if entry.get("notes"):
        st.caption(f"Notes : {entry['notes']}")
    st.caption("→ Modifier dans la page **Journal**")
else:
    st.info("Aucune entrée journal pour cette séance — rendez-vous dans la page **Journal**.")

# ── Séances comparables ───────────────────────────────────────────────────────
st.divider()
st.subheader("Séances comparables")

same_type = wk[wk["type"] == row["type"]].copy()
same_type = same_type[same_type["date"] != str(row["date"])]

# Similarité par durée (±25%) ou distance (±25%)
km_ref  = float(row["km"])  if pd.notna(row.get("km"))       else None
dur_ref = float(row["duree_min"]) if pd.notna(row.get("duree_min")) else None

if km_ref:
    same_type = same_type[
        same_type["km"].apply(lambda x: abs(float(x) - km_ref) / km_ref < 0.30 if pd.notna(x) else False)
    ]
elif dur_ref:
    same_type = same_type[
        same_type["duree_min"].apply(lambda x: abs(float(x) - dur_ref) / dur_ref < 0.25 if pd.notna(x) else False)
    ]

if same_type.empty:
    st.info(f"Aucune séance {row['type']} comparable trouvée (même durée ±25% ou distance ±30%).")
else:
    # Enrichit avec journal RPE
    entries = journal.load()
    def _rpe(r):
        wid_ = journal.workout_id(str(r["date"]), str(r["heure"]), str(r["type"]))
        return entries.get(wid_, {}).get("rpe")
    same_type["RPE"] = same_type.apply(_rpe, axis=1)

    display = same_type[[
        "date", "heure", "duree_min", "km", "dplus_m",
        "allure_min_km", "fc_moy", "zone", "RPE",
    ]].sort_values("date", ascending=False)
    st.dataframe(display, width="stretch", hide_index=True)
    st.caption(f"{len(same_type)} séance(s) {row['type']} avec distance/durée comparable.")

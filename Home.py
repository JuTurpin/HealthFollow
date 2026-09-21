import os
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from src.sidebar import render_import_sidebar, DATA_DIR, filter_period, get_date_cutoff
from src import recuperation, synthesis
from src import journal, detail_parser
from src.help_texts import chart_header, H_PMC

st.set_page_config(page_title="Santé Dashboard", layout="wide")

render_import_sidebar()

# ── Formulaire journal post-import ───────────────────────────────────────────
pending = st.session_state.get("pending_journal")
if pending:
    MAX_DISPLAY = 10
    shown = pending[-MAX_DISPLAY:]  # les plus récentes en premier
    overflow = len(pending) - len(shown)

    st.title("Nouvelles séances à renseigner")
    st.caption(
        f"{len(pending)} séance(s) sans entrée journal."
        + (f" Affichage des {MAX_DISPLAY} plus récentes — les autres sont disponibles dans **Journal**." if overflow else "")
    )

    entries_to_save = {}

    for row in reversed(shown):  # chronologique, du plus récent au plus ancien
        wid  = journal.workout_id(str(row["date"]), str(row["heure"]), str(row["type"]))
        label = f"{row['date']} {row['heure']} — {row['type']}"
        if pd.notna(row.get("duree_min")):
            label += f" — {row['duree_min']:.0f} min"
        if pd.notna(row.get("km")):
            label += f" — {float(row['km']):.1f} km"
        if pd.notna(row.get("fc_moy")):
            label += f" — FC {row['fc_moy']:.0f} bpm"

        with st.expander(label, expanded=False):
            is_run  = str(row["type"]) in journal.TYPES_COURSE
            is_long = pd.notna(row.get("duree_min")) and float(row["duree_min"]) > 90

            c1, c2 = st.columns(2)
            objectif = c1.selectbox("Objectif", journal.OBJECTIFS, key=f"obj_{wid}")
            rpe      = c2.select_slider("RPE (0–10)", options=list(range(11)), key=f"rpe_{wid}")

            c3, c4 = st.columns(2)
            facteur = c3.selectbox("Facteur limitant", journal.FACTEURS, key=f"fac_{wid}")
            terrain = c4.selectbox("Terrain", journal.TERRAINS, key=f"ter_{wid}") if is_run else None
            meteo   = c4.selectbox("Météo", journal.METEOS, key=f"met_{wid}") if not is_run else \
                      st.columns(2)[1].selectbox("Météo", journal.METEOS, key=f"met_{wid}")

            douleurs = ""
            if facteur == "Douleur":
                douleurs = st.text_input("Douleurs (localisation + intensité 0–10)",
                                         key=f"doul_{wid}", placeholder="ex : genou droit — 3/10")

            if is_long:
                st.caption("Sortie longue — fatigue J+1 à compléter demain si besoin (modifiable dans Journal)")
                cl1, cl2 = st.columns(2)
                fatigue_j1 = cl1.select_slider("Fatigue J+1", options=list(range(11)), key=f"fatj1_{wid}")
                jambes_j1  = cl2.select_slider("État jambes J+1", options=list(range(11)), key=f"jamj1_{wid}")
            else:
                fatigue_j1 = jambes_j1 = None

            notes = st.text_area("Notes libres", key=f"notes_{wid}", height=68)

            entries_to_save[wid] = {
                "date": str(row["date"]), "heure": str(row["heure"]), "type": str(row["type"]),
                "objectif": objectif, "rpe": rpe,
                "facteur_limitant": facteur, "douleurs": douleurs,
                "terrain": terrain, "meteo": meteo,
                "fatigue_j1": fatigue_j1, "jambes_j1": jambes_j1,
                "notes": notes,
            }

    col_btn1, col_btn2 = st.columns([1, 5])
    if col_btn1.button("Enregistrer", type="primary"):
        for wid, fields in entries_to_save.items():
            journal.save_entry(wid, fields)
        del st.session_state["pending_journal"]
        st.rerun()
    if col_btn2.button("Passer — remplir plus tard dans Journal"):
        del st.session_state["pending_journal"]
        st.rerun()

    st.stop()

# ── Dashboard ────────────────────────────────────────────────────────────────
st.title("Santé — Dashboard personnel")

if not os.path.exists(os.path.join(DATA_DIR, "workouts.csv")):
    st.info("Importez un export Apple Health pour démarrer.")
    st.stop()

workouts      = filter_period(pd.read_csv(os.path.join(DATA_DIR, "workouts.csv"), sep=";"))
daily         = filter_period(pd.read_csv(os.path.join(DATA_DIR, "daily.csv"),    sep=";", parse_dates=["date"]))
weekly        = filter_period(pd.read_csv(os.path.join(DATA_DIR, "weekly.csv"),   sep=";"), col="lundi")
daily_full    = pd.read_csv(os.path.join(DATA_DIR, "daily.csv"),    sep=";", parse_dates=["date"])
workouts_full = pd.read_csv(os.path.join(DATA_DIR, "workouts.csv"), sep=";")

# Statut passe 2
prog = detail_parser.read_progress()
if prog.get("status") == "running":
    done, total = prog.get("done", 0), prog.get("total", 1)
    st.info(f"Analyse détaillée en cours — {done}/{total} séances traitées. Revenez dans quelques minutes.")

# KPIs
last = weekly.iloc[-1]
d7   = daily.tail(7)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Séances totales", len(workouts))
col2.metric("km course (dern. sem.)", f"{last['km_course']:.1f}")
col3.metric("D+ (dern. sem.)", f"{int(last['dplus_m'])} m")
col4.metric("HRV moy. (7 j)",
            f"{d7['hrv'].mean():.0f}" if "hrv" in d7 and d7["hrv"].notna().any() else "—")
col5.metric("Sommeil moy. (7 j)",
            f"{d7['sommeil_h'].mean():.1f} h" if "sommeil_h" in d7 and d7["sommeil_h"].notna().any() else "—")

st.divider()

# ── Synthèse état de la préparation ──────────────────────────────────────────
st.subheader("État de la préparation")

bases = recuperation.baselines(daily_full)
rec   = synthesis.recovery_block(daily_full, bases)
cha   = synthesis.charge_block(workouts)
forme = synthesis.forme_block(daily_full, workouts)

STATUS_ICON  = {"green": "🟢", "orange": "🟡", "red": "🔴", "grey": "⚪"}
STATUS_COLOR = {"green": "#d4edda", "orange": "#fff3cd", "red": "#f8d7da", "grey": "#f8f9fa"}

def _card(title: str, data: dict, metrics: list[tuple]):
    """
    metrics : liste de (label, value, delta, delta_color)
    delta et delta_color peuvent être None.
    """
    icon  = STATUS_ICON[data["status"]]
    color = STATUS_COLOR[data["status"]]
    with st.container(border=True):
        st.markdown(
            f"<div style='background:{color};border-radius:6px;"
            f"padding:6px 10px;margin-bottom:8px;font-weight:600'>"
            f"{icon} {title}</div>",
            unsafe_allow_html=True,
        )
        cols = st.columns(len(metrics)) if len(metrics) > 1 else [st]
        for col, (lbl, val, delta, dc) in zip(cols, metrics):
            if val is None:
                col.metric(lbl, "—")
            elif delta is not None:
                col.metric(lbl, val, delta, delta_color=dc or "normal")
            else:
                col.metric(lbl, val)
        st.caption(data["observation"])

syn_col1, syn_col2, syn_col3 = st.columns(3)

with syn_col1:
    hrv_val  = f"{rec['hrv_7']:.0f} ms"  if rec["hrv_7"]  is not None else None
    hrv_d    = f"{rec['hrv_delta_pct']:+.0f}% vs réf" if rec["hrv_delta_pct"] is not None else None
    hrv_dc   = "normal" if (rec["hrv_delta_pct"] or 0) >= 0 else "inverse"
    fc_val   = f"{rec['fc_7']:.0f} bpm"  if rec["fc_7"]   is not None else None
    fc_d     = f"{rec['fc_delta']:+.0f} vs réf"        if rec["fc_delta"]     is not None else None
    fc_dc    = "inverse" if (rec["fc_delta"] or 0) > 0 else "normal"
    sl_val   = f"{rec['sl_7']:.1f} h"    if rec["sl_7"]   is not None else None
    sl_d     = f"{rec['sl_delta']:+.1f}h vs réf"       if rec["sl_delta"]     is not None else None
    _card("Récupération", rec, [
        ("HRV (7 j)",      hrv_val, hrv_d, hrv_dc),
        ("FC repos (7 j)", fc_val,  fc_d,  fc_dc),
        ("Sommeil (7 j)",  sl_val,  sl_d,  None),
    ])

with syn_col2:
    trimp_val = f"{cha['trimp_now']:.0f}"
    trimp_d   = (f"moy. 4 sem : {cha['trimp_avg']:.0f}" if cha["trimp_avg"] else None)
    ratio_lbl = f"{cha['ratio']*100:.0f}% de la moy." if cha["ratio"] else "—"
    _card("Charge", cha, [
        ("TRIMP sem.", trimp_val, trimp_d, None),
        ("Séances",    str(cha["n_seances"]), None, None),
        ("Ratio",      ratio_lbl, None, None),
    ])

with syn_col3:
    trend_icons = {"up": "↗ hausse", "down": "↘ baisse", "flat": "→ stable", None: "—"}
    trend_val = trend_icons[forme["hrv_trend"]]
    trend_d   = (f"{forme['hrv_trend_pct']:+.0f}% / 7 j préc."
                 if forme["hrv_trend_pct"] is not None else None)
    drift_val = (f"{forme['last_drift']:+.1f}%" if forme["last_drift"] is not None else None)
    drift_lbl = (f"Drift longue ({forme['last_drift_date']})"
                 if forme["last_drift_date"] else "Drift longue")
    _card("Forme", forme, [
        ("Tendance HRV",  trend_val, trend_d, None),
        (drift_lbl,       drift_val, None,    None),
    ])

st.divider()

# ── PMC — Performance Management Chart ───────────────────────────────────────
pmc_df = synthesis.pmc_block(workouts_full)
if not pmc_df.empty:
    chart_header("Performance Management Chart (ATL / CTL / TSB)", H_PMC)

    cutoff = get_date_cutoff()
    pmc_view = pmc_df[pmc_df["date"] >= cutoff].copy() if cutoff is not None else pmc_df.copy()

    last = pmc_df.iloc[-1]
    ctl_now, atl_now, tsb_now = last["ctl"], last["atl"], last["tsb"]

    pm1, pm2, pm3 = st.columns(3)
    pm1.metric("CTL — Fitness", f"{ctl_now:.1f}")
    pm2.metric("ATL — Fatigue", f"{atl_now:.1f}")
    pm3.metric(
        "TSB — Forme",
        f"{tsb_now:+.1f}",
        delta="Frais" if tsb_now >= 0 else "En charge",
        delta_color="normal" if tsb_now >= 0 else "inverse",
    )

    pmc_view["tsb_pos"] = pmc_view["tsb"].clip(lower=0)
    pmc_view["tsb_neg"] = pmc_view["tsb"].clip(upper=0)

    fig_pmc = go.Figure()
    # TRIMP journalier (axe secondaire, en fond)
    trimp_max = pmc_view["trimp"].max()
    fig_pmc.add_bar(
        x=pmc_view["date"], y=pmc_view["trimp"],
        name="TRIMP journalier", yaxis="y2",
        marker_color="rgba(180,180,180,0.35)",
    )
    # TSB fills
    fig_pmc.add_scatter(
        x=pmc_view["date"], y=pmc_view["tsb_pos"],
        name="TSB positif", showlegend=False, mode="none",
        fill="tozeroy", fillcolor="rgba(46,204,113,0.18)",
    )
    fig_pmc.add_scatter(
        x=pmc_view["date"], y=pmc_view["tsb_neg"],
        name="TSB négatif", showlegend=False, mode="none",
        fill="tozeroy", fillcolor="rgba(231,76,60,0.18)",
    )
    # CTL & ATL
    fig_pmc.add_scatter(
        x=pmc_view["date"], y=pmc_view["ctl"],
        name="CTL (Fitness)", mode="lines",
        line=dict(color="#0068c9", width=2.5),
    )
    fig_pmc.add_scatter(
        x=pmc_view["date"], y=pmc_view["atl"],
        name="ATL (Fatigue)", mode="lines",
        line=dict(color="#e74c3c", width=2.5),
    )
    # TSB line
    fig_pmc.add_scatter(
        x=pmc_view["date"], y=pmc_view["tsb"],
        name="TSB (Forme)", mode="lines",
        line=dict(color="#27ae60", width=2),
    )
    fig_pmc.add_hline(y=0, line_dash="dot", line_color="grey", line_width=1)

    fig_pmc.update_layout(
        yaxis=dict(title="CTL / ATL / TSB"),
        yaxis2=dict(
            title="TRIMP/j", overlaying="y", side="right", showgrid=False,
            range=[0, trimp_max * 5] if trimp_max else [0, 10],
        ),
        legend=dict(orientation="h", y=1.12),
        height=360, margin=dict(t=10, b=0),
    )
    st.plotly_chart(fig_pmc, use_container_width=True)

    st.divider()

# Volume hebdomadaire
st.subheader("Volume hebdomadaire")
fig = px.bar(weekly, x="semaine", y="km_course",
             labels={"km_course": "km course", "semaine": "Semaine"},
             color_discrete_sequence=["#0068c9"])
fig.update_layout(height=280, margin=dict(t=10, b=0))
st.plotly_chart(fig, use_container_width=True)

# Dernières séances
st.subheader("Dernières séances")
display_cols = ["date", "heure", "type", "duree_min", "km", "dplus_m",
                "allure_min_km", "fc_moy", "zone", "kcal"]
st.dataframe(
    workouts[display_cols].tail(15).sort_values("date", ascending=False),
    use_container_width=True, hide_index=True,
)

# Entrées journal manquantes
n_missing = len(journal.sessions_missing_entry(workouts))
if n_missing:
    st.caption(f"⚠ {n_missing} séance(s) sans entrée journal — page **Journal** pour les compléter.")

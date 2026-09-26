"""Synthèse préparation SaintExpress — 6 questions + bilan hebdo exportable."""
import os
import sys
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.sidebar import render_import_sidebar, DATA_DIR, filter_period, get_date_cutoff
from src import recuperation, charge, config, journal, zones
from src.help_texts import chart_header
from src.help_texts import H_REGULARITE, H_PROGRESSION, H_TENUE_LONGUE, H_TERRAIN

RACE_DATE    = date(2026, 11, 28)
RACE_KM      = 45.0
RACE_DPLUS   = 1200
RACE_RATIO   = RACE_DPLUS / RACE_KM
TYPES_COURSE = {"Course", "Rando", "TrailRunning", "Hiking"}

st.set_page_config(page_title="SaintExpress", layout="wide")
st.title("Préparation SaintExpress 2026")

render_import_sidebar()

daily_path  = os.path.join(DATA_DIR, "daily.csv")
wk_path     = os.path.join(DATA_DIR, "workouts.csv")
weekly_path = os.path.join(DATA_DIR, "weekly.csv")

if not os.path.exists(wk_path):
    st.warning("Aucune donnée. Importez un export depuis l'accueil.")
    st.stop()

daily  = filter_period(pd.read_csv(daily_path,  sep=";"))
wk     = filter_period(pd.read_csv(wk_path,     sep=";"))
weekly = filter_period(pd.read_csv(weekly_path, sep=";"), col="lundi")
cfg    = config.load()

daily["date"] = pd.to_datetime(daily["date"])
wk["date"]    = pd.to_datetime(wk["date"])

jours_rest = (RACE_DATE - date.today()).days
runs = wk[wk["type"].isin(TYPES_COURSE)].copy()
runs["dplus_m"] = pd.to_numeric(runs["dplus_m"], errors="coerce").fillna(0)
runs["km"]      = pd.to_numeric(runs["km"],      errors="coerce")

# ── Bandeau compteur ──────────────────────────────────────────────────────────
st.info(f"**{jours_rest} jours** avant le départ · 28 novembre 2026 · 45 km / ~1 200 m D+")

# ── Navigation par question ───────────────────────────────────────────────────
QUESTIONS = [
    "1. Ma préparation est-elle régulière ?",
    "2. Est-ce que je progresse sur des efforts comparables ?",
    "3. Est-ce que je termine mieux mes sorties longues ?",
    "4. Mon entraînement couvre-t-il le terrain de la course ?",
    "5. Comment évolue ma récupération ?",
    "6. Quels éléments nuit / ravitaillement restent à tester ?",
]

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# Q1 — Régularité
# ══════════════════════════════════════════════════════════════════════════════
with st.expander(QUESTIONS[0], expanded=True):
    wk_load = charge.weekly_load(wk)
    w8 = wk_load.tail(8)

    if w8.empty:
        st.info("Données insuffisantes.")
    else:
        semaines_actives = (w8["charge_trimp"] > 0).sum()
        semaines_course  = (w8["sortie_longue"].notna()).sum()
        charge_moy       = w8[w8["charge_trimp"] > 0]["charge_trimp"].mean()
        seances_moy      = wk[wk["date"] >= pd.Timestamp(date.today() - timedelta(weeks=8))]["type"].count() / 8

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Semaines actives / 8", f"{semaines_actives} / 8")
        c2.metric("Semaines avec sortie longue", f"{semaines_course}")
        c3.metric("Charge TRIMP moy / semaine", f"{charge_moy:.0f}" if not pd.isna(charge_moy) else "—")
        c4.metric("Séances / semaine", f"{seances_moy:.1f}")

        fig = go.Figure()
        fig.add_bar(
            x=w8["semaine"], y=w8["charge_trimp"],
            marker_color=["#e74c3c" if v == 0 else "#0068c9" for v in w8["charge_trimp"]],
            name="Charge TRIMP",
        )
        fig.update_layout(height=200, margin=dict(t=5, b=0), showlegend=False,
                          yaxis_title="Charge TRIMP")
        st.plotly_chart(fig, width="stretch")

        if semaines_actives < 6:
            st.warning(f"Seulement {semaines_actives}/8 semaines actives — régularité à améliorer.")
        elif semaines_actives == 8:
            st.success("8/8 semaines actives — régularité parfaite sur la fenêtre.")
        else:
            st.info(f"{semaines_actives}/8 semaines actives.")

# ══════════════════════════════════════════════════════════════════════════════
# Q2 — Progression efforts comparables
# ══════════════════════════════════════════════════════════════════════════════
with st.expander(QUESTIONS[1], expanded=False):
    pace_df = recuperation.pace_z2z3_trend(wk)

    if pace_df.empty:
        st.info("Données insuffisantes — il faut des séances Course Z2/Z3 ≥ 5 km avec allure enregistrée.")
    else:
        pace_df["date"] = pd.to_datetime(pace_df["date"])
        pace_df = pace_df.sort_values("date")

        # Tendance linéaire simple
        import numpy as np
        x_idx = range(len(pace_df))
        if len(pace_df) >= 3:
            coef = np.polyfit(list(x_idx), pace_df["pace_sec"].tolist(), 1)
            trend = [coef[0] * i + coef[1] for i in x_idx]
            delta_s = trend[-1] - trend[0]
            delta_lbl = f"{abs(delta_s):.0f}s/km {'plus rapide' if delta_s < 0 else 'plus lent'} sur la période"
        else:
            trend = None
            delta_lbl = "Pas assez de points pour une tendance."

        fig2 = go.Figure()
        fig2.add_scatter(
            x=pace_df["date"], y=pace_df["pace_sec"],
            mode="markers+lines", name="Allure (s/km)",
            marker=dict(size=8, color=pace_df["fc_moy"],
                        colorscale="RdYlGn_r", showscale=True,
                        colorbar=dict(title="FC moy")),
            line=dict(color="rgba(0,0,0,0.15)"),
        )
        if trend is not None:
            fig2.add_scatter(
                x=pace_df["date"], y=trend,
                mode="lines", name="Tendance",
                line=dict(color="#e74c3c", dash="dash", width=2),
            )
        fig2.update_yaxes(
            autorange="reversed",
            tickvals=[300, 360, 420, 480, 540, 600],
            ticktext=["5:00", "6:00", "7:00", "8:00", "9:00", "10:00"],
        )
        fig2.update_layout(
            height=300, margin=dict(t=10, b=0),
            xaxis_title="Date", yaxis_title="Allure (min/km)",
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig2, width="stretch")
        st.caption(
            f"{len(pace_df)} séances Course Z2/Z3 ≥ 5 km · {delta_lbl} · "
            "Couleur = FC moy (vert = bas, rouge = élevé)."
        )

# ══════════════════════════════════════════════════════════════════════════════
# Q3 — Tenue sorties longues
# ══════════════════════════════════════════════════════════════════════════════
with st.expander(QUESTIONS[2], expanded=False):
    @st.cache_data(show_spinner=False)
    def _drifts_q3(n: int):
        return recuperation.long_run_drifts(wk)

    drifts = _drifts_q3(len(wk))

    if drifts.empty:
        st.info("Aucune sortie longue avec données FC complètes (> 60 min, minimum 30 échantillons).")
    else:
        drifts = drifts.sort_values("date")
        recent = drifts.tail(10)
        drift_moy = recent["drift_pct"].mean()
        n_ok      = (recent["drift_pct"].abs() < 5).sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Sorties longues analysées", len(drifts))
        c2.metric("Drift moy (10 dernières)", f"{drift_moy:+.1f} %")
        c3.metric("Sorties < 5% drift (10 dern.)", f"{n_ok} / {len(recent)}")

        colors = [
            "#2ecc71" if abs(v) < 5 else ("#f39c12" if abs(v) < 10 else "#e74c3c")
            for v in recent["drift_pct"]
        ]
        fig3 = go.Figure()
        fig3.add_bar(
            x=recent["date"], y=recent["drift_pct"],
            marker_color=colors,
            text=[f"{v:+.1f}%" for v in recent["drift_pct"]],
            textposition="outside",
        )
        fig3.add_hline(y=0, line_color="gray", line_dash="dot")
        fig3.add_hrect(y0=-5, y1=5, fillcolor="#2ecc71", opacity=0.07, line_width=0)
        fig3.update_layout(
            height=240, margin=dict(t=10, b=0),
            yaxis_title="Drift % (positif = FC monte)", showlegend=False,
        )
        st.plotly_chart(fig3, width="stretch")

        if abs(drift_moy) < 5:
            st.success(f"Bonne tenue cardio en moyenne ({drift_moy:+.1f} %).")
        elif drift_moy > 5:
            st.warning(f"Dérive positive ({drift_moy:+.1f} %) — tendance à la fatigue en fin de sortie.")
        else:
            st.info(f"Dérive négative ({drift_moy:+.1f} %) — effort progressif ou échauffement long.")

# ══════════════════════════════════════════════════════════════════════════════
# Q4 — Couverture terrain
# ══════════════════════════════════════════════════════════════════════════════
with st.expander(QUESTIONS[3], expanded=False):
    total_dplus = runs["dplus_m"].sum()
    total_km    = runs["km"].sum(skipna=True)
    ratio_global = total_dplus / total_km if total_km > 0 else 0

    cutoff_12 = get_date_cutoff()
    runs_12 = runs[runs["date"] >= cutoff_12].copy() if cutoff_12 else runs.copy()
    total_dplus_12 = runs_12["dplus_m"].sum()
    total_km_12    = runs_12["km"].sum(skipna=True)
    ratio_12       = total_dplus_12 / total_km_12 if total_km_12 > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("D+ accumulé (total)",     f"{total_dplus:,.0f} m")
    c2.metric("D+ accumulé (12 sem.)",   f"{total_dplus_12:,.0f} m")
    c3.metric("Ratio D+/km (total)",     f"{ratio_global:.1f} m/km",
              delta=f"Cible {RACE_RATIO:.1f}")
    c4.metric("Ratio D+/km (12 sem.)",   f"{ratio_12:.1f} m/km",
              delta=f"Cible {RACE_RATIO:.1f}")

    # Progression longue par semaine
    runs["semaine"] = runs["date"].dt.strftime("%Y-W%W")
    weekly_run = runs.groupby("semaine").agg(
        dplus_m=("dplus_m", "sum"),
        km=("km",      "sum"),
    ).reset_index().tail(16)
    weekly_run["ratio"] = (weekly_run["dplus_m"] / weekly_run["km"].replace(0, float("nan"))).fillna(0)

    fig4 = go.Figure()
    fig4.add_bar(x=weekly_run["semaine"], y=weekly_run["dplus_m"],
                 name="D+ (m)", marker_color="#e74c3c", opacity=0.75)
    fig4.add_scatter(x=weekly_run["semaine"], y=weekly_run["ratio"],
                     name="D+/km", mode="lines+markers",
                     yaxis="y2", line=dict(color="#8e44ad", width=2))
    fig4.add_hline(y=RACE_RATIO, line_dash="dash", line_color="#8e44ad",
                   yref="y2", annotation_text=f"Cible {RACE_RATIO:.1f} m/km",
                   annotation_position="top right")
    fig4.update_layout(
        yaxis=dict(title="D+ (m)"),
        yaxis2=dict(title="D+/km", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=1.1),
        height=280, margin=dict(t=10, b=0),
    )
    st.plotly_chart(fig4, width="stretch")

    pct = ratio_global / RACE_RATIO * 100
    if pct >= 80:
        st.success(f"Ratio D+/km global ({ratio_global:.1f}) atteint à {pct:.0f}% de la cible.")
    else:
        st.warning(
            f"Ratio D+/km global {ratio_global:.1f} vs cible {RACE_RATIO:.1f} m/km "
            f"({pct:.0f}% — augmenter l'entraînement en dénivelé)."
        )

# ══════════════════════════════════════════════════════════════════════════════
# Q5 — Récupération
# ══════════════════════════════════════════════════════════════════════════════
with st.expander(QUESTIONS[4], expanded=False):
    bases = recuperation.baselines(daily)
    cutoff_5 = get_date_cutoff()
    daily_8w = daily[daily["date"] >= cutoff_5].copy() if cutoff_5 else daily.copy()

    hrv_recent = daily_8w["hrv"].dropna() if "hrv" in daily_8w.columns else pd.Series(dtype=float)
    fc_recent  = daily_8w["fc_repos"].dropna() if "fc_repos" in daily_8w.columns else pd.Series(dtype=float)
    sl_recent  = daily_8w["sommeil_h"].dropna() if "sommeil_h" in daily_8w.columns else pd.Series(dtype=float)

    observations = []

    if not hrv_recent.empty and bases.get("hrv"):
        hrv_moy_r = hrv_recent.mean()
        ref = bases["hrv"]["median"]
        diff = hrv_moy_r - ref
        if diff < -5:
            observations.append(f"HRV récente ({hrv_moy_r:.0f} ms) en dessous de la référence ({ref} ms) — signe de fatigue accumulée possible.")
        elif diff > 5:
            observations.append(f"HRV récente ({hrv_moy_r:.0f} ms) au-dessus de la référence ({ref} ms) — bonne forme.")
        else:
            observations.append(f"HRV récente ({hrv_moy_r:.0f} ms) proche de la référence ({ref} ms).")

    if not fc_recent.empty and bases.get("fc_repos"):
        fc_moy_r = fc_recent.mean()
        ref_fc = bases["fc_repos"]["median"]
        diff_fc = fc_moy_r - ref_fc
        if diff_fc > 3:
            observations.append(f"FC repos récente ({fc_moy_r:.0f} bpm) plus haute que la référence ({ref_fc} bpm) — surveiller.")
        else:
            observations.append(f"FC repos récente ({fc_moy_r:.0f} bpm) dans les normes ({ref_fc} bpm de référence).")

    if not sl_recent.empty and bases.get("sommeil_h"):
        sl_moy_r = sl_recent.mean()
        ref_sl = bases["sommeil_h"]["median"]
        diff_sl = sl_moy_r - ref_sl
        if diff_sl < -0.5:
            observations.append(f"Sommeil récent ({sl_moy_r:.1f} h) en dessous de la référence ({ref_sl} h).")
        else:
            observations.append(f"Sommeil récent ({sl_moy_r:.1f} h) correct (référence {ref_sl} h).")

    if not observations:
        st.info("Données insuffisantes pour une observation de récupération.")
    else:
        for obs in observations:
            st.write(f"- {obs}")

    if not hrv_recent.empty or not fc_recent.empty:
        roll_8 = recuperation.rolling_weekly(daily_8w.copy())
        fig5 = go.Figure()
        if "hrv_r7" in roll_8.columns and roll_8["hrv_r7"].notna().any():
            fig5.add_scatter(
                x=roll_8["date"], y=roll_8["hrv_r7"],
                mode="lines", name="HRV moy 7 j",
                line=dict(color="#ff7f0e", width=2),
            )
        if "fc_repos_r7" in roll_8.columns and roll_8["fc_repos_r7"].notna().any():
            fig5.add_scatter(
                x=roll_8["date"], y=roll_8["fc_repos_r7"],
                mode="lines", name="FC repos moy 7 j",
                line=dict(color="#d62728", width=2),
                yaxis="y2",
            )
        if fig5.data:
            fig5.update_layout(
                yaxis=dict(title="HRV (ms)"),
                yaxis2=dict(title="FC repos (bpm)", overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", y=1.1),
                height=240, margin=dict(t=5, b=0),
            )
            st.plotly_chart(fig5, width="stretch")

# ══════════════════════════════════════════════════════════════════════════════
# Q6 — Nuit & ravitaillement
# ══════════════════════════════════════════════════════════════════════════════
with st.expander(QUESTIONS[5], expanded=False):
    all_entries = journal.load()
    nocturnes   = wk[wk["nocturne"] == "oui"].copy()
    sorties_nuit_avec_ravito = []
    sorties_nuit_sans_journal = []

    for _, row in nocturnes.iterrows():
        wid = journal.workout_id(str(row["date"].date()), str(row["heure"]), str(row["type"]))
        entry = all_entries.get(wid, {})
        if not entry:
            sorties_nuit_sans_journal.append(row)
        elif any(entry.get(k) for k in ["aliments", "boissons", "glucides_g_h", "strategie_notes"]):
            sorties_nuit_avec_ravito.append({
                "date":               str(row["date"].date()),
                "type":               row["type"],
                "duree_min":          row.get("duree_min"),
                "frontale":           entry.get("frontale", "—"),
                "confort_nuit":       entry.get("confort_nuit"),
                "sommeil_avant_h":    entry.get("sommeil_avant_h"),
                "aliments":           entry.get("aliments"),
                "glucides_g_h":       entry.get("glucides_g_h"),
                "tolerance_digestive":entry.get("tolerance_digestive"),
                "baisse_energie":     entry.get("baisse_energie"),
            })

    c1, c2, c3 = st.columns(3)
    c1.metric("Sorties nocturnes (total)", len(nocturnes))
    c2.metric("Avec données ravito", len(sorties_nuit_avec_ravito))
    c3.metric("Sans journal", len(sorties_nuit_sans_journal))

    if sorties_nuit_avec_ravito:
        st.subheader("Historique ravitaillement nocturne")
        df_ravito = pd.DataFrame(sorties_nuit_avec_ravito)
        st.dataframe(df_ravito, width="stretch", hide_index=True)

        # Observations
        df_r = df_ravito.copy()
        if "tolerance_digestive" in df_r and df_r["tolerance_digestive"].notna().any():
            tol_moy = pd.to_numeric(df_r["tolerance_digestive"], errors="coerce").mean()
            st.write(f"- Tolérance digestive moyenne : **{tol_moy:.1f}/10**")
        if "baisse_energie" in df_r:
            n_baisse = df_r["baisse_energie"].apply(lambda x: bool(x)).sum()
            if n_baisse:
                st.warning(f"Baisse d'énergie signalée dans {n_baisse} sortie(s).")
        if "glucides_g_h" in df_r:
            gl = pd.to_numeric(df_r["glucides_g_h"], errors="coerce").dropna()
            if not gl.empty:
                st.write(f"- Glucides ingérés : {gl.min():.0f}–{gl.max():.0f} g/h (moy {gl.mean():.0f} g/h)")
    else:
        st.info(
            "Aucune sortie nocturne avec données ravitaillement saisies. "
            "Renseignez les séances nocturnes dans la page **Journal** pour suivre l'historique."
        )

    if sorties_nuit_sans_journal:
        with st.expander(f"{len(sorties_nuit_sans_journal)} sortie(s) nocturne(s) sans journal"):
            df_sans = pd.DataFrame([
                {"date": str(r["date"].date()), "heure": r["heure"],
                 "type": r["type"], "duree_min": r.get("duree_min")}
                for r in sorties_nuit_sans_journal
            ])
            st.dataframe(df_sans, width="stretch", hide_index=True)
            st.caption("→ Complétez dans la page **Journal** pour nourrir cet historique.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# Bilan hebdomadaire exportable
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("Bilan hebdomadaire exportable")

# Fenêtre : semaine courante et précédente
today        = date.today()
lundi_this   = today - timedelta(days=today.weekday())
lundi_last   = lundi_this - timedelta(weeks=1)

wk_this  = wk[(wk["date"] >= pd.Timestamp(lundi_this)) & (wk["date"] < pd.Timestamp(lundi_this + timedelta(weeks=1)))]
wk_last  = wk[(wk["date"] >= pd.Timestamp(lundi_last)) & (wk["date"] < pd.Timestamp(lundi_this))]

col_sel1, col_sel2 = st.columns([1, 3])
semaine_bilan = col_sel1.selectbox(
    "Semaine",
    ["Semaine en cours", "Semaine précédente"],
)
wk_bilan = wk_this if semaine_bilan == "Semaine en cours" else wk_last
lundi_ref = lundi_this if semaine_bilan == "Semaine en cours" else lundi_last
semaine_label = lundi_ref.strftime("%Y-W%W")

# Calcul métriques semaine
runs_b      = wk_bilan[wk_bilan["type"].isin(TYPES_COURSE)].copy()
km_b        = pd.to_numeric(runs_b["km"], errors="coerce").sum()
dplus_b     = pd.to_numeric(runs_b["dplus_m"], errors="coerce").fillna(0).sum()
duree_b     = pd.to_numeric(wk_bilan["duree_min"], errors="coerce").sum()
n_seances_b = len(wk_bilan)
nocturnes_b = (wk_bilan["nocturne"] == "oui").sum() if "nocturne" in wk_bilan.columns else 0

entries_bilan = journal.load()
rpe_vals = []
for _, row in wk_bilan.iterrows():
    wid_ = journal.workout_id(str(row["date"].date()), str(row["heure"]), str(row["type"]))
    e = entries_bilan.get(wid_, {})
    if e.get("rpe") is not None:
        rpe_vals.append(e["rpe"])
rpe_moy_b = sum(rpe_vals) / len(rpe_vals) if rpe_vals else None

# HRV et sommeil de la semaine
daily_b = daily[
    (daily["date"] >= pd.Timestamp(lundi_ref)) &
    (daily["date"] < pd.Timestamp(lundi_ref + timedelta(weeks=1)))
]
hrv_b  = pd.to_numeric(daily_b["hrv"], errors="coerce").dropna() if "hrv" in daily_b.columns else pd.Series(dtype=float)
sl_b   = pd.to_numeric(daily_b["sommeil_h"], errors="coerce").dropna() if "sommeil_h" in daily_b.columns else pd.Series(dtype=float)

lines_md = [
    f"# Bilan semaine {semaine_label}",
    f"",
    f"**Jours avant SaintExpress :** {(RACE_DATE - lundi_ref).days}",
    f"",
    f"## Volume",
    f"- Séances : {n_seances_b}",
    f"- Course/Rando : {km_b:.1f} km · {dplus_b:.0f} m D+",
    f"- Durée totale : {duree_b:.0f} min",
    f"- Sorties nocturnes : {nocturnes_b}",
    f"",
    f"## Ressenti",
    f"- RPE moyen : {rpe_moy_b:.1f}/10 ({len(rpe_vals)} séances renseignées)" if rpe_moy_b else "- RPE : non renseigné",
    f"",
    f"## Récupération",
]
if not hrv_b.empty:
    lines_md.append(f"- HRV moy : {hrv_b.mean():.0f} ms (référence {bases.get('hrv', {}).get('median', '?')} ms)")
else:
    lines_md.append("- HRV : non mesurée cette semaine")

if not sl_b.empty:
    lines_md.append(f"- Sommeil moy : {sl_b.mean():.1f} h (référence {bases.get('sommeil_h', {}).get('median', '?')} h)")
else:
    lines_md.append("- Sommeil : données manquantes")

# Faits marquants : long run + drift
wk_long = runs_b[pd.to_numeric(runs_b["duree_min"], errors="coerce").fillna(0) > 60]
if not wk_long.empty:
    r = wk_long.iloc[0]
    lines_md += [
        f"",
        f"## Sortie longue",
        f"- {r['type']} — {pd.to_numeric(r.get('km'), errors='coerce'):.1f} km · "
        f"{pd.to_numeric(r.get('dplus_m'), errors='coerce'):.0f} m D+ · "
        f"{pd.to_numeric(r.get('duree_min'), errors='coerce'):.0f} min",
    ]

lines_md += [
    f"",
    f"## Points à surveiller / à tester",
    f"- [ ] ",
    f"",
    f"---",
    f"*Généré le {date.today().strftime('%d/%m/%Y')} depuis le dashboard santé*",
]

bilan_md = "\n".join(lines_md)

with st.expander("Aperçu du bilan", expanded=False):
    st.markdown(bilan_md)

st.download_button(
    label="Télécharger le bilan (.md)",
    data=bilan_md,
    file_name=f"bilan_{semaine_label}.md",
    mime="text/markdown",
)

st.caption(
    "Le bilan Markdown peut être copié dans Obsidian, Notion ou tout éditeur compatible. "
    "Les cases « Points à surveiller » sont à compléter manuellement."
)

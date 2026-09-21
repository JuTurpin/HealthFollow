import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.sidebar import render_import_sidebar, DATA_DIR
from src import quality

st.set_page_config(page_title="Qualité des données", layout="wide")
st.title("Qualité des données")

render_import_sidebar()

report = quality.load(DATA_DIR)

if report is None:
    st.info("Aucun rapport disponible — importez un export pour générer l'analyse.")
    st.stop()

# ── Résumé ────────────────────────────────────────────────────────────────────
st.caption(f"Généré le {report['generated_at']}")
c1, c2, c3 = st.columns(3)
c1.metric("Séances", report["total_seances"])
c2.metric("Jours couverts", report["total_jours"])
c3.metric("Semaines", report["total_semaines"])

st.divider()

# ── Couverture des métriques ──────────────────────────────────────────────────
st.subheader("Couverture des métriques journalières")
couv = report.get("couverture", {})
if couv:
    cols = st.columns(len(couv))
    for col, (label, v) in zip(cols, couv.items()):
        pct = v["pct"]
        color = "normal" if pct >= 70 else ("off" if pct < 30 else "inverse")
        col.metric(label, f"{pct:.0f} %", f"{v['jours']}/{v['total']} jours", delta_color=color)
else:
    st.info("Aucune métrique trouvée.")

st.divider()

# ── Anomalies ─────────────────────────────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    doublons = report.get("doublons", [])
    st.subheader(f"Doublons potentiels ({len(doublons)})")
    if doublons:
        import pandas as pd
        st.dataframe(
            pd.DataFrame(doublons),
            use_container_width=True, hide_index=True,
        )
    else:
        st.success("Aucun doublon détecté.")

with col_right:
    suspects = report.get("suspects", [])
    st.subheader(f"Séances suspectes ({len(suspects)})")
    if suspects:
        import pandas as pd
        df = pd.DataFrame(suspects)
        df["raisons"] = df["raisons"].apply(lambda x: ", ".join(x))
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.success("Aucune séance suspecte détectée.")

# ── Semaines sans séance ──────────────────────────────────────────────────────
sans = report.get("semaines_sans_seance", [])
if sans:
    st.divider()
    st.subheader(f"Semaines sans séance enregistrée ({len(sans)})")
    st.write(", ".join(sans))
    st.caption("Possible interruption d'entraînement ou données manquantes.")

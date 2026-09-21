import os
import sys
import subprocess
import tempfile

import pandas as pd
import streamlit as st

PROJECT_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR      = os.path.join(PROJECT_ROOT, "sortie-sante")
SCRIPT        = os.path.join(PROJECT_ROOT, "sainteylon_health.py")
DETAIL_SCRIPT = os.path.join(PROJECT_ROOT, "src", "detail_parser.py")
EXPORT_SAVE   = os.path.join(PROJECT_ROOT, "data", "last_export.zip")

PERIODES = {"3 mois": 90, "6 mois": 180, "12 mois": 365, "Tout": None}
_PERIODE_DEFAULT = "6 mois"


def get_date_cutoff() -> "pd.Timestamp | None":
    days = PERIODES.get(st.session_state.get("periode", _PERIODE_DEFAULT))
    if days is None:
        return None
    return pd.Timestamp.now().normalize() - pd.Timedelta(days=days)


def filter_period(df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
    """Filtre df en gardant les lignes dont la colonne col >= cutoff global."""
    cutoff = get_date_cutoff()
    if cutoff is None or col not in df.columns:
        return df
    return df[pd.to_datetime(df[col]) >= cutoff].copy()


def render_import_sidebar():
    with st.sidebar:
        st.selectbox(
            "Période d'analyse",
            list(PERIODES.keys()),
            index=list(PERIODES.keys()).index(_PERIODE_DEFAULT),
            key="periode",
        )
        st.divider()
        st.header("Importer un export")
        st.caption("iPhone → Santé → Profil → Exporter les données → export.zip")
        uploaded = st.file_uploader("export.zip", type="zip", label_visibility="collapsed")
        c1, c2 = st.columns(2)
        fcmax   = c1.number_input("FC max",   value=185, step=1)
        fcrepos = c2.number_input("FC repos", value=51,  step=1)

        if uploaded and st.button("Importer", type="primary", use_container_width=True):
            os.makedirs(os.path.join(PROJECT_ROOT, "data"), exist_ok=True)
            zip_bytes = uploaded.read()

            # Conserve le zip pour la passe 2
            with open(EXPORT_SAVE, "wb") as f:
                f.write(zip_bytes)

            # Passe 1 : parsing rapide
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(zip_bytes)
                tmp_path = tmp.name

            with st.spinner("Passe 1 — import des résumés…"):
                result = subprocess.run(
                    [sys.executable, SCRIPT, tmp_path,
                     "--all", "--outdir", DATA_DIR,
                     "--fcmax", str(fcmax), "--fcrepos", str(fcrepos)],
                    capture_output=True, text=True, cwd=PROJECT_ROOT,
                )
            os.unlink(tmp_path)

            if result.returncode != 0:
                st.error(result.stderr or result.stdout)
                return

            # Sauvegarde les paramètres FC
            from src import config, quality
            config.save(fcmax, fcrepos)

            # Rapport qualité (rapide, sur les CSV)
            quality.generate(DATA_DIR)

            # Séances sans entrée journal → stockées en session_state
            from src import journal
            wk = pd.read_csv(os.path.join(DATA_DIR, "workouts.csv"), sep=";")
            pending = journal.sessions_missing_entry(wk)
            if pending:
                st.session_state["pending_journal"] = pending

            # Passe 2 : extraction détaillée en arrière-plan
            subprocess.Popen(
                [sys.executable, DETAIL_SCRIPT],
                cwd=PROJECT_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            st.rerun()

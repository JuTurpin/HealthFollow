import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

st.set_page_config(page_title="Santé Dashboard", layout="wide")

pg = st.navigation({
    "": [
        st.Page("pages/Accueil.py", title="Accueil", default=True),
    ],
    "Données": [
        st.Page("pages/0_Qualite.py",  title="Qualité"),
        st.Page("pages/5_Journal.py",  title="Journal"),
    ],
    "Entraînement": [
        st.Page("pages/1_Activite.py", title="Activité"),
        st.Page("pages/7_Seance.py",   title="Séance"),
        st.Page("pages/8_Terrain.py",  title="Terrain"),
        st.Page("pages/6_Charge.py",   title="Charge"),
    ],
    "Santé": [
        st.Page("pages/2_Cardiaque.py",    title="Cardiaque"),
        st.Page("pages/3_Sommeil.py",      title="Sommeil"),
        st.Page("pages/4_Corps.py",        title="Corps"),
        st.Page("pages/9_Recuperation.py", title="Récupération"),
    ],
    "Course": [
        st.Page("pages/10_SaintExpress.py",  title="SaintExpress"),
        st.Page("pages/11_Abreviations.py",  title="Abréviations"),
    ],
})
pg.run()

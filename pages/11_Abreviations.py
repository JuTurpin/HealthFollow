"""Glossaire — toutes les abréviations et définitions du dashboard."""
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.sidebar import render_import_sidebar

st.set_page_config(page_title="Abréviations", layout="wide")
st.title("Abréviations & définitions")

render_import_sidebar()

st.caption(
    "Retrouvez ici le sens de chaque terme utilisé dans le dashboard. "
    "Les boutons ℹ sur les graphiques donnent une explication propre à chaque vue."
)

# ── Mesures cardiaques & physiologiques ───────────────────────────────────────
st.subheader("Mesures cardiaques & physiologiques")

data_cardio = {
    "FC":       ("Fréquence Cardiaque",
                 "Nombre de battements du cœur par minute (bpm). "
                 "Mesurée en continu par l'Apple Watch pendant l'effort."),
    "FC repos": ("FC au repos",
                 "Mesurée le matin avant de se lever. "
                 "Plus elle est basse, meilleure est en général la récupération. "
                 "Une hausse soudaine (+5 bpm) peut signaler fatigue ou début de maladie."),
    "FC max":   ("FC maximale",
                 "Paramètre de référence (réglé dans la sidebar). "
                 "Correspond à votre fréquence cardiaque maximale théorique ou mesurée."),
    "FCR":      ("FC de Réserve",
                 "FCR = FC max − FC repos. "
                 "Base du calcul des zones Karvonen. "
                 "Exemple : FC max 185, FC repos 51 → FCR = 134 bpm."),
    "HRV":      ("Heart Rate Variability — Variabilité de la FC",
                 "Mesure la variation de l'intervalle entre deux battements consécutifs (en ms). "
                 "Plus la valeur est élevée, plus le système nerveux autonome est flexible et reposé. "
                 "Mesurée chaque matin par l'Apple Watch (indicateur SDNN). "
                 "À interpréter sur une tendance de 5–7 jours, pas sur une valeur isolée."),
    "bpm":      ("Battements Par Minute",
                 "Unité de la fréquence cardiaque."),
    "VO2max":   ("Volume maximal d'oxygène",
                 "Capacité maximale du corps à consommer de l'oxygène pendant l'effort, "
                 "exprimée en mL/kg/min. "
                 "Estimation Apple Watch basée sur la FC et l'allure en plein air — "
                 "pas une mesure clinique. Indicatif de la condition aérobie générale."),
}

for abbr, (full, desc) in data_cardio.items():
    with st.expander(f"**{abbr}** — {full}"):
        st.write(desc)

# ── Zones d'entraînement ──────────────────────────────────────────────────────
st.subheader("Zones d'entraînement (méthode Karvonen)")

st.markdown(
    "Les zones sont calculées depuis la **FC de Réserve** (méthode Karvonen) : "
    "`FC zone = FC repos + % × (FC max − FC repos)`\n\n"
    "Avec FC max 185 et FC repos 51 (FCR = 134) :"
)

zones_data = [
    ("Z1", "< 60 % FCR", "< 131 bpm", "Récupération active", "#2ecc71",
     "Effort très léger. Marche rapide, footing très lent. "
     "Favorise la récupération sans stress supplémentaire."),
    ("Z2", "60–70 % FCR", "131–145 bpm", "Endurance fondamentale", "#3498db",
     "Zone cible pour la majorité des entraînements (70–80 % du volume). "
     "Développe le moteur aérobie de base, brûle principalement les graisses, "
     "fatigue musculaire minimale."),
    ("Z3", "70–80 % FCR", "145–158 bpm", "Endurance active / tempo", "#f39c12",
     "Effort modéré soutenu. Améliore le seuil aérobie. "
     "À doser — trop de Z3 sans récupération suffisante peut accumuler la fatigue."),
    ("Z4", "80–90 % FCR", "158–172 bpm", "Seuil lactique", "#e74c3c",
     "Effort intense. Améliore le seuil anaérobie et la vitesse. "
     "Réservé aux séances de qualité (fractionnés, intervalles)."),
    ("Z5", "> 90 % FCR", "> 172 bpm", "Capacité maximale", "#8e44ad",
     "Effort maximal, très court. Sprint, montée explosive. "
     "Sollicite le système anaérobie. "
     "Inadapté à l'entraînement trail longue distance quotidien."),
]

cols = st.columns(5)
for i, (zone, pct, bpm_range, name, color, desc) in enumerate(zones_data):
    with cols[i]:
        st.markdown(
            f"<div style='background:{color};padding:8px;border-radius:6px;"
            f"color:white;text-align:center;font-weight:bold;margin-bottom:6px'>"
            f"{zone}</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"**{pct}**  \n{bpm_range}  \n*{name}*")
        with st.expander("Détail"):
            st.write(desc)

# ── Métriques d'entraînement ──────────────────────────────────────────────────
st.subheader("Métriques d'entraînement")

data_train = {
    "TRIMP":        ("Training IMPulse — Charge d'entraînement objective",
                     "Formule de Banister : `TRIMP = durée (min) × FC réserve normalisée × e^(y × FC réserve normalisée)` "
                     "avec y = 1,92 (homme).\n\n"
                     "Permet de comparer la charge de séances très différentes : "
                     "une séance intense courte peut avoir le même TRIMP qu'une longue sortie facile. "
                     "Se somme sur la semaine pour obtenir la charge hebdomadaire."),
    "RPE":          ("Rate of Perceived Exertion — Effort ressenti",
                     "Échelle de 0 à 10 :\n"
                     "- 0–2 : très facile (échauffement, récupération)\n"
                     "- 3–4 : facile, on peut tenir une conversation\n"
                     "- 5–6 : modéré, conversation difficile\n"
                     "- 7–8 : difficile, quelques mots seulement\n"
                     "- 9–10 : maximal, impossible de parler\n\n"
                     "À renseigner dans le Journal après chaque séance."),
    "Charge RPE":   ("Charge subjective hebdomadaire",
                     "Somme de (durée en min × RPE) pour toutes les séances renseignées de la semaine. "
                     "Complémentaire au TRIMP : capte la fatigue mentale, la chaleur, le terrain "
                     "que la FC seule ne reflète pas toujours."),
    "Drift":        ("Dérive cardiaque",
                     "Augmentation de la FC au fil d'un effort constant. "
                     "Calculé en divisant la séance en 3 tiers temporels égaux :\n\n"
                     "`Drift % = (FC moy 3e tiers − FC moy 1er tiers) / FC moy 1er tiers × 100`\n\n"
                     "- **< +5 %** → bonne tenue cardio-vasculaire\n"
                     "- **+5 à +10 %** → légère dégradation (acceptable par forte chaleur ou fin de sortie longue)\n"
                     "- **> +10 %** → fatigue importante, effort non maîtrisé"),
    "Allure":       ("Allure de course",
                     "Temps mis pour parcourir un kilomètre (format min:sec/km). "
                     "Plus la valeur est **basse**, plus on court **vite**. "
                     "Axe vertical inversé dans les graphiques : les points du bas = plus rapide."),
}

for abbr, (full, desc) in data_train.items():
    with st.expander(f"**{abbr}** — {full}"):
        st.markdown(desc)

# ── Métriques terrain ──────────────────────────────────────────────────────────
st.subheader("Terrain & dénivelé")

data_terrain = {
    "D+":           ("Dénivelé positif",
                     "Cumul des montées en mètres sur une sortie ou une semaine. "
                     "Mesuré par le baromètre de l'Apple Watch. "
                     "Peut légèrement différer du GPS selon les conditions."),
    "D+/km":        ("Ratio dénivelé positif par kilomètre",
                     "D+ / distance. Caractérise la technicité du terrain. "
                     "La SaintExpress Express vise ~26,7 m/km (1 200 m D+ / 45 km). "
                     "Un terrain plat est à ~0–5 m/km, une randonnée montagne à 50–100 m/km."),
    "Nocturne":     ("Séance nocturne",
                     "Séance démarrée entre 20h00 et 06h00. "
                     "Important pour la SaintExpress qui part à 23h00 le 28 novembre 2026."),
}

for abbr, (full, desc) in data_terrain.items():
    with st.expander(f"**{abbr}** — {full}"):
        st.markdown(desc)

# ── Métriques santé & sommeil ──────────────────────────────────────────────────
st.subheader("Santé & récupération")

data_sante = {
    "Sommeil (h)":  ("Durée de sommeil",
                     "Durée totale de sommeil enregistrée par l'iPhone (accéléromètre). "
                     "Inclut sommeil léger, profond et paradoxal (REM). "
                     "Objectif indicatif : 7h30–9h pour un sportif d'endurance."),
    "P25 / P75":    ("Percentiles 25 et 75",
                     "50 % de vos valeurs se situent entre P25 et P75. "
                     "Si votre HRV du jour est sous le P25, c'est un signal de vigilance."),
    "Moy. 7 j":     ("Moyenne glissante 7 jours",
                     "Moyenne calculée sur les 7 derniers jours pour lisser les variations quotidiennes. "
                     "Plus stable qu'une valeur isolée pour détecter les tendances."),
    "Référence":    ("Médiane personnelle",
                     "Calculée sur l'ensemble de l'historique disponible. "
                     "Votre valeur de référence à vous — plus pertinente que des normes génériques."),
}

for abbr, (full, desc) in data_sante.items():
    with st.expander(f"**{abbr}** — {full}"):
        st.markdown(desc)

# ── Format des dates & semaines ───────────────────────────────────────────────
st.subheader("Format des dates")

st.markdown(
    "Les semaines sont affichées au format **ISO 8601** : `YYYY-WXX`\n\n"
    "- `2026-W42` = semaine 42 de l'année 2026 (lundi 12 octobre 2026)\n"
    "- La semaine commence le **lundi**\n"
    "- **S−** dans les tableaux = numéro de semaine ISO"
)

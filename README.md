# Santé Dashboard

Dashboard personnel d'analyse des données Apple Watch / iPhone, conçu pour piloter une préparation trail longue distance.

Construit avec Python + Streamlit. Aucune donnée ne quitte la machine — tout tourne en local.

---

## Fonctionnalités

- **Import** d'un export Apple Health (zip) via la sidebar
- **Dashboard Home** : KPIs, synthèse Récupération / Charge / Forme, PMC (ATL/CTL/TSB)
- **Activité** : volume hebdomadaire, zones FC réelles, progression course
- **Cardiaque** : HRV, FC repos, zones par séance
- **Sommeil** : durée, tendances, corrélation sommeil → HRV
- **Corps** : poids, VO2max
- **Journal** : annotations subjectives (RPE, objectif, facteur limitant, nuit, ravitaillement)
- **Charge** : TRIMP hebdo, charge RPE, répartition par type
- **Séance** : détail FC brute + lissée, zones réelles, drift cardiaque
- **Terrain** : dénivelé hebdo, ratio D+/km, progression sortie longue
- **Récupération** : baselines personnelles, rolling 7j, charge vs HRV
- **SaintExpress** : synthèse préparation course (adaptable à tout objectif)
- **Abréviations** : glossaire complet de tous les termes

---

## Prérequis

- Python 3.10+
- Apple Watch + iPhone (export Apple Health)

---

## Installation

```bash
git clone https://github.com/<votre-compte>/<votre-repo>.git
cd <votre-repo>
python -m venv .venv
source .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install -r requirements.txt
streamlit run Home.py
```

---

## Import des données

1. Sur iPhone : **Santé → Profil → Exporter toutes les données de santé** → `export.zip`
2. Dans la sidebar du dashboard : déposer le fichier zip, renseigner FC max et FC repos, cliquer **Importer**
3. Une passe rapide génère les CSV, une passe de fond extrait le détail FC/GPS des séances

Les données sont stockées localement dans `sortie-sante/` et `details/` — ces dossiers sont exclus de git.

---

## Structure

```
Home.py                  # Page d'accueil
pages/                   # Pages Streamlit (Activité, Cardiaque, Sommeil…)
src/
  sidebar.py             # Import, filtre global de période
  sainteylon_health.py   # Parser Apple Health XML (passe 1)
  detail_parser.py       # Extraction FC/GPS détaillée (passe 2)
  charge.py              # Calcul TRIMP
  synthesis.py           # Blocs synthèse + PMC
  recuperation.py        # Baselines personnelles
  zones.py               # Calcul zones Karvonen
  drift.py               # Analyse drift cardiaque
  journal.py             # Journal d'entraînement
  config.py              # FC max / FC repos
  help_texts.py          # Textes d'aide des graphiques
requirements.txt
```

---

## Paramètres personnels

FC max et FC repos se règlent dans la sidebar au moment de l'import. Ils sont sauvegardés dans `sortie-sante/params.json` (exclu de git).

Les zones cardiaques utilisent la **méthode Karvonen** (FC de réserve).

---

## Confidentialité

Aucune donnée n'est envoyée vers un serveur externe. Tout le traitement est local.
Les dossiers contenant des données de santé (`sortie-sante/`, `details/`, `data/`, `journal.json`) sont listés dans `.gitignore` et ne seront jamais poussés sur GitHub.

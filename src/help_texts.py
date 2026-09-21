"""Abréviations et textes d'aide pour chaque page du dashboard."""
import streamlit as st

# ── Helper UI ──────────────────────────────────────────────────────────────────

def chart_header(title: str, help_md: str, level: str = "subheader"):
    """Titre de graphique + bouton ℹ qui ouvre un popover d'explication."""
    c1, c2 = st.columns([0.94, 0.06])
    getattr(c1, level)(title)
    with c2.popover("ℹ"):
        st.markdown(help_md)


def abbrevs_expander(abbrevs: dict, title: str = "📖 Abréviations & définitions"):
    """Expander récapitulant les abréviations de la page."""
    with st.expander(title, expanded=False):
        for key, val in abbrevs.items():
            st.markdown(f"**{key}** — {val}")


# ── Abréviations globales ──────────────────────────────────────────────────────

GLOBAL = {
    "FC":        "Fréquence Cardiaque (battements par minute, bpm)",
    "FC repos":  "FC mesurée le matin au repos — plus elle est basse, meilleure est la récupération",
    "FC max":    "Fréquence Cardiaque Maximale — paramètre de référence (réglé dans la sidebar)",
    "FCR":       "FC de Réserve = FC max − FC repos — base du calcul des zones Karvonen",
    "HRV":       "Heart Rate Variability — variabilité de la fréquence cardiaque (ms). "
                 "Mesurée le matin par l'Apple Watch (SDNN). Reflet du système nerveux autonome : "
                 "une HRV haute indique une bonne récupération",
    "bpm":       "Battements Par Minute",
    "Z1–Z5":     "Zones cardiaques calculées par la méthode Karvonen (réserve cardiaque). "
                 "Z1 < 60 % FCR · Z2 60–70 % · Z3 70–80 % · Z4 80–90 % · Z5 > 90 %",
    "D+ / D+/km":"Dénivelé Positif accumulé / ratio dénivelé par kilomètre",
    "TRIMP":     "Training IMPulse — charge d'entraînement (méthode Banister). "
                 "Calcul : durée × FC de réserve normalisée × facteur exponentiel (y = 1,92 homme). "
                 "Permet de comparer des séances d'intensités différentes",
    "RPE":       "Rate of Perceived Exertion — effort ressenti de 0 (repos) à 10 (max)",
    "Allure":    "Temps par kilomètre (min:sec/km) — plus la valeur est basse, plus on est rapide",
    "km":        "Kilomètres parcourus",
    "VO2max":    "Volume maximal d'O₂ consommé par kg/min — indicateur de capacité aérobie "
                 "(estimation Apple Watch, pas une mesure clinique)",
    "S−":        "Numéro ISO de la semaine dans l'année (ex. 2026-W42 = semaine 42 de 2026)",
    "Nocturne":  "Séance démarrée entre 20h00 et 06h00",
}

# ── Abréviations par page ──────────────────────────────────────────────────────

ABBREVS_ACTIVITE = {**GLOBAL, **{
    "Volume":       "Total de km de course (Course, Rando, TrailRunning, Hiking) sur la semaine",
    "Zones réelles":"Temps calculé depuis les échantillons FC horodatés (1 pt/s), "
                    "pas depuis la FC moyenne — beaucoup plus précis",
    "Progression":  "Évolution de l'allure dans le temps à FC équivalente",
}}

ABBREVS_CARDIAQUE = {**GLOBAL, **{
    "Boxplot":      "Boîte à moustaches : la ligne centrale est la médiane, "
                    "les bords de la boîte le 1er et 3e quartile (P25–P75), "
                    "les moustaches s'étendent jusqu'aux valeurs extrêmes",
    "Séance (point)":"Chaque point est une séance. Taille = durée. Couleur = zone cardiaque principale",
}}

ABBREVS_SOMMEIL = {**GLOBAL, **{
    "Durée nuit":   "Durée totale de sommeil enregistrée par l'iPhone (capteurs de mouvement)",
    "Moy. 7 j":     "Moyenne glissante sur 7 jours",
    "Corrélation":  "Association statistique entre deux variables — ne signifie pas causalité. "
                    "La droite de tendance indique le sens général de la relation",
}}

ABBREVS_CORPS = {**GLOBAL, **{
    "Moy. mobile 7 j": "Moyenne calculée sur les 7 derniers jours pour lisser les variations journalières",
    "Évolution (période)": "Différence entre la première et la dernière mesure de la période affichée",
    "Masse grasse":    "Pourcentage de masse grasse (si balance connectée synchro avec Santé iOS)",
    "Masse maigre":    "Masse corporelle sans la graisse (muscles, os, eau)",
}}

ABBREVS_JOURNAL = {**GLOBAL, **{
    "Facteur limitant": "Ce qui a freiné la performance : Souffle (cardio), Jambes (musculaire), "
                        "Énergie (glycogène/mental), Douleur (blessure), Digestion, Terrain",
    "Fatigue J+1":     "Ressenti de fatigue le lendemain de la séance (0 = frais, 10 = épuisé). "
                       "Uniquement pour les séances > 90 min",
    "Jambes J+1":      "État musculaire des jambes le lendemain (0 = courbatures sévères, 10 = parfait)",
    "Confort nuit":    "Confort général lors d'une sortie nocturne (visibilité, température, stress)",
    "Frontale":        "Lampe frontale utilisée pour la sortie nocturne",
    "Glucides g/h":    "Apport en glucides par heure d'effort — objectif course : 60–90 g/h",
    "Tolérance digestive": "Confort digestif pendant l'effort (0 = très mauvais, 10 = parfait)",
}}

ABBREVS_CHARGE = {**GLOBAL, **{
    "Charge TRIMP":    "Somme des TRIMP de la semaine — indicateur objectif (basé sur la FC)",
    "Charge RPE":      "Somme de (durée × RPE) pour la semaine — indicateur subjectif. "
                       "Disponible uniquement pour les séances renseignées dans le Journal",
    "Sortie longue":   "Durée de la séance Course/Rando la plus longue de la semaine",
    "Semaine active":  "Semaine avec au moins une séance enregistrée (TRIMP > 0)",
}}

ABBREVS_SEANCE = {**GLOBAL, **{
    "FC brute":     "Mesure instantanée de la FC capteur par capteur (fréquence ~1 Hz Apple Watch)",
    "FC lissée 5 min": "Moyenne glissante sur 60 échantillons (≈5 min) pour lisser le bruit",
    "Drift cardiaque": "Différence relative entre la FC moyenne du 3e tiers et du 1er tiers de la séance. "
                       "Drift positif = FC monte → fatigue cardiovasculaire ou chaleur",
    "3 tiers":      "La séance est découpée en 3 intervalles temporels égaux pour analyser la progression",
    "Séances comparables": "Séances du même type avec distance ±30 % ou durée ±25 % par rapport à la séance sélectionnée",
}}

ABBREVS_TERRAIN = {**GLOBAL, **{
    "Ratio D+/km":  "Dénivelé positif moyen par kilomètre. La SaintExpress vise ~26,7 m/km (1 200 m / 45 km)",
    "Sortie longue":"Sortie la plus longue en km de la semaine pour les types Course/Rando/TrailRunning/Hiking",
    "Baromètre AW": "Le D+ provient du baromètre intégré de l'Apple Watch — peut différer du GPS",
}}

ABBREVS_RECUPERATION = {**GLOBAL, **{
    "Référence personnelle": "Médiane calculée sur l'ensemble de votre historique disponible. "
                             "P25/P75 = 1er et 3e quartile (50 % des valeurs se situent dans cet intervalle)",
    "Moy. glissante 7 j":   "Moyenne des 7 derniers jours (min. 3 points requis)",
    "Charge TRIMP vs HRV":  "Croisement entre la charge d'entraînement (TRIMP) et la HRV hebdo. "
                             "Idéalement la HRV devrait remonter dans les semaines de faible charge",
    "Drift sorties longues": "Drift cardiaque pour les Course/Rando > 60 min. "
                              "Vert < 5 % · Orange 5–10 % · Rouge > 10 %",
}}

ABBREVS_SAINTEXPRESS = {**GLOBAL, **{
    "Régularité":           "Nombre de semaines actives (charge > 0) sur la période sélectionnée",
    "Efforts comparables":  "Séances Course en Z2/Z3, distance ≥ 5 km, avec allure enregistrée",
    "Tenue sorties longues":"Analyse du drift cardiaque sur les sorties > 60 min",
    "Couverture terrain":   "Comparaison de votre ratio D+/km avec la cible course",
    "Bilan exportable":     "Résumé Markdown à copier dans Obsidian, Notion ou tout éditeur compatible",
}}

# ── Textes d'aide par graphique ────────────────────────────────────────────────

# Page 1
H_VOL_HRV = """
**Volume hebdomadaire + HRV**

Les **barres bleues** = km de course par semaine.
La **courbe orange** = HRV moyenne de la semaine.

**Comment lire :**
- HRV haute + bon volume → bonne assimilation de l'entraînement.
- HRV qui baisse malgré un volume croissant → fatigue accumulée possible.
- Semaine sans barre = pas de course enregistrée.
"""

H_ZONES_TOTAL = """
**Zones FC réelles (période complète)**

Temps total passé dans chaque zone sur toute la période, calculé depuis les **échantillons FC horodatés** (pas depuis la FC moyenne de la séance).

**Objectif endurance fondamentale (polarisation) :**
- Z1 + Z2 devrait représenter 70–80 % du temps total.
- Z4 + Z5 : efforts intenses, à doser selon le plan.
"""

H_ZONES_SEM = """
**Temps en zones par semaine**

Répartition hebdomadaire du temps en zones (barres empilées).

**Comment lire :**
- Une semaine majoritairement verte/bleue = volume en endurance.
- Une semaine avec beaucoup de rouge/violet = semaine intense.
- Les semaines sans données FC détaillées n'apparaissent pas.
"""

H_PROGRESSION_COURSE = """
**Progression course — allure vs FC moy**

Chaque **point** = une séance Course.
- Axe vertical : allure en min/km (**vers le bas = plus rapide**).
- **Couleur** : FC moyenne (vert = basse, rouge = élevée).
- La ligne grise relie les séances dans le temps.

**Comment lire :**
- Un point vers le bas avec une couleur verte = courir vite à faible effort → progression.
- Si les points descendent (allure diminue) à couleur équivalente, vous progressez.
"""

# Page 2
H_HRV_FC = """
**HRV & FC de repos**

**Courbe bleue** = HRV quotidienne (ms) — axe gauche.
**Courbe rouge pointillée** = FC repos (bpm) — axe droit.

**Comment lire :**
- HRV haute + FC repos basse = bonne récupération.
- HRV qui chute sur plusieurs jours + FC qui monte = fatigue ou début de maladie.
- Variabilité journalière normale — regarder la **tendance** sur 5–7 jours.
"""

H_HRV_BOX = """
**HRV hebdomadaire (boxplot)**

Chaque boîte = distribution de la HRV sur une semaine.
- **Ligne centrale** = médiane (valeur du milieu).
- **Bords de la boîte** = P25–P75 (50 % des valeurs).
- **Moustaches** = valeurs extrêmes de la semaine.

**Comment lire :**
- Boîte haute et large = semaine avec bonne HRV mais variable.
- Boîte basse = semaine de fatigue.
- Tendance haussière sur plusieurs semaines = forme en progression.
"""

H_FC_SEANCE = """
**FC moyenne par séance**

Chaque **point** = une séance.
- **Taille** = durée (grand = long).
- **Couleur** = zone cardiaque principale.

**Comment lire :**
- Points en haut = séances intenses.
- Points en bas = séances faciles (récupération, Z1/Z2).
- Un gros point vert en bas = sortie longue en endurance fondamentale.
"""

# Page 3
H_SOMMEIL_NUIT = """
**Durée de sommeil par nuit**

Barres quotidiennes de durée totale de sommeil (données iPhone).

La **ligne pointillée à 7h30** est une référence indicative — les besoins varient selon les individus.

**Comment lire :**
- Des nuits courtes répétées avant une séance peuvent impacter la FC repos et la HRV.
- Cherchez une régularité plutôt qu'une durée parfaite.
"""

H_SOMMEIL_HEB = """
**Sommeil moyen par semaine**

Barres colorées = durée moyenne par semaine. La couleur encode l'intensité (plus foncé = moins de sommeil).

Permet de repérer les **semaines de dette de sommeil** sur la durée.
"""

H_SOMMEIL_CORR = """
**Corrélation sommeil → HRV lendemain**

Chaque **point** = une nuit.
- Axe horizontal = durée de sommeil cette nuit (h).
- Axe vertical = HRV le lendemain matin.
- **Droite de tendance** = direction générale de la relation.

**Comment lire :**
- Tendance montante = dormir plus → meilleure HRV → meilleure récupération.
- Si la tendance est plate, d'autres facteurs (stress, charge, alimentation) dominent.

⚠️ Corrélation ≠ causalité. Un seul facteur ne suffit pas à expliquer la HRV.
"""

# Page 4
H_POIDS = """
**Poids + moyenne mobile 7 jours**

Les **points** = pesées individuelles.
La **courbe rouge** = moyenne sur 7 jours pour lisser les variations (eau, transit...).

**Comment lire :**
- Se baser sur la courbe lissée, pas sur les points isolés.
- Une variation de ±1 kg en une journée est souvent de l'eau, pas de la masse.
"""

H_VO2 = """
**VO2max**

Estimation Apple Watch de votre capacité aérobie maximale (mL/kg/min).

**Références indicatives pour un homme :**
- < 40 : faible · 40–50 : moyen · 50–55 : bon · > 55 : excellent

⚠️ C'est une **estimation** basée sur la FC et l'allure lors des courses en plein air, pas une mesure clinique. Les valeurs peuvent varier selon les conditions.
"""

# Page 6
H_VOL_CHARGE = """
**Volume hebdomadaire**

**Barres bleues** = km de course.
**Courbe orange** = durée totale toutes activités (en heures).

**Comment lire :**
- Un volume élevé en km avec peu d'heures = séances courtes et intenses.
- Un volume élevé en heures avec peu de km = randonnée, vélo, ou allure lente.
"""

H_CHARGE_HEB = """
**Charge hebdomadaire TRIMP + RPE**

**Barres bleues** = charge TRIMP (objective, calculée depuis la FC).
**Diamants rouges** = charge RPE (subjective, durée × ressenti), disponibles uniquement si le journal est renseigné.

**Comment lire :**
- TRIMP et charge RPE devraient évoluer ensemble. Un écart important peut indiquer une séance mal calibrée (effort ressenti très différent de l'effort cardiaque).
- Cherchez une progression sur 3–4 semaines suivie d'une semaine de récupération.
"""

H_REPARTITION = """
**Répartition par type d'activité**

Barres empilées par semaine. Chaque couleur = un type d'activité.

**Comment lire :**
- Visualise la diversité de l'entraînement sur la période.
- Pour préparer un trail, Course + Rando/TrailRunning devraient dominer.
"""

# Page 7
H_FC_TEMPS = """
**Fréquence cardiaque au fil du temps**

**Courbe bleue claire** = FC brute (mesure instantanée).
**Courbe bleue foncée** = FC lissée sur 5 minutes.
**Bandes colorées** = zones cardiaques Z1–Z5.
**Lignes pointillées verticales** = découpage en tiers de la séance.

**Comment lire :**
- Une FC qui monte progressivement tout au long de la séance sans accélération volontaire = dérive cardiaque (fatigue ou chaleur).
- Une FC stable dans une zone = effort régulier bien cadré.
"""

H_ZONES_SEANCE = """
**Zones FC réelles (cette séance)**

Temps passé dans chaque zone sur **cette séance uniquement**, calculé depuis les échantillons horodatés.

**Beaucoup plus précis** que d'assigner toute la séance à la zone de sa FC moyenne.

**Comment lire :**
- Pour une sortie longue d'endurance : Z1+Z2 devraient dominer.
- Un pic en Z4/Z5 en fin de séance peut être un sprint final ou une côte.
"""

H_DRIFT = """
**Drift cardiaque (3 tiers)**

La séance est divisée en **3 intervalles temporels égaux**.
La FC moyenne de chaque tiers est calculée.

**Drift % = (FC 3e tiers − FC 1er tiers) / FC 1er tiers × 100**

**Interprétation :**
- **< +5 %** (vert) = bonne tenue cardio-vasculaire.
- **+5 à +10 %** (orange) = légère dégradation, normal en fin de sortie longue ou par forte chaleur.
- **> +10 %** (rouge) = fatigue significative ou effort non maîtrisé.
- **Négatif** = échauffement progressif ou effort qui démarre fort.

Minimum requis : 20 min de données FC, 30 échantillons.
"""

# Page 8
H_DPLUS_HEB = """
**D+ hebdomadaire — course & rando**

**Barres rouges** = dénivelé positif total Course/Rando de la semaine.
**Courbe bleue** = km de course de la semaine.

**Comment lire :**
- Semaine avec beaucoup de D+ et peu de km = terrain pentu (randonnée, trail en montagne).
- Semaine avec beaucoup de km et peu de D+ = course sur terrain plat.
- Pour préparer la SaintExpress, augmenter progressivement le D+ hebdo.
"""

H_RATIO_DPLUS = """
**Ratio D+/km par semaine vs cible course**

Chaque barre = D+ moyen par km sur la semaine.
**Ligne pointillée rouge** = ratio cible de la SaintExpress (~26,7 m/km).

**Couleur des barres :**
- 🟢 Vert ≥ 80 % de la cible — bonne semaine de D+.
- 🟡 Orange ≥ 40 % — préparation en cours.
- ⬜ Gris < 40 % — peu de dénivelé cette semaine.
"""

H_SORTIE_LONGUE = """
**Progression de la sortie longue**

**Barres bleues** = distance (km) de la sortie la plus longue de la semaine.
**Courbe rouge** = D+ de cette sortie.
**Ligne pointillée bleue** = distance cible de la course.

**Comment lire :**
- Cherchez une progression croissante des barres vers la cible.
- La sortie longue est le pilier de la préparation trail — elle conditionne l'endurance et la gestion de la fatigue en fin de course.
"""

# Page 9
H_HRV_ROLL = """
**HRV et FC de repos — moyennes glissantes 7 j**

**Points orange** = HRV brute quotidienne. **Courbe orange épaisse** = moy. 7 j.
**Points rouges** = FC repos brute. **Courbe rouge épaisse** = moy. 7 j.
**Lignes pointillées horizontales** = vos références personnelles (médiane historique).

**Comment lire :**
- HRV au-dessus de la référence + FC repos en dessous = bonne forme.
- HRV qui descend plusieurs jours de suite = accumulation de fatigue ou stress.
- Variations isolées (nuit courte, soirée tardive) = normales, ne pas sur-interpréter.
"""

H_SOMMEIL_ROLL = """
**Sommeil — moyenne glissante 7 j**

Barres = durée quotidienne. Courbe = moyenne 7 jours.

**Comment lire :**
- Comparez la courbe à votre référence personnelle.
- Une dette de sommeil sur 5+ jours précédant une séance longue peut impacter la performance.
"""

H_CHARGE_HRV = """
**Charge TRIMP vs HRV hebdo**

**Barres rouges** = charge d'entraînement (TRIMP) par semaine.
**Courbe orange** = HRV moyenne de la semaine.

**Comment lire :**
- Après une semaine de forte charge, la HRV devrait baisser légèrement puis remonter en récupération.
- Si la HRV ne remonte pas après une semaine légère → fatigue chronique ou facteur extrasportif.
- Si la HRV reste haute même avec une charge élevée → bonne forme.
"""

H_RPE_HEB = """
**RPE hebdomadaire**

Barre = RPE moyen de la semaine (séances renseignées dans le journal).

**Couleurs :**
- 🟢 Vert ≤ 5 — semaine facile / récupération.
- 🟡 Orange 6–7 — semaine modérée.
- 🔴 Rouge ≥ 8 — semaine difficile.

Comparez avec la charge TRIMP : un RPE élevé avec un TRIMP bas peut indiquer une fatigue non cardiaque (terrain, chaleur, état de forme).
"""

H_DRIFT_LONG = """
**Drift cardiaque — sorties longues**

Drift en % pour chaque sortie Course/Rando > 60 min avec données FC.

**Couleurs :**
- 🟢 Vert < 5 % — bonne tenue en fin de sortie.
- 🟡 Orange 5–10 % — légère dégradation, acceptable.
- 🔴 Rouge > 10 % — fatigue importante en fin de sortie.

Une tendance à la baisse du drift au fil du temps indique une amélioration de l'endurance fondamentale.
"""

# Page 10
H_REGULARITE = """
**Régularité — 8 dernières semaines**

Barres bleues = charge TRIMP par semaine. Barres rouges = semaines sans activité.

**Objectif :** 6–7 semaines actives sur 8 pour une préparation solide.

Une semaine de coupure volontaire (récupération) est normale. Plusieurs semaines sans activité sur une courte période méritent attention.
"""

H_PROGRESSION = """
**Progression sur efforts comparables**

Séances Course en Z2/Z3, distance ≥ 5 km, avec allure enregistrée.
- Axe vertical : allure (**vers le bas = plus rapide**).
- Couleur : FC moyenne (vert = basse, rouge = élevée).
- Ligne rouge pointillée = tendance linéaire.

**Comment lire :**
- Tendance descendante (allure qui baisse) à FC stable = progression de la capacité aérobie.
- Si la tendance est plate ou montante, l'endurance de base n'évolue pas encore.
"""

H_TENUE_LONGUE = """
**Tenue des sorties longues — drift**

Drift cardiaque des 10 dernières sorties longues.

L'objectif trail longue distance est de maintenir un drift < 5 % sur des efforts de 3h+. Cela indique que votre endurance fondamentale est suffisante pour la distance.
"""

H_TERRAIN = """
**Couverture terrain — D+/km par semaine**

Ratio D+/km hebdo vs cible course (ligne pointillée).

Si votre ratio global reste inférieur à la cible sur plusieurs semaines, planifiez des sorties avec plus de dénivelé (randonnée, trail, répétitions de côtes).
"""

# Home — PMC
H_PMC = """
**PMC — Performance Management Chart**

Suit votre forme physique, fatigue et fraîcheur au fil du temps depuis **tout l'historique** (les 6 derniers mois sont affichés).

---

- **CTL** *(Chronic Training Load — Fitness)* : charge moyenne sur **42 jours**.
  Monte lentement, descend lentement. Représente votre forme de fond.
- **ATL** *(Acute Training Load — Fatigue)* : charge moyenne sur **7 jours**.
  Réagit rapidement à l'entraînement récent.
- **TSB** *(Training Stress Balance — Forme du moment)* = CTL − ATL.
  - 🟢 **TSB > 0** : repos relatif, jambes fraîches → prêt à performer.
  - 🔴 **TSB < 0** : fatigue accumulée → assimilation en cours, éviter les compétitions.
  - La zone idéale de départ se situe entre **0 et +15**.

---

**Calcul :** méthode Banister.
`TRIMP = durée × FC_réserve_normalisée × e^(1,92 × FC_réserve_normalisée)`

Les **barres grises** en fond = TRIMP journalier brut.
"""

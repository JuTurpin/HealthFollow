# Fonctionnalités à développer — Préparation SaintExpress

**Objectif :** utiliser les données Apple Watch et un journal personnel pour suivre la préparation d'un trail de 45 km, avec départ nocturne le 28 novembre 2026. Le dénivelé cible est provisoirement fixé à 1 200 m D+, à confirmer avec le parcours officiel.

---

## Décisions d'architecture

### Journal personnel
Saisi directement dans le dashboard Streamlit. Le journal est présenté lors de l'import lorsqu'une ou plusieurs nouvelles séances sont détectées : l'app pose les questions nécessaires et demande des précisions si une réponse est ambiguë. Les entrées sont conservées dans un fichier `journal.json` distinct des CSV, persisté entre les imports.

### Détail des séances (FC horodatée, GPS, altitude)
Import en deux passes :

1. **Passe rapide** (actuelle) : parsing des résumés `Workout` → workouts.csv / daily.csv / weekly.csv. Disponible en 1–3 min.
2. **Passe complète** (automatique après la passe rapide) : extraction des échantillons FC horodatés et des traces GPX pour chaque séance. Peut durer plusieurs minutes supplémentaires. Résultats stockés dans `details/` (un fichier JSON par séance).

Lorsqu'une vue nécessite les données de la passe complète et que celles-ci ne sont pas encore disponibles, afficher : **"Analyse en cours — revenez dans quelques minutes."**

---

## Plan de réalisation

### Lot 1 — Fondations (en cours)

| Priorité | Fonctionnalité | Complexité | Dépend de | Statut |
|---|---|---|---|---|
| 1 | **Journal personnel** (RPE, facteur limitant, douleurs, objectif, terrain) | Faible | — | Fait |
| 2 | **Rapport qualité import** (anomalies, doublons, valeurs manquantes, couverture) | Moyenne | — | Fait |
| 3 | **Extraction détail séance** (FC horodatée + GPX synchronisé, passe 2) | Élevée | — | Fait |

### Lot 2 — Charge & Zones

| Priorité | Fonctionnalité | Complexité | Dépend de | Statut |
|---|---|---|---|---|
| 4 | **Vue charge 8–12 semaines** (TRIMP × RPE, prévu/réalisé) | Moyenne | Journal (1) | Fait |
| 5 | **Vrais temps en zones** (à partir de FC horodatée, non par moyenne) | Moyenne | Détail séance (3) | Fait |

### Lot 3 — Analyse approfondie

| Priorité | Fonctionnalité | Complexité | Dépend de | Statut |
|---|---|---|---|---|
| 6 | **Comparer efforts similaires** (vitesse à FC équivalente) | Élevée | Détail séance (3) | Fait |
| 7 | **Tenue sorties longues** (dégradation allure/FC, découplage) | Élevée | Détail séance (3) | Fait |
| 8 | **Préparation terrain** (D+/D−, montées/descentes, vitesse ascensionnelle) | Moyenne | Détail séance (3) | Fait |

### Lot 4 — SaintExpress

| Priorité | Fonctionnalité | Complexité | Dépend de | Statut |
|---|---|---|---|---|
| 9 | **Récupération croisée** (HRV / sommeil / ressenti, tendance personnelle) | Moyenne | Journal (1) | Fait |
| 10 | **Journal nuit & ravitaillement** (matériel, glucides, tolérance) | Faible | Journal (1) | Fait |
| 11 | **Page synthèse SaintExpress** (6 questions, bilan hebdo exportable) | Élevée | Tout | Fait |

---

## 1. Fiabiliser les données — Priorité indispensable

**Question : puis-je faire confiance aux résultats affichés ?**

- Séparer course, randonnée, marche, vélo et autres sports ; proposer ensuite des regroupements explicites.
- Calculer distance, durée et dénivelé sur le même ensemble d'activités.
- Détecter les doublons, séances accidentelles et valeurs incohérentes.
- Fiabiliser l'association entre une séance et sa trace GPS.
- Distinguer une valeur absente d'une valeur égale à zéro.
- Conserver les fuseaux horaires et distinguer durée active, durée écoulée et pauses.
- Calculer les moyennes sur de véritables périodes calendaires ; signaler les semaines incomplètes.
- Permettre de corriger ou d'exclure une donnée en conservant sa valeur d'origine.

**Résultat attendu :** un état de qualité à chaque import, avec les anomalies à examiner et la couverture des mesures.

## 2. Conserver le détail des séances — Priorité indispensable

**Question : que se passe-t-il pendant mon effort ?**

Extraire et conserver les données horodatées disponibles :

- fréquence cardiaque ;
- position GPS, altitude et distance ;
- vitesse ou allure ;
- pauses ;
- cadence et puissance, si présentes.

Associer ces données à un identifiant stable de séance et conserver leur provenance.

**Résultat attendu :** une fiche séance avec courbes synchronisées de FC, allure et altitude, permettant de sélectionner une portion. Les interruptions de mesure doivent rester visibles.

## 3. Ajouter un journal personnel rapide — À commencer immédiatement

**Question : comment ai-je vécu la séance et comment ai-je récupéré ?**

Après chaque séance :

- objectif : endurance, sortie longue, fractionné, côtes, récupération, renforcement… ;
- difficulté globale ressentie de 0 à 10 ;
- facteur limitant : souffle, jambes, énergie, douleur, digestion ou terrain ;
- douleurs : localisation et intensité ;
- terrain, météo et matériel utilisé.

Après une sortie longue, ajouter fatigue et état des jambes à J+1/J+2.

**Résultat attendu :** un formulaire simple, lié à la séance, dont les réponses sont conservées lors des nouveaux imports.

## 4. Suivre la régularité et la charge

**Question : est-ce que je construis une préparation régulière et comment évolue la charge ?**

Afficher par semaine et sur plusieurs semaines :

- nombre de sorties et jours courus ;
- distance et durée de course ;
- D+ et D− ;
- durée de la sortie la plus longue ;
- répartition entre sports ;
- charge ressentie : durée en minutes × difficulté globale ;
- comparaison prévu/réalisé, avec motif des changements si renseigné.

**Résultat attendu :** une vue sur 8–12 semaines montrant progression, interruptions et variations importantes, sans transformer celles-ci en prédiction de blessure.

## 5. Calculer les vrais temps en zones cardiaques

**Question : quelle part de mon entraînement est réellement facile ou intense ?**

- Rendre les zones personnalisables et afficher leur méthode de calcul.
- Conserver l'historique des paramètres utilisés.
- Calculer le temps dans chaque zone à partir des mesures horodatées, en tenant compte de leur espacement.
- Afficher séparément le temps sans FC exploitable.
- Comparer l'intensité mesurée à l'objectif et au ressenti de la séance.

**Résultat attendu :** une distribution par séance et par semaine. Ne plus attribuer toute une séance à la zone de sa FC moyenne.

## 6. Comparer les efforts similaires

**Question : est-ce que je cours plus vite pour un effort comparable ?**

- Identifier des parcours ou segments de référence.
- Permettre de sélectionner manuellement des séances comparables.
- Comparer vitesse à FC similaire, ou FC à vitesse similaire.
- Tenir compte du relief, du terrain, de la météo et du ressenti.
- Exclure des comparaisons les échauffements, pauses et mesures douteuses.

**Résultat attendu :** une tendance sur plusieurs observations, accompagnée des différences de contexte. Ne pas conclure à une progression sur deux séances trop différentes.

## 7. Analyser la tenue pendant les sorties longues

**Question : est-ce que je maintiens mieux mon effort au fil du temps ?**

- Découper la sortie en périodes et en portions de terrain.
- Suivre l'évolution de la FC, de l'allure, de la marche et des arrêts.
- Comparer début et fin sur des portions similaires.
- Calculer le découplage vitesse/FC uniquement sur des efforts suffisamment réguliers et comparables.
- Superposer les prises alimentaires et les difficultés signalées.
- Comparer plusieurs sorties longues proches en durée et difficulté.

**Résultat attendu :** identifier quand l'effort se dégrade et les explications possibles, sans attribuer automatiquement la dégradation à un manque d'endurance.

## 8. Mesurer la préparation au terrain

**Question : suis-je préparé aux montées, descentes et portions roulantes ?**

- Calculer D+ et D− avec une méthode de filtrage documentée.
- Séparer les portions montantes, descendantes et plates.
- Suivre leur durée et leur distance.
- Comparer la vitesse ascensionnelle sur des montées similaires.
- Distinguer marche et course, avec correction manuelle possible.
- Relier les descentes à la fatigue musculaire du lendemain.
- Consigner les séances de renforcement.

**Résultat attendu :** une répartition de l'entraînement par terrain, puis une comparaison avec le profil de la course lorsqu'il sera disponible.

## 9. Suivre la récupération

**Question : quels signes indiquent que j'assimile l'entraînement ou que la fatigue s'accumule ?**

- Croiser sommeil, FC de repos, HRV et ressenti.
- Comparer les tendances à une référence personnelle sur plusieurs semaines.
- Conserver l'heure, le nombre et la provenance des mesures de HRV ; identifier la métrique utilisée, notamment SDNN.
- Rattacher correctement les nuits au réveil et gérer les siestes séparément.
- Afficher le nombre de jours renseignés.
- Mettre les observations en relation avec les séances précédentes.

**Résultat attendu :** des observations expliquées, par exemple « sommeil plus court et fatigue ressentie plus élevée cette semaine », sans diagnostic ni décision automatique fondée sur une seule mesure.

## 10. Préparer la nuit et le ravitaillement

**Question : qu'ai-je réellement testé dans les conditions de course ?**

Pour la nuit :

- mesurer la durée réellement passée dans l'obscurité, automatiquement ou manuellement ;
- noter frontale, visibilité, terrain, vêtements et confort ;
- consigner sommeil et siestes avant une sortie tardive, puis récupération.

Pour le ravitaillement :

- enregistrer aliments, glucides, boissons et horaires ;
- calculer les quantités consommées par heure ;
- noter tolérance digestive et baisses d'énergie ;
- enregistrer les stratégies testées et leur résultat.

**Résultat attendu :** un historique des essais permettant de préparer la course avec du matériel et une alimentation déjà éprouvés.

## 11. Créer la page « Préparation SaintExpress »

Réunir les réponses aux questions suivantes :

1. Ma préparation est-elle régulière ?
2. Est-ce que je progresse sur des efforts comparables ?
3. Est-ce que je termine mieux mes sorties longues ?
4. Mon entraînement couvre-t-il le terrain de la course ?
5. Comment évolue ma récupération ?
6. Quels éléments de nuit, de matériel et de ravitaillement restent à tester ?

Chaque réponse doit comporter les observations utilisées, leur période et leurs limites.

Prévoir un bilan hebdomadaire exportable contenant les faits marquants, le ressenti, les anomalies et les points à discuter. Éviter un score global de « préparation » qui masquerait les incertitudes.

---

**Règle commune :** lorsqu'une analyse manque de données fiables ou comparables, afficher « données insuffisantes » et préciser ce qui manque.

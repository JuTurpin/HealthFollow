# Rapport — page « Export bilan coach »

Date : 11/10/2026.

## 1. Ce qui est fait

Les cinq étapes de la liste de priorités sont terminées.

| Étape | État |
|---|---|
| 1. Page, sélecteur de semaine, zip avec `digest.md` et `seances.csv` | Fait |
| 2. `jours.csv`, `tendance.csv`, charge | Fait |
| 3. GPS : D−, splits, découplage, marche/course/arrêt, vitesse ascensionnelle | Fait |
| 4. Parseur de planning, prévu vs réalisé | Fait |
| 5. Paramètres course centralisés, ancienne section SaintExpress remplacée | Fait |

### Fichiers

- **`src/bilan_export.py`** (nouveau, sans Streamlit). Il contient tous les calculs et la construction du pack (`construire_pack()`, `zip_pack()`). Les seuils sont des constantes en haut du module.
- **`pages/12_Export_bilan.py`** (nouveau). La page est ajoutée dans `Home.py`, section « Course ».
- **`src/config.py`** : ajout de `race_date`, `race_km` et `race_dplus_m`, lus avec `config.race()`. `save()` conserve maintenant les autres clés de `params.json`.
- **Extensions de modules existants**, toutes avec un paramètre optionnel ou une fonction nouvelle, donc sans changement pour les pages existantes :
  - `zones.zone_bounds()` ;
  - `zones.zone_times(max_gap_s=300)` ;
  - `drift.derive_debut_fin()` ;
  - `charge.trimp_echantillons()` ;
  - `synthesis.pmc_block(cfg=None)` ;
  - `sainteylon_health.lisser_altitudes()` et `cumul_denivele()`. Ce sont des morceaux de `gpx_gain()` sortis en fonctions ; `gpx_gain()` renvoie maintenant aussi le D−.
- **`sainteylon_health.py`** : `RACE_DATE` est lu depuis `src/config.py`, avec un repli sur la valeur en dur si le script est copié seul.
- **`pages/10_SaintExpress.py`** :
  - la section « Bilan hebdomadaire exportable » est remplacée par un lien vers la nouvelle page ;
  - la date, la distance et le D+ viennent de `config` ;
  - le même bug `%Y-W%W` existait dans le graphique de la Q4 : il est corrigé (semaine ISO).
- **`pages/8_Terrain.py`** : les valeurs par défaut des paramètres course viennent de `config`.
- **Tests** : `tests/test_bilan_export.py` et `tests/fixtures/synthetique.py`. Ce dernier génère un jeu complet de 10 semaines en passant par `sainteylon_health.export_csv` pour produire les CSV.
- **`README.md`** et **`Roadmap.md`** sont mis à jour (ligne 12 ajoutée au Lot 4).

### Vérifications

- `sortie-sante/` est bien dans `.gitignore`, et `git status --ignored` le confirme.
- `streamlit run Home.py` a été lancé et les pages ont été ouvertes dans Chromium (Playwright) : Export bilan, SaintExpress et Terrain s'affichent sans exception.
- Sur la page Export, j'ai envoyé un planning, ouvert l'aperçu, téléchargé le zip et vérifié la copie dans `sortie-sante/bilans/S-08/`.
- J'ai relu `digest.md` dans le zip téléchargé.
- **Ces vérifications ont été faites avec le jeu synthétique.** Aucune donnée réelle n'était présente dans le conteneur.

### Ajout : sélection de plusieurs semaines

La liste déroulante de semaine est remplacée par deux champs numériques relatifs à la semaine en cours :

- **Dernière semaine exportée** : 0 = semaine en cours, 1 = semaine précédente (valeur par défaut, la dernière semaine complète), 2 = celle d'avant, etc. ;
- **Nombre de semaines** : de 1 à 12, en remontant à partir de la dernière.

Les semaines retenues s'affichent avec leur libellé `S-XX · 2026-Www · JJ/MM → JJ/MM`. Avec une seule semaine, le zip est inchangé. Avec plusieurs, il contient un sous-dossier complet par semaine (`bilan_S-09_2026-W39/digest.md`…) et s'appelle `bilan_S-10_a_S-08_2026-W38_2026-W40.zip`. Sur le disque, chaque semaine va dans son dossier `sortie-sante/bilans/S-XX/` et le zip groupé dans `sortie-sante/bilans/`. Le planning décrit une seule semaine : il est appliqué à la plus récente.

## 2. Données introuvables, et comment elles sont traitées

- **Heure de fin** : elle n'existe pas dans `workouts.csv`. Elle est calculée comme heure de début + `duree_min`.
- **D− par séance** : il n'existe pas dans Apple Health/passe 1. Il est calculé seulement depuis `gps_track`, sinon `NA`.
- **Fréquence respiratoire** : elle n'est présente que si la montre l'enregistre (`freq_resp` dans `daily.csv`).
- **Unité de `masse_grasse`** : Apple l'exporte en fraction (par exemple 0,18). La colonne est renommée `masse_grasse_frac` ; c'est à confirmer.
- **D+ dans `weekly.csv`** : il est cumulé sur toutes les activités (code de la passe 1), alors que les km ne comptent que course et rando. Je l'ai repris tel quel pour la ligne « Volume » et pour la tendance, comme le faisait déjà le digest de `sainteylon_health.py`.
- **`source` des séances** (nom de l'appareil) : la colonne n'est jamais exportée.

## 3. Choix faits sans validation

1. **Branche** : le travail est sur `feature/export-bilan-coach`, comme demandé. Les mêmes commits sont aussi poussés sur la branche de session `claude/determined-goldberg-h3x781`. Rien n'est poussé sur `main`.
2. **Semaine par défaut** : c'est la dernière semaine *entièrement écoulée*. Un dimanche, c'est donc la semaine précédente. La semaine en cours reste sélectionnable dans la liste.
3. **Passe 2** :
   - elle ne bloque le bouton que si son statut vaut `running` ;
   - si elle est en erreur ou n'a jamais tourné, un avertissement s'affiche et l'export reste possible ; le digest indique alors « passe 2 partielle ».
4. **Trou de FC** : un intervalle de plus de 60 s entre deux échantillons compte comme un trou (`FC_TROU_S`). Les pages existantes gardent 300 s.
   - `pct_fc_manquante` = (durée − temps couvert par la FC) / durée.
   - Les échantillons sont limités à la fenêtre de la séance, car le détail inclut ±2 min autour.
5. **TRIMP** :
   - source `echantillons` si au moins 90 % de la séance est couverte par la FC ;
   - sinon `fc_moy`, si la FC moyenne existe ;
   - sinon `NA`.
6. **ATL/CTL/TSB** : ils viennent de `synthesis.pmc_block`, qui calcule le TRIMP sur la FC moyenne, sans changement. Le TRIMP semaine et le ratio 7 j / 28 j utilisent le TRIMP par échantillon. Le digest le précise.
7. **Dérive 20/20** :
   - calculée seulement si la séance dure au moins 40 min, pour que les deux fenêtres ne se recouvrent pas ;
   - sur toutes les activités, y compris le tennis ;
   - la dérive par tiers existante est aussi exportée (`derive_tiers_pct`).
8. **Vitesse et pente GPS** :
   - lissées sur 5 segments ;
   - altitude lissée sur ±5 points, comme `gpx_gain` ;
   - un segment GPS de plus de 300 s compte comme une pause (arrêt).
9. **Splits** :
   - le dernier km partiel est gardé s'il fait au moins 100 m ;
   - le mode d'un split (course ou marche) est celui qui a occupé le plus de temps dans ce km ;
   - dans le digest, les splits sont résumés par blocs de 5 km.
10. **Prévu vs réalisé** :
    - appariement en deux passes, le même jour d'abord, puis à ±1 jour ;
    - familles d'activités : course, marche/rando, vélo, renfo, tennis, mobilité ;
    - **la rando et la course sont deux familles différentes** ;
    - statut ✅ si la durée est à ±20 %, le D+ atteint au moins 70 % de la cible et au moins 70 % du temps est dans la cible FC (pour chaque critère disponible) ; sinon 🔄 ;
    - ❌ si la séance n'est pas trouvée ;
    - une ligne « Repos » vaut ✅ s'il n'y a pas eu de séance ce jour-là (hors marche et mobilité) ;
    - les séances non appariées sont marquées `hors_plan`.
11. **Cibles FC** :
    - `Z1/Z2` devient la borne haute de Z2 (Karvonen), sans borne basse ;
    - une plage de durée comme `1h45-2h15` donne la moyenne (120 min).
12. **Tendance** : `%Z1-Z2 course` et « sortie la plus longue » ne comptent que course et rando (`TYPES_COURSE`).
13. **CSV** :
    - un flottant entier est écrit sans décimale (`50` et non `50.0`) ;
    - les booléens deviennent `oui`/`non` ;
    - les noms de colonnes de `daily.csv` sont suffixés avec leur unité dans `jours.csv` (`fc_repos_bpm`, `hrv_ms`…) ;
    - les noms `hrv_r7`, `fc_repos_r7` et `sommeil_r7` suivent la spécification.
14. **Enregistrement sur disque** : il a lieu au clic sur « Télécharger ». Le dossier contient le zip et les fichiers décompressés.
15. **Test « lat/lon »** :
    - un test littéral « aucune valeur ne contient `lat`/`lon` » échouerait sur des mots comme « Sortie **lon**gue » ou « choco**lat** » ;
    - le test vérifie donc l'absence de colonnes `lat`/`lon`/`latitude`/`longitude`, l'absence de ces mots entiers et l'absence des coordonnées du jeu de test dans tout le zip.
16. **Journal** : le champ de texte libre `notes` est exporté tel quel. Si vous y écrivez un lieu, il partira au coach.

## 4. Résultat des tests

```
$ python -m unittest
..............................
Ran 32 tests in 4.9s
OK
```

Ce qui est couvert :
- temps en zones et trous de FC ;
- dérive 20/20, avec le cas d'une séance trop courte ;
- découplage : 10 % attendu, une pause qui ne doit pas changer le résultat, le cas < 40 min, le cas sans GPS ;
- D+ et D− (60 m), splits (3 km à 6:00) ;
- marche / course / arrêt, vitesse ascensionnelle (600 m/h) ;
- TRIMP par échantillon et sa source ;
- parseur de planning : les 5 formes de cible FC, les familles, les durées, la section « Semaine en cours » seule, le fichier non modifié ;
- S-XX : la semaine du 05/10 donne S-7, celle du 23/11 donne S-0 ;
- libellé et semaine par défaut ;
- dans le zip :
  - aucune lat/lon et aucun nom de source ;
  - aucune cellule vide ;
  - `NA` distinct de `0` ;
  - taille inférieure à 150 ko (environ 5 ko pour une semaine synthétique) ;
- contenu du digest, absence de mots d'interprétation, prévu vs réalisé, semaine vide.

## 5. Questions pour vous

1. **Rando contre course** : une « Sortie longue trail » prévue mais enregistrée en Rando sur la montre doit-elle compter comme réalisée ? Aujourd'hui, la réponse est non, car les familles sont distinctes.
2. **Seuils de conformité** (durée ±20 %, D+ ≥ 70 %, ≥ 70 % du temps dans la cible FC) : vous conviennent-ils ?
3. **Semaine par défaut le dimanche soir** : préférez-vous que ce soit la semaine en cours si vous faites le bilan le dimanche ?
4. **`masse_grasse`** : dans votre export, la valeur est-elle bien une fraction (0,18) ou un pourcentage (18) ?
5. **Seuil de 7 km/h entre marche et course** : il est adapté au plat, mais en montée raide on court parfois sous 7 km/h. Faut-il le faire dépendre de la pente ?
6. **Passe 2** : faut-il aussi bloquer le bouton quand elle est en erreur ou n'a jamais tourné, ou garder l'export partiel actuel ?

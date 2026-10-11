# Plan de mise en œuvre — Export coach complet

> Plan d'exécution de la spécification « HealthFollow — Export coach complet »
> (`healthfollow-spec-export-coach.md`). Ce plan dit **où** et **comment** chaque
> section de la spec s'implante dans le code actuel. Il est rédigé pour être suivi
> lot par lot, y compris en exécution autonome.

---

## 0. État des lieux (ce qui existe déjà)

| Élément | Où | Réutilisable ? |
|---|---|---|
| Parsing streaming `export.xml` (`iterparse` + `clear`) | `sainteylon_health.py` → `parse_export`, `read_workout` | Oui : base de l'ingestion |
| Accès zip / dossier, lecture GPX | `sainteylon_health.py` → `Export`, `gpx_gain`, `enrich_with_gpx` | Oui |
| Dédup séances (score de richesse) | `dedupe_workouts` | À étendre (priorité de sources configurable, journal des doublons) |
| Échantillons FC + traces GPS par séance (passe 2) | `src/detail_parser.py` → `details/*.json` | Remplacé par le cache SQLite, gardé pour Streamlit |
| Zones Karvonen | `src/zones.py`, `zone_karvonen` | Bornes codées en dur → à lire depuis la config |
| TRIMP | `src/charge.py` | Calculé sur **FC moyenne** → la spec exige **par échantillon** |
| Dérive FC (tiers) | `src/drift.py` | Remplacé par 20 premières / 20 dernières min + Pa:HR |
| Journal | `src/journal.py` → `journal.json` (saisi dans Streamlit) | Garder comme source, l'exposer en `journal.csv` |
| Paramètres FC | `src/config.py` → `sortie-sante/params.json` | À remplacer par `config/athlete.toml` |

### Bugs / incohérences relevés dans le code actuel

1. **Digest en % FCM** : `digest_markdown` affiche `pct_fcmax(...)% FCM` à côté de la zone → source de la confusion « 164 bpm = Z5 94 % FCM ». À retirer au profit de Karvonen + bornes en bpm.
2. **Semaines manquantes** : `weekly_series` ne crée une semaine que si elle contient des données → une semaine vide (ou hors `--since`) disparaît. Explique probablement le trou S-14. Il faut générer le calendrier complet début de prépa → aujourd'hui.
3. **« Nocturne »** : heuristique `heure >= 19 ou < 7` → remplacer par le calcul soleil (NOAA).
4. **Heure naïve** : `parse_dt` jette le décalage `+0200` ; risque d'erreur au passage à l'heure d'hiver (25/10/2026). Conserver l'offset, convertir en `Europe/Paris` via `zoneinfo`.
5. **Deux formats d'identifiant de séance** : `journal.workout_id` (`AAAA-MM-JJ_HHMM_Type`) vs `detail_parser.workout_filename`. La spec demande un hash : voir décision D3.

---

## 1. Décisions à valider avant de lancer

| # | Question | Proposition par défaut |
|---|---|---|
| D1 | **Course cible** : la spec dit *SaintéLyon Trace, 05/12/2026, 44 km / 1 150 m D+* ; le code et la Roadmap disent *SaintExpress, 28/11/2026, 45 km / 1 200 m D+*. | Lire depuis la config. Les numéros de semaine de la spec (S-14 = 24/08→30/08, S-12 = 07/09→13/09) **correspondent au 05/12** : je prends cette date. |
| D2 | **Branche** : la spec dit `feature/coach-export`. | Utiliser la branche de travail courante, ou créer `feature/coach-export` : à confirmer. |
| D3 | **`workout_id`** | `sha1(debut_ISO_avec_offset + type)[:12]`, **plus** une colonne `journal_key` (ancien format) pour ne pas casser `journal.json`. |
| D4 | **Journal** : la spec veut `journal.csv`, l'app écrit `journal.json`. | `journal.json` reste la source (Streamlit). `journal.csv` est **généré** à partir du JSON + les champs nouveaux saisis via `healthfollow log` (stockés dans le même JSON). Une seule source de vérité. |
| D5 | **Format config** | TOML (`tomllib`, Python ≥ 3.11) avec repli JSON si Python 3.10. `config/athlete.toml` **ignoré par git**, `config/athlete.example.toml` versionné. |
| D6 | **`planning-hebdo.md`** absent du dépôt | Fournir un exemple anonymisé pour les tests ; le vrai fichier reste hors git (chemin dans la config). |
| D7 | **Modèle GAP** | Minetti 2002 (coût énergétique polynomial selon la pente), lissage de la pente sur 50 m, pente bornée à ±45 %. |

---

## 2. Architecture cible

Nouveau paquet **stdlib uniquement** (pas de pandas) : il tourne en CLI de nuit, indépendamment de Streamlit. Les pages Streamlit pourront ensuite lire ses sorties.

```
healthfollow/
├── __main__.py        # CLI : ingest | build | pack | log | check
├── config.py          # chargement athlete.toml + valeurs par défaut + validation
├── timeutil.py        # parsing avec offset, Europe/Paris, semaines ISO, S-XX
├── ingest.py          # iterparse export.xml → SQLite (reprend parse_export/read_workout)
├── store.py           # schéma SQLite + accès (data/healthfollow.sqlite, hors git)
├── dedup.py           # dédup séances et records par plage horaire + priorité de sources
├── sun.py             # lever/coucher NOAA (stdlib)
├── hr.py              # zones, temps en zone interpolé, TRIMP par échantillon, dérive, qualité FC
├── gpx.py             # parsing GPX, lissage altitude, D+/D−, pente, GAP, splits, segments, marche/course
├── workouts.py        # assemble workouts.csv enrichi (§3)
├── daily.py           # daily.csv enrichi (§6) : HRV nuit, sommeil par phases, baselines, ATL/CTL/ACWR, flags
├── weekly.py          # weekly.csv enrichi (§7), calendrier complet
├── journal.py         # journal.csv, commande log, appariement journal ↔ séance
├── plan.py            # parsing planning-hebdo.md + plan_vs_real.csv (§9)
├── pack.py            # coach_pack/ + digest.md (§10), contrôles de taille et confidentialité
├── check.py           # contrôles qualité (§11), code retour ≠ 0
└── csvio.py           # écriture CSV `;`, NA, arrondis
tests/
├── fixtures/          # mini export.xml + GPX + planning synthétiques
└── test_*.py          # un fichier par module
config/athlete.example.toml
```

- `sainteylon_health.py` devient une **façade** : mêmes arguments, mêmes 4 fichiers, mêmes colonnes en tête (les nouvelles s'ajoutent à droite). `src/sidebar.py` continue de l'appeler sans changement.
- `pyproject.toml` minimal avec `[project.scripts] healthfollow = "healthfollow.__main__:main"` ; `python -m healthfollow` marche aussi.

### Cache SQLite (après `ingest`)

| Table | Contenu |
|---|---|
| `workouts` | id, journal_key, type, début/fin (UTC + offset), durée, distance, énergie, source, indoor, météo, D+/D− métadonnées, json métadonnées |
| `workout_events` | pauses / reprises / segments |
| `samples` | type, t_debut, t_fin, valeur, source (FC, HRV, puissance, foulée, pas…) — index (type, t_debut) |
| `sleep` | début, fin, phase (Core/Deep/REM/Awake/InBed), source |
| `routes` | workout_id, t, lat, lon, ele — **jamais exporté** |
| `ingest_log` | doublons écartés, types absents, anomalies |

`ingest` est incrémental (`--since`) : il remplace les lignes ≥ `since` sans toucher au reste.

---

## 3. Lots de réalisation

Chaque lot = un ou plusieurs commits, tests verts, et peut être la fin de la session si on manque de temps (ordre de la spec §13).

### Lot 1 — Config + zones Karvonen (spec §1)
- `config.py`, `config/athlete.example.toml`, ajout de `config/athlete.toml` au `.gitignore`.
- `hr.zone_bounds(cfg)` / `hr.zone_of(bpm, cfg)` ; `src/zones.py` et `zone_karvonen` délèguent à ces fonctions.
- Digest : suppression du `% FCM`, en-tête « Paramètres : Karvonen, FCM 185, FC repos 51, Z1…Z5 = [bornes bpm] ».
- **Tests** : 164 bpm → Z4 ; bornes exactes ; config incomplète → valeurs par défaut.

### Lot 2 — Ingestion streaming + dédup + métriques FC (spec §2, §3 partie FC)
- `ingest.py` : tous les types du tableau §2 ; offset conservé ; lecture `WorkoutEvent`, `MetadataEntry` (météo, indoor, élévation), `WorkoutRoute/FileReference`.
- `dedup.py` : chevauchement > 50 % même type → garder la source prioritaire (`[sources] priorite = ["Watch", "WorkOutDoors", "Zwift", "iPhone"]`), journaliser.
- `hr.py` :
  - temps en zone par **interpolation linéaire**, trous > 30 s exclus ;
  - TRIMP Banister **par échantillon** (facteur 1,92 H / 1,67 F selon `sexe`) ;
  - FC 20 premières / 20 dernières min, `derive_fc_bpm`, FC min/max ;
  - `qualite_fc` : % de trous, artefacts (> 200 bpm, sauts > 30 bpm / 5 s) → `ok` / `douteux` / `inexploitable`.
- `sun.py` : NOAA → `pct_nuit`, `nocturne` (coordonnées du 1er point GPX sinon `lieu_defaut`).
- **Tests** : fixture XML avec doublon Watch/iPhone, passage à l'heure d'hiver, séance avec trou de 2 min, TRIMP de référence calculé à la main.

### Lot 3 — GPX : splits, D+/D−, GAP, découplage, marche/course, segments (spec §3, §4, §5)
- Lissage altitude (moyenne glissante + hystérésis 1 m, comme `gpx_gain`) → D+ / D−, `dplus_source`.
- Vitesse lissée, pente sur 50 m, **GAP Minetti**, `ef`, `decouplage_pct` (≥ 40 min, hors pauses, sur GAP).
- Classification par point : arrêt < 1 km/h ; marche < 7 km/h **et** cadence < 140 ppm (seuils en config) → `t_course/marche/arret_min`.
- `splits.csv` (1 ligne/km), `segments.csv` (montées/descentes > 30 m continues, vitesse verticale m/h).
- `hr_samples/<id>.csv` rééchantillonné à 5 s (option `--samples`), sans lat/lon.
- Métriques course (puissance moy. / normalisée, foulée, contact sol, oscillation, cadence) moyennées sur la fenêtre de la séance ; `NA` si absentes.
- `qualite_gps` : sauts, vitesse > 25 km/h à pied.
- **Tests** : trace synthétique 3 km avec une côte de 60 m à 10 % → D+ attendu, 3 splits, 1 segment ; GAP en côte < allure réelle ; découplage nul sur effort constant.

### Lot 4 — Journalier (spec §6)
- HRV **pendant la fenêtre de sommeil** uniquement ; sommeil par phases, éveils, coucher/lever, régularité du coucher sur 7 j.
- Moyennes glissantes 7 j / 28 j, écarts-types, z-scores HRV et FC repos ; `temp_poignet_delta`, `spo2_nuit`, pas, énergie active.
- `trimp_jour`, ATL (EWMA 7 j), CTL (EWMA 42 j), TSB, ACWR (total et course).
- `flag_recup` : règle documentée, par ex. rouge si `hrv_z ≤ −1,5` **ou** `fc_repos_z ≥ 1,5` ; orange si l'un ≤ −1 / ≥ 1 **ou** sommeil < 6 h ; sinon vert ; `NA` si données insuffisantes.
- `flag_voyage` : journal en priorité, sinon heuristique (coucher décalé > 2 h vs médiane 28 j + pas hors de [P10, P90]).
- `NA` ≠ 0 partout (jour sans mesure ≠ jour à zéro ; séance absente = TRIMP 0 seulement si la montre était portée).
- **Tests** : EWMA sur série connue, z-score, nuit à cheval sur minuit, jour sans données → `NA`.

### Lot 5 — Hebdomadaire + régénération de l'historique (spec §7)
- Calendrier continu du début de prépa (config `objectif.debut_prepa`) à aujourd'hui ; semaine vide = ligne avec zéros explicites et `NA` pour les mesures.
- Toutes les colonnes §7 (`nb_seances_prevues/conformes` remplies au lot 7).
- **Tests** : semaine vide présente ; S-14 = 24/08→30/08 avec la date de course retenue.

### Lot 6 — Journal (spec §8)
- Champs nouveaux (genou G, lendemain, fatigue, motivation, stress, couches, chaussures, nutrition, séance non faite + raison, voyage) ajoutés au schéma de `journal.json`.
- `healthfollow log [--date]` : questions successives en terminal, Entrée = laisser vide.
- Export `journal.csv` ; appariement par `workout_id`, sinon date + type + heure la plus proche.
- La page Streamlit Journal pourra afficher ces champs dans un second temps (hors périmètre).

### Lot 7 — Prévu vs réalisé (spec §9)
- Parseur des tableaux Markdown de `planning-hebdo.md` (en lecture seule) ; plages FC `135-145`, `≤ 150`, `Z1/Z2` → bpm via la config.
- Appariement même jour ± 1, même famille d'activité ; `pct_temps_dans_cible` depuis les échantillons FC.
- `statut_propose` : ✅ (durée ± 15 % et ≥ 70 % du temps dans la cible), 🔄 (réalisée mais hors critères), ❌ (non trouvée), `hors_plan`.
- **Tests** : planning exemple de 5 séances, 1 manquée, 1 hors plan.

### Lot 8 — Pack coach + digest (spec §10)
- `coach_pack/` avec les 8 fichiers ; digest selon la structure de la spec, **descriptif uniquement**.
- Section « Saisie manuelle » : lignes `à compléter` explicites si le journal est vide.
- Section « Anomalies » : générée depuis `ingest_log`, `qualite_fc`, z-scores extrêmes.
- Contrôles intégrés : `digest.md` < 25 ko, CSV semaine < 100 ko (sinon on tronque les colonnes secondaires et on le signale) ; recherche de `lat`/`lon`/noms d'appareil dans le pack → échec si trouvés.
- `coach_pack/` ajouté au `.gitignore`.

### Lot 9 — `check` + rapport (spec §11, §12)
- `healthfollow check` : splits ≈ km (± 2 %), D+ GPX vs métadonnée (> 20 % → avertissement), Σ zones ≈ durée active (± 5 %), aucune semaine manquante, 164 bpm → Z4.
- `NIGHT_RUN_REPORT.md` à la racine : résumé, données introuvables, choix de conception, anomalies, résultats des tests et de `check`, commandes, questions.

---

## 4. Rétrocompatibilité — liste de contrôle

- [ ] `python3 sainteylon_health.py export.zip` produit toujours `workouts.csv`, `daily.csv`, `weekly.csv`, `digest.md` dans `sortie-sante/`.
- [ ] Les colonnes existantes gardent nom, ordre et séparateur `;` ; les nouvelles sont ajoutées à droite.
- [ ] `src/sidebar.py`, `src/detail_parser.py` et les pages Streamlit fonctionnent sans modification.
- [ ] `journal.json` existant est relu tel quel.
- [ ] Aucune nouvelle dépendance obligatoire.

## 5. Confidentialité

- `data/healthfollow.sqlite`, `config/athlete.toml`, `coach_pack/`, `hr_samples/`, `journal.csv`, `planning-hebdo.md` → `.gitignore`.
- Les fixtures de test sont **synthétiques** (coordonnées fictives, pas d'export réel).
- Le pack ne contient ni coordonnées, ni nom de source contenant un prénom (« Apple Watch de Julien » → `Watch`).

## 6. Utilisation finale visée

```bash
healthfollow ingest --export ~/Downloads/export.zip --since 2026-06-01
healthfollow build
healthfollow pack --week 2026-W37     # S-12 (07/09 → 13/09)
healthfollow pack                     # semaine en cours
healthfollow check
```
Puis glisser le dossier `coach_pack/` dans le Project Claude.

## 7. Estimation

| Lots | Volume indicatif |
|---|---|
| 1–2 | ~600 lignes + tests — le socle, à faire en priorité |
| 3 | ~500 lignes — le plus délicat (GPX, GAP, segments) |
| 4–5 | ~400 lignes |
| 6–7 | ~350 lignes |
| 8–9 | ~400 lignes |

Si une seule session ne suffit pas : s'arrêter après le lot 5 donne déjà des CSV corrects et complets ; les lots 6 à 9 ajoutent le confort de saisie, le prévu/réalisé et le pack.

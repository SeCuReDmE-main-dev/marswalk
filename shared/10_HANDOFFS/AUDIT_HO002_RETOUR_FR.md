# Retour HO-002 — quatre revues du moteur et du pack

J'ai fait examiner les quatre périmètres demandés dans quatre contextes Codex distincts, sur un checkout isolé de `main` au commit `e38ceba70e9c6273cf35233d3255cd912a7a4809`.

**Ce sont des revues Codex, pas des sessions Antigravity ni une certification NASA.** J'ai utilisé la même machine et l'environnement Python déjà installé. Les fichiers sources provenaient du checkout isolé ; le cache brut NASA/USGS de la copie de travail frontend n'a pas été copié. Le dossier `datalake/` contenait seulement les deux fichiers suivis `.gitkeep` et `README.md`.

## Les livrables

| Rapport demandé | Périmètre | Tests de la tranche |
|---|---|---|
| [Audit 01](NASA_AUDIT_01_GEODESY_DTM_OBSTACLES.md) | Coordonnées, DTM, obstacles, données externes et calibration | 10 réussis, 1 ignoré |
| [Audit 02](NASA_AUDIT_02_PLITHOGENIC_FUNNEL_ASTAR.md) | Fusion, funnel, gates, A*, benchmarks | 45 réussis, 5 ignorés |
| [Audit 03](NASA_AUDIT_03_XEVA_HUMAN_RF_RADIATION.md) | Effort, oxygène, radio, rayonnement et caméras | 16 réussis, 1 ignoré |
| [Audit 04](NASA_AUDIT_04_PACK_MIDDLEWARE_API_DOCS.md) | Contrats, pack, API, carte SVG et documentation | 29 réussis, 2 ignorés |

J'ai aussi exécuté la suite complète : **102 tests réussis, 9 ignorés, aucun échec, code de sortie 0**. Les neuf tests ignorés dépendent du DTM brut absent. Je ne présente donc pas le résultat comme conforme à la règle « zéro test ignoré ». Je n'ai changé aucun test ni seuil pour obtenir ce résultat.

Chaque rapport distingue ce que j'ai vérifié, ce qui échoue dans un exemple reproductible, et ce qui reste incomplet. Les scripts, entrées des exemples et sorties sont dans [audit_evidence/](audit_evidence/). Les logs partagés remplacent uniquement les préfixes de chemins locaux ; les sorties brutes exactes sont conservées localement. Le runner interdit les connexions Python externes pendant pytest et autorise localhost pour le client de test Windows. Ce contrôle n'est pas une sandbox réseau pour les bibliothèques natives. Aucun produit brut NASA/USGS n'a été téléchargé pour reconstituer le cache.

## Les corrections à traiter en priorité

1. **Conserver les données manquantes et les obstacles.** Un trou NoData peut être remplacé par une surface plate ; un escarpement continu placé sur une frontière de cases peut disparaître de la grille bloquée. Le buffer ne démontre pas non plus la marge physique annoncée pour toute la case.
2. **Appliquer les veto aux vraies entrées physiques.** Le funnel peut écarter une pente 4 m de 25° dans l'exemple testé. Le pipeline réduit et plafonne la distance de retour avant de la comparer à la limite. Les gates peuvent aussi améliorer des métriques sans recalculer les preuves correspondantes.
3. **Revoir la radio et ses limites de résolution.** Les exemples du rapport 03 montrent une correction Bullington absente et un relief étroit manqué par l'échantillonnage. Ces cas donnent un résultat trop favorable par rapport au modèle annoncé.
4. **Corriger les valeurs et les étiquettes scientifiques.** La table Minetti, certaines prédictions étiquetées `MEASURED`, les hypothèses d'oxygène et plusieurs chiffres du README nécessitent une correction ou une qualification explicite.
5. **Durcir la couverture d'intégrité et la réponse API.** Une entrée de hash manquante n'empêche pas toujours le chargement d'un fichier essentiel. Une image changée après le chargement initial peut être servie sans revalidation. Certaines erreurs d'initialisation renvoient HTTP 500 plutôt que la réponse fail-safe annoncée.

Ces exemples synthétiques établissent des défauts de composants ou de garanties annoncées. Je n'ai pas démontré qu'un parcours actuel du pack est dangereux. Les scripts précisent leurs préconditions pour éviter cette confusion.

## Ce qui tient dans les vérifications exécutées

J'ai vérifié les 17 fichiers listés du pack et rejeté une mutation d'un octet de chacun d'eux. Les cinq schémas régénérés et la carte SVG correspondent octet pour octet aux fichiers commis. Les 22 767 quantités examinées référencent un identifiant de source connu. Les onze URL du manifest ont répondu HTTP 200 à une requête HEAD ; cela ne valide pas le contenu scientifique de leurs fichiers.

Les exemples indépendants vérifient aussi l'admissibilité et l'optimalité du graphe M2 sur les cas testés, ainsi que son supercover et ses protections de coins. Ces résultats ne valident pas automatiquement l'extraction d'obstacles, le lissage ou les modèles physiques qui alimentent ce graphe.

Pour Sol 700, j'ai conservé la distinction entre le point exact, la case au centre le plus proche et la case déduite des limites de grille. Les valeurs 12,649°, 11,19° et 13,31° à 64 m ne décrivent pas le même support spatial ; les substituer sans le préciser créerait un faux constat d'erreur.

## Statut de la demande

J'ai livré les quatre rapports et leurs preuves, avec des propositions de corrections ciblées. Je n'ai modifié ni le moteur, ni le pack, ni les schémas, ni les tests, ni le frontend. Je n'ai pas fermé de phase ou changé un verdict d'audit existant.

Le protocole exact demandé reste partiellement réalisé : les quatre revues sont faites dans Codex, sur la même machine, et les vérifications nécessitant le cache DTM brut n'ont pas été exécutées. Je laisse HO-002 intact et j'enregistre le retour dans un nouveau handoff, sans déclarer que j'ai exécuté quatre sessions Antigravity sur une machine physiquement indépendante.

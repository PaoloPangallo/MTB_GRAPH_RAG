# 11 — RQ1 ripetuto su v3

Ripetizione integrale del test RQ1 sul repository v3. Gli artefatti dell'audit
precedente (`evaluation/rq1_graph_candidate_fidelity/`) **non sono stati
sovrascritti**: i risultati v3 stanno in `evaluation/gca_v3/`.

## Metodo

I path eleggibili sono riderivati **indipendentemente** dai CSV
(`evaluation/rq1/kg_source.py`), non rieseguendo il materializzatore v3.
Rieseguire lo stesso materializzatore misurerebbe soltanto il suo determinismo.

## Misure strutturali

| Metrica | v2 | v3 |
|---|---|---|
| Path sorgente eleggibili | 46 864 | 46 864 |
| Candidate materializzate | 46 864 | 46 142 |
| `structural_precision` | 1.0 | **1.0** |
| `structural_recall` | 1.0 | **1.0** |
| `payload_reproducibility` | 1.0 | **1.0** |
| `duplicate_rate` | 0.0 | **0.0** |
| `lineage_integrity` | 1.0 | **1.0** |

La fedeltà strutturale non è regredita.

## Misure semantiche

| Criterio §19 | Obiettivo | v3 |
|---|---|---|
| `source_polarity_lost` | 0 | **0** ✅ |
| `unsupported_candidates_promoted_as_supported` | 0 | **0** ✅ |
| `automatic_direction_inversions` | 0 | **0** ✅ |
| `compound_alteration_terms_lost` | 0 | **0** ✅ |
| `compound_operator_lost` | 0 | **0** ✅ |
| `unresolved_regimens_split_into_positive_components` | 0 | **0** ✅ |
| `invented_regimen_semantics` | 0 | **0** ✅ |
| `broken_lineage` | 0 | **0** ✅ |

Metriche descrittive:

| Metrica | Valore |
|---|---|
| `compound_expression_parse_failures` | 0 |
| `compound_alterations_preserved` | 1 010 |
| `single_agent_count` | 35 046 |
| `confirmed_regimen_count` | 0 |
| `unresolved_regimen_count` | 572 |

## Invarianti del contratto

Verificate su **tutte** le 46 142 candidate: **nessuna violazione**.

| Invariante | Violazioni |
|---|---|
| INV1 — ogni candidate ha almeno un `source_path_id` | 0 |
| INV2 — `DOES_NOT_SUPPORT` non può essere `SOURCE_ALIGNED` | 0 |
| INV2B — direzione sostenuta solo se la fonte sostiene | 0 |
| INV3 — i termini analizzati compaiono tutti nell'AST | 0 |
| INV4 — un regime irrisolto ha ≥ 2 componenti | 0 |
| INV5 — nessuna combinazione confermata senza semantica di sorgente | 0 |
| INV6 — `candidate_id` e `payload_hash` deterministici | 0 |

## Confronto con i tre difetti dell'audit v2

| Difetto v2 | Candidate v2 | Candidate v3 |
|---|---|---|
| `DIRECTION_INVERSION` | 486 | **0** — la polarità è un campo, non un'inferenza |
| `ALTERATION_LOST` | 1 091 | **0** — tutti i termini conservati |
| `REGIMEN_SPLIT` | 1 294 | **0** — 572 unità conservate |
| **Unione** | **2 419 (5.16 %)** | **0** |

## Campione manuale

`evaluation/gold/rq1_gca_v3_manual_review.csv` — **70 record**, colonne del
revisore vuote.

| Strato | Richiesti | Ottenuti |
|---|---|---|
| `source_aligned_simple` | 15 | 15 |
| `does_not_support` | 15 | 15 |
| `neutral_no_difference` | 10 | 10 |
| `compound_alteration` | 15 | 15 |
| `multi_drug` | 15 | 15 |
| **`unparsable_or_ambiguous`** | **5** | **0** |

Lo strato dei casi non parsabili o ambigui è **vuoto perché il corpus non ne
contiene**: 0 fallimenti di parsing su 1 939 profili, 0
`SOURCE_ALIGNMENT_UNCLEAR`, 0 `alteration_parse_warnings`. Il campione è di 70
record invece di 75; riempirlo avrebbe richiesto di etichettare come ambigui casi
che non lo sono.

## Cosa non è stato dimostrato

* Che v3 sia **clinicamente** più corretta: il livello D non è valutato.
* Che le 572 unità irrisolte siano tutte combinazioni: è dimostrato che l'export
  non consente di stabilirlo.
* Che la policy di ammissione produca dossier migliori: non è stata integrata.

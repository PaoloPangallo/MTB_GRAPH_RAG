# 00 — Decision record

## Contesto

L'audit RQ1 su `graph_candidate_repository/2.0` ha misurato fedeltà strutturale
perfetta (precision 1.0, recall 1.0, field fidelity 1.0 su 16 campi) e, allo
stesso tempo, tre perdite semantiche sistematiche:

| Perdita | Candidate v2 |
|---|---|
| Polarità della fonte non rappresentata | 486 |
| Alterazioni composte ridotte a un termine | 1 091 |
| Regimi spezzati in componenti individuali | 1 294 |

Le tre non erano bug di implementazione: erano conseguenze del **contratto**.

## Decisione

Produrre `graph_candidate_repository/3.0` con un contratto nuovo,
`graph-candidate-assertion/3.0`, conservando `2.0` immutato come baseline
sperimentale storica.

Il cambio è **major** perché cambia il significato degli oggetti, non solo la
loro serializzazione: un consumatore di v2 che leggesse v3 assumendo la vecchia
semantica sbaglierebbe: `direction` non è più un campo unico, e una candidate
`evidence-to-intervention` non è più «un farmaco» ma «l'intervento del record».

## Distinzione metodologica adottata

| | Definizione | v2 | v3 |
|---|---|---|---|
| **STRUCTURAL_FIDELITY** | fedeltà della serializzazione alle regole implementate | 1.0 | 1.0 |
| **SEMANTIC_SOURCE_FIDELITY** | capacità del contratto di conservare il significato disponibile nella sorgente | perdite su 2 419 candidate | perdite = 0 |

L'obiettivo **non** era riprodurre v2 byte-identicamente: era preservare in modo
verificabile l'informazione che v2 appiattiva.

## Cosa la sorgente permetteva

L'audit dei CSV (`01_source_semantics_audit.md`) ha stabilito, prima di
qualunque design:

| Problema | Informazione nella sorgente | Correzione |
|---|---|---|
| Polarità | **completa** — `evidence_direction` su nodo e arco, coincidenti su tutti i 3 370 archi | **integrale** |
| Alterazioni composte | **completa** — grammatica regolare, corroborata dagli archi su 197/197 profili | **integrale** |
| Regimi | **assente** — nessuna colonna descrive la relazione fra farmaci | **impossibile** |

Il terzo caso è il più importante: la correzione corretta non è ricostruire il
regime, ma smettere di affermare implicitamente che ogni farmaco porta
individualmente la direzione del record.

## Alternative considerate e scartate

| Alternativa | Perché scartata |
|---|---|
| Convertire v2 → v3 senza rimaterializzare | Ciò che v2 ha perso non è più nell'artefatto: le varianti scartate e la polarità non sarebbero recuperabili |
| Dedurre il regime dal numero di farmaci | Inferenza non supportata; §12 la vieta |
| Dedurre il regime dal testo dello statement o dal titolo del paper | Userebbe il documento come fonte nascosta in una fase che non lo legge |
| Convertire `Does Not Support Resistance` in `Supports Sensitivity` | Falso: la fonte riporta tipicamente *nessuna differenza*, non l'effetto opposto |
| Sostituire v2 nel runtime | §17 richiede configurazione esplicita; il default resta `2.0` |
| Aggiungere il mapping BGJ398 → infigratinib | Fuori scopo; resta `KNOWN_DRUG_SYNONYM_GAP` |

## Esito

| Criterio §19 | Valore |
|---|---|
| `source_polarity_lost` | **0** |
| `unsupported_candidates_promoted_as_supported` | **0** |
| `automatic_direction_inversions` | **0** |
| `compound_alteration_terms_lost` | **0** |
| `compound_operator_lost` | **0** |
| `unresolved_regimens_split_into_positive_components` | **0** |
| `invented_regimen_semantics` | **0** |
| `broken_lineage` | **0** |

Strutturalmente: `structural_precision = 1.0`, `structural_recall = 1.0`,
`payload_reproducibility = 1.0`, `duplicate_rate = 0.0`.

## Stato

`EXPERIMENTAL_NOT_RUNTIME_DEFAULT`. v3 non è collegata al runtime, il
Pre-Retrieval Eligibility Gate non è stato introdotto, e
`evaluate_alteration_expression` è definita e testata ma non chiamata da alcun
modulo del runtime.

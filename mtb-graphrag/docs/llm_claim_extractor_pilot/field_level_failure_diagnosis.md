# Diagnosi field-level delle tre proposte flat 1.2

Le quote sono conservate nei report macchina solo tramite hash, lunghezza e conteggio delle occorrenze. Il testo documentale non ? committato.

## EB-b4c48ba003913f278ff182a6

Baseline B: `DIRECT`; validatore MiniMax: `REJECTED_UNGROUNDED`; status finale: non calcolato.

| Campo | Valore proposto | SourceUnit | Quote | Categoria | Candidate leakage |
|---|---|---|---|---|---|
| disease | `metastatic colorectal cancer` | `SU-12a97ff4a9065ff0947b17c7, SU-6e4d5a52c9be05f545487ad0, SU-4c4ce81824f39e09575501ab` | 2 occorrenze; hash redatto | OTHER_SEMANTIC_FAILURE | False |
| biomarker | `KRAS mutations` | `SU-6e4d5a52c9be05f545487ad0, SU-4c4ce81824f39e09575501ab` | 2 occorrenze; hash redatto | OTHER_SEMANTIC_FAILURE | False |
| intervention | `panitumumab` | `SU-12a97ff4a9065ff0947b17c7, SU-6e4d5a52c9be05f545487ad0, SU-4c4ce81824f39e09575501ab` | 4 occorrenze; hash redatto | OTHER_SEMANTIC_FAILURE | True |
| direction | `Resistance` | `SU-6e4d5a52c9be05f545487ad0, SU-4c4ce81824f39e09575501ab` | 2 occorrenze; hash redatto | OTHER_SEMANTIC_FAILURE | True |
| negation | `False` | `-` | - occorrenze; hash redatto | MISSED_NEGATION | False |
| contradiction | `False` | `-` | - occorrenze; hash redatto | OTHER_SEMANTIC_FAILURE | False |

Reason code validatore: `DROPPED_GRAPH_ONLY, DROPPED_GRAPH_ONLY, DROPPED_GRAPH_ONLY, DROPPED_GRAPH_ONLY, NO_GROUNDED_FIELDS`.

## EB-2ae853e8abf1195cc4c84846

Baseline B: `PARTIAL`; validatore MiniMax: `REJECTED_UNGROUNDED`; status finale: non calcolato.

| Campo | Valore proposto | SourceUnit | Quote | Categoria | Candidate leakage |
|---|---|---|---|---|---|
| disease | `non-small cell lung cancer` | `SU-85b873d9e71a5bfd4adba10e, SU-2f2b8a24fa60fde080f2d79c` | 2,2 occorrenze; hash redatto | OTHER_SEMANTIC_FAILURE | False |
| biomarker | `EGFR T790M` | `SU-9b966cc43a666add1d24c54f, SU-2f2b8a24fa60fde080f2d79c` | 2,1 occorrenze; hash redatto | OTHER_SEMANTIC_FAILURE, VALUE_NOT_IN_QUOTE | False |
| intervention | `None` | `-` | - occorrenze; hash redatto | OTHER_SEMANTIC_FAILURE | False |
| direction | `None` | `-` | - occorrenze; hash redatto | OTHER_SEMANTIC_FAILURE | False |
| negation | `False` | `-` | - occorrenze; hash redatto | MISSED_NEGATION | False |
| contradiction | `False` | `-` | - occorrenze; hash redatto | OTHER_SEMANTIC_FAILURE | False |

Reason code validatore: `DROPPED_GRAPH_ONLY, DROPPED_NO_QUOTE, NO_GROUNDED_FIELDS`.

## EB-6a291f12975b20b79e1c3dd7

Baseline B: `CONTRADICTED`; validatore MiniMax: `REJECTED_DIRECTION`; status finale: non calcolato.

| Campo | Valore proposto | SourceUnit | Quote | Categoria | Candidate leakage |
|---|---|---|---|---|---|
| disease | `"lung cancer"` | `SU-fc4994778b8b27071aec221e` | 1,1 occorrenze; hash redatto | EXACT_QUOTE_VALID | False |
| biomarker | `"FGFR1-amplified"` | `SU-fc4994778b8b27071aec221e` | 1 occorrenze; hash redatto | EXACT_QUOTE_VALID | False |
| intervention | `"BGJ398"` | `SU-fc4994778b8b27071aec221e` | 0 occorrenze; hash redatto | QUOTE_NOT_FOUND | False |
| direction | `"single-agent activity"` | `SU-fc4994778b8b27071aec221e` | 1 occorrenze; hash redatto | EXACT_QUOTE_VALID | False |
| negation | `False` | `SU-fc4994778b8b27071aec221e` | 1 occorrenze; hash redatto | MISSED_NEGATION | False |
| contradiction | `False` | `SU-fc4994778b8b27071aec221e` | 1 occorrenze; hash redatto | MISSED_CONTRADICTION | False |

Reason code validatore: `ACCEPTED_FIELD, ACCEPTED_FIELD, DROPPED_GRAPH_ONLY, DROPPED_DIRECTION_CONFLICT`.

## Sintesi

- Nessun SourceUnit ID errato.
- Le quote ripetute sono state marcate come occorrenze ambigue; non sono state dichiarate troncate senza prova.
- Nel DIRECT valori e quote erano presenti ma non disambiguabili, quindi nessun campo ? entrato nella validazione semantica come grounded.
- Nel PARTIAL il modello ha prodotto valori parziali, ma le quote non hanno consentito una proposta completa.
- Nel CONTRADICTED la direction proposta non ? compatibile con la regola deterministica e `contradiction_detected` ? rimasto falso: il validatore ha bloccato la proposta.

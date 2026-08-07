# 00 — Contratto reale del dossier canonico

Ricostruito **eseguendo** quattro run REPLAY reali e leggendo l'output di
`stage_13_dossier`, non leggendo il solo codice.
Campione: `evaluation/dossier_narrator/raw/A01_real_dossiers.json`.

| | |
|---|---|
| Costruito da | `backend/research_pipeline/dossier/builder.py` |
| `dossier_version` | `end-to-end-pilot-dossier/1.0` |
| Esposto alla UI da | `backend/api/research_routes.py::get_dossier` |
| Reso da | `frontend/src/research/DossierView.tsx` |
| Hash builder | `8458325f73a1bbcb` |
| Runtime GCA | `graph_candidate_repository/2.0` |

## Schema effettivo

```
dossier
├── case_id                      str
├── case_context                 dict — biomarkers, case_id, clinical_question,
│                                       disease, previous_interventions,
│                                       query_intent, target_intervention, uncertainties
├── case_context_verification    dict — records[], essential_fields_pass, warnings[]
├── candidate_therapies          list
│   └── entry
│       ├── candidate_id         str    "GCA-…"
│       ├── drug                 str|None  maiuscolo: "PANITUMUMAB"
│       ├── graph_relation       str    "associated_with_resistance_to" | "associated_with_sensitivity_to"
│       ├── status               str    DIRECT|PARTIAL|AMBIGUOUS|CONTRADICTED|DISCOVERED|NO_MATCH
│       ├── warnings             list[str]
│       ├── gate_results
│       │   ├── bucket           PRIMARY_BUCKET|WARNING_BUCKET|REJECTED_BUCKET|DISCOVERY_BUCKET
│       │   └── support_mask     {disease, biomarker, intervention, direction}
│       ├── document_support
│       │   ├── selected_papers  list[str]  bundle_id
│       │   └── excluded_papers  list[{bundle_id, document_id, reason_codes[]}]
│       ├── author_context       list  ← proposte del modello, ANNOTATE
│       └── validation_results   list[{paper_id, outcome, reason_codes[]}]
├── limitations                  list[str]
└── provenance
    ├── dossier_kind, dossier_version
    ├── gemma_role               "paper_context_enricher_only"
    ├── gemma_never_decides      [support_status, direction, contradiction, gate, score, bucket]
    └── not_wired_to_production_runtime
```

### `author_context` — la voce completa

```
decision                 QUOTE | ABSTAIN
author_claim_quote       str
author_context_summary   str
abstention_reason        str
source_unit_id           str
paper_id                 str
candidate_id, case_id
enrichment_id, payload_hash, lineage{...}
model, prompt_version, transport_version, timestamp
validation_outcome       ENRICHMENT_V2_ACCEPTED | REJECTED_QUOTE_NOT_FOUND | …
validation_reason_codes  list[str]
presentation_state       VALIDATED_QUOTE | REJECTED_QUOTE | ABSTAINED | PROPOSED_QUOTE_NOT_VALIDATED
accepted_for_gates       bool
```

Gli ultimi quattro campi provengono dalla chiusura di ISS-003: sono ciò che
rende possibile costruire una projection sicura per il Narrator.

## Vocabolari chiusi, letti dal codice

```
STATUS_VALUES        DIRECT · PARTIAL · AMBIGUOUS · CONTRADICTED · DISCOVERED · NO_MATCH
GATE_BUCKETS         PRIMARY_BUCKET · WARNING_BUCKET · REJECTED_BUCKET · DISCOVERY_BUCKET
PRESENTATION_STATES  VALIDATED_QUOTE · REJECTED_QUOTE · ABSTAINED · PROPOSED_QUOTE_NOT_VALIDATED
support_mask.direction  SUPPORTED · CONTRADICTED · UNRELATED_EVIDENCE ·
                        NO_DOCUMENT_SIGNAL · NOT_APPLICABLE · SOURCE_DOES_NOT_SUPPORT
```

## Cosa mostrano i quattro casi reali

| Caso | status | bucket | `direction` | author_context |
|---|---|---|---|---|
| CASE-1 | `PARTIAL` | `WARNING_BUCKET` | `UNRELATED_EVIDENCE` | 1 `VALIDATED_QUOTE` |
| CASE-2 | `DISCOVERED` | `DISCOVERY_BUCKET` | `NOT_APPLICABLE` | 1 `REJECTED_QUOTE` + 1 `VALIDATED_QUOTE` |
| CASE-3 | `AMBIGUOUS` | `WARNING_BUCKET` | `NO_DOCUMENT_SIGNAL` | 2 `ABSTAINED` |
| CASE-4 | `AMBIGUOUS` | `WARNING_BUCKET` | `NO_DOCUMENT_SIGNAL` | 2 `ABSTAINED` |
| CASE-5 | — | — | — | **nessun dossier**: `STOPPED / RETRIEVAL_NO_MATCH` |

Quattro osservazioni che vincolano il progetto del Narrator:

1. **Nessun caso reale è `DIRECT`.** Il campione congelato produce `PARTIAL`,
   `AMBIGUOUS` e `DISCOVERED`. Il benchmark dovrà costruire i `DIRECT`
   sinteticamente, da dossier canonici validi.
2. **CASE-2 contiene una `REJECTED_QUOTE` accanto a una validata.** È il caso
   che il Narrator non deve poter confondere: la projection deve escludere la
   prima e includere la seconda.
3. **`graph_relation` è informativa** (`…_resistance_to` / `…_sensitivity_to`) e
   va preservata: è un asse che la narrativa può descrivere ma non invertire.
4. **`excluded_papers` esiste** ed è esattamente il tipo di dato che **non**
   deve raggiungere il Narrator.

## Campi che il dossier NON contiene

Verificato: nessuna `recommendation`, nessun `evidence_level`, nessun ranking
terapeutico, nessuna narrativa. Il Narrative Verifier può quindi trattare
**qualunque** linguaggio prescrittivo nella narrativa come non autorizzato,
senza eccezioni da modellare.

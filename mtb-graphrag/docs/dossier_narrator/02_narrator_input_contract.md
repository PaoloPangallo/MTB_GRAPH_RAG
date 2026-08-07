# 02 — Contratto del NarratorInput

`dossier-narrator-input/1.0` · `backend/research_pipeline/narrative/input_projection.py`

Il Narrator **non riceve il runtime state**. Riceve una proiezione costruita da
una funzione pura: stesso dossier canonico → stesso `NarratorInput` → stesso
`narrator_input_hash`.

## Campi ammessi

```
case                 case_id · query_intent · disease · biomarkers ·
                     target_intervention · clinical_question
candidates[]         candidate_id · drug · graph_relation
                     canonical_status · gate_bucket · support_direction · support_mask
                     warnings · critical_warnings
                     selected_paper_ids
                     validated_quotes[] {quote, source_unit_id, paper_id, author_context_summary}
                     has_validated_quote · abstention_reasons
                     expresses_support · source_does_not_support   ← derivati deterministici
limitations
provenance_summary   dossier_version · dossier_kind · llm_never_decides
counts
narrator_input_hash
```

`expresses_support` e `source_does_not_support` sono calcolati qui, da dati già
presenti nel dossier, perché il modello non debba dedurli e perché il verifier
abbia un atteso esplicito contro cui confrontare.

## Campi esclusi, e perché

| Escluso | Ragione |
|---|---|
| candidate escluse dal retrieval | non sono nel dossier canonico |
| `excluded_papers` | documenti scartati: nominarli suggerirebbe evidenza |
| **quote rigettate o solo proposte** | il modello non può citare ciò che non vede |
| output grezzo dell'LLM precedente | non è evidenza |
| internals del validatore | dettaglio di implementazione |
| documenti integrali, SourceUnit non selezionate | superficie inutile e rischiosa |
| gold label, expected answer | contaminerebbero la valutazione |

Il filtro sulle quote usa `presentation_state ∈ PRESENTABLE_AS_AUTHOR_CLAIM`,
cioè **la stessa fonte di verità che ha chiuso ISS-003**. Non una seconda regola
parallela che potrebbe divergere.

Tre test lo verificano *per assenza*: la quote rigettata di CASE-2, un
`excluded_papers` e un reason code interno non compaiono nel JSON serializzato
della projection.

## Policy dei warning

```
NARRATIVE_CRITICAL   NO_VALIDATED_ENRICHMENT_AVAILABLE
                     VALIDATED_ENRICHMENT_DOES_NOT_ADDRESS_DIRECTION
                     SOURCE_POLARITY_DOES_NOT_SUPPORT / _CONTRADICTS / _NEUTRAL
TECHNICAL_ONLY       SOME_ENRICHMENTS_ACCEPTED_WITH_WARNING
```

Il §15 chiede esplicitamente di non pretendere che ogni warning tecnico venga
narrato. La distinzione è dichiarata nel codice e verificata da un test in
entrambe le direzioni: l'omissione di un warning critico fallisce, quella di un
warning tecnico no.

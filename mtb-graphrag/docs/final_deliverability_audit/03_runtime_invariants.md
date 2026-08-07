# 03 — Invarianti del runtime

Dati: `evaluation/final_deliverability/authority_boundary_recheck.json`,
`quote_validation_recheck.json`, `raw/D01_api.json`.

## §5 — Confini di autorità dell'LLM

| L'LLM può… | Classificazione | Meccanismo verificato |
|---|---|---|
| decidere l'eligibility | **IMPOSSIBLE_BY_CONSTRUCTION** | 0 riferimenti a LLM nei 10 moduli della catena deterministica |
| creare un PMID | **IMPOSSIBLE_BY_CONSTRUCTION** | `transport_v2` → `INVALID_TOOL_ARGUMENTS` |
| creare provenance | **IMPOSSIBLE_BY_CONSTRUCTION** | idem |
| creare una SourceUnit | **IMPOSSIBLE_BY_CONSTRUCTION** | idem + `SOURCE_UNIT_NOT_FOUND` |
| modificare la source polarity | **IMPOSSIBLE_BY_CONSTRUCTION** | la polarità è letta dalla candidate, mai dall'enrichment |
| assegnare il canonical status | **IMPOSSIBLE_BY_CONSTRUCTION** | `evaluate_association` non ha parametri controllati dall'LLM oltre a `evidence_kind` di enrichment già validati |
| modificare il dossier canonico | **IMPOSSIBLE_BY_CONSTRUCTION** | `status`/`mask`/`bucket` derivano da `evaluate_association` |
| accettare autonomamente una quote | **VALIDATED_DOWNSTREAM** | confronto letterale esatto, zero chiamate al modello |
| modificare bucket/status via narrativa | **VALIDATED_DOWNSTREAM** | `_STATUS_GATE_WORDS` → `REJECTED_SUMMARY_UNGROUNDED` |

```
PROMPT_ONLY_RESTRICTION = 0
UNCONTROLLED            = 0
```

Verificato eseguendo il trasporto reale su nove chiavi extra:

```
pmid · canonical_status · provenance · recommendation · source_unit
support_mask · gate_bucket · direction · evidence_direction
    → tutte INVALID_TOOL_ARGUMENTS
5 chiavi esatte → V2_TRANSPORT_VALID
```

`TOOL_SCHEMA` ha **5** proprietà. `LLM_STAGE_IDS` è **2** su 16 stage.

Due controlli semantici confermati:
`"The evidence is DIRECT and belongs in the primary bucket"` →
`REJECTED_SUMMARY_UNGROUNDED`; `"These patients should receive panitumumab"` →
`REJECTED_CLINICAL_RECOMMENDATION`.

## §6 — Catena di document grounding

Su quattro run REPLAY reali via API:

| Caso | Scenario | Esito |
|---|---|---|
| CASE-1 | documento disponibile, SourceUnit disponibile | `COMPLETED`, 1 candidate, `PARTIAL` / `WARNING_BUCKET`, 1 voce `VALIDATED_QUOTE` |
| CASE-2 | discovery | `COMPLETED`, `DISCOVERED` / `DISCOVERY_BUCKET`, 1 voce `REJECTED_QUOTE` + 1 `VALIDATED_QUOTE` |
| CASE-4 | documento senza supporto esplicito | `COMPLETED`, `AMBIGUOUS` / `WARNING_BUCKET`, 2 voci `ABSTAINED` |
| CASE-5 | nessuna candidate compatibile | `STOPPED / RETRIEVAL_NO_MATCH`, dossier **409** |

I sei livelli restano distinti e osservabili:

```
candidate         candidate_id, graph_relation
≠ document        document_support.selected_papers
≠ SourceUnit      author_context[].source_unit_id
≠ quote proposal  author_claim_quote presente
≠ validated quote presentation_state = VALIDATED_QUOTE
≠ canonical status status / gate_results
```

CASE-5 è la prova che una candidate senza corrispondenza non produce dossier:
l'endpoint risponde `409`, non un dossier vuoto.

CASE-4 mostra ABSTAIN gestito come esito normale: `AMBIGUOUS`, non un guasto.

## §13 — LIVE / REPLAY

| Verifica | Esito |
|---|---|
| `POST /runs` LIVE senza servizi | **HTTP 503**, con il motivo e la variabile da configurare |
| degradato in REPLAY | **no** |
| `HYBRID` richiedibile | **no** — HTTP 422 |
| modalità sconosciuta (`DEMO`) | rifiutata |
| `REPLAY` senza artefatti congelati | rifiutato |
| run REPLAY | `execution_mode = REPLAY`, `fully_live = false`, `llm_calls = 0` |

Una failure LIVE **non** degrada silenziosamente. È il comportamento che il §13
richiede, verificato sull'API reale.

## Rilievo nuovo — NEW-01 (P2, non bloccante)

`evaluate_association` ritorna per `THERAPY_DISCOVERY` **prima** del controllo di
polarità (`gates.py:192-195`). Una candidate la cui fonte dichiara
`Does Not Support` riceve quindi:

```
status = DISCOVERED · bucket = DISCOVERY_BUCKET
support_mask.direction = NOT_APPLICABLE · warnings = []
```

**Non viola i criteri del §17**: `direction` non è `SUPPORTED` e
`DISCOVERY_BUCKET` non è `PRIMARY_BUCKET`. Ed è in parte difendibile: in
discovery non esiste un intervento richiesto, quindi la *coerenza di direzione*
è genuinamente non applicabile.

Ma la **polarità** è un asse diverso dalla coerenza di direzione, è nota, e non
viene segnalata. Un clinico in modalità discovery non ha modo di sapere che la
fonte non sostiene l'associazione.

Popolazione: **999** candidate nel repository, di cui **una sola** raggiungibile
end-to-end — `GCA-003ca9889b3d8906d4674f37` (Melanoma / NIVOLUMAB,
`direction = Sensitivity/Response`, `evidence_direction = Does Not Support`).

Classificato **P2**: da dichiarare nella tesi, non da correggere prima del
freeze.

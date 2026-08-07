# 07 — Dossier strutturato e narrazione

## §14 — Il dossier è costruito prima di qualunque narrazione

Non c'è ambiguità: **non esiste alcuna narrazione.** `stage_13_dossier` è
l'ultimo stage eseguito; `stage_14` e `stage_15` sono chiusi `SKIPPED` da
`skip_remaining`, con `artifact_origin = NOT_APPLICABLE` e reason code
`NOT_IMPLEMENTED`.

L'ordine è quindi banalmente rispettato, ma per assenza del narratore, non
perché una separazione sia stata esercitata.

## Contenuto del dossier canonico

`dossier/builder.py::build_dossier_preview` + `build_candidate_therapy_entry`:

| Campo richiesto dal §14 | Presente | Dove |
|---|:-:|---|
| candidate id | ✅ | `candidate_therapies[].candidate_id` |
| graph direction | ⚠️ | `graph_relation` = `candidate["predicate"]`, **non** `direction` |
| source alignment | ❌ | non esiste in v2 (INV-C03) |
| disease | ✅ | `case_context` |
| alteration | ✅ | `case_context.biomarkers` |
| intervention | ✅ | `candidate_therapies[].drug` |
| provenance | ⚠️ | blocco `provenance` a livello di dossier, non per candidate |
| document | ✅ | `document_support.selected_papers` / `excluded_papers` |
| SourceUnit | ⚠️ | solo dentro `author_context[].source_unit_id` |
| quote status | ⚠️ | `validation_results[]`, **non associato alla singola quote** |
| canonical status | ✅ | `status` |
| reason code | ✅ | `validation_results[].reason_codes`, `warnings` |
| warning | ✅ | `warnings` |
| audit-only state | ❌ | non esiste in v2 (è una nozione di `admission.py`, shadow) |

### `graph_relation` non è la direzione

`orchestrator.py:628` passa `graph_relation=candidate.get("predicate", "")`. Per
la maggior parte delle candidate `predicate` vale `has_evidence_statement` — il
**tipo di arco del grafo**, non la direzione clinica né la polarità della fonte.
Il campo `direction`, che contiene l'informazione realmente rilevante (e
ambigua, INV-C03), **non compare nel dossier**.

La UI rende `graph_relation` sotto l'etichetta «Relazione del grafo» con la
didascalia «Candidate proposta dal grafo — non ancora prova documentale». La
didascalia è corretta e onesta; il valore mostrato è poco informativo.

### Il blocco `provenance` del dossier

```python
"provenance": {
    "dossier_kind": "research_only_end_to_end_pilot_preview",
    "gemma_role": "paper_context_enricher_only",
    "gemma_never_decides": ["support_status","direction","contradiction","gate","score","bucket"],
    "not_wired_to_production_runtime": True,
}
```

`gemma_never_decides` è **vero e verificato** (vedi `06_llm_authority_boundaries.md`).
`not_wired_to_production_runtime: True` è coerente con il fatto che il router di
ricerca è dietro un flag e separato da `/api/v1`.

È provenance a livello di *dossier*, non a livello di *candidate*: non c'è, per
ciascuna candidate, la catena `candidate → identifier → documento → SourceUnit →
quote → validazione`. Quella catena esiste, ma in un endpoint separato:
`GET /runs/{id}/provenance` (`research_routes.py:265`), che la ricostruisce dagli
eventi del ledger. È una scelta difendibile; va detto che il dossier da solo non
la contiene.

## Il narratore e il verificatore narrativo

| | |
|---|---|
| `stage_14_narrator` | **NOT IMPLEMENTED** |
| `stage_15_narrative_verifier` | **NOT IMPLEMENTED** |

Verificato su tre livelli, non solo nei test:

1. `contracts.NOT_IMPLEMENTED_STAGE_IDS = frozenset({"stage_14_narrator", "stage_15_narrative_verifier"})`;
2. `orchestrator.skip_remaining` li chiude `SKIPPED` con reason code
   `NOT_IMPLEMENTED` e `artifact_origin = NOT_APPLICABLE` — **in ogni run, anche
   quelle completate**;
3. `GET /runs/{id}` espone `stages_not_implemented`, e la UI li mostra come tali.

Non esiste alcun modulo `narrator.py` o `narrative_verifier.py` nel repository.
`ROLE_OPTIONAL_NARRATOR` in `backend/pipeline/llm/model_registry.py` appartiene
alla **pipeline di prodotto legacy**, non al runtime di ricerca.

**Classificazione §15: `NOT IMPLEMENTED`** per entrambi.

Il §15 del mandato è esplicito: «Non considerare un narrator senza verifica
equivalente all'architettura target». Qui non c'è né l'uno né l'altro, il che è
**preferibile** a un narratore non verificato: il sistema non genera prosa
clinica, quindi non c'è prosa da verificare. Ma va detto nella tesi che l'ultimo
tratto dell'architettura target — *Dossier → Narrator → Narrative Verifier →
dossier leggibile per MTB* — **non è implementato**, e che ciò che l'MTB vede è
il dossier strutturato reso dalla UI.

Questa è una `FUTURE_FEATURE` dichiarata, non un difetto: il contratto la
espone, l'esecuzione la salta, l'API lo dice. **P3.**

## §14 — «Il narrator non può modificare il dossier canonico»

Vero, per assenza. `narrator_can_change_canonical_dossier = n/a`.

## L'unico problema reale del dossier

È INV-D06, documentato in `05_document_grounding.md`: `author_context` riceve
`call["enrichment"]` senza filtro sull'esito di validazione
(`orchestrator.py:616-617`), e la UI (`DossierView.tsx:89`) classifica come
`accepted` per presenza della quote anziché per esito.

Il dossier **canonico** — `status`, `gate_results`, `support_mask`, `warnings` —
resta protetto. Il dossier **presentato** no.

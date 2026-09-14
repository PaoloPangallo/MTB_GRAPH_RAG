# Vista narrativa del dossier canonico

## Attivazione

La vista narrativa e' opzionale e viene attivata nell'ambiente di runtime con:

```text
RESEARCH_NARRATOR_ENABLED=1
```

L'impostazione e' letta da `backend/research_pipeline/run_store.py:narrator_enabled()`.
Con valore assente o diverso da `1`, `true`, `yes`, `on`, il Narrator non viene
chiamato: il dossier strutturato continua comunque a essere prodotto.

L'endpoint `GET /research/config` espone il flag in
`runtime.narrator_enabled`. Per una run completata, `GET /research/runs/{run_id}/dossier`
restituisce sempre il dossier canonico in `dossier`, la trace deterministica in
`narrative_trace` e, solo se verificata, la vista LLM in `narrative`.

## Collegamento nel runtime

```text
CaseContext
  -> retrieval e routing PAPER / CLINICAL_TRIAL / KG_ONLY
  -> relation_aware_report  (dossier canonico strutturato)
       |- API: dossier + narrative_trace
       `- build_narrator_input(relation_aware_report)
             -> Dossier Narrator (LLM, opzionale)
             -> Narrative Verifier (deterministico)
             -> API: narrative oppure STRUCTURED_DOSSIER_FALLBACK
```

Il dossier viene costruito allo stage 13 prima della narrativa. Gli stage 14 e
15 non cambiano `relation_aware_report`, ne' gli stati PAPER, TRIAL o KG_ONLY.
Se il Narrator, il trasporto o il verifier falliscono, l'API conserva il dossier
e restituisce `presentation_mode=STRUCTURED_DOSSIER_FALLBACK`; `narrative` non
viene esposta come contenuto verificato.

## Trace di provenance per il backend/UI

`narrative_trace` e' una projection deterministica di
`relation_aware_report`, non un output LLM. Le entry sono indicizzate da
`candidate_id`, lo stesso identificativo presente in `candidate_narratives`,
cosi' ogni affermazione leggibile puo' essere ricondotta alla sorgente del
dossier:

| Ramo | Campi di trace |
| --- | --- |
| PAPER | documento/PMCID, SourceUnit, quote validata, esito quote/Reader, support level e field mask, provenance grafica |
| TRIAL | NCT, record ClinicalTrials.gov, condizioni, interventi, fase/stato, `NOT_EVALUATED`, `TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE` |
| KG_ONLY | tripla grafica, database sorgente, graph provenance, `KG_ONLY`, `NOT_AVAILABLE` |

La trace e' disponibile anche se il Narrator e' disabilitato o il verifier
respinge la prosa: in entrambi i casi il client puo' continuare a mostrare
l'evidenza strutturata senza fidarsi di citazioni generate dal modello.

## Input del Narrator

`backend/research_pipeline/narrative/input_projection.py:build_narrator_input()`
crea una proiezione deterministica e isolata del dossier. Non fa retrieval,
non usa fonti esterne, non ricalcola il supporto e non modifica l'oggetto in
ingresso. La projection include:

| Famiglia | Informazioni consegnate al Narrator |
| --- | --- |
| PAPER | `candidate_id`, relazione, documento/PMID, quote validate, stato di supporto, campi di supporto, warning e limitazioni |
| TRIAL | `candidate_id`, NCT, titolo, condizioni, interventi, fase/stato, `trial_resolution_status`, `eligibility_status`, `evidence_interpretation`, provenance grafica |
| KG_ONLY | `candidate_id`, soggetto-relazione-oggetto, contesto di malattia, direzione, tipo di evidenza, database sorgente, provenance grafica, `verification_status`, `document_provenance` |

Quote rigettate, SourceUnit non selezionate, output grezzo del Reader e label
gold non sono inclusi. L'input porta `contract_version=dossier-narrator-input/1.0`
e `narrator_input_hash`, calcolato deterministicamente sul payload.

## Prompt e contratto LLM

Il prompt effettivo e' in `backend/research_pipeline/narrative/prompt.py`:

```text
prompt version: dossier-narrator-prompt/1.0
tool name:      emit_dossier_narrative
language:       it
transport:      dossier-narrative-transport/1.0
```

La tool call ha schema chiuso (`additionalProperties=false`) e richiede soltanto:

```text
narrative_summary
candidate_narratives[] { candidate_id, text }
limitations_summary
closing_note
```

Il system prompt vieta al modello di fare grading, raccomandazioni, retrieval,
uso di conoscenza biomedica esterna o correzioni del dossier. Inoltre specifica:

- **PAPER**: preservare esattamente `FULL_SUPPORT`, `PARTIAL_SUPPORT`,
  `NO_SUPPORT`, `CONTRADICTORY`, `UNVERIFIABLE`; nessuna escalation.
- **TRIAL**: `TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE` non e' prova di
  efficacia; `eligibility_status=NOT_EVALUATED` non permette inferenze di
  eleggibilita'.
- **KG_ONLY**: `verification_status=KG_ONLY` e
  `document_provenance=NOT_AVAILABLE` sono provenance grafica, non evidenza
  documentale validata.

Il messaggio utente e' esclusivamente la serializzazione JSON della projection,
con chiavi ordinate (`build_user_message()`): nessun secondo dossier o dato
legacy viene costruito per il modello.

## Verifica e presentazione

`backend/research_pipeline/narrative/verifier.py:verify_narrative()` riceve:

```text
canonical_dossier = relation_aware_report
narrator_input    = projection del medesimo dossier
narrative_output  = tool call del Narrator
```

Il verifier e' software deterministico; non usa LLM, retrieval o documenti
esterni. Controlla, tra l'altro, candidate sconosciute o mancanti, entita' e
quote non autorizzate, escalation di supporto, inversioni di polarita',
promozione di quote rigettate, raccomandazioni non autorizzate, omissioni di
limitazioni critiche, efficacia/eleggibilita' inventate per TRIAL e conversione
di KG_ONLY in evidenza documentale.

Gli NCT presenti nelle entry `TRIAL` entrano esplicitamente nella identifier
closure del verifier. Sono quindi nominabili dal Narrator, mentre un NCT non
presente nel dossier continua a essere rifiutato come entita' non autorizzata.

`PASS` significa soltanto che nessuna violazione delle regole implementate e'
stata rilevata; non equivale a validazione clinica della narrativa. Solo un
`PASS` rende disponibile `verified_narrative` nell'output API.

## Osservabilita' e failure path

| Evento | Conseguenza |
| --- | --- |
| Narrator disabilitato | stage 14 e 15 `SKIPPED`; dossier disponibile |
| Trasporto/tool call non valida | stage 14 `WARNING`; fallback strutturato |
| Verifier `FAIL` | stage 15 `WARNING`; narrativa non esposta; dossier invariato |
| Verifier `PASS` | `presentation_mode=VERIFIED_NARRATIVE`; narrativa esposta separatamente |

Ogni chiamata persiste hash dell'input, hash della narrativa, versione del
prompt, versione del transport, modello, latenza, token count e risultato del
verifier negli eventi di stage. Il Narrator e' post-dossier: non consuma il
budget che limita le chiamate che costruiscono evidenza scientifica.

## Invariante operativa

```text
relation_aware_report e' la source of truth scientifica.
La narrativa e' una vista opzionale, verificata e revocabile.
```

Di conseguenza, client clinici o tecnici devono poter mostrare il dossier anche
quando `narrative` e' nullo, usando `presentation_mode` e
`narrative_verification.reason_codes` per spiegare il fallback.

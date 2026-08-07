# 05 — Document → SourceUnit → QUOTE/ABSTAIN → validazione

Sonda: `evaluation/deliverability/probes/probe_d_quotes.py`.
Dati: `evaluation/deliverability/raw/D01_quote_validation.jsonl`.

## §9 — La catena reale

```
GraphCandidateAssertion
  └─ document_identifiers[] : [{"pmid": "...", "scope": "evidence_record"},
                               {"pmid": "...", "scope": "linked_publication"}]
        │  scope distingue la provenienza dell'identificatore: candidate-level
        │  (evidence_record) vs parent-level (linked_publication)
        ↓
  EvidenceBundle (25 in totale, 16 candidate distinte, 25 documenti)
        ↓ bundle_id, document_id, source_unit_ids[]
  DocumentRuntime.resolve()          documents/live_resolution.py
        ├─ AuthorizedDocumentCache(root=cache_root(), network=False)
        ├─ manifest_hash, cache_hits, cache_misses
        └─ doc.resolved = False  →  DOCUMENT_UNAVAILABLE (nessun fallback)
        ↓
  DocumentRuntime.load_units()       ri-parsing dal documento in cache
        ↓ units_by_id con `text`
  paper_selection                    max 2 paper / associazione, 4 unit / paper
        ↓
  enricher v2 (LLM)                  vede SOLO le SourceUnit selezionate
        ↓ QUOTE | ABSTAIN
  validator_v2                       verifica letterale deterministica
```

### PMID risolto ≠ PMID che supporta la candidate

Verificato: nessun modulo tratta la risoluzione del documento come prova di
supporto. Le due nozioni restano su assi separati:

- `stage_5` dichiara `{"graph_derived": True, "documentary_proof": False}`;
- `stage_6` produce solo `DOCUMENT_RESOLVED_FROM_CACHE` / `DOCUMENT_UNAVAILABLE`;
- il grounding documentale diventa vero **solo** dopo un esito di validazione
  accettato. `research_routes.py:258-261` lo codifica esplicitamente:

```python
_ACCEPTED_OUTCOMES = ("ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING",
                      "ENRICHMENT_V2_ACCEPTED", "ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY")
# «Solo questi rendono document_grounded vero: un'astensione o un rigetto
#  lasciano la candidate al livello del grafo.»
```

Questa è una proprietà **corretta e ben implementata**.

### Nessun fallback in LIVE

`orchestrator.py:464-482`: in LIVE, cache assente → `FAILED /
DOCUMENT_CACHE_UNAVAILABLE`; zero documenti risolti → `FAILED /
NO_DOCUMENT_RESOLVED`. Il corrispondente artefatto registrato **non** viene
usato al suo posto. È esattamente la proprietà giusta, e ha il costo descritto
nel §16: in questo ambiente LIVE non arriva oltre lo stage 6.

## §10 — SourceUnit

`load_source_unit_index()` carica **solo locatori**: `source_unit_id`,
`document_id`, `unit_type`, `section`, `paragraph_index`, `sentence_index`,
`char_start`, `char_end`, `page`, `content_hash` (SHA-256). 3 402 unità, nessun
testo. È ciò che l'API può esporre senza esporre il documento.

Il testo esiste **solo** quando `DocumentRuntime.load_units()` lo ri-parsa dalla
cache autorizzata. Una SourceUnit non può quindi essere «inventata»: o esiste
nell'indice congelato e nel bundle del paper, o il validatore la rifiuta
(INV-D02, INV-D03).

## §11 — Contratto dell'enricher: chiuso per costruzione ✅

`prompt_v2.TOOL_SCHEMA` ha **esattamente cinque proprietà**:

```
decision · source_unit_id · author_claim_quote · author_context_summary · abstention_reason
```

e `transport_v2.transport_result_v2` righe 71-73:

```python
extra = set(args) - required
if extra:
    return "INVALID_TOOL_ARGUMENTS", finish_reason, None, [f"EXTRA_KEYS:{sorted(extra)}"]
```

Verificato eseguendo il trasporto reale:

| tool call del modello | esito |
|---|---|
| esattamente le 5 chiavi | `V2_TRANSPORT_VALID` |
| + `pmid` | `INVALID_TOOL_ARGUMENTS` — `EXTRA_KEYS:['pmid']` |
| + `canonical_status` | `INVALID_TOOL_ARGUMENTS` |
| + `provenance` | `INVALID_TOOL_ARGUMENTS` |
| una chiave mancante | `MISSING_ARGUMENT` |

**L'LLM non può emettere un PMID, un documento, una SourceUnit, un canonical
status, una recommendation, un farmaco nuovo o una provenance.** Non perché il
prompt glielo vieti: perché lo schema della tool call non ha quei campi e il
trasporto rifiuta la chiamata che li contiene. Classificazione §21:
**`IMPOSSIBLE_BY_CONSTRUCTION`**.

*(Nota di metodo: una prima versione di questa sonda iniettava campi inventati
direttamente nel dossier builder, saltando il trasporto. Il risultato apparente
— «i campi inventati arrivano al dossier» — era un artefatto della sonda, non
del sistema, ed è stato corretto. Il trasporto li blocca.)*

## §12 — Batteria di validazione delle quote: 13 casi su 14 conformi

Validatore realmente collegato al percorso LIVE:
`live_providers.validate_fn` → `validator_v2.validate_enrichment_v2`.

| # | Scenario | Esito | Ammesso ai gate |
|---|---|---|:-:|
| A | quote letterale valida | `ENRICHMENT_V2_ACCEPTED` | ✅ sì |
| B | quote inesistente nel documento | `REJECTED_QUOTE_NOT_FOUND` | ❌ |
| C | quote quasi identica, **una parola cambiata** (polarità invertita) | `REJECTED_QUOTE_NOT_FOUND` | ❌ |
| D | quote presa da un'altra SourceUnit | `REJECTED_QUOTE_NOT_FOUND` | ❌ |
| E | SourceUnit di un altro documento | `REJECTED_SOURCE_UNIT` (`SOURCE_UNIT_NOT_IN_PAPER`) | ❌ |
| F | SourceUnit inventata | `REJECTED_SOURCE_UNIT` (`SOURCE_UNIT_NOT_FOUND`) | ❌ |
| G | quote vuota | `REJECTED_QUOTE_NOT_FOUND` | ❌ |
| H | ABSTAIN pulito | `ENRICHMENT_V2_ABSTAINED` | ❌ |
| H-bis | ABSTAIN con campi popolati | `ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS` | ❌ |
| J | quote non contigua (ellissi) | `REJECTED_QUOTE_NON_CONTIGUOUS` | ❌ |
| K | summary con raccomandazione clinica | `REJECTED_CLINICAL_RECOMMENDATION` | ❌ |
| L | summary non ancorato alla quote | `REJECTED_SUMMARY_UNGROUNDED` | ❌ |
| M | summary che assegna uno status canonico | `REJECTED_SUMMARY_UNGROUNDED` | ❌ |
| N | quote che non nomina il farmaco | `ENRICHMENT_V2_ACCEPTED` | ✅ sì |

**Invarianti del §12:**

```
invented_quote_accepted            = 0   ✅
invented_sourceunit_accepted       = 0   ✅
quote_from_wrong_document_accepted = 0   ✅
```

Il caso C è il più significativo: `"did not derive benefit from panitumumab"`
contro `"did derive benefit from panitumumab"` — una sola parola rimossa,
polarità invertita — viene rifiutato. La verifica è `quote not in unit_text`,
confronto letterale esatto, **completamente indipendente dall'LLM**: nessuna
chiamata al modello, nessuna soglia di similarità, nessun giudice.

Il caso M merita attenzione: se il modello scrive nel summary «the evidence is
DIRECT and belongs in the primary bucket», `_STATUS_GATE_WORDS` lo intercetta e
rifiuta. L'LLM non può nemmeno *suggerire* uno status a parole.

### Il caso N è una debolezza reale, non un difetto

`validator_v2.py:59`:

```python
if drug_norm and drug_norm not in _norm(quote) and drug_norm not in _norm(unit_text):
    return _result("REJECTED_CONTEXT_MISMATCH", ["DRUG_NOT_PRESENT_IN_PASSAGE"])
```

Il farmaco deve comparire nella quote **oppure** nel testo dell'unità. Una quote
che non nomina il farmaco viene quindi accettata come claim d'autore *su quel
farmaco*, purché il farmaco compaia da qualche altra parte nella stessa
SourceUnit. È deliberato (una frase può riferirsi al farmaco per anafora), ma
indebolisce l'ancoraggio. **P3**, da dichiarare come limite.

## ⛔ INV-D06 — Una quote fabbricata entra nel dossier e viene mostrata

Questo è il risultato più serio del Checkpoint D.

**Ciò che funziona.** Un enrichment rigettato non influenza nulla di canonico:

```
validazione     : REJECTED_QUOTE_NOT_FOUND
_accepted_for_gates(...) -> None
status canonico : AMBIGUOUS
support_mask    : direction = NO_DOCUMENT_SIGNAL
bucket          : WARNING_BUCKET
```

**Ciò che non funziona.** `orchestrator.py:616-617`:

```python
if call["enrichment"] is not None:
    enrichment_entries.append(call["enrichment"])   # INCONDIZIONATO
```

L'append non guarda l'esito della validazione. `enrichment_entries` diventa
`author_context` in `build_candidate_therapy_entry`, e finisce nel dossier
canonico. Poi `frontend/src/research/DossierView.tsx:89`:

```js
const accepted  = entry.author_context.filter((e) => e.author_claim_quote);
const abstained = entry.author_context.filter((e) => !e.author_claim_quote);
```

Il filtro è sulla **presenza** di una quote, non sul suo esito di validazione. La
variabile si chiama `accepted`. Le sue voci sono rese (righe 154-171) in corsivo,
con bordo laterale colorato, sotto il titolo «Author context — *Ciò che gli
autori dei paper hanno scritto*».

Risultato verificato:

```
quote fabbricata: "Panitumumab significantly prolonged overall survival in KRAS G12D patients."
esito validazione: REJECTED_QUOTE_NOT_FOUND
bucket UI "accepted": 1  →  la quote fabbricata viene mostrata come citazione d'autore
```

**Mitigazione parziale presente**: gli esiti di validazione sono resi come chip
in fondo allo stesso riquadro (righe 189-203). Ma sono un elenco piatto, non
associati alla singola quote: nulla, nell'interfaccia, collega
`REJECTED_QUOTE_NOT_FOUND` a *quella* citazione.

### Perché è P0

La domanda del §34 — *«Una quote inventata o una SourceUnit inventata possono
entrare nel dossier canonico?»* — ha risposta **sì** per la quote (no per la
SourceUnit). Il criterio di deliverability del §27 «quote inventate non vengono
accettate» è soddisfatto nel senso dello **stato canonico** e violato nel senso
del **dossier presentato al clinico**. In uno strumento di supporto decisionale
per un Molecular Tumor Board, mostrare come citazione d'autore una frase che il
modello ha inventato è la modalità di errore più consequenziale possibile.

**Fix minimo** (non applicato): filtrare `enrichment_entries` sugli esiti
accettati, oppure — meglio, perché conserva l'auditabilità — allegare a ogni
voce di `author_context` il proprio `validation_outcome` e far filtrare la UI su
quello invece che sulla presenza della quote.

Se la tesi delimita esplicitamente la claim allo **stato canonico**, il problema
scende a P1. Come sta ora, la delimitazione non è dichiarata da nessuna parte e
la UI afferma il contrario.

## §20 — La catena a sette livelli di RQ2 non è calcolabile oggi

| Livello | Calcolabile in questo ambiente |
|---|---|
| 1. candidate ha un identificatore documentale | ✅ dal repository |
| 2. l'identificatore risolve | ✅ dal manifest |
| 3. documento disponibile | ❌ `data_cache/` assente |
| 4. SourceUnit disponibile con testo | ❌ idem |
| 5. passaggio rilevante trovato | ❌ idem |
| 6. quote proposta | ⚠️ solo i 7 artefatti congelati del pilot |
| 7. quote validata | ⚠️ idem, e in REPLAY **non viene rieseguita** |

I livelli 3-5 non sono misurabili senza la cache documentale; i livelli 6-7
esistono solo come 7 chiamate registrate al commit `6ee64c5`. Vedi
`09_rq_readiness.md` e `10_reproducibility.md`.

# 10 — Decisione di valutazione

Risposte alle quattro domande di ricerca. Nessuna risposta afferma più di quanto
i dati prodotti dimostrino.

---

## RQ1 — Le GraphCandidateAssertion sono una materializzazione fedele e completa dei path eleggibili del Knowledge Graph?

### Fedele al proprio contratto: **sì, integralmente.**

Riderivando i path in modo indipendente dall'export CSV congelato:

| | |
|---|---|
| Path eleggibili | 46 864 |
| Candidate | 46 864 |
| `materialization_precision` | **1.0** |
| `materialization_recall` | **1.0** |
| `field_completeness` | **1.0** (16 campi) |
| Mancanti / spurie / duplicati esatti | **0 / 0 / 0** |

L'accoppiamento è biiettivo e il payload riderivato dal CSV riproduce lo stesso
`payload_hash` su **tutti** i 46 864 record.

### Fedele al grafo: **no.** Tre difetti sistematici.

| Difetto | Candidate | Conseguenza |
|---|---|---|
| `DIRECTION_INVERSION` | **486** (14.4 % di `evidence-to-drug`) | La candidate afferma l'associazione che il record sorgente **nega** con `evidence_direction = "Does Not Support"` |
| `ALTERATION_LOST` | **1 091** | Profili multi-variante ridotti a una variante; **AND e OR indistinguibili** |
| `REGIMEN_SPLIT` | **1 294** | Record multi-farmaco divisi in candidate a farmaco singolo; `regimen` mai popolato |

Totale con almeno un difetto: **2 419 (5.16 %)**.

> **Sì alla completezza, sì alla fedeltà rispetto al contratto, no alla fedeltà
> rispetto al grafo.** Rispondere «sì» senza qualificazione sarebbe scorretto: le
> regole sono implementate perfettamente e nondimeno perdono informazione
> clinicamente decisiva.

`gca_correctness_measured = true` · `gca_completeness_measured = true`

---

## RQ2 — I PMID associati sono bibliograficamente validi, e quale quota è candidate-level, parent-level, parziale o non determinabile?

### Validità bibliografica: **alta.**

| | |
|---|---|
| Coppie candidate–PMID | 8 230 (17.6 % delle candidate) |
| Candidate **senza** PMID | 38 634 (82.4 %) |
| Sintatticamente valide | 8 209 / 8 230 (99.74 %) |
| Risolvibili in PubMed | 2 228 / 2 229 (99.96 %) |

Le 21 invalide sono difetti **della sorgente**: 17 campi con più PMID separati da
`;` (23 PMID resi irraggiungibili) e 4 con un DOI al posto del PMID.

### Ripartizione della provenance

| Livello | Coppie | Quota |
|---|---|---|
| `PMID_CANDIDATE_LEVEL` | 4 860 | **59.1 %** |
| `PMID_PARENT_LEVEL_ONLY` | 3 370 | **40.9 %** |
| — di cui da record multi-farmaco | 1 294 | 15.7 % del totale |
| Parziale / non determinabile | **non misurato** | richiede annotazione umana |

**Nessuna candidate ha più di un PMID distinto**: i due scope
(`evidence_record`, `linked_publication`) portano sempre la stessa fonte.

### Segnalazioni

* 1 PMID **inesistente** (`174591`), su una candidate che è anche un caso di
  inversione di direzione;
* 3 articoli con **ritrattazione o erratum**, fra cui **1 ritrattato**. Il
  repository non porta alcun campo di stato bibliografico;
* solo **15 documenti su 2 229** sono disponibili in cache: il livello
  *documentary support* non è valutabile su scala.

```
semantic_pmid_precision_claimed_without_gold = false
```

> **Sì sulla validità bibliografica. Sulla pertinenza semantica non è possibile
> rispondere**: il campione di 50 coppie è pronto e non annotato.

---

## RQ3 — OncoKB può essere usato come sorgente esterna controllata di citazioni candidate quando il KG non possiede PMID?

### **No, non su questo corpus.** Due ragioni indipendenti.

**Licenza.** La FAQ ufficiale OncoKB vieta l'uso per addestrare modelli AI/ML e
richiede *«explicit permission»* per il benchmarking di modelli esistenti — che è
esattamente l'uso previsto. Un token è presente e autentica contro l'istanza di
produzione (verificato con una sola chiamata a `/api/v1/info`, solo metadata), ma
un token non è quel permesso.

**Fattibilità.** L'evidenza OncoKB è chiavizzata su
(gene, alterazione, tipo di tumore, farmaco). Delle 38 634 candidate senza PMID:

| Interrogabili | **0 (0 %)** |
|---|---|
| Prive di alterazione | 38 634 |
| Prive di disease | 38 634 |
| Prive anche del gene | 7 381 |

Quattro degli otto strati richiesti dal protocollo sono **vuoti**.

> Le candidate che avrebbero bisogno del fallback sono precisamente quelle prive
> delle chiavi con cui interrogarlo. La causa è il difetto documentato in RQ1: il
> contesto molecolare esiste solo sulle regole derivate da Evidence, che sono
> esattamente quelle che **hanno già** un PMID.

```
ONCOKB_FALLBACK_BLOCKED_NO_AUTHORIZATION   (licenza)
ONCOKB_FALLBACK_LOW_YIELD                  (tecnica)
oncokb_integrated_into_runtime = false
```

Il pilot non è stato eseguito: avrebbe consumato chiamate verso una risorsa
licenziata per dimostrare un esito già determinato dalla struttura del corpus.

---

## RQ4 — Il parser estrae correttamente i casi completi, conserva l'incertezza nei casi ambigui e si astiene da inferenze oncologiche su input come «Mi fa male la gamba»?

### Astensione: **sì, senza eccezioni.**

| Metrica critica | Valore |
|---|---|
| `out_of_scope_false_oncology_extraction` | **0** |
| `non_actionable_false_diagnosis` | **0** |
| `adversarial_instruction_compliance` | **0** |
| `forbidden_downstream_calls` | **0** |

«Mi fa male la gamba» **non** produce sarcoma, metastasi né alterazioni
molecolari: il modello non emette affatto la tool call, e lo fa in modo
riproducibile (3/3). Nessuna delle cinque injection è stata eseguita: nessuna
fuga di prompt, nessun biomarcatore fabbricato pur essendo esplicitamente
richiesto, nessun target imposto dalla direttiva iniettata.
`quotes_not_in_text = 0`: nessuna citazione è stata inventata.

### Estrazione: **parzialmente.**

| | |
|---|---|
| Tool call conformi | 26/35 (74.3 %) |
| `field_precision` / `field_recall` | 0.759 / 0.786 |
| `null_preservation` | 0.938 |
| `offset_validity` | **0.044** |

### Incertezza: **no, non in modo affidabile.**

`ambiguity_recorded_when_expected = 0.667`. E soprattutto: **tutte e 5 le
contraddizioni sono state estratte senza segnalazione** e instradate al
retrieval. Un testo che dice insieme «KRAS wild-type» e «KRAS G12D» produce una
candidate che prosegue.

### Il gap architetturale

Il runtime **non possiede uno stato `OUT_OF_SCOPE`**. `MISSING_IN_TEXT` non è
`MISMATCH`, quindi un CaseContext vuoto supera `essential_fields_pass` ed entra
nel retrieval.

```
routing_matches_protocol_requirement = 0.314
```

Esistono **due soli esiti di routing**, e la categoria dell'input non li
determina: «Che tempo fa domani?» e un caso oncologico completo ricevono lo
stesso instradamento. Dove gli input fuori dominio si fermano, si fermano perché
il *modello* non produce una tool call conforme — **non** perché l'architettura
li riconosca. L'astensione osservata è una proprietà del modello, non una
garanzia del sistema.

> **Sì all'astensione oncologica. No alla conservazione dell'incertezza. Il gap
> di scope è documentato, non colmato.**

---

## Conferme richieste dal protocollo

```
kg_source_identified                            = true
neo4j_required_for_runtime                      = false
neo4j_used_read_only                            = false   (non usata affatto)
gca_correctness_measured                        = true
gca_completeness_measured                       = true
materialization_precision                       = 1.0
materialization_recall                          = 1.0
direction_inversions                            = 486     (graph fidelity; 0 di contratto)
spurious_candidates                             = 0
missing_candidates                              = 0
candidate_pmid_pairs_audited                    = 8230
pmid_syntactically_valid                        = 8209
pmid_resolvable                                 = 2228    (su 2229 PMID unici)
pmid_parent_level_only                          = 3370
semantic_pmid_precision_claimed_without_gold    = false
manual_review_samples_created                   = true    (50 + 50, colonne vuote)
oncokb_official_docs_reviewed                   = true
oncokb_license_compatible                       = undetermined
oncokb_authorized_token_available               = true
oncokb_calls_executed                           = 1       (/api/v1/info, solo metadata)
oncokb_integrated_into_runtime                  = false
casecontext_benchmark_frozen_before_run         = true
parser_calls_executed                           = 50      (35 smoke + 15 repeatability)
out_of_scope_false_oncology_extraction          = 0
non_actionable_false_diagnosis                  = 0
adversarial_instruction_compliance              = 0
forbidden_downstream_calls                      = 0
gold_modified_after_execution                   = false
llm_used_as_primary_gold_judge                  = false
validator_weakened                              = false
drug_synonym_hardcoding_added                   = false
sensitive_data_committed                        = false
runtime_tests_passed                            = true    (2962 passed, 17 skipped)
evaluation_tests_passed                         = true    (42 passed)
push_executed                                   = false
merge_executed                                  = false
```

## Raccomandazioni, in ordine di priorità

1. **Correggere `DIRECTION_INVERSION`** — 486 candidate affermano l'opposto della
   propria fonte. È il difetto con la maggiore conseguenza clinica.
2. **Riparare l'endpoint di default** — `https://api.ollama.com` risponde
   HTTP 405: con la configurazione di default il parser fallisce sempre.
3. **Introdurre un esito per contraddizione e fuori dominio** — oggi non esiste;
   il gap è documentato in `06` e `07`.
4. **Propagare alteration e disease alle regole non-Evidence** — sblocca RQ3 e
   riduce la quota di candidate prive di contesto molecolare.
5. **Annotare i due campioni manuali** — senza di essi la pertinenza semantica dei
   PMID resta non misurata.
6. **Chiedere a OncoKB il permesso esplicito** prima di qualunque uso.
7. **Rappresentare i regimi** — richiede una sorgente che trasporti il tipo di
   interazione fra farmaci, oggi assente dall'export.

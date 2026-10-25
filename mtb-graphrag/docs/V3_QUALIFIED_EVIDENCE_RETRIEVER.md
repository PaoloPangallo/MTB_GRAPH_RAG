# QualifiedEvidenceRetriever — specifica del prototipo

**Corpus: `qualification_corpus/2.0` · sola lettura · deterministico · offline.**

Questo documento precede l'implementazione. Descrive che cosa il retriever fa,
che cosa non fa, e — soprattutto — dove passa la linea fra le due cose.

---

## 1. Le sei operazioni, e le quattro che il retriever implementa

Confonderle è il modo più rapido di costruire un sistema che sembra funzionare e
prende decisioni che nessuno ha autorizzato.

| operazione | che cosa fa | qui |
|---|---|---|
| **candidate generation** | trova gli statement che potrebbero essere pertinenti | **sì** |
| **hard filtering** | rimuove un candidato dal risultato | **sì, ma solo su campi nativi** |
| **soft ranking** | ordina i candidati con segnali graduati | **sì** |
| **evidence annotation** | attacca warning, provenienza e spiegazioni | **sì** |
| applicability | decide se una evidenza si applica a *questo* paziente | no |
| final clinical decision | raccomanda una terapia | no |

Il retriever produce **evidenze ordinate e motivate per il dossier MTB**. Non
produce raccomandazioni terapeutiche, e non dichiara applicabilità clinica.

---

## 2. Il principio che governa tutto

```
qualifier eligibility != final
→ qualifier cannot exclude an EvidenceStatement
```

Sul corpus 2.0 **nessuna unità è `final`**. Quindi, oggi, nessun qualificatore
source-derived può eliminare nulla.

| eligibility | ranking | warning | hard filter | applicabilità |
|---|---|---|---|---|
| `none` | nessun bonus clinico | «unreviewed» | mai | mai |
| `prototype_only` | bonus limitato e dichiarato | sì | **mai** | mai |
| `final` | pieno | sì | consentito | fuori perimetro |

I **campi nativi** degli `EvidenceStatement` — disease, biomarker, intervention,
direction, assertion polarity, evidence scope, source identity — vengono dal
grafo congelato e restano utilizzabili per generare candidati e per i filtri
strutturali già consentiti dal contratto V2. Non sono soggetti a questa politica:
bloccarli renderebbe il sistema meno capace senza renderlo più prudente.

La differenza fra mostrare e filtrare non è di grado. Un qualificatore mostrato
che sia sbagliato viene letto da chi può correggerlo. Un qualificatore che filtri
e sia sbagliato **rimuove** una evidenza, e nessuno vede ciò che non compare più.

---

## 3. Input — `QualifiedRetrievalQuery`

| campo | obbligatorio | uso |
|---|---|---|
| `query_id`, `case_id` | sì / no | identità e tracciabilità |
| `disease`, `disease_aliases` | sì | candidate generation + hard filter nativo |
| `biomarkers` (gene, alteration, normalized) | sì | candidate generation + hard filter nativo |
| `interventions` | no | filtro nativo se presente, altrimenti solo ranking |
| `directions` | no | `sensitivity`, `resistance`, `diagnostic`, `prognostic` |
| `assertion_polarities` | no | `supports`, `does_not_support` |
| `evidence_scopes` | no | filtro nativo se richiesto |
| `preferred_evidence_context` | no | `clinical`, `preclinical`, `both` — **solo ranking** |
| contesto clinico opzionale | no | stage, setting, therapy line, prior therapies, population, resection status — **solo ranking e warning** |
| `top_k` | no (default 20) | taglio finale, dopo il ranking |
| `mode` | no (default `qualified_soft`) | modalità di retrieval |
| `corpus_fingerprint` | no | se presente, deve coincidere con il manifest |

**I qualificatori clinici della query non escludono mai** quando il dato della
fonte è `prototype_only`. Producono bonus, penalità e warning.

Validazione: query vuota, biomarcatore mancante, disease mancante, valori non
normalizzati, fingerprint errato, modalità sconosciuta, `top_k` non valido.

---

## 4. Output — `QualifiedRetrievalResult` e quattro liste

Il risultato non è una lista sola. Nessun candidato sparisce senza traccia.

| lista | contenuto |
|---|---|
| `ranked_results` | i risultati principali, ordinati |
| `retained_with_warning` | mantenuti, con almeno un warning che ne limita la lettura |
| `audit_only_results` | conservati ma non presentati come evidenza primaria (es. `candidate_invalid`) |
| `rejected_by_native_constraints` | esclusi da un vincolo **nativo**, con regola, campo, valore atteso, valore trovato e codice motivo |

Ogni risultato porta: rank, score totale, **breakdown**, match nativi, match
qualificati, mismatch, warning, contesto dell'evidenza, tipo di supporto, stato
del candidate link, polarità, direzione, source id, unità attive, source basis,
review status, eligibility, se è hard-filterable, mapping terminologici,
dimensioni irrisolte, informazione case-level, informazione sull'evidenza
negativa, riferimenti di provenienza, codici di spiegazione e testo di
spiegazione deterministico.

La spiegazione è **template-based**. Nessun LLM.

---

## 5. Modalità

### `v2_compatibility`
Riproduce il comportamento del retrieval V2 per quanto gli stessi input lo
consentano: candidate generation sui soli campi nativi, nessun qualificatore V3,
la rappresentazione V3 usata come contenitore. Produce un report di parity.

Il V2 di riferimento è la traccia **offline** del pilota
(`benchmarks/mtb_evidence/pilot/audit/*/normalized_records.jsonl`), non una query
al grafo: il grafo non è disponibile in questa fase. Dove il V2 usa dettagli non
presenti nel corpus offline, la divergenza va documentata invece di essere
azzerata.

### `native_only`
Solo campi nativi. Nessun qualificatore source-derived tocca il punteggio.
È l'ablation interna della V3: la differenza fra questa modalità e
`qualified_soft` **è** il contributo dei qualificatori.

### `qualified_soft`
Candidate generation e filtri sui campi nativi; scoring nativo; più i segnali
`prototype_only` come bonus limitati, le penalità, i warning e la provenienza.
Nessun hard filter qualificato. È la modalità V3-A prototipale.

### `audit_all`
Tutti i candidati compatibili con il biomarcatore, compresi quelli con disease
mismatch, intervention mismatch, candidate invalid, conflitto o ambiguità —
marcati e non presentati come risultati principali. Serve all'error analysis, non
è la modalità predefinita.

---

## 6. Candidate generation

Deterministica, principalmente sui campi nativi, in quest'ordine:

1. biomarcatore (gene e/o alterazione normalizzata);
2. disease;
3. direction o evidence scope, se richiesti;
4. intervento, se presente nella query;
5. eligibility strutturale dello statement;
6. deduplicazione per identità dello statement.

**Non sono mai motivo di esclusione**: setting, therapy line, population, stage,
prior therapy o regime `prototype_only`; conflitto fra qualificatori;
`not_separable`; `unknown`; fonte abstract-only; evidenza preclinica. Tutti
influenzano ranking o warning.

Un `candidate_invalid` approvato in prima revisione **non viene rimosso in
silenzio**: in `qualified_soft` riceve una penalità forte, finisce in
`audit_only_results`, ed espone motivo, dimensione non sostenuta, fonte e stato
provvisorio della revisione.

---

## 7. Normalizzazione e match

Si riusano i normalizzatori esistenti (`_normalize.py`). Nessun sinonimo clinico
o farmacologico viene inventato.

| grado | significato |
|---|---|
| `exact` | stringhe identiche dopo normalizzazione minima |
| `normalized_exact` | identiche dopo normalizzazione del vocabolario |
| `verified_synonym` | sinonimo confermato da una verifica terminologica |
| `verified_development_code` | codice di sviluppo confermato |
| `pending_terminology_mapping` | mapping esistente ma **non verificato** |
| `ambiguous_mapping` | più candidati, nessuno scelto |
| `rejected_mapping` | mapping esaminato e respinto |
| `no_match` | — |

Un mapping `requires_terminology_verification` **non vale come exact match**.
Produce un match debole, un warning, una penalità e una spiegazione.

Tre casi obbligatori:

- **CH5424802 → alectinib**: mapping non verificato, non exact;
- **copy-number gain → amplification**: non equivalenza letterale, non exact;
- **less sensitive → resistance**: `relative_reduced_sensitivity`, non
  `complete_resistance`.

---

## 8. Scoring

Lo score è **decomponibile**. `RetrievalScoreBreakdown` elenca ogni componente
con nome, peso, valore e ragione; la somma delle componenti è lo score totale, e
un test lo verifica.

I pesi vivono in `qualified_retriever_scoring_config.json`: versione, pesi,
soglie, regole di tie-break, policy per campi mancanti, policy per
`prototype_only`, hash. Non sono sparsi nel codice.

I pesi **non sono ottimizzati sul clinical gold**. Sono valori iniziali semplici e
motivati, congelati prima del futuro confronto.

### Le otto regole sullo score

1. `unknown` → contributo **neutro**: né positivo né negativo.
2. `not_applicable` → la dimensione è **esclusa** dallo score per quella unità.
3. `not_separable` → nessun bonus, warning, penalità prudente documentata, mai
   rifiuto.
4. `prototype_only` → contributo massimo limitato da un tetto dichiarato; non può
   da solo superare un mismatch nativo forte; non può eliminare un candidato.
5. `none` → nessun bonus clinico source-derived; mostrabile come `unreviewed`.
6. `candidate_invalid` → penalità forte, non evidenza primaria in
   `qualified_soft`, conservato nell'audit trail.
7. `does_not_support` → non diventa supporto positivo; recuperabile come evidenza
   negativa; penalizzato o premiato secondo la polarità richiesta.
8. case-level o named-patient-subset → warning di non generalizzabilità, nessun
   bonus population-level, nessuna inferenza di frequenza.

---

## 9. Tie-breaking

L'ordine è totalmente deterministico:

1. score totale decrescente;
2. score nativo decrescente;
3. directness del supporto;
4. review status;
5. source basis (full text → abstract only → registry only);
6. preferenza di contesto dell'evidenza;
7. identificatore canonico della fonte;
8. statement ID.

Non si usano: ordine di ingestione, timestamp, ordine dei file, hash casuali.

---

## 10. Determinismo

- due esecuzioni sugli stessi input producono gli stessi byte;
- invertire l'ordine di ingresso non cambia il ranking;
- la configurazione di scoring è versionata e hashata;
- nessun path di macchina compare negli artefatti;
- nessuna rete, nessun Neo4j, nessun LLM.

---

## 11. Compatibilità V2

Un parity harness confronta il V2 offline con `v2_compatibility` e `native_only`,
misurando **solo aspetti tecnici**: overlap del candidate set, overlap
statement/source, overlap dell'ordine, candidati mancanti, candidati in più,
cause delle divergenze.

Non si misurano ancora: therapy precision, recall clinico, terapie attese dal
gold, applicabilità finale.

L'obiettivo non è una parity di 1.0. È che **nessuna evidenza si perda senza un
motivo noto**.

---

## 12. Limiti del prototipo

- nessuna unità è `final`: nessun hard filter qualificato è possibile, e il
  contratto per farlo esiste ma non è esercitato;
- il gold è provvisorio e non valutabile: nessuna metrica di qualità è calcolabile;
- 10 unità attive dichiarano `biomarker_requirements` senza `biomarker_role`: un
  filtro per biomarcatore non distinguerebbe un requisito di arruolamento da un
  reperto alla progressione;
- il pannello preclinico di PMID 23344087 è `not_separable`: nessun ranking a
  livello di componente;
- il V2 di riferimento è una traccia offline, non il grafo;
- la spiegazione è template-based: descrive la decisione, non la argomenta.

---

## 13. Che cosa sblocca il passo successivo

Il confronto **esplorativo** V2 contro V3-A richiede solo che i controlli tecnici
passino. La valutazione **finale** richiede una seconda revisione indipendente,
unità `final` e un gold valutabile: nessuna delle tre esiste.

I due stati restano distinti in `V2_V3A_EVALUATION_READINESS.md`.

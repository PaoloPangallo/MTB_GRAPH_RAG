# Readiness per il prototipo `QualifiedEvidenceRetriever`

**Corpus: `qualification_corpus/2.0` · stato `ready_for_prototype`.**

Il retriever **non è implementato in questa fase**. Questo documento dice che cosa
il corpus gli permette di fare, e soprattutto che cosa non gli permette.

---

## 1. La frase in una riga

Il prototipo può **leggere e mostrare** qualificatori source-derived. Non può
**filtrare** con essi.

La differenza non è di grado. Un qualificatore mostrato che sia sbagliato viene
letto da chi può accorgersene e correggerlo. Un qualificatore che filtri e sia
sbagliato **rimuove** una evidenza, e nessuno vede ciò che non compare più.

---

## 2. Readiness per dimensione

Un unico booleano direbbe che tutto il corpus è ugualmente utilizzabile, e non lo
è.

| dimensione | stato | perché |
|---|---|---|
| campi nativi `EvidenceStatement` | `ready` | vengono dal grafo congelato, nessuna revisione li riguarda |
| qualificatori source-checked | `prototype_ready` | letti sulla fonte, mai confermati da una seconda persona |
| qualificatori di prima revisione | `prototype_ready` | una sola annotazione, non indipendente e non clinica |
| qualificatori machine-extracted | `not_ready` | eligibility `none`: nessuno ha letto la fonte |
| qualificatori `final` | `not_available` | non ne esiste nessuno |
| hard filtering | `not_available` | richiede `final`, e `final` richiede una seconda revisione |
| filtro per componente su PMID 23344087 | `not_available` | il pannello è `not_separable` |

`prototype_ready` non è `final_ready`, e la distinzione va rispettata nel codice
del retriever, non solo nella documentazione.

---

## 3. Che cosa il corpus fornisce

| artefatto | contenuto |
|---|---|
| `evidence_statements.jsonl` | 147 statement, invariati dal grafo congelato |
| `active_source_profile_units.jsonl` | 109 unità attive — le sole da indicizzare |
| `historical_source_profile_units.jsonl` | 14 unità storiche — **da non indicizzare** |
| `qualification_links.jsonl` | 201 link, tutti verso unità attive |
| `qualified_evidence_views.jsonl` | 147 viste in modalità `prototype` |
| `statement_qualification_gold.jsonl` | 94 record, provvisori e non valutabili |
| `review_decisions.jsonl` | 17 decisioni di prima revisione |
| `terminology_mappings.jsonl` | 8 mapping, 6 ancora da verificare |
| `qualification_corpus_manifest.json` | impronte, hash dei componenti, versione |

Ogni qualificatore in una vista espone: valore, unità di origine, identificatore
della fonte, locator, stato di revisione, `propagation_eligibility`,
`display_allowed`, `hard_filter_allowed` e provenienza completa. Il retriever ha
tutto ciò che serve per dire **perché** mostra un valore, senza dover risalire a
un altro file.

---

## 4. I sette vincoli che il prototipo deve rispettare

1. **Indicizzare solo `active_source_profile_units.jsonl`.** Le 14 unità storiche
   esistono perché la storia sia leggibile: una parent sostituita o una proposta
   respinta trovata fra i qualificatori non porterebbe alcun segnale che dica che
   descrive uno stato superato.

2. **Non applicare qualificatori con eligibility `none`.** Sono 92 unità attive su
   109. Il corpus li ha già esclusi dai link, ma il retriever non deve
   reintrodurli leggendo direttamente le unità.

3. **Mostrare i `prototype_only`, marcati come provvisori.** Sono 17 unità.
   Nasconderli sarebbe prudente e sbagliato: toglierebbe a chi può correggerli
   l'unica occasione di vederli.

4. **Rifiutare il filtro nel punto d'uso.** `QualifiedEvidenceView.assert_hard_filterable`
   esiste già e solleva `PrototypeHardFilterError`. Un chiamante che legga
   `qualified_dimensions` e filtri senza chiedere non trova ostacoli: la chiamata
   di verifica va fatta, non presupposta.

5. **Non collassare le tre assenze.** `unknown`, `not_applicable` e
   `not_separable` non sono sinonimi, e la vista li tiene in campi distinti con
   `sentinel_sources` a dire quale unità ha prodotto quale.

6. **Non risolvere i conflitti.** 53 conflitti restano registrati e non applicati.
   Quando due unità attive propongono valori diversi per la stessa dimensione, la
   dimensione non viene applicata: scegliere è un giudizio umano.

7. **Non generalizzare le evidenze case-level.** Due statement case-level e uno
   named-patient-subset portano `cohort_generalizable = false` e
   `frequency_inference = forbidden`. Le regole della guardia 1.2 valgono anche a
   valle.

---

## 5. Quattro casi da usare come test del prototipo

| caso | che cosa deve succedere |
|---|---|
| `ES-V2-evidence-100005` | `population` è in conflitto fra coorte clinica e modelli Ba/F3 → non applicata |
| `PU-PMID-22235099-h3122-kras-engineered` | polarità `does_not_support`, zero dimensioni aggiunte → mai un supporto positivo |
| `PU-PMID-23344087-preclinical-unresolved-panel` | `not_separable` su composizione e mapping → nessun filtro per componente |
| `PU-PMID-22235099-cuto1-comparative` | `biomarker_requirements` vuoto → il biomarcatore del paziente 10 non attraversa il confine |

---

## 6. Che cosa resta chiuso

```
hard_filtering_available     = false
final_evaluation_ready       = false
gold_evaluable               = false
detector_promotion_ready     = false
standard_queue_resumed       = false
```

Nessuna metrica finale di linking, agreement, accuratezza del rilevatore o
qualità del retrieval può essere calcolata sul prototipo. Il gold ha una sola
annotazione per link, non indipendente e non clinica: misurare il retriever
contro di esso misurerebbe il sistema contro se stesso.

---

## 7. Che cosa aprirebbe `final`

Perché una unità diventi `final` — e quindi un qualificatore diventi
hard-filterable — servono, secondo la politica corrente:

- una seconda revisione **indipendente** con accordo esplicito, oppure una
  adjudication, oppure un dossier congelato;
- **e** una coorte risolta: una coorte irrisolta non propaga nemmeno dopo una
  adjudication, perché non si saprebbe a quale braccio applicare il valore.

I 70 packet ciechi della seconda revisione sono pronti e invariati. Il pannello di
PMID 23344087 resterebbe comunque non filtrabile per componente anche dopo una
seconda revisione: il limite non è di chi legge, è del documento — l'abstract non
contiene la composizione, e due lettori dello stesso abstract non possono
scoprirla.

---

## 8. Una lacuna da chiudere prima o poi

10 unità attive dichiarano `biomarker_requirements` senza `biomarker_role`
(`biomarker_role_backfill_required = true`). Quattro sono `prototype_only` e
finiscono nelle viste. Il prototipo può mostrarle; un eventuale filtro per
biomarcatore non potrebbe distinguere un requisito di arruolamento da un reperto
alla progressione, ed è una delle ragioni per cui il filtro resta chiuso.

---

## 9. Prossimo passo

Implementazione del prototipo `QualifiedEvidenceRetriever` su
`qualification_corpus/2.0`, in sola lettura e sola visualizzazione.

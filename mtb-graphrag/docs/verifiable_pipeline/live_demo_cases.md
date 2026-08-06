# Casi dimostrativi

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Sei casi. Cinque sintetici, eseguibili dalla Supervisor UI; il sesto è un test
automatico ed è etichettato come tale.

Nessun dato reale di paziente è usato in nessuno di essi. I testi sono composti
in modo deterministico a partire da record `GraphCandidateAssertion` /
`EvidenceBundle` già congelati nel repository, così l'esito atteso è noto senza
inventare alcuna associazione clinica.

---

## CASE-1 — Positive match · **LIVE**

Colorectal cancer, KRAS G12D, panitumumab.

```
mode LIVE · fully_live true · replay 0 · llm_calls 2 · COMPLETED
documento pmid:19223544 dalla cache · 4 SourceUnit con testo · 1 paper
QUOTE → ENRICHMENT_V2_ACCEPTED (offset 95)
status PARTIAL · WARNING_BUCKET
```

La quote dice che le mutazioni KRAS conferiscono **resistenza**. Lo status non
diventa positivo: `VALIDATED_ENRICHMENT_DOES_NOT_ADDRESS_DIRECTION`.

---

## CASE-2 — Mixed quote validation · **REPLAY**

Colorectal cancer, BRAF V600E, farmaco non nominato nel testo.

```
mode REPLAY · fully_live false · replay 6 · llm_calls 0 · COMPLETED
2 paper: 1 quote REJECTED_QUOTE_NOT_FOUND, 1 ENRICHMENT_V2_ACCEPTED
status DISCOVERED · DISCOVERY_BUCKET
```

Non eseguito live per budget (costava 3 chiamate su un residuo di 1). Etichettato
REPLAY ovunque. È il caso che dimostra il retrieval per scoperta: encorafenib è
trovato nel grafo senza che il farmaco compaia nel testo clinico.

---

## CASE-3 — Abstention · **LIVE**

Colorectal cancer, MSI (grado non specificato), nivolumab.

```
mode LIVE · fully_live true · replay 0 · llm_calls 3 · COMPLETED
4 documenti risolti · 9 SourceUnit con testo · 2 paper selezionati, 2 esclusi
  (MAX_PAPERS_PER_ASSOCIATION_EXCEEDED)
ABSTAIN ×2 → ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS, ENRICHMENT_V2_ABSTAINED
status AMBIGUOUS · NO_VALIDATED_ENRICHMENT_AVAILABLE
```

Astensioni reali e motivate: *«describes the statistical analysis plan …, but does
not report any actual observations»*. Un ABSTAIN è un esito valido, non un guasto.

---

## CASE-4 — Contradicted / resistance · **LIVE**

Lung squamous cell carcinoma, FGFR1 amplification, infigratinib.

```
mode LIVE · fully_live true · replay 0 · llm_calls 3 · COMPLETED
2 documenti · 6 SourceUnit · 2 paper
QUOTE  → REJECTED_CONTEXT_MISMATCH (DRUG_NOT_PRESENT_IN_PASSAGE)
ABSTAIN → ENRICHMENT_V2_ABSTAINED
status AMBIGUOUS · NO_VALIDATED_ENRICHMENT_AVAILABLE
```

**Il caso non è diventato positivo**, e il testo documentale non è stato adattato
alla candidate. Il modello ha citato una frase su BGJ398 mentre il farmaco
richiesto era infigratinib — stesso composto, nome diverso — e il validatore, che
confronta stringhe, ha rigettato. Falso negativo, comportamento voluto.

---

## CASE-5 — No match · **LIVE**

Colorectal cancer, gene fabbricato `ZZTK9 P44R`, panitumumab.

```
mode LIVE · fully_live true · replay 0 · llm_calls 1 · STOPPED
stopped_at RETRIEVAL_NO_MATCH
```

**Gemma non è stato chiamato** per l'enrichment: la sola chiamata è il parser. Il
verificatore trova MATCH per il biomarcatore inventato — è genuinamente presente
nel testo, il parser ha estratto fedelmente — e il retrieval trova zero candidate
compatibili, perché il gene non esiste nel repository. Nessuna evidenza
artificiale viene costruita.

---

## CASE-6 — CaseContext mismatch · **TEST SCENARIO, non demo live**

```
CASECONTEXT_MISMATCH
  → retrieval SKIPPED
  → document resolution SKIPPED
  → Gemma SKIPPED
  → dossier SKIPPED · run STOPPED
```

**Non è una demo live e non viene presentato come tale.** Produrlo dal modello
reale richiederebbe che il parser inventi un campo che il testo non contiene:
non lo si può chiedere in modo affidabile, e metterlo in scena non sarebbe
onesto.

Vive come test automatico (`CaseContextMismatchTest`), con il CaseContext
divergente costruito esplicitamente ed etichettato `TEST SCENARIO`. Ciò che il
test verifica è reale: il verificatore, gli stage saltati e i reason code sono
quelli di produzione, e il test fallisce se Gemma viene chiamato.

`CASECONTEXT_MISMATCH` è in `CORRECT_STOP_REASONS`: la pipeline si è fermata
perché doveva.

---

## Riepilogo

| Caso | Modalità | Esito | LLM | Quote acc. | Rig. | Astensioni |
|---|---|---|---:|---:|---:|---:|
| CASE-1 | LIVE | COMPLETED | 2 | 1 | 0 | 0 |
| CASE-2 | REPLAY | COMPLETED | 0 | 1 | 1 | 0 |
| CASE-3 | LIVE | COMPLETED | 3 | 0 | 0 | 2 |
| CASE-4 | LIVE | COMPLETED | 3 | 0 | 1 | 1 |
| CASE-5 | LIVE | STOPPED | 1+1 | 0 | 0 | 0 |
| CASE-6 | test | STOPPED | 0 | 0 | 0 | 0 |

CASE-5 conta 2 chiamate perché è stato eseguito due volte: la seconda per
verificare la correzione del conteggio canonico dopo un riavvio.

**Totale chiamate reali a `gemma4:cloud`: 10 su 10 autorizzate.**

Gli esiti non sono stati forzati. L'obiettivo era verificare il percorso, non
riprodurre gli output storici.

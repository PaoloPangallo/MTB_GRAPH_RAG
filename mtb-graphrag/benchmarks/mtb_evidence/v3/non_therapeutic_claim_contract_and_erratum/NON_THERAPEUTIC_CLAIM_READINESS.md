# Readiness del contratto dei claim non terapeutici

Versione contratto: `non-therapeutic-claim-contract/1.0`
Erratum: `adjudication_erratum/1.0`
Specification emendata: `migration_specification_amended/1.1`
Stato: `amended_not_promoted`

## Flag

| Flag | Valore | Motivo |
|---|---|---|
| `three_records_audited` | true | `evidence:347`, `evidence:1846`, `evidence:1847`, con fonte, locator, verdetto e reason code |
| `non_therapeutic_scope_decided` | true | 2 diagnostici approvati, 1 sospeso; nessun intervento inventato |
| `diagnostic_claim_contract_ready` | true | Campi, interpretazioni, tre inferenze vietate, scope di scoring e metriche |
| `prognostic_claim_contract_ready` | true | Contratto completo, senza casi approvati nel corpus |
| `predictive_claim_required` | **false** | Nessun caso materializzabile; il tipo sarebbe ridondante |
| `adjudication_erratum_complete` | true | Due correzioni, hash originali citati, originali invariati |
| `migration_specification_amended` | true | Versione 1.1, sostituisce la 1.0 senza cancellarla |
| `expected_claim_count_reconciled` | true | 149 → **148**, derivato |
| `shadow_repository_update_ready` | **true** | Il contratto è completo e i due claim sono simulati con ID stabili |
| `terminology_review_ready` | **false** | Vedi sotto |
| `corpus_promotion_ready` | **false** | Vedi sotto |
| `full_exploratory_rerun_ready` | **false** | Vedi sotto |

## Conteggio riconciliato

| | |
|---|---|
| Claim terapeutici (invariati) | 146 |
| Claim diagnostici | 2 |
| Claim prognostici | 0 |
| **Totale** | **148** |
| Parent | 147 |
| Parent senza claim | 3 — `evidence:347`, `evidence:3811`, `evidence:4759` |

Il totale non è stato imposto. Se l'audit avesse approvato anche `evidence:347`
sarebbe stato 149, e sarebbe stato derivato allo stesso modo: il numero è
l'esito della lettura dei documenti, non il suo obiettivo.

## Perché `shadow_repository_update_ready` può essere true

Il contratto definisce i due tipi con i campi richiesti, la matrice di
eleggibilità per tipo di query, lo scope di scoring e la separazione dei
denominatori. I due claim diagnostici hanno soggetto, biomarcatore, disease
scope, interpretazione, polarità, source unit, locator e provenienza — tutte le
precondizioni di materializzazione sono soddisfatte e verificate. Gli ID sono
deterministici, senza collisioni fra loro, con i claim terapeutici e con i
parent, e non contengono alcun campo intervento artificiale.

L'aggiornamento del repository shadow è la fase successiva e non è stato
eseguito: il repository generato prima resta byte per byte quello che era.

## Perché `terminology_review_ready` resta false

Restano aperti i quattro gruppi con revisione terminologica pendente
(`evidence:12156`, `evidence:1851`, `evidence:1853`, `evidence:841`) e i due
mapping non approvati (`infigratinib`, `luminespib`). A questi si aggiungono le
due source unit dei nuovi claim diagnostici: `PU-PMID-24122810-cohort-1` è
`awaiting_first_review` con `is_evaluable: false` e zero source span, e
`PU-PMID-24662454-cohort-1` è `awaiting_source_review`. L'audit è ancorato
all'abstract; la conferma umana sulla fonte primaria non è avvenuta.

## Perché `corpus_promotion_ready` resta false

La divergenza di conteggio che bloccava la promozione è riconciliata, e
l'incoerenza della prosa è corretta: due dei blocker precedenti cadono. Ne
restano tre.

**`evidence:347` è sospeso, non risolto.** La direzione `prognostic` del grafo è
contraddetta dalla fonte, che è un'analisi predittiva su cetuximab. Promuovere il
corpus lascerebbe dentro un record la cui classificazione è nota per essere
sbagliata e la cui classificazione corretta non è ancora stabilita. Serve il full
text.

**Le revisioni terminologiche e documentali sono aperte.** Vedi sopra.

**I claim non terapeutici non sono implementati.** Il contratto è dichiarativo.
Finché `DiagnosticClaim` non esiste nel repository shadow, promuovere il corpus
significherebbe promuovere una tassonomia che il codice non conosce.

## Perché `full_exploratory_rerun_ready` resta false

Deve restare false, e lo è. Nessuna metrica è stata calcolata in questa fase, il
gold non è stato letto, e i denominatori sono appena cambiati: le famiglie
diagnostica e prognostica ora esistono e vanno separate da quella terapeutica.
Un rerun prima della promozione confronterebbe numeri costruiti su tassonomie
diverse.

## Blocker

| Blocker | Impatto |
|---|---|
| `evidence:347` sospeso, full text richiesto | Blocca `corpus_promotion_ready` |
| Source unit dei claim diagnostici non revisionate | Blocca `terminology_review_ready` e `corpus_promotion_ready` |
| 4 gruppi con terminology review aperta, 2 mapping non approvati | Blocca `terminology_review_ready` |
| Claim non terapeutici non implementati nel repository shadow | Blocca `corpus_promotion_ready` |
| Disease hierarchy policy non attiva | Blocca la migrazione del retriever |

## Risolti da questa fase

| Blocker precedente | Esito |
|---|---|
| Divergenza fra 149 proiettati e 146 derivati | Riconciliata a 148 con erratum A |
| Prosa §16 incoerente su `evidence:275` | Corretta con erratum B |
| Tre record senza tipo di claim | Due tipizzati come diagnostici, uno sospeso con motivazione |

## Prossimo passo

Implementare `DiagnosticClaim` e `PrognosticClaim` nel modello shadow e
rigenerare il repository con i due claim diagnostici materializzati, portando il
totale a 148 nel repository stesso e non solo in simulazione. In parallelo,
richiedere il full text di `PMID:24662454` per sciogliere `evidence:347` e la
revisione umana delle due source unit.

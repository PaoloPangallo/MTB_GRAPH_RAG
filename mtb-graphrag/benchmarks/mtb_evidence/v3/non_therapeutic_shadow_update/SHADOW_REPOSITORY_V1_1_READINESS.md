# Readiness del repository shadow 1.1

Model schema: `qualified_claim_model/1.1`
Repository: `qualified_claim_repository/1.1`
Stato: `shadow_not_promoted`

## Flag

| Flag | Valore | Motivo |
|---|---|---|
| `diagnostic_claim_model_implemented` | **true** | `DiagnosticClaim` con campi, invarianti e conversioni vietate che sollevano |
| `prognostic_claim_model_implemented` | **true** | `PrognosticClaim` implementato e testato |
| `diagnostic_claims_materialized` | **true** | 2, per `evidence:1846` ed `evidence:1847` |
| `prognostic_claims_materialized` | **false** | 0 istanze: nessun record del corpus ne sostiene uno |
| `evidence_347_promotion_status_resolved` | **true** | `promotion_blocked_pending_full_text`, non più promuovibile |
| `claim_domain_gate_implemented` | **true** | Matrice a 4 query × 5 tipi, ranking cross-domain impossibile |
| `sectioned_untyped_output_implemented` | **true** | Tre sezioni separate, nessun confronto numerico fra domini |
| `shadow_repository_v1_1_ready` | **true** | Deterministico, conteggi derivati, 1.0 invariato |
| `source_review_required` | **true** | Vedi sotto |
| `terminology_review_required` | **true** | Vedi sotto |
| `corpus_promotion_ready` | **false** | Vedi sotto |
| `operational_retriever_migration_ready` | **false** | Vedi sotto |
| `full_exploratory_rerun_ready` | **false** | Vedi sotto |

## Perché `shadow_repository_v1_1_ready` può essere true

Il repository è generato in modo deterministico — due generazioni producono gli
stessi byte, invertire l'ordine di record e query non cambia nulla, nessun path
specifico della macchina compare negli artefatti. Copre tutti e 147 i graph
evidence ID, deriva 148 claim come somma delle parti invece che come costante,
non ha collisioni fra i suoi 148 claim, i 147 parent e le 12 associazioni, e
riproduce esattamente i due `claim_id` della simulazione emendata.

Il repository 1.0 non è stato toccato: vive dov'era, è citato nel lineage con
l'hash di ognuno dei suoi 19 artefatti, e un test li ricalcola tutti.

## Perché `source_review_required` resta true

Entrambi i claim diagnostici poggiano su `PU-PMID-24122810-cohort-1`, che è
`awaiting_first_review`, ha `is_evaluable: false` e zero source span.
L'estrazione è ancorata all'abstract e la conferma umana sulla fonte primaria
non è avvenuta. I claim lo dichiarano: `final_evaluable = false` e
`SOURCE_UNIT_AWAITING_HUMAN_REVIEW` fra le limitazioni.

## Perché `terminology_review_required` resta true

Restano aperti i quattro gruppi terapeutici con revisione terminologica pendente
(`evidence:12156`, `evidence:1851`, `evidence:1853`, `evidence:841`) e i due
mapping non approvati (`infigratinib`, `luminespib`). Questa fase non li ha
toccati, come da perimetro.

## Perché `corpus_promotion_ready` resta false

Tre blocker, tutti verificabili.

**Il full text di `PMID:24662454` non è stato recuperato.** `evidence:347` è
bloccato in attesa, non risolto. Lo stato impedisce che lo statement rientri come
claim prognostico, il che era la cosa urgente, ma non stabilisce cosa quel record
sia. Promuovere ora congelerebbe un «non lo sappiamo» in un corpus operativo.

**Le source unit non sono revisionate.** Promuovere i due claim diagnostici
significherebbe rendere operativi claim la cui fonte nessuno ha letto per intero.

**La revisione terminologica è aperta.** Vedi sopra.

## Perché `operational_retriever_migration_ready` resta false

Il retriever operativo non è stato toccato e non può esserlo prima che il corpus
sia promosso: interrogherebbe oggetti che non esistono. La sequenza resta corpus,
poi indice, poi retriever. Si aggiunge ora un vincolo nuovo: il retriever
operativo non conosce il concetto di dominio, e migrarlo senza prima
implementarvi la separazione per dominio produrrebbe risultati diagnostici dentro
il ranking terapeutico — esattamente ciò che il gate 1.1 esiste per impedire. La
disease hierarchy policy resta inoltre non attiva.

## Perché `full_exploratory_rerun_ready` resta false

Deve restare false, e lo è. Nessuna metrica è stata calcolata, il gold non è
stato letto, e i denominatori sono cambiati di nuovo: le famiglie diagnostica e
prognostica ora hanno istanze — due e zero — e il denominatore therapy-level
resta 146 e non 148. Un rerun prima della promozione confronterebbe numeri
costruiti su tassonomie diverse.

## Blocker

| Blocker | Impatto |
|---|---|
| Full text di `PMID:24662454` non recuperato | Blocca `corpus_promotion_ready`; `evidence:347` resta sospeso |
| Source unit `PU-PMID-24122810-cohort-1` non revisionata | Blocca `corpus_promotion_ready` e `source_review_required` |
| 4 gruppi con terminology review, 2 mapping non approvati | Blocca `terminology_review_required` |
| Retriever operativo non conosce i domini | Blocca `operational_retriever_migration_ready` |
| Disease hierarchy policy non attiva | Blocca `operational_retriever_migration_ready` |

## Risolti da questa fase

| Blocker precedente | Esito |
|---|---|
| Claim non terapeutici non implementati nel repository shadow | Implementati e materializzati |
| `evidence:347` promuovibile come claim prognostico legacy | `promotion_blocked_pending_full_text` |
| Totale 148 solo in simulazione | Derivato nel repository |

## Prossimo passo

Richiedere il full text di `PMID:24662454` per stabilire cosa sia `evidence:347`,
e la revisione umana di `PU-PMID-24122810-cohort-1` per rendere valutabili i due
claim diagnostici. In parallelo, chiudere la revisione terminologica sui quattro
gruppi terapeutici. Solo dopo ha senso portare la separazione per dominio nel
retriever operativo e, in sequenza, promuovere il corpus.

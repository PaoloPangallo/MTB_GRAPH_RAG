# Architettura del retriever V3

Backend: `qualified_claim_v3`  
Versione: `qualified_claim_retriever/1.0`  
Repository: `qualified_claim_repository/1.4`  
Gate: `qualified_claim_structural_gate/1.1`  
Corpus: `31636f26c44bee03b16ed7d7c5e9b9580292f750e04b80e4effbaf9618ec39fa`

## Cosa il retriever non reimplementa

Il retriever V3 e' un giro attorno a componenti gia' congelati. Il corpus
lo apre il loader promosso, i gate li applica il gate integrato 1.1, i pesi
vengono letti dalla configurazione operativa senza essere toccati. Cio' che
questo modulo aggiunge e' quali oggetti entrano, come i bucket vengono
composti e che cosa esce.

| Componente | Origine |
| --- | --- |
| Loader | `backend.pipeline.evidence.corpus.loader` |
| Gate | `backend.pipeline.evidence.shadow.integrated_gates_v11` |
| Pesi | `qualified_retriever_scoring_config.json` |
| Contratto di risultato | `qualified_claim_retrieval_result/1.3` |

Il loader non viene duplicato su nessuno dei cinque assi che gia' copre:

- `hash_verification`
- `schema_validation`
- `redirect_lineage`
- `parent_claim_lookup`
- `policy_mode_validation`

## Ordine dei gate

L'ordine non e' una descrizione a posteriori. I primi nove passi sono
quelli che il gate integrato esegue, nella sequenza in cui li esegue, e un
solo gate incompatibile annulla ogni eleggibilita' residua.

| # | Passo |
| --- | --- |
| 1 | `active_claim_loading` |
| 2 | `claim_status_gate` |
| 3 | `domain_gate` |
| 4 | `biomarker_gate` |
| 5 | `disease_gate` |
| 6 | `intervention_identity_gate` |
| 7 | `formulation_gate` |
| 8 | `regimen_class_aggregate_gate` |
| 9 | `direction_polarity_gate` |
| 10 | `bucket_composition` |
| 11 | `scoring_where_permitted` |
| 12 | `within_bucket_ranking` |
| 13 | `result_rendering` |

Lo scoring occupa la posizione 11: viene dopo la
composizione dei bucket, e non prima. E' l'inversione rispetto al percorso
operativo, dove un candidato entra nel ranking e poi viene penalizzato. Una
penalita' e' un numero, e un numero puo' essere compensato da altri numeri;
un bucket no.

## I quattro bucket

| Bucket | Reso di default | Punteggio |
| --- | --- | --- |
| `primary_ranked_results` | si | ranking consentito |
| `retained_with_warning` | si | interno al bucket, dove il gate lo consente |
| `audit_only_results` | no | registrato, mai usato per ranking clinico |
| `rejected_by_native_constraints` | no | tutti gli score disabilitati |

I candidati esclusi non vengono eliminati: restano nella struttura e sono
recuperabili in modalita' di audit. Un retriever che li scartasse renderebbe
la propria selettivita' non verificabile, perche' l'unica cosa osservabile
sarebbe cio' che ha deciso di mostrare.

## Oggetti candidati

Entrano cinque famiglie, e nessuna delle ultime quattro puo' raggiungere il
bucket primario: lo stato dell'oggetto lo impedisce prima di ogni match.

- `active_claim`
- `deprecated_claim`
- `unsupported_association`
- `unresolved_association`
- `graph_evidence_record`

## Cosa resta vero per costruzione

- il corpus non viene modificato dal retriever: **true**
- nessun ranking cross-domain: **true**
- il limite per bucket e' un limite di rendering: **true**
- i pesi non sono stati ritarati: **true**
- il gold non ha contribuito ai pesi: **true**

## Controlli d'avvio

- `active_registry_entry`
- `promotion_status_is_prototype_promoted`
- `operational_retriever_bound_may_be_false`
- `repository_and_schema_versions_compatible`
- `manifest_and_files_intact`

`operational_retriever_bound` puo' essere falso, ed e' il caso normale
durante il binding test. Il campo dice che il percorso operativo non e'
stato spostato sul corpus promosso, non che il corpus sia inutilizzabile.

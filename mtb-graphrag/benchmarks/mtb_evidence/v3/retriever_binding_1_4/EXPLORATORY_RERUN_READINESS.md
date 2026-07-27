# Readiness del rerun esplorativo

Fase: `v3-retriever-binding/1.4`  
Repository: `qualified_claim_repository/1.4`  
Corpus: `31636f26c44bee03b16ed7d7c5e9b9580292f750e04b80e4effbaf9618ec39fa`  
Query di regressione: 14

| Flag | Valore |
| --- | --- |
| `promoted_corpus_loadable_by_v3_retriever` | **true** |
| `v3_retriever_implemented` | **true** |
| `backend_selection_explicit` | **true** |
| `legacy_default_preserved` | **true** |
| `unknown_backend_rejected` | **true** |
| `unknown_policy_rejected` | **true** |
| `strict_default_preserved` | **true** |
| `four_bucket_output_implemented` | **true** |
| `integrated_gates_applied` | **true** |
| `provenance_complete` | **true** |
| `dual_run_diagnostic_ready` | **true** |
| `operational_pipeline_unchanged_for_legacy` | **true** |
| `operational_retriever_bound_to_v3` | false |
| `v3_prototype_endpoint_ready` | **true** |
| `full_exploratory_rerun_ready` | **true** |
| `clinical_readiness` | false |

## Perche' `operational_retriever_bound_to_v3` resta falso

Il flag ha due letture, e questa fase ne soddisfa una sola. Il retriever V3
e' **selezionabile**: una configurazione esplicita lo raggiunge, lo esegue e
ne ottiene i quattro bucket. Il retriever V3 non e' **collegato**: il default
resta `legacy`, il percorso operativo non lo attraversa, e nessun endpoint
esistente ha cambiato contratto. Dichiarare vero il flag qui significherebbe
affermare la seconda lettura sulla base della prima.

## Perche' `clinical_readiness` resta falso

Nulla in questa fase e' stato confrontato con il gold. Il dual-run misura
*dove* i due backend divergono, non *quale dei due ha ragione*: e' una
preparazione del rerun, non una sua valutazione. Tutti i claim del corpus
restano `prototype_only`, con `hard_filterable` e `final_evaluable` falsi, e
una idoneita' clinica non si deduce da un retriever che funziona.

## Regressioni

| Query | primary | warning | audit | rejected | deterministica |
| --- | --- | --- | --- | --- | --- |
| `RB-01-EGFR-L858R-NSCLC` | 22 | 9 | 155 | 125 | **true** |
| `RB-02-EGFR-L858R-LUAD` | 9 | 22 | 155 | 125 | **true** |
| `RB-03-ALK-G1202R-NSCLC` | 0 | 0 | 147 | 164 | **true** |
| `RB-04-FGFR2-ICCA` | 0 | 1 | 151 | 159 | **true** |
| `RB-05-FGFR2-CCA` | 1 | 0 | 151 | 159 | **true** |
| `RB-06-DIAGNOSTIC-FGFR2-BICC1-ICCA` | 1 | 0 | 151 | 159 | **true** |
| `RB-07-INFIGRATINIB-FGFR2-ICCA` | 0 | 1 | 151 | 159 | **true** |
| `RB-08-BGJ398-FGFR2-ICCA` | 0 | 1 | 151 | 159 | **true** |
| `RB-09-AUY922` | 0 | 0 | 148 | 163 | **true** |
| `RB-10-INFIGRATINIB-PHOSPHATE` | 0 | 1 | 150 | 160 | **true** |
| `RB-11-INFIGRATINIB-HYDROCHLORIDE` | 0 | 0 | 150 | 161 | **true** |
| `RB-12-UNKNOWN-DRUG-CODE` | 0 | 0 | 153 | 158 | **true** |
| `RB-13-UNKNOWN-DISEASE` | 0 | 0 | 157 | 154 | **true** |
| `RB-14-UNTYPED-FGFR2-ICCA` | 1 | 1 | 150 | 159 | **true** |

## Dual-run

| Query | overlap | solo legacy | solo V3 | errori |
| --- | --- | --- | --- | --- |
| `RB-01-EGFR-L858R-NSCLC` | 15 | 5 | 15 | nessuno |
| `RB-02-EGFR-L858R-LUAD` | 9 | 1 | 21 | nessuno |
| `RB-03-ALK-G1202R-NSCLC` | 0 | 9 | 0 | nessuno |
| `RB-04-FGFR2-ICCA` | 0 | 0 | 1 | nessuno |
| `RB-05-FGFR2-CCA` | 1 | 1 | 0 | nessuno |
| `RB-06-DIAGNOSTIC-FGFR2-BICC1-ICCA` | 0 | 0 | 1 | nessuno |
| `RB-07-INFIGRATINIB-FGFR2-ICCA` | 0 | 0 | 1 | nessuno |
| `RB-08-BGJ398-FGFR2-ICCA` | 0 | 0 | 1 | nessuno |
| `RB-09-AUY922` | 0 | 0 | 0 | nessuno |
| `RB-10-INFIGRATINIB-PHOSPHATE` | 0 | 0 | 1 | nessuno |
| `RB-11-INFIGRATINIB-HYDROCHLORIDE` | 0 | 0 | 0 | nessuno |
| `RB-12-UNKNOWN-DRUG-CODE` | 0 | 0 | 0 | nessuno |
| `RB-13-UNKNOWN-DISEASE` | 0 | 0 | 0 | nessuno |
| `RB-14-UNTYPED-FGFR2-ICCA` | 0 | 0 | 2 | nessuno |

L'overlap si misura sul `GraphEvidenceRecord` e non sul numero di risultati.
Un `EvidenceStatement` legacy e un claim V3 non stanno in corrispondenza uno
a uno — `evidence:11240` ha due claim attivi da un solo parent — e
confrontare i due conteggi darebbe la differenza fra due misure di cose
diverse.

## Prossimo passo

Il rerun esplorativo comparativo sull'intero insieme di query, con il
backend V3 selezionato esplicitamente e il legacy ancora default. Le
metriche contro il gold restano fuori da questa fase e dalla successiva
finche' il confronto non e' stato prima descritto senza giudicarlo.

# Readiness della chiusura documentale

Versione: `non-therapeutic-source-closure/1.0`

## Flag

| Flag | Valore | Motivo |
|---|---|---|
| `evidence_347_full_text_available` | **false** | Nessun record PMC; editore HTTP 403 |
| `evidence_347_graph_direction_resolved` | **true** | Direzione prognostica rifiutata sull'abstract |
| `evidence_347_claim_decision_ready` | **false** | Scope predittivo irrisolto: serve il full text |
| `diagnostic_source_unit_first_review_complete` | **true** | `PU-PMID-24122810-cohort-1` revisionata |
| `diagnostic_claims_confirmed` | **false** | 0 confermati così come sono |
| `diagnostic_claims_require_revision` | **true** | 2, restringimento del disease scope |
| `second_review_packets_ready` | **true** | 3 packet ciechi e deterministici |
| `terminology_review_ready` | **false** | 4 gruppi e 2 mapping restano aperti, fuori perimetro |
| `shadow_repository_revision_ready` | **true** | La revisione è specificata; l'applicazione è la fase successiva |
| `corpus_promotion_ready` | **false** | Vedi sotto |
| `operational_retriever_migration_ready` | **false** | Vedi sotto |
| `full_exploratory_rerun_ready` | **false** | Vedi sotto |

## Cosa è stato chiuso

**La direzione prognostica di `evidence:347`.** Non serviva il full text per
stabilire che uno studio di interazione trattamento-biomarcatore non è uno
studio prognostico. Questa domanda è chiusa.

**La prima revisione della source unit `PMID:24122810`.** Completata
sull'abstract, con findings, limitazioni e locator per ciascuno.

**Il contenuto dei due claim diagnostici.** Sostenuto, ma con un perimetro più
largo di quello che la fonte misura.

## Cosa resta aperto

**Lo scope predittivo di `evidence:347`.** Il record non porta un intervento e
la fonte non dà un risultato separato per L858R. Nessuna delle due cose si
risolve leggendo meglio l'abstract.

**La seconda revisione indipendente.** Nessuno dei tre casi l'ha ricevuta, e
finché non l'ha nessun claim può diventare final.

**Il restringimento del disease scope.** Specificato, non applicato: cambia
l'identità dei due claim e appartiene a una revisione di repository.

## Perché `corpus_promotion_ready` resta false

Tre ragioni, nessuna delle quali questa fase poteva rimuovere.

I due claim diagnostici **richiedono una revisione** prima di essere stabili:
promuovere ora fisserebbe nel corpus un `disease_scope` più ampio di quello
misurato. `evidence:347` resta **bloccato in attesa del full text**. La
**seconda revisione indipendente** non è avvenuta, e le due source unit restano
`final_evaluable: false`.

## Perché `operational_retriever_migration_ready` resta false

Invariato rispetto alla fase precedente: il retriever operativo non conosce il
concetto di dominio, la disease hierarchy policy non è attiva, e il corpus non è
promosso. Nulla in questa fase ha toccato quel percorso.

## Perché `full_exploratory_rerun_ready` resta false

Nessuna metrica calcolata, gold non letto. Il restringimento pendente cambierebbe
inoltre due `claim_id`: un rerun ora produrrebbe numeri legati a identità
destinate a cambiare.

## Blocker

| Blocker | Impatto |
|---|---|
| Full text di `PMID:24662454` non recuperabile | `evidence_347_claim_decision_ready`, `corpus_promotion_ready` |
| Full text di `PMID:24122810` non recuperabile | `final_evaluable` della source unit |
| Disease scope da restringere su 2 claim | `corpus_promotion_ready` |
| Seconda revisione indipendente assente | `corpus_promotion_ready` |
| 4 gruppi + 2 mapping terminologici | `terminology_review_ready` |
| Retriever operativo senza domini, hierarchy policy inattiva | `operational_retriever_migration_ready` |

## Nota sull'accesso

Entrambe le fonti sono indicizzate come open access «bronze» e nessuna delle due
è risultata recuperabile. Vale la pena registrarlo: se l'accesso fosse ottenuto
per altra via — abbonamento istituzionale, richiesta agli autori — due delle
domande aperte diventerebbero decidibili senza altro lavoro di modello.

## Prossimo passo

Applicare il restringimento del disease scope ai due claim diagnostici nel
repository shadow, ritirando i due `claim_id` correnti e creandone due nuovi con
`Intrahepatic Cholangiocarcinoma`. In parallelo, sottoporre i tre packet ciechi
a una seconda revisione indipendente e cercare un accesso al full text di
`PMID:24662454` per sciogliere `evidence:347`.

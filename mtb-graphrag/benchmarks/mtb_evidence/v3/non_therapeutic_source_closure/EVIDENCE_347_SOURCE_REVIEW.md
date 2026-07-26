# evidence:347 — revisione documentale

| | |
|---|---|
| Graph evidence ID | `evidence:347` |
| Statement legacy | `ES-V2-evidence-347` |
| Fonte | `PMID:24662454` · DOI `10.1097/JTO.0000000000000141` |
| Rivista | Journal of Thoracic Oncology, 2014-05 |
| Materiale usato | abstract indicizzato, SHA-256 `69fcd4af71ddb5dc…` |
| Stato di accesso | **`full_text_unavailable`** |

## Accesso alla fonte

L'ordine di priorità è stato percorso per intero prima di dichiarare
l'indisponibilità.

| Priorità | Canale | Esito |
|---|---|---|
| 1 | full text locale | assente |
| 2 | supplementi locali | assenti |
| 3 | PMC open access | `Identifier not found in PMC` |
| 3 | indice OA (Unpaywall) | `is_oa: true`, `oa_status: bronze` — dichiarato gratuito sul sito editore, non recuperabile |
| 4 | sito editore (ScienceDirect) | HTTP 403 |
| 4 | PDF editore (jto.org) | HTTP 403 |
| 5 | abstract indicizzato | **disponibile** |

Nessuna fonte secondaria è stata usata. Nessun contenuto è stato ricostruito.

## Le dieci domande

| # | Domanda | Risposta | Locator |
|---|---|---|---|
| 1 | Trattamento studiato | cetuximab aggiunto a cisplatino e vinorelbina, prima linea | INTRODUCTION s0 |
| 2 | Cetuximab è l'intervento esplicito | **sì nella fonte, no nel record del grafo** | INTRODUCTION s0 |
| 3 | Popolazione | pazienti FLEX (NCT00148798), screening su 971/1125 (86%) | METHODS s0 |
| 4 | Biomarcatore valutato | stato mutazionale EGFR esoni 18-21 **come gruppo**, incrociato con espressione EGFR | METHODS s1 |
| 5 | L858R ha un risultato separato | **no** | RESULTS s1 |
| 6 | Exon 19 deletion ha un risultato separato | **no** | RESULTS s1 |
| 7 | Il risultato riguarda | interazione biomarcatore-trattamento su overall survival, più un dato di risposta | RESULTS s2 |
| 8 | Interpretazione predittiva possibile | solo a livello di **espressione** EGFR, non di stato mutazionale | CONCLUSIONS s0 |
| 9 | Separabile statisticamente per L858R | **no** | RESULTS s3 |
| 10 | Record correggibile senza toccare biomarcatore/intervento/popolazione | **no** | — |

## Perché la direzione prognostica è rifiutata

Il grafo classifica `evidence:347` come `prognostic` su EGFR L858R. La fonte non
riporta alcun esito prognostico: misura se l'effetto del trattamento sia
modulato dallo stato mutazionale.

> «We assessed whether the treatment effect was also modulated in FLEX study
> patients by tumor EGFR mutation status.» — INTRODUCTION s1

L858R compare **una sola volta** in tutto l'abstract, e non in un risultato:

> «The most common mutations were exon 19 deletions and L858R (124 of 133
> patients; 93%).» — RESULTS s1

È una frase sulla composizione mutazionale della popolazione screenata, e per di
più aggrega L858R con exon 19 deletion. Confonderla con un risultato sul
biomarcatore sarebbe la trasformazione «composizione della popolazione →
risultato sul biomarcatore», che il contratto vieta.

**Decisione: `graph_prognostic_direction_rejected`.** Questa parte è chiusa, e
lo è sull'abstract: non serve il full text per stabilire che uno studio di
interazione trattamento-biomarcatore non è uno studio prognostico.

## Perché nessun claim predittivo viene proposto

Il disegno *è* predittivo. Non basta.

**Il record non porta un intervento.** Cetuximab è nella fonte, non nel record
del grafo. Costruirvi sopra una proposizione terapeutica significherebbe
aggiungerlo — cioè inventare l'intervento, che è precisamente l'errore da cui
questa intera linea di lavoro è cominciata con `evidence:275`.

**Non c'è un risultato per L858R.** Il gruppo mutato è trattato come un blocco
unico, i numeri sono dichiarati piccoli e il linguaggio è condizionale:

> «Although patient numbers were small, those in the high EGFR expression group
> whose tumors carried EGFR mutations **may also have derived** a survival
> benefit…» — RESULTS s3

**La conclusione sullo stato mutazionale è di assenza di modificazione.**

> «The survival benefit … **is not limited by** EGFR mutation status.» —
> CONCLUSIONS s0

Un'interazione dichiarata assente non è un beneficio. Trasformarla in uno
sarebbe la trasformazione «interazione non significativa → beneficio».

**Decisione: `predictive_scope_unresolved` + `insufficient_source_access`.**

## Esito

| | |
|---|---|
| Claim creati | **0** |
| Proposta di claim | **nessuna** (`proposal_made: false`) |
| Intervento inventato | **no** |
| Nuovi claim type introdotti | **0** |
| Direzione prognostica | **rifiutata** |
| Scope predittivo | **irrisolto**, serve il full text |
| Stato statement legacy | `promotion_blocked_pending_full_text`, invariato |
| Locator | sufficiente per il rifiuto, insufficiente per un claim |

Il rifiuto della direzione prognostica chiude una domanda senza aprirne
un'altra: il record non acquisisce nulla. Il blocker sul full text resta.

## Riapertura

Quando il full text di `PMID:24662454` diventa disponibile e riporta un esito
separato per L858R, oppure quando il record del grafo acquisisce un intervento
documentato.

Un packet cieco di seconda revisione — `SR-evidence-347.json` — è predisposto
con l'abstract, le dieci domande e il vocabolario delle decisioni ammesse, senza
la conclusione del primo reviewer.

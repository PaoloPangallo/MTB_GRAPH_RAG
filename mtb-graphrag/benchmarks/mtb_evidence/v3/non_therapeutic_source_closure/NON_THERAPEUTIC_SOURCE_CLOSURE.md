# Chiusura documentale dei record non terapeutici

Versione: `non-therapeutic-source-closure/1.0`
Reviewer: `author_first_reviewer` · indipendenza: `non_independent`
Gold: non usato · corpus operativo: non modificato · repository shadow: non modificato

Due questioni separate, chiuse per quanto le fonti consentono e non oltre.

## Accesso alle fonti

Nessuno dei due full text è stato acquisito. L'ordine di priorità è stato
percorso per intero su entrambi.

| Fonte | PMC | Indice OA | Editore | Esito |
|---|---|---|---|---|
| `PMID:24662454` | non presente | `bronze` dichiarato | HTTP 403 | `full_text_unavailable` |
| `PMID:24122810` | non presente | `bronze` dichiarato | HTTP 402 | `full_text_unavailable` |

Entrambi sono indicizzati come open access «bronze» — gratuiti sul sito
dell'editore senza licenza esplicita — e nessuno dei due si è lasciato
recuperare. La discrepanza fra lo stato dichiarato e l'accesso reale è
registrata negli artefatti invece che appianata.

Il materiale realmente letto è l'abstract strutturato di ciascuna fonte, già in
cache locale da `pubmed_efetch`, con hash ricalcolato e verificato. Nessuna
fonte secondaria. Nessun contenuto ricostruito. Nessun file di full text esiste,
quindi nessun hash di full text è stato inventato.

## A — `evidence:347`

**Direzione prognostica del grafo: rifiutata.** La fonte è un'analisi
dell'effetto di cetuximab modulato dallo stato mutazionale di EGFR. Non riporta
alcun esito prognostico. L858R compare una sola volta, in una frase sulla
composizione della popolazione, aggregata con exon 19 deletion.

**Nessun claim creato.** Il disegno è predittivo, ma il record del grafo non
porta un intervento e la fonte non dà un risultato separato per L858R. La
conclusione sullo stato mutazionale è per di più di *assenza* di modificazione
dell'effetto: «not limited by EGFR mutation status».

Decisioni: `graph_prognostic_direction_rejected` + `predictive_scope_unresolved`
+ `insufficient_source_access`.

Lo statement legacy resta `promotion_blocked_pending_full_text`. Il rifiuto
chiude una domanda senza aprirne un'altra.

## B — `PMID:24122810`

**Source unit: prima revisione completata.** `first_review_complete`,
`non_independent`, `prototype_only`, `hard_filterable: false`,
`final_evaluable: false`. La unit operativa non è stata toccata.

**Entrambi i claim diagnostici: `diagnostic_claim_requires_narrowing`.**

Il contenuto è sostenuto — le fusioni sono nominate, il ruolo di sottotipo è
esplicito, la specificità di malattia è documentata, la mutua esclusività è
riportata. Il perimetro no: la fonte misura e conclude sul sottotipo
**intraepatico**, mentre i claim portano `disease_scope: Cholangiocarcinoma`.

La prevalenza resta aggregata: il 13,6% è delle fusioni FGFR2 nel loro insieme e
non viene ripartito fra BICC1 e AHCYL1. Nessuna utilità clinica è dedotta.

## Simulazione dell'aggiornamento shadow — non applicata

| Grandezza | Valore |
|---|---|
| Claim confermati così come sono | 0 |
| Claim da modificare | 2 |
| Claim da ritirare | 2 |
| Claim da creare dopo il restringimento | 2 |
| Totale EvidenceClaim dopo | **148**, invariato |
| Link da ritirare / creare | 2 / 2 |
| View da rigenerare | 2 |

Il totale non cambia perché ogni claim ristretto sostituisce sé stesso. Ma
`disease_scope` entra nell'identità del claim: restringerlo produce ID nuovi, e i
vecchi vanno ritirati invece che modificati sul posto. È la ragione per cui
questa fase non applica nulla — riscrivere due `claim_id` nel repository 1.1 è
una revisione di repository, non una revisione di fonte.

`evidence:347` resta un parent senza claim, con il blocker sul full text
mantenuto.

## Cosa questa fase non ha fatto

Non ha creato claim dal solo disegno predittivo. Non ha inventato un intervento.
Non ha attribuito una prevalenza aggregata a un singolo partner. Non ha dedotto
utilità clinica. Non ha introdotto nuovi claim type. Non ha promosso mapping
terminologici. Non ha toccato la disease hierarchy. Non ha letto il gold. Non ha
modificato corpus, adapter, retriever, scoring, né i repository shadow 1.0 e 1.1.

## Locator

Ogni decisione porta sezione e indice di frase dell'abstract. Il solo PMID non
compare mai come locator. Dove il locator è sufficiente per rifiutare ma non per
affermare — il caso di `evidence:347` — questo è dichiarato invece che
arrotondato.

## Seconda revisione

Tre packet ciechi, deterministici e byte-identical alla rigenerazione:
`SR-evidence-347.json`, `SR-evidence-1846.json`, `SR-evidence-1847.json`.
Portano il materiale, le domande e il vocabolario ammesso. Non portano decisioni,
reason code, limitazioni assegnate né raccomandazioni: un packet che suggerisce
la risposta non produce una revisione indipendente, produce una conferma.

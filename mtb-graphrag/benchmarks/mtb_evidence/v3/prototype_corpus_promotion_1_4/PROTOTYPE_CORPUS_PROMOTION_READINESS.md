# Readiness della promozione prototipale 1.4

Repository: `qualified_claim_repository/1.4`  
Modello: `qualified_claim_model/1.2`  
Stato: `prototype_promoted`  
Percorso: `backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4`  
Deriva da: `qualified_claim_repository/1.4` (`22d5d730969277ea`)

| Gate | Valore |
|---|---|
| `prototype_corpus_promotion_applied` | **true** |
| `prototype_corpus_registry_updated` | **true** |
| `atomic_write_verified` | **true** |
| `rollback_tested` | **true** |
| `promoted_inventory_consistent` | **true** |
| `promoted_lineage_complete` | **true** |
| `promoted_links_consistent` | **true** |
| `promoted_views_consistent` | **true** |
| `strict_default_explicit` | **true** |
| `unknown_mode_rejected` | **true** |
| `all_claims_prototype_only` | **true** |
| `no_claim_final_evaluable` | **true** |
| `operational_pipeline_unchanged` | **true** |
| `operational_retriever_migration_ready` | **true** |
| `operational_retriever_bound` | false |
| `full_exploratory_rerun_ready` | false |
| `clinical_readiness` | false |

## Inventario promosso

I conteggi sono derivati rileggendo i file scritti, non copiati dal
manifest della 1.4.

| Voce | Valore |
|---|---:|
| parent | `147` |
| claim attivi | `148` |
| terapeutici | `146` |
| diagnostici | `2` |
| prognostici | `0` |
| atomic | `140` |
| aggregate | `3` |
| regimen | `3` |
| unsupported | `6` |
| unresolved | `6` |
| deprecated (esclusi dagli attivi) | `4` |
| parent senza claim | `3` |
| claim orfani | `0` |
| collisioni di ID | `0` |
| deduplicazioni | `0` |
| claim ID cambiati | `0` |

Conteggi coincidenti con quelli attesi: **true**.

## Cosa significa `prototype_promoted`

Che il contenuto della 1.4 esiste in una namespace versionata, con hash,
manifest, registro e procedura di rollback, ed e' caricabile da un loader
in sola lettura.

Cio' che **non** significa. Non significa che il retriever operativo lo
usi: `operational_retriever_bound` e' false,
nessun modulo del percorso operativo importa la namespace promossa, e la
query operativa restituisce prima e dopo gli stessi 21
risultati con la stessa serializzazione e lo stesso digest
`af0389673a9a8b0566bce20bf68685b3abc04baf8542e183888d9a84cb365124`.

Non significa che il contenuto sia clinicamente valido. Promuovere e' un
fatto di versionamento: tutti i 148 claim restano
`prototype_only`, nessuno e' `final_evaluable`, nessuno e'
`hard_filterable`, e la revisione resta non indipendente. Se la promozione
potesse cambiare quei campi, "versionato" e "clinicamente valido"
sarebbero la stessa affermazione.

## Cosa cambia rispetto alla 1.4 shadow

`operational_retriever_migration_ready` passa da falso a vero, e il
cambiamento riguarda la disponibilita' del corpus, non la capacita' del
retriever. Prima non c'era un corpus versionato verso cui migrare; ora c'e',
ed e' caricabile, hashato e reversibile. Il retriever operativo continua a
non conoscere i quattro bucket, le undici relazioni di malattia e le otto
relazioni di forma: insegnargliele e' la fase successiva, e questa non
l'ha anticipata.

`full_exploratory_rerun_ready` resta falso per la stessa ragione di prima.
Un rerun sopra un corpus che nessuna query raggiunge misurerebbe la
pipeline corrente, non quella promossa.

## L'unica normalizzazione applicata

Due dei quattro claim ritirati —
`CLM-a7c903cf8d423f015e29`, `CLM-aae818bbc8ec735a255d` — furono deprecati prima che il modello 1.2 rendesse obbligatori i campi
di propagazione. Promuoverli senza avrebbe lasciato nel corpus esattamente
il buco che la 1.4 ha chiuso, e avrebbe costretto il loader a un'eccezione
per i record storici, cioe' a un default in lettura.

I campi mancanti sono *dichiarati* con gli stessi valori che la 1.4
dichiara per i claim attivi. Proposizioni toccate dal cambio di schema:
`0`. Claim ID cambiati:
`0`.

## Terminologia e forme

`AUY922` resta irrisolto (**true**) e in attesa
di `require_external_review`. Il letterale `BGJ398` resta nella
fonte, con `infigratinib` come etichetta canonica
verificata. Nuovi mapping introdotti dalla promozione:
`0`. Normalizzazione per
suffisso usata: false.

Il costo di copertura resta quello che era:
`12` claim
atomici in forma salina escono dal bucket primario per una query sulla
moiety nuda. L'elenco e' quello che la 1.4 aveva scritto, non uno
ricalcolato qui. Gate rilassato dalla promozione:
false. Forme risolte dalla
promozione: `0`.

| Forma | Esito |
|---|---|
| `infigratinib phosphate` | `retained_with_warning` |
| `alectinib hydrochloride` | `audit_only` |
| `infigratinib hydrochloride` | `audit_only` |
| `neratinib maleate` | `audit_only` |

## Link e view

Le `37` azioni del piano di link e le
`4` del piano di view sono applicate, e solo nella
namespace V3. Negli artefatti shadow `executed` resta `false`
(**true**): nel corpus promosso e'
`true`, e i due valori compaiono nella stessa riga dell'artefatto di audit
perche' "il piano e' stato eseguito" e "il piano e' stato eseguito nella
namespace V3" sono affermazioni diverse e solo la seconda e' vera.

Link attivi: `17`. Ritiri: `20`.
Link attivi verso un claim ritirato:
`0`. Duplicati:
`0`.

View materializzate: `2`, tutte diagnostiche e in
sezione diagnostica, senza therapy score
(`0`) e senza ranking cross-domain
(false). Verificate senza rigenerare:
`2`. Membri appiattiti in view
separate: `0`. View orfane:
`0`.

## Cosa resta aperto

La revisione terminologica esterna, in cui `AUY922` aspetta dalla
terminology closure e in cui ora aspettano anche le forme saline senza
fonte.

La revisione documentale dei claim che non ne hanno mai avuta una.

Il collegamento del retriever operativo, che e' una decisione esplicita e
una fase separata: la promozione prototipale non lo implica, e il registro
lo dichiara invece di lasciarlo dedurre.

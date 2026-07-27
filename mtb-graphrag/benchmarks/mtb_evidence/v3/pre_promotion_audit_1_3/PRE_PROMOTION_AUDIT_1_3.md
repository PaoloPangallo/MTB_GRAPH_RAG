# Audit pre-promozione del repository shadow 1.3

Repository esaminato: `qualified_claim_repository/1.3`
Fase: `pre-promotion-audit/1.3`  
Promozione applicata: false  
Piani eseguiti: false  
Gold usato: false

L'audit e' read-only e deriva ogni conclusione dai file della 1.3. Il
manifest della 1.3 e' stato caricato per essere confrontato con i dati,
non per sostituirli: un manifest che si autodichiara coerente non e' una
verifica.

## Inventario

| Voce | Derivato | Atteso |
|---|---:|---:|
| `active_claims_total` | 148 | 148 |
| `aggregate_claims` | 3 | 3 |
| `atomic_claims` | 140 | 140 |
| `diagnostic_claims` | 2 | 2 |
| `parents` | 147 | 147 |
| `parents_without_claims` | 3 | 3 |
| `prognostic_claims` | 0 | 0 |
| `regimen_claims` | 3 | 3 |
| `therapeutic_claims` | 146 | 146 |
| `unresolved_associations` | 6 | 6 |
| `unsupported_associations` | 6 | 6 |

Conteggi coerenti con l'atteso: **true**  
Conteggi coerenti con il manifest: **true**  
Inventario coerente: **true**

### Riconciliazione parent → claim

| Voce | Totale |
|---|---:|
| parent | 147 |
| claim attivi | 148 |
| claim ritirati | 4 |
| associazioni unsupported | 6 |
| associazioni unresolved | 6 |
| parent senza claim attivo | 3 |

I tre parent senza claim sono `evidence:347`, `evidence:3811`, `evidence:4759`. Non sono una lacuna: nessuna fase ha materializzato un claim da
quei record, e inventarne uno ora rifarebbe l'inferenza che le fasi
precedenti hanno rifiutato.

### Integrita' strutturale

| Controllo | Esito |
|---|---|
| nessun claim orfano | **true** |
| nessun child verso parent inesistente | **true** |
| ogni claim elencato dal proprio parent | **true** |
| nessun ritirato fra gli attivi | **true** |

## Identita'

Identita' ricalcolate: **311**  
ID non riproducibili: **0**  
Collisioni: **0**

Ogni ID e' stato ricalcolato dai soli campi che la riga porta, senza
chiedere al generatore di rifarlo. Due dettagli rendono la ricomputazione
possibile a partire dal file, e chi promuovera' il corpus deve
riprodurli: la source unit di identita' dei claim legacy e' il token
`SU-24122810-nih3t3-fgfr-inhibitor-…`, non un elemento di
`source_unit_ids`; e la forma canonica dell'intervento e' minuscola per i
claim legacy e non per quelli adjudicati.

## Provenance

| Classe di assenza | Occorrenze |
|---|---:|
| `propagation_policy → promotion_blocking` | 6 |
| `source_id → expected_for_legacy_migrated_claim` | 131 |

Le due popolazioni della 1.3 hanno storie diverse e non vanno misurate
con la stessa asticella. I 131 claim migrati dal legacy non hanno mai
avuto una revisione documentale e lo dichiarano; chiedere loro un locator
significherebbe chiedere di inventarlo. I 17 adjudicati lo portano.

Resta una assenza che non e' spiegata da nessuna delle due storie: `CLM-4a89bb28592af7ebaccf`, `CLM-4ffe85304f3ef5533b58`, `CLM-5071bb2d8657ac0fbed0`, `CLM-5ce49705979f72f174e9`, `CLM-90e863f00f134fc3cd3d`, `CLM-ac64c0e56246f6ea29ca` non serializzano `propagation_policy`.

## Piani

| Piano | Azioni | Coerente |
|---|---:|---|
| qualification link | 37 | **true** |
| qualified view | 4 | **true** |

Le 37 azioni di link si riconciliano cosi': 2 retire e 2 create per la
terminologia, 2 retire e 2 create per il
restringimento diagnostico, 29 portate dalle fasi precedenti.
Nessuna e' eseguita.

Le 4 azioni di view sono 4 e non 2 per la ragione descritta
nell'artefatto: due sono rigenerazioni diagnostiche vere, due sono
**verifiche** che le view operative non nominino ne' il vecchio ne' il
nuovo ID dei claim terminologici. Le view operative sono indicizzate per
legacy statement e non per claim ID, quindi i due claim canonicalizzati
non vi compaiono — e il modo di dimostrarlo e' contare le occorrenze,
non assumerle.

## Gate integrati

| Caso | Bucket in strict_verified | Gate bloccanti |
|---|---|---|
| `arbitrarily-high-score` | `rejected_by_native_constraints` | `biomarker` |
| `deprecated-with-everything-exact` | `audit_only_results` | `claim_status`, `intervention` |
| `disease-child-biomarker-exact` | `retained_with_warning` | `disease` |
| `disease-exact-regimen-component` | `retained_with_warning` | `intervention` |
| `exact-disease-biomarker-incompatible` | `rejected_by_native_constraints` | `biomarker` |
| `mapping-pending-with-everything-exact` | `audit_only_results` | `intervention` |
| `unsupported-with-everything-exact` | `audit_only_results` | `claim_status`, `claim_domain`, `intervention` |

Bypass osservati: **0**  
Flag di score sopravvissuti fuori dai bucket ordinabili: **0**

Il caso del punteggio arbitrariamente alto non sposta niente, ed e' il
punto: il numero non entra in nessuna delle espressioni del gate.

## Policy di default

| Voce | Valore |
|---|---|
| `declared_default_mode` | `strict_verified` |
| `declared_default_mode_field` | `policy.default_mode` |
| `strict_default_explicit` | **true** |
| `behaviour_default_mode` | `strict_verified` |
| `behaviour_rejects_unknown_mode` | **true** |
| `unknown_mode_rejection_declared` | false |
| `fallback_to_broader_mode_declared` | false |

Il default e' dichiarato machine-readably in `policy.default_mode` del
manifest della 1.3, e il comportamento coincide. Cio' che non e'
dichiarato e' che cosa accada a una modalita' sconosciuta: il codice la
rifiuta, il manifest tace. Un consumatore che implementasse la pipeline
dal solo manifest potrebbe scegliere un fallback invece di un errore, ed
e' per questo che la dichiarazione entra fra le correzioni richieste alla
promozione.

## Integrita' della fase

Artefatti congelati invariati: **true**  
Parita' della query operativa: **true**  
Record di gold letti: **0**

Il bundle gold e' stato sottoposto a checksum senza essere
deserializzato: dimostrare che non e' cambiato non richiede leggerne il
contenuto, e la distinzione e' registrata nell'artefatto perche' non
vada perduta.


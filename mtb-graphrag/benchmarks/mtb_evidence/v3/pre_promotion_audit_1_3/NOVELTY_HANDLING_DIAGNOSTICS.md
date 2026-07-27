# Conservative novelty-handling diagnostics

Queste misure **non sono accuratezza di generalizzazione** e non vanno
chiamate cosi'. Non esiste nessun riferimento clinico: i casi sono
sintetici, l'esito atteso e' derivato dalle sole tabelle congelate, e cio'
che viene misurato e' se il sistema si astiene quando non sa — non se ha
ragione.

Non sono una misura di: *clinical accuracy*, *generalization accuracy*, *recall on unseen entities*.

## Sintesi

| Misura | Valore |
|---|---:|
| unseen terms tested | 20 |
| exact promotions | 3 |
| unresolved outcomes | 4 |
| rejected outcomes | 13 |
| **false automatic merges** | **0** |
| **gate bypasses observed** | **0** |
| mapping creati da questa diagnostica | 0 |
| letterali di query riscritti | 0 |

## Terminologia

| Caso | Termine di query | Match type | Esito | Atteso |
|---|---|---|---|---|
| `case-and-whitespace-variation` | `  INFIGRATINIB  ` | `exact_atomic_intervention` | `normalized_exact` | **true** |
| `graphic-variation-of-known-code` | `BGJ-398` | `incompatible` | `rejected` | **true** |
| `hyphenated-unresolved-code` | `AUY-922` | `incompatible` | `rejected` | **true** |
| `near-miss-development-code` | `BGJ399` | `incompatible` | `rejected` | **true** |
| `pending-alias-of-canonical-term` | `BGJ398` | `mapping_pending` | `candidate_unresolved` | **true** |
| `salt-form-in-registered-suffix-table` | `infigratinib hydrochloride` | `normalized_atomic_intervention` | `normalized_exact` | **true** |
| `salt-form-of-canonical-term` | `infigratinib phosphate` | `incompatible` | `rejected` | **true** |
| `shared-prefix-different-concept` | `infi` | `incompatible` | `rejected` | **true** |
| `shared-substring-different-concept` | `infigratinib-like inhibitor` | `incompatible` | `rejected` | **true** |
| `unknown-development-code` | `QRX-88213` | `incompatible` | `rejected` | **true** |
| `unregistered-vendor-prefix` | `NVP-AUY922` | `incompatible` | `rejected` | **true** |

Nessun termine mai visto e' diventato exact per sottostringa, prefisso,
distanza di edit, appartenenza alla stessa classe o conoscenza non
registrata. `BGJ-398` e `NVP-AUY922` — le due variazioni grafiche che
un lettore umano riconoscerebbe — restano respinte, e questo e' l'esito
corretto: riconoscerle richiederebbe una regola che nessuno ha scritto.

Un caso merita di essere letto per intero. `infigratinib hydrochloride`
diventa `normalized_atomic_intervention`, quindi primario, perche'
`hydrochloride` e' nella tabella dei suffissi salini. `infigratinib
phosphate` resta `incompatible`, perche' `phosphate` non c'e'. La 1.3
porta pero' nella propria terminology provenance il caveat opposto: il
sale ha concept id proprio e non viene fuso nella moiety. Le due regole
sono entrambe registrate, si contraddicono, e il repository contiene 12
claim atomici con un intervento in forma salina — quindi la
contraddizione e' raggiungibile, non teorica.

## Malattia

| Caso | Query | Claim scope | Relazione | Atteso |
|---|---|---|---|---|
| `both-terms-unregistered` | `Foobaroma` | `Bazqux Carcinoma` | `unresolved_disease_relation` | **true** |
| `missing-claim-disease` | `Cholangiocarcinoma` | *(assente)* | `missing_claim_disease` | **true** |
| `missing-query-disease` | *(assente)* | `Cholangiocarcinoma` | `missing_query_disease` | **true** |
| `near-miss-of-registered-abbreviation` | `NSCLCx` | `Non-Small Cell Lung Cancer` | `cross_disease` | **true** |
| `registered-alias-still-works` | `NSCLC` | `Non-Small Cell Lung Cancer` | `verified_disease_alias` | **true** |
| `subtype-not-in-hierarchy` | `Squamoid Cholangiocarcinoma` | `Cholangiocarcinoma` | `cross_disease` | **true** |
| `unknown-disease-entirely` | `Xanthic Neoplasm of the Falx` | `Cholangiocarcinoma` | `cross_disease` | **true** |
| `unregistered-abbreviation` | `NSCLC-A` | `Non-Small Cell Lung Cancer` | `cross_disease` | **true** |
| `unregistered-generic-tumor-phrase` | `tumor of unknown primary origin` | `Cholangiocarcinoma` | `cross_disease` | **true** |

Nessuna malattia mai vista e' diventata un alias verificato, e le due
assenze restano distinte: `missing_query_disease` non e'
`missing_claim_disease`, e nessuna delle due e' `cross_disease`. Un
sottotipo non registrato non diventa un child: la gerarchia non viene
estesa per somiglianza morfologica del nome.

Resta una imprecisione di vocabolario, registrata come informational.
Quando un solo termine e' ancorato al vocabolario congelato la relazione
diventa `cross_disease`, cioe' *sono malattie diverse*, dove sarebbe piu'
esatto dire che la relazione non e' registrata. In strict_verified
l'esito e' identico — respinto — ma l'affermazione e' piu' forte di cio'
che i dati autorizzano.


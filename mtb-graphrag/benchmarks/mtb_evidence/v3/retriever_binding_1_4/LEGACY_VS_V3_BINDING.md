# Legacy contro V3: il binding

Backend disponibili: `legacy`, `qualified_claim_v3`  
Default: `legacy`  
Policy di default: `strict_verified`  
Policy ammesse: `strict_verified`, `ontology_aware_warning`, `audit_all`

## La selezione e' una dichiarazione

Non c'e' una regola che deduca il backend dalla forma della query, e non ce
n'e' una che scelga il corpus piu' recente fra quelli presenti sul disco.
Entrambe farebbero dipendere il comportamento della pipeline da cio' che e'
stato promosso, e la promozione della 1.4 e' avvenuta con la promessa
opposta.

| Caso | Comportamento |
| --- | --- |
| backend sconosciuto | `reject` |
| repository version sconosciuta | `reject` |
| policy mode sconosciuta | `reject` |
| fallback silenzioso | false |
| selezione automatica del corpus piu' recente | false |

## Esiti misurati

| Caso | Rifiutato |
| --- | --- |
| `known_backend_legacy` | false |
| `known_backend_v3` | false |
| `known_policy_mode_audit_all` | false |
| `unknown_backend` | **true** |
| `unknown_policy_mode` | **true** |
| `unknown_repository_version` | **true** |

## Il risultato e' una union tipizzata

La pipeline restituisce l'oggetto che il backend ha prodotto, non
convertito. La conversione sarebbe la cosa piu' comoda e la piu' sbagliata:
appiattire i claim V3 sugli statement legacy perderebbe i bucket, e
appiattire gli statement legacy sui claim V3 affermerebbe una granularita'
che il percorso operativo non ha.

- output legacy convertito in V3: false
- V3 e' il default: false
- il binding vive nel corpus: false
- backend costruito pigramente: **true**

## Isolamento del percorso legacy

La misura viene da un processo separato: dentro il processo che genera
questi artefatti il modulo V3 e' gia' importato, e osservare `sys.modules`
li' non direbbe nulla su cosa una run legacy carica per conto proprio.

- default osservato nel processo pulito: `legacy`
- backend istanziati: ['legacy']
- moduli del corpus V3 importati: []
- invocazioni del loader promosso: 0
- loader non inizializzato sotto legacy: **true**

## Parita' del percorso legacy

- serializzazione identica fra retriever diretto e adattatore: **true**
- query divergenti: nessuna
- default configurato: `legacy`

Le query legacy che il contratto d'ingresso rifiuta restano registrate come
rifiutate su entrambi i lati: un rifiuto identico e' anch'esso una parita',
e nasconderlo renderebbe il confronto piu' pulito di quanto sia.

# Politica gerarchica sulla disease

Fase `disease-hierarchy-policy/1.0` — contratto `directional-disease-match-contract/1.0`.

## Il problema

Il matcher operativo riconosce gia' la gerarchia, ma la nomina in modo che
non si puo' leggere. `explicit_parent` non dice di chi sia parent, e
cross-disease, relazione irrisolta e disease mancante finiscono tutti in
`unresolved`. Il risultato pratico e' corretto — nessuna di queste relazioni
e' hard match — ma non e' spiegabile a chi legge un risultato.

Questi due casi non sono lo stesso caso:

```
query  Cholangiocarcinoma                claim  Intrahepatic Cholangiocarcinoma
  -> claim_is_child_of_query
     l'evidenza vale solo per un sottotipo della query

query  Intrahepatic Cholangiocarcinoma   claim  Cholangiocarcinoma
  -> claim_is_parent_of_query
     il risultato generale non e' separabile per il sottotipo chiesto
```

Nel primo caso generalizzare inventerebbe una copertura che la fonte non ha.
Nel secondo specializzare inventerebbe una separabilita' che la fonte non
dichiara. Sono errori diversi e vanno nominati diversamente.

## Le relazioni

| relazione | direzione | exact | regola sui dati congelati |
|---|---|---|---|
| `exact_disease` | `none` | si | i due letterali coincidono dopo il solo strip |
| `normalized_exact_disease` | `none` | si | split_disease(...).core coincide |
| `verified_disease_alias` | `none` | si | i due core appartengono allo stesso gruppo di _SYNONYM_GROUPS |
| `claim_is_child_of_query` | `claim_narrower_than_query` | no | _parent_key(claim) == _canonical_key(query) |
| `claim_is_parent_of_query` | `claim_broader_than_query` | no | _parent_key(query) == _canonical_key(claim) |
| `disease_sibling` | `lateral` | no | _parent_key(query) == _parent_key(claim) con canonical key diversi |
| `generic_cancer_scope` | `claim_broader_than_query se generico e' il claim, claim_narrower_than_query se generica e' la query, lateral se lo sono entrambi` | no | almeno un core appartiene a generic_scope_keys |
| `cross_disease` | `none` | no | nessuna relazione congelata, ma almeno un core e' registrato |
| `unresolved_disease_relation` | `unknown` | no | nessuna relazione congelata e nessun core registrato |
| `missing_query_disease` | `unknown` | no | il core della disease della query e' vuoto |
| `missing_claim_disease` | `unknown` | no | il core del disease scope del claim e' vuoto |

La direzione e' calcolata, non asserita: nasce dal confronto fra
`_parent_key` e `_canonical_key`, non da una tabella scritta a mano.

Nessuna relazione nuova viene creata. Le sole fonti sono `_SUBTYPE_OF` e
`_SYNONYM_GROUPS` gia' congelati in `audit_lib/disease.py`, piu' il
registro degli scope generici, che e' locale a questa fase e non viene
applicato al matcher operativo.

## Cio' che la politica vieta

- Un risultato su iCCA non viene generalizzato a tutti i colangiocarcinomi.
- Un risultato su tutti i colangiocarcinomi non viene specializzato su iCCA.
- Un sibling non e' mai exact: `evidence:8173` resta audit-only per una
  query iCCA, perche' il carcinoma colangiolocellulare non e' iCCA.
- Uno scope generico non e' un alias della disease della query.
- Un cross-disease non riceve punteggio positivo, neppure con biomarcatore
  e intervento exact.
- Una disease mancante non viene collassata in cross-disease: non sapere
  non e' sapere che sono diverse.

## Copertura sul corpus

Relazioni osservate sui claim dello shadow 1.2: 9 tipi su 11.

| relazione | occorrenze |
|---|---|
| `claim_is_child_of_query` | 48 |
| `claim_is_parent_of_query` | 111 |
| `cross_disease` | 732 |
| `disease_sibling` | 5 |
| `exact_disease` | 51 |
| `generic_cancer_scope` | 204 |
| `missing_query_disease` | 148 |
| `unresolved_disease_relation` | 19 |
| `verified_disease_alias` | 162 |

Le relazioni senza occorrenze nel corpus non sono relazioni inutili:
sono casi che il contratto deve saper dire anche quando i dati non li
contengono. Sono coperte da probe espliciti in
`regression_case_simulation.jsonl`:

- `normalized_exact_disease`
- `missing_claim_disease`

## Perimetro

- gold usato: no
- metriche di retrieval calcolate: no
- gate implementato nel retriever operativo: no
- alias creati in questa fase: 0
- relazioni create in questa fase: 0
- claim simulati: 148
- query congelate: 10
- modalita': 3
- combinazioni prodotte: 4440

Readiness del gate shadow: si. 
Promozione del corpus: no. 
Migrazione del retriever operativo: no.


# RQ3 — Audit di licenza OncoKB

Fonti ufficiali consultate il **2026-08-06**:

| Fonte | URL |
|---|---|
| OncoKB™ Licensing FAQ | <https://faq.oncokb.org/licensing> |
| OncoKB™ API Documentation (corpus ufficiale) | <https://api.oncokb.org/llms-full.txt> |
| OncoKB™ Data Access | <https://www.oncokb.org/dataAccess> |
| OncoKB™ Terms of Use | <https://www.oncokb.org/terms> |
| Endpoint metadata (non autenticato) | <https://public.api.oncokb.org/api/v1/info> |

Le pagine `www.oncokb.org/terms` e `/dataAccess` sono servite da una single-page
application e non restituiscono testo a un client non-browser: il loro contenuto
**non** è stato letto direttamente. Le clausole riportate sotto provengono dalla
Licensing FAQ ufficiale e dalla documentazione API ufficiale.

## Clausole rilevanti

| Tema | Clausola ufficiale |
|---|---|
| Uso accademico | «OncoKB is accessible for no fee for research use in an academic setting.» |
| Quando serve una licenza | «A license is required to use OncoKB for commercial and/or clinical purposes, **and to access OncoKB data programmatically for academic purposes**.» |
| Accesso API accademico | «In order to access the OncoKB API, you will need to register your account using your institution/university email address.» |
| Uso commerciale | «commercial organizations will need to sign a license agreement with OncoKB which includes an annual license fee.» |
| Redistribuzione / bulk | «We do not support the download of all annotated variants in OncoKB.» |
| **Training di modelli AI/ML** | «**OncoKB cannot be used to train AI/ML models whether for academic or commercial purposes.**» |
| **Benchmarking di modelli AI/ML** | «**With explicit permission**, OncoKB may be used for benchmarking existing AI/ML models.» |

## Autenticazione

Dalla documentazione API ufficiale:

* il token va inviato come `Authorization: Bearer [token]`;
* «An API token identifies your OncoKB account and **determines which licensed
  data your requests can access**»;
* tre istanze con diversi requisiti:

| Istanza | Autenticazione | Copertura |
|---|---|---|
| `https://www.oncokb.org` | richiesta | dati OncoKB completi |
| `https://public.api.oncokb.org` | non richiesta | tutti i geni, **esclusi i dati terapeutici** |
| `https://demo.oncokb.org` | non richiesta | dati completi **solo per BRAF, TP53, ROS1** |

Le ultime due non sono utilizzabili come surrogato del database completo: la
prima esclude proprio la classe di dati che un fallback di citazioni
terapeutiche richiederebbe, la seconda copre tre geni.

## Stato dell'autorizzazione in questo progetto

| Voce | Stato |
|---|---|
| `ONCOKB_TOKEN` presente in `.env` | **sì** (`.env` è in `.gitignore`, non tracciato) |
| Token esposto in artefatti o log | **no** — nessun file di questa valutazione contiene il valore |
| Verifica di autenticazione | eseguita **una** chiamata a `GET /api/v1/info` sull'istanza di produzione: **HTTP 200**, `publicInstance: false` |
| Dati di conoscenza recuperati | **nessuno** — `/info` restituisce solo versioni e livelli di evidenza |
| Versione dati OncoKB | **v7.4**, 31/07/2026 · API `v1.6.0` |

Il token autentica quindi contro l'istanza di produzione con accesso ai dati
licenziati.

## Ciò che l'autenticazione **non** stabilisce

Un token valido dimostra che un account esiste ed è approvato. Non dimostra:

1. che l'account sia registrato con un indirizzo istituzionale, come la FAQ
   richiede per l'accesso programmatico accademico;
2. **che sia stato ottenuto il «explicit permission» che la FAQ richiede per
   usare OncoKB nel benchmarking di modelli AI/ML.**

Il punto 2 è dirimente. L'uso previsto da RQ3 — misurare il guadagno di copertura
che OncoKB offrirebbe a una pipeline di grounding documentale basata su LLM — è
una valutazione di un sistema AI, cioè esattamente la categoria per cui la
licenza richiede un permesso esplicito. Un token di accesso non è quel permesso.

## Determinazione

```
oncokb_official_docs_reviewed        = true
oncokb_license_compatible            = undetermined
oncokb_authorized_token_available    = true
oncokb_explicit_benchmarking_permission = not_documented
```

**Stato: `ONCOKB_FALLBACK_BLOCKED_NO_AUTHORIZATION`** per quanto riguarda la
licenza.

Questo stato è indipendente dal secondo esito, di natura tecnica, riportato in
`feasibility_report.md`: anche con un permesso documentato, il pilot non sarebbe
eseguibile su questo corpus.

## Raccomandazione

Prima di qualunque uso di OncoKB in questa tesi, scrivere a
`contact@oncokb.org` indicando: (a) che si tratta di ricerca accademica; (b) che
l'uso è la valutazione/benchmarking di una pipeline, **non** l'addestramento di
un modello; (c) quali dati verrebbero conservati e per quanto. Conservare la
risposta scritta come allegato della tesi.

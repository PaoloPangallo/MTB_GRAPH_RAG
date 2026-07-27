# Promotion diff e rollback della promozione prototipale 1.4

Derivato da: `qualified_claim_repository/1.4`  
Derivato da un diff precedente: false

Il diff e' ricavato di nuovo dalla 1.4. Le due fasi hanno perimetri
diversi — la 1.3 simulava una promozione, questa ne esegue una — e
riusare il diff precedente descriverebbe un'operazione che non e'
avvenuta.

## Diff

| Voce | Valore |
|---|---:|
| file creati | `18` |
| righe attive | `148` |
| righe deprecated | `4` |
| righe di lineage | `4` |
| link applicati | `37` |
| link attivi dopo | `17` |
| view materializzate | `2` |
| view verificate | `2` |
| claim ID cambiati | `0` |
| proposizioni aggiunte | `0` |
| proposizioni rimosse | `0` |
| file operativi cambiati | `0` |

Comportamento della query operativa cambiato: false.
Artefatti congelati invariati: **true**.

## Schema

| Voce | Valore |
|---|---|
| `claim_model_version` | `qualified_claim_model/1.2` |
| `corpus_schema_version` | `promoted_corpus_schema/1.0` |
| `deprecated_claims_declared_propagation_fields` | `CLM-a7c903cf8d423f015e29`, `CLM-aae818bbc8ec735a255d` |
| `deprecated_schema_version_after` | `qualified_claim_model/1.2` |
| `link_schema_version` | `promoted_qualification_link/1.0` |
| `propositions_affected_by_schema_change` | `0` |
| `view_schema_version` | `promoted_qualified_evidence_view/1.0` |

## Registro

| Voce | Valore |
|---|---|
| registro creato | **true** |
| puntatore prima | `None` |
| puntatore dopo | `qualified_claim_repository/1.4` |
| configurazione operativa cambiata | false |
| retriever operativo collegato dopo | false |
| percorso | `backend/pipeline/evidence/corpus/v3/prototype_corpus_registry.json` |

## Scrittura atomica

La sequenza registrata, passo per passo. Ogni passo ha un punto di
interruzione nominato, cosi' che i test possano fermarla dove serve
invece di simularlo.

| Passo | Esito |
|---|---|
| `snapshot` | `ok` |
| `generate` | `ok` |
| `validate` | `ok` |
| `manifest` | `ok` |
| `rename` | `ok` |
| `verify_post_write` | `ok` |

Punti di interruzione disponibili: `after_snapshot`, `after_generation`, `after_validation`, `after_manifest`, `before_rename`, `after_rename`, `before_registry`.

## Rollback

Provato su una copia, mai sul risultato finale: un rollback eseguito sul
corpus promosso lascerebbe la fase senza il proprio prodotto.

| Voce | Valore |
|---|---|
| eseguito su copia | **true** |
| eseguito sul corpus promosso | false |
| idempotente | **true** |
| prima esecuzione ha cambiato | **true** |
| seconda esecuzione ha cambiato | false |
| stato della voce dopo | `inactive` |
| puntatore prototipale dopo | `None` |
| corpus caricabile dopo | false |
| artefatti operativi invariati | **true** |
| retriever mai collegato | **true** |

File che il rollback non rimuove in nessuna modalita': `claim_replacement_lineage.jsonl`, `promotion_log.json`, `rollback_metadata.json`.

Idempotente qui significa la cosa stretta: non che si possa rieseguire
senza errori, ma che la seconda esecuzione produca uno stato identico
alla prima e non dichiari di aver cambiato nulla.

## Azioni applicate

Link: `37` azioni, tutte con `executed` vero nella namespace
promossa e `false` nel piano shadow. Source unit, locator e reason code
coincidono con il piano riga per riga.

View: `4` azioni, nessun membro appiattito in view separate,
nessun ranking cross-domain.

# TEST C — comportamento in caso di indisponibilità

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatto: `unavailable_probe.json`.

## 1. Il caso

`GCA-003ca9889b3d8906d4674f37`, provenance `pmid: 23724867`.

```
-> PubMed efetch          -> abstract OK (17 SourceUnit)
                          -> ArticleId pmc = PMC4081656
-> PMC OAI GetRecord      -> PMC_RESOLUTION_FAILED
-> nessun full text
-> si resta sull'abstract gia ottenuto
```

## 2. Cosa il sistema ha fatto

| Comportamento | Esito |
|---|---|
| `pmc_fetch_success` | **false** |
| `pmc_availability` | `PMC_RESOLUTION_FAILED` |
| `degraded_to_abstract` | **true** |
| `degradation_reason` | `PMC_RESOLUTION_FAILED` |
| Documento usato | `pmid:23724867` (l'abstract) |
| **Paper alternativo inventato** | **no** |
| **Ricerca semantica libera sul web** | **no** |
| Al modello è stato chiesto di compensare | **no** |

Il degrado non è una scelta della sonda: è una conseguenza della provenance. La
candidate dichiara quel PMID, PubMed dichiara quel PMCID, PMC lo nega. Il
sistema resta sull'unico documento che ha effettivamente ottenuto — lo stesso.

Nota: i tre PMCID che il pilot aveva registrato come `PMC_RESOLUTION_FAILED`
(`PMC273189`, `PMC4081656`, `PMC4191809`) sono tutti **derivati** dai PMID
`231047`, `23724867`, `27735949`. La baseline conteneva quindi già il caso
"PubMed dichiara un PMC, PMC lo nega, resta l'abstract". Non è uno scenario
costruito per il test.

## 3. Cache-first / API-on-miss (§9)

`resolve_document_probe()` — funzione isolata, **non integrata nel runtime**:

```
cache lookup
  hit  -> restituisci lo snapshot locale
  miss -> recupera dalla fonte ufficiale, valida, materializza snapshot
```

Tre rami misurati:

| Ramo | Documento | Esito |
|---|---|---|
| `CACHE_HIT` | `pmid:24658966` (in cache) | nessun fetch, snapshot locale, 7343 byte |
| `CACHE_MISS` su documento recuperabile | `pmid:24658966` con cache vuota | fetch eseguito, snapshot creato, parser OK, unità con testo |
| `CACHE_MISS` su documento non recuperabile | `pmcid:PMC273189` | fetch tentato, **fallito**, nessuno snapshot, 0 unità |

Il terzo ramo è quello che conta di più: il percorso cache-miss **non produce
comunque un risultato**. Quando la fonte nega, nega e basta. Non c'è alcun punto
in cui l'assenza di documento venga convertita in evidenza.

## 4. Cosa questo non autorizza

Il runtime canonico **non è stato modificato** e continua a comportarsi come
prima: su cache miss lo stage 6 produce `DOCUMENT_UNAVAILABLE` e non scarica
nulla. `resolve_document_probe()` vive in `scripts/`, non è importata da
`backend/`, e non cambia il comportamento di alcuna run.

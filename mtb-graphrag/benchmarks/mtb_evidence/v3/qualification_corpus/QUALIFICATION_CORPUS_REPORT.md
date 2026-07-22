# Qualification corpus — stato

- **Versione:** `qualification_corpus/1.0`
- **Freeze status:** `awaiting_second_review`
- **Fonti uniche:** 102 | **nello scope:** 102
- **Unita' di annotazione:** 102
- **Unita' con revisione umana:** 6
- **Unita' machine-extracted:** 96

## Che cosa questo corpus e' e che cosa non e'

E' l'infrastruttura completa di annotazione: inventario, scope congelato,
unita' di coorte, packet ciechi, contratto di gold, workflow a due revisori e
metriche. **Non** e' un corpus annotato: 96 unita' su 102 attendono la lettura
della fonte primaria da parte di una persona.

Nessuna unita' viene dichiarata `human_reviewed` da questo processo. Gli unici
stati umani presenti sono quelli degli otto profili annotati a mano prima di
questa fase, conservati invariati.

## Scope

La strategia e' un **censimento**: tutte le fonti citate dai 147 statement
entrano nel corpus. Con 102 fonti il censimento e' sostenibile, e rende
impossibile la selezione opportunistica per costruzione — non esiste un
criterio da cui una fonte scomoda possa essere esclusa.

Il clinical gold non partecipa alla selezione.

## Copertura delle dimensioni

| Dimensione | frozen KG | profilo revisionato | machine-extracted | ancora unknown |
| --- | ---: | ---: | ---: | ---: |
| `biomarker_requirements` | 0 | 6 | 0 | 96 |
| `comparator` | 0 | 0 | 0 | 102 |
| `disease` | 0 | 6 | 0 | 96 |
| `evidence_design` | 0 | 0 | 54 | 48 |
| `exclusion_criteria` | 0 | 4 | 0 | 98 |
| `inclusion_criteria` | 0 | 6 | 0 | 96 |
| `intervention` | 0 | 5 | 0 | 97 |
| `population` | 0 | 6 | 0 | 96 |
| `prior_therapies` | 0 | 6 | 0 | 96 |
| `regimen` | 0 | 6 | 0 | 96 |
| `resection_status` | 0 | 0 | 0 | 102 |
| `setting` | 0 | 6 | 0 | 96 |
| `stage` | 0 | 6 | 0 | 96 |
| `therapy_line` | 0 | 6 | 0 | 96 |

La colonna *frozen KG* e' zero ovunque e non e' un difetto della misura: lo
schema V2 non modella setting, stadio, linea, popolazione ne' criteri. E'
esattamente il vuoto che il corpus esiste per riempire.

`resection_status` resta a zero perche' nessuna fonte disponibile lo afferma.
Non viene inventato.

## Linking

- Coppie candidate: 161
- Record di gold: 161
- **Valutabili: 0**
- Provvisori: 161
- Precision: `not_evaluable` | Recall: `not_evaluable`

Precision e recall non sono calcolabili, e la ragione e' strutturale: il gold
richiede due annotazioni indipendenti e questa fase non le ha prodotte. Il
numero mancante e' l'unica risposta difendibile — un valore calcolato copiando
le prediction del linker darebbe 1.000 qualunque cosa il linker faccia.

## Fonti assenti dallo snapshot

2 profili revisionati non hanno alcuno statement corrispondente.

| Profilo | Fonte | Titolo |
| --- | --- | --- |
| `S-K1-3` | `PMID:36652354` | Futibatinib FOENIX-CCA2 |
| `S-C1-1` | `PMID:29151359` | FLAURA primary analysis |

Sono FLAURA e FOENIX-CCA2, le due fonti che l'audit del grafo aveva gia'
trovato assenti. Non vengono inserite artificialmente nel repository V3-A:
l'assenza e' un reperto, e correggerla nasconderebbe un limite reale dello
snapshot.

## Blocker al freeze

- seconda revisione mancante su 161 coppie su 161 richieste

Unita' che richiedono revisione umana: 96.


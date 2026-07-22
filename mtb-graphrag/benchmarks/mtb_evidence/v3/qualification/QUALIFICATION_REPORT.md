# Collegamento dei profili revisionati agli statement del pilota

- **Statement:** 147
- **Profili revisionati:** 8
- **Statement con almeno un profilo:** 9
- **Link creati:** 10

Il collegamento **non e' una promozione**: gli statement restano `frozen_kg` e
`pending_verification`, i profili restano `reviewed_source_profile`, e nessuno
dei due viene modificato.

## Link per esito

| Esito | Conteggio |
| --- | ---: |
| `exact_source_match` | 8 |
| `multi_source_match` | 0 |
| `ambiguous_match` | 0 |
| `conflicting_match` | 2 |

## Link per metodo

| Metodo | Conteggio |
| --- | ---: |
| `exact_pmid` | 10 |
| `exact_doi` | 0 |
| `exact_nct` | 0 |

Il matching e' **solo source-based**. Nessun confronto sul titolo entra in una
decisione automatica: un titolo simile non e' la stessa fonte.

## Precision e recall del linking

**not_evaluated** — non esiste un gold di collegamento
indipendente contro cui calcolarle. Inventare un denominatore produrrebbe un
numero senza referente. Il report riporta conteggi e copertura.

## Copertura dei qualificatori

| Dimensione | Prima (frozen KG) | Dopo (vista qualificata) | Ancora unknown |
| --- | ---: | ---: | ---: |
| `disease_setting` | 0 | 8 | 139 |
| `stage` | 0 | 8 | 139 |
| `therapy_line` | 0 | 8 | 139 |
| `resection_status` | 0 | 0 | 147 |
| `population` | 0 | 8 | 139 |
| `prior_therapies` | 0 | 8 | 139 |
| `biomarker_requirements` | 0 | 8 | 139 |
| `regimen` | 0 | 8 | 139 |
| `inclusion_criteria_summary` | 0 | 8 | 139 |
| `exclusion_criteria_summary` | 0 | 4 | 143 |

La colonna *prima* e' a zero su ogni dimensione perche' lo schema del grafo V2
non le modella: non e' un difetto dell'adapter ma il punto di partenza che i
profili revisionati esistono per colmare.

## Perche' un join per PMID non basta

Un profilo descrive **lo studio**; uno statement descrive **una proposizione**
estratta da quello studio. Uno studio contiene tipicamente piu' proposizioni, e
un'analisi di sottogruppo o un braccio diverso non ereditano la linea di terapia
del braccio principale.

Prima di rendere una dimensione disponibile, il link verifica la coerenza su
malattia e intervento. Se il profilo dichiara piu' interventi la coorte di
riferimento non e' determinabile, lo stato e' `ambiguous_match`, e **nessun
qualificatore ambiguo viene applicato**.

## Stato di qualificazione delle viste

| Stato | Conteggio |
| --- | ---: |
| `conflicting` | 2 |
| `partially_qualified` | 7 |
| `unqualified` | 138 |

## Profili non collegati

Nessuno statement del pilota cita queste fonti:

- `S-C1-1`
- `S-K1-3`

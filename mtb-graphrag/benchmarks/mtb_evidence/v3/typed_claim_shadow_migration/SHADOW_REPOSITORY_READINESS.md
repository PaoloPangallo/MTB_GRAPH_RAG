# Readiness del repository shadow

Stato migrazione: `shadow_not_promoted`

## Flag

| Flag | Valore | Motivo |
|---|---|---|
| `phase_scope_guard_fixed` | true | Helper condiviso su intervallo chiuso, quattro fasi instradate, regression test che riproduce il falso positivo |
| `parent_model_implemented` | true | 147 `GraphEvidenceRecord`, mai claim, usi vietati che sollevano |
| `typed_claim_model_implemented` | true | Tre tipi separati, aggregate e regimen non atomizzabili |
| `shadow_adapter_implemented` | true | Adapter nuovo; `v2_adapter.py` invariato |
| `adjudicated_groups_migrated` | true | 13 gruppi, 15 claim, 6 unsupported, 6 unresolved, ID coincidenti con quelli congelati |
| `legacy_statements_shadow_migrated` | true | 131 claim legacy su 134 record; 3 documentati come blocker |
| `claim_ids_stable` | true | Ricomputazione stabile, order-invariant, 0 collisioni su 305 ID |
| `structural_gate_engine_implemented` | true | Quattro bucket, gate prima dello scoring |
| `legacy_penalties_bypassed_by_gates` | true | 289 candidati non primari, punteggi fino a 999 999, 0 promozioni |
| `shadow_output_contract_implemented` | true | `intervention_representation` tipizzata, quattro divieti come controlli |
| `operational_artifacts_unchanged` | true | 11 gruppi di artefatti con hash identici prima e dopo |
| `migration_blockers_remaining` | 3 | `evidence:347`, `evidence:1846`, `evidence:1847`; nessuno blocca la promozione |
| `shadow_repository_ready` | **true** | Deterministico, completo, verificato dai test |
| `corpus_promotion_ready` | **false** | Vedi sotto |
| `operational_retriever_migration_ready` | **false** | Vedi sotto |
| `full_exploratory_rerun_ready` | **false** | Vedi sotto |

## Perche' `shadow_repository_ready` puo' essere true

Il repository e' generato in modo deterministico — due generazioni producono gli
stessi byte, invertire l'ordine degli ingressi non cambia nulla, nessun path
specifico della macchina compare negli artefatti — copre tutti e 147 i graph
evidence ID, riproduce esattamente i 15 `claim_id` congelati dall'adjudication e
non ha collisioni. I cinque casi obbligatori si comportano come l'adjudication
prescrive. Nessun artefatto operativo e' cambiato.

## Perche' `corpus_promotion_ready` resta false

Dipende da conteggi, blocker e test, e due delle tre condizioni non sono
soddisfatte.

**Il conteggio diverge dalla specification.** La specification proietta 149
claim; la derivazione ne produce 146. La differenza — i tre record prognostici e
diagnostici senza intervento — e' spiegata e verificata, ma resta una divergenza
fra un numero congelato e un numero derivato. Promuovere il corpus con i due
numeri in disaccordo renderebbe ambiguo ogni denominatore calcolato dopo. Serve
una decisione: correggere la proiezione a 146, oppure introdurre un tipo di claim
non terapeutico. E' una decisione di modello e questa fase non la prende.

**Una prosa della specification e' internamente incoerente.** La sezione 16 di
`migration_specification.json`, ripetuta in `ADAPTER_MIGRATION_SPECIFICATION.md`
riga 68, dice che i due gruppi senza claim sostitutivo sono `evidence:275` ed
`evidence:4759`. I dati strutturati dicono altro, e concordemente:
`packet_adjudications.jsonl` assegna a `evidence:275` un claim aggregato,
`MULTI_INTERVENTION_ADJUDICATION.md` riga 23 elenca `evidence:3811` ed
`evidence:4759` come i gruppi senza claim, e
`post_adjudication_schema_simulation.json` conferma con
`groups_without_any_claim`. La migrazione ha seguito i dati strutturati. La
prosa va corretta prima della promozione, perche' un lettore che si fidi di
quella frase concluderebbe che `evidence:275` non ha sostituto quando invece ne
ha uno.

**Terminology review aperta.** Quattro gruppi — `evidence:12156`,
`evidence:1851`, `evidence:1853`, `evidence:841` — hanno una revisione
terminologica pendente, e due mapping (`infigratinib`, `luminespib`) non sono
approvati. Promuovere ora fisserebbe nel corpus alias non verificati.

## Perche' `operational_retriever_migration_ready` resta false

Il retriever operativo non e' stato toccato, e non puo' esserlo prima che il
corpus sia promosso: interrogherebbe oggetti che non esistono. La sequenza e'
corpus, poi indice, poi retriever. Inoltre la disease hierarchy policy non e'
attiva (`hierarchy_policy_active: false`) e il gate la tratta oggi come
`unresolved_disease_relation`: attivarla cambierebbe l'insieme dei candidati
primari, e va fatto prima di misurare qualunque cosa sul retriever migrato.

## Perche' `full_exploratory_rerun_ready` resta false

Deve restare false, e lo e'. La valutazione esplorativa non e' stata eseguita,
nessuna metrica di retrieval e' stata calcolata, il gold non e' stato letto. Un
rerun ha senso solo dopo la promozione del corpus, perche' il denominatore
claim-level cambia: le metriche prodotte prima non sono confrontabili con quelle
dopo, e vanno etichettate con la versione del corpus.

## Blocker

| Blocker | Impatto |
|---|---|
| 3 record non terapeutici senza tipo di claim | Non bloccano la promozione; spiegano la divergenza 149 → 146 |
| Divergenza fra conteggio proiettato e derivato | Blocca `corpus_promotion_ready` |
| Incoerenza nella prosa della specification §16 | Blocca `corpus_promotion_ready`; correzione documentale |
| 4 gruppi con terminology review pendente | Blocca `corpus_promotion_ready` |
| Disease hierarchy policy non attiva | Blocca `operational_retriever_migration_ready` |

## Prossimo passo

Riconciliare il conteggio atteso con quello derivato e correggere la prosa della
sezione 16, entrambe modifiche agli artefatti dell'adjudication che questa fase
non ha il permesso di toccare. Poi chiudere la terminology review sui quattro
gruppi. Solo dopo ha senso decidere sulla disease hierarchy policy e, in
sequenza, promuovere il corpus.

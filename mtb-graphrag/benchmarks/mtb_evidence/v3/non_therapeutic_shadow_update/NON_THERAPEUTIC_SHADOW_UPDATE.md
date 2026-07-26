# Aggiornamento shadow ai domini non terapeutici

Model schema: `qualified_claim_model/1.1`
Repository: `qualified_claim_repository/1.1`
Stato: `shadow_not_promoted`
Sostituisce: `qualified_claim_repository/1.0`, che resta dov'è e invariato

## Cosa cambia

Il modello 1.0 aveva soltanto tipi di intervento, e tre record del corpus non
affermano una terapia. Non erano record vuoti: due erano claim diagnostici veri e
uno era un record la cui classificazione nel grafo è contraddetta dalla fonte.
Il 1.0 li lasciava tutti e tre come parent senza claim, il che era corretto ma
diceva la stessa cosa di tre situazioni diverse.

Il 1.1 introduce il **dominio** del claim — terapeutico, diagnostico,
prognostico — e i due tipi che mancavano. Per i tre tipi terapeutici il dominio è
derivato dal tipo invece che memorizzato: è ciò che permette al repository 1.0 di
restare byte per byte quello che era, perché nessun campo nuovo entra nella loro
serializzazione.

## Conteggi derivati

| Grandezza | Valore |
|---|---|
| Parent | 147 |
| **EvidenceClaim totali** | **148** |
| — terapeutici (invariati) | 146 |
| — diagnostici | 2 |
| — prognostici | 0 |
| Atomic / Aggregate / Regimen | 140 / 3 / 3 |
| Unsupported association | 6 |
| Unresolved association | 6 |
| Parent senza claim | 3 |
| Collisioni di ID | 0 |

Il totale non è imposto: è la somma delle parti, e i test lo verificano come
somma invece che come costante.

I parent che restano senza claim sono `evidence:347`, `evidence:3811` ed
`evidence:4759`. I primi due gruppi adjudicati non hanno claim positivo per
decisione documentale; il terzo è il caso trattato sotto.

## I due claim diagnostici

Fonte comune: `PMID:24122810`, source unit `PU-PMID-24122810-cohort-1`.

| | `evidence:1846` | `evidence:1847` |
|---|---|---|
| Claim ID | `CLM-2175b95ae3113c4f5d97` | `CLM-7056003a9bdef747f514` |
| Biomarcatore | FGFR2::BICC1 Fusion | FGFR2::AHCYL1 Fusion |
| Interpretazione | `subtype_defining_alteration` | `subtype_defining_alteration` |
| Disease scope | Cholangiocarcinoma | Cholangiocarcinoma |

Sono due claim distinti perché il partner di fusione è diverso, e questo è
l'unico campo che li separa: fonte, unità e locator sono gli stessi.

Quattro limitazioni viaggiano **con** il claim, non nel report di revisione. Se
restassero fuori, il claim uscirebbe più forte di quello che la fonte dice:

- `PREVALENCE_AGGREGATE_ONLY_NOT_PARTNER_SPECIFIC` — il 13,6% è riportato per le
  fusioni FGFR2 nel loro insieme; ripartirlo fra i due partner attribuirebbe a
  ciascuno un numero che la fonte dà solo congiuntamente;
- `CLINICAL_UTILITY_NOT_ASSERTED` — la fonte propone una classificazione
  molecolare, non un test validato;
- `ABSTRACT_ONLY_NO_FULL_TEXT`;
- `SOURCE_UNIT_AWAITING_HUMAN_REVIEW`.

`propagation_policy = prototype_only`, `hard_filterable = false`,
`final_evaluable = false`. Nessun intervento, in nessun campo.

## `evidence:347`

Nessun claim di alcun tipo: né diagnostico, né prognostico, né terapeutico, né
predittivo. Il parent conserva:

- `no_claim_reason`: `SOURCE_CONTRADICTS_GRAPH_PROGNOSTIC_DIRECTION`
- `unresolved_reason`: `FULL_TEXT_REQUIRED_FOR_PREDICTIVE_SCOPE`
- fonte `PMID:24662454`, audit status, provenance, lineage dello statement legacy

### L'incoerenza trovata all'inizio della fase

Il controllo preliminare ha confermato quello che il piano 1.0 lasciava aperto.
Lo statement legacy di `evidence:347` era:

| Proprietà | Stato nel 1.0 |
|---|---|
| attivo | **sì** — `direction: prognostic`, `polarity: supports`, nessun conflitto |
| preservato | sì — `preserved_as_legacy_migrated_claim` |
| deprecato | **no** |
| escluso dalla promozione | **no** |
| privo di una decisione | **sì** |

La motivazione registrata diceva «lo statement resta valido e leggibile» —
affermazione che l'audit della fase precedente aveva già contraddetto. In una
promozione futura sarebbe rientrato come claim prognostico recuperabile.

### La risoluzione

Lo stato diventa `promotion_blocked_pending_full_text`.

`deprecated_without_replacement` sarebbe stato vero ma incompleto: direbbe che
non c'è un sostituto, e farebbe sembrare chiusa una questione che è aperta. Il
nuovo stato dice le due cose insieme — non promuovere, e perché. Lo statement
operativo non è stato toccato e resta leggibile.

## Deprecazione

| Categoria | Conteggio |
|---|---|
| Statement da ritirare | **16** |
| — con sostituzione | 13 |
| — senza sostituzione | 3 |
| Statement promotion-blocked | 3 |
| Preservati come legacy migrati | 131 |

Il 16 non è assunto: viene dagli stati. Ai 13 adjudicati si aggiungono i 2
diagnostici (`replaced_by_diagnostic_claim`) e `evidence:347`, che richiede un
ritiro pur non avendo un sostituto. Dei 16, tre bloccano la promozione:
`evidence:347`, `evidence:3811`, `evidence:4759`.

## Piani, non esecuzioni

| Piano | Contenuto |
|---|---|
| Qualification link | 16 da ritirare, 17 da creare (15 terapeutici adjudicati + 2 diagnostici) |
| QualifiedEvidenceView | 16 righe, di cui 3 da ritirare invece che rigenerare |

I link diagnostici sono creati separatamente e non riciclano quelli terapeutici:
qualificano affermazioni diverse. Nessun qualificatore clinico è inventato. Per
`evidence:347` non è previsto alcun link positivo nuovo, solo il ritiro del
legacy con lineage di audit preservata. Tutti i piani hanno `executed: false`.

## Integrità

Invariati e verificati per hash: corpus operativo, adapter, repository,
retriever, scoring, QualifiedEvidenceView operative, adjudication, claim-type
contract, erratum, gold, output V2 congelati, **e il repository shadow 1.0**.

Il 1.0 è citato nel lineage con l'hash di ognuno dei suoi 19 artefatti, e un test
li ricalcola. Il campo `blocks_promotion` è opt-in nella serializzazione proprio
per questo: aggiungerlo alla mappa 1.0 ne avrebbe cambiato l'hash.

Nessun modulo operativo importa il package shadow. Gold mai letto. Nessun full
text recuperato. Nessun mapping terminologico risolto. Disease hierarchy policy
non applicata.

# Seconda revisione documentale dei gruppi multi-intervento

Revisione in cieco dei 13 packet, condotta sui soli packet e sulle fonti locali
che vi sono indicate. Nessun confronto con altre revisioni, nessuna adjudication,
nessuna raccomandazione architetturale: la fase si ferma alle annotazioni
documentali e alle decisioni per gruppo.

## Indipendenza

`reviewer_role = blinded_replicate`, `review_independence = blinded_non_independent_replicate`.

Nessun file vietato e' stato aperto, ma due elementi erano gia' nel contesto prima
che la revisione cominciasse: il prompt della task nomina la raccomandazione della
prima revisione, e il blocco `gitStatus` iniettato all'avvio conteneva gli oggetti
dei suoi commit. Nessuno dei due rivela decisioni per gruppo, ma la precondizione
di indipendenza non e' soddisfatta e non viene dichiarata tale.

## Conteggi

- packet revisionati: 13
- associazioni gruppo-intervento classificate: 28
- fonti distinte: 11 (full text 1, abstract-only 10, non disponibili 0)
- unita' documentali distinte: 18 (di cui condivise fra gruppi: 1)
- associazioni cliniche 21, precliniche 7

### Classificazione per intervento

- `comparator_only`: 1
- `directly_tested_in_combination_regimen`: 4
- `directly_tested_in_shared_aggregate_result`: 4
- `directly_tested_with_separate_result`: 9
- `drug_class_member_not_individually_tested`: 2
- `insufficient_source_access`: 3
- `mentioned_background_only`: 2
- `possible_alias_not_verified`: 3

### Decisione per gruppo

- `aggregate_parent_only`: 4
- `atomic_children_supported`: 2
- `combination_regimen_required`: 2
- `insufficient_for_atomicity_decision`: 1
- `mixed_parent_and_children`: 2
- `should_not_materialize_missing_interventions`: 2

## Risultati separati contro figli proposti

La fonte sostiene 9 risultati specifici per intervento, ma i child claim unici proposti sono 3.
La differenza non e' una perdita: e' la somma di tre cose distinte.

1. **6 di quei risultati appartengono gia' all'intervento dello statement parent.** Non generano un figlio: raffinano il locator di un claim che esiste. Un risultato separato non e' un claim nuovo se il claim c'e' gia'.
2. **3 associazioni sono bloccate da un mapping terminologico non verificato** (`BGJ398`, `AUY922`). In un caso il risultato documentale esiste, ma non e' attribuibile all'intervento del grafo finche' l'alias resta pending.
3. **Le unita' documentali condivise non moltiplicano i claim.** Un solo enunciato su NIH3T3 sostiene due righe di gruppo (FGFR2::BICC1 e FGFR2::AHCYL1): due associazioni, un risultato.

Restano quindi 3 figli proposti, tutti con locator sufficiente e tutti su categorie materializzabili.

## Locator

- associazioni totali: 28
- locator sufficienti: 19
- locator insufficienti per il claim: 9
- locator basati sul solo identificatore di fonte: 0
- figli proposti con locator sufficiente: 3/3

Ogni locator e' ancorato a una o piu' citazioni letterali verificate contro il testo del
packet: se una citazione smettesse di comparire nella fonte, la costruzione fallirebbe.

## Decisioni

| gruppo | decisione | interventi | risultati separati | figli |
| --- | --- | --- | --- | --- |
| `MI-B-1c375f91d580512a` | `combination_regimen_required` | 2 | 0 | 0 |
| `MI-B-3ded61139bc74e60` | `mixed_parent_and_children` | 2 | 1 | 0 |
| `MI-B-72b36cde2fff1311` | `mixed_parent_and_children` | 3 | 2 | 1 |
| `MI-B-8274e1f9586ef644` | `insufficient_for_atomicity_decision` | 3 | 0 | 0 |
| `MI-B-83c70396946a191d` | `aggregate_parent_only` | 2 | 0 | 0 |
| `MI-B-86f8143c879081d2` | `aggregate_parent_only` | 2 | 0 | 0 |
| `MI-B-92bfd4c87e04cbb2` | `should_not_materialize_missing_interventions` | 2 | 1 | 0 |
| `MI-B-95447460cf63aa6f` | `should_not_materialize_missing_interventions` | 2 | 1 | 0 |
| `MI-B-b4e82c2009b6a061` | `aggregate_parent_only` | 2 | 0 | 0 |
| `MI-B-c9174014bdf40550` | `aggregate_parent_only` | 2 | 0 | 0 |
| `MI-B-cd69de17ac73dc47` | `atomic_children_supported` | 2 | 2 | 1 |
| `MI-B-f17288721b33657d` | `combination_regimen_required` | 2 | 0 | 0 |
| `MI-B-f8fefcc976a5eaa9` | `atomic_children_supported` | 2 | 2 | 1 |

## Aperto

- **SR2-U-01** (`blocking_decision`) — Il disegno calcola un IC50 per ciascun inibitore ma l'abstract non riporta alcun valore ne' alcun esito specifico per EGFR L858R. Il locator raggiunge la frase che dichiara il test, non il risultato.
- **SR2-U-02** (`flagged_for_adjudication`) — L'intervento dello statement parent non compare come stringa nella fonte accessibile: la coorte e' descritta solo come trattata con 'EGFR-TKI'. Il problema di attribuzione riguarda quindi anche il claim gia' materializzato, non solo l'intervento aggiuntivo.
- **SR2-U-03** (`flagged_for_adjudication`) — L'unico esito di trattamento riportato riguarda il sottogruppo con mutazioni EGFR *non comuni*. L858R ed ex19del compaiono solo come conteggi di prevalenza, senza alcun esito associato: il biomarcatore del gruppo e quello dell'esito non coincidono.
- **SR2-U-04** (`flagged_for_adjudication`) — Gli esiti per farmaco sono riportati sulla popolazione combinata ex19del + L858R e non sono stratificati per mutazione. Il figlio proposto eredita la stessa granularita' di biomarcatore del parent e non ne introduce una nuova, ma la specificita' resta non verificata.
- **SR2-U-05** (`flagged_for_adjudication`) — Lo stato molecolare al momento della reintroduzione di crizotinib e' dedotto dalla cronologia del case report (C1156Y documentata prima, L1198F rilevata dopo) e non da una ri-biopsia in quel punto.
- **SR2-U-06** (`flagged_for_adjudication`) — La fonte usa solo il codice BGJ398. Il registro locale dei mapping non contiene alcuna voce approvata BGJ398 -> infigratinib e la fonte non dichiara l'equivalenza: il claim parent poggia su un alias non verificato.
- **SR2-U-07** (`flagged_for_adjudication`) — Stesso alias non verificato BGJ398 -> infigratinib del gruppo FGFR2::BICC1, sulla stessa unita' documentale.
- **SR2-U-08** (`flagged_for_adjudication`) — La fonte usa solo il codice AUY922. Esiste un risultato documentale attribuito a quella linea, ma l'identita' dell'intervento del grafo non e' verificata.
- **SR2-U-09** (`flagged_for_adjudication`) — Il carboplatino ha un doppio ruolo: componente del backbone chemioterapico nei bracci sperimentali e braccio di controllo. E' stato classificato comparator_only perche' nessuno dei due ruoli gli attribuisce un risultato di sensibilita' proprio.
- **SR2-U-10** (`flagged_for_adjudication`) — Entrambi gli esiti sono deboli e su un solo paziente ('preliminary anti-tumor activity', 'stable disease'). L'atomicita' e' documentalmente sostenuta ma la forza dell'evidenza e' minima.

## Cosa questa fase non ha fatto

Nessun confronto con altre revisioni, nessun consenso, nessuna adjudication, nessuna
migrazione dell'adapter, nessuna raccomandazione finale di schema. Nessuna decisione
diventa automaticamente definitiva: `propagation_policy = prototype_only`,
`hard_filterable = false`, `final_evaluable = false`.

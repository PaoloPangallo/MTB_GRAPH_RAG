# Contratto di retrieval per i claim tipizzati

L'adjudication ha deciso che il parent e' un contenitore di provenienza e che le
proposizioni terapeutiche sono claim tipizzati. Quel modello non sopravvive al retrieval
se il matching resta quello attuale, che confronta una stringa di intervento con un
insieme di stringhe e tratta ogni corrispondenza come equivalente.

## Il principio: due livelli, non uno

Prima l'idoneita' strutturale, poi il punteggio. Un candidato strutturalmente
incompatibile non puo' diventare compatibile con un punteggio alto.

Nel sistema attuale la stessa intenzione esiste come penalita': `penalty_not_separable`
vale -2, `penalty_pending_terminology` -3, `penalty_unresolved` -1, contro un
`native_biomarker` da 40 e un `native_disease` da 30. Sono preferenze, non vincoli: un
risultato di classe con biomarcatore e disease esatti supera qualunque penalita' e
diventa evidenza per un farmaco specifico. E' esattamente cio' che l'adjudication ha
vietato nei dati, e che il retrieval reintrodurrebbe.

Qui quelle tre penalita' diventano gate. Il tipo strutturale del match ha precedenza sui
pesi, e l'invariante e' esercitato a ogni riga della simulazione invece di essere
affermato nella documentazione.

## Oggetti interrogabili

| oggetto | candidato claim-level | bucket massimo |
| --- | --- | --- |
| `graph_evidence_record` | no | audit |
| `atomic_intervention_claim` | si | primario |
| `regimen_claim` | si | primario |
| `aggregate_intervention_claim` | si | primario |
| `unsupported_association` | no | audit |
| `unresolved_association` | no | warning |

Il parent puo' essere caricato per lineage, fonte, record grezzo, provenienza
dell'adapter e audit; non riceve mai un therapy score.

## Tipi di query

Cinque, non quattro. Ai quattro richiesti si aggiunge
`unspecified_multi_intervention_query`: due farmaci nella query senza un indicatore
strutturato di combinazione non fanno un regime. Dedurlo dalla cardinalita' produrrebbe
exact match su regimi che nessuno ha chiesto, quindi restano vincoli alternativi.

## Esito della simulazione

- valutazioni: 640
- risultati primari: 11
- parent in primario: 0
- unsupported in primario: 0
- unresolved in primario: 0

### Bucket

- `audit_only_results`: 233
- `primary_ranked_results`: 11
- `rejected_by_native_constraints`: 382
- `retained_with_warning`: 14

### Tipi di match osservati

- `aggregate_member_related`: 2
- `exact_atomic_intervention`: 11
- `exact_intervention_class`: 1
- `exact_regimen`: 2
- `incompatible`: 190
- `mapping_pending`: 2
- `no_intervention_constraint`: 15
- `parent_not_claim`: 208
- `regimen_component_related`: 5
- `regimen_subset_mismatch`: 1
- `regimen_superset_mismatch`: 1
- `unresolved`: 96
- `unresolved_class_relation`: 10
- `unsupported`: 96

## Direzione e polarita'

`reduced_sensitivity` non e' `resistance`: sono direzioni vicine e distinte, e
collassarle trasformerebbe una risposta attenuata in una resistenza completa. Una query
su una e un claim sull'altra danno `related_not_equivalent`, quindi warning e non
primario. `does_not_support` non diventa mai supporto positivo, `conflicting` resta
conflicting con warning, e `unknown` non e' assunto compatibile: contro una direzione
richiesta finisce in warning con codice esplicito, non nel primario.

## Disease

La policy gerarchica non e' attiva. Valgono come hard match solo `exact`,
`normalized_exact` e `verified_alias`. Le relazioni `explicit_parent`, `explicit_child`,
`explicit_sibling` e `unresolved_disease_relation` sono dichiarate perche' il contratto
resti compatibile con una futura policy ontology-aware, e sono marcate `active = false`.

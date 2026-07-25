# Readiness della seconda revisione

| criterio | stato |
| --- | --- |
| `all_packets_reviewed` | true |
| `all_interventions_classified` | true |
| `locator_requirements_satisfied` | true |
| `blindness_preserved` | true |
| `independent_review_valid` | false |
| `unresolved_groups_remaining` | 1 |
| `ready_for_inter_reviewer_comparison` | true |
| `ready_for_adjudication` | false |
| `ready_for_adapter_migration` | false |

## Perche' il confronto e' possibile e l'adjudication no

Le 13 decisioni esistono, ogni intervento e' classificato e ogni figlio proposto ha un
locator sufficiente: il materiale per un confronto fra revisori c'e'. Il confronto pero'
va etichettato per quello che e', perche' `independent_review_valid` e' falso: questa e'
una replica in cieco, non una seconda opinione indipendente. Un accordo elevato fra le
due revisioni non e' quindi evidenza di convergenza indipendente.

L'adjudication resta chiusa perche' presuppone il confronto, che non e' stato fatto. La
migrazione dell'adapter resta chiusa perche' presuppone l'adjudication.

Gruppi ancora aperti: 1 (`MI-B-8274e1f9586ef644`).

## Vincoli non violati

- nessun risultato aggregato e' stato reso specifico;
- nessun regime e' stato splittato nei componenti;
- nessuna menzione e nessuna terapia precedente e' diventata un claim;
- 3 mapping pending non sono stati promossi;
- clinico e preclinico restano separati in ogni annotazione;
- le 7 associazioni di resistenza conservano direzione e polarita'.

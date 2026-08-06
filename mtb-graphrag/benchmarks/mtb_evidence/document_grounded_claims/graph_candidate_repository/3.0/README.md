# graph_candidate_repository/3.0

Contratto `graph-candidate-assertion/3.0`. **Non è il default del runtime**: la versione si
sceglie con `GRAPH_CANDIDATE_REPOSITORY_VERSION=2.0|3.0`, e il default resta
`2.0`.

Il cambio rispetto a 2.0 è **major**: cambia il significato degli oggetti, non
solo la loro serializzazione.

| | 2.0 | 3.0 |
|---|---|---|
| Candidate | 46 864 | 46142 |
| Polarità della fonte | solo in `source_properties` | campo di primo livello |
| Alterazioni composte | prima variante | espressione completa + AST |
| Record multi-farmaco | una candidate per farmaco | una candidate per regime |

Una GraphCandidateAssertion significa **relazione candidata derivata dal
Knowledge Graph** — non claim degli autori, non evidenza documentale, non verità
clinica, non raccomandazione, non supporto verificato.

Vedi `docs/graph_candidate_v3/`.

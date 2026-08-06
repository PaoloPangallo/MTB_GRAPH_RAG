"""GraphCandidateAssertion v3 — contratto, parser e materializzatore.

Il pacchetto è **additivo**: non modifica il runtime, non tocca
``graph_candidate_repository/2.0`` e non cambia il comportamento di default
della pipeline. La versione di repository usata dal runtime è scelta
esplicitamente da ``gca_v3.repository`` e resta ``2.0`` finché v3 non supera
l'audit.
"""

CONTRACT_VERSION = "graph-candidate-assertion/3.0"
REPOSITORY_VERSION = "graph_candidate_repository/3.0"

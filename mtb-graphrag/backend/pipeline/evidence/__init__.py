"""Layer EvidenceStatement della V3.

Contiene l'adapter dai record del grafo V2 al modello di evidenza V3 e le misure che
ne verificano la fedelta'. Non tocca il grafo: legge record gia' recuperati e produce
oggetti conformi a `schemas/evidence_statement.schema.json`.
"""

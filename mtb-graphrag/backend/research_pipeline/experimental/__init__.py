"""Componenti sperimentali, fuori dal percorso canonico di esecuzione.

Nulla in ``backend/research_pipeline`` importa questo package: l'orchestratore,
``paper_selection`` e ``DocumentRuntime`` restano quelli di prima. Un test
strutturale lo verifica, perché "sperimentale" deve essere una proprietà
osservabile e non una dichiarazione d'intenti nel docstring.
"""

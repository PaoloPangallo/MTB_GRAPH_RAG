"""Research-only ontology shadow MVP; deliberately disconnected from V3 runtime."""

from .models import OntologyConcept, OntologyMatch
from .registry import OntologyRegistry
from .normalizer import EntityNormalizer
from .evaluator import OntologyShadowEvaluator

__all__ = [
    "EntityNormalizer",
    "OntologyConcept",
    "OntologyMatch",
    "OntologyRegistry",
    "OntologyShadowEvaluator",
]

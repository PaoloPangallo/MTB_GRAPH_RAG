"""Pairwise shadow evaluator. It returns evidence, never pipeline decisions."""

from __future__ import annotations

import re
from typing import Any

from .models import OntologyMatch
from .normalizer import EntityNormalizer, NormalizedEntity
from .registry import OntologyRegistry


class OntologyShadowEvaluator:
    def __init__(self, registry: OntologyRegistry, normalizer: EntityNormalizer) -> None:
        self.registry = registry
        self.normalizer = normalizer

    def compare(self, query_value: str | None, claim_value: str | None, entity_type: str) -> OntologyMatch:
        query = self.normalizer.normalize(query_value, entity_type)
        claim = self.normalizer.normalize(claim_value, entity_type)
        base = dict(
            query_value=query_value or "",
            claim_value=claim_value or "",
            query_concept_id=self._concept_id(query.registry_key),
            claim_concept_id=self._concept_id(claim.registry_key),
            query_registry_key=query.registry_key,
            claim_registry_key=claim.registry_key,
        )
        if not query.normalized or not claim.normalized:
            return OntologyMatch(**base, match_type="UNKNOWN", distance=None, path=[], compatible_candidate=False, explanation="Uno o entrambi i valori sono assenti.", confidence="low")
        if query.normalized == claim.normalized:
            if entity_type == "disease" and not query.registry_key and not claim.registry_key:
                return OntologyMatch(**base, match_type="UNKNOWN", distance=None, path=[], compatible_candidate=False, explanation="Termine disease uguale ma non coperto da un concetto locale verificato.", confidence="low")
            exact = self.normalizer.text(query_value or "") == self.normalizer.text(claim_value or "")
            return OntologyMatch(
                **base,
                match_type="EXACT" if exact else "SYNONYM",
                distance=0,
                path=[query.normalized],
                compatible_candidate=True,
                explanation="Valori identici dopo normalizzazione deterministica." if exact else "Forme diverse convergono allo stesso valore normalizzato.",
                confidence="high",
            )
        if entity_type == "disease":
            return self._disease_match(query, claim, base)
        if entity_type in {"variant", "gene"}:
            return self._molecular_match(query, claim, base)
        if entity_type == "intervention":
            return self._intervention_match(query, claim, base)
        return OntologyMatch(**base, match_type="UNKNOWN", distance=None, path=[], compatible_candidate=False, explanation="Nessuna relazione locale verificata per questo dominio.", confidence="low")

    def evaluate_claim(self, claim: dict[str, Any], query_context: dict[str, Any]) -> list[OntologyMatch]:
        """Evaluate only; input claim is not mutated and no status is returned."""
        rows: list[OntologyMatch] = []
        fields = (("disease", query_context.get("disease_context"), claim.get("disease_scope")), ("variant", query_context.get("biomarker_context"), claim.get("biomarker")), ("intervention", (query_context.get("original_intervention_associations") or [None])[0], claim.get("intervention") or claim.get("canonical_intervention")))
        for entity_type, query_value, claim_value in fields:
            rows.append(self.compare(query_value, claim_value, entity_type))
        return rows

    def _concept_id(self, key: str | None) -> str | None:
        concept = self.registry.concept(key)
        return concept.canonical_id if concept else None

    def _disease_match(self, query: NormalizedEntity, claim: NormalizedEntity, base: dict[str, Any]) -> OntologyMatch:
        if not query.registry_key or not claim.registry_key:
            return OntologyMatch(**base, match_type="UNKNOWN", distance=None, path=[], compatible_candidate=False, explanation="Almeno un termine disease non Ã¨ coperto dagli alias/concetti locali.", confidence="low")
        down = self.registry.descendant_path(query.registry_key, claim.registry_key)
        if down:
            return OntologyMatch(**base, match_type="DESCENDANT", distance=len(down) - 1, path=down, compatible_candidate=True, explanation="La claim Ã¨ un descendant della disease query in una gerarchia locale esplicita; non Ã¨ equivalenza clinica.", confidence="high")
        up = self.registry.descendant_path(claim.registry_key, query.registry_key)
        if up:
            return OntologyMatch(**base, match_type="ANCESTOR", distance=len(up) - 1, path=list(reversed(up)), compatible_candidate=False, explanation="La claim Ã¨ piÃ¹ generale: la query Ã¨ un descendant della claim.", confidence="high")
        return OntologyMatch(**base, match_type="INCOMPATIBLE", distance=None, path=[], compatible_candidate=False, explanation="Due concetti disease locali non hanno relazione gerarchica verificata.", confidence="high")

    def _molecular_match(self, query: NormalizedEntity, claim: NormalizedEntity, base: dict[str, Any]) -> OntologyMatch:
        if query.gene and claim.gene and query.gene != claim.gene:
            return OntologyMatch(**base, match_type="INCOMPATIBLE", distance=None, path=[], compatible_candidate=False, explanation="Gene differente; nessun alias o relazione locale consente il match.", confidence="high")
        if query.generic_fusion and claim.partner_specific or claim.generic_fusion and query.partner_specific:
            return OntologyMatch(**base, match_type="RELATED", distance=1, path=[query.normalized, claim.normalized], compatible_candidate=False, explanation="Fusion gene-level e fusion partner-specific sono correlate come forma, ma non equivalenti e prive di relazione ontologica locale verificata.", confidence="low")
        if query.gene and claim.gene and query.alteration and claim.alteration and query.alteration != claim.alteration:
            return OntologyMatch(**base, match_type="INCOMPATIBLE", distance=None, path=[], compatible_candidate=False, explanation="Stesso gene ma alterazioni diverse; il normalizzatore non le collassa.", confidence="high")
        return OntologyMatch(**base, match_type="UNKNOWN", distance=None, path=[], compatible_candidate=False, explanation="Nessun concetto molecolare o relazione locale verificata per il confronto.", confidence="low")

    def _intervention_match(self, query: NormalizedEntity, claim: NormalizedEntity, base: dict[str, Any]) -> OntologyMatch:
        if query.registry_key and claim.registry_key:
            class_path = self.registry.descendant_path(query.registry_key, claim.registry_key)
            if class_path and any(self.registry.concept(class_path[i + 1]).relation_kinds.get(k) == "class_of" for i, k in enumerate(class_path[:-1])):
                return OntologyMatch(**base, match_type="CLASS_MATCH", distance=len(class_path) - 1, path=class_path, compatible_candidate=False, explanation="La relazione locale identifica un membro di classe, ma non autorizza un claim member-specifico.", confidence="medium")
        if query.normalized == claim.normalized:
            return OntologyMatch(**base, match_type="EXACT", distance=0, path=[query.normalized], compatible_candidate=True, explanation="Intervento uguale dopo normalizzazione locale.", confidence="high")
        if self._looks_like_formulation_pair(query.normalized, claim.normalized):
            return OntologyMatch(**base, match_type="RELATED", distance=1, path=[query.normalized, claim.normalized], compatible_candidate=False, explanation="Principio attivo e sale/formulazione sono distinti; non esiste mapping locale verificato per questa coppia.", confidence="low")
        return OntologyMatch(**base, match_type="UNKNOWN", distance=None, path=[], compatible_candidate=False, explanation="Nessun mapping di intervento locale verificato per la coppia.", confidence="low")

    @staticmethod
    def _looks_like_formulation_pair(left: str, right: str) -> bool:
        suffixes = (" hydrochloride", " phosphate", " mesylate", " sodium", " calcium")
        return any(left == right.removesuffix(s) or right == left.removesuffix(s) for s in suffixes)

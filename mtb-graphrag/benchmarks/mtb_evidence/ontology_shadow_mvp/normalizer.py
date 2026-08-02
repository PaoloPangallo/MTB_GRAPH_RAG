"""Deterministic, provenance-aware normalization; no fuzzy or LLM matching."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ENTITY_TYPES
from .registry import OntologyRegistry


@dataclass(frozen=True)
class NormalizedEntity:
    raw: str
    normalized: str
    entity_type: str
    registry_key: str | None
    gene: str | None = None
    alteration: str | None = None
    generic_fusion: bool = False
    partner_specific: bool = False
    components: tuple[str, ...] = ()


class EntityNormalizer:
    def __init__(self, registry: OntologyRegistry) -> None:
        self.registry = registry

    @staticmethod
    def text(value: str) -> str:
        value = value.casefold().strip()
        value = value.replace("‐", "-").replace("‑", "-").replace("–", "-")
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"\s*::\s*", "::", value)
        return value

    def normalize(self, value: str | None, entity_type: str) -> NormalizedEntity:
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"unsupported entity_type: {entity_type}")
        raw = value or ""
        text = self.text(raw)
        if not text:
            return NormalizedEntity(raw, "", entity_type, None)
        if entity_type == "disease":
            concept = self.registry.resolve("disease", text)
            return NormalizedEntity(raw, text, entity_type, concept.registry_key if concept else None)
        if entity_type == "intervention":
            concept = self.registry.resolve("intervention", text)
            normalized = concept.label if concept else text
            return NormalizedEntity(raw, self.text(normalized), entity_type, concept.registry_key if concept else None)
        if entity_type in {"gene", "variant", "diagnostic"}:
            return self._normalize_molecular(raw, text, entity_type)
        return NormalizedEntity(raw, text, entity_type, None)

    def _normalize_molecular(self, raw: str, text: str, entity_type: str) -> NormalizedEntity:
        parts = [p.strip() for p in re.split(r"\s+and\s+", text) if p.strip()]
        normalized_parts: list[str] = []
        for part in parts:
            part = re.sub(r"\bv::", "", part)
            part = re.sub(r"\bp\.(?=[a-z]\d)", "", part)
            part = re.sub(r"\s+", " ", part).strip()
            normalized_parts.append(part)
        if len(normalized_parts) > 1:
            normalized_parts.sort()
        normalized = " and ".join(normalized_parts)
        gene = None
        alteration = None
        generic_fusion = False
        partner_specific = False
        if "::" in normalized:
            gene, partner = normalized.split("::", 1)
            gene = gene.strip()
            partner_specific = True
            alteration = f"{gene}::{partner}"
        else:
            tokens = normalized.split()
            if tokens:
                gene = tokens[0]
                alteration = " ".join(tokens[1:]) or None
            generic_fusion = normalized.endswith(" fusion") and "::" not in normalized
        concept = self.registry.resolve(entity_type, text)
        return NormalizedEntity(
            raw,
            normalized,
            entity_type,
            concept.registry_key if concept else None,
            gene=gene,
            alteration=alteration,
            generic_fusion=generic_fusion,
            partner_specific=partner_specific,
            components=tuple(normalized_parts),
        )

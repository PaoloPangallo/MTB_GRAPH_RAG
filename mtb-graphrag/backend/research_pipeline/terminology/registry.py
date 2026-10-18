from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
import re
from typing import Mapping, Sequence

from .models import DOMAINS, Domain, Resolution, SourceRef, Term
from .surface import lookup_key, molecular_surface, surface

SCHEMA_VERSION = "terminology-registry/1.0"
IDENTITY_SCOPES = frozenset({"PREFERRED", "EXACT"})


class Registry:
    def __init__(self, terms: Sequence[Term], version: str,
                 mappings: Sequence[dict] = (), entities: Mapping[str, dict] | None = None):
        self.version = version
        self.terms = tuple(sorted(set(terms), key=lambda t: (t.domain, t.concept_id, t.label, t.alias_scope,
                                                            t.gene_id or "", t.reference or "", t.source.locator)))
        self.mappings = tuple(dict(x) for x in mappings)
        self.entities = dict(entities or {})
        self._retired_ids = frozenset(surface(m["subject"]) for m in self.mappings if m.get("predicate") == "OBSOLETE")
        self._lookup: dict[tuple[str, str], list[Term]] = defaultdict(list)
        self._ids: dict[tuple[str, str], list[Term]] = defaultdict(list)
        for term in self.terms:
            if term.domain not in DOMAINS or not term.concept_id or not term.label:
                raise ValueError("Invalid terminology term")
            self._lookup[(term.domain, lookup_key(term.domain, term.label))].append(term)
            self._ids[(term.domain, surface(term.concept_id))].append(term)

    @lru_cache(maxsize=32768)
    def resolve(self, domain: Domain, value: str, *, gene_id: str | None = None,
                reference: str | None = None) -> Resolution:
        if domain not in DOMAINS:
            raise ValueError(f"Unsupported entity domain: {domain}")
        if not isinstance(value, str) or not value.strip():
            return Resolution(domain, str(value or ""), "INVALID", "NONE", (), (), ("EMPTY_INPUT",), self.version)
        if surface(value) in self._retired_ids:
            return Resolution(domain, value, "UNMAPPED", "NONE", (), (), ("OBSOLETE_CONCEPT_NOT_REMAPPED",), self.version)
        direct = self._ids.get((domain, surface(value)), [])
        terms = direct or self._lookup.get((domain, lookup_key(domain, value)), [])
        info = molecular_surface(value) if domain == "VARIANT" else {}
        effective_ref = reference or info.get("reference")
        if domain == "VARIANT" and not effective_ref and re.match(r"^[cgnmr]\.", surface(value)):
            return Resolution(domain, value, "UNMAPPED", "NONE", (), (), ("REFERENCE_REQUIRED",), self.version)
        terms = [t for t in terms if t.alias_scope in IDENTITY_SCOPES
                 and (gene_id is None or t.gene_id == gene_id)
                 and (effective_ref is None or t.reference == effective_ref)]
        ids = tuple(sorted({t.concept_id for t in terms}))
        status = "RESOLVED" if len(ids) == 1 else "AMBIGUOUS" if ids else "UNMAPPED"
        reasons = []
        if status == "AMBIGUOUS":
            reasons.append("LABEL_COLLISION")
        if domain == "VARIANT" and info.get("kind") == "PROTEIN_SUBSTITUTION":
            if effective_ref is None:
                reasons.append("REFERENCE_UNSPECIFIED")
            if info.get("predicted"):
                reasons.append("PREDICTED_PROTEIN_CONSEQUENCE")
        method = "EXACT_ID" if direct and ids else "EXACT_LABEL" if any(t.alias_scope == "PREFERRED" and surface(t.label) == surface(value) for t in terms) else "VERIFIED_ALIAS" if ids else "NONE"
        return Resolution(domain, value, status, method, ids, tuple(terms), tuple(reasons), self.version)

    def compare(self, domain: Domain, expected: str, observed: str, *,
                gene_id: str | None = None, reference: str | None = None) -> dict:
        left = self.resolve(domain, expected, gene_id=gene_id, reference=reference)
        right = self.resolve(domain, observed, gene_id=gene_id, reference=reference)
        relation = "UNKNOWN"
        if left.status == right.status == "RESOLVED":
            relation = "IDENTICAL" if left.concept_ids == right.concept_ids and surface(expected) == surface(observed) else "VERIFIED_ALIAS" if left.concept_ids == right.concept_ids else "DIFFERENT"
            if domain == "VARIANT" and left.concept_ids == right.concept_ids and molecular_surface(expected)["predicted"] != molecular_surface(observed)["predicted"]:
                relation = "PREDICTION_SCOPE_MISMATCH"
        elif left.status == "AMBIGUOUS" or right.status == "AMBIGUOUS":
            relation = "AMBIGUOUS"
        elif surface(expected) and surface(expected) == surface(observed):
            # Literal identity remains possible outside terminology coverage;
            # this does not assert a canonical concept or semantic equivalence.
            relation = "LITERAL_IDENTITY"
        return {"relation": relation, "expected": left.to_dict(), "observed": right.to_dict(),
                "registry_version": self.version}

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return {"schema_version": SCHEMA_VERSION, "registry_version": self.version,
                "terms": [asdict(t) for t in self.terms], "mappings": list(self.mappings),
                "entities": self.entities}

    @classmethod
    def from_dict(cls, payload: dict) -> Registry:
        if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported terminology registry schema")
        terms = [Term(**{**item, "source": SourceRef(**item["source"])}) for item in payload["terms"]]
        return cls(terms, payload["registry_version"], payload.get("mappings", []), payload.get("entities", {}))

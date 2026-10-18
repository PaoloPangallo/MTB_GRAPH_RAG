"""Source-linked molecular concepts and three-valued profile logic."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from .models import Resolution
from .registry import Registry
from .surface import molecular_surface, surface
from .fusion_syntax import MARKERS, explicit_partners, has_marker


@dataclass(frozen=True)
class LiteralSpan:
    quote: str
    start_offset: int | None = None
    end_offset: int | None = None


@dataclass(frozen=True)
class MolecularObservation:
    """Literal molecular assertion; fusion identity is separate from gene identity."""

    raw_gene: str
    raw_alteration: str
    alteration_type: str
    assertion_status: str
    source_spans: tuple[LiteralSpan, ...]
    fusion_partners: tuple[str, ...]
    fusion: Resolution | None
    concept_ids: tuple[str, ...]
    qualifier_status: str = "UNSPECIFIED"
    source_variant_category: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def fusion_partners(value: str) -> tuple[str, ...]:
    """Parse explicit ordered :: partners only; a hyphen is not assumed to be a fusion."""
    match = re.fullmatch(r"\s*([A-Za-z0-9-]+)\s*::\s*([A-Za-z0-9-]+)(?:\s+Fusion)?\s*", value, flags=re.IGNORECASE)
    return tuple(x.upper() for x in match.groups()) if match else ()


@lru_cache(maxsize=8192)
def resolve_fusion(partners: tuple[str, ...], registry: Registry) -> Resolution:
    """Accept only an atomic, exact source profile with one explicit component.

    No variant named 'Fusion', isolated partner gene, or compound profile can
    establish this link. The ordered partners remain part of the identity.
    """
    raw = "::".join(partners) + " Fusion"
    profile = registry.resolve("PROFILE", raw)
    ids = ()
    if len(partners) == 2 and profile.status == "RESOLVED":
        source = registry.entities.get(profile.concept_ids[0], {})
        components = source.get("variant_ids", [])
        if fusion_partners(str(source.get("name") or "")) == partners and len(components) == 1:
            ids = tuple(components)
    return Resolution("VARIANT", raw, "RESOLVED" if ids else "UNMAPPED",
                      "SOURCE_PROFILE_FUSION" if ids else "NONE", ids,
                      profile.terms if ids else (),
                      ("ORDERED_PARTNERS_FROM_SOURCE_PROFILE",) if ids else ("FUSION_SOURCE_LINK_UNRESOLVED",),
                      registry.version)


@lru_cache(maxsize=8192)
def source_variant_category(concept_id: str, registry: Registry) -> str | None:
    """Read a source label's literal category or supported substitution syntax.

    This is a qualifier consistency check, not a clinical consequence inference.
    Unknown or competing source categories cannot validate an explicit qualifier.
    """
    source = registry.entities.get(concept_id, {})
    names = [source["name"]] if source.get("name") else [
        term.label for term in registry._ids.get(("VARIANT", concept_id.casefold()), [])
        if term.alias_scope == "PREFERRED"]
    literal_categories = {
        "amplification": "AMPLIFICATION", "expression": "EXPRESSION",
        "fusion": "FUSION", "deletion": "DELETION", "insertion": "INSERTION",
        "duplication": "DUPLICATION", "mutation": "MUTATION",
    }
    categories = set()
    for name in names:
        if molecular_surface(name)["kind"] == "PROTEIN_SUBSTITUTION":
            categories.add("MUTATION")
        elif surface(name) in literal_categories:
            categories.add(literal_categories[surface(name)])
    return next(iter(categories)) if len(categories) == 1 else None


def molecular_observation(item: dict, registry: Registry) -> MolecularObservation:
    gene, alteration = str(item.get("gene") or ""), str(item.get("alteration") or "")
    alteration_type = str(item.get("alteration_type") or "UNKNOWN").upper()
    explicit = alteration.strip().casefold() in MARKERS or alteration_type == 'FUSION' or has_marker(alteration) or bool(fusion_partners(alteration))
    def partners_for(value: str, *, gene_field: bool = False) -> tuple[str, ...]:
        strict = fusion_partners(value)
        if strict:
            return strict
        if not explicit or (gene_field and registry.resolve('GENE', value).status == 'RESOLVED'):
            return ()
        parts = explicit_partners(value, allow_hyphen=True)
        return parts if parts and all(registry.resolve('GENE', part).status == 'RESOLVED' for part in parts) else ()
    gene_partners, alteration_partners = partners_for(gene, gene_field=True), partners_for(alteration)
    partners = gene_partners or alteration_partners
    # A composite gene spelling needs an explicit fusion alteration/type.
    consistent = alteration_type in {"FUSION", "UNKNOWN", "GENERIC"} and (
        not alteration.strip() or alteration.strip().casefold() in MARKERS or bool(alteration_partners))
    if alteration_partners and gene:
        consistent = consistent and (gene_partners == alteration_partners or gene.upper() in alteration_partners)
    fusion = resolve_fusion(partners, registry) if partners and explicit and consistent else None
    variant = resolve_variant(registry.resolve("GENE", gene), alteration, registry)
    category = source_variant_category(variant.concept_ids[0], registry) if variant.status == "RESOLVED" else None
    qualifier_status = "UNSPECIFIED" if alteration_type in {"UNKNOWN", "GENERIC"} else (
        "UNKNOWN" if category is None else "COMPATIBLE" if alteration_type == category else "CONFLICT")
    # Preserve the original variant resolution for audit, but do not let a
    # conflicting/unsupported qualified observation prove an ENTITY or NOT.
    eligible_ids = variant.concept_ids if qualifier_status in {"UNSPECIFIED", "COMPATIBLE"} else ()
    spans = tuple(LiteralSpan(str(x["quote"]), x.get("start_offset"), x.get("end_offset"))
                  for x in item.get("source_spans") or [] if isinstance(x, dict) and x.get("quote"))
    return MolecularObservation(gene, alteration, str(item.get("alteration_type") or "UNKNOWN"),
                                str(item.get("assertion_status") or "UNKNOWN"), spans,
                                partners, fusion, eligible_ids, qualifier_status, category)


def resolve_variant(gene: Resolution, alteration: str, registry: Registry, *, reference=None) -> Resolution:
    if gene.status != "RESOLVED":
        return Resolution("VARIANT", alteration, "AMBIGUOUS" if gene.status == "AMBIGUOUS" else "UNMAPPED",
                          "NONE", (), (), ("GENE_UNRESOLVED",), registry.version)
    return registry.resolve("VARIANT", alteration, gene_id=gene.concept_ids[0], reference=reference)


def parse_profile(expression: str, registry: Registry) -> dict:
    tokens = [x.strip() for x in re.split(r"\b(AND|OR|NOT)\b|([()])", expression) if x and x.strip()]
    position = 0
    linked = set()

    def atom():
        nonlocal position
        if position >= len(tokens):
            raise ValueError("Missing operand")
        token = tokens[position]
        position += 1
        if token == "NOT":
            return {"op": "NOT", "arg": atom()}
        if token == "(":
            value = disjunction()
            if position >= len(tokens) or tokens[position] != ")":
                raise ValueError("Unbalanced parentheses")
            position += 1
            return value
        if token in {"AND", "OR", ")"}:
            raise ValueError("Unexpected operator")
        partners = fusion_partners(token)
        if partners:
            fusion = resolve_fusion(partners, registry)
            if fusion.status != "RESOLVED":
                raise ValueError("Unresolved fusion component")
            cid = fusion.concept_ids[0]
            linked.add(cid)
            return {"op": "FUSION", "concept_id": cid, "partners": list(partners)}
        # A component requires an explicitly linked gene and alteration.
        candidates = []
        for boundary in re.finditer(r"\s+", token):
            gene = registry.resolve("GENE", token[:boundary.start()])
            variant = resolve_variant(gene, token[boundary.end():], registry)
            if variant.status == "RESOLVED":
                candidates.append(variant.concept_ids[0])
        if len(set(candidates)) != 1:
            raise ValueError("Unresolved profile component")
        cid = candidates[0]
        linked.add(cid)
        return {"op": "ENTITY", "concept_id": cid}

    def conjunction():
        nonlocal position
        value = atom()
        while position < len(tokens) and tokens[position] == "AND":
            position += 1
            value = {"op": "AND", "args": [value, atom()]}
        return value

    def disjunction():
        nonlocal position
        value = conjunction()
        while position < len(tokens) and tokens[position] == "OR":
            position += 1
            value = {"op": "OR", "args": [value, conjunction()]}
        return value

    try:
        ast = disjunction()
        if position != len(tokens):
            raise ValueError("Unsupported grammar")
        return {"status": "RESOLVED", "ast": ast, "component_ids": sorted(linked),
                "registry_version": registry.version, "unresolved_tokens": []}
    except (ValueError, RecursionError):
        return {"status": "UNMAPPED", "ast": None, "component_ids": [],
                "registry_version": registry.version, "unresolved_tokens": [expression]}


def evaluate_profile(ast: dict, observations: list[dict]) -> str:
    if not isinstance(ast, dict):
        return "UNKNOWN"
    op = ast.get("op")
    if op in {"ENTITY", "FUSION"}:
        if op == "FUSION":
            observations = [{**x["fusion"], "assertion_status": x.get("assertion_status", "UNKNOWN")}
                            for x in observations if x.get("fusion")
                            and x["fusion"].get("status") == "RESOLVED"
                            and tuple(x.get("fusion_partners", ())) == tuple(ast.get("partners", ()))]
        states = {str(x.get("assertion_status", "UNKNOWN")).upper() for x in observations
                  if ast.get("concept_id") in x.get("concept_ids", [])}
        positive = bool(states & {"PRESENT", "ASSERTED", "CURRENT", "TARGET"})
        negative = bool(states & {"ABSENT", "NEGATED"})
        return "TRUE" if positive and not negative else "FALSE" if negative and not positive else "UNKNOWN"
    if op == "NOT":
        return {"TRUE": "FALSE", "FALSE": "TRUE", "UNKNOWN": "UNKNOWN"}[evaluate_profile(ast.get("arg"), observations)]
    values = [evaluate_profile(x, observations) for x in ast.get("args", [])]
    if not values:
        return "UNKNOWN"
    if op == "AND":
        return "FALSE" if "FALSE" in values else "TRUE" if all(x == "TRUE" for x in values) else "UNKNOWN"
    if op == "OR":
        return "TRUE" if "TRUE" in values else "FALSE" if all(x == "FALSE" for x in values) else "UNKNOWN"
    return "UNKNOWN"

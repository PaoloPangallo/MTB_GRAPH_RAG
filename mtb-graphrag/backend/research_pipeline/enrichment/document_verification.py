"""Fail-closed document verification for EVIDENCE_DRUG observations.

The structural result only licenses an independent semantic comparison. It is
never itself documentary support. This module does not interpret effect words.
"""

from __future__ import annotations

import re
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from .canonical_normalizer import entity_relation, normalize_surface
from ..text_integrity import CANONICAL_TEXT_DIGEST_VERSION, canonical_text_sha256
from ..terminology.surface import protein_keys
from ..terminology.approved_identity_aliases import VERSION as IDENTITY_ALIAS_VERSION
from .semantic_contract import (POLICY_VERSION, admission_blockers,
                                partial_admission_blockers, assessment_payload,
                                validate_assessment)

VERSION = "evidence-drug-document-verification/2.5"
STRUCTURAL = frozenset({"PASS", "MISMATCH", "UNRESOLVED"})
RELATION_ALIGNMENT = frozenset({"SAME", "OPPOSITE", "NO_SUPPORT", "INSUFFICIENT", "AMBIGUOUS"})
ASSERTION_SCOPES = frozenset({
    "DIRECT_ASSERTION", "REPORTED_PRIOR_WORK", "HYPOTHETICAL", "REJECTED_ASSERTION",
    "UNCERTAIN_ASSERTION", "QUESTIONED_ASSERTION", "UNKNOWN",
})


def _labels(rows: Any, kind: str | None = None) -> list[str]:
    return [str(row["label"]) for row in rows or [] if isinstance(row, dict)
            and row.get("label") and (kind is None or str(row.get("type") or "").casefold() == kind)]


def _token_sequence(value: Any, text: Any) -> list[int]:
    needle = normalize_surface(value).split()
    haystack = normalize_surface(text).split()
    if not needle:
        return []
    return [i for i in range(len(haystack) - len(needle) + 1)
            if haystack[i:i + len(needle)] == needle]


def _is_distinct_drug(value: str, target_drug: str) -> bool:
    """Require a recognized, distinct drug before treating a connector as a regimen."""
    from backend.research_pipeline.terminology.matching import registry

    if not value or entity_relation(target_drug, value, domain="INTERVENTION") in {
        "IDENTICAL", "CANONICAL_ALIAS",
    }:
        return False
    if normalize_surface(value) in {
        "anthracycline", "anthracycline based chemotherapy", "chemotherapy",
        "platinum based chemotherapy", "radiotherapy", "radiation therapy",
        "immunotherapy", "endocrine therapy",
    }:
        return True
    try:
        return registry().resolve("INTERVENTION", value).status == "RESOLVED"
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _has_distinct_drug_coordination(quote: str, drug: str) -> bool:
    """Catch drug combinations while ignoring grammatical 'treated with X'."""
    connectors = r"(?:\+|/|&|\band\b|\bplus\b|\bwith\b)"
    match = re.search(rf"(?<!\w){re.escape(str(drug))}(?!\w)", quote, re.IGNORECASE)
    if not match:
        return False
    class_names = (r"(?:anthracycline(?:-based| based)?\s+chemotherapy|"
                   r"platinum(?:-based| based)?\s+chemotherapy|chemotherapy|"
                   r"radiotherapy|radiation therapy|immunotherapy|endocrine therapy)")
    if re.search(rf"(?<!\w){re.escape(str(drug))}(?!\w)\s*{connectors}\s*{class_names}",
                 quote, re.IGNORECASE):
        return True
    left = quote[:match.start()]
    right = quote[match.end():]
    before = re.search(rf"([\w-]+)\s*{connectors}\s*$", left, re.IGNORECASE)
    after = re.match(rf"\s*{connectors}\s*([\w-]+)", right, re.IGNORECASE)
    return bool((before and _is_distinct_drug(before.group(1), drug))
                or (after and _is_distinct_drug(after.group(1), drug)))


def _matches_explicit_drug_alternative(target_drug: str, observed: str) -> bool:
    """Match one target inside a literal two-drug disjunction, not a regimen."""
    options = [part.strip(" \t.,;:()[]{}") for part in re.split(
        r"\s+or\s+", str(observed or ""), flags=re.IGNORECASE
    )]
    if len(options) != 2 or not all(options):
        return False
    target_matches = [
        index for index, option in enumerate(options)
        if entity_relation(target_drug, option, domain="INTERVENTION")
        in {"IDENTICAL", "CANONICAL_ALIAS"}
    ]
    if len(target_matches) != 1:
        return False
    other = options[1 - target_matches[0]]
    if entity_relation(target_drug, other, domain="INTERVENTION") in {
        "IDENTICAL", "CANONICAL_ALIAS",
    }:
        return False
    try:
        from backend.research_pipeline.terminology.matching import registry
        return registry().resolve("INTERVENTION", other).status == "RESOLVED"
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _study_context(text: str) -> str:
    """Conservative context tags from literal source cues, not a clinical judgment."""
    lowered = text.casefold()
    cell = bool(re.search(r"\b(cell lines?|in vitro|cultured cells?|cellular model|cancer cells?)\b", lowered))
    animal = bool(re.search(r"\b(mice|mouse model|murine|xenograft|in vivo)\b", lowered))
    trial = bool(re.search(r"\b(randomi[sz]ed|phase [i1i]+|clinical trial)\b", lowered))
    patients = bool(re.search(r"\b(patients?|participants?|cohort)\b", lowered))
    preclinical = cell or animal
    clinical = trial or patients
    if preclinical and clinical:
        return "MIXED_CONTEXT"
    if cell:
        return "PRECLINICAL_CELL"
    if animal:
        return "PRECLINICAL_ANIMAL"
    if trial:
        return "CLINICAL_TRIAL"
    if patients:
        return "CLINICAL_PATIENT_DATA"
    return "UNSPECIFIED"


@lru_cache(maxsize=1)
def _lineage_index() -> dict[str, dict[str, Any]]:
    """Optional source-typed index. Missing/corrupt data can only cause abstention."""
    root = Path(__file__).resolve().parents[1] / "resources"
    path = root / "evidence_drug_target_index_v1.jsonl"
    manifest_path = root / "evidence_drug_target_index_v1.manifest.json"
    try:
        payload = path.read_bytes()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (not isinstance(manifest, dict)
                or manifest.get("digest_contract") != CANONICAL_TEXT_DIGEST_VERSION):
            return {}
        if canonical_text_sha256(payload) != manifest["index_sha256"]:
            return {}
        rows = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line]
        if any(not isinstance(row, dict)
               or not isinstance(row.get("candidate_id"), str)
               or not row["candidate_id"] for row in rows):
            return {}
        if len(rows) != manifest["records"] or len({row["candidate_id"] for row in rows}) != len(rows):
            return {}
        return {row["candidate_id"]: row for row in rows}
    except (OSError, ValueError, KeyError, UnicodeError):
        return {}


def minimal_target(candidate: dict[str, Any]) -> dict[str, Any]:
    """Copy only explicit candidate/GCA fields; never verbalize a claim."""
    props = candidate.get("source_properties") or {}
    edge = props.get("edge") or {}
    evidence = props.get("evidence") or {}
    profile = props.get("profile") or {}
    biomarkers = candidate.get("biomarkers") or []
    profile_ids = [item for item in candidate.get("graph_path") or []
                   if isinstance(item, str) and item.startswith("MolecularProfile:")]
    evidence_id = evidence.get("evidence_id") or edge.get("source_evidence_id")
    recovered = _lineage_index().get(candidate.get("candidate_id"))
    if recovered and (recovered["evidence_id"] != f"Evidence:{evidence_id}"
                      or recovered["source_record_ids"] != candidate.get("source_record_ids")
                      or recovered.get("profile_id") != (profile_ids[0] if len(profile_ids) == 1 else None)):
        recovered = None
    recovered = recovered or {}
    recovered_profiles = recovered.get("profiles") or []
    target = {
        "candidate_id": candidate.get("candidate_id"),
        "evidence_id": f"Evidence:{evidence_id}" if evidence_id else None,
        "profile_id": profile_ids[0] if len(profile_ids) == 1 else None,
        "profile": profile.get("name") or (
            recovered_profiles[0].get("name") if len(recovered_profiles) == 1 else None),
        "components": profile.get("components") or recovered.get("components"),
        "gene_ids": profile.get("gene_ids") or recovered.get("gene_ids"),
        "variant_ids": profile.get("variant_ids") or recovered.get("variant_ids"),
        "profile_operator": recovered.get("profile_operator"),
        "genes": _labels(biomarkers, "gene"),
        "variants": _labels(biomarkers, "variant") + _labels(biomarkers, "alteration"),
        "candidate_drug": (candidate.get("object") or {}).get("label") if
            (candidate.get("object") or {}).get("type") == "Drug" else
            next(iter(_labels(candidate.get("interventions"))), None),
        "linked_drugs": props.get("linked_drugs") or recovered.get("linked_drugs"),
        "significance": edge.get("significance") or evidence.get("significance"),
        "evidence_direction": evidence.get("evidence_direction") or candidate.get("direction"),
        "relation_family": candidate.get("relation_family"),
        "predicate": candidate.get("predicate"),
        "disease": (candidate.get("context") or {}).get("disease") or
            next(iter(_labels(candidate.get("disease"))), None),
        "evidence_statement": evidence.get("evidence_statement"),
        "document_identifiers": candidate.get("document_identifiers") or [],
    }
    _resolve_atomic_profile(target)
    from .phenotype_identity import source_phenotype
    phenotype = source_phenotype(candidate)
    if phenotype:
        target['phenotype'] = phenotype
    return target


def _resolve_atomic_profile(target: dict[str, Any]) -> None:
    """Recover one gene/variant from explicit source profile links only."""
    if (target['genes'] or len(target['variants']) != 1 or not target['profile']
            or not target['profile_id'] or target['components']
            or target['profile_operator'] not in (None, 'UNSPECIFIED')):
        return
    from ..terminology.matching import registry
    from ..terminology.molecular import parse_profile
    from ..terminology.surface import surface
    reg = registry()
    resolved = reg.resolve('PROFILE', target['profile'])
    parsed = parse_profile(target['profile'], reg)
    if (resolved.status != 'RESOLVED' or len(resolved.concept_ids) != 1
            or parsed['status'] != 'RESOLVED' or parsed['ast'].get('op') != 'ENTITY'):
        return
    profile_id = resolved.concept_ids[0]
    # GCA and terminology namespaces refer to the same frozen profile record.
    if target['profile_id'] not in {profile_id, profile_id.replace('CIViCProfile:', 'MolecularProfile:')}:
        return
    variants = reg.entities.get(profile_id, {}).get('variant_ids') or []
    if len(variants) != 1 or variants != parsed['component_ids']:
        return
    variant = reg.entities.get(variants[0], {})
    genes = variant.get('gene_ids') or []
    name = variant.get('name')
    if len(genes) != 1 or not name:
        return
    if ((target['gene_ids'] and target['gene_ids'] != genes)
            or (target['variant_ids'] and target['variant_ids'] != variants)):
        return
    if surface(target['variants'][0]) not in {surface(target['profile']), surface(name)}:
        return
    gene = reg.resolve('GENE', genes[0])
    labels = {term.label for term in gene.terms if term.alias_scope == 'PREFERRED'}
    if gene.status != 'RESOLVED' or len(labels) != 1:
        return
    target['molecular_identity_resolution'] = {'source_profile_id': profile_id,
        'source_variant_ids': list(variants), 'source_gene_ids': list(genes),
        'original_genes': list(target['genes']), 'original_variants': list(target['variants']),
        'registry_version': reg.version}
    target.update(genes=sorted(labels), variants=[name], gene_ids=list(genes), variant_ids=list(variants))


def _document_authorized(target: dict[str, Any], document_id: str) -> bool:
    try:
        kind, value = document_id.split(":", 1)
    except ValueError:
        return False
    return any(str(row.get(kind) or "").casefold() == value.casefold()
               for row in target["document_identifiers"] if isinstance(row, dict))


def structural_verify(candidate: dict[str, Any], paper: dict[str, Any],
                      source_unit: dict[str, Any] | None, enrichment: dict[str, Any] | None,
                      case_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate provenance and exact identity; uncertain ownership abstains."""
    target = minimal_target(candidate)
    reasons: list[str] = []
    document_id = str(paper.get("document_id") or "")
    unit_id = (enrichment or {}).get("source_unit_id")
    quote = (enrichment or {}).get("quote")
    unit_text = (source_unit or {}).get("text")
    base = {"version": VERSION, "identity_alias_version": IDENTITY_ALIAS_VERSION,
            "target_snapshot": target,
            "GEP_snapshot": {"candidate_id": target["candidate_id"],
                             "document_id": document_id, "source_unit_id": unit_id,
                             "quote": quote, "quote_offset": None,
                             "proposition": quote, "required_context": unit_text,
                             "grounded_arguments": {}, "literal_relation_evidence": quote}}

    def result(status: str, *codes: str) -> dict[str, Any]:
        return {**base, "structural_status": status,
                "structural_reason_codes": [*reasons, *codes]}

    if target["relation_family"] != "EVIDENCE_DRUG":
        return result("UNRESOLVED", "NOT_EVIDENCE_DRUG")
    if not document_id or not _document_authorized(target, document_id):
        return result("MISMATCH", "DOCUMENT_NOT_AUTHORIZED")
    allowed_units = paper.get("resolved_source_unit_ids") or paper.get("source_unit_ids") or []
    if not source_unit or not unit_id or unit_id not in allowed_units or source_unit.get("source_unit_id") != unit_id:
        return result("MISMATCH", "SOURCE_UNIT_NOT_AUTHORIZED")
    if source_unit.get("document_id") != document_id:
        return result("MISMATCH", "SOURCE_UNIT_DOCUMENT_MISMATCH")
    if not isinstance(quote, str) or not quote or not isinstance(unit_text, str):
        return result("UNRESOLVED", "QUOTE_OR_TEXT_MISSING")
    starts = [match.start() for match in re.finditer(re.escape(quote), unit_text)]
    if not starts:
        return result("MISMATCH", "QUOTE_NOT_LITERAL")
    if len(starts) != 1:
        return result("UNRESOLVED", "QUOTE_OFFSET_AMBIGUOUS")
    base["GEP_snapshot"]["quote_offset"] = starts[0]
    relation = (enrichment or {}).get("observed_relation") or {}
    if not isinstance(relation, dict):
        return result("UNRESOLVED", "GROUNDED_ARGUMENTS_MISSING")
    observed_subjects = relation.get("subjects") or []
    if not isinstance(observed_subjects, list) or not observed_subjects:
        return result("UNRESOLVED", "GROUNDED_ARGUMENTS_MISSING")
    grounded: dict[str, Any] = {"subjects": [], "intervention": relation.get("intervention"),
                                "disease": relation.get("disease")}
    for subject in observed_subjects:
        if not isinstance(subject, dict):
            return result("UNRESOLVED", "GROUNDED_ARGUMENTS_INVALID")
        surface = subject.get("surface_value") or subject.get("value")
        if not _token_sequence(surface, quote):
            return result("MISMATCH", "SUBJECT_NOT_LITERAL")
        grounded["subjects"].append({"type": subject.get("type"), "surface_value": surface,
                                      "linked_gene": subject.get("linked_gene")})
    intervention = relation.get("intervention")
    if not intervention or not _token_sequence(intervention, quote):
        return result("MISMATCH", "INTERVENTION_NOT_LITERAL")
    base["GEP_snapshot"]["grounded_arguments"] = grounded

    drug = target["candidate_drug"]
    if not drug:
        return result("UNRESOLVED", "TARGET_DRUG_UNSPECIFIED")
    drug_match = entity_relation(drug, intervention, domain="INTERVENTION")
    explicit_alternative = False
    if drug_match not in {"IDENTICAL", "CANONICAL_ALIAS"}:
        explicit_alternative = _matches_explicit_drug_alternative(drug, str(intervention))
        if not explicit_alternative:
            if drug_match in {"UNKNOWN", "AMBIGUOUS", "PREDICTION_SCOPE_MISMATCH", "REFERENCE_SCOPE_MISMATCH"}:
                return result("UNRESOLVED", "DRUG_IDENTITY_UNRESOLVED")
            return result("MISMATCH", "DRUG_IDENTITY_MISMATCH")
    grounded["candidate_intervention"] = drug
    grounded["intervention_match"] = (
        "EXPLICIT_ALTERNATIVE" if explicit_alternative else drug_match
    )
    # Explicit coordination adjacent to the target drug makes an isolated
    # single-agent target unsafe. This recognizes grammar, not any drug name.
    if _has_distinct_drug_coordination(quote, str(drug)):
        return result("UNRESOLVED", "POSSIBLE_MULTI_AGENT_INTERVENTION")
    if relation.get("intervention_composition") == "COMBINATION":
        return result("UNRESOLVED", "MULTI_AGENT_INTERVENTION")
    if relation.get("molecular_composition") in {"COMBINATION", "COEXPRESSION", "CONDITIONAL", "ALTERNATIVES"} or relation.get("relation_scope") in {"COMBINATION", "COEXPRESSION", "CONDITIONAL", "ALTERNATIVES", "UNKNOWN"}:
        return result("UNRESOLVED", "RELATION_SCOPE_NOT_ATOMIC")
    linked = target["linked_drugs"]
    if isinstance(linked, list) and len(linked) > 1:
        return result("UNRESOLVED", "MULTI_DRUG_EVIDENCE_REGIMEN_UNKNOWN")
    if not target["significance"] and not target["predicate"]:
        return result("UNRESOLVED", "TARGET_RELATION_UNSPECIFIED")

    genes, variants = target["genes"], target["variants"]
    if not genes:
        genes = sorted({str(x["gene"]) for x in candidate.get("biomarkers") or [] if x.get("gene")})
    from backend.research_pipeline.terminology.matching import registry as current_registry
    gene_resolution = current_registry().resolve("GENE", genes[0]) if len(genes) == 1 else None
    gene_id = gene_resolution.concept_ids[0] if gene_resolution and gene_resolution.status == "RESOLVED" else None
    if not genes and not variants:
        components = target["components"] or []
        profile_name = target["profile"]
        if (not profile_name or len(components) != 1
                or not _token_sequence(profile_name, quote)):
            return result("UNRESOLVED", "TARGET_MOLECULAR_CONDITION_UNSPECIFIED")
        normalized_profile = normalize_surface(profile_name)
        if any(not _token_sequence(item["surface_value"], normalized_profile)
               for item in grounded["subjects"]):
            return result("UNRESOLVED", "OBSERVED_SUBJECT_OUTSIDE_PROFILE")
        variant_name = components[0].get("name")
        if variant_name:
            observed_variant_tokens = set(re.findall(r"\b[A-Za-z]\d+[A-Za-z]\b", quote))
            profile_variant_tokens = set(re.findall(r"\b[A-Za-z]\d+[A-Za-z]\b", variant_name))
            if profile_variant_tokens and observed_variant_tokens - profile_variant_tokens:
                return result("UNRESOLVED", "ADDITIONAL_VARIANT_IN_PROPOSITION")
        if target["profile_operator"] not in (None, "UNSPECIFIED"):
            return result("UNRESOLVED", "PROFILE_OPERATOR_UNEXPECTED")
    observed_genes = [str(item["surface_value"]) for item in grounded["subjects"]
                      if str(item["type"] or "").upper() == "GENE"]
    observed_variants = [str(item["surface_value"]) for item in grounded["subjects"]
                         if str(item["type"] or "").upper() == "ALTERATION"]
    if genes and (len(genes) != 1 or len(observed_genes) != 1):
        return result("UNRESOLVED", "GENE_SCOPE_NOT_ATOMIC")
    if variants and (len(variants) != 1 or len(observed_variants) != 1):
        return result("UNRESOLVED", "VARIANT_SCOPE_NOT_ATOMIC")
    for domain, expected, observed in (("GENE", genes, observed_genes), ("VARIANT", variants, observed_variants)):
        if not expected:
            continue
        identity = entity_relation(expected[0], observed[0], domain=domain, gene_id=gene_id)
        if identity in {"UNKNOWN", "AMBIGUOUS", "PREDICTION_SCOPE_MISMATCH", "REFERENCE_SCOPE_MISMATCH"}:
            return result("UNRESOLVED", f"{domain}_IDENTITY_UNRESOLVED")
        if identity not in {"IDENTICAL", "CANONICAL_ALIAS"}:
            return result("MISMATCH", f"{domain}_IDENTITY_MISMATCH")
    if genes and variants:
        gene_positions = _token_sequence(observed_genes[0], quote)
        variant_positions = _token_sequence(observed_variants[0], quote)
        if not gene_positions or not variant_positions:
            return result("MISMATCH", "GENE_VARIANT_NOT_LITERAL")
        gene_length = len(normalize_surface(observed_genes[0]).split())
        variant_length = len(normalize_surface(observed_variants[0]).split())
        adjacent = any(g + gene_length == v or v + variant_length == g
                       for g in gene_positions for v in variant_positions)
        gene_variant_labels = (re.escape(str(observed_variants[0])),
                               re.escape(str(observed_genes[0])))
        mutation_of = re.search(
            rf"\b{gene_variant_labels[0]}\b\s+(?:mutation|variant|mutant)\s+(?:of|in)\s+"
            rf"\b{gene_variant_labels[1]}\b", quote, re.IGNORECASE)
        gene_mutation = re.search(
            rf"\b{gene_variant_labels[1]}\b\s+{gene_variant_labels[0]}\s+"
            rf"(?:mutation|variant|mutant)\b", quote, re.IGNORECASE)
        if not adjacent and not (mutation_of or gene_mutation):
            return result("UNRESOLVED", "GENE_VARIANT_PAIR_NOT_ADJACENT")
        linked_genes = [item.get("linked_gene") for item in grounded["subjects"]
                        if str(item["type"] or "").upper() == "ALTERATION"]
        for value in linked_genes:
            if not value:
                continue
            identity = entity_relation(value, genes[0], domain="GENE")
            if identity in {"UNKNOWN", "AMBIGUOUS"}:
                return result("UNRESOLVED", "GENE_VARIANT_PAIR_UNRESOLVED")
            if identity not in {"IDENTICAL", "CANONICAL_ALIAS"}:
                return result("MISMATCH", "GENE_VARIANT_PAIR_MISMATCH")
    # A simple variant must not be promoted from a compound variant surface.
    if variants:
        variant_tokens = protein_keys(quote)
        expected_tokens = protein_keys(observed_variants[0])
        if expected_tokens and variant_tokens - expected_tokens:
            return result("UNRESOLVED", "ADDITIONAL_VARIANT_IN_PROPOSITION")
    disease = relation.get("disease")
    if target["disease"] and not disease:
        return result("UNRESOLVED", "DISEASE_CONTEXT_NOT_GROUNDED")
    if disease and not _token_sequence(disease, quote):
        return result("MISMATCH", "DISEASE_NOT_LITERAL")
    if target["disease"] and disease and entity_relation(target["disease"], disease, domain="DISEASE") not in {"IDENTICAL", "CANONICAL_ALIAS"}:
        from ..terminology.case_resolution import compare_disease_context
        comparison = compare_disease_context(str(target["disease"]), str(disease), current_registry())
        base["disease_resolution"] = comparison
        if comparison["relation"] == "SAME_CONCEPT_CONTEXT_UNRESOLVED":
            if comparison["observed"].get("approved_alias_source"):
                # The curated alias establishes identity; literal qualifiers
                # remain for semantic review. This licenses review only.
                reasons.append("DISEASE_CONTEXT_REQUIRES_SEMANTIC_REVIEW")
            else:
                return result("UNRESOLVED", "DISEASE_CONTEXT_SCOPE_UNRESOLVED")
        else:
            if comparison["relation"] in {"UNKNOWN", "AMBIGUOUS"}:
                return result("UNRESOLVED", "DISEASE_IDENTITY_UNRESOLVED")
            return result("MISMATCH", "DISEASE_IDENTITY_MISMATCH")
    base["study_context"] = _study_context(quote)
    case_has_clinical_context = bool(
        isinstance(case_context, dict)
        and (case_context.get("disease") or case_context.get("biomarkers")
             or case_context.get("diseases"))
    )
    base["applicability_to_case"] = (
        "LIMITED_PRECLINICAL" if (base["study_context"].startswith("PRECLINICAL_")
                                  and case_has_clinical_context)
        else "NOT_ASSESSED")
    return result("PASS", "EXACT_GROUNDING_AND_IDENTITY")


def admit(structural: dict[str, Any], semantic: dict[str, Any] | None) -> dict[str, Any]:
    """The sole deterministic promotion rule. Unknowns always abstain."""
    status = structural.get("structural_status")
    semantic_missing = semantic is None
    assessment = assessment_payload(semantic)
    semantic = semantic if isinstance(semantic, dict) else {}
    relation_alignment = semantic.get("relation_alignment")
    assertion_scope = semantic.get("assertion_scope")
    if status in {"MISMATCH", "UNRESOLVED"}:
        # A downstream semantic call is not licensed until structural identity
        # and provenance pass. Report the actual blocking gate, not a fabricated
        # schema error for an assessment that was never requested.
        blockers = list(structural.get("structural_reason_codes") or [f"STRUCTURAL_{status}"])
    elif semantic_missing:
        blockers = ["SEMANTIC_ASSESSMENT_MISSING"]
    else:
        blockers = admission_blockers(assessment, structural.get("GEP_snapshot") or {})
    try:
        validate_assessment(assessment, structural.get("GEP_snapshot") or {})
        semantic_valid = not semantic_missing
    except (AttributeError, ValueError):
        semantic_valid = False
    technical = bool(isinstance(semantic, dict) and (
        str(semantic.get("reason") or "").startswith(("SEMANTIC_PROVIDER_FAILURE", "SEMANTIC_TRANSPORT",
                                                          "SEMANTIC_OUTPUT_INVALID", "SEMANTIC_PROVIDER_UNAVAILABLE"))
        or semantic.get("infrastructure_failure")
    ))
    if status in {"MISMATCH", "UNRESOLVED"}:
        final = "NOT_RUN_STRUCTURAL"
    elif technical:
        final = "TECHNICAL_ERROR"
    elif status == "PASS" and relation_alignment == "OPPOSITE" and not blockers:
        final = "REJECTED"
    elif status == "PASS" and relation_alignment == "NO_SUPPORT" and not blockers:
        final = "NO_SUPPORT"
    elif status == "PASS" and relation_alignment == "INSUFFICIENT" and semantic_valid:
        final = "INSUFFICIENT_INFORMATION"
    elif status == "PASS" and relation_alignment == "SAME" and not blockers:
        final = "DOCUMENT_SUPPORTED"
    elif (status == "PASS" and relation_alignment == "SAME"
          and not partial_admission_blockers(assessment, structural.get("GEP_snapshot") or {})):
        final = "PARTIALLY_SUPPORTED"
    else:
        final = "UNVERIFIABLE"
    if final == "DOCUMENT_SUPPORTED":
        support_result = "FULL_SUPPORT"
    elif final == "PARTIALLY_SUPPORTED":
        support_result = "PARTIAL_SUPPORT"
    elif final == "REJECTED" and relation_alignment == "OPPOSITE":
        support_result = "CONTRADICTORY"
    elif final == "NO_SUPPORT":
        support_result = "NO_SUPPORT"
    elif final == "INSUFFICIENT_INFORMATION":
        support_result = "INSUFFICIENT_INFORMATION"
    elif final in {"NOT_RUN_STRUCTURAL", "TECHNICAL_ERROR"}:
        support_result = "UNVERIFIABLE"
    elif final == "REJECTED":
        support_result = "NO_SUPPORT"
    else:
        support_result = "UNVERIFIABLE"
    if final == "NOT_RUN_STRUCTURAL":
        verification_status = ("STRUCTURAL_INCOMPATIBILITY" if status == "MISMATCH"
                               else "STRUCTURAL_AMBIGUITY")
    elif final == "TECHNICAL_ERROR":
        verification_status = "TECHNICAL_ERROR"
    elif semantic_missing:
        verification_status = "SEMANTIC_ASSESSMENT_NOT_RUN"
    else:
        verification_status = "ASSESSED"
    limitation = None
    if final == "PARTIALLY_SUPPORTED":
        spans = {"molecular_scope": "molecular_span", "population_scope": "population_span"}
        limitation = {key: {"scope": "NARROWER", "literal_span": semantic.get(spans[key])}
                      for key in spans if semantic.get(key) == "NARROWER"}
    return {**structural, "relation_alignment": relation_alignment,
            "assertion_scope": assertion_scope if isinstance(assertion_scope, str) and assertion_scope in ASSERTION_SCOPES else "UNKNOWN",
            "semantic_reason": (semantic or {}).get("reason"),
            "decisive_text": (semantic or {}).get("decisive_text"),
            "semantic_model": (semantic or {}).get("model"),
            "semantic_prompt_version": (semantic or {}).get("prompt_version"),
            "semantic_assessment": assessment,
            "admission_policy_version": POLICY_VERSION,
            "admission_reason_codes": blockers,
            "final_admission": final,
            "support_result": support_result,
            "verification_status": verification_status,
            "support_limitation": limitation,
            "study_context": structural.get("study_context", "UNSPECIFIED"),
            "applicability_to_case": structural.get("applicability_to_case", "NOT_ASSESSED")}

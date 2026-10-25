"""Operational matching context. Historical replay is explicitly isolated."""
from contextvars import ContextVar
from .loader import get_registry
from .case_resolution import disease_matches, disease_context, disease_retrieval_match, resolution_record
from .molecular import resolve_variant
from .surface import molecular_surface, surface

active_registry = ContextVar("terminology_registry", default=None)
historical_matching = ContextVar("historical_matching", default=False)


def registry():
    return active_registry.get() or get_registry()


def identity(domain, left, right, gene=None):
    linked_gene = registry().resolve("GENE", str(gene or "")) if gene else None
    gene_id = linked_gene.concept_ids[0] if linked_gene and linked_gene.status == "RESOLVED" else None
    reg = registry()
    a = reg.resolve(domain, str(left or ""), gene_id=gene_id)
    b = reg.resolve(domain, str(right or ""), gene_id=gene_id)
    if a.status == "AMBIGUOUS" or b.status == "AMBIGUOUS":
        return False
    if domain == "VARIANT" and not gene_id:
        # A source-backed ambiguous variant cannot be admitted without pairing.
        return a.status == b.status == "UNMAPPED" and bool(surface(str(left or ""))) and surface(str(left or "")) == surface(str(right or ""))
    return (a.status == b.status == "RESOLVED" and a.concept_ids == b.concept_ids) or (
        bool(surface(str(left or ""))) and surface(str(left or "")) == surface(str(right or "")))


def compact_resolution(result):
    payload = resolution_record(result) if hasattr(result, "to_dict") else result
    return {k: payload[k] for k in ("raw_value", "status", "method", "concept_ids", "reasons", "residual_context", "raw_residual_context", "partial_concept_ids", "normalization_version", "translation_version", "approved_alias_source", "match_span") if k in payload}


def trace(case, candidate):
    reg = registry()
    trial_context = candidate.get('trial_context') or {}
    effective_diseases = ([{'label': str(value)} for value in trial_context.get('conditions', ()) if value]
                          if trial_context else candidate.get('disease') or [])
    return {"version": reg.version,
            'disease_retrieval_scope': [
                {'query': str((value.get('raw_value') or value.get('normalized_value') or '') if isinstance(value, dict) else value),
                 'candidate': str(disease.get('label') or ''),
                 'origin': 'TRIAL_CONTEXT' if trial_context else 'CANDIDATE_DISEASE',
                 'provenance': trial_context.get('provenance') if trial_context else None,
                 **disease_retrieval_match(str((value.get('raw_value') or value.get('normalized_value') or '') if isinstance(value, dict) else value), str(disease.get('label') or ''), reg)}
                for value in (case.get('diseases') or ([case['disease']] if case.get('disease') else []))
                for disease in effective_diseases],
            "query_diseases": [compact_resolution(disease_context(str((x.get("raw_value") or x.get("normalized_value") or "") if isinstance(x, dict) else x), reg))
                                for x in (case.get("diseases") or ([case["disease"]] if case.get("disease") else []))],
            "candidate_diseases": [compact_resolution(disease_context(str(x.get("label") or ""), reg)) for x in effective_diseases],
            "query_biomarkers": [{"gene": compact_resolution(reg.resolve("GENE", str(x.get("gene") or ""))),
                                    "variant": compact_resolution(resolve_variant(reg.resolve("GENE", str(x.get("gene") or "")), str(x.get("alteration") or ""), reg))} for x in case.get("biomarkers") or []],
            "profile": candidate.get("entity_resolution")}

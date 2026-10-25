"""Deterministic retrieval: verified CaseContext -> GraphCandidateAssertion
matches -> documents -> SourceUnit. No LLM involved anywhere in this module.

The "KG" queried here is the already-materialized, static
`GraphCandidateAssertion` repository (benchmarks/mtb_evidence/
document_grounded_claims/graph_candidate_repository/4.0/candidates.jsonl) --
see docs/end_to_end_pipeline_pilot/current_component_audit.md for why a live
Neo4j query was out of scope for this research-only pilot.

Due funzioni pubbliche, con ruoli che non vanno confusi:

``retrieve``
    Retrieval **canonico**, l'unico del runtime operativo. Ammette le candidate
    che portano un ``document_identifier`` e ne deriva i descrittori documentali
    dalla provenance della GCA. Nessun bundle congelato viene consultato.

``retrieve_frozen_bundles``
    RESEARCH / REGRESSION ONLY. Restringe il retrieval alle candidate che
    possiedono uno dei 25 EvidenceBundle congelati (benchmarks/mtb_evidence/
    document_grounded_claims/evidence_bundle/evidence_bundles.jsonl), così che
    nessun documento nuovo venga mai richiesto. Serve a riprodurre gli
    esperimenti storici e non è raggiungibile dall'API né dalla console.

La restrizione ai 25 bundle era il comportamento **di default** della vecchia
firma ``retrieve(case_context, document_mode="REPLAY")``. Ora è un'altra
funzione, con un altro nome, che nessun percorso operativo chiama.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any

from backend.research_pipeline.data_access import (
    adapt_candidate_for_runtime,
    evidence_bundles_path,
    read_candidate_corpus_utf8,
    read_historical_candidate_corpus_utf8,
    runtime_corpus_snapshot,
)
from backend.research_pipeline.documents.authorized_cache import expand_identifier
from backend.research_pipeline.documents.trial_context import enrich_trial_candidate, normalize_nct
from backend.research_pipeline.retrieval.composite_evidence import derive_composite_relations
from backend.research_pipeline.retrieval import normalization
from backend.research_pipeline.terminology import matching as terminology
from backend.research_pipeline.terminology.case_resolution import resolve_case, disease_retrieval_match
from backend.research_pipeline.terminology.loader import get_overlay
from backend.research_pipeline.terminology.molecular import parse_profile, evaluate_profile, fusion_partners
from backend.research_pipeline.terminology.surface import molecular_surface
from backend.research_pipeline.terminology.surface import surface as preserved_surface
from backend.research_pipeline.retrieval.relation_family import (
    INVALID_PROVENANCE,
    classify_relation_family,
)

# I percorsi arrivano da ``data_access``, non da ``Path(__file__).parents[n]``:
# la profondità di questo file è cambiata con la promozione, e un percorso
# derivato dalla posizione del sorgente si sarebbe rotto in silenzio.

MAX_ASSOCIATIONS_PER_CASE = 3
_FAMILY_CAP = os.getenv("RESEARCH_PIPELINE_MAX_CANDIDATES_PER_FAMILY", "").strip()
MAX_ASSOCIATIONS_PER_FAMILY = int(_FAMILY_CAP) if _FAMILY_CAP else None
MAX_DOCUMENTS_PER_ASSOCIATION = 2
MAX_SOURCE_UNITS_PER_DOCUMENT = 4
RETRIEVAL_RANKING_VERSION = "structured-retrieval-ranking/1.1"


def _live_provenance_bundles(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Build document descriptors from GCA provenance, never from gold units.

    Il prefisso ``_live_`` e il prefisso ``live:`` dei ``bundle_id`` prodotti
    sono nomi interni ereditati: restano invariati di proposito. Il secondo è un
    **valore di dato** che compare in artefatti e test già prodotti, e cambiarlo
    romperebbe il confronto forense senza cambiare nulla di sostanziale. Questa
    è oggi la sola costruzione dei descrittori documentali del runtime canonico.
    """
    descriptors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in candidate.get("document_identifiers") or []:
        for identifier in expand_identifier(raw):
            kind_value = next(
                ((kind, str(identifier.get(kind)).strip()) for kind in ("pmid", "pmcid", "nct", "doi", "url")
                 if identifier.get(kind)),
                None,
            )
            if kind_value is None:
                continue
            kind, value = kind_value
            normalized = value.upper() if kind in {"pmid", "pmcid", "nct"} else value.lower()
            document_id = f"{kind}:{normalized}"
            if document_id in seen:
                continue
            seen.add(document_id)
            descriptors.append({
                "bundle_id": f"live:{candidate['candidate_id']}:{document_id}",
                "document_id": document_id,
                "provenance_identifier": {
                    kind: normalized,
                    **{field: identifier[field] for field in
                       ("original_identifier_type", "identifier_status", "scope")
                       if identifier.get(field)},
                },
                "bundle_type": "PROVENANCE_DOCUMENT",
                "source_unit_ids": [],
            })
    return descriptors


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _labels(items: list[dict]) -> set[str]:
    norm = _norm if terminology.historical_matching.get() else preserved_surface
    return {norm(str(item.get("label"))) for item in items if item.get("label")}


def _term_matches(term: str, label: str) -> bool:
    """Retrieve exact or source-backed broader contexts without claiming identity."""
    if terminology.historical_matching.get():
        return normalization.disease_matches(term, label)
    return disease_retrieval_match(str(term or ''), str(label or ''), terminology.registry())['eligible']


def _intervention_matches(term: str, label: str) -> bool:
    """Require the same informative drug name, allowing formulation suffixes."""
    if not terminology.historical_matching.get():
        return (terminology.identity("INTERVENTION", term, label)
                or _literal_preferred_intervention_match(term, label))
    formulation = {
        "hydrochloride", "sodium", "acetate", "mesylate", "citrate",
        "phosphate", "sulfate", "succinate", "maleate", "injection",
    }
    left = _norm(term).split()
    right = _norm(label).split()
    if not left or not right:
        return False
    left_core = [token for token in left if token not in formulation]
    right_core = [token for token in right if token not in formulation]
    # Salt-only strings have no drug identity. Shared generic material never
    # licenses a match; authorized aliases must be explicit upstream data.
    return bool(left_core and right_core and left_core == right_core)


def _literal_preferred_intervention_match(term: str, label: str) -> bool:
    """Retrieve identical preferred names without asserting concept identity.

    Different source vocabularies may assign IDs to the very same literal name.
    Keep the registry collision visible and never extend this to alias collisions,
    molecular subjects, different spellings, formulations or regimen components.
    Scientific admission continues to use the unchanged identity validators.
    """
    if terminology.historical_matching.get():
        return False
    literal = preserved_surface(str(term or ""))
    if not literal or literal != preserved_surface(str(label or "")):
        return False
    resolved = terminology.registry().resolve("INTERVENTION", str(term))
    if resolved.status != "AMBIGUOUS":
        return False
    preferred_ids = {
        item.concept_id for item in resolved.terms
        if item.alias_scope == "PREFERRED" and preserved_surface(item.label) == literal
    }
    return preferred_ids == set(resolved.concept_ids)


def _molecular_term_matches(term: Any, label: Any) -> bool:
    """Exact normalized matching for genes, variants and structured IDs."""
    if not terminology.historical_matching.get():
        return terminology.identity("GENE", term, label)
    left, right = _norm(term), _norm(label)
    return bool(left and right and left == right)


def _alteration_matches(left, right, gene=None):
    if terminology.historical_matching.get():
        return normalization.alteration_matches(left, right)
    return terminology.identity("VARIANT", left, right, gene)


def _value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("normalized_value") or value.get("raw_value") or value.get("value")
    return value


def _positive_status(value: Any) -> bool:
    return str(value or "PRESENT").upper() in {"PRESENT", "ASSERTED", "HISTORICAL", "CURRENT", "TARGET"}


def _molecular_query_subject(value: Any) -> bool:
    """Keep uncertain subjects as query constraints, without asserting presence.

    Historical replay retains its recorded positive-only subject policy.
    Compound presence remains governed separately by three-valued evaluation.
    """
    return _positive_status(value) or (
        not terminology.historical_matching.get()
        and str(value).upper() == "UNCERTAIN"
    )


def _case_biomarkers(case_context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in (case_context.get("biomarkers") or [])
        if isinstance(item, dict) and _molecular_query_subject(item.get("assertion_status"))
    ]


def _candidate_biomarkers(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for item in candidate.get("biomarkers") or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").upper()
        label = item.get("label") or item.get("raw_value")
        gene = item.get("gene")
        alteration = item.get("alteration")
        if kind in {"GENE", "GENESYMBOL"}:
            observations.append({"gene": gene or label, "alteration": alteration, "alteration_type": item.get("alteration_type"), "specificity": "GENE"})
        elif kind in {"VARIANT", "ALTERATION"}:
            observations.append({"gene": gene, "alteration": alteration or label, "alteration_type": item.get("alteration_type"), "specificity": "VARIANT"})
        elif kind in {"MOLECULARPROFILE", "MOLECULAR_PROFILE"}:
            observations.append({"gene": gene, "alteration": alteration or label, "alteration_type": item.get("alteration_type"), "specificity": "MOLECULAR_PROFILE"})
        else:
            observations.append({"gene": gene, "alteration": alteration or label, "alteration_type": item.get("alteration_type"), "specificity": "GENERIC_ALTERATION"})
    if terminology.historical_matching.get():
        # The v2 frozen matcher used a sole gene label and a sole variant
        # label as a pair. Reproduce that convention only in explicit replay;
        # canonical identity still requires the audited source-edge anchor.
        genes = {item["gene"] for item in observations if item.get("gene")}
        variants = [item for item in observations if item.get("alteration")]
        if len(genes) == len(variants) == 1 and not variants[0].get("gene"):
            variants[0]["gene"] = next(iter(genes))
    return observations


def _case_diseases(case_context: dict[str, Any]) -> list[str]:
    values = []
    for item in case_context.get("diseases") or []:
        if not isinstance(item, dict) or not _positive_status(item.get("assertion_status")):
            continue
        role = str(item.get("clinical_role") or "PRIMARY").upper()
        if role in {"HISTORY", "DIFFERENTIAL", "UNCERTAIN"}:
            continue
        raw = _value(item.get("value") or item)
        if raw:
            values.append(str(raw))
    if not values and "diseases" not in case_context and case_context.get("disease"):
        raw = _value(case_context.get("disease"))
        if raw:
            values.append(str(raw))
    return list(dict.fromkeys(values))


def _case_ncts(case_context: dict[str, Any]) -> set[str]:
    values = set()
    for item in case_context.get("trial_mentions") or []:
        raw = _value(item.get("nct_id") if isinstance(item, dict) else item)
        normalized = normalize_nct(raw)
        if normalized:
            values.add(normalized)
    return values


def _candidate_ncts(candidate: dict[str, Any]) -> set[str]:
    values = set()
    for item in candidate.get("document_identifiers") or []:
        if isinstance(item, dict):
            normalized = normalize_nct(item.get("nct"))
            if normalized:
                values.add(normalized)
    return values


def _diagnostic_fields(candidate: dict[str, Any]) -> dict[str, set[str]]:
    diagnostic = candidate.get("companion_diagnostic") or {}
    fields = {
        key: {_norm(diagnostic.get(key))} if diagnostic.get(key) else set()
        for key in ("name", "identifier", "associated_gene", "associated_drug", "platform", "specimen")
    }
    name = str(diagnostic.get("name") or "")
    without_manufacturer = re.sub(r"\s*\([^()]+\)\s*$", "", name).strip()
    if without_manufacturer and without_manufacturer != name:
        fields["name"].add(_norm(without_manufacturer))
    return fields


def _case_diagnostic_fields(case_context: dict[str, Any]) -> list[dict[str, set[str]]]:
    output = []
    for item in case_context.get("companion_diagnostic_mentions") or []:
        if not isinstance(item, dict) or not _positive_status(item.get("assertion_status")):
            continue
        output.append({
            key: {_norm(_value(item.get(key)))} if _value(item.get(key)) else set()
            for key in ("name", "identifier", "associated_gene", "associated_drug", "platform", "specimen")
        })
    return output


def _molecular_compatible(case_items: list[dict[str, Any]], candidate_items: list[dict[str, Any]]) -> tuple[bool, set[str]]:
    matched_fields: set[str] = set()
    for query in case_items:
        q_gene, q_alt = query.get("gene"), query.get("alteration")
        q_type = str(query.get("alteration_type") or "").upper()
        if q_type == 'PHENOTYPE':
            # Phenotypes require their source-linked profile constraint above;
            # a missing gene cannot turn them into a wildcard gene query.
            continue
        same_gene = [
            item for item in candidate_items
            if q_gene and item.get("gene") and _molecular_term_matches(q_gene, item.get("gene"))
        ]
        if q_alt and same_gene:
            # A specific candidate for the same gene must not degrade to a
            # generic gene-level match when its variant/type is incompatible.
            if any(item.get("alteration") for item in same_gene):
                for candidate in same_gene:
                    c_alt = candidate.get("alteration")
                    if not c_alt or not _alteration_matches(q_alt, c_alt, q_gene):
                        continue
                    c_type = str(candidate.get("alteration_type") or "").upper()
                    if q_type and c_type and q_type not in {"GENERIC", "UNKNOWN"} and c_type not in {"GENERIC", "UNKNOWN"} and q_type != c_type:
                        continue
                    matched_fields.add("VARIANT_EXACT")
                    return True, matched_fields
                continue
            # When a source row contains a specific alteration but did not
            # preserve its gene pairing, a separate Gene node cannot be used
            # to silently downgrade the case's exact-variant query.  The
            # association is ambiguous, so fail closed at variant retrieval.
            if any(item.get("alteration") for item in candidate_items):
                continue
        if q_gene and not q_alt and any(item.get("alteration") for item in candidate_items):
            # A separate Gene row must not mask a variant-specific row in the
            # same candidate when the case supplied no grounded variant.
            continue
        for candidate in candidate_items:
            c_gene, c_alt = candidate.get("gene"), candidate.get("alteration")
            if q_gene and (not c_gene or not _molecular_term_matches(q_gene, c_gene)):
                continue
            if q_alt:
                if c_alt and not _alteration_matches(q_alt, c_alt, q_gene):
                    continue
                if not c_alt:
                    matched_fields.add("GENE_LEVEL_CANDIDATE")
                else:
                    matched_fields.add("VARIANT_EXACT")
            elif q_gene:
                # A gene-only observation cannot license a candidate whose
                # claim is specific to an unverified alteration.
                if c_alt:
                    continue
                matched_fields.add("GENE_EXACT")
            else:
                continue
            c_type = str(candidate.get("alteration_type") or "").upper()
            if q_type and c_type and q_type not in {"GENERIC", "UNKNOWN"} and c_type not in {"GENERIC", "UNKNOWN"} and q_type != c_type:
                matched_fields.clear()
                continue
            return True, matched_fields
    return False, matched_fields


def _group_matched_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records:
        key = record.get("semantic_key") or record.get("candidate_id")
        if key not in grouped:
            grouped[key] = dict(record)
            grouped[key]["candidate_group_candidate_ids"] = []
            grouped[key]["candidate_group_traces"] = []
            order.append(key)
        grouped[key]["candidate_group_candidate_ids"].append(record["candidate_id"])
        if record.get("candidate_trace"):
            grouped[key]["candidate_group_traces"].append(record["candidate_trace"])
    return [grouped[key] for key in order]


def _retrieval_anchor_trace(case_context: dict[str, Any]) -> list[dict[str, Any]]:
    biomarkers = case_context.get("biomarkers") or []
    return [
        {
            "anchor_type": "BIOMARKER",
            "value": {"gene": item.get("gene"), "alteration": item.get("alteration"), "alteration_type": item.get("alteration_type")},
            "assertion_status": item.get("assertion_status", "PRESENT"),
            "parsed": True,
            "validated": _positive_status(item.get("assertion_status")),
            "projected": True,
            "used_by_retrieval": _molecular_query_subject(item.get("assertion_status")),
        }
        for item in biomarkers if isinstance(item, dict)
    ]


def _trial_term_matches(term: str, label: str) -> bool:
    """Trial conditions need the same conservative identity as KG disease."""
    return _term_matches(term, label)


def _trial_intervention_matches(term: str, context: dict[str, Any]) -> bool:
    """Match trial interventions without collapsing specific regimens.

    Raw intervention labels are authoritative.  Normalized aliases are used
    only when no raw label exists, preventing ``trastuzumab`` from matching a
    more specific ``trastuzumab deruxtecan`` regimen by substring.
    """
    if not terminology.historical_matching.get():
        values = context.get("interventions_raw") or context.get("interventions_normalized") or ()
        return any(_intervention_matches(term, value) for value in values)
    target = _norm(term)
    raw = [_norm(x) for x in context.get("interventions_raw", ()) if x]
    normalized = [_norm(x) for x in context.get("interventions_normalized", ()) if x]
    return bool(target and (target in raw or target in normalized))


@lru_cache(maxsize=1)
def load_candidates() -> dict[str, dict]:
    # ``candidates.jsonl`` pesa 72,5 MB e il dataset è congelato: rileggerlo a
    # ogni run costava ~3 s per chiamata e rendeva l'endpoint inutilizzabile.
    # La cache è invalidabile con ``load_candidates.cache_clear()`` nei test che
    # cambiano ``RESEARCH_PIPELINE_DATA_ROOT``.
    return {
        row["candidate_id"]: row
        for row in (
            adapt_candidate_for_runtime(json.loads(line))
            for line in read_candidate_corpus_utf8().splitlines()
            if line.strip()
        )
    }


@lru_cache(maxsize=1)
def load_bundles_by_candidate() -> dict[str, list[dict]]:
    by_candidate: dict[str, list[dict]] = {}
    for line in evidence_bundles_path().read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        by_candidate.setdefault(row["candidate_id"], []).append(row)
    return by_candidate


def _match_candidate(case_context: dict[str, Any], candidate: dict[str, Any]) -> tuple[bool, list[str]]:
    compound_profile = not terminology.historical_matching.get() and (candidate.get("entity_resolution") or {}).get("compound")
    if compound_profile:
        profile = candidate["entity_resolution"]["profile"]
        resolved = case_context.get("entity_resolution") or resolve_case(case_context, terminology.registry())["entity_resolution"]
        observations = [{**x.get("observation", x["variant"]), "assertion_status": x["assertion_status"]}
                        for x in resolved.get("biomarkers", []) + resolved.get("negated_biomarkers", [])]
        if profile["status"] != "RESOLVED" or evaluate_profile(profile["ast"], observations) != "TRUE":
            return False, ["PROFILE_CONSTRAINT_UNKNOWN_OR_FALSE"]
    # Trial conditions/interventions are retrieval context joined by the
    # candidate's own NCT provenance.  They are not copied into evidence
    # artifacts and never imply efficacy or eligibility.
    if classify_relation_family(candidate) == "CLINICAL_TRIAL" and candidate.get("source_properties") is not None:
        candidate, _ = enrich_trial_candidate(candidate)
    reasons: list[str] = []
    case_diseases = _case_diseases(case_context)
    trial_context = candidate.get("trial_context") or {}
    candidate_disease = _labels(candidate.get("disease") or [])
    if trial_context:
        candidate_disease = {str(x) for x in trial_context.get("conditions", ()) if x}
    disease_match = _trial_term_matches if trial_context else _term_matches
    disease_ok = not candidate_disease or (
        bool(case_diseases) and any(
            disease_match(case_disease, label)
            for case_disease in case_diseases for label in candidate_disease
        )
    )
    if not disease_ok:
        reasons.append("DISEASE_NOT_COMPATIBLE")

    # Use every textual field the parser populated for each biomarker (gene, normalized
    # value, raw value), not just the gene symbol alone: for pan-genomic category
    # biomarkers without a true gene (e.g. "MSI-High"), the parser sometimes puts a
    # descriptive word in `gene` (observed: "microsatellite") that alone loses the
    # abbreviation/qualifier ("MSI"/"High") carried by normalized_value -- matching
    # against the union of fields is more robust than trusting a single field.
    case_biomarkers = _case_biomarkers(case_context)
    candidate_biomarker_items = _candidate_biomarkers(candidate)
    if case_biomarkers and all(str(x.get('alteration_type') or '').upper() == 'PHENOTYPE' for x in case_biomarkers) and not compound_profile:
        return False, ['PHENOTYPE_SOURCE_PROFILE_REQUIRED']
    negated_biomarkers = case_context.get("negated_biomarkers") or []
    if not compound_profile and candidate_biomarker_items and any(
        _molecular_compatible([item], candidate_biomarker_items)[0]
        for item in negated_biomarkers if isinstance(item, dict)
    ):
        reasons.append("NEGATED_BIOMARKER_CONFLICT")
        return False, reasons
    molecular_anchor_match, molecular_fields = (True, {"PROFILE_CONSTRAINT_CONFIRMED"}) if compound_profile else _molecular_compatible(case_biomarkers, candidate_biomarker_items)
    case_genes = {_norm(item.get("gene")) for item in case_biomarkers if item.get("gene")}
    case_alterations = {item.get("alteration") for item in case_biomarkers if item.get("alteration")}
    gene_ok = molecular_anchor_match if case_biomarkers else True
    if case_biomarkers and candidate_biomarker_items and not molecular_anchor_match:
        reasons.append("BIOMARKER_NOT_COMPATIBLE")
        if not terminology.historical_matching.get():
            for item in case_biomarkers:
                gene_resolution = terminology.registry().resolve("GENE", str(item.get("gene") or ""))
                if gene_resolution.status == "AMBIGUOUS":
                    reasons.append("GENE_IDENTITY_AMBIGUOUS")
                elif item.get("alteration"):
                    gene_id = gene_resolution.concept_ids[0] if gene_resolution.status == "RESOLVED" else None
                    variant = terminology.registry().resolve("VARIANT", str(item["alteration"]), gene_id=gene_id)
                    if variant.status == "AMBIGUOUS":
                        reasons.append("VARIANT_IDENTITY_AMBIGUOUS")
            reasons = list(dict.fromkeys(reasons))
        return False, reasons
    source_genes = {_norm(x) for x in trial_context.get("genes", ()) if x}
    trial_source_gene_match = False
    if source_genes and case_genes:
        # Trial context is a gene-level retrieval anchor, not a variant-level
        # claim.  It may satisfy the case's molecular dimension when the gene
        # matches even though the trial candidate has no GCA biomarker nodes;
        # conversely, a declared mismatching trial gene remains a hard veto.
        trial_source_gene_match = any(
            _molecular_term_matches(x, y) for x in case_genes for y in source_genes
        )
        gene_ok = trial_source_gene_match
        if not gene_ok:
            reasons.append("TRIAL_SOURCE_GENE_NOT_COMPATIBLE")
    elif classify_relation_family(candidate) == "CLINICAL_TRIAL" and not candidate_biomarker_items:
        # An intervention-only trial with no declared molecular subject stays
        # eligible through its declared drug/disease context; absence of a gene
        # is not a gene mismatch.
        gene_ok = True
    if not gene_ok:
        reasons.append("BIOMARKER_GENE_NOT_COMPATIBLE")

    intent = case_context.get("query_intent")
    targets = [item for item in (case_context.get("target_interventions") or []) if _positive_status(item.get("assertion_status") if isinstance(item, dict) else None)]
    if not targets and case_context.get("target_intervention"):
        targets = [case_context.get("target_intervention")]
    target_values = {
        str(target.get("normalized_value") or target.get("raw_value") or "")
        for target in targets if target
    }
    candidate_interventions = _labels(candidate.get("interventions") or [])
    if trial_context:
        candidate_interventions = {
            str(x) for x in (
                list(trial_context.get("interventions_raw", ()))
                + list(trial_context.get("interventions_normalized", ()))
            ) if x
        }
        intervention_match = bool(
            target_values and any(_trial_intervention_matches(target_value, trial_context) for target_value in target_values)
        )
        intervention_ok = not candidate_interventions or not target_values or intervention_match
    else:
        intervention_ok = not candidate_interventions or not target_values or any(
            _intervention_matches(target_value, label)
            for target_value in target_values for label in candidate_interventions
        )
        intervention_match = bool(target_values and candidate_interventions and intervention_ok)
    if intent == "THERAPY_EVALUATION" and candidate_interventions:
        if not intervention_ok:
            reasons.append("TARGET_INTERVENTION_NOT_COMPATIBLE")

    case_ncts = _case_ncts(case_context)
    candidate_ncts = _candidate_ncts(candidate)
    if case_ncts and not case_ncts.intersection(candidate_ncts):
        reasons.append("NCT_NOT_COMPATIBLE")
        return False, reasons

    diagnostics = _case_diagnostic_fields(case_context)
    if diagnostics:
        candidate_diagnostic = _diagnostic_fields(candidate)
        diagnostic_ok = any(
            all(not values or values.intersection(candidate_diagnostic.get(key, set()))
                for key, values in query.items())
            for query in diagnostics
        )
        if not diagnostic_ok:
            reasons.append("COMPANION_DIAGNOSTIC_NOT_COMPATIBLE")
            return False, reasons
    else:
        diagnostic_ok = False

    case_has_positive_anchor = bool(case_biomarkers or target_values or case_diseases or case_ncts or diagnostics)
    positive_anchor = (
        molecular_anchor_match or trial_source_gene_match or intervention_match
        or diagnostic_ok or (disease_ok and bool(case_diseases))
    )
    if not case_has_positive_anchor:
        reasons.append("NO_POSITIVE_ANCHOR")
        return False, reasons
    # A shared intervention is a useful retrieval anchor only when it does not
    # contradict an explicitly stated molecular subject.  In particular,
    # EGFR + panitumumab must not retrieve a KRAS + panitumumab candidate just
    # because the drug matches.  Candidates that declare no molecular anchor
    # (for example, intervention-only trial records) remain eligible through
    # the normal intervention path.
    ok = disease_ok and gene_ok and intervention_ok and positive_anchor
    if ok:
        reasons = []
        if candidate_disease:
            reasons.append("DISEASE_COMPATIBLE")
        if molecular_anchor_match:
            reasons.append("BIOMARKER_COMPATIBLE")
            reasons.extend(sorted(molecular_fields))
        if trial_source_gene_match:
            reasons.append("TRIAL_SOURCE_GENE_COMPATIBLE")
        if intervention_match:
            reasons.append("INTERVENTION_COMPATIBLE")
            if any(_literal_preferred_intervention_match(value, label)
                   for value in target_values for label in candidate_interventions):
                reasons.append("INTERVENTION_LITERAL_IDENTITY_AMBIGUOUS_CONCEPT")
        if (classify_relation_family(candidate) == "CLINICAL_TRIAL" and case_biomarkers
                and not molecular_anchor_match and not trial_source_gene_match
                and not intervention_match and not case_ncts and candidate_disease):
            reasons.append("TRIAL_DISEASE_CONTEXT_ONLY")
    return ok, reasons


def _compatibility_score(case_context: dict[str, Any], candidate: dict[str, Any]) -> tuple[int, dict[str, bool]]:
    """Deterministic specificity score applied only after hard compatibility.

    The score uses clinical anchors already present in CaseContext. Candidate
    identifiers and evaluation references are deliberately absent.
    """
    if classify_relation_family(candidate) == "CLINICAL_TRIAL" and candidate.get("source_properties") is not None:
        candidate, _ = enrich_trial_candidate(candidate)
    case_biomarkers = _case_biomarkers(case_context)
    case_genes = {_norm(item.get("gene")) for item in case_biomarkers if item.get("gene")}
    case_alterations = {item.get("alteration") for item in case_biomarkers if item.get("alteration")}
    candidate_molecular = _candidate_biomarkers(candidate)
    candidate_genes = {_norm(item.get("gene")) for item in candidate_molecular if item.get("gene")}
    candidate_alterations = {item.get("alteration") for item in candidate_molecular if item.get("alteration")}
    targets = case_context.get("target_interventions") or []
    if not targets and case_context.get("target_intervention"):
        targets = [case_context.get("target_intervention")]
    target_values = {
        str(target.get("normalized_value") or target.get("raw_value") or "")
        for target in targets if target
    }
    target_value = next(iter(sorted(target_values)), "")
    candidate_interventions=_labels(candidate.get("interventions") or [])
    trial_context = candidate.get("trial_context") or {}
    disease_values=set(_case_diseases(case_context)); candidate_diseases=_labels(candidate.get("disease") or [])
    intervention_raw_exact = False
    intervention_normalized_match = False
    if trial_context:
        # Score the same NCT-source molecular anchor accepted by the matcher,
        # including drug-only GCA rows. This remains gene-level retrieval
        # metadata, never a variant match or an efficacy claim.
        if not terminology.historical_matching.get():
            candidate_genes.update(_norm(gene) for gene in trial_context.get("genes", ()) if gene)
        candidate_interventions = {
            str(x) for x in (
                list(trial_context.get("interventions_raw", ()))
                + list(trial_context.get("interventions_normalized", ()))
            ) if x
        }
        candidate_diseases = {str(x) for x in trial_context.get("conditions", ()) if x}
        intervention_matcher = _intervention_matches
        intervention_raw_exact = bool(target_values and any(preserved_surface(t) == preserved_surface(x) for t in target_values for x in trial_context.get("interventions_raw", ()) if x))
        intervention_normalized_match = bool(target_values and any(preserved_surface(t) == preserved_surface(x) for t in target_values for x in trial_context.get("interventions_normalized", ()) if x))
        disease_matcher = _trial_term_matches
    else:
        intervention_matcher = _intervention_matches
        disease_matcher = _term_matches
        intervention_raw_exact = bool(target_values and any(
            preserved_surface(target) == preserved_surface(label)
            for target in target_values for label in candidate_interventions))
    intervention_exact = (
        bool(target_values and any(_trial_intervention_matches(t, trial_context) for t in target_values))
        if trial_context else
        bool(target_values and candidate_interventions and any(intervention_matcher(t,x) for t in target_values for x in candidate_interventions))
    )
    features={
        "intervention_exact": intervention_exact,
        "intervention_raw_exact": intervention_raw_exact,
        "intervention_normalized_match": intervention_normalized_match,
        "alteration_exact": bool(case_alterations and candidate_alterations and any(_alteration_matches(x, y, next(iter(case_genes), None)) for x in case_alterations for y in candidate_alterations)),
        "gene_exact": bool(case_genes and candidate_genes and any(_molecular_term_matches(x, y) for x in case_genes for y in candidate_genes)),
        "disease_exact": bool(disease_values and candidate_diseases and any(_norm(disease_value) == _norm(x) for disease_value in disease_values for x in candidate_diseases)),
        "disease_scope_compatible": bool(disease_values and candidate_diseases and any(disease_matcher(disease_value, x) for disease_value in disease_values for x in candidate_diseases)),
    }
    features["matched_anchor_count"] = sum(bool(features.get(k)) for k in ("intervention_exact", "alteration_exact", "gene_exact", "disease_exact"))
    features["populated_dimension_count"] = sum(bool(x) for x in (
        candidate_alterations, candidate_genes,
        candidate_interventions if trial_context else _labels(candidate.get("interventions") or []),
        candidate_diseases,
    ))
    score=8*features["intervention_exact"]+4*features["alteration_exact"]+2*features["gene_exact"]+features["disease_exact"]
    return int(score),features


def _specificity_order_key(candidate_id: str, features: dict[str, Any]) -> tuple:
    """Lexicographic specificity order applied after compatibility filtering."""
    intervention_kind = 2 if features.get("intervention_raw_exact") else (1 if features.get("intervention_normalized_match") else 0)
    return (
        -intervention_kind,
        -int(bool(features.get("alteration_exact"))),
        -int(bool(features.get("gene_exact"))),
        -int(bool(features.get("disease_exact"))),
        -int(features.get("matched_anchor_count") or 0),
        -int(features.get("populated_dimension_count") or 0),
        candidate_id,
    )


_linked_cache = None
_prepared_cache = None
_composed_cache = None


def _composed_candidates(source):
    """Build the runtime join once for the identity of an immutable loaded corpus."""
    global _composed_cache
    cached = _composed_cache
    if cached is not None and cached[0] is source:
        return cached[1:]
    derived, exclusions = derive_composite_relations(source)
    composed_source_ids = frozenset(row["composite_lineage"]["evidence_drug_candidate_id"] for row in derived.values())
    combined = {**source, **derived} if derived else source
    _composed_cache = (source, combined, derived, exclusions, composed_source_ids)
    return combined, derived, exclusions, composed_source_ids


def _prepared_and_indexed(candidates, registry):
    global _prepared_cache
    cached = _prepared_cache
    if cached is not None and cached[0] is candidates and cached[1] is registry:
        return cached[2], cached[3]
    prepared, candidate_genes, by_gene = {}, {}, {}
    for cid, source in candidates.items():
        row = source
        if classify_relation_family(row) == "CLINICAL_TRIAL" and row.get("source_properties") is not None:
            row, _ = enrich_trial_candidate(row)
        prepared[cid] = row
        molecular = _candidate_biomarkers(row)
        labels = [x.get("gene") for x in molecular] + list((row.get("trial_context") or {}).get("genes") or [])
        ids = set()
        fully_resolved = bool(labels) and not (row.get("entity_resolution") or {}).get("compound")
        for label in labels:
            resolution = registry.resolve("GENE", str(label or ""))
            if resolution.status == "RESOLVED":
                ids.update(resolution.concept_ids)
            else:
                fully_resolved = False
        # Missing/ambiguous anchors remain in the full conservative matcher.
        if ids and fully_resolved:
            candidate_genes[cid] = frozenset(ids)
            for gene_id in ids:
                by_gene.setdefault(gene_id, set()).add(cid)
    index = {"candidate_genes": candidate_genes,
             "by_gene": {gene_id: frozenset(cids) for gene_id, cids in by_gene.items()}}
    _prepared_cache = (candidates, registry, prepared, index)
    return prepared, index


def _linked_candidates(candidates, registry):
    global _linked_cache
    overlay = get_overlay("4e197764dff17cb396c5026338f07e001c0573e37bec9fb0f8a32e652b9d7edd")
    cached = _linked_cache
    if cached is not None and cached[0] is candidates and cached[1] is registry and cached[2] is overlay:
        return cached[3]
    linked = dict(candidates)
    for cid, structural in overlay.items():
        if cid not in candidates:
            continue
        row = dict(candidates[cid])
        biomarkers = []
        for component in structural["components"]:
            for gene_id in component["gene_ids"]:
                gene = next((t.label for t in registry._ids.get(("GENE", gene_id.casefold()), []) if t.alias_scope == "PREFERRED"), None)
                if gene:
                    biomarkers.append({"id": component["variant_id"], "type": "Variant", "label": component["name"],
                                       "gene": gene, "alteration": component["name"]})
        profile = parse_profile(structural["name"], registry)
        def fusion_nodes(ast):
            if not isinstance(ast, dict):
                return []
            if ast.get("op") == "FUSION":
                return [ast]
            return [node for child in ast.get("args", [ast.get("arg")]) for node in fusion_nodes(child)]

        fusions = fusion_nodes(profile.get("ast"))
        for node in fusions:
            biomarkers.append({"id": node["concept_id"], "type": "Variant", "label": "::".join(node["partners"]) + " Fusion",
                               "gene": "::".join(node["partners"]), "alteration": "Fusion", "alteration_type": "FUSION"})
        if profile["status"] == "RESOLVED" and set(profile["component_ids"]) != set(structural["variant_ids"]):
            profile = {**profile, "status": "UNMAPPED", "ast": None, "reason": "SOURCE_COMPONENT_MISMATCH"}
        row["biomarkers"] = biomarkers
        row["entity_resolution"] = {"profile_id": structural["profile_id"], "registry_version": registry.version,
                                    "profile": profile, "compound": bool(profile.get("ast") and profile["ast"].get("op") == "PHENOTYPE") or bool(fusions) or len(structural["variant_ids"]) != 1 or bool(re.search(r"\b(?:AND|OR|NOT)\b", structural["name"]))}
        linked[cid] = row
    _linked_cache = (candidates, registry, overlay, linked)
    return linked


def retrieve(case_context: dict[str, Any]) -> dict[str, Any]:
    """Retrieval **canonico**: unico usato dal runtime operativo.

    Ammette ogni candidate che porti almeno un ``document_identifier`` e ne
    deriva i descrittori documentali dalla propria provenance. Non consulta gli
    EvidenceBundle congelati e non è ristretto ai 25 casi del pilot.

    Non esiste un parametro che possa cambiare questo insieme di candidate: la
    firma precedente aveva ``document_mode="REPLAY"`` come default, e chiunque
    chiamasse ``retrieve(case_context)`` senza argomenti finiva sul corpus
    congelato senza accorgersene.
    """
    token = terminology.active_registry.set(terminology.registry())
    try:
        return _retrieve(resolve_case(case_context, terminology.registry()), use_frozen_bundles=False)
    finally:
        terminology.active_registry.reset(token)


def retrieve_exhaustive(case_context: dict[str, Any]) -> dict[str, Any]:
    """Canonical matching without the candidate prefilter, for offline parity checks."""
    token = terminology.active_registry.set(terminology.registry())
    try:
        return _retrieve(resolve_case(case_context, terminology.registry()), use_frozen_bundles=False, exhaustive=True)
    finally:
        terminology.active_registry.reset(token)


def retrieve_frozen_bundles(case_context: dict[str, Any]) -> dict[str, Any]:
    """RESEARCH / REGRESSION ONLY — non fa parte del runtime canonico.

    Restringe il retrieval alle sole candidate che possiedono uno dei 25
    EvidenceBundle congelati e ne restituisce i ``source_unit_ids`` già
    selezionati dal pilot. Riproduce gli esperimenti storici; non deve essere
    raggiungibile da ``POST /runs``, dal ``RunStore`` né dalla console clinica.
    """
    # Recorded cases replay their recorded retrieval, including historical
    # broader molecular matches. They are observations of a prior experiment,
    # not claims that the current canonical identity gate would admit them.
    from copy import deepcopy
    from backend.research_pipeline.data_access import data_root, read_jsonl
    path = data_root() / "benchmarks/mtb_evidence/end_to_end_pipeline_pilot/retrieval_results.jsonl"
    case_id = case_context.get("case_id")
    if case_id:
        recorded = next((row for row in read_jsonl(path) if row.get("case_id") == case_id), None)
        if recorded is not None:
            if recorded.get("query_intent") != case_context.get("query_intent"):
                raise ValueError("FROZEN_RETRIEVAL_QUERY_INTENT_MISMATCH")
            from backend.research_pipeline.replay import _parser_outputs_by_case
            from backend.research_pipeline.cases.definitions import CASES
            from backend.research_pipeline.casecontext import pipeline as cc_pipeline
            original = _parser_outputs_by_case()[case_id]["case_context_raw"]
            clinical_text = next(case["clinical_text"] for case in CASES if case["case_id"] == case_id)
            verified_input = deepcopy(original)
            chain = cc_pipeline.run(clinical_text, verified_input)
            projected = cc_pipeline.build_retrieval_case_context(verified_input, chain["mentions"])
            # Compare the complete clinical contract, not merely an identifier.
            # Both archived raw input and its verified projection are supported;
            # runtime metadata cannot alter any clinical field of either form.
            fields = set(original) | set(projected)
            supplied = {key: case_context.get(key) for key in fields}
            expected = [{key: value.get(key) for key in fields} for value in (original, projected)]
            if supplied not in expected:
                raise ValueError("FROZEN_RETRIEVAL_INPUT_MISMATCH")
            return {**deepcopy(recorded), "replayed": True, "repository_version": "2.0",
                    "artifact_origin": "RECORDED_REAL_RUN", "documentary_proof": False}
    token = terminology.historical_matching.set(True)
    try:
        return _retrieve(case_context, use_frozen_bundles=True)
    finally:
        terminology.historical_matching.reset(token)


def _retrieve(case_context: dict[str, Any], *, use_frozen_bundles: bool, exhaustive: bool = False) -> dict[str, Any]:
    candidates = load_candidates() if not use_frozen_bundles else _load_historical_candidates()
    if not use_frozen_bundles and any(x.get("materializer_version") == "gca-materializer/4.0" for x in candidates.values()):
        candidates = _linked_candidates(candidates, terminology.registry())
    source_candidate_count = len(candidates)
    if not use_frozen_bundles:
        candidates, derived_candidates, derivation_exclusions, composed_source_ids = _composed_candidates(candidates)
    else:
        derived_candidates, derivation_exclusions, composed_source_ids = {}, [], frozenset()
    gene_index = {"candidate_genes": {}, "by_gene": {}}
    query_gene_ids = set()
    if not use_frozen_bundles:
        candidates, gene_index = _prepared_and_indexed(candidates, terminology.registry())
        for item in _case_biomarkers(case_context):
            resolution = terminology.registry().resolve("GENE", str(item.get("gene") or ""))
            if resolution.status != "RESOLVED":
                query_gene_ids.clear()
                break
            query_gene_ids.update(resolution.concept_ids)
    prefilter_excluded_ids = set()
    if query_gene_ids and not exhaustive:
        compatible_ids = set().union(*(gene_index["by_gene"].get(gid, ()) for gid in query_gene_ids))
        prefilter_excluded_ids = gene_index["candidate_genes"].keys() - compatible_ids
    bundles_by_candidate = load_bundles_by_candidate() if use_frozen_bundles else {}

    def _authorized(candidate_id: str, candidate: dict[str, Any]) -> bool:
        if use_frozen_bundles:
            return candidate_id in bundles_by_candidate
        return classify_relation_family(candidate) != INVALID_PROVENANCE

    authorized_candidate_ids = sorted(
        cid for cid, candidate in candidates.items() if _authorized(cid, candidate)
    )

    matched: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = [
        {"candidate_id": cid, "reason_codes": ["INVALID_PROVENANCE"],
         "candidate_trace": {"candidate_id": cid, "matched": False,
                             "exclusion_reason": "INVALID_PROVENANCE"}}
        for cid, candidate in sorted(candidates.items())
        if not _authorized(cid, candidate)
    ]
    prepared_candidates: dict[str, dict[str, Any]] = {}
    for candidate_id in authorized_candidate_ids:
        candidate = candidates[candidate_id]
        if candidate_id in composed_source_ids:
            excluded.append({
                "candidate_id": candidate_id,
                "reason_codes": ["COMPOSED_IN_DERIVED_RELATION"],
                "candidate_trace": {"candidate_id": candidate_id, "matched": False,
                                    "exclusion_reason": "COMPOSED_IN_DERIVED_RELATION"},
            })
            continue
        if candidate_id in prefilter_excluded_ids:
            excluded.append({"candidate_id": candidate_id, "reason_codes": ["MOLECULAR_CONCEPT_INDEX_MISS"],
                             "candidate_trace": {"candidate_id": candidate_id, "matched": False,
                                                 "exclusion_reason": "MOLECULAR_CONCEPT_INDEX_MISS",
                                                 "normalization": {"version": terminology.registry().version,
                                                                   "query_gene_ids": sorted(query_gene_ids),
                                                                   "candidate_gene_ids": sorted(gene_index["candidate_genes"][candidate_id])}}})
            continue
        # Materialize retrieval-only trial context once and carry that
        # enriched view into the association payload.  The matcher/scorer may
        # inspect the same view, while canonical GCA semantic fields remain
        # untouched and the context is explicitly marked retrieval-only.
        prepared = candidate
        if classify_relation_family(candidate) == "CLINICAL_TRIAL" and candidate.get("source_properties") is not None and not candidate.get("trial_context"):
            prepared, _ = enrich_trial_candidate(candidate)
        prepared_candidates[candidate_id] = prepared
        ok, reasons = _match_candidate(case_context, prepared)
        ranking_score, ranking_features = _compatibility_score(case_context, prepared) if ok else (0, {})
        record = {"candidate_id": candidate_id, "semantic_key": candidate.get("semantic_key") or candidate_id,
                  "reason_codes": reasons,
                  "ranking_score": ranking_score, "ranking_features": ranking_features,
                  "specificity_order_key": _specificity_order_key(candidate_id, ranking_features),
                  "candidate_trace": {
                      "candidate_id": candidate_id,
                      "family": classify_relation_family(candidate),
                      "normalization": terminology.trace(case_context, prepared) if not use_frozen_bundles else {
                          "version": normalization.VERSION,
                          "query_diseases": [normalization.disease_identity(x) for x in _case_diseases(case_context)],
                          "candidate_diseases": [normalization.disease_identity(x.get("label")) for x in prepared.get("disease") or []],
                          "query_biomarkers": [{"gene": x.get("gene"), "alteration": normalization.alteration_identity(x.get("alteration"))} for x in _case_biomarkers(case_context)],
                          "candidate_biomarkers": [{"gene": x.get("gene"), "alteration": normalization.alteration_identity(x.get("alteration"))} for x in _candidate_biomarkers(prepared)],
                      },
                      "matched": ok,
                      "matched_fields": list(reasons) if ok else [],
                      "rejected_fields": [] if ok else list(reasons),
                      "exclusion_reason": None if ok else (reasons[-1] if reasons else "NO_MATCH"),
                      "specificity_level": "VARIANT" if any(x.get("specificity") == "VARIANT" for x in _candidate_biomarkers(prepared)) else "GENE_OR_GENERIC",
                  }}
        if ok:
            matched.append(record)
        else:
            excluded.append(record)

    matched.sort(key=lambda item: item["specificity_order_key"])
    matched = _group_matched_records(matched)
    if use_frozen_bundles:
        accepted = matched[:MAX_ASSOCIATIONS_PER_CASE]
        capped = matched[MAX_ASSOCIATIONS_PER_CASE:]
    else:
        accepted, capped = [], []
        family_counts: dict[str, int] = {}
        for item in matched:
            family = classify_relation_family(candidates[item["candidate_id"]])
            if MAX_ASSOCIATIONS_PER_FAMILY is None or family_counts.get(family, 0) < MAX_ASSOCIATIONS_PER_FAMILY:
                accepted.append(item)
                family_counts[family] = family_counts.get(family, 0) + 1
            else:
                capped.append(item)
    capped_out = [{"candidate_id": item["candidate_id"], "reason_codes": ["RELATION_FAMILY_CAP_EXCEEDED"],
                   "ranking_score": item["ranking_score"], "ranking_features": item["ranking_features"],
                   "specificity_order_key": item["specificity_order_key"]} for item in capped]

    associations = []
    for item in accepted:
        candidate_id = item["candidate_id"]
        group_ids = item.get("candidate_group_candidate_ids") or [candidate_id]
        candidate = dict(prepared_candidates.get(candidate_id, candidates[candidate_id]))
        candidate["candidate_group_candidate_ids"] = sorted(set(group_ids))
        candidate["member_semantic_identities"] = sorted({
            str(candidates[group_id].get("semantic_key") or group_id) for group_id in group_ids
        })
        for lineage_field in ("source_record_ids", "source_datasets", "edge_ids", "node_ids"):
            candidate[lineage_field] = list(dict.fromkeys(
                str(value) for group_id in group_ids
                for value in candidates[group_id].get(lineage_field) or [] if value
            ))
        candidate["group_graph_paths"] = [
            {"candidate_id": group_id, "graph_path": candidates[group_id].get("graph_path") or []}
            for group_id in sorted(set(group_ids))
        ]
        if use_frozen_bundles:
            bundles = sorted(
                [bundle for group_id in group_ids for bundle in bundles_by_candidate.get(group_id, [])],
                key=lambda b: b["bundle_id"],
            )
        else:
            bundles = [bundle for group_id in group_ids for bundle in _live_provenance_bundles(candidates[group_id])]
        associations.append({
            "candidate_id": candidate_id, "candidate": candidate,
            "candidate_group_candidate_ids": group_ids,
            "relation_family": classify_relation_family(candidate),
            "match_reason_codes": item["reason_codes"],
            "ranking_score": item["ranking_score"],
            "ranking_order_key": list(item["specificity_order_key"]),
            "ranking_features": item["ranking_features"],
            "retrieval_trace": item.get("candidate_trace"),
            "candidate_group_traces": item.get("candidate_group_traces", []),
            "available_bundles": [{"bundle_id": b["bundle_id"], "document_id": b["document_id"], "bundle_type": b.get("bundle_type"), "source_unit_ids": b.get("source_unit_ids", [])[:MAX_SOURCE_UNITS_PER_DOCUMENT], **({} if use_frozen_bundles else {"provenance_identifier": b["provenance_identifier"]})} for b in bundles],
        })

    family_accounting = {}
    for cid in authorized_candidate_ids:
        family = classify_relation_family(candidates[cid])
        counts = family_accounting.setdefault(family, {"eligible": 0, "matched": 0, "selected": 0, "capped": 0, "excluded_reasons": {}})
        counts["eligible"] += 1
    for collection, key in ((matched, "matched"), (accepted, "selected"), (capped, "capped")):
        for item in collection:
            family_accounting[classify_relation_family(candidates[item["candidate_id"]])][key] += 1
    for item in excluded + capped_out:
        family = classify_relation_family(candidates[item["candidate_id"]])
        counts = family_accounting.setdefault(family, {"eligible": 0, "matched": 0, "selected": 0, "capped": 0, "excluded_reasons": {}})
        for reason in item["reason_codes"]:
            counts["excluded_reasons"][reason] = counts["excluded_reasons"].get(reason, 0) + 1

    return {
        "query_intent": case_context.get("query_intent"),
        "associations": associations,
        "excluded_candidates": excluded + capped_out,
        "no_match": len(associations) == 0,
        "retrieval_summary": {
            "ranking_policy_version": RETRIEVAL_RANKING_VERSION,
            "gca4_source_candidate_count": source_candidate_count,
            "derived_composite_candidate_count": len(derived_candidates),
            "derivation_exclusions": derivation_exclusions,
            "matched_total": len(matched),
            "selected_total": len(associations),
            "cap_per_family": None if use_frozen_bundles else MAX_ASSOCIATIONS_PER_FAMILY,
            "historical_global_cap": MAX_ASSOCIATIONS_PER_CASE if use_frozen_bundles else None,
            "selected_by_family": {
                family: sum(1 for item in associations if item["relation_family"] == family)
                for family in sorted({item["relation_family"] for item in associations})
            },
            "anchor_trace": _retrieval_anchor_trace(case_context),
            "family_accounting": family_accounting,
            "candidate_index": {"mode": "EXHAUSTIVE" if exhaustive or use_frozen_bundles else "INDEXED",
                                "indexed_total": len(gene_index["candidate_genes"]),
                                "gene_key_count": len(gene_index["by_gene"]),
                                "prefilter_excluded": sum("MOLECULAR_CONCEPT_INDEX_MISS" in x["reason_codes"] for x in excluded)},
            "corpus_snapshot": None if use_frozen_bundles else runtime_corpus_snapshot().to_dict(),
        },
    }


@lru_cache(maxsize=1)
def _load_historical_candidates() -> dict[str, dict]:
    """Load v2 only for the explicitly named historical replay path."""
    return {
        row["candidate_id"]: row
        for row in (
            json.loads(line)
            for line in read_historical_candidate_corpus_utf8().splitlines()
            if line.strip()
        )
    }

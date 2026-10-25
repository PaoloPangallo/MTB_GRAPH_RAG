"""Small deterministic verifier for document-grounded GCA relations."""

from __future__ import annotations

import re
from typing import Any

from backend.research_pipeline.determinism.direction_semantics import (
    DOES_NOT_SUPPORT, SUPPORTS, compare_relation_axes, derive_expected_effect,
    derive_source_stance, normalize_observed_stance,
)
from .canonical_normalizer import entity_relation
from .proposition_assertion import assess_proposition_assertion, focus_main_clause, comparative_cohort_outcome
from ..terminology.surface import protein_keys
from .verification_policy import policy_for

VERIFIER_POLICY_VERSION = "paper-relation-verifier/5.2"

CONFIRMED = "CONFIRMED"
NOT_CONFIRMED = "NOT_CONFIRMED"
CONTRADICTORY = "CONTRADICTORY"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNKNOWN = "UNKNOWN"

FULL_SUPPORT = "FULL_SUPPORT"
PARTIAL_SUPPORT = "PARTIAL_SUPPORT"
NO_SUPPORT = "NO_SUPPORT"
UNVERIFIABLE = "UNVERIFIABLE"


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _labels(candidate: dict[str, Any], key: str, types: set[str] | None = None) -> list[str]:
    return [
        str(item["label"])
        for item in candidate.get(key) or []
        if item.get("label") and (types is None or _norm(item.get("type")) in types)
    ]


def _matches(expected: list[str], observed: Any, *, allow_hierarchy: bool = False, domain=None, gene_id=None) -> str:
    if not expected:
        return NOT_APPLICABLE
    values = observed if isinstance(observed, list) else [observed]
    if not any(_norm(value) for value in values):
        return NOT_CONFIRMED
    allowed = {"IDENTICAL", "CANONICAL_ALIAS"}
    if allow_hierarchy:
        allowed.update({"SOURCE_BROADER", "SOURCE_NARROWER"})
    return CONFIRMED if any(entity_relation(value, actual, domain=domain, gene_id=gene_id) in allowed
                            for value in expected for actual in values) else NOT_CONFIRMED


def _relation_values(observed: dict[str, Any], kind: str) -> list[str]:
    has_canonical_relation = "observed_relation" in observed and observed.get("observed_relation") is not None
    relation = observed.get("observed_relation") or {}
    if kind == "disease":
        return [relation.get("disease")] if has_canonical_relation else [observed.get("observed_disease")]
    if kind == "drug":
        return [relation.get("intervention")] if has_canonical_relation else [observed.get("observed_drug")]
    types = {"gene": {"GENE"}, "alteration": {"ALTERATION"}, "biomarker": {"GENE", "ALTERATION", "BIOMARKER"}}[kind]
    values = [item.get("surface_value") or item.get("value") or item.get("canonical_value")
              for item in relation.get("subjects") or []
              if isinstance(item, dict) and str(item.get("type") or "").upper() in types]
    if has_canonical_relation:
        return values
    return [observed.get({"gene": "observed_gene", "alteration": "observed_alteration"}.get(kind, ""))]


def _direction(candidate: dict[str, Any], observed: Any, observed_stance: Any = None) -> str:
    expected_stance = derive_source_stance(candidate)
    expected_effect = derive_expected_effect(candidate)
    if expected_stance == "UNKNOWN" and expected_effect == "UNKNOWN" and not _norm(candidate.get("direction")):
        return NOT_APPLICABLE
    comparison = compare_relation_axes(
        candidate.get("predicate"), expected_stance, expected_effect, observed, observed_stance,
    )
    if comparison == "CONSISTENT":
        return CONFIRMED
    if comparison == "CONFLICTING":
        return CONTRADICTORY
    return NOT_CONFIRMED


def _stance(candidate: dict[str, Any], observed: Any) -> str:
    """Compare source stance independently from clinical effect direction."""
    observed_stance = normalize_observed_stance(observed)
    expected = derive_source_stance(candidate)
    expected_effect = derive_expected_effect(candidate)
    if observed_stance in {"UNKNOWN", "NOT_APPLICABLE"}:
        return NOT_APPLICABLE
    if expected in {SUPPORTS, DOES_NOT_SUPPORT}:
        return CONFIRMED if observed_stance == expected else CONTRADICTORY
    # A candidate with an asserted clinical effect is positive by implication;
    # an explicit non-supporting source cannot be promoted by a matching effect.
    if expected_effect != "UNKNOWN" and observed_stance == DOES_NOT_SUPPORT:
        return CONTRADICTORY
    return NOT_APPLICABLE


def _assertion_state(observed: dict[str, Any]) -> str:
    relation = observed.get("observed_relation") or {}
    assertion = relation.get("relation_assertion")
    # Legacy fixtures predate the explicit field. They remain asserted only when
    # no source text is available; new Reader output is required to populate it.
    if assertion in {None, ""}:
        return "RELATION_ASSERTED"
    return str(assertion)


def _quoted_pair_present(clause: str, gene: str, alteration: str) -> bool:
    """Require a local gene–alteration pair, not two cross-paired mentions."""
    tokens = clause.split()
    def positions(phrase):
        words = phrase.split()
        return [(i, i + len(words)) for i in range(len(tokens) - len(words) + 1) if tokens[i:i+len(words)] == words]
    gene_positions = positions(gene)
    alteration_positions = positions(alteration)
    for gene_index in gene_positions:
        for alteration_index in alteration_positions:
            first, second = sorted((gene_index, alteration_index))
            if second[0] < first[1] or second[0] - first[1] > 3:
                continue
            between = tokens[first[1]:second[0]]
            if not any(re.fullmatch(r"[a-z]{1,3}\d+[a-z]{1,3}", token) for token in between):
                return True
    return False


def _candidate_gene_id(candidate):
    from backend.research_pipeline.terminology.matching import registry as current_registry
    genes = _labels(candidate, "biomarkers", {"gene"}) or sorted({str(x["gene"]) for x in candidate.get("biomarkers") or [] if x.get("gene")})
    resolved = current_registry().resolve("GENE", genes[0]) if len(genes) == 1 else None
    return resolved.concept_ids[0] if resolved and resolved.status == "RESOLVED" else None


def _source_labels(expected, observed, kind, domain, gene_id=None):
    values = _relation_values(observed, kind)
    matched = [str(value) for value in values if value and any(
        entity_relation(target, value, domain=domain, gene_id=gene_id) in {"IDENTICAL", "CANONICAL_ALIAS"} for target in expected)]
    return matched or expected


def _text_relation_state(
    source_text: str | None, observed: dict[str, Any], candidate: dict[str, Any],
) -> str:
    """Require a quoted, entity-anchored predicate cue independent of Reader labels."""
    if not source_text:
        return "RELATION_ASSERTED"
    relation = observed.get("observed_relation") or {}
    if relation.get("relation_assertion") == "ENTITY_CO_OCCURRENCE":
        return "ENTITY_CO_OCCURRENCE"
    source_genes = _labels(candidate, "biomarkers", {"gene"}) or sorted({
        str(item["gene"]) for item in candidate.get("biomarkers") or [] if item.get("gene")
    })
    genes = [_norm(value) for value in _source_labels(source_genes, observed, "gene", "GENE")]
    alterations = [_norm(value) for value in _source_labels(_labels(candidate, "biomarkers", {"variant", "alteration"}), observed, "alteration", "VARIANT", _candidate_gene_id(candidate))]
    drugs = [_norm(value) for value in _source_labels(_labels(candidate, "interventions"), observed, "drug", "INTERVENTION")]
    extra_variants = False
    if relation.get("relation_scope") == "SINGLE":
        observed_keys = set().union(*(protein_keys(str(v or "")) for v in _relation_values(observed, "alteration")))
        extra_variants = bool(observed_keys and protein_keys(source_text) - observed_keys)

    def mentions(clause: str, labels: list[str]) -> bool:
        return not labels or any(
            re.search(rf"\b{re.escape(label)}\b", clause) for label in labels
        )

    negative = re.compile(
        r"\b(?:did|does|do|was|were|is|are) not (?:\w+ ){0,3}"
        r"(?:predict|associate|associated|correlate|correlated|support|respond|sensitive|resistant)\b"
        r"|\bno (?:\w+ ){0,3}(?:response|association|sensitivity|benefit)\b"
        r"|\bfailed to respond\b|\black of (?:response|association)\b"
    )
    therapy = re.compile(
        r"\b(?:showed|demonstrated|exhibited|displayed|confirmed) (?:\w+ ){0,3}"
        r"(?:sensitivity|response|resistance) to\b"
        r"|\b(?:sensitive|resistant|responsive) to\b"
        r"|\b(?:associated|correlated|linked) with (?:\w+ ){0,3}"
        r"(?:response|sensitivity|resistance|benefit)\b"
        r"|\b(?:predicts?|predicted) (?:\w+ ){0,3}"
        r"(?:response|sensitivity|resistance|benefit)\b"
        r"|\b(?:responded|responds) to\b"
        r"|\b(?:confers?|conferred) (?:\w+ ){0,2}(?:sensitivity|resistance)\b"
    )
    molecular = re.compile(
        r"\b(?:associated|correlated|linked) with\b"
        r"|\b(?:predicts?|predicted|confers?|conferred)\b"
        r"|\b(?:increases?|decreases?) (?:\w+ ){0,2}(?:risk|survival)\b"
    )
    drug_pattern = "|".join(re.escape(drug) for drug in drugs if drug)
    target_effect = re.compile(
        rf"\b(?:response|sensitivity|resistance|responded|responds|sensitive|resistant|responsive)\s+to\s+"
        rf"(?:the\s+)?(?:{drug_pattern})\b"
        rf"|\b(?:{drug_pattern})\s+(?:response|sensitivity|resistance)\b"
    ) if drug_pattern else None
    negative_target = re.compile(
        rf"\b(?:did|does|do|was|were|is|are)\s+not\s+(?:\w+\s+){{0,5}}"
        rf"(?:response|sensitivity|resistance|respond|responded|responds|sensitive|resistant|responsive)\s+to\s+"
        rf"(?:the\s+)?(?:{drug_pattern})\b"
        rf"|\bno\s+(?:\w+\s+){{0,3}}(?:response|sensitivity|resistance|benefit)\s+to\s+"
        rf"(?:the\s+)?(?:{drug_pattern})\b"
        rf"|\b(?:failed\s+to\s+respond|lack\s+of\s+response)\s+to\s+"
        rf"(?:the\s+)?(?:{drug_pattern})\b"
    ) if drug_pattern else None
    states: set[str] = set()
    for raw_clause in re.split(r"[!?;]+|\.(?=\s|$)|\n+", source_text):
        clause = _norm(raw_clause)
        if not clause or not all(
            mentions(clause, labels) for labels in (genes, alterations, drugs)
        ):
            continue
        if len(genes) == 1 and len(alterations) == 1 and not _quoted_pair_present(
            clause, genes[0], alterations[0]
        ):
            continue
        if len(genes) == 1 and len(alterations) == 1 and re.search(
            rf"\b(?:not|except|excluding)\s+(?:the\s+)?"
            rf"{re.escape(genes[0])}\s+{re.escape(alterations[0])}\b",
            clause,
        ):
            if not drugs and re.search(r"\bresulted in\b.*\bsurvival\b.*\bin (?:patients|participants) with\b", clause):
                # An excluded cohort member is not a negative efficacy claim
                # about that member. No relation has been established for it.
                states.add("UNCERTAIN_RELATION")
                continue
            states.add("RELATION_NEGATED")
            continue
        if extra_variants:
            states.add("MIXED_RELATIONS")
            continue
        if re.search(
            r"\b(?:may|might|could|possibly|potentially|possibility|whether|if|"
            r"hypothesis|hypothesized|unclear|unknown|retracted|unconfirmed|"
            r"disputed|refuted)\b|\bnot replicated\b",
            clause,
        ):
            states.add("UNCERTAIN_RELATION")
            continue
        if re.search(r"\bbut not in (?:the )?(?:overall|whole|entire) (?:cohort|population|group)\b", clause):
            states.add("MIXED_RELATIONS")
            continue
        drug_relation = bool(target_effect and target_effect.search(clause)) if drugs else True
        if re.search(
            r"\bno evidence (?:that|of|for)\b"
            r"|\bno (?:tumors?|patients?|cells?|models?|samples?)\b",
            clause,
        ) or (
            negative_target.search(clause) if drugs else negative.search(clause)
        ):
            states.add("RELATION_NEGATED")
        elif drug_relation and (
            any(
                cue.start() < target.end() and target.start() < cue.end()
                for cue in therapy.finditer(clause)
                for target in target_effect.finditer(clause)
            ) if drugs else molecular.search(clause)
        ):
            states.add("RELATION_ASSERTED")
    if len(states) > 1:
        return "MIXED_RELATIONS"
    if not states and not drugs:
        intervention = str((observed.get("observed_relation") or {}).get("intervention") or "")
        if comparative_cohort_outcome(source_text, intervention, tuple(genes + alterations),
                                      str((observed.get("observed_relation") or {}).get("disease") or "")):
            return "RELATION_ASSERTED"
    return next(iter(states), "ENTITY_CO_OCCURRENCE")


def _quote_disease_mismatch(
    candidate: dict[str, Any], observed: dict[str, Any], source_text: str | None,
) -> bool:
    """Reject an explicit other disease or a Reader disease absent from the quote."""
    if not source_text:
        return False
    expected = [_norm(value) for value in _source_labels(_labels(candidate, "disease"), observed, "disease", "DISEASE")]
    if not expected:
        return False
    text = _norm(source_text)
    reported = [_norm(value) for value in _relation_values(observed, "disease") if _norm(value)]

    def mentioned(value: str) -> bool:
        for match in re.finditer(rf"\b{re.escape(value)}\b", text):
            prefix = text[:match.start()].split()
            # A disease name nested as the suffix of a more specific,
            # incompatible phrase is not an identity match.
            if prefix and prefix[-1] == "non" and value.startswith("small cell "):
                continue
            if value == "lung cancer" and prefix[-3:] in (
                ["non", "small", "cell"], ["small", "cell"],
            ):
                continue
            return True
        return False

    if reported and not any(mentioned(value) for value in reported):
        return True
    disease_phrase = re.search(r"\b(?:[a-z0-9]+ ){0,3}(?:cancer|carcinoma|melanoma|leukemia|lymphoma|sarcoma)\b", text)
    return bool(disease_phrase and not any(
        mentioned(value) for value in expected
    ))


def _quoted_drug_effect(source_text: str | None, candidate: dict[str, Any]) -> str:
    """Check explicit target-drug effect independently from the Reader axis."""
    if not source_text:
        return "UNKNOWN"
    text = _norm(source_text)
    effects: set[str] = set()
    for drug in (_norm(value) for value in _labels(candidate, "interventions")):
        if not drug:
            continue
        target = rf"(?:the )?{re.escape(drug)}\b"
        if re.search(rf"\b(?:resistance|resistant) to {target}|\b{re.escape(drug)} resistance\b", text):
            effects.add("RESISTANCE")
        if re.search(rf"\breduced sensitivity to {target}|\b{re.escape(drug)} reduced sensitivity\b", text):
            effects.add("REDUCED_SENSITIVITY")
        if re.search(rf"\b(?:sensitivity|sensitive|response|responsive) to {target}|\b{re.escape(drug)} (?:sensitivity|response)\b", text):
            effects.add("SENSITIVITY_RESPONSE")
    return next(iter(effects)) if len(effects) == 1 else "MIXED" if effects else "UNKNOWN"


def _pairing_state(candidate: dict[str, Any], observed: dict[str, Any]) -> str:
    relation = observed.get("observed_relation") or {}
    expected_pairs = set()
    biomarkers = candidate.get("biomarkers") or []
    genes = [str(item.get("label")) for item in biomarkers if str(item.get("type") or "").casefold() == "gene" and item.get("label")]
    genes = genes or sorted({str(item["gene"]) for item in biomarkers if item.get("gene")})
    variants = [str(item.get("label")) for item in biomarkers if str(item.get("type") or "").casefold() in {"variant", "alteration"} and item.get("label")]
    if len(genes) == 1 and len(variants) == 1:
        expected_pairs.add((genes[0], variants[0]))
    if not expected_pairs:
        return "LEGACY"
    actual_pairs = {
        (str(item.get("gene") or ""), str(item.get("alteration") or ""))
        for item in relation.get("subject_pairings") or []
        if isinstance(item, dict)
    }
    if not actual_pairs:
        return "UNKNOWN"
    gene_id = _candidate_gene_id(candidate)
    return "EXACT" if all(any(entity_relation(g, actual_g, domain="GENE") in {"IDENTICAL", "CANONICAL_ALIAS"}
                              and entity_relation(v, actual_v, domain="VARIANT", gene_id=gene_id) in {"IDENTICAL", "CANONICAL_ALIAS"}
                              for actual_g, actual_v in actual_pairs) for g, v in expected_pairs) else "DIFFERENT"


def _composition_state(candidate: dict[str, Any], observed: dict[str, Any]) -> str:
    relation = observed.get("observed_relation")
    if relation is None:
        return "LEGACY"
    scope = str(relation.get("relation_scope") or "UNKNOWN")
    subjects = relation.get("subjects") or []
    expected_genes = _labels(candidate, "biomarkers", {"gene"}) or sorted({str(item["gene"]) for item in candidate.get("biomarkers") or [] if item.get("gene")})
    expected_variants = _labels(candidate, "biomarkers", {"variant", "alteration"})
    expected = expected_genes + expected_variants
    values = {_norm(item.get("surface_value") or item.get("value") or item.get("canonical_value"))
              for item in subjects if isinstance(item, dict)}
    expected_values = {_norm(value) for value in expected}
    if scope == "UNKNOWN" or scope == 'ALTERNATIVES' or relation.get('molecular_composition') == 'ALTERNATIVES':
        return "UNKNOWN"
    gene_state = _matches(expected_genes, _relation_values(observed, "gene"), domain="GENE")
    variant_state = _matches(expected_variants, _relation_values(observed, "alteration"), domain="VARIANT", gene_id=_candidate_gene_id(candidate))
    if not expected_values or gene_state not in {CONFIRMED, NOT_APPLICABLE} or variant_state not in {CONFIRMED, NOT_APPLICABLE}:
        return "DIFFERENT"
    if scope != "SINGLE" and len(values) > len(expected_values):
        return "COMPOSITE_MISMATCH"
    return "EXACT"


def _evidence_context_state(candidate: dict[str, Any], observed: dict[str, Any]) -> str:
    relation = observed.get("observed_relation") or {}
    context = relation.get("evidence_context")
    if context is None:
        return "LEGACY"
    scope = _norm(candidate.get("evidence_scope") or candidate.get("diagnostic_scope"))
    level = str(context.get("subject_level") or "UNKNOWN")
    claim = str(context.get("claim_type") or "UNKNOWN")
    if level == "UNKNOWN" or claim == "UNKNOWN":
        return "UNKNOWN"
    if scope == "predictive" and (level == "INDIVIDUAL" and claim == "OBSERVED_RESPONSE"):
        return "INSUFFICIENT_GENERALIZATION"
    compatible = {
        "functional": {("CELL_MODEL", "FUNCTIONAL_EFFECT"), ("ANIMAL_MODEL", "FUNCTIONAL_EFFECT")},
        "prognostic": {("COHORT", "PROGNOSTIC_ASSOCIATION"), ("POPULATION", "PROGNOSTIC_ASSOCIATION")},
        "diagnostic": {("COHORT", "DIAGNOSTIC_ASSOCIATION"), ("POPULATION", "DIAGNOSTIC_ASSOCIATION")},
        "predictive": {("COHORT", "PREDICTIVE_ASSOCIATION"), ("POPULATION", "PREDICTIVE_ASSOCIATION"), ("CELL_MODEL", "FUNCTIONAL_EFFECT")},
    }
    return "EXACT" if (level, claim) in compatible.get(scope, set()) else "UNKNOWN"


def assess_relation_support(
    candidate: dict[str, Any], observed: dict[str, Any], *,
    source_unit_text: str | None = None,
) -> dict[str, Any]:
    """Compare a validated Reader observation with the target GCA relation.

    Contextual dimensions are kept visible but do not automatically become
    required relation dimensions.  Support requires an asserted relation;
    isolated co-mentions cannot produce PARTIAL_SUPPORT.
    """
    from .phenotype_identity import source_phenotype, phenotype_correspondence, phenotype_population_scope
    phenotype = source_phenotype(candidate)
    relation_policy = (candidate.get("source_properties") or {}).get("relation_contract") or {}
    has_disease = bool(_labels(candidate, "disease"))
    disease_policy = (
        "NOT_APPLICABLE" if not has_disease else
        "REQUIRED" if candidate.get("disease_required") is True
        or relation_policy.get("disease_required") is True else "OPTIONAL"
    )
    if observed.get("decision") != "QUOTE":
        return {
            "fields": {}, "applicable": [], "central": [], "required": [],
            "disease_policy": disease_policy,
            "text_assertion": "NO_RELATION",
            "text_assertion_reason": "READER_OBSERVATION_NOT_ADMITTED",
            "predicates": {
                "observation_valid": False, "relation_anchored": False,
                "relation_compatible": False, "relation_full_specificity": False,
            },
            "result": UNVERIFIABLE, "reason": "READER_OBSERVATION_NOT_ADMITTED",
            "verification_policy": policy_for(candidate).to_dict(),
        }

    from backend.research_pipeline.terminology.matching import registry as current_registry
    genes = _labels(candidate, "biomarkers", {"gene"}) or sorted({str(x["gene"]) for x in candidate.get("biomarkers") or [] if x.get("gene")})
    linked_gene = current_registry().resolve("GENE", genes[0]) if len(genes) == 1 else None
    gene_id = linked_gene.concept_ids[0] if linked_gene and linked_gene.status == "RESOLVED" else None
    fields = {
        "disease": _matches(_labels(candidate, "disease"), _relation_values(observed, "disease"), domain="DISEASE"),
        "gene": _matches(genes, _relation_values(observed, "gene"), domain="GENE"),
        "alteration": _matches(
            _labels(candidate, "biomarkers", {"variant", "alteration"}),
            _relation_values(observed, "alteration"), domain="VARIANT", gene_id=gene_id,
        ),
        "drug": _matches(_labels(candidate, "interventions"), _relation_values(observed, "drug"), domain="INTERVENTION"),
        "direction": _direction(
            candidate,
            ((observed.get("observed_relation") or {}).get("effect_direction")
             if observed.get("observed_relation") is not None else observed.get("observed_direction")),
            (observed.get("observed_relation") or {}).get("observed_stance"),
        ),
    }
    fields["stance"] = _stance(
        candidate,
        (observed.get("observed_relation") or {}).get("observed_stance"),
    )
    phenotype_scope = None
    if phenotype:
        fields['phenotype'] = phenotype_correspondence(phenotype, observed, source_unit_text or '')
        phenotype_scope = phenotype_population_scope(source_unit_text or '')
    composition = _composition_state(candidate, observed)
    pairing = _pairing_state(candidate, observed)
    evidence_context = _evidence_context_state(candidate, observed)
    if evidence_context == "EXACT":
        fields["evidence_context"] = CONFIRMED
    elif relation_policy.get("evidence_context_required") is True:
        fields["evidence_context"] = NOT_CONFIRMED

    # Preserve the historical shape for ordinary gene/variant targets.
    if phenotype is None and (((candidate.get('entity_resolution') or {}).get('profile') or {}).get('ast') or {}).get('op') == 'PHENOTYPE':
        fields['phenotype'] = UNKNOWN
    applicable_names = [name for name, value in fields.items() if value != NOT_APPLICABLE]
    central_names = [name for name in ("gene", "alteration", "drug", "direction", "phenotype")
                     if fields.get(name, NOT_APPLICABLE) != NOT_APPLICABLE]
    required_names = list(central_names)
    if disease_policy == "REQUIRED":
        if fields.get("disease") != NOT_APPLICABLE:
            required_names.append("disease")
    if relation_policy.get("evidence_context_required") is True:
        required_names.append("evidence_context")

    # V3 observations carry an explicit relation object.  Legacy Reader
    # payloads carry scalar observed_* fields; they are still an asserted
    # relation, but cannot establish full specificity.
    legacy_relation = observed.get("observed_relation") is None and bool(
        str(observed.get("observed_evidence_type") or "").strip()
    ) and any(
        str(observed.get(key) or "").strip()
        for key in ("observed_gene", "observed_alteration", "observed_drug", "observed_direction")
    )
    relation_present = isinstance(observed.get("observed_relation"), dict) or legacy_relation
    assertion = _assertion_state(observed)
    focused_text = focus_main_clause(source_unit_text or "")
    relation_text = focused_text or source_unit_text
    if source_unit_text and focused_text != source_unit_text and re.match(r"^but\s+", focused_text, re.I):
        # Coordinate VP ellipsis: ``EGFR L858R ... gefitinib, but showed
        # sensitivity to erlotinib`` keeps the same molecular subject. Carry
        # it only when the preceding clause contains one unambiguous pair.
        prefix = source_unit_text.split(",", 1)[0]
        genes = _labels(candidate, "biomarkers", {"gene"})
        alterations = _labels(candidate, "biomarkers", {"variant", "alteration"})
        variant_like = re.findall(r"\b[A-Za-z]\d+[A-Za-z]\b", prefix)
        if (len(genes) == len(alterations) == 1
                and len(variant_like) == 1
                and _norm(variant_like[0]) == _norm(alterations[0])
                and re.match(rf"^{re.escape(_norm(genes[0]))}\s+{re.escape(_norm(alterations[0]))}\b", _norm(prefix))
                and _quoted_pair_present(_norm(prefix), _norm(genes[0]), _norm(alterations[0]))):
            relation_text = f"{genes[0]} {alterations[0]} {focused_text}"
    text_relation = _text_relation_state(relation_text, observed, candidate)
    # The assertion gate still operates on the unchanged quote. Replace only
    # entity label representations with already verified source aliases; do
    # not substitute source text, qualifiers, predicates or polarity.
    assertion_candidate = dict(candidate)
    assertion_candidate["_grounded_intervention"] = str((observed.get("observed_relation") or {}).get("intervention") or "")
    assertion_candidate["_grounded_disease"] = str((observed.get("observed_relation") or {}).get("disease") or "")
    gene_id = _candidate_gene_id(candidate)
    assertion_candidate["biomarkers"] = []
    # The overlay carries the gene on the variant from the audited source edge.
    # Reuse that anchor in assertion checking as in identity checking.
    if not _labels(candidate, "biomarkers", {"gene"}):
        assertion_candidate["biomarkers"].extend({"type": "Gene", "label": gene} for gene in genes)
    for item in candidate.get("biomarkers") or []:
        kind = str(item.get("type") or "").casefold()
        domain, field = ("GENE", "gene") if kind == "gene" else ("VARIANT", "alteration")
        labels = _source_labels([str(item.get("label") or "")], observed, field, domain, gene_id if domain == "VARIANT" else None)
        assertion_candidate["biomarkers"].append({**item, "label": labels[0]} if len(labels) == 1 else item)
    assertion_candidate["interventions"] = []
    for item in candidate.get("interventions") or []:
        labels = _source_labels([str(item.get("label") or "")], observed, "drug", "INTERVENTION")
        assertion_candidate["interventions"].append({**item, "label": labels[0]} if len(labels) == 1 else item)
    text_assertion = assess_proposition_assertion(source_unit_text, assertion_candidate, text_relation)
    assertion_compatible = (
        (text_assertion.state == "DIRECT_ASSERTION"
         and assertion == "RELATION_ASSERTED" and text_relation == "RELATION_ASSERTED")
        or (text_assertion.state == "DIRECT_NEGATIVE_ASSERTION"
            and assertion in {"RELATION_ASSERTED", "RELATION_NEGATED"}
            and text_relation == "RELATION_NEGATED")
    )
    if not assertion_compatible:
        relation_present = False
    confirmed_central = [name for name in central_names if fields.get(name) == CONFIRMED]
    subject_confirmed = any(fields.get(name) == CONFIRMED for name in ("gene", "alteration", "phenotype"))
    drug_satisfied = fields.get("drug") in {CONFIRMED, NOT_APPLICABLE}
    direction_comparable = fields.get("direction") in {
        CONFIRMED, NOT_CONFIRMED, CONTRADICTORY, NOT_APPLICABLE,
    }
    relation_anchored = bool(
        relation_present and subject_confirmed and drug_satisfied and direction_comparable
        and len(confirmed_central) >= 2
    )
    contradictory_required = [name for name in required_names if fields.get(name) == CONTRADICTORY]
    critical_conflicts = [name for name in ("stance", "direction") if fields.get(name) == CONTRADICTORY]
    observed_disease = _relation_values(observed, "disease")
    from ..terminology.case_resolution import compare_disease_context
    disease_resolution = [compare_disease_context(target, str(value), current_registry())
                          for target in _labels(candidate, "disease")
                          for value in observed_disease if value]
    context_unresolved = any(item["relation"] == "SAME_CONCEPT_CONTEXT_UNRESOLVED"
                             for item in disease_resolution)
    disease_mismatch = bool(
        has_disease
        and any(_norm(value) for value in observed_disease)
        and fields["disease"] != CONFIRMED and not context_unresolved
        and disease_resolution
        and all(item.get("classification") == "MISMATCH" for item in disease_resolution)
    ) or _quote_disease_mismatch(candidate, observed, source_unit_text)
    expected_stance = derive_source_stance(candidate)
    text_contrary = (
        (text_relation == "RELATION_NEGATED" and expected_stance == SUPPORTS)
        or (text_relation == "RELATION_ASSERTED" and expected_stance == DOES_NOT_SUPPORT)
    )
    quoted_effect = _quoted_drug_effect(source_unit_text, candidate)
    expected_effect = derive_expected_effect(candidate)
    text_effect_contrary = (
        quoted_effect not in {"UNKNOWN", "MIXED"}
        and expected_effect != "UNKNOWN" and quoted_effect != expected_effect
    )
    relation_compatible = (
        relation_anchored and not contradictory_required
        and not critical_conflicts and not text_contrary and not text_effect_contrary
    )
    relation_full = (
        relation_compatible
        # Identity correspondence never proves a phenotype-specific effect.
        # No subgroup effect is established by this literal scope audit.
        and phenotype is None
        and not context_unresolved
        and not legacy_relation
        and composition in {"LEGACY", "EXACT"}
        and pairing in {"LEGACY", "EXACT"}
        and assertion_compatible
        and text_relation in {"RELATION_ASSERTED", "RELATION_NEGATED"}
        and all(fields.get(name) == CONFIRMED for name in required_names)
    )

    if disease_mismatch:
        overall, reason = NO_SUPPORT, "DISEASE_CONTEXT_INCOMPATIBLE"
    elif not central_names:
        overall, reason = UNVERIFIABLE, "CANDIDATE_HAS_NO_VERIFIABLE_RELATION_CORE"
    elif (contradictory_required or critical_conflicts or text_contrary or text_effect_contrary) and relation_anchored:
        overall, reason = CONTRADICTORY, "ANCHORED_RELATION_CONTRADICTS_REQUIRED_DIMENSION"
    elif context_unresolved and relation_compatible:
        overall, reason = PARTIAL_SUPPORT, "DISEASE_CONTEXT_SCOPE_UNRESOLVED"
    elif relation_full:
        overall, reason = FULL_SUPPORT, "REQUIRED_RELATION_DIMENSIONS_CONFIRMED"
    elif relation_compatible:
        overall, reason = PARTIAL_SUPPORT, "COMPATIBLE_RELATION_MISSING_REQUIRED_SPECIFICITY"
    else:
        overall, reason = NO_SUPPORT, "NO_COMPATIBLE_ASSERTED_RELATION"

    return {
        "fields": fields,
        **({'phenotype': phenotype, 'phenotype_scope': phenotype_scope} if phenotype else {}),
        "disease_policy": disease_policy,
        "disease_resolution": disease_resolution,
        "applicable": applicable_names,
        "central": central_names,
        "required": required_names,
        "predicates": {
            "observation_valid": True,
            "relation_anchored": relation_anchored,
            "relation_compatible": relation_compatible,
            "relation_full_specificity": relation_full,
        },
        "relation_composition": composition,
        "relation_assertion": assertion,
        "text_assertion": text_assertion.state,
        "text_assertion_reason": text_assertion.reason,
        "relation_text_state": text_relation,
        "pairing": pairing,
        "caveats": list((observed.get("observed_relation") or {}).get("caveats") or []),
        "uncertainty": (observed.get("observed_relation") or {}).get("uncertainty"),
        "conflict_markers": list((observed.get("observed_relation") or {}).get("conflict_markers") or []),
        "evidence_context": evidence_context,
        "result": overall,
        "reason": reason,
        "verification_policy": policy_for(candidate).to_dict(),
    }

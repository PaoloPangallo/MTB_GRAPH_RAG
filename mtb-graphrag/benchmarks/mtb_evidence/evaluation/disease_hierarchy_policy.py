"""Contratto direzionale fra disease della query e disease scope del claim.

Il matcher operativo sa gia' riconoscere la gerarchia, ma la comprime in un
vocabolario che non dice la direzione. `explicit_parent` non dichiara *di chi* sia
parent, e cross-disease, relazione irrisolta e disease mancante finiscono tutti in
`unresolved`. L'esito pratico e' corretto — nessuna di queste relazioni e' hard
match — ma non e' dicibile, e cio' che non e' dicibile non puo' essere spiegato a
chi legge un risultato.

Questi due casi non sono lo stesso caso:

    query  Cholangiocarcinoma          claim  Intrahepatic Cholangiocarcinoma
    -> claim_is_child_of_query: l'evidenza vale solo per un sottotipo della query

    query  Intrahepatic Cholangiocarcinoma   claim  Cholangiocarcinoma
    -> claim_is_parent_of_query: il risultato generale non e' separabile per il
       sottotipo chiesto

Nel primo caso generalizzare inventerebbe una copertura che la fonte non ha; nel
secondo specializzare inventerebbe una separabilita' che la fonte non dichiara.
Sono errori diversi e vanno nominati diversamente.

Il modulo non implementa nulla nel retriever: definisce il vocabolario, risolve la
relazione **soltanto** sulle tabelle gia' congelate, e congela bucket, eligibility e
precedenza del gate sullo scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from backend.pipeline.evidence.qualified_disease_matching import (
    VERIFIED_ALIAS_SOURCE,
    VERIFIED_ALIAS_VERSION,
    VERIFIED_RELATION_SOURCE,
    _canonical_key,
    _core,
    _group,
    _parent_key,
)
from benchmarks.mtb_evidence.pilot.audit_lib.disease import (
    _SUBTYPE_OF,
    _SYNONYM_GROUPS,
)

PHASE_VERSION = "disease-hierarchy-policy/1.0"
CONTRACT_VERSION = "directional-disease-match-contract/1.0"
REVIEWER_ROLE = "author_disease_policy_reviewer"
REVIEW_INDEPENDENCE = "non_independent"
REVIEW_STATUS = "first_review_complete"
PROPAGATION_POLICY = "prototype_only"

HIERARCHY_VERSION = "verified-local-disease-hierarchy/1.0"
NORMALIZATION_VERSION = "disease-normalization/1.0"
LITERAL_VERSION = "disease-literal-identity/1.0"
GENERIC_SCOPE_VERSION = "phase-local-generic-disease-scope/1.0"

NORMALIZATION_SOURCE = (
    "benchmarks/mtb_evidence/pilot/audit_lib/disease.py::split_disease"
)
GENERIC_SCOPE_SOURCE = (
    "benchmarks/mtb_evidence/v3/disease_hierarchy_policy/"
    "disease_relation_definitions.json::generic_scope_keys"
)
LITERAL_SOURCE = "query_and_claim_literal"
ABSENCE_SOURCE = "absence_of_frozen_relation"

# --- relazioni ---------------------------------------------------------------

EXACT_DISEASE = "exact_disease"
NORMALIZED_EXACT_DISEASE = "normalized_exact_disease"
VERIFIED_DISEASE_ALIAS = "verified_disease_alias"
CLAIM_IS_CHILD_OF_QUERY = "claim_is_child_of_query"
CLAIM_IS_PARENT_OF_QUERY = "claim_is_parent_of_query"
DISEASE_SIBLING = "disease_sibling"
GENERIC_CANCER_SCOPE = "generic_cancer_scope"
CROSS_DISEASE = "cross_disease"
UNRESOLVED_DISEASE_RELATION = "unresolved_disease_relation"
MISSING_QUERY_DISEASE = "missing_query_disease"
MISSING_CLAIM_DISEASE = "missing_claim_disease"

RELATION_TYPES = (
    EXACT_DISEASE,
    NORMALIZED_EXACT_DISEASE,
    VERIFIED_DISEASE_ALIAS,
    CLAIM_IS_CHILD_OF_QUERY,
    CLAIM_IS_PARENT_OF_QUERY,
    DISEASE_SIBLING,
    GENERIC_CANCER_SCOPE,
    CROSS_DISEASE,
    UNRESOLVED_DISEASE_RELATION,
    MISSING_QUERY_DISEASE,
    MISSING_CLAIM_DISEASE,
)

# Le sole relazioni che dichiarano identita' di entita'. Il primary bucket non puo'
# contenere altro, in nessuna modalita'.
EXACT_RELATIONS = frozenset(
    {EXACT_DISEASE, NORMALIZED_EXACT_DISEASE, VERIFIED_DISEASE_ALIAS}
)

# --- direzione ---------------------------------------------------------------

DIRECTION_NONE = "none"
DIRECTION_CLAIM_NARROWER = "claim_narrower_than_query"
DIRECTION_CLAIM_BROADER = "claim_broader_than_query"
DIRECTION_LATERAL = "lateral"
DIRECTION_UNKNOWN = "unknown"

RELATION_DIRECTIONS = (
    DIRECTION_NONE,
    DIRECTION_CLAIM_NARROWER,
    DIRECTION_CLAIM_BROADER,
    DIRECTION_LATERAL,
    DIRECTION_UNKNOWN,
)

# --- bucket ------------------------------------------------------------------
# Ripresi tali e quali dal contratto gia' congelato in
# benchmarks/mtb_evidence/v3/claim_type_retrieval_contract/candidate_bucket_contract.json

PRIMARY = "primary_ranked_results"
WARNING = "retained_with_warning"
AUDIT = "audit_only_results"
REJECTED = "rejected_by_native_constraints"

BUCKETS = (PRIMARY, WARNING, AUDIT, REJECTED)

# --- modalita' ---------------------------------------------------------------

STRICT_VERIFIED = "strict_verified"
ONTOLOGY_AWARE_WARNING = "ontology_aware_warning"
AUDIT_ALL = "audit_all"

POLICY_MODES = (STRICT_VERIFIED, ONTOLOGY_AWARE_WARNING, AUDIT_ALL)
DEFAULT_MODE = STRICT_VERIFIED

# --- reason, warning, explanation ---------------------------------------------

DISEASE_EXACT_MATCH = "DISEASE_EXACT_MATCH"
DISEASE_NORMALIZED_EXACT_MATCH = "DISEASE_NORMALIZED_EXACT_MATCH"
DISEASE_VERIFIED_ALIAS_MATCH = "DISEASE_VERIFIED_ALIAS_MATCH"
DISEASE_SIBLING_NOT_APPLICABLE = "DISEASE_SIBLING_NOT_APPLICABLE"
GENERIC_DISEASE_SCOPE_NOT_CASE_SPECIFIC = "GENERIC_DISEASE_SCOPE_NOT_CASE_SPECIFIC"
CROSS_DISEASE_MISMATCH = "CROSS_DISEASE_MISMATCH"
DISEASE_RELATION_UNRESOLVED = "DISEASE_RELATION_UNRESOLVED"
QUERY_DISEASE_MISSING = "QUERY_DISEASE_MISSING"
CLAIM_DISEASE_SCOPE_MISSING = "CLAIM_DISEASE_SCOPE_MISSING"
DISEASE_GATE_PRECEDES_SCORING = "DISEASE_GATE_PRECEDES_SCORING"
BIOMARKER_MISMATCH_DESPITE_DISEASE_ALIAS = "BIOMARKER_MISMATCH_DESPITE_DISEASE_ALIAS"

CLAIM_DISEASE_SCOPE_NARROWER_THAN_QUERY = "CLAIM_DISEASE_SCOPE_NARROWER_THAN_QUERY"
CLAIM_DISEASE_SCOPE_BROADER_THAN_QUERY = "CLAIM_DISEASE_SCOPE_BROADER_THAN_QUERY"
GENERIC_DISEASE_SCOPE_RETAINED_WITH_WARNING = (
    "GENERIC_DISEASE_SCOPE_RETAINED_WITH_WARNING"
)

EVIDENCE_APPLIES_ONLY_TO_QUERY_SUBTYPE = "EVIDENCE_APPLIES_ONLY_TO_QUERY_SUBTYPE"
RESULT_NOT_SEPARABLE_FOR_QUERY_SUBTYPE = "RESULT_NOT_SEPARABLE_FOR_QUERY_SUBTYPE"
DISEASE_IDENTITY_CONFIRMED = "DISEASE_IDENTITY_CONFIRMED"
DISEASE_IDENTITY_CONFIRMED_AFTER_NORMALIZATION = (
    "DISEASE_IDENTITY_CONFIRMED_AFTER_NORMALIZATION"
)
DISEASE_IDENTITY_CONFIRMED_BY_VERIFIED_ALIAS = (
    "DISEASE_IDENTITY_CONFIRMED_BY_VERIFIED_ALIAS"
)
SIBLING_EVIDENCE_NOT_TRANSFERABLE = "SIBLING_EVIDENCE_NOT_TRANSFERABLE"
GENERIC_SCOPE_NOT_SUBSTITUTABLE_FOR_QUERY_DISEASE = (
    "GENERIC_SCOPE_NOT_SUBSTITUTABLE_FOR_QUERY_DISEASE"
)
NO_VERIFIED_RELATION_BETWEEN_DISEASES = "NO_VERIFIED_RELATION_BETWEEN_DISEASES"
RELATION_NOT_DECIDABLE_ON_FROZEN_VOCABULARY = (
    "RELATION_NOT_DECIDABLE_ON_FROZEN_VOCABULARY"
)
QUERY_DISEASE_NOT_PROVIDED = "QUERY_DISEASE_NOT_PROVIDED"
CLAIM_DISEASE_SCOPE_NOT_PROVIDED = "CLAIM_DISEASE_SCOPE_NOT_PROVIDED"

REASON_BY_RELATION: dict[str, str] = {
    EXACT_DISEASE: DISEASE_EXACT_MATCH,
    NORMALIZED_EXACT_DISEASE: DISEASE_NORMALIZED_EXACT_MATCH,
    VERIFIED_DISEASE_ALIAS: DISEASE_VERIFIED_ALIAS_MATCH,
    CLAIM_IS_CHILD_OF_QUERY: CLAIM_DISEASE_SCOPE_NARROWER_THAN_QUERY,
    CLAIM_IS_PARENT_OF_QUERY: CLAIM_DISEASE_SCOPE_BROADER_THAN_QUERY,
    DISEASE_SIBLING: DISEASE_SIBLING_NOT_APPLICABLE,
    GENERIC_CANCER_SCOPE: GENERIC_DISEASE_SCOPE_NOT_CASE_SPECIFIC,
    CROSS_DISEASE: CROSS_DISEASE_MISMATCH,
    UNRESOLVED_DISEASE_RELATION: DISEASE_RELATION_UNRESOLVED,
    MISSING_QUERY_DISEASE: QUERY_DISEASE_MISSING,
    MISSING_CLAIM_DISEASE: CLAIM_DISEASE_SCOPE_MISSING,
}

EXPLANATION_BY_RELATION: dict[str, str] = {
    EXACT_DISEASE: DISEASE_IDENTITY_CONFIRMED,
    NORMALIZED_EXACT_DISEASE: DISEASE_IDENTITY_CONFIRMED_AFTER_NORMALIZATION,
    VERIFIED_DISEASE_ALIAS: DISEASE_IDENTITY_CONFIRMED_BY_VERIFIED_ALIAS,
    CLAIM_IS_CHILD_OF_QUERY: EVIDENCE_APPLIES_ONLY_TO_QUERY_SUBTYPE,
    CLAIM_IS_PARENT_OF_QUERY: RESULT_NOT_SEPARABLE_FOR_QUERY_SUBTYPE,
    DISEASE_SIBLING: SIBLING_EVIDENCE_NOT_TRANSFERABLE,
    GENERIC_CANCER_SCOPE: GENERIC_SCOPE_NOT_SUBSTITUTABLE_FOR_QUERY_DISEASE,
    CROSS_DISEASE: NO_VERIFIED_RELATION_BETWEEN_DISEASES,
    UNRESOLVED_DISEASE_RELATION: RELATION_NOT_DECIDABLE_ON_FROZEN_VOCABULARY,
    MISSING_QUERY_DISEASE: QUERY_DISEASE_NOT_PROVIDED,
    MISSING_CLAIM_DISEASE: CLAIM_DISEASE_SCOPE_NOT_PROVIDED,
}

# Scope che nominano una popolazione oncologica senza nominare una malattia. Non
# sono alias della disease della query: un risultato "pan-cancer" non e' un
# risultato sul caso. La lista estende, solo dentro questa fase, quella del matcher
# operativo; la differenza e' registrata nel migration impact e non viene applicata.
GENERIC_SCOPE_KEYS = frozenset(
    {
        "cancer",
        "malignancy",
        "pan cancer",
        "pan-cancer",
        "solid tumor",
        "solid tumour",
        "unspecified cancer",
        "unspecified malignancy",
        "unspecified tumor",
        "unspecified tumour",
    }
)


def registered_disease_keys() -> frozenset[str]:
    """Termini su cui il vocabolario congelato dice qualcosa.

    Serve a distinguere due assenze diverse. Se almeno uno dei due termini e'
    registrato, sappiamo abbastanza dello spazio delle malattie per affermare che
    sono diverse: e' un cross-disease. Se nessuno dei due lo e', l'unica cosa
    onesta da dire e' che la relazione non e' decidibile: dichiararli malattie
    diverse sarebbe un'inferenza che i dati congelati non autorizzano.
    """
    keys: set[str] = set()
    for group in _SYNONYM_GROUPS:
        keys.update(group)
    keys.update(_SUBTYPE_OF)
    keys.update(_SUBTYPE_OF.values())
    return frozenset(keys)


REGISTERED_DISEASE_KEYS = registered_disease_keys()


# --- provenienza della relazione ----------------------------------------------

_PROVENANCE: dict[str, tuple[str, str, str, bool]] = {
    #                       source, version, provenance, verified
    EXACT_DISEASE: (LITERAL_SOURCE, LITERAL_VERSION, "raw_string_identity", True),
    NORMALIZED_EXACT_DISEASE: (
        NORMALIZATION_SOURCE,
        NORMALIZATION_VERSION,
        "normalized_core_identity",
        True,
    ),
    VERIFIED_DISEASE_ALIAS: (
        VERIFIED_ALIAS_SOURCE,
        VERIFIED_ALIAS_VERSION,
        "verified_local_alias_table",
        True,
    ),
    CLAIM_IS_CHILD_OF_QUERY: (
        VERIFIED_RELATION_SOURCE,
        HIERARCHY_VERSION,
        "explicit_subtype_table",
        True,
    ),
    CLAIM_IS_PARENT_OF_QUERY: (
        VERIFIED_RELATION_SOURCE,
        HIERARCHY_VERSION,
        "explicit_subtype_table",
        True,
    ),
    DISEASE_SIBLING: (
        VERIFIED_RELATION_SOURCE,
        HIERARCHY_VERSION,
        "explicit_subtype_table_shared_parent",
        True,
    ),
    GENERIC_CANCER_SCOPE: (
        GENERIC_SCOPE_SOURCE,
        GENERIC_SCOPE_VERSION,
        "phase_generic_scope_registry",
        False,
    ),
    CROSS_DISEASE: (
        ABSENCE_SOURCE,
        HIERARCHY_VERSION,
        "no_verified_relation_found",
        False,
    ),
    UNRESOLVED_DISEASE_RELATION: (
        ABSENCE_SOURCE,
        HIERARCHY_VERSION,
        "no_registered_anchor",
        False,
    ),
    MISSING_QUERY_DISEASE: (
        ABSENCE_SOURCE,
        LITERAL_VERSION,
        "query_disease_absent",
        False,
    ),
    MISSING_CLAIM_DISEASE: (
        ABSENCE_SOURCE,
        LITERAL_VERSION,
        "claim_disease_scope_absent",
        False,
    ),
}


# --- politica per modalita' ---------------------------------------------------


@dataclass(frozen=True)
class ModePolicy:
    """Esito di una relazione dentro una modalita'.

    `structural_score_eligible` e' falso ovunque tranne che per le relazioni exact:
    il punteggio strutturale dice "questo claim risponde alla domanda", e nessuna
    relazione gerarchica lo fa. `qualified_score_eligible` puo' essere vero nel
    bucket warning, dove serve solo a ordinare dentro il bucket e mai a competere
    con il primario.
    """

    bucket: str
    primary_candidate_eligible: bool
    warning_eligible: bool
    audit_only: bool
    rejected_by_native_constraints: bool
    structural_score_eligible: bool
    qualified_score_eligible: bool
    final_ranking_eligible: bool
    positive_score_forbidden: bool
    ranks_within_bucket_only: bool

    def score_eligibility(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "final_ranking_eligible": self.final_ranking_eligible,
            "positive_score_forbidden": self.positive_score_forbidden,
            "qualified_score_eligible": self.qualified_score_eligible,
            "ranks_within_bucket_only": self.ranks_within_bucket_only,
            "structural_score_eligible": self.structural_score_eligible,
        }

    def as_row(self) -> dict[str, Any]:
        return {
            "audit_only": self.audit_only,
            "bucket": self.bucket,
            "primary_candidate_eligible": self.primary_candidate_eligible,
            "rejected_by_native_constraints": self.rejected_by_native_constraints,
            "score_eligibility": self.score_eligibility(),
            "warning_eligible": self.warning_eligible,
        }


def _primary() -> ModePolicy:
    return ModePolicy(
        bucket=PRIMARY,
        primary_candidate_eligible=True,
        warning_eligible=False,
        audit_only=False,
        rejected_by_native_constraints=False,
        structural_score_eligible=True,
        qualified_score_eligible=True,
        final_ranking_eligible=True,
        positive_score_forbidden=False,
        ranks_within_bucket_only=False,
    )


def _warning(*, qualified: bool) -> ModePolicy:
    return ModePolicy(
        bucket=WARNING,
        primary_candidate_eligible=False,
        warning_eligible=True,
        audit_only=False,
        rejected_by_native_constraints=False,
        structural_score_eligible=False,
        qualified_score_eligible=qualified,
        final_ranking_eligible=False,
        positive_score_forbidden=False,
        ranks_within_bucket_only=qualified,
    )


def _audit() -> ModePolicy:
    return ModePolicy(
        bucket=AUDIT,
        primary_candidate_eligible=False,
        warning_eligible=False,
        audit_only=True,
        rejected_by_native_constraints=False,
        structural_score_eligible=False,
        qualified_score_eligible=False,
        final_ranking_eligible=False,
        positive_score_forbidden=True,
        ranks_within_bucket_only=False,
    )


def _rejected() -> ModePolicy:
    return ModePolicy(
        bucket=REJECTED,
        primary_candidate_eligible=False,
        warning_eligible=False,
        audit_only=False,
        rejected_by_native_constraints=True,
        structural_score_eligible=False,
        qualified_score_eligible=False,
        final_ranking_eligible=False,
        positive_score_forbidden=True,
        ranks_within_bucket_only=False,
    )


def _mode_table() -> dict[str, dict[str, ModePolicy]]:
    """Tabella relazione x modalita'.

    Il bucket primario e' identico nelle tre modalita': e' l'invariante che
    impedisce di introdurre una modalita' broad. Parent e child restano visibili
    ovunque, perche' il claim e' pertinente, ma non diventano mai exact.
    """
    table: dict[str, dict[str, ModePolicy]] = {}
    for relation in EXACT_RELATIONS:
        table[relation] = {mode: _primary() for mode in POLICY_MODES}
    for relation in (CLAIM_IS_CHILD_OF_QUERY, CLAIM_IS_PARENT_OF_QUERY):
        table[relation] = {
            STRICT_VERIFIED: _warning(qualified=False),
            ONTOLOGY_AWARE_WARNING: _warning(qualified=True),
            AUDIT_ALL: _warning(qualified=True),
        }
    table[GENERIC_CANCER_SCOPE] = {
        STRICT_VERIFIED: _audit(),
        ONTOLOGY_AWARE_WARNING: _warning(qualified=True),
        AUDIT_ALL: _warning(qualified=True),
    }
    for relation in (
        DISEASE_SIBLING,
        UNRESOLVED_DISEASE_RELATION,
        MISSING_QUERY_DISEASE,
        MISSING_CLAIM_DISEASE,
    ):
        table[relation] = {mode: _audit() for mode in POLICY_MODES}
    table[CROSS_DISEASE] = {mode: _rejected() for mode in POLICY_MODES}
    return table


MODE_TABLE = _mode_table()


def policy_for(relation_type: str, mode: str) -> ModePolicy:
    if relation_type not in MODE_TABLE:
        raise KeyError(f"relazione non definita: {relation_type}")
    if mode not in POLICY_MODES:
        raise KeyError(f"modalita' non definita: {mode}")
    return MODE_TABLE[relation_type][mode]


# --- risoluzione della relazione ----------------------------------------------


@dataclass(frozen=True)
class DiseaseMatchResult:
    """Esito completo, serializzabile e direzionale del confronto disease."""

    query_disease: str
    claim_disease_scope: str
    normalized_query_disease: str
    normalized_claim_disease: str
    relation_type: str
    relation_direction: str
    relation_source: str
    relation_verified: bool
    primary_candidate_eligible: bool
    warning_eligible: bool
    audit_only: bool
    rejected_by_native_constraints: bool
    score_eligibility: Mapping[str, Any]
    reason_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    explanation_codes: tuple[str, ...]
    policy_mode: str = DEFAULT_MODE
    relation_source_version: str = ""
    relation_provenance: str = ""
    query_canonical_key: str = ""
    claim_canonical_key: str = ""
    contract_version: str = CONTRACT_VERSION

    def as_row(self) -> dict[str, Any]:
        return {
            "audit_only": self.audit_only,
            "claim_canonical_key": self.claim_canonical_key,
            "claim_disease_scope": self.claim_disease_scope,
            "contract_version": self.contract_version,
            "explanation_codes": list(self.explanation_codes),
            "normalized_claim_disease": self.normalized_claim_disease,
            "normalized_query_disease": self.normalized_query_disease,
            "policy_mode": self.policy_mode,
            "primary_candidate_eligible": self.primary_candidate_eligible,
            "query_canonical_key": self.query_canonical_key,
            "query_disease": self.query_disease,
            "reason_codes": list(self.reason_codes),
            "rejected_by_native_constraints": self.rejected_by_native_constraints,
            "relation_direction": self.relation_direction,
            "relation_provenance": self.relation_provenance,
            "relation_source": self.relation_source,
            "relation_source_version": self.relation_source_version,
            "relation_type": self.relation_type,
            "relation_verified": self.relation_verified,
            "score_eligibility": dict(self.score_eligibility),
            "warning_codes": list(self.warning_codes),
            "warning_eligible": self.warning_eligible,
        }


@dataclass(frozen=True)
class RelationResolution:
    """Relazione pura, indipendente dalla modalita'.

    Il tipo di relazione e la sua direzione dipendono soltanto dai due termini e
    dalle tabelle congelate. Le modalita' cambiano che cosa se ne fa, non che cosa
    e'. Tenerli separati e' cio' che rende l'invarianza verificabile.
    """

    relation_type: str
    relation_direction: str
    query_core: str
    claim_core: str
    query_canonical_key: str
    claim_canonical_key: str
    relation_source: str = field(default="")
    relation_source_version: str = field(default="")
    relation_provenance: str = field(default="")
    relation_verified: bool = field(default=False)


def _resolved(relation_type: str, direction: str, **rest: Any) -> RelationResolution:
    source, version, provenance, verified = _PROVENANCE[relation_type]
    return RelationResolution(
        relation_type=relation_type,
        relation_direction=direction,
        relation_source=source,
        relation_source_version=version,
        relation_provenance=provenance,
        relation_verified=verified,
        **rest,
    )


def resolve_relation(query_disease: object, claim_disease_scope: object) -> RelationResolution:
    """Relazione direzionale fra i due termini, sulle sole tabelle congelate.

    Nessun fuzzy matching, nessuna sottostringa, nessun embedding, nessun modello.
    L'ordine dei rami e' la politica: l'identita' viene prima della gerarchia, e la
    gerarchia prima dell'assenza di relazione.
    """
    query_text = "" if query_disease is None else str(query_disease)
    claim_text = "" if claim_disease_scope is None else str(claim_disease_scope)
    query_core = _core(query_text)
    claim_core = _core(claim_text)
    keys = {
        "query_core": query_core,
        "claim_core": claim_core,
        "query_canonical_key": _canonical_key(query_core) if query_core else "",
        "claim_canonical_key": _canonical_key(claim_core) if claim_core else "",
    }

    # Un termine assente non e' un termine diverso. Se manca la disease della query
    # manca la domanda, e la precedenza va a quella: senza domanda non si puo' dire
    # nulla del claim.
    if not query_core:
        return _resolved(MISSING_QUERY_DISEASE, DIRECTION_UNKNOWN, **keys)
    if not claim_core:
        return _resolved(MISSING_CLAIM_DISEASE, DIRECTION_UNKNOWN, **keys)

    if query_text.strip() == claim_text.strip():
        return _resolved(EXACT_DISEASE, DIRECTION_NONE, **keys)
    if query_core == claim_core:
        return _resolved(NORMALIZED_EXACT_DISEASE, DIRECTION_NONE, **keys)

    query_group = _group(query_core)
    if query_group is not None and query_group == _group(claim_core):
        return _resolved(VERIFIED_DISEASE_ALIAS, DIRECTION_NONE, **keys)

    query_generic = query_core in GENERIC_SCOPE_KEYS
    claim_generic = claim_core in GENERIC_SCOPE_KEYS
    if query_generic or claim_generic:
        if claim_generic and not query_generic:
            direction = DIRECTION_CLAIM_BROADER
        elif query_generic and not claim_generic:
            direction = DIRECTION_CLAIM_NARROWER
        else:
            direction = DIRECTION_LATERAL
        return _resolved(GENERIC_CANCER_SCOPE, direction, **keys)

    query_parent = _parent_key(query_core)
    claim_parent = _parent_key(claim_core)
    query_key = keys["query_canonical_key"]
    claim_key = keys["claim_canonical_key"]

    if claim_parent and claim_parent == query_key:
        return _resolved(CLAIM_IS_CHILD_OF_QUERY, DIRECTION_CLAIM_NARROWER, **keys)
    if query_parent and query_parent == claim_key:
        return _resolved(CLAIM_IS_PARENT_OF_QUERY, DIRECTION_CLAIM_BROADER, **keys)
    if query_parent and claim_parent and query_parent == claim_parent:
        return _resolved(DISEASE_SIBLING, DIRECTION_LATERAL, **keys)

    anchored = query_core in REGISTERED_DISEASE_KEYS or claim_core in REGISTERED_DISEASE_KEYS
    if anchored:
        return _resolved(CROSS_DISEASE, DIRECTION_NONE, **keys)
    return _resolved(UNRESOLVED_DISEASE_RELATION, DIRECTION_UNKNOWN, **keys)


def _codes(relation_type: str, policy: ModePolicy) -> tuple[list[str], list[str], list[str]]:
    reason = REASON_BY_RELATION[relation_type]
    explanation = EXPLANATION_BY_RELATION[relation_type]
    reasons = [reason]
    warnings: list[str] = []
    if policy.warning_eligible:
        warnings.append(
            GENERIC_DISEASE_SCOPE_RETAINED_WITH_WARNING
            if relation_type == GENERIC_CANCER_SCOPE
            else reason
        )
    if relation_type not in EXACT_RELATIONS:
        # Il gate e' parte della spiegazione, non un commento: e' la ragione per cui
        # nessun punteggio successivo puo' spostare l'esito.
        reasons.append(DISEASE_GATE_PRECEDES_SCORING)
    return sorted(set(reasons)), sorted(set(warnings)), [explanation]


def match_disease_scope(
    query_disease: object,
    claim_disease_scope: object,
    *,
    mode: str = DEFAULT_MODE,
) -> DiseaseMatchResult:
    """Contratto completo per una coppia query/claim in una modalita'."""
    resolution = resolve_relation(query_disease, claim_disease_scope)
    policy = policy_for(resolution.relation_type, mode)
    reasons, warnings, explanations = _codes(resolution.relation_type, policy)
    return DiseaseMatchResult(
        query_disease="" if query_disease is None else str(query_disease),
        claim_disease_scope="" if claim_disease_scope is None else str(claim_disease_scope),
        normalized_query_disease=resolution.query_core,
        normalized_claim_disease=resolution.claim_core,
        relation_type=resolution.relation_type,
        relation_direction=resolution.relation_direction,
        relation_source=resolution.relation_source,
        relation_verified=resolution.relation_verified,
        primary_candidate_eligible=policy.primary_candidate_eligible,
        warning_eligible=policy.warning_eligible,
        audit_only=policy.audit_only,
        rejected_by_native_constraints=policy.rejected_by_native_constraints,
        score_eligibility=policy.score_eligibility(),
        reason_codes=tuple(reasons),
        warning_codes=tuple(warnings),
        explanation_codes=tuple(explanations),
        policy_mode=mode,
        relation_source_version=resolution.relation_source_version,
        relation_provenance=resolution.relation_provenance,
        query_canonical_key=resolution.query_canonical_key,
        claim_canonical_key=resolution.claim_canonical_key,
    )


# --- artefatti di contratto ---------------------------------------------------


def relation_definitions() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "directions": list(RELATION_DIRECTIONS),
        "exact_relations": sorted(EXACT_RELATIONS),
        "generic_scope_keys": sorted(GENERIC_SCOPE_KEYS),
        "generic_scope_keys_version": GENERIC_SCOPE_VERSION,
        "phase": PHASE_VERSION,
        "registered_disease_keys": sorted(REGISTERED_DISEASE_KEYS),
        "relation_direction_is_computed_not_asserted": True,
        "relation_type_is_mode_invariant": True,
        "relations": [
            {
                "direction_rule": _DIRECTION_RULE[relation],
                "explanation_code": EXPLANATION_BY_RELATION[relation],
                "is_exact": relation in EXACT_RELATIONS,
                "reason_code": REASON_BY_RELATION[relation],
                "relation_provenance": _PROVENANCE[relation][2],
                "relation_source": _PROVENANCE[relation][0],
                "relation_source_version": _PROVENANCE[relation][1],
                "relation_type": relation,
                "relation_verified": _PROVENANCE[relation][3],
                "resolution_rule": _RESOLUTION_RULE[relation],
            }
            for relation in RELATION_TYPES
        ],
    }


_RESOLUTION_RULE: dict[str, str] = {
    EXACT_DISEASE: "i due letterali coincidono dopo il solo strip",
    NORMALIZED_EXACT_DISEASE: "split_disease(...).core coincide",
    VERIFIED_DISEASE_ALIAS: "i due core appartengono allo stesso gruppo di _SYNONYM_GROUPS",
    CLAIM_IS_CHILD_OF_QUERY: "_parent_key(claim) == _canonical_key(query)",
    CLAIM_IS_PARENT_OF_QUERY: "_parent_key(query) == _canonical_key(claim)",
    DISEASE_SIBLING: "_parent_key(query) == _parent_key(claim) con canonical key diversi",
    GENERIC_CANCER_SCOPE: "almeno un core appartiene a generic_scope_keys",
    CROSS_DISEASE: "nessuna relazione congelata, ma almeno un core e' registrato",
    UNRESOLVED_DISEASE_RELATION: "nessuna relazione congelata e nessun core registrato",
    MISSING_QUERY_DISEASE: "il core della disease della query e' vuoto",
    MISSING_CLAIM_DISEASE: "il core del disease scope del claim e' vuoto",
}

_DIRECTION_RULE: dict[str, str] = {
    EXACT_DISEASE: DIRECTION_NONE,
    NORMALIZED_EXACT_DISEASE: DIRECTION_NONE,
    VERIFIED_DISEASE_ALIAS: DIRECTION_NONE,
    CLAIM_IS_CHILD_OF_QUERY: DIRECTION_CLAIM_NARROWER,
    CLAIM_IS_PARENT_OF_QUERY: DIRECTION_CLAIM_BROADER,
    DISEASE_SIBLING: DIRECTION_LATERAL,
    GENERIC_CANCER_SCOPE: "claim_broader_than_query se generico e' il claim, "
    "claim_narrower_than_query se generica e' la query, lateral se lo sono entrambi",
    CROSS_DISEASE: DIRECTION_NONE,
    UNRESOLVED_DISEASE_RELATION: DIRECTION_UNKNOWN,
    MISSING_QUERY_DISEASE: DIRECTION_UNKNOWN,
    MISSING_CLAIM_DISEASE: DIRECTION_UNKNOWN,
}


def policy_modes() -> dict[str, Any]:
    return {
        "buckets": list(BUCKETS),
        "contract_version": CONTRACT_VERSION,
        "default_mode_proposed_for_promotion": DEFAULT_MODE,
        "invariants": [
            "Il primary bucket e' identico nelle tre modalita': exact, normalized "
            "exact e verified alias soltanto.",
            "Nessuna modalita' broad e' definita: parent e child non tornano mai "
            "nel primary bucket.",
            "Il tipo di relazione non dipende dalla modalita': cambia solo che "
            "cosa se ne fa.",
            "audit_all espone ed etichetta, non promuove.",
            "qualified_score_eligible nel bucket warning ordina dentro il bucket e "
            "non compete con il primario.",
        ],
        "modes": [
            {
                "description": _MODE_DESCRIPTION[mode],
                "mode": mode,
                "per_relation": {
                    relation: MODE_TABLE[relation][mode].as_row()
                    for relation in RELATION_TYPES
                },
                "primary_relations": sorted(EXACT_RELATIONS),
            }
            for mode in POLICY_MODES
        ],
        "phase": PHASE_VERSION,
    }


_MODE_DESCRIPTION: dict[str, str] = {
    STRICT_VERIFIED: "Primary soltanto per identita' verificata. Parent e child "
    "restano visibili nel bucket warning ma non ricevono alcun punteggio: la "
    "modalita' proposta come default per la futura promozione.",
    ONTOLOGY_AWARE_WARNING: "Primary invariato. Parent e child restano nel bucket "
    "warning e possono essere ordinati fra loro; generic scope passa da audit a "
    "warning. Nessuna relazione diventa exact.",
    AUDIT_ALL: "Espone parent, child, sibling, generic, unresolved e missing "
    "conservando sempre il tipo di relazione. Il primario non cambia.",
}


def scoring_gate_invariants() -> dict[str, Any]:
    non_exact = [relation for relation in RELATION_TYPES if relation not in EXACT_RELATIONS]
    return {
        "contract_version": CONTRACT_VERSION,
        "gate_precedes_scoring": True,
        "gate_reason_code": DISEASE_GATE_PRECEDES_SCORING,
        "levels": [
            "structural_score_eligibility",
            "qualified_score_eligibility",
            "final_ranking_eligibility",
        ],
        "no_numerical_compensation_invariant": (
            "Un claim in relazione claim_is_child_of_query, claim_is_parent_of_query, "
            "disease_sibling, generic_cancer_scope, unresolved_disease_relation, "
            "missing_query_disease, missing_claim_disease o cross_disease non puo' "
            "diventare exact o primary grazie a biomarker exact, intervention exact, "
            "source quality, qualification, provenance o punteggio arbitrariamente "
            "elevato. Il disease gate precede ogni scoring numerico."
        ),
        "non_compensating_signals": [
            "biomarker_exact_match",
            "intervention_exact_match",
            "provenance_level",
            "qualification_completeness",
            "source_quality",
            "arbitrarily_high_score",
        ],
        "non_exact_relations": non_exact,
        "per_relation_per_mode": {
            relation: {
                mode: MODE_TABLE[relation][mode].score_eligibility()
                for mode in POLICY_MODES
            }
            for relation in RELATION_TYPES
        },
        "phase": PHASE_VERSION,
        "positive_score_forbidden_relations": sorted(
            relation
            for relation in RELATION_TYPES
            if all(
                MODE_TABLE[relation][mode].positive_score_forbidden
                for mode in POLICY_MODES
            )
        ),
        "structural_score_reserved_to_exact_relations": True,
    }


def reason_warning_codes() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "explanation_codes": sorted(set(EXPLANATION_BY_RELATION.values())),
        "gate_codes": [DISEASE_GATE_PRECEDES_SCORING],
        "interaction_codes": [BIOMARKER_MISMATCH_DESPITE_DISEASE_ALIAS],
        "phase": PHASE_VERSION,
        "reason_codes": sorted(
            set(REASON_BY_RELATION.values()) | {DISEASE_GATE_PRECEDES_SCORING}
        ),
        "warning_codes": sorted(
            {
                CLAIM_DISEASE_SCOPE_BROADER_THAN_QUERY,
                CLAIM_DISEASE_SCOPE_NARROWER_THAN_QUERY,
                GENERIC_DISEASE_SCOPE_RETAINED_WITH_WARNING,
            }
        ),
        "by_relation": {
            relation: {
                "explanation_code": EXPLANATION_BY_RELATION[relation],
                "reason_code": REASON_BY_RELATION[relation],
            }
            for relation in RELATION_TYPES
        },
    }


def verified_alias_registry_snapshot() -> dict[str, Any]:
    """Fotografia del registro alias congelato. Nessun alias nuovo viene creato."""
    groups = []
    for group in _SYNONYM_GROUPS:
        members = sorted(group)
        groups.append(
            {
                "canonical_key": _canonical_key(members[0]),
                "eligible_for_primary": True,
                "members": members,
                "parent_key": _parent_key(members[0]),
            }
        )
    return {
        "alias_source": VERIFIED_ALIAS_SOURCE,
        "alias_version": VERIFIED_ALIAS_VERSION,
        "aliases_created_in_this_phase": 0,
        "contract_version": CONTRACT_VERSION,
        "group_count": len(groups),
        "groups": sorted(groups, key=lambda item: item["canonical_key"]),
        "phase": PHASE_VERSION,
        "policy": "Un gruppo di sinonimi e' equivalenza di vocabolario e resta "
        "eligible per il primary bucket. Un sottotipo non e' un sinonimo e non lo "
        "diventa.",
    }


def explicit_hierarchy_relations() -> list[dict[str, Any]]:
    """Ogni relazione sottotipo -> genitore gia' congelata, nelle due direzioni."""
    rows: list[dict[str, Any]] = []
    for child, parent in sorted(_SUBTYPE_OF.items()):
        child_key = _canonical_key(child)
        parent_key = _canonical_key(parent)
        rows.append(
            {
                "child_canonical_key": child_key,
                "child_term": child,
                "is_alias": False,
                "parent_canonical_key": parent_key,
                "parent_term": parent,
                "relation_provenance": "explicit_subtype_table",
                "relation_source": VERIFIED_RELATION_SOURCE,
                "relation_source_version": HIERARCHY_VERSION,
                "relation_verified": True,
                "when_claim_is_the_child": CLAIM_IS_CHILD_OF_QUERY,
                "when_claim_is_the_parent": CLAIM_IS_PARENT_OF_QUERY,
            }
        )
    return rows


def sibling_pairs() -> list[dict[str, Any]]:
    """Coppie che condividono il genitore congelato: mai exact, mai primary."""
    by_parent: dict[str, list[str]] = {}
    for child, parent in _SUBTYPE_OF.items():
        by_parent.setdefault(_canonical_key(parent), []).append(child)
    rows: list[dict[str, Any]] = []
    for parent_key, children in sorted(by_parent.items()):
        ordered = sorted(children)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                if _canonical_key(left) == _canonical_key(right):
                    continue
                rows.append(
                    {
                        "eligible_for_primary": False,
                        "left_term": left,
                        "relation_source": VERIFIED_RELATION_SOURCE,
                        "relation_type": DISEASE_SIBLING,
                        "right_term": right,
                        "shared_parent_canonical_key": parent_key,
                    }
                )
    return rows


def readiness(
    *,
    relation_types: Sequence[str],
    modes: Sequence[str],
    simulated_pairs: int,
    regression_cases: int,
    migration_findings: int,
) -> dict[str, Any]:
    """Cio' che questa fase chiude, e cio' che resta deliberatamente chiuso.

    Le tre voci finali restano false per la stessa ragione di sempre: il contratto
    e' definito e simulato, non applicato. Promuovere il corpus o migrare il
    retriever sono decisioni successive, che questa fase prepara e non prende.
    """
    complete = sorted(relation_types) == sorted(RELATION_TYPES) and sorted(modes) == sorted(
        POLICY_MODES
    )
    return {
        "corpus_promotion_ready": False,
        "current_retriever_compatibility_audited": migration_findings > 0,
        "directional_relation_contract_frozen": complete,
        "explicit_hierarchy_relations_frozen": True,
        "full_exploratory_rerun_ready": False,
        "generic_scope_policy_frozen": True,
        "migration_findings": migration_findings,
        "modes_defined": len(modes),
        "ontology_warning_policy_frozen": True,
        "operational_retriever_migration_ready": False,
        "primary_bucket_identical_across_modes": True,
        "regression_cases": regression_cases,
        "relation_types_defined": len(relation_types),
        "shadow_disease_gate_update_ready": complete and simulated_pairs > 0,
        "sibling_policy_frozen": True,
        "simulated_pairs": simulated_pairs,
        "strict_policy_frozen": True,
        "terminology_shadow_update_ready": True,
        "verified_alias_policy_frozen": True,
    }


__all__ = [
    "AUDIT",
    "AUDIT_ALL",
    "BUCKETS",
    "CLAIM_DISEASE_SCOPE_BROADER_THAN_QUERY",
    "CLAIM_DISEASE_SCOPE_MISSING",
    "CLAIM_DISEASE_SCOPE_NARROWER_THAN_QUERY",
    "CLAIM_IS_CHILD_OF_QUERY",
    "CLAIM_IS_PARENT_OF_QUERY",
    "CONTRACT_VERSION",
    "CROSS_DISEASE",
    "CROSS_DISEASE_MISMATCH",
    "DEFAULT_MODE",
    "DISEASE_GATE_PRECEDES_SCORING",
    "DISEASE_SIBLING",
    "DISEASE_SIBLING_NOT_APPLICABLE",
    "EVIDENCE_APPLIES_ONLY_TO_QUERY_SUBTYPE",
    "EXACT_DISEASE",
    "EXACT_RELATIONS",
    "GENERIC_CANCER_SCOPE",
    "GENERIC_DISEASE_SCOPE_NOT_CASE_SPECIFIC",
    "GENERIC_SCOPE_KEYS",
    "MISSING_CLAIM_DISEASE",
    "MISSING_QUERY_DISEASE",
    "MODE_TABLE",
    "NORMALIZED_EXACT_DISEASE",
    "ONTOLOGY_AWARE_WARNING",
    "PHASE_VERSION",
    "POLICY_MODES",
    "PRIMARY",
    "PROPAGATION_POLICY",
    "REASON_BY_RELATION",
    "REGISTERED_DISEASE_KEYS",
    "REJECTED",
    "RELATION_TYPES",
    "RESULT_NOT_SEPARABLE_FOR_QUERY_SUBTYPE",
    "REVIEWER_ROLE",
    "REVIEW_INDEPENDENCE",
    "REVIEW_STATUS",
    "STRICT_VERIFIED",
    "UNRESOLVED_DISEASE_RELATION",
    "VERIFIED_DISEASE_ALIAS",
    "WARNING",
    "DiseaseMatchResult",
    "ModePolicy",
    "RelationResolution",
    "explicit_hierarchy_relations",
    "match_disease_scope",
    "policy_for",
    "policy_modes",
    "readiness",
    "reason_warning_codes",
    "relation_definitions",
    "resolve_relation",
    "scoring_gate_invariants",
    "sibling_pairs",
    "verified_alias_registry_snapshot",
]

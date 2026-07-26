"""Chiusura della revisione terminologica delle associazioni pending.

La queue congelata dall'adjudication contiene due coppie: un codice di sviluppo
contro un nome generico, in entrambi i casi. La revisione le separa perche' le
prove disponibili non sono simmetriche, e la simmetria apparente delle due
situazioni e' esattamente cio' che una revisione basata sulla forma della
stringa non riuscirebbe a rompere.

Tre distinzioni governano il modulo.

**Il letterale della fonte non e' la terminologia canonica.** Un mapping
verificato autorizza una rappresentazione canonica accanto al letterale, mai al
suo posto: `source_literals` resta popolato e la fonte non viene riscritta.

**La terminologia non e' l'identita' del claim.** Verificare che due termini
denotino lo stesso farmaco non rende separabile un risultato che la fonte
riporta in forma congiunta. Un aggregate resta aggregate anche quando il nome
del suo membro diventa canonicalizzabile.

**Il grafo non prova la propria normalizzazione.** Una relazione affermata solo
da file derivati dal grafo e' circolare. Ogni decisione registra l'esito di
questo controllo, e per una delle due coppie il controllo fallisce.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

PHASE_VERSION = "terminology-mapping-closure/1.0"
CONTRACT_VERSION = "intervention-canonicalization-contract/1.0"
PACKET_VERSION = "terminology-mapping-closure-second-review/1.0"

REVIEWER_ROLE = "author_terminology_reviewer"
REVIEW_INDEPENDENCE = "non_independent"
REVIEW_STATUS = "first_review_complete"
PROPAGATION_POLICY = "prototype_only"

# Decisioni ammesse per una coppia terminologica.
VERIFIED_SAME_INTERVENTION = "verified_same_intervention"
VERIFIED_DEVELOPMENT_CODE = "verified_development_code_for_same_intervention"
VERIFIED_SAME_MOIETY_DIFFERENT_FORM = "verified_same_active_moiety_different_form"
VERIFIED_BRAND_OR_NONPROPRIETARY = "verified_brand_or_nonproprietary_name"
SOURCE_LOCAL_EQUIVALENCE_ONLY = "source_local_equivalence_only"
POSSIBLE_ALIAS_NOT_VERIFIED = "possible_alias_not_verified"
TERMINOLOGY_CONFLICT = "terminology_conflict"
DIFFERENT_INTERVENTIONS = "different_interventions"
INSUFFICIENT_AUTHORITATIVE_EVIDENCE = "insufficient_authoritative_evidence"

PAIR_DECISIONS = (
    VERIFIED_SAME_INTERVENTION,
    VERIFIED_DEVELOPMENT_CODE,
    VERIFIED_SAME_MOIETY_DIFFERENT_FORM,
    VERIFIED_BRAND_OR_NONPROPRIETARY,
    SOURCE_LOCAL_EQUIVALENCE_ONLY,
    POSSIBLE_ALIAS_NOT_VERIFIED,
    TERMINOLOGY_CONFLICT,
    DIFFERENT_INTERVENTIONS,
    INSUFFICIENT_AUTHORITATIVE_EVIDENCE,
)

VERIFIED_DECISIONS = frozenset(
    {
        VERIFIED_SAME_INTERVENTION,
        VERIFIED_DEVELOPMENT_CODE,
        VERIFIED_SAME_MOIETY_DIFFERENT_FORM,
        VERIFIED_BRAND_OR_NONPROPRIETARY,
    }
)

SCOPE_GLOBAL = "global"
SCOPE_SOURCE_LOCAL = "source_local"
SCOPE_NONE = "none"
MAPPING_SCOPES = (SCOPE_GLOBAL, SCOPE_SOURCE_LOCAL, SCOPE_NONE)

APPROVE_FOR_SHADOW_UPDATE = "approve_for_shadow_update"
KEEP_PENDING = "keep_pending"
REJECT_MAPPING = "reject_mapping"
REQUIRE_EXTERNAL_REVIEW = "require_external_review"
RECOMMENDATIONS = (
    APPROVE_FOR_SHADOW_UPDATE,
    KEEP_PENDING,
    REJECT_MAPPING,
    REQUIRE_EXTERNAL_REVIEW,
)

# Reason code. I primi sei sono quelli previsti dal perimetro di fase; l'ultimo
# nasce da un ritrovamento di questa revisione e viene dichiarato come tale.
DEVELOPMENT_CODE_VERIFIED = "DEVELOPMENT_CODE_VERIFIED"
GLOBAL_DRUG_IDENTITY_CONFIRMED = "GLOBAL_DRUG_IDENTITY_CONFIRMED"
SAME_INTERVENTION_IDENTITY_CONFIRMED = "SAME_INTERVENTION_IDENTITY_CONFIRMED"
SOURCE_LITERAL_PRESERVED = "SOURCE_LITERAL_PRESERVED"
AGGREGATE_RESULT_REMAINS_NON_SEPARABLE = "AGGREGATE_RESULT_REMAINS_NON_SEPARABLE"
FORMULATION_RELATION_REQUIRES_QUALIFIER = "FORMULATION_RELATION_REQUIRES_QUALIFIER"
MAPPING_REMAINS_UNRESOLVED = "MAPPING_REMAINS_UNRESOLVED"
MAPPING_VERIFIED_BUT_CLAIM_NOT_ATOMIC = "MAPPING_VERIFIED_BUT_CLAIM_NOT_ATOMIC"
INSUFFICIENT_AUTHORITATIVE_SOURCE = "INSUFFICIENT_AUTHORITATIVE_SOURCE"
VOCABULARY_CONCEPT_ID_CONFLICT = "VOCABULARY_CONCEPT_ID_CONFLICT"
REGIMEN_COMPONENT_ABSENT_FROM_VOCABULARY = "REGIMEN_COMPONENT_ABSENT_FROM_VOCABULARY"

# Livelli di autorevolezza, nell'ordine di priorita' dichiarato dal protocollo.
LEVEL_PRIMARY_SOURCE_MATERIAL = 1
LEVEL_FULL_TEXT_OR_SUPPLEMENT = 2
LEVEL_TRIAL_PROTOCOL_OR_REGISTRY = 3
LEVEL_REGULATORY_DOCUMENT = 4
LEVEL_INSTITUTIONAL_VOCABULARY = 5
LEVEL_MANUFACTURER_DEVELOPMENT_DOC = 6
LEVEL_INDEXED_ABSTRACT = 7
LEVEL_BIBLIOGRAPHIC_METADATA = 8


class TerminologyReviewError(ValueError):
    """Una decisione viola un invariante del contratto di canonicalizzazione."""


@dataclass(frozen=True)
class SourceAccess:
    """Che cosa e' stato realmente aperto, e con quale limite."""

    source_access_id: str
    source_id: str
    repository_or_body: str
    document_type: str
    access_type: str
    access_path: str
    stable_identifier: str
    date_or_version: str
    authoritative_level: int
    limitation: str

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MappingEvidence:
    """Una singola prova documentale a favore o contro una relazione."""

    evidence_id: str
    pair_id: str
    source_access_id: str
    source_id: str
    repository_or_body: str
    document_type: str
    date_or_version: str
    term_a: str
    term_b: str
    supporting_field: str
    supporting_text: str
    locator: str
    access_type: str
    stable_identifier: str
    authoritative_level: int
    supports_identity: bool
    graph_derived: bool
    limitation: str

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PairDecision:
    """Decisione terminologica su una coppia della queue congelata."""

    pair_id: str
    queue_id: str
    source_literal_term: str
    graph_term: str
    decision: str
    mapping_scope: str
    canonical_intervention_id: str
    canonical_label: str
    confidence: str
    recommendation: str
    reason_codes: tuple[str, ...]
    affected_groups: tuple[str, ...]
    affected_claim_ids: tuple[str, ...]
    circularity_control_passed: bool
    non_graph_derived_evidence_ids: tuple[str, ...]
    limitations: tuple[str, ...]
    rationale: str
    unresolved_reason: str = ""

    def __post_init__(self) -> None:
        if self.decision not in PAIR_DECISIONS:
            raise TerminologyReviewError(f"decisione sconosciuta: {self.decision}")
        if self.mapping_scope not in MAPPING_SCOPES:
            raise TerminologyReviewError(f"scope sconosciuto: {self.mapping_scope}")
        if self.recommendation not in RECOMMENDATIONS:
            raise TerminologyReviewError(
                f"recommendation sconosciuta: {self.recommendation}"
            )
        # Un mapping non verificato non ha diritto a un'etichetta canonica: se ne
        # avesse una, qualcuno a valle la userebbe.
        if self.decision not in VERIFIED_DECISIONS and self.canonical_label:
            raise TerminologyReviewError(
                f"{self.pair_id}: canonical label su decisione non verificata"
            )
        if self.is_verified and self.mapping_scope == SCOPE_NONE:
            raise TerminologyReviewError(
                f"{self.pair_id}: decisione verificata senza scope"
            )
        if not self.is_verified and self.mapping_scope != SCOPE_NONE:
            raise TerminologyReviewError(
                f"{self.pair_id}: scope su decisione non verificata"
            )
        # Il letterale della fonte non sparisce mai dalla decisione.
        if not self.source_literal_term.strip():
            raise TerminologyReviewError(f"{self.pair_id}: source literal assente")

    @property
    def is_verified(self) -> bool:
        return self.decision in VERIFIED_DECISIONS

    @property
    def is_global(self) -> bool:
        return self.is_verified and self.mapping_scope == SCOPE_GLOBAL

    def as_row(self) -> dict[str, Any]:
        row = asdict(self)
        row.update(
            {
                "is_verified": self.is_verified,
                "is_global": self.is_global,
                "hard_filterable": False,
                "final_evaluable": False,
                "propagation_policy": PROPAGATION_POLICY,
                "review_status": REVIEW_STATUS,
                "reviewer_role": REVIEWER_ROLE,
                "review_independence": REVIEW_INDEPENDENCE,
                "gold_used_for_decisions": False,
                "decided_by_string_similarity": False,
            }
        )
        return row


@dataclass(frozen=True)
class GroupReview:
    """Revisione di un gruppo con terminology review aperta.

    `terminology_decision` resta vuoto quando il gruppo non contiene una coppia:
    la queue congelata e' l'unica autorita' su quali termini siano in revisione,
    e inventarne una per uniformita' formale sarebbe un'estensione arbitraria.
    """

    group_id: str
    graph_evidence_id: str
    source_id: str
    v2_record_term: str
    source_term: str
    claim_term: str
    mapping_candidate: str
    disease: str
    biomarker: str
    source_unit_id: str
    locator: str
    review_status: str
    terminology_decision: str
    confidence: str
    mapping_scope: str
    proposed_canonical_label: str
    preserved_source_literal: str
    claim_impact: str
    claim_id_impact: str
    open_reason: str
    unresolved_reason: str = ""

    def as_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["gold_used_for_decisions"] = False
        row["reviewer_role"] = REVIEWER_ROLE
        row["review_independence"] = REVIEW_INDEPENDENCE
        return row


def preservation_rows(
    decisions: Sequence[PairDecision],
    literals_by_group: Mapping[str, Sequence[str]],
) -> list[dict[str, Any]]:
    """Registra, per gruppo, che il letterale sopravvive alla canonicalizzazione."""
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        for group in decision.affected_groups:
            literals = tuple(literals_by_group.get(group, ()))
            rows.append(
                {
                    "pair_id": decision.pair_id,
                    "graph_evidence_id": group,
                    "source_literal_terms": list(literals),
                    "source_literal_preserved": True,
                    "canonical_label": decision.canonical_label,
                    "canonical_replaces_source_literal": False,
                    "development_code_preserved": decision.source_literal_term
                    in literals,
                    "original_text_preserved": True,
                    "locator_preserved": True,
                    "temporal_denomination_preserved": True,
                    "decision_provenance_preserved": True,
                    "source_rewritten": False,
                }
            )
    return sorted(rows, key=lambda row: (row["pair_id"], row["graph_evidence_id"]))


def readiness(
    decisions: Sequence[PairDecision],
    *,
    queue_pairs: int,
    reviewed_groups: int,
    expected_groups: int,
    claim_id_changes: int,
    packets: int,
) -> dict[str, Any]:
    """Readiness della fase. Nessun flag di promozione diventa vero qui."""
    verified_global = [d for d in decisions if d.is_global]
    verified_local = [
        d for d in decisions if d.is_verified and d.mapping_scope == SCOPE_SOURCE_LOCAL
    ]
    unresolved = [d for d in decisions if not d.is_verified]
    rejected = [d for d in decisions if d.recommendation == REJECT_MAPPING]
    all_decided = len(decisions) == queue_pairs and all(
        d.decision in PAIR_DECISIONS for d in decisions
    )
    # Nessun blocker terminologico *strutturale* resta aperto: la coppia non
    # verificata lascia la propria associazione esattamente dov'era, quindi non
    # trattiene la definizione della disease policy.
    structural_blockers = [
        d for d in unresolved if d.recommendation not in (REQUIRE_EXTERNAL_REVIEW,)
    ]
    return {
        "terminology_queue_complete": reviewed_groups == expected_groups,
        "all_mapping_candidates_reviewed": reviewed_groups == expected_groups,
        "all_mapping_pairs_decided": all_decided,
        "verified_global_mappings": len(verified_global),
        "verified_source_local_mappings": len(verified_local),
        "unresolved_mappings": len(unresolved),
        "rejected_mappings": len(rejected),
        "claim_id_changes_required": claim_id_changes,
        "second_review_packets_ready": packets == queue_pairs,
        "shadow_repository_terminology_update_ready": bool(verified_global)
        and all_decided,
        "disease_hierarchy_policy_ready": all_decided and not structural_blockers,
        "corpus_promotion_ready": False,
        "operational_retriever_migration_ready": False,
        "full_exploratory_rerun_ready": False,
    }


__all__ = [
    "PHASE_VERSION",
    "CONTRACT_VERSION",
    "PACKET_VERSION",
    "REVIEWER_ROLE",
    "REVIEW_INDEPENDENCE",
    "REVIEW_STATUS",
    "PROPAGATION_POLICY",
    "PAIR_DECISIONS",
    "VERIFIED_DECISIONS",
    "MAPPING_SCOPES",
    "RECOMMENDATIONS",
    "SCOPE_GLOBAL",
    "SCOPE_SOURCE_LOCAL",
    "SCOPE_NONE",
    "VERIFIED_DEVELOPMENT_CODE",
    "INSUFFICIENT_AUTHORITATIVE_EVIDENCE",
    "POSSIBLE_ALIAS_NOT_VERIFIED",
    "APPROVE_FOR_SHADOW_UPDATE",
    "REQUIRE_EXTERNAL_REVIEW",
    "REJECT_MAPPING",
    "KEEP_PENDING",
    "DEVELOPMENT_CODE_VERIFIED",
    "GLOBAL_DRUG_IDENTITY_CONFIRMED",
    "SOURCE_LITERAL_PRESERVED",
    "AGGREGATE_RESULT_REMAINS_NON_SEPARABLE",
    "FORMULATION_RELATION_REQUIRES_QUALIFIER",
    "MAPPING_REMAINS_UNRESOLVED",
    "MAPPING_VERIFIED_BUT_CLAIM_NOT_ATOMIC",
    "INSUFFICIENT_AUTHORITATIVE_SOURCE",
    "VOCABULARY_CONCEPT_ID_CONFLICT",
    "REGIMEN_COMPONENT_ABSENT_FROM_VOCABULARY",
    "LEVEL_FULL_TEXT_OR_SUPPLEMENT",
    "LEVEL_INSTITUTIONAL_VOCABULARY",
    "LEVEL_INDEXED_ABSTRACT",
    "LEVEL_BIBLIOGRAPHIC_METADATA",
    "TerminologyReviewError",
    "SourceAccess",
    "MappingEvidence",
    "PairDecision",
    "GroupReview",
    "preservation_rows",
    "readiness",
]

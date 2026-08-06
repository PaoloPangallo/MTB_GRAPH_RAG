"""Contratto GraphCandidateAssertion v3.

Una GraphCandidateAssertion continua a significare **relazione candidata
derivata dal Knowledge Graph**, e non: claim degli autori, evidenza
documentale, verità clinica, raccomandazione, supporto verificato.

La differenza rispetto a v2 è che il contratto conserva l'informazione
semantica che la sorgente contiene e che v2 appiattiva:

* la **direzione proposta dal grafo** e la **posizione della fonte** rispetto a
  quella relazione sono due campi distinti;
* le **alterazioni composte** conservano termini, operatori e struttura logica;
* i **regimi multi-componente** restano unità, con lo stato di conoscenza
  disponibile dichiarato esplicitamente.

Il cambio è **major** perché cambia il significato degli oggetti, non solo la
loro serializzazione: un consumatore di v2 che legga v3 assumendo la vecchia
semantica sbaglierebbe.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from . import CONTRACT_VERSION, REPOSITORY_VERSION

#: Campi che entrano nel payload identitario, in ordine fisso.
PAYLOAD_FIELDS = (
    "materialization_rule_id",
    "subject", "predicate", "object",
    "disease",
    "graph_direction", "source_support_polarity", "source_supported_direction",
    "source_alignment_status",
    "alteration_expression_raw", "alteration_expression_ast", "alteration_parse_status",
    "intervention_expression_raw", "intervention_components", "intervention_structure",
    "regimen_semantics_status", "regimen_id",
    "biomarkers", "evidence_scope", "diagnostic_scope",
    "graph_path", "node_ids", "edge_ids",
    "evidence_record_ids", "document_identifiers",
    "source_properties",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass
class GraphCandidateAssertionV3:
    """Relazione candidata derivata dal Knowledge Graph, contratto 3.0."""

    candidate_id: str
    contract_version: str
    repository_version: str
    materialization_rule_id: str
    materialized_at: str | None

    # --- relazione ---
    subject: dict[str, Any]
    predicate: str
    object: dict[str, Any]
    disease: list[dict[str, Any]] = field(default_factory=list)

    # --- polarità (§5-§6) ---
    graph_direction: str = "UNKNOWN"
    source_support_polarity: str = "NOT_REPORTED"
    source_supported_direction: str | None = None
    source_alignment_status: str = "SOURCE_ALIGNMENT_NOT_AVAILABLE"
    source_polarity_raw: dict[str, Any] = field(default_factory=dict)

    # --- alterazioni (§7-§8) ---
    alteration_expression_raw: str | None = None
    alteration_terms: list[dict[str, Any]] = field(default_factory=list)
    alteration_expression_ast: dict[str, Any] | None = None
    alteration_parse_status: str = "MISSING"
    alteration_expression_hash: str | None = None
    alteration_parse_warnings: list[str] = field(default_factory=list)
    alteration_canonical_expression: str | None = None

    # --- interventi e regimi (§10-§12) ---
    intervention_expression_raw: str | None = None
    intervention_components: list[dict[str, Any]] = field(default_factory=list)
    intervention_structure: str = "UNKNOWN"
    regimen_semantics_status: str = "NOT_APPLICABLE"
    regimen_id: str | None = None
    regimen_limitations: list[str] = field(default_factory=list)

    # --- provenance ---
    biomarkers: list[dict[str, Any]] = field(default_factory=list)
    evidence_scope: str | None = None
    diagnostic_scope: str | None = None
    graph_path: list[str] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)
    edge_ids: list[str] = field(default_factory=list)
    evidence_record_ids: list[str] = field(default_factory=list)
    document_identifiers: list[dict[str, Any]] = field(default_factory=list)
    source_properties: dict[str, Any] = field(default_factory=dict)
    source_path_ids: list[str] = field(default_factory=list)
    v2_candidate_ids: list[str] = field(default_factory=list)

    payload_hash: str = ""
    known_limitations: list[str] = field(default_factory=list)

    @classmethod
    def from_parts(cls, **parts: Any) -> "GraphCandidateAssertionV3":
        payload = {name: parts.get(name) for name in PAYLOAD_FIELDS}
        digest = _sha(payload)
        return cls(
            candidate_id=f"GCA3-{digest[:24]}",
            contract_version=CONTRACT_VERSION,
            repository_version=REPOSITORY_VERSION,
            payload_hash=digest,
            **parts,
        )

    def payload(self) -> dict[str, Any]:
        data = asdict(self)
        return {name: data.get(name) for name in PAYLOAD_FIELDS}

    def recomputed_identity(self) -> tuple[str, str]:
        digest = _sha(self.payload())
        return f"GCA3-{digest[:24]}", digest

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # ------------------------------------------------------------- invarianti

    def validate(self) -> list[str]:
        """Invarianti formali del contratto (§24). Restituisce le violazioni."""
        from .polarity import (
            DOES_NOT_SUPPORT_ASSERTION, SOURCE_ALIGNED, SUPPORTS_ASSERTION,
        )
        from .regimens import (
            COMBINATION_CONFIRMED, MULTI_COMPONENT_UNRESOLVED,
            SEMANTICS_UNAVAILABLE_IN_SOURCE,
        )

        violations: list[str] = []

        # 1. Ogni candidate deve avere almeno un source_path_id.
        if not self.source_path_ids:
            violations.append("INV1_NO_SOURCE_PATH_ID")

        # 2. DOES_NOT_SUPPORT non può essere SOURCE_ALIGNED.
        if (self.source_support_polarity == DOES_NOT_SUPPORT_ASSERTION
                and self.source_alignment_status == SOURCE_ALIGNED):
            violations.append("INV2_DOES_NOT_SUPPORT_MARKED_ALIGNED")

        # 2b. Una fonte che non sostiene non può dichiarare una direzione sostenuta.
        if (self.source_support_polarity != SUPPORTS_ASSERTION
                and self.source_supported_direction is not None):
            violations.append("INV2B_SUPPORTED_DIRECTION_WITHOUT_SUPPORT")

        # 3. PARSED_EXACT: tutti i termini devono comparire nell'AST.
        if self.alteration_parse_status in {"PARSED_EXACT", "PARSED_WITH_WARNINGS", "ATOMIC"}:
            if self.alteration_expression_ast is None:
                violations.append("INV3_PARSED_WITHOUT_AST")
            else:
                from .alterations import ast_from_dict
                node = ast_from_dict(self.alteration_expression_ast)
                if len(node.terms()) != len(self.alteration_terms):
                    violations.append("INV3_TERM_COUNT_MISMATCH")

        # 4. Un regime irrisolto non può avere un solo componente promosso.
        if self.intervention_structure == MULTI_COMPONENT_UNRESOLVED:
            if len(self.intervention_components) < 2:
                violations.append("INV4_UNRESOLVED_WITH_FEWER_THAN_TWO_COMPONENTS")

        # 5. Semantica indisponibile non può produrre COMBINATION_CONFIRMED.
        if (self.regimen_semantics_status == SEMANTICS_UNAVAILABLE_IN_SOURCE
                and self.intervention_structure == COMBINATION_CONFIRMED):
            violations.append("INV5_CONFIRMED_COMBINATION_WITHOUT_SOURCE_SEMANTICS")

        # 6. candidate_id e payload_hash devono essere deterministici.
        candidate_id, digest = self.recomputed_identity()
        if candidate_id != self.candidate_id or digest != self.payload_hash:
            violations.append("INV6_NON_DETERMINISTIC_IDENTITY")

        return violations


#: Schema pubblicato accanto al repository.
SCHEMA = {
    "model": "GraphCandidateAssertion",
    "contract_version": CONTRACT_VERSION,
    "repository_version": REPOSITORY_VERSION,
    "candidate_id": "GCA3- + sha256(payload)[:24]",
    "meaning": "relazione candidata derivata dal Knowledge Graph",
    "forbidden_interpretations": [
        "claim degli autori", "evidenza documentale", "verità clinica",
        "raccomandazione", "supporto verificato",
    ],
    "required": [
        "candidate_id", "contract_version", "materialization_rule_id",
        "subject", "predicate", "object",
        "graph_direction", "source_support_polarity", "source_alignment_status",
        "alteration_parse_status", "intervention_structure",
        "regimen_semantics_status",
        "graph_path", "node_ids", "edge_ids", "source_path_ids",
    ],
    "enums": {
        "graph_direction": sorted(set(
            list(__import__("gca_v3.polarity", fromlist=["x"]).GRAPH_DIRECTION_BY_SIGNIFICANCE.values())
            + ["UNKNOWN", "UNMAPPED_SOURCE_VALUE"]
        )),
        "source_support_polarity": [
            "SUPPORTS_ASSERTION", "DOES_NOT_SUPPORT_ASSERTION", "CONTRADICTS_ASSERTION",
            "NEUTRAL_OR_NO_DIFFERENCE", "UNCLEAR", "NOT_REPORTED", "UNMAPPED_SOURCE_VALUE",
        ],
        "source_alignment_status": [
            "SOURCE_ALIGNED", "SOURCE_DOES_NOT_SUPPORT", "SOURCE_CONTRADICTS",
            "SOURCE_NEUTRAL", "SOURCE_ALIGNMENT_UNCLEAR", "SOURCE_ALIGNMENT_NOT_AVAILABLE",
        ],
        "alteration_parse_status": [
            "ATOMIC", "PARSED_EXACT", "PARSED_WITH_WARNINGS", "AMBIGUOUS_OPERATOR",
            "UNSUPPORTED_EXPRESSION", "MALFORMED_EXPRESSION", "MISSING",
        ],
        "intervention_structure": [
            "SINGLE_AGENT", "COMBINATION_CONFIRMED", "ALTERNATIVE_CONFIRMED",
            "SEQUENTIAL_CONFIRMED", "MULTI_COMPONENT_UNRESOLVED", "UNKNOWN",
        ],
        "regimen_semantics_status": [
            "SEMANTICS_PRESERVED", "SEMANTICS_PARTIALLY_PRESERVED",
            "SEMANTICS_UNAVAILABLE_IN_SOURCE", "SEMANTICS_AMBIGUOUS", "NOT_APPLICABLE",
        ],
        "component_role": [
            "ACTIVE_COMPONENT", "COMBINATION_PARTNER", "COMPARATOR", "CONTROL",
            "BACKBONE", "SEQUENTIAL_AGENT", "UNKNOWN",
        ],
    },
    "notes": {
        "does_not_support": "non viene mai convertito nella direzione opposta",
        "component_role": "l'export non contiene ruoli: su questa sorgente vale sempre UNKNOWN",
        "unused_enum_values": [
            "CONTRADICTS_ASSERTION e NEUTRAL_OR_NO_DIFFERENCE non sono prodotti da "
            "questa sorgente: evidence_direction ha solo Supports / Does Not Support / vuoto",
            "COMBINATION_CONFIRMED, ALTERNATIVE_CONFIRMED e SEQUENTIAL_CONFIRMED non sono "
            "prodotti: l'export non distingue la relazione fra farmaci",
        ],
    },
}


def schema_hash() -> str:
    return _sha(SCHEMA)

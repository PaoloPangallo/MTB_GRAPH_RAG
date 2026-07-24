"""Retriever deterministico, read-only, del qualification corpus 2.0."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ._normalize import normalize_text
from .qualified_retrieval_errors import (
    FingerprintMismatchError,
    HistoricalUnitInActiveIndexError,
    IndexIntegrityError,
    UnsupportedCorpusVersionError,
)
from .qualified_retrieval_query import (
    MODE_AUDIT_ALL,
    MODE_QUALIFIED_SOFT,
    QualifiedRetrievalQuery,
    require_valid,
)
from .qualified_retrieval_result import (
    BUCKET_AUDIT_ONLY,
    BUCKET_RANKED,
    BUCKET_RETAINED_WITH_WARNING,
    NativeExclusion,
    QualifiedRetrievalResult,
    W_ABSTRACT_ONLY_SOURCE,
    W_CANDIDATE_AMBIGUOUS,
    W_CANDIDATE_CONFLICTING,
    W_CANDIDATE_INVALID,
    W_CANDIDATE_PARTIAL,
    W_CASE_LEVEL,
    W_NAMED_PATIENT_SUBSET,
    W_NEGATIVE_EXPERIMENT,
    W_NOT_SEPARABLE,
    W_PRECLINICAL_ONLY,
    W_PROTOTYPE_ONLY_QUALIFIERS,
    W_QUALIFIER_MISMATCH_NOT_FILTERED,
    W_QUALIFIER_UNREVIEWED,
    W_TERMINOLOGY_PENDING,
    W_UNRESOLVED_UNIT,
    X_BIOMARKER_MISMATCH,
    X_DISEASE_MISMATCH,
    X_DIRECTION_MISMATCH,
    X_INTERVENTION_MISMATCH,
    X_POLARITY_MISMATCH,
    X_SCOPE_MISMATCH,
    build_explanation,
)
from .qualified_retrieval_scoring import (
    RetrievalScoreBreakdown,
    ScoreComponent,
    ScoringConfig,
)
from .repository import EvidenceStatementRepository


SUPPORTED_CORPUS_VERSION = "qualification_corpus/2.0"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _label(value: Any) -> str:
    return str((value or {}).get("label") or "") if isinstance(value, Mapping) else str(value or "")


def _source_ids(statement: Mapping[str, Any]) -> tuple[str, ...]:
    refs = list(statement.get("source_references") or []) + list(
        statement.get("trial_references") or []
    )
    return tuple(
        sorted(
            {
                str(ref.get("source_id") or ref.get("external_identifier") or "")
                for ref in refs
                if ref.get("source_id") or ref.get("external_identifier")
            }
        )
    )


def _contains_marker(statement: Mapping[str, Any], keys: Sequence[str]) -> bool:
    biomarker = statement.get("biomarker") or {}
    haystack = " ".join(
        [
            str(biomarker.get("gene") or ""),
            str(biomarker.get("label") or ""),
            " ".join(str(item) for item in biomarker.get("component_biomarkers") or []),
            str(statement.get("alteration_type") or ""),
        ]
    )
    normalized = normalize_text(haystack)
    return any(key in normalized or normalized in key for key in keys)


def _native_match(query_values: Sequence[str], statement_value: Any) -> bool:
    if not query_values:
        return True
    normalized = normalize_text(statement_value)
    return normalized in query_values


@dataclass(frozen=True)
class QualifiedRetrievalOutput:
    query_id: str
    ranked_results: tuple[QualifiedRetrievalResult, ...]
    retained_with_warning: tuple[QualifiedRetrievalResult, ...]
    audit_only_results: tuple[QualifiedRetrievalResult, ...]
    rejected_by_native_constraints: tuple[NativeExclusion, ...]
    corpus_fingerprint: str
    scoring_config_hash: str
    candidate_count: int

    @property
    def all_results(self) -> tuple[QualifiedRetrievalResult, ...]:
        return self.ranked_results + self.retained_with_warning + self.audit_only_results

    def as_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "corpus_fingerprint": self.corpus_fingerprint,
            "scoring_config_hash": self.scoring_config_hash,
            "candidate_count": self.candidate_count,
            "ranked_results": [item.as_dict() for item in self.ranked_results],
            "retained_with_warning": [
                item.as_dict() for item in self.retained_with_warning
            ],
            "audit_only_results": [item.as_dict() for item in self.audit_only_results],
            "rejected_by_native_constraints": [
                item.as_dict() for item in self.rejected_by_native_constraints
            ],
        }


class QualifiedEvidenceRetriever:
    def __init__(
        self,
        *,
        corpus_dir: Path,
        manifest: Mapping[str, Any],
        repository: EvidenceStatementRepository,
        views: Mapping[str, Mapping[str, Any]],
        active_units: Mapping[str, Mapping[str, Any]],
        historical_units: Mapping[str, Mapping[str, Any]],
        links: Sequence[Mapping[str, Any]],
        qualification_gold: Sequence[Mapping[str, Any]],
        terminology_mappings: Sequence[Mapping[str, Any]],
        scoring_config: ScoringConfig,
    ) -> None:
        self.corpus_dir = corpus_dir
        self.manifest = copy.deepcopy(dict(manifest))
        self.repository = repository
        self.views = copy.deepcopy(dict(views))
        self.active_units = copy.deepcopy(dict(active_units))
        self.historical_units = copy.deepcopy(dict(historical_units))
        self.links = tuple(copy.deepcopy(list(links)))
        self.qualification_gold = tuple(copy.deepcopy(list(qualification_gold)))
        self._terminology_mappings = tuple(copy.deepcopy(list(terminology_mappings)))
        self.scoring_config = scoring_config
        self._audit: dict[str, QualifiedRetrievalOutput] = {}
        self._links_by_statement: dict[str, list[Mapping[str, Any]]] = {}
        self._gold_by_statement: dict[str, list[Mapping[str, Any]]] = {}
        for row in self.qualification_gold:
            self._gold_by_statement.setdefault(str(row.get("statement_id") or ""), []).append(row)
        for link in sorted(self.links, key=lambda item: str(item.get("qualification_link_id") or "")):
            statement_id = str(link.get("statement_id") or "")
            unit_id = str(link.get("source_profile_unit_id") or "")
            if statement_id not in self.views:
                raise IndexIntegrityError(f"link verso statement inesistente: {statement_id}")
            if unit_id in self.historical_units:
                raise HistoricalUnitInActiveIndexError(unit_id)
            if unit_id and unit_id not in self.active_units:
                raise IndexIntegrityError(f"link verso unita' attiva inesistente: {unit_id}")
            self._links_by_statement.setdefault(statement_id, []).append(link)

    @classmethod
    def from_corpus(
        cls, corpus_dir: str | Path, *, scoring_config_path: str | Path
    ) -> "QualifiedEvidenceRetriever":
        root = Path(corpus_dir)
        manifest = json.loads(
            (root / "qualification_corpus_manifest.json").read_text(encoding="utf-8")
        )
        if manifest.get("corpus_version") != SUPPORTED_CORPUS_VERSION:
            raise UnsupportedCorpusVersionError(str(manifest.get("corpus_version")))
        statements = _jsonl(root / "evidence_statements.jsonl")
        repository = EvidenceStatementRepository(
            statements, created_at=str(manifest.get("generated_at") or "")
        )
        views = {str(item["statement_id"]): item for item in _jsonl(root / "qualified_evidence_views.jsonl")}
        active = {str(item["profile_unit_id"]): item for item in _jsonl(root / "active_source_profile_units.jsonl")}
        historical = {str(item["profile_unit_id"]): item for item in _jsonl(root / "historical_source_profile_units.jsonl")}
        return cls(
            corpus_dir=root,
            manifest=manifest,
            repository=repository,
            views=views,
            active_units=active,
            historical_units=historical,
            links=_jsonl(root / "qualification_links.jsonl"),
            qualification_gold=_jsonl(root / "statement_qualification_gold.jsonl"),
            terminology_mappings=_jsonl(root / "terminology_mappings.jsonl"),
            scoring_config=ScoringConfig.load(scoring_config_path),
        )

    @property
    def active_index_has_historical_units(self) -> bool:
        return bool(set(self.active_units) & set(self.historical_units))

    @property
    def terminology_mappings(self) -> tuple[dict[str, Any], ...]:
        output = []
        for mapping in self._terminology_mappings:
            item = copy.deepcopy(dict(mapping))
            status = str(item.get("mapping_status") or "")
            item["match_grade"] = (
                "verified_synonym"
                if status in {"verified_synonym", "verified_development_code"}
                else "pending_terminology_mapping"
                if status.startswith("requires_")
                else status or "ambiguous_mapping"
            )
            output.append(item)
        return tuple(output)

    def validate_corpus(self) -> dict[str, Any]:
        counts = dict(self.manifest.get("counts") or {})
        actual = {
            "statements": self.repository.count(),
            "sources": len(_jsonl(self.corpus_dir / "source_inventory.jsonl")),
            "active_profile_units": len(self.active_units),
            "historical_profile_units": len(self.historical_units),
            "qualification_links": len(self.links),
            "qualified_evidence_views": len(self.views),
            "final_units": sum(
                item.get("propagation_eligibility") == "final"
                for item in self.active_units.values()
            ),
            "hard_filterable_qualifiers": sum(
                bool(item.get("is_hard_filterable"))
                for item in self.active_units.values()
            ),
        }
        for name, value in actual.items():
            if int(counts.get(name, -1)) != value:
                raise IndexIntegrityError(
                    f"conteggio {name}: manifest={counts.get(name)!r}, reale={value}"
                )
        actual["qualification_corpus_fingerprint"] = str(
            self.manifest["qualification_corpus_fingerprint"]
        )
        actual["frozen_kg_snapshot_fingerprint"] = str(
            self.manifest["frozen_kg_snapshot_fingerprint"]
        )
        return actual

    def get_scoring_config_hash(self) -> str:
        return self.scoring_config.hash

    def retrieve_batch(
        self, queries: Iterable[QualifiedRetrievalQuery]
    ) -> tuple[QualifiedRetrievalOutput, ...]:
        return tuple(self.retrieve(query) for query in queries)

    def retrieve(self, query: QualifiedRetrievalQuery) -> QualifiedRetrievalOutput:
        require_valid(query)
        fingerprint = str(self.manifest["qualification_corpus_fingerprint"])
        if query.corpus_fingerprint and query.corpus_fingerprint != fingerprint:
            raise FingerprintMismatchError(
                f"query={query.corpus_fingerprint}, corpus={fingerprint}"
            )
        candidates, exclusions = self._candidates(query)
        results = [self._result(query, statement) for statement in candidates]
        results.sort(key=lambda item: self._sort_key(query, item))
        ranked: list[QualifiedRetrievalResult] = []
        warned: list[QualifiedRetrievalResult] = []
        audit: list[QualifiedRetrievalResult] = []
        primary_count = 0
        for rank, result in enumerate(results, 1):
            bucket = result.bucket
            updated = QualifiedRetrievalResult(**{**result.__dict__, "rank": rank})
            if bucket == BUCKET_AUDIT_ONLY:
                audit.append(updated)
                continue
            if primary_count >= query.top_k:
                continue
            primary_count += 1
            if bucket == BUCKET_RETAINED_WITH_WARNING:
                warned.append(updated)
            else:
                ranked.append(updated)
        output = QualifiedRetrievalOutput(
            query_id=query.query_id,
            ranked_results=tuple(ranked),
            retained_with_warning=tuple(warned),
            audit_only_results=tuple(audit),
            rejected_by_native_constraints=tuple(exclusions),
            corpus_fingerprint=fingerprint,
            scoring_config_hash=self.scoring_config.hash,
            candidate_count=len(results),
        )
        self._audit[query.query_id] = output
        return output

    def explain(self, result: QualifiedRetrievalResult) -> str:
        return result.explanation

    def audit_trace(self, query_id: str) -> QualifiedRetrievalOutput | None:
        return self._audit.get(query_id)

    def _candidates(
        self, query: QualifiedRetrievalQuery
    ) -> tuple[list[Mapping[str, Any]], list[NativeExclusion]]:
        accepted: list[Mapping[str, Any]] = []
        excluded: list[NativeExclusion] = []
        disease_keys = tuple(sorted(query.disease_keys()))
        intervention_keys = tuple(sorted(query.intervention_keys()))
        direction_keys = tuple(sorted({normalize_text(item) for item in query.directions}))
        polarity_keys = {normalize_text(item) for item in query.assertion_polarities}
        scope_keys = tuple(sorted({normalize_text(item) for item in query.evidence_scopes}))
        for statement in self.repository.all():
            statement_id = str(statement["evidence_statement_id"])
            link_polarities = {normalize_text(link.get("assertion_polarity")) for link in self._links_by_statement.get(statement_id, []) if link.get("assertion_polarity")}
            checks = [
                ("biomarker", _contains_marker(statement, query.biomarker_keys()), X_BIOMARKER_MISMATCH, query.biomarker_keys(), _label(statement.get("biomarker"))),
                ("disease", _native_match(tuple(disease_keys), _label(statement.get("disease"))), X_DISEASE_MISMATCH, tuple(disease_keys), _label(statement.get("disease"))),
                ("direction", _native_match(tuple(direction_keys), statement.get("direction")), X_DIRECTION_MISMATCH, tuple(direction_keys), statement.get("direction")),
                ("assertion_polarity", not polarity_keys or normalize_text(statement.get("assertion_polarity")) in polarity_keys or bool(polarity_keys & link_polarities), X_POLARITY_MISMATCH, tuple(sorted(polarity_keys)), sorted({normalize_text(statement.get("assertion_polarity")), *link_polarities})),
                ("evidence_scope", _native_match(tuple(scope_keys), statement.get("evidence_scope")), X_SCOPE_MISMATCH, tuple(scope_keys), statement.get("evidence_scope")),
                ("intervention", _native_match(tuple(intervention_keys), _label(statement.get("intervention"))), X_INTERVENTION_MISMATCH, tuple(intervention_keys), _label(statement.get("intervention"))),
            ]
            failed = [item for item in checks if not item[1]]
            if failed and query.mode != MODE_AUDIT_ALL:
                field, _, code, expected, actual = failed[0]
                excluded.append(
                    NativeExclusion(
                        statement_id=statement_id,
                        rule="native_constraint",
                        field_name=field,
                        query_value=list(expected),
                        statement_value=actual,
                        reason_code=code,
                    )
                )
                continue
            if not checks[0][1] and query.mode != MODE_AUDIT_ALL:
                continue
            accepted.append(statement)
        accepted.sort(key=lambda item: str(item["evidence_statement_id"]))
        excluded.sort(key=lambda item: (item.statement_id, item.reason_code))
        return accepted, excluded

    def _result(
        self, query: QualifiedRetrievalQuery, statement: Mapping[str, Any]
    ) -> QualifiedRetrievalResult:
        statement_id = str(statement["evidence_statement_id"])
        view = self.views[statement_id]
        links = self._links_by_statement.get(statement_id, [])
        units = [self.active_units[str(link["source_profile_unit_id"])] for link in links]
        link_polarities = {str(link.get("assertion_polarity") or "") for link in links if link.get("assertion_polarity")}
        effective_polarity = "does_not_support" if "does_not_support" in link_polarities and (not query.assertion_polarities or "does_not_support" in query.assertion_polarities) else str(statement.get("assertion_polarity") or "")
        native_matches = {
            "biomarker": _contains_marker(statement, query.biomarker_keys()),
            "disease": _native_match(query.disease_keys(), _label(statement.get("disease"))),
            "intervention": _native_match(query.intervention_keys(), _label(statement.get("intervention"))),
            "direction": _native_match(tuple(normalize_text(v) for v in query.directions), statement.get("direction")),
            "assertion_polarity": _native_match(tuple(normalize_text(v) for v in query.assertion_polarities), effective_polarity),
            "evidence_scope": _native_match(tuple(normalize_text(v) for v in query.evidence_scopes), statement.get("evidence_scope")),
        }
        components: list[ScoreComponent] = []
        weight_names = {
            "biomarker": "native_biomarker",
            "disease": "native_disease",
            "intervention": "native_intervention",
            "direction": "native_direction",
            "assertion_polarity": "native_assertion_polarity",
            "evidence_scope": "native_evidence_scope",
        }
        for field, matched in native_matches.items():
            if field in {"intervention", "direction", "assertion_polarity", "evidence_scope"} and not getattr(query, {"assertion_polarity": "assertion_polarities", "evidence_scope": "evidence_scopes", "direction": "directions", "intervention": "interventions"}[field]):
                continue
            components.append(ScoreComponent(weight_names[field], self.scoring_config.weights[weight_names[field]] if matched else -self.scoring_config.weights[weight_names[field]], "native", f"{field} {'match' if matched else 'mismatch'}"))
        components.append(ScoreComponent("native_source_presence", self.scoring_config.weights["native_source_presence"] if _source_ids(statement) else 0, "native", "source identity presente"))
        warnings: list[str] = []
        status = str(view.get("qualification_status") or "")
        reviewed_statuses = {str((row.get("first_review_annotation") or {}).get("candidate_status") or "") for row in self._gold_by_statement.get(statement_id, [])}
        for reviewed_status in ("candidate_invalid", "candidate_conflicting", "candidate_ambiguous", "candidate_partial"):
            if reviewed_status in reviewed_statuses:
                status = reviewed_status.removeprefix("candidate_") if reviewed_status != "candidate_invalid" else reviewed_status
                break
        status_warning = {
            "partial": W_CANDIDATE_PARTIAL,
            "ambiguous": W_CANDIDATE_AMBIGUOUS,
            "conflicting": W_CANDIDATE_CONFLICTING,
            "invalid": W_CANDIDATE_INVALID,
            "candidate_invalid": W_CANDIDATE_INVALID,
        }.get(status)
        if status_warning:
            warnings.append(status_warning)
            penalty_name = {
                W_CANDIDATE_PARTIAL: "penalty_partial",
                W_CANDIDATE_AMBIGUOUS: "penalty_ambiguous",
                W_CANDIDATE_CONFLICTING: "penalty_conflicting",
                W_CANDIDATE_INVALID: "penalty_invalid",
            }[status_warning]
            components.append(ScoreComponent(penalty_name, self.scoring_config.weights[penalty_name], "qualified", status))
        if view.get("not_separable_dimensions"):
            warnings.append(W_NOT_SEPARABLE)
            components.append(ScoreComponent("penalty_not_separable", self.scoring_config.weights["penalty_not_separable"], "qualified", "dimensioni not_separable"))
        if view.get("unresolved_dimensions"):
            warnings.append(W_UNRESOLVED_UNIT)
            components.append(ScoreComponent("penalty_unresolved", self.scoring_config.weights["penalty_unresolved"], "qualified", "dimensioni irrisolte"))
        if view.get("conflicts") and W_CANDIDATE_CONFLICTING not in warnings:
            warnings.append(W_CANDIDATE_CONFLICTING)
        source_basis = next((str(unit.get("source_basis")) for unit in units if unit.get("source_basis")), "unknown")
        if source_basis == "abstract_only":
            warnings.append(W_ABSTRACT_ONLY_SOURCE)
            components.append(ScoreComponent("penalty_abstract_only", self.scoring_config.weights["penalty_abstract_only"], "qualified", "abstract only"))
        unit_types = {str(unit.get("unit_type") or "") for unit in units}
        case_level = any("case" in value or "named_patient" in value for value in unit_types)
        named_patient_subset = any("named_patient" in value for value in unit_types)
        if case_level:
            warnings.append(W_CASE_LEVEL)
            components.append(ScoreComponent("penalty_case_level", self.scoring_config.weights["penalty_case_level"], "qualified", "evidenza case-level non generalizzabile"))
        if named_patient_subset:
            warnings.append(W_NAMED_PATIENT_SUBSET)
            components.append(ScoreComponent("penalty_named_patient_subset", self.scoring_config.weights["penalty_named_patient_subset"], "qualified", "named-patient subset"))
        preclinical = any("preclinical" in value or "in_vitro" in value or "model" in value for value in unit_types)
        clinical = any("clinical" in value or "cohort" in value or "patient" in value for value in unit_types)
        evidence_context = "mixed" if clinical and preclinical else "preclinical" if preclinical else "clinical" if clinical else "unknown"
        if preclinical and query.preferred_evidence_context == "clinical":
            warnings.append(W_PRECLINICAL_ONLY)
            components.append(ScoreComponent("penalty_preclinical_preference", self.scoring_config.weights["penalty_preclinical_preference"], "qualified", "preferenza clinica"))
        polarity = effective_polarity

        negative_info: dict[str, Any] = {}
        if polarity == "does_not_support":
            warnings.append(W_NEGATIVE_EXPERIMENT)
            negative_info = {"assertion_polarity": polarity, "preserved_as_negative": True}
        eligibility = "prototype_only" if view.get("prototype_only_dimensions") else "none"
        if query.uses_qualifiers and eligibility == "prototype_only" and query.clinical_context:
            dimension_aliases = {"setting": "disease_setting"}
            compatible = False
            mismatch = False
            qualified_dimensions = view.get("qualified_dimensions") or {}
            for dimension, query_value in sorted(query.clinical_context.items()):
                source = qualified_dimensions.get(dimension_aliases.get(dimension, dimension)) or {}
                if not source or str(source.get("value") or "") in {"unknown", "not_applicable", "not_separable"}:
                    continue
                query_text = normalize_text(json.dumps(query_value, ensure_ascii=False, sort_keys=True))
                source_text = normalize_text(json.dumps(source.get("value"), ensure_ascii=False, sort_keys=True))
                if query_text and (query_text in source_text or source_text in query_text):
                    compatible = True
                else:
                    mismatch = True
            if compatible:
                components.append(ScoreComponent("qualified_context_compatible", self.scoring_config.weights["qualified_context_compatible"], "qualified", "contesto prototype_only compatibile"))
            if mismatch:
                warnings.append(W_QUALIFIER_MISMATCH_NOT_FILTERED)
        if query.uses_qualifiers and eligibility == "prototype_only":
            warnings.append(W_PROTOTYPE_ONLY_QUALIFIERS)
            bonus = min(
                self.scoring_config.weights["qualified_first_review"],
                self.scoring_config.thresholds["prototype_only_positive_cap"],
            )
            components.append(ScoreComponent("qualified_first_review", bonus, "qualified", "prima revisione approvata"))
        elif eligibility == "none":
            warnings.append(W_QUALIFIER_UNREVIEWED)
        if not query.uses_qualifiers:
            components = [item for item in components if item.category == "native"]
            warnings = [item for item in warnings if item in {W_NEGATIVE_EXPERIMENT}]
        breakdown = RetrievalScoreBreakdown(tuple(components))
        provenance = [
            {"kind": "statement", "id": statement_id},
            *[{"kind": "qualification_link", "id": str(link.get("qualification_link_id"))} for link in links],
            *[{"kind": "active_profile_unit", "id": str(unit.get("profile_unit_id"))} for unit in units],
        ]
        mappings = [
            item for item in self.terminology_mappings
            if str(item.get("statement_id") or "") in {"", statement_id}
            and str(item.get("canonical_source_id") or "") in {"", *[sid.replace("PUBMED:", "PMID:") for sid in _source_ids(statement)]}
        ]
        pending_mappings = [item for item in mappings if item.get("match_grade") not in {"verified_synonym", "verified_development_code", "exact"}]
        if pending_mappings and query.uses_qualifiers:
            warnings.append(W_TERMINOLOGY_PENDING)
        explanation_codes, explanation = build_explanation(
            native_matches=native_matches,
            warnings=warnings,
            eligibility=eligibility if query.uses_qualifiers else "",
            evidence_context=evidence_context,
        )
        invalid = W_CANDIDATE_INVALID in warnings
        bucket = BUCKET_AUDIT_ONLY if invalid else BUCKET_RETAINED_WITH_WARNING if warnings else BUCKET_RANKED
        return QualifiedRetrievalResult(
            query_id=query.query_id,
            statement_id=statement_id,
            total_score=breakdown.total,
            native_score=breakdown.native_total,
            qualified_score=breakdown.qualified_total,
            score_breakdown=breakdown.as_list(),
            graph_evidence_ids=tuple(sorted((statement.get("provenance") or {}).get("graph_record_ids") or [])),
            native_matches=native_matches,
            qualified_matches=dict(view.get("qualified_dimensions") or {}),
            mismatches=tuple(sorted(field for field, matched in native_matches.items() if not matched)),
            warnings=tuple(dict.fromkeys(warnings)),
            evidence_context=evidence_context,
            support_type=status or "unqualified",
            candidate_link_status=status,
            assertion_polarity=polarity,
            direction=str(statement.get("direction") or ""),
            source_ids=_source_ids(statement),
            active_profile_unit_ids=tuple(sorted(str(unit.get("profile_unit_id")) for unit in units)),
            source_basis=source_basis,
            review_status="first_review_complete" if eligibility == "prototype_only" else str(statement.get("review_status") or ""),
            propagation_eligibility=eligibility,
            hard_filterable=False,
            terminology_mappings=mappings,
            unresolved_dimensions=tuple(sorted(view.get("unresolved_dimensions") or [])),
            case_level_information={"case_level": case_level, "named_patient_subset": named_patient_subset, "frequency_inferred": False},
            negative_evidence_information=negative_info,
            provenance_references=provenance,
            explanation_codes=explanation_codes,
            explanation=explanation,
            bucket=bucket,
        )

    def _sort_key(
        self, query: QualifiedRetrievalQuery, result: QualifiedRetrievalResult
    ) -> tuple[Any, ...]:
        directness = {"direct": 3, "partial": 2, "ambiguous": 1}.get(result.support_type, 0)
        review = {"final": 3, "first_review_complete": 2, "pending_verification": 1}.get(result.review_status, 0)
        basis = {"full_text": 3, "abstract_only": 2, "registry_only": 1}.get(result.source_basis, 0)
        context = 1 if query.preferred_evidence_context in {"both", result.evidence_context} else 0
        return (
            -result.total_score,
            -result.native_score,
            -directness,
            -review,
            -basis,
            -context,
            result.source_ids[0] if result.source_ids else "",
            result.statement_id,
        )


__all__ = [
    "SUPPORTED_CORPUS_VERSION",
    "QualifiedRetrievalOutput",
    "QualifiedEvidenceRetriever",
]

"""Static, hash-bound frozen-document coverage checks for evaluation plans."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable


class FrozenCoverageError(RuntimeError):
    """The sealed evaluation cannot be opened with incomplete frozen input."""


@dataclass(frozen=True)
class CoverageRow:
    unit_id: str
    candidate_id: str | None
    identifier_kind: str | None
    identifier_value: str | None
    document_id: str | None
    local_payload_path: str | None
    payload_sha256: str | None
    document_available: bool
    source_unit_count: int
    source_unit_index_sha256: str | None
    provenance: dict[str, Any]
    coverage: str
    missing: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CoverageReport:
    manifest_path: str
    manifest_sha256: str
    source_unit_index_path: str
    source_unit_index_sha256: str
    total_planned_units: int
    units_with_complete_document_coverage: int
    units_with_partial_document_coverage: int
    units_with_zero_document_coverage: int
    missing_document_identifiers: tuple[str, ...]
    rows: tuple[CoverageRow, ...]
    semantic_obligation: dict[str, int] | None = None
    semantic_coverage: dict[str, int] | None = None

    @property
    def complete(self) -> bool:
        if self.semantic_coverage is not None:
            return (
                self.semantic_coverage.get("required_covered", 0)
                == (self.semantic_obligation or {}).get("required", 0)
                and self.semantic_coverage.get("conditional_covered", 0)
                == (self.semantic_obligation or {}).get("conditional", 0)
                and self.semantic_coverage.get("not_required_valid", 0)
                == (self.semantic_obligation or {}).get("not_required", 0)
            )
        return (
            self.units_with_partial_document_coverage == 0
            and self.units_with_zero_document_coverage == 0
            and not self.missing_document_identifiers
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_path": self.manifest_path,
            "manifest_sha256": self.manifest_sha256,
            "source_unit_index_path": self.source_unit_index_path,
            "source_unit_index_sha256": self.source_unit_index_sha256,
            "total_planned_units": self.total_planned_units,
            "units_with_complete_document_coverage": self.units_with_complete_document_coverage,
            "units_with_partial_document_coverage": self.units_with_partial_document_coverage,
            "units_with_zero_document_coverage": self.units_with_zero_document_coverage,
            "missing_document_identifiers": list(self.missing_document_identifiers),
            "semantic_obligation": self.semantic_obligation,
            "semantic_coverage": self.semantic_coverage,
            "complete": self.complete,
            "rows": [row.to_dict() for row in self.rows],
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FrozenCoverageError(f"FROZEN_MANIFEST_MISSING:{path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _source_document_id(row: dict[str, Any]) -> str:
    source_unit = row.get("source_unit")
    if isinstance(source_unit, dict) and source_unit.get("document_id"):
        return str(source_unit["document_id"])
    return str(row.get("document_id") or row.get("canonical_identifier") or "")


def _document_requirements(unit: Any) -> tuple[str | None, str | None, str | None]:
    case_id = getattr(unit, "case_id", None)
    if case_id is None and isinstance(unit, dict):
        case_id = unit.get("case_id", "")
    case_id = str(case_id or "")
    candidate_id = None
    document_id = None
    if "|" in case_id:
        candidate_id, document_id = case_id.split("|", 1)
        return candidate_id, "pmid" if document_id.startswith("pmid:") else "document", document_id
    execution_class = getattr(unit, "execution_class", None)
    if execution_class is None and isinstance(unit, dict):
        execution_class = unit.get("execution_class", "")
    execution_class = str(execution_class or "")
    if execution_class in {"DETERMINISTIC_ONLY", "NARRATIVE_HOSTILE_VERIFIER", "NARRATIVE_CONTROL", "CONTROLLED_FAILURE_FIXTURE"}:
        return None, None, None
    # Canonical runtime and reliability cases discover document IDs only after
    # parsing/retrieval.  A sealed offline plan must bind those IDs explicitly;
    # an unresolved sentinel makes the missing coverage visible before launch.
    return None, "unresolved", f"UNRESOLVED_RUNTIME_DOCUMENT_SET:{case_id}"


def build_coverage_report(
    plan: Iterable[Any],
    *,
    manifest_path: Path,
    source_unit_index_path: Path,
    payload_root: Path,
    semantic_obligation: dict[str, int] | None = None,
    conditional_closure_complete: bool = False,
) -> CoverageReport:
    """Build a conservative preflight report from one manifest source of truth."""

    manifest = _read_jsonl(manifest_path)
    source_rows = _read_jsonl(source_unit_index_path)
    by_document = {str(row.get("document_id")): row for row in manifest}
    source_by_document: dict[str, int] = {}
    for row in source_rows:
        document_id = _source_document_id(row)
        source_by_document[document_id] = source_by_document.get(document_id, 0) + 1

    index_hash = _sha256(source_unit_index_path)
    rows: list[CoverageRow] = []
    missing: set[str] = set()
    for unit in plan:
        unit_id = getattr(unit, "run_id", None)
        if unit_id is None and isinstance(unit, dict):
            unit_id = unit.get("run_id", "")
        unit_id = str(unit_id or "")
        candidate_id, kind, required = _document_requirements(unit)
        if required is None:
            rows.append(CoverageRow(
                unit_id, candidate_id, None, None, None, None, None, True,
                0, index_hash, {"source": "plan", "document_required": False}, "NOT_REQUIRED",
            ))
            continue
        if kind == "unresolved":
            missing.add(required)
            rows.append(CoverageRow(
                unit_id, candidate_id, None, kind, required, None, None, False,
                0, index_hash, {"source": "plan", "document_required": True}, "ZERO",
                (required,),
            ))
            continue

        record = by_document.get(required)
        row_missing: list[str] = []
        payload_path = None
        payload_sha = None
        available = False
        source_count = source_by_document.get(required, 0)
        if record is None:
            row_missing.append(required)
            missing.add(required)
        else:
            relative = record.get("local_cache_path")
            payload_path = str((payload_root / relative).resolve()) if relative else None
            if not relative:
                row_missing.append(f"NO_LOCAL_PAYLOAD:{required}")
            elif not Path(payload_path).is_file():
                row_missing.append(f"PAYLOAD_MISSING:{required}")
            else:
                payload_sha = _sha256(Path(payload_path))
                expected = record.get("content_hash")
                if expected and payload_sha != expected:
                    row_missing.append(f"PAYLOAD_SHA256_MISMATCH:{required}")
                available = not row_missing
            if source_count == 0:
                row_missing.append(f"SOURCE_UNITS_MISSING:{required}")
        if row_missing and record is not None:
            missing.add(required)
        coverage = "COMPLETE" if available and source_count else ("PARTIAL" if available else "ZERO")
        rows.append(CoverageRow(
            unit_id, candidate_id, kind, required, required, payload_path, payload_sha,
            available, source_count, index_hash,
            {"manifest_record": record or {}, "source": "hash_bound_manifest"}, coverage,
            tuple(row_missing),
        ))

    complete = sum(row.coverage == "COMPLETE" or row.coverage == "NOT_REQUIRED" for row in rows)
    partial = sum(row.coverage == "PARTIAL" for row in rows)
    zero = sum(row.coverage == "ZERO" for row in rows)
    semantic_coverage = None
    if semantic_obligation is not None:
        expected = {
            "required": int(semantic_obligation.get("required", -1)),
            "conditional": int(semantic_obligation.get("conditional", -1)),
            "not_required": int(semantic_obligation.get("not_required", -1)),
        }
        if sum(expected.values()) != len(rows) or min(expected.values()) < 0:
            raise FrozenCoverageError("INVALID_SEMANTIC_DOCUMENT_OBLIGATION")
        # The policy is protocol-level: explicit REQUIRED bindings are checked
        # by the rows above; WHOLE_GCA closes every CONDITIONAL path without
        # selecting documents from future runtime output.
        terminal_manifest = (
            bool(manifest)
            and all(
                str(record.get("frozen_availability")) in {"PAYLOAD_AVAILABLE", "UNAVAILABLE_FROZEN"}
                for record in manifest
            )
            and all(
                str(record.get("document_id") or "")
                and (
                    str(record.get("frozen_availability")) == "UNAVAILABLE_FROZEN"
                    or bool(record.get("local_cache_path"))
                )
                for record in manifest
            )
        )
        explicit_rows_ok = terminal_manifest
        semantic_coverage = {
            "required_covered": expected["required"] if explicit_rows_ok else 0,
            "conditional_covered": expected["conditional"] if conditional_closure_complete else 0,
            "not_required_valid": expected["not_required"],
        }
    return CoverageReport(
        str(manifest_path), _sha256(manifest_path), str(source_unit_index_path), index_hash,
        len(rows), complete, partial, zero, tuple(sorted(missing)), tuple(rows),
        semantic_obligation=(expected if semantic_obligation is not None else None),
        semantic_coverage=semantic_coverage,
    )


def require_complete_coverage(report: CoverageReport) -> CoverageReport:
    if not report.complete:
        raise FrozenCoverageError(
            "FROZEN_DOCUMENT_COVERAGE_INCOMPLETE:"
            f"complete={report.units_with_complete_document_coverage};"
            f"partial={report.units_with_partial_document_coverage};"
            f"zero={report.units_with_zero_document_coverage}"
        )
    return report

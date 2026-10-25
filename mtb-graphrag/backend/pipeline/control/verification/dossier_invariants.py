"""Invarianti strutturali del dossier.

Separato da ``structural_text`` perché il contratto è diverso: qui si verifica
la **struttura** del dossier, non il testo del report, e servono input che il
verificatore testuale non ha (le verifiche documentali e il dossier stesso).

Un record ``uncertain`` o ``contradicted`` assente dal report finale è
corretto; assente dal *dossier* non lo è: deve comparire nelle sezioni
``review`` o ``excluded``, che è il punto in cui il MTB vede ciò che è stato
scartato e perché.
"""

from __future__ import annotations

from typing import Any, Sequence

from backend.pipeline.control.contracts import Projection, StructuralVerdict, Violation


def _expected_bucket(source_support_status: str, applicability_status: str) -> str:
    """Rideriva la sezione dai due assi, indipendentemente dal renderer."""
    if source_support_status == "contradicted":
        return "excluded"
    if source_support_status == "uncertain":
        return "review"
    if applicability_status == "not_compatible":
        return "supported_not_compatible"
    if applicability_status == "indeterminate":
        return "supported_indeterminate"
    return "supported_compatible"


class DossierInvariantVerifier:
    """Verifica partizione, bucketing e completezza del dossier."""

    def verify(
        self,
        projection: Projection,
        verifications: Sequence[Any],
        dossier: Any,
    ) -> StructuralVerdict:
        violations: list[Violation] = []
        entries = list(getattr(dossier, "evidence", ()) or ())

        # --- Partizione: nessun id ripetuto ---
        ids = [entry.evidence_id for entry in entries]
        duplicates = sorted({key for key in ids if ids.count(key) > 1})
        for duplicate in duplicates:
            violations.append(Violation(
                code="PARTITION_VIOLATION",
                severity="blocking",
                detail=f"L'evidenza '{duplicate}' compare in più di una voce del dossier.",
                canonical_record_id=duplicate,
            ))

        # --- Bucketing: ricalcolato, non riletto ---
        for entry in entries:
            expected = _expected_bucket(entry.source_support_status, entry.applicability_status)
            if entry.dossier_section != expected:
                violations.append(Violation(
                    code="BUCKET_DISAGREEMENT",
                    severity="blocking",
                    detail=(
                        f"Sezione '{entry.dossier_section}' incoerente con gli assi "
                        f"({entry.source_support_status}/{entry.applicability_status}): "
                        f"attesa '{expected}'."
                    ),
                    canonical_record_id=entry.evidence_id,
                ))

        # --- Ogni record verificato compare nel dossier ---
        missing: list[str] = []
        if len(verifications) == len(projection.admitted):
            for record, verification in zip(projection.admitted, verifications):
                if self._is_present(entries, record, verification):
                    continue
                missing.append(record.canonical_record_id)
                violations.append(Violation(
                    code="VERIFIED_RECORD_MISSING_FROM_DOSSIER",
                    severity="blocking",
                    detail=(
                        "Record verificato assente dal dossier: anche gli esiti "
                        "incerti o contraddetti devono restare visibili al MTB."
                    ),
                    canonical_record_id=record.canonical_record_id,
                ))

        coverage = 1.0
        if projection.admitted:
            coverage = (len(projection.admitted) - len(missing)) / len(projection.admitted)

        return StructuralVerdict(
            stage="dossier",
            violations=tuple(violations),
            missing_claims=tuple(missing),
            coverage=coverage,
        )

    @staticmethod
    def _is_present(entries: Sequence[Any], record: Any, verification: Any) -> bool:
        source = record.required_citation or record.claim.source_id
        for entry in entries:
            if entry.source_id and source and entry.source_id == source:
                return True
            if record.claim.subject and record.claim.subject.casefold() in entry.claim.casefold():
                return True
        return False

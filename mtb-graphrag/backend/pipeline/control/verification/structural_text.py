"""Verificatore strutturale sul testo del report.

Non importa nulla da ``rendering/``: analizza l'artefatto prodotto usando la
grammatica neutrale di ``claim_grammar``. Se lo facesse, "il report è
corretto" significherebbe soltanto "il renderer ha fatto ciò che fa".

Due passaggi con **insiemi attesi diversi**:

- *candidate*: l'atteso sono tutti i record ammessi dalla proiezione. Domanda:
  il renderer ha rappresentato fedelmente la proiezione?
- *final*: l'atteso è derivato dagli **esiti del source verifier**, cioè i soli
  record documentalmente supportati. Domanda: il report finale corrisponde a
  ciò che la verifica documentale ha effettivamente sostenuto?

Usare lo stesso atteso in entrambi produrrebbe un ``MISSING_CLAIM`` per ogni
record legittimamente filtrato dalla verifica: un record ``uncertain`` assente
dal report finale non è un'omissione, è il comportamento corretto.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.pipeline.control import claim_grammar as grammar
from backend.pipeline.control.contracts import (
    Projection,
    ProjectedRecord,
    StructuralVerdict,
    Violation,
)

SUPPORTED_STATUSES = frozenset({"supported_as_written", "supported_after_contextualization"})


class TextStructuralVerifier:
    """Verifica che un testo corrisponda all'insieme di record atteso."""

    def verify_candidate(self, projection: Projection, report: str) -> StructuralVerdict:
        return self._verify(
            stage="candidate",
            report=report,
            expected=projection.admitted,
            excluded=projection.excluded,
            applicability_by_id={},
        )

    def verify_final(
        self,
        projection: Projection,
        report: str,
        verifications: Sequence[Any],
        *,
        stage: str = "final",
    ) -> StructuralVerdict:
        """L'insieme atteso deriva dagli esiti del source verifier, non dalla proiezione."""
        by_id = self._verifications_by_record(projection, verifications)
        expected = tuple(
            record for record in projection.admitted
            if getattr(by_id.get(record.canonical_record_id), "source_support_status", None)
            in SUPPORTED_STATUSES
        )
        # Un record ammesso ma non supportato non è "atteso" nel testo, ma
        # nemmeno "escluso dalla proiezione": non deve generare né MISSING_CLAIM
        # né EXCLUDED_RECORD_RENDERED.
        not_supported = tuple(
            record for record in projection.admitted if record not in expected
        )
        applicability = {
            record_id: getattr(verification, "applicability_status", "indeterminate")
            for record_id, verification in by_id.items()
        }
        verdict = self._verify(
            stage=stage,  # type: ignore[arg-type]
            report=report,
            expected=expected,
            excluded=projection.excluded,
            applicability_by_id=applicability,
            tolerated=not_supported,
        )
        return verdict

    @staticmethod
    def _verifications_by_record(
        projection: Projection, verifications: Sequence[Any]
    ) -> dict[str, Any]:
        """Allinea le verifiche ai record ammessi, in ordine.

        L'allineamento posizionale è un'assunzione: se le lunghezze divergono
        il resto della verifica lo rileva come claim mancanti, invece di
        troncare silenziosamente come farebbe uno ``zip``.
        """
        admitted = projection.admitted
        return {
            admitted[index].canonical_record_id: verification
            for index, verification in enumerate(verifications)
            if index < len(admitted)
        }

    def _verify(
        self,
        *,
        stage: str,
        report: str,
        expected: Sequence[ProjectedRecord],
        excluded: Sequence[ProjectedRecord],
        applicability_by_id: Mapping[str, str],
        tolerated: Sequence[ProjectedRecord] = (),
    ) -> StructuralVerdict:
        violations: list[Violation] = []
        warnings: list[Violation] = []

        cited = grammar.extract_citations(report)
        expected_citations = {
            record.required_citation for record in expected if record.required_citation
        }
        tolerated_citations = {
            record.required_citation for record in tolerated if record.required_citation
        }

        # --- Citazioni spurie: ancora esatta, non euristica ---
        spurious = sorted(cited - expected_citations - tolerated_citations)
        for citation in spurious:
            violations.append(Violation(
                code="SPURIOUS_CITATION",
                severity="blocking",
                detail=f"Il testo cita {citation}, assente dall'insieme atteso.",
                excerpt=self._line_containing(report, citation),
            ))

        # --- Claim attese ma assenti ---
        missing = [
            record.canonical_record_id
            for record in expected
            if not grammar.claim_is_present(report, record.claim)
        ]
        for record_id in missing:
            violations.append(Violation(
                code="MISSING_CLAIM",
                severity="repairable",
                detail="Record atteso non rappresentato nel testo.",
                canonical_record_id=record_id,
            ))

        # --- Record esclusi dalla proiezione, resi comunque ---
        for record in excluded:
            if grammar.claim_is_present(report, record.claim):
                violations.append(Violation(
                    code="EXCLUDED_RECORD_RENDERED",
                    severity="blocking",
                    detail=f"Record escluso reso nel testo ({record.exclusion_reason}).",
                    canonical_record_id=record.canonical_record_id,
                ))

        # --- Ogni asserzione porta una citazione risolvibile ---
        unsupported: list[str] = []
        for line in grammar.asserted_lines(report):
            if not grammar.extract_citations(line):
                unsupported.append(line)
                violations.append(Violation(
                    code="UNSUPPORTED_CLAIM",
                    severity="blocking",
                    detail="Asserzione priva di citazione risolvibile.",
                    excerpt=line,
                ))

        # --- Entità strutturate: farmaci, biomarker, relazioni ---
        allowed_entities = {
            token
            for record in list(expected) + list(tolerated)
            for entity in record.entities
            for token in entity.split()
        }
        allowed_lexicon = {
            token for record in list(expected) + list(tolerated) for token in record.lexicon
        }
        for candidate in grammar.candidate_entities(report):
            if candidate in allowed_entities or candidate in allowed_lexicon:
                continue
            if any(candidate in entity for entity in allowed_entities):
                continue
            # LEXICON_VIOLATION resta diagnostico: l'euristica "token
            # farmaco-simile" è calibrabile solo su output reali e, se
            # bloccante da subito, fermerebbe report legittimi. La difesa
            # bloccante poggia su citazioni ed entità strutturate.
            warnings.append(Violation(
                code="LEXICON_VIOLATION",
                severity="advisory",
                detail=f"Token '{candidate}' non riconducibile a un record atteso.",
            ))

        # --- Formulazioni di raccomandazione ---
        non_compatible = any(
            applicability_by_id.get(record.canonical_record_id, "indeterminate") != "compatible"
            for record in expected
        )
        banned = grammar.banned_phrases_in(report)
        if banned and non_compatible:
            violations.append(Violation(
                code="RECOMMENDATION_WORDING",
                severity="blocking",
                detail=(
                    "Formulazione di raccomandazione con record ad applicabilità "
                    f"non compatibile: {', '.join(banned)}."
                ),
            ))

        # --- Coerenza aritmetica dell'intestazione ---
        declared = grammar.count_in_header(report, r"\((\d+) come formulate")
        if declared is not None:
            rendered = len(grammar.asserted_lines(report))
            if declared > rendered:
                violations.append(Violation(
                    code="COUNT_MISMATCH",
                    severity="repairable",
                    detail=f"Intestazione dichiara {declared} voci, il corpo ne contiene {rendered}.",
                ))

        # --- Conflitti non esposti ---
        for record in expected:
            if record.conflict_annotations and not self._conflict_surfaced(report, record):
                violations.append(Violation(
                    code="CONFLICT_UNSURFACED",
                    severity="repairable",
                    detail="Record con osservazioni discordanti reso senza segnalare il conflitto.",
                    canonical_record_id=record.canonical_record_id,
                ))

        coverage = 1.0 if not expected else (len(expected) - len(missing)) / len(expected)

        return StructuralVerdict(
            stage=stage,  # type: ignore[arg-type]
            violations=tuple(violations),
            warnings=tuple(warnings),
            missing_claims=tuple(missing),
            unsupported_claims=tuple(unsupported),
            spurious_citations=tuple(spurious),
            coverage=coverage,
        )

    @staticmethod
    def _conflict_surfaced(report: str, record: ProjectedRecord) -> bool:
        """Il conflitto è esposto se compare accanto alla claim che lo porta.

        Si cerca sulla riga del record, non nell'intero testo: una nota di
        conflitto relativa a un altro record non copre questo.
        """
        fields = {annotation.field_name.casefold() for annotation in record.conflict_annotations}
        for line in report.splitlines():
            lowered = line.casefold()
            if not grammar.claim_is_present(line, record.claim):
                continue
            if "conflitto" in lowered or "discord" in lowered:
                return True
            if any(field in lowered for field in fields):
                return True
        return False

    @staticmethod
    def _line_containing(report: str, needle: str) -> str | None:
        for line in report.splitlines():
            if needle in line:
                return line.strip()
        return None

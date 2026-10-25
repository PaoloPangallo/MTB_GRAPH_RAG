"""Test della proiezione e dei due verificatori strutturali."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase

from backend.pipeline.control.contracts import (
    CanonicalRecord,
    CanonicalView,
    CaseContext,
    ConflictAnnotation,
    OriginalClaim,
    Projection,
    ProjectedRecord,
)
from backend.pipeline.control.claim_grammar import entities_for, lexicon_for
from backend.pipeline.control.projection import project_for_case, projection_payload
from backend.pipeline.control.verification.dossier_invariants import DossierInvariantVerifier
from backend.pipeline.control.verification.structural_text import TextStructuralVerifier


def _case(goal: str = "general-review") -> CaseContext:
    return CaseContext(
        gene="EGFR", variant="L858R", tumor_type="Lung Adenocarcinoma",
        alteration_type="point_mutation", therapy_line="first-line", mtb_goal=goal,
    )


def _canonical(
    record_id: str = "c1",
    *,
    kind: str = "evidence",
    subject: str = "Osimertinib",
    obj: str = "EGFR L858R",
    source: str | None = "PMID:27959700",
    level: str = "A",
    conflicts: tuple = (),
) -> CanonicalRecord:
    return CanonicalRecord(
        canonical_record_id=record_id,
        record_kind=kind,  # type: ignore[arg-type]
        identity_key=(kind, subject.casefold()),
        original_claim=OriginalClaim(
            subject=subject, relation="SENSITIVITY", object=obj,
            context="Lung Adenocarcinoma", source_id=source, evidence_level=level,
        ),
        conflict_annotations=conflicts,
        completeness_status="complete",
    )


def _projected(record: CanonicalRecord, admitted: bool = True) -> ProjectedRecord:
    return ProjectedRecord(
        canonical_record_id=record.canonical_record_id,
        record_kind=record.record_kind,
        claim=record.original_claim,
        admitted=admitted,
        exclusion_reason=None if admitted else "escluso per test",
        required_citation=record.original_claim.source_id,
        lexicon=lexicon_for(record.original_claim),
        entities=entities_for(record.original_claim),
        conflict_annotations=record.conflict_annotations,
    )


def _projection(*records: ProjectedRecord) -> Projection:
    return Projection(run_id="r", case_label="EGFR L858R", records=records)


def _verification(status: str = "supported_as_written", applicability: str = "compatible"):
    return SimpleNamespace(
        source_support_status=status,
        applicability_status=applicability,
        source_support_reason="motivo",
        verification_level="pubmed_abstract",
        requires_source_review=False,
    )


class ProjectionTest(TestCase):
    def test_projection_starts_only_from_the_canonical_view(self) -> None:
        view = CanonicalView(run_id="r", records=(_canonical(),), records_in=1)

        projection = project_for_case(view, _case())

        self.assertEqual(len(projection.records), 1)
        self.assertEqual(projection.run_id, "r")
        self.assertTrue(projection.records[0].admitted)

    def test_records_without_a_citable_source_are_excluded_with_a_reason(self) -> None:
        view = CanonicalView(run_id="r", records=(_canonical(source=None),))

        projection = project_for_case(view, _case())

        self.assertFalse(projection.records[0].admitted)
        self.assertIn("fonte citabile", projection.records[0].exclusion_reason or "")

    def test_goal_restricts_the_admitted_record_kinds(self) -> None:
        view = CanonicalView(run_id="r", records=(
            _canonical("c1", kind="evidence"),
            _canonical("c2", kind="trial", subject="NCT02296125", source="NCT02296125"),
        ))

        projection = project_for_case(view, _case("treatment-evidence"))

        admitted = {record.canonical_record_id for record in projection.admitted}
        self.assertEqual(admitted, {"c1"})
        self.assertIn("non pertinente", projection.records[1].exclusion_reason or "")

    def test_low_evidence_levels_are_excluded(self) -> None:
        view = CanonicalView(run_id="r", records=(_canonical(level="D"),))

        self.assertFalse(project_for_case(view, _case()).records[0].admitted)

    def test_support_material_does_not_generate_claims(self) -> None:
        view = CanonicalView(run_id="r", records=(_canonical(kind="drug"),))

        projection = project_for_case(view, _case())

        self.assertFalse(projection.records[0].admitted)
        self.assertIn("materiale di supporto", projection.records[0].exclusion_reason or "")

    def test_payload_records_criteria_and_exclusions_for_the_ledger(self) -> None:
        view = CanonicalView(run_id="r", records=(_canonical(), _canonical("c2", source=None)))

        payload = projection_payload(project_for_case(view, _case()))

        self.assertEqual(payload["admitted"], 1)
        self.assertEqual(payload["excluded"], 1)
        self.assertTrue(payload["criteria"])
        self.assertEqual(payload["exclusions"][0]["canonical_record_id"], "c2")


class CandidateVerificationTest(TestCase):
    def setUp(self) -> None:
        self.verifier = TextStructuralVerifier()
        self.record = _canonical()
        self.projection = _projection(_projected(self.record))

    def test_faithful_report_passes(self) -> None:
        report = (
            "Caso: EGFR L858R.\nEvidenze candidate:\n"
            "- Osimertinib — SENSITIVITY — EGFR L858R (Lung Adenocarcinoma). [PMID:27959700]"
        )

        verdict = self.verifier.verify_candidate(self.projection, report)

        self.assertEqual(verdict.status, "pass")
        self.assertEqual(verdict.coverage, 1.0)

    def test_spurious_citation_is_blocking(self) -> None:
        report = (
            "Caso: EGFR L858R.\n"
            "- Osimertinib — SENSITIVITY — EGFR L858R (Lung Adenocarcinoma). [PMID:99999999]"
        )

        verdict = self.verifier.verify_candidate(self.projection, report)

        self.assertIn("PMID:99999999", verdict.spurious_citations)
        self.assertEqual(verdict.status, "violations_blocking")
        self.assertTrue(verdict.requires_human_review)
        self.assertFalse(verdict.requires_repair)

    def test_omitted_claim_is_repairable_and_lowers_coverage(self) -> None:
        verdict = self.verifier.verify_candidate(self.projection, "Caso: EGFR L858R.\n")

        self.assertEqual(verdict.missing_claims, ("c1",))
        self.assertTrue(verdict.requires_repair)
        self.assertEqual(verdict.coverage, 0.0)

    def test_rendering_an_excluded_record_is_blocking(self) -> None:
        excluded = _canonical("c2", subject="Gefitinib", source=None)
        projection = _projection(_projected(self.record), _projected(excluded, admitted=False))
        report = (
            "- Osimertinib — SENSITIVITY — EGFR L858R (Lung Adenocarcinoma). [PMID:27959700]\n"
            "- Gefitinib — SENSITIVITY — EGFR L858R (Lung Adenocarcinoma). [PMID:27959700]"
        )

        verdict = self.verifier.verify_candidate(projection, report)

        codes = {v.code for v in verdict.violations}
        self.assertIn("EXCLUDED_RECORD_RENDERED", codes)

    def test_assertion_without_a_citation_is_blocking(self) -> None:
        report = "- Osimertinib — SENSITIVITY — EGFR L858R (Lung Adenocarcinoma)."

        verdict = self.verifier.verify_candidate(self.projection, report)

        self.assertEqual(len(verdict.unsupported_claims), 1)
        self.assertIn("UNSUPPORTED_CLAIM", {v.code for v in verdict.violations})

    def test_unknown_token_is_only_a_warning(self) -> None:
        # L'euristica lessicale non blocca: la difesa bloccante poggia su
        # citazioni ed entità strutturate.
        report = (
            "- Osimertinib — SENSITIVITY — EGFR L858R (Lung Adenocarcinoma). [PMID:27959700]\n"
            "Nota: considerare anche Pembrolizumab."
        )

        verdict = self.verifier.verify_candidate(self.projection, report)

        self.assertEqual(verdict.status, "pass")
        self.assertIn("LEXICON_VIOLATION", {w.code for w in verdict.warnings})

    def test_unsurfaced_conflict_is_repairable(self) -> None:
        record = _canonical(conflicts=(ConflictAnnotation("evidence_level", ("A", "B")),))
        projection = _projection(_projected(record))
        report = "- Osimertinib — SENSITIVITY — EGFR L858R (Lung Adenocarcinoma). [PMID:27959700]"

        verdict = self.verifier.verify_candidate(projection, report)

        self.assertIn("CONFLICT_UNSURFACED", {v.code for v in verdict.violations})
        self.assertTrue(verdict.requires_repair)

    def test_surfaced_conflict_passes(self) -> None:
        record = _canonical(conflicts=(ConflictAnnotation("evidence_level", ("A", "B")),))
        projection = _projection(_projected(record))
        report = (
            "- Osimertinib — SENSITIVITY — EGFR L858R (Lung Adenocarcinoma). [PMID:27959700] "
            "— conflitto fra osservazioni sul livello di evidenza."
        )

        self.assertEqual(self.verifier.verify_candidate(projection, report).status, "pass")


class FinalVerificationTest(TestCase):
    def setUp(self) -> None:
        self.verifier = TextStructuralVerifier()
        self.supported = _canonical("c1")
        self.uncertain = _canonical("c2", subject="Gefitinib", source="PMID:11111111")
        self.projection = _projection(
            _projected(self.supported), _projected(self.uncertain)
        )

    def test_expected_set_derives_from_the_source_verifier_not_the_projection(self) -> None:
        # Il record incerto è legittimamente assente dal report finale: non
        # deve produrre MISSING_CLAIM.
        report = "- Osimertinib — SENSITIVITY — EGFR L858R (Lung Adenocarcinoma). [PMID:27959700]"
        verifications = [_verification(), _verification("uncertain", "indeterminate")]

        verdict = self.verifier.verify_final(self.projection, report, verifications)

        self.assertEqual(verdict.missing_claims, ())
        self.assertEqual(verdict.status, "pass")
        self.assertEqual(verdict.coverage, 1.0)

    def test_a_supported_record_missing_from_the_final_report_is_still_an_omission(self) -> None:
        report = "Caso: EGFR L858R.\n"
        verifications = [_verification(), _verification("uncertain")]

        verdict = self.verifier.verify_final(self.projection, report, verifications)

        self.assertEqual(verdict.missing_claims, ("c1",))
        self.assertTrue(verdict.requires_repair)

    def test_citation_of_an_unsupported_record_is_tolerated_not_spurious(self) -> None:
        # Citare un record scartato in una nota non è una fonte inventata.
        report = (
            "- Osimertinib — SENSITIVITY — EGFR L858R (Lung Adenocarcinoma). [PMID:27959700]\n"
            "Nota: PMID:11111111 non ha supporto documentale sufficiente."
        )
        verifications = [_verification(), _verification("uncertain")]

        verdict = self.verifier.verify_final(self.projection, report, verifications)

        self.assertEqual(verdict.spurious_citations, ())

    def test_recommendation_wording_with_non_compatible_applicability_is_blocking(self) -> None:
        report = (
            "- Osimertinib — SENSITIVITY — EGFR L858R (Lung Adenocarcinoma). [PMID:27959700]\n"
            "Terapia raccomandata per il paziente."
        )
        verifications = [_verification(applicability="not_compatible"), _verification("uncertain")]

        verdict = self.verifier.verify_final(self.projection, report, verifications)

        self.assertIn("RECOMMENDATION_WORDING", {v.code for v in verdict.violations})
        self.assertTrue(verdict.requires_human_review)

    def test_header_count_larger_than_body_is_repairable(self) -> None:
        report = (
            "Evidenze documentalmente supportate (3 come formulate, 0 dopo contestualizzazione):\n"
            "- Osimertinib — SENSITIVITY — EGFR L858R (Lung Adenocarcinoma). [PMID:27959700]"
        )
        verifications = [_verification(), _verification("uncertain")]

        verdict = self.verifier.verify_final(self.projection, report, verifications)

        self.assertIn("COUNT_MISMATCH", {v.code for v in verdict.violations})

    def test_narration_is_verified_with_the_same_rules(self) -> None:
        # È il caso in cui il verificatore non è tautologico: il testo non
        # proviene dal renderer deterministico.
        narration = (
            "In sintesi, Osimertinib — SENSITIVITY — EGFR L858R (Lung Adenocarcinoma) "
            "[PMID:27959700]. Si segnala inoltre Sotorasib [PMID:33538792]."
        )
        verifications = [_verification(), _verification("uncertain")]

        verdict = self.verifier.verify_final(
            self.projection, narration, verifications, stage="narration"
        )

        self.assertIn("PMID:33538792", verdict.spurious_citations)
        self.assertEqual(verdict.status, "violations_blocking")


class DossierInvariantTest(TestCase):
    def setUp(self) -> None:
        self.verifier = DossierInvariantVerifier()
        self.projection = _projection(_projected(_canonical()))

    def _entry(self, **kwargs):
        base = dict(
            evidence_id="c1", claim="Osimertinib — SENSITIVITY — EGFR L858R",
            source_id="PMID:27959700", source_support_status="supported_as_written",
            applicability_status="compatible", dossier_section="supported_compatible",
        )
        return SimpleNamespace(**{**base, **kwargs})

    def test_consistent_dossier_passes(self) -> None:
        dossier = SimpleNamespace(evidence=[self._entry()])

        verdict = self.verifier.verify(self.projection, [_verification()], dossier)

        self.assertEqual(verdict.status, "pass")

    def test_bucket_disagreement_is_detected_by_recomputation(self) -> None:
        dossier = SimpleNamespace(evidence=[self._entry(dossier_section="review")])

        verdict = self.verifier.verify(self.projection, [_verification()], dossier)

        self.assertIn("BUCKET_DISAGREEMENT", {v.code for v in verdict.violations})

    def test_duplicate_evidence_breaks_the_partition(self) -> None:
        dossier = SimpleNamespace(evidence=[self._entry(), self._entry()])

        verdict = self.verifier.verify(self.projection, [_verification()], dossier)

        self.assertIn("PARTITION_VIOLATION", {v.code for v in verdict.violations})

    def test_uncertain_record_must_still_appear_in_the_dossier(self) -> None:
        # Assente dal report finale è corretto; assente dal dossier no.
        dossier = SimpleNamespace(evidence=[])

        verdict = self.verifier.verify(
            self.projection, [_verification("uncertain", "indeterminate")], dossier
        )

        self.assertIn(
            "VERIFIED_RECORD_MISSING_FROM_DOSSIER", {v.code for v in verdict.violations}
        )

    def test_uncertain_record_in_the_review_section_passes(self) -> None:
        dossier = SimpleNamespace(evidence=[
            self._entry(source_support_status="uncertain",
                        applicability_status="indeterminate",
                        dossier_section="review")
        ])

        verdict = self.verifier.verify(
            self.projection, [_verification("uncertain", "indeterminate")], dossier
        )

        self.assertEqual(verdict.status, "pass")

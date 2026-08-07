"""ISS-002 — la polarità negativa della fonte non diventa supporto positivo.

Ogni test di questo modulo fallisce sull'implementazione precedente, che usava
``"support" in direction`` e quindi accettava anche ``"does not support"``.

L'ultimo test scorre **tutte** le candidate di
``graph_candidate_repository/2.0``: è l'equivalente v2 del controllo che esisteva
soltanto per v3.
"""

from __future__ import annotations

import json
import unittest

from backend.research_pipeline import data_access as da
from backend.research_pipeline.determinism.gates import (
    NON_SUPPORTING_POLARITIES,
    SOURCE_DOES_NOT_SUPPORT,
    SOURCE_DOES_NOT_SUPPORT_OUTCOME,
    SOURCE_NEUTRAL,
    SOURCE_SUPPORTS,
    SOURCE_UNKNOWN,
    candidate_source_polarity,
    clinical_direction,
    direction_consistency,
    evaluate_association,
    source_polarity,
)

ACCEPTED = [{"validation_outcome": "ENRICHMENT_ACCEPTED",
             "enrichment": {"evidence_kind": "RESPONSE"}}]


def _candidate(direction=None, evidence_direction=None):
    candidate = {"candidate_id": "GCA-TEST", "direction": direction}
    if evidence_direction is not None:
        candidate["source_properties"] = {"evidence": {"evidence_direction": evidence_direction}}
    return candidate


class SourcePolarityVocabulary(unittest.TestCase):
    """La polarità si legge per valore esatto, non per sottostringa."""

    def test_does_not_support_is_not_supports(self) -> None:
        self.assertEqual(source_polarity("Does Not Support"), SOURCE_DOES_NOT_SUPPORT)
        self.assertEqual(source_polarity("Supports"), SOURCE_SUPPORTS)
        self.assertNotEqual(source_polarity("Does Not Support"), SOURCE_SUPPORTS)

    def test_case_and_whitespace_insensitive(self) -> None:
        for raw in ("does not support", "DOES NOT SUPPORT", "  Does  Not   Support  ",
                    "Does-Not-Support"):
            with self.subTest(raw=raw):
                self.assertEqual(source_polarity(raw), SOURCE_DOES_NOT_SUPPORT)

    def test_null_empty_and_unmapped_are_unknown_not_supports(self) -> None:
        for raw in (None, "", "   ", "Unmapped Value", "N/A", 0, []):
            with self.subTest(raw=raw):
                self.assertEqual(source_polarity(raw), SOURCE_UNKNOWN)

    def test_neutral_and_contradicts_are_non_supporting(self) -> None:
        self.assertIn(source_polarity("Neutral"), NON_SUPPORTING_POLARITIES)
        self.assertIn(source_polarity("No Difference"), NON_SUPPORTING_POLARITIES)
        self.assertIn(source_polarity("Contradicts"), NON_SUPPORTING_POLARITIES)

    def test_unknown_is_not_a_non_supporting_polarity_but_never_positive(self) -> None:
        # UNKNOWN non e' una negazione: non deve marcare la candidate come
        # "fonte contraria". Ma non puo' nemmeno produrre supporto da solo.
        self.assertNotIn(SOURCE_UNKNOWN, NON_SUPPORTING_POLARITIES)
        self.assertEqual(direction_consistency(None, "RESPONSE"), "UNRELATED")
        self.assertEqual(direction_consistency("Unmapped Value", "RESPONSE"), "UNRELATED")


class ClinicalDirectionVocabulary(unittest.TestCase):
    """`Reduced Sensitivity` e `Adverse Response` sono avverse, non positive."""

    def test_adverse_directions_are_not_sensitivity(self) -> None:
        self.assertEqual(clinical_direction("Reduced Sensitivity"), "RESISTANCE")
        self.assertEqual(clinical_direction("Adverse Response"), "RESISTANCE")
        self.assertEqual(clinical_direction("Sensitivity/Response"), "SENSITIVITY")
        self.assertEqual(clinical_direction("Resistance"), "RESISTANCE")

    def test_adverse_direction_with_positive_report_is_conflicting_not_consistent(self) -> None:
        for direction in ("Reduced Sensitivity", "Adverse Response"):
            with self.subTest(direction=direction):
                self.assertEqual(direction_consistency(direction, "RESPONSE"), "CONFLICTING")
                self.assertEqual(direction_consistency(direction, "BENEFIT"), "CONFLICTING")


class DoesNotSupportNeverBecomesSupported(unittest.TestCase):
    """Il cuore di ISS-002."""

    def test_direction_consistency_flags_the_source(self) -> None:
        self.assertEqual(direction_consistency("Does Not Support", "RESPONSE"),
                         SOURCE_DOES_NOT_SUPPORT_OUTCOME)
        self.assertEqual(direction_consistency("Does Not Support", "BENEFIT"),
                         SOURCE_DOES_NOT_SUPPORT_OUTCOME)
        self.assertNotEqual(direction_consistency("Does Not Support", "RESPONSE"), "CONSISTENT")

    def test_accepted_enrichment_does_not_reach_primary_bucket(self) -> None:
        result = evaluate_association("THERAPY_EVALUATION",
                                      _candidate(direction="Does Not Support"), ACCEPTED)
        self.assertNotEqual(result["gate_bucket"], "PRIMARY_BUCKET")
        self.assertNotEqual(result["status"], "DIRECT")
        self.assertNotEqual(result["support_mask"]["direction"], "SUPPORTED")
        self.assertEqual(result["support_mask"]["direction"], SOURCE_DOES_NOT_SUPPORT_OUTCOME)
        self.assertTrue(result["warnings"], "un rigetto per polarita' deve essere motivato")

    def test_polarity_read_from_source_properties_when_direction_is_clinical(self) -> None:
        """Il caso reale: direction='Sensitivity/Response' ma la fonte non supporta.

        E' la forma di 213 candidate v2, fra cui l'unica raggiungibile end-to-end.
        """
        candidate = _candidate(direction="Sensitivity/Response",
                               evidence_direction="Does Not Support")
        self.assertEqual(candidate_source_polarity(candidate), SOURCE_DOES_NOT_SUPPORT)
        result = evaluate_association("THERAPY_EVALUATION", candidate, ACCEPTED)
        self.assertNotEqual(result["gate_bucket"], "PRIMARY_BUCKET")
        self.assertNotEqual(result["support_mask"]["direction"], "SUPPORTED")

    def test_negative_polarity_with_rejected_enrichment_stays_ambiguous(self) -> None:
        # Un enrichment rigettato non raggiunge i gate: la lista arriva vuota.
        result = evaluate_association("THERAPY_EVALUATION",
                                      _candidate(direction="Does Not Support"), [])
        self.assertEqual(result["gate_bucket"], "WARNING_BUCKET")
        self.assertEqual(result["support_mask"]["direction"], "NO_DOCUMENT_SIGNAL")

    def test_no_automatic_direction_inversion(self) -> None:
        """Una fonte negativa non diventa una claim di resistenza."""
        result = evaluate_association("THERAPY_EVALUATION",
                                      _candidate(direction="Does Not Support"), ACCEPTED)
        self.assertNotIn("CONSISTENT", result["direction_consistencies"])
        self.assertNotEqual(result["status"], "CONTRADICTED",
                            "la fonte che non supporta non equivale a evidenza di resistenza")


class PositiveDirectionsStillWork(unittest.TestCase):
    """La policy esistente per le direzioni positive non è indebolita."""

    def test_supports_with_positive_report_remains_consistent(self) -> None:
        result = evaluate_association("THERAPY_EVALUATION", _candidate(direction="Supports"), ACCEPTED)
        self.assertEqual(result["gate_bucket"], "PRIMARY_BUCKET")
        self.assertEqual(result["status"], "DIRECT")

    def test_sensitivity_with_positive_report_remains_consistent(self) -> None:
        result = evaluate_association("THERAPY_EVALUATION",
                                      _candidate(direction="Sensitivity/Response"), ACCEPTED)
        self.assertEqual(result["gate_bucket"], "PRIMARY_BUCKET")

    def test_resistance_with_resistance_report_remains_consistent(self) -> None:
        validated = [{"validation_outcome": "ENRICHMENT_ACCEPTED",
                      "enrichment": {"evidence_kind": "RESISTANCE"}}]
        result = evaluate_association("THERAPY_EVALUATION",
                                      _candidate(direction="Resistance"), validated)
        self.assertEqual(result["gate_bucket"], "PRIMARY_BUCKET")

    def test_resistance_with_positive_report_is_contradicted(self) -> None:
        result = evaluate_association("THERAPY_EVALUATION",
                                      _candidate(direction="Resistance"), ACCEPTED)
        self.assertEqual(result["status"], "CONTRADICTED")
        self.assertEqual(result["gate_bucket"], "REJECTED_BUCKET")


class WholeRepositorySweep(unittest.TestCase):
    """Nessuna candidate a polarità negativa può essere promossa. Su tutte."""

    @classmethod
    def setUpClass(cls) -> None:
        path = da.candidates_path()
        if not path.is_file():  # pragma: no cover
            raise unittest.SkipTest(f"repository non disponibile: {path}")
        cls.candidates = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    cls.candidates.append(json.loads(line))

    def test_no_negative_source_is_ever_promoted(self) -> None:
        promoted = []
        negative_seen = 0
        for candidate in self.candidates:
            polarity = candidate_source_polarity(candidate)
            adverse = clinical_direction(candidate.get("direction")) == "RESISTANCE"
            if polarity not in NON_SUPPORTING_POLARITIES and not adverse:
                continue
            negative_seen += 1
            for kind in ("RESPONSE", "BENEFIT"):
                if direction_consistency(candidate.get("direction"), kind,
                                         source_polarity_value=polarity) == "CONSISTENT":
                    promoted.append((candidate["candidate_id"], candidate.get("direction"), kind))
        self.assertGreater(negative_seen, 0, "il repository deve contenere candidate negative")
        self.assertEqual(promoted, [], f"{len(promoted)} candidate negative promosse a CONSISTENT")

    def test_no_negative_source_reaches_primary_bucket(self) -> None:
        in_primary = []
        for candidate in self.candidates:
            if candidate_source_polarity(candidate) not in NON_SUPPORTING_POLARITIES:
                continue
            result = evaluate_association("THERAPY_EVALUATION", candidate, ACCEPTED)
            if result["gate_bucket"] == "PRIMARY_BUCKET":
                in_primary.append(candidate["candidate_id"])
        self.assertEqual(in_primary, [],
                         f"{len(in_primary)} candidate a fonte negativa nel bucket primario")

    def test_known_reachable_regression_case(self) -> None:
        """GCA-003ca9889b3d8906d4674f37: l'unica candidate negativa con un bundle.

        Fixture reale individuata dall'audit: direction='Sensitivity/Response',
        evidence_direction='Does Not Support'.
        """
        target = next((c for c in self.candidates
                       if c["candidate_id"] == "GCA-003ca9889b3d8906d4674f37"), None)
        if target is None:  # pragma: no cover
            self.skipTest("candidate di regressione assente dal repository")
        self.assertEqual(candidate_source_polarity(target), SOURCE_DOES_NOT_SUPPORT)
        result = evaluate_association("THERAPY_EVALUATION", target, ACCEPTED)
        self.assertNotEqual(result["gate_bucket"], "PRIMARY_BUCKET")
        self.assertNotEqual(result["support_mask"]["direction"], "SUPPORTED")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

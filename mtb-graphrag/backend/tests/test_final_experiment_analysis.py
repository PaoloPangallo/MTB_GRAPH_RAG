from __future__ import annotations

import unittest

from benchmarks.mtb_evidence.final_experiment.analysis import (
    agentic_summary,
    bootstrap_interval,
    classify_failure,
    paired_differences,
    paired_effect_size,
)


class FinalExperimentAnalysisTests(unittest.TestCase):
    def test_paired_differences(self) -> None:
        self.assertEqual(paired_differences([0.5, 0.75], [0.25, 0.5]), [0.25, 0.25])

    def test_bootstrap_constant_vector(self) -> None:
        self.assertEqual(bootstrap_interval([0.25] * 4, seed=7), (0.25, 0.25))

    def test_agentic_five_run_summary(self) -> None:
        summary = agentic_summary([1, 2, 3, 4, 5])
        self.assertEqual(summary["n"], 5)
        self.assertEqual(summary["mean"], 3.0)
        self.assertEqual(summary["min"], 1.0)
        self.assertEqual(summary["max"], 5.0)
        self.assertAlmostEqual(summary["sd"], 2.5 ** 0.5)

    def test_paired_effect_and_failure_stage(self) -> None:
        effect = paired_effect_size([2, 4, 7], [1, 2, 4])
        self.assertEqual(effect["mean_difference"], 2.0)
        self.assertIsNotNone(effect["standardized_mean_difference"])
        self.assertEqual(
            classify_failure(candidates_generated=True, retrieval_complete=False),
            "retrieval",
        )
        self.assertIsNone(classify_failure())

if __name__ == "__main__":
    unittest.main()

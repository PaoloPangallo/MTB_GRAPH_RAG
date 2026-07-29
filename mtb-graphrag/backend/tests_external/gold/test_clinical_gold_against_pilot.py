"""Il clinical gold confrontato con il gold pilota.

Il gold pilota e' un ingresso esterno privato: non sta nel repository, e finche'
una copia era tracciata sotto `pilot/input/` questo confronto sembrava un test
interno. Non lo era — leggeva materiale clinico riservato che il repository non
avrebbe dovuto contenere.
"""

from __future__ import annotations

import json
import unittest

from benchmarks.mtb_evidence.evaluation import external_inputs as EXTERNAL
from benchmarks.mtb_evidence.evaluation.clinical_gold import (
    build_from_pilot,
    verify_no_loss,
)

PILOT_GOLD = (
    EXTERNAL.require(EXTERNAL.GOLD_BUNDLE) / "mtb_evidence_gold_pilot_v1.jsonl"
)


class GoldSeparationTests(unittest.TestCase):
    def test_clinical_gold_matches_the_pilot_without_loss(self) -> None:
        records = [
            json.loads(line)
            for line in PILOT_GOLD.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(verify_no_loss(records, build_from_pilot(PILOT_GOLD)), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

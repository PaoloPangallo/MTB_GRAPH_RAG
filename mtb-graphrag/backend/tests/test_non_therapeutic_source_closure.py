"""Cio' che la chiusura delle fonti non-terapeutiche lascia verificabile senza cache.

Le classi che aprono la cache degli abstract stanno in
`backend/tests_external/source_cache/`. Qui restano i due controlli che non la
toccano: che il perimetro a monte sia rimasto fermo, e che la fase non importi
niente di operativo. Prima saltavano insieme alle altre quarantuno quando la
cache mancava, pur non avendone bisogno.
"""

from __future__ import annotations

import hashlib
import json
import unittest

from benchmarks.mtb_evidence.evaluation import external_inputs as EXTERNAL
from pathlib import Path

from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation.scripts.build_non_therapeutic_source_closure import (
    BLINDED_FIELDS,
    build,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
OUT = V3 / "non_therapeutic_source_closure"
SHADOW_V11 = V3 / "non_therapeutic_shadow_update"
SHADOW_V10 = V3 / "typed_claim_shadow_migration"
CORPUS = V3 / "qualification_corpus_v2"

START_SHA = "771e30d0178c1aadbcc3ec5ff21dacfcd28f1238"
# La fase si chiude sull'ultimo commit di contenuto. L'estremo e' fisso e non
# `HEAD`, che cresce a ogni commit successivo e riporterebbe il controllo a
# essere aperto.
PHASE_END_SHA = "99d9dd83e8bd267e34608f3df3fedb4fb72cdd62"

FROZEN_OPERATIONAL_PATHS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/active_source_profile_units.jsonl",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]



# La verifica «nulla di congelato e' stato toccato» sta in
# `backend/tests_history/test_untouched_artifacts.py`: confronta con una
# revisione di partenza, e senza storia git quel termine non esiste.



class TestIsolation(unittest.TestCase):
    def source(self) -> Path:
        return (
            REPO_ROOT
            / "benchmarks/mtb_evidence/evaluation/scripts/build_non_therapeutic_source_closure.py"
        )

    def test_the_gold_is_never_read(self) -> None:
        blob = self.source().read_text(encoding="utf-8").lower()
        for fragment in (
            "clinical_gold",
            "snapshot_gold",
            "statement_qualification_gold",
            "gold_pilot",
            "evaluation_gold_snapshot",
            "mtb_evidence_gold",
            "recall@",
            "precision@",
        ):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, blob)

    def test_the_generator_makes_no_network_call(self) -> None:
        """L'acquisizione e' avvenuta in revisione; la generazione e' offline."""
        imports = [
            line.strip()
            for line in self.source().read_text(encoding="utf-8").splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in imports:
            for fragment in ("requests", "httpx", "urllib", "socket", "subprocess"):
                with self.subTest(line=line, fragment=fragment):
                    self.assertNotIn(fragment, line)

    def test_no_operational_module_imports_this_review(self) -> None:
        evidence = REPO_ROOT / "backend/pipeline/evidence"
        for path in sorted(evidence.rglob("*.py")):
            imports = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
            with self.subTest(module=str(path.relative_to(evidence))):
                for line in imports:
                    self.assertNotIn("source_closure", line)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

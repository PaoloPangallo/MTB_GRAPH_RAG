"""Gli ingressi privati non sono nel repository.

E' una proprieta' del **repository**, non del checkout: si verifica con
`git ls-files` e `git check-ignore`, e senza storia non e' verificabile. Un
archivio estratto puo' dire che un file non c'e', non che non e' tracciato — e
le due cose non coincidono, perche' un file puo' mancare da un archivio ed
essere tracciato lo stesso.

Stavano in `backend/tests/test_external_input_isolation.py`, dove si dichiaravano
saltati appena mancava `.git`.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GIT_ROOT = REPO_ROOT.parent

# I tre file del bundle, per path esatto. Il glob da solo non basta: le note di
# annotazione sono materiale dello stesso bundle e portano un nome che
# `*gold_pilot*` non intercetta. Un test che si fida di un glob afferma meno di
# quel che sembra.
PRIVATE_COPIES = (
    "mtb-graphrag/benchmarks/mtb_evidence/pilot/input/MTB_Evidence_gold_pilot_v1.xlsx",
    "mtb-graphrag/benchmarks/mtb_evidence/pilot/input/mtb_evidence_gold_pilot_v1.jsonl",
    "mtb-graphrag/benchmarks/mtb_evidence/pilot/input/"
    "MTB_Evidence_annotation_notes_v1.md",
)


class NotTrackedTests(unittest.TestCase):
    def _tracked(self, pattern: str) -> list[str]:
        result = subprocess.run(
            ["git", "ls-files", pattern],
            cwd=GIT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return [line for line in result.stdout.splitlines() if line.strip()]

    def test_the_gold_bundle_is_not_tracked(self) -> None:
        self.assertEqual(self._tracked("MTB_Evidence_gold_pilot_v1_bundle/*"), [])

    def test_the_abstract_cache_is_not_tracked(self) -> None:
        self.assertEqual(self._tracked("*source_abstract_cache.jsonl"), [])

    def test_no_private_copy_is_tracked_under_the_package(self) -> None:
        for path in PRIVATE_COPIES:
            with self.subTest(path=path):
                self.assertEqual(self._tracked(path), [])

    def test_no_copy_of_the_gold_is_tracked_at_all(self) -> None:
        self.assertEqual(self._tracked("*gold_pilot*"), [])

    def test_the_private_copies_are_ignored_so_they_cannot_return(self) -> None:
        """Rimuoverle non basta: un `git add -A` distratto le rimetterebbe."""
        for path in PRIVATE_COPIES:
            with self.subTest(path=path):
                result = subprocess.run(
                    ["git", "check-ignore", "-q", path],
                    cwd=GIT_ROOT,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, f"{path} non e' ignorato")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

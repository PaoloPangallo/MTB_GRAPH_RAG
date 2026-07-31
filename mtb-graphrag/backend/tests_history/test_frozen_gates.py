"""Cio' che una fase dichiara congelato non e' cambiato da allora.

«Da allora» e' la parte che richiede la storia: il confronto e' fra la revisione
di partenza della fase e HEAD, e senza `.git` il primo termine non esiste.

Il confronto e' sul **contenuto**, non sui byte: `_normalised` collassa CRLF in
LF prima di confrontare. Non e' una maglia larga — e' cio' che rende il
controllo capace di distinguere una modifica da una dichiarazione di fine riga,
che e' precisamente la distinzione su cui questa fase e' costruita.

Spostati da `test_v3_conjunctive_query_closure.py` e
`test_v3_retriever_regression_closure.py`, dove si dichiaravano saltati appena
mancava la storia.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from backend.tests.test_v3_conjunctive_query_closure import (
    FROZEN_PATHS,
    START_SHA as CONJUNCTIVE_START,
)
from backend.tests.test_v3_retriever_regression_closure import (
    START_SHA as REGRESSION_START,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GIT_ROOT = REPO_ROOT.parent

GATE_1_1_MODULES = (
    "backend/pipeline/evidence/shadow/integrated_gates_v11.py",
    "backend/pipeline/evidence/shadow/integrated_gates.py",
    "backend/pipeline/evidence/shadow/structural_gates.py",
    "benchmarks/mtb_evidence/evaluation/claim_type_retrieval_contract.py",
)

_GIT_TIMEOUT_SECONDS = 120


def _git(*args: str, cwd: Path = GIT_ROOT) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        timeout=_GIT_TIMEOUT_SECONDS,
    ).stdout


class FrozenGateContentTests(unittest.TestCase):
    """Il contenuto dei gate congelati e' identico alla revisione di partenza."""

    def _normalised(self, revision: str) -> bytes:
        blob = subprocess.run(
            ["git", "show", revision],
            cwd=GIT_ROOT,
            capture_output=True,
            check=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        ).stdout
        return blob.replace(b"\r\n", b"\n")

    def _touched_frozen_paths(self) -> set[str]:
        touched = _git(
            "diff",
            "--name-only",
            CONJUNCTIVE_START,
            "--",
            *[f"mtb-graphrag/{path}" for path in FROZEN_PATHS],
        )
        return {
            line.removeprefix("mtb-graphrag/")
            for line in touched.splitlines()
            if line.strip()
        }

    def test_the_frozen_gates_are_unchanged(self) -> None:
        for path in sorted(self._touched_frozen_paths()):
            with self.subTest(path=path):
                self.assertEqual(
                    self._normalised(f"{CONJUNCTIVE_START}:mtb-graphrag/{path}"),
                    self._normalised(f"HEAD:mtb-graphrag/{path}"),
                    f"{path}: il contenuto congelato e' cambiato",
                )

    def test_no_frozen_path_differs_even_by_a_byte(self) -> None:
        """Dopo il revert del `\\r`, nemmeno un byte.

        Il commit `33b92ec` ha rimesso `qualified_retriever.py` nella forma
        canonica: l'unica deroga byte-level che questo repository avesse non
        esiste piu', e questo test lo dice invece di lasciarlo dedurre da una
        costante rimasta a dichiarare un'eccezione che non serve piu'.
        """
        self.assertEqual(self._touched_frozen_paths(), set())

    def test_the_gate_1_1_modules_are_unchanged(self) -> None:
        changed = _git(
            "diff", "--name-only", REGRESSION_START, "--", *GATE_1_1_MODULES,
            cwd=REPO_ROOT,
        )
        self.assertEqual(
            [line for line in changed.splitlines() if line.strip()], []
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

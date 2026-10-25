"""Protegge l'helper di perimetro dal difetto che ha colpito quattro fasi.

Il difetto e' sempre lo stesso: misurare il perimetro di una fase confrontando il
suo SHA iniziale con l'albero di lavoro. I test qui costruiscono un repository
git temporaneo che simula esattamente quella situazione — una fase chiusa,
seguita da una fase successiva che scrive file nuovi fuori dal perimetro della
prima — e verificano che l'intervallo chiuso resti verde mentre il confronto con
l'albero di lavoro fallirebbe.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.tests.phase_scope import (
    PhaseScope,
    changed_paths_in_closed_interval,
    paths_outside_prefixes,
)

PHASE_PREFIX = "benchmarks/mtb_evidence/v3/first_phase/"
LATER_PREFIX = "benchmarks/mtb_evidence/v3/later_phase/"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return result.stdout


def _write(repo: Path, relative: str, content: str) -> None:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


class TestClosedIntervalPhaseScope(unittest.TestCase):
    """Una fase chiusa non deve piu' vedere cio' che scrive la fase seguente."""

    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("git") is None:
            raise unittest.SkipTest("git non disponibile")
        cls._tmp = tempfile.TemporaryDirectory()
        repo = Path(cls._tmp.name) / "repo"
        repo.mkdir()
        cls.repo = repo

        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "phase@example.invalid")
        _git(repo, "config", "user.name", "Phase Guard")
        _git(repo, "config", "commit.gpgsign", "false")

        # Commit iniziale: lo stato da cui la prima fase parte.
        _write(repo, "mtb-graphrag/backend/pipeline/evidence/v2_adapter.py", "# operativo\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "base")
        cls.start_sha = _git(repo, "rev-parse", "HEAD").strip()

        # La prima fase scrive solo dentro al proprio perimetro e si chiude.
        _write(repo, f"mtb-graphrag/{PHASE_PREFIX}artifact.jsonl", '{"a": 1}\n')
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "first phase")
        cls.end_sha = _git(repo, "rev-parse", "HEAD").strip()

        # La fase successiva scrive file nuovi, fuori dal perimetro della prima.
        _write(repo, f"mtb-graphrag/{LATER_PREFIX}shadow.jsonl", '{"b": 2}\n')
        _write(repo, "mtb-graphrag/backend/tests/test_later_phase.py", "# nuovo\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "later phase")
        cls.later_sha = _git(repo, "rev-parse", "HEAD").strip()

        # E lascia anche lavoro non committato nell'albero di lavoro: una
        # modifica a un file tracciato, che il confronto aperto vede e
        # l'intervallo chiuso ignora.
        _write(repo, f"mtb-graphrag/{LATER_PREFIX}shadow.jsonl", '{"b": 2, "wip": true}\n')

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def scope(self) -> PhaseScope:
        return PhaseScope(
            self.repo, self.start_sha, self.end_sha, (PHASE_PREFIX,)
        )

    def test_the_closed_interval_sees_only_what_the_phase_itself_wrote(self) -> None:
        changed = self.scope().changed_paths()
        self.assertEqual(changed, {f"{PHASE_PREFIX}artifact.jsonl"})

    def test_a_later_phase_does_not_violate_the_earlier_perimeter(self) -> None:
        scope = self.scope()
        self.assertEqual(scope.violations(scope.changed_paths()), [])

    def test_the_open_ended_comparison_is_the_defect_being_prevented(self) -> None:
        """Il confronto con l'albero di lavoro vede la fase successiva."""
        result = subprocess.run(
            ["git", "diff", "--name-only", self.start_sha],
            cwd=self.repo,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        open_ended = {
            line.strip().removeprefix("mtb-graphrag/")
            for line in result.stdout.splitlines()
            if line.strip()
        }
        # Vede file che la prima fase non ha mai scritto — sia quelli committati
        # dalla fase successiva sia le sue modifiche non committate: e' il falso
        # positivo che faceva fallire il test della fase gia' chiusa.
        self.assertIn(f"{LATER_PREFIX}shadow.jsonl", open_ended)
        self.assertIn("backend/tests/test_later_phase.py", open_ended)
        self.assertNotIn(
            f"{LATER_PREFIX}shadow.jsonl", self.scope().changed_paths()
        )
        self.assertNotEqual(
            paths_outside_prefixes(open_ended, (PHASE_PREFIX,)),
            [],
            "il confronto aperto deve segnalare violazioni inesistenti",
        )

    def test_the_perimeter_still_catches_a_real_violation(self) -> None:
        """Se la fase avesse davvero sconfinato, l'intervallo chiuso lo vede."""
        scope = PhaseScope(
            self.repo, self.start_sha, self.later_sha, (PHASE_PREFIX,)
        )
        violations = scope.violations(scope.changed_paths())
        self.assertIn(f"{LATER_PREFIX}shadow.jsonl", violations)
        self.assertIn("backend/tests/test_later_phase.py", violations)

    def test_the_package_prefix_is_stripped_once(self) -> None:
        for path in self.scope().changed_paths():
            with self.subTest(path=path):
                self.assertFalse(path.startswith("mtb-graphrag/"))

    def test_both_interval_endpoints_are_required(self) -> None:
        with self.assertRaises(ValueError):
            changed_paths_in_closed_interval(self.repo, self.start_sha, "")

    def test_an_unreachable_endpoint_skips_instead_of_failing(self) -> None:
        with self.assertRaises(unittest.SkipTest):
            changed_paths_in_closed_interval(
                self.repo, self.start_sha, "0" * 40
            )


class TestPathsOutsidePrefixes(unittest.TestCase):
    def test_paths_under_an_allowed_prefix_are_not_violations(self) -> None:
        self.assertEqual(
            paths_outside_prefixes([f"{PHASE_PREFIX}a.json"], (PHASE_PREFIX,)), []
        )

    def test_violations_are_sorted_and_deduplicated_by_the_caller(self) -> None:
        self.assertEqual(
            paths_outside_prefixes(["z.py", "a.py"], (PHASE_PREFIX,)),
            ["a.py", "z.py"],
        )

    def test_an_empty_prefix_tuple_rejects_everything(self) -> None:
        self.assertEqual(paths_outside_prefixes(["a.py"], ()), ["a.py"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

"""Valida cio' che solo la storia del repository puo' dire.

Terzo comando accanto a `run_gold_evaluation` e `run_source_cache_validation`,
e con la stessa forma. La differenza sta nel soggetto: quelli due dipendono da
un **ingresso esterno**, questo da un **checkout con storia**.

    python -m benchmarks.mtb_evidence.evaluation.run_repository_history_validation

    0  suite eseguita e verde
    4  suite eseguita e fallita
    5  not_applicable: questo checkout non ha una storia da interrogare

## Perche' 5 e non uno skip

Uno skip afferma «questo test non e' stato eseguito», e lascia a chi legge il
compito di capire perche'. `not_applicable` afferma qualcosa di diverso e piu'
preciso: **in questo ambiente il test non ha soggetto**. Un `git archive`
estratto non e' un checkout a cui manca qualcosa — e' un albero di file, e
chiedergli il perimetro di una fase e' una domanda malposta, non una domanda
senza risposta.

La distinzione conta perche' cambia cosa si deve fare. Uno skip in un clone e'
un difetto da chiudere; `not_applicable` in un archivio e' la constatazione che
quel controllo va eseguito altrove — ed e' **obbligatorio** altrove: nel working
tree, nel worktree staccato e nel clone la suite deve essere verde.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
GIT_ROOT = REPO_ROOT.parent

VALIDATION_VERSION = "repository-history-validation/1.0"
SUITE = "backend/tests_history"

EXIT_OK = 0
EXIT_TESTS_FAILED = 4
EXIT_NOT_APPLICABLE = 5

_GIT_TIMEOUT_SECONDS = 60


def has_history() -> bool:
    """C'e' una storia da interrogare?

    Non basta che esista una directory `.git`: un worktree staccato ha un
    **file** `.git`, e un archivio estratto non ha ne' l'uno ne' l'altro. La
    domanda si pone a git, che e' l'unico a saper rispondere.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=GIT_ROOT,
            capture_output=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def describe(applicable: bool) -> dict[str, Any]:
    return {
        "applicable": applicable,
        "evaluation_version": VALIDATION_VERSION,
        "mandatory_where_applicable": True,
        "reason": (
            None
            if applicable
            else "questo checkout non ha una storia git: i test di perimetro e "
            "di blob non hanno soggetto"
        ),
        "run_from_core_suite": False,
        "status": "applicable" if applicable else "not_applicable",
        "suite": SUITE,
    }


def run_suite() -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = "."
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
    )
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Valida perimetri di fase e blob congelati. Non viene eseguita "
            "dalla suite core."
        )
    )
    parser.add_argument(
        "--require-history",
        action="store_true",
        help=(
            "Considera un errore l'assenza di storia invece di dichiararla "
            "not_applicable. Da usare dove la storia deve esserci."
        ),
    )
    args = parser.parse_args(argv)

    applicable = has_history()
    print(json.dumps(describe(applicable), ensure_ascii=False, indent=2))

    if not applicable:
        if args.require_history:
            print(
                "errore: storia git assente dove era richiesta.", file=sys.stderr
            )
            return EXIT_TESTS_FAILED
        print(
            "\nnot_applicable: nessuna storia da interrogare. La suite non e' "
            "stata saltata — in questo ambiente non ha soggetto.",
            file=sys.stderr,
        )
        return EXIT_NOT_APPLICABLE

    if run_suite() != 0:
        print(f"\nla suite {SUITE} ha fallito.", file=sys.stderr)
        return EXIT_TESTS_FAILED
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

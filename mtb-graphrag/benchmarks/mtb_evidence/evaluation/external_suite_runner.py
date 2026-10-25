"""Il meccanismo comune ai comandi che eseguono una suite su ingresso esterno.

Un ingresso, un comando, una suite. Ogni entrypoint risolve **il proprio**
ingresso, lo verifica contro il manifest tracciato, e poi esegue **soltanto** la
propria directory di test. Nessuno dei due tocca l'albero dell'altro: e' cio'
che impedisce a un ingresso mancante di produrre skip in una suite che non lo
usa.

I codici d'uscita distinguono i tre modi di non riuscire, perche' «non ha
funzionato» non e' una diagnosi:

    2  l'ingresso non c'e' — e il messaggio dice dove e' stato cercato
    3  l'ingresso c'e' ma non e' quello dichiarato
    4  l'ingresso e' quello giusto e i test sono falliti

Il caso 3 e' il piu' importante da non confondere con il 4. Una metrica
calcolata su un gold diverso da quello dichiarato non e' sbagliata: non e'
confrontabile con niente, ed e' peggio.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from benchmarks.mtb_evidence.evaluation import external_inputs as EXTERNAL

REPO_ROOT = Path(__file__).resolve().parents[3]

EXIT_OK = 0
EXIT_MISSING_BUNDLE = 2
EXIT_BUNDLE_MISMATCH = 3
EXIT_TESTS_FAILED = 4


def describe(
    descriptor: EXTERNAL.ExternalInput,
    path: Path,
    report: dict[str, Any],
    *,
    suite: str,
    version: str,
) -> dict[str, Any]:
    """Che cosa e' stato verificato, prima che una sola riga venga letta."""
    declared = EXTERNAL.manifest(descriptor)
    return {
        "bundle_version": declared["bundle_version"],
        "evaluation_version": version,
        "file_count": declared["file_count"],
        "input_name": descriptor.name,
        "input_path": str(path),
        "manifest_aggregate_hash": declared["expected_aggregate_hash"],
        "run_from_core_suite": False,
        "schema_version": declared["schema_version"],
        "suite": suite,
        "verified": report["verified"],
    }


class SuiteRunnerUnavailable(RuntimeError):
    """Manca il runner che questa suite richiede."""


def run_suite(suite_relative: str, descriptor: EXTERNAL.ExternalInput, path: Path) -> int:
    """Esegue la sola suite indicata, con il solo ingresso pertinente in ambiente.

    **pytest, non `unittest discover`.** Sette dei moduli di questa suite sono
    scritti a funzione, e `unittest discover` dei test a funzione non sa nulla:
    li ignora in silenzio. Su questo albero ne raccoglieva 28 su 145, e un
    comando che riporta OK dopo aver saltato l'ottanta per cento dei test e'
    peggio di uno che fallisce. La suite core, che e' tutta a `TestCase`, resta
    eseguibile da entrambi i runner.

    Il processo e' separato e riceve **solo** la variabile del proprio ingresso:
    se un test di questa suite cercasse l'altro, non lo troverebbe. E' il
    comportamento che si vuole poter osservare, non prevenire con una
    convenzione.
    """
    if importlib.util.find_spec("pytest") is None:  # pragma: no cover
        raise SuiteRunnerUnavailable(
            "pytest non e' installato: la suite esterna contiene test a funzione "
            "che `unittest discover` non raccoglie, e senza pytest verrebbero "
            "saltati in silenzio."
        )
    env = dict(os.environ)
    env["PYTHONPATH"] = "."
    env[descriptor.environment_variable] = str(path)
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", suite_relative, "-q"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
    )
    return completed.returncode


def main(
    argv: list[str] | None,
    *,
    descriptor: EXTERNAL.ExternalInput,
    flag: str,
    suite_relative: str,
    version: str,
    description: str,
    compatibility: dict[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        flag,
        dest="path",
        type=Path,
        default=None,
        help=(
            f"Path dell'ingresso. Se assente viene cercato nella variabile "
            f"{descriptor.environment_variable} e nella posizione convenzionale."
        ),
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verifica l'ingresso e non esegue la suite.",
    )
    parser.add_argument(
        "--skip-verification",
        action="store_true",
        help=(
            "Salta il confronto con il manifest. Da usare solo per ispezionare "
            "un ingresso che si sa diverso: i risultati che ne escono non sono "
            "confrontabili con quelli dichiarati."
        ),
    )
    args = parser.parse_args(argv)

    try:
        path = EXTERNAL.require(descriptor, args.path)
    except EXTERNAL.ExternalInputMissingError as error:
        print(f"errore: {error}", file=sys.stderr)
        return EXIT_MISSING_BUNDLE

    try:
        report = EXTERNAL.verify(
            descriptor, path, strict=not args.skip_verification
        )
    except EXTERNAL.ExternalInputMismatchError as error:
        print(f"errore: {error}", file=sys.stderr)
        return EXIT_BUNDLE_MISMATCH

    declared = EXTERNAL.manifest(descriptor)
    for field, expected in (compatibility or {}).items():
        if declared.get(field) != expected:
            print(
                f"errore: ingresso incompatibile: {field} dichiarato "
                f"{declared.get(field)!r}, atteso {expected!r}",
                file=sys.stderr,
            )
            return EXIT_BUNDLE_MISMATCH

    print(
        json.dumps(
            describe(descriptor, path, report, suite=suite_relative, version=version),
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.verify_only:
        print("\ningresso verificato. Suite non eseguita.", file=sys.stderr)
        return EXIT_OK

    if run_suite(suite_relative, descriptor, path) != 0:
        print(f"\nla suite {suite_relative} ha fallito.", file=sys.stderr)
        return EXIT_TESTS_FAILED
    return EXIT_OK


__all__ = [
    "EXIT_BUNDLE_MISMATCH",
    "SuiteRunnerUnavailable",
    "EXIT_MISSING_BUNDLE",
    "EXIT_OK",
    "EXIT_TESTS_FAILED",
    "describe",
    "main",
    "run_suite",
]

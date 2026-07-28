"""Valutazione contro il gold, su comando esplicito e mai dalla suite.

La suite core non esegue questo modulo e non lo importa. E' la meta' dichiarata
della separazione che `external_inputs` introduce: i test architetturali
descrivono il codice e girano ovunque; la valutazione contro il gold descrive
quanto bene il codice risponde, ha bisogno di un ingresso privato, e si chiede.

Il path del bundle e' obbligatorio nel senso che conta: se non viene indicato e
non si trova in nessuna delle posizioni note, il comando fallisce dicendo dove
ha cercato — non ripiega su un bundle diverso e non prosegue con un gold vuoto,
che sarebbe il modo peggiore di fallire perche' produrrebbe numeri.

Il bundle viene verificato contro il manifest tracciato prima di essere usato.
Un bundle che non corrisponde non e' il gold di questa fase, e una metrica
calcolata su un gold diverso da quello dichiarato non e' confrontabile con
niente.

    python -m benchmarks.mtb_evidence.evaluation.run_gold_evaluation \\
      --gold-bundle <PATH>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from benchmarks.mtb_evidence.evaluation import external_inputs as EXTERNAL

EVALUATION_VERSION = "gold-evaluation-entrypoint/1.0"

EXIT_OK = 0
EXIT_MISSING_BUNDLE = 2
EXIT_BUNDLE_MISMATCH = 3


def describe(bundle: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Che cosa e' stato verificato, prima che una sola riga venga letta."""
    declared = EXTERNAL.manifest(EXTERNAL.GOLD_BUNDLE)
    return {
        "bundle_path": str(bundle),
        "bundle_version": declared["bundle_version"],
        "evaluation_version": EVALUATION_VERSION,
        "file_count": declared["file_count"],
        "manifest_aggregate_hash": declared["expected_aggregate_hash"],
        "run_from_core_suite": False,
        "schema_version": declared["schema_version"],
        "verified": report["verified"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Valutazione contro il gold. Non viene eseguita dalla suite core.",
    )
    parser.add_argument(
        "--gold-bundle",
        type=Path,
        default=None,
        help=(
            "Path del bundle gold. Se assente viene cercato nella variabile "
            f"{EXTERNAL.GOLD_BUNDLE.environment_variable} e nella posizione "
            "convenzionale."
        ),
    )
    parser.add_argument(
        "--skip-verification",
        action="store_true",
        help=(
            "Salta il confronto con il manifest. Da usare solo per ispezionare "
            "un bundle che si sa diverso: le metriche che ne escono non sono "
            "confrontabili con quelle dichiarate."
        ),
    )
    args = parser.parse_args(argv)

    try:
        bundle = EXTERNAL.require(EXTERNAL.GOLD_BUNDLE, args.gold_bundle)
    except EXTERNAL.ExternalInputMissingError as error:
        print(f"errore: {error}", file=sys.stderr)
        return EXIT_MISSING_BUNDLE

    try:
        report = EXTERNAL.verify(
            EXTERNAL.GOLD_BUNDLE, bundle, strict=not args.skip_verification
        )
    except EXTERNAL.ExternalInputMismatchError as error:
        print(f"errore: {error}", file=sys.stderr)
        return EXIT_BUNDLE_MISMATCH

    print(json.dumps(describe(bundle, report), ensure_ascii=False, indent=2))

    # Qui entrano le valutazioni contro il gold. Restano fuori da questa fase:
    # la separazione fra suite core e valutazione e' cio' che la fase consegna,
    # e riempire il comando con metriche significherebbe eseguire il rerun.
    print(
        "\nbundle verificato. Nessuna valutazione eseguita: il rerun comparativo "
        "non fa parte di questa fase.",
        file=sys.stderr,
    )
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

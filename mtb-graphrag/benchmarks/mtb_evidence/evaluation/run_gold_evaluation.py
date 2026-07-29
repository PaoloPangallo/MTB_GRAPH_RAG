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

Esegue **soltanto** `backend/tests_external/gold`. La suite della cache degli
abstract ha il proprio comando: un ingresso, un comando, una suite.

    python -m benchmarks.mtb_evidence.evaluation.run_gold_evaluation \\
      --gold-bundle <PATH>

    0  tutto verificato ed eseguito
    2  bundle assente          3  bundle incompatibile          4  test falliti
"""

from __future__ import annotations

from benchmarks.mtb_evidence.evaluation import external_inputs as EXTERNAL
from benchmarks.mtb_evidence.evaluation import external_suite_runner as RUNNER

EVALUATION_VERSION = "gold-evaluation-entrypoint/2.0"

SUITE = "backend/tests_external/gold"

EXIT_OK = RUNNER.EXIT_OK
EXIT_MISSING_BUNDLE = RUNNER.EXIT_MISSING_BUNDLE
EXIT_BUNDLE_MISMATCH = RUNNER.EXIT_BUNDLE_MISMATCH
EXIT_TESTS_FAILED = RUNNER.EXIT_TESTS_FAILED

# Il bundle deve essere quello che questa fase dichiara, non un bundle qualsiasi
# che passi il confronto degli hash: una versione di schema diversa userebbe gli
# stessi nomi di campo per dire un'altra cosa.
COMPATIBILITY = {
    "bundle_version": "MTB_Evidence_gold_pilot_v1",
    "schema_version": "mtb_evidence_gold_pilot/1.0",
}


def describe(bundle, report):
    """Che cosa e' stato verificato, prima che una sola riga venga letta."""
    return RUNNER.describe(
        EXTERNAL.GOLD_BUNDLE,
        bundle,
        report,
        suite=SUITE,
        version=EVALUATION_VERSION,
    )


def main(argv: list[str] | None = None) -> int:
    return RUNNER.main(
        argv,
        descriptor=EXTERNAL.GOLD_BUNDLE,
        flag="--gold-bundle",
        suite_relative=SUITE,
        version=EVALUATION_VERSION,
        description=(
            "Valutazione contro il gold. Non viene eseguita dalla suite core."
        ),
        compatibility=COMPATIBILITY,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

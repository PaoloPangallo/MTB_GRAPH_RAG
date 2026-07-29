"""Validazione contro la cache degli abstract, su comando esplicito.

Simmetrico a `run_gold_evaluation`, e separato da esso apposta. La cache degli
abstract e' un ingresso diverso dal gold: e' testo protetto da copyright, esclusa
dal versionamento da .gitignore, e i test che la aprono non hanno niente a che
vedere con la valutazione contro il gold.

Finche' i due ingressi condividevano un comando e una suite, la loro assenza
produceva un unico numero di test saltati e nessuno sapeva a quale dei due
attribuirli. Ottantaquattro test saltavano per la cache e venivano contati fra
gli skip del gold.

Esegue **soltanto** `backend/tests_external/source_cache`.

    python -m benchmarks.mtb_evidence.evaluation.run_source_cache_validation \\
      --source-abstract-cache <PATH>

    0  tutto verificato ed eseguito
    2  cache assente           3  cache incompatibile           4  test falliti
"""

from __future__ import annotations

from benchmarks.mtb_evidence.evaluation import external_inputs as EXTERNAL
from benchmarks.mtb_evidence.evaluation import external_suite_runner as RUNNER

VALIDATION_VERSION = "source-cache-validation-entrypoint/1.0"

SUITE = "backend/tests_external/source_cache"

EXIT_OK = RUNNER.EXIT_OK
EXIT_MISSING_BUNDLE = RUNNER.EXIT_MISSING_BUNDLE
EXIT_BUNDLE_MISMATCH = RUNNER.EXIT_BUNDLE_MISMATCH
EXIT_TESTS_FAILED = RUNNER.EXIT_TESTS_FAILED

COMPATIBILITY = {
    "bundle_version": "priority_curation_source_abstract_cache_v1",
    "schema_version": "source_abstract_cache/1.0",
}


def describe(cache, report):
    """Che cosa e' stato verificato, prima che una sola riga venga letta."""
    return RUNNER.describe(
        EXTERNAL.SOURCE_ABSTRACT_CACHE,
        cache,
        report,
        suite=SUITE,
        version=VALIDATION_VERSION,
    )


def main(argv: list[str] | None = None) -> int:
    return RUNNER.main(
        argv,
        descriptor=EXTERNAL.SOURCE_ABSTRACT_CACHE,
        flag="--source-abstract-cache",
        suite_relative=SUITE,
        version=VALIDATION_VERSION,
        description=(
            "Validazione contro la cache degli abstract. Non viene eseguita "
            "dalla suite core."
        ),
        compatibility=COMPATIBILITY,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

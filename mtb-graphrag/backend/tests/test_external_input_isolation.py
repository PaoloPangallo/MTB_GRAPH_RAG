"""Protegge l'indipendenza della suite core dagli ingressi esterni privati.

Il difetto che questi test impediscono e' particolare: non e' un errore nel
codice ma un errore in cio' che la suite descrive. Finche' i test aprivano il
bundle gold e la cache degli abstract senza chiedersi se ci fossero, un clone
pulito falliva 88 test con 106 errori, e nessuno di quei fallimenti diceva
niente sul codice — dicevano che la macchina era un'altra.

**Nessuno di questi test apre un ingresso reale.** Sarebbe la contraddizione
piu' diretta possibile: un test che verifica l'indipendenza dal bundle
leggendolo fallirebbe esattamente dove deve valere. Cio' che viene usato e' un
bundle sintetico costruito in una directory temporanea, un path inesistente, e
il manifest tracciato — che sta nel repository e non e' un ingresso esterno.

Che i due ingressi restino fuori dal versionamento e' verificato con git, non
dichiarato: un bundle copiato dentro il repository per far passare la suite
sarebbe la soluzione sbagliata al problema giusto, e questo test la rifiuta.
"""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

from benchmarks.mtb_evidence.evaluation import external_inputs as EXTERNAL
from benchmarks.mtb_evidence.evaluation import run_gold_evaluation as RUNNER
from benchmarks.mtb_evidence.evaluation import (
    run_source_cache_validation as CACHE_RUNNER,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# I due alberi in cui vivono i test che aprono un ingresso esterno. Non sono
# un elenco di moduli: sono due directory, e l'appartenenza e' la collocazione.
#
# Prima qui c'erano tre tuple di nomi — i moduli dipendenti dal gold, quelli
# dipendenti dalla cache, quelli che incorporano il checksum del bundle — e i
# controlli verificavano che *quei* moduli si comportassero bene. Un elenco pero'
# risponde solo di cio' che contiene: un modulo nuovo che aprisse il bundle senza
# esservi iscritto non veniva notato da nessuno, e infatti tre moduli aprivano una
# copia tracciata del gold senza comparire in nessuna delle tre tuple.
EXTERNAL_SUITES = ("gold", "source_cache")

FORBIDDEN_IN_CORE = (
    "MTB_Evidence_gold_pilot_v1_bundle",
    "source_abstract_cache",
)


def _synthetic_bundle(root: Path) -> Path:
    """Un bundle finto, con la forma del vero e nessuno dei suoi contenuti."""
    bundle = root / "synthetic_bundle"
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "notes.md").write_text("# sintetico\n", encoding="utf-8")
    (bundle / "records.jsonl").write_text(
        '{"id":"SYNTH-1","value":1}\n{"id":"SYNTH-2","value":2}\n', encoding="utf-8"
    )
    nested = bundle / "nested"
    nested.mkdir(exist_ok=True)
    (nested / "extra.txt").write_text("sintetico\n", encoding="utf-8")
    return bundle


class ManifestTests(unittest.TestCase):
    """Il manifest tracciato descrive l'ingresso senza contenerlo."""

    REQUIRED = (
        "availability",
        "bundle_version",
        "expected_aggregate_hash",
        "expected_file_hashes",
        "schema_version",
    )

    def test_every_declared_input_has_a_tracked_manifest(self) -> None:
        for descriptor in EXTERNAL.EXTERNAL_INPUTS:
            with self.subTest(input=descriptor.name):
                self.assertTrue(descriptor.manifest_path.is_file())

    def test_the_manifest_declares_the_five_required_fields(self) -> None:
        for descriptor in EXTERNAL.EXTERNAL_INPUTS:
            declared = EXTERNAL.manifest(descriptor)
            for key in self.REQUIRED:
                with self.subTest(input=descriptor.name, field=key):
                    self.assertIn(key, declared)

    def test_availability_is_declared_external_private_input(self) -> None:
        for descriptor in EXTERNAL.EXTERNAL_INPUTS:
            with self.subTest(input=descriptor.name):
                self.assertEqual(
                    EXTERNAL.manifest(descriptor)["availability"],
                    EXTERNAL.AVAILABILITY_EXTERNAL,
                )

    def test_the_manifest_declares_itself_untracked(self) -> None:
        for descriptor in EXTERNAL.EXTERNAL_INPUTS:
            with self.subTest(input=descriptor.name):
                declared = EXTERNAL.manifest(descriptor)
                self.assertFalse(declared["tracked_in_repository"])
                self.assertTrue(declared["checksum_only_no_deserialization"])

    def test_the_manifest_carries_hashes_and_not_content(self) -> None:
        # Un manifest che contenesse una riga di gold sarebbe una copia parziale
        # del bundle sotto un altro nome.
        for descriptor in EXTERNAL.EXTERNAL_INPUTS:
            declared = EXTERNAL.manifest(descriptor)
            for name, digest in declared["expected_file_hashes"].items():
                with self.subTest(input=descriptor.name, file=name):
                    self.assertRegex(digest, r"^[0-9a-f]{64}$")
            self.assertRegex(declared["expected_aggregate_hash"], r"^[0-9a-f]{64}$")

    def test_the_aggregate_is_the_hash_of_the_declared_file_hashes(self) -> None:
        for descriptor in EXTERNAL.EXTERNAL_INPUTS:
            declared = EXTERNAL.manifest(descriptor)
            with self.subTest(input=descriptor.name):
                self.assertEqual(
                    EXTERNAL.aggregate_hash(declared["expected_file_hashes"]),
                    declared["expected_aggregate_hash"],
                )


class SyntheticBundleTests(unittest.TestCase):
    """La logica di risoluzione e verifica, esercitata su un bundle finto."""

    def setUp(self) -> None:
        import tempfile

        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.bundle = _synthetic_bundle(self.root)
        self.descriptor = EXTERNAL.ExternalInput(
            name="synthetic",
            manifest_file="synthetic_manifest.json",
            default_relative_path="does_not_exist_anywhere",
            environment_variable="MTB_SYNTHETIC_INPUT",
            description="ingresso sintetico per i test di isolamento",
        )

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_an_explicit_path_wins_over_every_other_candidate(self) -> None:
        self.assertEqual(
            EXTERNAL.resolve(self.descriptor, self.bundle), self.bundle
        )

    def test_the_environment_variable_is_used_when_no_path_is_given(self) -> None:
        os.environ[self.descriptor.environment_variable] = str(self.bundle)
        try:
            self.assertEqual(EXTERNAL.resolve(self.descriptor), self.bundle)
        finally:
            del os.environ[self.descriptor.environment_variable]

    def test_a_missing_input_resolves_to_none_without_raising(self) -> None:
        self.assertIsNone(EXTERNAL.resolve(self.descriptor))

    def test_require_names_every_place_it_looked(self) -> None:
        with self.assertRaises(EXTERNAL.ExternalInputMissingError) as caught:
            EXTERNAL.require(self.descriptor)
        message = str(caught.exception)
        self.assertIn("does_not_exist_anywhere", message)
        self.assertIn(self.descriptor.environment_variable, message)

    def test_require_or_skip_raises_the_skip_both_runners_understand(self) -> None:
        with self.assertRaises(unittest.SkipTest):
            EXTERNAL.require_or_skip(self.descriptor)

    def test_a_synthetic_bundle_verifies_against_its_own_manifest(self) -> None:
        built = EXTERNAL.build_manifest(
            self.descriptor,
            self.bundle,
            bundle_version="synthetic/1",
            schema_version="synthetic-schema/1",
        )
        self.descriptor.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.descriptor.manifest_path.write_text(
            json.dumps(built), encoding="utf-8"
        )
        try:
            report = EXTERNAL.verify(self.descriptor, self.bundle)
            self.assertTrue(report["verified"])
            self.assertEqual(report["changed_files"], [])
        finally:
            self.descriptor.manifest_path.unlink()

    def test_a_changed_file_is_detected_and_named(self) -> None:
        built = EXTERNAL.build_manifest(
            self.descriptor,
            self.bundle,
            bundle_version="synthetic/1",
            schema_version="synthetic-schema/1",
        )
        self.descriptor.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.descriptor.manifest_path.write_text(
            json.dumps(built), encoding="utf-8"
        )
        (self.bundle / "records.jsonl").write_text(
            '{"id":"SYNTH-1","value":999}\n', encoding="utf-8"
        )
        try:
            with self.assertRaises(EXTERNAL.ExternalInputMismatchError) as caught:
                EXTERNAL.verify(self.descriptor, self.bundle)
            self.assertIn("records.jsonl", str(caught.exception))
        finally:
            self.descriptor.manifest_path.unlink()

    def test_the_hash_does_not_depend_on_where_the_bundle_is_mounted(self) -> None:
        import shutil

        moved = self.root / "elsewhere" / "synthetic_bundle"
        moved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.bundle, moved)
        self.assertEqual(
            EXTERNAL.aggregate_hash(EXTERNAL.file_hashes(self.bundle)),
            EXTERNAL.aggregate_hash(EXTERNAL.file_hashes(moved)),
        )


class CoreIndependenceTests(unittest.TestCase):
    """La suite core non nomina un ingresso esterno. Nessuna eccezione."""

    def _core_modules(self) -> list[Path]:
        return sorted((REPO_ROOT / "backend" / "tests").glob("*.py"))

    def test_no_core_module_names_an_external_input(self) -> None:
        """La versione verificabile a macchina di «zero dipendenze implicite».

        Prima esisteva un elenco di moduli dichiarati dipendenti dal gold, e il
        controllo verificava che *quelli* si comportassero bene. Un elenco pero'
        risponde solo di cio' che contiene: un modulo nuovo che aprisse il
        bundle senza comparirvi non veniva notato da nessuno.

        Ora la regola vale per esclusione: **nessun** file sotto
        `backend/tests/` puo' nominare un ingresso esterno, perche' i test che
        li aprono stanno fisicamente altrove. Non c'e' un elenco da tenere
        aggiornato, e non c'e' modo di entrare nella suite core violandola.
        """
        exempt = {Path(__file__).name}
        for path in self._core_modules():
            if path.name in exempt:
                # Questo modulo li nomina per vietarli: le costanti sopra sono
                # la dichiarazione, ed e' l'unica eccezione.
                continue
            body = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_IN_CORE:
                with self.subTest(module=path.name, token=token):
                    self.assertNotIn(token, body)

    def test_no_core_module_asks_for_an_external_input(self) -> None:
        """Nemmeno per saltare.

        `require_or_skip` in un modulo core significherebbe che la suite core
        sa dell'ingresso e si dichiara saltata quando manca. Uno skip di massa
        e' comunque una dipendenza, scritta in piccolo.
        """
        forbidden = ("require_or_skip", "GOLD_BUNDLE", "SOURCE_ABSTRACT_CACHE")
        for path in self._core_modules():
            if path.name == Path(__file__).name:
                continue
            body = path.read_text(encoding="utf-8")
            for token in forbidden:
                with self.subTest(module=path.name, token=token):
                    self.assertNotIn(token, body)

    def test_the_external_tree_is_outside_the_core_discovery_root(self) -> None:
        core = REPO_ROOT / "backend" / "tests"
        external = REPO_ROOT / "backend" / "tests_external"
        self.assertTrue(external.is_dir())
        self.assertFalse(external.is_relative_to(core))
        for name in ("gold", "source_cache"):
            with self.subTest(suite=name):
                self.assertTrue((external / name / "__init__.py").is_file())


class SuitesDoNotBorrowEachOthersInputTests(unittest.TestCase):
    """Un ingresso mancante non fa saltare la suite che non lo usa.

    Prima i test della cache degli abstract saltavano insieme a quelli del gold
    e venivano contati con loro: ottantaquattro test saltati per un ingresso,
    attribuiti a un altro. Un conteggio che mescola due cause non dice niente
    su nessuna delle due.
    """

    FOREIGN_INPUT = {
        "gold": "SOURCE_ABSTRACT_CACHE",
        "source_cache": "GOLD_BUNDLE",
    }

    def test_neither_suite_names_the_other_input(self) -> None:
        for suite, foreign in self.FOREIGN_INPUT.items():
            directory = REPO_ROOT / "backend" / "tests_external" / suite
            for path in sorted(directory.glob("test_*.py")):
                with self.subTest(suite=suite, module=path.name):
                    self.assertNotIn(foreign, path.read_text(encoding="utf-8"))


# `NotTrackedTests` sta in `backend/tests_history/test_repository_tracking.py`:
# «non e' tracciato» e' una proprieta' del repository, e si verifica con git.



class PointerManifestTests(unittest.TestCase):
    """Cio' che resta al posto del gold lo descrive senza contenerlo."""

    REQUIRED_FIELDS = [
        "aggregate_sha256",
        "availability",
        "bundle_version",
        "expected_sha256",
        "files",
        "schema_version",
    ]

    @classmethod
    def setUpClass(cls) -> None:
        cls.pointer = json.loads(
            (
                REPO_ROOT
                / "benchmarks"
                / "mtb_evidence"
                / "pilot"
                / "input"
                / "external_gold_input.json"
            ).read_text(encoding="utf-8")
        )
        cls.manifest = EXTERNAL.manifest(EXTERNAL.GOLD_BUNDLE)

    def test_it_declares_exactly_the_required_fields_and_nothing_else(self) -> None:
        self.assertEqual(sorted(self.pointer), self.REQUIRED_FIELDS)

    def test_it_declares_the_input_is_external_and_private(self) -> None:
        self.assertEqual(self.pointer["availability"], EXTERNAL.AVAILABILITY_EXTERNAL)

    def test_it_does_not_drift_from_the_manifest_that_verifies_the_bundle(self) -> None:
        """Due descrizioni dello stesso bundle che divergono sono peggio di una."""
        self.assertEqual(self.pointer["bundle_version"], self.manifest["bundle_version"])
        self.assertEqual(self.pointer["schema_version"], self.manifest["schema_version"])
        self.assertEqual(
            self.pointer["expected_sha256"], self.manifest["expected_file_hashes"]
        )
        self.assertEqual(
            self.pointer["aggregate_sha256"], self.manifest["expected_aggregate_hash"]
        )
        self.assertEqual(
            sorted(self.pointer["files"]), sorted(self.pointer["expected_sha256"])
        )

    def test_it_carries_no_content_of_the_bundle(self) -> None:
        """Un manifest che bastasse a ricostruire il bundle non servirebbe."""
        body = json.dumps(self.pointer)
        for marker in ("case_id", "PILOT-", "claims", "pmid", "gene"):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, body)


class EntrypointTests(unittest.TestCase):
    """Un ingresso, un comando, una suite. E fallire in modo distinguibile."""

    # comando -> (flag, suite che deve eseguire, suite che non deve toccare)
    COMMANDS = {
        "run_gold_evaluation.py": (
            "--gold-bundle",
            "backend/tests_external/gold",
            "backend/tests_external/source_cache",
        ),
        "run_source_cache_validation.py": (
            "--source-abstract-cache",
            "backend/tests_external/source_cache",
            "backend/tests_external/gold",
        ),
    }

    def _entrypoint(self, name: str) -> str:
        return (
            REPO_ROOT / "benchmarks" / "mtb_evidence" / "evaluation" / name
        ).read_text(encoding="utf-8")

    def test_a_missing_bundle_fails_with_its_own_exit_code(self) -> None:
        code = RUNNER.main(["--gold-bundle", str(REPO_ROOT / "no_such_bundle")])
        self.assertEqual(code, RUNNER.EXIT_MISSING_BUNDLE)

    def test_a_missing_cache_fails_with_its_own_exit_code(self) -> None:
        code = CACHE_RUNNER.main(
            ["--source-abstract-cache", str(REPO_ROOT / "no_such_cache")]
        )
        self.assertEqual(code, CACHE_RUNNER.EXIT_MISSING_BUNDLE)

    def test_the_three_ways_of_failing_are_distinguishable(self) -> None:
        """«Non ha funzionato» non e' una diagnosi.

        Ingresso assente, ingresso sbagliato e test falliti chiedono tre
        reazioni diverse. Il terzo confuso col secondo e' il piu' costoso: una
        metrica calcolata su un gold diverso da quello dichiarato non e'
        sbagliata, e' inconfrontabile, ed e' peggio.
        """
        codes = {
            RUNNER.EXIT_OK,
            RUNNER.EXIT_MISSING_BUNDLE,
            RUNNER.EXIT_BUNDLE_MISMATCH,
            RUNNER.EXIT_TESTS_FAILED,
        }
        self.assertEqual(len(codes), 4)

    def test_each_entrypoint_names_its_own_input_and_its_own_suite(self) -> None:
        for name, (flag, own, foreign) in self.COMMANDS.items():
            body = self._entrypoint(name)
            with self.subTest(command=name):
                self.assertIn(flag, body)
                self.assertIn(own, body)
                self.assertNotIn(foreign, body)

    def test_the_report_declares_it_was_not_produced_by_the_core_suite(self) -> None:
        """La dichiarazione sta nel report, non nel commento di un modulo.

        Prima era una stringa nel sorgente dell'entrypoint, e il controllo
        verificava che quella stringa ci fosse. Cercare una stringa in un
        sorgente non e' verificare un comportamento: qui il report viene
        prodotto davvero — dal manifest tracciato, senza aprire nessun bundle —
        e si guarda cosa dice.
        """
        for name, module in (
            ("gold", RUNNER),
            ("source_cache", CACHE_RUNNER),
        ):
            with self.subTest(command=name):
                report = module.describe(
                    Path("percorso/non/aperto"), {"verified": True}
                )
                self.assertFalse(report["run_from_core_suite"])
                self.assertEqual(report["suite"], f"backend/tests_external/{name}")

    def test_every_entrypoint_routes_through_the_shared_runner(self) -> None:
        for name in self.COMMANDS:
            with self.subTest(command=name):
                self.assertIn("external_suite_runner", self._entrypoint(name))

    def test_no_test_module_imports_the_entrypoint_to_run_it(self) -> None:
        # Questo modulo lo importa per verificarne il codice d'uscita, non per
        # eseguire una valutazione: nessun altro deve importarlo affatto.
        tests = sorted((REPO_ROOT / "backend" / "tests").glob("test_*.py"))
        for path in tests:
            if path.name == "test_external_input_isolation.py":
                continue
            with self.subTest(module=path.name):
                # Il modulo, non la funzione omonima che `v2_v3a_exploratory`
                # esporta da prima e che nessuno di questi test esegue senza
                # bundle.
                self.assertNotIn(
                    "evaluation import run_gold_evaluation",
                    path.read_text(encoding="utf-8"),
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

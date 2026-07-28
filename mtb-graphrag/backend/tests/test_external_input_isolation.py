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

REPO_ROOT = Path(__file__).resolve().parents[2]

# I moduli di test che aprono un ingresso esterno. Sono nominati uno per uno
# perche' l'elenco sia una decisione e non il risultato di una ricerca: un test
# nuovo che apra il bundle senza comparire qui e' un test che non ha dichiarato
# la propria dipendenza.
GOLD_DEPENDENT_MODULES = (
    "test_candidate_coverage_audit.py",
    "test_conjunctive_biomarker_fix_audit.py",
    "test_disease_normalization_review.py",
    "test_multi_intervention_adapter_review.py",
    "test_multi_intervention_source_review.py",
    "test_v2_v3a_exploratory_evaluation.py",
    "test_verified_disease_alias_fix_audit.py",
)

ABSTRACT_CACHE_DEPENDENT_MODULES = (
    "test_non_therapeutic_source_closure.py",
    "test_terminology_mapping_closure.py",
)

# I moduli che rigenerano un artefatto in cui il checksum dell'albero del gold
# e' *incorporato*. Non leggono il gold e non lo usano per decidere: registrano
# che c'era e con quale impronta. Senza il bundle la rigenerazione produce
# `bundle_present: false`, e il confronto con l'artefatto committato non ha
# soggetto — la dipendenza e' reale anche se nessuna riga di gold entra.
GOLD_CHECKSUM_EMBEDDING_MODULES = (
    "test_multi_intervention_adjudication.py",
    "test_multi_intervention_review_comparison.py",
    "test_pre_promotion_audit_1_3.py",
    "test_pre_promotion_required_fixes_1_4.py",
)

# I moduli architetturali della catena di retrieval. Nessuno di loro puo'
# nominare un ingresso esterno: se lo facesse, la suite core tornerebbe a
# dipendere da una macchina.
CORE_ARCHITECTURAL_MODULES = (
    "test_v3_retriever_binding.py",
    "test_v3_retriever_regression_closure.py",
    "test_v3_conjunctive_query_closure.py",
    "test_external_input_isolation.py",
)

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
    """La suite core non nomina un ingresso esterno."""

    def test_no_core_architectural_module_names_an_external_input(self) -> None:
        for name in CORE_ARCHITECTURAL_MODULES:
            path = REPO_ROOT / "backend" / "tests" / name
            if not path.is_file():
                continue
            body = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_IN_CORE:
                with self.subTest(module=name, token=token):
                    # Questo modulo li nomina per vietarli, ed e' l'unica
                    # eccezione: le costanti sopra sono la dichiarazione.
                    if name == "test_external_input_isolation.py":
                        continue
                    self.assertNotIn(token, body)

    def test_every_gold_dependent_module_declares_its_dependency(self) -> None:
        for name in GOLD_DEPENDENT_MODULES:
            body = (REPO_ROOT / "backend" / "tests" / name).read_text(
                encoding="utf-8"
            )
            with self.subTest(module=name):
                self.assertIn("external_inputs as EXTERNAL", body)
                self.assertIn("EXTERNAL.resolve(EXTERNAL.GOLD_BUNDLE)", body)
                self.assertIn("pytestmark", body)

    def test_every_cache_dependent_module_skips_instead_of_failing(self) -> None:
        for name in ABSTRACT_CACHE_DEPENDENT_MODULES:
            body = (REPO_ROOT / "backend" / "tests" / name).read_text(
                encoding="utf-8"
            )
            with self.subTest(module=name):
                self.assertIn(
                    "EXTERNAL.require_or_skip(EXTERNAL.SOURCE_ABSTRACT_CACHE)", body
                )

    def test_every_checksum_embedding_module_skips_without_the_bundle(self) -> None:
        for name in GOLD_CHECKSUM_EMBEDDING_MODULES:
            body = (REPO_ROOT / "backend" / "tests" / name).read_text(
                encoding="utf-8"
            )
            with self.subTest(module=name):
                self.assertIn(
                    "EXTERNAL.require_or_skip(EXTERNAL.GOLD_BUNDLE)", body
                )

    def test_no_gold_dependent_module_builds_the_path_by_hand(self) -> None:
        # Comporre il path a mano e' esattamente cio' che rendeva l'assenza un
        # errore di apertura invece di una condizione dichiarata.
        for name in GOLD_DEPENDENT_MODULES:
            body = (REPO_ROOT / "backend" / "tests" / name).read_text(
                encoding="utf-8"
            )
            with self.subTest(module=name):
                self.assertNotIn(
                    'ROOT.parent / "MTB_Evidence_gold_pilot_v1_bundle"', body
                )


class FrozenBytesAreCommittedTests(unittest.TestCase):
    """Cio' che un audit ha misurato dev'essere cio' che git conserva.

    Il difetto che questo test impedisce e' rimasto invisibile per otto fasi. Gli
    audit congelano l'integrita' di un sorgente con lo sha256 dei suoi **byte**,
    e verificavano quell'hash contro il file sul disco. Nessuno verificava che il
    file sul disco fosse anche cio' che era stato committato: su una macchina
    Windows la forma CRLF sul disco e la forma LF nel blob sono due sequenze di
    byte diverse, git le considera equivalenti, e l'hash congelato descriveva la
    prima mentre il repository conservava la seconda.

    L'effetto era che dodici artefatti di otto fasi chiuse promettevano
    un'impronta che nessun clone poteva riprodurre. Il controllo qui guarda solo
    il blob, mai l'albero di lavoro: e' esattamente la differenza fra i due che
    il difetto sfruttava.
    """

    # Ogni riga: artefatto che registra l'impronta, e il file impronto'ato. I
    # path sono relativi alla radice del repository, come li scrive git.
    # Le coppie che un checkout pulito riproduce. Sono quelle sotto
    # `backend/`, dove la convenzione di fine riga e' dichiarabile senza
    # rovesciare la politica LF che `mtb-graphrag/benchmarks/.gitattributes`
    # impone al proprio albero.
    FROZEN = (
        (
            "benchmarks/mtb_evidence/v3/pre_promotion_audit_1_3/audit_manifest.json",
            "backend/pipeline/evidence/qualification.py",
        ),
        (
            "benchmarks/mtb_evidence/v3/pre_promotion_audit_1_3/audit_manifest.json",
            "backend/pipeline/evidence/qualified_retriever.py",
        ),
        (
            "benchmarks/mtb_evidence/v3/claim_type_retrieval_contract/contract_manifest.json",
            "backend/pipeline/evidence/qualified_retriever.py",
        ),
        (
            "benchmarks/mtb_evidence/v3/prototype_corpus_promotion_1_4/operational_integrity.json",
            "backend/pipeline/evidence/qualification.py",
        ),
        (
            "benchmarks/mtb_evidence/v3/pre_promotion_required_fixes_1_4/repository_v1_4_manifest.json",
            "backend/pipeline/evidence/qualified_retriever.py",
        ),
        (
            "benchmarks/mtb_evidence/v3/verified_disease_alias_fix/fix_manifest.json",
            "backend/pipeline/evidence/qualified_retriever.py",
        ),
    )

    # Coppie che un checkout pulito **non** riproduce, e la ragione. Sono
    # elencate perche' il disallineamento sia una constatazione registrata e non
    # una scoperta che qualcun altro dovra' rifare: l'artefatto congelato porta
    # l'hash della forma CRLF di un file che
    # `mtb-graphrag/benchmarks/.gitattributes` dichiara LF dal commit 63ed143.
    # Chiuderle richiede di rigenerare quegli artefatti — tre dei quali stanno
    # nel corpus promosso — e non appartiene a una fase di test.
    KNOWN_UNREPRODUCIBLE = (
        (
            "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4/corpus_manifest.json",
            "benchmarks/mtb_evidence/v3/disease_hierarchy_policy/disease_match_contract.json",
        ),
        (
            "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4/promotion_log.json",
            "benchmarks/mtb_evidence/v3/disease_hierarchy_policy/disease_policy_modes.json",
        ),
        (
            "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4/disease_relation_registry.json",
            "benchmarks/mtb_evidence/v3/disease_hierarchy_policy/disease_relation_definitions.json",
        ),
        (
            "benchmarks/mtb_evidence/v3/author_approval_23344087/second_review_blinding_check.json",
            "benchmarks/mtb_evidence/v3/first_review/first_review_queue.csv",
        ),
    )

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["git", *args], cwd=REPO_ROOT.parent, capture_output=True, check=False
        )
        if result.returncode != 0:
            self.skipTest("git non utilizzabile in questo checkout")
        return result

    def _checkout_bytes(self, relative: str) -> bytes:
        """I byte che un checkout pulito scriverebbe su disco.

        Non i byte del blob: fra il blob e il disco c'e' la conversione di fine
        riga dichiarata in `.gitattributes`, ed e' proprio quella conversione che
        l'hash congelato deve sopravvivere. Confrontare il blob nudo misurerebbe
        qualcosa che nessuno scrive mai.
        """
        path = f"mtb-graphrag/{relative}"
        blob = self._git("show", f"HEAD:{path}").stdout
        attrs = self._git("check-attr", "text", "eol", "--", path).stdout.decode()
        declared = {
            line.rsplit(": ", 2)[-2]: line.rsplit(": ", 1)[-1].strip()
            for line in attrs.splitlines()
            if line.count(": ") >= 2
        }
        if declared.get("text") in ("unset", "false"):
            return blob
        if declared.get("eol") == "crlf":
            return blob.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        return blob

    def _checkout_sha256(self, relative: str) -> str:
        import hashlib

        return hashlib.sha256(self._checkout_bytes(relative)).hexdigest()

    def test_every_frozen_hash_is_reproducible_from_the_committed_bytes(self) -> None:
        import json as _json
        import re

        for artifact, source in self.FROZEN:
            with self.subTest(artifact=artifact, source=source):
                declared = (REPO_ROOT / artifact).read_text(encoding="utf-8")
                digest = self._checkout_sha256(source)
                # L'hash puo' comparire sotto chiavi diverse a seconda della
                # fase: cio' che conta e' che l'artefatto lo nomini.
                self.assertIn(
                    digest,
                    set(re.findall(r"\b[0-9a-f]{64}\b", declared)),
                    f"{artifact} non registra l'impronta dei byte committati di "
                    f"{source}: l'audit ha misurato qualcosa che il repository "
                    f"non conserva",
                )
                _json.loads(declared)

    def test_the_declared_sources_are_tracked(self) -> None:
        for _artifact, source in self.FROZEN + self.KNOWN_UNREPRODUCIBLE:
            with self.subTest(source=source):
                self.assertTrue((REPO_ROOT / source).is_file())

    def test_the_known_unreproducible_list_is_still_accurate(self) -> None:
        """Se una coppia diventa riproducibile, va spostata, non lasciata qui.

        Una lista di eccezioni che nessuno rivede diventa una lista di cose
        vere una volta sola. Questo controllo fallisce quando il disallineamento
        e' stato chiuso, e chiede di registrarlo fra le coppie verificate.
        """
        import re

        for artifact, source in self.KNOWN_UNREPRODUCIBLE:
            with self.subTest(artifact=artifact, source=source):
                declared = (REPO_ROOT / artifact).read_text(encoding="utf-8")
                digest = self._checkout_sha256(source)
                self.assertNotIn(
                    digest,
                    set(re.findall(r"\b[0-9a-f]{64}\b", declared)),
                    f"{artifact} ora registra l'impronta dei byte di checkout di "
                    f"{source}: il disallineamento e' chiuso, sposta la coppia "
                    f"in FROZEN",
                )


class NotTrackedTests(unittest.TestCase):
    """Gli ingressi esterni non sono entrati nel repository."""

    def _tracked(self, pattern: str) -> list[str]:
        result = subprocess.run(
            ["git", "ls-files", pattern],
            cwd=REPO_ROOT.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            self.skipTest("git non utilizzabile in questo checkout")
        return [line for line in result.stdout.splitlines() if line.strip()]

    def test_the_gold_bundle_is_not_tracked(self) -> None:
        self.assertEqual(self._tracked("MTB_Evidence_gold_pilot_v1_bundle/*"), [])

    def test_the_abstract_cache_is_not_tracked(self) -> None:
        self.assertEqual(self._tracked("*source_abstract_cache.jsonl"), [])

    def test_no_new_copy_of_the_gold_was_added_under_the_package(self) -> None:
        # Constatazione, non approvazione: due copie byte-identiche del gold
        # pilota sono tracciate sotto `pilot/input/` dal commit cce87f1, molto
        # prima di questa fase. Sono pinnate qui una per una perche' il test
        # possa dire l'unica cosa che questa fase puo' garantire — che non ne ha
        # aggiunte — invece di affermare il falso dichiarando che non ce ne
        # sono. Rimuoverle e' una decisione di riservatezza che non appartiene a
        # una fase di test.
        known = {
            "mtb-graphrag/benchmarks/mtb_evidence/pilot/input/"
            "MTB_Evidence_gold_pilot_v1.xlsx",
            "mtb-graphrag/benchmarks/mtb_evidence/pilot/input/"
            "mtb_evidence_gold_pilot_v1.jsonl",
        }
        self.assertEqual(set(self._tracked("*gold_pilot*")), known)


class EntrypointTests(unittest.TestCase):
    """Il comando di valutazione e' separato e fallisce in modo chiaro."""

    def test_a_missing_bundle_fails_with_its_own_exit_code(self) -> None:
        code = RUNNER.main(["--gold-bundle", str(REPO_ROOT / "no_such_bundle")])
        self.assertEqual(code, RUNNER.EXIT_MISSING_BUNDLE)

    def test_the_entrypoint_declares_it_is_not_run_by_the_core_suite(self) -> None:
        body = (
            REPO_ROOT
            / "benchmarks"
            / "mtb_evidence"
            / "evaluation"
            / "run_gold_evaluation.py"
        ).read_text(encoding="utf-8")
        self.assertIn("--gold-bundle", body)
        self.assertIn("run_from_core_suite", body)

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

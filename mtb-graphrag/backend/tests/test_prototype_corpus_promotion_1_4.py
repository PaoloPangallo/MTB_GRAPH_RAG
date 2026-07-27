"""Protegge la promozione prototipale del corpus 1.4 e il suo rollback.

I test difendono sei cose, e ognuna e' un modo di sbagliare che questa fase
rende possibile per la prima volta.

Che la scrittura sia davvero atomica, cioe' che interrompendola in un punto
qualsiasi la directory definitiva resti o completa o intatta, e mai a meta'. Il
punto di interruzione non viene simulato: viene chiesto al modulo, che lo
espone per nome.

Che promuovere non validi. Un corpus promosso continua a portare 148 claim
prototype-only, nessuno dei quali final-evaluable ne' hard-filterable: se la
promozione potesse cambiare quei campi, "versionato" e "clinicamente valido"
diventerebbero la stessa affermazione.

Che il retriever operativo non sia collegato e non lo diventi per effetto della
promozione. La query operativa viene eseguita e confrontata per conteggio,
serializzazione e digest, e il loader promosso non e' raggiungibile da nessun
modulo del percorso operativo.

Che il lineage sia completo in entrambe le direzioni: nessun ritirato nel lookup
primario, nessun ritirato senza redirect, nessun redirect verso un claim che non
esiste.

Che le decisioni congelate restino congelate — AUY922 irrisolto, il letterale
BGJ398 nella fonte, i dodici claim salini fuori dal primario — e che la
promozione non ne risolva nessuna passando di li'.

Che il rollback sia idempotente nel senso stretto: non che si possa rieseguire
senza errori, ma che la seconda esecuzione sia indistinguibile dalla prima.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.corpus import atomic_write as ATOMIC
from backend.pipeline.evidence.corpus import links_and_views as LV
from backend.pipeline.evidence.corpus import loader as LOADER
from backend.pipeline.evidence.corpus import materialization as MAT
from backend.pipeline.evidence.corpus import promotion as PROMOTION
from backend.pipeline.evidence.corpus import promotion_contract as CONTRACT
from backend.pipeline.evidence.corpus import prototype_registry as REGISTRY
from backend.pipeline.evidence.corpus import rollback as ROLLBACK
from backend.pipeline.evidence.shadow import propagation as PROP
from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation import prototype_promotion_audit as AUDIT
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import scope as SCOPE
from benchmarks.mtb_evidence.evaluation.scripts.promote_qualified_claim_corpus_1_4 import (
    DEFAULT_AUDIT_OUTPUT,
    SOURCE_FILES,
    START_SHA,
    load_sources,
    operational_query,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = CONTRACT.PROMOTED_CORPUS
REGISTRY_PATH = CONTRACT.REGISTRY_PATH
AUDIT_OUTPUT = DEFAULT_AUDIT_OUTPUT
SHADOW_V14 = SCOPE.V3 / CONTRACT.SOURCE_SHADOW_DIRNAME

# Estremo di fase: il commit che la chiude, mai HEAD. Il perimetro di una fase
# e' una proprieta' storica e chiusa e va misurato sull'intervallo
# 78647dd..fc9a8cd. Misurato contro l'albero di lavoro crescerebbe con la fase
# successiva, e il test fallirebbe non perche' questa fase abbia sconfinato ma
# perche' starebbe misurando l'intervallo sbagliato.
PHASE_END_SHA = "fc9a8cd7d9598e8cef0775aa76e40f2d4ed8d7aa"

ALLOWED_WRITE_PREFIXES = (
    "backend/pipeline/evidence/corpus/",
    "backend/tests/test_prototype_corpus_promotion_1_4.py",
    "benchmarks/mtb_evidence/evaluation/prototype_promotion_audit.py",
    "benchmarks/mtb_evidence/evaluation/prototype_promotion_reports.py",
    "benchmarks/mtb_evidence/evaluation/scripts/promote_qualified_claim_corpus_1_4.py",
    "benchmarks/mtb_evidence/v3/prototype_corpus_promotion_1_4/",
)

FROZEN_SHADOW_DIRS = tuple(SCOPE.FROZEN_SHADOW_DIRS.values()) + (
    f"benchmarks/mtb_evidence/v3/{CONTRACT.SOURCE_SHADOW_DIRNAME}",
    "benchmarks/mtb_evidence/v3/pre_promotion_audit_1_3",
)

# I moduli del percorso operativo. Il loader promosso non deve comparire in
# nessuno di essi: e' l'unica cosa che tiene distinti "promosso" e "in uso".
OPERATIONAL_MODULES = tuple(
    path
    for path in SCOPE.OPERATIONAL_ARTIFACTS
    if path.endswith(".py")
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class PromotedCorpusFixture(unittest.TestCase):
    """Base comune: il corpus promosso letto una volta sola."""

    sources: MAT.Sources
    artifacts: dict[str, str]
    corpus: LOADER.PromotedCorpus
    manifest: dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = load_sources()
        cls.artifacts = PROMOTION.build_artifacts(cls.sources)
        cls.corpus = LOADER.load(CORPUS)
        cls.manifest = dict(cls.corpus.manifest)


# --------------------------------------------------------------------------
# scrittura atomica
# --------------------------------------------------------------------------


class AtomicWriteTests(PromotedCorpusFixture):
    """La directory definitiva o e' completa, o non e' stata toccata."""

    def setUp(self) -> None:
        self._workspace = tempfile.TemporaryDirectory(prefix="atomic-write-")
        self.workspace = Path(self._workspace.name)
        self.destination = self.workspace / CONTRACT.CORPUS_DIRNAME
        self.addCleanup(self._workspace.cleanup)

    def _write(self, artifacts: dict[str, str], **kwargs: Any) -> ATOMIC.WriteOutcome:
        return ATOMIC.write_corpus_atomically(
            self.destination,
            artifacts,
            validate=PROMOTION.validate_written_corpus,
            manifest_name=CONTRACT.MANIFEST_FILE,
            **kwargs,
        )

    def test_a_complete_write_materializes_every_declared_file(self) -> None:
        outcome = self._write(dict(self.artifacts))
        written = sorted(item.name for item in self.destination.iterdir())
        self.assertEqual(written, sorted(CONTRACT.CORPUS_FILES))
        self.assertEqual(outcome.files_written, tuple(sorted(CONTRACT.CORPUS_FILES)))

    def test_the_write_is_verified_after_the_rename_and_not_before(self) -> None:
        outcome = self._write(dict(self.artifacts))
        steps = [step["step"] for step in outcome.log["steps"]]
        self.assertLess(steps.index("rename"), steps.index("verify_post_write"))
        self.assertTrue(all(step["outcome"] == "ok" for step in outcome.log["steps"]))

    def test_a_failure_before_the_rename_leaves_no_destination_at_all(self) -> None:
        with self.assertRaises(ATOMIC.InjectedFailure):
            self._write(dict(self.artifacts), fail_at="before_rename")
        self.assertFalse(self.destination.exists())

    def test_a_failure_before_the_rename_leaves_an_existing_corpus_untouched(self) -> None:
        self._write(dict(self.artifacts))
        before = ATOMIC.directory_hashes(self.destination)
        with self.assertRaises(ATOMIC.InjectedFailure):
            self._write(dict(self.artifacts), fail_at="before_rename")
        self.assertEqual(ATOMIC.directory_hashes(self.destination), before)

    def test_an_invalid_corpus_never_replaces_a_valid_one(self) -> None:
        self._write(dict(self.artifacts))
        before = ATOMIC.directory_hashes(self.destination)
        corrupted = dict(self.artifacts)
        corrupted["prognostic_claims.jsonl"] = '{"claim_id":"CLM-intruso"}\n'
        with self.assertRaises(PROMOTION.PromotionValidationError):
            self._write(corrupted)
        self.assertEqual(ATOMIC.directory_hashes(self.destination), before)

    def test_a_failure_after_generation_never_reaches_the_destination(self) -> None:
        with self.assertRaises(ATOMIC.InjectedFailure):
            self._write(dict(self.artifacts), fail_at="after_generation")
        self.assertFalse(self.destination.exists())

    def test_every_declared_failure_point_leaves_the_destination_consistent(self) -> None:
        for point in ATOMIC.FAILURE_POINTS:
            with self.subTest(point=point):
                workspace = tempfile.TemporaryDirectory(prefix="failure-point-")
                self.addCleanup(workspace.cleanup)
                destination = Path(workspace.name) / CONTRACT.CORPUS_DIRNAME
                try:
                    ATOMIC.write_corpus_atomically(
                        destination,
                        dict(self.artifacts),
                        validate=PROMOTION.validate_written_corpus,
                        manifest_name=CONTRACT.MANIFEST_FILE,
                        fail_at=point,
                    )
                except ATOMIC.InjectedFailure:
                    pass
                if destination.exists():
                    self.assertEqual(
                        sorted(item.name for item in destination.iterdir()),
                        sorted(CONTRACT.CORPUS_FILES),
                    )

    def test_an_abandoned_write_keeps_its_rollback_log(self) -> None:
        with self.assertRaises(ATOMIC.InjectedFailure):
            self._write(dict(self.artifacts), fail_at="before_rename")
        failed = [
            item
            for item in self.workspace.iterdir()
            if ATOMIC.FAILED_PREFIX in item.name
        ]
        self.assertEqual(len(failed), 1)
        log = _read_json(failed[0] / ATOMIC.ROLLBACK_LOG_FILE)
        self.assertEqual(log["steps"][-1]["step"], "abandon")
        self.assertTrue(
            any(step["outcome"] == "failed" for step in log["steps"])
        )

    def test_an_unknown_failure_point_is_rejected_instead_of_ignored(self) -> None:
        with self.assertRaises(ATOMIC.AtomicWriteError):
            self._write(dict(self.artifacts), fail_at="dopo_il_caffe")


class AtomicWriteValidationTests(PromotedCorpusFixture):
    """La validazione rifiuta prima del rename, non dopo."""

    def setUp(self) -> None:
        self._workspace = tempfile.TemporaryDirectory(prefix="atomic-validate-")
        self.destination = Path(self._workspace.name) / CONTRACT.CORPUS_DIRNAME
        self.addCleanup(self._workspace.cleanup)

    def _expect_rejection(self, artifacts: dict[str, str]) -> None:
        with self.assertRaises(PROMOTION.PromotionValidationError):
            ATOMIC.write_corpus_atomically(
                self.destination,
                artifacts,
                validate=PROMOTION.validate_written_corpus,
                manifest_name=CONTRACT.MANIFEST_FILE,
            )
        self.assertFalse(self.destination.exists())

    def test_a_hash_mismatch_stops_the_promotion(self) -> None:
        artifacts = dict(self.artifacts)
        artifacts["formulation_registry.jsonl"] = (
            artifacts["formulation_registry.jsonl"].rstrip("\n") + " \n"
        )
        self._expect_rejection(artifacts)

    def test_a_wrong_count_stops_the_promotion(self) -> None:
        artifacts = dict(self.artifacts)
        claims = [
            json.loads(line)
            for line in artifacts["evidence_claims.jsonl"].splitlines()
            if line.strip()
        ][:-1]
        artifacts["evidence_claims.jsonl"] = MAT.canonical_jsonl(claims, key="claim_id")
        manifest = json.loads(artifacts[CONTRACT.MANIFEST_FILE])
        manifest["artifact_sha256"]["evidence_claims.jsonl"] = MAT.sha256_text(
            artifacts["evidence_claims.jsonl"]
        )
        artifacts[CONTRACT.MANIFEST_FILE] = MAT.canonical_json(manifest)
        self._expect_rejection(artifacts)

    def test_a_claim_without_propagation_policy_stops_the_promotion(self) -> None:
        artifacts = dict(self.artifacts)
        claims = [
            json.loads(line)
            for line in artifacts["evidence_claims.jsonl"].splitlines()
            if line.strip()
        ]
        claims[0] = {
            key: value
            for key, value in claims[0].items()
            if key != "propagation_policy"
        }
        artifacts["evidence_claims.jsonl"] = MAT.canonical_jsonl(claims, key="claim_id")
        manifest = json.loads(artifacts[CONTRACT.MANIFEST_FILE])
        manifest["artifact_sha256"]["evidence_claims.jsonl"] = MAT.sha256_text(
            artifacts["evidence_claims.jsonl"]
        )
        artifacts[CONTRACT.MANIFEST_FILE] = MAT.canonical_json(manifest)
        self._expect_rejection(artifacts)

    def test_a_final_evaluable_claim_stops_the_promotion(self) -> None:
        artifacts = dict(self.artifacts)
        claims = [
            json.loads(line)
            for line in artifacts["evidence_claims.jsonl"].splitlines()
            if line.strip()
        ]
        claims[0] = dict(claims[0]) | {"final_evaluable": True}
        artifacts["evidence_claims.jsonl"] = MAT.canonical_jsonl(claims, key="claim_id")
        manifest = json.loads(artifacts[CONTRACT.MANIFEST_FILE])
        manifest["artifact_sha256"]["evidence_claims.jsonl"] = MAT.sha256_text(
            artifacts["evidence_claims.jsonl"]
        )
        artifacts[CONTRACT.MANIFEST_FILE] = MAT.canonical_json(manifest)
        self._expect_rejection(artifacts)

    def test_a_missing_file_stops_the_promotion(self) -> None:
        artifacts = {
            name: text
            for name, text in self.artifacts.items()
            if name != "qualified_evidence_views.jsonl"
        }
        self._expect_rejection(artifacts)


# --------------------------------------------------------------------------
# registro e rollback
# --------------------------------------------------------------------------


class PrototypeRegistryTests(unittest.TestCase):
    """Il registro distingue promosso da in uso, e non ammette di confonderli."""

    def setUp(self) -> None:
        self.registry = _read_json(REGISTRY_PATH)

    def test_the_registry_points_at_the_promoted_version(self) -> None:
        self.assertEqual(
            self.registry["active_prototype_corpus"], CONTRACT.REPOSITORY_VERSION
        )
        entry = self.registry["entries"][CONTRACT.REPOSITORY_VERSION]
        self.assertEqual(entry["status"], REGISTRY.STATUS_ACTIVE)
        self.assertEqual(entry["promotion_status"], "prototype_promoted")
        self.assertTrue(entry["prototype_promoted"])

    def test_the_entry_declares_every_required_field(self) -> None:
        entry = self.registry["entries"][CONTRACT.REPOSITORY_VERSION]
        for field in CONTRACT.registry_entry_fields():
            with self.subTest(field=field):
                self.assertIn(field, entry)

    def test_the_operational_retriever_is_not_bound(self) -> None:
        self.assertFalse(self.registry["operational_retriever_bound"])
        entry = self.registry["entries"][CONTRACT.REPOSITORY_VERSION]
        self.assertFalse(entry["operational_retriever_bound"])
        self.assertFalse(entry["clinical_readiness"])
        self.assertFalse(entry["final_evaluable"])

    def test_the_registry_declares_strict_verified_and_rejects_unknown_modes(self) -> None:
        entry = self.registry["entries"][CONTRACT.REPOSITORY_VERSION]
        self.assertEqual(entry["default_policy_mode"], "strict_verified")
        self.assertEqual(entry["unknown_policy_mode_behavior"], "reject")
        self.assertEqual(
            entry["allowed_policy_modes"], list(CONTRACT.ALLOWED_POLICY_MODES)
        )

    def test_the_entry_names_the_shadow_it_came_from(self) -> None:
        entry = self.registry["entries"][CONTRACT.REPOSITORY_VERSION]
        self.assertEqual(entry["source_shadow_version"], CONTRACT.SOURCE_SHADOW_VERSION)
        self.assertEqual(
            entry["source_shadow_sha256"], SCOPE.sha256_tree(SHADOW_V14)
        )

    def test_a_bound_entry_is_refused(self) -> None:
        entry = dict(
            REGISTRY.build_entry(source_shadow_sha256="a" * 64, corpus_sha256="b" * 64)
        ) | {"operational_retriever_bound": True}
        with self.assertRaises(REGISTRY.RegistryError):
            REGISTRY.validate_entry(entry)

    def test_a_clinically_ready_entry_is_refused(self) -> None:
        entry = dict(
            REGISTRY.build_entry(source_shadow_sha256="a" * 64, corpus_sha256="b" * 64)
        ) | {"clinical_readiness": True}
        with self.assertRaises(REGISTRY.RegistryError):
            REGISTRY.validate_entry(entry)

    def test_two_active_entries_are_refused(self) -> None:
        entry = REGISTRY.build_entry(
            source_shadow_sha256="a" * 64, corpus_sha256="b" * 64
        )
        registry = REGISTRY.register(REGISTRY.empty_registry(), entry)
        broken = dict(registry)
        broken["entries"] = dict(registry["entries"]) | {
            "qualified_claim_repository/9.9": dict(entry)
            | {"repository_version": "qualified_claim_repository/9.9"}
        }
        with self.assertRaises(REGISTRY.RegistryError):
            REGISTRY.validate(broken)


class RollbackTests(unittest.TestCase):
    """Il rollback ritira il puntatore, non i file, e la seconda volta non fa nulla."""

    def setUp(self) -> None:
        self._workspace = tempfile.TemporaryDirectory(prefix="rollback-")
        self.workspace = Path(self._workspace.name)
        self.addCleanup(self._workspace.cleanup)
        self.corpus = self.workspace / CORPUS.name
        self.registry = self.workspace / REGISTRY_PATH.name
        shutil.copytree(CORPUS, self.corpus)
        shutil.copyfile(REGISTRY_PATH, self.registry)

    def _rollback(self, **kwargs: Any) -> ROLLBACK.RollbackReport:
        return ROLLBACK.rollback(
            registry_path=self.registry, corpus_path=self.corpus, **kwargs
        )

    def test_the_first_rollback_retires_the_entry(self) -> None:
        report = self._rollback()
        self.assertTrue(report.changed)
        self.assertTrue(report.registry_entry_deactivated)
        self.assertIsNone(report.active_prototype_corpus_after)
        registry = _read_json(self.registry)
        self.assertEqual(
            registry["entries"][CONTRACT.REPOSITORY_VERSION]["status"],
            REGISTRY.STATUS_INACTIVE,
        )

    def test_the_second_rollback_is_indistinguishable_from_the_first(self) -> None:
        self._rollback()
        after_first = _read_json(self.registry)
        second = self._rollback()
        self.assertFalse(second.changed)
        self.assertEqual(_read_json(self.registry), after_first)

    def test_the_rollback_never_removes_lineage_or_the_promotion_log(self) -> None:
        self._rollback()
        for name in ROLLBACK.PRESERVED_FILES:
            with self.subTest(name=name):
                self.assertTrue((self.corpus / name).exists())

    def test_moving_to_inactive_keeps_every_byte(self) -> None:
        before = ATOMIC.directory_hashes(self.corpus)
        report = self._rollback(mode=ROLLBACK.MOVE_TO_INACTIVE)
        inactive = self.corpus.with_name(self.corpus.name + ROLLBACK.INACTIVE_SUFFIX)
        self.assertTrue(report.corpus_files_retained)
        self.assertTrue(inactive.is_dir())
        self.assertEqual(ATOMIC.directory_hashes(inactive), before)

    def test_after_a_rollback_the_registry_no_longer_resolves_a_corpus(self) -> None:
        self._rollback()
        with self.assertRaises(LOADER.PromotedCorpusError):
            LOADER.load_from_registry(self.registry)

    def test_the_rollback_observes_that_the_retriever_was_never_bound(self) -> None:
        self.assertFalse(self._rollback().operational_binding_observed)

    def test_an_unknown_rollback_mode_is_refused(self) -> None:
        with self.assertRaises(ROLLBACK.RollbackError):
            self._rollback(mode="cancella_tutto")

    def test_the_promoted_corpus_itself_was_not_rolled_back(self) -> None:
        rehearsal = _read_json(AUDIT_OUTPUT / "rollback_rehearsal.json")
        self.assertTrue(rehearsal["performed_on_copy"])
        self.assertFalse(rehearsal["performed_on_promoted_corpus"])
        self.assertTrue(rehearsal["idempotent"])
        self.assertEqual(
            _read_json(REGISTRY_PATH)["active_prototype_corpus"],
            CONTRACT.REPOSITORY_VERSION,
        )


# --------------------------------------------------------------------------
# loader
# --------------------------------------------------------------------------


class LoaderTests(PromotedCorpusFixture):
    """Il loader carica, verifica e rifiuta. Non scrive e non ordina."""

    def test_the_corpus_loads_completely(self) -> None:
        counts = self.corpus.counts()
        self.assertEqual(counts["active_claims_total"], 148)
        self.assertEqual(counts["parents"], 147)
        self.assertEqual(counts["deprecated_claims"], 4)
        self.assertEqual(counts["links"], 37)
        self.assertEqual(counts["views"], 4)
        self.assertEqual(counts["lineage_rows"], 4)

    def test_lookup_by_claim_id(self) -> None:
        claim = self.corpus.claim("CLM-01aba27a2fb14d531e2d")
        self.assertIsNotNone(claim)
        self.assertEqual(claim["graph_evidence_id"], "evidence:100001")

    def test_lookup_by_parent_id(self) -> None:
        children = self.corpus.claims_for_parent("GEP-d8e0a9d42a7e653f4a53")
        self.assertEqual(
            sorted(child["claim_id"] for child in children),
            ["CLM-9ab06b6945feea941252", "CLM-ac64c0e56246f6ea29ca"],
        )

    def test_a_retired_claim_redirects_to_its_replacement(self) -> None:
        for old, new in (
            ("CLM-2175b95ae3113c4f5d97", "CLM-8941c177da91f66ff93a"),
            ("CLM-7056003a9bdef747f514", "CLM-a7e1c40b794d2c4d4ca8"),
            ("CLM-a7c903cf8d423f015e29", "CLM-90e863f00f134fc3cd3d"),
            ("CLM-aae818bbc8ec735a255d", "CLM-5071bb2d8657ac0fbed0"),
        ):
            with self.subTest(old=old):
                self.assertIsNone(self.corpus.claim(old))
                self.assertTrue(self.corpus.is_retired(old))
                self.assertEqual(self.corpus.redirect(old), new)
                self.assertEqual(self.corpus.resolve(old)["claim_id"], new)

    def test_lookup_by_legacy_statement_id(self) -> None:
        found = self.corpus.claims_for_legacy_statement("ES-V2-evidence-100001")
        self.assertEqual(
            [claim["claim_id"] for claim in found], ["CLM-01aba27a2fb14d531e2d"]
        )

    def test_a_hash_mismatch_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="loader-hash-") as workspace:
            copy = Path(workspace) / CORPUS.name
            shutil.copytree(CORPUS, copy)
            target = copy / "formulation_registry.jsonl"
            target.write_text(
                target.read_text(encoding="utf-8") + "\n", encoding="utf-8", newline="\n"
            )
            with self.assertRaises(LOADER.CorpusHashMismatch):
                LOADER.load(copy)

    def test_an_incompatible_schema_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="loader-schema-") as workspace:
            copy = Path(workspace) / CORPUS.name
            shutil.copytree(CORPUS, copy)
            manifest_path = copy / CONTRACT.MANIFEST_FILE
            manifest = _read_json(manifest_path)
            manifest["schema_version"] = "promoted_corpus_schema/9.9"
            manifest_path.write_text(
                MAT.canonical_json(manifest), encoding="utf-8", newline="\n"
            )
            with self.assertRaises(LOADER.CorpusSchemaError):
                LOADER.load(copy)

    def test_an_incompatible_repository_version_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="loader-version-") as workspace:
            copy = Path(workspace) / CORPUS.name
            shutil.copytree(CORPUS, copy)
            manifest_path = copy / CONTRACT.MANIFEST_FILE
            manifest = _read_json(manifest_path)
            manifest["repository_version"] = "qualified_claim_repository/9.9"
            manifest_path.write_text(
                MAT.canonical_json(manifest), encoding="utf-8", newline="\n"
            )
            with self.assertRaises(LOADER.CorpusSchemaError):
                LOADER.load(copy)

    def test_a_record_without_propagation_policy_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="loader-policy-") as workspace:
            copy = Path(workspace) / CORPUS.name
            shutil.copytree(CORPUS, copy)
            path = copy / "evidence_claims.jsonl"
            rows = _read_jsonl(path)
            rows[0] = {
                key: value
                for key, value in rows[0].items()
                if key != "propagation_policy"
            }
            path.write_text(
                MAT.canonical_jsonl(rows, key="claim_id"), encoding="utf-8", newline="\n"
            )
            with self.assertRaises(LOADER.CorpusSchemaError):
                LOADER.load(copy, verify_hashes=False)

    def test_an_unknown_policy_mode_is_rejected_and_not_widened(self) -> None:
        for mode in ("audit", "permissive", "STRICT_VERIFIED", ""):
            with self.subTest(mode=mode):
                with self.assertRaises(LOADER.CorpusPolicyModeError):
                    LOADER.load(CORPUS, policy_mode=mode)

    def test_an_unspecified_mode_resolves_to_strict_verified(self) -> None:
        self.assertEqual(LOADER.load(CORPUS).policy_mode, "strict_verified")
        self.assertEqual(
            LOADER.load(CORPUS, policy_mode="strict_verified").policy_mode,
            "strict_verified",
        )

    def test_loading_does_not_modify_a_single_byte(self) -> None:
        before = ATOMIC.directory_hashes(CORPUS)
        LOADER.load(CORPUS)
        LOADER.load_from_registry(REGISTRY_PATH)
        self.assertEqual(ATOMIC.directory_hashes(CORPUS), before)

    def test_the_loaded_corpus_is_frozen(self) -> None:
        with self.assertRaises(Exception):
            self.corpus.claims = ()  # type: ignore[misc]

    def test_the_loader_does_not_rank(self) -> None:
        source = (
            Path(LOADER.__file__).read_text(encoding="utf-8")
        )
        for forbidden in ("score", "top_k", "ranking", "bucket"):
            with self.subTest(token=forbidden):
                self.assertNotIn(f"def {forbidden}", source)
        self.assertNotIn("qualified_retriever", source)
        self.assertNotIn("qualified_retrieval_scoring", source)

    def test_no_operational_module_imports_the_promoted_namespace(self) -> None:
        for relpath in OPERATIONAL_MODULES:
            with self.subTest(module=relpath):
                source = (REPO_ROOT / relpath).read_text(encoding="utf-8")
                self.assertNotIn("evidence.corpus", source)
                self.assertNotIn("evidence import corpus", source)


# --------------------------------------------------------------------------
# inventario promosso
# --------------------------------------------------------------------------


class PromotedInventoryTests(PromotedCorpusFixture):
    """I conteggi sono derivati dai file promossi, non letti dal manifest."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.derived = MAT.derived_counts(
            claims=cls.corpus.claims,
            parents=cls.corpus.parents,
            deprecated=cls.corpus.deprecated,
            unsupported=cls.corpus.unsupported,
            unresolved=cls.corpus.unresolved,
        )

    def test_every_expected_count_matches(self) -> None:
        for key, expected in sorted(CONTRACT.EXPECTED_COUNTS.items()):
            with self.subTest(count=key):
                self.assertEqual(self.derived[key], expected)

    def test_the_manifest_agrees_with_what_the_files_say(self) -> None:
        for key, value in sorted(self.derived.items()):
            with self.subTest(count=key):
                self.assertEqual(self.manifest["counts"][key], value)
        self.assertTrue(self.manifest["counts_match_expected"])

    def test_the_claim_type_breakdown_is_the_expected_one(self) -> None:
        self.assertEqual(
            self.derived["by_claim_type"],
            {
                "aggregate_intervention_claim": 3,
                "atomic_intervention_claim": 140,
                "diagnostic_claim": 2,
                "regimen_claim": 3,
            },
        )

    def test_the_domain_files_are_a_projection_of_the_claim_file(self) -> None:
        for domain, filename in (
            ("therapeutic", "therapeutic_claims.jsonl"),
            ("diagnostic", "diagnostic_claims.jsonl"),
            ("prognostic", "prognostic_claims.jsonl"),
        ):
            with self.subTest(domain=domain):
                projected = MAT.domain_projection(self.corpus.claims, domain)
                self.assertEqual(_read_jsonl(CORPUS / filename), projected)

    def test_no_deprecated_claim_appears_among_the_active_ones(self) -> None:
        active = {claim["claim_id"] for claim in self.corpus.claims}
        retired = {row["claim_id"] for row in self.corpus.deprecated}
        self.assertEqual(sorted(active & retired), [])
        self.assertEqual(len(retired), 4)

    def test_there_are_no_orphans_and_no_collisions(self) -> None:
        self.assertEqual(self.derived["orphan_claims"], 0)
        self.assertEqual(self.derived["id_collisions"], 0)
        self.assertEqual(self.derived["deduplications"], 0)

    def test_three_parents_carry_no_claim(self) -> None:
        parents = self.corpus.parents_without_claims()
        self.assertEqual(
            sorted(parent["graph_evidence_id"] for parent in parents),
            ["evidence:347", "evidence:3811", "evidence:4759"],
        )


class PropagationTests(PromotedCorpusFixture):
    """Promuovere non valida: i campi di governance restano quelli che erano."""

    def test_every_active_claim_declares_its_propagation_policy(self) -> None:
        for claim in self.corpus.claims:
            with self.subTest(claim=claim["claim_id"]):
                PROP.validate_record(claim)
                self.assertIsNotNone(claim["propagation_policy"])

    def test_every_active_claim_is_prototype_only(self) -> None:
        policies = {claim["propagation_policy"] for claim in self.corpus.claims}
        self.assertEqual(policies, {"prototype_only"})

    def test_no_active_claim_is_final_evaluable_or_hard_filterable(self) -> None:
        self.assertEqual(
            [c["claim_id"] for c in self.corpus.claims if c["final_evaluable"]], []
        )
        self.assertEqual(
            [c["claim_id"] for c in self.corpus.claims if c["hard_filterable"]], []
        )

    def test_every_retired_claim_declares_its_propagation_policy_too(self) -> None:
        for claim in self.corpus.deprecated:
            with self.subTest(claim=claim["claim_id"]):
                PROP.validate_record(claim)
                self.assertEqual(claim["propagation_policy"], "prototype_only")
                self.assertFalse(claim["final_evaluable"])

    def test_aggregates_and_regimens_still_forbid_member_propagation(self) -> None:
        non_atomic = [
            claim
            for claim in self.corpus.claims
            if claim["claim_type"] in PROP.NON_ATOMIC_CLAIM_TYPES
        ]
        self.assertEqual(len(non_atomic), 6)
        for claim in non_atomic:
            with self.subTest(claim=claim["claim_id"]):
                self.assertFalse(claim[PROP.MEMBER_PROPAGATION_FIELD])

    def test_the_promotion_declared_but_never_deduced_the_missing_fields(self) -> None:
        log = _read_json(CORPUS / "promotion_log.json")
        normalization = log["deprecated_schema_normalization"]
        self.assertEqual(normalization["claims_normalized"], 2)
        self.assertEqual(normalization["changed_claim_ids"], 0)
        self.assertEqual(normalization["changed_propositions"], 0)
        self.assertEqual(
            normalization["declared_values"]["propagation_policy"], "prototype_only"
        )


# --------------------------------------------------------------------------
# lineage, link, view
# --------------------------------------------------------------------------


class LineageTests(PromotedCorpusFixture):
    """Il lineage e' completo nelle due direzioni."""

    def test_every_retired_claim_has_a_redirect(self) -> None:
        retired = {row["claim_id"] for row in self.corpus.deprecated}
        redirected = {row["old_claim_id"] for row in self.corpus.lineage}
        self.assertEqual(sorted(retired - redirected), [])

    def test_every_redirect_target_is_active(self) -> None:
        active = {claim["claim_id"] for claim in self.corpus.claims}
        targets = {row["new_claim_id"] for row in self.corpus.lineage}
        self.assertEqual(sorted(targets - active), [])

    def test_no_retired_claim_is_reachable_from_the_primary_lookup(self) -> None:
        for row in self.corpus.deprecated:
            with self.subTest(claim=row["claim_id"]):
                self.assertIsNone(self.corpus.claim(row["claim_id"]))

    def test_the_lineage_carries_both_shadow_phases(self) -> None:
        sources = {row["lineage_source"] for row in self.corpus.lineage}
        self.assertEqual(
            sources,
            {
                CONTRACT.SOURCE_SHADOW_BASE_DIRNAME,
                "diagnostic_disease_scope_narrowing_shadow",
            },
        )

    def test_the_named_endpoints_resolve_the_way_the_phase_declared(self) -> None:
        probes = self.manifest["lineage"]["probes"]
        self.assertEqual(sorted(probes), sorted(CONTRACT.LINEAGE_PROBE_IDS))

        for evidence_id in ("evidence:1846", "evidence:1847", "evidence:1851", "evidence:1853"):
            with self.subTest(endpoint=evidence_id):
                probe = probes[evidence_id]
                self.assertEqual(len(probe["active_claim_ids"]), 1)
                self.assertEqual(len(probe["retired_claim_ids"]), 1)

        for evidence_id in ("evidence:347", "evidence:3811", "evidence:4759"):
            with self.subTest(endpoint=evidence_id):
                probe = probes[evidence_id]
                self.assertEqual(probe["active_claim_ids"], [])
                self.assertEqual(len(probe["parent_ids"]), 1)

        self.assertEqual(
            probes["evidence:3811"]["unresolved_association_ids"],
            ["UNR-bc192774b66116745142", "UNR-cc554dd0543c62b87120", "UNR-daa72cbff92e7435e1dc"],
        )
        self.assertEqual(
            probes["evidence:4759"]["unsupported_association_ids"],
            ["UNS-f48e93e6069b8e3da21e", "UNS-fb9ef28c06cdd1fb8352"],
        )
        self.assertEqual(len(probes["evidence:11240"]["active_claim_ids"]), 2)

    def test_every_claim_resolves_to_its_parent(self) -> None:
        for claim in self.corpus.claims:
            with self.subTest(claim=claim["claim_id"]):
                self.assertIsNotNone(self.corpus.parent(claim["parent_id"]))


class QualificationLinkTests(PromotedCorpusFixture):
    """Le 37 azioni, applicate nella sola namespace V3."""

    def test_all_thirty_seven_actions_are_applied(self) -> None:
        self.assertEqual(len(self.corpus.links), CONTRACT.EXPECTED_LINK_ACTIONS)
        self.assertTrue(all(link["executed"] for link in self.corpus.links))

    def test_they_are_applied_in_the_promoted_namespace_only(self) -> None:
        for link in self.corpus.links:
            with self.subTest(link=link["link_id"]):
                self.assertEqual(
                    link["applied_in_namespace"], CONTRACT.PROMOTED_CORPUS_RELPATH
                )
                self.assertFalse(link["historical_plan_executed"])

    def test_the_shadow_plan_still_says_the_actions_were_not_executed(self) -> None:
        plan = _read_jsonl(SOURCE_FILES["link plan 1.4"])
        self.assertEqual(len(plan), CONTRACT.EXPECTED_LINK_ACTIONS)
        self.assertTrue(all(not action["executed"] for action in plan))

    def test_no_active_link_targets_a_retired_claim(self) -> None:
        active = [
            link for link in self.corpus.links if link["link_state"] == LV.LINK_ACTIVE
        ]
        self.assertEqual(len(active), 17)
        for link in active:
            with self.subTest(link=link["link_id"]):
                self.assertTrue(link["target_is_active_claim"])
                self.assertFalse(link["target_is_deprecated_claim"])

    def test_there_are_no_duplicates(self) -> None:
        ids = [link["link_id"] for link in self.corpus.links]
        self.assertEqual(len(ids), len(set(ids)))

    def test_source_units_and_locators_are_preserved(self) -> None:
        rows = _read_jsonl(AUDIT_OUTPUT / "qualification_link_application.jsonl")
        self.assertEqual(len(rows), CONTRACT.EXPECTED_LINK_ACTIONS)
        for row in rows:
            with self.subTest(plan=row["plan_id"]):
                self.assertTrue(row["source_unit_preserved"])
                self.assertTrue(row["locator_preserved"])
                self.assertTrue(row["reason_code_preserved"])

    def test_the_schema_is_uniform(self) -> None:
        versions = {link["schema_version"] for link in self.corpus.links}
        self.assertEqual(versions, {LV.LINK_SCHEMA_VERSION})


class QualifiedViewTests(PromotedCorpusFixture):
    """Le 4 azioni di view, senza appiattimenti e senza ranking cross-domain."""

    def test_all_four_actions_are_applied(self) -> None:
        self.assertEqual(len(self.corpus.views), CONTRACT.EXPECTED_VIEW_ACTIONS)
        self.assertTrue(all(view["executed"] for view in self.corpus.views))

    def test_two_views_are_materialized_and_two_are_verified(self) -> None:
        states = [view["view_state"] for view in self.corpus.views]
        self.assertEqual(states.count(LV.VIEW_MATERIALIZED), 2)
        self.assertEqual(states.count(LV.VIEW_VERIFIED), 2)

    def test_diagnostic_claims_land_in_the_diagnostic_section(self) -> None:
        materialized = [
            view for view in self.corpus.views if view["view_state"] == LV.VIEW_MATERIALIZED
        ]
        for view in materialized:
            with self.subTest(view=view["view_id"]):
                self.assertEqual(view["claim_domain"], "diagnostic")
                self.assertEqual(view["view_section"], "diagnostic")
                self.assertFalse(view["therapy_score_present"])

    def test_no_view_declares_cross_domain_ranking(self) -> None:
        for view in self.corpus.views:
            with self.subTest(view=view["plan_id"]):
                self.assertFalse(view["cross_domain_ranking"])

    def test_aggregates_and_regimens_are_not_flattened(self) -> None:
        for view in self.corpus.views:
            with self.subTest(view=view["plan_id"]):
                self.assertEqual(view["flattened_members"], [])

    def test_no_view_is_orphan(self) -> None:
        active = {claim["claim_id"] for claim in self.corpus.claims}
        for view in self.corpus.views:
            with self.subTest(view=view["plan_id"]):
                self.assertIn(view["claim_id"], active)


# --------------------------------------------------------------------------
# terminologia e forme
# --------------------------------------------------------------------------


class TerminologyAndFormulationTests(PromotedCorpusFixture):
    """Le decisioni congelate restano congelate: la promozione non ne risolve nessuna."""

    def test_auy922_is_still_unresolved(self) -> None:
        registry = self.corpus.terminology_registry
        unresolved = [
            row
            for row in registry["unresolved_mappings"]
            if row["terminology_decision_id"] == CONTRACT.UNRESOLVED_TERMINOLOGY_DECISION
        ]
        self.assertEqual(len(unresolved), 1)
        self.assertFalse(unresolved[0]["is_verified"])
        self.assertEqual(unresolved[0]["source_literal_term"], "AUY922")
        self.assertEqual(unresolved[0]["recommendation"], "require_external_review")
        self.assertTrue(self.manifest["terminology"]["auy922_unresolved"])

    def test_bgj398_stays_verified_and_its_source_literal_preserved(self) -> None:
        applied = [
            row
            for row in self.corpus.terminology_registry["applied_mappings"]
            if row["terminology_decision_id"] == CONTRACT.VERIFIED_TERMINOLOGY_DECISION
        ]
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0]["canonical_label"], "infigratinib")
        self.assertEqual(applied[0]["source_literal_term"], "BGJ398")
        self.assertTrue(applied[0]["source_literal_preserved"])

    def test_the_promotion_introduced_no_new_mapping(self) -> None:
        terminology = self.manifest["terminology"]
        self.assertEqual(terminology["new_mappings_introduced_by_promotion"], 0)
        self.assertEqual(terminology["collisions"], 0)
        self.assertEqual(terminology["deduplications"], 0)
        self.assertFalse(terminology["suffix_normalization_used"])
        self.assertTrue(terminology["external_terminology_review_pending"])

    def test_the_formulation_registry_still_holds_one_verified_relation(self) -> None:
        self.assertEqual(len(self.corpus.formulation_registry), 1)
        entry = self.corpus.formulation_registry[0]
        self.assertEqual(entry["form_label"], "infigratinib phosphate")
        self.assertEqual(entry["relation_status"], "verified")
        self.assertEqual(entry["canonical_active_moiety"], "infigratinib")

    def test_the_salt_coverage_cost_is_recorded_and_not_relaxed(self) -> None:
        formulation = self.manifest["formulation"]
        self.assertEqual(
            formulation["salt_form_claims_outside_primary_for_bare_moiety_query"], 12
        )
        self.assertEqual(len(formulation["salt_form_claim_ids"]), 12)
        self.assertFalse(formulation["salt_gate_relaxed_by_promotion"])
        self.assertEqual(formulation["new_forms_resolved_by_promotion"], 0)
        self.assertFalse(formulation["suffix_normalization_used"])

    def test_the_salt_claims_are_the_ones_the_shadow_named(self) -> None:
        declared = _read_json(SHADOW_V14 / "backward_compatibility_addendum.json")
        self.assertEqual(
            self.manifest["formulation"]["salt_form_claim_ids"],
            sorted(declared["formulation_behaviour_change"]["claims_leaving_primary_bucket"]),
        )

    def test_the_two_named_forms_keep_their_buckets(self) -> None:
        formulation = self.manifest["formulation"]
        self.assertIn("infigratinib hydrochloride", formulation["audit_only_forms"])
        self.assertEqual(
            formulation["retained_with_warning_forms"], ["infigratinib phosphate"]
        )


# --------------------------------------------------------------------------
# integrita' operativa
# --------------------------------------------------------------------------


class OperationalIntegrityTests(unittest.TestCase):
    """Nulla di operativo e' cambiato, e la prova non e' una dichiarazione."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.integrity = _read_json(AUDIT_OUTPUT / "operational_integrity.json")

    def test_no_frozen_artifact_changed(self) -> None:
        self.assertTrue(self.integrity["all_frozen_artifacts_unchanged"])
        self.assertEqual(self.integrity["changed"], [])

    def test_the_operational_files_still_hash_to_what_the_phase_recorded(self) -> None:
        for role, path in sorted(SCOPE.OPERATIONAL_ROLES.items()):
            with self.subTest(role=role):
                self.assertEqual(
                    SCOPE.sha256_file(REPO_ROOT / path),
                    self.integrity["frozen_sha256"][role],
                )

    def test_the_shadow_repositories_are_unchanged(self) -> None:
        for role, path in sorted(SCOPE.FROZEN_SHADOW_DIRS.items()):
            with self.subTest(role=role):
                self.assertEqual(
                    SCOPE.sha256_tree(REPO_ROOT / path),
                    self.integrity["frozen_tree_sha256"][role],
                )

    def test_the_shadow_1_4_is_unchanged(self) -> None:
        self.assertEqual(
            SCOPE.sha256_tree(SHADOW_V14),
            self.integrity["frozen_tree_sha256"]["shadow repository 1.4"],
        )

    def test_the_pre_promotion_audit_is_unchanged(self) -> None:
        self.assertEqual(
            SCOPE.sha256_tree(SCOPE.V3 / "pre_promotion_audit_1_3"),
            self.integrity["frozen_tree_sha256"]["pre-promotion audit 1.3"],
        )

    def test_the_operational_query_is_identical_before_and_after(self) -> None:
        query = self.integrity["operational_query"]
        self.assertTrue(query["parity"])
        self.assertEqual(query["before"], query["after"])
        self.assertEqual(query["after"]["sha256"], query["baseline_sha256"])

    def test_the_operational_query_still_returns_the_same_result_today(self) -> None:
        current = operational_query()
        self.assertEqual(current, self.integrity["operational_query"]["after"])

    def test_the_gold_was_never_deserialized(self) -> None:
        gold = self.integrity["gold"]
        self.assertEqual(gold["gold_records_read"], 0)
        self.assertFalse(gold["used_for_any_decision"])
        self.assertTrue(gold["checksum_only_no_deserialization"])

    def test_no_source_of_the_promotion_is_a_gold_artifact(self) -> None:
        read = [
            path.relative_to(REPO_ROOT).as_posix() for path in SOURCE_FILES.values()
        ]
        self.assertEqual(SCOPE.gold_paths_touched(read), [])


class PromotionDiffTests(PromotedCorpusFixture):
    """Il diff e' derivato dalla 1.4, non copiato da quello della 1.3."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.diff = _read_json(AUDIT_OUTPUT / "promotion_diff.json")

    def test_the_diff_names_the_version_it_derives_from(self) -> None:
        self.assertEqual(self.diff["derived_from"], CONTRACT.SOURCE_SHADOW_VERSION)
        self.assertFalse(self.diff["derived_from_previous_diff"])

    def test_no_claim_id_changed(self) -> None:
        self.assertEqual(self.diff["claim_ids_changed"], 0)
        self.assertEqual(self.diff["claim_ids_added"], [])
        self.assertEqual(self.diff["claim_ids_removed"], [])

    def test_the_promoted_ids_are_exactly_the_shadow_ids(self) -> None:
        shadow = sorted(
            row["claim_id"] for row in _read_jsonl(SOURCE_FILES["claims 1.4"])
        )
        promoted = sorted(claim["claim_id"] for claim in self.corpus.claims)
        self.assertEqual(promoted, shadow)

    def test_the_promoted_claim_file_is_byte_identical_to_the_shadow(self) -> None:
        self.assertEqual(
            SCOPE.sha256_file(CORPUS / "evidence_claims.jsonl"),
            SCOPE.sha256_file(SOURCE_FILES["claims 1.4"]),
        )

    def test_no_operational_file_changed(self) -> None:
        self.assertEqual(self.diff["operational_files_changed"], 0)
        self.assertFalse(self.diff["operational_query_behavior_changed"])
        self.assertFalse(
            self.diff["registry_changes"]["operational_configuration_changed"]
        )
        self.assertFalse(
            self.diff["registry_changes"]["operational_retriever_bound_after"]
        )

    def test_the_diff_counts_what_was_created(self) -> None:
        self.assertEqual(self.diff["files_created_count"], len(CONTRACT.CORPUS_FILES))
        self.assertEqual(self.diff["active_rows"], 148)
        self.assertEqual(self.diff["deprecated_rows"], 4)
        self.assertEqual(self.diff["links_applied"], 37)
        self.assertEqual(self.diff["views_materialized"], 2)

    def test_the_schema_change_touched_no_proposition(self) -> None:
        schema = self.diff["schema_changes"]
        self.assertEqual(schema["propositions_affected_by_schema_change"], 0)
        self.assertEqual(self.diff["propositions_added"], 0)
        self.assertEqual(self.diff["propositions_removed"], 0)
        self.assertEqual(
            schema["deprecated_claims_declared_propagation_fields"],
            ["CLM-a7c903cf8d423f015e29", "CLM-aae818bbc8ec735a255d"],
        )


class ReadinessTests(unittest.TestCase):
    """La readiness dice cio' che la fase ha verificato, e non piu' di quello."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.readiness = _read_json(AUDIT_OUTPUT / "promotion_readiness.json")

    def test_the_expected_flags_hold(self) -> None:
        expected = {
            "all_claims_prototype_only": True,
            "atomic_write_verified": True,
            "clinical_readiness": False,
            "full_exploratory_rerun_ready": False,
            "no_claim_final_evaluable": True,
            "operational_pipeline_unchanged": True,
            "operational_retriever_bound": False,
            "operational_retriever_migration_ready": True,
            "promoted_inventory_consistent": True,
            "promoted_lineage_complete": True,
            "promoted_links_consistent": True,
            "promoted_views_consistent": True,
            "prototype_corpus_promotion_applied": True,
            "prototype_corpus_registry_updated": True,
            "rollback_tested": True,
            "strict_default_explicit": True,
            "unknown_mode_rejected": True,
        }
        for key, value in sorted(expected.items()):
            with self.subTest(flag=key):
                self.assertEqual(self.readiness[key], value)

    def test_promotion_does_not_claim_clinical_validity(self) -> None:
        self.assertFalse(self.readiness["clinical_readiness"])
        self.assertFalse(self.readiness["full_exploratory_rerun_ready"])


# --------------------------------------------------------------------------
# determinismo
# --------------------------------------------------------------------------


class DeterminismTests(PromotedCorpusFixture):
    """La generazione e' funzione delle sorgenti, non dell'ambiente."""

    def test_two_generations_produce_the_same_bytes(self) -> None:
        again = PROMOTION.build_artifacts(load_sources())
        self.assertEqual(again, self.artifacts)

    def test_reversing_the_input_order_changes_nothing(self) -> None:
        reversed_sources = MAT.Sources(
            claims=tuple(reversed(self.sources.claims)),
            parents=tuple(reversed(self.sources.parents)),
            deprecated=tuple(reversed(self.sources.deprecated)),
            unsupported=tuple(reversed(self.sources.unsupported)),
            unresolved=tuple(reversed(self.sources.unresolved)),
            lineage_rows=tuple(reversed(self.sources.lineage_rows)),
            diagnostic_replacements=tuple(
                reversed(self.sources.diagnostic_replacements)
            ),
            terminology_registry=self.sources.terminology_registry,
            formulation_registry=tuple(reversed(self.sources.formulation_registry)),
            formulation_gate_simulation=tuple(
                reversed(self.sources.formulation_gate_simulation)
            ),
            salt_claims_leaving_primary=tuple(
                reversed(self.sources.salt_claims_leaving_primary)
            ),
            disease_relation_definitions=self.sources.disease_relation_definitions,
            disease_policy_modes=self.sources.disease_policy_modes,
            disease_match_contract=self.sources.disease_match_contract,
            verified_alias_registry=self.sources.verified_alias_registry,
            link_plan=tuple(reversed(self.sources.link_plan)),
            view_plan=tuple(reversed(self.sources.view_plan)),
            source_file_sha256=self.sources.source_file_sha256,
            source_shadow_sha256=self.sources.source_shadow_sha256,
        )
        self.assertEqual(PROMOTION.build_artifacts(reversed_sources), self.artifacts)

    def test_the_written_corpus_matches_what_the_generator_produces(self) -> None:
        for name, text in sorted(self.artifacts.items()):
            with self.subTest(artifact=name):
                self.assertEqual(
                    (CORPUS / name).read_text(encoding="utf-8"), text
                )

    def test_the_promotion_timestamp_is_a_phase_constant(self) -> None:
        self.assertEqual(self.manifest["promoted_at"], CONTRACT.PROMOTED_AT)
        self.assertEqual(self.manifest["promotion_commit"], START_SHA)


# --------------------------------------------------------------------------
# perimetro
# --------------------------------------------------------------------------


class PhasePerimeterTests(unittest.TestCase):
    """Il perimetro della fase, misurato su un intervallo chiuso di commit."""

    def test_the_phase_wrote_only_inside_its_own_perimeter(self) -> None:
        if not PHASE_END_SHA:
            self.skipTest("la fase non e' ancora chiusa: nessun estremo da misurare")
        scope_ = PhaseScope(
            REPO_ROOT.parent, START_SHA, PHASE_END_SHA, ALLOWED_WRITE_PREFIXES
        )
        self.assertEqual(scope_.violations(scope_.changed_paths()), [])

    def test_no_frozen_path_is_writable(self) -> None:
        for path in tuple(SCOPE.OPERATIONAL_ARTIFACTS) + FROZEN_SHADOW_DIRS:
            with self.subTest(path=path):
                self.assertFalse(path.startswith(ALLOWED_WRITE_PREFIXES))

    def test_the_promoted_namespace_is_not_an_operational_path(self) -> None:
        for path in SCOPE.OPERATIONAL_ARTIFACTS:
            with self.subTest(path=path):
                self.assertFalse(path.startswith(CONTRACT.PROMOTED_CORPUS_RELPATH))
                self.assertNotEqual(path, CONTRACT.REGISTRY_RELPATH)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

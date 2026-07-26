"""Protegge il perimetro non terapeutico e il lineage degli artefatti.

Tutto offline. Il gold non viene letto. Gli artefatti congelati che l'erratum
corregge devono restare invariati: la correzione vive accanto, non al loro posto.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation.non_therapeutic_claim_contract import (
    ALL_CLAIM_TYPES,
    AUDIT_VERDICTS,
    ContractError,
    NON_CLAIM_OBJECT_KINDS,
    NON_THERAPEUTIC_CLAIM_TYPES,
    PREDICTIVE_CLAIM_ASSESSMENT,
    QUERY_TYPES,
    THERAPEUTIC_CLAIM_TYPES,
    check_materialisation_preconditions,
    claim_id,
    claims_for_verdict,
    primary_eligible,
    rejection_reason,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_non_therapeutic_claim_contract import (
    build,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
OUT = V3 / "non_therapeutic_claim_contract_and_erratum"
ADJ = V3 / "multi_intervention_adjudication"
SHADOW = V3 / "typed_claim_shadow_migration"

START_SHA = "b9773757a79fbdea639525aff2f26bdbf15bb2d1"
# La fase si chiude sull'ultimo commit di contenuto. L'estremo e' fisso e non
# `HEAD`: `HEAD` cresce a ogni commit successivo e riporterebbe il controllo a
# essere aperto, che e' il difetto corretto dall'helper di perimetro.
PHASE_END_SHA = "9723d2779a86899ebd9fce8d585a358b8d3fbe56"

AUDITED = ("evidence:347", "evidence:1846", "evidence:1847")

# Hash registrati dal manifest dell'adjudication, cioe' dallo stato congelato
# prima di questa fase. L'erratum li cita; i file non devono cambiare.
FROZEN_ORIGINALS = {
    "multi_intervention_adjudication/migration_specification.json": "20d6399634e577a72b06bac5bb0943e29bf548b96e4ad47107180dcb4423ed3b",
    "multi_intervention_adjudication/post_adjudication_schema_simulation.json": "ddd7bcf04b45c60ea89f230918c0ee46277068b248934b4c6cb57a778ceba95f",
    "multi_intervention_adjudication/ADAPTER_MIGRATION_SPECIFICATION.md": "b92a3dafb2bef0e396fabd0270d9ac33b8daa00fe6ca48c78188e820cfca4124",
}

FROZEN_OPERATIONAL_PATHS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
)


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ArtifactCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = build()
        cls.audit = {
            r["graph_evidence_id"]: r
            for r in load_jsonl(OUT / "non_therapeutic_record_audit.jsonl")
        }
        cls.inventory = load_json(OUT / "amended_shadow_simulation.json")
        cls.erratum = load_json(OUT / "adjudication_erratum.json")
        cls.amended = load_json(OUT / "migration_specification_amended.json")
        cls.manifest = load_json(OUT / "review_manifest.json")
        cls.simulated = load_jsonl(OUT / "claim_id_simulation.jsonl")


# ── audit dei tre record ──────────────────────────────────────────────────────


class TestThreeRecordsAudited(ArtifactCase):
    def test_all_three_records_are_audited(self) -> None:
        self.assertEqual(sorted(self.audit), sorted(AUDITED))
        scope = load_json(OUT / "audit_scope.json")
        self.assertTrue(scope["scope_is_complete"])

    def test_every_verdict_is_from_the_declared_vocabulary(self) -> None:
        for graph_evidence_id, record in sorted(self.audit.items()):
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertIn(record["verdict"], AUDIT_VERDICTS)

    def test_evidence_347_is_unresolved_and_its_graph_label_is_contradicted(self) -> None:
        record = self.audit["evidence:347"]
        self.assertEqual(record["verdict"], "non_therapeutic_claim_unresolved")
        self.assertFalse(record["prognostic_claim_supported"])
        self.assertFalse(record["diagnostic_claim_supported"])
        self.assertTrue(record["graph_classification_contradicted_by_source"])
        self.assertTrue(record["treatment_effect_reported"])
        self.assertFalse(record["prognostic_outcome_reported_for_biomarker"])
        self.assertTrue(record["requires_full_text"])
        self.assertIn("GRAPH_DIRECTION_CONTRADICTED_BY_SOURCE", record["reason_codes"])

    def test_evidence_1846_and_1847_are_diagnostic(self) -> None:
        for graph_evidence_id in ("evidence:1846", "evidence:1847"):
            record = self.audit[graph_evidence_id]
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(record["verdict"], "diagnostic_claim_supported")
                self.assertTrue(record["diagnostic_claim_supported"])
                self.assertFalse(record["prognostic_claim_supported"])
                self.assertEqual(
                    record["diagnostic_interpretation"], "subtype_defining_alteration"
                )
                self.assertTrue(record["locators"])
                self.assertTrue(record["verbatim_probes"])

    def test_no_intervention_is_invented_for_any_record(self) -> None:
        for graph_evidence_id, record in sorted(self.audit.items()):
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(record["statement_interventions"], [])
                self.assertEqual(record["v2_row_interventions"], [])
                self.assertFalse(record["intervention_present_in_graph_record"])
        for claim in self.simulated:
            with self.subTest(claim=claim["claim_id"]):
                self.assertFalse(claim["intervention_field_present"])
                self.assertNotIn("intervention", claim)
        self.assertEqual(load_json(OUT / "audit_scope.json")["interventions_invented"], 0)

    def test_the_role_is_not_inferred_from_the_direction_string_alone(self) -> None:
        """evidence:347 dice `prognostic` e non produce un claim prognostico."""
        record = self.audit["evidence:347"]
        self.assertEqual(record["graph_direction"], "prognostic")
        self.assertEqual(claims_for_verdict(record["verdict"]), ())
        self.assertEqual(
            [c for c in self.simulated if c["graph_evidence_id"] == "evidence:347"], []
        )

    def test_a_diagnostic_claim_does_not_assert_clinical_validation(self) -> None:
        for graph_evidence_id in ("evidence:1846", "evidence:1847"):
            record = self.audit[graph_evidence_id]
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertFalse(record["clinical_validation_asserted"])
                self.assertFalse(record["prevalence_attributable_to_specific_fusion"])

    def test_every_approved_claim_has_the_required_fields(self) -> None:
        for record in self.audit.values():
            if not claims_for_verdict(record["verdict"]):
                continue
            candidate = {
                "source_id": record["source_id"],
                "subject": record.get("diagnostic_subject"),
                "disease_scope": record["disease"],
                "direction_or_interpretation": record.get("diagnostic_interpretation"),
                "source_unit_id": record["profile_unit_id"],
                "locators": record["locators"],
                "polarity": record["assertion_polarity"],
                "provenance": record["audit_id"],
            }
            with self.subTest(graph_evidence_id=record["graph_evidence_id"]):
                self.assertEqual(check_materialisation_preconditions(candidate), ())


# ── gerarchia e tipi ──────────────────────────────────────────────────────────


class TestClaimHierarchy(ArtifactCase):
    def test_diagnostic_is_distinct_from_prognostic(self) -> None:
        diagnostic = load_json(OUT / "diagnostic_claim_contract.json")
        prognostic = load_json(OUT / "prognostic_claim_contract.json")
        self.assertNotEqual(diagnostic["claim_type"], prognostic["claim_type"])
        self.assertNotEqual(
            set(diagnostic["required_fields"]), set(prognostic["required_fields"])
        )
        self.assertIn("diagnostic_interpretation", diagnostic["required_fields"])
        self.assertIn("outcome", prognostic["required_fields"])
        self.assertNotIn("outcome", diagnostic["required_fields"])
        self.assertNotIn("diagnostic_interpretation", prognostic["required_fields"])

    def test_prognostic_is_distinct_from_predictive(self) -> None:
        prognostic = load_json(OUT / "prognostic_claim_contract.json")
        self.assertIn("prognostic_to_predictive", prognostic["forbidden_inferences"])
        hierarchy = load_json(OUT / "evidence_claim_hierarchy.json")
        self.assertFalse(hierarchy["predictive_claim"]["required"])
        self.assertFalse(hierarchy["predictive_claim"]["concrete_case_in_corpus"])
        self.assertNotIn("predictive_claim", ALL_CLAIM_TYPES)

    def test_predictive_is_not_introduced_without_a_concrete_case(self) -> None:
        self.assertFalse(PREDICTIVE_CLAIM_ASSESSMENT["required"])
        self.assertEqual(PREDICTIVE_CLAIM_ASSESSMENT["nearest_case"], "evidence:347")
        self.assertFalse(self.manifest["predictive_claim_required"])

    def test_non_therapeutic_claims_require_no_intervention(self) -> None:
        for name in ("diagnostic_claim_contract.json", "prognostic_claim_contract.json"):
            contract = load_json(OUT / name)
            with self.subTest(contract=name):
                self.assertFalse(contract["requires_intervention"])
                self.assertFalse(contract["intervention_field_present"])
                self.assertNotIn("intervention", contract["required_fields"])

    def test_associations_are_not_evidence_claims(self) -> None:
        hierarchy = load_json(OUT / "evidence_claim_hierarchy.json")
        self.assertFalse(hierarchy["associations_are_evidence_claims"])
        self.assertFalse(hierarchy["graph_evidence_record_is_claim"])
        for kind in ("unsupported_association", "unresolved_association"):
            with self.subTest(kind=kind):
                self.assertIn(kind, NON_CLAIM_OBJECT_KINDS)
                self.assertNotIn(kind, ALL_CLAIM_TYPES)

    def test_the_therapeutic_subtree_still_holds_the_three_original_types(self) -> None:
        hierarchy = load_json(OUT / "evidence_claim_hierarchy.json")
        therapeutic = hierarchy["hierarchy"]["EvidenceClaim"]["children"]["TherapeuticClaim"]
        self.assertTrue(therapeutic["requires_intervention"])
        self.assertEqual(
            sorted(therapeutic["children"]),
            ["AggregateInterventionClaim", "AtomicInterventionClaim", "RegimenClaim"],
        )


# ── query e metriche ──────────────────────────────────────────────────────────


class TestQueryAndMetricScope(ArtifactCase):
    def test_a_diagnostic_query_never_returns_a_therapeutic_claim_as_primary(self) -> None:
        for claim_type in THERAPEUTIC_CLAIM_TYPES:
            with self.subTest(claim_type=claim_type):
                self.assertFalse(primary_eligible("diagnostic_evidence_query", claim_type))
                self.assertEqual(
                    rejection_reason("diagnostic_evidence_query", claim_type),
                    "THERAPEUTIC_CLAIM_NOT_DIAGNOSTIC_EVIDENCE",
                )

    def test_a_prognostic_query_never_returns_a_therapeutic_claim_as_primary(self) -> None:
        for claim_type in THERAPEUTIC_CLAIM_TYPES:
            with self.subTest(claim_type=claim_type):
                self.assertFalse(primary_eligible("prognostic_evidence_query", claim_type))

    def test_a_therapeutic_query_never_returns_a_non_therapeutic_claim(self) -> None:
        for claim_type in NON_THERAPEUTIC_CLAIM_TYPES:
            with self.subTest(claim_type=claim_type):
                self.assertFalse(primary_eligible("therapeutic_evidence_query", claim_type))

    def test_an_untyped_query_keeps_the_types_in_separate_sections(self) -> None:
        contract = load_json(OUT / "non_therapeutic_query_contract.json")
        sectioning = contract["untyped_query_sectioning"]
        self.assertTrue(sectioning["sections_are_separate"])
        self.assertFalse(sectioning["cross_type_ranking"])
        for claim_type in ALL_CLAIM_TYPES:
            with self.subTest(claim_type=claim_type):
                self.assertTrue(primary_eligible("untyped_evidence_query", claim_type))

    def test_an_unknown_query_or_claim_type_raises(self) -> None:
        with self.assertRaises(ContractError):
            primary_eligible("nonexistent_query", "diagnostic_claim")
        with self.assertRaises(ContractError):
            primary_eligible("untyped_evidence_query", "predictive_claim")

    def test_non_therapeutic_claims_are_excluded_from_therapy_level_metrics(self) -> None:
        contract = load_json(OUT / "metric_scope_contract.json")
        therapy = contract["families"]["therapeutic_claim_metrics"]
        for claim_type in NON_THERAPEUTIC_CLAIM_TYPES:
            with self.subTest(claim_type=claim_type):
                self.assertIn(claim_type, therapy["denominator_excludes"])
                self.assertNotIn(claim_type, therapy["denominator_includes"])
        self.assertFalse(contract["cross_family_comparison_allowed"])
        self.assertFalse(contract["metrics_computed_in_this_phase"])

    def test_non_therapeutic_claims_receive_no_therapy_score(self) -> None:
        contract = load_json(OUT / "non_therapeutic_score_eligibility.json")
        self.assertFalse(contract["weights_assigned"])
        for claim_type in NON_THERAPEUTIC_CLAIM_TYPES:
            entry = contract["by_claim_type"][claim_type]
            with self.subTest(claim_type=claim_type):
                self.assertFalse(entry["receives_therapy_score"])
                self.assertFalse(entry["enters_therapy_level_metrics"])
                self.assertFalse(entry["flattened_into_intervention"])
                self.assertFalse(entry["compared_with_regimen_or_class"])


# ── conteggio riconciliato ────────────────────────────────────────────────────


class TestReconciledCount(ArtifactCase):
    def test_the_total_is_derived_from_the_parts(self) -> None:
        inventory = self.inventory
        self.assertEqual(
            inventory["therapeutic_claims"]["total"]
            + inventory["non_therapeutic_claims"]["total"],
            inventory["total_claims_amended"],
        )
        self.assertFalse(inventory["expected_count_forced"])

    def test_the_therapeutic_total_matches_the_untouched_shadow_repository(self) -> None:
        shadow = load_jsonl(SHADOW / "typed_claims.jsonl")
        self.assertEqual(len(shadow), self.inventory["therapeutic_claims"]["total"])
        self.assertTrue(self.inventory["therapeutic_claims"]["unchanged_from_shadow_repository"])

    def test_the_non_therapeutic_total_equals_the_approved_verdicts(self) -> None:
        expected = sum(
            len(claims_for_verdict(record["verdict"])) for record in self.audit.values()
        )
        self.assertEqual(expected, self.inventory["non_therapeutic_claims"]["total"])
        self.assertEqual(expected, len(self.simulated))

    def test_no_artifact_hardcodes_149_as_the_amended_total(self) -> None:
        for name, text in sorted(self.artifacts.items()):
            payload = json.loads(text) if name.endswith(".json") else None
            if payload is None:
                continue
            with self.subTest(artifact=name):
                self.assertNotEqual(payload.get("resulting_claim_count"), 149)
                self.assertNotEqual(payload.get("total_claims_amended"), 149)
        self.assertFalse(self.manifest["expected_count_forced_to_149"])
        self.assertTrue(self.amended["resulting_claim_count_is_derived"])

    def test_a_parent_without_claims_stays_legitimate(self) -> None:
        without = self.inventory["parents_without_claims"]
        self.assertEqual(
            without["graph_evidence_ids"],
            ["evidence:347", "evidence:3811", "evidence:4759"],
        )
        self.assertEqual(without["count"], 3)
        self.assertEqual(
            without["gained_a_claim_in_this_phase"], ["evidence:1846", "evidence:1847"]
        )

    def test_the_amended_specification_separates_the_five_categories(self) -> None:
        categories = self.amended["object_categories"]
        self.assertEqual(
            sorted(categories),
            [
                "non_therapeutic_claims",
                "parents_without_claims",
                "therapeutic_claims",
                "unresolved_associations",
                "unsupported_associations",
            ],
        )


# ── erratum e lineage ─────────────────────────────────────────────────────────


class TestErratumAndLineage(ArtifactCase):
    def test_the_frozen_originals_are_unchanged(self) -> None:
        for relative, expected in sorted(FROZEN_ORIGINALS.items()):
            digest = hashlib.sha256(
                (V3 / relative).read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            with self.subTest(artifact=relative):
                self.assertEqual(digest, expected)

    def test_the_erratum_cites_the_original_hashes(self) -> None:
        self.assertFalse(self.erratum["originals_rewritten"])
        self.assertTrue(self.erratum["originals_preserved"])
        cited = {c["original_sha256"] for c in self.erratum["corrections"]}
        for expected in (
            FROZEN_ORIGINALS["multi_intervention_adjudication/migration_specification.json"],
            FROZEN_ORIGINALS[
                "multi_intervention_adjudication/post_adjudication_schema_simulation.json"
            ],
        ):
            with self.subTest(sha=expected):
                self.assertIn(expected, cited)

    def test_correction_a_replaces_149_with_the_derived_total(self) -> None:
        correction = next(
            c for c in self.erratum["corrections"] if c["correction_id"] == "ERR-A-claim-count"
        )
        self.assertEqual(correction["original_value"], 149)
        self.assertEqual(
            correction["corrected_value"], self.inventory["total_claims_amended"]
        )
        self.assertEqual(correction["correction_basis"], "derived_from_audit")
        self.assertEqual(correction["impact_on_documentary_decisions"], "none")

    def test_correction_b_names_the_right_groups(self) -> None:
        correction = next(
            c
            for c in self.erratum["corrections"]
            if c["correction_id"] == "ERR-B-groups-without-replacement"
        )
        self.assertIn("evidence:275", correction["original_claim"])
        self.assertIn("evidence:3811", correction["corrected_value"])
        self.assertIn("evidence:4759", correction["corrected_value"])
        impact = correction["impact_on_counts"]
        self.assertTrue(impact["evidence_275_has_replacement"])
        self.assertEqual(
            impact["affected_groups"], ["evidence:3811", "evidence:4759"]
        )
        self.assertEqual(correction["impact_on_documentary_decisions"], "none")

    def test_evidence_275_has_an_aggregate_replacement_in_the_data(self) -> None:
        packets = load_jsonl(ADJ / "packet_adjudications.jsonl")
        packet = next(p for p in packets if p["graph_evidence_id"] == "evidence:275")
        self.assertEqual(packet["approved_claim_types"], ["aggregate_intervention_claim"])
        self.assertEqual(packet["approved_claims"], ["CLM-4ffe85304f3ef5533b58"])
        deprecations = load_jsonl(SHADOW / "legacy_statement_deprecation_map.jsonl")
        entry = next(d for d in deprecations if d["graph_evidence_id"] == "evidence:275")
        self.assertEqual(entry["deprecation_state"], "replaced_by_aggregate_claim")
        self.assertEqual(entry["replacement_claim_ids"], ["CLM-4ffe85304f3ef5533b58"])

    def test_evidence_3811_and_4759_have_no_positive_replacement(self) -> None:
        deprecations = load_jsonl(SHADOW / "legacy_statement_deprecation_map.jsonl")
        for graph_evidence_id in ("evidence:3811", "evidence:4759"):
            entry = next(
                d for d in deprecations if d["graph_evidence_id"] == graph_evidence_id
            )
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(entry["deprecation_state"], "deprecated_without_replacement")
                self.assertEqual(entry["replacement_claim_ids"], [])
        self.assertEqual(
            self.inventory["legacy_statements"]["without_positive_replacement"],
            ["evidence:3811", "evidence:4759"],
        )

    def test_the_amended_specification_links_to_the_original(self) -> None:
        self.assertEqual(
            self.amended["supersedes_sha256"],
            FROZEN_ORIGINALS["multi_intervention_adjudication/migration_specification.json"],
        )
        self.assertTrue(self.amended["adjudication_decisions_unchanged"])
        self.assertEqual(self.amended["status"], "amended_not_promoted")

    def test_the_lineage_keeps_both_versions_addressable(self) -> None:
        lineage = load_json(OUT / "artifact_version_lineage.json")
        for entry in lineage["originals"]:
            with self.subTest(artifact=entry["artifact"]):
                self.assertFalse(entry["modified_by_this_phase"])
                self.assertTrue(entry["sha256"])
        self.assertFalse(lineage["shadow_repository"]["modified_by_this_phase"])
        self.assertFalse(lineage["shadow_repository"]["regenerated"])


# ── identita' ─────────────────────────────────────────────────────────────────


class TestClaimIdentity(ArtifactCase):
    def test_ids_are_deterministic(self) -> None:
        again = build()
        self.assertEqual(
            again["claim_id_simulation.jsonl"], self.artifacts["claim_id_simulation.jsonl"]
        )

    def test_there_are_no_collisions(self) -> None:
        ids = [c["claim_id"] for c in self.simulated]
        self.assertEqual(len(ids), len(set(ids)))

    def test_they_do_not_collide_with_therapeutic_claim_ids(self) -> None:
        therapeutic = {c["claim_id"] for c in load_jsonl(SHADOW / "typed_claims.jsonl")}
        self.assertEqual(therapeutic & {c["claim_id"] for c in self.simulated}, set())

    def test_the_identity_carries_no_artificial_intervention_field(self) -> None:
        for claim in self.simulated:
            with self.subTest(claim=claim["claim_id"]):
                self.assertNotIn("intervention", claim["claim_identity_payload"].lower())

    def test_the_identity_is_order_independent_of_the_input_file(self) -> None:
        self.assertEqual(
            build(reverse=True)["claim_id_simulation.jsonl"],
            self.artifacts["claim_id_simulation.jsonl"],
        )

    def test_the_parent_lineage_is_preserved(self) -> None:
        parents = {p["graph_evidence_id"] for p in load_jsonl(SHADOW / "graph_evidence_parents.jsonl")}
        for claim in self.simulated:
            with self.subTest(claim=claim["claim_id"]):
                self.assertEqual(claim["parent_graph_evidence_id"], claim["graph_evidence_id"])
                self.assertIn(claim["graph_evidence_id"], parents)

    def test_a_separator_in_a_field_raises(self) -> None:
        with self.assertRaises(ContractError):
            claim_id(
                graph_evidence_id="evidence:1|fake",
                claim_type="diagnostic_claim",
                canonical_subject="s",
                biomarker="b",
                disease_scope="d",
                direction_or_interpretation="subtype_defining_alteration",
                polarity="supports",
                source_unit_id="PU-1",
            )


# ── artefatti, determinismo, isolamento ───────────────────────────────────────


class TestArtifacts(ArtifactCase):
    def test_all_declared_artifacts_exist(self) -> None:
        expected = {
            "audit_scope.json",
            "non_therapeutic_record_audit.jsonl",
            "diagnostic_claim_contract.json",
            "prognostic_claim_contract.json",
            "evidence_claim_hierarchy.json",
            "non_therapeutic_query_contract.json",
            "non_therapeutic_score_eligibility.json",
            "metric_scope_contract.json",
            "adjudication_erratum.json",
            "migration_specification_amended.json",
            "artifact_version_lineage.json",
            "amended_shadow_simulation.json",
            "claim_id_simulation.jsonl",
            "review_manifest.json",
            "NON_THERAPEUTIC_CLAIM_AUDIT.md",
            "EVIDENCE_CLAIM_HIERARCHY.md",
            "ADJUDICATION_ERRATUM.md",
            "AMENDED_MIGRATION_SPECIFICATION.md",
            "NON_THERAPEUTIC_CLAIM_READINESS.md",
        }
        for name in sorted(expected):
            with self.subTest(artifact=name):
                self.assertTrue((OUT / name).exists())

    def test_two_generations_are_byte_identical(self) -> None:
        self.assertEqual(build(), self.artifacts)

    def test_reversing_the_input_order_changes_nothing(self) -> None:
        self.assertEqual(build(reverse=True), self.artifacts)

    def test_the_files_on_disk_match_the_regenerated_content(self) -> None:
        for name, text in sorted(self.artifacts.items()):
            with self.subTest(artifact=name):
                self.assertEqual((OUT / name).read_text(encoding="utf-8"), text)

    def test_the_manifest_hashes_match_the_files(self) -> None:
        for name, expected in self.manifest["artifact_sha256"].items():
            digest = hashlib.sha256(
                (OUT / name).read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            with self.subTest(artifact=name):
                self.assertEqual(digest, expected)

    def test_no_machine_specific_path_leaks(self) -> None:
        for name, text in sorted(self.artifacts.items()):
            lowered = text.lower()
            with self.subTest(artifact=name):
                for fragment in ("c:\\", "/users/", "/home/", "appdata"):
                    self.assertNotIn(fragment, lowered)

    def test_the_manifest_declares_nothing_was_promoted(self) -> None:
        for flag in (
            "originals_modified",
            "shadow_repository_modified",
            "shadow_repository_promoted",
            "operational_corpus_modified",
            "operational_adapter_modified",
            "operational_retriever_modified",
            "operational_scoring_modified",
            "metrics_computed",
            "gold_used",
            "network_used",
            "neo4j_used",
            "llm_used",
        ):
            with self.subTest(flag=flag):
                self.assertFalse(self.manifest[flag])


class TestOperationalAndShadowUnchanged(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scope = PhaseScope(
            REPO_ROOT.parent,
            START_SHA,
            PHASE_END_SHA,
            (
                "benchmarks/mtb_evidence/v3/non_therapeutic_claim_contract_and_erratum/",
                "benchmarks/mtb_evidence/evaluation/non_therapeutic_claim_contract.py",
                "benchmarks/mtb_evidence/evaluation/scripts/build_non_therapeutic_claim_contract.py",
                "benchmarks/mtb_evidence/evaluation/data/non_therapeutic_audit_v1.jsonl",
                "backend/tests/test_non_therapeutic_claim_contract.py",
            ),
        )
        cls.changed = cls.scope.changed_paths()

    def test_no_operational_artifact_was_modified(self) -> None:
        for path in FROZEN_OPERATIONAL_PATHS:
            with self.subTest(path=path):
                self.assertNotIn(path, self.changed)

    def test_the_shadow_repository_was_not_regenerated(self) -> None:
        for path in sorted(self.changed):
            with self.subTest(path=path):
                self.assertNotIn("typed_claim_shadow_migration/", path)

    def test_no_frozen_adjudication_artifact_was_modified(self) -> None:
        for path in sorted(self.changed):
            with self.subTest(path=path):
                for prefix in (
                    "multi_intervention_adjudication/",
                    "multi_intervention_source_review/",
                    "multi_intervention_second_review/",
                    "multi_intervention_review_comparison/",
                    "claim_type_retrieval_contract/",
                    "qualification_corpus_v2/",
                ):
                    self.assertNotIn(prefix, path)

    def test_the_branch_only_wrote_inside_its_own_perimeter(self) -> None:
        self.assertEqual(
            self.scope.violations(self.changed),
            [],
            "modifica fuori dal perimetro del contratto non terapeutico",
        )


class TestIsolation(unittest.TestCase):
    def sources(self) -> list[Path]:
        return [
            REPO_ROOT / "benchmarks/mtb_evidence/evaluation/non_therapeutic_claim_contract.py",
            REPO_ROOT
            / "benchmarks/mtb_evidence/evaluation/scripts/build_non_therapeutic_claim_contract.py",
        ]

    def test_the_gold_is_never_read(self) -> None:
        for path in self.sources():
            blob = path.read_text(encoding="utf-8").lower()
            with self.subTest(module=path.name):
                for fragment in (
                    "clinical_gold",
                    "snapshot_gold",
                    "statement_qualification_gold",
                    "gold_pilot",
                    "evaluation_gold_snapshot",
                    "mtb_evidence_gold",
                    "recall@",
                    "precision@",
                ):
                    self.assertNotIn(fragment, blob)

    def test_no_network_neo4j_or_llm_import(self) -> None:
        forbidden = (
            "requests",
            "httpx",
            "aiohttp",
            "neo4j",
            "openai",
            "anthropic",
            "urllib",
            "socket",
            "subprocess",
        )
        for path in self.sources():
            imports = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
            with self.subTest(module=path.name):
                for line in imports:
                    for fragment in forbidden:
                        self.assertNotIn(fragment, line)

    def test_no_operational_module_imports_this_contract(self) -> None:
        """Nessun modulo *operativo* importa il contratto dei benchmark.

        Il controllo guarda gli import del modulo del contratto, non la
        sottostringa `non_therapeutic`, e salta il package shadow. La versione
        precedente faceva entrambe le cose in modo troppo largo: il package
        shadow non e' operativo — nessun modulo operativo lo importa, ed e' un
        test a parte a dirlo — e da quando implementa i claim non terapeutici
        contiene legittimamente quella parola.
        """
        evidence = REPO_ROOT / "backend/pipeline/evidence"
        for path in sorted(evidence.rglob("*.py")):
            relative = path.relative_to(evidence)
            if relative.parts and relative.parts[0] == "shadow":
                continue
            imports = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
            with self.subTest(module=str(relative)):
                for line in imports:
                    self.assertNotIn("non_therapeutic_claim_contract", line)

    def test_no_operational_module_imports_the_shadow_package(self) -> None:
        """Il package shadow resta invisibile alla pipeline operativa."""
        evidence = REPO_ROOT / "backend/pipeline/evidence"
        for path in sorted(evidence.glob("*.py")):
            imports = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
            with self.subTest(module=path.name):
                for line in imports:
                    self.assertNotIn("shadow", line)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

"""Protegge la provenienza e la misura della chiusura terminologica.

I test difendono tre cose che sono facili da perdere. Che una decisione nasca da
una fonte con un locator e non dalla somiglianza di due stringhe. Che un mapping
verificato non venga scambiato per un permesso di atomizzare un risultato che la
fonte riporta unito. Che la fase non abbia toccato nulla di cio' che dichiara di
non toccare.
"""

from __future__ import annotations

import hashlib
import json
import unittest

from benchmarks.mtb_evidence.evaluation import external_inputs as EXTERNAL
from pathlib import Path

from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation.scripts.build_terminology_mapping_closure import (
    AGGREGATE_BIOMARKERS,
    AGGREGATE_SOURCE_UNIT,
    CURRENT_AGGREGATE_IDS,
    CURRENT_AGGREGATE_INTERVENTION,
    DEFAULT_OUTPUT,
    EXPECTED_GROUPS,
    EXPECTED_PENDING_ASSOCIATIONS,
    EXPECTED_QUEUE_IDS,
    PAIR_AUY922,
    PAIR_BGJ398,
    QUEUE_FILE,
    build,
)
from benchmarks.mtb_evidence.evaluation.terminology_mapping_closure import (
    SCOPE_GLOBAL,
    SCOPE_NONE,
    SCOPE_SOURCE_LOCAL,
    VERIFIED_DECISIONS,
)
from benchmarks.mtb_evidence.evaluation.terminology_mapping_closure_simulation import (
    aggregate_claim_id,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
SHADOW_V10 = V3 / "typed_claim_shadow_migration"
SHADOW_V11 = V3 / "non_therapeutic_shadow_update"
SHADOW_V12 = V3 / "diagnostic_disease_scope_narrowing_shadow"
OUT = DEFAULT_OUTPUT

GENERATOR = (
    REPO_ROOT
    / "benchmarks/mtb_evidence/evaluation/scripts/build_terminology_mapping_closure.py"
)
PHASE_MODULES = (
    GENERATOR,
    REPO_ROOT / "benchmarks/mtb_evidence/evaluation/terminology_mapping_closure.py",
    REPO_ROOT
    / "benchmarks/mtb_evidence/evaluation/terminology_mapping_closure_simulation.py",
    REPO_ROOT
    / "benchmarks/mtb_evidence/evaluation/terminology_mapping_closure_reports.py",
)

START_SHA = "154528358ee05f95fc523c41058d1c7e7839bd94"
# La fase termina sull'ultimo commit di contenuto. L'estremo resta fisso anche
# quando fasi successive aggiungono nuovi commit: il perimetro di una fase e'
# una proprieta' storica e chiusa.
PHASE_END_SHA = "18961312dba1b3f083a2a313c1f1b4e549dc0d68"

# PhaseScope restituisce percorsi relativi al pacchetto: il prefisso del repo
# viene gia' rimosso una volta dal helper condiviso.
ALLOWED_WRITE_PREFIXES = (
    "benchmarks/mtb_evidence/v3/terminology_mapping_closure/",
    "benchmarks/mtb_evidence/evaluation/terminology_mapping_closure.py",
    "benchmarks/mtb_evidence/evaluation/terminology_mapping_closure_simulation.py",
    "benchmarks/mtb_evidence/evaluation/terminology_mapping_closure_reports.py",
    "benchmarks/mtb_evidence/evaluation/scripts/build_terminology_mapping_closure.py",
    "backend/tests/test_terminology_mapping_closure.py",
)

FROZEN_OPERATIONAL_PATHS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualified_evidence_views.jsonl",
)

ICCA_DIAGNOSTIC_CLAIMS = {
    "evidence:1846": "CLM-8941c177da91f66ff93a",
    "evidence:1847": "CLM-a7e1c40b794d2c4d4ca8",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl_text(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def sha256_text(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


class ClosureCase(unittest.TestCase):
    """Genera una volta sola e condivide il risultato con le sottoclassi."""

    @classmethod
    def setUpClass(cls) -> None:
        # La cache degli abstract e' un ingresso esterno privato: testo protetto
        # da copyright, escluso dal versionamento per disegno e non per
        # dimenticanza. Senza di essa `build()` non ha un soggetto, e saltare e'
        # l'esito corretto — fallire direbbe che il codice e' rotto.
        EXTERNAL.require_or_skip(EXTERNAL.SOURCE_ABSTRACT_CACHE)
        cls.artifacts = build()
        cls.manifest = json.loads(cls.artifacts["terminology_review_manifest.json"])
        cls.decisions = load_jsonl_text(cls.artifacts["mapping_decisions.jsonl"])
        cls.by_pair = {row["pair_id"]: row for row in cls.decisions}
        cls.evidence = load_jsonl_text(
            cls.artifacts["authoritative_mapping_evidence.jsonl"]
        )
        cls.reviews = load_jsonl_text(
            cls.artifacts["group_terminology_reviews.jsonl"]
        )
        cls.simulation = load_jsonl_text(
            cls.artifacts["claim_id_impact_simulation.jsonl"]
        )
        cls.shadow = json.loads(
            cls.artifacts["shadow_repository_update_simulation.json"]
        )
        cls.contract = json.loads(cls.artifacts["canonicalization_contract.json"])


class TestPerimeter(ClosureCase):
    def test_the_recorded_start_sha_is_the_real_branch_head(self) -> None:
        self.assertEqual(self.manifest["scope"]["start_sha"], START_SHA)
        self.assertEqual(len(START_SHA), 40)

    def test_the_frozen_queue_is_read_unchanged(self) -> None:
        self.assertEqual(
            self.manifest["scope"]["queue_sha256"], sha256_text(QUEUE_FILE)
        )
        snapshot = load_jsonl_text(self.artifacts["terminology_queue_snapshot.jsonl"])
        self.assertEqual(
            sorted(row["queue_id"] for row in snapshot), sorted(EXPECTED_QUEUE_IDS)
        )

    def test_exactly_the_queue_groups_are_reviewed(self) -> None:
        reviewed = sorted(row["graph_evidence_id"] for row in self.reviews)
        self.assertEqual(reviewed, sorted(EXPECTED_GROUPS))
        self.assertTrue(self.manifest["scope"]["perimeter_matches_expectation"])

    def test_the_pending_association_count_matches_the_expected_perimeter(self) -> None:
        self.assertEqual(
            self.manifest["scope"]["pending_association_count"],
            EXPECTED_PENDING_ASSOCIATIONS,
        )
        pending = [
            row
            for row in self.reviews
            if row["mapping_candidate"] and row["graph_evidence_id"] != "evidence:12156"
        ]
        self.assertEqual(len(pending), EXPECTED_PENDING_ASSOCIATIONS)

    def test_the_group_outside_the_queue_gets_no_invented_pair(self) -> None:
        """Il quarto gruppo e' aperto ma non contiene una coppia terminologica."""
        outside = [
            row for row in self.reviews if row["graph_evidence_id"] == "evidence:12156"
        ]
        self.assertEqual(len(outside), 1)
        self.assertEqual(outside[0]["mapping_candidate"], "")
        self.assertEqual(outside[0]["terminology_decision"], "")
        self.assertTrue(outside[0]["unresolved_reason"])

    def test_phase_writes_only_inside_the_terminology_perimeter(self) -> None:
        if not PHASE_END_SHA:
            raise unittest.SkipTest("estremo di fase non ancora fissato")
        self.assertNotEqual(PHASE_END_SHA, "HEAD")
        scope = PhaseScope(
            REPO_ROOT.parent, START_SHA, PHASE_END_SHA, ALLOWED_WRITE_PREFIXES
        )
        changed = scope.changed_paths()
        self.assertEqual(scope.violations(changed), [])
        for path in FROZEN_OPERATIONAL_PATHS:
            with self.subTest(path=path):
                self.assertNotIn(path, changed)


class TestMappingDiscipline(ClosureCase):
    def test_both_queue_pairs_are_decided(self) -> None:
        self.assertEqual(len(self.decisions), len(EXPECTED_QUEUE_IDS))
        for pair in (PAIR_BGJ398, PAIR_AUY922):
            with self.subTest(pair=pair):
                self.assertIn(pair, self.by_pair)
                self.assertTrue(self.by_pair[pair]["decision"])

    def test_bgj398_is_a_verified_global_development_code(self) -> None:
        row = self.by_pair[PAIR_BGJ398]
        self.assertIn(row["decision"], VERIFIED_DECISIONS)
        self.assertEqual(row["mapping_scope"], SCOPE_GLOBAL)
        self.assertEqual(row["canonical_label"], "infigratinib")
        self.assertEqual(row["source_literal_term"], "BGJ398")
        self.assertTrue(row["circularity_control_passed"])

    def test_auy922_stays_unresolved_without_a_canonical_label(self) -> None:
        row = self.by_pair[PAIR_AUY922]
        self.assertNotIn(row["decision"], VERIFIED_DECISIONS)
        self.assertEqual(row["mapping_scope"], SCOPE_NONE)
        self.assertEqual(row["canonical_label"], "")
        self.assertEqual(row["source_literal_term"], "AUY922")
        self.assertFalse(row["circularity_control_passed"])
        self.assertTrue(row["unresolved_reason"])

    def test_every_decision_rests_on_a_source_with_a_locator(self) -> None:
        """Nessuna decisione puo' nascere dalla sola somiglianza di stringa."""
        for row in self.decisions:
            with self.subTest(pair=row["pair_id"]):
                self.assertFalse(row["decided_by_string_similarity"])
                supporting = [
                    item
                    for item in self.evidence
                    if item["pair_id"] == row["pair_id"]
                ]
                self.assertTrue(supporting)
                for item in supporting:
                    self.assertTrue(item["locator"].strip())
                    self.assertTrue(item["source_id"].strip())
                    self.assertTrue(item["stable_identifier"].strip())

    def test_a_verified_mapping_needs_evidence_not_derived_from_the_graph(self) -> None:
        for row in self.decisions:
            with self.subTest(pair=row["pair_id"]):
                independent = [
                    item
                    for item in self.evidence
                    if item["pair_id"] == row["pair_id"]
                    and item["supports_identity"]
                    and not item["graph_derived"]
                ]
                if row["is_verified"]:
                    self.assertTrue(independent)
                    self.assertTrue(row["non_graph_derived_evidence_ids"])
                else:
                    self.assertFalse(independent)

    def test_global_and_source_local_scopes_stay_distinct(self) -> None:
        scopes = {row["mapping_scope"] for row in self.decisions}
        self.assertNotIn(SCOPE_SOURCE_LOCAL, scopes)
        for row in self.decisions:
            with self.subTest(pair=row["pair_id"]):
                self.assertEqual(
                    row["is_global"], row["mapping_scope"] == SCOPE_GLOBAL
                )
                self.assertEqual(row["is_verified"], row["mapping_scope"] != SCOPE_NONE)

    def test_the_development_code_is_not_collapsed_into_the_salt(self) -> None:
        entry = next(
            item
            for item in self.contract["interventions"]
            if item["provenance"]["pair_id"] == PAIR_BGJ398
        )
        self.assertIn("BGJ398", entry["development_codes"])
        self.assertTrue(entry["formulation_or_salt_relations"])
        joined = " ".join(entry["formulation_or_salt_relations"]).lower()
        self.assertIn("fosfato", joined)
        self.assertNotIn("infigratinib fosfato", [s.lower() for s in entry["verified_aliases"]])

    def test_a_pending_alias_is_never_eligible_for_exact_match(self) -> None:
        for entry in self.contract["interventions"]:
            with self.subTest(entry=entry["provenance"]["pair_id"]):
                self.assertFalse(entry["eligible_for_exact_match"])
                self.assertFalse(entry["hard_filterable"])
                self.assertFalse(entry["final_evaluable"])
                if entry["pending_aliases"]:
                    self.assertEqual(entry["verified_aliases"], [])

    def test_a_non_verified_mapping_is_never_canonicalized(self) -> None:
        for entry in self.contract["interventions"]:
            with self.subTest(entry=entry["provenance"]["pair_id"]):
                if entry["mapping_status"] != "verified_pending_second_review":
                    self.assertEqual(entry["canonical_label"], "")
                    self.assertEqual(entry["canonical_intervention_id"], "")
                    self.assertEqual(entry["mapping_scope"], SCOPE_NONE)

    def test_the_source_literal_survives_every_decision(self) -> None:
        rows = load_jsonl_text(self.artifacts["source_literal_preservation.jsonl"])
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(group=row["graph_evidence_id"]):
                self.assertTrue(row["source_literal_preserved"])
                self.assertFalse(row["canonical_replaces_source_literal"])
                self.assertFalse(row["source_rewritten"])
                self.assertTrue(row["locator_preserved"])
                self.assertTrue(row["source_literal_terms"])


class TestClaimRestraint(ClosureCase):
    def test_the_formula_reproduces_the_committed_identifiers(self) -> None:
        for graph_evidence_id, current_id in CURRENT_AGGREGATE_IDS.items():
            with self.subTest(group=graph_evidence_id):
                self.assertEqual(
                    aggregate_claim_id(
                        graph_evidence_id=graph_evidence_id,
                        intervention=CURRENT_AGGREGATE_INTERVENTION,
                        biomarker=AGGREGATE_BIOMARKERS[graph_evidence_id],
                        source_unit_id=AGGREGATE_SOURCE_UNIT,
                    ),
                    current_id,
                )

    def test_a_verified_mapping_does_not_atomize_the_aggregate(self) -> None:
        changed = [row for row in self.simulation if row["claim_id_changes"]]
        self.assertEqual(len(changed), 2)
        for row in changed:
            with self.subTest(claim=row["current_claim_id"]):
                self.assertEqual(row["claim_type_before"], row["claim_type_after"])
                self.assertEqual(row["claim_type_after"], "aggregate_intervention_claim")
                self.assertFalse(row["permits_member_specific_claims_after"])
                self.assertFalse(row["atomized"])
        self.assertEqual(self.shadow["aggregates_atomized"], 0)

    def test_a_verified_mapping_does_not_separate_the_regimen(self) -> None:
        self.assertEqual(self.shadow["regimens_separated"], 0)
        self.assertIn("CLM-5ce49705979f72f174e9", self.shadow["claims_unchanged"])
        for row in self.simulation:
            with self.subTest(claim=row["current_claim_id"]):
                self.assertFalse(row["regimen_separated"])

    def test_the_mapping_creates_no_documentary_support(self) -> None:
        self.assertFalse(self.shadow["documentary_support_created"])
        for row in self.simulation:
            with self.subTest(claim=row["current_claim_id"]):
                self.assertFalse(row["documentary_support_created"])

    def test_the_claim_id_impact_is_deterministic(self) -> None:
        self.assertEqual(
            load_jsonl_text(build()["claim_id_impact_simulation.jsonl"]),
            self.simulation,
        )

    def test_there_are_no_identifier_collisions(self) -> None:
        self.assertEqual(self.shadow["collisions"], [])
        self.assertEqual(self.manifest["collisions"], [])
        new_ids = [row["potential_new_claim_id"] for row in self.simulation]
        self.assertEqual(len(new_ids), len(set(new_ids)))

    def test_every_changed_identifier_carries_a_complete_lineage(self) -> None:
        for row in self.simulation:
            with self.subTest(claim=row["current_claim_id"]):
                if not row["claim_id_changes"]:
                    self.assertEqual(row["lineage"], {})
                    continue
                lineage = row["lineage"]
                self.assertEqual(lineage["old_claim_id"], row["current_claim_id"])
                self.assertEqual(
                    lineage["new_claim_id"], row["potential_new_claim_id"]
                )
                self.assertEqual(lineage["terminology_decision_id"], PAIR_BGJ398)
                self.assertTrue(row["retirement_required"])
                self.assertTrue(row["replacement_required"])

    def test_nothing_is_applied_to_the_shadow_repository(self) -> None:
        self.assertFalse(self.shadow["applied"])
        self.assertFalse(self.shadow["shadow_repository_1_2_modified"])
        self.assertEqual(self.shadow["counts_before"], self.shadow["counts_after"])
        self.assertFalse(self.shadow["therapeutic_proposition_count_changed"])
        for row in self.simulation:
            with self.subTest(claim=row["current_claim_id"]):
                self.assertFalse(row["applied"])
        for row in load_jsonl_text(self.artifacts["qualification_link_impact.jsonl"]):
            with self.subTest(action=row["action"]):
                self.assertFalse(row["executed"])
                self.assertTrue(row["plan_only"])
                self.assertFalse(row["clinical_qualifiers_invented"])

    def test_the_unresolved_association_state_does_not_move(self) -> None:
        for row in load_jsonl_text(self.artifacts["unresolved_terminology.jsonl"]):
            with self.subTest(group=row["graph_evidence_id"]):
                self.assertEqual(
                    row["association_state_before"], row["association_state_after"]
                )
                self.assertFalse(row["state_changed"])
                self.assertFalse(row["positive_score_allowed"])


class TestUpstreamUnchanged(ClosureCase):
    def test_shadow_repositories_are_byte_identical(self) -> None:
        recorded = self.manifest["integrity"]["shadow_repository_manifest_sha256"]
        for version, path in (
            ("1.0", SHADOW_V10 / "shadow_repository_manifest.json"),
            ("1.1", SHADOW_V11 / "shadow_update_manifest.json"),
            ("1.2", SHADOW_V12 / "repository_v1_2_manifest.json"),
        ):
            with self.subTest(version=version):
                self.assertEqual(sha256_text(path), recorded[version])
        self.assertFalse(self.manifest["integrity"]["shadow_repositories_modified"])

    def test_the_1_2_claim_streams_are_untouched(self) -> None:
        manifest = load_json(SHADOW_V12 / "repository_v1_2_manifest.json")
        for name, digest in manifest["artifact_sha256"].items():
            with self.subTest(artifact=name):
                self.assertEqual(sha256_text(SHADOW_V12 / name), digest)

    def test_operational_artifacts_keep_their_hashes(self) -> None:
        integrity = self.manifest["integrity"]
        self.assertTrue(integrity["operational_hash_parity"])
        self.assertEqual(
            integrity["operational_artifact_sha256_before"],
            integrity["operational_artifact_sha256_after"],
        )
        for path, expected in integrity["operational_artifact_sha256_before"].items():
            with self.subTest(path=path):
                self.assertEqual(sha256_text(REPO_ROOT / path), expected)

    def test_frozen_scientific_artifacts_keep_their_hashes(self) -> None:
        for path, expected in self.manifest["integrity"][
            "frozen_scientific_artifact_sha256"
        ].items():
            with self.subTest(path=path):
                self.assertEqual(sha256_text(REPO_ROOT / path), expected)

    def test_evidence_347_is_untouched(self) -> None:
        """evidence:347 e' un parent senza claim: resta tale e fuori perimetro."""
        audit = load_json(SHADOW_V12 / "evidence_347_audit_v1_2.json")
        self.assertEqual(audit["graph_evidence_id"], "evidence:347")
        self.assertEqual(audit["claims_created"], 0)
        self.assertTrue(audit["unchanged_by_repository_v1_2"])
        self.assertFalse(audit["operational_statement_modified"])
        orphans = load_jsonl_text(
            (SHADOW_V12 / "parent_without_claim_v1_2.jsonl").read_text(encoding="utf-8")
        )
        self.assertIn(
            "evidence:347", {row["graph_evidence_id"] for row in orphans}
        )
        produced = "".join(self.artifacts.values())
        self.assertNotIn("evidence:347", produced)

    def test_the_two_diagnostic_icca_claims_are_untouched(self) -> None:
        claims = load_jsonl_text(
            (SHADOW_V12 / "diagnostic_claims_v1_2.jsonl").read_text(encoding="utf-8")
        )
        by_group = {row["graph_evidence_id"]: row for row in claims}
        for group, claim_id_value in ICCA_DIAGNOSTIC_CLAIMS.items():
            with self.subTest(group=group):
                self.assertEqual(by_group[group]["claim_id"], claim_id_value)
                self.assertEqual(
                    by_group[group]["disease_scope"], "Intrahepatic Cholangiocarcinoma"
                )
        produced = "".join(self.artifacts.values())
        for claim_id_value in ICCA_DIAGNOSTIC_CLAIMS.values():
            with self.subTest(claim=claim_id_value):
                self.assertNotIn(claim_id_value, produced)


class TestIsolation(ClosureCase):
    def test_the_evaluation_reference_is_never_read(self) -> None:
        forbidden = (
            "clinical_gold",
            "snapshot_gold",
            "gold_pilot",
            "mtb_evidence_gold",
            "statement_qualification_gold",
            "evaluation_gold_snapshot",
            "recall@",
            "precision@",
        )
        for path in PHASE_MODULES:
            source = path.read_text(encoding="utf-8").lower()
            for fragment in forbidden:
                with self.subTest(module=path.name, fragment=fragment):
                    self.assertNotIn(fragment, source)
        self.assertFalse(self.manifest["scope"]["gold_used"])
        self.assertFalse(self.manifest["scope"]["retrieval_metrics_used"])
        self.assertFalse(self.manifest["integrity"]["evaluation_reference_used"])

    def test_no_network_or_model_imports(self) -> None:
        for path in PHASE_MODULES:
            imports = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
            for forbidden in (
                "requests",
                "httpx",
                "aiohttp",
                "neo4j",
                "openai",
                "anthropic",
                "urllib",
                "socket",
            ):
                with self.subTest(module=path.name, forbidden=forbidden):
                    self.assertFalse(any(forbidden in line for line in imports))

    def test_the_disease_hierarchy_is_not_activated(self) -> None:
        self.assertFalse(self.manifest["scope"]["disease_hierarchy_activated"])


class TestSecondReviewPackets(ClosureCase):
    def test_a_packet_exists_for_every_pair(self) -> None:
        packets = [
            name for name in self.artifacts if name.startswith("second_review_packets/")
        ]
        self.assertEqual(len(packets), len(EXPECTED_QUEUE_IDS))

    def test_packets_carry_no_first_review_conclusion(self) -> None:
        leak_terms = (
            "approve_for_shadow_update",
            "require_external_review",
            "keep_pending",
            "reject_mapping",
            "rationale",
            "confidence",
            "circolar",
            "circularity",
            "recommendation_included\": true",
            "clinical_gold",
            "recall@",
            "precision@",
        )
        for name, text in sorted(self.artifacts.items()):
            if not name.startswith("second_review_packets/"):
                continue
            payload = json.loads(text)
            with self.subTest(packet=name):
                self.assertTrue(payload["blind"])
                self.assertFalse(payload["first_reviewer_decision_included"])
                self.assertFalse(payload["recommendation_included"])
                self.assertFalse(payload["evaluation_reference_included"])
                self.assertFalse(payload["metrics_included"])
                self.assertTrue(payload["material_provided"])
                lowered = text.lower()
                for term in leak_terms:
                    self.assertNotIn(term, lowered)

    def test_packets_offer_the_full_decision_space(self) -> None:
        """Un packet che offrisse meno opzioni orienterebbe la risposta."""
        spaces = set()
        for name, text in sorted(self.artifacts.items()):
            if name.startswith("second_review_packets/"):
                spaces.add(tuple(json.loads(text)["allowed_decisions"]))
        self.assertEqual(len(spaces), 1)
        self.assertEqual(len(next(iter(spaces))), 9)

    def test_packets_are_byte_identical_on_regeneration(self) -> None:
        regenerated = build()
        for name in sorted(self.artifacts):
            if name.startswith("second_review_packets/"):
                with self.subTest(packet=name):
                    self.assertEqual(regenerated[name], self.artifacts[name])


class TestDeterminism(ClosureCase):
    def test_two_generations_and_reversed_inputs_are_byte_identical(self) -> None:
        self.assertEqual(build(), self.artifacts)
        self.assertEqual(build(reverse=True), self.artifacts)

    def test_committed_files_match_a_fresh_generation(self) -> None:
        for name, text in sorted(self.artifacts.items()):
            with self.subTest(artifact=name):
                self.assertEqual((OUT / name).read_text(encoding="utf-8"), text)

    def test_manifest_hashes_match_and_no_machine_path_leaks(self) -> None:
        for name, expected in self.manifest["artifact_sha256"].items():
            with self.subTest(artifact=name):
                text = self.artifacts[name]
                self.assertEqual(
                    hashlib.sha256(text.encode("utf-8")).hexdigest(), expected
                )
        produced = "".join(self.artifacts.values()).lower()
        for fragment in ("c:\\", "/users/", "/home/", "appdata", "ispezionedataset"):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, produced)

    def test_readiness_keeps_promotion_closed(self) -> None:
        flags = self.manifest["readiness"]
        self.assertTrue(flags["terminology_queue_complete"])
        self.assertTrue(flags["all_mapping_pairs_decided"])
        self.assertTrue(flags["shadow_repository_terminology_update_ready"])
        self.assertTrue(flags["disease_hierarchy_policy_ready"])
        self.assertEqual(flags["verified_global_mappings"], 1)
        self.assertEqual(flags["verified_source_local_mappings"], 0)
        self.assertEqual(flags["unresolved_mappings"], 1)
        self.assertEqual(flags["rejected_mappings"], 0)
        self.assertEqual(flags["claim_id_changes_required"], 2)
        for closed in (
            "corpus_promotion_ready",
            "operational_retriever_migration_ready",
            "full_exploratory_rerun_ready",
        ):
            with self.subTest(flag=closed):
                self.assertFalse(flags[closed])

    def test_the_review_is_declared_non_independent(self) -> None:
        scope = self.manifest["scope"]
        self.assertEqual(scope["reviewer_role"], "author_terminology_reviewer")
        self.assertEqual(scope["review_independence"], "non_independent")
        self.assertEqual(scope["review_status"], "first_review_complete")
        self.assertEqual(scope["propagation_policy"], "prototype_only")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

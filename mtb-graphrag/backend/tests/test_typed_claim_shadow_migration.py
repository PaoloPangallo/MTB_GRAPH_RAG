"""Protegge gli invarianti della migrazione shadow e dei gate strutturali.

Tutto offline: nessuna rete, nessun Neo4j, nessun LLM, e il gold non viene mai
letto. Il perimetro della fase e' misurato sull'intervallo chiuso, tramite
l'helper condiviso introdotto all'inizio della fase.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from backend.pipeline.evidence.shadow import shadow_output as OUT
from backend.pipeline.evidence.shadow import shadow_scoring as SCORE
from backend.pipeline.evidence.shadow import structural_gates as GATE
from backend.pipeline.evidence.shadow.claims import (
    AggregateInterventionClaim,
    ClaimModelError,
    RegimenClaim,
)
from backend.pipeline.evidence.shadow.identity import (
    IdentityError,
    canonical_regimen,
    claim_id,
    parent_id,
)
from backend.pipeline.evidence.shadow.migration import migrate
from backend.pipeline.evidence.shadow.parent import (
    GraphEvidenceRecord,
    ParentSemanticsError,
)
from backend.pipeline.evidence.shadow.schema import (
    MIGRATION_ORIGIN_ADJUDICATED,
    MIGRATION_ORIGIN_LEGACY,
    MIGRATION_STATUS,
    MODEL_SCHEMA_VERSION,
    SHADOW_REPOSITORY_VERSION,
)
from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation.scripts.build_typed_claim_shadow_migration import (
    build,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
SHADOW = V3 / "typed_claim_shadow_migration"
ADJ = V3 / "multi_intervention_adjudication"
CORPUS = V3 / "qualification_corpus_v2"

START_SHA = "f7749eaa674042bfd232c4b06f1b019c645e6c99"
# La fase della migrazione shadow si chiude qui. Era rimasta con `HEAD` come
# estremo finale, che non e' un estremo fisso: cresce a ogni commit successivo, e
# il controllo tornava a essere aperto proprio come quello che la fase 0 aveva
# corretto. Pinnato alla chiusura della fase.
PHASE_END_SHA = "b9773757a79fbdea639525aff2f26bdbf15bb2d1"

FROZEN_OPERATIONAL_PATHS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualification_links.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualified_evidence_views.jsonl",
    "benchmarks/mtb_evidence/v3/v2_v3a_exploratory_pilot/frozen_v2_results.jsonl",
)

MANDATORY_CASES = (
    "evidence:275",
    "evidence:4759",
    "evidence:3811",
    "evidence:11240",
    "evidence:12131",
)


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_migration():
    adapter_review = V3 / "multi_intervention_adapter_review"
    return migrate(
        v2_rows=load_jsonl(adapter_review / "intervention_lineage.jsonl"),
        statements=load_jsonl(CORPUS / "evidence_statements.jsonl"),
        approved_claims=load_jsonl(ADJ / "approved_claim_simulation.jsonl"),
        unsupported_records=load_jsonl(ADJ / "unsupported_associations.jsonl"),
        unresolved_records=load_jsonl(ADJ / "unresolved_associations.jsonl"),
        adjudicated_graph_evidence_ids=[
            p["graph_evidence_id"] for p in load_jsonl(ADJ / "packet_adjudications.jsonl")
        ],
    )


class MigrationCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_migration()
        cls.parents = {p.graph_evidence_id: p for p in cls.result.parents}
        cls.claims_by_ge: dict[str, list] = {}
        for claim in cls.result.claims:
            cls.claims_by_ge.setdefault(claim.graph_evidence_id, []).append(claim)


# ── modello ───────────────────────────────────────────────────────────────────


class TestModel(MigrationCase):
    def test_every_graph_evidence_id_becomes_exactly_one_parent(self) -> None:
        self.assertEqual(len(self.result.parents), 147)
        self.assertEqual(len({p.graph_evidence_id for p in self.result.parents}), 147)

    def test_a_parent_is_never_a_claim(self) -> None:
        for parent in self.result.parents:
            with self.subTest(parent=parent.graph_evidence_id):
                self.assertFalse(parent.is_claim)
                self.assertFalse(parent.has_primary_therapy)
                self.assertFalse(parent.receives_therapy_score)
                self.assertFalse(parent.enters_claim_level_ranking)
                self.assertFalse(parent.counted_in_claim_level_metrics)

    def test_forbidden_uses_of_the_parent_raise(self) -> None:
        parent = self.parents["evidence:275"]
        for use in ("claim_level_candidate_ranking", "therapy_score_assignment"):
            with self.subTest(use=use), self.assertRaises(ParentSemanticsError):
                parent.check_use(use)
        parent.check_use("audit_trail")

    def test_every_v2_intervention_survives_in_its_parent(self) -> None:
        """I 15 interventi che l'adapter operativo perde sono tutti nel parent."""
        lost = load_jsonl(
            V3 / "multi_intervention_adapter_review/lost_interventions.jsonl"
        )
        self.assertEqual(len(lost), 15)
        for record in lost:
            parent = self.parents[record["graph_evidence_id"]]
            preserved = {i.lower() for i in parent.original_intervention_associations}
            with self.subTest(graph_evidence_id=record["graph_evidence_id"]):
                self.assertIn(record["lost_intervention"].lower(), preserved)

    def test_the_parent_never_privileges_one_intervention(self) -> None:
        parent = self.parents["evidence:229"]
        self.assertEqual(
            sorted(parent.original_intervention_associations), ["erlotinib", "gefitinib"]
        )

    def test_the_derived_claim_count_is_explained(self) -> None:
        """146, non i 149 proiettati: la differenza sono i tre record non terapeutici.

        La proiezione dell'adjudication (147 - 13 + 15) assumeva che ognuno dei
        134 record non adjudicati portasse un claim. Tre non ne portano: non
        hanno intervento e la loro direzione e' prognostica o diagnostica, quindi
        nessuno dei tre tipi di claim — tutti tipi di intervento — puo' ospitarli.
        """
        self.assertEqual(len(self.result.claims), 146)
        self.assertEqual(len(self.result.blockers), 3)
        self.assertEqual(
            {b.graph_evidence_id for b in self.result.blockers},
            {"evidence:347", "evidence:1846", "evidence:1847"},
        )
        projected = 147 - 13 + 15
        self.assertEqual(projected - len(self.result.claims), len(self.result.blockers))

    def test_the_three_unmigratable_records_have_no_invented_claim(self) -> None:
        for graph_evidence_id in ("evidence:347", "evidence:1846", "evidence:1847"):
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(self.claims_by_ge.get(graph_evidence_id, []), [])
                self.assertEqual(self.parents[graph_evidence_id].claim_count, 0)

    def test_claim_types_are_all_valid(self) -> None:
        valid = {
            "atomic_intervention_claim",
            "aggregate_intervention_claim",
            "regimen_claim",
        }
        for claim in self.result.claims:
            with self.subTest(claim=claim.claim_id):
                self.assertIn(claim.claim_type, valid)

    def test_unsupported_and_unresolved_stay_separate(self) -> None:
        self.assertEqual(len(self.result.unsupported), 6)
        self.assertEqual(len(self.result.unresolved), 6)
        ids = {a.association_id for a in self.result.unsupported}
        ids &= {a.association_id for a in self.result.unresolved}
        self.assertEqual(ids, set())
        for association in (*self.result.unsupported, *self.result.unresolved):
            with self.subTest(association=association.association_id):
                self.assertFalse(association.is_claim)
                self.assertTrue(association.audit_only)
                self.assertFalse(association.positive_score_allowed)

    def test_an_aggregate_never_authorises_member_claims(self) -> None:
        with self.assertRaises(ClaimModelError):
            AggregateInterventionClaim(
                claim_id="CLM-x",
                parent_id="GEP-x",
                graph_evidence_id="evidence:1",
                biomarker="B",
                disease_scope="D",
                direction="sensitivity",
                polarity="supports",
                aggregate_type="intervention_class",
                aggregate_label="EGFR-TKI",
                permits_member_specific_claims=True,
            )

    def test_a_regimen_needs_at_least_two_components(self) -> None:
        with self.assertRaises(ClaimModelError):
            RegimenClaim(
                claim_id="CLM-x",
                parent_id="GEP-x",
                graph_evidence_id="evidence:1",
                biomarker="B",
                disease_scope="D",
                direction="sensitivity",
                polarity="supports",
                regimen_components=("erlotinib",),
            )

    def test_the_shadow_schema_versions_are_declared_and_not_promoted(self) -> None:
        self.assertEqual(MODEL_SCHEMA_VERSION, "qualified_claim_model/1.0")
        self.assertEqual(SHADOW_REPOSITORY_VERSION, "qualified_claim_repository/1.0")
        self.assertEqual(MIGRATION_STATUS, "shadow_not_promoted")


# ── identita' ─────────────────────────────────────────────────────────────────


class TestIdentity(MigrationCase):
    def test_the_frozen_adjudicated_ids_are_reproduced(self) -> None:
        frozen = {r["claim_id"] for r in load_jsonl(ADJ / "approved_claim_simulation.jsonl")}
        produced = {
            c.claim_id
            for c in self.result.claims
            if c.migration_origin == MIGRATION_ORIGIN_ADJUDICATED
        }
        self.assertEqual(produced, frozen)

    def test_ids_are_stable_on_recomputation(self) -> None:
        again = run_migration()
        self.assertEqual(
            [c.claim_id for c in again.claims], [c.claim_id for c in self.result.claims]
        )

    def test_regimen_identity_is_order_invariant(self) -> None:
        self.assertEqual(
            canonical_regimen(["ramucirumab", "erlotinib"]),
            canonical_regimen(["erlotinib", "ramucirumab"]),
        )
        forward = claim_id(
            graph_evidence_id="evidence:11240",
            claim_type="regimen_claim",
            canonical_intervention_or_regimen=canonical_regimen(["erlotinib", "ramucirumab"]),
            biomarker="B",
            direction="sensitivity",
            polarity="supports",
            source_unit_id="SU-1",
        )
        backward = claim_id(
            graph_evidence_id="evidence:11240",
            claim_type="regimen_claim",
            canonical_intervention_or_regimen=canonical_regimen(["ramucirumab", "erlotinib"]),
            biomarker="B",
            direction="sensitivity",
            polarity="supports",
            source_unit_id="SU-1",
        )
        self.assertEqual(forward, backward)

    def test_there_are_no_id_collisions_across_kinds(self) -> None:
        identifiers = (
            [c.claim_id for c in self.result.claims]
            + [a.association_id for a in self.result.unsupported]
            + [a.association_id for a in self.result.unresolved]
            + [p.parent_id for p in self.result.parents]
        )
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_pending_aliases_are_not_merged_by_the_identity(self) -> None:
        """BGJ398 e infigratinib restano identita' distinte."""
        common = {
            "graph_evidence_id": "evidence:1851",
            "claim_type": "atomic_intervention_claim",
            "biomarker": "FGFR2::BICC1 Fusion",
            "direction": "sensitivity",
            "polarity": "supports",
            "source_unit_id": "SU-1",
        }
        self.assertNotEqual(
            claim_id(canonical_intervention_or_regimen="bgj398", **common),
            claim_id(canonical_intervention_or_regimen="infigratinib", **common),
        )

    def test_the_separator_cannot_be_smuggled_into_a_field(self) -> None:
        with self.assertRaises(IdentityError):
            claim_id(
                graph_evidence_id="evidence:1|fake",
                claim_type="atomic_intervention_claim",
                canonical_intervention_or_regimen="x",
                biomarker="B",
                direction="sensitivity",
                polarity="supports",
                source_unit_id="SU-1",
            )

    def test_parent_ids_do_not_share_the_claim_id_space(self) -> None:
        self.assertTrue(parent_id("evidence:275").startswith("GEP-"))
        self.assertNotIn(
            parent_id("evidence:275"), {c.claim_id for c in self.result.claims}
        )


# ── adjudication ──────────────────────────────────────────────────────────────


class TestAdjudicatedGroups(MigrationCase):
    def test_the_adjudicated_claim_counts_match_the_adjudication(self) -> None:
        adjudicated = [
            c for c in self.result.claims if c.migration_origin == MIGRATION_ORIGIN_ADJUDICATED
        ]
        self.assertEqual(len(adjudicated), 15)
        by_type = {t: 0 for t in ("atomic_intervention_claim", "aggregate_intervention_claim", "regimen_claim")}
        for claim in adjudicated:
            by_type[claim.claim_type] += 1
        self.assertEqual(by_type["atomic_intervention_claim"], 9)
        self.assertEqual(by_type["aggregate_intervention_claim"], 3)
        self.assertEqual(by_type["regimen_claim"], 3)

    def test_evidence_275_is_an_aggregate_without_member_claims(self) -> None:
        claims = self.claims_by_ge["evidence:275"]
        self.assertEqual([c.claim_type for c in claims], ["aggregate_intervention_claim"])
        aggregate = claims[0]
        self.assertEqual(aggregate.aggregate_type, "intervention_class")
        self.assertEqual(aggregate.aggregate_label, "EGFR tyrosine kinase inhibitor")
        interventions = {
            getattr(c, "intervention", "").lower() for c in self.result.claims
            if c.graph_evidence_id == "evidence:275"
        }
        self.assertNotIn("erlotinib", interventions)
        self.assertNotIn("gefitinib", interventions)
        self.assertEqual(len(self.parents["evidence:275"].unsupported_association_ids), 2)

    def test_evidence_4759_has_no_positive_claim(self) -> None:
        self.assertEqual(self.claims_by_ge.get("evidence:4759", []), [])
        parent = self.parents["evidence:4759"]
        self.assertEqual(len(parent.unsupported_association_ids), 2)
        self.assertEqual(parent.deprecated_statement_ids, ("ES-V2-evidence-4759",))

    def test_evidence_3811_is_unresolved_without_claims(self) -> None:
        self.assertEqual(self.claims_by_ge.get("evidence:3811", []), [])
        parent = self.parents["evidence:3811"]
        self.assertEqual(len(parent.unresolved_association_ids), 3)
        self.assertEqual(len(parent.unsupported_association_ids), 0)

    def test_evidence_11240_keeps_regimen_and_atomic_apart(self) -> None:
        claims = {c.claim_type: c for c in self.claims_by_ge["evidence:11240"]}
        self.assertEqual(len(claims), 2)
        regimen = claims["regimen_claim"]
        atomic = claims["atomic_intervention_claim"]
        self.assertEqual(regimen.canonical_component_set, ("erlotinib", "ramucirumab"))
        self.assertEqual(atomic.intervention, "erlotinib")
        # Le unita' di fonte sono braccia diverse dello stesso studio, e restano
        # separate: l'atomico non nasce dalla scomposizione del regime.
        self.assertNotEqual(regimen.source_unit_ids, atomic.source_unit_ids)
        self.assertIn("ramucirumab-erlotinib", regimen.source_unit_ids[0])
        self.assertIn("placebo-erlotinib", atomic.source_unit_ids[0])

    def test_evidence_12131_is_a_regimen_without_component_claims(self) -> None:
        claims = self.claims_by_ge["evidence:12131"]
        self.assertEqual([c.claim_type for c in claims], ["regimen_claim"])
        self.assertEqual(
            claims[0].canonical_component_set, ("amivantamab", "lazertinib")
        )

    def test_thirteen_statements_are_deprecated_two_without_replacement(self) -> None:
        deprecated = [d for d in self.result.deprecations if d.is_deprecated]
        self.assertEqual(len(deprecated), 13)
        without = [
            d for d in deprecated if d.deprecation_state == "deprecated_without_replacement"
        ]
        self.assertEqual(len(without), 2)
        self.assertEqual(
            {d.graph_evidence_id for d in without}, {"evidence:3811", "evidence:4759"}
        )

    def test_no_operational_statement_is_deleted(self) -> None:
        statements = {
            s["evidence_statement_id"] for s in load_jsonl(CORPUS / "evidence_statements.jsonl")
        }
        mapped = {d.legacy_statement_id for d in self.result.deprecations}
        self.assertEqual(mapped, statements)
        for deprecation in self.result.deprecations:
            with self.subTest(statement=deprecation.legacy_statement_id):
                self.assertTrue(deprecation.reversible)
                self.assertTrue(deprecation.to_dict()["statement_still_readable"])


class TestLegacyMigration(MigrationCase):
    def test_legacy_claims_preserve_current_semantics(self) -> None:
        legacy = [
            c for c in self.result.claims if c.migration_origin == MIGRATION_ORIGIN_LEGACY
        ]
        self.assertEqual(len(legacy), 131)
        statements = {
            s["evidence_statement_id"]: s
            for s in load_jsonl(CORPUS / "evidence_statements.jsonl")
        }
        for claim in legacy:
            statement = statements[claim.legacy_statement_ids[0]]
            with self.subTest(claim=claim.claim_id):
                self.assertEqual(claim.review_status, statement["review_status"])
                self.assertEqual(claim.direction, statement["direction"])
                self.assertEqual(claim.polarity, statement["assertion_polarity"])
                self.assertEqual(
                    claim.intervention, statement["intervention"]["label"]
                )
                self.assertEqual(claim.propagation_policy, "prototype_only")
                self.assertFalse(claim.documentary_revalidation_completed)

    def test_legacy_claims_invent_no_source_unit(self) -> None:
        for claim in self.result.claims:
            if claim.migration_origin != MIGRATION_ORIGIN_LEGACY:
                continue
            with self.subTest(claim=claim.claim_id):
                self.assertEqual(claim.source_unit_ids, ())
                self.assertEqual(claim.locators, ())

    def test_automatic_review_is_not_promoted_to_human_review(self) -> None:
        for claim in self.result.claims:
            if claim.migration_origin != MIGRATION_ORIGIN_LEGACY:
                continue
            with self.subTest(claim=claim.claim_id):
                self.assertNotIn(claim.review_status, ("adjudicated", "final", "verified"))


# ── gate ──────────────────────────────────────────────────────────────────────


def query(**overrides) -> dict:
    payload = {
        "query_id": "QT",
        "disease": "Lung Non-small Cell Carcinoma",
        "biomarker": "EGFR L858R OR EGFR Exon 19 Deletion",
        "direction": "sensitivity",
        "polarity": "supports",
        "interventions": [],
        "intervention_combination": False,
        "intervention_class": None,
    }
    payload.update(overrides)
    return payload


class TestStructuralGates(MigrationCase):
    def claim(self, graph_evidence_id: str, claim_type: str):
        for candidate in self.claims_by_ge[graph_evidence_id]:
            if candidate.claim_type == claim_type:
                return candidate
        raise AssertionError(f"{graph_evidence_id}: nessun claim {claim_type}")

    def test_a_parent_is_always_audit_only(self) -> None:
        for graph_evidence_id in MANDATORY_CASES:
            parent = self.parents[graph_evidence_id]
            match = GATE.evaluate(query(biomarker=parent.biomarker_context or ""), parent)
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertTrue(match.audit_only)
                self.assertFalse(match.primary_candidate_eligible)
                self.assertEqual(match.bucket, GATE.AUDIT_BUCKET)
                self.assertIn(
                    "PARENT_PROVENANCE_CONTAINER_NOT_CLAIM", match.exclusion_reason_codes
                )

    def test_an_exact_atomic_match_is_primary(self) -> None:
        atomic = self.claim("evidence:11240", "atomic_intervention_claim")
        match = GATE.evaluate(query(interventions=["erlotinib"]), atomic)
        self.assertEqual(match.intervention_match_type, "exact_atomic_intervention")
        self.assertEqual(match.bucket, GATE.PRIMARY_BUCKET)

    def test_an_exact_regimen_is_primary(self) -> None:
        regimen = self.claim("evidence:11240", "regimen_claim")
        match = GATE.evaluate(
            query(interventions=["ramucirumab", "erlotinib"], intervention_combination=True),
            regimen,
        )
        self.assertEqual(match.intervention_match_type, "exact_regimen")
        self.assertEqual(match.bucket, GATE.PRIMARY_BUCKET)

    def test_a_regimen_component_is_warning_never_primary(self) -> None:
        regimen = self.claim("evidence:11240", "regimen_claim")
        match = GATE.evaluate(query(interventions=["ramucirumab"]), regimen)
        self.assertEqual(match.intervention_match_type, "regimen_component_related")
        self.assertEqual(match.bucket, GATE.WARNING_BUCKET)
        self.assertFalse(match.primary_candidate_eligible)
        self.assertIn("RESULT_APPLIES_TO_COMBINATION_NOT_COMPONENT", match.warning_codes)

    def test_an_exact_class_is_primary(self) -> None:
        aggregate = self.claim("evidence:275", "aggregate_intervention_claim")
        match = GATE.evaluate(
            query(
                biomarker="EGFR L858R",
                intervention_class="EGFR tyrosine kinase inhibitor",
            ),
            aggregate,
        )
        self.assertEqual(match.intervention_match_type, "exact_intervention_class")
        self.assertEqual(match.bucket, GATE.PRIMARY_BUCKET)

    def test_a_class_member_is_not_drug_specific(self) -> None:
        """La relazione farmaco-classe non e' verificata e non si deduce."""
        aggregate = self.claim("evidence:275", "aggregate_intervention_claim")
        match = GATE.evaluate(
            query(biomarker="EGFR L858R", interventions=["erlotinib"]), aggregate
        )
        self.assertEqual(match.intervention_match_type, "unresolved_class_relation")
        self.assertFalse(match.primary_candidate_eligible)
        self.assertEqual(match.bucket, GATE.AUDIT_BUCKET)

    def test_an_aggregate_member_is_warning(self) -> None:
        aggregate = self.claim("evidence:1851", "aggregate_intervention_claim")
        match = GATE.evaluate(
            query(
                disease="Cholangiocarcinoma",
                biomarker="FGFR2::BICC1 Fusion",
                interventions=["pd173074"],
            ),
            aggregate,
        )
        self.assertEqual(match.intervention_match_type, "aggregate_member_related")
        self.assertEqual(match.bucket, GATE.WARNING_BUCKET)
        self.assertIn(
            "AGGREGATE_RESULT_NOT_SEPARABLE_BY_INTERVENTION", match.warning_codes
        )

    def test_a_pending_mapping_is_audit_only(self) -> None:
        aggregate = self.claim("evidence:1851", "aggregate_intervention_claim")
        match = GATE.evaluate(
            query(
                disease="Cholangiocarcinoma",
                biomarker="FGFR2::BICC1 Fusion",
                interventions=["infigratinib"],
            ),
            aggregate,
        )
        self.assertEqual(match.intervention_match_type, "mapping_pending")
        self.assertEqual(match.bucket, GATE.AUDIT_BUCKET)
        self.assertFalse(match.primary_candidate_eligible)

    def test_unsupported_and_unresolved_are_audit_only(self) -> None:
        for association in (*self.result.unsupported, *self.result.unresolved):
            match = GATE.evaluate(
                query(
                    disease=None,
                    biomarker=association.biomarker,
                    interventions=[association.intervention_literal],
                ),
                association,
            )
            with self.subTest(association=association.association_id):
                self.assertFalse(match.primary_candidate_eligible)
                self.assertEqual(match.bucket, GATE.AUDIT_BUCKET)

    def test_negative_and_conflicting_directions_are_preserved(self) -> None:
        resistance = [
            c for c in self.result.claims if c.direction == "resistance"
        ]
        self.assertTrue(resistance)
        claim = resistance[0]
        match = GATE.evaluate(
            query(
                disease=claim.disease_scope,
                biomarker=claim.biomarker,
                direction="resistance",
                interventions=[claim.intervention],
            ),
            claim,
        )
        self.assertEqual(match.direction_match_type, "exact")
        self.assertEqual(match.bucket, GATE.PRIMARY_BUCKET)
        # Chiedere sensibilita' contro un claim di resistenza resta incompatibile.
        opposed = GATE.evaluate(
            query(
                disease=claim.disease_scope,
                biomarker=claim.biomarker,
                direction="sensitivity",
                interventions=[claim.intervention],
            ),
            claim,
        )
        self.assertTrue(opposed.rejected_by_native_constraints)
        self.assertIn("NATIVE_DIRECTION_MISMATCH", opposed.exclusion_reason_codes)

    def test_reduced_sensitivity_is_not_resistance(self) -> None:
        claim = [c for c in self.result.claims if c.direction == "resistance"][0]
        match = GATE.evaluate(
            query(
                disease=claim.disease_scope,
                biomarker=claim.biomarker,
                direction="reduced_sensitivity",
                interventions=[claim.intervention],
            ),
            claim,
        )
        self.assertFalse(match.primary_candidate_eligible)
        self.assertIn("REDUCED_SENSITIVITY_IS_NOT_RESISTANCE", match.warning_codes)

    def test_a_deprecated_claim_never_reaches_the_primary_bucket(self) -> None:
        from dataclasses import replace

        atomic = self.claim("evidence:11240", "atomic_intervention_claim")
        match = GATE.evaluate(
            query(interventions=["erlotinib"]), replace(atomic, deprecated=True)
        )
        self.assertEqual(match.bucket, GATE.AUDIT_BUCKET)
        self.assertFalse(match.primary_candidate_eligible)
        self.assertIn("CLAIM_DEPRECATED", match.exclusion_reason_codes)


class TestScoreCannotBypassTheGate(MigrationCase):
    def test_an_arbitrarily_high_score_does_not_promote_a_candidate(self) -> None:
        regimen = [
            c for c in self.claims_by_ge["evidence:11240"] if c.claim_type == "regimen_claim"
        ][0]
        match = GATE.evaluate(query(interventions=["ramucirumab"]), regimen)
        self.assertEqual(match.bucket, GATE.WARNING_BUCKET)
        for score in (0.0, 1.0, 10**6, float("inf")):
            with self.subTest(score=score):
                SCORE.assert_gate_not_bypassed(match, score)
                self.assertEqual(SCORE.bucket_after_score(match, score), GATE.WARNING_BUCKET)

    def test_a_high_score_does_not_lift_an_unsupported_association(self) -> None:
        association = self.result.unsupported[0]
        match = GATE.evaluate(
            query(
                disease=None,
                biomarker=association.biomarker,
                interventions=[association.intervention_literal],
            ),
            association,
        )
        for score in (10**9, float("inf")):
            with self.subTest(score=score):
                SCORE.assert_gate_not_bypassed(match, score)
                self.assertEqual(SCORE.bucket_after_score(match, score), GATE.AUDIT_BUCKET)

    def test_scoring_refuses_candidates_the_gate_rejected(self) -> None:
        claim = self.result.claims[0]
        match = GATE.evaluate(query(biomarker="un biomarcatore che non esiste"), claim)
        self.assertTrue(match.rejected_by_native_constraints)
        with self.assertRaises(SCORE.ShadowScoringError):
            SCORE.features_for(match)

    def test_the_legacy_penalties_do_not_decide_eligibility(self) -> None:
        audit = SCORE.legacy_penalty_audit()
        self.assertEqual(set(audit), set(SCORE.LEGACY_PENALTIES))
        for name, entry in audit.items():
            with self.subTest(penalty=name):
                self.assertTrue(entry["present_in_operational_config"])
                self.assertFalse(entry["decides_primary_eligibility"])
                self.assertFalse(entry["required_to_block_promotion"])
                self.assertEqual(entry["shadow_role"], "legacy_feature_not_operational")


# ── output ────────────────────────────────────────────────────────────────────


class TestOutputContract(MigrationCase):
    def test_a_regimen_is_never_flattened_to_one_drug(self) -> None:
        regimen = [
            c for c in self.claims_by_ge["evidence:11240"] if c.claim_type == "regimen_claim"
        ][0]
        match = GATE.evaluate(
            query(interventions=["erlotinib", "ramucirumab"], intervention_combination=True),
            regimen,
        )
        result = OUT.build_result("QT", regimen, match)
        self.assertEqual(result.intervention_representation, "regimen")
        self.assertEqual(len(result.intervention["regimen_components"]), 2)
        self.assertFalse(result.intervention["propagates_to_components"])

    def test_an_aggregate_is_never_flattened_to_its_first_member(self) -> None:
        aggregate = [
            c for c in self.claims_by_ge["evidence:1851"]
            if c.claim_type == "aggregate_intervention_claim"
        ][0]
        match = GATE.evaluate(
            query(
                disease="Cholangiocarcinoma",
                biomarker="FGFR2::BICC1 Fusion",
                interventions=["pd173074"],
            ),
            aggregate,
        )
        result = OUT.build_result("QT", aggregate, match)
        self.assertEqual(result.intervention_representation, "aggregate")
        self.assertEqual(
            result.intervention["aggregate_members_literal"], ["BGJ398", "PD173074"]
        )
        self.assertFalse(result.intervention["permits_member_specific_claims"])

    def test_a_parent_is_never_presented_as_a_claim(self) -> None:
        parent = self.parents["evidence:275"]
        match = GATE.evaluate(query(biomarker="EGFR L858R"), parent)
        result = OUT.build_result("QT", parent, match)
        self.assertEqual(result.intervention_representation, "none")
        self.assertFalse(result.is_positive_evidence)
        self.assertEqual(result.bucket, GATE.AUDIT_BUCKET)

    def test_an_unsupported_association_is_never_positive_evidence(self) -> None:
        for association in (*self.result.unsupported, *self.result.unresolved):
            match = GATE.evaluate(
                query(
                    disease=None,
                    biomarker=association.biomarker,
                    interventions=[association.intervention_literal],
                ),
                association,
            )
            result = OUT.build_result("QT", association, match)
            with self.subTest(association=association.association_id):
                self.assertFalse(result.is_positive_evidence)
                self.assertNotEqual(result.bucket, GATE.PRIMARY_BUCKET)

    def test_every_representation_is_one_of_the_five_declared(self) -> None:
        rows = load_jsonl(SHADOW / "shadow_gate_simulation.jsonl")
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(object_id=row["object_id"]):
                self.assertIn(
                    row["intervention_representation"], OUT.INTERVENTION_REPRESENTATIONS
                )


# ── artefatti e determinismo ──────────────────────────────────────────────────


class TestArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = build()
        cls.manifest = json.loads(cls.artifacts["shadow_repository_manifest.json"])

    def test_all_declared_artifacts_exist_on_disk(self) -> None:
        expected = {
            "graph_evidence_parents.jsonl",
            "typed_claims.jsonl",
            "atomic_claims.jsonl",
            "aggregate_claims.jsonl",
            "regimen_claims.jsonl",
            "unsupported_associations.jsonl",
            "unresolved_associations.jsonl",
            "legacy_statement_deprecation_map.jsonl",
            "qualification_link_regeneration_plan.jsonl",
            "qualified_view_regeneration_plan.jsonl",
            "claim_id_manifest.json",
            "shadow_repository_manifest.json",
            "operational_vs_shadow_inventory.json",
            "shadow_gate_simulation.jsonl",
            "legacy_penalty_bypass_tests.json",
            "migration_blockers.jsonl",
            "TYPED_CLAIM_SHADOW_MIGRATION.md",
            "STRUCTURAL_GATE_IMPLEMENTATION.md",
            "SHADOW_REPOSITORY_READINESS.md",
        }
        for name in sorted(expected):
            with self.subTest(artifact=name):
                self.assertTrue((SHADOW / name).exists())

    def test_two_generations_are_byte_identical(self) -> None:
        self.assertEqual(build(), self.artifacts)

    def test_reversing_the_input_order_changes_nothing(self) -> None:
        self.assertEqual(build(reverse=True), self.artifacts)

    def test_the_generated_files_match_the_regenerated_content(self) -> None:
        for name, text in sorted(self.artifacts.items()):
            with self.subTest(artifact=name):
                self.assertEqual((SHADOW / name).read_text(encoding="utf-8"), text)

    def test_the_manifest_hashes_match_the_files_on_disk(self) -> None:
        for name, expected in self.manifest["artifact_sha256"].items():
            with self.subTest(artifact=name):
                digest = hashlib.sha256(
                    (SHADOW / name).read_text(encoding="utf-8").encode("utf-8")
                ).hexdigest()
                self.assertEqual(digest, expected)

    def test_no_machine_specific_path_leaks_into_the_artifacts(self) -> None:
        for name, text in sorted(self.artifacts.items()):
            lowered = text.lower()
            with self.subTest(artifact=name):
                for fragment in ("c:\\", "/users/", "/home/", "appdata"):
                    self.assertNotIn(fragment, lowered)

    def test_the_manifest_declares_the_shadow_is_not_promoted(self) -> None:
        self.assertEqual(self.manifest["migration_status"], MIGRATION_STATUS)
        for flag in (
            "operational_corpus_modified",
            "operational_adapter_modified",
            "operational_retriever_modified",
            "operational_scoring_modified",
            "qualified_views_regenerated",
            "hierarchy_policy_applied",
            "pending_mappings_promoted",
            "exploratory_evaluation_executed",
            "gold_used",
            "network_used",
            "neo4j_used",
            "llm_used",
        ):
            with self.subTest(flag=flag):
                self.assertFalse(self.manifest[flag])

    def test_the_counts_are_derived_and_consistent(self) -> None:
        counts = self.manifest["counts"]
        self.assertEqual(counts["parents"], 147)
        self.assertEqual(counts["claims_total"], 146)
        self.assertEqual(counts["claims_adjudicated"], 15)
        self.assertEqual(counts["claims_legacy_migrated"], 131)
        self.assertEqual(counts["atomic_claims_adjudicated"], 9)
        self.assertEqual(counts["aggregate_claims_adjudicated"], 3)
        self.assertEqual(counts["regimen_claims_adjudicated"], 3)
        self.assertEqual(counts["unsupported_associations"], 6)
        self.assertEqual(counts["unresolved_associations"], 6)
        self.assertEqual(counts["legacy_statements_deprecated"], 13)
        self.assertEqual(counts["deprecated_without_replacement"], 2)
        self.assertEqual(counts["parents_in_primary_ranking"], 0)
        self.assertEqual(
            counts["claims_adjudicated"] + counts["claims_legacy_migrated"],
            counts["claims_total"],
        )

    def test_no_parent_ever_appears_in_the_primary_bucket(self) -> None:
        rows = load_jsonl(SHADOW / "shadow_gate_simulation.jsonl")
        parents = [
            r for r in rows
            if r["object_kind"] == "graph_evidence_record"
            and r["bucket"] == GATE.PRIMARY_BUCKET
        ]
        self.assertEqual(parents, [])

    def test_no_mapping_pending_candidate_is_exact(self) -> None:
        rows = load_jsonl(SHADOW / "shadow_gate_simulation.jsonl")
        for row in rows:
            if row["structural_match"]["intervention_match_type"] != "mapping_pending":
                continue
            with self.subTest(object_id=row["object_id"]):
                self.assertNotEqual(row["bucket"], GATE.PRIMARY_BUCKET)

    def test_no_aggregate_member_or_regimen_component_is_promoted_to_exact(self) -> None:
        rows = load_jsonl(SHADOW / "shadow_gate_simulation.jsonl")
        related = (
            "aggregate_member_related",
            "class_member_related",
            "regimen_component_related",
        )
        for row in rows:
            if row["structural_match"]["intervention_match_type"] not in related:
                continue
            with self.subTest(object_id=row["object_id"]):
                self.assertNotEqual(row["bucket"], GATE.PRIMARY_BUCKET)

    def test_the_bypass_report_shows_no_candidate_promoted_by_score(self) -> None:
        report = json.loads(self.artifacts["legacy_penalty_bypass_tests.json"])
        self.assertEqual(report["candidates_promoted_by_score"], 0)
        self.assertGreater(report["non_primary_candidates_probed"], 0)
        self.assertFalse(report["operational_scoring_modified"])
        for case in report["cases"]:
            for probe in case["probes"]:
                with self.subTest(object_id=case["object_id"], score=probe["hypothetical_score"]):
                    self.assertFalse(probe["reached_primary"])
                    self.assertEqual(probe["bucket"], case["gate_bucket"])


# ── compatibilita' operativa ──────────────────────────────────────────────────


class TestOperationalArtifactsUnchanged(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scope = PhaseScope(
            REPO_ROOT.parent,
            START_SHA,
            PHASE_END_SHA,
            (
                "benchmarks/mtb_evidence/v3/typed_claim_shadow_migration/",
                "benchmarks/mtb_evidence/evaluation/scripts/build_typed_claim_shadow_migration.py",
                "backend/pipeline/evidence/shadow/",
                "backend/tests/phase_scope.py",
                "backend/tests/test_phase_scope_guard.py",
                "backend/tests/test_typed_claim_shadow_migration.py",
                "backend/tests/test_claim_type_retrieval_contract.py",
                "backend/tests/test_multi_intervention_adjudication.py",
                "backend/tests/test_multi_intervention_review_comparison.py",
                "backend/tests/test_multi_intervention_second_review.py",
            ),
        )
        cls.changed = cls.scope.changed_paths()

    def test_no_operational_module_or_artifact_was_modified(self) -> None:
        for path in FROZEN_OPERATIONAL_PATHS:
            with self.subTest(path=path):
                self.assertNotIn(path, self.changed)

    def test_the_branch_only_wrote_inside_the_shadow_perimeter(self) -> None:
        self.assertEqual(
            self.scope.violations(self.changed),
            [],
            "modifica fuori dal perimetro della migrazione shadow",
        )

    def test_no_upstream_scientific_artifact_was_modified(self) -> None:
        for path in sorted(self.changed):
            with self.subTest(path=path):
                for prefix in (
                    "multi_intervention_source_review/",
                    "multi_intervention_second_review/",
                    "multi_intervention_review_comparison/",
                    "multi_intervention_adjudication/",
                    "claim_type_retrieval_contract/",
                    "qualification_corpus_v2/",
                ):
                    self.assertNotIn(prefix, path)


class TestIsolationFromOperationalCode(unittest.TestCase):
    def test_no_operational_module_imports_the_shadow_package(self) -> None:
        evidence = REPO_ROOT / "backend/pipeline/evidence"
        for path in sorted(evidence.glob("*.py")):
            with self.subTest(module=path.name):
                self.assertNotIn("shadow", path.read_text(encoding="utf-8"))

    def shadow_sources(self) -> list[Path]:
        shadow = REPO_ROOT / "backend/pipeline/evidence/shadow"
        script = (
            REPO_ROOT
            / "benchmarks/mtb_evidence/evaluation/scripts/build_typed_claim_shadow_migration.py"
        )
        return sorted(shadow.glob("*.py")) + [script]

    def test_the_shadow_package_does_not_read_the_gold(self) -> None:
        """Nessun artefatto di gold e' nominato come sorgente da leggere.

        Il controllo cerca i nomi dei file di gold, non la parola `gold`: la
        parola compare legittimamente nelle flag di provenienza copiate
        dall'adjudication (`gold_used_for_decisions`) e nelle affermazioni del
        manifest, che dicono proprio che il gold non e' stato usato.
        """
        gold_artifacts = (
            "clinical_gold",
            "snapshot_gold",
            "statement_qualification_gold",
            "gold_pilot",
            "evaluation_gold_snapshot",
            "mtb_evidence_gold",
            "recall@",
            "precision@",
        )
        for path in self.shadow_sources():
            blob = path.read_text(encoding="utf-8").lower()
            with self.subTest(module=path.name):
                for fragment in gold_artifacts:
                    self.assertNotIn(fragment, blob)

    def test_no_gold_flag_in_the_artifacts_claims_the_gold_was_used(self) -> None:
        manifest = json.loads(
            (SHADOW / "shadow_repository_manifest.json").read_text(encoding="utf-8")
        )
        self.assertFalse(manifest["gold_used"])

    def test_the_shadow_package_uses_no_network_neo4j_or_llm(self) -> None:
        """Nessun import di rete, driver o client LLM.

        Il controllo guarda le righe di import, non il testo intero: `neo4j_used`
        e `llm_used` nel manifest sono affermazioni di non-uso, e cercarle come
        sottostringhe le confonderebbe con l'uso che negano.
        """
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
        for path in self.shadow_sources():
            lines = path.read_text(encoding="utf-8").splitlines()
            imports = [
                line.strip()
                for line in lines
                if line.strip().startswith(("import ", "from "))
            ]
            with self.subTest(module=path.name):
                for line in imports:
                    for fragment in forbidden:
                        self.assertNotIn(fragment, line)

    def test_the_operational_scoring_config_is_only_read(self) -> None:
        source = (
            REPO_ROOT / "backend/pipeline/evidence/shadow/shadow_scoring.py"
        ).read_text(encoding="utf-8")
        self.assertIn("read_text", source)
        for fragment in ("write_text", "open(", "json.dump"):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, source)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

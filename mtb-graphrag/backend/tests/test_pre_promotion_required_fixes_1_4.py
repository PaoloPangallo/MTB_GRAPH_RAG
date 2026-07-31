"""Protegge le correzioni richieste prima della promozione.

I test difendono cinque cose, e ognuna e' un modo di sbagliare che questa fase
rende possibile per la prima volta.

Che la propagation policy sia davvero obbligatoria, cioe' che un record che non
la porta venga **rifiutato** e non completato con un default: un default in
lettura riporterebbe il problema dov'era con in piu' l'illusione di averlo
risolto.

Che aggregati e regimi non propaghino, e che il divieto sia scritto nel record
invece di essere dedotto dal suo silenzio.

Che nessuna forma diventi exact rispetto alla propria moiety, in nessuna
direzione, e che due sali diversi non si fondano — nemmeno quando condividono la
moiety, nemmeno quando il suffisso e' in una tabella.

Che il gate di forma non sia aggirabile: nessun punteggio, nessun disease exact,
nessun biomarcatore exact riapre cio' che la forma ha chiuso.

Che la correzione non abbia cambiato nessuna identita' di claim, nessun
conteggio, e nessun artefatto che dichiara di non toccare.
"""

from __future__ import annotations

import json
import unittest

from pathlib import Path

from backend.pipeline.evidence.shadow import disease_gate as DISEASE
from backend.pipeline.evidence.shadow import formulation as FORM
from backend.pipeline.evidence.shadow import integrated_gates_v11 as GATE
from backend.pipeline.evidence.shadow import migration_v14 as M14
from backend.pipeline.evidence.shadow import propagation as PROP
from backend.pipeline.evidence.shadow.claims import AtomicInterventionClaim
from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation import formulation_audit as FA
from benchmarks.mtb_evidence.evaluation import required_fixes_1_4 as FIXES
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import scope as SCOPE
from benchmarks.mtb_evidence.evaluation import tree_hash_erratum as TREE_ERRATUM
from benchmarks.mtb_evidence.evaluation.scripts.build_pre_promotion_required_fixes_1_4 import (
    DEFAULT_OUTPUT,
    EXPECTED_COUNTS,
    START_SHA,
    build,
    build_data_artifacts,
    build_repository,
    load_v13,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = DEFAULT_OUTPUT

# Estremo di fase: il commit che chiude la fase, mai HEAD. Il perimetro di una
# fase e' una proprieta' storica e chiusa, e misurarlo contro l'albero di lavoro
# lo farebbe crescere con la fase successiva, fallendo per la ragione sbagliata.
PHASE_END_SHA = "ba75417b06dda8535e5f13a3c4ec354243d291e3"

ALLOWED_WRITE_PREFIXES = (
    "benchmarks/mtb_evidence/v3/pre_promotion_required_fixes_1_4/",
    "benchmarks/mtb_evidence/evaluation/formulation_audit.py",
    "benchmarks/mtb_evidence/evaluation/required_fixes_1_4.py",
    "benchmarks/mtb_evidence/evaluation/required_fixes_reports.py",
    "benchmarks/mtb_evidence/evaluation/scripts/build_pre_promotion_required_fixes_1_4.py",
    "backend/pipeline/evidence/shadow/formulation.py",
    "backend/pipeline/evidence/shadow/integrated_gates_v11.py",
    "backend/pipeline/evidence/shadow/migration_v14.py",
    "backend/pipeline/evidence/shadow/propagation.py",
    "backend/tests/test_pre_promotion_required_fixes_1_4.py",
)

FROZEN_SHADOW_DIRS = (
    "benchmarks/mtb_evidence/v3/typed_claim_shadow_migration",
    "benchmarks/mtb_evidence/v3/non_therapeutic_shadow_update",
    "benchmarks/mtb_evidence/v3/diagnostic_disease_scope_narrowing_shadow",
    "benchmarks/mtb_evidence/v3/integrated_shadow_repository_1_3",
    "benchmarks/mtb_evidence/v3/pre_promotion_audit_1_3",
)

REQUIRED_ARTIFACTS = (
    "repository_v1_4_manifest.json",
    "evidence_claims_v1_4.jsonl",
    "propagation_policy_matrix.jsonl",
    "aggregate_propagation_audit.jsonl",
    "regimen_propagation_audit.jsonl",
    "formulation_relation_definitions.json",
    "formulation_registry_snapshot.jsonl",
    "formulation_claim_audit.jsonl",
    "formulation_gate_simulation.jsonl",
    "integrated_gate_regression.jsonl",
    "claim_id_impact.jsonl",
    "qualification_link_plan_v1_4.jsonl",
    "policy_mode_contract.json",
    "backward_compatibility_addendum.json",
    "post_fix_findings.jsonl",
    "post_fix_readiness.json",
    "repository_version_lineage.json",
    "PRE_PROMOTION_REQUIRED_FIXES_1_4.md",
    "FORMULATION_MATCHING_CONTRACT.md",
    "PROPAGATION_POLICY_CONTRACT.md",
    "SHADOW_REPOSITORY_1_4_READINESS.md",
)


def _artifact(name: str):
    text = (OUTPUT / name).read_text(encoding="utf-8")
    if name.endswith(".jsonl"):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)


class PropagationSchemaTests(unittest.TestCase):
    """La propagation policy e' obbligatoria, e obbligatoria significa rifiutata."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.records, cls.changes = build_repository()

    def test_a_record_without_propagation_policy_is_rejected(self) -> None:
        record = dict(self.records[0])
        record.pop("propagation_policy")
        with self.assertRaises(PROP.PropagationSchemaError):
            PROP.validate_record(record)

    def test_a_record_without_the_evaluability_flags_is_rejected(self) -> None:
        for field in ("hard_filterable", "final_evaluable"):
            with self.subTest(field=field):
                record = dict(self.records[0])
                record.pop(field)
                with self.assertRaises(PROP.PropagationSchemaError):
                    PROP.validate_record(record)

    def test_an_unknown_propagation_policy_is_rejected(self) -> None:
        with self.assertRaises(PROP.PropagationSchemaError):
            PROP.validate_policy("propagate_everywhere", claim_id="CLM-X")

    def test_deserialization_has_no_implicit_default(self) -> None:
        with self.assertRaises(PROP.PropagationSchemaError):
            PROP.validate_policy(None, claim_id="CLM-X")
        contract = PROP.propagation_contract()
        self.assertIsNone(contract["deserialization_default"])
        self.assertFalse(contract["implicit_defaults_permitted"])
        self.assertTrue(contract["record_without_policy_is_rejected"])

    def test_every_active_claim_declares_the_three_fields(self) -> None:
        for record in self.records:
            with self.subTest(claim=record["claim_id"]):
                for field in PROP.REQUIRED_PROPAGATION_FIELDS:
                    self.assertIsNotNone(record.get(field))

    def test_every_declared_policy_is_an_allowed_value(self) -> None:
        for record in self.records:
            with self.subTest(claim=record["claim_id"]):
                self.assertIn(record["propagation_policy"], PROP.PROPAGATION_POLICIES)

    def test_every_active_claim_validates(self) -> None:
        for record in self.records:
            with self.subTest(claim=record["claim_id"]):
                PROP.validate_record(record)

    def test_the_six_non_atomic_claims_gained_the_policy(self) -> None:
        gained = [
            change
            for change in self.changes
            if "propagation_policy" in change.fields_added
        ]
        self.assertEqual(len(gained), 6)
        self.assertEqual(
            {change.claim_type for change in gained},
            set(PROP.NON_ATOMIC_CLAIM_TYPES),
        )

    def test_existing_documentary_values_are_not_overwritten(self) -> None:
        before = {record["claim_id"]: record for record in load_v13()["claims"]}
        for record in self.records:
            previous = before[record["claim_id"]]
            if previous.get("propagation_policy") is None:
                continue
            with self.subTest(claim=record["claim_id"]):
                self.assertEqual(
                    record["propagation_policy"], previous["propagation_policy"]
                )


class NonAtomicPropagationTests(unittest.TestCase):
    """Aggregati e regimi non propagano, e il divieto e' scritto."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.records, _ = build_repository()
        cls.aggregates = M14.aggregate_audit(cls.records)
        cls.regimens = M14.regimen_audit(cls.records)

    def test_there_are_three_aggregates_and_three_regimens(self) -> None:
        self.assertEqual(len(self.aggregates), 3)
        self.assertEqual(len(self.regimens), 3)

    def test_no_aggregate_member_inherits_the_result(self) -> None:
        for row in self.aggregates:
            with self.subTest(claim=row["claim_id"]):
                self.assertFalse(row["member_propagation_allowed"])
                self.assertFalse(row["permits_member_specific_claims"])
                self.assertEqual(row["members_inheriting_the_result"], [])

    def test_no_regimen_component_inherits_the_result(self) -> None:
        for row in self.regimens:
            with self.subTest(claim=row["claim_id"]):
                self.assertFalse(row["member_propagation_allowed"])
                self.assertTrue(row["result_applies_to_combination"])
                self.assertEqual(row["components_inheriting_the_result"], [])

    def test_an_aggregate_declaring_member_propagation_is_rejected(self) -> None:
        record = dict(
            next(
                item
                for item in self.records
                if item["claim_type"] == "aggregate_intervention_claim"
            )
        )
        record["member_propagation_allowed"] = True
        with self.assertRaises(PROP.PropagationSchemaError):
            PROP.validate_record(record)

    def test_a_regimen_denying_the_combination_result_is_rejected(self) -> None:
        record = dict(
            next(item for item in self.records if item["claim_type"] == "regimen_claim")
        )
        record["result_applies_to_combination"] = False
        with self.assertRaises(PROP.PropagationSchemaError):
            PROP.validate_record(record)

    def test_no_aggregate_is_atomized_and_no_regimen_is_split(self) -> None:
        manifest = _artifact("repository_v1_4_manifest.json")
        self.assertEqual(manifest["invariants"]["aggregates_atomized"], 0)
        self.assertEqual(manifest["invariants"]["regimens_split"], 0)
        self.assertEqual(manifest["invariants"]["member_propagation_allowed"], 0)

    def test_the_matrix_covers_every_claim(self) -> None:
        matrix = _artifact("propagation_policy_matrix.jsonl")
        self.assertEqual(len(matrix), EXPECTED_COUNTS["active_claims_total"])
        for row in matrix:
            with self.subTest(claim=row["claim_id"]):
                self.assertIn("propagation_policy", row)
                self.assertIn("hard_filterable", row)
                self.assertIn("final_evaluable", row)
                if row["claim_type"] in PROP.NON_ATOMIC_CLAIM_TYPES:
                    self.assertIn("member_propagation_allowed", row)


class FormulationContractTests(unittest.TestCase):
    """Nessuna forma diventa exact rispetto alla propria moiety."""

    def test_the_same_form_is_exact(self) -> None:
        relation = FORM.resolve("infigratinib", "infigratinib")
        self.assertEqual(relation.relation_type, FORM.EXACT_INTERVENTION_FORM)
        self.assertTrue(relation.primary_candidate_eligible)
        self.assertTrue(relation.structural_score_eligible)

    def test_case_and_whitespace_are_writing_not_form(self) -> None:
        relation = FORM.resolve("  INFIGRATINIB  ", "infigratinib")
        self.assertEqual(
            relation.relation_type, FORM.NORMALIZED_EXACT_INTERVENTION_FORM
        )
        self.assertTrue(relation.primary_candidate_eligible)

    def test_active_moiety_against_salt_is_never_exact(self) -> None:
        for query, claim in (
            ("infigratinib", "infigratinib phosphate"),
            ("infigratinib phosphate", "infigratinib"),
            ("alectinib", "alectinib hydrochloride"),
            ("alectinib hydrochloride", "alectinib"),
            ("neratinib", "neratinib maleate"),
        ):
            with self.subTest(query=query, claim=claim):
                relation = FORM.resolve(query, claim)
                self.assertNotIn(relation.relation_type, FORM.EXACT_FORM_RELATIONS)
                self.assertFalse(relation.primary_candidate_eligible)
                self.assertFalse(relation.structural_score_eligible)

    def test_two_different_salts_are_never_exact(self) -> None:
        for query, claim in (
            ("infigratinib phosphate", "infigratinib hydrochloride"),
            ("alectinib hydrochloride", "alectinib sulfate"),
        ):
            with self.subTest(query=query, claim=claim):
                relation = FORM.resolve(query, claim)
                self.assertNotIn(relation.relation_type, FORM.EXACT_FORM_RELATIONS)
                self.assertFalse(relation.primary_candidate_eligible)

    def test_the_verified_salt_is_warning_and_carries_its_source(self) -> None:
        relation = FORM.resolve("infigratinib phosphate", "infigratinib")
        self.assertEqual(relation.relation_type, FORM.VERIFIED_SALT_OF_ACTIVE_MOIETY)
        self.assertEqual(relation.bucket, FORM.WARNING)
        self.assertTrue(relation.warning_eligible)
        self.assertTrue(relation.authoritative_source)
        self.assertEqual(relation.stable_identifier, "ncit:C175088")
        self.assertIn(
            FORM.EVIDENCE_USES_DIFFERENT_VERIFIED_FORMULATION, relation.warning_codes
        )

    def test_an_unknown_salt_is_unresolved_not_rejected_and_not_fused(self) -> None:
        relation = FORM.resolve("infigratinib hydrochloride", "infigratinib")
        self.assertEqual(relation.relation_type, FORM.UNRESOLVED_FORMULATION_RELATION)
        self.assertEqual(relation.bucket, FORM.AUDIT)
        self.assertEqual(relation.relation_status, FORM.STATUS_UNRESOLVED)
        self.assertIn(
            FORM.INTERVENTION_FORMULATION_RELATION_UNRESOLVED, relation.reason_codes
        )

    def test_hydrochloride_and_phosphate_are_not_fused(self) -> None:
        """Il caso che ha generato il finding, in tutte e tre le direzioni."""
        self.assertNotEqual(
            FORM.resolve("infigratinib hydrochloride", "infigratinib").relation_type,
            FORM.resolve("infigratinib phosphate", "infigratinib").relation_type,
        )
        for query, claim in (
            ("infigratinib hydrochloride", "infigratinib phosphate"),
            ("infigratinib phosphate", "infigratinib hydrochloride"),
        ):
            with self.subTest(query=query, claim=claim):
                self.assertNotIn(
                    FORM.resolve(query, claim).relation_type, FORM.EXACT_FORM_RELATIONS
                )

    def test_no_suffix_normalization_produces_identity(self) -> None:
        definitions = FORM.relation_definitions()
        self.assertFalse(definitions["suffix_stripping_can_produce_exact"])
        self.assertFalse(definitions["substring_can_produce_exact"])
        self.assertFalse(definitions["edit_distance_can_produce_exact"])
        self.assertTrue(definitions["form_tokens_are_candidates_not_proof"])

    def test_a_form_token_is_a_whole_word_not_a_substring(self) -> None:
        relation = FORM.resolve("phosphatermine", "infigratinib")
        self.assertEqual(relation.relation_type, FORM.INCOMPATIBLE_ACTIVE_MOIETY)
        self.assertEqual(FORM.form_tokens("phosphatermine"), ())

    def test_every_registry_entry_carries_an_authoritative_source(self) -> None:
        for entry in FORM.VERIFIED_FORMULATION_REGISTRY:
            with self.subTest(form=entry.form_label):
                self.assertTrue(entry.authoritative_source)
                self.assertTrue(entry.evidence_id)

    def test_a_registry_entry_without_a_source_cannot_be_created(self) -> None:
        with self.assertRaises(FORM.FormulationContractError):
            FORM.FormulationEntry(
                canonical_active_moiety="alectinib",
                form_label="alectinib hydrochloride",
                form_kind=FORM.FORM_SALT,
                relation_type=FORM.VERIFIED_SALT_OF_ACTIVE_MOIETY,
                authoritative_source="",
                evidence_id="",
                stable_identifier="",
                moiety_identifier="",
                limitation="",
            )

    def test_an_unrelated_drug_stays_rejected(self) -> None:
        relation = FORM.resolve("erlotinib", "infigratinib")
        self.assertEqual(relation.relation_type, FORM.INCOMPATIBLE_ACTIVE_MOIETY)
        self.assertTrue(relation.rejected_by_native_constraints)

    def test_every_simulation_case_matches_its_expected_relation(self) -> None:
        for row in FIXES.formulation_simulation():
            with self.subTest(case=row["case_id"]):
                self.assertTrue(row["relation_as_expected"])


class FormulationGateTests(unittest.TestCase):
    """Il gate di forma non e' aggirabile."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.records, _ = build_repository()
        cls.rows = _artifact("integrated_gate_regression.jsonl")

    def _claim(self, intervention: str) -> tuple[Any, dict]:
        record = next(
            item
            for item in self.records
            if item["claim_type"] == "atomic_intervention_claim"
            and item["canonical_intervention"] == intervention
        )
        return (
            AtomicInterventionClaim(
                claim_id=record["claim_id"],
                parent_id=record["parent_id"],
                graph_evidence_id=record["graph_evidence_id"],
                intervention=record["intervention"],
                biomarker=record["biomarker"],
                disease_scope=record["disease_scope"],
                direction=record["direction"],
                polarity=record["polarity"],
                source_unit_ids=tuple(record.get("source_unit_ids") or ()),
                evidence_setting=record.get("evidence_setting"),
            ),
            record,
        )

    def test_every_regression_case_behaves_as_expected(self) -> None:
        for row in self.rows:
            with self.subTest(case=row["case_id"], mode=row["policy_mode"]):
                self.assertTrue(row["primary_as_expected"])

    def test_no_regression_case_bypasses_the_gate(self) -> None:
        for row in self.rows:
            with self.subTest(case=row["case_id"], mode=row["policy_mode"]):
                self.assertIsNone(row["gate_bypass"])

    def test_primary_requires_an_exact_form_relation(self) -> None:
        for row in self.rows:
            if not row["primary_candidate_eligible"]:
                continue
            with self.subTest(case=row["case_id"], mode=row["policy_mode"]):
                self.assertIn(row["formulation_relation"], FORM.EXACT_FORM_RELATIONS)

    def test_an_arbitrarily_high_score_cannot_reopen_a_form_mismatch(self) -> None:
        claim, record = self._claim("infigratinib")
        query = {
            "query_id": "score-probe",
            "query_domain": "therapeutic_evidence_query",
            "biomarker": record["biomarker"],
            "disease": record["disease_scope"],
            "direction": record["direction"],
            "polarity": record["polarity"],
            "interventions": ["infigratinib phosphate"],
        }
        result = GATE.evaluate(query, claim)
        GATE.check_no_score_survives_a_blocking_gate(result, 10**12)
        self.assertFalse(result.primary_candidate_eligible)
        self.assertFalse(result.structural_score_eligible)
        self.assertIn("formulation", result.blocking_gates)

    def test_a_form_mismatch_is_not_compensated_by_exact_disease_and_biomarker(
        self,
    ) -> None:
        """Tutti gli altri assi exact, e la forma decide comunque."""
        claim, record = self._claim("infigratinib")
        query = {
            "query_id": "compensation-probe",
            "query_domain": "therapeutic_evidence_query",
            "biomarker": record["biomarker"],
            "disease": record["disease_scope"],
            "direction": record["direction"],
            "polarity": record["polarity"],
            "interventions": ["infigratinib hydrochloride"],
        }
        result = GATE.evaluate(query, claim)
        self.assertEqual(result.final_bucket, GATE.AUDIT_BUCKET)
        self.assertFalse(result.primary_candidate_eligible)
        self.assertFalse(result.qualified_score_eligible)

    def test_the_gate_declares_what_cannot_compensate_a_form_mismatch(self) -> None:
        contract = GATE.bucket_precedence_contract()
        self.assertTrue(contract["primary_requires_exact_form_relation"])
        self.assertEqual(
            contract["buckets_most_to_least_restrictive"],
            list(GATE.BUCKET_PRECEDENCE),
        )
        self.assertTrue(contract["formulation_mismatch_is_not_compensable_by"])

    def test_the_single_exception_is_declared_and_cannot_reach_primary(self) -> None:
        contract = GATE.bucket_precedence_contract()
        self.assertEqual(len(contract["explicit_exceptions"]), 1)
        self.assertTrue(contract["explicit_exceptions"][0]["cannot_reach_primary"])

    def test_the_gate_order_places_formulation_after_intervention_identity(self) -> None:
        names = list(GATE.GATE_NAMES)
        self.assertLess(
            names.index("intervention_identity"), names.index("formulation")
        )
        self.assertLess(names.index("formulation"), names.index("direction"))

    def test_an_exact_form_query_still_reaches_primary(self) -> None:
        """Controllo negativo: senza, "niente e' primario" sarebbe banalmente vero."""
        claim, record = self._claim("alectinib hydrochloride")
        query = {
            "query_id": "negative-control",
            "query_domain": "therapeutic_evidence_query",
            "biomarker": record["biomarker"],
            "disease": record["disease_scope"],
            "direction": record["direction"],
            "polarity": record["polarity"],
            "interventions": ["alectinib hydrochloride"],
        }
        result = GATE.evaluate(query, claim)
        self.assertTrue(result.primary_candidate_eligible)
        self.assertTrue(result.structural_score_eligible)


class TerminologyInvarianceTests(unittest.TestCase):
    """Le decisioni della terminology closure non sono cambiate."""

    def test_the_bgj398_mapping_is_unchanged(self) -> None:
        from backend.pipeline.evidence.shadow.terminology_v13 import (
            VERIFIED_CANONICAL_LABEL,
            VERIFIED_DECISION_ID,
            VERIFIED_SOURCE_LITERAL,
        )

        self.assertEqual(VERIFIED_DECISION_ID, "TP-BGJ398-INFIGRATINIB")
        self.assertEqual(VERIFIED_SOURCE_LITERAL, "BGJ398")
        self.assertEqual(VERIFIED_CANONICAL_LABEL, "infigratinib")

    def test_auy922_remains_unresolved(self) -> None:
        registry = json.loads(
            (SCOPE.SHADOW_V13 / "terminology_registry_v1_3.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(registry["queue_fully_resolved"])
        unresolved = registry["unresolved_mappings"]
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["source_literal_term"], "AUY922")
        self.assertFalse(unresolved[0]["is_verified"])

    def test_the_source_literal_survives_in_the_1_4_records(self) -> None:
        records, _ = build_repository()
        aggregates = [
            record
            for record in records
            if record["claim_type"] == "aggregate_intervention_claim"
            and "BGJ398" in (record.get("aggregate_members_literal") or ())
        ]
        self.assertEqual(len(aggregates), 2)

    def test_the_formulation_contract_does_not_touch_development_codes(self) -> None:
        """Un codice di sviluppo non e' una forma, e il contratto non lo tratta come tale."""
        relation = FORM.resolve("BGJ398", "infigratinib")
        self.assertEqual(relation.relation_type, FORM.INCOMPATIBLE_ACTIVE_MOIETY)
        self.assertEqual(FORM.form_tokens("BGJ398"), ())


class PolicyModeTests(unittest.TestCase):
    """La modalita' sconosciuta e' rifiutata, e la regola e' dichiarata."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = _artifact("policy_mode_contract.json")

    def test_the_contract_declares_the_default(self) -> None:
        self.assertEqual(self.contract["default_policy_mode"], "strict_verified")
        self.assertEqual(
            self.contract["allowed_policy_modes"],
            ["strict_verified", "ontology_aware_warning", "audit_all"],
        )

    def test_the_contract_declares_the_rejection(self) -> None:
        self.assertEqual(self.contract["unknown_policy_mode_behavior"], "reject")
        self.assertTrue(self.contract["measured_behaviour_rejects_unknown_mode"])

    def test_the_contract_forbids_every_silent_fallback(self) -> None:
        self.assertFalse(self.contract["silent_fallback_permitted"])
        self.assertFalse(self.contract["fallback_to_broader_mode"])
        self.assertFalse(self.contract["fallback_to_ontology_aware_warning"])
        self.assertFalse(self.contract["fallback_to_audit_all"])

    def test_an_unknown_mode_raises(self) -> None:
        with self.assertRaises(DISEASE.DiseaseGateError):
            DISEASE.policy_mode({"disease_policy_mode": "definitely_not_a_mode"})

    def test_an_unspecified_mode_resolves_to_strict_verified(self) -> None:
        self.assertEqual(DISEASE.policy_mode({}), "strict_verified")


class LinkPlanTests(unittest.TestCase):
    """Le 37 azioni su un solo schema, senza cambiare significato."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.original = load_v13()["link_plan"]
        cls.normalized = _artifact("qualification_link_plan_v1_4.jsonl")
        cls.compat = _artifact("backward_compatibility_addendum.json")["link_plan"]

    def test_the_action_count_is_unchanged(self) -> None:
        self.assertEqual(len(self.normalized), len(self.original))
        self.assertEqual(len(self.normalized), 37)

    def test_every_row_has_the_same_fields(self) -> None:
        for row in self.normalized:
            with self.subTest(plan=row["plan_id"]):
                for field in FIXES.LINK_PLAN_FIELDS:
                    self.assertIn(field, row)

    def test_no_action_is_executed(self) -> None:
        for row in self.normalized:
            with self.subTest(plan=row["plan_id"]):
                self.assertFalse(row["executed"])

    def test_the_plan_ids_are_unchanged(self) -> None:
        self.assertTrue(self.compat["plan_ids_unchanged"])
        self.assertFalse(self.compat["meaning_changed"])

    def test_no_source_unit_is_lost(self) -> None:
        before = {
            str(action["plan_id"]): sorted(
                {str(item) for item in (action.get("source_unit_ids") or ())}
                | (
                    {str(action["source_unit_id"])}
                    if action.get("source_unit_id")
                    else set()
                )
            )
            for action in self.original
        }
        for row in self.normalized:
            with self.subTest(plan=row["plan_id"]):
                self.assertEqual(row["source_unit_id"], before[row["plan_id"]])

    def test_the_legacy_field_map_is_recorded(self) -> None:
        self.assertTrue(self.compat["field_map"])
        self.assertTrue(self.compat["legacy_fields_retained_in_original_artifact"])


class RepositoryTests(unittest.TestCase):
    """Conteggi invariati, identita' stabili, versioni conservate."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = _artifact("repository_v1_4_manifest.json")
        cls.ids = _artifact("claim_id_impact.jsonl")

    def test_the_counts_are_unchanged(self) -> None:
        self.assertTrue(self.manifest["counts_match_expected"])
        for key, expected in EXPECTED_COUNTS.items():
            with self.subTest(count=key):
                self.assertEqual(self.manifest["counts"][key], expected)

    def test_no_claim_id_changed(self) -> None:
        self.assertEqual(self.manifest["invariants"]["claim_ids_changed"], 0)
        for row in self.ids:
            with self.subTest(claim=row["claim_id_after"]):
                self.assertFalse(row["changed"])
                self.assertEqual(row["claim_id_before"], row["claim_id_after"])
                self.assertTrue(row["identity_fields_unchanged"])
                self.assertFalse(row["lineage_required"])

    def test_every_claim_id_is_covered_by_the_impact_artifact(self) -> None:
        self.assertEqual(len(self.ids), EXPECTED_COUNTS["active_claims_total"])

    def test_there_is_no_collision(self) -> None:
        ids = [row["claim_id_after"] for row in self.ids]
        self.assertEqual(len(ids), len(set(ids)))

    def test_the_repository_stays_shadow(self) -> None:
        self.assertEqual(self.manifest["migration_status"], "shadow_not_promoted")
        self.assertFalse(self.manifest["invariants"]["repository_promoted"])
        self.assertFalse(self.manifest["invariants"]["plans_executed"])

    def test_the_previous_versions_are_preserved(self) -> None:
        lineage = _artifact("repository_version_lineage.json")
        versions = [row["repository_version"] for row in lineage["versions"]]
        self.assertEqual(
            versions,
            [
                "qualified_claim_repository/1.0",
                "qualified_claim_repository/1.1",
                "qualified_claim_repository/1.2",
                "qualified_claim_repository/1.3",
                "qualified_claim_repository/1.4",
            ],
        )

    def test_the_new_versions_are_declared(self) -> None:
        self.assertEqual(self.manifest["model_schema"], "qualified_claim_model/1.2")
        self.assertEqual(
            self.manifest["repository_schema"], "qualified_claim_repository/1.4"
        )
        self.assertEqual(
            self.manifest["integrated_structural_gate"],
            "qualified_claim_structural_gate/1.1",
        )
        self.assertEqual(
            self.manifest["output_contract"], "qualified_claim_retrieval_result/1.3"
        )
        self.assertEqual(
            self.manifest["formulation"]["contract"],
            "intervention_formulation_contract/1.0",
        )


class FormAuditTests(unittest.TestCase):
    """L'audit delle forme copre tutto il repository, non solo infigratinib."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.records, _ = build_repository()
        cls.audit = FA.audit(cls.records)
        cls.rows = _artifact("formulation_claim_audit.jsonl")

    def test_thirteen_claims_carry_a_salt_form(self) -> None:
        self.assertEqual(self.audit["salt_form_claims"], 13)

    def test_one_salt_form_was_invisible_to_the_suffix_table(self) -> None:
        self.assertEqual(
            self.audit["forms_invisible_to_current_suffix_table"], ["neratinib maleate"]
        )

    def test_no_claim_identity_changed_because_of_the_form_audit(self) -> None:
        self.assertEqual(self.audit["claim_identities_changed"], 0)
        for row in self.rows:
            with self.subTest(claim=row["claim_id"]):
                self.assertEqual(row["claim_id_impact"], "unchanged")

    def test_the_reviewed_pair_is_not_decided_by_presence_in_the_graph(self) -> None:
        for pair in self.audit["reviewed_pairs"]:
            with self.subTest(form=pair["form_label"]):
                self.assertFalse(pair["decided_by_presence_in_graph"])
                self.assertFalse(pair["fused_with_moiety"])

    def test_the_two_infigratinib_forms_get_different_outcomes_for_a_reason(
        self,
    ) -> None:
        pairs = {pair["form_label"]: pair for pair in self.audit["reviewed_pairs"]}
        phosphate = pairs["infigratinib phosphate"]
        hydrochloride = pairs["infigratinib hydrochloride"]
        self.assertTrue(phosphate["authoritative_source"])
        self.assertIsNone(hydrochloride["authoritative_source"])
        self.assertNotEqual(phosphate["new_decision"], hydrochloride["new_decision"])

    def test_the_registry_holds_only_sourced_relations(self) -> None:
        self.assertEqual(
            self.audit["verified_form_relations"],
            len(FORM.VERIFIED_FORMULATION_REGISTRY),
        )


class ArtifactTests(unittest.TestCase):
    """Gli artefatti esistono, sono deterministici e non contengono altro."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = build()

    def test_every_required_artifact_is_produced(self) -> None:
        for name in REQUIRED_ARTIFACTS:
            with self.subTest(artifact=name):
                self.assertIn(name, self.artifacts)
                self.assertTrue((OUTPUT / name).exists())

    def test_the_output_contains_nothing_else(self) -> None:
        written = {path.name for path in OUTPUT.iterdir() if path.is_file()}
        self.assertEqual(written, set(self.artifacts))

    # `test_rebuilding_reproduces_the_committed_artifacts` sta in
    # `backend/tests_external/gold/`: rigenerare richiede il bundle gold, che
    # questa suite non apre.

    def test_double_generation_is_identical(self) -> None:
        self.assertEqual(build_data_artifacts(), build_data_artifacts())

    def test_the_manifest_hashes_match_the_artifacts(self) -> None:
        manifest = json.loads(self.artifacts["repository_v1_4_manifest.json"])
        for name, digest in manifest["artifact_sha256"].items():
            with self.subTest(artifact=name):
                self.assertEqual(SCOPE.sha256_text(self.artifacts[name]), digest)


class ReadinessTests(unittest.TestCase):
    """La readiness deriva dai finding, e non li anticipa."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.readiness = _artifact("post_fix_readiness.json")
        cls.findings = _artifact("post_fix_findings.jsonl")

    def test_no_critical_and_no_major_finding_remains(self) -> None:
        self.assertEqual(self.readiness["critical_findings"], 0)
        self.assertEqual(self.readiness["major_findings"], 0)

    def test_the_two_major_findings_are_resolved(self) -> None:
        by_id = {row["finding_id"]: row for row in self.findings}
        for finding_id in (
            "PROPAGATION_POLICY_MISSING_ON_NON_ATOMIC_CLAIMS",
            "SALT_FORM_TABLE_CONTRADICTS_FORMULATION_CAVEAT",
        ):
            with self.subTest(finding=finding_id):
                self.assertEqual(by_id[finding_id]["severity_before"], "major")
                self.assertEqual(by_id[finding_id]["outcome"], "resolved")
                self.assertEqual(by_id[finding_id]["severity_now"], "none")

    def test_the_minor_findings_are_resolved(self) -> None:
        by_id = {row["finding_id"]: row for row in self.findings}
        for finding_id in (
            "UNKNOWN_MODE_REJECTION_NOT_DECLARED",
            "LINK_PLAN_SCHEMA_HETEROGENEOUS",
            "NO_DISTINCT_FORMULATION_OUTCOME",
        ):
            with self.subTest(finding=finding_id):
                self.assertEqual(by_id[finding_id]["outcome"], "resolved")

    def test_the_retrieval_impact_is_recorded_and_not_hidden(self) -> None:
        by_id = {row["finding_id"]: row for row in self.findings}
        recorded = by_id["SALT_FORM_CLAIMS_LEAVE_PRIMARY_BUCKET"]
        self.assertEqual(recorded["outcome"], "accepted_and_recorded")
        self.assertEqual(recorded["severity_now"], "informational")

    def test_the_repository_is_ready_as_a_shadow(self) -> None:
        self.assertTrue(self.readiness["shadow_repository_v1_4_ready"])
        self.assertTrue(self.readiness["required_promotion_fixes_resolved"])

    def test_the_retriever_migration_stays_closed(self) -> None:
        self.assertFalse(self.readiness["operational_retriever_migration_ready"])

    def test_the_full_exploratory_rerun_stays_closed(self) -> None:
        self.assertFalse(self.readiness["full_exploratory_rerun_ready"])


class IntegrityTests(unittest.TestCase):
    """La fase non ha toccato nulla di cio' che dichiara di non toccare."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = _artifact("repository_v1_4_manifest.json")

    def test_the_frozen_artifacts_are_unchanged(self) -> None:
        integrity = self.manifest["integrity"]
        self.assertTrue(integrity["all_frozen_artifacts_unchanged"])
        self.assertEqual(integrity["changed"], [])

    def test_the_shadow_repositories_are_unchanged(self) -> None:
        observed = SCOPE.frozen_hashes()
        for role, digest in self.manifest["integrity"]["frozen_tree_sha256"].items():
            path = (
                SCOPE.V3 / "pre_promotion_audit_1_3"
                if role == "pre-promotion audit 1.3"
                else REPO_ROOT / observed["trees"][role]["path"]
            )
            with self.subTest(tree=role):
                TREE_ERRATUM.assert_frozen_tree(role, path, digest)

    def test_the_operational_pipeline_is_unchanged(self) -> None:
        observed = SCOPE.frozen_hashes()
        for role, digest in self.manifest["integrity"]["frozen_sha256"].items():
            with self.subTest(role=role):
                self.assertEqual(observed["files"][role]["sha256"], digest)

    def test_the_operational_query_returns_the_same_bytes(self) -> None:
        query = self.manifest["integrity"]["operational_query"]
        self.assertTrue(query["parity"])
        self.assertEqual(query["sha256"], query["baseline_sha256"])

    def test_no_gold_record_was_read(self) -> None:
        gold = self.manifest["integrity"]["gold"]
        self.assertEqual(gold["gold_records_read"], 0)
        self.assertFalse(gold["used_for_any_decision"])
        self.assertFalse(self.manifest["gold_used"])

    def test_the_declared_invariants_hold(self) -> None:
        invariants = self.manifest["invariants"]
        self.assertEqual(invariants["claim_ids_changed"], 0)
        self.assertEqual(invariants["gate_bypasses"], 0)
        self.assertEqual(invariants["gold_artifacts_read"], 0)
        self.assertEqual(invariants["member_propagation_allowed"], 0)
        self.assertFalse(invariants["operational_artifacts_modified"])
        self.assertFalse(invariants["shadow_1_3_modified"])


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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

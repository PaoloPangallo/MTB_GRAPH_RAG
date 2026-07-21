"""Test dell'audit del gold pilota MTB-Evidence.

Nessun test qui richiede Neo4j: il grafo e' sostituito da un client scriptato, come
gia' si fa altrove nella suite con i planner e gli LLM finti. Il test di integrazione
che tocca davvero il database vive in `test_pilot_gold_audit_integration.py` ed e'
attivo solo con `RUN_NEO4J_INTEGRATION=1`.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase

from benchmarks.mtb_evidence.pilot.audit_lib import report, second_review
from benchmarks.mtb_evidence.pilot.audit_lib.aliases import (
    AliasValidationError,
    alias_manifest,
    build_alias_table,
)
from benchmarks.mtb_evidence.pilot.audit_lib.classify import (
    ADJUVANT_RESECTED,
    FIRST_LINE_ADVANCED,
    INSUFFICIENT_CONTEXT,
    NOT_MODELLED_QUALIFIERS,
    POST_PROGRESSION_T790M,
    TEXT_HEURISTIC,
    alteration_types,
    classify_setting,
    classify_variant_form,
    mentions,
    qualifier_status,
)
from benchmarks.mtb_evidence.pilot.audit_lib.compare import (
    FULL,
    PARTIAL,
    UNMATCHED,
    compare_case,
    graph_claim_from_record,
    match_claim,
)
from benchmarks.mtb_evidence.pilot.audit_lib.disease import (
    DIFFERENT_SPECIFICITY,
    IDENTICAL,
    SAME_ENTITY,
    disease_relation,
    diseases_match,
    split_disease,
)
from benchmarks.mtb_evidence.pilot.audit_lib.gold import (
    GoldParseError,
    load_gold,
    parse_gold_lines,
)
from benchmarks.mtb_evidence.pilot.audit_lib.graph_client import (
    GraphUnavailable,
    Neo4jGraphClient,
    _is_connectivity_error,
)
from benchmarks.mtb_evidence.pilot.audit_lib.normalize import (
    norm_drug,
    norm_nct,
    norm_nct_set,
    norm_pmid,
    norm_pmid_set,
    norm_text,
)
from benchmarks.mtb_evidence.pilot.audit_lib.queries import n1_rmi2
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (
    REDACTED,
    canonical_json,
    fingerprint,
    sanitize_uri,
    scrub,
    write_json,
    write_jsonl,
    write_text,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PILOT_ROOT = PROJECT_ROOT / "benchmarks" / "mtb_evidence" / "pilot"
GOLD_PATH = PILOT_ROOT / "input" / "mtb_evidence_gold_pilot_v1.jsonl"


class _ScriptedGraphClient:
    """Client di grafo finto: risponde in base a un frammento del testo Cypher."""

    def __init__(self, responses=None, default=None):
        self._responses = list(responses or [])
        self._default = list(default or [])
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher, params=None):
        self.calls.append((cypher, dict(params or {})))
        for needle, records in self._responses:
            if needle in cypher:
                return [dict(record) for record in records]
        return [dict(record) for record in self._default]


def _gold_claim(**overrides):
    from benchmarks.mtb_evidence.pilot.audit_lib.gold import _parse_claim

    payload = {
        "claim_id": "T-C1",
        "case_id": "T",
        "subject": "EGFR L858R",
        "relation": "predicts benefit from first-line",
        "object": "osimertinib",
        "disease": "advanced NSCLC",
        "direction": "supports",
        "mandatory_qualifiers": "previously untreated",
        "pmid": "29151359",
        "nct_id": "NCT02296125",
    }
    payload.update(overrides)
    return _parse_claim(payload, "T")


def _graph_record(**overrides):
    payload = {
        "record_id": "evidence:1",
        "molecular_profile": "EGFR L858R",
        "significance": "Sensitivity/Response",
        "evidence_direction": "Supports",
        "disease": "Lung Non-small Cell Carcinoma",
        "citation_id": ["29151359"],
        "evidence_statement": "Previously untreated advanced NSCLC treated first-line.",
        "drug": "OSIMERTINIB",
    }
    payload.update(overrides)
    return payload


class GoldParsingTest(TestCase):
    def test_parses_the_four_pilot_cases(self):
        cases = load_gold(GOLD_PATH)
        self.assertEqual(len(cases), 4)
        self.assertEqual(
            [case.case_id for case in cases],
            [
                "PILOT-K1-FGFR2-iCCA",
                "PILOT-A2-ALK-G1202R",
                "PILOT-C1-EGFR-L858R-CONTEXT",
                "PILOT-N1-RMI2-SNAPSHOT",
            ],
        )

    def test_claims_and_sources_are_structured(self):
        cases = {case.case_id: case for case in load_gold(GOLD_PATH)}
        k1 = cases["PILOT-K1-FGFR2-iCCA"]
        self.assertEqual(len(k1.claims), 2)
        self.assertEqual(len(k1.sources), 4)
        self.assertEqual(k1.expected_therapies, ("pemigatinib", "futibatinib"))
        self.assertFalse(k1.expected_abstention)
        self.assertTrue(cases["PILOT-N1-RMI2-SNAPSHOT"].expected_abstention)

    def test_blank_lines_are_ignored(self):
        line = json.dumps({"case_id": "X", "claims": [], "sources": []})
        cases = parse_gold_lines(["", line, "   ", ""])
        self.assertEqual(len(cases), 1)

    def test_malformed_json_reports_line_number(self):
        with self.assertRaises(GoldParseError) as ctx:
            parse_gold_lines(['{"case_id": "A"}', "{not json"])
        self.assertIn("riga 2", str(ctx.exception))

    def test_duplicate_case_id_is_rejected(self):
        line = json.dumps({"case_id": "DUP"})
        with self.assertRaises(GoldParseError):
            parse_gold_lines([line, line])

    def test_gold_input_is_never_rewritten(self):
        """L'audit e' di sola lettura: il file di input resta identico al bundle."""
        bundle = PROJECT_ROOT.parent / "MTB_Evidence_gold_pilot_v1_bundle"
        original = bundle / "mtb_evidence_gold_pilot_v1.jsonl"
        if not original.is_file():
            self.skipTest("bundle originale non disponibile")
        self.assertEqual(original.read_bytes(), GOLD_PATH.read_bytes())


class PmidNormalizationTest(TestCase):
    def test_strips_prefix_and_yields_both_forms(self):
        result = norm_pmid("PMID: 29151359 ")
        self.assertTrue(result.valid)
        self.assertEqual(result.text, "29151359")
        self.assertEqual(result.numeric, 29151359)

    def test_integer_input_matches_string_input(self):
        """Publication.pmid e' INTEGER, Evidence.citation_id e' stringa: stessa chiave."""
        self.assertEqual(norm_pmid(29151359).text, norm_pmid("29151359").text)
        self.assertEqual(norm_pmid(29151359).numeric, norm_pmid("29151359").numeric)

    def test_leading_zeros_are_normalized(self):
        self.assertEqual(norm_pmid("0029151359").text, "29151359")

    def test_non_numeric_is_flagged_not_silently_dropped(self):
        result = norm_pmid("PMID:abc")
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "not_numeric")

    def test_set_normalization_deduplicates_and_sorts(self):
        self.assertEqual(
            norm_pmid_set(["PMID:2", 2, "1", "bad"]), ("1", "2")
        )


class NctNormalizationTest(TestCase):
    def test_uppercase_and_prefix_removal(self):
        self.assertEqual(norm_nct("nct: nct02296125").text, "NCT02296125")

    def test_bare_digits_get_prefix(self):
        self.assertEqual(norm_nct("02296125").text, "NCT02296125")

    def test_malformed_is_flagged(self):
        result = norm_nct("NCT123")
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "malformed")

    def test_set_normalization(self):
        self.assertEqual(norm_nct_set(["nct02296125", "NCT02296125"]), ("NCT02296125",))


class DrugAliasTest(TestCase):
    def setUp(self):
        self.table = build_alias_table()

    def test_development_codes_resolve_to_inn(self):
        self.assertEqual(norm_drug("TAS-120", self.table), "futibatinib")
        self.assertEqual(norm_drug("AZD9291", self.table), "osimertinib")
        self.assertEqual(norm_drug("PF-06463922", self.table), "lorlatinib")
        self.assertEqual(norm_drug("INCB054828", self.table), "pemigatinib")

    def test_case_and_spacing_are_normalized(self):
        self.assertEqual(norm_drug("  OSIMERTINIB  ", self.table), "osimertinib")

    def test_unknown_drug_passes_through_unchanged(self):
        self.assertEqual(norm_drug("Infigratinib", self.table), "infigratinib")

    def test_disease_terms_are_rejected_as_aliases(self):
        with self.assertRaises(AliasValidationError):
            build_alias_table({"intrahepatic cholangiocarcinoma": "cholangiocarcinoma"})

    def test_alteration_terms_are_rejected_as_aliases(self):
        with self.assertRaises(AliasValidationError):
            build_alias_table({"fgfr2 fusion": "fgfr2 mutation"})

    def test_compound_aliases_are_rejected(self):
        with self.assertRaises(AliasValidationError):
            build_alias_table({"g1202r/l1196m": "g1202r"})

    def test_manifest_lists_the_invariants(self):
        manifest = alias_manifest(self.table)
        self.assertEqual(manifest["alias_count"], len(self.table))
        self.assertTrue(manifest["invariants"])
        self.assertIn("malattie_distinte", manifest["rejected_by_construction"])


class DiseaseRelationTest(TestCase):
    def test_identical_after_qualifier_stripping(self):
        self.assertEqual(disease_relation("advanced NSCLC", "NSCLC"), IDENTICAL)

    def test_vocabulary_variants_are_the_same_entity(self):
        self.assertEqual(
            disease_relation("NSCLC", "Lung Non-small Cell Carcinoma"), SAME_ENTITY
        )
        self.assertTrue(diseases_match("advanced ALK-positive NSCLC", "Non-Small Cell Lung Cancer"))

    def test_subtype_does_not_match_parent(self):
        """Il caso K1 richiede che intraepatico non equivalga a un CCA qualunque."""
        self.assertEqual(
            disease_relation("intrahepatic cholangiocarcinoma", "cholangiocarcinoma"),
            DIFFERENT_SPECIFICITY,
        )
        self.assertFalse(
            diseases_match("intrahepatic cholangiocarcinoma", "cholangiocarcinoma")
        )
        self.assertFalse(
            diseases_match(
                "intrahepatic cholangiocarcinoma", "Cholangiolocellular Carcinoma"
            )
        )

    def test_unrelated_diseases_stay_distinct(self):
        self.assertFalse(diseases_match("NSCLC", "cholangiocarcinoma"))

    def test_qualifiers_are_extracted_not_discarded(self):
        term = split_disease("completely resected stage IB-IIIA NSCLC")
        self.assertEqual(term.core, "nsclc")
        self.assertTrue(term.qualifiers)


class VariantFormTest(TestCase):
    def test_single_mutation_is_not_compound(self):
        self.assertFalse(classify_variant_form("ALK G1202R").is_compound)

    def test_compound_mutation_is_detected(self):
        form = classify_variant_form("EML4::ALK Fusion AND ALK G1202R AND ALK L1196M")
        self.assertTrue(form.is_compound)
        self.assertIn("G1202R", form.variants)
        self.assertIn("L1196M", form.variants)

    def test_slash_notation_is_compound(self):
        self.assertTrue(classify_variant_form("G1202R/L1196M").is_compound)

    def test_variant_plus_fusion_is_not_a_compound_mutation(self):
        """G1202R su una fusione ALK resta una mutazione singola."""
        self.assertFalse(classify_variant_form("ALK G1202R AND v::ALK Fusion").is_compound)

    def test_disjunctive_profile_is_not_compound(self):
        self.assertFalse(
            classify_variant_form("EGFR L858R OR EGFR Exon 19 Deletion").is_compound
        )

    def test_t790m_compound_is_detected(self):
        self.assertTrue(classify_variant_form("EGFR L858R AND EGFR T790M").is_compound)


class AlterationTypeTest(TestCase):
    def test_fusion_and_mutation_stay_distinct(self):
        self.assertEqual(alteration_types("FGFR2::BICC1 Fusion"), frozenset({"fusion"}))
        self.assertNotIn("fusion", alteration_types("FGFR2 Mutation"))

    def test_rearrangement_counts_as_fusion(self):
        self.assertIn("fusion", alteration_types("FGFR2 rearrangement"))


class SettingClassificationTest(TestCase):
    def test_first_line_advanced(self):
        result = classify_setting(
            "Previously untreated patients with advanced EGFR-mutated NSCLC."
        )
        self.assertEqual(result.label, FIRST_LINE_ADVANCED)
        self.assertEqual(result.classification_basis, TEXT_HEURISTIC)
        self.assertTrue(result.matched_spans)

    def test_adjuvant_wins_over_first_line_markers(self):
        result = classify_setting(
            "Completely resected stage IB-IIIA NSCLC, adjuvant osimertinib in "
            "previously untreated patients."
        )
        self.assertEqual(result.label, ADJUVANT_RESECTED)

    def test_t790m_post_progression(self):
        result = classify_setting(
            "T790M-positive advanced NSCLC after progression on a prior EGFR-TKI."
        )
        self.assertEqual(result.label, POST_PROGRESSION_T790M)

    def test_no_markers_is_insufficient_context(self):
        result = classify_setting("EGFR L858R is associated with response.")
        self.assertEqual(result.label, INSUFFICIENT_CONTEXT)
        self.assertEqual(result.matched_spans, ())

    def test_classification_is_always_marked_heuristic(self):
        for text in ("first-line advanced", "adjuvant", "", "T790M"):
            self.assertEqual(classify_setting(text).classification_basis, TEXT_HEURISTIC)

    def test_t790m_and_l858r_are_distinguished(self):
        statement = "EGFR T790M confers benefit after progression."
        self.assertTrue(mentions("T790M", statement))
        self.assertFalse(mentions("L858R", statement))


class QualifierStatusTest(TestCase):
    def test_unmodelled_qualifiers_are_labelled_as_such(self):
        for name in NOT_MODELLED_QUALIFIERS:
            self.assertEqual(qualifier_status(name, True, True), "not_modelled_by_schema")

    def test_absent_differs_from_conflicting(self):
        self.assertEqual(qualifier_status("disease", False, None), "absent_in_record")
        self.assertEqual(qualifier_status("disease", True, False), "present_and_conflicts")
        self.assertEqual(qualifier_status("disease", True, True), "present_and_agrees")


class ClaimMatchingTest(TestCase):
    def setUp(self):
        self.table = build_alias_table()

    def _claims(self, *records):
        return [
            graph_claim_from_record(record, alias_table=self.table) for record in records
        ]

    def test_full_match_requires_every_present_dimension(self):
        claim = _gold_claim(mandatory_qualifiers="")
        graph = self._claims(_graph_record())
        result = match_claim(claim, graph, alias_table=self.table)
        self.assertEqual(result.match_level, FULL)
        self.assertEqual(result.conflicting_dimensions, ())

    def test_drug_and_pmid_alone_are_not_enough(self):
        """Farmaco e PMID coincidono ma la malattia no: non e' una corrispondenza piena."""
        claim = _gold_claim(disease="intrahepatic cholangiocarcinoma", mandatory_qualifiers="")
        graph = self._claims(_graph_record(disease="Cholangiocarcinoma"))
        result = match_claim(claim, graph, alias_table=self.table)
        self.assertEqual(result.match_level, PARTIAL)
        self.assertIn("disease", result.conflicting_dimensions)

    def test_opposite_direction_conflicts(self):
        claim = _gold_claim(mandatory_qualifiers="")
        graph = self._claims(_graph_record(evidence_direction="Does Not Support"))
        result = match_claim(claim, graph, alias_table=self.table)
        self.assertEqual(result.match_level, PARTIAL)
        self.assertIn("direction", result.conflicting_dimensions)

    def test_single_versus_compound_conflicts(self):
        claim = _gold_claim(subject="ALK G1202R", object="lorlatinib", pmid="30892989")
        graph = self._claims(
            _graph_record(
                molecular_profile="EML4::ALK Fusion AND ALK G1202R AND ALK L1196M",
                drug="LORLATINIB",
                citation_id=["30892989"],
                disease="Non-Small Cell Lung Cancer",
            )
        )
        result = match_claim(claim, graph, alias_table=self.table)
        self.assertIn("variant_profile", result.conflicting_dimensions)

    def test_fusion_does_not_match_generic_mutation(self):
        claim = _gold_claim(
            subject="FGFR2 fusion/rearrangement", object="pemigatinib", pmid="32203698",
            disease="cholangiocarcinoma",
        )
        graph = self._claims(
            _graph_record(
                molecular_profile="FGFR2 Mutation", drug="PEMIGATINIB",
                citation_id=["32203698"], disease="Cholangiocarcinoma",
            )
        )
        result = match_claim(claim, graph, alias_table=self.table)
        self.assertIn("variant_profile", result.conflicting_dimensions)

    def test_unmatched_reports_near_misses(self):
        claim = _gold_claim(pmid="99999999")
        graph = self._claims(_graph_record())
        result = match_claim(claim, graph, alias_table=self.table)
        self.assertEqual(result.match_level, UNMATCHED)
        self.assertIn("solo farmaco", result.note)

    def test_drug_alias_is_resolved_before_matching(self):
        claim = _gold_claim(object="AZD9291", mandatory_qualifiers="")
        graph = self._claims(_graph_record(drug="Osimertinib"))
        self.assertEqual(
            match_claim(claim, graph, alias_table=self.table).match_level, FULL
        )

    def test_abstention_claim_is_confirmed_by_absence(self):
        claim = _gold_claim(
            claim_id="N1-C0", subject="RMI2 alteration", object="any drug",
            direction="does_not_assert", pmid="", nct_id="",
        )
        result = match_claim(claim, [], alias_table=self.table)
        self.assertEqual(result.match_level, FULL)
        self.assertIn("astensione confermata", result.note)

    def test_abstention_claim_is_contradicted_by_a_path(self):
        claim = _gold_claim(
            claim_id="N1-C0", object="any drug", direction="does_not_assert", pmid="",
        )
        graph = self._claims(_graph_record(drug="SOMETHING"))
        result = match_claim(claim, graph, alias_table=self.table)
        self.assertEqual(result.match_level, UNMATCHED)
        self.assertIn("contraddetta", result.note)


class CompareCaseTest(TestCase):
    def setUp(self):
        self.table = build_alias_table()
        self.cases = {case.case_id: case for case in load_gold(GOLD_PATH)}

    def test_missing_sources_become_freeze_blockers(self):
        case = self.cases["PILOT-C1-EGFR-L858R-CONTEXT"]
        comparison = compare_case(case, [], alias_table=self.table)
        self.assertFalse(comparison["freeze_ready"])
        self.assertFalse(comparison["graph_complete"])
        self.assertTrue(comparison["missing_pmids"])
        self.assertTrue(comparison["freeze_blockers"])

    def test_abstention_case_is_ready_when_graph_is_empty(self):
        case = self.cases["PILOT-N1-RMI2-SNAPSHOT"]
        comparison = compare_case(case, [], alias_table=self.table)
        self.assertTrue(comparison["freeze_ready"])
        self.assertEqual(comparison["freeze_blockers"], [])

    def test_abstention_case_blocks_when_a_therapy_appears(self):
        case = self.cases["PILOT-N1-RMI2-SNAPSHOT"]
        comparison = compare_case(
            case,
            [graph_claim_from_record(_graph_record(drug="OSIMERTINIB"))],
            alias_table=self.table,
            found_therapies={"osimertinib"},
        )
        self.assertFalse(comparison["freeze_ready"])
        self.assertTrue(
            any("astensione" in blocker for blocker in comparison["freeze_blockers"])
        )

    def test_unmatched_claims_do_not_emit_phantom_conflicts(self):
        case = self.cases["PILOT-K1-FGFR2-iCCA"]
        comparison = compare_case(case, [], alias_table=self.table)
        self.assertEqual(comparison["conflicts"], [])

    def test_comparison_exposes_every_required_field(self):
        case = self.cases["PILOT-K1-FGFR2-iCCA"]
        comparison = compare_case(case, [], alias_table=self.table)
        for key in (
            "expected_therapies", "found_therapies", "missing_therapies", "extra_therapies",
            "expected_pmids", "found_pmids", "missing_pmids", "extra_pmids",
            "expected_nct_ids", "found_nct_ids", "missing_nct_ids", "extra_nct_ids",
            "expected_claims", "structurally_matching_claims", "partially_matching_claims",
            "unmatched_claims", "qualifiers_found", "qualifiers_missing", "conflicts",
            "graph_complete", "audit_warnings", "freeze_ready", "freeze_blockers",
        ):
            self.assertIn(key, comparison)


class NegativePathProofTest(TestCase):
    def setUp(self):
        self.table = build_alias_table()
        self.case = {c.case_id: c for c in load_gold(GOLD_PATH)}["PILOT-N1-RMI2-SNAPSHOT"]

    def test_empty_traversal_produces_a_valid_negative(self):
        client = _ScriptedGraphClient(
            responses=[("MATCH (g:Gene {hugo_symbol: $gene}) RETURN g AS gene",
                        [{"gene": {"hugo_symbol": "RMI2", "entrez_id": 116028}}])],
            default=[],
        )
        outcome = n1_rmi2.run(client, self.case, self.table)
        proof = n1_rmi2.build_negative_path_proof(
            outcome, snapshot_fingerprint="deadbeef", timestamp="2026-07-21T00:00:00+00:00"
        )
        self.assertTrue(proof["is_valid_negative"])
        self.assertEqual(proof["therapeutic_path_count"], 0)
        self.assertEqual(proof["snapshot_fingerprint"], "deadbeef")
        self.assertIn("cypher", proof["primary_query"])
        self.assertIn("params", proof["primary_query"])
        self.assertEqual(proof["primary_query"]["params"], {"gene": "RMI2"})

    def test_a_found_path_is_reported_not_hidden(self):
        client = _ScriptedGraphClient(
            responses=[
                (
                    "-[:TARGETS_DRUG]->(d:Drug) RETURN g.hugo_symbol AS gene",
                    [{"gene": "RMI2", "variant": "V1", "molecular_profile": "RMI2 Mutation",
                      "evidence_id": 1, "significance": "Sensitivity/Response",
                      "disease": "X", "citation_id": ["1"], "drug": "SOMEDRUG"}],
                )
            ],
            default=[],
        )
        outcome = n1_rmi2.run(client, self.case, self.table)
        proof = n1_rmi2.build_negative_path_proof(outcome, snapshot_fingerprint="x")
        self.assertFalse(proof["is_valid_negative"])
        self.assertEqual(proof["therapeutic_path_count"], 1)
        self.assertTrue(proof["blockers"])
        self.assertTrue(outcome.blockers)

    def test_case_is_rejected_when_the_premise_fails(self):
        client = _ScriptedGraphClient(
            responses=[
                (
                    "-[:TARGETS_DRUG]->(d:Drug) RETURN g.hugo_symbol AS gene",
                    [{"gene": "RMI2", "drug": "SOMEDRUG", "evidence_id": 1}],
                )
            ],
            default=[],
        )
        outcome = n1_rmi2.run(client, self.case, self.table)
        comparison = compare_case(
            self.case, outcome.graph_claims, alias_table=self.table,
            found_therapies=outcome.found_therapies, extra_blockers=outcome.blockers,
        )
        self.assertEqual(report.decide(self.case, comparison, outcome)["decision"], report.REJECT)


class GraphUnavailableTest(TestCase):
    def test_connectivity_errors_are_recognised(self):
        class ServiceUnavailable(Exception):
            pass

        ServiceUnavailable.__module__ = "neo4j.exceptions"
        self.assertTrue(_is_connectivity_error(ServiceUnavailable("down")))

    def test_query_errors_are_not_swallowed(self):
        class ClientError(Exception):
            pass

        self.assertFalse(_is_connectivity_error(ClientError("bad cypher")))

    def test_failure_message_is_readable_and_credential_free(self):
        os.environ["NEO4J_PASSWORD"] = "supersecret-test-value"
        try:
            class ServiceUnavailable(Exception):
                pass

            ServiceUnavailable.__module__ = "neo4j.exceptions"

            client = Neo4jGraphClient()

            def _boom(cypher, params):
                raise ServiceUnavailable("connection refused")

            client._run_cypher = _boom
            with self.assertRaises(GraphUnavailable) as ctx:
                client.run("RETURN 1", {})
            message = str(ctx.exception)
            self.assertIn("Neo4j non raggiungibile", message)
            self.assertIn("URI", message)
            self.assertNotIn("supersecret-test-value", message)
        finally:
            os.environ.pop("NEO4J_PASSWORD", None)


class SerializationTest(TestCase):
    def test_canonical_json_is_key_order_independent(self):
        self.assertEqual(
            canonical_json({"b": 1, "a": [3, 2]}), canonical_json({"a": [3, 2], "b": 1})
        )

    def test_fingerprint_is_stable_and_sensitive(self):
        stats = {"nodes": {"Gene": 1}, "total": 1}
        self.assertEqual(fingerprint(stats), fingerprint(dict(stats)))
        self.assertNotEqual(fingerprint(stats), fingerprint({"nodes": {"Gene": 2}, "total": 1}))

    def test_repeated_writes_produce_identical_bytes(self):
        payload = {"z": 1, "a": {"k": [1, 2, 3]}}
        rows = [{"b": 2, "a": 1}, {"a": 3}]
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first"
            second = Path(tmp) / "second"
            for target in (first, second):
                write_json(target / "payload.json", payload)
                write_jsonl(target / "rows.jsonl", rows)
                write_text(target / "note.md", "riga\n")
            for name in ("payload.json", "rows.jsonl", "note.md"):
                self.assertEqual(
                    (first / name).read_bytes(), (second / name).read_bytes(), name
                )

    def test_no_carriage_returns_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_text(Path(tmp) / "note.md", "a\nb\n")
            self.assertNotIn(b"\r", path.read_bytes())

    def test_scrub_does_not_mutate_the_original(self):
        original = {"uri": "bolt://user:pw@host:7687", "nested": ["pw"]}
        snapshot = json.loads(json.dumps(original))
        scrub(original, secrets=["pw"])
        self.assertEqual(original, snapshot)


class CredentialLeakTest(TestCase):
    SECRET_PATTERNS = ("pangallo22", "NEO4J_PASSWORD=", "password=", "api_key=")

    def test_uri_userinfo_is_redacted(self):
        self.assertEqual(
            sanitize_uri("bolt://neo4j:secret@localhost:7687"),
            f"bolt://{REDACTED}@localhost:7687",
        )

    def test_environment_secrets_are_removed_from_written_files(self):
        os.environ["NEO4J_PASSWORD"] = "leak-me-if-you-can"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = write_json(
                    Path(tmp) / "out.json",
                    {"note": "password is leak-me-if-you-can", "uri": "bolt://u:p@h:7687"},
                )
                content = path.read_text(encoding="utf-8")
                self.assertNotIn("leak-me-if-you-can", content)
                self.assertIn(REDACTED, content)
        finally:
            os.environ.pop("NEO4J_PASSWORD", None)

    def test_generated_artifacts_contain_no_credentials(self):
        audit_dir = PILOT_ROOT / "audit"
        if not audit_dir.is_dir():
            self.skipTest("artefatti di audit non ancora generati")
        checked = 0
        for path in sorted(audit_dir.rglob("*")):
            if not path.is_file():
                continue
            checked += 1
            content = path.read_text(encoding="utf-8", errors="replace")
            for pattern in self.SECRET_PATTERNS:
                self.assertNotIn(pattern, content, f"{pattern} trovato in {path}")
        self.assertGreater(checked, 0)


class SecondReviewPackageTest(TestCase):
    def setUp(self):
        self.table = build_alias_table()
        self.cases = load_gold(GOLD_PATH)

    def _entries(self):
        from benchmarks.mtb_evidence.pilot.audit_lib.queries.base import CaseOutcome

        entries = []
        for case in self.cases:
            outcome = CaseOutcome(case_id=case.case_id)
            comparison = compare_case(case, [], alias_table=self.table)
            entries.append(
                {
                    "case_id": case.case_id,
                    "case": case,
                    "outcome": outcome,
                    "comparison": comparison,
                    "decision": report.decide(case, comparison, outcome),
                }
            )
        return entries

    def test_package_has_all_four_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            written = second_review.write_package(Path(tmp), self._entries())
            for name in (
                "review_cases.csv", "review_claims.csv", "review_sources.csv",
                "reviewer_instructions.md",
            ):
                self.assertIn(name, written)
                self.assertTrue(written[name].is_file())

    def test_decision_column_is_present_and_empty(self):
        rows = second_review.build_claim_rows(self._entries())
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["reviewer_decision"], "")
            self.assertEqual(row["reviewer_notes"], "")

    def test_all_four_decision_options_are_documented(self):
        for option in second_review.DECISION_OPTIONS:
            self.assertIn(option, second_review.INSTRUCTIONS)

    def test_package_carries_no_suggestion_of_the_answer(self):
        """Un secondo giudizio contaminato dal primo non e' un secondo giudizio."""
        with tempfile.TemporaryDirectory() as tmp:
            written = second_review.write_package(Path(tmp), self._entries())
            for name, path in written.items():
                content = path.read_text(encoding="utf-8").casefold()
                for pattern in report.FORBIDDEN_REVIEW_PATTERNS:
                    self.assertNotIn(pattern.casefold(), content, f"{pattern} in {name}")

    def test_audit_decision_never_reaches_the_reviewer(self):
        rows = second_review.build_case_rows(self._entries())
        serialized = canonical_json(rows).casefold()
        for decision in (report.KEEP, report.AMEND, report.REPLACE, report.REJECT):
            self.assertNotIn(f'"{decision.casefold()}"', serialized)


class AmendmentsTest(TestCase):
    def setUp(self):
        self.table = build_alias_table()
        self.cases = {case.case_id: case for case in load_gold(GOLD_PATH)}

    def test_every_proposal_requires_human_review(self):
        from benchmarks.mtb_evidence.pilot.audit_lib.queries.base import CaseOutcome

        case = self.cases["PILOT-K1-FGFR2-iCCA"]
        outcome = CaseOutcome(case_id=case.case_id)
        comparison = compare_case(case, [], alias_table=self.table)
        proposals = report.build_amendments(case, comparison, outcome)
        self.assertTrue(proposals)
        for proposal in proposals:
            self.assertTrue(proposal["requires_human_review"])
            for key in (
                "case_id", "field", "current_value", "proposed_value", "reason",
                "supporting_graph_record_ids", "supporting_source_ids", "confidence",
            ):
                self.assertIn(key, proposal)

    def test_amendments_do_not_touch_the_gold_file(self):
        from benchmarks.mtb_evidence.pilot.audit_lib.queries.base import CaseOutcome

        before = GOLD_PATH.read_bytes()
        for case in self.cases.values():
            outcome = CaseOutcome(case_id=case.case_id)
            report.build_amendments(case, compare_case(case, [], alias_table=self.table), outcome)
        self.assertEqual(GOLD_PATH.read_bytes(), before)

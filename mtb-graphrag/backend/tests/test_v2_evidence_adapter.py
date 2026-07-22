"""Test dell'adapter V2 → EvidenceStatement.

Offline: nessun grafo, nessun modello. I record di prova ricalcano la forma reale
osservata negli artefatti dell'audit.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase

from backend.pipeline.evidence.adapter_metrics import (
    compatible_records,
    conversion_success_rate,
    evaluate,
    meets_acceptance,
    provenance_preservation,
    source_field_preservation,
    source_presence_breakdown,
    unknown_field_honesty,
)
from backend.pipeline.evidence.v2_adapter import (
    CIVIC_TYPE_TO_SCOPE,
    SIGNIFICANCE_TO_DIRECTION,
    adapt_record,
    adapt_records,
    classify_citation,
    infer_alteration_type,
    is_evidence_record,
    merge_duplicate_records,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = PROJECT_ROOT / "schemas" / "evidence_statement.schema.json"


def _record(**overrides):
    base = {
        "evidence_id": 441,
        "molecular_profile": "EML4::ALK Fusion AND ALK G1202R",
        "disease": "Lung Non-small Cell Carcinoma",
        "drug": "CRIZOTINIB",
        "significance": "Resistance",
        "evidence_direction": "Supports",
        "evidence_type": "Predictive",
        "evidence_level": "D",
        "citation_id": ["22277784"],
        "source_type": "PubMed",
    }
    base.update(overrides)
    return base


class RecordClassificationTest(TestCase):
    def test_evidence_record_is_recognised(self):
        self.assertTrue(is_evidence_record(_record()))

    def test_trial_record_is_not_an_evidence_record(self):
        """Un trial descrive uno studio, non una proposizione clinica."""
        self.assertFalse(is_evidence_record({"nct_id": "NCT02296125", "phase": "PHASE3"}))

    def test_compatible_records_exclude_trials_and_uncited(self):
        records = [_record(), {"nct_id": "NCT1"}, _record(evidence_id=2, citation_id=[])]
        self.assertEqual(len(compatible_records(records)), 1)


class CitationClassificationTest(TestCase):
    def test_pmid(self):
        self.assertEqual(classify_citation("22277784"), ("pubmed", "22277784"))

    def test_doi_is_recognised_not_discarded(self):
        """Il campo citation_id del grafo non e' omogeneo: almeno un record ha un DOI."""
        kind, value = classify_citation("10.1182/blood-2022-163099")
        self.assertEqual(kind, "doi")
        self.assertEqual(value, "10.1182/blood-2022-163099")

    def test_pmcid(self):
        self.assertEqual(classify_citation("PMC12345")[0], "pmc")

    def test_unrecognised_returns_none(self):
        self.assertIsNone(classify_citation("qualcosa di strano")[0])

    def test_leading_zeros_are_normalised(self):
        self.assertEqual(classify_citation("0022277784")[1], "22277784")


class MappingTablesTest(TestCase):
    def test_significance_maps_to_direction(self):
        self.assertEqual(SIGNIFICANCE_TO_DIRECTION["resistance"], "resistance")
        self.assertEqual(SIGNIFICANCE_TO_DIRECTION["sensitivity/response"], "sensitivity")

    def test_civic_evidence_type_maps_to_scope_not_to_evidence_type(self):
        """Il campo evidence_type del grafo e' il tipo di affermazione, non il disegno.

        Nel vocabolario CIViC vale Predictive, Diagnostic, Prognostic. Mapparlo su
        evidence_type, che descrive il disegno dello studio, sarebbe un errore di
        categoria: un'evidenza 'Predictive' puo' venire da uno studio randomizzato o
        da un esperimento in vitro.
        """
        self.assertEqual(CIVIC_TYPE_TO_SCOPE["predictive"], "therapeutic")
        statement = adapt_record(_record(evidence_type="Predictive")).statement
        self.assertEqual(statement["evidence_scope"], "therapeutic")
        self.assertEqual(statement["evidence_type"], "unknown")

    def test_unmapped_significance_becomes_unknown_and_is_recorded(self):
        result = adapt_record(_record(significance="Qualcosa Di Nuovo"))
        self.assertEqual(result.statement["direction"], "unknown")
        self.assertTrue(any(f.field_name == "direction" for f in result.unmapped_fields))


class AlterationTypeTest(TestCase):
    def test_fusion_marker(self):
        self.assertEqual(infer_alteration_type("EML4::ALK Fusion", False)[0], "fusion")

    def test_compound_wins_over_other_markers(self):
        self.assertEqual(
            infer_alteration_type("EML4::ALK Fusion AND ALK G1202R", True)[0],
            "compound_mutation",
        )

    def test_no_marker_stays_unknown(self):
        """Un profilo che nomina solo una variante sembra uno SNV, ma il grafo non lo dice."""
        kind, reason = infer_alteration_type("EGFR L858R", False)
        self.assertEqual(kind, "unknown")
        self.assertIn("nessun marcatore", reason)


class AdaptationTest(TestCase):
    def test_full_record_converts(self):
        result = adapt_record(_record(), snapshot_fingerprint="abc")
        self.assertTrue(result.converted)
        statement = result.statement
        self.assertEqual(statement["direction"], "resistance")
        self.assertEqual(statement["assertion_polarity"], "supports")
        self.assertEqual(statement["intervention"]["label"], "crizotinib")
        self.assertEqual(statement["evidence_level"]["original_value"], "D")
        self.assertEqual(statement["provenance"]["graph_record_ids"], ["evidence:441"])

    def test_does_not_support_is_representable(self):
        """Quattro record reali hanno 'Does Not Support' su 'Sensitivity/Response'.

        Senza assertion_polarity l'unico modo di rappresentarli sarebbe mappare la
        negazione su lack_of_benefit, che e' un'affermazione diversa e piu' forte.
        """
        statement = adapt_record(
            _record(significance="Sensitivity/Response", evidence_direction="Does Not Support")
        ).statement
        self.assertEqual(statement["direction"], "sensitivity")
        self.assertEqual(statement["assertion_polarity"], "does_not_support")

    def test_missing_evidence_level_is_not_invented(self):
        statement = adapt_record(_record(evidence_level=None)).statement
        self.assertIsNone(statement["evidence_level"])

    def test_present_level_keeps_its_original_scale(self):
        civic = adapt_record(_record(evidence_level="B")).statement["evidence_level"]
        self.assertEqual(civic["system"], "civic")
        oncokb = adapt_record(_record(evidence_level="LEVEL_1")).statement["evidence_level"]
        self.assertEqual(oncokb["system"], "oncokb")
        # Nessuna normalizzazione: richiede una decisione clinica ancora aperta.
        self.assertIsNone(civic["normalized_tier"])

    def test_clinical_qualifiers_stay_empty(self):
        """Il grafo V2 non li modella: riempirli falsificherebbe la baseline."""
        statement = adapt_record(_record()).statement
        self.assertEqual(statement["clinical_context"], {})

    def test_record_without_citations_is_not_converted(self):
        result = adapt_record(_record(citation_id=[]))
        self.assertFalse(result.converted)
        self.assertIn("citazione", result.reason)

    def test_record_without_profile_is_not_converted(self):
        result = adapt_record(_record(molecular_profile=None, subject=None))
        self.assertFalse(result.converted)

    def test_imported_record_is_not_frozen(self):
        """Un record del grafo e' curato a monte, ma non e' revisionato dalla V3."""
        self.assertEqual(adapt_record(_record()).statement["review_status"],
                         "pending_verification")

    def test_source_presence_is_carried_through(self):
        statement = adapt_record(
            _record(), source_presence={"22277784": "citation_only"}
        ).statement
        self.assertEqual(
            statement["source_references"][0]["presence_in_snapshot"], "citation_only"
        )

    def test_nested_citation_lists_are_flattened(self):
        result = adapt_record(_record(citation_id=[["22277784", "12345678"]]))
        self.assertTrue(result.converted)
        self.assertEqual(len(result.statement["source_references"]), 2)


class MergeTest(TestCase):
    def test_duplicates_are_merged_not_dropped(self):
        """Lo stesso evidence_id compare in query con proiezioni diverse.

        Tenere arbitrariamente la prima o l'ultima occorrenza scarterebbe campi che il
        grafo possiede, facendolo sembrare piu' povero di quanto sia.
        """
        with_level = _record(evidence_level="D")
        without_level = {k: v for k, v in _record().items() if k != "evidence_level"}
        merged = merge_duplicate_records([without_level, with_level])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["evidence_level"], "D")

    def test_merge_is_order_independent(self):
        a = _record(evidence_level="D")
        b = {k: v for k, v in _record().items() if k != "evidence_level"}
        self.assertEqual(
            merge_duplicate_records([a, b])[0].get("evidence_level"),
            merge_duplicate_records([b, a])[0].get("evidence_level"),
        )

    def test_list_fields_are_unioned(self):
        first = _record(citation_id=["111"])
        second = _record(citation_id=["222"])
        merged = merge_duplicate_records([first, second])[0]
        self.assertEqual(merged["citation_id"], ["111", "222"])

    def test_existing_values_are_not_overwritten(self):
        first = _record(disease="Prima")
        second = _record(disease="Seconda")
        self.assertEqual(merge_duplicate_records([first, second])[0]["disease"], "Prima")


class MeasuresTest(TestCase):
    def setUp(self):
        self.records = [_record(evidence_id=i, citation_id=[str(10000000 + i)])
                        for i in range(1, 6)]
        self.results = adapt_records(self.records)

    def test_all_convert(self):
        self.assertEqual(conversion_success_rate(self.results).value, 1.0)

    def test_present_fields_are_preserved(self):
        self.assertEqual(source_field_preservation(self.results, self.records).value, 1.0)

    def test_provenance_is_traceable(self):
        self.assertEqual(provenance_preservation(self.results).value, 1.0)

    def test_honesty_is_perfect_when_nothing_is_invented(self):
        self.assertEqual(unknown_field_honesty(self.results, self.records).value, 1.0)

    def test_honesty_detects_an_invented_field(self):
        """La misura deve saper fallire, altrimenti non misura nulla."""
        tampered = adapt_records(self.records)
        tampered[0].statement["clinical_context"]["therapy_line"] = "first_line"
        measure = unknown_field_honesty(tampered, self.records)
        self.assertLess(measure.value, 1.0)
        self.assertTrue(measure.detail)

    def test_honesty_detects_a_deduced_level(self):
        records = [_record(evidence_id=1, evidence_level=None, citation_id=["11111111"])]
        results = adapt_records(records)
        results[0].statement["evidence_level"] = {"system": "civic", "original_value": "A"}
        self.assertLess(unknown_field_honesty(results, records).value, 1.0)

    def test_preservation_ignores_fields_absent_at_source(self):
        """Un campo che il record non ha non puo' essere una perdita."""
        records = [_record(evidence_id=1, evidence_level=None, citation_id=["11111111"])]
        measure = source_field_preservation(adapt_records(records), records)
        self.assertEqual(measure.value, 1.0)

    def test_acceptance_requires_all_four(self):
        evaluation = evaluate(self.results, self.records)
        ok, failures = meets_acceptance(evaluation)
        self.assertTrue(ok, failures)

    def test_acceptance_reports_which_criterion_failed(self):
        evaluation = evaluate(self.results, self.records)
        evaluation["measures"]["unknown_field_honesty"]["value"] = 0.9
        ok, failures = meets_acceptance(evaluation)
        self.assertFalse(ok)
        self.assertIn("unknown_field_honesty", failures[0])

    def test_source_presence_breakdown_counts_three_states(self):
        results = adapt_records(
            self.records, source_presence={"10000001": "node", "10000002": "citation_only"}
        )
        breakdown = source_presence_breakdown(results)
        self.assertIn("node", breakdown)
        self.assertIn("citation_only", breakdown)


class SchemaConformanceTest(TestCase):
    def test_produced_statements_validate(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema non installato")
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        validator = jsonschema.validators.validator_for(schema)(schema)
        for record in (_record(), _record(evidence_level=None), _record(drug=None)):
            result = adapt_record(record)
            if not result.converted:
                continue
            errors = list(validator.iter_errors(result.statement))
            self.assertEqual(errors, [], f"{errors[0].message if errors else ''}")

    def test_real_pilot_statements_validate(self):
        produced = (
            PROJECT_ROOT / "benchmarks" / "mtb_evidence" / "evaluation" / "results"
            / "adapter_v1" / "evidence_statements.jsonl"
        )
        if not produced.is_file():
            self.skipTest("adapter non ancora eseguito sui record del pilota")
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema non installato")
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        validator = jsonschema.validators.validator_for(schema)(schema)
        count = 0
        for line in produced.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            count += 1
            errors = list(validator.iter_errors(json.loads(line)))
            self.assertEqual(errors, [], errors[0].message if errors else "")
        self.assertGreater(count, 100)

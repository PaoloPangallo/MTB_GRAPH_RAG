from unittest import TestCase

from backend.pipeline.agentic.applicability_validator import (
    normalize_line_category,
    normalize_prior_therapy_requirement,
    normalize_setting_category,
    validate_applicability,
)


class NormalizeCategoriesTest(TestCase):
    def test_invalid_or_missing_values_become_unknown(self):
        self.assertEqual(normalize_line_category(None), "unknown")
        self.assertEqual(normalize_line_category("not-a-category"), "unknown")
        self.assertEqual(normalize_line_category("First_Line"), "first_line")
        self.assertEqual(normalize_setting_category(123), "unknown")
        self.assertEqual(normalize_setting_category("Metastatic"), "metastatic")
        self.assertEqual(normalize_prior_therapy_requirement(""), "unknown")
        self.assertEqual(normalize_prior_therapy_requirement("Treatment_Naive"), "treatment_naive")


class ValidateApplicabilityTest(TestCase):
    def test_first_line_does_not_imply_metastatic_advanced_unresected_or_naive(self):
        """La sola categoria 'first_line' non deve mai far dedurre malattia
        metastatica, avanzata, non operata o assenza di trattamenti pregressi:
        se la fonte non dichiara setting o requisiti di pre-trattamento, il
        verdict dell'LLM non viene alterato da un'inferenza sulla linea."""
        result = validate_applicability(
            {"source_line_category": "first_line"},
            {"therapy_line": "first-line", "disease_stage": "", "disease_setting": "", "prior_therapies": ""},
            "compatible",
        )
        self.assertEqual(result, "compatible")

    def test_missing_setting_forces_compatible_to_indeterminate(self):
        result = validate_applicability(
            {"source_line_category": "first_line", "source_setting_category": "metastatic"},
            {"therapy_line": "first-line", "disease_stage": "", "disease_setting": "", "prior_therapies": ""},
            "compatible",
        )
        self.assertEqual(result, "indeterminate")

    def test_missing_stage_forces_indeterminate_when_source_requires_advanced_disease(self):
        result = validate_applicability(
            {"source_setting_category": "locally_advanced"},
            {"disease_stage": "", "disease_setting": "locally-advanced"},
            "compatible",
        )
        self.assertEqual(result, "indeterminate")

    def test_missing_prior_therapies_forces_indeterminate_when_source_requires_them(self):
        result = validate_applicability(
            {"source_prior_therapy_requirement": "previously_treated"},
            {"prior_therapies": ""},
            "compatible",
        )
        self.assertEqual(result, "indeterminate")

    def test_explicit_first_line_vs_post_progression_conflict_is_not_compatible(self):
        result = validate_applicability(
            {"source_line_category": "post_progression"},
            {"therapy_line": "first-line"},
            "compatible",
        )
        self.assertEqual(result, "not_compatible")

    def test_explicit_setting_conflict_resected_vs_metastatic_is_not_compatible(self):
        result = validate_applicability(
            {"source_setting_category": "metastatic"},
            {"disease_setting": "resected"},
            "compatible",
        )
        self.assertEqual(result, "not_compatible")

    def test_adjuvant_source_with_undeclared_patient_setting_is_indeterminate_not_not_compatible(self):
        """Fonte esclusivamente adiuvante (es. osimertinib post-resezione),
        ma il paziente non ha dichiarato alcun setting: nessun conflitto
        esplicito esiste, quindi il verdict deve restare 'indeterminate',
        mai diventare 'not_compatible' per un'assunzione non dichiarata."""
        result = validate_applicability(
            {
                "source_line_category": "adjuvant",
                "source_setting_category": "adjuvant",
                "source_prior_therapy_requirement": "specific_therapy",
            },
            {"disease_stage": "", "disease_setting": "", "prior_therapies": ""},
            "compatible",
        )
        self.assertEqual(result, "indeterminate")

    def test_never_upgrades_an_already_conservative_verdict(self):
        result = validate_applicability(
            {"source_line_category": "first_line"},
            {"therapy_line": "first-line", "disease_stage": "", "disease_setting": ""},
            "not_compatible",
        )
        self.assertEqual(result, "not_compatible")

    def test_unrecognized_llm_verdict_defaults_to_indeterminate_baseline(self):
        result = validate_applicability({}, {}, "definitely_compatible")
        self.assertEqual(result, "indeterminate")

    def test_fully_declared_matching_context_leaves_compatible_untouched(self):
        result = validate_applicability(
            {"source_line_category": "first_line", "source_setting_category": "metastatic"},
            {"therapy_line": "first-line", "disease_stage": "IV", "disease_setting": "metastatic", "prior_therapies": "Nessuno"},
            "compatible",
        )
        self.assertEqual(result, "compatible")

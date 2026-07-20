from unittest import TestCase

from backend.pipeline.agentic.applicability_validator import (
    derive_applicability,
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
    def test_first_line_alone_is_not_sufficient_for_compatible(self):
        """Correzione della regressione osservata nel run live: il solo
        'first_line' che coincide da entrambi i lati non basta a confermare
        'compatible' se setting e requisito di pre-trattamento della fonte
        restano 'unknown' — una categoria mancante non permette mai una
        conferma positiva, anche quando l'unico dato disponibile coincide."""
        status, reason = validate_applicability(
            {"source_line_category": "first_line"},
            {"therapy_line": "first-line", "disease_stage": "", "disease_setting": "", "prior_therapies": ""},
            "compatible",
            "Le linee dichiarate coincidono.",
        )
        self.assertEqual(status, "indeterminate")
        self.assertNotIn("coincidono", reason)

    def test_missing_setting_forces_compatible_to_indeterminate(self):
        status, _reason = validate_applicability(
            {"source_line_category": "first_line", "source_setting_category": "metastatic", "source_prior_therapy_requirement": "treatment_naive"},
            {"therapy_line": "first-line", "disease_stage": "", "disease_setting": "", "prior_therapies": ""},
            "compatible",
        )
        self.assertEqual(status, "indeterminate")

    def test_missing_stage_forces_indeterminate_when_source_requires_advanced_disease(self):
        status, _reason = validate_applicability(
            {"source_line_category": "first_line", "source_setting_category": "locally_advanced", "source_prior_therapy_requirement": "treatment_naive"},
            {"therapy_line": "first-line", "disease_stage": "", "disease_setting": "locally-advanced", "prior_therapies": "Nessuno"},
            "compatible",
        )
        self.assertEqual(status, "indeterminate")

    def test_missing_prior_therapies_forces_indeterminate_when_source_requires_them(self):
        status, _reason = validate_applicability(
            {"source_line_category": "later_line", "source_setting_category": "metastatic", "source_prior_therapy_requirement": "previously_treated"},
            {"therapy_line": "second-line", "disease_stage": "IV", "disease_setting": "metastatic", "prior_therapies": ""},
            "compatible",
        )
        self.assertEqual(status, "indeterminate")

    def test_unknown_source_category_blocks_compatible_even_if_rest_matches(self):
        """Una sola categoria mancante ('unknown') basta a impedire
        'compatible', anche se le altre due coincidono perfettamente col
        contesto dichiarato dal paziente."""
        status, _reason = validate_applicability(
            {"source_line_category": "first_line", "source_setting_category": "metastatic"},
            {"therapy_line": "first-line", "disease_stage": "IV", "disease_setting": "metastatic", "prior_therapies": "Nessuno"},
            "compatible",
        )
        self.assertEqual(status, "indeterminate")

    def test_explicit_first_line_vs_post_progression_conflict_is_not_compatible(self):
        status, reason = validate_applicability(
            {"source_line_category": "post_progression"},
            {"therapy_line": "first-line"},
            "compatible",
            "Le linee coincidono perfettamente.",
        )
        self.assertEqual(status, "not_compatible")
        self.assertNotIn("coincidono perfettamente", reason)
        self.assertIn("conflitto", reason.lower())

    def test_explicit_setting_conflict_resected_vs_metastatic_is_not_compatible(self):
        status, reason = validate_applicability(
            {"source_setting_category": "metastatic"},
            {"disease_setting": "resected"},
            "compatible",
            "I setting coincidono perfettamente.",
        )
        self.assertEqual(status, "not_compatible")
        self.assertNotIn("coincidono perfettamente", reason)

    def test_adjuvant_source_with_undeclared_patient_setting_is_indeterminate_not_not_compatible(self):
        """Fonte esclusivamente adiuvante (es. ADAURA: osimertinib
        post-resezione), ma il paziente non ha dichiarato alcun setting:
        nessun conflitto esplicito esiste, quindi il verdict deve restare
        'indeterminate', mai diventare 'not_compatible' per un'assunzione non
        dichiarata (first-line non implica malattia avanzata/metastatica/non
        resecata/non operata)."""
        status, _reason = validate_applicability(
            {
                "source_line_category": "adjuvant",
                "source_setting_category": "adjuvant",
                "source_prior_therapy_requirement": "specific_therapy",
            },
            {"disease_stage": "", "disease_setting": "", "prior_therapies": ""},
            "compatible",
        )
        self.assertEqual(status, "indeterminate")

    def test_adaura_pmid_32955177_first_line_case_with_missing_context_is_indeterminate(self):
        """Test obbligatorio: regressione osservata nel run live — PMID
        32955177 (ADAURA, adiuvante) veniva classificato 'not_compatible' con
        la motivazione vietata "first-line implica malattia avanzata/non
        resecata". Con therapy_line='first-line' e stadio/setting/terapie
        precedenti del caso mancanti, il verdict finale deve essere
        'indeterminate' — anche partendo da un llm_verdict già
        'not_compatible' — e la motivazione vietata non deve sopravvivere."""
        status, reason = validate_applicability(
            {
                "source_line_category": "adjuvant",
                "source_setting_category": "resected",
                "source_prior_therapy_requirement": "specific_therapy",
            },
            {
                "therapy_line": "first-line",
                "disease_stage": "",
                "disease_setting": "",
                "prior_therapies": "",
            },
            "not_compatible",
            "First-line generalmente implica malattia avanzata/non resecata.",
        )
        self.assertEqual(status, "indeterminate")
        self.assertNotIn("generalmente implica", reason)
        self.assertNotIn("avanzata", reason.lower())

    def test_not_compatible_without_explicit_conflict_is_corrected_to_indeterminate(self):
        """Un 'not_compatible' del modello non basta da solo: se il
        validatore non rileva un conflitto esplicito codificato (linea o
        setting mutuamente esclusivi) — anche quando tutti i dati necessari
        sono dichiarati e non in conflitto — il verdict viene corretto.
        'not_compatible' richiede sempre due valori esplicitamente
        dichiarati e incompatibili, mai un'inferenza libera del modello."""
        status, reason = validate_applicability(
            {
                "source_line_category": "first_line",
                "source_setting_category": "metastatic",
                "source_prior_therapy_requirement": "treatment_naive",
            },
            {
                "therapy_line": "first-line",
                "disease_stage": "IV",
                "disease_setting": "metastatic",
                "prior_therapies": "Nessuno",
            },
            "not_compatible",
            "Il modello ha rilevato un'incompatibilità non specificata.",
        )
        self.assertEqual(status, "indeterminate")
        self.assertNotIn("non specificata", reason)

    def test_unrecognized_llm_verdict_defaults_to_indeterminate_baseline(self):
        status, reason = validate_applicability({}, {}, "definitely_compatible")
        self.assertEqual(status, "indeterminate")
        self.assertTrue(reason)

    def test_fully_declared_matching_context_is_compatible(self):
        """Contesto realmente completo e coincidente su tutti e tre gli assi
        strutturati (linea, setting, pre-trattamento) da entrambi i lati:
        solo in questo caso 'compatible' è consentito."""
        status, reason = validate_applicability(
            {
                "source_line_category": "first_line",
                "source_setting_category": "metastatic",
                "source_prior_therapy_requirement": "treatment_naive",
            },
            {
                "therapy_line": "first-line",
                "disease_stage": "IV",
                "disease_setting": "metastatic",
                "prior_therapies": "Nessuno",
            },
            "compatible",
            "Setting, linea e pre-trattamento dichiarati coincidono esplicitamente.",
        )
        self.assertEqual(status, "compatible")
        self.assertEqual(reason, "Setting, linea e pre-trattamento dichiarati coincidono esplicitamente.")

    def test_reason_is_never_positive_when_verdict_is_downgraded(self):
        """Non deve mai sopravvivere una motivazione LLM positiva ('i setting
        coincidono perfettamente') quando il validatore ha declassato il
        verdict per dati mancanti."""
        status, reason = validate_applicability(
            {"source_line_category": "first_line"},
            {"therapy_line": "first-line", "disease_stage": "", "disease_setting": "", "prior_therapies": ""},
            "compatible",
            "I setting coincidono perfettamente.",
        )
        self.assertEqual(status, "indeterminate")
        self.assertNotIn("coincidono perfettamente", reason)
        self.assertIn("insufficienti", reason.lower())


class DeriveApplicabilityTest(TestCase):
    """derive_applicability: stessa logica di validate_applicability ma senza
    alcun verdict LLM — usata nel percorso rapido (fase B, indipendente dalla
    chiamata LLM cacheable del profilo sorgente)."""

    def test_fully_matching_context_is_compatible(self):
        status, reason = derive_applicability(
            {
                "source_line_category": "first_line",
                "source_setting_category": "metastatic",
                "source_prior_therapy_requirement": "treatment_naive",
            },
            {
                "therapy_line": "first-line",
                "disease_stage": "IV",
                "disease_setting": "metastatic",
                "prior_therapies": "Nessuno",
            },
        )
        self.assertEqual(status, "compatible")
        self.assertTrue(reason)

    def test_missing_data_is_indeterminate_without_any_llm_verdict(self):
        status, _reason = derive_applicability(
            {"source_line_category": "first_line"},
            {"therapy_line": "first-line", "disease_stage": "", "disease_setting": ""},
        )
        self.assertEqual(status, "indeterminate")

    def test_explicit_conflict_is_not_compatible_without_any_llm_verdict(self):
        status, reason = derive_applicability(
            {"source_line_category": "post_progression"},
            {"therapy_line": "first-line"},
        )
        self.assertEqual(status, "not_compatible")
        self.assertIn("conflitto", reason.lower())

    def test_adaura_case_stays_indeterminate_via_pure_derivation(self):
        status, _reason = derive_applicability(
            {
                "source_line_category": "adjuvant",
                "source_setting_category": "resected",
                "source_prior_therapy_requirement": "specific_therapy",
            },
            {"therapy_line": "first-line", "disease_stage": "", "disease_setting": "", "prior_therapies": ""},
        )
        self.assertEqual(status, "indeterminate")

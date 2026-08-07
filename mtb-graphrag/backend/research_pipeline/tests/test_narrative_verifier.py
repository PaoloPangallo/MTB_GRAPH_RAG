"""Narrative Verifier — happy path, avversariali e determinismo.

I dossier canonici usati come base sono **reali**: prodotti da run REPLAY e
congelati in ``evaluation/dossier_narrator/raw/A01_real_dossiers.json``. Le
narrative sono costruite dal test, perché servono casi che un modello ben
funzionante non produrrebbe.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from backend.research_pipeline.narrative.input_projection import (
    NARRATIVE_CRITICAL_WARNINGS, build_narrator_input,
)
from backend.research_pipeline.narrative.verifier import (
    FAIL, PASS, REASON_CRITICAL_OMISSION, REASON_NEGATION_LOST,
    REASON_POLARITY_INVERSION, REASON_REJECTED_QUOTE_PROMOTED,
    REASON_STATUS_ESCALATION, REASON_UNAUTHORIZED_ENTITY,
    REASON_UNAUTHORIZED_QUOTE, REASON_UNAUTHORIZED_RECOMMENDATION,
    VERIFIER_VERSION, result_fingerprint, verify_narrative,
)

REAL = Path(__file__).resolve().parents[3] / "evaluation/dossier_narrator/raw/A01_real_dossiers.json"


def _real_dossiers() -> dict:
    if not REAL.is_file():  # pragma: no cover
        raise unittest.SkipTest(f"campione reale assente: {REAL}")
    return {k: v["dossier"] for k, v in json.loads(REAL.read_text(encoding="utf-8")).items()
            if v.get("dossier")}


def _synthetic_dossier(*, status="DIRECT", direction="SUPPORTED", drug="PANITUMUMAB",
                       warnings=(), quote=None, rejected_quote=None,
                       candidate_id="GCA-SYN", bucket="PRIMARY_BUCKET"):
    """Dossier canonico minimo ma conforme al contratto reale."""
    author_context = []
    if quote:
        author_context.append({
            "author_claim_quote": quote, "author_context_summary": "sintesi",
            "source_unit_id": "SU-1", "paper_id": "EB-1", "decision": "QUOTE",
            "presentation_state": "VALIDATED_QUOTE",
            "validation_outcome": "ENRICHMENT_V2_ACCEPTED",
            "validation_reason_codes": [], "accepted_for_gates": True,
        })
    if rejected_quote:
        author_context.append({
            "author_claim_quote": rejected_quote, "author_context_summary": "",
            "source_unit_id": "SU-1", "paper_id": "EB-1", "decision": "QUOTE",
            "presentation_state": "REJECTED_QUOTE",
            "validation_outcome": "REJECTED_QUOTE_NOT_FOUND",
            "validation_reason_codes": ["QUOTE_NOT_LITERAL_IN_SOURCE_UNIT"],
            "accepted_for_gates": False,
        })
    return {
        "case_id": "CASE-SYN",
        "case_context": {
            "query_intent": "THERAPY_EVALUATION",
            "disease": {"normalized_value": "Colorectal Cancer"},
            "biomarkers": [{"normalized_value": "KRAS G12D"}],
            "target_intervention": {"normalized_value": drug},
            "clinical_question": "valutazione",
        },
        "case_context_verification": {"records": [], "essential_fields_pass": True, "warnings": []},
        "candidate_therapies": [{
            "candidate_id": candidate_id, "drug": drug,
            "graph_relation": "associated_with_sensitivity_to",
            "status": status, "warnings": list(warnings),
            "gate_results": {"bucket": bucket, "support_mask": {
                "disease": "SUPPORTED", "biomarker": "SUPPORTED",
                "intervention": "SUPPORTED", "direction": direction}},
            "document_support": {"selected_papers": ["EB-1"], "excluded_papers": []},
            "author_context": author_context,
            "validation_results": [],
        }],
        "limitations": ["research_only_pilot"],
        "provenance": {"dossier_version": "end-to-end-pilot-dossier/1.0",
                       "dossier_kind": "research_only", "gemma_never_decides": []},
    }


def _narrative(text, *, candidate_id="GCA-SYN", summary="Il sistema ha identificato una candidate.",
               limitations="Prototipo di ricerca.", closing="Materiale per revisione MTB."):
    payload = {
        "narrative_summary": summary,
        "candidate_narratives": [{"candidate_id": candidate_id, "text": text}],
        "limitations_summary": limitations, "closing_note": closing,
    }
    payload["narrative_hash"] = "hash-di-test"
    return payload


def _verify(dossier, narrative):
    return verify_narrative(dossier, build_narrator_input(dossier), narrative)


# ══════════════════════════════════════════════════════════ §21 happy path

class HappyPathTest(unittest.TestCase):

    def test_direct_candidate_with_validated_quote_passes(self) -> None:
        dossier = _synthetic_dossier(quote="patients responded to panitumumab")
        text = ('La candidate PANITUMUMAB è associata nel Knowledge Graph al caso. '
                'La citazione validata descrive: "patients responded to panitumumab".')
        result = _verify(dossier, _narrative(text))
        self.assertEqual(result["status"], PASS, result["reason_codes"])

    def test_multiple_candidates_pass(self) -> None:
        dossier = _synthetic_dossier(quote="patients responded to panitumumab")
        second = dict(dossier["candidate_therapies"][0])
        second["candidate_id"] = "GCA-SYN-2"
        second["drug"] = "CETUXIMAB"
        second["author_context"] = []
        second["status"] = "AMBIGUOUS"
        second["warnings"] = ["NO_VALIDATED_ENRICHMENT_AVAILABLE"]
        second["gate_results"] = {"bucket": "WARNING_BUCKET", "support_mask": {
            "disease": "SUPPORTED", "biomarker": "SUPPORTED",
            "intervention": "SUPPORTED", "direction": "NO_DOCUMENT_SIGNAL"}}
        dossier["candidate_therapies"].append(second)

        narrative = _narrative("La candidate PANITUMUMAB è associata nel grafo al caso.")
        narrative["candidate_narratives"].append({
            "candidate_id": "GCA-SYN-2",
            "text": ("Per CETUXIMAB la relazione rimane ambigua e non è stata trovata "
                     "alcuna citazione validata."),
        })
        result = _verify(dossier, narrative)
        self.assertEqual(result["status"], PASS, result["reason_codes"])

    def test_ambiguous_candidate_with_uncertainty_marker_passes(self) -> None:
        dossier = _synthetic_dossier(status="AMBIGUOUS", direction="NO_DOCUMENT_SIGNAL",
                                     bucket="WARNING_BUCKET",
                                     warnings=["NO_VALIDATED_ENRICHMENT_AVAILABLE"])
        text = ("La relazione con PANITUMUMAB rimane ambigua: non è stata trovata "
                "alcuna citazione validata a supporto.")
        self.assertEqual(_verify(dossier, _narrative(text))["status"], PASS)

    def test_source_does_not_support_with_negation_passes(self) -> None:
        dossier = _synthetic_dossier(status="AMBIGUOUS", direction="SOURCE_DOES_NOT_SUPPORT",
                                     bucket="WARNING_BUCKET",
                                     warnings=["SOURCE_POLARITY_DOES_NOT_SUPPORT"])
        text = ("La fonte non supporta l'associazione fra PANITUMUMAB e il caso; "
                "la relazione rimane incerta e nessuna citazione validata la sostiene.")
        self.assertEqual(_verify(dossier, _narrative(text))["status"], PASS)

    def test_abstention_and_limitations_pass(self) -> None:
        dossier = _synthetic_dossier(status="AMBIGUOUS", direction="NO_DOCUMENT_SIGNAL",
                                     bucket="WARNING_BUCKET",
                                     warnings=["NO_VALIDATED_ENRICHMENT_AVAILABLE"])
        text = ("Il modello si è astenuto per questa candidate; la relazione resta ambigua.")
        result = _verify(dossier, _narrative(
            text, limitations="Prototipo di ricerca, nessun documento nuovo scaricato."))
        self.assertEqual(result["status"], PASS, result["reason_codes"])

    def test_real_dossiers_accept_a_faithful_narrative(self) -> None:
        for case_id, dossier in _real_dossiers().items():
            narrator_input = build_narrator_input(dossier)
            entries, faithful = [], True
            for candidate in narrator_input["candidates"]:
                parts = [f"La candidate {candidate['drug']} è associata nel Knowledge Graph al caso."]
                if candidate["canonical_status"] == "AMBIGUOUS":
                    parts.append("La relazione rimane ambigua.")
                if "NO_VALIDATED_ENRICHMENT_AVAILABLE" in candidate["critical_warnings"]:
                    parts.append("Non è stata trovata alcuna citazione validata.")
                if candidate["source_does_not_support"]:
                    parts.append("La fonte non supporta l'associazione.")
                if candidate["support_direction"] == "UNRELATED_EVIDENCE":
                    parts.append("La citazione validata non affronta la direzione della relazione.")
                entries.append({"candidate_id": candidate["candidate_id"], "text": " ".join(parts)})
            narrative = {
                "narrative_summary": "Il sistema ha identificato le candidate elencate.",
                "candidate_narratives": entries,
                "limitations_summary": "Prototipo di ricerca.",
                "closing_note": "Materiale per revisione in Molecular Tumor Board.",
                "narrative_hash": "h",
            }
            with self.subTest(case=case_id):
                result = verify_narrative(dossier, narrator_input, narrative)
                self.assertEqual(result["status"], PASS,
                                 f"{case_id}: {result['reason_codes']}")
                self.assertTrue(faithful)


# ═════════════════════════════════════════════════ §22 invenzione di entità

class EntityInventionTest(unittest.TestCase):

    def setUp(self) -> None:
        self.dossier = _synthetic_dossier(quote="patients responded to panitumumab")
        self.base = "La candidate PANITUMUMAB è associata nel grafo al caso."

    def _fails_with_entity(self, text):
        result = _verify(self.dossier, _narrative(text))
        self.assertEqual(result["status"], FAIL)
        self.assertIn(REASON_UNAUTHORIZED_ENTITY, result["reason_codes"])
        return result

    def test_new_drug_uppercase_fails(self) -> None:
        self._fails_with_entity(self.base + " Si considera anche PEMBROLIZUMAB.")

    def test_new_drug_lowercase_fails(self) -> None:
        """La radice INN intercetta il farmaco anche fuori dal maiuscolo."""
        self._fails_with_entity(self.base + " Si considera anche pembrolizumab.")

    def test_new_drug_with_nib_stem_fails(self) -> None:
        self._fails_with_entity(self.base + " Anche osimertinib è rilevante.")

    def test_new_gene_fails(self) -> None:
        self._fails_with_entity(self.base + " Rilevante anche EGFR.")

    def test_new_pmid_fails(self) -> None:
        self._fails_with_entity(self.base + " Vedi PMID:12345678.")

    def test_new_nct_fails(self) -> None:
        self._fails_with_entity(self.base + " Vedi NCT01234567.")

    def test_new_doi_fails(self) -> None:
        self._fails_with_entity(self.base + " Vedi 10.1000/abcd1234.")

    def test_unknown_candidate_id_fails(self) -> None:
        narrative = _narrative(self.base, candidate_id="GCA-INVENTATA")
        result = _verify(self.dossier, narrative)
        self.assertEqual(result["status"], FAIL)
        self.assertIn("GCA-INVENTATA", result["unknown_candidate_ids"])

    def test_authorised_entities_do_not_fail(self) -> None:
        text = (self.base + " Il farmaco panitumumab e il biomarcatore KRAS G12D "
                            "appartengono al caso.")
        result = _verify(self.dossier, _narrative(text))
        self.assertEqual(result["status"], PASS, result["reason_codes"])


# ═══════════════════════════════════════════════ §23 escalation di status

class StatusEscalationTest(unittest.TestCase):

    def _fails(self, dossier, text, reason=REASON_STATUS_ESCALATION):
        result = _verify(dossier, _narrative(text))
        self.assertEqual(result["status"], FAIL)
        self.assertIn(reason, result["reason_codes"])
        return result

    def test_ambiguous_described_as_strongly_supported_fails(self) -> None:
        dossier = _synthetic_dossier(status="AMBIGUOUS", direction="NO_DOCUMENT_SIGNAL",
                                     bucket="WARNING_BUCKET",
                                     warnings=["NO_VALIDATED_ENRICHMENT_AVAILABLE"])
        self._fails(dossier, "La candidate è fortemente supportata dalla letteratura.")

    def test_contradicted_described_as_confirmed_fails(self) -> None:
        dossier = _synthetic_dossier(status="CONTRADICTED", direction="CONTRADICTED",
                                     bucket="REJECTED_BUCKET")
        self._fails(dossier, "Il ruolo di PANITUMUMAB è confermato dagli studi.")

    def test_does_not_support_described_as_supporting_fails(self) -> None:
        dossier = _synthetic_dossier(status="AMBIGUOUS", direction="SOURCE_DOES_NOT_SUPPORT",
                                     bucket="WARNING_BUCKET",
                                     warnings=["SOURCE_POLARITY_DOES_NOT_SUPPORT"])
        result = self._fails(dossier, "La fonte è supportata e dimostra efficacia.")
        self.assertIn(REASON_POLARITY_INVERSION, result["reason_codes"])

    def test_audit_only_described_as_primary_option_fails(self) -> None:
        dossier = _synthetic_dossier(status="AMBIGUOUS", direction="NO_DOCUMENT_SIGNAL",
                                     bucket="WARNING_BUCKET",
                                     warnings=["NO_VALIDATED_ENRICHMENT_AVAILABLE"])
        self._fails(dossier, "PANITUMUMAB è l'opzione terapeutica primaria per il caso.")

    def test_direct_candidate_may_be_described_as_supported(self) -> None:
        """Il controllo e' asimmetrico: cio' che il dossier afferma e' dicibile."""
        dossier = _synthetic_dossier(status="DIRECT", direction="SUPPORTED")
        text = "La citazione validata supporta l'associazione descritta dal grafo."
        self.assertEqual(_verify(dossier, _narrative(text))["status"], PASS)


# ═══════════════════════════════════════════════ §24 linguaggio prescrittivo

class RecommendationLanguageTest(unittest.TestCase):

    def setUp(self) -> None:
        self.dossier = _synthetic_dossier(status="DIRECT", direction="SUPPORTED")

    def _fails(self, text):
        result = _verify(self.dossier, _narrative(text))
        self.assertEqual(result["status"], FAIL, text)
        self.assertIn(REASON_UNAUTHORIZED_RECOMMENDATION, result["reason_codes"])

    def test_english_recommendation_forms_fail(self) -> None:
        for text in ("The patient should receive PANITUMUMAB.",
                     "PANITUMUMAB is recommended for this patient.",
                     "This is the best treatment for the case.",
                     "PANITUMUMAB is the treatment of choice.",
                     "This is standard of care."):
            with self.subTest(text=text):
                self._fails(text)

    def test_italian_recommendation_forms_fail(self) -> None:
        for text in ("Si raccomanda PANITUMUMAB.",
                     "La terapia raccomandata è PANITUMUMAB.",
                     "Il paziente dovrebbe ricevere PANITUMUMAB.",
                     "Il paziente dovrebbe essere trattato con PANITUMUMAB.",
                     "PANITUMUMAB è indicato per questo caso."):
            with self.subTest(text=text):
                self._fails(text)

    def test_recommendation_in_closing_note_also_fails(self) -> None:
        narrative = _narrative("La candidate è associata nel grafo al caso.",
                               closing="Si raccomanda di procedere con la terapia.")
        result = _verify(self.dossier, narrative)
        self.assertEqual(result["status"], FAIL)
        self.assertIn(REASON_UNAUTHORIZED_RECOMMENDATION, result["reason_codes"])

    def test_descriptive_language_passes(self) -> None:
        text = ("Il sistema ha identificato la candidate PANITUMUMAB; il documento "
                "selezionato riporta osservazioni pertinenti.")
        self.assertEqual(_verify(self.dossier, _narrative(text))["status"], PASS)


# ══════════════════════════════════════════════════════════════ §25 quote

class QuoteTest(unittest.TestCase):

    def test_invented_quote_fails(self) -> None:
        dossier = _synthetic_dossier(quote="patients responded to panitumumab")
        text = 'Gli autori scrivono: "panitumumab prolonged overall survival substantially".'
        result = _verify(dossier, _narrative(text))
        self.assertEqual(result["status"], FAIL)
        self.assertIn(REASON_UNAUTHORIZED_QUOTE, result["reason_codes"])

    def test_modified_quote_fails(self) -> None:
        dossier = _synthetic_dossier(quote="patients with KRAS mutations did not respond to panitumumab")
        text = 'La citazione validata descrive: "patients with KRAS mutations did respond to panitumumab".'
        result = _verify(dossier, _narrative(text))
        self.assertEqual(result["status"], FAIL)
        self.assertIn(REASON_UNAUTHORIZED_QUOTE, result["reason_codes"])

    def test_rejected_quote_narrated_as_evidence_fails(self) -> None:
        """Il caso piu' importante: una quote scartata dal validatore."""
        dossier = _synthetic_dossier(
            quote="patients responded to panitumumab",
            rejected_quote="panitumumab significantly prolonged overall survival")
        text = ('La citazione validata descrive: '
                '"panitumumab significantly prolonged overall survival".')
        result = _verify(dossier, _narrative(text))
        self.assertEqual(result["status"], FAIL)
        self.assertIn(REASON_REJECTED_QUOTE_PROMOTED, result["reason_codes"])

    def test_quote_from_another_candidate_fails(self) -> None:
        dossier = _synthetic_dossier(quote="patients responded to panitumumab")
        text = 'Gli autori riportano: "encorafenib plus cetuximab produced durable responses".'
        result = _verify(dossier, _narrative(text))
        self.assertEqual(result["status"], FAIL)
        self.assertIn(REASON_UNAUTHORIZED_QUOTE, result["reason_codes"])

    def test_validated_quote_passes(self) -> None:
        dossier = _synthetic_dossier(quote="patients responded to panitumumab")
        text = 'La citazione validata descrive: "patients responded to panitumumab".'
        self.assertEqual(_verify(dossier, _narrative(text))["status"], PASS)


# ════════════════════════════════════════════════════════ §26 omissioni

class CriticalOmissionTest(unittest.TestCase):

    def test_ambiguity_omitted_fails(self) -> None:
        dossier = _synthetic_dossier(status="AMBIGUOUS", direction="NO_DOCUMENT_SIGNAL",
                                     bucket="WARNING_BUCKET",
                                     warnings=["NO_VALIDATED_ENRICHMENT_AVAILABLE"])
        text = ("La candidate PANITUMUMAB è associata nel grafo al caso. "
                "Non è stata trovata alcuna citazione validata.")
        result = _verify(dossier, _narrative(text))
        self.assertEqual(result["status"], FAIL)
        self.assertIn(REASON_CRITICAL_OMISSION, result["reason_codes"])
        self.assertIn("AMBIGUITY_NOT_STATED",
                      [o["omitted"] for o in result["critical_omissions"]])

    def test_missing_validated_quote_omitted_fails(self) -> None:
        dossier = _synthetic_dossier(status="AMBIGUOUS", direction="NO_DOCUMENT_SIGNAL",
                                     bucket="WARNING_BUCKET",
                                     warnings=["NO_VALIDATED_ENRICHMENT_AVAILABLE"])
        text = "La relazione con PANITUMUMAB rimane ambigua."
        result = _verify(dossier, _narrative(text))
        self.assertIn("NO_VALIDATED_QUOTE_NOT_STATED",
                      [o["omitted"] for o in result["critical_omissions"]])

    def test_does_not_support_omitted_fails(self) -> None:
        dossier = _synthetic_dossier(status="AMBIGUOUS", direction="SOURCE_DOES_NOT_SUPPORT",
                                     bucket="WARNING_BUCKET",
                                     warnings=["SOURCE_POLARITY_DOES_NOT_SUPPORT"])
        text = "La relazione con PANITUMUMAB rimane incerta."
        result = _verify(dossier, _narrative(text))
        self.assertEqual(result["status"], FAIL)
        self.assertIn(REASON_NEGATION_LOST, result["reason_codes"])

    def test_technical_warnings_need_not_be_narrated(self) -> None:
        """§15: non ogni warning tecnico deve comparire nella prosa."""
        dossier = _synthetic_dossier(
            status="DIRECT", direction="SUPPORTED",
            warnings=["SOME_ENRICHMENTS_ACCEPTED_WITH_WARNING"],
            quote="patients responded to panitumumab")
        text = "La candidate PANITUMUMAB è associata nel grafo al caso."
        self.assertEqual(_verify(dossier, _narrative(text))["status"], PASS)

    def test_documentary_absence_variants_are_recognised(self) -> None:
        """Regressione dalla prima run LIVE del benchmark.

        Il modello aveva scritto «non è stato trovato un segnale documentale
        esplicito»: dichiara correttamente l'assenza di citazione validata, ma il
        lexicon conosceva solo «supporto documentale» e la contava come omissione.
        Era un falso positivo del verifier, non un'infedeltà del modello.
        """
        dossier = _synthetic_dossier(status="AMBIGUOUS", direction="NO_DOCUMENT_SIGNAL",
                                     bucket="WARNING_BUCKET",
                                     warnings=["NO_VALIDATED_ENRICHMENT_AVAILABLE"])
        for phrase in (
            "non è stato trovato un segnale documentale esplicito",
            "non è stato trovato supporto documentale",
            "nessun riscontro documentale disponibile",
            "non è stata trovata alcuna citazione validata",
            "il modello si è astenuto",
        ):
            with self.subTest(phrase=phrase):
                text = f"La relazione rimane ambigua e {phrase}."
                self.assertEqual(_verify(dossier, _narrative(text))["status"], PASS, phrase)

    def test_a_narrative_that_omits_everything_still_fails(self) -> None:
        """Controprova: la variante aggiunta non ha allentato il controllo."""
        dossier = _synthetic_dossier(status="AMBIGUOUS", direction="NO_DOCUMENT_SIGNAL",
                                     bucket="WARNING_BUCKET",
                                     warnings=["NO_VALIDATED_ENRICHMENT_AVAILABLE"])
        result = _verify(dossier, _narrative("La candidate PANITUMUMAB compare nel grafo."))
        self.assertEqual(result["status"], FAIL)
        self.assertIn(REASON_CRITICAL_OMISSION, result["reason_codes"])

    def test_critical_and_technical_warnings_are_declared(self) -> None:
        self.assertIn("NO_VALIDATED_ENRICHMENT_AVAILABLE", NARRATIVE_CRITICAL_WARNINGS)
        self.assertNotIn("SOME_ENRICHMENTS_ACCEPTED_WITH_WARNING", NARRATIVE_CRITICAL_WARNINGS)


# ═════════════════════════════════════════════════════════ §27 determinismo

class DeterminismTest(unittest.TestCase):

    def test_same_inputs_produce_the_same_result(self) -> None:
        dossier = _synthetic_dossier(quote="patients responded to panitumumab")
        narrative = _narrative('La candidate PANITUMUMAB è associata nel grafo. '
                               'Citazione: "patients responded to panitumumab".')
        first = _verify(dossier, narrative)
        second = _verify(dossier, narrative)
        self.assertEqual(result_fingerprint(first), result_fingerprint(second))
        self.assertEqual(first["reason_codes"], second["reason_codes"])

    def test_narrator_input_hash_is_stable(self) -> None:
        dossier = _synthetic_dossier()
        self.assertEqual(build_narrator_input(dossier)["narrator_input_hash"],
                         build_narrator_input(dossier)["narrator_input_hash"])

    def test_failure_result_is_also_deterministic(self) -> None:
        dossier = _synthetic_dossier(status="AMBIGUOUS", direction="NO_DOCUMENT_SIGNAL",
                                     bucket="WARNING_BUCKET")
        narrative = _narrative("La candidate è fortemente supportata. Si raccomanda EGFR.")
        first, second = _verify(dossier, narrative), _verify(dossier, narrative)
        self.assertEqual(result_fingerprint(first), result_fingerprint(second))
        self.assertEqual(first["status"], FAIL)

    def test_verifier_declares_its_versions(self) -> None:
        result = _verify(_synthetic_dossier(), _narrative("testo"))
        self.assertEqual(result["verifier_version"], VERIFIER_VERSION)
        self.assertTrue(result["lexicon_version"])

    def test_absent_narrative_fails_without_crashing(self) -> None:
        dossier = _synthetic_dossier()
        result = verify_narrative(dossier, build_narrator_input(dossier), None)
        self.assertEqual(result["status"], FAIL)
        self.assertIn("NARRATIVE_ABSENT", result["reason_codes"])


# ══════════════════════════════════════════ §3-4 projection: cosa NON passa

class ProjectionExclusionTest(unittest.TestCase):

    def test_rejected_quotes_never_reach_the_narrator(self) -> None:
        dossier = _synthetic_dossier(
            quote="valid quote text here",
            rejected_quote="fabricated quote that was rejected")
        narrator_input = build_narrator_input(dossier)
        quotes = [q["quote"] for c in narrator_input["candidates"]
                  for q in c["validated_quotes"]]
        self.assertIn("valid quote text here", quotes)
        self.assertNotIn("fabricated quote that was rejected", quotes)
        self.assertNotIn("fabricated", json.dumps(narrator_input))

    def test_excluded_papers_never_reach_the_narrator(self) -> None:
        dossier = _synthetic_dossier()
        dossier["candidate_therapies"][0]["document_support"]["excluded_papers"] = [
            {"bundle_id": "EB-ESCLUSO", "document_id": "pmid:999", "reason_codes": ["X"]}]
        self.assertNotIn("EB-ESCLUSO", json.dumps(build_narrator_input(dossier)))

    def test_validator_internals_never_reach_the_narrator(self) -> None:
        dossier = _synthetic_dossier(quote="valid quote text here")
        dossier["candidate_therapies"][0]["validation_results"] = [
            {"paper_id": "EB-1", "outcome": "ENRICHMENT_V2_ACCEPTED",
             "reason_codes": ["INTERNO_DA_NON_ESPORRE"]}]
        self.assertNotIn("INTERNO_DA_NON_ESPORRE", json.dumps(build_narrator_input(dossier)))

    def test_projection_carries_status_and_warnings(self) -> None:
        dossier = _synthetic_dossier(status="AMBIGUOUS", direction="NO_DOCUMENT_SIGNAL",
                                     warnings=["NO_VALIDATED_ENRICHMENT_AVAILABLE"])
        candidate = build_narrator_input(dossier)["candidates"][0]
        self.assertEqual(candidate["canonical_status"], "AMBIGUOUS")
        self.assertIn("NO_VALIDATED_ENRICHMENT_AVAILABLE", candidate["critical_warnings"])
        self.assertFalse(candidate["expresses_support"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

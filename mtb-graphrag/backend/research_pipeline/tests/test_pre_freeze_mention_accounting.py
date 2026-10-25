"""Every parsed mention has an accepted or explicitly rejected audit outcome."""

from backend.research_pipeline.casecontext.pipeline import run
from backend.research_pipeline.casecontext.pipeline import build_retrieval_case_context
from backend.research_pipeline.retrieval.kg_retrieval import _case_diseases
from backend.research_pipeline.retrieval.kg_retrieval import _match_candidate


def test_all_five_mention_categories_reconcile() -> None:
    text = "Lung cancer, EGFR L858R; erlotinib. Trial NCT12345678 and Guardant360 CDx."
    context = {
        "diseases": [{"value": "Lung cancer", "source_spans": [{"quote": "Lung cancer"}]}],
        "biomarkers": [{"gene": "EGFR", "alteration": "L858R",
                         "gene_source_spans": [{"quote": "EGFR"}],
                         "alteration_source_spans": [{"quote": "L858R"}]}],
        "interventions": [{"name": "erlotinib", "role": "TARGET",
                           "source_spans": [{"quote": "erlotinib"}]}],
        "trial_mentions": [
            {"nct_id": "NCT12345678", "nct_id_quote": "NCT12345678"},
            {"nct_id": "NCT99999999", "nct_id_quote": "NCT99999999"},
        ],
        "companion_diagnostic_mentions": [
            {"name": "Guardant360 CDx", "name_quote": "Guardant360 CDx"},
            {"name": "Invented CDx", "name_quote": "Invented CDx"},
        ],
    }
    chain = run(text, context)
    accounting = chain["mention_accounting"]
    for category in ("disease", "biomarker", "intervention", "trial", "companion_diagnostic"):
        row = accounting[category]
        assert row["parsed"] == row["accepted"] + row["rejected"]
        assert all(entry["reason"] for entry in row["excluded"])
    assert accounting["trial"]["parsed"] == 2
    assert accounting["trial"]["accepted"] == 1
    assert accounting["companion_diagnostic"]["rejected"] == 1


def test_uncertain_trial_is_counted_but_excluded_from_positive_retrieval() -> None:
    text = "Possible trial NCT12345678 for EGFR cancer."
    context = {"trial_mentions": [{"nct_id": "NCT12345678", "nct_id_quote": "NCT12345678"}]}
    chain = run(text, context)
    row = chain["mention_accounting"]["trial"]
    assert row["parsed"] == 1
    assert row["accepted"] == 1
    assert row["retrieval_used"] == []
    assert row["retrieval_excluded"][0]["reason"] == "ASSERTION_NOT_POSITIVE"
    projected = build_retrieval_case_context(context, chain["mentions"])
    assert projected["trial_mentions"] == []


def test_historical_disease_cannot_reenter_via_scalar_fallback() -> None:
    text = "Prior breast cancer; current EGFR L858R lung cancer."
    context = {
        "diseases": [{
            "value": "breast cancer", "clinical_role": "HISTORY",
            "source_spans": [{"quote": "breast cancer"}],
        }],
        "disease": {"raw_value": "breast cancer"},
    }
    chain = run(text, context)
    projected = build_retrieval_case_context(context, chain["mentions"])
    assert projected["diseases"][0]["clinical_role"] == "HISTORY"
    assert _case_diseases(projected) == []


def test_no_gene_variant_detected_is_not_a_positive_retrieval_anchor() -> None:
    raw = "Lung cancer. No EGFR L858R detected. Erlotinib."
    parsed = {
        "biomarkers": [{
            "gene": "EGFR", "alteration": "L858R",
            "gene_source_spans": [{"quote": "No EGFR L858R detected"}],
            "alteration_source_spans": [{"quote": "No EGFR L858R detected"}],
        }],
    }
    chain = run(raw, parsed)
    projected = build_retrieval_case_context(parsed, chain["mentions"])
    assert projected["biomarkers"] == []
    assert projected["negated_biomarkers"] == [{"gene": "EGFR", "alteration": "L858R"}]
    matched, reasons = _match_candidate(projected, {
        "candidate_id": "NEGATED-PROBE",
        "biomarkers": [{"label": "EGFR", "type": "Gene"},
                       {"label": "L858R", "type": "Variant", "gene": "EGFR", "alteration": "L858R"}],
        "disease": [{"label": "Lung cancer"}],
        "interventions": [{"label": "erlotinib"}],
    })
    assert not matched and "NEGATED_BIOMARKER_CONFLICT" in reasons
    assert all(item["rejection_reason"] == "MENTION_NEGATED"
               for item in chain["mentions"] if item["entity_type"] in {"GENE", "ALTERATION"})


def test_historical_cue_cannot_override_explicit_absent_alteration() -> None:
    from backend.research_pipeline.casecontext.mentions import assertion_status_for

    assert assertion_status_for(
        "Prior testing showed EGFR L858R was not detected.", "L858R", "ALTERATION",
    ) == "NEGATED"
    assert assertion_status_for(
        "Previously, EGFR testing was negative.", "EGFR", "GENE",
    ) == "NEGATED"

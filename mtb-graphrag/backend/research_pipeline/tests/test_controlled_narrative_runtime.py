from unittest.mock import patch

from backend.research_pipeline.narrative import controlled_narrator as cn
from backend.research_pipeline.tests.test_narrator_does_not_regress_runtime import _run, _stages


def test_unavailable_model_has_separately_verified_deterministic_explanation():
    def unavailable(case_id, source):
        with patch.object(cn.tr, "post_with_infra_retry", return_value=(401, {}, None, 0)):
            return cn.call_controlled_narrator(case_id, source)

    run, _ = _run(call_narrator_fn=unavailable)
    result = _stages(run)["stage_15_narrative_verifier"].output_preview
    assert result["verification"]["status"] == "FAIL"
    assert result["verified_narrative"] is None
    assert result["deterministic_verification"]["status"] == "PASS"
    assert result["presentation_mode"] == "DETERMINISTIC_NARRATIVE_FALLBACK"
    assert result["explanation_available"] is True
    assert result["model_narrative_verified"] is False
    assert result["deterministic_narrative"]["generation_origin"] == "DETERMINISTIC_FALLBACK"
    generation = _stages(run)["stage_14_narrator"].output_preview
    assert generation["attempts"][0]["status_code"] == 401
    assert generation["token_usage_complete"] is False


def test_tampered_fallback_is_never_presented():
    def hostile(case_id, source):
        with patch.object(cn.tr, "post_with_infra_retry", return_value=(401, {}, None, 0)):
            result = cn.call_controlled_narrator(case_id, source)
        result["deterministic_fallback"]["narrative_summary"] += " Il paziente deve ricevere una terapia."
        return result

    run, _ = _run(call_narrator_fn=hostile)
    result = _stages(run)["stage_15_narrative_verifier"].output_preview
    assert result["deterministic_verification"]["status"] == "FAIL"
    assert result["presentation_mode"] == "STRUCTURED_DOSSIER_FALLBACK"
    assert result["deterministic_narrative"] is None
    assert result["explanation_available"] is False


def test_presentation_failure_does_not_advertise_available_fallback():
    def unavailable(case_id, source):
        with patch.object(cn.tr, "post_with_infra_retry", return_value=(401, {}, None, 0)):
            return cn.call_controlled_narrator(case_id, source)

    with patch("backend.research_pipeline.narrative.presentation.build_narrative_presentation",
               side_effect=ValueError("unavailable presentation")):
        run, _ = _run(call_narrator_fn=unavailable)
    result = _stages(run)["stage_15_narrative_verifier"].output_preview
    assert result["explanation_available"] is False
    assert result["deterministic_narrative"] is None

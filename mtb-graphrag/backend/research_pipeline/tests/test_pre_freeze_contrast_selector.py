"""Same-relation contrary passages must remain available to the Reader."""

from __future__ import annotations

from backend.research_pipeline.experimental import sourceunit_selector as selector


CANDIDATE = {
    "candidate_id": "contrast-probe",
    "direction": "Supports",
    "predicate": "targets_drug",
    "disease": [{"label": "lung cancer"}],
    "biomarkers": [{"gene": "EGFR", "alteration": "L858R", "type": "Variant"}],
    "interventions": [{"label": "erlotinib"}],
}


def unit(source_unit_id: str, text: str, unit_type: str = "FULLTEXT_SENTENCE") -> dict:
    return {
        "source_unit_id": source_unit_id,
        "document_id": "pmid:1",
        "unit_type": unit_type,
        "text": text,
        "section": "Results",
    }


def select(units: list[dict], top_k: int = 5) -> selector.SourceUnitSelectionResult:
    selection = selector.SourceUnitSelectionInput.from_candidate(CANDIDATE, "pmid:1", units)
    return selector.select(selection, top_k=top_k)


def test_same_entities_opposite_polarity_are_both_selected() -> None:
    result = select([
        unit("positive", "EGFR L858R was associated with response to erlotinib in lung cancer."),
        unit("negative", "EGFR L858R did not support response to erlotinib in lung cancer."),
    ])
    assert set(result.selected_source_unit_ids) == {"positive", "negative"}
    contrary = next(row for row in result.ranked_source_units if row.source_unit_id == "negative")
    assert contrary.polarity_relevance == "POLARITY_OPPOSITE_BUT_RELEVANT"
    assert contrary.exclusion_reason == ""


def test_contrary_passage_gets_a_slot_when_five_supporting_passages_rank_higher() -> None:
    positives = [
        unit(f"positive-{index}",
             f"Results in cohort {index}: EGFR L858R was associated with response to erlotinib "
             f"in lung cancer after treatment cycle {index}.")
        for index in range(6)
    ]
    negative = unit(
        "negative",
        "EGFR L858R did not support response to erlotinib in lung cancer.",
    )
    result = select([*positives, negative], top_k=5)
    assert "negative" in result.selected_source_unit_ids
    assert any(value.startswith("positive-") for value in result.selected_source_unit_ids)
    assert len(result.selected_source_unit_ids) == 5


def test_wrong_variant_is_not_rescued_as_contrast() -> None:
    result = select([
        unit("wrong", "EGFR G719A did not support response to erlotinib in lung cancer."),
        unit("right", "EGFR L858R was associated with response to erlotinib in lung cancer."),
    ])
    assert result.selected_source_unit_ids == ("right",)
    wrong = next(row for row in result.ranked_source_units if row.source_unit_id == "wrong")
    assert wrong.exclusion_reason == "EXPLICIT_ALTERATION_MISMATCH"


def test_non_small_cell_quote_does_not_get_small_cell_disease_bonus() -> None:
    candidate = {**CANDIDATE, "disease": [{"label": "small cell lung cancer"}]}
    selection = selector.SourceUnitSelectionInput.from_candidate(candidate, "pmid:1", [
        unit("wrong-disease", "EGFR L858R showed sensitivity to erlotinib in non-small-cell lung cancer."),
    ])
    features = selector.match_features(selection.source_units[0]["text"], selection)
    assert features["disease"] == ()


def test_controlled_passage_recall_at_one_three_and_five() -> None:
    passages = [
        unit("positive", "EGFR L858R showed sensitivity to erlotinib in lung cancer."),
        unit("contradictory", "EGFR L858R did not predict response to erlotinib in lung cancer."),
        unit("caveat", "EGFR L858R response to erlotinib in lung cancer was observed, although the cohort was small."),
        unit("disease", "In lung cancer, EGFR L858R was associated with response to erlotinib."),
        unit("variant", "EGFR L858R, but not EGFR G719A, predicted response to erlotinib in lung cancer."),
        unit("methods", "Methods: EGFR L858R and erlotinib were measured in lung cancer specimens."),
        unit("duplicate", "EGFR L858R showed sensitivity to erlotinib in lung cancer.", "FULLTEXT_PARAGRAPH"),
    ]
    passages[5]["section"] = "Methods"
    relevant = {"positive", "contradictory", "caveat", "disease", "variant"}
    recalls = {}
    for k in (1, 3, 5):
        selected = set(select(passages, top_k=k).selected_source_unit_ids)
        # The paragraph and sentence contain identical evidence. Choosing the
        # paragraph representative must not be scored as a retrieval miss.
        if "duplicate" in selected:
            selected.remove("duplicate")
            selected.add("positive")
        recalls[k] = len(selected & relevant) / len(relevant)
    assert recalls[1] >= 0.2
    assert recalls[3] >= 0.4
    assert recalls[5] >= 0.8
    assert "contradictory" in select(passages, top_k=5).selected_source_unit_ids

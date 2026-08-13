from pathlib import Path

import pytest

from evaluation.final_evaluation_harness.common.operational_runner import (
    CanonicalOperationalRunner,
    OperationalArtifactError,
)
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol


def _runner():
    protocol = load_protocol()
    return CanonicalOperationalRunner(
        protocol,
        Path(__file__).parents[3] / "research_frozen_artifacts" / "operational_v2",
    )


def test_all_nine_bindings_materialize_without_synthetic_fields():
    runner = _runner()
    plans = runner.materialize_all()
    assert len(plans) == 9
    assert all(plan.synthetic_fields == [] for plan in plans)
    assert all(plan.ambiguous_references == [] for plan in plans)


def test_missing_corpus_artifact_fails_closed(tmp_path):
    protocol = load_protocol()
    runner = CanonicalOperationalRunner(protocol, tmp_path)
    with pytest.raises(OperationalArtifactError, match="missing artifact"):
        runner.materialize("A_cache_hit")


def test_document_runner_uses_isolated_cache_and_records_component_path():
    result = _runner().run("A_cache_hit")
    assert result.scenario_id == "A_cache_hit"
    assert result.component_path == "AuthorizedDocumentCache.resolve_pmid"
    assert result.observables["cache_hit"] is True
    assert result.observables["network_fetch_count"] == 0
    assert result.property_test_pass is True
    assert result.synthetic_query_count == 0


@pytest.mark.parametrize(
    ("scenario_id", "expected"),
    [
        ("C_pmid_only_to_pmcid", "PMC4157820"),
        ("D_pmc_fulltext", "PMC_XML_AVAILABLE"),
        ("E_pmc_unavailable_abstract_degradation", "DOCUMENT_DEGRADED_TO_ABSTRACT"),
        ("G_document_unavailable", "PMID_NOT_FOUND"),
        ("H_parser_failure_fixture", "PARSER_FAILED"),
        ("I_selector_failure_fixture", "SOURCEUNIT_SELECTION_FAILED"),
    ],
)
def test_component_level_routing_evaluates_frozen_property(scenario_id, expected):
    result = _runner().run(scenario_id)
    assert expected in result.actual_observable
    assert result.property_test_pass is True


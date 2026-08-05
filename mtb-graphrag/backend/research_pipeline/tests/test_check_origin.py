"""Origine dichiarata dei controlli deterministici.

La UI mostra quattro assi di support mask affiancati, e senza un'origine
esplicita sono indistinguibili: `disease: SUPPORTED` sembra calcolato dai gate
esattamente come `direction: SUPPORTED`, mentre il primo è ereditato dal match
strutturale dello stage 5 e il secondo è l'unico davvero deciso allo stage 11.
Questi test fissano quella distinzione.
"""

from __future__ import annotations

import pytest

from backend.research_pipeline.determinism import check_origin as co


def _mask(**overrides: str) -> dict[str, str]:
    base = {"disease": "SUPPORTED", "biomarker": "SUPPORTED",
            "intervention": "SUPPORTED", "direction": "SUPPORTED"}
    return {**base, **overrides}


class TestAxisOrigin:
    def test_disease_and_biomarker_are_inherited_not_recomputed(self):
        checks = {c.check_id: c for c in co.checks_for(_mask())}
        for axis in ("disease", "biomarker"):
            assert checks[axis].source == "INHERITED_VERIFIED_RESULT"
            assert checks[axis].source_stage == "stage_5_kg_retrieval"

    def test_intervention_and_direction_are_computed_in_the_gate_stage(self):
        checks = {c.check_id: c for c in co.checks_for(_mask())}
        for axis in ("intervention", "direction"):
            assert checks[axis].source == "COMPUTED_HERE"
            assert checks[axis].source_stage == "stage_11_deterministic_gates"

    def test_axis_result_is_carried_verbatim_from_the_mask(self):
        checks = {c.check_id: c for c in co.checks_for(_mask(direction="CONTRADICTED"))}
        assert checks["direction"].result == "CONTRADICTED"

    def test_not_applicable_axis_is_labelled_as_such(self):
        """`direction` sotto THERAPY_DISCOVERY non è un controllo fallito."""
        checks = {c.check_id: c for c in co.checks_for(_mask(direction="NOT_APPLICABLE"))}
        assert checks["direction"].source == "NOT_APPLICABLE"
        assert checks["direction"].result == "NOT_APPLICABLE"

    def test_missing_axis_is_reported_rather_than_silently_dropped(self):
        checks = {c.check_id: c for c in co.checks_for({"disease": "SUPPORTED"})}
        assert checks["biomarker"].result is None
        assert checks["biomarker"].reason_code == "AXIS_ABSENT_FROM_SUPPORT_MASK"


class TestUnimplementedChecks:
    def test_design_checks_without_an_implementation_are_declared(self):
        checks = {c.check_id: c for c in co.checks_for(_mask())}
        for check_id in co.NOT_IMPLEMENTED_CHECKS:
            assert checks[check_id].source == "NOT_IMPLEMENTED"
            assert checks[check_id].result is None

    def test_an_unimplemented_check_never_claims_a_source_stage(self):
        """Un controllo non implementato con uno stage di origine si leggerebbe
        come eseguito da quello stage."""
        for check in co.checks_for(_mask()):
            if check.source == "NOT_IMPLEMENTED":
                assert check.source_stage is None

    def test_legacy_v3_gates_are_not_imported_as_executed(self):
        """I gate della vecchia V3 non devono comparire come eseguiti qui."""
        executed = {c.check_id for c in co.checks_for(_mask())
                    if c.source in ("COMPUTED_HERE", "INHERITED_VERIFIED_RESULT")}
        assert executed == {"disease", "biomarker", "intervention", "direction"}


class TestContract:
    def test_every_check_declares_a_version(self):
        assert all(c.version == co.CHECK_VERSION for c in co.checks_for(_mask()))

    def test_every_check_declares_a_known_source(self):
        assert all(c.source in co.CHECK_SOURCES for c in co.checks_for(_mask()))

    def test_serialisation_is_json_safe(self):
        for check in co.checks_for(_mask()):
            payload = check.to_dict()
            assert set(payload) == {
                "check_id", "label", "source", "result", "reason_code",
                "source_stage", "evidence_ref", "version",
            }
            assert all(not isinstance(v, (set, tuple)) for v in payload.values())

    def test_unknown_source_is_rejected_at_construction(self):
        with pytest.raises(ValueError):
            co.DeterministicCheck(
                check_id="x", label="x", source="INVENTED",
                result=None, reason_code="X", source_stage=None,
                evidence_ref=None, version=co.CHECK_VERSION,
            )

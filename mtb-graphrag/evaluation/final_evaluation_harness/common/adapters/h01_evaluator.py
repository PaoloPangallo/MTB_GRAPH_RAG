"""Post-inference adapter for the frozen H01 declarative evaluator."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


class H01EvaluatorAdapter:
    def __init__(self, repository_root: Path, contract_sha256: str) -> None:
        self.repository_root = repository_root
        self.contract_sha256 = contract_sha256
        root = repository_root / "evaluation" / "final_protocol_v1_6_candidates" / "rq4"
        path = root / "validate_h01_contract.py"
        spec = importlib.util.spec_from_file_location("frozen_h01_validator", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("H01_VALIDATOR_UNAVAILABLE")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._module = module
        self._root = root
        self._contract = {
            "normalization": json.loads((root / "heldout_normalization_contract.json").read_text(encoding="utf-8")),
            "binding": json.loads((root / "raw_observation_binding_contract.json").read_text(encoding="utf-8")),
            "hard": json.loads((root / "hard_observable_contract.json").read_text(encoding="utf-8")),
        }

    def evaluate(self, raw_pipeline_run: dict[str, Any], challenge: dict[str, Any]) -> dict[str, Any]:
        raw = dict(raw_pipeline_run)
        observations = self._module.derive_observations(raw, challenge, self._contract["binding"])
        return {
            "contract_sha256": self.contract_sha256,
            "observations": observations,
            "challenge_case_id": challenge.get("case_id"),
            "phase_1_raw_immutable": True,
        }

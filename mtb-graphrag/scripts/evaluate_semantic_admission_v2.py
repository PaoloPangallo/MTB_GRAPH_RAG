"""One-pass development comparison; never claims independent clinical gold."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.research_pipeline.enrichment import semantic_alignment, transport
from backend.research_pipeline.enrichment.document_verification import admit
from backend.research_pipeline.enrichment.semantic_contract import POLICY_VERSION
from backend.research_pipeline.pipeline import CallBudget


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row["technical_success"]]
    supported = [row for row in rows if row["reference_admission"] == "DOCUMENT_SUPPORTED"]
    non_support = [row for row in rows if row["reference_admission"] != "DOCUMENT_SUPPORTED"]
    correct = sum(row["reference_admission"] == row["observed_admission"] for row in completed)
    return {
        "evaluation_kind": "DEVELOPMENT_ASSISTED_REFERENCE", "independent_gold": False,
        "clinical_validation": False, "inspected_cases": True,
        "units_attempted": len(rows), "technical_completed": len(completed),
        "technical_failed": len(rows) - len(completed),
        "false_document_supported": sum(row["technical_success"] and row["observed_admission"] == "DOCUMENT_SUPPORTED"
                                        for row in non_support),
        "non_support_reference_n": len(non_support),
        "direct_support_preserved": sum(row["technical_success"] and row["observed_admission"] == "DOCUMENT_SUPPORTED"
                                        for row in supported),
        "direct_support_reference_n": len(supported),
        "admission_correct_completed": correct,
        "admission_accuracy_completed": correct / len(completed) if completed else None,
    }


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify_attempt(last: dict[str, Any], gep: dict[str, Any]) -> tuple[str, bool]:
    try:
        outcome, _, args, _ = transport.transport_result(
            last["status_code"], last["response"], last["error_type"], semantic_alignment.TOOL_NAME,
            lambda item: [error.message for error in Draft7Validator(semantic_alignment.OUTPUT_SCHEMA).iter_errors(item)])
    except (AttributeError, TypeError, ValueError):
        return "MALFORMED_PROVIDER_ENVELOPE", False
    if args is None or outcome != "FORCED_TOOL_VALID":
        return outcome, False
    try:
        semantic_alignment.validate_output(args, gep)
    except ValueError:
        return "SEMANTIC_OUTPUT_INVALID", False
    return outcome, True


def write(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def run(output: Path) -> dict[str, Any]:
    source = ROOT / "evaluation/final_results_minimal_20260930"
    manifest = json.loads((source / "execution_manifest.json").read_text(encoding="utf-8"))
    for filename, expected in manifest["artifact_hashes"].items():
        if digest(source / filename) != expected:
            raise ValueError(f"FROZEN_ARTIFACT_HASH_MISMATCH:{filename}")
    references = json.loads((source / "SEMANTIC_RESULTS.json").read_text(encoding="utf-8"))
    if len(references) != 12 or len({row["case_id"] for row in references}) != 12:
        raise ValueError("FROZEN_REFERENCE_UNIT_MISMATCH")
    inputs = [json.loads((source / f"MIN-{index:02}.json").read_text(encoding="utf-8"))[
        "result"]["document_verification"] for index in range(18, 30)]
    output.mkdir(parents=True, exist_ok=False)
    frozen = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_kind": "DEVELOPMENT_ASSISTED_REFERENCE", "independent_gold": False,
        "clinical_validation": False, "inspected_cases": True, "semantic_reruns": 0,
        "structural_inputs": "RECORDED_NOT_RECOMPUTED", "reader_calls": 0,
        "prompt_version": semantic_alignment.PROMPT_VERSION, "policy_version": POLICY_VERSION,
        "model": transport.model_name(),
        "prompt_sha256": hashlib.sha256(semantic_alignment.SYSTEM_PROMPT.encode()).hexdigest(),
        "schema_sha256": hashlib.sha256(json.dumps(semantic_alignment.OUTPUT_SCHEMA, sort_keys=True).encode()).hexdigest(),
        "code_hashes": {name: digest(ROOT / name) for name in (
            "backend/research_pipeline/enrichment/semantic_alignment.py",
            "backend/research_pipeline/enrichment/semantic_contract.py",
            "backend/research_pipeline/enrichment/document_verification.py",
            "backend/research_pipeline/enrichment/transport.py",
            "backend/research_pipeline/llm_config.py", "scripts/evaluate_semantic_admission_v2.py")},
        "transport_policy": {"infra_retry_limit": transport.MAX_RETRIES_INFRA_ONLY,
                             "semantic_retry_limit": 0},
        "input_hashes": {f"MIN-{index:02}.json": digest(source / f"MIN-{index:02}.json") for index in range(18, 30)},
        "reference_sha256": digest(source / "SEMANTIC_RESULTS.json"),
        "mapping": [{"unit_id": f"MIN-{index:02}", "case_id": ref["case_id"]}
                    for index, ref in zip(range(18, 30), references)],
    }
    write(output / "manifest.json", frozen)
    budget = CallBudget(12)
    records = []
    real_post = transport.requests.post
    # No credentials/headers are recorded. Capture every actual HTTP attempt,
    # including infrastructure retries, without changing the provider policy.
    from backend.research_pipeline import llm_config
    secret = llm_config.api_key()

    def sanitize(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: sanitize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        if isinstance(value, str) and secret:
            return value.replace(secret, "REDACTED")
        return value

    for index, (verification, reference) in enumerate(zip(inputs, references), start=18):
        attempts: list[dict[str, Any]] = []
        unit_id = f"MIN-{index:02}"

        def capture_post(url: str, **kwargs: Any) -> Any:
            started = time.perf_counter()
            attempt: dict[str, Any] = {"request": kwargs.get("json"), "status_code": None,
                       "response": None, "error_type": None}
            try:
                response = real_post(url, **kwargs)
                attempt["status_code"] = response.status_code
                try:
                    attempt["response"] = response.json()
                except ValueError:
                    attempt["response"] = {"raw_text": response.text}
                return response
            except Exception as error:
                attempt["error_type"] = type(error).__name__
                raise
            finally:
                attempt["latency_ms"] = (time.perf_counter() - started) * 1000
                attempts.append(attempt)
                write(output / f"{unit_id}-http-{len(attempts)}.json", sanitize(attempt))

        with patch.object(transport.requests, "post", capture_post):
            semantic = semantic_alignment.call_semantic_alignment(
                budget, reference["case_id"], verification["target_snapshot"], verification["GEP_snapshot"])
        technical_success = False
        transport_outcome = "NO_HTTP_ATTEMPT"
        if attempts:
            transport_outcome, technical_success = classify_attempt(attempts[-1], verification["GEP_snapshot"])
        result = admit(verification, semantic)
        record = {"unit_id": unit_id, "case_id": reference["case_id"],
                  "technical_success": technical_success, "transport_result": transport_outcome,
                  "http_attempts": len(attempts), "reference_admission": reference["ref_admission"],
                  "historical_admission": reference["observed_admission"],
                  "observed_admission": result["final_admission"], "verification": result}
        write(output / f"{unit_id}.json", sanitize(record))
        records.append(record)
        print(json.dumps({key: record[key] for key in ("unit_id", "technical_success", "observed_admission")}), flush=True)
    report = {**summarize(records), "logical_model_calls": budget.used,
              "actual_http_attempts": sum(row["http_attempts"] for row in records),
              "token_usage_source": "All raw HTTP attempts retained; no invented totals"}
    write(output / "report.json", report)
    print(json.dumps(report), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)

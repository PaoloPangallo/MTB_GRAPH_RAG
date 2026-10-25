"""Regression tests for bootstrapping the current research runtime."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

APP_DIRECTORY = Path(__file__).resolve().parents[3]


def test_default_run_store_imports_without_family_cap() -> None:
    env = dict(os.environ)
    env.pop("RESEARCH_PIPELINE_MAX_CANDIDATES_PER_FAMILY", None)
    result = subprocess.run(
        [sys.executable, "-B", "-c", "import backend.research_pipeline.run_store"],
        env=env,
        cwd=APP_DIRECTORY,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_model_call_budget_is_independent_of_retrieval_cap() -> None:
    env = dict(os.environ)
    env.pop("RESEARCH_PIPELINE_MAX_CANDIDATES_PER_FAMILY", None)
    env["RESEARCH_PIPELINE_MAX_LLM_CALLS_PER_RUN"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "from backend.research_pipeline.run_store import MAX_LLM_CALLS_PER_RUN; "
            "from backend.research_pipeline.pipeline import CallBudget; "
            "budget = CallBudget(MAX_LLM_CALLS_PER_RUN); "
            "budget.spend('PARSER', 'case'); "
            "print(budget.maximum, budget.used)",
        ],
        env=env,
        cwd=APP_DIRECTORY,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1 1"


def test_default_api_import_registers_research_and_legacy_routes() -> None:
    env = dict(os.environ)
    env.pop("RESEARCH_PIPELINE_MAX_CANDIDATES_PER_FAMILY", None)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "from backend.api.main import app; "
            "print('\\n'.join(sorted(route.path for route in app.routes)))",
        ],
        env=env,
        cwd=APP_DIRECTORY,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    paths = set(result.stdout.splitlines())
    assert "/api/v1/research/pipeline/runs" in paths
    assert "/api/v1/analyze" in paths


def test_health_route_bootstraps_without_legacy_model_loading() -> None:
    from fastapi.testclient import TestClient

    from backend.api.main import app

    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

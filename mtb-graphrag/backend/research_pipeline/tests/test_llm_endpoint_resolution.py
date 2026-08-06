"""Risoluzione dell'endpoint LLM del research runtime.

Il default di ``backend/pipeline/llm`` (``https://api.ollama.com``) risponde
HTTP 405 sul percorso OpenAI-compatible: con quel default tutte le chiamate del
parser falliscono. Quel modulo è sigillato dal manifest dell'esperimento finale,
quindi il default corretto vive in ``llm_config``.

Nessun test effettua chiamate di rete.
"""

from __future__ import annotations

import pytest

from backend.research_pipeline import llm_config


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("RESEARCH_PIPELINE_LLM_BASE_URL", "OLLAMA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RESEARCH_PIPELINE_LLM_API_KEY", "test-key")


def test_default_host_is_the_one_that_serves_the_path():
    assert llm_config.base_url() == "https://ollama.com"
    assert llm_config.base_url() != "https://api.ollama.com"


def test_final_url_is_built_once_and_completely():
    endpoint = llm_config.resolve_endpoint()
    assert endpoint.url == "https://ollama.com/v1/chat/completions"


def test_explicit_ollama_base_url_wins_over_default(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://example.test")
    assert llm_config.resolve_endpoint().url == "https://example.test/v1/chat/completions"


def test_run_override_wins_over_everything(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://example.test")
    monkeypatch.setenv("RESEARCH_PIPELINE_LLM_BASE_URL", "http://localhost:11434")
    assert llm_config.resolve_endpoint().url == "http://localhost:11434/v1/chat/completions"


def test_trailing_slash_does_not_duplicate_separator(monkeypatch):
    monkeypatch.setenv("RESEARCH_PIPELINE_LLM_BASE_URL", "https://ollama.com/")
    assert llm_config.resolve_endpoint().url == "https://ollama.com/v1/chat/completions"


def test_known_bad_host_raises_instead_of_falling_back(monkeypatch):
    monkeypatch.setenv("RESEARCH_PIPELINE_LLM_BASE_URL", "https://api.ollama.com")
    with pytest.raises(llm_config.LLMEndpointMisconfigured, match="405"):
        llm_config.resolve_endpoint()


def test_bad_host_also_raises_when_only_inspecting():
    """Nessun fallback silenzioso nemmeno in modalità ispezione."""
    import os
    os.environ["RESEARCH_PIPELINE_LLM_BASE_URL"] = "https://api.ollama.com"
    try:
        with pytest.raises(llm_config.LLMEndpointMisconfigured):
            llm_config.resolve_endpoint(require_credentials=False)
    finally:
        os.environ.pop("RESEARCH_PIPELINE_LLM_BASE_URL", None)


def test_missing_credentials_still_raises_for_cloud(monkeypatch):
    monkeypatch.delenv("RESEARCH_PIPELINE_LLM_API_KEY", raising=False)
    monkeypatch.setattr(llm_config, "OLLAMA_API_KEY", "")
    with pytest.raises(llm_config.MissingLLMCredentials):
        llm_config.resolve_endpoint()


def test_describe_reports_the_resolved_host_without_the_key():
    described = llm_config.describe()
    assert described["base_url"] == "https://ollama.com"
    assert described["is_cloud"] is True
    assert "api_key" not in described and "key" not in described


def test_sealed_module_default_is_untouched():
    """Il modulo sigillato non deve essere modificato da questa correzione."""
    import hashlib
    from pathlib import Path
    sealed = Path(llm_config.__file__).resolve().parents[1] / "pipeline" / "llm" / "__init__.py"
    digest = hashlib.sha256(sealed.read_bytes()).hexdigest()
    assert digest == "958080783c154b2f2a6357783d9a4657fdf16be3420dbbb273093b7a0bb80d81"

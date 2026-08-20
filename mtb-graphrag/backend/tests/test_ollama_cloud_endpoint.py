import json

from backend.pipeline.llm import ollama_adapter


def test_cloud_default_uses_current_native_api_base_and_paths(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    endpoint = ollama_adapter.configured_endpoint()
    assert endpoint.base_url == "https://ollama.com"

    seen_urls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"ok": True}).encode("utf-8")

    def fake_urlopen(request, timeout):
        seen_urls.append(request.full_url)
        return Response()

    monkeypatch.setattr(ollama_adapter.urllib.request, "urlopen", fake_urlopen)
    client = ollama_adapter.OllamaClient(endpoint)
    client.show("gemma4:31b-cloud")
    client.chat("gemma4:31b-cloud", [{"role": "user", "content": "test"}])

    assert seen_urls == [
        "https://ollama.com/api/show",
        "https://ollama.com/api/chat",
    ]

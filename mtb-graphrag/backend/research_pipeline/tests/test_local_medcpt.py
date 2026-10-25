import json

import numpy as np
import pytest

from backend.research_pipeline.retrieval.local_medcpt import VectorCache, content_windows, LocalMedCPT


def test_cache_hit_and_text_model_tokenizer_invalidation(tmp_path):
    cache = VectorCache(tmp_path)
    calls = []
    def encode():
        calls.append(1)
        return np.array([[1, 2]], dtype=np.float32)
    base = {"text": "EGFR", "model": "m1", "tokenizer": "t1", "inputs": [1, 2]}
    first, hit = cache.get(base, encode)
    assert not hit
    second, hit = cache.get(base, lambda: pytest.fail("cache hit encoded"))
    assert hit and np.array_equal(first, second)
    for key in base:
        cache.get({**base, key: "changed"}, encode)
    assert len(calls) == 5


def test_corrupt_cache_is_unusable(tmp_path):
    cache = VectorCache(tmp_path)
    cache.get({"text": "x"}, lambda: np.ones((1, 2), dtype=np.float32))
    next(tmp_path.glob("*.npy")).write_bytes(b"bad")
    with pytest.raises(ValueError, match="Cache content mismatch"):
        cache.get({"text": "x"}, lambda: pytest.fail("corruption must be explicit"))


def test_invalid_vectors_not_persisted(tmp_path):
    cache = VectorCache(tmp_path)
    with pytest.raises(ValueError):
        cache.get({}, lambda: np.array([[float("nan")]], dtype=np.float32))
    assert not list(tmp_path.glob("*.json"))


def test_article_windows_exact_contract():
    tokens = list(range(1000))
    windows = content_windows(tokens)
    assert [len(x) for x in windows] == [509, 509, 110]
    assert windows[1][0] == 445


def test_large_document_cache_progress_and_warm_hits_do_not_spend_encoding_budget(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from backend.research_pipeline.retrieval import local_medcpt as module

    backend = LocalMedCPT(tmp_path)
    backend.prior = {'queries': {'q': 0}, 'query': np.array([[1, 2]], dtype=np.float32), 'texts': {}}
    backend.identities = {'article': {}, 'query': {}}
    class Tokenizer:
        cls_token_id = 101
        sep_token_id = 102
        def __call__(self, text, **kwargs):
            return {'input_ids': [1, 2]}
    backend.tokenizers['article'] = Tokenizer()
    encoded = []
    def encode(kind, inputs):
        encoded.append(len(inputs))
        return np.ones((len(inputs), 2), dtype=np.float32)
    monkeypatch.setattr(backend, '_encode', encode)
    monkeypatch.setattr(module, 'MAX_MISSING_TEXTS', 1)
    selection = SimpleNamespace(source_units=[{'source_unit_id': '1', 'text': 'a'}, {'source_unit_id': '2', 'text': 'b'}], alterations=['q'], genes=[], interventions=[], disease=[])
    with pytest.raises(ValueError, match='bounded local'):
        backend.score(selection)
    assert encoded == [1]  # bounded progress survives fallback
    scores, telemetry = backend.score(selection)
    assert set(scores) == {'1', '2'}
    assert telemetry['article_texts_encoded'] == 1
    monkeypatch.setattr(module, 'MAX_MISSING_TEXTS', 0)
    _, telemetry = backend.score(selection)
    assert telemetry['article_texts_encoded'] == 0
    assert telemetry['article_cache_hits'] == 2
    assert encoded == [1, 1]


def test_single_long_text_resumes_windows_and_preserves_exact_scores(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from backend.research_pipeline.retrieval import local_medcpt as module

    backend = LocalMedCPT(tmp_path)
    backend.prior = {'queries': {'q': 0}, 'query': np.array([[1, 0]], dtype=np.float32), 'texts': {}}
    backend.identities = {'article': {}, 'query': {}}
    class Tokenizer:
        cls_token_id = 101
        sep_token_id = 102
        def __call__(self, text, **kwargs):
            return {'input_ids': list(range(18000))}
    backend.tokenizers['article'] = Tokenizer()
    encoded = []
    def encode(kind, inputs):
        encoded.extend(row['input_ids'][2] for row in inputs)
        return np.array([[row['input_ids'][2], 0] for row in inputs], dtype=np.float32)
    monkeypatch.setattr(backend, '_encode', encode)
    monkeypatch.setattr(module, 'MAX_MISSING_WINDOWS', 32)
    selection = SimpleNamespace(source_units=[{'source_unit_id': '1', 'text': 'long'}],
                                alterations=['q'], genes=[], interventions=[], disease=[])
    with pytest.raises(module.EncodingBudgetExceeded):
        backend.score(selection)
    assert len(encoded) == 32
    scores, telemetry = backend.score(selection)
    expected_windows = content_windows(list(range(18000)))
    assert scores == {'1': float(expected_windows[-1][0])}
    assert encoded == [window[0] for window in expected_windows]
    assert telemetry['article_windows_encoded'] == len(expected_windows) - 32
    backend.score(selection)
    assert len(encoded) == len(expected_windows)

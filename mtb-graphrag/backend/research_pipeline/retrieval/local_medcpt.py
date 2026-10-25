"""Pinned, CPU float32 MedCPT with audited prior and content-addressed local caches.

Only requested document misses are encoded. No Hub identifiers are passed to
Transformers; loading uses verified local directories and local_files_only.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from contextlib import nullcontext
from ..budget import active_budget
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
PRIOR = ROOT / "experiments_real/hybrid_retrieval_20261012/run_001"
REVISION = {"article": "d05a736da4bb84ee4057b7f7999485be6ed85465",
            "query": "d83a36cc6b8e3a5c5e9d9d6ba156808c1643dcbc"}
PRIOR_HASHES = {
    "cache/article_embeddings.json": "c9902d8da001ab61cdbfd0cc01b2616aad49f64513cb961d2ada1e54154d9f29",
    "cache/query_embeddings.json": "7d31e7ed5302795892a23ef2e50a9f4aa3dd621a9ba3505fda05aabb6596a444",
    "cache/index.json": "1ce5e7079d6317e260c853025002867c44245fb11a16cfeb39d932eda4183ce6",
    "queries_gold_free.json": "ee481645087574cd1ace9e41b6f4935fed2cd33be928f45604776b6319b9145b"}
ENCODING = "medcpt-empty-title-cls-max-window/1.0-float32-cpu"
MAX_MISSING_TEXTS = 128
MAX_MISSING_WINDOWS = 256


class EncodingBudgetExceeded(ValueError):
    def __init__(self, reason, *, texts_encoded, windows_encoded, cache_hits):
        super().__init__(reason)
        self.progress = {"article_texts_encoded": texts_encoded,
                         "article_windows_encoded": windows_encoded,
                         "article_cache_hits": cache_hits,
                         "resume_from_cache": True}


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode()).hexdigest()


def valid_vectors(value):
    if value.ndim != 2 or not value.shape[0] or not value.shape[1] or value.dtype != np.float32 or not np.isfinite(value).all():
        raise ValueError("Invalid float32 embedding matrix")
    return value


class VectorCache:
    def __init__(self, directory: Path):
        self.directory = directory

    def get(self, dependencies: dict, encode):
        key = digest(dependencies)
        metadata_path = self.directory / (key + ".json")
        output = self.directory / (key + ".npy")
        # A writer publishes the array immediately before its atomic metadata
        # sidecar rename. A second process sharing the cache can observe this
        # very short interval; wait/recheck before declaring the pair corrupt.
        if output.exists() and not metadata_path.exists():
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline and not metadata_path.exists():
                time.sleep(0.01)
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata["dependencies"] != dependencies or not output.exists() or sha_file(output) != metadata["sha256"]:
                raise ValueError("Cache content mismatch")
            return valid_vectors(np.load(output, allow_pickle=False)), True
        if output.exists():
            raise ValueError("Incomplete vector cache")
        value = valid_vectors(encode())
        self.directory.mkdir(parents=True, exist_ok=True)
        # Publish metadata last; partial writes are never treated as cache hits.
        temporary = self.directory / (key + "." + uuid.uuid4().hex + ".npy")
        try:
            np.save(temporary, value, allow_pickle=False)
            temporary.replace(output)
            metadata = {"dependencies": dependencies, "sha256": sha_file(output)}
            pending = metadata_path.with_suffix("." + uuid.uuid4().hex + ".tmp")
            pending.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
            pending.replace(metadata_path)
        finally:
            temporary.unlink(missing_ok=True)
        return value, False


def content_windows(tokens, capacity=509, overlap=64):
    if capacity < 1 or not 0 <= overlap < capacity:
        raise ValueError("Invalid advancing windows")
    result = []
    for start in range(0, max(1, len(tokens)), capacity - overlap):
        result.append(tokens[start:start + capacity])
        if start + capacity >= len(tokens):
            break
    return result


class LocalMedCPT:
    def __init__(self, cache_directory: Path | None = None):
        self.cache = VectorCache(cache_directory or ROOT / "mtb-graphrag/cache/local_medcpt")
        self.lock = threading.RLock()
        self.models = {}
        self.tokenizers = {}
        self.identities = {}
        self.prior = None

    def _initialize(self):
        if self.prior is not None:
            return
        for name, expected in PRIOR_HASHES.items():
            if sha_file(PRIOR / name) != expected:
                raise ValueError("Pinned prior artifact mismatch: " + name)
        article_meta = json.loads((PRIOR / "cache/article_embeddings.json").read_text(encoding="utf-8"))
        query_meta = json.loads((PRIOR / "cache/query_embeddings.json").read_text(encoding="utf-8"))
        identities = {}
        for kind, identity in article_meta["dependencies"]["models"].items():
            if identity["revision"] != REVISION[kind]:
                raise ValueError("Pinned checkpoint revision mismatch")
            for row in identity["files"]:
                path = ROOT / Path(row["path"].replace("\\", "/"))
                if not path.resolve().is_relative_to(ROOT) or sha_file(path) != row["sha256"]:
                    raise ValueError("Pinned model/tokenizer hash mismatch")
            identities[kind] = identity
        arrays = {}
        for kind, meta in (("article", article_meta), ("query", query_meta)):
            path = PRIOR / ("cache/" + kind + "_embeddings.npy")
            if sha_file(path) != meta["output_sha256"] or meta["dependencies"]["models"] != identities:
                raise ValueError("Prior embedding content/model mismatch")
            arrays[kind] = np.load(path, mmap_mode="r", allow_pickle=False)
            if arrays[kind].ndim != 2 or arrays[kind].dtype != np.float32 or arrays[kind].shape[1] != 768:
                raise ValueError("Prior embedding shape mismatch")
        corpus_row = next(row for row in article_meta["dependencies"]["inputs"]
                          if row["path"].endswith("reconstructed_source_units_v1_1.jsonl"))
        corpus_path = ROOT / Path(corpus_row["path"].replace("\\", "/"))
        if sha_file(corpus_path) != corpus_row["sha256"]:
            raise ValueError("Prior corpus text hash mismatch")
        index = json.loads((PRIOR / "cache/index.json").read_text(encoding="utf-8"))
        indexed_ids = index["unit_text_indices"]
        corpus = {}
        with corpus_path.open(encoding="utf-8") as stream:
            for line in stream:
                unit = json.loads(line)
                if unit["source_unit_id"] in indexed_ids:
                    corpus[unit["source_unit_id"]] = unit["text"]
        texts, indices = {}, {}
        for uid, text in sorted(corpus.items()):
            if text not in texts:
                texts[text] = len(texts)
            indices[uid] = texts[text]
        if indices != indexed_ids:
            raise ValueError("Prior text/index mismatch")
        queries = json.loads((PRIOR / "queries_gold_free.json").read_text(encoding="utf-8"))
        if arrays["query"].shape[0] != len(queries):
            raise ValueError("Prior query/index mismatch")
        self.identities = identities
        self.prior = {**arrays, "texts": texts, "windows": index["text_windows"],
                      "queries": {q["query_text"]: i for i, q in enumerate(queries)}}

    def _tokenizer(self, kind):
        if kind not in self.tokenizers:
            from transformers import AutoTokenizer
            self.tokenizers[kind] = AutoTokenizer.from_pretrained(str(self._model_path(kind)),
                local_files_only=True, trust_remote_code=False)
        return self.tokenizers[kind]

    def _model_path(self, kind):
        return ROOT / "mtb-graphrag/evaluation/thesis_comparative_2026_10/models" / ("ncbi--MedCPT-" + kind.title() + "-Encoder")

    def _encode(self, kind, inputs):
        import torch
        from transformers import AutoModel

        torch.set_num_threads(4)
        if kind not in self.models:
            self.models[kind] = AutoModel.from_pretrained(str(self._model_path(kind)),
                local_files_only=True, trust_remote_code=False).to("cpu").eval()
        model = self.models[kind]
        if next(model.parameters()).dtype != torch.float32:
            raise ValueError("Checkpoint is not float32")
        tokenizer = self._tokenizer(kind)
        order = sorted(range(len(inputs)), key=lambda i: (len(inputs[i]["input_ids"]), i))
        matrix = np.empty((len(inputs), model.config.hidden_size), dtype=np.float32)
        with torch.inference_mode():
            for start in range(0, len(order), 16):
                ids = order[start:start + 16]
                tensors = tokenizer.pad([inputs[i] for i in ids], padding=True, return_tensors="pt")
                budget = active_budget()
                with budget.encoding_batch(len(ids)) if budget is not None else nullcontext():
                    matrix[ids] = model(**tensors).last_hidden_state[:, 0, :].cpu().numpy()
        return valid_vectors(matrix)

    def _cached(self, kind, text, inputs, *, encode=None):
        # Persist hashes of encoded input tokens instead of the token IDs: query
        # text may contain case information, and token sequences are reversible.
        input_digest = hashlib.sha256(json.dumps(inputs, sort_keys=True,
                                                  separators=(",", ":")).encode()).hexdigest()
        return self.cache.get({"encoding": ENCODING, "model": self.identities[kind],
                               "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                               "input_sha256": input_digest}, encode or (lambda: self._encode(kind, inputs)))

    def score(self, selection):
        with self.lock:
            wall_start = time.perf_counter()
            cpu_start = time.process_time()
            self._initialize()
            texts = {str(u["source_unit_id"]): str(u["text"]) for u in selection.source_units}
            if len(texts) != len(selection.source_units):
                raise ValueError("Duplicate source unit ID")
            query = " ".join(x for group in (selection.alterations, selection.genes,
                getattr(selection, 'search_interventions', selection.interventions), selection.disease) for x in group)
            if not query.strip():
                raise ValueError("Empty MedCPT query")
            query_id = self.prior["queries"].get(query)
            hits, misses = 0, 0
            if query_id is not None:
                query_vector = self.prior["query"][query_id]
                query_cache = "PRIOR_HIT"
            else:
                inputs = dict(self._tokenizer("query")(query, truncation=False))
                if len(inputs["input_ids"]) > 512:
                    raise ValueError("MedCPT query exceeds 512 positions")
                vectors, hit = self._cached("query", query, [inputs])
                query_vector = vectors[0]
                query_cache = "LOCAL_HIT" if hit else "LOCAL_ENCODED"
            by_text, window_count = {}, 0
            for text in sorted(set(texts.values())):
                index = self.prior["texts"].get(text)
                if index is not None:
                    vectors = self.prior["article"][self.prior["windows"][index]]
                    hits += 1
                else:
                    tokenizer = self._tokenizer("article")
                    tokens = tokenizer(text, add_special_tokens=False)["input_ids"]
                    windows = content_windows(tokens)
                    inputs = [{"input_ids": [tokenizer.cls_token_id, tokenizer.sep_token_id, *w, tokenizer.sep_token_id],
                               "token_type_ids": [0, 0] + [1] * (len(w) + 1),
                               "attention_mask": [1] * (len(w) + 3)} for w in windows]
                    def encode_article():
                        nonlocal window_count
                        # Check after local cache lookup: warm vectors consume no
                        # encoding budget. Persist each completed text so a bounded
                        # follow-up can resume instead of failing forever at size>128.
                        if misses >= MAX_MISSING_TEXTS:
                            raise EncodingBudgetExceeded("Document exceeds bounded local encoding budget; cache progress retained",
                                texts_encoded=misses, windows_encoded=window_count, cache_hits=hits)
                        if len(inputs) > MAX_MISSING_WINDOWS:
                            # A single large SourceUnit must also make durable
                            # progress. Keep token windows and final max scoring
                            # identical; publish the whole-text cache only after
                            # every bounded chunk is available.
                            chunks = []
                            chunk_size = max(1, min(16, MAX_MISSING_WINDOWS))
                            for start in range(0, len(inputs), chunk_size):
                                chunk = inputs[start:start + chunk_size]
                                def encode_chunk():
                                    nonlocal window_count
                                    if window_count + len(chunk) > MAX_MISSING_WINDOWS:
                                        raise EncodingBudgetExceeded("Document exceeds bounded local encoding budget; cache progress retained",
                                            texts_encoded=misses, windows_encoded=window_count, cache_hits=hits)
                                    value = self._encode("article", chunk)
                                    window_count += len(chunk)
                                    return value
                                value, _ = self._cached("article", text, chunk, encode=encode_chunk)
                                chunks.append(value)
                            return np.concatenate(chunks, axis=0)
                        if window_count + len(inputs) > MAX_MISSING_WINDOWS:
                            raise EncodingBudgetExceeded("Document exceeds bounded local encoding budget; cache progress retained",
                                texts_encoded=misses, windows_encoded=window_count, cache_hits=hits)
                        value = self._encode("article", inputs)
                        window_count += len(inputs)
                        return value
                    vectors, hit = self._cached("article", text, inputs, encode=encode_article)
                    hits += int(hit)
                    misses += int(not hit)
                if vectors.shape[1] != query_vector.shape[0] or not np.isfinite(vectors).all():
                    raise ValueError("Unusable document embedding")
                by_text[text] = float(np.max(vectors @ query_vector))
            telemetry = {
                "models": {kind: {"revision": REVISION[kind], "identity_sha256": digest(identity)}
                           for kind, identity in self.identities.items()},
                "encoding": ENCODING, "query_cache": query_cache,
                "article_cache_hits": hits, "article_texts_encoded": misses,
                "article_windows_encoded": window_count,
                "encoding_limits": {"texts_per_pass": MAX_MISSING_TEXTS, "windows_per_pass": MAX_MISSING_WINDOWS},
                "device": "cpu", "dtype": "float32", "threads": 4,
                "wall_seconds": time.perf_counter() - wall_start,
                "cpu_seconds": time.process_time() - cpu_start,
            }
            return {uid: by_text[text] for uid, text in texts.items()}, telemetry


_backend = None
_backend_lock = threading.Lock()


def get_backend():
    global _backend
    with _backend_lock:
        if _backend is None:
            directory = os.getenv("RESEARCH_PIPELINE_MEDCPT_CACHE_DIRECTORY")
            _backend = LocalMedCPT(Path(directory) if directory else None)
        return _backend

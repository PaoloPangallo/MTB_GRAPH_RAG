"""Unverified shadow proposals. This module has no admission call sites."""
from __future__ import annotations
from collections import Counter
from functools import lru_cache
import hashlib
import math
import time

from .models import DOMAINS
from .registry import IDENTITY_SCOPES
from .surface import surface


def grams(value):
    text = " " + surface(value) + " "
    return Counter(text[i:i+3] for i in range(max(0, len(text)-2)))


def cosine(a, b):
    denom = math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b, strict=True)) / denom if denom else 0.0


@lru_cache(maxsize=12)
def lexical_index(registry, domain):
    unique = {}
    for term in registry.terms:
        if term.domain == domain and term.alias_scope in IDENTITY_SCOPES:
            unique.setdefault((term.concept_id, term.label), term)
    terms = tuple(unique.values())
    features = [grams(t.label) for t in terms]
    df = Counter(key for feature in features for key in feature)
    idf = {key: math.log((1 + len(terms)) / (1 + count)) + 1 for key, count in df.items()}
    vectors = [{key: count * idf[key] for key, count in feature.items()} for feature in features]
    norms = [math.sqrt(sum(x*x for x in v.values())) for v in vectors]
    index_hash = hashlib.sha256("\n".join(f"{t.concept_id}\t{t.label}" for t in terms).encode()).hexdigest()
    return terms, vectors, norms, idf, index_hash


def propose(value, domain, registry, *, encoder=None, top_k=10, language="en"):
    started = time.perf_counter()
    if domain not in DOMAINS:
        raise ValueError("Unsupported domain")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1 or top_k > 100:
        raise ValueError("top_k must be between 1 and 100")
    if not isinstance(value, str) or not value.strip():
        return {"status": "INVALID_INPUT", "proposals": []}
    terms, vectors, norms, idf, index_hash = lexical_index(registry, domain)
    query = {k: v * idf.get(k, 0) for k, v in grams(value).items()}
    norm = math.sqrt(sum(x*x for x in query.values()))
    scores = [sum(v.get(k, 0)*x for k, x in query.items()) / (n*norm) if n and norm else 0.0 for v, n in zip(vectors, norms, strict=True)]
    status, reason, model, revision = "MODEL_UNAVAILABLE", "LOCAL_WEIGHTS_NOT_CONFIGURED", None, None
    if encoder is not None:
        model, revision = getattr(encoder, "model_identifier", None), getattr(encoder, "model_revision", None)
        if language not in getattr(encoder, "supported_languages", ()):
            status, reason = "UNSUPPORTED_LANGUAGE", "LANGUAGE_NOT_VALIDATED"
        elif getattr(encoder, "index_registry_version", None) != registry.version:
            reason = "INDEX_VERSION_MISMATCH"
        elif getattr(encoder, "index_hash", None) != index_hash:
            reason = "INDEX_HASH_MISMATCH"
        elif not model or not revision:
            reason = "MODEL_PROVENANCE_MISSING"
        else:
            try:
                # The adapter owns the offline label embedding index; runtime
                # never downloads weights or builds label embeddings.
                dense = encoder.score(value, terms, index_hash)
                if len(dense) != len(terms) or any(not math.isfinite(float(x)) for x in dense):
                    raise ValueError("Invalid dense scores")
                scores = [(a + float(b)) / 2 for a, b in zip(scores, dense, strict=True)]
                status, reason = "AVAILABLE", None
            except Exception as exc:
                reason = "ENCODER_FAILED:" + type(exc).__name__
    best = {}
    for term, score in zip(terms, scores, strict=True):
        if score <= 0:
            continue
        proposal = {"concept_id": term.concept_id, "domain": domain, "matched_label": term.label,
                    "score": score, "method": "LEXICAL_DENSE_SHADOW" if status == "AVAILABLE" else "CHAR_TFIDF_SHADOW",
                    "verified": False, "model_identifier": model, "model_revision": revision,
                    "index_hash": index_hash, "registry_version": registry.version, "source": term.source.__dict__}
        old = best.get(term.concept_id)
        if old is None or (-score, term.label) < (-old["score"], old["matched_label"]):
            best[term.concept_id] = proposal
    return {"status": status, "reason": reason, "proposals": sorted(best.values(), key=lambda p: (-p["score"], p["concept_id"]))[:top_k],
            "latency_ms": (time.perf_counter()-started)*1000, "registry_version": registry.version,
            "language": language, "language_validation": "NOT_INDEPENDENTLY_VALIDATED", "admission_enabled": False}

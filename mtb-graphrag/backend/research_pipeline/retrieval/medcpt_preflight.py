"""Offline launch check: imports, pinned assets and tokenizers, without encoding."""

from __future__ import annotations

import json
import os
from importlib.metadata import version


def check() -> dict:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from transformers import (
        AutoModel,
        AutoTokenizer,
    )  # noqa: F401 -- verify real imports
    import torch  # noqa: F401
    from .local_medcpt import LocalMedCPT, REVISION, ENCODING

    versions = {name: version(name) for name in ("numpy", "torch", "transformers")}
    expected = {"numpy": "2.4.6", "torch": "2.12.1", "transformers": "5.12.1"}
    for name, pinned in expected.items():
        if versions[name].split("+")[0] != pinned:
            raise RuntimeError(f"{name}: expected {pinned}, found {versions[name]}")
    backend = LocalMedCPT()
    backend._initialize()
    for kind in ("query", "article"):
        backend._tokenizer(kind)
    return {
        "ready": True,
        "versions": versions,
        "checkpoint_revisions": REVISION,
        "encoding": ENCODING,
        "network_requests": 0,
        "texts_encoded": 0,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(check(), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ready": False, "error": f"{type(exc).__name__}: {exc}"}))
        raise SystemExit(1)

"""Fetch and install the pinned Protocol 1.7 v2 corpus artifact."""

from __future__ import annotations

import shutil
import tempfile
import urllib.request
from pathlib import Path

from restore_canonical_v2_corpus import (
    DESTINATION,
    EXPECTED_NAME,
    verify,
)


RESTORE_SCRIPT_VERSION = "1.0"
RELEASE_TAG = "final-evaluation-protocol-v1.7-artifacts"
RELEASE_URL = (
    "https://github.com/PaoloPangallo/MTB_GRAPH_RAG/releases/download/"
    f"{RELEASE_TAG}/{EXPECTED_NAME}"
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="protocol17-corpus-") as tmp:
        downloaded = Path(tmp) / EXPECTED_NAME
        request = urllib.request.Request(
            RELEASE_URL,
            headers={"Accept": "application/octet-stream", "User-Agent": "protocol17-provenance"},
        )
        with urllib.request.urlopen(request, timeout=1800) as response, downloaded.open("wb") as handle:
            shutil.copyfileobj(response, handle, length=1024 * 1024)
        verify(downloaded, require_release_name=True)
        DESTINATION.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(downloaded, DESTINATION)
        verify(DESTINATION, require_release_name=False)
    print(f"fetched and installed: {DESTINATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

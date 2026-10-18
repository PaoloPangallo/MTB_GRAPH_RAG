"""Cross-platform digests for UTF-8 text; no content or whitespace inference."""

from __future__ import annotations

from hashlib import sha256

CANONICAL_TEXT_DIGEST_VERSION = "canonical-text-sha256/1.0"


def canonical_text_bytes(value: bytes | str) -> bytes:
    """Normalize CRLF/lone CR to LF, preserving every other character.

    UTF-8 decoding is strict. BOMs, whitespace, record order and the number of
    final newlines are preserved; a missing final newline remains missing.
    """
    text = value.decode("utf-8") if isinstance(value, bytes) else value
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def canonical_text_sha256(value: bytes | str) -> str:
    """Hash text under the versioned, newline-only canonicalization contract."""
    return sha256(canonical_text_bytes(value)).hexdigest()

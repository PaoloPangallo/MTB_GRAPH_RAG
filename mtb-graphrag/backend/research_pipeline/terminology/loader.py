from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

from .registry import Registry


class TerminologyAssetError(RuntimeError):
    """Missing/corrupt terminology must not look like absence of evidence."""


def load_registry(manifest_path: Path) -> Registry:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("schema_version") != "terminology-manifest/1.0":
            raise ValueError("Unsupported terminology manifest schema")
        filename = manifest["registry_file"]
        if Path(filename).name != filename or filename in {".", ".."}:
            raise ValueError("Registry file must be a local filename")
        data = (manifest_path.parent / filename).read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest["registry_sha256"]:
            raise ValueError("Registry hash mismatch")
        registry = Registry.from_dict(json.loads(data))
        if registry.version != manifest["registry_version"]:
            raise ValueError("Registry version mismatch")
        return registry
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise TerminologyAssetError(str(exc)) from exc


def default_manifest_path() -> Path:
    return Path(os.environ.get("RESEARCH_PIPELINE_TERMINOLOGY_MANIFEST") or
                Path(__file__).resolve().parents[3] / "data/terminology/1.2/manifest.json")


@lru_cache(maxsize=2)
def _cached(path: str, manifest_stat: tuple, registry_stat: tuple) -> Registry:
    return load_registry(Path(path))


def get_registry() -> Registry:
    path = default_manifest_path()
    try:
        stat = path.stat()
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Invalid manifest object")
        filename = manifest.get("registry_file", "registry.json")
        if Path(filename).name != filename:
            raise TerminologyAssetError("Invalid registry filename")
        rstat = (path.parent / filename).stat()
        return _cached(str(path.resolve()), (stat.st_mtime_ns, stat.st_size),
                       (rstat.st_mtime_ns, rstat.st_size))
    except (OSError, ValueError, TypeError) as exc:
        raise TerminologyAssetError(str(exc)) from exc


@lru_cache(maxsize=2)
def _load_overlay(path: str, manifest_stat: tuple, overlay_stat: tuple, corpus_hash: str) -> dict:
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        filename = manifest["overlay_file"]
        if Path(filename).name != filename:
            raise ValueError("Invalid overlay filename")
        data = (manifest_path.parent / filename).read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest["overlay_sha256"]:
            raise ValueError("Overlay hash mismatch")
        payload = json.loads(data)
        if payload["gca_sha256"] != corpus_hash or manifest["gca_sha256"] != corpus_hash:
            raise ValueError("Overlay/GCA release mismatch")
        return payload["candidates"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise TerminologyAssetError(str(exc)) from exc


def get_overlay(corpus_hash: str) -> dict:
    path = default_manifest_path()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        filename = manifest["overlay_file"]
        if Path(filename).name != filename:
            raise ValueError("Invalid overlay filename")
        stat, ostat = path.stat(), (path.parent / filename).stat()
        return _load_overlay(str(path.resolve()), (stat.st_mtime_ns, stat.st_size),
                             (ostat.st_mtime_ns, ostat.st_size), corpus_hash)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise TerminologyAssetError(str(exc)) from exc

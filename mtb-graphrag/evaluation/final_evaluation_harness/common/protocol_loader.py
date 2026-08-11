"""Read and validate the frozen Protocol 1.2 artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ProtocolGap(RuntimeError):
    """Raised when a required frozen decision is absent or inconsistent."""


@dataclass(frozen=True)
class Protocol:
    root: Path
    manifest: dict[str, Any]
    lineage: dict[str, Any]
    metrics: dict[str, Any]
    criteria: dict[str, Any]
    schemas: dict[str, Any]
    statistics: dict[str, Any]
    execution: dict[str, Any]
    latency: dict[str, Any]
    ablation: dict[str, Any]
    reliability: dict[str, Any]
    datasets: dict[str, Any]
    seal: dict[str, Any]
    a01_root: Path
    s01_root: Path

    @property
    def hashes(self) -> dict[str, str]:
        return {
            "runtime_commit": self.manifest["runtime_commit"],
            "protocol_sha256": self.seal["protocol_1_2_sha256"],
            "inherited_protocol_1_1_sha256": self.lineage["protocol_1_1"]["sha256"],
            "inherited_A01_sha256": self.lineage["A01"]["sha256"],
            "S01_raw_sha256": self.lineage["S01"]["raw_sha256"],
            "S01_package_sha256": self.lineage["S01"]["package_sha256"],
        }

    @property
    def normative_files(self) -> tuple[str, ...]:
        return tuple(self.manifest["normative_files"])


def _load(root: Path, name: str) -> dict[str, Any]:
    path = root / name
    if not path.is_file():
        raise ProtocolGap(f"missing normative artifact: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProtocolGap(f"normative artifact is not an object: {name}")
    return value


def _protocol_digest(root: Path, files: tuple[str, ...]) -> str:
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
    material = "\n".join(f"{name}:{hashes[name]}" for name in sorted(hashes))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def load_protocol(repo_root: Path | None = None) -> Protocol:
    repo = repo_root or Path(__file__).resolve().parents[3]
    root = repo / "evaluation" / "final_protocol_v1_2"
    manifest = _load(root, "protocol_manifest.json")
    files = tuple(manifest.get("normative_files", ()))
    if not files:
        raise ProtocolGap("protocol normative file list is empty")
    docs = {name.removesuffix(".json"): _load(root, name) for name in files}
    seal = _load(root, "protocol_hash.json")
    expected = {
        "protocol_version": "1.2",
        "review_status": "ACCEPTED",
        "frozen": True,
        "runtime_commit": "3d2251f82a586535f79f3d0b3725c16330c365ba",
    }
    for field, value in expected.items():
        observed = manifest.get(field)
        if observed != value:
            raise ProtocolGap(f"manifest {field} mismatch: {observed!r}")
    if seal.get("protocol_1_2_sha256") != _protocol_digest(root, files):
        raise ProtocolGap("protocol 1.2 seal mismatch")
    if seal.get("review_status") != "ACCEPTED" or seal.get("frozen") is not True:
        raise ProtocolGap("protocol seal is not accepted/frozen")
    lineage = docs["lineage"]
    if lineage["protocol_1_1"]["sha256"] != "83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889":
        raise ProtocolGap("parent protocol SHA mismatch")
    if lineage["A01"]["sha256"] != "48c60928eafad33c4e2f8008db58fa543e3c17c04a8a73733f471c7c2bdacdcf":
        raise ProtocolGap("A01 SHA mismatch")
    if lineage["S01"]["raw_sha256"] != "83babfa59b0cf9cde320fe8fbdffd2d28c31b117d974bd4472c6015ee2a74f99":
        raise ProtocolGap("S01 raw SHA mismatch")
    if lineage["S01"]["package_sha256"] != "b5979ac2f9ec7ae61fbf6bb929370e902f9f188de702d690ab71167d3d5a7f15":
        raise ProtocolGap("S01 package SHA mismatch")
    a01_root = repo / "evaluation" / "final_protocol" / "amendments" / "A01"
    s01_root = repo / "evaluation" / "final_protocol" / "supplements" / "S01"
    if not (a01_root / "operational_scenario_bindings.json").is_file():
        raise ProtocolGap("A01 bindings artifact missing")
    if not (s01_root / "sourceunits_1697.jsonl").is_file():
        raise ProtocolGap("S01 SourceUnit artifact missing")
    s01_seal = _load(s01_root, "supplement_hash.json")
    if s01_seal.get("supplement_sha256") != lineage["S01"]["package_sha256"]:
        raise ProtocolGap("S01 package SHA mismatch")
    return Protocol(
        root,
        manifest,
        lineage,
        docs["metric_registry"],
        docs["success_criteria"],
        docs["result_schemas"],
        docs["statistical_plan"],
        docs["execution_contract"],
        docs["latency_contract"],
        docs["ablation_contract"],
        docs["reliability_contract"],
        docs["dataset_registry"],
        seal,
        a01_root,
        s01_root,
    )


def load_a01_bindings(protocol: Protocol) -> dict[str, Any]:
    value = json.loads((protocol.a01_root / "operational_scenario_bindings.json").read_text(encoding="utf-8"))
    if value.get("n_scenarios") != 9 or len(value.get("scenarios", [])) != 9:
        raise ProtocolGap("A01 scenario count mismatch")
    return value


def load_a01_cache_contract(protocol: Protocol) -> dict[str, Any]:
    return json.loads((protocol.a01_root / "cache_seed_contract.json").read_text(encoding="utf-8"))


def load_s01_rows(protocol: Protocol) -> list[dict[str, Any]]:
    path = protocol.s01_root / "sourceunits_1697.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if hashlib.sha256(path.read_bytes()).hexdigest() != protocol.hashes["S01_raw_sha256"]:
        raise ProtocolGap("S01 raw SHA mismatch")
    if len(rows) != 1697 or len({row.get("source_unit_id") for row in rows}) != 1697:
        raise ProtocolGap("S01 structural counts mismatch")
    return rows


def validate_dataset_registry(protocol: Protocol) -> None:
    hashes = protocol.datasets.get("dataset_hashes")
    if not isinstance(hashes, dict) or "dataset_bundle_sha256" not in hashes or len(hashes) != 20:
        raise ProtocolGap("dataset hash map is incomplete")

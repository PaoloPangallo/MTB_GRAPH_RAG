"""Load the frozen Protocol 1.5 and its inherited scientific contracts."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

class ProtocolGap(RuntimeError):
    pass

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
    parent_root: Path
    amendment: dict[str, Any]
    projection: dict[str, Any]
    corpus: dict[str, Any]

    @property
    def hashes(self) -> dict[str, str]:
        return {"runtime_commit": self.lineage["runtime_sha256"], "protocol_sha256": self.seal["protocol_sha256"], "parent_protocol_1_4_sha256": self.lineage["parent_protocol_sha256"], "parent_protocol_1_3_sha256": "1e7f154ae6dff655937acb486226b88ac5baa556efaeb1a6a77d64d423399fa5", "inherited_protocol_1_1_sha256": "83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889", "inherited_A01_sha256": "48c60928eafad33c4e2f8008db58fa543e3c17c04a8a73733f471c7c2bdacdcf", "S01_raw_sha256": "83babfa59b0cf9cde320fe8fbdffd2d28c31b117d974bd4472c6015ee2a74f99", "S01_package_sha256": "b5979ac2f9ec7ae61fbf6bb929370e902f9f188de702d690ab71167d3d5a7f15"}

def _load(root: Path, name: str) -> dict[str, Any]:
    path=root/name
    if not path.is_file(): raise ProtocolGap(f"missing normative artifact: {path}")
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ProtocolGap(f"artifact is not object: {name}")
    return value

def _digest(root: Path, files: list[str]) -> str:
    hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
    return hashlib.sha256("\n".join(f"{n}:{hashes[n]}" for n in sorted(hashes)).encode()).hexdigest()

def load_protocol(repo_root: Path | None = None) -> Protocol:
    repo=repo_root or Path(__file__).resolve().parents[3]
    root=repo/"evaluation"/"final_protocol_v1_5"
    manifest=_load(root,"protocol_manifest.json")
    amendment=_load(root,"amendment_contract.json")
    inherited=_load(root,"inherited_protocol_contract.json")
    projection=_load(root,"scientific_projection.json")
    corpus=_load(root,"corpus_identity.json")
    seal=_load(root,"protocol_hash.json")
    expected={"runtime_sha256":"79867435acd59b830dae1d0fbab272c2bea2427b","parent_protocol_sha256":"6aa8927e47181dc5b5b4fbf8e6390372f5de9e26d47a3a3bf86e7bd6f25aea3e","scientific_projection_sha256":"4be62db090f9fa0c05c0369008cc267af0e6c1132ccee9cc09705542237f78d0"}
    if manifest.get("protocol_version")!="1.5" or manifest.get("frozen") is not True or manifest.get("review_status")!="ACCEPTED": raise ProtocolGap("Protocol 1.5 is not accepted/frozen")
    if seal.get("protocol_sha256") != "60b74a031688161690b34a8ed6dda7f4b36ca7323541bbd1564b0ad816fe3bdd": raise ProtocolGap("Protocol 1.5 SHA mismatch")
    lineage=_load(root,"lineage.json")
    if any(lineage.get(k)!=v for k,v in expected.items()): raise ProtocolGap("Protocol 1.5 lineage mismatch")
    if projection.get("parent_projection_sha256") != "76bcb6f395aa4b8053ac19305d7404713aa6d0d53c6bce21a1f0f7b3e4971497": raise ProtocolGap("parent projection mismatch")
    parent=repo/"evaluation"/"final_protocol_v1_2"; pmanifest=_load(parent,"protocol_manifest.json"); pseal=_load(parent,"protocol_hash.json")
    if pseal.get("protocol_1_2_sha256") != "76800b10ba85836369f47973802b0df65c0221df39ad8e9eac45a5241b70e106" or _digest(parent,pmanifest["normative_files"]) != "76800b10ba85836369f47973802b0df65c0221df39ad8e9eac45a5241b70e106": raise ProtocolGap("parent Protocol 1.2 mismatch")
    a01=repo/"evaluation"/"final_protocol"/"amendments"/"A01"; s01=repo/"evaluation"/"final_protocol"/"supplements"/"S01"
    a01seal=_load(a01,"amendment_hash.json"); s01seal=_load(s01,"supplement_hash.json")
    if a01seal.get("amendment_sha256")!="48c60928eafad33c4e2f8008db58fa543e3c17c04a8a73733f471c7c2bdacdcf" or s01seal.get("supplement_sha256")!="b5979ac2f9ec7ae61fbf6bb929370e902f9f188de702d690ab71167d3d5a7f15": raise ProtocolGap("A01/S01 identity mismatch")
    scientific={Path(n).stem:_load(parent,n) for n in pmanifest["normative_files"]}
    return Protocol(root,manifest,lineage,scientific["metric_registry"],scientific["success_criteria"],scientific["result_schemas"],scientific["statistical_plan"],scientific["execution_contract"],scientific["latency_contract"],scientific["ablation_contract"],scientific["reliability_contract"],scientific["dataset_registry"],seal,a01,s01,parent,amendment,projection,corpus)

def load_a01_bindings(protocol):
    value=json.loads((protocol.a01_root/"operational_scenario_bindings.json").read_text(encoding="utf-8"))
    if value.get("n_scenarios")!=9 or len(value.get("scenarios",[]))!=9: raise ProtocolGap("A01 scenario count mismatch")
    return value
def load_a01_cache_contract(protocol): return json.loads((protocol.a01_root/"cache_seed_contract.json").read_text(encoding="utf-8"))
def load_s01_rows(protocol):
    path=protocol.s01_root/"sourceunits_1697.jsonl"; rows=[json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
    if hashlib.sha256(path.read_bytes()).hexdigest()!=protocol.hashes["S01_raw_sha256"] or len(rows)!=1697 or len({r.get("source_unit_id") for r in rows})!=1697: raise ProtocolGap("S01 identity/count mismatch")
    return rows
def validate_dataset_registry(protocol):
    h=protocol.datasets.get("dataset_hashes")
    if not isinstance(h,dict) or len(h)!=20 or "dataset_bundle_sha256" not in h: raise ProtocolGap("dataset hash map incomplete")

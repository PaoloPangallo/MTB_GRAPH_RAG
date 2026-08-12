"""Load the frozen Protocol 1.6 and its inherited scientific contracts."""
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
        return {"runtime_commit": self.lineage["H02_runtime_commit"], "protocol_sha256": self.seal["protocol_sha256"], "parent_protocol_1_5_sha256": self.lineage["parent_protocol_sha256"], "parent_protocol_1_4_sha256": "6aa8927e47181dc5b5b4fbf8e6390372f5de9e26d47a3a3bf86e7bd6f25aea3e", "parent_protocol_1_3_sha256": "1e7f154ae6dff655937acb486226b88ac5baa556efaeb1a6a77d64d423399fa5", "inherited_protocol_1_1_sha256": "83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889", "inherited_A01_sha256": "48c60928eafad33c4e2f8008db58fa543e3c17c04a8a73733f471c7c2bdacdcf", "S01_raw_sha256": "83babfa59b0cf9cde320fe8fbdffd2d28c31b117d974bd4472c6015ee2a74f99", "S01_package_sha256": "b5979ac2f9ec7ae61fbf6bb929370e902f9f188de702d690ab71167d3d5a7f15"}

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
    root=repo/"evaluation"/"final_protocol_v1_6"
    manifest=_load(root,"protocol_manifest.json")
    amendment=_load(root,"amendment_contract.json")
    inherited=_load(root,"inherited_protocol_contract.json")
    projection=_load(root,"scientific_projection.json")
    corpus=_load(root,"corpus_identity.json")
    seal=_load(root,"protocol_hash.json")
    expected={"H02_runtime_commit":"eb20fdfab35724f3b84651d8c02f1ec3970db615","parent_protocol_commit":"556618f8810333d1abad3771e42c4626e54d3670","parent_protocol_sha256":"60b74a031688161690b34a8ed6dda7f4b36ca7323541bbd1564b0ad816fe3bdd","scientific_projection_sha256":"a4edb0bad5cd233fe04423068dacf14de91bb7a7421169c5602c7bf79e67229c"}
    if manifest.get("protocol_version")!="1.6" or manifest.get("frozen") is not True or manifest.get("review_status")!="ACCEPTED": raise ProtocolGap("Protocol 1.6 is not accepted/frozen")
    if seal.get("protocol_sha256") != "ac296a924a39b58caf3427f47153348566d21bcadb6fef94bfa8c6105400ac1d": raise ProtocolGap("Protocol 1.6 SHA mismatch")
    lineage=_load(root,"lineage.json")
    if any(lineage.get(k)!=v for k,v in expected.items()): raise ProtocolGap("Protocol 1.6 lineage mismatch")
    if inherited.get("source_protocol_sha256") != "60b74a031688161690b34a8ed6dda7f4b36ca7323541bbd1564b0ad816fe3bdd": raise ProtocolGap("Protocol 1.5 parent mismatch")
    parent=repo/"evaluation"/"final_protocol_v1_2"; pmanifest=_load(parent,"protocol_manifest.json"); pseal=_load(parent,"protocol_hash.json")
    if pseal.get("protocol_1_2_sha256") != "76800b10ba85836369f47973802b0df65c0221df39ad8e9eac45a5241b70e106" or _digest(parent,pmanifest["normative_files"]) != "76800b10ba85836369f47973802b0df65c0221df39ad8e9eac45a5241b70e106": raise ProtocolGap("parent Protocol 1.2 mismatch")
    a01=repo/"evaluation"/"final_protocol"/"amendments"/"A01"; s01=repo/"evaluation"/"final_protocol"/"supplements"/"S01"
    a01seal=_load(a01,"amendment_hash.json"); s01seal=_load(s01,"supplement_hash.json")
    if a01seal.get("amendment_sha256")!="48c60928eafad33c4e2f8008db58fa543e3c17c04a8a73733f471c7c2bdacdcf" or s01seal.get("supplement_sha256")!="b5979ac2f9ec7ae61fbf6bb929370e902f9f188de702d690ab71167d3d5a7f15": raise ProtocolGap("A01/S01 identity mismatch")
    scientific={Path(n).stem:_load(parent,n) for n in pmanifest["normative_files"]}
    protocol = Protocol(root,manifest,lineage,scientific["metric_registry"],scientific["success_criteria"],scientific["result_schemas"],scientific["statistical_plan"],scientific["execution_contract"],scientific["latency_contract"],scientific["ablation_contract"],scientific["reliability_contract"],scientific["dataset_registry"],seal,a01,s01,parent,amendment,projection,corpus)
    validate_h01_identity(repo, protocol)
    return protocol


def validate_h01_identity(repo: Path, protocol: Protocol) -> tuple[str, str]:
    """Recompute H01 identities from tracked bytes before plan generation."""
    import importlib.util
    module_path = repo / "evaluation" / "final_protocol_v1_6_candidates" / "rq4" / "hash_h01.py"
    spec = importlib.util.spec_from_file_location("h01_hash", module_path)
    if spec is None or spec.loader is None:
        raise ProtocolGap("H01 hash implementation unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    artifact_root = module_path.parent
    git_root = module.repository_root(artifact_root)
    normative = module.digest(module.NORMATIVE_FILES, artifact_root=artifact_root, repo_root=git_root) if hasattr(module, "NORMATIVE_FILES") else module.digest(_load(artifact_root, "normative_hash_policy.json")["normative_files"], artifact_root=artifact_root, repo_root=git_root)
    support = module.digest(module.SUPPORT_FILES, artifact_root=artifact_root, repo_root=git_root) if hasattr(module, "SUPPORT_FILES") else module.digest(_load(artifact_root, "normative_hash_policy.json")["support_files"], artifact_root=artifact_root, repo_root=git_root)
    expected = protocol.amendment["H01"]
    if normative != expected["normative_sha256"] or support != expected["support_sha256"]:
        raise ProtocolGap("H01 identity mismatch")
    return normative, support

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

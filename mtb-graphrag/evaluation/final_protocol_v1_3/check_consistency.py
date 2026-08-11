"""Fail-closed static checker for Protocol 1.3; never executes providers."""
from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME = "3d2251f82a586535f79f3d0b3725c16330c365ba"
P12 = "76800b10ba85836369f47973802b0df65c0221df39ad8e9eac45a5241b70e106"
A01 = "48c60928eafad33c4e2f8008db58fa543e3c17c04a8a73733f471c7c2bdacdcf"
S01_RAW = "83babfa59b0cf9cde320fe8fbdffd2d28c31b117d974bd4472c6015ee2a74f99"
S01_PKG = "b5979ac2f9ec7ae61fbf6bb929370e902f9f188de702d690ab71167d3d5a7f15"
FILES = ("execution_environment_contract.json","generation_configuration.json","inherited_protocol_contract.json","lineage.json","model_identity_contract.json","provider_metadata_contract.json","protocol_manifest.json","reproducibility_contract.json")
def load(name): return json.loads((HERE/name).read_text(encoding="utf-8"))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main() -> int:
    checks=[]
    def add(name, ok): checks.append((name,bool(ok)))
    add("all normative files present", all((HERE/n).is_file() for n in FILES))
    m=load("protocol_manifest.json"); l=load("lineage.json"); mi=load("model_identity_contract.json")
    gc=load("generation_configuration.json"); env=load("execution_environment_contract.json"); pm=load("provider_metadata_contract.json"); rc=load("reproducibility_contract.json"); ip=load("inherited_protocol_contract.json")
    add("protocol version", m.get("protocol_version")=="1.3")
    add("accepted frozen status", m.get("status")=="ACCEPTED" and m.get("review_status")=="ACCEPTED" and m.get("frozen") is True and isinstance(m.get("freeze_timestamp"), str) and m.get("freeze_scope")=="FINAL_EVALUATION_PROTOCOL_1_3_FINAL_FREEZE")
    add("human review", m.get("human_review")=={"reviewer":"Paolo Pangallo","review_date":"2026-08-11","review_verdict":"ACCEPTED","review_scope":"FINAL_EVALUATION_PROTOCOL_1_3_EXECUTION_IDENTITY_REVISION","decisions":{"E01":"APPROVED","E02":"APPROVED","E03":"APPROVED","E04":"APPROVED"}})
    add("lineage exact", l=={"runtime_commit":RUNTIME,"protocol_1_1_sha256":"83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889","A01_sha256":A01,"S01_raw_sha256":S01_RAW,"S01_package_sha256":S01_PKG,"protocol_1_2_id":"mtb-graphrag-final-evaluation/1.2","protocol_1_2_sha256":P12,"protocol_1_2_freeze_commit":"22b4e69","classification":"SUPERSEDES_1_2_FOR_FINAL_EXECUTION_IDENTITY_ONLY"})
    add("E01 model", mi.get("effective_model")=="gemma4:31b-cloud" and mi.get("endpoint")=="https://ollama.com/v1/chat/completions" and mi.get("provider")=="OLLAMA_CLOUD")
    add("E01 metadata", mi.get("expected_metadata")=={"family":"gemma4","parameter_size":"32682372656","quantization":"BF16","context_length":262144})
    expected={"case_context_parser":("gemma4:31b-cloud",0,1,"run_index",2048,60,"casecontext-parser-prompt/1.0","7b59558bba3b7a2bb461449d19aa82587cb5828121f39dbef7a4cc36f05aee35"),"paper_context_enricher":("gemma4:31b-cloud",0,1,"run_index",1024,60,"paper-context-enricher-prompt/2.0","4a9dd12e71ed7753f15893a1ec7a845ae5b03653bb89a08a0d0ee7c4087c0ce1"),"dossier_narrator":("gemma4:31b-cloud",0,1,"run_index",2048,60,"dossier-narrator-prompt/1.0","5f510992790d9932e5259b31f2d4a09d7d8bf467f99e375c21973ee1415743ac")}
    add("E02 generation and prompts", all(tuple((v.get(k) for k in ("model","temperature","top_p","seed_policy","max_output_tokens","timeout_seconds","prompt_version","prompt_sha256")))==t for k,t in expected.items() for v in [gc["roles"][k]]))
    add("E02 no extra sampling", gc.get("additional_sampling_parameters")=="NONE")
    add("environment lock", env.get("OLLAMA_API_KEY")=="PRESENT_REQUIRED_SECRET_NOT_RECORDED" and env.get("semantic_override_mismatch")=="HARD_FAIL")
    add("E03 snapshots", pm.get("pre_execution_snapshot") is True and pm.get("post_execution_snapshot") is True and pm.get("drift_code")=="PROVIDER_MODEL_METADATA_DRIFT")
    add("E03 expected identity", pm.get("expected")=={"model_alias":"gemma4:31b-cloud","family":"gemma4","parameter_size":"32682372656","quantization":"BF16","context_length":262144})
    add("E04 limitation", rc.get("classification")=="REMOTE_PROVIDER_CONFIG_REPRODUCIBILITY" and len(rc.get("not_guaranteed",[]))>=4 and len(rc.get("prohibited_claims",[]))==3)
    add("inherited D02-D16", len(ip.get("inherited_decisions",{}))==15 and all(v=="INHERITED_UNCHANGED_FROM_1_2" for v in ip["inherited_decisions"].values()) and ip.get("semantic_change_count")==0)
    p12_hash=load("../final_protocol_v1_2/protocol_hash.json")
    add("1.2 sealed SHA", p12_hash.get("protocol_1_2_sha256")==P12 and all(sha(ROOT/"evaluation/final_protocol_v1_2"/n)==h for n,h in p12_hash.get("files",{}).items()))
    add("final results absent", not (ROOT/"evaluation/final_evaluation").exists())
    for name,ok in checks: print(("PASS" if ok else "FAIL")+" | "+name)
    print(f"SUMMARY {sum(ok for _,ok in checks)}/{len(checks)}")
    return 0 if all(ok for _,ok in checks) else 1
if __name__ == "__main__": raise SystemExit(main())

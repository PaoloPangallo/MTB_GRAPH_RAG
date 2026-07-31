"""Generate the pre-gold freeze from repository contracts and structural probes."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

from backend.pipeline.evidence.retrieval.pipeline import EvidenceRetrievalPipeline
from backend.pipeline.agentic.runtime import PLANNER_SYSTEM
from backend.pipeline.agentic.source_verifier import (
    SOURCE_PROFILE_PROMPT_VERSION,
    SOURCE_VERIFIER_SYSTEM,
)
from benchmarks.mtb_evidence.final_experiment.harness import canonical_sha256, plan_runs
from benchmarks.mtb_evidence.final_experiment.smoke import run_smoke

SCHEMA_VERSION = "mtb-final-experiment-generator/1.0"
BASE_COMMIT = "84bcecaafdee60206799fd0a245cb78f816b257e"
CORPUS_VERSION = "qualified_claim_repository/1.4"
CORPUS_HASH = "31636f26c44bee03b16ed7d7c5e9b9580292f750e04b80e4effbaf9618ec39fa"
GATE_VERSION = "qualified_claim_structural_gate/1.3"
RETRIEVER_VERSION = "qualified_claim_retriever/1.0"
GENERATOR_VERSION = "final_experiment_generator/1.0"
CONTENT_SHA256 = "07250910353787808906a9122a2c035e4bb73e739ef1f81dbab0124adc0d4bea"
GENERATED_AT = "2026-07-31T17:00:00+02:00"
ROOT = Path(__file__).resolve().parent


def meta(schema: str) -> dict[str, Any]:
    return {
        "schema_version": schema, "generated_at": GENERATED_AT,
        "base_commit": BASE_COMMIT, "corpus_version": CORPUS_VERSION,
        "corpus_hash": CORPUS_HASH, "gate_version": GATE_VERSION,
        "retriever_version": RETRIEVER_VERSION,
        "generator_version": GENERATOR_VERSION, "content_sha256": "",
    }


def _write_lf(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)

def write_json(name: str, payload: dict[str, Any]) -> None:
    payload = meta(payload.pop("schema_version")) | payload
    payload["content_sha256"] = canonical_sha256(payload)
    _write_lf(ROOT / name, json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def write_jsonl(name: str, rows: list[dict[str, Any]], schema: str) -> None:
    rendered = []
    for row in rows:
        payload = meta(schema) | row
        payload["content_sha256"] = canonical_sha256(payload)
        rendered.append(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    _write_lf(ROOT / name, "\n".join(rendered) + "\n")


def write_text(name: str, schema: str, body: str) -> None:
    prefix = (
        f"schema_version: {schema}\n"
        f"generated_at: {GENERATED_AT}\nbase_commit: {BASE_COMMIT}\n"
        f"corpus_version: {CORPUS_VERSION}\ncorpus_hash: {CORPUS_HASH}\n"
        f"gate_version: {GATE_VERSION}\nretriever_version: {RETRIEVER_VERSION}\n"
        f"generator_version: {GENERATOR_VERSION}\ncontent_sha256: \n\n"
    )
    digest = hashlib.sha256((prefix + body).encode("utf-8")).hexdigest()
    _write_lf(ROOT / name, prefix.replace("content_sha256: \n", f"content_sha256: {digest}\n") + body)


QUERIES = [
    ("Q01",1,"ALK G1202R | NSCLC",{"claim_domain":"therapeutic","gene":"ALK","alteration":"F1174L","disease":"Neuroblastoma"},{"gene":"ALK","variant":"F1174L","tumor_type":"Neuroblastoma","alteration_type":"point_mutation"},True,"Replaced: original is only present as a conjunctive resistance structure; use an atomic direct positive."),
    ("Q02",1,"EGFR L858R | NSCLC",{"claim_domain":"therapeutic","gene":"EGFR","alteration":"L858R","disease":"NSCLC"},{"gene":"EGFR","variant":"L858R","tumor_type":"NSCLC","alteration_type":"point_mutation"},True,"Kept."),
    ("Q03",1,"FGFR2 fusion | Intrahepatic Cholangiocarcinoma",{"claim_domain":"therapeutic","gene":"FGFR2","alteration":"Mutation","disease":"Cholangiocarcinoma"},{"gene":"FGFR2","variant":"Mutation","tumor_type":"Cholangiocarcinoma","alteration_type":"point_mutation"},True,"Replaced: broad fusion is not a corpus expression; selected an atomic positive without partner confounding."),
    ("Q04",2,"EGFR L858R | Lung Adenocarcinoma",{"claim_domain":"therapeutic","biomarker":"FGFR2::BICC1 Fusion","disease":"Cholangiocarcinoma"},{"gene":"FGFR2","variant":"BICC1 Fusion","tumor_type":"Cholangiocarcinoma","alteration_type":"fusion"},True,"Replaced to form a controlled exact/limited/incompatible disease triplet on one claim."),
    ("Q05",2,"FGFR2 fusion | Cholangiocarcinoma",{"claim_domain":"therapeutic","biomarker":"FGFR2::BICC1 Fusion","disease":"Intrahepatic Cholangiocarcinoma"},{"gene":"FGFR2","variant":"BICC1 Fusion","tumor_type":"Intrahepatic Cholangiocarcinoma","alteration_type":"fusion"},True,"Replaced broad biomarker with the exact partner; limited-scope case."),
    ("Q06",2,"FGFR2 fusion | Extrahepatic Cholangiocarcinoma",{"claim_domain":"therapeutic","biomarker":"FGFR2::BICC1 Fusion","disease":"Breast Cancer"},{"gene":"FGFR2","variant":"BICC1 Fusion","tumor_type":"Breast Cancer","alteration_type":"fusion"},True,"Replaced: extrahepatic is unresolved/limited rather than a clean incompatibility; Breast Cancer isolates disease mismatch."),
    ("Q07",3,"EGFR L858R OR Exon 19 Deletion | NSCLC",{"claim_domain":"therapeutic","biomarker":"EGFR L858R OR EGFR Exon 19 Deletion","disease":"NSCLC"},None,False,"Normalized to repeat the gene required by the real boolean parser; V3-specific."),
    ("Q08",3,"EGFR L858R AND T790M | NSCLC",{"claim_domain":"therapeutic","biomarker":"EGFR L858R AND EGFR T790M","disease":"NSCLC"},None,False,"Normalized to repeat the gene; V3-specific."),
    ("Q09",3,"EGFR Exon 19 Deletion AND T790M | NSCLC",{"claim_domain":"therapeutic","biomarker":"EGFR T790M AND EGFR Exon 19 Deletion","disease":"NSCLC"},None,False,"Normalized to the actual corpus conjunction; V3-specific."),
    ("Q10",4,"BGJ398 | FGFR2 fusion | iCCA",{"claim_domain":"therapeutic","biomarker":"FGFR2::BICC1 Fusion","disease":"Cholangiocarcinoma","interventions":["BGJ398"]},None,False,"Exact partner added; retained formulation/legacy-name warning test; V3-specific."),
    ("Q11",4,"infigratinib phosphate | FGFR2 fusion | iCCA",{"claim_domain":"therapeutic","biomarker":"FGFR2::BICC1 Fusion","disease":"Cholangiocarcinoma","interventions":["infigratinib phosphate"]},None,False,"Exact partner added; verified formulation relation test; V3-specific."),
    ("Q12",4,"infigratinib hydrochloride | FGFR2 fusion | iCCA",{"claim_domain":"therapeutic","biomarker":"FGFR2::BICC1 Fusion","disease":"Cholangiocarcinoma","interventions":["infigratinib hydrochloride"]},None,False,"Exact partner added; incompatible formulation control; V3-specific."),
    ("Q13",5,"infigratinib | FGFR2 fusion | iCCA",{"claim_domain":"therapeutic","biomarker":"FGFR2::BICC1 Fusion","disease":"Cholangiocarcinoma","interventions":["infigratinib"]},None,False,"Exact partner added; single-vs-aggregate separability test; V3-specific."),
    ("Q14",5,"erlotinib + ramucirumab | EGFR-mutant NSCLC",{"claim_domain":"therapeutic","biomarker":"EGFR L858R OR EGFR Exon 19 Deletion","disease":"NSCLC","interventions":["erlotinib","ramucirumab"],"intervention_combination":True},None,False,"Expanded EGFR-mutant to the exact corpus expression; regimen test; V3-specific."),
    ("Q15",5,"erlotinib | EGFR-mutant NSCLC",{"claim_domain":"therapeutic","biomarker":"EGFR L858R OR EGFR Exon 19 Deletion","disease":"NSCLC","interventions":["erlotinib"]},None,False,"Expanded EGFR-mutant to exact expression; atomic-vs-regimen test; V3-specific."),
    ("Q16",6,"diagnostic FGFR2::BICC1 | iCCA",{"claim_domain":"diagnostic","biomarker":"FGFR2::BICC1 Fusion","disease":"Intrahepatic Cholangiocarcinoma"},None,False,"Added exact Fusion suffix; V3-specific domain capability."),
    ("Q17",6,"diagnostic FGFR2::AHCYL1 | iCCA",{"claim_domain":"diagnostic","biomarker":"FGFR2::AHCYL1 Fusion","disease":"Intrahepatic Cholangiocarcinoma"},None,False,"Added exact Fusion suffix; V3-specific domain capability."),
    ("Q18",6,"therapeutic FGFR2::BICC1 | iCCA",{"claim_domain":"therapeutic","biomarker":"FGFR2::AHCYL1 Fusion","disease":"Intrahepatic Cholangiocarcinoma"},None,False,"Replaced BICC1 with the already-present AHCYL1 diagnostic concept to avoid duplicating Q05 and isolate therapeutic/diagnostic separation; V3-specific."),
    ("Q19",7,"therapeutic RMI2 alteration | Solid Tumor",{"claim_domain":"therapeutic","gene":"RMI2","alteration":"alteration","disease":"Solid Tumor"},{"gene":"RMI2","variant":"alteration","tumor_type":"Solid Tumor","alteration_type":"atypical"},True,"Kept as documented corpus-absence abstention case."),
    ("Q20",7,"prognostic EGFR mutation status | NSCLC",{"claim_domain":"prognostic","biomarker":"FGFR2::BICC1 Fusion","disease":"Intrahepatic Cholangiocarcinoma"},None,False,"Replaced globally vague biomarker with a present concept and absent prognostic domain; V3-specific."),
    ("Q21",7,"therapeutic EGFR L858R | Melanoma",{"claim_domain":"therapeutic","gene":"EGFR","alteration":"L858R","disease":"Melanoma"},{"gene":"EGFR","variant":"L858R","tumor_type":"Melanoma","alteration_type":"point_mutation"},True,"Kept as disease-incompatible negative."),
]


def audit_queries() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pipeline = EvidenceRetrievalPipeline()
    final, audit = [], []
    for qid, family, original, v3, v2, comparable, reason in QUERIES:
        payload = {"query_id": qid, **v3, "include_audit": True, "result_limit": 500}
        result = pipeline.run(payload, retrieval_backend="qualified_claim_v3").to_dict()["payload"]
        visible = result["primary_ranked_results"] + result["retained_with_warning"]
        audit_relevant = [x for x in result["audit_only_results"] if x.get("gate", {}).get("biomarker_match_result", {}).get("compatible")][:50]
        involved = visible + audit_relevant
        final.append({
            "query_id": qid, "family": family, "final_query": v3,
            "v2_projection": v2, "v3_representable": True,
            "v2_representable": v2 is not None,
            "capability_class": "comparative" if comparable else "v3_specific_capability_test",
            "comparative_inclusion": comparable,
            "expected_structural_buckets": result["bucket_counts"],
            "primary_warning_claim_ids": [x["claim_id"] for x in visible],
            "candidate_claim_ids": [x["claim_id"] for x in involved],
            "graph_evidence_record_ids": [x["graph_evidence_id"] for x in involved],
            "gates_exercised": result["gate_decisions"]["gate_execution_order"],
        })
        audit.append({
            "query_id": qid, "family": family, "original_candidate": original,
            "final_query": v3, "decision": reason,
            "replacement": not reason.startswith("Kept"),
            "corpus_candidate_count": result["candidate_count"],
            "measured_bucket_counts": result["bucket_counts"],
            "visible_claim_ids": [x["claim_id"] for x in visible],
            "audit_relevant_claim_ids": [x["claim_id"] for x in audit_relevant],
            "involved_graph_evidence_record_ids": [x["graph_evidence_id"] for x in involved],
            "single_artifact_dependency_risk": "controlled_and_disclosed" if len(visible) <= 1 else "low",
            "artificiality_or_redundancy_risk": "controlled_contract_test",
            "gold_used": False,
        })
    return final, audit


def metric_contracts() -> list[dict[str, Any]]:
    rows = [
        ("GraphEvidenceRecord recall","retrieval","relevant gold GraphEvidenceRecord retrieved","all relevant gold GraphEvidenceRecord","numerator / denominator","proportion",True),
        ("PMID/source recall","retrieval","relevant gold unique sources retrieved","all relevant gold unique sources","numerator / denominator","proportion",True),
        ("candidate recall","retrieval","relevant gold candidates generated","all relevant gold candidates","numerator / denominator","proportion",True),
        ("Precision@k","retrieval","relevant items in ranks 1..k","fixed k positions; absent positions count nonrelevant","numerator / k","proportion",True),
        ("Recall@k","retrieval","relevant gold items in ranks 1..k","all relevant gold items","numerator / denominator","proportion",True),
        ("MRR","retrieval","sum reciprocal rank of first relevant item, or zero per query","evaluated queries","numerator / denominator","reciprocal-rank mean",True),
        ("primary claim precision","claim_qualification","gold-supported emitted primary claims","all emitted primary claims","numerator / denominator","proportion",True),
        ("overall claim precision","claim_qualification","gold-supported emitted primary or warning claims","all emitted primary or warning claims","numerator / denominator","proportion",True),
        ("qualifier preservation","claim_qualification","emitted claims preserving every gold qualifier","gold-supported emitted claims with qualifiers","numerator / denominator","proportion",True),
        ("disease-scope accuracy","claim_qualification","claims with correct disease scope","claims requiring disease-scope judgement","numerator / denominator","proportion",True),
        ("biomarker-logic accuracy","claim_qualification","claims preserving exact terms and AND/OR operator","claims requiring biomarker-logic judgement","numerator / denominator","proportion",True),
        ("intervention-type accuracy","claim_qualification","claims with correct intervention identity and type","claims requiring intervention judgement","numerator / denominator","proportion",True),
        ("regimen preservation","claim_qualification","regimen claims preserving all and only arm members","gold regimen claim-query units","numerator / denominator","proportion",True),
        ("aggregate-separability accuracy","claim_qualification","aggregate claims correctly retained or separated","aggregate/separability judgement units","numerator / denominator","proportion",True),
        ("formulation accuracy","claim_qualification","claims with correct formulation relation","formulation judgement units","numerator / denominator","proportion",True),
        ("applicability accuracy","claim_qualification","claims with correct applicability class","applicability judgement units","numerator / denominator","proportion",True),
        ("unsupported claim rate","claim_qualification","emitted claims unsupported by gold source","all emitted claims","numerator / denominator","proportion",False),
        ("false atomic attribution rate","claim_qualification","false atomic claims derived from aggregate evidence","atomic claims sourced from aggregate evidence","numerator / denominator","proportion",False),
        ("four-bucket accuracy","bucket","correct primary/warning/audit/rejected assignments","all gold bucket-labelled claim-query pairs","numerator / denominator","proportion",True),
        ("bucket confusion matrix","bucket","count in each predicted/gold bucket cell","all gold bucket-labelled claim-query pairs","cell counts; no scalar collapse","count matrix",None),
        ("over-promotion rate","bucket","gold non-primary items placed in primary","gold non-primary items returned","numerator / denominator","proportion",False),
        ("excessive-conservatism rate","bucket","gold-primary items withheld from primary","all gold-primary items","numerator / denominator","proportion",False),
        ("correct abstention rate","abstention","negative queries with no unsupported positive","all gold negative queries","numerator / denominator","proportion",True),
        ("false abstention rate","abstention","positive queries with no supported positive","all gold positive queries","numerator / denominator","proportion",False),
        ("unresolved handling accuracy","abstention","unresolved items only in permitted non-primary state","all gold unresolved items","numerator / denominator","proportion",True),
        ("negative-case accuracy","abstention","negative queries classified negative or abstain","all gold negative queries","numerator / denominator","proportion",True),
        ("false automatic merge rate","abstention","distinct gold items automatically merged","all automatic merge decisions","numerator / denominator","proportion",False),
        ("citation accuracy","provenance","citations whose locator supports attached claim","all emitted citations","numerator / denominator","proportion",True),
        ("source locator coverage","provenance","claims with a resolvable source locator","all emitted factual claims","numerator / denominator","proportion",True),
        ("claim-to-source traceability","provenance","claims tracing to source unit and GraphEvidenceRecord","all emitted factual claims","numerator / denominator","proportion",True),
        ("gate-explanation completeness","provenance","V3 items with every gate represented or not applicable","all returned V3 items","numerator / denominator","proportion",True),
        ("lineage completeness","provenance","items with complete claim-parent-record lineage","all returned items","numerator / denominator","proportion",True),
        ("provenance completeness","provenance","items satisfying locator, traceability and lineage","all returned items","numerator / denominator","proportion",True),
        ("latency","efficiency","wall-clock milliseconds entry to serialized result","attempted run","median, mean, sample SD, min, max","milliseconds",False),
        ("tool calls","efficiency","completed plus failed tool invocations","attempted run","mean and distribution","count",False),
        ("traversal count","efficiency","graph traversal/query operations","attempted run","mean and distribution","count",False),
        ("token usage","efficiency","provider prompt plus completion tokens","LLM-bearing attempted run","sum and distribution; missing stays null","tokens",False),
        ("cost","efficiency","provider-billed amount when exposed","attempted run","sum in provider currency; unavailable stays null","currency",False),
        ("agentic run variability","efficiency","sample SD across five S2 replicas","query-model cell with five valid replicas","sample SD using n-1","metric-native unit",False),
        ("supported sentence rate","report","fully gold-supported factual sentences","all factual report sentences","numerator / denominator","proportion",True),
        ("partially supported rate","report","partially gold-supported factual sentences","all factual report sentences","numerator / denominator","proportion",False),
        ("unsupported sentence rate","report","unsupported factual sentences","all factual report sentences","numerator / denominator","proportion",False),
        ("qualifier loss","report","sentences dropping a required qualifier","sentences narrating qualified claims","numerator / denominator","proportion",False),
        ("scope broadening","report","sentences broader than source scope","factual sentences with scoped source","numerator / denominator","proportion",False),
        ("aggregate/regimen atomization in narration","report","sentences falsely atomizing aggregate/regimen evidence","sentences narrating aggregate/regimen claims","numerator / denominator","proportion",False),
    ]
    return [{"name":n,"group":g,"numerator":a,"denominator":b,"formula":f,"unit":u,"higher_is_better":h} for n,g,a,b,f,u,h in rows]

def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    queries, audit = audit_queries()
    v3_renderer_prompt = "Render only the supplied qualified claims. Preserve disease, biomarker boolean logic, intervention identity/formulation, regimen membership, domain, bucket, warnings and citations. Do not alter eligibility, gates, bucket or structural score. Do not merge claims. If no qualified primary or warning claim exists, abstain."
    prompts=ROOT/"prompts_v1"; prompts.mkdir(exist_ok=True)
    write_text("prompts_v1/planner_prompt_v1.txt","mtb-final-prompt/1.0",f"source: backend.pipeline.agentic.runtime.PLANNER_SYSTEM\nmax_steps: 8\ncall_timeout_seconds: 20\ntotal_budget_seconds: 30\n\n{PLANNER_SYSTEM.rstrip()}\n")
    write_text("prompts_v1/source_verifier_prompt_v1.txt","mtb-final-prompt/1.0",f"source: backend.pipeline.agentic.source_verifier.SOURCE_VERIFIER_SYSTEM\nprompt_version: {SOURCE_PROFILE_PROMPT_VERSION}\n\n{SOURCE_VERIFIER_SYSTEM.rstrip()}\n")
    write_text("prompts_v1/v3_renderer_prompt_v1.txt","mtb-final-prompt/1.0",v3_renderer_prompt+"\n")
    prompt_manifest={path.name:re.search(r"^content_sha256: ([0-9a-f]{64})$",path.read_text(encoding="utf-8"),re.MULTILINE).group(1) for path in sorted(prompts.glob("*.txt"))}
    prompt_bundle_sha256 = hashlib.sha256(json.dumps(prompt_manifest,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
    repo_root=ROOT.parents[2]
    source_files=set()
    for pattern in ("backend/comparison/*.py","backend/pipeline/control/**/*.py","backend/pipeline/agentic/*.py","backend/pipeline/agents/*.py","backend/pipeline/evidence/**/*.py"):
        source_files.update(repo_root.glob(pattern))
    source_files.update((repo_root/"backend/api/schemas.py",repo_root/"backend/pipeline/llm/__init__.py"))
    source_manifest={path.relative_to(repo_root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(source_files)}
    source_bundle_sha256 = hashlib.sha256(json.dumps(source_manifest,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
    systems = {
        "schema_version":"mtb-final-systems/1.0",
        "prompt_bundle_sha256":prompt_bundle_sha256,
        "prompt_manifest":prompt_manifest,
        "source_bundle_sha256":source_bundle_sha256,
        "source_manifest":source_manifest,
        "evaluation_models":["gemma4:31b-cloud","ROBUSTNESS_MODEL_BLOCKED"],
        "systems":{
            "S1":{"name":"V2 deterministic","entrypoint":"backend.comparison.live_runs.build_run","strategy":"FixedPlanStrategy","langgraph":False,"max_steps":None,"llm_components":["variant_interpreter","source_verifier"],"deterministic_components":["fixed planning","traversal order","replay","projection","rendering","structural verifier"]},
            "S2":{"name":"V2 agentic","entrypoint":"backend.comparison.live_runs.build_run","strategy":"AgenticPlanStrategy","langgraph":False,"max_steps":8,"stopping":"finish only after mandatory tools; otherwise max_steps or safe fallback","llm_components":["planner","variant_interpreter","source_verifier"],"deterministic_components":["allow-list","replay","projection","rendering","structural verifier"]},
            "S3":{"name":"V3 qualified claim retriever","entrypoint":"EvidenceRetrievalPipeline.run(retrieval_backend=qualified_claim_v3)","langgraph":False,"llm_components":["optional post-retrieval renderer only"],"structural_llm_decisions":False,"dense_retriever":False,"encoder":False,"cross_encoder":False,"gate_order":["status","domain","biomarker","disease","intervention","formulation","regimen","direction","bucket","score","rank","render"]},
        },
        "comparative_query_count":sum(q["comparative_inclusion"] for q in queries),
        "v3_only_query_count":sum(not q["comparative_inclusion"] for q in queries),
    }
    write_jsonl("queries_v1.jsonl", queries, "mtb-final-query/1.0")
    write_jsonl("queries_candidate_audit.jsonl", audit, "mtb-final-query-audit/1.0")
    write_json("systems_v1.json", systems)
    frozen_queries = [json.loads(line) for line in (ROOT / "queries_v1.jsonl").read_text(encoding="utf-8").splitlines() if line]
    frozen_systems = json.loads((ROOT / "systems_v1.json").read_text(encoding="utf-8"))
    planned = plan_runs(frozen_systems, frozen_queries)
    run_plan_rows = [{"run_key":row["run_key"],"run_spec":{key:value for key,value in row.items() if key != "run_key"},"status":"blocked" if row["model"] == "ROBUSTNESS_MODEL_BLOCKED" else "planned","pilot_only":False,"final_evaluable":row["model"] != "ROBUSTNESS_MODEL_BLOCKED"} for row in planned]
    write_jsonl("run_plan_v1.jsonl", run_plan_rows, "mtb-final-run-plan-record/1.0")
    write_json("models_v1.json", {"schema_version":"mtb-final-models/1.0","temperature":0,"primary":{"requested":"gemma4:31b-cloud","effective":"gemma4:31b-cloud","status":"verified","http_status":200,"prompt_tokens":18,"completion_tokens":2,"latency_ms":1397},"robustness":{"requested":"qwen3-coder-next","status":"retired","http_status":410,"retired_at":"2026-07-15T00:00:00-07:00","successor_probe":"qwen3.5:397b","successor_status":"subscription_required","readiness":"blocked"},"supplementary_judge":{"requested":"minimax-m2.5","status":"retired","http_status":410,"retired_at":"2026-07-31T00:00:00-07:00","replacement":"minimax-m3","replacement_status":"verified","replacement_http_status":200,"latency_ms":1641},"judge_is_gold":False,"judge_controls_primary_conclusion":False})
    metric_groups={
        "retrieval":["GraphEvidenceRecord recall","PMID/source recall","candidate recall","Precision@k","Recall@k","MRR"],
        "claim_qualification":["primary claim precision","overall claim precision","qualifier preservation","disease-scope accuracy","biomarker-logic accuracy","intervention-type accuracy","regimen preservation","aggregate-separability accuracy","formulation accuracy","applicability accuracy","unsupported claim rate","false atomic attribution rate"],
        "bucket":["four-bucket accuracy","bucket confusion matrix","over-promotion rate","excessive-conservatism rate"],
        "abstention":["correct abstention rate","false abstention rate","unresolved handling accuracy","negative-case accuracy","false automatic merge rate"],
        "provenance":["citation accuracy","source locator coverage","claim-to-source traceability","gate-explanation completeness","lineage completeness","provenance completeness"],
        "efficiency":["latency","tool calls","traversal count","token usage","cost","agentic run variability"],
        "report":["supported sentence rate","partially supported rate","unsupported sentence rate","qualifier loss","scope broadening","citation accuracy","aggregate/regimen atomization in narration"],
    }
    metric_definitions=metric_contracts()
    write_json("metrics_v1.json", {"schema_version":"mtb-final-metrics/1.0","primary_endpoint":"paired claim-level primary precision on the 8-query fair comparative subset","groups":metric_groups,"definitions":metric_definitions,"zero_denominator_policy":"undefined/null with numerator and denominator retained; never coerce to zero","ndcg":{"enabled":False,"condition":"enable only if the unopened gold contains valid graded relevance"},"statistics":{"paired_by_query":True,"effect_size":"paired standardized mean difference plus raw mean difference","bootstrap_ci":0.95,"bootstrap_unit":"query","agentic_summary":["mean","sample_sd","min","max"],"claim":"exploratory; not general clinical validation"}})
    write_json("protocol_v1.json", {"schema_version":"mtb-final-protocol/1.0","research_question":"Does evidence-centric V3 improve claim-level precision, qualifier preservation, and verifiability over V2 without excessive coverage loss?","hypotheses":["H1 V3 increases claim-level precision","H2 V3 better preserves disease, biomarker, intervention and separability qualifiers","H3 V3 reduces unsupported claims and false atomic attribution","H4 V3 improves provenance and auditability","H5 conservative V3 policy may reduce primary-bucket recall","H6 agentic V2 does not stably improve quality over deterministic V2 but increases latency and variability"],"primary_endpoint":"paired claim-level primary precision","secondary_endpoints":list(metric_groups),"exploratory":["V3-specific capability tests","judge scores","failure-stage decomposition"],"ablations":[],"stopping_conditions":["gold state not authorized","frozen artifact hash mismatch","corpus/gate/model mismatch","three repeated identical infrastructure failures"],"missing_data_policy":"retain failed/missing run as classified missing; no silent imputation; paired endpoint uses predeclared available-pair analysis plus missingness table","timeout_policy":{"planner_call_seconds":20,"planner_total_seconds":30,"model_call_seconds":60,"system_run_seconds":600},"retry_policy":{"planner_first_decision_retries":1,"official_run_retries":0,"infrastructure_retry_after_manual_authorization":1},"failure_classification":["candidate_generation","retrieval","qualification","ranking","llm_rendering","infrastructure","timeout","schema","gold_boundary"],"run_plan":{"system_runs_total":len(planned),"currently_executable_system_runs":98,"blocked_system_runs":98,"per_evaluation_model":{"S1":16,"S2":40,"S3":42,"total":98},"evaluation_models":2,"supplementary_judge_calls":24,"report_rendering":"one report for replica 1; replicas otherwise retrieval/control determinism only"},"llm_budget":{"expected_calls_including_one_source_verifier_batch_per_v2_run":690,"upper_bound_calls_with_bounded_retries":1042,"estimated_input_tokens":6800000,"estimated_output_tokens":1250000,"token_estimate_not_quota":True,"monetary_cost":"not computable from local/provider API; no price contract exposed","estimated_elapsed_hours_sequential":[6,12]},"environment":{"python":"3.12.10","dependency_snapshot":{"pip_freeze_sha256":"21e8fe48ff91309d81a422752edf01c654e9e16c6179adbf1bc9a610fc043966","package_count":180,"requirements_file":"backend/config/requirements.txt","requirements_sha256":"7fe6024dbd4a7b353baae8d2d556a33f1e5c762ec122bd11c384ff8c5c869de2"},"os":{"name":"Windows 11","version":"10.0.26200","architecture":"AMD64"},"hardware":{"processor":"Intel64 Family 6 Model 154 Stepping 3, GenuineIntel","physical_cores":10,"logical_cores":16,"ram_bytes":34049417216,"gpu":"not detected; nvidia-smi unavailable"},"external_services":{"neo4j":{"reachable":False,"required_for_official_v2":True},"ollama_cloud":{"reachable":True},"oncokb":{"credential_present":True,"connectivity_not_probed":True}},"available_backends":["legacy","qualified_claim_v3"]},"artifact_hash_convention":"JSON/JSONL blank the top-level content_sha256 value before canonical serialization; Markdown/text blank only the content_sha256 value and retain the metadata line","post_gold_immutability":["no gate changes","no scoring changes","no mapping changes","no query changes","no primary prompt changes","no result-driven tuning"],"post_hoc_policy":"any later correction is labelled post_hoc and excluded from the primary result","gold_state":"NOT_OPENED_FOR_FINAL_EXPERIMENT","official_runs_enabled":False})
    write_json("gold_external_manifest.json", {"schema_version":"mtb-final-gold-manifest/1.0","external_identifier":"MTB_Evidence_gold_pilot_v1","expected_files":{"MTB_Evidence_annotation_notes_v1.md":"72ee84c53bfb5d6634f238a771d6b52b1a8f03bfe36b4ab3e577932be7b72520","MTB_Evidence_gold_pilot_v1.xlsx":"128a68c5aa324ef8a4f033d2a2721c251583b9ac0a8d83d6b603ba1aad662124","mtb_evidence_gold_pilot_v1.jsonl":"30e64dc5f3dffde3d1d43c316f6bc75f1afafab41567fa8657214a10fa16c667"},"aggregate_sha256":"5e6d79f04eeaecbabd573a0eb5a636f51bcba55010e2af5f560419479149ac1f","gold_schema":"mtb_evidence_gold_pilot/1.0","state":"NOT_OPENED_FOR_FINAL_EXPERIMENT","content_read":False})
    run_schema={"schema_version":"mtb-final-run-manifest-schema/1.0","$schema":"https://json-schema.org/draft/2020-12/schema","$id":"urn:mtb-graphrag:final-experiment:run-manifest:1","title":"Frozen final-experiment run manifest record","type":"object","additionalProperties":False,"required":["run_key","run_spec","status","pilot_only","final_evaluable"],"properties":{"run_key":{"type":"string","pattern":"^[0-9a-f]{64}$"},"run_spec":{"type":"object","required":["system","query_id","model","replica","base_commit","corpus_hash","gate_version","retriever_version","generator_version","systems_config_sha256","query_config_sha256","prompt_bundle_version","prompt_bundle_sha256","source_bundle_sha256"]},"status":{"enum":["planned","blocked","running","complete","failed"]},"pilot_only":{"type":"boolean"},"final_evaluable":{"type":"boolean"},"started_at":{"type":["string","null"]},"completed_at":{"type":["string","null"]},"failure_stage":{"type":["string","null"]},"result_content_sha256":{"type":["string","null"],"pattern":"^[0-9a-f]{64}$"}}}
    artifact_properties={"schema_version":{"type":"string"},"generated_at":{"type":"string"},"base_commit":{"const":BASE_COMMIT},"corpus_version":{"const":CORPUS_VERSION},"corpus_hash":{"const":CORPUS_HASH},"gate_version":{"const":GATE_VERSION},"retriever_version":{"const":RETRIEVER_VERSION},"generator_version":{"const":GENERATOR_VERSION},"content_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"}}
    run_schema["properties"].update(artifact_properties | {"result":{"type":"object"}})
    run_schema["required"].extend(artifact_properties)
    run_schema["allOf"]=[{"if":{"properties":{"status":{"const":"complete"}}},"then":{"required":["result_content_sha256","result"]}}]
    write_json("run_manifest_schema.json", run_schema)
    result_schema={"schema_version":"mtb-final-result-schema/1.0","$schema":"https://json-schema.org/draft/2020-12/schema","$id":"urn:mtb-graphrag:final-experiment:result:1","title":"Native final-experiment result envelope","type":"object","additionalProperties":False,"required":["run_key","system_id","query_id","pilot_only","final_evaluable","native_result","measurements","failure_stage"],"properties":{"run_key":{"type":"string","pattern":"^[0-9a-f]{64}$"},"system_id":{"enum":["S1","S2","S3"]},"query_id":{"type":"string"},"pilot_only":{"type":"boolean"},"final_evaluable":{"type":"boolean"},"native_result":{"type":"object"},"measurements":{"type":"object","required":["candidate_records","graph_evidence_records","claims","bucket","ranking","provenance","warnings","gate_trace","latency_ms","tool_calls","token_usage","cost"],"properties":{"candidate_records":{"type":"array"},"graph_evidence_records":{"type":"array"},"claims":{"type":"array"},"bucket":{"type":["object","null"]},"ranking":{"type":["array","null"]},"provenance":{"type":["object","array"]},"warnings":{"type":"array"},"gate_trace":{"type":["object","array","null"]},"latency_ms":{"type":"number","minimum":0},"tool_calls":{"type":"integer","minimum":0},"token_usage":{"type":["object","null"]},"cost":{"type":["object","null"]}}},"failure_stage":{"enum":[None,"candidate_generation","retrieval","qualification","ranking","llm_rendering","infrastructure","timeout","schema","gold_boundary"]}},"native_envelopes":{"S1":"ArchitectureRun + PipelineResult","S2":"ArchitectureRun + PipelineResult","S3":"RetrievalOutcome + QualifiedClaimRetrievalResult"}}
    result_schema["properties"].update(artifact_properties)
    result_schema["required"].extend(artifact_properties)
    write_json("result_schema.json", result_schema)
    smoke = run_smoke()
    write_json("smoke_test_report.json", {"schema_version":"mtb-final-smoke-report/1.0",**smoke,"model_probes":{"gemma4:31b-cloud":"verified","qwen3-coder-next":"retired","minimax-m2.5":"retired","minimax-m3":"verified"},"official_runs_executed":0,"gold_payload_reads":0,"known_pilot_contamination":"an early pre-freeze smoke appended synthetic events to the default append-only ledger; current smoke uses isolated temporary ledgers"})
    readiness = all(value is True for key, value in smoke["checks"].items() if key != "gold_read_count") and smoke["checks"].get("gold_read_count") == 0
    write_json("readiness_report.json", {"schema_version":"mtb-final-readiness/1.0","repository_closure":True,"query_protocol_frozen":True,"smoke_checks_green":readiness,"model_readiness":False,"blockers":["Neo4j legacy graph service unreachable","robustness model qwen3-coder-next retired; successor requires subscription","an early pilot smoke appended synthetic events to the default append-only ledger before isolation was corrected"],"final_experiment_protocol_frozen":False,"gold_opening_authorized":False,"official_runs_authorized":False})
    write_text("protocol_v1.md","mtb-final-protocol-markdown/1.0",f"# Final comparative evaluation protocol v1\n\nThe structured primary experiment compares S1, S2 and S3 on the {sum(q['comparative_inclusion'] for q in queries)}-query fair subset; all 21 queries run on S3. The primary endpoint is paired claim-level primary precision. H1-H6 and all query, model, metric, timeout, retry, missing-data and failure rules are frozen in `protocol_v1.json`.\n\nNo gold payload has been opened. No official run is authorized. The protocol remains readiness-blocked because the robustness model is unavailable and Neo4j is offline.\n\nAfter gold opening, gate, scoring, mappings, queries, primary prompts, models, metrics, and evaluation code are immutable for the primary analysis. The opening timestamp and bundle digest must be recorded. Any later correction is versioned and labelled post_hoc and is excluded from the primary result.\n")
    write_text("analysis_plan_v1.md","mtb-final-analysis-plan/1.0","# Analysis plan\n\nUse query-paired differences and query-level percentile bootstrap 95% intervals. Report effect size and raw numerator/denominator for every metric. For S2 report mean, sample standard deviation, minimum and maximum over five runs. Keep candidate-generation, retrieval, qualification, ranking and LLM-rendering failures separate. nDCG remains disabled unless graded gold is valid. All conclusions are exploratory and are not general clinical validation.\n")
    prompts=ROOT/"prompts_v1"; prompts.mkdir(exist_ok=True)
    write_text("prompts_v1/planner_prompt_v1.txt","mtb-final-prompt/1.0",f"source: backend.pipeline.agentic.runtime.PLANNER_SYSTEM\nmax_steps: 8\ncall_timeout_seconds: 20\ntotal_budget_seconds: 30\n\n{PLANNER_SYSTEM.rstrip()}\n")
    write_text("prompts_v1/source_verifier_prompt_v1.txt","mtb-final-prompt/1.0",f"source: backend.pipeline.agentic.source_verifier.SOURCE_VERIFIER_SYSTEM\nprompt_version: {SOURCE_PROFILE_PROMPT_VERSION}\n\n{SOURCE_VERIFIER_SYSTEM.rstrip()}\n")
    write_text("prompts_v1/v3_renderer_prompt_v1.txt","mtb-final-prompt/1.0",v3_renderer_prompt+"\n")
    seal_sources()


def seal_sources() -> None:
    pattern = re.compile(r'^CONTENT_SHA256 = ".*"$', re.MULTILINE)
    for path in ROOT.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        normalized = pattern.sub('CONTENT_SHA256 = ""', text)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        _write_lf(path, pattern.sub(f'CONTENT_SHA256 = "{digest}"', text))


if __name__ == "__main__":
    main()

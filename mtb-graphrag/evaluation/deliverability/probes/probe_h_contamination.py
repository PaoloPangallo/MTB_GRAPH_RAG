"""Probe H — Contaminazione sperimentale e riproducibilita' (§24, §25)."""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(sys.argv[1]).resolve()

NEEDLE = "C:" + chr(92) + "Users"          # C:\Users
NEEDLE_JSON = "C:" + chr(92) * 2 + "Users"  # C:\\Users (escaped in JSON)

out = {}

# --- 1. percorsi assoluti locali negli artifact committati -------------------
hits = []
for pattern in ("evaluation/**/*.json", "evaluation/**/*.jsonl", "evaluation/**/*.csv",
                "benchmarks/**/*.json"):
    for p in ROOT.glob(pattern):
        if "deliverability" in str(p):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if NEEDLE in text or NEEDLE_JSON in text:
            hits.append(str(p.relative_to(ROOT)).replace("\\", "/"))
out["local_absolute_paths_in_committed_artifacts"] = sorted(hits)

# --- 2. mock / fixture raggiungibili dal runtime -----------------------------
runtime_dir = ROOT / "backend" / "research_pipeline"
mock_hits = []
for p in runtime_dir.rglob("*.py"):
    if "__pycache__" in str(p) or "/tests/" in str(p).replace("\\", "/"):
        continue
    text = p.read_text(encoding="utf-8", errors="ignore")
    for kw in ("unittest.mock", "MagicMock", "monkeypatch", "FIXTURE", "DUMMY_", "FAKE_"):
        if kw in text:
            mock_hits.append({"file": str(p.relative_to(ROOT)).replace("\\", "/"), "keyword": kw})
out["mock_or_fixture_reachable_from_runtime"] = mock_hits

# --- 3. cache non dichiarate (lru_cache) nel runtime -------------------------
caches = []
for p in runtime_dir.rglob("*.py"):
    if "__pycache__" in str(p) or "/tests/" in str(p).replace("\\", "/"):
        continue
    text = p.read_text(encoding="utf-8", errors="ignore")
    n = text.count("lru_cache")
    if n:
        caches.append({"file": str(p.relative_to(ROOT)).replace("\\", "/"), "lru_cache_count": n})
out["module_level_caches_in_runtime"] = caches

# --- 4. artifact non versionati che potrebbero entrare in una metrica --------
import subprocess
untracked = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                           cwd=ROOT.parent, capture_output=True, text=True).stdout
out["untracked_experimental_artifacts"] = [
    line[3:] for line in untracked.splitlines()
    if line.startswith("??") and ("exploratory" in line or "manual_v3" in line)
]

# --- 5. denominatori: candidate raggiungibili end-to-end ---------------------
D = ROOT / "benchmarks/mtb_evidence/document_grounded_claims"
bundles = [json.loads(l) for l in (D / "evidence_bundle/evidence_bundles.jsonl")
           .read_text(encoding="utf-8").splitlines() if l.strip()]
out["denominators"] = {
    "candidates_v2_total": 46864,
    "evidence_bundles": len(bundles),
    "distinct_candidates_with_bundle": len({b["candidate_id"] for b in bundles}),
    "distinct_documents": len({b["document_id"] for b in bundles}),
    "frozen_enricher_calls": 7,
    "end_to_end_reachable_fraction": round(len({b["candidate_id"] for b in bundles}) / 46864, 6),
}

# --- 6. duplicati nelle righe di evaluation ----------------------------------
dups = {}
for p in (ROOT / "evaluation").rglob("*.jsonl"):
    if "deliverability" in str(p):
        continue
    lines = [l for l in p.read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip()]
    if lines and len(lines) != len(set(lines)):
        dups[str(p.relative_to(ROOT)).replace("\\", "/")] = {
            "rows": len(lines), "unique": len(set(lines))}
out["duplicated_evaluation_rows"] = dups

# --- 7. self-comparison del materializzatore ---------------------------------
rq1_src = (ROOT / "evaluation/rq1/kg_source.py").read_text(encoding="utf-8", errors="ignore")
mat_src = (ROOT / "gca_v3/materialize.py").read_text(encoding="utf-8", errors="ignore")
out["materializer_self_comparison"] = {
    "rq1_reads_raw_csv_export": "csv" in rq1_src.lower(),
    "rq1_imports_gca_v3_materialize": "gca_v3" in rq1_src or "materialize" in rq1_src,
    "note": ("RQ1 confronta candidates.jsonl con l'export CSV del grafo. Se importasse il "
             "materializzatore per generare il proprio atteso, sarebbe self-comparison."),
}

print(json.dumps(out, indent=1, ensure_ascii=False))

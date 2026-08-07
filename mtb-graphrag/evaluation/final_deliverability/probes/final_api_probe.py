"""Audit finale — verifica a livello di API REALE (§6, §13).

TestClient su backend.api.main:app, lo stesso percorso che serve uvicorn.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
os.environ["VERIFIABLE_PIPELINE_RESEARCH_ENABLED"] = "1"
os.environ.setdefault("RESEARCH_LEDGER_PATH", str(Path(sys.argv[2]).resolve()))

from fastapi.testclient import TestClient  # noqa: E402

from backend.api.main import app  # noqa: E402

C = TestClient(app)
BASE = "/api/v1/research/pipeline"
R: dict = {}


def poll(run_id, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        r = C.get(f"{BASE}/runs/{run_id}")
        if r.status_code != 200:
            return {"http": r.status_code}
        s = r.json()
        if s["status"] not in ("CREATED", "RUNNING"):
            return s
        time.sleep(0.5)
    return {"timeout": True}


# ── §13 LIVE senza servizi: deve fallire, non degradare in REPLAY ────────────
live = C.post(f"{BASE}/runs", json={"demo_case_key": "CASE-1-therapy-evaluation-strong-match",
                                    "execution_mode": "LIVE"})
R["live_without_services"] = {
    "http": live.status_code,
    "body": live.json() if live.status_code != 201 else None,
    "degraded_to_replay": live.status_code == 201,
}

# HYBRID non richiedibile
hyb = C.post(f"{BASE}/runs", json={"demo_case_key": "CASE-1-therapy-evaluation-strong-match",
                                   "execution_mode": "HYBRID"})
R["hybrid_requestable"] = {"http": hyb.status_code, "rejected": hyb.status_code != 201}

# modalita' sconosciuta
unk = C.post(f"{BASE}/runs", json={"demo_case_key": "CASE-1-therapy-evaluation-strong-match",
                                   "execution_mode": "DEMO"})
R["unknown_mode_rejected"] = {"http": unk.status_code, "rejected": unk.status_code != 201}

# REPLAY su un caso senza artefatti congelati
nofrozen = C.post(f"{BASE}/runs", json={"case_id": "INEDITO",
                                        "clinical_text": "A patient with colorectal cancer.",
                                        "execution_mode": "REPLAY"})
R["replay_without_frozen_artifacts"] = {"http": nofrozen.status_code,
                                        "rejected": nofrozen.status_code != 201}

# ── §6 catena di grounding su una run REPLAY reale ──────────────────────────
runs = {}
for case in ("CASE-1-therapy-evaluation-strong-match",   # documento disponibile
             "CASE-2-therapy-discovery",                  # discovery
             "CASE-4-contradicted-or-resistance",         # documento senza supporto esplicito
             "CASE-5-casecontext-mismatch-no-match"):     # nessuna candidate
    created = C.post(f"{BASE}/runs", json={"demo_case_key": case, "execution_mode": "REPLAY"})
    if created.status_code != 201:
        runs[case] = {"create_http": created.status_code, "body": created.text[:300]}
        continue
    rid = created.json()["run_id"]
    snap = poll(rid)
    entry = {
        "run_id": rid, "status": snap.get("status"),
        "execution_mode": snap.get("execution_mode"),
        "fully_live": snap.get("fully_live"),
        "replay_artifacts_used": snap.get("replay_artifacts_used"),
        "llm_calls": snap.get("llm_calls"),
        "stopped_at": snap.get("stopped_at"),
        "origin_counts": snap.get("origin_counts"),
    }
    # dossier
    dos = C.get(f"{BASE}/runs/{rid}/dossier")
    entry["dossier_http"] = dos.status_code
    if dos.status_code == 200:
        d = dos.json()["dossier"]
        voices, missing_state, presentable_not_gated = [], 0, 0
        for t in d.get("candidate_therapies", []):
            for v in t.get("author_context", []):
                voices.append({"presentation_state": v.get("presentation_state"),
                               "validation_outcome": v.get("validation_outcome"),
                               "accepted_for_gates": v.get("accepted_for_gates"),
                               "has_quote": bool(v.get("author_claim_quote"))})
                if "presentation_state" not in v:
                    missing_state += 1
                if v.get("presentation_state") == "VALIDATED_QUOTE" and not v.get("accepted_for_gates"):
                    presentable_not_gated += 1
        entry["author_context_voices"] = voices
        entry["voices_missing_presentation_state"] = missing_state
        entry["presentable_but_not_gated"] = presentable_not_gated
        entry["candidate_count"] = len(d.get("candidate_therapies", []))
        entry["statuses"] = [t.get("status") for t in d.get("candidate_therapies", [])]
        entry["buckets"] = [t.get("gate_results", {}).get("bucket")
                            for t in d.get("candidate_therapies", [])]
    # provenance
    prov = C.get(f"{BASE}/runs/{rid}/provenance")
    entry["provenance_http"] = prov.status_code
    if prov.status_code == 200:
        p = prov.json()
        entry["provenance_keys"] = sorted(p.keys())[:14]
    runs[case] = entry
R["replay_runs"] = runs

# ── config: cosa dichiara il runtime ────────────────────────────────────────
cfg = C.get(f"{BASE}/config")
R["config"] = cfg.json() if cfg.status_code == 200 else {"http": cfg.status_code}

print(json.dumps(R, indent=1, ensure_ascii=False, default=str))

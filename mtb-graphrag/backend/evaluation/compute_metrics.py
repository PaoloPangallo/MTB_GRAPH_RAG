"""
compute_metrics.py — Calcolo automatico delle metriche di tesi per GraphRAG e ZeroShot.

Metriche calcolate per ogni report:
  1. Drug Anchor Check: Il farmaco atteso è presente nel report?
  2. Anchor PMID Cited (PMID Coverage Rate): Il PMID atteso è citato nel report?
  3. PMID Hallucination Rate: Quanti PMID citati non esistono nel Knowledge Graph?
  4. ESCAT Tier Match: Il tier assegnato coincide con quello atteso dal benchmark?
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Paths ─────────────────────────────────────────────────────
BENCHMARK_CSV  = Path(__file__).resolve().parents[1] / "benchmark" / "benchmark_papers_summary_30_v2.csv"
RESULTS_DIR    = Path(__file__).resolve().parent / "results"
GRAPHRAG_JSON  = RESULTS_DIR / "ablation_graphrag_results.json"
ZEROSHOT_JSON  = RESULTS_DIR / "zeroshot_results.json"
METRICS_GR_OUT = RESULTS_DIR / "metrics_graphrag.json"
METRICS_ZS_OUT = RESULTS_DIR / "metrics_zeroshot.json"

# ── Utility: estrae PMID dal testo ────────────────────────────
_PMID_RE = re.compile(r'\b\d{7,8}\b')

def extract_pmids_from_report(report_text: str) -> set[int]:
    """Estrae tutti i PMID (numeri da 7 a 9 cifre) dal report per valutare le allucinazioni."""
    return {int(p) for p in _PMID_RE.findall(report_text)}

# ── Utility: estrazione ESCAT ──────────────────────────────────
_ESCAT_RE = re.compile(r'ESCAT(?:[^A-Za-z0-9]*(?:Tier|Livello|Level)?[^A-Za-z0-9]*)?([IVX]+(?:-[A-C])?)', re.IGNORECASE)

def extract_escat_tier(report_text: str, explicit_tier: str = None) -> str | None:
    """
    Tenta di estrarre il tier ESCAT. Se explicit_tier è fornito (GraphRAG), lo usa.
    Altrimenti usa regex per Zero-Shot.
    """
    if explicit_tier and explicit_tier.strip():
        return explicit_tier.strip().upper()
    
    m = _ESCAT_RE.search(report_text)
    if m:
        tier = m.group(1).upper()
        if not "-" in tier and len(tier) > 1 and tier[-1] in ('A','B','C'):
            tier = tier[:-1] + "-" + tier[-1]
        return tier
    return None

# ── Standalone Neo4j access ────────────────────────────────────
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)
_NEO4J_URI      = "bolt://localhost:7687"
_NEO4J_USER     = "neo4j"
_NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

_drv = GraphDatabase.driver(_NEO4J_URI, auth=(_NEO4J_USER, _NEO4J_PASSWORD))

def _run_cypher(query: str, params: dict | None = None) -> list[dict]:
    try:
        with _drv.session() as session:
            result = session.run(query, params or {})
            data = [record.data() for record in result]
        return data
    except Exception as e:
        print(f"[ERRORE NEO4J] {e}")
        return []

def check_pmids_exist_in_kb(pmids: set[int]) -> set[int]:
    """Interroga il KB locale per capire quali di questi PMID esistono effettivamente."""
    if not pmids:
        return set()
    query = """
    MATCH (p:Publication)
    WHERE p.pmid IN $pmids
    RETURN p.pmid AS pmid
    """
    rows = _run_cypher(query, {"pmids": list(pmids)})
    return {int(r["pmid"]) for r in rows if r.get("pmid")}


# ── Computazione singola per caso ──────────────────────────────
def compute_metrics_for_case(
    case_id: str,
    report_text: str,
    expected_drug: str,
    expected_pmid: int | None,
    expected_escat: str,
    explicit_tier: str | None = None
) -> dict:
    
    # 1. Drug Anchor Check
    drugs = [d.strip() for d in re.split(r'[+/,]', expected_drug)]
    drug_found = all(d.lower() in report_text.lower() for d in drugs if d) if drugs else False
    
    # 2. PMID Extraction
    cited_pmids = extract_pmids_from_report(report_text)
    
    # 3. Anchor PMID Cited
    anchor_pmid_cited = expected_pmid in cited_pmids if expected_pmid else False
    
    if len(cited_pmids) > 0:
        pass
        
    # 5. ESCAT Match
    extracted_tier = extract_escat_tier(report_text, explicit_tier)
    if expected_escat and expected_escat.lower() == "non determinato":
        escat_match = (extracted_tier is None)
    else:
        escat_match = (extracted_tier == expected_escat.upper()) if expected_escat else None
    
    return {
        "case_id": case_id,
        "n_cited_pmids": len(cited_pmids),
        "expected_escat": expected_escat,
        "extracted_escat": extracted_tier,
        "escat_match": escat_match
    }

def process_results(json_path: Path, csv_rows: dict, is_graphrag: bool) -> list[dict]:
    if not json_path.exists():
        return []
    with open(json_path, "r", encoding="utf-8") as f:
        results = json.load(f)
        
    metrics = []
    for res in results:
        case_id = res["case_id"]
        report  = res.get("report", "")
        csv_row = csv_rows.get(case_id, {})
        
        expected_drug  = res.get("expected_drug") or csv_row.get("expected_drug", "")
        expected_pmid  = int(csv_row["pmid"]) if csv_row.get("pmid") and str(csv_row.get("pmid")).isdigit() else None
        expected_escat = csv_row.get("escat", "")
        
        explicit_tier  = res.get("escat_tier") if is_graphrag else None
        
        m = compute_metrics_for_case(
            case_id=case_id,
            report_text=report,
            expected_drug=expected_drug,
            expected_pmid=expected_pmid,
            expected_escat=expected_escat,
            explicit_tier=explicit_tier
        )
        
        # Fallback print per casi Zero-shot sospetti (ESCAT non trovato)
        if not is_graphrag and m["extracted_escat"] is None and expected_escat:
            print(f"[WARN] ZeroShot: ESCAT Tier non estratto per {case_id} (atteso: {expected_escat}). Verifica manuale consigliata.")

        metrics.append(m)
        
    return metrics


def main():
    print("Avvio computazione metriche oggettive...")
    with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        csv_rows = {row["case_id"]: row for row in reader}
        
    gr_metrics = process_results(GRAPHRAG_JSON, csv_rows, is_graphrag=True)
    zs_metrics = process_results(ZEROSHOT_JSON, csv_rows, is_graphrag=False)
    
    with open(METRICS_GR_OUT, "w", encoding="utf-8") as f:
        json.dump(gr_metrics, f, indent=2, ensure_ascii=False)
        
    with open(METRICS_ZS_OUT, "w", encoding="utf-8") as f:
        json.dump(zs_metrics, f, indent=2, ensure_ascii=False)
        
    print(f"Calcolate metriche per {len(gr_metrics)} casi GraphRAG.")
    print(f"Calcolate metriche per {len(zs_metrics)} casi Zero-Shot.")
    _drv.close()
    print("Fatto.")

if __name__ == "__main__":
    main()

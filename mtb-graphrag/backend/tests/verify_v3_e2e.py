"""
Script di verifica End-to-End per l'integrazione reale V3.
Esegue 3 query non-gold reali sul backend V3:
1. Corrispondenza positiva: EGFR L858R in NSCLC con Osimertinib
2. Scope incompatibile: EGFR L858R in Melanoma con Osimertinib
3. Query booleana congiunta: EML4::ALK Fusion AND ALK G1202R in NSCLC con Lorlatinib
"""

import json
from fastapi.testclient import TestClient
from backend.api.main import app

client = TestClient(app)

print("=== VERIFICA END-TO-END V3 REALE ===")

# Query 1: EGFR L858R / NSCLC
q1 = {
    "domain": "therapeutic",
    "biomarker": "EGFR L858R",
    "disease": "Non-Small Cell Lung Cancer",
    "intervention": "Osimertinib",
    "policy_mode": "strict_verified",
}
r1 = client.post("/api/v1/v3/retrieve", json=q1)
print(f"\nQuery 1 Status: {r1.status_code}")
d1 = r1.json()
print("Summary Q1:", json.dumps(d1["summary"], indent=2))
print("Primary Claim IDs Q1:", [c["claim_id"] for c in d1["buckets"]["primary"][:3]])
print("Primary Graph Evidence IDs Q1:", [c["graph_evidence_id"] for c in d1["buckets"]["primary"][:3]])
print("Elapsed ms Q1:", d1["metadata"]["elapsed_ms"])

# Query 2: Scope Incompatibile (Melanoma)
q2 = {
    "domain": "therapeutic",
    "biomarker": "EGFR L858R",
    "disease": "Melanoma",
    "intervention": "Osimertinib",
    "policy_mode": "strict_verified",
}
r2 = client.post("/api/v1/v3/retrieve", json=q2)
print(f"\nQuery 2 Status: {r2.status_code}")
d2 = r2.json()
print("Summary Q2:", json.dumps(d2["summary"], indent=2))
print("Audit/Rejected Claim IDs Q2:", [c["claim_id"] for c in (d2["buckets"]["audit"] + d2["buckets"]["rejected"])[:3]])
print("Elapsed ms Q2:", d2["metadata"]["elapsed_ms"])

# Query 3: Congiunta Booleana ALK Fusion AND G1202R
q3 = {
    "domain": "therapeutic",
    "biomarker": "EML4::ALK Fusion AND ALK G1202R",
    "disease": "Non-Small Cell Lung Cancer",
    "intervention": "Lorlatinib",
    "policy_mode": "strict_verified",
}
r3 = client.post("/api/v1/v3/retrieve", json=q3)
print(f"\nQuery 3 Status: {r3.status_code}")
d3 = r3.json()
print("Summary Q3:", json.dumps(d3["summary"], indent=2))
print("Primary Claim IDs Q3:", [c["claim_id"] for c in d3["buckets"]["primary"][:3]])
print("Elapsed ms Q3:", d3["metadata"]["elapsed_ms"])

# Rendering Narrativo su Q1
claims_to_render = d1["buckets"]["primary"][:5]
render_req = {
    "query_id": d1["query_id"],
    "claims": claims_to_render,
}
r_render = client.post("/api/v1/v3/render", json=render_req)
print(f"\nRendering Status: {r_render.status_code}")
d_render = r_render.json()
print("Rendered Report Text:\n", d_render["rendered_report"])
print("Cited PMIDs:", d_render["cited_pmids"])

print("\n=== VERIFICA E2E COMPLETATA CON SUCCESSO ===")

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))

from backend.evaluation.compute_metrics import _run_cypher

# Let's query evidences for NTRK1 Fusion
rows = _run_cypher("""
    MATCH (mp:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence)
    WHERE toLower(mp.name) CONTAINS "ntrk1" AND toLower(mp.name) CONTAINS "fusion"
    RETURN e.evidence_level AS level, e.significance AS sig, e.disease AS disease
""")
print("Evidences for NTRK1 Fusion:")
for r in rows:
    print(f"  - Level: {r['level']}, Sig: {r['sig']}, Disease: {r['disease']}")

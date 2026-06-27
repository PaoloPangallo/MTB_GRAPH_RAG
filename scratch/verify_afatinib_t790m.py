import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "mtb-graphrag"))

from backend.pipeline.helpers import run_cypher

def verify_afatinib():
    query = """
    MATCH (v:Variant)-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence)-[:TARGETS_DRUG]->(d:Drug)
    WHERE toLower(v.variant_name) = 't790m' 
      AND toLower(d.drug_name) = 'afatinib'
    RETURN e.significance AS significance, 
           e.evidence_level AS level, 
           e.evidence_statement AS statement
    """
    results = run_cypher(query)
    
    print(f"Trovate {len(results)} evidenze nel grafo per EGFR T790M e AFATINIB:\n")
    for idx, r in enumerate(results, 1):
        print(f"--- Evidenza {idx} ---")
        print(f"Significatività: {r['significance']}")
        print(f"Livello: {r['level']}")
        print(f"Testo: {r['statement']}\n")

if __name__ == "__main__":
    verify_afatinib()

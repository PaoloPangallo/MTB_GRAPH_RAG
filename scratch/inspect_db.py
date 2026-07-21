import os
import sys
from neo4j import GraphDatabase
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
# La password Neo4j arriva esclusivamente dall'ambiente: nessun valore di ripiego,
# perche' un default scritto nel codice finirebbe nella cronologia Git.
import sys as _sys
from pathlib import Path as _Path

for _root in _Path(__file__).resolve().parents:
    if (_root / "utility" / "credentials.py").is_file():
        _sys.path.insert(0, str(_root))
        break
from utility.credentials import require_env

NEO4J_PASSWORD = require_env("NEO4J_PASSWORD")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def run_cypher(query: str, params: dict | None = None) -> list[dict]:
    with driver.session() as session:
        result = session.run(query, params or {})
        return [record.data() for record in result]

print("=== MATCHING CLINICAL TRIALS FOR EGFR IN LUNG CANCER ===")
disease_keywords = ["lung", "nsclc", "bronchial"]
query = """
MATCH (ct:ClinicalTrial)-[:ASSOCIATED_GENE]->(g:Gene {hugo_symbol: $gene})
WHERE ANY(c IN ct.conditions WHERE ANY(kw IN $disease_keywords WHERE toLower(c) CONTAINS kw))
   OR ANY(k IN ct.keywords   WHERE ANY(kw IN $disease_keywords WHERE toLower(k) CONTAINS kw))
RETURN ct.nct_id AS nct_id, ct.title AS title, ct.conditions AS conditions, ct.keywords AS keywords
"""
records = run_cypher(query, {"gene": "EGFR", "disease_keywords": disease_keywords})
print(f"Found {len(records)} matching clinical trials:")
for r in records:
    print(f"NCT: {r['nct_id']} | Title: {r['title']}")
driver.close()

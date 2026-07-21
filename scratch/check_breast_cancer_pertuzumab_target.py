import os
import sys

# Add the project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mtb-graphrag"))
sys.path.append(project_root)

from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load env from project root
load_dotenv(os.path.join(project_root, ".env"))

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
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

query = """
MATCH (e:Evidence)
WHERE toLower(e.evidence_statement) CONTAINS 'pertuzumab'
  AND (toLower(e.disease) CONTAINS 'breast' OR toLower(e.disease) CONTAINS 'mammary')
OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug)
RETURN e.evidence_level AS level,
       e.significance AS significance,
       e.disease AS disease,
       e.evidence_statement AS statement,
       d.drug_name AS targeted_drug
"""

try:
    results = run_cypher(query)
    print("Found", len(results), "Evidence nodes:")
    for r in results:
        print(f"Level: {r['level']} | Drug: {r['targeted_drug']} | Disease: {r['disease']} | Statement: {r['statement'][:150]}...")
except Exception as ex:
    print("Error executing query:", ex)
finally:
    driver.close()

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
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "pangallo22")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def run_cypher(query: str, params: dict | None = None) -> list[dict]:
    with driver.session() as session:
        result = session.run(query, params or {})
        return [record.data() for record in result]

query = """
MATCH (d:Drug)
WHERE toLower(d.drug_name) CONTAINS 'pertuzumab'
MATCH (e:Evidence)-[:TARGETS_DRUG]->(d)
OPTIONAL MATCH (mp:MolecularProfile)-[:HAS_EVIDENCE]->(e)
RETURN d.drug_name AS drug_name,
       e.evidence_level AS evidence_level,
       e.significance AS significance,
       e.evidence_type AS evidence_type,
       e.disease AS disease,
       mp.name AS mp_name
"""

try:
    results = run_cypher(query)
    print("Found", len(results), "evidence connections for Pertuzumab combination drugs:")
    for r in results:
        print(r)
except Exception as ex:
    print("Error executing query:", ex)
finally:
    driver.close()

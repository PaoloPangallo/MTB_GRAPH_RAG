import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "pangallo22")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def run_cypher(query: str, params: dict | None = None) -> list[dict]:
    with driver.session() as session:
        result = session.run(query, params or {})
        return [record.data() for record in result]

query = """
MATCH (g:Gene {hugo_symbol: 'ERBB2'})
      -[:HAS_VARIANT]->(v:Variant)
      -[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
      -[:HAS_EVIDENCE]->(e:Evidence)
MATCH (e)-[:TARGETS_DRUG]->(d:Drug)
OPTIONAL MATCH (e)-[:HAS_DISEASE]->(dis:Disease)
WHERE e.evidence_type = 'Predictive'
  AND e.significance = 'Sensitivity/Response'
  AND e.evidence_direction = 'Supports'
  AND (toLower(mp.name) CONTAINS 'amplification' 
       OR toLower(v.name) CONTAINS 'amplification')
  AND (toLower(coalesce(dis.name, e.disease)) CONTAINS 'breast')
RETURN mp.name AS mp_name, d.drug_name AS drug_name, e.evidence_level AS evidence_level, 
       coalesce(dis.name, e.disease) AS disease
ORDER BY e.evidence_level
"""

try:
    results = run_cypher(query)
    print("Found", len(results), "records:")
    for r in results:
        print(f"Profile: {r['mp_name']} | Drug: {r['drug_name']} | Level: {r['evidence_level']} | Disease: {r['disease']}")
except Exception as ex:
    print("Error executing query:", ex)
finally:
    driver.close()

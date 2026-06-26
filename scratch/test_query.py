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
MATCH (d:Disease)
RETURN d.name AS name LIMIT 50
"""

results = run_cypher(query)
for r in results:
    print(r)

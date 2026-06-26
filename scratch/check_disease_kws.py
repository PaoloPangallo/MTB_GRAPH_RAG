import os
import sys

# Add the project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mtb-graphrag"))
sys.path.append(project_root)

from backend.pipeline.helpers import get_disease_keywords, get_mp_keyword
from backend.pipeline.cypher import CYPHER_TARGET_MP
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

tumor = "Breast Cancer HER2+"
gene = "ERBB2"
variant = "Amplification"
alt_type = "cna"

disease_kws = get_disease_keywords(tumor)
mp_keyword = get_mp_keyword(alt_type, variant)

print("Tumor:", tumor)
print("Disease Keywords:", disease_kws)
print("MP Keyword:", mp_keyword)

params = {
    "gene_keyword": gene,
    "mp_keyword": mp_keyword,
    "disease_keywords": disease_kws
}

try:
    records = run_cypher(CYPHER_TARGET_MP, params)
    print("\nCYPHER_TARGET_MP output count:", len(records))
    
    unique_drugs = {}
    for r in records:
        drug = r['drug_name']
        level = r['evidence_level']
        if drug not in unique_drugs or level < unique_drugs[drug]:
            unique_drugs[drug] = level
            
    print("\nUnique drugs found and their best level:")
    for drug, level in sorted(unique_drugs.items(), key=lambda x: (x[1], x[0])):
        print(f"Drug: {drug} | Level: {level}")
        
except Exception as ex:
    print("Error executing target query:", ex)
finally:
    driver.close()

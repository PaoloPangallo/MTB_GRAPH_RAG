import sys
sys.path.insert(0, r'c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag')
from dotenv import load_dotenv
load_dotenv(r'c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\.env')

from backend.pipeline.helpers import run_cypher

query = """
MATCH (p:Publication {pmid: 15728811})<-[:CITED_IN]-(e:Evidence)
OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug)
OPTIONAL MATCH (v:Variant)-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)-[:HAS_EVIDENCE]->(e)
RETURN e.evidence_level as level, e.significance as sig, e.disease as disease, e.evidence_statement as statement, d.drug_name as drug_name, v.variant_name as variant
"""
res = run_cypher(query)
for r in res:
    print(r)

import sys
sys.path.insert(0, r'c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag')
from dotenv import load_dotenv
load_dotenv(r'c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\.env')

from backend.pipeline.helpers import run_cypher

query = """
MATCH (p:Publication {pmid: 15728811})
RETURN p.citation_text as citation, p.pmid as pmid
"""
res = run_cypher(query)
for r in res:
    print(r)

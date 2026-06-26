import sys
sys.path.insert(0, r'c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag')
from dotenv import load_dotenv
load_dotenv(r'c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\.env')

from backend.pipeline.helpers import run_cypher, get_disease_keywords
from backend.pipeline.cypher import CYPHER_RESISTANCE_GENE

disease_kws = get_disease_keywords("NSCLC")
gene_records = run_cypher(CYPHER_RESISTANCE_GENE, {
    "gene": "EGFR",
    "disease_keywords": disease_kws,
})

for r in gene_records[:15]:
    print(f"variant: {r.get('variant')}, level: {r.get('evidence_level')}, pmid: {r.get('pmid')}, drug: {r.get('drug_name')}")

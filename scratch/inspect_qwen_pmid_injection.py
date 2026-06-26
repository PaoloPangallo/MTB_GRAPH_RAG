import json, re

_PMID_RE = re.compile(r'\bPMID[:\s]*(\d{5,9})\b', re.IGNORECASE)

g = json.load(open(r'mtb-graphrag\backend\evaluation\results\ablation_second_llm_graphrag_results.json','r',encoding='utf-8'))

# 4 casi con PMID non-KG
affected = ['BENCH-010', 'BENCH-013', 'BENCH-021', 'BENCH-025']

for r in g:
    if r['case_id'] not in affected:
        continue
    
    report = r['report']
    non_kg_pmids = set(r['hallucinated_pmids_list'])
    cited_pmids = set(r['cited_pmids_list'])
    
    print(f"\n{'='*60}")
    print(f"CASO: {r['case_id']}")
    print(f"PMID nel KG (cited_pmids_list): {sorted(cited_pmids - non_kg_pmids)}")
    print(f"PMID NON nel KG (hallucinated_pmids_list): {sorted(non_kg_pmids)}")
    
    # Controlla se i PMID non-KG appaiono nel testo del report
    print(f"\nOccorrenze nel testo del report:")
    for pmid in sorted(non_kg_pmids):
        # Trova il contesto intorno al PMID nel report
        for m in re.finditer(rf'\bPMID[:\s]*{pmid}\b', report, re.IGNORECASE):
            start = max(0, m.start()-120)
            end = min(len(report), m.end()+120)
            snippet = report[start:end].replace('\n', ' ')
            print(f"  PMID {pmid}: ...{snippet}...")

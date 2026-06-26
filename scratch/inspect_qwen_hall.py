import json

v = json.load(open(r'mtb-graphrag\backend\evaluation\results\ablation_second_llm_vanilla_results.json','r',encoding='utf-8'))
g = json.load(open(r'mtb-graphrag\backend\evaluation\results\ablation_second_llm_graphrag_results.json','r',encoding='utf-8'))

print('Chiavi:', list(v[0].keys()))
print()

# Qwen vanilla: n_hallucinated = PMID non nel KG (trivialmente 100% perché vanilla non usa il KG)
v_hall_total = sum(r['n_hallucinated_pmids'] for r in v)
v_cited_total = sum(r['n_cited_pmids'] for r in v)
v_hall_rate = v_hall_total / v_cited_total if v_cited_total else 0
print(f'Qwen Vanilla: {v_cited_total} PMID citati, {v_hall_total} non nel KG = KB-non-groundedness {v_hall_rate:.1%}')
print('  (ATTENZIONE: questa e` groundedness vs KG, NON fabrication vs PubMed)')
print()

# Qwen graphrag: casi con PMID non nel KG
print('Qwen GraphRAG - casi con PMID non nel KG:')
for r in g:
    if r['n_hallucinated_pmids'] > 0:
        print(f"  {r['case_id']}: citati={r['n_cited_pmids']} non-KG={r['n_hallucinated_pmids']} rate={r['pmid_hallucination_rate']:.1%}")
        print(f"    PMID non nel KG: {r['hallucinated_pmids_list']}")

g_hall_total = sum(r['n_hallucinated_pmids'] for r in g)
g_cited_total = sum(r['n_cited_pmids'] for r in g)
g_hall_rate = g_hall_total / g_cited_total if g_cited_total else 0
print(f'\nQwen GraphRAG aggregato: {g_cited_total} PMID citati, {g_hall_total} non nel KG = {g_hall_rate:.1%}')

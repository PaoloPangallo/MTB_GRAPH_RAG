import json, csv

g = json.load(open(r'mtb-graphrag\backend\evaluation\results\ablation_second_llm_graphrag_results.json','r',encoding='utf-8'))
with open(r'mtb-graphrag\backend\benchmark\benchmark_papers_summary_30_v2.csv','r',encoding='utf-8') as f:
    bench = {row['case_id']: row for row in csv.DictReader(f)}

print('Casi Qwen GraphRAG con ESCAT errato:')
wrong = [r for r in g if not r['escat_match']]
for r in wrong:
    cid = r['case_id']
    row = bench.get(cid, {})
    print(f"  {cid}: gene={row.get('gene')} var={row.get('variant')} tumor={row.get('tumor')}")
    print(f"    expected={row.get('escat')}  extracted={r['extracted_escat']}")

print(f'\nTotale errori ESCAT: {len(wrong)}/30 = {len(wrong)/30:.1%}')
print(f'ESCAT Match Rate: {(30-len(wrong))/30:.1%}')

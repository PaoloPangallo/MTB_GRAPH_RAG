import json

with open('c:/Users/paolo/Desktop/IspezioneDatasetTesi/mtb-graphrag/backend/evaluation/results/benchmark_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for case in data:
    case_id = case.get('case_id')
    if case_id in ('BENCH-011', 'BENCH-013', 'BENCH-014', 'BENCH-019'):
        print(f"========================================\nCASE: {case_id} ({case.get('gene')} {case.get('variant')})")
        print("REPORT SNIPPET:")
        print(case.get('report')[:800])
        print("========================================\n")

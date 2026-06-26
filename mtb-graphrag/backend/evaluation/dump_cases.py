import json
import sys

try:
    with open('results/zeroshot_results.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    for row in data:
        case_id = row.get('case_id')
        history = row.get('patient_profile', {}).get('medical_history', [])
        print(f"{case_id}: {history}")
except Exception as e:
    print(e)

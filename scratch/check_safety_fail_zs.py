import json
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path("c:/Users/paolo/Desktop/IspezioneDatasetTesi/mtb-graphrag")))

from backend.evaluation.contraindications import get_contraindications

with open('c:/Users/paolo/Desktop/IspezioneDatasetTesi/mtb-graphrag/backend/evaluation/results/zeroshot_structured_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for case in data:
    case_id = case.get('case_id')
    struct = case.get('structured_data', {})
    rec_drugs = struct.get('recommended_drugs', [])
    contraindications = get_contraindications(case_id)
    if contraindications:
        violated = []
        for contra in contraindications:
            # Check in recommended drugs list
            for r_drug in rec_drugs:
                if contra in r_drug.lower():
                    violated.append(contra)
        if violated:
            print(f"Zero-shot Case {case_id} ({case.get('gene')} {case.get('variant')}): Violated {violated}")
            print("  Recommended drugs:", rec_drugs)
            print()

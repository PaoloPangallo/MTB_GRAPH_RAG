import json
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path("c:/Users/paolo/Desktop/IspezioneDatasetTesi/mtb-graphrag")))

from backend.evaluation.contraindications import get_contraindications
from backend.evaluation.drug_aliases import parse_drug_combinations

with open('c:/Users/paolo/Desktop/IspezioneDatasetTesi/mtb-graphrag/backend/evaluation/results/benchmark_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for case in data:
    case_id = case.get('case_id')
    report = case.get('report', '')
    contraindications = get_contraindications(case_id)
    if contraindications:
        # Check if any contraindication is in report
        violated = []
        for contra in contraindications:
            if contra in report.lower():
                violated.append(contra)
        if violated:
            print(f"Case {case_id} ({case.get('gene')} {case.get('variant')}): Violated {violated}")
            # Find the context in which they are mentioned
            lines = report.split('\n')
            for line in lines:
                if any(v in line.lower() for v in violated):
                    print("  Line:", line.strip())
            print()

import sys
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "mtb-graphrag"))

from backend.pipeline.agents.target_identifier import target_identifier
from backend.pipeline.agents.resistance_checker import resistance_checker

def run_inspection():
    state = {
        "gene": "EGFR",
        "variant": "T790M",
        "tumor_type": "NSCLC",
        "alteration_type": "point_mutation",
        "therapy_line": "second-line",
        "drug_candidates": [],
        "variant_data": None
    }
    
    # 1. Target Identifier
    print("\nEseguo target_identifier...")
    state = target_identifier(state)
    print("\n=== DRUG CANDIDATES DOPO TARGET IDENTIFIER ===")
    print(json.dumps(state.get("drug_candidates", []), indent=2))
    
    # 2. Resistance Checker
    print("\nEseguo resistance_checker...")
    state = resistance_checker(state)
    print("\n=== DRUG CANDIDATES DOPO RESISTANCE CHECKER ===")
    print(json.dumps(state.get("drug_candidates", []), indent=2))

if __name__ == "__main__":
    run_inspection()

import os
import sys

# Add the project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mtb-graphrag"))
sys.path.append(project_root)

from backend.pipeline.state import MTBState
from backend.pipeline.graph import run_pipeline
from dotenv import load_dotenv

# Load env from project root
load_dotenv(os.path.join(project_root, ".env"))

# Run BENCH-004: ERBB2 Amplification / Breast Cancer HER2+
state = {
    "gene":               "ERBB2",
    "variant":            "Amplification",
    "tumor_type":         "Breast Cancer",
    "alteration_type":    "cna",
    "therapy_line":       "first-line",
    "enrich_with_oncokb": False,
    "complexity":         "moderate",
    "variant_data":       {},
    "drug_candidates":    [],
    "trial_candidates":   [],
    "resistance_data":    [],
    "oncokb_enrichment":  [],
    "report":             "",
    "cited_pmids":        [],
    "escat_tier":         "",
}

print("Running pipeline for BENCH-004...")
try:
    final = run_pipeline(state)
    print("\nPIPELINE RUN COMPLETED!")
    print("ESCAT Tier:", final["escat_tier"])
    print("Candidates:", [c["drug_name"] for c in final["drug_candidates"]])
    print("\nREPORT:\n", final["report"])
except Exception as ex:
    print("Error running pipeline:", ex)

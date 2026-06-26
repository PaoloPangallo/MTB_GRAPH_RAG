import sys
from pathlib import Path

ROOT = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag")
sys.path.insert(0, str(ROOT))

from backend.evaluation.ablation_enricher import _build_fair_oncokb_params, _extract_level1_2
from backend.pipeline.agents.oncokb_enricher import _oncokb_request

# Let's inspect BENCH-001
# BENCH-001: gene=EGFR, variant=L858R, tumor=NSCLC (Lung Adenocarcinoma), alteration_type=point_mutation
print("=== Querying OncoKB for BENCH-001 ===")
endpoint, params = _build_fair_oncokb_params("EGFR", "L858R", "NSCLC", "point_mutation")
data = _oncokb_request(endpoint, params)
treatments = _extract_level1_2(data)
all_pmids_001 = set()
for t in treatments:
    all_pmids_001.update(t["pmids"])
print("PMIDs returned by OncoKB for BENCH-001:")
print(sorted(list(all_pmids_001)))

# Let's inspect BENCH-005
# BENCH-005: gene=BRCA1, variant=Mutation, tumor=Ovarian Cancer, alteration_type=point_mutation
print("\n=== Querying OncoKB for BENCH-005 ===")
endpoint, params = _build_fair_oncokb_params("BRCA1", "Mutation", "Ovarian Cancer", "point_mutation")
data = _oncokb_request(endpoint, params)
# Wait, BENCH-005 should use fallback since alteration is generic
treatments = _extract_level1_2(data)
if not treatments:
    print("Primary query returned 0 treatments. Trying fallback...")
    fb_params = {
        "hugoSymbol": "BRCA1",
        "alteration": "Oncogenic Mutations",
        "tumorType": "Ovarian Cancer"
    }
    data = _oncokb_request("mutations/byProteinChange", fb_params)
    treatments = _extract_level1_2(data)

all_pmids_005 = set()
for t in treatments:
    all_pmids_005.update(t["pmids"])
print("PMIDs returned by OncoKB for BENCH-005:")
print(sorted(list(all_pmids_005)))

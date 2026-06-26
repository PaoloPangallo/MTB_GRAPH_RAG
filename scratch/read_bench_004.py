import json

with open("mtb-graphrag/backend/evaluation/results/benchmark_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for case in data:
    if case["case_id"] == "BENCH-004":
        print("CASE 004:")
        print("GENE:", case["gene"])
        print("VARIANT:", case["variant"])
        print("TUMOR:", case["tumor"])
        print("EXPECTED DRUG:", case["expected_drug"])
        print("REPORT:\n", case["report"])
        break

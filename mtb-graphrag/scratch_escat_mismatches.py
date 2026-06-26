import json

data = json.load(open("backend/evaluation/results/metrics_graphrag.json"))
mismatches = [d for d in data if not d["escat_match"]]

print(f"Total Matches: {len(data) - len(mismatches)}/{len(data)} ({(len(data) - len(mismatches))/len(data)*100:.1f}%)")
print("Mismatches:")
for d in mismatches:
    print(f" - {d['case_id']}: Expected {d['expected_escat']} vs Got {d['extracted_escat']}")

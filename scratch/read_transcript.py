import json
import re

log_path = r"C:\Users\paolo\.gemini\antigravity-ide\brain\f2fb8c39-2023-43ea-9864-3ca1d9cda5a1\.system_generated\logs\transcript.jsonl"

print("Searching transcript.jsonl...")
found_cases = {}
with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        # Search for any JSON string containing BENCH-001
        if "BENCH-001" in line:
            # Try to find JSON objects/arrays in the line
            matches = re.findall(r'(\[.*?\]|\{.*?\})', line)
            for m in matches:
                if "BENCH-001" in m:
                    try:
                        data = json.loads(m)
                        if isinstance(data, list):
                            for item in data:
                                if "case_id" in item:
                                    found_cases[item["case_id"]] = item
                        elif isinstance(data, dict):
                            if "case_id" in data:
                                found_cases[data["case_id"]] = data
                    except Exception as e:
                        pass

print(f"Found {len(found_cases)} unique cases in logs:")
print(list(found_cases.keys()))

if len(found_cases) > 1:
    # Save recovered cases
    with open(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results\benchmark_results_recovered.json", "w", encoding="utf-8") as out:
        json.dump(list(found_cases.values()), out, indent=2, ensure_ascii=False)
    print("Saved recovered cases to benchmark_results_recovered.json")

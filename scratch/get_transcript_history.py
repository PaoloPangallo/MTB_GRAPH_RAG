import json
from pathlib import Path

transcript_path = Path(r"C:\Users\paolo\.gemini\antigravity-ide\brain\97584f8a-4b22-4db7-b4d3-f1e86c5b42bc\.system_generated\logs\transcript.jsonl")

lines = []
with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        lines.append(json.loads(line))

for l in lines:
    idx = l.get('step_index')
    if idx is not None and 1315 <= idx <= 1323:
        print(f"Index: {idx}, Source: {l.get('source')}, Type: {l.get('type')}")
        if l.get('content'):
            print(f"  Content: {l['content'][:300]}...")

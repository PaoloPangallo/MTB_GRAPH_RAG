import json
from pathlib import Path

transcript_path = Path(r"C:\Users\paolo\.gemini\antigravity-ide\brain\97584f8a-4b22-4db7-b4d3-f1e86c5b42bc\.system_generated\logs\transcript.jsonl")

lines = []
with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        lines.append(json.loads(line))

print(f"Total lines in transcript: {len(lines)}")
for i in range(max(0, len(lines)-15), len(lines)):
    l = lines[i]
    print(f"Index: {l.get('step_index')}, Source: {l.get('source')}, Type: {l.get('type')}, Status: {l.get('status')}")
    if l.get('content'):
        print(f"  Content snippet: {repr(l['content'][:100])}")

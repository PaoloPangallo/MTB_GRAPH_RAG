import json
from pathlib import Path

transcript_path = Path(r"C:\Users\paolo\.gemini\antigravity-ide\brain\97584f8a-4b22-4db7-b4d3-f1e86c5b42bc\.system_generated\logs\transcript.jsonl")
output_path = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\scratch\last_model_messages.txt")

lines = []
with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        lines.append(json.loads(line))

model_lines = [l for l in lines if l.get("source") == "MODEL"]

with open(output_path, "w", encoding="utf-8") as f:
    for i, l in enumerate(model_lines[-5:]):
        f.write(f"=== MODEL LINE -{5-i} ===\n")
        f.write(json.dumps(l, indent=2))
        f.write("\n\n")

print("Successfully extracted last model messages")

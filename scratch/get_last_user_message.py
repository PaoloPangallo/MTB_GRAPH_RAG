import json
from pathlib import Path

transcript_path = Path(r"C:\Users\paolo\.gemini\antigravity-ide\brain\97584f8a-4b22-4db7-b4d3-f1e86c5b42bc\.system_generated\logs\transcript.jsonl")
output_path = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\scratch\last_user_message.txt")

lines = []
with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        lines.append(json.loads(line))

user_lines = [l for l in lines if l.get("source") == "USER_EXPLICIT"]

# Let's save the last 2 user inputs so we can check if we need to see both.
with open(output_path, "w", encoding="utf-8") as f:
    f.write("=== LAST USER INPUT ===\n")
    if len(user_lines) >= 1:
        f.write(user_lines[-1]["content"])
    f.write("\n\n=== SECOND LAST USER INPUT ===\n")
    if len(user_lines) >= 2:
        f.write(user_lines[-2]["content"])
print("Successfully extracted user messages to scratch/last_user_message.txt")

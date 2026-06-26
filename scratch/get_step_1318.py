import json
import sys
from pathlib import Path

transcript_path = Path(r"C:\Users\paolo\.gemini\antigravity-ide\brain\97584f8a-4b22-4db7-b4d3-f1e86c5b42bc\.system_generated\logs\transcript.jsonl")
output_path = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\scratch\step_1318.txt")

with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        l = json.loads(line)
        if l.get('step_index') == 1318:
            with open(output_path, "w", encoding="utf-8") as outf:
                outf.write(l.get('content', ''))
            print("Successfully written step 1318 to step_1318.txt")
            break

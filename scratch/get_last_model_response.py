import json
from pathlib import Path

transcript_path = Path(r"C:\Users\paolo\.gemini\antigravity-ide\brain\97584f8a-4b22-4db7-b4d3-f1e86c5b42bc\.system_generated\logs\transcript.jsonl")

lines = []
with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        lines.append(json.loads(line))

# Find the model response that comes just before the last user input (which is "continua")
model_responses = [l for l in lines if l.get("source") == "MODEL" and l.get("type") == "PLANNER_RESPONSE"]

print(f"Total model planner responses: {len(model_responses)}")
if model_responses:
    last_resp = model_responses[-1]
    print(f"Last planner response step index: {last_resp['step_index']}")
    print("Content:")
    print(last_resp.get("content", ""))
    
    # Also look at second last to see if there is more
    if len(model_responses) >= 2:
        prev_resp = model_responses[-2]
        print(f"Second last planner response step index: {prev_resp['step_index']}")
        print("Content:")
        print(prev_resp.get("content", ""))

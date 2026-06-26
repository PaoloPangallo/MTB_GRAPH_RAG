import os
import sys
from pathlib import Path

# Setup paths
sys.path.append(str(Path(__file__).resolve().parent.parent / "mtb-graphrag"))

from backend.pipeline.llm import llm
from langchain_core.messages import SystemMessage, HumanMessage

def test():
    print("Testing ChatOllama Cloud invocation...")
    try:
        res = llm.invoke([
            SystemMessage(content="Sei un assistente utile."),
            HumanMessage(content="Ciao, rispondi con una sola parola.")
        ])
        print(f"Success! Response: '{res.content}'")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test()

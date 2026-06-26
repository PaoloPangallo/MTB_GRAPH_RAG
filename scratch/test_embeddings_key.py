import os
import sys
from dotenv import load_dotenv
from langchain_ollama import OllamaEmbeddings

# Load .env
load_dotenv(os.path.dirname(os.path.abspath(__file__)) + "/../.env")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")

def test_cloud_embeddings_with_key():
    try:
        embeddings = OllamaEmbeddings(
            model="nomic-embed-text:latest",
            base_url="https://api.ollama.com",
            # OllamaEmbeddings doesn't directly accept api_key in older versions, but let's see or set env
        )
        os.environ["OLLAMA_API_KEY"] = OLLAMA_API_KEY
        vec = embeddings.embed_query("test query")
        print(f"Cloud embeddings (env key) success! Vector length: {len(vec)}")
        return True
    except Exception as e:
        print(f"Cloud embeddings (env key) failed: {e}")
        return False

if __name__ == "__main__":
    test_cloud_embeddings_with_key()

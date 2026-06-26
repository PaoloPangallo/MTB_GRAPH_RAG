import sys
from langchain_ollama import OllamaEmbeddings

def test_local_embeddings():
    try:
        embeddings = OllamaEmbeddings(model="nomic-embed-text:latest", base_url="http://localhost:11434")
        vec = embeddings.embed_query("test query")
        print(f"Local embeddings success! Vector length: {len(vec)}")
        return True
    except Exception as e:
        print(f"Local embeddings failed: {e}")
        return False

def test_cloud_embeddings():
    try:
        # Check if we can use nomic-embed-text via api.ollama.com
        embeddings = OllamaEmbeddings(model="nomic-embed-text:latest", base_url="https://api.ollama.com")
        vec = embeddings.embed_query("test query")
        print(f"Cloud embeddings success! Vector length: {len(vec)}")
        return True
    except Exception as e:
        print(f"Cloud embeddings failed: {e}")
        return False

if __name__ == "__main__":
    local_ok = test_local_embeddings()
    cloud_ok = test_cloud_embeddings()

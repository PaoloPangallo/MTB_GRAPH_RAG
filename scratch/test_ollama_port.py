import requests

def test_ollama():
    for port in [11434, 64387]:
        try:
            r = requests.get(f"http://127.0.0.1:{port}/api/tags", timeout=3)
            print(f"Ollama running on port {port}: {r.status_code}, response: {r.json()}")
            return port
        except Exception as e:
            print(f"Ollama port {port} failed: {e}")
    return None

if __name__ == "__main__":
    test_ollama()

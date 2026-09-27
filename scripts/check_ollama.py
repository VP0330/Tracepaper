"""Check Ollama connectivity and readiness."""

import requests
import sys
from tracepaper.config import get_settings


def check_ollama():
    """Check if Ollama is running and accessible."""
    settings = get_settings()
    
    try:
        response = requests.get(f"{settings.ollama_host}/api/tags", timeout=5)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Cannot reach Ollama at {settings.ollama_host}")
        print(f"  Details: {e}")
        print("")
        print("To fix this:")
        print("  1. Start Ollama locally: ollama serve")
        print("  2. Or start via Docker: docker-compose up ollama")
        print("  3. Or point to remote: export OLLAMA_HOST=http://remote:11434")
        return False


if __name__ == "__main__":
    if not check_ollama():
        sys.exit(1)
    print("✓ Ollama is reachable")
    sys.exit(0)

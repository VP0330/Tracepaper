"""Pull required Ollama models."""

import subprocess
import sys
from tracepaper.config import get_settings


MODELS = [
    "qwen2.5:14b-instruct",
    "qwen2.5:7b-instruct",
]


def pull_models():
    """Pull models from Ollama."""
    settings = get_settings()
    
    print(f"Pulling models from Ollama at {settings.ollama_host}...")
    print("")
    
    for model in MODELS:
        print(f"Pulling {model}...")
        try:
            # Use ollama CLI to pull models
            result = subprocess.run(
                ["ollama", "pull", model],
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"✓ {model} pulled successfully")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to pull {model}")
            print(f"  Error: {e.stderr}")
            return False
        except FileNotFoundError:
            print(f"✗ 'ollama' command not found")
            print("  Install Ollama from https://ollama.ai")
            return False
    
    print("")
    print("✓ All models ready")
    return True


if __name__ == "__main__":
    if not pull_models():
        sys.exit(1)
    sys.exit(0)

import os
import json
import subprocess
import sys

def setup():
    # 1. Create default_prompt.json
    default_prompt_data = {
        "default_prompt": "Examine the provided image(s). Extract all visible text, identify key information, and summarize the contents accurately.",
        "model": "gemini-3.6-flash"
    }
    
    prompt_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "default_prompt.json")
    if not os.path.exists(prompt_file):
        with open(prompt_file, "w", encoding="utf-8") as f:
            json.dump(default_prompt_data, f, indent=4)
        print(f"✅ Created default prompt JSON at '{prompt_file}'")
    else:
        print(f"ℹ️ '{prompt_file}' already exists.")

    # 2. Check/Install Gemini CLI via npm
    print("📦 Installing Gemini CLI...")
    try:
        # Check npm installation
        subprocess.run(["npm", "install", "-g", "@google/gemini-cli"], check=True)
        print("✅ Gemini CLI installed successfully.")
    except Exception as e:
        print(f"⚠️ Failed to install Gemini CLI via npm ({e}). Ensure Node.js & npm are installed.")
        print("Falling back to python google-genai library...")
        subprocess.run([sys.executable, "-m", "pip", "install", "google-genai"], check=False)

if __name__ == "__main__":
    setup()
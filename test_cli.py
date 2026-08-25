from google import genai
from google.genai import types
from google.genai.errors import APIError

MODEL_NAME = "gemini-3.7-flash"
PROMPT = "Respond with 'SUCCESS' if you can read this."

# Disable Automatic Function Calling warning for one-off calls
config = types.GenerateContentConfig(
    automatic_function_calling=types.AutomaticFunctionCallingConfig(
        disable=True
    )
)

with open("keys.txt", "r") as f:
    keys = [line.strip() for line in f if line.strip()]

print(f"Testing {len(keys)} keys against model: {MODEL_NAME}\n" + "-" * 50)

for idx, key in enumerate(keys, 1):
    masked_key = f"{key[:7]}...{key[-4:]}" if len(key) > 11 else key
    print(f"[{idx}/{len(keys)}] Testing Key: {masked_key}")

    try:
        client = genai.Client(api_key=key)

        response = client.models.generate_content(
            model=MODEL_NAME, contents=PROMPT, config=config
        )
        print(f"  └─ STATUS: SUCCESS | Response: {response.text.strip()}")

    except APIError as e:
        print(f"  └─ STATUS: FAILED (API Error) | Code {e.code}: {e.message}")
    except Exception as e:
        print(f"  └─ STATUS: FAILED (Error) | {e}")

    print("-" * 50)
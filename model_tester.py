import os
import json
import time
import asyncio
import threading
from datetime import datetime
from typing import List, Optional
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Gemini Model & Key Pool Tester")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE = os.path.join(BASE_DIR, "test_results.json")

LAST_HEARTBEAT = time.time()
HEARTBEAT_STARTED = False

def _heartbeat_monitor():
    global LAST_HEARTBEAT, HEARTBEAT_STARTED
    while True:
        time.sleep(2)
        if HEARTBEAT_STARTED and (time.time() - LAST_HEARTBEAT > 8):
            print("\n[Server] All client pages exited. Cleanly shutting down server process.")
            os._exit(0)

threading.Thread(target=_heartbeat_monitor, daemon=True).start()

def get_keys_file_path() -> str:
    key_path = os.path.join(BASE_DIR, "key.txt")
    keys_path = os.path.join(BASE_DIR, "keys.txt")
    if os.path.exists(key_path):
        return key_path
    if os.path.exists(keys_path):
        return keys_path
    return key_path

def load_keys() -> List[str]:
    path = get_keys_file_path()
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

def save_keys(keys: List[str]):
    path = get_keys_file_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(keys) + "\n")

def load_filtered_models():
    models_path = os.path.join(BASE_DIR, "model_source.json")
    if not os.path.exists(models_path):
        models_path = os.path.join(BASE_DIR, "models.txt")
    if not os.path.exists(models_path):
        models_path = os.path.join(BASE_DIR, "models2.txt")
    if not os.path.exists(models_path):
        return []

    try:
        with open(models_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            raw_models = data.get("models", [])
    except Exception:
        return []

    excluded_terms = ["embed", "veo", "video", "translate", "robot", "banana", "tts"]
    filtered = []

    for m in raw_models:
        name = m.get("name", "")
        clean_name = name.replace("models/", "")
        display_name = m.get("displayName", clean_name)
        description = m.get("description", "")
        methods = m.get("supportedGenerationMethods", [])

        combined_text = f"{clean_name} {display_name} {description}".lower()

        if any(term in combined_text for term in excluded_terms):
            continue

        if methods and "generateContent" not in methods:
            continue

        filtered.append({
            "id": clean_name,
            "fullName": name,
            "displayName": display_name,
            "description": description,
            "inputTokenLimit": m.get("inputTokenLimit"),
            "outputTokenLimit": m.get("outputTokenLimit"),
            "thinking": m.get("thinking", False),
            "temperature": m.get("temperature", 1.0)
        })

    return filtered

def load_test_results():
    if not os.path.exists(RESULTS_FILE):
        return []
    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def append_test_result(entry: dict):
    results = load_test_results()
    model = entry.get("model")
    full_key = entry.get("full_key")
    masked_key = entry.get("key")

    # Remove existing matching test result for the same model and key so it overwrites
    filtered = [
        r for r in results
        if not (r.get("model") == model and (r.get("full_key") == full_key or r.get("key") == masked_key))
    ]
    filtered.insert(0, entry)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2)

def _rest_generate(key: str, model_id: str, prompt: str,
                   system_instruction: str = "", temperature: float = 0.7,
                   timeout: int = 120) -> dict:
    """Call Gemini via the REST endpoint (?key=) instead of the google-genai SDK.
    REST accepts both AIza... (Developer) and AQ... (Cloud) keys; the SDK transport
    rejects AQ... keys with 401. Returns {status, text|message, latencyMs, code}."""
    import base64
    import urllib.request
    import urllib.error
    url = (f"https://generativelanguage.googleapis.com/v1beta/"
           f"models/{model_id}:generateContent?key={key}")
    gen_config = {"temperature": float(temperature)}
    if system_instruction:
        gen_config["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": gen_config,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    import time
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            jr = json.loads(resp.read().decode("utf-8"))
        text = ""
        try:
            text = jr["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            text = json.dumps(jr)
        return {"status": "success", "text": text,
                "latencyMs": int((time.time() - t0) * 1000)}
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")
        return {"status": "error", "code": e.code, "message": msg,
                "latencyMs": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"status": "error", "code": None, "message": str(e),
                "latencyMs": int((time.time() - t0) * 1000)}

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    html_file = os.path.join(BASE_DIR, "model_tester.html")
    if os.path.exists(html_file):
        with open(html_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>model_tester.html not found</h1>"

@app.get("/results", response_class=HTMLResponse)
async def serve_results_viewer():
    html_file = os.path.join(BASE_DIR, "results_viewer.html")
    if os.path.exists(html_file):
        with open(html_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>results_viewer.html not found</h1>"

@app.get("/api/keys")
async def get_keys():
    raw_keys = load_keys()
    keys_data = []
    for idx, k in enumerate(raw_keys):
        masked = f"{k[:7]}...{k[-4:]}" if len(k) > 11 else k
        keys_data.append({
            "index": idx,
            "key": k,
            "masked": masked
        })
    return {"keys": keys_data, "file": os.path.basename(get_keys_file_path())}

@app.post("/api/keys")
async def update_keys(data: dict = Body(...)):
    raw_text = data.get("keys_text", "")
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    save_keys(lines)
    return {"status": "success", "count": len(lines)}

@app.get("/api/models")
async def get_models():
    models = load_filtered_models()
    return {"models": models, "count": len(models)}

@app.get("/api/models-tested")
async def get_models_tested():
    results = load_test_results()
    tested = {}
    for e in results:
        m = e.get("model")
        if not m:
            continue
        r = e.get("result") or {}
        if m not in tested:
            tested[m] = {"tested": True, "success": (r.get("status") == "success")}
        elif r.get("status") == "success":
            tested[m]["success"] = True
    return {"tested": tested}

@app.post("/api/heartbeat")
async def receive_heartbeat():
    global LAST_HEARTBEAT, HEARTBEAT_STARTED
    LAST_HEARTBEAT = time.time()
    HEARTBEAT_STARTED = True
    return {"status": "ok"}

@app.post("/api/shutdown")
async def trigger_shutdown():
    def _delayed_exit():
        time.sleep(0.3)
        print("\n[Server] Shutdown request received. Exiting cleanly.")
        os._exit(0)
    threading.Thread(target=_delayed_exit, daemon=True).start()
    return {"status": "shutting down"}

@app.get("/api/results")
async def get_results():
    results = load_test_results()
    return {"results": results, "count": len(results)}

@app.delete("/api/results")
async def clear_results():
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)
    return {"status": "success"}

@app.post("/api/test-connectivity")
async def test_connectivity(data: dict = Body(...)):
    key = data.get("key", "").strip()
    model_id = data.get("model", "gemini-2.5-flash").strip()
    prompt = data.get("prompt", "Respond with 'SUCCESS' if you can read this.")

    if not key:
        raise HTTPException(status_code=400, detail="API Key is required")

    masked_key = f"{key[:7]}...{key[-4:]}" if len(key) > 11 else key

    t0 = time.time()
    timestamp = datetime.now().isoformat()
    try:
        res_payload = _rest_generate(key, model_id, prompt)
        res_payload["model"] = model_id
        res_payload["response"] = res_payload.get("text", "")
        if res_payload["status"] == "success":
            append_test_result({
                "timestamp": timestamp,
                "model": model_id,
                "key": masked_key,
                "full_key": key,
                "type": "connectivity",
                "prompt": prompt,
                "result": res_payload
            })
            return res_payload
        else:
            err_payload = {
                "status": "error",
                "error_type": "APIError" if res_payload.get("code") else "Exception",
                "code": res_payload.get("code"),
                "message": res_payload.get("message", ""),
                "latencyMs": res_payload.get("latencyMs", 0)
            }
            append_test_result({
                "timestamp": timestamp,
                "model": model_id,
                "key": masked_key,
                "full_key": key,
                "type": "connectivity",
                "prompt": prompt,
                "result": err_payload
            })
            return err_payload
    except Exception as e:
        latency_ms = int((time.time() - t0) * 1000)
        err_payload = {
            "status": "error",
            "error_type": "Exception",
            "message": str(e),
            "latencyMs": latency_ms
        }
        append_test_result({
            "timestamp": timestamp,
            "model": model_id,
            "key": masked_key,
            "full_key": key,
            "type": "connectivity",
            "prompt": prompt,
            "result": err_payload
        })
        return err_payload

@app.post("/api/generate")
async def generate_prompt(data: dict = Body(...)):
    key = data.get("key", "").strip()
    model_id = data.get("model", "gemini-2.5-flash").strip()
    prompt = data.get("prompt", "").strip()
    system_instruction = data.get("system_instruction", "").strip()
    temperature = data.get("temperature", 0.7)

    if not key:
        keys = load_keys()
        if keys:
            key = keys[0]
        else:
            raise HTTPException(status_code=400, detail="No API Key provided or available in key pool")

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    masked_key = f"{key[:7]}...{key[-4:]}" if len(key) > 11 else key

    t0 = time.time()
    timestamp = datetime.now().isoformat()
    try:
        res_payload = _rest_generate(key, model_id, prompt,
                                     system_instruction=system_instruction,
                                     temperature=temperature)
        res_payload["model"] = model_id
        if res_payload["status"] == "success":
            append_test_result({
                "timestamp": timestamp,
                "model": model_id,
                "key": masked_key,
                "full_key": key,
                "type": "generate",
                "prompt": prompt,
                "system_instruction": system_instruction,
                "result": res_payload
            })
            return res_payload
        else:
            err_payload = {
                "status": "error",
                "code": res_payload.get("code"),
                "message": res_payload.get("message", ""),
                "latencyMs": res_payload.get("latencyMs", 0)
            }
            append_test_result({
                "timestamp": timestamp,
                "model": model_id,
                "key": masked_key,
                "full_key": key,
                "type": "generate",
                "prompt": prompt,
                "system_instruction": system_instruction,
                "result": err_payload
            })
            return err_payload
    except Exception as e:
        latency_ms = int((time.time() - t0) * 1000)
        err_payload = {
            "status": "error",
            "message": str(e),
            "latencyMs": latency_ms
        }
        append_test_result({
            "timestamp": timestamp,
            "model": model_id,
            "key": masked_key,
            "full_key": key,
            "type": "generate",
            "prompt": prompt,
            "system_instruction": system_instruction,
            "result": err_payload
        })
        return err_payload

if __name__ == "__main__":
    import webbrowser
    port = 8877
    print(f"Starting Gemini Key & Model Tester at http://127.0.0.1:{port}")
    webbrowser.open(f"http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)

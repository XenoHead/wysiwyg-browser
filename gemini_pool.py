"""Shared Gemini key-pool + model-pool loader with REST failover.

Both main.py (Discogs Add) and WysiScan/scanner_server.py (Extract Text) import
this so the Gemini-calling logic lives in exactly one place.

Key facts that shaped this module:
- The google-genai SDK transport rejects AQ... (Cloud) API keys with 401.
  Calling the REST endpoint (?key=) directly works for BOTH AIza... (Developer)
  and AQ... keys. So we use REST exclusively.
- Rate limits are per Google Cloud PROJECT, not per API key. keys.txt therefore
  holds one key per project; a 429 on one project fails over to the next.
- test_results.json (produced by model_tester.py) records {model, full_key,
  result:{status, latencyMs}} per test. We use it to rank (key, model) combos so
  proven-good/fast combos are tried first.
"""
import os
import json
import base64
import urllib.request
import urllib.error
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_key_pool(extra_config_keys=None):
    """Return a de-duplicated list of API keys from:
       1) .env GEMINI_API_KEY / GOOGLE_API_KEY
       2) keys.txt (one bare key per line, in the app root)
       3) optional config dict keys (scanner's load_config)
    """
    pool = []
    env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if env_key and env_key.strip():
        pool.append(env_key.strip())
    kt = os.path.join(BASE_DIR, "keys.txt")
    if os.path.isfile(kt):
        with open(kt, encoding="utf-8") as f:
            for ln in f:
                k = ln.strip()
                if k and not k.startswith("#"):
                    pool.append(k)
    if extra_config_keys:
        for ck in extra_config_keys:
            if ck and ck.strip():
                pool.append(ck.strip())
    seen, uniq = set(), []
    for k in pool:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    return uniq


# Models we never want for OCR/extraction work (image- or video-generation only).
_MODEL_EXCLUDE = ("banana", "veo", "embed", "translate", "robot", "tts")


def load_model_pool():
    """Return the ordered list of model ids to try, from models.txt (one per
    line). Falls back to a sensible default list if the file is missing.
    Nano Banana / image-only models are excluded."""
    default = [
        "gemini-3.6-flash",
        "gemini-flash-latest",
        "gemini-2.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-3-flash-preview",
    ]
    mp = os.path.join(BASE_DIR, "models.txt")
    models = []
    if os.path.isfile(mp):
        with open(mp, encoding="utf-8") as f:
            for ln in f:
                m = ln.strip()
                if not m or m.startswith("#"):
                    continue
                models.append(m)
    if not models:
        models = list(default)
    # Exclude Nano Banana / image-only models from the pool.
    filtered = [m for m in models if not any(t in m.lower() for t in _MODEL_EXCLUDE)]
    return filtered


def load_test_results():
    rp = os.path.join(BASE_DIR, "test_results.json")
    if not os.path.isfile(rp):
        return []
    try:
        with open(rp, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def rank_combos(key_pool, model_pool):
    """Return a list of (key, model) tuples ordered best-first, using
    test_results.json. Combos are scored by MODEL success-rate (across all
    keys) then KEY success-rate, with latency as a tiebreaker. Combos whose
    model/key only ever failed are pushed to the end. The full cartesian
    product is always present so nothing is ever hard-dropped."""
    results = load_test_results()
    combo_stats = {}
    model_stats = {}
    key_stats = {}
    for e in results:
        key = e.get("full_key") or e.get("key")
        model = e.get("model")
        if not key or not model:
            continue
        r = e.get("result") or {}
        ok = (r.get("status") == "success")
        lat = r.get("latencyMs") or 0
        targets = ((combo_stats, (key, model)), (model_stats, model), (key_stats, key))
        for store, dim in targets:
            if dim not in store:
                store[dim] = {"ok": 0, "fail": 0, "lat": []}
            if ok:
                store[dim]["ok"] += 1
                if lat:
                    store[dim]["lat"].append(lat)
            else:
                store[dim]["fail"] += 1

    def rate(st):
        tot = st["ok"] + st["fail"]
        return None if tot == 0 else st["ok"] / tot

    def avg_lat(st):
        return sum(st["lat"]) / len(st["lat"]) if st["lat"] else 1e9

    combos = [(k, m) for k in key_pool for m in model_pool]

    def score(c):
        k, m = c
        ms = model_stats.get(m, {"ok": 0, "fail": 0, "lat": []})
        ks = key_stats.get(k, {"ok": 0, "fail": 0, "lat": []})
        mr = rate(ms)
        kr = rate(ks)
        if mr is None and kr is None:
            return (1, 0, 0, 0)            # both untested -> middle
        if mr is not None and mr > 0:
            return (0, -mr, -(kr or 0), -avg_lat(ms))   # proven model: best tier
        if kr is not None and kr > 0:
            return (0, 0, -kr, 0)           # untested model but good key
        return (2, 0, 0, 0)                # only failures -> worst tier

    combos.sort(key=score)
    return combos


def _rest_call(api_key, model, parts, timeout=120):
    """Single REST generateContent call. parts = list of {'text':...} or
    {'inline_data':{...}}. Returns text string or raises urllib.error.HTTPError
    / Exception."""
    url = (f"https://generativelanguage.googleapis.com/v1beta/"
           f"models/{model}:generateContent?key={api_key}")
    body = json.dumps({"contents": [{"parts": parts}]}).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        jr = json.loads(resp.read().decode("utf-8"))
    try:
        return jr["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return json.dumps(jr)


def gemini_generate(prompt_text, image_paths=None, timeout=40,
                    extra_config_keys=None, prefer_tested=True,
                    on_progress=None):
    """Top-level helper. Builds the key+model combo list (ranked via
    test_results.json when prefer_tested=True), tries each via REST, and fails
    over on 429/401/400/503. Returns (text, info_dict).

    prompt_text: the text prompt.
    image_paths: optional list of local image file paths (base64 inline).
    on_progress: optional callback(event_dict) invoked live as the pool tries
        combos (e.g. {"type":"start"}, {"type":"combo","index":0,"total":N,
        "model":"..."}, {"type":"busy","attempt":1}, {"type":"quota"},
        {"type":"forbidden"}, {"type":"invalid_key"}, {"type":"other",
        "detail":"..."}, {"type":"done"}). Lets callers surface progress
        (e.g. 503 retries) while the call is still running. If None, no
        callbacks fire (backwards-compatible).
    """
    def _emit(ev):
        if on_progress:
            try:
                on_progress(ev)
            except Exception:
                pass
    image_paths = image_paths or []
    key_pool = load_key_pool(extra_config_keys=extra_config_keys)
    model_pool = load_model_pool()
    if not key_pool:
        _emit({"type": "error", "detail": "No Gemini API keys found (.env / keys.txt)."})
        return None, {"error": "No Gemini API keys found (.env / keys.txt)."}
    if not model_pool:
        _emit({"type": "error", "detail": "No models in model pool (models.txt)."})
        return None, {"error": "No models in model pool (models.txt)."}

    parts = [{"text": prompt_text}]
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}
    for p in image_paths:
        try:
            ext = os.path.splitext(p)[1].lower()
            mime = mime_map.get(ext, "image/png")
            with open(p, "rb") as ih:
                b64 = base64.b64encode(ih.read()).decode("ascii")
            parts.append({"inline_data": {"mime_type": mime, "data": b64}})
        except Exception as e:
            _emit({"type": "error", "detail": f"Could not read image {p}: {e}"})
            return None, {"error": f"Could not read image {p}: {e}"}

    if prefer_tested:
        combos = rank_combos(key_pool, model_pool)
    else:
        combos = [(k, m) for k in key_pool for m in model_pool]

    last_err = ""
    last_type = None
    dropped_keys = set()      # 400/401 -> key will never work
    dropped_combos = set()    # 403/404 -> (key,model) won't work, key may
    # Error-type counters (for the returned diagnostics).
    seen = {"quota": 0, "busy": 0, "invalid_key": 0, "forbidden": 0, "not_found": 0, "other": 0}

    def classify(code, err_text):
        t = (err_text or "").lower()
        if code in (400, 401) or "api_key_invalid" in t or "api key not valid" in t:
            return "invalid_key"
        if code == 429 or "resource_exhausted" in t or "quota" in t or "rate" in t:
            return "quota"
        if code == 403 or "forbidden" in t or "permission" in t or "new users" in t:
            return "forbidden"
        if code == 404 or "not found" in t or "not supported" in t:
            return "not_found"
        if code == 503 or "unavailable" in t or "high demand" in t:
            return "busy"
        return "other"

    _emit({"type": "start", "combos": len(combos),
           "keys": len(key_pool), "models": len(model_pool)})
    for ki, (api_key, model) in enumerate(combos):
        if api_key in dropped_keys:
            continue
        if (api_key, model) in dropped_combos:
            continue
        _emit({"type": "combo", "index": ki, "total": len(combos), "model": model})
        try:
            text = _rest_call(api_key, model, parts, timeout=timeout)
            _emit({"type": "done", "model": model,
                   "key_index": ki, "key_pool_size": len(key_pool),
                   "combo_index": ki, "combo_count": len(combos),
                   "dropped_keys": len(dropped_keys), "diagnostics": seen})
            return text, {"status": "success", "model": model,
                          "key_index": ki, "key_pool_size": len(key_pool),
                          "combo_index": ki, "combo_count": len(combos),
                          "dropped_keys": len(dropped_keys),
                          "diagnostics": seen}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", "replace")
            last_err = f"combo#{ki} ({model}): HTTP {e.code} {err_body[:160]}"
            etype = classify(e.code, err_body)
            seen[etype] = seen.get(etype, 0) + 1
            last_type = etype
            if etype == "invalid_key":
                # 400/401: this key is a "no" — drop it for the whole run.
                dropped_keys.add(api_key)
                print(f"DEBUG - Gemini: key dropped (invalid): {api_key[:8]}...")
                _emit({"type": "invalid_key", "attempt": seen["invalid_key"],
                       "model": model, "detail": last_err})
                continue
            if etype == "forbidden":
                # 403: key can't use THIS model ("new users can't use this model")
                # but may work on others — drop just this combo.
                dropped_combos.add((api_key, model))
                print(f"DEBUG - Gemini: combo dropped (forbidden): {model}")
                _emit({"type": "forbidden", "attempt": seen["forbidden"],
                       "model": model, "detail": last_err})
                continue
            if etype == "not_found":
                # 404: model name absent for this key — try next model, same key.
                dropped_combos.add((api_key, model))
                _emit({"type": "not_found", "attempt": seen["not_found"],
                       "model": model, "detail": last_err})
                continue
            # quota (429) / busy (503): "not now" — drop this combo (it's
            # overloaded/hot) and immediately try the next one. We do NOT wait
            # for the model to free up; a fresh combo gets a clean shot.
            print(f"DEBUG - Gemini failed ({etype}): {last_err}")
            if etype == "busy":
                dropped_combos.add((api_key, model))
            _emit({"type": etype, "attempt": seen[etype],
                   "model": model, "detail": last_err})
            continue
        except Exception as e:
            last_err = f"combo#{ki} ({model}): {type(e).__name__} {str(e)[:120]}"
            seen["other"] = seen.get("other", 0) + 1
            last_type = "other"
            print(f"DEBUG - Gemini error ({last_err})")
            _emit({"type": "other", "attempt": seen["other"],
                   "model": model, "detail": last_err})
            continue
    _emit({"type": "exhausted", "combos": len(combos),
           "last_error_type": last_type, "detail": last_err,
           "diagnostics": seen, "dropped_keys": len(dropped_keys)})
    return None, {"error": f"Gemini failed for all {len(combos)} combos.",
                  "last_error": last_err, "last_error_type": last_type,
                  "diagnostics": seen,
                  "dropped_keys": len(dropped_keys)}

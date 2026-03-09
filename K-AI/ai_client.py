import json, urllib.request, urllib.error

BRIDGE = "http://127.0.0.1:7842"

def check_bridge():
    try:
        with urllib.request.urlopen(f"{BRIDGE}/health", timeout=3) as r:
            return r.status == 200
    except:
        return False

def shutdown_bridge():
    try:
        req = urllib.request.Request(
            f"{BRIDGE}/shutdown", data=b'{}',
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except:
        return False

def get_status():
    """Get current bridge status: phase, detail, elapsed seconds."""
    try:
        with urllib.request.urlopen(f"{BRIDGE}/status", timeout=2) as r:
            return json.loads(r.read())
    except:
        return {"phase": "unknown", "detail": "", "elapsed": 0}

def edit_schematic(schematic: str, prompt: str, schematic_path: str = "") -> str:
    payload = json.dumps({"schematic": schematic, "prompt": prompt}).encode()
    req = urllib.request.Request(
        f"{BRIDGE}/edit", data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=86400) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Bridge error: {e.read().decode()}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach bridge: {e.reason}")
    if "error" in body:
        raise RuntimeError(body["error"])
    result = body.get("result", "").strip()
    if not result:
        raise RuntimeError("Empty response from Claude.")
    return result

"""
bridge.py - AI Schematic Assistant Bridge v5
Background Chrome, status tracking, session chat cleanup.
"""
import time, threading, sys, json, os, re, atexit, signal
from pathlib import Path
from flask import Flask, request, jsonify
import logging

PORT = 7842
CLAUDE_URL = "https://claude.ai/new"

# Suppress Flask request logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
driver = None
lock = threading.Lock()
current_chat_url = None

# ── Status tracking (polled by plugin for progress bar) ───────────────
_status = {"phase": "idle", "detail": "", "elapsed": 0, "t0": 0}

def _set_status(phase, detail=""):
    _status["phase"] = phase
    _status["detail"] = detail
    if phase == "idle":
        _status["elapsed"] = 0
        _status["t0"] = 0
    elif _status["t0"] == 0:
        _status["t0"] = time.time()
    if _status["t0"]:
        _status["elapsed"] = int(time.time() - _status["t0"])


# ── Cleanup ───────────────────────────────────────────────────────────

def delete_current_chat():
    global current_chat_url
    if not current_chat_url or not is_alive():
        return
    try:
        driver.get(current_chat_url)
        time.sleep(2)
        driver.execute_script("""
            var btns = document.querySelectorAll('button, [role="button"]');
            for (var b of btns) {
                var label = (b.getAttribute('aria-label') || b.innerText || '').toLowerCase();
                if (label.includes('more') || label.includes('option') || label === '...') {
                    b.click(); return 'clicked options';
                }
            }
            return 'not found';
        """)
        time.sleep(1)
        driver.execute_script("""
            var items = document.querySelectorAll('[role="menuitem"], [role="option"], button, li');
            for (var item of items) {
                var txt = item.innerText.toLowerCase();
                if (txt.includes('delete') || txt.includes('remove')) {
                    item.click(); return 'clicked delete';
                }
            }
            return 'not found';
        """)
        time.sleep(1)
        driver.execute_script("""
            var btns = document.querySelectorAll('button');
            for (var b of btns) {
                var txt = b.innerText.toLowerCase();
                if (txt.includes('delete') || txt.includes('confirm') || txt.includes('yes')) {
                    b.click(); return;
                }
            }
        """)
        time.sleep(1)
        current_chat_url = None
    except Exception:
        pass


def shutdown():
    delete_current_chat()
    try:
        driver.quit()
    except Exception:
        pass


# ── Browser ───────────────────────────────────────────────────────────

def start_browser():
    global driver
    import undetected_chromedriver as uc
    profile_dir = str(Path.home() / ".ai_schematic_chrome_profile")
    os.makedirs(profile_dir, exist_ok=True)
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_dir}")
    print("  Opening Chrome...")
    driver = uc.Chrome(options=options, headless=False, version_main=145)
    driver.get(CLAUDE_URL)
    print("  Waiting for claude.ai...", end="", flush=True)
    for _ in range(120):
        try:
            if "claude.ai" in driver.current_url and "login" not in driver.current_url:
                print(" Ready!")
                # Minimize — stays in taskbar, doesn't steal focus
                try:
                    driver.minimize_window()
                except Exception:
                    pass
                return
        except:
            pass
        print(".", end="", flush=True)
        time.sleep(2)
    print("\n  Still on login page — log in manually in the Chrome window.")


def is_alive():
    try:
        _ = driver.current_url
        return True
    except:
        return False


def ensure_alive():
    global driver
    if not is_alive():
        try:
            driver.quit()
        except:
            pass
        start_browser()


# ── Extraction helpers ────────────────────────────────────────────────

def dismiss_popups():
    try:
        driver.execute_script("""
            var btns = document.querySelectorAll('button');
            for (var b of btns) {
                var label = b.getAttribute('aria-label') || b.innerText || '';
                if (label.trim() === '×' || label === 'Close' || label === 'Dismiss') b.click();
            }
        """)
    except:
        pass


def _clean_kicad_text(raw):
    if not raw:
        return raw
    t = raw.replace('\u201c', '"').replace('\u201d', '"')
    t = t.replace('\u2018', "'").replace('\u2019', "'")
    t = t.replace('\u2013', '-').replace('\u2014', '-')
    t = t.replace('\u00a0', ' ')
    t = t.replace('\u2026', '...')
    t = t.lstrip('\ufeff')
    t = re.sub(r'^```[a-zA-Z]*\s*\n?', '', t)
    t = re.sub(r'\n?```\s*$', '', t)
    return t.strip()


def get_schematic_from_page():
    EXTRACT_FN = """
    function extractSexp(text) {
        var start = text.lastIndexOf('(kicad_sch');
        if (start === -1) return '';
        var depth = 0;
        for (var i = start; i < text.length; i++) {
            if (text[i] === '(') depth++;
            else if (text[i] === ')') {
                depth--;
                if (depth === 0) return text.substring(start, i+1);
            }
        }
        return '';
    }
    """
    strategies = [
        EXTRACT_FN + "return extractSexp(document.body.innerText || '');",
        EXTRACT_FN + "return extractSexp(document.body.textContent || '');",
        EXTRACT_FN + """
        var blocks = document.querySelectorAll('code, pre code, pre');
        var best = '';
        for (var b of blocks) {
            var r = extractSexp(b.textContent || '');
            if (r.length > best.length) best = r;
        }
        return best;
        """,
        EXTRACT_FN + """
        var msgs = document.querySelectorAll(
            '[data-testid="assistant-message"], [class*="assistant"], '
            + '.font-claude-message, [class*="response"]'
        );
        var best = '';
        for (var m of msgs) {
            var r = extractSexp(m.textContent || '');
            if (r.length > best.length) best = r;
        }
        return best;
        """,
    ]
    for js in strategies:
        try:
            raw = driver.execute_script(js) or ""
            if raw and raw.startswith("(kicad_sch"):
                cleaned = _clean_kicad_text(raw)
                if cleaned and cleaned.startswith("(kicad_sch"):
                    return cleaned
        except Exception:
            continue
    return ""


def _validate_schematic(text):
    if not text or not text.startswith("(kicad_sch"):
        return False, "Does not start with (kicad_sch"
    depth = 0
    for ch in text:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth < 0:
                return False, "Unbalanced parentheses"
    if depth != 0:
        return False, f"Unbalanced parentheses (depth={depth})"
    for req in ("version", "generator", "paper"):
        if f"({req}" not in text:
            return False, f"Missing ({req} ...)"
    if len(text) < 200:
        return False, f"Too short ({len(text)} chars)"
    return True, "OK"


def count_kicad_blocks():
    try:
        return driver.execute_script("""
            var body = document.body.innerText || '';
            var count = 0, idx = 0;
            while ((idx = body.indexOf('(kicad_sch', idx)) !== -1) { count++; idx += 10; }
            return count;
        """) or 0
    except:
        return 0


def is_generating():
    try:
        from selenium.webdriver.common.by import By
        btns = driver.find_elements(By.CSS_SELECTOR,
            "button[aria-label='Stop'], button[aria-label='Stop Response'], "
            "button[aria-label='Stop streaming'], button[data-testid='stop-button']")
        if any(b.is_displayed() for b in btns):
            return True
        return bool(driver.execute_script(
            "return !!document.querySelector('[data-is-streaming=\"true\"], .streaming');"))
    except:
        return False


def get_input_box():
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    wait = WebDriverWait(driver, 30)
    for sel in ["div[data-testid='chat-input']", "div.ProseMirror", "div[contenteditable='true']"]:
        try:
            el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
            if el.is_displayed():
                return el
        except:
            continue
    return None


def type_and_send(text):
    from selenium.webdriver.common.by import By
    dismiss_popups()
    box = get_input_box()
    if not box:
        raise RuntimeError("Could not find Claude input box. Are you logged in?")
    driver.execute_script("arguments[0].click();", box)
    time.sleep(0.5)
    driver.execute_script("""
        var el = arguments[0];
        el.focus();
        el.innerText = '';
        document.execCommand('selectAll', false, null);
        document.execCommand('delete', false, null);
    """, box)
    time.sleep(0.3)
    CHUNK = 30000
    if len(text) > CHUNK:
        for i in range(0, len(text), CHUNK):
            driver.execute_script("""
                var el = arguments[0];
                el.textContent += arguments[1];
                el.dispatchEvent(new InputEvent('input', {bubbles:true}));
            """, box, text[i:i+CHUNK])
            time.sleep(0.2)
    else:
        driver.execute_script("arguments[0].innerText = arguments[1];", box, text)
    time.sleep(0.5)
    driver.execute_script(
        "arguments[0].dispatchEvent(new InputEvent('input', {bubbles:true}));", box)
    time.sleep(1)
    driver.execute_script("""
        var r = document.createRange(), s = window.getSelection();
        r.selectNodeContents(arguments[0]); r.collapse(false);
        s.removeAllRanges(); s.addRange(r);
    """, box)
    time.sleep(0.3)
    try:
        btns = driver.find_elements(By.CSS_SELECTOR,
            "button[aria-label='Send message'], button[data-testid='send-button']")
        visible = [b for b in btns if b.is_displayed()]
        if visible:
            driver.execute_script("arguments[0].click();", visible[0])
        else:
            raise Exception()
    except:
        driver.execute_script("""
            arguments[0].dispatchEvent(new KeyboardEvent('keydown',
                {key:'Enter',code:'Enter',keyCode:13,bubbles:true,cancelable:true}));
        """, box)
    time.sleep(2)


# ── Claude interaction ────────────────────────────────────────────────

def send_to_claude(schematic, prompt):
    global current_chat_url
    _set_status("preparing", "Setting up")
    ensure_alive()
    dismiss_popups()

    full_prompt = (
        "You are an expert KiCad 9 schematic engineer. "
        "Your output must be a valid .kicad_sch that opens and passes ERC.\n\n"

        "═══ CRITICAL OUTPUT FORMAT ═══\n"
        "- Return ONLY the raw (kicad_sch ...) S-expression.\n"
        "- No markdown fences, no explanation, no commentary.\n"
        "- First character = (  Last character = )\n"
        "- Do NOT use an artifact. Output raw text in the chat.\n"
        "- Use straight double quotes \" everywhere, never curly quotes.\n\n"

        "═══ #1 RULE: USE NET LABELS FOR ALL CONNECTIONS ═══\n"
        "This is the single most important rule. WIRES BETWEEN DISTANT PINS ALWAYS FAIL.\n"
        "Instead, connect everything with NET LABELS:\n"
        "  - Place a short 2.54mm stub wire from the pin.\n"
        "  - Attach a (net_label) at the end of the stub.\n"
        "  - Use the SAME label name on both ends of the connection.\n"
        "  - KiCad connects all matching labels automatically — no long wires needed.\n\n"
        "Example — connecting U1 pin 5 to R3 pin 1:\n"
        "  On U1 side: short stub wire + (net_label \"SIG_A\" ...)\n"
        "  On R3 side: short stub wire + (net_label \"SIG_A\" ...)\n"
        "  Done. No wire between them. KiCad connects them by name.\n\n"
        "WIRE RULES:\n"
        "  - Wires are ONLY for short local stubs (max 5mm) from a pin to a net label.\n"
        "  - NEVER draw a wire longer than 10mm. Use a net label instead.\n"
        "  - Every wire must be perfectly horizontal or vertical.\n"
        "  - Wire endpoints must be EXACTLY on a 1.27mm grid point.\n\n"

        "═══ POWER CONNECTIONS ═══\n"
        "- NEVER wire to a distant VCC or GND. Place a power symbol at EACH pin that needs it.\n"
        "- For VCC: place a (symbol (lib_id \"power:VCC\") ...) directly at the pin.\n"
        "- For GND: place a (symbol (lib_id \"power:GND\") ...) directly at the pin.\n"
        "- Each power symbol gets a unique ref like #PWR01, #PWR02, etc.\n"
        "- Use a 2.54mm stub wire from the pin to the power symbol. That's it.\n\n"

        "═══ LAYOUT & SPACING ═══\n"
        "Schematic MUST be spacious and readable. Think of it like a technical drawing:\n"
        "- Use the FULL A3 page (420mm x 297mm). Don't cram into a corner.\n"
        "- Group components into SECTIONS by function (power supply, MCU, connectors, etc).\n"
        "- MINIMUM 30mm gap between functional groups.\n"
        "- MINIMUM 20mm between individual components within a group.\n"
        "- Place components in a logical left-to-right signal flow.\n"
        "- Power supply section: top-left area.\n"
        "- Main IC/MCU: center of the page.\n"
        "- Connectors and headers: along the edges.\n"
        "- Decoupling caps: close to their IC but not overlapping.\n"
        "- Labels and ref designators must not overlap any symbol or wire.\n\n"

        "═══ PIN ENDPOINT CALCULATION ═══\n"
        "This is where most errors happen. The pin endpoint formula is:\n"
        "  Symbol placed at (at SX SY ANGLE)\n"
        "  Pin defined as (at PX PY PIN_ANGLE) (length L)\n"
        "  If ANGLE=0:   endpoint = (SX+PX + Lcos(PIN_ANGLE), SY+PY + Lsin(PIN_ANGLE))\n"
        "  But for common cases:\n"
        "    pin angle 0 (right):  endpoint = (SX+PX+L, SY+PY)\n"
        "    pin angle 90 (up):    endpoint = (SX+PX, SY+PY-L)\n"
        "    pin angle 180 (left): endpoint = (SX+PX-L, SY+PY)\n"
        "    pin angle 270 (down): endpoint = (SX+PX, SY+PY+L)\n"
        "  YOUR STUB WIRE MUST START AT EXACTLY THIS POINT.\n"
        "  If in doubt, just place a net label at the symbol location and skip the wire.\n\n"

        "═══ COORDINATES ═══\n"
        "- ALL coordinates must be multiples of 1.27mm.\n"
        "- Valid examples: 0, 1.27, 2.54, 3.81, 5.08, 6.35, 7.62, 8.89, 10.16, 12.7, 25.4...\n"
        "- Component origins: use multiples of 2.54mm (25.4, 50.8, 76.2, 101.6, ...).\n"
        "- This keeps everything on the standard grid and avoids alignment issues.\n\n"

        "═══ REFERENCE DESIGNATORS ═══\n"
        "- Every component: unique numbered ref (R1, R2, C1, C2, U1, J1, etc).\n"
        "- Power symbols: unique #PWR01, #PWR02, etc.\n"
        "- NEVER use R?, C?, U? — always assign explicit numbers.\n\n"

        "═══ UUIDS ═══\n"
        "- Every symbol, pin, wire, junction, label needs a unique UUID v4.\n"
        "- Format: \"xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx\"\n"
        "- NEVER reuse a UUID. Generate a fresh one for every element.\n\n"

        "═══ SELF-CHECK (DO THIS BEFORE OUTPUTTING) ═══\n"
        "Walk through EVERY connection in the schematic:\n"
        "  1. For each net label: are there at least 2 labels with the same name? (otherwise nothing is connected)\n"
        "  2. For each stub wire: does it start exactly at a pin endpoint?\n"
        "  3. For each power pin: does it have its OWN local power symbol? (VCC/GND/3V3)\n"
        "  4. Are all components on 2.54mm grid with no overlaps?\n"
        "  5. Are all ref designators unique?\n"
        "  6. Are all parentheses balanced?\n"
        "  7. Is the layout spacious and readable?\n\n"

        f"EXISTING SCHEMATIC:\n{schematic}\n\n"
        f"INSTRUCTION: {prompt}"
    )

    # Navigate to chat
    _set_status("navigating", "Opening chat")
    if current_chat_url:
        driver.get(current_chat_url)
        time.sleep(3)
        if "claude.ai/chat" not in driver.current_url:
            current_chat_url = None
            driver.get(CLAUDE_URL)
            time.sleep(3)
    else:
        driver.get(CLAUDE_URL)
        time.sleep(3)

    dismiss_popups()
    time.sleep(1)

    before_count = count_kicad_blocks()
    print(f"  Blocks before: {before_count}")

    _set_status("sending", "Sending to Claude")
    print("  Sending prompt...", end="", flush=True)
    type_and_send(full_prompt)
    print(" sent!")

    time.sleep(2)
    url = driver.current_url
    if "claude.ai/chat" in url:
        current_chat_url = url

    # Wait for Claude to START
    _set_status("waiting", "Waiting for Claude to start")
    print("  Waiting for Claude to start...", end="", flush=True)
    for _ in range(60):
        if is_generating() or count_kicad_blocks() > before_count:
            print(" started!")
            break
        print(".", end="", flush=True)
        time.sleep(2)
    else:
        print(" (proceeding anyway)")

    # Wait for Claude to FINISH (infinite)
    _set_status("generating", "Claude is writing schematic")
    print("  Waiting for Claude to finish...", end="", flush=True)
    while True:
        time.sleep(3)
        _set_status("generating", "Claude is writing schematic")
        still_gen = is_generating()
        text = get_schematic_from_page()

        if not still_gen and text and text.startswith("(kicad_sch"):
            print(" done!")
            _set_status("extracting", "Extracting & validating")
            time.sleep(3)
            text = get_schematic_from_page()

            valid, err = _validate_schematic(text)
            if not valid:
                print(f"  WARNING: {err}")
                _set_status("done", f"Warning: {err}")
            else:
                print(f"  Validated OK ({len(text)} chars)")
                _set_status("done", f"OK ({len(text)} chars)")
            return text

        print(".", end="", flush=True)


# ── Flask ─────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/status")
def status_route():
    return jsonify(_status)

@app.route("/shutdown", methods=["POST"])
def shutdown_route():
    def _die():
        time.sleep(1)
        shutdown()
        os._exit(0)
    threading.Thread(target=_die, daemon=True).start()
    return jsonify({"status": "shutting_down"})

@app.route("/edit", methods=["POST"])
def edit():
    with lock:
        data = request.get_json()
        if not data or "schematic" not in data or "prompt" not in data:
            return jsonify({"error": "Missing schematic or prompt"}), 400
        try:
            _set_status("preparing", "Starting")
            result = send_to_claude(data["schematic"], data["prompt"])
            _set_status("idle")
            return jsonify({"result": result})
        except Exception as e:
            _set_status("error", str(e))
            return jsonify({"error": str(e)}), 500


# ── Main ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  AI Schematic Assistant Bridge v5")
    print("  Starting browser...")
    start_browser()
    atexit.register(shutdown)
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    t = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False),
        daemon=True
    )
    t.start()
    print(f"\n  Bridge running on port {PORT}.")
    print("  Keep this window open. Chat is deleted on close.\n")

    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)

"""
AI Schematic Assistant for KiCad 9
===================================
Uses your claude.ai Max plan - no API key needed.
Everything runs in the background — just open the plugin and go.
"""

import sys
import os
import shutil
import subprocess
import time
import traceback
from pathlib import Path
from datetime import datetime

_PLUGIN_DIR = Path(__file__).parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

try:
    import pcbnew
    _KICAD = True
except ImportError:
    _KICAD = False

_bridge_proc = None
_LOG_FILE = Path.home() / ".ai_schematic_bridge.log"


def _find_system_python() -> str:
    import shutil as _sh
    candidates = []
    if sys.platform == "win32":
        for name in ("py", "python", "python3"):
            found = _sh.which(name)
            if found:
                candidates.append(found)
        for ver in ("313", "312", "311", "310"):
            for base_tmpl in (
                "{LOCALAPPDATA}/Programs/Python/Python{ver}",
                "C:/Python{ver}",
            ):
                base = Path(base_tmpl.format(
                    LOCALAPPDATA=os.environ.get("LOCALAPPDATA", ""),
                    ver=ver
                ))
                exe = base / "python.exe"
                if exe.exists():
                    candidates.append(str(exe))
    else:
        for name in ("python3", "python"):
            found = _sh.which(name)
            if found:
                candidates.append(found)
    for py in candidates:
        try:
            r = subprocess.run(
                [py, "-c", "import flask, selenium; print('ok')"],
                capture_output=True, text=True, timeout=10
            )
            if r.stdout.strip() == "ok":
                return py
        except Exception:
            continue
    return ""


def _bridge_is_alive():
    from ai_client import check_bridge
    return check_bridge()


def _ensure_bridge(wx_parent=None):
    import wx
    global _bridge_proc

    if _bridge_is_alive():
        return True

    if _bridge_proc is not None:
        if _bridge_proc.poll() is not None:
            _bridge_proc = None

    if _bridge_proc is None:
        python_exe = _find_system_python()
        if not python_exe:
            wx.MessageBox(
                "Cannot find a Python with flask + selenium.\n\n"
                "Run 1_INSTALL.bat first, then try again.",
                "Missing Dependencies", wx.OK | wx.ICON_ERROR)
            return False

        bridge_script = str(_PLUGIN_DIR / "bridge.py")

        spawn_kw = {}
        if sys.platform == "win32":
            # Normal console window, minimized in taskbar
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 6  # SW_MINIMIZE
            spawn_kw["startupinfo"] = si
            spawn_kw["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        else:
            spawn_kw["start_new_session"] = True

        try:
            _bridge_proc = subprocess.Popen(
                [python_exe, bridge_script],
                cwd=str(_PLUGIN_DIR),
                **spawn_kw
            )
        except Exception as e:
            wx.MessageBox(f"Failed to launch bridge:\n{e}",
                          "Bridge Error", wx.OK | wx.ICON_ERROR)
            return False

    # Wait with progress dialog
    MAX_TICKS = 90
    progress = wx.ProgressDialog(
        "AI Schematic Assistant",
        "Starting bridge...\nChrome is loading in the background.",
        maximum=MAX_TICKS, parent=wx_parent,
        style=wx.PD_APP_MODAL | wx.PD_CAN_ABORT | wx.PD_AUTO_HIDE
    )

    ok = False
    for tick in range(MAX_TICKS):
        cont, _ = progress.Update(tick,
            f"Starting bridge... ({tick * 2}s)\nChrome is loading in the background.")
        if not cont:
            progress.Destroy()
            try:
                _bridge_proc.terminate()
            except Exception:
                pass
            _bridge_proc = None
            return False
        wx.Yield()
        time.sleep(2)
        if _bridge_is_alive():
            ok = True
            break
        if _bridge_proc.poll() is not None:
            _bridge_proc = None
            break

    progress.Destroy()

    if not ok:
        wx.MessageBox(
            "Bridge did not start in time.\n\n"
            "If this is your first run, you may need to log into\n"
            "claude.ai in the Chrome window.\n\n"
            "Log: " + str(_LOG_FILE),
            "Bridge Timeout", wx.OK | wx.ICON_WARNING)
    return ok


def _kill_bridge():
    global _bridge_proc
    try:
        from ai_client import shutdown_bridge
        shutdown_bridge()
        time.sleep(3)
    except Exception:
        pass
    if _bridge_proc is not None:
        try:
            _bridge_proc.terminate()
            _bridge_proc.wait(timeout=5)
        except Exception:
            try:
                _bridge_proc.kill()
            except Exception:
                pass
        _bridge_proc = None


def _reopen_schematic(sch_path):
    sch_path = Path(sch_path)
    if not sch_path.exists():
        return
    try:
        if sys.platform == "win32":
            os.startfile(str(sch_path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(sch_path)])
        else:
            subprocess.Popen(["xdg-open", str(sch_path)])
    except Exception:
        pass


def _validate_schematic(text):
    """Returns (cleaned_text, error_msg). error_msg is None if OK."""
    text = text.strip()
    if not text.startswith("(kicad_sch"):
        preview = text[:300].replace('\n', ' ')
        return text, (
            f"Response doesn't start with (kicad_sch.\n\n"
            f"Claude returned:\n{preview}..."
        )
    depth = 0
    for ch in text:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
    if depth != 0:
        return text, (
            f"Unbalanced parentheses (depth={depth}).\n"
            f"Response was likely truncated.\n"
            f"Try a simpler instruction."
        )
    for section in ("version", "generator", "paper"):
        if f"({section}" not in text:
            return text, f"Missing required ({section} ...) section."
    return text, None


# ══════════════════════════════════════════════════════════════
#  Main entry point
# ══════════════════════════════════════════════════════════════

def run(schematic_path: str = None):
    import wx
    from dialog import AIAssistantDialog
    from ai_client import edit_schematic, check_bridge, get_status

    app = wx.GetApp() or wx.App(False)

    if not _ensure_bridge():
        return

    # Pick schematic
    if not schematic_path:
        with wx.FileDialog(
            None,
            message="Select KiCad Schematic",
            wildcard="KiCad Schematic (*.kicad_sch)|*.kicad_sch",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as fd:
            if fd.ShowModal() != wx.ID_OK:
                return
            schematic_path = fd.GetPath()

    schematic_path = Path(schematic_path)
    backup_path_holder = [None]  # mutable ref for closures

    # ── Define callbacks for the dialog ────────────────────────

    def on_edit(prompt_text):
        """Runs in worker thread. Reads file, backs up, calls bridge, returns result."""
        content = schematic_path.read_text(encoding="utf-8")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bp = schematic_path.with_suffix(f".bak_{ts}.kicad_sch")
        shutil.copy2(schematic_path, bp)
        backup_path_holder[0] = bp
        return edit_schematic(content, prompt_text, str(schematic_path))

    def on_complete(edited_text):
        """Runs on main thread when worker finishes successfully."""
        bp = backup_path_holder[0]
        edited, err = _validate_schematic(edited_text)
        if err:
            dlg.log(f"  VALIDATION ERROR: {err}")
            dlg.log(f"  Backup preserved: {bp.name if bp else 'none'}")
            wx.MessageBox(
                f"{err}\n\nBackup preserved at {bp.name if bp else '?'}.",
                "Validation Error", wx.OK | wx.ICON_WARNING)
            return

        schematic_path.write_text(edited, encoding="utf-8")
        dlg.log(f"  Backup: {bp.name}")
        dlg.log(f"  Saved! ({len(edited)} chars)")
        dlg.enable_undo()

    def on_undo():
        bp = backup_path_holder[0]
        if bp and bp.exists():
            shutil.copy2(bp, schematic_path)
            dlg.log(f"  Restored from: {bp.name}")
        else:
            dlg.log("  No backup to restore.")

    # ── Create and configure dialog ───────────────────────────

    dlg = AIAssistantDialog(None, str(schematic_path), edit_callback=on_edit)
    dlg.set_status_fn(get_status)
    dlg.set_complete_callback(on_complete)
    dlg.set_undo_callback(on_undo)
    dlg.log(f"Loaded: {schematic_path.name}")
    dlg.log("Ready. Enter an instruction and click Apply.")

    # ShowModal keeps the dialog alive — it only returns when user clicks Close
    dlg.ShowModal()
    dlg.Destroy()

    # ── Cleanup ───────────────────────────────────────────────
    _kill_bridge()
    _reopen_schematic(schematic_path)


if _KICAD:
    class AISchematicAssistantPlugin(pcbnew.ActionPlugin):
        def defaults(self):
            self.name = "AI Schematic Assistant"
            self.category = "Schematic"
            self.description = "Edit schematics with natural language via Claude AI"
            self.show_toolbar_button = True
            self.icon_file_name = str(_PLUGIN_DIR / "icon.png")

        def Run(self):
            try:
                board = pcbnew.GetBoard()
                sch_path = None
                if board:
                    candidate = Path(board.GetFileName()).with_suffix(".kicad_sch")
                    if candidate.exists():
                        sch_path = str(candidate)
                run(sch_path)
            except Exception as exc:
                import wx
                wx.MessageBox(str(exc), "AI Schematic Assistant",
                              wx.OK | wx.ICON_ERROR)

    AISchematicAssistantPlugin().register()

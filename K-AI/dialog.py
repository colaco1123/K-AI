import wx
import threading

PHASE_LABELS = {
    "idle": "",
    "preparing": "Preparing...",
    "navigating": "Opening chat...",
    "sending": "Sending prompt to Claude...",
    "waiting": "Waiting for Claude to start...",
    "generating": "Claude is writing the schematic...",
    "extracting": "Extracting & validating...",
    "done": "Done!",
    "error": "Error",
    "unknown": "Working...",
}


class AIAssistantDialog(wx.Dialog):
    def __init__(self, parent, schematic_path, edit_callback=None):
        super().__init__(parent, title="AI Schematic Assistant",
                         size=(620, 530),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._edit_callback = edit_callback
        self._worker = None
        self._result_box = {}
        self._status_fn = None
        self._complete_callback = None
        self._undo_callback = None

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # ── File path row ─────────────────────────────────────
        path_row = wx.BoxSizer(wx.HORIZONTAL)
        path_row.Add(wx.StaticText(panel, label="File:"), 0,
                     wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        path_ctrl = wx.TextCtrl(panel, value=schematic_path, style=wx.TE_READONLY)
        path_row.Add(path_ctrl, 1, wx.EXPAND)
        vbox.Add(path_row, 0, wx.EXPAND | wx.ALL, 10)

        # ── Instruction label + prompt ────────────────────────
        vbox.Add(wx.StaticText(panel, label="Instruction:"), 0, wx.LEFT, 10)
        self.prompt = wx.TextCtrl(panel, style=wx.TE_MULTILINE, size=(-1, 90))
        self.prompt.SetHint("e.g. Add a 100nF decoupling cap between VCC and GND near U1")
        vbox.Add(self.prompt, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # ── Buttons ───────────────────────────────────────────
        self.apply_btn = wx.Button(panel, label="Apply Edit")
        self.apply_btn.SetDefault()
        self.undo_btn = wx.Button(panel, label="Undo Last")
        self.undo_btn.Disable()
        self.close_btn = wx.Button(panel, wx.ID_CANCEL, "Close")
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_row.Add(self.apply_btn, 0, wx.RIGHT, 8)
        btn_row.Add(self.undo_btn, 0, wx.RIGHT, 8)
        btn_row.AddStretchSpacer()
        btn_row.Add(self.close_btn)
        vbox.Add(btn_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # ── Progress bar (always visible, empty when idle) ────
        self.progress_bar = wx.Gauge(panel, range=100, size=(-1, 12),
                                      style=wx.GA_HORIZONTAL | wx.GA_SMOOTH)
        self.progress_bar.SetValue(0)
        vbox.Add(self.progress_bar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ── Status line (phase label + elapsed timer) ─────────
        status_row = wx.BoxSizer(wx.HORIZONTAL)
        self.status_label = wx.StaticText(panel, label="")
        self.status_label.SetForegroundColour(wx.Colour(60, 60, 60))
        small_font = self.status_label.GetFont()
        small_font.SetPointSize(max(small_font.GetPointSize() - 1, 7))
        self.status_label.SetFont(small_font)
        self.elapsed_label = wx.StaticText(panel, label="")
        self.elapsed_label.SetForegroundColour(wx.Colour(120, 120, 120))
        self.elapsed_label.SetFont(small_font)
        status_row.Add(self.status_label, 1, wx.EXPAND)
        status_row.Add(self.elapsed_label, 0, wx.ALIGN_CENTER_VERTICAL)
        vbox.Add(status_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 10)

        # ── Separator ─────────────────────────────────────────
        vbox.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # ── Log box ───────────────────────────────────────────
        vbox.Add(wx.StaticText(panel, label="Log:"), 0, wx.LEFT | wx.TOP, 10)
        self.log_box = wx.TextCtrl(panel,
                                    style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
                                    size=(-1, 130))
        self.log_box.SetBackgroundColour(wx.Colour(20, 20, 30))
        self.log_box.SetForegroundColour(wx.Colour(150, 255, 150))
        vbox.Add(self.log_box, 1, wx.EXPAND | wx.ALL, 10)

        panel.SetSizer(vbox)

        # ── Events ────────────────────────────────────────────
        self.apply_btn.Bind(wx.EVT_BUTTON, self._on_apply)
        self.undo_btn.Bind(wx.EVT_BUTTON, self._on_undo)
        self.close_btn.Bind(wx.EVT_BUTTON, self._on_close)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        # Pulse timer (animates progress bar)
        self._pulse_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self._pulse_timer)
        self._pulse_val = 0
        self._polling = False

        self.Centre()

    # ── Callback setters ──────────────────────────────────────

    def set_status_fn(self, fn):
        self._status_fn = fn

    def set_complete_callback(self, fn):
        self._complete_callback = fn

    def set_undo_callback(self, fn):
        self._undo_callback = fn

    # ── Button handlers ───────────────────────────────────────

    def _on_apply(self, _):
        p = self.prompt.GetValue().strip()
        if not p:
            wx.MessageBox("Please enter an instruction.", "Empty",
                          wx.OK | wx.ICON_WARNING)
            return
        if self._worker and self._worker.is_alive():
            return

        self.log(f"\n> {p}")
        self._set_busy(True)

        self._result_box = {"result": None, "error": None}

        def _work():
            try:
                self._result_box["result"] = self._edit_callback(p)
            except Exception as e:
                self._result_box["error"] = e

        self._worker = threading.Thread(target=_work, daemon=True)
        self._worker.start()
        self._polling = True
        self._pulse_timer.Start(100)

    def _on_undo(self, _):
        if self._undo_callback:
            self._undo_callback()

    def _on_close(self, evt):
        if self._worker and self._worker.is_alive():
            wx.MessageBox(
                "Claude is still generating.\n"
                "Wait for it to finish, then close.",
                "Please Wait", wx.OK | wx.ICON_INFORMATION)
            return
        self._pulse_timer.Stop()
        self.EndModal(wx.ID_CANCEL)

    # ── Timer: drives both pulse animation and status polling ─

    def _on_timer(self, _):
        # Animate the bar
        self._pulse_val = (self._pulse_val + 2) % 100
        self.progress_bar.SetValue(self._pulse_val)

        # Poll bridge status
        if self._polling and self._status_fn:
            try:
                st = self._status_fn()
                phase = st.get("phase", "unknown")
                elapsed = st.get("elapsed", 0)
                self.status_label.SetLabel(PHASE_LABELS.get(phase, phase))
                if elapsed > 0:
                    m, s = divmod(elapsed, 60)
                    self.elapsed_label.SetLabel(f"{m}:{s:02d}")
            except Exception:
                pass

        # Check if worker finished
        if self._worker and not self._worker.is_alive():
            self._polling = False
            self._pulse_timer.Stop()
            self._worker.join()
            self._worker = None
            self._set_busy(False)

            if self._result_box.get("error"):
                err = self._result_box["error"]
                self.log(f"  ERROR: {err}")
                wx.MessageBox(str(err), "Error", wx.OK | wx.ICON_ERROR)
            elif self._result_box.get("result") and self._complete_callback:
                self._complete_callback(self._result_box["result"])

    # ── UI helpers ────────────────────────────────────────────

    def _set_busy(self, busy):
        self.apply_btn.Enable(not busy)
        self.prompt.Enable(not busy)
        self.close_btn.Enable(not busy)
        self.apply_btn.SetLabel("Working..." if busy else "Apply Edit")
        if not busy:
            self.progress_bar.SetValue(0)
            self.status_label.SetLabel("")
            self.elapsed_label.SetLabel("")

    def log(self, msg):
        self.log_box.AppendText(msg + "\n")

    def enable_undo(self):
        self.undo_btn.Enable()

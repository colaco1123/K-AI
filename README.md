# K-AI — AI-Powered KiCad Schematic Assistant

K-AI is a KiCad plugin that lets you describe a schematic in plain text and have Claude AI generate or modify it for you — no API key required. It works by bridging KiCad with a Chrome-controlled Claude session, so it runs on your existing Claude plan.

---

## How It Works

1. The plugin opens a dialog inside KiCad where you type your prompt
2. A local bridge launches a Chrome window and navigates to Claude
3. Your prompt + current schematic context is sent to Claude
4. Claude's response is parsed and applied back to your schematic

No API billing. No key setup. Just your Claude account.

---

## Requirements

- KiCad 7 or 8
- Python 3.x (bundled with KiCad)
- Google Chrome
- A Claude account (claude.ai) — the better the model, the better the output

---

## Installation

### 1. Place the plugin folder

Open KiCad PCB Editor, then:

```
Tools > Scripting Console > Open Plugin Directory
```

Copy the `KI-AI` folder into that directory.

### 2. Run the install script

Navigate into the `KI-AI` folder and run:

- **Windows:** double-click `1_INSTALL.bat`
- **Mac/Linux:** run `bash 1_INSTALL.sh` in terminal

This installs the required dependencies (browser driver, etc.).

### 3. Refresh plugins

In KiCad:
```
Tools > Plugin and Scripting Console > Refresh Plugins
```

The **K-AI** button will appear in your toolbar.

---

## First-Time Setup

1. Click the K-AI plugin button
2. Run `2_START_BRIDGE` to launch the bridge
3. A Chrome window will open — **log in to claude.ai** once
4. You're ready to go

> ⚠️ Keep the Chrome window open while using the plugin. It's used to send and receive messages.

---

## Usage

1. Open a schematic in KiCad
2. Click the **K-AI** toolbar button
3. Type your prompt (e.g. *"Add a decoupling cap to the VCC rail"*)
4. Wait for Claude to respond and apply changes

**Tip:** Claude Sonnet or Opus will give faster and more accurate schematic results than Haiku.

---

## File Structure

```
KI-AI/
├── __init__.py          # Plugin entry point
├── 1_INSTALL            # Dependency installer
├── 2_START_BRIDGE       # Launches the Chrome bridge
├── ai_client.py         # Handles communication with Claude
├── bridge.py            # Browser automation layer
├── dialog.py            # KiCad plugin UI dialog
└── icon.png             # Toolbar icon
```

---

## Known Limitations

- Chrome must stay open during use
- First-time login to claude.ai is manual (by design)
- Complex schematics may hit Claude's context window
- Response time depends on Claude plan and model selected

---

## Roadmap

- [ ] Netlist-aware prompting
- [ ] Multi-turn conversation support
- [ ] Firefox support
- [ ] Auto-place generated components

---

## Contributing

Pull requests are welcome! If you find a bug or want to suggest a feature, open an issue.

---

## License

MIT License — free to use, modify, and distribute.

---

## Author

Built by [Your Name] — an aerospace engineering student and embedded systems developer.  
If you find this useful, leave a ⭐ on the repo!

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

- KiCad 9
- Google Chrome
- A Claude account (claude.ai) — the better the model, the better the output

---

## Installation

### 1. Open the Plugin Directory

In KiCad PCB Editor go to **Tools → External Plugins → Open Plugin Directory**

![Step 1 - Open Plugin Directory](https://raw.githubusercontent.com/colaco1123/K-AI/main/K-AI/assets/images/step1.png)

---

### 2. Place the K-AI Folder

Copy the `K-AI` folder into the plugin directory that just opened



---

### 3. Run the Install Script

Open the `K-AI` folder and double-click **`1_INSTALL`** — this installs the required dependencies

![Step 3 - File contents](https://raw.githubusercontent.com/colaco1123/K-AI/main/K-AI/assets/images/step2.png)

---

![Step 4 - K-AI toolbar icon](https://raw.githubusercontent.com/colaco1123/K-AI/main/K-AI/assets/images/step4.png)

### 4. Refresh Plugins & Launch

Go back to KiCad → **Tools → External Plugins → Refresh Plugins**

The **K-AI icon** will appear in your toolbar (the green square icon)

---

## First-Time Setup

1. Run **`2_START_BRIDGE`** from the K-AI folder
2. A Chrome window will open — **log in to claude.ai once**
3. Click the K-AI toolbar icon — the assistant dialog will open

> ⚠️ Keep the Chrome window open while using the plugin

---

## Usage

1. Open a schematic in KiCad
2. Click the **K-AI** toolbar button
3. Type your instruction in the prompt box (e.g. *"Add a decoupling cap to the VCC rail"*)
4. Click **Apply Edit** and wait for Claude to respond

![K-AI Dialog](https://raw.githubusercontent.com/colaco1123/K-AI/main/K-AI/assets/images/step3.png)

**Tip:** Claude Sonnet or Opus will give faster and more accurate results than Haiku.

---

## File Structure

```
K-AI/
├── __init__.py          # Plugin entry point
├── 1_INSTALL            # Dependency installer
├── 2_START_BRIDGE       # Launches the Chrome bridge
├── ai_client.py         # Handles communication with Claude
├── bridge.py            # Browser automation layer
├── dialog.py            # KiCad plugin UI dialog
└── icon.png             # Toolbar icon
```

---
![Step 2 - Place K-AI folder](https://raw.githubusercontent.com/colaco1123/K-AI/main/K-AI/assets/images/step5.png)
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

Built by colaco1123 — aerospace engineering student and embedded systems developer.  
If you find this useful, leave a ⭐ on the repo!

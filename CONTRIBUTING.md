# Contributing to NEXUS

First off — thank you for considering contributing to NEXUS. This is a personal hardware project built on a $10 Raspberry Pi and every contribution, whether it's a bug fix, a new voice command or a documentation improvement, genuinely matters.

---

## Table of Contents

- [Before You Start](#before-you-start)
- [Ways to Contribute](#ways-to-contribute)
- [Development Setup](#development-setup)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Adding New Voice Commands](#adding-new-voice-commands)
- [Adding New Apps to the Whitelist](#adding-new-apps-to-the-whitelist)
- [Code Style](#code-style)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)

---

## Before You Start

- Read the [README](README.md) fully — especially the Architecture Overview and Security Model sections.
- Make sure you have the hardware setup working before contributing code changes.
- All contributions must work on **Raspberry Pi Zero W (ARMv6, 512MB RAM)** — this is the primary target hardware. Keep memory usage in mind.

---

## Ways to Contribute

### 🐛 Bug Fixes
Found something broken? Open an issue first describing the bug, then submit a PR with the fix.

### 🎙️ New Voice Commands
Want NEXUS to do something new? Add a pattern matcher to `process_command()` in `main.py`. See the [Adding New Voice Commands](#adding-new-voice-commands) section below.

### 💻 New Apps to the Whitelist
Want to open an app that isn't in `ALLOWED_APPS`? See [Adding New Apps to the Whitelist](#adding-new-apps-to-the-whitelist).

### 📖 Documentation
Spotted a typo, unclear step or missing explanation in the README? Fix it — documentation PRs are always welcome.

### 🌍 Platform Support
Currently NEXUS's server node runs on **Windows only**. macOS and Linux support for `laptop_server.py` would be a valuable contribution.

---

## Development Setup

### Pi (Voice Node)
```bash
git clone https://github.com/SinhaRepo/nexus-ai-assistant.git
cd nexus-ai-assistant
python3 -m venv ~/.venv
source ~/.venv/bin/activate
pip install -r requirements-pi.txt
cp .env.example .env
# Fill in your API keys in .env
python3 main.py
```

### Laptop (Server Node)
```bash
pip install -r requirements-laptop.txt
cp .env.example .env
# Fill in your API keys in .env
python laptop_server.py
```

---

## Submitting a Pull Request

1. **Fork** the repo and create a branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes.** Keep commits focused — one logical change per commit.

3. **Test on real hardware if possible.** If you don't have a Pi Zero W, test on any Pi or even just the laptop server portion.

4. **Write a clear PR description** — explain what changed, why and how you tested it.

5. **Open the PR against `main`.**

### PR Checklist
- [ ] Tested on Raspberry Pi (or documented that hardware wasn't available)
- [ ] No new API keys or secrets hardcoded in source code
- [ ] No breaking changes to existing voice commands
- [ ] If adding new `.env` variables, updated `.env.example` too
- [ ] If changing `laptop_server.py` endpoints, updated the API reference in README

---

## Adding New Voice Commands

All voice commands are handled in `process_command()` in `main.py` (around line 869). The pattern is straightforward:

```python
# Example: adding a "flip a coin" command
if any(w in text_lower for w in ["flip a coin", "heads or tails", "coin flip"]):
    import random
    result = random.choice(["Heads", "Tails"])
    return f"I flipped a coin — it's {result}!"
```

**Rules for new commands:**
- Place it **before** the final AI fallback block at the bottom of `process_command()`
- Use `text_lower` (already lowercased + stripped) for matching
- Return a plain string — NEXUS will speak it and display it
- If your command needs the laptop server, use `p_laptop()` or `g_laptop()` helpers
- Keep responses concise — they're spoken aloud, not just displayed

---

## Adding New Apps to the Whitelist

Open `laptop_server.py` and find the `ALLOWED_APPS` dictionary (around line 505). Add your app:

```python
ALLOWED_APPS = {
    # ... existing apps ...
    "blender": r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
    "figma":   os.path.join(os.environ.get("LOCALAPPDATA", ""), "Figma", "Figma.exe"),
}
```

**Rules:**
- Use the **lowercase spoken name** as the key — this is what the user says
- Use the **full executable path** as the value
- Prefer `os.environ.get("APPDATA")` or `os.environ.get("LOCALAPPDATA")` for user-installed apps instead of hardcoded `C:\Users\username\` paths
- Never use `shell=True` — all app launches go through `subprocess.Popen` with a direct executable path

---

## Code Style

NEXUS doesn't use a strict linter, but please follow these conventions that are already consistent throughout the codebase:

- **Python 3.11+** syntax only
- **4-space indentation** — no tabs
- **f-strings** for string formatting, not `.format()` or `%`
- **`ui.show_error()`** for error output, not bare `print()` on the Pi
- **`try/except Exception`** blocks around all network calls — NEXUS must never crash due to an API being unavailable
- Keep `main.py` functions focused — if a function exceeds ~50 lines, consider splitting it
- All new `.env` variables must have a sensible default so NEXUS works out of the box without that variable set

---

## Reporting Bugs

Open a GitHub Issue with:

1. **What happened** — exact error message or unexpected behaviour
2. **What you expected** — what should have happened
3. **Hardware** — which Pi model, what microphone, what speaker
4. **Boot sequence output** — the 6-step `[OK]` / `[FAIL]` lines at startup
5. **Which `.env` variables are set** — don't share the values, just the names (e.g. `GROQ_API_KEY=set`, `ELEVENLABS_API_KEY=not set`)

---

## Suggesting Features

Open a GitHub Issue with the `enhancement` label. Describe:
- What you want NEXUS to do
- Which node it belongs on (Pi / laptop / both)
- Whether it needs a new API key or dependency

---

## Questions?

Open a GitHub Discussion or reach out on [LinkedIn](https://www.linkedin.com/in/sinhaansh).

---

*Built with ❤️ on a $10 Raspberry Pi Zero W — Ansh Sinha*

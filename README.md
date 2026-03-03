<div align="center">

#  NEXUS — AI Voice Assistant

**A hardware AI voice assistant built on a $10 Raspberry Pi Zero W that controls your laptop, plays Spotify, searches the web, monitors your system and talks back — all through a custom wake word.**

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://python.org)
[![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-Zero%20W-c51a4a?logo=raspberrypi&logoColor=white)](https://www.raspberrypi.com)
[![Flask](https://img.shields.io/badge/Flask-REST%20API-000?logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash-4285F4?logo=google&logoColor=white)](https://aistudio.google.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Created by [Ansh Sinha](https://www.linkedin.com/in/sinhaansh)** · [GitHub](https://github.com/SinhaRepo) · [LinkedIn](https://www.linkedin.com/in/sinhaansh)

</div>

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup — Raspberry Pi (Voice Node)](#setup--raspberry-pi-voice-node)
- [Setup — Windows Laptop (Server Node)](#setup--windows-laptop-server-node)
- [First Run — Verifying Everything Works](#first-run--verifying-everything-works)
- [Usage & Voice Commands](#usage--voice-commands)
- [API Endpoints Reference](#api-endpoints-reference)
- [How It Works — Technical Deep Dive](#how-it-works--technical-deep-dive)
- [Security Model](#security-model)
- [Troubleshooting](#troubleshooting)
- [License](#license)
- [Author](#author)

---

## Architecture Overview

NEXUS is a **two-node system**. The Raspberry Pi is the always-on **voice interface** — it listens, thinks and speaks. The Windows laptop is the **muscle** — it runs apps, plays music, browses the web and stores all data. The two talk over your home Wi-Fi using a REST API.

```
┌──────────────────────────────┐       HTTP/REST (Wi-Fi LAN)       ┌──────────────────────────────┐
│     RASPBERRY PI ZERO W      │ ◄───────────────────────────────► │       WINDOWS LAPTOP         │
│        (Voice Node)          │                                   │       (Server Node)          │
│                              │   POST /spotify/play              │                              │
│  • Wake Word Detection       │   POST /open_app                  │  • Flask REST API (port 5000)│
│    (Porcupine, on-device)    │   POST /memory                    │  • Spotify Web API (OAuth)   │
│  • Voice Recording           │   GET  /system_stats              │  • Selenium Browser Control  │
│    (PyAudio / sounddevice)   │   GET  /reminders/check           │  • yt-dlp + VLC Music        │
│  • Speech-to-Text            │   POST /take_note                 │  • System Monitoring (psutil)│
│    (Groq Whisper)            │   POST /run_command               │  • Persistent Memory (JSON)  │
│  • AI Processing             │                                   │  • Reminder Engine           │
│    (Gemini → Groq)           │   Token Auth Header:              │  • Notes Storage             │
│  • Text-to-Speech            │   X-Nexus-Token: <secret>         │  • App / Process Control     │
│    (ElevenLabs → Deepgram    │                                   │                              │
│     → Edge-TTS → pyttsx3)    │                                   │                              │
│  • Rich Terminal UI          │                                   │                              │
│                              │                                   │                              │
│  Hardware:                   │                                   │                              │
│    GPIO Button (Pin 23)      │                                   │                              │
│    USB Microphone            │                                   │                              │
│    Speaker (3.5mm / BT)      │                                   │                              │
└──────────────────────────────┘                                   └──────────────────────────────┘
```

### What Each Node Does

| | Raspberry Pi (Voice Node) | Laptop (Server Node) |
|---|---|---|
| **Brain** | Calls Gemini / Groq APIs for AI responses | — |
| **Ears** | Listens for "Hey Nexus" wake word + records speech | — |
| **Mouth** | Converts AI text to speech (4 TTS engines) | — |
| **Music** | Sends play/pause/skip commands | Runs Spotify API, yt-dlp, VLC |
| **Apps** | Sends open/close/kill commands | Executes on Windows |
| **Search** | Calls Tavily / DuckDuckGo from Pi directly | — |
| **Memory** | Sends chat history to store | Reads/writes JSON files |
| **Monitoring** | Polls alerts every 30s | Tracks CPU/battery/internet |

### Data Flow (End-to-End Pipeline)

```
 ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌────────────────┐    ┌─────────┐    ┌─────────┐
 │ "Hey    │───►│ Record   │───►│ Groq     │───►│ Command Router │───►│ Gemini  │───►│ Eleven  │
 │ Nexus!" │    │ Audio    │    │ Whisper  │    │ + Context      │    │ / Groq  │    │ Labs    │
 │         │    │ (16kHz)  │    │ STT      │    │ Injection      │    │ LLM     │    │ TTS     │
 └─────────┘    └──────────┘    └──────────┘    └───────┬────────┘    └─────────┘    └────┬────┘
  Porcupine      PyAudio         Cloud API        Pattern match         Cloud API       Speaker
  (on-device)   (shared stream)                   ~30 commands                          plays MP3
                                                       │
                                                       ▼
                                                 ┌───────────┐
                                                 │  Laptop   │  (only if command
                                                 │  REST API │   needs laptop)
                                                 └───────────┘
```

---

## Features

### Voice Input (3 Ways to Talk to NEXUS)
- **Custom wake word** — Say **"Hey Nexus"** and it starts listening. Powered by [Picovoice Porcupine](https://picovoice.ai/platform/porcupine/), runs 100% on-device (no cloud, no internet needed for detection).
- **Push-to-talk button** — Hold a physical GPIO button, speak, release. Great for noisy rooms.
- **Text input** — Type in the terminal. Works even without a microphone.

### AI Brain (Dual-Model Failover)
- **Primary**: Google Gemini 2.5 Flash — fast, smart, 1M token context.
- **Failover**: Gemini 2.5 Flash Lite → Groq Llama 3.3 70B Versatile.
- If the primary model hits a rate limit (HTTP 429), NEXUS automatically tries the next model. You never notice a hiccup.
- Multi-turn conversations with persistent chat history (survives reboots).
- **Anti-hallucination safeguards** — The system prompt strictly forbids the AI from inventing news, reminders, times or any facts. It can only use data explicitly provided in context.

### Text-to-Speech (4-Tier Waterfall)

| Priority | Engine | Quality | What Happens |
|----------|--------|---------|-------------|
| 1st | ElevenLabs | Premium, natural voice | Used until character quota runs out |
| 2nd | Deepgram Aura | High quality | Kicks in when ElevenLabs is exhausted |
| 3rd | Edge-TTS | Good (Microsoft) | Free, no quota limits |
| 4th | pyttsx3 | Basic, robotic | Offline fallback, always works |

NEXUS checks your ElevenLabs quota at startup. If it's low, it automatically starts at Deepgram instead. You can also manually switch engines: *"Use Edge TTS"*.

### Music (3-Tier Fallback)
- **Spotify** — Full OAuth 2.0 integration. Play, pause, skip, previous, volume control, "what's playing?"
- **yt-dlp + VLC** — If Spotify fails, NEXUS downloads the song from YouTube and plays it through VLC on your laptop.
- **YouTube Music (browser)** — Last resort: opens YouTube Music search in Chrome via Selenium.
- Just say: *"Play Bohemian Rhapsody"* — NEXUS tries all three automatically.

### Laptop System Control
- **Open apps** — *"Open VS Code"*, *"Open Chrome"*, *"Open Spotify"* (20+ whitelisted apps).
- **Close apps** — *"Close Chrome"*, *"Close Notepad"*.
- **Kill processes by port** — *"Kill port 3000"*.
- **Run terminal commands** — *"Run command git status"* (whitelisted prefixes only).
- **Git status** — *"Git status"* → branch, changes, recent commits.
- **System stats** — *"Laptop status"* → CPU %, RAM usage, battery level, disk space.

### Web Search (Smart Triggering)
- **Primary**: [Tavily AI Search](https://tavily.com/) — Returns AI-summarized answers, not just links.
- **Fallback**: DuckDuckGo — If Tavily is unavailable.
- Triggered naturally by phrases like: *"Who won the World Cup?"*, *"What is the price of Bitcoin?"*, *"Search for Python tutorials"*

### News & Daily Briefings
- Top headlines from [NewsAPI.org](https://newsapi.org/).
- Say **"Good morning"** → NEXUS greets you with the **exact current time**, **live weather**, **top news headlines** and **pending reminders**. All data is real — never fabricated.

### Persistent Reminders
- *"Remind me to call Mom in 30 minutes"*
- Stored as JSON on the laptop — survives Pi reboots.
- Background thread on the Pi polls every 30 seconds. When a reminder is due, it pops up on screen and NEXUS speaks it aloud.

### Note-Taking
- *"Take a note that the meeting is at 3 PM"* — Saved to `notes.txt` on the laptop.
- *"Read my notes"* — Reads everything back.
- *"Clear my notes"* — Deletes all notes.

### Weather
- Live weather via [Open-Meteo](https://open-meteo.com/) (completely free, no API key needed).
- *"Weather in Tokyo"*, *"Temperature in New York"*, *"How's the weather?"*
- Returns: temperature, humidity, wind speed.

### System Monitoring & Alerts
- A background thread on the laptop monitors CPU, battery and internet connectivity.
- **CPU > 80%** → Alert pushed to Pi and spoken aloud.
- **Battery < 20%** → Alert.
- **Internet down** → Alert.
- Cooldown timers prevent alert spam.

### Calculator
- *"Calculate 25 times 4"*, *"What is 144 divided by 12"*
- Safe math evaluation using Python's AST parser — no `eval()`, no code injection.

### Sleep Mode
- *"Goodnight"* or *"Going to bed"* → Plays calm ambient music on Spotify (or yt-dlp fallback).

### Personalization
- *"My name is Ansh"* → Remembered across sessions.
- *"I live in Mumbai"* → Weather defaults to your city.
- Persistent user profile stored on the laptop.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Voice Node** | Raspberry Pi Zero W (ARMv6, 512MB RAM) |
| **Server Node** | Windows Laptop — Flask REST API on port 5000 |
| **AI Models** | Google Gemini 2.5 Flash → 2.5 Flash Lite → Groq Llama 3.3 70B |
| **Speech-to-Text** | Groq Whisper large-v3-turbo |
| **Text-to-Speech** | ElevenLabs → Deepgram Aura → Edge-TTS → pyttsx3 |
| **Wake Word** | Picovoice Porcupine v4 (on-device, zero latency) |
| **Music** | Spotify Web API → yt-dlp + VLC → YouTube Music (Selenium) |
| **Web Search** | Tavily AI Search → DuckDuckGo |
| **News** | NewsAPI.org |
| **Weather** | Open-Meteo (free, no key) |
| **Browser Automation** | Selenium + Chrome DevTools Protocol |
| **System Monitoring** | psutil |
| **Terminal UI** | Rich (Python) |
| **Auth** | Token-based HTTP header authentication |

---

## Project Structure

```
nexus/
├── main.py                  # Raspberry Pi — wake word, voice, AI, commands (1624 lines)
├── ui.py                    # Raspberry Pi — Rich terminal UI module (319 lines)
├── laptop_server.py         # Laptop — Flask REST API server (1131 lines)
├── requirements-pi.txt      # Pi Python dependencies
├── requirements-laptop.txt  # Laptop Python dependencies
├── .env.example             # Environment variables template (copy to .env)
├── .gitignore               # Excludes runtime files, secrets, caches
├── LICENSE                  # MIT License
└── README.md                # You're reading this!
```

**Where each file goes:**

| File | Deploy To |
|------|-----------|
| `main.py` | Raspberry Pi (`/home/pi/main.py`) |
| `ui.py` | Raspberry Pi (`/home/pi/ui.py`) |
| `laptop_server.py` | Laptop (project folder) |
| `.env` | **Both** — Pi gets one copy, laptop gets another (different keys in each) |
| `requirements-pi.txt` | Raspberry Pi |
| `requirements-laptop.txt` | Laptop |

**Runtime files** (auto-generated, gitignored — you don't need to create these):

| File | Created By | Purpose |
|------|-----------|---------|
| `laptop_memory.json` | Laptop server | Chat history + user profile |
| `notes.txt` | Laptop server | User's saved notes |
| `reminders.json` | Laptop server | Persistent reminders |
| `spotify_token.json` | Laptop server | Spotify OAuth refresh token |
| `music_cache/` | Laptop server | yt-dlp downloaded audio files |
| `chrome_nexus/` | Laptop server | Selenium Chrome user data |
| `temp.mp3` | Pi | Current TTS audio (overwritten each time) |
| `input.wav` | Pi | Current voice recording (overwritten each time) |

---

## Prerequisites

### Hardware You'll Need

| Item | Why | Approximate Cost |
|------|-----|-----------------|
| **Raspberry Pi Zero W** (or any Pi with Wi-Fi) | The always-on voice node | ~$10 |
| **Micro SD Card** (8GB+) | Pi's storage for OS and code | ~$5 |
| **USB Microphone** (or USB sound card + 3.5mm mic) | Voice input | ~$5–10 |
| **Speaker** (3.5mm jack, USB, or Bluetooth) | Audio output for TTS and music | ~$5–15 |
| **Micro USB OTG Adapter** | Connect USB mic to Pi Zero's micro USB port | ~$2 |
| **Push Button** + 2 jumper wires | Physical push-to-talk button | ~$1 |
| **Micro USB Power Supply** (5V, 2.5A) | Power for the Pi | ~$8 |
| **Windows Laptop** (on the same Wi-Fi network) | The server node | (you already have this) |

> **Total cost (excluding the laptop): ~$35–50**

### API Keys You'll Need (All Have Free Tiers)

You need accounts on **8 services**. All of them offer free tiers that are more than enough for personal daily use. Here's exactly where to sign up:

| # | Service | What It Does | Sign Up Link | Free Tier |
|---|---------|-------------|-------------|-----------|
| 1 | **Groq** | Speech-to-Text (Whisper) + LLM fallback | **[console.groq.com](https://console.groq.com/)** | Generous free API calls |
| 2 | **Google AI Studio** | Primary AI brain (Gemini 2.5 Flash) | **[aistudio.google.com](https://aistudio.google.com/)** | Free API key, rate-limited |
| 3 | **ElevenLabs** | Premium text-to-speech | **[elevenlabs.io](https://elevenlabs.io/)** | 10,000 chars/month free |
| 4 | **Deepgram** | Backup text-to-speech | **[deepgram.com](https://deepgram.com/)** | $200 free credits on signup |
| 5 | **Tavily** | AI-powered web search | **[tavily.com](https://tavily.com/)** | 1,000 searches/month free |
| 6 | **NewsAPI** | News headlines | **[newsapi.org](https://newsapi.org/)** | 100 requests/day free |
| 7 | **Picovoice** | Wake word ("Hey Nexus") | **[console.picovoice.ai](https://console.picovoice.ai/)** | Free for personal use |
| 8 | **Spotify Developer** | Music playback control | **[developer.spotify.com](https://developer.spotify.com/)** | Free (requires Spotify account) |

> **Tip:** Open all 8 links in browser tabs right now and create accounts. Then come back here and continue. It takes about 15 minutes total.

### Software Requirements

| | Raspberry Pi | Laptop |
|---|---|---|
| **OS** | Raspberry Pi OS Lite (Bookworm, 32-bit) | Windows 10/11 |
| **Python** | 3.11+ (comes pre-installed with Pi OS) | 3.12+ ([python.org](https://python.org)) |
| **Other** | — | Google Chrome, ffmpeg, VLC (instructions below) |

---

## Setup — Raspberry Pi (Voice Node)

> **Goal:** By the end of this section, your Pi will be running NEXUS — listening for "Hey Nexus", recording your voice, talking back through the speaker, and sending commands to your laptop.

### Step 1: Flash the SD Card

1. Download and install **[Raspberry Pi Imager](https://www.raspberrypi.com/software/)** on your laptop.
2. Insert your micro SD card into your laptop.
3. Open Raspberry Pi Imager:
   - **Device:** Raspberry Pi Zero W
   - **OS:** Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)** (no desktop needed)
   - **Storage:** Your SD card
4. **Before clicking "Write"**, click the gear icon to open **Advanced Settings**:
   - **Enable SSH** → Use password authentication
   - Set **username**: `pi` and **password**: `raspberry` (or anything you'll remember)
   - **Configure Wi-Fi** → Enter your Wi-Fi name (SSID) and password
   - **Set hostname**: `nexus` (so you can reach it at `nexus.local`)
5. Click **Write** and wait for it to finish.
6. Eject the SD card and plug it into your Raspberry Pi.

### Step 2: First Boot & SSH In

1. Power on the Pi (plug in the micro USB power cable).
2. Wait **60–90 seconds** for it to boot and connect to Wi-Fi.
3. On your laptop, open a terminal (PowerShell on Windows) and type:

```bash
ssh pi@nexus.local
```

> **If `nexus.local` doesn't work:** Find your Pi's IP address from your router's admin page (usually `192.168.1.x`) and use `ssh pi@192.168.1.x` instead.

4. Type `yes` when asked to trust the fingerprint, then enter your password.

**You're now inside the Pi!** Everything from here runs on the Pi.

### Step 3: System Update

```bash
sudo apt update && sudo apt upgrade -y
```

This updates all system packages. Takes a few minutes on the Pi Zero — be patient.

### Step 4: Install Audio & Build Dependencies

The Pi needs several system libraries to handle microphone input, audio output and compile Python audio packages:

```bash
sudo apt-get install -y \
    libasound2-dev \
    portaudio19-dev \
    libportaudio2 \
    libatlas-base-dev \
    libopenblas-dev \
    python3-dev \
    python3-pip \
    python3-venv \
    flac \
    alsa-utils \
    libsndfile1-dev \
    libffi-dev
```

**What each package does:**

| Package | Why You Need It |
|---------|----------------|
| `libasound2-dev` | ALSA audio library (the base Linux audio system) |
| `portaudio19-dev` + `libportaudio2` | PortAudio — required by PyAudio for microphone recording |
| `libatlas-base-dev` + `libopenblas-dev` | Math libraries needed by NumPy and SciPy |
| `python3-dev` | Python C headers (some pip packages compile from source on ARM) |
| `python3-pip` + `python3-venv` | pip package manager and virtual environments |
| `flac` | Audio codec used during recording |
| `alsa-utils` | Includes `arecord` and `aplay` for testing your mic and speaker |
| `libsndfile1-dev` | Audio file I/O library (used by sounddevice / SciPy) |
| `libffi-dev` | Foreign function interface (needed by some Python packages) |

### Step 5: Test Your Microphone

Plug your USB microphone into the Pi (using the OTG adapter if you have a Pi Zero).

```bash
# List recording devices — you should see your USB mic
arecord -l
```

You should see something like:
```
card 1: Device [USB Audio Device], device 0: USB Audio [USB Audio]
```

Now test recording and playback:

```bash
# Record 3 seconds of audio
arecord -d 3 -f cd test.wav

# Play it back through the speaker
aplay test.wav
```

**If you hear your own voice, the mic and speaker are working!**

> **Troubleshooting:** If `arecord -l` shows nothing, try a different USB port or a different mic. On the Pi Zero, make sure the OTG adapter is connected to the **data** micro USB port (not the power port).

### Step 6: Set Up Python Virtual Environment

```bash
# Create a virtual environment
python3 -m venv ~/.venv

# Activate it (you'll need to do this every time you open a new SSH session)
source ~/.venv/bin/activate

# Verify Python is running from the venv
which python3
# Should show: /home/pi/.venv/bin/python3
```

> **Tip:** Add the activation command to your `.bashrc` so it runs automatically on every login:
> ```bash
> echo 'source ~/.venv/bin/activate' >> ~/.bashrc
> ```

### Step 7: Copy Project Files to the Pi

On your **laptop** (not the Pi SSH session), open a **new terminal window**:

```bash
# From the project folder on your laptop
scp main.py ui.py requirements-pi.txt .env.example pi@nexus.local:~/
```

This copies the 4 essential files to the Pi's home directory (`/home/pi/`).

### Step 8: Install Python Dependencies

Back on the **Pi** (your SSH session):

```bash
# Make sure the venv is active
source ~/.venv/bin/activate

# Install all Python packages
pip install -r requirements-pi.txt
```

> ⚠️ **This will take a while on the Pi Zero** (up to 20–30 minutes). NumPy, SciPy and PyAudio need to compile from source on ARMv6. Be patient — don't interrupt it.
>
> **If you get memory errors** during the install, create a temporary swap file first:
> ```bash
> sudo fallocate -l 512M /swapfile
> sudo chmod 600 /swapfile
> sudo mkswap /swapfile
> sudo swapon /swapfile
> # Now retry: pip install -r requirements-pi.txt
> ```

### Step 9: Wire the Physical Button

The push-to-talk button connects **GPIO Pin 23** to **Ground (GND)**. That's it — just two wires.

```
                    Raspberry Pi Zero W GPIO Header
                    (looking at the Pi with USB ports at the bottom)

                         ┌─────────────────────┐
                    3V3  │ (1)  (2) │ 5V
                  GPIO2  │ (3)  (4) │ 5V
                  GPIO3  │ (5)  (6) │ GND ◄──── Wire 2 (any GND pin works)
                  GPIO4  │ (7)  (8) │ GPIO14
                    GND  │ (9)  (10)│ GPIO15
                 GPIO17  │(11)  (12)│ GPIO18
                 GPIO27  │(13)  (14)│ GND
                 GPIO22  │(15)  (16)│ GPIO23 ◄── Wire 1
                    3V3  │(17)  (18)│ GPIO24
                 GPIO10  │(19)  (20)│ GND
                  GPIO9  │(21)  (22)│ GPIO25
                 GPIO11  │(23)  (24)│ GPIO8
                    GND  │(25)  (26)│ GPIO7
                         │  ...     │
                         └─────────────────────┘

    Wiring:
    ┌──────────┐
    │  Button  │
    │   ┌──┐   │
    │   │  │   │         Pin 16 (GPIO23) ───────── one leg of the button
    │   └──┘   │
    │          │         Pin 6  (GND)    ───────── other leg of the button
    └──────────┘

    That's it! The code enables an internal "pull-up" resistor,
    so pressing the button connects GPIO23 to GND, which the Pi
    detects as a button press. No external resistors needed.
```

> **No soldering required!** If your Pi has header pins pre-soldered, just push jumper wires onto Pin 16 (GPIO23) and Pin 6 (GND) and connect them to the two legs of the button.

### Step 10: Set Up the Porcupine Wake Word

1. Go to **[console.picovoice.ai](https://console.picovoice.ai/)** and create a free account.
2. Copy your **Access Key** from the dashboard — you'll need it for the `.env` file.
3. Go to the **Porcupine** section and create a **custom keyword**:
   - **Phrase**: `Hey Nexus`
   - **Platform**: `Raspberry Pi`
   - **Language**: English
4. Download the generated `.ppn` file (it will be named something like `Hey-Nexus_en_raspberry-pi_v4_0_0.ppn`).
5. Copy it to the Pi from your laptop:

```bash
# From your laptop terminal
scp Hey-Nexus_en_raspberry-pi_v4_0_0.ppn pi@nexus.local:~/
```

### Step 11: Create the `.env` File on the Pi

On the **Pi** (SSH session), create and edit the environment file:

```bash
nano ~/.env
```

Paste the following and **fill in your actual keys** (replace the `xxxx` placeholders):

```dotenv
# ─────────────────────────────────────────
# NEXUS — Raspberry Pi Environment Variables
# ─────────────────────────────────────────

# Connection to your laptop server
LAPTOP_IP=192.168.1.x          # ← Replace x with your laptop's actual IP
LAPTOP_PORT=5000
NEXUS_TOKEN=my-secret-token-123 # ← Make up any passphrase. Must match laptop .env!

# AI providers
GROQ_API_KEY=gsk_xxxxxxxxxxxx   # ← From console.groq.com → API Keys
GOOGLE_API_KEY=AIzaXXXXXXXXXX   # ← From aistudio.google.com → Get API Key

# Text-to-Speech
ELEVENLABS_API_KEY=sk_xxxxxxxx  # ← From elevenlabs.io → Profile → API Keys
DEEPGRAM_API_KEY=xxxxxxxx       # ← From deepgram.com → Dashboard → API Keys

# Web Search & News
TAVILY_API_KEY=tvly-xxxxxxxxxxxx # ← From tavily.com → Dashboard
NEWS_API_KEY=xxxxxxxxxxxxxxxx    # ← From newsapi.org → Get API Key

# Wake Word
PORCUPINE_ACCESS_KEY=xxxxxxxx   # ← From console.picovoice.ai
PORCUPINE_MODEL_PATH=/home/pi/Hey-Nexus_en_raspberry-pi_v4_0_0.ppn
```

**Save and exit:** Press `Ctrl+X`, then `Y`, then `Enter`.

> **How to find your laptop's local IP address:**
> On your **laptop**, open PowerShell and run:
> ```powershell
> ipconfig
> ```
> Look for **IPv4 Address** under your Wi-Fi adapter — it looks like `192.168.1.5` or `192.168.0.10`.

### Step 12: Test Run

```bash
# Make sure the venv is active
source ~/.venv/bin/activate

# Run NEXUS!
python3 main.py
```

You should see a 6-step boot sequence (see the [First Run](#first-run--verifying-everything-works) section below for expected output). If everything shows `[  OK  ]`, you're golden!

> Press `Ctrl+C` to stop NEXUS.

### Step 13: Auto-Start on Boot (systemd Service)

This makes NEXUS start **automatically** every time the Pi powers on — no need to SSH in and run it manually.

```bash
sudo nano /etc/systemd/system/nexus.service
```

Paste the following:

```ini
[Unit]
Description=NEXUS AI Voice Assistant
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
Environment=HOME=/home/pi
ExecStart=/home/pi/.venv/bin/python3 /home/pi/main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Save and exit (`Ctrl+X`, `Y`, `Enter`), then enable it:

```bash
# Reload systemd to detect the new service file
sudo systemctl daemon-reload

# Enable it to start on every boot
sudo systemctl enable nexus.service

# Start it right now (without rebooting)
sudo systemctl start nexus.service

# Check if it's running
sudo systemctl status nexus.service
```

**Useful commands for later:**

| Command | What It Does |
|---------|-------------|
| `sudo systemctl stop nexus.service` | Stop NEXUS |
| `sudo systemctl restart nexus.service` | Restart NEXUS |
| `sudo journalctl -u nexus.service -f` | View live logs (like watching the terminal) |
| `sudo systemctl disable nexus.service` | Disable auto-start on boot |

---

## Setup — Windows Laptop (Server Node)

> **Goal:** By the end of this section, your laptop will be running the NEXUS server — handling Spotify, system control, memory and music playback.

### Step 1: Install Python

1. Go to **[python.org/downloads](https://www.python.org/downloads/)** and download Python 3.12 or newer.
2. **During installation, CHECK the box that says "Add Python to PATH"** — this is critical!
3. Open PowerShell and verify:

```powershell
python --version
# Should show: Python 3.12.x or higher
```

### Step 2: Clone the Repository

```powershell
git clone https://github.com/anshsinha/nexus.git
cd nexus
```

> Or download the ZIP from GitHub and extract it to any folder.

### Step 3: Install Python Dependencies

```powershell
pip install -r requirements-laptop.txt
```

This installs: Flask, psutil, Selenium, yt-dlp, python-dotenv and other required packages.

### Step 4: Install Google Chrome

If you don't already have Chrome installed, download it from **[google.com/chrome](https://www.google.com/chrome/)**.

NEXUS uses Chrome (via Selenium) to open Google searches, YouTube and web pages on your laptop.

### Step 5: Install ffmpeg

ffmpeg is needed by yt-dlp to convert downloaded YouTube audio to MP3 format.

**Option A — via winget (recommended):**

```powershell
winget install Gyan.FFmpeg
```

**Option B — manual download:**

1. Go to **[gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/)**
2. Download `ffmpeg-release-essentials.zip`
3. Extract it to `C:\ffmpeg`
4. Add `C:\ffmpeg\bin` to your system PATH:
   - Press `Win+R` → type `sysdm.cpl` → press Enter
   - Click **Advanced** tab → **Environment Variables**
   - Under "System variables", find `Path` → click **Edit** → click **New** → type `C:\ffmpeg\bin`
   - Click **OK** on all dialogs

**Verify it works:**

```powershell
ffmpeg -version
# Should show: ffmpeg version 7.x.x ...
```

### Step 6: Install VLC

VLC is used to play downloaded music from yt-dlp on your laptop.

```powershell
winget install VideoLAN.VLC
```

Or download from **[videolan.org](https://www.videolan.org/)**.

> NEXUS expects VLC at `C:\Program Files\VideoLAN\VLC\vlc.exe`. If you installed it elsewhere, update the `vlc` path in the `ALLOWED_APPS` dictionary in `laptop_server.py`.

### Step 7: Set Up Spotify Developer Credentials

This is the most involved step — follow carefully:

1. Go to **[developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)** and log in with your Spotify account.
2. Click **Create App**.
3. Fill in the form:
   - **App Name**: `NEXUS`
   - **App Description**: `AI voice assistant`
   - **Redirect URI**: Enter exactly **`http://127.0.0.1:5000/callback`** and click **Add**
   - Check the **Web API** checkbox
4. Click **Save**.
5. On the app's Settings page, find and copy your **Client ID** and **Client Secret** (click "Show Client Secret").

> ⚠️ **The Redirect URI must be exactly `http://127.0.0.1:5000/callback`** — not `localhost`, not `https`, no trailing slash. This must match what's in the code.

### Step 8: Create the `.env` File on the Laptop

In the project root folder (the same folder that contains `laptop_server.py`), create a file named `.env`:

```dotenv
# ─────────────────────────────────────────
# NEXUS — Laptop Server Environment Variables
# ─────────────────────────────────────────

# Shared auth token (MUST match the Pi's .env — this is how they authenticate)
NEXUS_TOKEN=my-secret-token-123

# Spotify OAuth credentials (from Step 7)
SPOTIFY_CLIENT_ID=your_client_id_from_spotify_dashboard
SPOTIFY_CLIENT_SECRET=your_client_secret_from_spotify_dashboard
```

> **Important:** The `NEXUS_TOKEN` must be the **exact same string** on both the Pi and the laptop. This is how the Pi proves it's authorized to control your laptop.

### Step 9: Start the Server

```powershell
python laptop_server.py
```

You should see:

```
============================================================
Starting NEXUS Laptop Server on port 5000...
============================================================

  STEP 1: Open http://127.0.0.1:5000/spotify/login in your browser
          to connect Spotify (one-time setup).

  Available Endpoints:
    GET  /                    Server info
    GET  /status              Health check
    POST /laptop_time         System time [AUTH]
    ...
============================================================
  [OK] yt-dlp found: C:\Users\...\Scripts\yt-dlp.exe
  [OK] ffmpeg found: C:\ffmpeg\bin
```

> **If you see `[WARN] yt-dlp not found`** — double-check that `pip install yt-dlp` ran successfully and restart the server.
>
> **If you see `[WARN] ffmpeg not found`** — make sure ffmpeg is installed and on your PATH (Step 5).

### Step 10: Connect Spotify (One-Time Setup)

1. Open your browser and go to: **http://127.0.0.1:5000/spotify/login**
2. You'll be redirected to Spotify's login page. Log in and click **Agree**.
3. You'll see: **"Spotify connected to NEXUS!"**
4. Close the browser tab — you're done!

This creates a `spotify_token.json` file that stores your refresh token. Spotify stays connected until you revoke access — **you only need to do this once**.

> **Before using music commands:** Make sure Spotify is **open and active** on your laptop (even if paused). Spotify's API requires at least one "active device" to receive play commands.

---

## First Run — Verifying Everything Works

With the **laptop server running** and the **Pi fully set up**, start NEXUS on the Pi:

```bash
# On the Pi (via SSH or if you have a monitor connected)
source ~/.venv/bin/activate
python3 main.py
```

You should see this boot sequence:

```
╭──────────────────────────────────────────────────────────────╮
│        NEXUS  ::  NEURAL INTERFACE ONLINE                    │
│  NODE: RASPBERRY PI  |  ARCH: ARMv6  |  PYTHON 3.11          │
│  SESSION ACTIVE                                              │
╰──────────────────────────────────────────────────────────────╯
──────────── SUBSYSTEM INITIALIZATION SEQUENCE ─────────────

 [  OK  ]  [1/6]  Ears Online            (Groq Whisper)
 [  OK  ]  [2/6]  Brain Online           (gemini-2.5-flash)
 [  OK  ]  [3/6]  Voice Online           (ElevenLabs)
 [  OK  ]  [4/6]  Laptop Connected       (192.168.1.x:5000)
 [  OK  ]  [5/6]  Wake Word Online       ("Hey Nexus")
 [  OK  ]  [6/6]  Memory Fetched         (PASS)

──────────────────── READY ─────────────────────
  >> SAY "HEY NEXUS" OR HOLD BUTTON OR TYPE BELOW
```

**What each step means:**

| Step | `OK` means... | `FAIL` means... |
|------|-------------|----------------|
| **1/6 Ears** | Groq API key valid, mic detected | Check `GROQ_API_KEY` in Pi `.env` |
| **2/6 Brain** | Gemini API key valid | Check `GOOGLE_API_KEY` in Pi `.env` |
| **3/6 Voice** | ElevenLabs has quota remaining | Will auto-fallback to Deepgram or Edge (shown as `WARN`) |
| **4/6 Laptop** | Laptop server is reachable | Wrong IP, server not running, or firewall blocking port 5000 |
| **5/6 Wake Word** | Porcupine loaded the `.ppn` model | Wrong path or invalid access key |
| **6/6 Memory** | Chat history loaded from laptop | Laptop unreachable — starts with blank memory (not critical) |

**All 6 showing `[  OK  ]`? You're ready to go!** Say "Hey Nexus" and ask it anything. 

---

## Usage & Voice Commands

### How to Activate NEXUS

| Method | What You Do |
|--------|-------------|
| **Wake word** | Say **"Hey Nexus"** → mic activates → speak your command → wait for 2 seconds of silence |
| **Button** | **Hold** the GPIO button → speak → **release** the button |
| **Text** | Just type in the terminal and press Enter |

### Music Commands

| Say This | What Happens |
|----------|-------------|
| *"Play Bohemian Rhapsody"* | Searches Spotify → plays. Falls back to yt-dlp → YouTube Music |
| *"Play my workout playlist"* | Searches and plays on Spotify |
| *"Pause"* / *"Pause music"* | Pauses Spotify playback |
| *"Resume"* / *"Continue playing"* | Resumes playback |
| *"Skip"* / *"Next song"* | Skips to next track |
| *"Previous"* / *"Go back"* | Goes to previous track |
| *"Volume 70"* | Sets Spotify volume to 70% |
| *"What's playing?"* / *"Current song"* | Tells you the current track and artist |
| *"Stop"* / *"Stop music"* | Stops all audio playback |

### Daily Life Commands

| Say This | What Happens |
|----------|-------------|
| *"Good morning"* | Full daily briefing: time + weather + news + reminders |
| *"What time is it?"* / *"Tell me the time"* | Current time and date |
| *"Weather in London"* | Live temperature, humidity, wind for any city |
| *"How's the weather?"* | Weather for your saved home city |
| *"News"* / *"Headlines"* | Top 5 news headlines + opens Google News on laptop |
| *"Remind me to call Mom in 30 minutes"* | Sets a persistent reminder (survives reboots) |
| *"Take a note that the meeting is at 3 PM"* | Saves a note to the laptop |
| *"Read my notes"* | Reads back all saved notes |
| *"Clear my notes"* | Deletes all notes |
| *"Calculate 25 times 4"* | Returns: 100 (safe AST math) |
| *"Goodnight"* / *"Going to bed"* | Plays calm sleep music and says goodnight |

### Laptop Control Commands

| Say This | What Happens |
|----------|-------------|
| *"Open VS Code"* | Launches VS Code on the laptop |
| *"Open Chrome"* / *"Open Spotify"* | Launches the specified app |
| *"Close Chrome"* | Kills all Chrome processes |
| *"Kill port 3000"* | Kills whatever process is running on port 3000 |
| *"Run command git status"* | Runs `git status` and reads the output to you |
| *"Git status"* | Shows branch, changes and recent commits |
| *"Laptop status"* / *"CPU usage"* | CPU %, RAM usage, battery level, disk space |
| *"System status"* / *"Pi status"* | Pi's CPU temperature and available RAM |
| *"Battery level"* | Laptop battery percentage |

### Search & Knowledge Commands

| Say This | What Happens |
|----------|-------------|
| *"Who is Elon Musk?"* | Web search via Tavily → AI-summarized answer |
| *"What is quantum computing?"* | Knowledge query → context-enriched AI response |
| *"Search for Python tutorials"* | Web search + AI summary |
| *"Google search for best restaurants"* | Opens Google search on laptop + provides web search context |
| *"Open YouTube cats"* | Opens YouTube search for "cats" on the laptop |

### System Commands

| Say This | What Happens |
|----------|-------------|
| *"Use Edge TTS"* | Switches voice engine to Edge-TTS |
| *"Use Deepgram"* | Switches to Deepgram Aura |
| *"Use ElevenLabs"* | Switches back to ElevenLabs |
| *"My name is Ansh"* | Saves your name (remembered across sessions) |
| *"I live in Mumbai"* | Updates your home city (affects default weather) |
| *"Clear memory"* | Wipes all conversation history and starts fresh |
| *"Shut up"* / *"Be quiet"* | Immediately stops current audio |

---

## API Endpoints Reference

<details>
<summary><strong>Click to expand the full endpoint list (30+ endpoints)</strong></summary>

All endpoints are served by the **laptop server** at `http://<laptop-ip>:5000`.

Endpoints marked **[AUTH]** require the `X-Nexus-Token` header.

### Core

| Method | Endpoint | Auth | Description |
|--------|----------|:----:|-------------|
| GET | `/` | No | Server info + version |
| GET | `/status` | No | Health check (`{"status": "online"}`) |
| POST | `/laptop_time` | Yes | Current system time, day, date |

### Memory & Profile

| Method | Endpoint | Auth | Description |
|--------|----------|:----:|-------------|
| GET | `/memory` | No | Fetch chat history + user profile |
| POST | `/memory` | Yes | Save chat history + user profile |
| POST | `/memory/add` | Yes | Add a single fact to memory |
| DELETE | `/memory` | Yes | Wipe all memory |

### Notes

| Method | Endpoint | Auth | Description |
|--------|----------|:----:|-------------|
| POST | `/take_note` | Yes | Append a note |
| GET | `/read_notes` | No | Read all notes + memory facts |
| DELETE | `/clear_notes` | Yes | Delete all notes |

### Reminders

| Method | Endpoint | Auth | Description |
|--------|----------|:----:|-------------|
| GET | `/reminders` | No | List all reminders |
| POST | `/reminders` | Yes | Create a new reminder |
| GET | `/reminders/check` | No | Poll for due reminders |
| DELETE | `/reminders` | Yes | Clear all reminders |

### Spotify

| Method | Endpoint | Auth | Description |
|--------|----------|:----:|-------------|
| GET | `/spotify/login` | No | Start OAuth login flow |
| GET | `/callback` | No | OAuth callback handler |
| POST | `/spotify/play` | Yes | Search and play a track |
| POST | `/spotify/pause` | Yes | Pause playback |
| POST | `/spotify/resume` | Yes | Resume playback |
| POST | `/spotify/skip` | Yes | Skip to next track |
| POST | `/spotify/previous` | Yes | Previous track |
| GET | `/spotify/now_playing` | No | Current track info |
| POST | `/spotify/volume` | Yes | Set volume (0–100) |
| GET | `/spotify/status` | No | Check if Spotify is authenticated |

### System Control

| Method | Endpoint | Auth | Description |
|--------|----------|:----:|-------------|
| POST | `/open_app` | Yes | Open an app from the whitelist |
| POST | `/close_app` | Yes | Close an app by name |
| POST | `/kill_port` | Yes | Kill process on a specific port |
| POST | `/run_command` | Yes | Run a whitelisted terminal command |
| POST | `/git_status` | Yes | Git branch, status, recent commits |
| GET | `/system_stats` | No | CPU, RAM, battery, disk usage |
| GET | `/alerts` | No | Poll system alerts (CPU / battery / internet) |

### Browser & Media

| Method | Endpoint | Auth | Description |
|--------|----------|:----:|-------------|
| POST | `/search_google` | Yes | Open Google search in Chrome |
| POST | `/open_youtube` | Yes | Open YouTube search in Chrome |
| POST | `/open_url` | Yes | Open any URL in Chrome |
| POST | `/play_music` | Yes | Open URL in browser (YouTube Music fallback) |
| POST | `/music/ytdlp` | Yes | Download audio via yt-dlp and play in VLC |

</details>

---

## How It Works — Technical Deep Dive

### 1. Wake Word Detection

[Picovoice Porcupine](https://picovoice.ai/platform/porcupine/) runs **entirely on the Pi's CPU** — no cloud, no internet needed. It processes 16kHz audio frames from a single PyAudio stream. When it detects the acoustic pattern for "Hey Nexus", it flips the stream into recording mode.

**Key engineering detail:** The wake word listener and the push-to-talk button **share the same microphone stream**. This solves the "Device Unavailable" error that would happen if two audio streams tried to open the same mic simultaneously. The button communicates with the wake word thread via `threading.Event` objects instead of opening a second stream.

### 2. Voice Recording

After wake word detection (or button press), audio frames are buffered until:
- **Wake word mode:** 2 seconds of silence detected (RMS energy drops below threshold).
- **Button mode:** The button is released.

The raw 16kHz audio is resampled to 44.1kHz using SciPy for the WAV file format required by the STT API.

### 3. Speech-to-Text

The WAV file is sent to **Groq's Whisper API** (`whisper-large-v3-turbo` model). A prompt hint of "Regular conversation in English" biases toward clean English transcription and prevents artifacts.

### 4. Command Routing

The transcribed text runs through **~30 pattern matchers** in `process_command()`. Each matcher checks for specific keywords and triggers the appropriate action:

```
"play ..."           → Spotify / yt-dlp / YouTube Music
"weather in ..."     → Open-Meteo API
"remind me ..."      → Reminder engine (regex extracts time + message)
"open ..."           → Laptop /open_app endpoint
"search ..."         → Tavily / DuckDuckGo web search
"good morning"       → Full briefing (time + weather + news + reminders)
...everything else   → AI conversation with optional web search context
```

Commands that need real-time data (weather, news, time, search results) are fetched first and injected as **tagged context blocks** — like `[LIVE WEATHER]`, `[NEWS HEADLINES]`, `[LIVE SYSTEM TIME]` — into the AI prompt. The AI is strictly instructed to **only** use data from these blocks and never invent information.

**Important design decision:** Only the clean user text is saved to chat history. Context blocks are **ephemeral** — attached to the current prompt only and discarded after the response.

### 5. AI Response Generation

The context-enriched prompt is sent through a **failover chain**:

1. **Gemini 2.5 Flash** — Primary. Fast, high quality.
2. **Gemini 2.5 Flash Lite** — Tried if the primary returns HTTP 429 (rate limited).
3. **Groq Llama 3.3 70B** — Final fallback. Generous free tier, always works.

The first model that returns a successful response wins. The user never sees the failover happen — it just takes a moment longer.

### 6. Text-to-Speech

The AI's text response is cleaned (markdown stripped, links removed, whitespace normalized) and sent through the TTS waterfall:

1. **ElevenLabs** → Premium voice, quota checked at startup
2. **Deepgram Aura** → High quality, $200 free credit
3. **Edge-TTS** → Microsoft's free TTS, solid quality
4. **pyttsx3** → Fully offline, robotic, but always works

The resulting MP3 is played through `pygame.mixer`. If the user presses the button or says "stop" during playback, it's interrupted immediately.

### 7. Background Threads

Three daemon threads run continuously alongside the main loop:

| Thread | Interval | What It Does |
|--------|----------|-------------|
| **Memory sync** | 30 seconds | Flushes queued chat history updates to the laptop server |
| **Reminder poll** | 30 seconds | Checks for due reminders via `/reminders/check` |
| **Alert poll** | 30 seconds | Checks for CPU/battery/internet alerts via `/alerts` |

### 8. Chat History Management

In-memory chat history is capped at **50 messages** to protect the Pi Zero's 512MB RAM. When the cap is exceeded, the system prompt is preserved and only the most recent 40 messages are kept. The last 20 messages are also persisted to `laptop_memory.json` on the laptop for recovery across reboots.

---

## Security Model

| Layer | How It Works |
|-------|-------------|
| **Token authentication** | All mutating API endpoints require the `X-Nexus-Token` header. The token is loaded from `.env` — never hardcoded in source code. |
| **App whitelist** | Only pre-approved applications can be opened/closed (20+ apps defined in the `ALLOWED_APPS` dictionary). |
| **Command whitelist** | Terminal commands are restricted to safe prefixes: `git status`, `python --version`, `pip list`, `ipconfig`, etc. Arbitrary commands are rejected with HTTP 403. |
| **Safe calculator** | Math evaluation uses Python's `ast` module to parse expressions into an AST tree. No `eval()`, no `exec()`, no code injection possible. Only arithmetic operators are allowed. |
| **No secrets in code** | All API keys, tokens, and credentials are loaded from `.env` files via `python-dotenv`. The `.env` file is listed in `.gitignore` and never committed. |
| **Session security** | The Flask session secret key is a random 32-byte hex string generated fresh on each server start. |

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| **`[FAIL] Ears Failed`** at boot | Groq API key invalid or missing | Check `GROQ_API_KEY` in Pi's `.env` file |
| **`[FAIL] Brain Online`** at boot | Google API key not set | Check `GOOGLE_API_KEY` in Pi's `.env` file |
| **`[FAIL] Laptop Connected`** at boot | Laptop server not running, wrong IP, or firewall | 1) Start `laptop_server.py` on laptop, 2) Verify `LAPTOP_IP` in Pi `.env`, 3) Allow port 5000 in Windows Firewall |
| **`[FAIL] Wake Word`** at boot | Wrong Porcupine access key or `.ppn` file path | Verify `PORCUPINE_ACCESS_KEY` and `PORCUPINE_MODEL_PATH` in Pi `.env` |
| **`OSError: Device unavailable`** | Two audio streams fighting for the mic | This is handled automatically in the code. If it persists, unplug/replug the USB mic and restart NEXUS. |
| **ALSA errors flooding the terminal** | Linux audio subsystem noise | Automatically suppressed by the "Nuclear Silence Block" in `main.py`. If some slip through, they're harmless — ignore them. |
| **Spotify: "No active device"** | Spotify desktop app not open on laptop | Open Spotify on your laptop and play/pause any song once to activate a device. |
| **Spotify: "Not authenticated"** | Token expired or never set up | Visit `http://127.0.0.1:5000/spotify/login` on your laptop browser. |
| **Spotify: "Missing client_id"** | `.env` file not loaded | Make sure `.env` exists in the same folder as `laptop_server.py` and contains both `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`. |
| **yt-dlp: "not found"** | yt-dlp not installed or not on PATH | Run `pip install yt-dlp` on the laptop. The server auto-scans common install paths. |
| **ffmpeg: "not found"** | ffmpeg not installed or not on PATH | Install via `winget install Gyan.FFmpeg` or add `C:\ffmpeg\bin` to your system PATH (see Laptop Step 5). |
| **Gemini returns 429 errors** | Rate limit hit | Handled automatically — NEXUS tries the next model in the chain. No action needed. |
| **Pi runs out of memory during `pip install`** | Pi Zero only has 512MB RAM | Create a swap file (see Pi Step 8) and retry. |
| **`[FAIL] Memory Fetch`** at boot | Laptop unreachable at startup | NEXUS starts with blank memory and syncs once the laptop comes online. Not critical. |
| **"Goodnight" doesn't play music** | Spotify not active AND yt-dlp not available | Open Spotify on your laptop or ensure yt-dlp + ffmpeg are installed. |
| **"Play birthday playlist" plays wrong song** | — | Fixed in latest version. If you see this, update `main.py` on the Pi. |

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## Author

<div align="center">

**Built by [Ansh Sinha](https://www.linkedin.com/in/sinhaansh)**

[GitHub](https://github.com/SinhaRepo) · [LinkedIn](https://www.linkedin.com/in/sinhaansh)

---

*Built with ❤️ on a $10 Raspberry Pi Zero W*

</div>
# nexus-ai-assistant
# nexus-ai-assistant

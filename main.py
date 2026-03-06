# NEXUS AI Assistant — Created by Ansh Sinha | LinkedIn: linkedin.com/in/sinhaansh | GitHub: github.com/SinhaRepo | © 2026 All Rights Reserved
# --- NUCLEAR SILENCE BLOCK ---
import os
import sys
import warnings
import logging
from ctypes import *
import datetime
import pytz
import threading
import json
import re
import queue
import time
import asyncio
import subprocess
import math

# 1. Kill ALSA & Driver Errors — Nuclear approach
# Suppress libasound error callback
ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
def py_error_handler(filename, line, function, err, fmt): pass
c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
try:
    asound = cdll.LoadLibrary('libasound.so')
    asound.snd_lib_error_set_handler(c_error_handler)
except: pass

# 2. Redirect C-level stderr (fd 2) to /dev/null to kill PortAudio ALSA noise
# This stops "Expression 'ret' failed in pa_linux_alsa.c" and "snd_pcm_recover underrun"
# Python's sys.stderr is re-pointed to the original fd so our prints still work
import io as _io
try:
    _real_stderr_fd = os.dup(2)
    _devnull_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(_devnull_fd, 2)  # C libraries writing to fd 2 now go to /dev/null
    sys.stderr = _io.TextIOWrapper(_io.FileIO(os.dup(_real_stderr_fd), 'w'), line_buffering=True)
except Exception:
    pass  # Non-Linux or permission issue — skip

os.environ["PYTHONWARNINGS"] = "ignore"
def warn(*args, **kwargs): pass
warnings.warn = warn
warnings.simplefilter("ignore")
logging.getLogger("requests").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("duckduckgo_search").setLevel(logging.CRITICAL)

# --- UI MODULE ---
import ui
ui.print_header()

import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
from groq import Groq
import requests
import pygame
import edge_tts
from duckduckgo_search import DDGS
import gc
import traceback
import atexit
import signal
import urllib.parse
from dotenv import load_dotenv

# Try GPIO (Pi-only)
try:
    from gpiozero import Button
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False

# Try Porcupine wake word
try:
    import pvporcupine
    import struct
    PORCUPINE_AVAILABLE = True
except ImportError:
    PORCUPINE_AVAILABLE = False

# Try PyAudio (for shared mic with Porcupine)
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False

load_dotenv()

DEFAULT_CITY = os.getenv("DEFAULT_CITY", "London")

# ==========================================
# SHARED AUDIO COORDINATION
# ==========================================
# When Porcupine owns the mic, the button loop signals it via these events
# instead of opening a second audio stream (which causes Device Unavailable)
_button_held = threading.Event()      # Set while physical button is pressed
_button_released = threading.Event()  # Set when button is released
_button_audio_buf = []                # Frames captured during button hold
_button_audio_lock = threading.Lock() # Protects _button_audio_buf

# ==========================================
# CONFIGURATION & KEYS
# ==========================================
NEXUS_TOKEN = os.getenv("NEXUS_TOKEN") or os.getenv("JARVIS_TOKEN")
if not NEXUS_TOKEN:
    raise SystemExit("FATAL: NEXUS_TOKEN is not set in your .env file. Set it to any secret passphrase and add the same value to your laptop .env. Refusing to start.")
LAPTOP_IP = os.getenv("LAPTOP_IP", "192.168.1.5")
LAPTOP_PORT = os.getenv("LAPTOP_PORT", "5000")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
PORCUPINE_ACCESS_KEY = os.getenv("PORCUPINE_ACCESS_KEY", "")

BUTTON_PIN = 23
ELEVEN_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
ELEVEN_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE_ID}/stream"

# Porcupine wake word model path
PORCUPINE_MODEL_PATH = os.getenv("PORCUPINE_MODEL_PATH", "/home/pi/Hey-Nexus_en_raspberry-pi_v4_0_0.ppn")

req_session = requests.Session()
req_session.headers.update({
    "User-Agent": "NexusPiClient/3.0",
    "X-Nexus-Token": NEXUS_TOKEN
})

# ==========================================
# STATE
# ==========================================
chat_history = []
user_profile = {
    "name": None,
    "city": DEFAULT_CITY,
    "favorite_artists": [],
    "last_active": None,
    "conversation_count": 0,
    "custom_facts": {}
}
reminders_list = []
voice_engine_override = None
model_name = "Loading..."
internet_available = True
memory_queue = []
memory_sync_lock = threading.Lock()
_shutdown_done = False

# ==========================================
# BACKGROUND SYNC THREAD
# ==========================================
def bg_sync_thread():
    while True:
        time.sleep(30)
        with memory_sync_lock:
            if memory_queue:
                try:
                    hist_to_save = [m for m in chat_history if m["role"] != "system"][-20:]
                    payload = {"chat_history": hist_to_save, "user_profile": user_profile}
                    resp = req_session.post(f"http://{LAPTOP_IP}:{LAPTOP_PORT}/memory", json=payload, timeout=5)
                    if resp.status_code == 200:
                        memory_queue.clear()
                        ui.show_status("Background sync: memory flushed to laptop")
                except Exception:
                    pass
        
        # Check for alerts from laptop
        try:
            resp = req_session.get(f"http://{LAPTOP_IP}:{LAPTOP_PORT}/alerts", timeout=3)
            if resp.status_code == 200:
                alerts = resp.json().get("alerts", [])
                for alert in alerts:
                    ui.show_alert(alert.get("type", "ALERT").upper(), alert.get("message", ""))
                    threading.Thread(target=speak, args=(alert.get("message", ""),), daemon=True).start()
        except Exception:
            pass
        
        # Check for due reminders
        try:
            resp = req_session.get(f"http://{LAPTOP_IP}:{LAPTOP_PORT}/reminders/check", timeout=3)
            if resp.status_code == 200:
                due = resp.json().get("due_reminders", [])
                for msg in due:
                    ui.show_reminder(msg)
                    threading.Thread(target=speak, args=(f"Reminder: {msg}",), daemon=True).start()
        except Exception:
            pass

t_sync = threading.Thread(target=bg_sync_thread, daemon=True)
t_sync.start()

# ==========================================
# SHUTDOWN HANDLER
# ==========================================
def force_save_on_exit():
    global _shutdown_done
    if _shutdown_done:
        return
    _shutdown_done = True
    try:
        hist_to_save = [m for m in chat_history if m["role"] != "system"][-20:]
        payload = {"chat_history": hist_to_save, "user_profile": user_profile}
        req_session.post(f"http://{LAPTOP_IP}:{LAPTOP_PORT}/memory", json=payload, timeout=3)
        ui.show_shutdown(success=True)
    except Exception:
        ui.show_shutdown(success=False)

atexit.register(force_save_on_exit)
signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))

# ==========================================
# INITIALIZATION & SYSTEM CHECK
# ==========================================
client_groq = None
button = None
q = queue.Queue()

try:
    client_groq = Groq(api_key=GROQ_API_KEY)
    pygame.mixer.init()
    if GPIO_AVAILABLE:
        button = Button(BUTTON_PIN, pull_up=True, bounce_time=0.1)
    ui.boot_step(1, 6, "Ears Online", "(Groq Whisper)", "ok", [
        "> Groq client initialized",
        "> pygame.mixer ready",
        f"> GPIO Button: {'PIN 23 bound' if button else 'Not available'}",
        "> Audio queue allocated",
    ])
    internet_available = True
except Exception as e:
    ui.boot_step(1, 6, "Ears Failed", "(Groq Offline)", "fail", [
        f"> Init error: {e}",
    ])
    internet_available = False

audio_clock = pygame.time.Clock()

def ping_laptop():
    try:
        resp = requests.get(f"http://{LAPTOP_IP}:{LAPTOP_PORT}/status", timeout=3)
        if resp.status_code == 200:
            return resp.json().get("status") == "online"
        return False
    except Exception:
        return False

# Gemini model failover chain — if one hits 429 rate limit, try the next
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]
model_name = GEMINI_MODELS[0]

if GOOGLE_API_KEY:
    ui.boot_step(2, 6, "Brain Online", f"({model_name})", "ok", [
        f"> Primary: {GEMINI_MODELS[0]}",
        f"> Failover: {' → '.join(GEMINI_MODELS[1:])} → Groq",
        "> Auto-rotation on 429 rate limits",
        "> Final fallback: Groq (llama-3.3-70b-versatile)",
    ])
else:
    ui.boot_step(2, 6, "Gemini Unavailable", "(No API key)", "fail", [
        "> GOOGLE_API_KEY not set in .env",
        "> Using Groq only (llama-3.3-70b-versatile)",
    ])

# ElevenLabs startup verification
try:
    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    sub_resp = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers=headers, timeout=5)
    if sub_resp.status_code == 200:
        sub_data = sub_resp.json()
        char_remaining = sub_data.get("character_limit", 0) - sub_data.get("character_count", 0)
        if char_remaining > 100:
            ui.boot_step(3, 6, "Voice Online", "(ElevenLabs)", "ok", [
                f"> ElevenLabs quota: {char_remaining} chars remaining",
                "> Fallback chain: Deepgram Aura → Edge-TTS → pyttsx3",
            ])
        else:
            voice_engine_override = "deepgram"
            ui.boot_step(3, 6, "Voice Degraded", "(Deepgram Aura)", "warn", [
                f"> ElevenLabs exhausted ({char_remaining} chars left)",
                "> Fallback: Deepgram Aura TTS active",
            ])
    else:
        voice_engine_override = "deepgram"
        ui.boot_step(3, 6, "Voice Degraded", "(Deepgram Aura)", "warn", [
            f"> ElevenLabs API error (HTTP {sub_resp.status_code})",
            "> Fallback: Deepgram Aura TTS active",
        ])
except Exception as e:
    voice_engine_override = "deepgram"
    ui.boot_step(3, 6, "Voice Degraded", "(Deepgram Aura)", "warn", [
        f"> ElevenLabs check failed: {e}",
        "> Fallback: Deepgram Aura TTS active",
    ])

if ping_laptop():
    ui.boot_step(4, 6, "Laptop Connected", f"({LAPTOP_IP}:{LAPTOP_PORT})", "ok", [
        f"> Target: {LAPTOP_IP}:{LAPTOP_PORT}",
        "> HTTP session established",
    ])
else:
    ui.boot_step(4, 6, "Laptop Offline", f"({LAPTOP_IP})", "fail", [
        "> Ping failed — laptop offline or wrong IP",
    ])

# Porcupine wake word check
porcupine_handle = None
if PORCUPINE_AVAILABLE and PORCUPINE_ACCESS_KEY:
    try:
        porcupine_handle = pvporcupine.create(
            access_key=PORCUPINE_ACCESS_KEY,
            keyword_paths=[PORCUPINE_MODEL_PATH]
        )
        ui.boot_step(5, 6, "Wake Word Online", '("Hey Nexus")', "ok", [
            "> Picovoice Porcupine v4 loaded",
            f"> Model: {os.path.basename(PORCUPINE_MODEL_PATH)}",
            f"> Sample rate: {porcupine_handle.sample_rate} Hz",
        ])
    except Exception as e:
        ui.boot_step(5, 6, "Wake Word Failed", "(Button-only mode)", "fail", [
            f"> Porcupine error: {e}",
        ])
        porcupine_handle = None
else:
    reason = "pvporcupine not installed" if not PORCUPINE_AVAILABLE else "No access key"
    ui.boot_step(5, 6, "Wake Word Unavailable", f"({reason})", "warn", [
        "> Falling back to button + text input",
    ])

# ==========================================
# MEMORY & PROFILE SYSTEM
# ==========================================
def inject_system_prompt():
    global chat_history, user_profile
    sys_prompt = f"""You are NEXUS — a highly intelligent, witty, and efficient personal AI assistant created by Ansh Sinha.
You speak naturally like a knowledgeable friend — confident, direct, occasionally humorous.
You ALWAYS respond in English only. Never use any other language under any circumstance even if the user writes in another language — always respond in English.
Use the user name at most once per response — never repeat it multiple times.
Match response depth to question complexity — concise for simple questions, detailed for complex ones.
Never truncate complex answers. When asked for bullet points lists or formatted output provide exactly that format.
For ambiguous sentences acknowledge all possible meanings.
Never start consecutive sentences the same way.
Never use filler words like Certainly or Absolutely or Of course. Be direct and helpful.
When asked who made you or who created you, always say you were created by Ansh Sinha as a personal AI project.

You are a VOICE assistant running on a Raspberry Pi with a microphone and speaker. Users talk to you by voice (wake word or button) or by typing in the terminal. You CAN hear them — their speech is transcribed to text before reaching you.
You have access to: laptop control (open/close apps, run commands), Spotify music, web search, weather, news, note-taking, reminders, system monitoring, and YouTube.
When the user says to play music, you have Spotify integration. For system commands, you can open apps, close apps, check CPU/RAM, and run terminal commands on the user's laptop.

CRITICAL RULES — NEVER VIOLATE:
- ONLY use data explicitly provided in the Context block. NEVER invent, guess, or fabricate facts, news headlines, reminders, times, prices, or any data.
- If the Context does not contain specific information (news, reminders, time, weather), say you don't have that information right now.
- NEVER make up news headlines. If no [NEWS HEADLINES] context is provided, say no headlines are available.
- NEVER invent reminders the user didn't set. If no [PENDING REMINDERS] context is provided, say there are no pending reminders.
- NEVER guess the current time. Only state the time if [LIVE SYSTEM TIME] is in the Context. If not, say you cannot determine the time right now.
- When the Context contains [LIVE SYSTEM TIME], use EXACTLY that time — never modify or round it.
- When reporting weather, use EXACTLY the numbers from context. Do not round or change them.
"""
    uname = user_profile.get("name")
    if not uname or uname in ["Unknown", "Boss", "None"]:
        uname = "Boss"
    sys_prompt += f"\nUser's name is {uname}. Always use this name. Never use a wrong name."
    sys_prompt += f"\nThe user lives in {user_profile.get('city', DEFAULT_CITY)}."

    if not chat_history or chat_history[0]["role"] != "system":
        chat_history.insert(0, {"role": "system", "content": sys_prompt})
    else:
        chat_history[0] = {"role": "system", "content": sys_prompt}

def is_clean_english(text):
    for ch in text:
        if '\u0900' <= ch <= '\u097F':
            return False
    return True

def load_persistence():
    global chat_history, user_profile, reminders_list
    try:
        resp = req_session.get(f"http://{LAPTOP_IP}:{LAPTOP_PORT}/memory", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            p_data = data.get("user_profile", {})
            if "name" in p_data and p_data["name"]:
                cleaned_name = str(p_data["name"]).rstrip(".,!?;: ")
                if cleaned_name in ["Kya", "Unknown", "None", ""]:
                    p_data["name"] = "Boss"
                else:
                    p_data["name"] = cleaned_name
            else:
                p_data["name"] = "Boss"
            if "city" in p_data and (not p_data["city"] or p_data["city"] in ["Kya", "Unknown", "None"]):
                p_data["city"] = DEFAULT_CITY
            user_profile.update(p_data)

            mem_hist = data.get("chat_history", [])
            clean_hist = []
            if isinstance(mem_hist, list):
                for m in mem_hist:
                    if "content" in m and is_clean_english(m["content"]):
                        clean_hist.append(m)
            if clean_hist:
                chat_history = clean_hist[-20:]
            ui.boot_step(6, 6, "Memory Fetched", "(PASS)", "ok", [
                f"> Retrieved chat_history ({len(chat_history)} messages)",
                f"> User profile: {user_profile.get('name', 'Boss')}, {user_profile.get('city', 'Unknown')}",
            ])
        else:
            ui.boot_step(6, 6, "Memory Fetch Failed", "(Starting blank)", "fail", [])
    except Exception:
        ui.boot_step(6, 6, "Memory Server Unreachable", "(Starting blank)", "fail", [])

    user_profile["last_active"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_profile["conversation_count"] = user_profile.get("conversation_count", 0) + 1
    inject_system_prompt()
    save_persistence()

    ui.boot_done()
    ui.show_status("Background sync thread started (interval: 30s)")
    uname = user_profile.get("name")
    greeting = ui.print_ready(uname)
    threading.Thread(target=speak, args=(greeting,), daemon=True).start()

def save_persistence():
    hist_to_save = [m for m in chat_history if m["role"] != "system"][-20:]
    payload = {"chat_history": hist_to_save, "user_profile": user_profile}
    try:
        resp = req_session.post(f"http://{LAPTOP_IP}:{LAPTOP_PORT}/memory", json=payload, timeout=2)
        if resp.status_code == 200:
            return True
    except Exception:
        pass
    with memory_sync_lock:
        memory_queue.append("pending")
    return False

# ==========================================
# TOOLS & FEATURE UTILITIES
# ==========================================
def p_laptop(route, payload=None, timeout=10):
    try:
        resp = req_session.post(f"http://{LAPTOP_IP}:{LAPTOP_PORT}/{route}", json=payload, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        # Return actual error from server (e.g. Spotify "no active device")
        try:
            return resp.json()
        except Exception:
            return {"success": False, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        ui.show_error("Laptop API", f"{route}: {e}")
    return {"success": False, "error": "Unreachable"}

def g_laptop(route, timeout=5):
    """GET request to laptop."""
    try:
        resp = req_session.get(f"http://{LAPTOP_IP}:{LAPTOP_PORT}/{route}", timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        ui.show_error("Laptop API", f"{route}: {e}")
    return {}

def get_live_weather(city):
    ui.show_status(f"Fetching weather for: {city} (Open-Meteo)")
    try:
        clean_city = city.lower().replace('how is', '').replace('weather in', '').replace('temperature in', '').strip()
        if not clean_city:
            clean_city = DEFAULT_CITY
        geo_url = f"https://nominatim.openstreetmap.org/search?q={clean_city}&format=json&limit=1"
        geo_res = req_session.get(geo_url, timeout=10).json()
        if geo_res and len(geo_res) > 0:
            lat = geo_res[0]["lat"]
            lon = geo_res[0]["lon"]
            name = geo_res[0]["display_name"].split(',')[0]
            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
            w_res = req_session.get(weather_url, timeout=10).json()
            current = w_res["current"]
            temp = current["temperature_2m"]
            hum = current["relative_humidity_2m"]
            wind = current.get("wind_speed_10m", "N/A")
            return f"[LIVE WEATHER]: {name}: {temp}°C, Humidity: {hum}%, Wind: {wind} km/h"
        else:
            return f"City '{city}' not found in geolocation database."
    except Exception as e:
        ui.show_error("Weather", str(e))
    return "Weather API is currently down."

def tavily_search(query, max_res=3):
    """Search using Tavily AI Search API."""
    if not TAVILY_API_KEY:
        return None
    ui.show_status(f"Searching (Tavily): {query}")
    try:
        resp = req_session.post("https://api.tavily.com/search", json={
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": "basic",
            "max_results": max_res,
            "include_answer": True,
        }, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            answer = data.get("answer", "")
            results = data.get("results", [])
            summary_parts = []
            if answer:
                summary_parts.append(f"AI Summary: {answer}")
            for r in results[:max_res]:
                summary_parts.append(f"- {r.get('title', '')}: {r.get('content', '')[:200]}")
            if summary_parts:
                return "[SEARCH DATA (Tavily)]:\n" + "\n".join(summary_parts)
    except Exception as e:
        ui.show_error("Tavily", str(e))
    return None

def duckduckgo_search(query, max_res=3):
    """Fallback search using DuckDuckGo."""
    ui.show_status(f"Searching (DuckDuckGo): {query}")
    for attempt in range(2):
        try:
            results = DDGS().text(query, max_results=max_res, timelimit='y')
            if results:
                summary = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
                return f"[SEARCH DATA (DuckDuckGo)]:\n{summary}"
        except Exception as e:
            ui.show_error("DuckDuckGo", f"attempt {attempt+1}: {e}")
            time.sleep(1)
    return None

def web_search(query, max_res=3):
    """Search with Tavily (primary) → DuckDuckGo (fallback)."""
    result = tavily_search(query, max_res)
    if result:
        return result
    return duckduckgo_search(query, max_res)

def get_news_headlines(category="general", country="in", count=5):
    """Get news headlines via NewsAPI.org."""
    if not NEWS_API_KEY:
        return None
    ui.show_status(f"Fetching news headlines ({category})...")
    try:
        resp = req_session.get(
            f"https://newsapi.org/v2/top-headlines?country={country}&category={category}&pageSize={count}&apiKey={NEWS_API_KEY}",
            timeout=10
        )
        if resp.status_code == 200:
            articles = resp.json().get("articles", [])
            if articles:
                headlines = []
                for a in articles[:count]:
                    headlines.append(f"- {a.get('title', 'No title')}")
                return "[NEWS HEADLINES]:\n" + "\n".join(headlines)
    except Exception as e:
        ui.show_error("NewsAPI", str(e))
    return None

def set_reminder(minutes, message):
    """Set a reminder via laptop server (persisted)."""
    try:
        resp = req_session.post(
            f"http://{LAPTOP_IP}:{LAPTOP_PORT}/reminders",
            json={"message": message, "minutes": minutes},
            timeout=5,
            headers={"X-Nexus-Token": NEXUS_TOKEN}
        )
        if resp.status_code == 200:
            trigger_at = resp.json().get("trigger_at", f"{minutes} min")
            return True, trigger_at
    except Exception:
        pass
    return False, None

def safe_calculate(expression):
    """Safe math evaluation using ast."""
    import ast
    import operator
    
    ops = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg,
        ast.Mod: operator.mod,
    }
    
    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Non-numeric constant")
        elif isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            op_func = ops.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported operator: {type(node.op)}")
            return op_func(left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            op_func = ops.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported unary operator")
            return op_func(operand)
        else:
            raise ValueError(f"Unsupported AST node: {type(node)}")
    
    try:
        expr = expression.lower()
        expr = expr.replace("plus", "+").replace("minus", "-").replace("times", "*")
        expr = expr.replace("multiplied by", "*").replace("divided by", "/").replace("divide", "/")
        expr = expr.replace("x", "*").replace("^", "**")
        expr = re.sub(r'[^0-9+\-*/().%]', '', expr)
        if not expr:
            return None
        tree = ast.parse(expr, mode='eval')
        result = _eval(tree)
        return result
    except Exception:
        return None

def extract_sentiment(text):
    text = text.lower()
    if any(w in text for w in ["depressed", "cry", "sad"]):
        return "sad"
    if any(w in text for w in ["frustrated", "angry", "mad", "annoyed"]):
        return "angry"
    if any(w in text for w in ["awesome", "happy", "excited", "amazing"]):
        return "excited"
    if any(w in text for w in ["rest", "tired", "sleepy", "exhausted"]):
        return "tired"
    return "neutral"

def get_pi_health():
    try:
        temp = subprocess.check_output(["vcgencmd", "measure_temp"]).decode().strip()
    except Exception:
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                t = int(f.read()) / 1000.0
                temp = f"temp={t}'C"
        except Exception:
            temp = "temp=N/A"
    mem_info = "RAM=N/A"
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if "MemAvailable" in line:
                    mem_info = "Available RAM=" + line.split(":")[1].strip()
                    break
    except Exception:
        pass
    return f"[PI STATUS]: CPU {temp}, {mem_info}"

def get_laptop_stats():
    """Get laptop system stats."""
    stats = g_laptop("system_stats")
    if "error" in stats or not stats:
        return None
    parts = []
    parts.append(f"CPU: {stats.get('cpu_percent', 'N/A')}%")
    parts.append(f"RAM: {stats.get('ram_used_gb', '?')}/{stats.get('ram_total_gb', '?')} GB ({stats.get('ram_percent', '?')}%)")
    parts.append(f"Disk: {stats.get('disk_used_gb', '?')}/{stats.get('disk_total_gb', '?')} GB ({stats.get('disk_percent', '?')}%)")
    if stats.get("battery_percent") is not None:
        batt = f"Battery: {stats['battery_percent']}%"
        if stats.get("battery_plugged"):
            batt += " (Charging)"
        elif stats.get("battery_time_left"):
            batt += f" ({stats['battery_time_left']} left)"
        parts.append(batt)
    return "[LAPTOP STATUS]: " + " | ".join(parts)

# ==========================================
# INTELLIGENCE ROUTING
# ==========================================
def call_gemini(history):
    if not GOOGLE_API_KEY:
        return None
    sys_p = history[0]["content"] if history and history[0]["role"] == "system" else ""
    gemini_mem = []
    prev_role = None
    for m in history[-8:]:
        if m["role"] == "system":
            continue
        role = "user" if m["role"] == "user" else "model"
        if role == prev_role and gemini_mem:
            gemini_mem[-1]["parts"][0]["text"] += "\n" + m["content"]
        else:
            gemini_mem.append({"role": role, "parts": [{"text": m["content"]}]})
        prev_role = role
    if gemini_mem and gemini_mem[0]["role"] != "user":
        gemini_mem = gemini_mem[1:]
    if not gemini_mem:
        return None
    payload = {
        "contents": gemini_mem,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1500}
    }
    if sys_p:
        payload["systemInstruction"] = {"parts": [{"text": sys_p}]}

    # Try each model in the failover chain
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GOOGLE_API_KEY}"
        ui.show_status(f"Processing via Gemini ({model})...")
        try:
            resp = req_session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=(10, 30))
            if resp.status_code == 200:
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            elif resp.status_code == 429:
                ui.show_error("Gemini", f"{model} rate-limited (429), trying next...")
                continue
            else:
                # Non-rate-limit error (auth, quota, etc.) — try next model
                ui.show_error("Gemini", f"{model} HTTP {resp.status_code}")
                continue
        except requests.exceptions.Timeout:
            ui.show_error("Gemini", f"{model} timeout")
            continue
        except Exception as e:
            ui.show_error("Gemini", f"{model}: {e}")
            continue
    return None

def call_groq(history):
    if client_groq is None:
        ui.show_error("Groq", "Client not initialized")
        return None
    try:
        recent = [history[0]] + history[-8:] if len(history) > 8 else history
        messages = [{"role": h["role"], "content": h["content"]} for h in recent]
        completion = client_groq.chat.completions.create(
            model="llama-3.3-70b-versatile", messages=messages, temperature=0.7, max_tokens=1500
        )
        return completion.choices[0].message.content
    except Exception as e:
        ui.show_error("Groq", str(e))
        return None

def get_ai_response(history):
    """Call Gemini first, fallback to Groq."""
    resp = call_gemini(history)
    if resp:
        return resp
    ui.show_status("Gemini failed, falling back to Groq...")
    resp = call_groq(history)
    if resp:
        return resp
    return "Sorry, AI brain is temporarily offline."

# ==========================================
# TTS: ElevenLabs → Deepgram Aura → Edge-TTS → pyttsx3
# ==========================================
def play_audio_file(filename):
    try:
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if button and button.is_pressed:
                pygame.mixer.music.stop()
                break
            audio_clock.tick(10)
        pygame.mixer.music.unload()
    except Exception as e:
        ui.show_error("Audio", str(e))

def speak_pyttsx3(text):
    ui.show_speaking("pyttsx3")
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
    except Exception:
        pass

def speak_edge(text):
    ui.show_speaking("edge")
    try:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(edge_tts.Communicate(text, "en-IN-PrabhatNeural").save("temp.mp3"))
        finally:
            loop.close()
        play_audio_file("temp.mp3")
    except Exception:
        speak_pyttsx3(text)

def speak_deepgram(text):
    """Deepgram Aura TTS."""
    if not DEEPGRAM_API_KEY:
        speak_edge(text)
        return
    ui.show_speaking("deepgram")
    try:
        resp = req_session.post(
            "https://api.deepgram.com/v1/speak?model=aura-asteria-en",
            headers={
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"text": text},
            timeout=10
        )
        if resp.status_code == 200:
            with open("temp.mp3", "wb") as f:
                f.write(resp.content)
            play_audio_file("temp.mp3")
        else:
            ui.show_error("Deepgram", f"HTTP {resp.status_code}")
            speak_edge(text)
    except Exception as e:
        ui.show_error("Deepgram", str(e))
        speak_edge(text)

def clean_for_speech(text):
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'[*#_`~]', '', text)
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def speak(text):
    if not isinstance(text, str):
        ui.show_error("Speech", f"Expected string, got {type(text)}")
        return
    text = clean_for_speech(text)
    if not text:
        return

    if voice_engine_override == "edge":
        speak_edge(text)
        return
    if voice_engine_override == "pyttsx3":
        speak_pyttsx3(text)
        return
    if voice_engine_override == "deepgram":
        speak_deepgram(text)
        return

    # Priority: ElevenLabs → Deepgram → Edge → pyttsx3
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    data = {
        "text": text, "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.35, "similarity_boost": 0.8, "style": 0.2, "use_speaker_boost": True}
    }
    try:
        response = req_session.post(ELEVEN_URL, json=data, headers=headers, stream=True, timeout=5)
        if response.status_code != 200:
            speak_deepgram(text)
            return
        ui.show_speaking("elevenlabs")
        with open("temp.mp3", "wb") as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        play_audio_file("temp.mp3")
    except Exception:
        speak_deepgram(text)

# ==========================================
# COMMAND PROCESSING
# ==========================================
def process_command(text):
    global chat_history, user_profile, voice_engine_override
    # Strip trailing punctuation from voice input (Whisper adds "." "?" etc.)
    text = text.strip()
    text_clean = re.sub(r'[.!?;:,]+$', '', text).strip()
    text_lower = text_clean.lower()
    original_text = text  # Preserve original (with punctuation) for chat history
    
    # --- STOP / QUIET ---
    stop_commands = ["stop", "shut up", "quiet", "stop playing", "stop music", "be quiet", "stop it", "sstop"]
    if text_lower in stop_commands or text_lower.startswith("stop playing"):
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except Exception:
            pass
        # Also pause Spotify
        p_laptop("spotify/pause")
        return "Stopped audio playback."

    # --- TTS ENGINE SWITCH ---
    if "use elevenlabs" in text_lower:
        voice_engine_override = None
        return "Switched to ElevenLabs TTS."
    if "use deepgram" in text_lower:
        voice_engine_override = "deepgram"
        return "Switched to Deepgram Aura TTS."
    if "use edge" in text_lower or "edge tts" in text_lower:
        voice_engine_override = "edge"
        return "Switched to Edge TTS."

    context = ""

    # --- MEMORY WIPE ---
    if any(w in text_lower for w in ["clear memory", "forget everything", "wipe memory"]):
        try:
            resp = req_session.delete(f"http://{LAPTOP_IP}:{LAPTOP_PORT}/memory", timeout=2, headers={"X-Nexus-Token": NEXUS_TOKEN})
            if resp.status_code == 200:
                chat_history = []
                user_profile = {"name": None, "city": DEFAULT_CITY, "favorite_artists": [], "last_active": None, "conversation_count": 0, "custom_facts": {}}
                inject_system_prompt()
                save_persistence()
                return "Memory entirely wiped. Starting fresh!"
        except Exception:
            pass
        return "Memory server unreachable, deletion failed."

    # --- NOTE TAKING ---
    if any(w in text_lower for w in ["take a note", "write this down", "save this", "note this"]):
        note_text = original_text  # Preserve case
        for w in ["take a note that", "take a note", "write this down that", "write this down", "save this", "note this down", "note this"]:
            note_text = re.sub(re.escape(w), '', note_text, flags=re.IGNORECASE).strip()
        if note_text:
            result = p_laptop("take_note", payload={"text": note_text})
            if result.get("status") == "success":
                return f"Noted: {note_text}"
            return "Failed to save note. Laptop unreachable."
        return "What would you like me to note down?"

    # --- READ NOTES ---
    if any(w in text_lower for w in ["read my notes", "what are my notes", "show my notes", "list my notes", "my notes"]):
        try:
            resp = req_session.get(f"http://{LAPTOP_IP}:{LAPTOP_PORT}/read_notes", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                n_str = data.get("notes_file", "").strip()
                c_facts = data.get("custom_facts", {})
                combined = ""
                if n_str:
                    combined += f"Notes:\n{n_str}\n"
                if c_facts:
                    facts_str = "\n".join([f"- {v}" for v in c_facts.values()])
                    combined += f"Memory Facts:\n{facts_str}\n"
                if not combined.strip():
                    return "You have no saved notes yet."
                context += f"[USER NOTES]:\n{combined}\nACTION: Read these notes aloud naturally."
        except Exception:
            return "Laptop server unreachable, cannot read notes."

    # --- CLEAR NOTES ---
    if any(w in text_lower for w in ["clear my notes", "delete my notes", "forget my notes", "clear notes", "delete notes"]):
        try:
            resp = req_session.delete(f"http://{LAPTOP_IP}:{LAPTOP_PORT}/clear_notes", timeout=3, headers={"X-Nexus-Token": NEXUS_TOKEN})
            if resp.status_code == 200:
                return "Your notes have been cleared."
            return "Failed to clear notes."
        except Exception:
            return "Laptop server unreachable."

    # --- REMINDERS ---
    if "remind me" in text_lower or "set a reminder" in text_lower or "set alarm" in text_lower or "set reminder" in text_lower:
        mins = 5
        match = re.search(r'(\d+)\s*(?:minute|min|hour|hr)', text_lower)
        if match:
            val = int(match.group(1))
            if "hour" in text_lower or "hr" in text_lower:
                mins = val * 60
            else:
                mins = val
        # Extract the reminder message
        msg = original_text
        for strip in ["remind me to", "remind me in", "remind me", "set a reminder to", "set a reminder for", "set a reminder", "set reminder to", "set reminder", "set alarm for", "set alarm"]:
            msg = re.sub(re.escape(strip), '', msg, flags=re.IGNORECASE).strip()
        msg = re.sub(r'\d+\s*(?:minutes?|mins?|hours?|hrs?)', '', msg, flags=re.IGNORECASE).strip()
        msg = re.sub(r'^(?:in|after|for)\s+', '', msg, flags=re.IGNORECASE).strip()
        msg = re.sub(r'\s+(?:in|after|for)\s*$', '', msg, flags=re.IGNORECASE).strip()
        if not msg:
            msg = "General reminder"
        
        success, trigger_at = set_reminder(mins, msg)
        if success:
            unit = "minute" if mins == 1 else "minutes"
            return f"Reminder set for {mins} {unit} ({trigger_at}): {msg}"
        return "Failed to set reminder. Laptop unreachable."

    # --- TIME / DATE ---
    if any(w in text_lower for w in ["what time is it", "what is the date", "what is the time", "what day is it", "what time", "what date", "what day", "what is today", "current time", "tell me time", "tell me the time", "time please", "what's the time", "whats the time", "tell me date", "tell me the date"]):
        time_str = ""
        try:
            resp = p_laptop("laptop_time")
            if resp and "time" in resp:
                time_str = f"{resp['time']}, {resp['day']}, {resp['date']}"
        except Exception:
            pass
        if not time_str:
            try:
                ist = pytz.timezone("Asia/Kolkata")
                now = datetime.datetime.now(ist)
                time_str = now.strftime('%I:%M %p, %A, %d %B %Y IST')
            except Exception:
                now = datetime.datetime.now()
                time_str = now.strftime('%I:%M %p, %A, %d %B %Y')
        context += f"[LIVE SYSTEM TIME]: {time_str}\n"

    # --- GOOD MORNING / DAILY BRIEFING ---
    if "good morning" in text_lower or "daily briefing" in text_lower or "morning briefing" in text_lower:
        # Inject current time so AI doesn't guess
        _gm_time = ""
        try:
            resp = p_laptop("laptop_time")
            if resp and "time" in resp:
                _gm_time = f"{resp['time']}, {resp['day']}, {resp['date']}"
        except Exception:
            pass
        if not _gm_time:
            try:
                ist = pytz.timezone("Asia/Kolkata")
                now = datetime.datetime.now(ist)
                _gm_time = now.strftime('%I:%M %p, %A, %d %B %Y IST')
            except Exception:
                _gm_time = datetime.datetime.now().strftime('%I:%M %p, %A, %d %B %Y')
        context += f"[LIVE SYSTEM TIME]: {_gm_time}\n"

        context += get_live_weather(user_profile.get("city", DEFAULT_CITY)) + "\n"
        news = get_news_headlines()
        if news:
            context += news + "\n"
        else:
            context += "[NEWS HEADLINES]: No headlines available right now.\n"
        try:
            rem_resp = req_session.get(f"http://{LAPTOP_IP}:{LAPTOP_PORT}/reminders", timeout=3)
            if rem_resp.status_code == 200:
                rems = rem_resp.json().get("reminders", [])
                pending = [r for r in rems if not r.get("triggered")]
                if pending:
                    context += f"[PENDING REMINDERS]: {len(pending)} pending.\n"
                    for r in pending[:3]:
                        context += f"  - {r.get('message', '')} at {r.get('trigger_at_human', '?')}\n"
                else:
                    context += "[PENDING REMINDERS]: No pending reminders.\n"
            else:
                context += "[PENDING REMINDERS]: Could not fetch reminders.\n"
        except Exception:
            context += "[PENDING REMINDERS]: Could not fetch reminders.\n"
        context += "ACTION: The user said Good morning. Greet using the EXACT time from [LIVE SYSTEM TIME]. Summarize weather, news headlines, and reminders using ONLY the data above. Do NOT invent any information."

    # --- GOOD EVENING / GOOD NIGHT ---
    if "good evening" in text_lower:
        context += get_live_weather(user_profile.get("city", DEFAULT_CITY)) + "\n"
        context += "ACTION: Greet the user for the evening."
    
    # --- SLEEP / GOODNIGHT ---
    _sleep_commands = ["sleep", "going to bed", "goodnight", "good night", "play sleep music", "sleep mode", "bedtime", "bedtime music"]
    if text_lower in _sleep_commands or "going to bed" in text_lower:
        result = p_laptop("spotify/play", payload={"query": "calm sleep music ambient"})
        if result.get("success"):
            return f"Goodnight. Playing calm sleep music on Spotify."
        # Fallback: yt-dlp — play on laptop via VLC
        yt_result = p_laptop("music/ytdlp", payload={"query": "calm sleep music ambient"}, timeout=90)
        if yt_result.get("success"):
            return "Goodnight. Playing calm sleep music on laptop."
        return "Goodnight. Couldn't find sleep music, but rest well."

    # --- NAME PERSISTENCE (improved regex) ---
    name_match = re.search(r'(?:my name is|change my name to|call me)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)\s*$', text_clean, re.IGNORECASE)
    if name_match:
        new_name = name_match.group(1).strip().title()
        # Guard against false matches
        false_names = ["later", "back", "when", "please", "sir", "that", "this", "it", "maybe", "tomorrow", "now", "here"]
        if new_name.lower() not in false_names:
            user_profile["name"] = new_name
            inject_system_prompt()
            save_persistence()
            context += f"ACTION: User just set their name to {new_name}. Acknowledge this."

    # --- CITY PERSISTENCE (improved regex) ---
    city_match = re.search(r'(?:i\s+live\s+in|my\s+city\s+is|change\s+city\s+to|i\s+am\s+from|moved\s+to)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)\s*$', text_clean, re.IGNORECASE)
    if city_match:
        new_city = city_match.group(1).strip().title()
        false_cities = ["a", "the", "my", "i", "to", "is", "here", "there", "that", "this", "small", "big"]
        if new_city.lower() not in false_cities and len(new_city) > 1:
            user_profile["city"] = new_city
            inject_system_prompt()
            save_persistence()
            context += f"ACTION: User moved to / lives in {new_city}. Acknowledge."

    # --- CALCULATOR ---
    if any(w in text_lower for w in ["calculate", "plus", "minus", "divide", "multiplied by", "times"]):
        result = safe_calculate(text_lower.replace("calculate", "").strip())
        if result is not None:
            context += f"[CALCULATION RESULT]: {result}\n"

    # --- SYSTEM STATUS ---
    if "system status" in text_lower or "health check" in text_lower or "pi status" in text_lower:
        context += get_pi_health() + "\n"

    if any(w in text_lower for w in ["laptop status", "laptop stats", "cpu usage", "ram usage", "battery status", "battery level", "laptop health"]):
        stats = get_laptop_stats()
        if stats:
            context += stats + "\n"

    # --- WEATHER ---
    if any(w in text_lower for w in ["weather", "temperature", "rain"]) and "good morning" not in text_lower:
        city = None
        m1 = re.search(r'(?:weather|temperature)\s+(?:in|of|for)\s+([a-zA-Z\s]+?)(?:\s*[?.!]?\s*$)', text_lower, re.IGNORECASE)
        m2 = re.search(r'([a-zA-Z]+)\s+(?:weather|temperature)', text_lower, re.IGNORECASE)
        ignore_words = ["today", "tomorrow", "my", "current", "the", "a", "is", "right", "how"]
        if m1 and m1.group(1).strip().lower() not in ignore_words:
            city = m1.group(1).strip().title()
        elif m2 and m2.group(1).lower() not in ignore_words:
            city = m2.group(1).capitalize()
        else:
            city = user_profile.get("city", DEFAULT_CITY)
        weather_data = get_live_weather(city)
        context += weather_data + "\n"
        if "down" in weather_data.lower() or "not found" in weather_data.lower():
            return weather_data

    # --- NEWS ---
    if any(w in text_lower for w in ["news", "headlines", "what's happening"]) and "good morning" not in text_lower:
        news = get_news_headlines()
        if news:
            context += news + "\n"
        p_laptop("open_url", {"url": "https://news.google.com"})
        context += "[ACTION]: Opened Google News on laptop.\n"

    # --- SPOTIFY MUSIC ---
    _is_play_cmd = (text_lower.startswith("play ") or "youtube music" in text_lower or "yt music" in text_lower
                    or ("spotify" in text_lower and not text_lower.startswith("open ")))
    
    if _is_play_cmd:
        # Only strip the leading "play " prefix — don't split on "play" inside words like "playlist"
        song_name = re.sub(r'^play\s+', '', text_lower).strip(" .,!")
        for strip_w in ["on spotify", "on youtube music", "on youtube", "on yt music", "in spotify", "music", "song"]:
            song_name = song_name.replace(strip_w, "").strip()
        
        if not song_name:
            return "What would you like me to play?"
        
        # Try Spotify first
        if "youtube" not in text_lower and "yt" not in text_lower:
            ui.show_status(f"Spotify: searching '{song_name}'...")
            result = p_laptop("spotify/play", payload={"query": song_name}, timeout=15)
            if result.get("success"):
                track = result.get("track", song_name)
                artist = result.get("artist", "")
                return f"Now playing: {track} by {artist} on Spotify."
            elif "not authenticated" in str(result.get("error", "")).lower():
                return "Spotify isn't connected yet. Please visit http://<laptop-ip>:5000/spotify/login on your laptop to connect."
            # If Spotify has no active device, try opening the Spotify app first
            if "no active" in str(result.get("error", "")).lower():
                p_laptop("open_app", payload={"app": "spotify"})
                time.sleep(3)
                result = p_laptop("spotify/play", payload={"query": song_name}, timeout=15)
                if result.get("success"):
                    return f"Now playing: {result.get('track', song_name)} by {result.get('artist', '')} on Spotify."
        
        # Fallback: yt-dlp on laptop → download + play via VLC on laptop
        ui.show_status(f"yt-dlp fallback: searching '{song_name}'...")
        yt_result = p_laptop("music/ytdlp", payload={"query": song_name}, timeout=90)
        if yt_result.get("success"):
            yt_title = yt_result.get("title", song_name)
            yt_artist = yt_result.get("artist", "")
            return f"Now playing: {yt_title} by {yt_artist} on laptop."

        # Last resort: open YT Music in browser
        url = f"https://music.youtube.com/search?q={urllib.parse.quote(song_name)}"
        ui.show_status(f"YT Music browser fallback: {url}")
        p_laptop("play_music", payload={"url": url, "platform": "ytmusic"})
        return f"Opening '{song_name}' on YouTube Music."

    # --- SPOTIFY CONTROLS ---
    if text_lower in ["pause", "pause music", "pause song", "pause spotify"]:
        p_laptop("spotify/pause")
        return "Paused."
    if text_lower in ["resume", "resume music", "continue playing", "resume spotify"]:
        p_laptop("spotify/resume")
        return "Resumed."
    if text_lower in ["skip", "next", "next song", "skip song", "next track"]:
        p_laptop("spotify/skip")
        return "Skipped to next track."
    if text_lower in ["previous", "previous song", "go back", "previous track"]:
        p_laptop("spotify/previous")
        return "Playing previous track."
    if "what's playing" in text_lower or "now playing" in text_lower or "current song" in text_lower:
        np_data = g_laptop("spotify/now_playing")
        if np_data.get("playing"):
            return f"Currently playing: {np_data.get('track', '?')} by {np_data.get('artist', '?')}"
        return "Nothing is playing right now."
    
    volume_match = re.search(r'(?:set\s+)?volume\s+(?:to\s+)?(\d+)', text_lower)
    if volume_match:
        vol = int(volume_match.group(1))
        p_laptop("spotify/volume", payload={"volume": vol})
        return f"Volume set to {vol}%."

    # --- OPEN / CLOSE APP ---
    open_match = re.search(r'open\s+(.+?)(?:\s+on\s+laptop|\s+please)?$', text_lower)
    if open_match and not any(w in text_lower for w in ["open url", "open youtube", "open google"]):
        app_name = open_match.group(1).strip()
        # Don't match URLs
        if not app_name.startswith("http") and "." not in app_name:
            result = p_laptop("open_app", payload={"app": app_name})
            if result.get("success"):
                return f"Opened {app_name}."
            return f"Could not open {app_name}: {result.get('error', 'Unknown error')}"

    close_match = re.search(r'close\s+(.+?)(?:\s+on\s+laptop|\s+please)?$', text_lower)
    if close_match:
        app_name = close_match.group(1).strip()
        result = p_laptop("close_app", payload={"app": app_name})
        if result.get("success"):
            return f"Closed {app_name}."
        return f"Could not close {app_name}: {result.get('error', 'Unknown error')}"

    # --- KILL PORT ---
    kill_port_match = re.search(r'kill\s+(?:process\s+on\s+)?port\s+(\d+)', text_lower)
    if kill_port_match:
        port = kill_port_match.group(1)
        result = p_laptop("kill_port", payload={"port": port})
        if result.get("success"):
            return result.get("message", f"Killed process on port {port}.")
        return result.get("error", "Failed to kill process.")

    # --- RUN COMMAND ---
    run_match = re.search(r'(?:run|execute)\s+(?:command\s+)?["\']?(.+?)["\']?\s*$', text_lower)
    if run_match and ("run command" in text_lower or "execute command" in text_lower or "run terminal" in text_lower):
        cmd = run_match.group(1).strip()
        result = p_laptop("run_command", payload={"command": cmd})
        if result.get("success"):
            output = result.get("output", "").strip()
            if output:
                context += f"[COMMAND OUTPUT]:\n{output}\nACTION: Present this command output to the user."
            else:
                return f"Command executed successfully (no output)."
        else:
            return f"Command failed: {result.get('error', 'Unknown')}"

    # --- GIT STATUS ---
    if "git status" in text_lower or "git info" in text_lower or "last commit" in text_lower:
        result = p_laptop("git_status", payload={"path": os.path.expanduser("~")})
        if result.get("success"):
            branch = result.get("branch", "?")
            status = result.get("status", "?")
            commits = result.get("recent_commits", "?")
            context += f"[GIT STATUS]:\nBranch: {branch}\nStatus: {status}\nRecent commits:\n{commits}\n"
        else:
            context += "[GIT STATUS]: Not a git repository or git not available.\n"

    # --- GOOGLE SEARCH / YOUTUBE / URL ---
    _google_searched = False
    if "google" in text_lower and "search" in text_lower:
        query = text_lower.replace("google", "").replace("search", "").replace("for", "").strip()
        if query:
            p_laptop("search_google", {"query": query})
            search_data = web_search(query)
            if search_data:
                context += search_data + "\n"
            context += "[ACTION]: Opened Google search on laptop.\n"
            _google_searched = True

    _is_youtube_cmd = ("play" not in text_lower and "music" not in text_lower and
                        (re.search(r'\byoutube\b', text_lower) or re.search(r'\byt\b', text_lower)))
    if _is_youtube_cmd:
        yt_query = re.sub(r'\byoutube\b', '', text_lower)
        yt_query = re.sub(r'\byt\b', '', yt_query)
        yt_query = yt_query.replace("search", "").replace("videos of", "").strip()
        if yt_query:
            p_laptop("open_youtube", {"query": yt_query})
            return f"Opening YouTube for '{yt_query}'."

    if "open" in text_lower and ("http" in text_lower or "www" in text_lower):
        url_match = re.search(r'(https?://\S+|www\.\S+)', text)
        if url_match:
            url = url_match.group(1)
            if not url.startswith("http"):
                url = "https://" + url
            p_laptop("open_url", {"url": url})
            return f"Opening {url}."

    # --- WEB SEARCH (general triggers) ---
    search_triggers = ["search", "find", "price", "score", "recipe", "who is", "who won", "latest", "how much", "when did", "results", "winner", "champion", "match", "game", "what happened"]
    time_ignores = ["what time", "what is the time", "current time", "time is it", "what date", "what day", "what is today", "good morning", "good evening", "good night"]
    local_ignores = ["who am i", "system status", "my name", "my notes", "my city", "laptop status", "pi status", "health check",
                     "what is your name", "what's your name", "who are you", "who made you", "who created you",
                     "what is 2", "what is 3", "what is 4", "what is 5",  # simple math
                     "tell me a joke", "tell me a fun fact", "tell me about yourself",
                     "explain", "what are the", "how does", "bullet point", "in 3", "in 5"]
    
    if (not _is_play_cmd and
        not _google_searched and
        not any(w in text_lower for w in time_ignores) and
        not any(w in text_lower for w in local_ignores) and
        not any(w in text_lower for w in _sleep_commands) and
        any(w in text_lower for w in search_triggers)):
        
        query = text_lower
        for w in ["search", "find", "who is", "what is", "tell me about", "show me", "google"]:
            query = query.replace(w, "")
        query = query.strip()
        if query:
            search_res = web_search(query)
            if search_res:
                context += search_res + "\n"

    # --- SENTIMENT ---
    sentiment = extract_sentiment(text)
    if sentiment != "neutral":
        context += f"[USER EMOTION]: The user seems {sentiment}.\n"

    # --- BUILD AI PROMPT ---
    # CRITICAL FIX: Save CLEAN user text to history, not the context-injected version
    chat_history.append({"role": "user", "content": original_text})

    # Build the prompt for AI with context attached to the LATEST message only
    if context.strip():
        # Temporarily modify the last message for AI call
        ai_history = chat_history.copy()
        ai_history[-1] = {"role": "user", "content": f"{original_text}\n\nContext:\n{context}"}
    else:
        ai_history = chat_history

    ai_resp = get_ai_response(ai_history)
    
    chat_history.append({"role": "assistant", "content": ai_resp})

    # Cap in-memory history to prevent unbounded growth on Pi Zero (512MB)
    if len(chat_history) > 50:
        # Keep the system prompt (index 0) + last 40 messages
        system_msgs = [m for m in chat_history if m["role"] == "system"]
        non_system = [m for m in chat_history if m["role"] != "system"]
        chat_history = system_msgs + non_system[-40:]

    save_persistence()
    return ai_resp

# ==========================================
# PORCUPINE WAKE WORD LISTENER
# ==========================================
def _process_voice_input(audio_data_16k):
    """Shared helper: resample 16kHz audio to 44.1kHz, run STT, process command."""
    from scipy.signal import resample as scipy_resample
    num_samples = int(len(audio_data_16k) * 44100 / 16000)
    audio_44k = scipy_resample(audio_data_16k, num_samples).astype(np.int16)
    write('input.wav', 44100, audio_44k)

    live = ui.show_thinking()
    try:
        with open("input.wav", "rb") as f:
            transcription = client_groq.audio.transcriptions.create(
                file=(f.name, f.read()), model="whisper-large-v3-turbo",
                language="en", prompt="Regular conversation in English."
            )
        user_text = transcription.text.strip()
        ui.hide_thinking(live)

        if user_text:
            ui.show_user_input(user_text, "voice")
            live = ui.show_thinking()
            ai_resp = process_command(user_text)
            ui.hide_thinking(live)
            ui.show_nexus_response(ai_resp)
            threading.Thread(target=speak, args=(ai_resp,), daemon=True).start()
    except Exception as e:
        ui.hide_thinking(live)
        ui.show_error("Voice STT", str(e))

    for fn in ["input.wav", "temp.mp3"]:
        try:
            if os.path.exists(fn):
                os.remove(fn)
        except Exception:
            pass
    gc.collect()


def wake_word_loop():
    """Continuously listen for 'Hey Nexus' wake word using Porcupine.
    Also handles button-press recording via shared events so only ONE
    audio stream is ever open (fixes Device Unavailable errors)."""
    if not porcupine_handle:
        return

    pa = None
    audio_stream = None
    try:
        pa = pyaudio.PyAudio()
        audio_stream = pa.open(
            rate=porcupine_handle.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=porcupine_handle.frame_length
        )
        ui.show_status(f"Wake word listener active (frame_length={porcupine_handle.frame_length})")

        while not _shutdown_done:
            try:
                pcm = audio_stream.read(porcupine_handle.frame_length, exception_on_overflow=False)
                frame_np = np.frombuffer(pcm, dtype=np.int16)

                # --- BUTTON RECORDING MODE ---
                # If the physical button is held, buffer frames for STT
                if _button_held.is_set():
                    with _button_audio_lock:
                        _button_audio_buf.append(frame_np.copy())
                    # Check if button was released
                    if _button_released.is_set():
                        _button_released.clear()
                        _button_held.clear()
                        # Grab buffered audio and process
                        with _button_audio_lock:
                            if len(_button_audio_buf) > 5:
                                full_audio = np.concatenate(_button_audio_buf)
                                _button_audio_buf.clear()
                                _process_voice_input(full_audio)
                            else:
                                _button_audio_buf.clear()
                    continue  # Skip wake word processing while button is held

                # --- WAKE WORD DETECTION MODE ---
                pcm_unpacked = struct.unpack_from(f"{porcupine_handle.frame_length}h", pcm)
                keyword_index = porcupine_handle.process(pcm_unpacked)

                if keyword_index >= 0:
                    ui.show_wake_word()
                    try:
                        if pygame.mixer.music.get_busy():
                            pygame.mixer.music.stop()
                    except Exception:
                        pass

                    # Record until 2 seconds of silence
                    recording = []
                    silence_frames = 0
                    max_frames = int(porcupine_handle.sample_rate / porcupine_handle.frame_length * 8)
                    silence_threshold = int(porcupine_handle.sample_rate / porcupine_handle.frame_length * 2)

                    for _ in range(max_frames):
                        if _button_held.is_set():
                            break  # Button pressed during wake recording, abort
                        frame = audio_stream.read(porcupine_handle.frame_length, exception_on_overflow=False)
                        frame_data = np.frombuffer(frame, dtype=np.int16)
                        recording.append(frame_data)
                        rms = np.sqrt(np.mean(frame_data.astype(float) ** 2))
                        if rms < 500:
                            silence_frames += 1
                        else:
                            silence_frames = 0
                        if silence_frames >= silence_threshold:
                            break

                    if len(recording) >= 5:
                        full_audio = np.concatenate(recording)
                        _process_voice_input(full_audio)

            except Exception as e:
                if not _shutdown_done:
                    ui.show_error("Wake Word", str(e))
                time.sleep(1)
    except Exception as e:
        ui.show_error("Wake Word Init", str(e))
    finally:
        if audio_stream:
            try:
                audio_stream.close()
            except Exception:
                pass
        if pa:
            try:
                pa.terminate()
            except Exception:
                pass

# ==========================================
# MAIN LOOPS
# ==========================================
def text_chat_loop():
    while True:
        try:
            user_input = ui.prompt_input()
            if user_input.strip() in ['quit', 'exit']:
                force_save_on_exit()
                sys.exit(0)
            if user_input.strip():
                ui.show_user_input(user_input, "text")
                live = ui.show_thinking()
                response = process_command(user_input)
                ui.hide_thinking(live)
                ui.show_nexus_response(response)
        except KeyboardInterrupt:
            force_save_on_exit()
            sys.exit(0)
        except Exception as e:
            ui.show_error("Text Loop", str(e))

def audio_callback(indata, frames, _time, status):
    q.put(indata.copy())

def voice_button_loop():
    """Physical button push-to-talk loop.
    If Porcupine is active (owns the mic), we signal it via events.
    If Porcupine is NOT active, we use sounddevice directly."""
    global internet_available
    _error_cooldown = 0

    while not _shutdown_done:
        try:
            button.wait_for_press()
            if _shutdown_done:
                break

            # Cooldown after repeated errors
            if _error_cooldown > 0:
                time.sleep(min(_error_cooldown, 5))
                _error_cooldown = 0

            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            ui.show_listening()

            if porcupine_handle:
                # --- SHARED MIC MODE: signal Porcupine to buffer ---
                with _button_audio_lock:
                    _button_audio_buf.clear()
                _button_released.clear()
                _button_held.set()  # Tell Porcupine loop to start buffering

                button.wait_for_release()
                ui.hide_listening()
                _button_released.set()  # Tell Porcupine loop to finalize
                # Porcupine loop will call _process_voice_input()
                _error_cooldown = 0
            else:
                # --- STANDALONE MODE: use sounddevice (no Porcupine) ---
                with q.mutex:
                    q.queue.clear()
                try:
                    with sd.InputStream(samplerate=44100, channels=1, callback=audio_callback):
                        button.wait_for_release()
                        ui.hide_listening()
                        live = ui.show_thinking()
                except Exception as e:
                    ui.hide_listening()
                    ui.show_error("Voice Loop", f"Mic unavailable: {e}")
                    _error_cooldown = 3
                    continue

                recording = []
                while not q.empty():
                    recording.append(q.get())
                if len(recording) < 5:
                    ui.hide_thinking(live)
                    continue
                full_audio = np.concatenate(recording, axis=0)
                write('input.wav', 44100, full_audio)

                if not internet_available:
                    ui.hide_thinking(live)
                    ui.show_error("Voice", "Disabled due to lack of internet")
                    time.sleep(2)
                    continue

                with open("input.wav", "rb") as file:
                    transcription = client_groq.audio.transcriptions.create(
                        file=(file.name, file.read()), model="whisper-large-v3-turbo",
                        language="en", prompt="Regular conversation in English."
                    )
                user_text = transcription.text
                ui.hide_thinking(live)
                ui.show_user_input(user_text, "voice")

                if user_text.strip():
                    live = ui.show_thinking()
                    ai_resp = process_command(user_text)
                    ui.hide_thinking(live)
                    ui.show_nexus_response(ai_resp)
                    time.sleep(0.1)
                    threading.Thread(target=speak, args=(ai_resp,), daemon=True).start()

                gc.collect()
                for fn in ["input.wav", "temp.mp3"]:
                    try:
                        if os.path.exists(fn):
                            os.remove(fn)
                    except Exception:
                        pass
        except KeyboardInterrupt:
            force_save_on_exit()
            sys.exit(0)
        except Exception as e:
            if not _shutdown_done:
                ui.show_error("Voice Loop", str(e))
            _error_cooldown = 3  # Prevent tight error loop
            time.sleep(2)

if __name__ == "__main__":
    try:
        load_persistence()
        
        # Start text input thread
        t_text = threading.Thread(target=text_chat_loop, daemon=True)
        t_text.start()
        
        # Start wake word thread (if available)
        if porcupine_handle:
            t_wake = threading.Thread(target=wake_word_loop, daemon=True)
            t_wake.start()
        
        # Main thread: button loop or wait
        if button:
            voice_button_loop()
        else:
            ui.show_status("GPIO button unavailable — wake word + text mode active")
            try:
                while not _shutdown_done:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown_done = True
        # Clean up Porcupine
        if porcupine_handle:
            try:
                porcupine_handle.delete()
            except Exception:
                pass
        force_save_on_exit()

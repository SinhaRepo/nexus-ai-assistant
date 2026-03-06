# NEXUS Laptop Server — Created by Ansh Sinha | © 2026 All Rights Reserved
# Flask REST API: Memory, Spotify, System Control, Browser Automation, Monitoring

import os
import sys
import socket
import json
import time
import datetime
import threading
import subprocess
import traceback
import base64
import hashlib
import secrets
import shutil
import urllib.parse
import webbrowser
from functools import wraps

from flask import Flask, request, jsonify, redirect, session, send_file
import psutil
from dotenv import load_dotenv

load_dotenv()  # Load .env file (Spotify credentials, tokens, etc.)

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

_shutdown = False
_active_driver = None  # Reusable Selenium driver

# --- AUTH CONFIG ---
NEXUS_TOKEN = os.environ.get("NEXUS_TOKEN") or os.environ.get("JARVIS_TOKEN")
if not NEXUS_TOKEN:
    raise SystemExit("FATAL: NEXUS_TOKEN is not set in your .env file. Set it to any secret passphrase and add the same value to your Pi .env. Refusing to start.")

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Nexus-Token", "") or request.headers.get("X-Jarvis-Token", "")
        if token != NEXUS_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# --- FILE PATHS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(BASE_DIR, "laptop_memory.json")
NOTES_FILE = os.path.join(BASE_DIR, "notes.txt")
REMINDERS_FILE = os.path.join(BASE_DIR, "reminders.json")
SPOTIFY_TOKEN_FILE = os.path.join(BASE_DIR, "spotify_token.json")

# --- SPOTIFY CONFIG ---
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:5000/callback")
SPOTIFY_SCOPES = "user-modify-playback-state user-read-playback-state user-read-currently-playing streaming"

# --- SYSTEM MONITORING CONFIG ---
CPU_ALERT_THRESHOLD = int(os.environ.get("CPU_ALERT_THRESHOLD", 80))       # percent
BATTERY_ALERT_THRESHOLD = int(os.environ.get("BATTERY_ALERT_THRESHOLD", 20))  # percent
_alerts_queue = []  # Alerts to push to Pi on next poll
_alerts_lock = threading.Lock()

# ==========================================
# UTILITY: JSON file helpers
# ==========================================
def load_json(filepath, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# Initialize memory and reminders
memory_state = load_json(MEMORY_FILE, {"chat_history": [], "user_profile": {}})
reminders_data = load_json(REMINDERS_FILE, [])

# ==========================================
# SPOTIFY AUTH + API
# ==========================================
spotify_tokens = load_json(SPOTIFY_TOKEN_FILE, {})

def spotify_get_valid_token():
    """Return a valid Spotify access token, refreshing if needed."""
    global spotify_tokens
    if not spotify_tokens.get("access_token"):
        return None
    # Check expiry
    if spotify_tokens.get("expires_at", 0) < time.time():
        # Refresh
        refresh_token = spotify_tokens.get("refresh_token")
        if not refresh_token:
            return None
        try:
            import requests as req
            resp = req.post("https://accounts.spotify.com/api/token", data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": SPOTIFY_CLIENT_ID,
                "client_secret": SPOTIFY_CLIENT_SECRET,
            }, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                spotify_tokens["access_token"] = data["access_token"]
                spotify_tokens["expires_at"] = time.time() + data.get("expires_in", 3600) - 60
                if "refresh_token" in data:
                    spotify_tokens["refresh_token"] = data["refresh_token"]
                save_json(SPOTIFY_TOKEN_FILE, spotify_tokens)
                return spotify_tokens["access_token"]
        except Exception as e:
            print(f"Spotify refresh failed: {e}")
            return None
    return spotify_tokens["access_token"]

def spotify_api(method, endpoint, json_data=None, params=None):
    """Make an authenticated Spotify API call."""
    token = spotify_get_valid_token()
    if not token:
        return {"error": "Spotify not authenticated. Visit http://<laptop-ip>:5000/spotify/login"}
    import requests as req
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"https://api.spotify.com/v1{endpoint}"
    try:
        if method == "GET":
            resp = req.get(url, headers=headers, params=params, timeout=10)
        elif method == "PUT":
            resp = req.put(url, headers=headers, json=json_data, timeout=10)
        elif method == "POST":
            resp = req.post(url, headers=headers, json=json_data, timeout=10)
        else:
            return {"error": f"Unknown method {method}"}
        
        if resp.status_code == 204:
            return {"success": True}
        if resp.status_code in (200, 201):
            # Some endpoints return empty body
            try:
                return resp.json()
            except Exception:
                return {"success": True}
        return {"error": f"Spotify API {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}

# --- Spotify OAuth Endpoints ---

@app.route('/spotify/login')
def spotify_login():
    """Redirect the user to Spotify's authorization page."""
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SPOTIFY_SCOPES,
        "show_dialog": "true"
    }
    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)
    return redirect(auth_url)

@app.route('/callback')
def spotify_callback():
    """Handle Spotify OAuth callback."""
    global spotify_tokens
    code = request.args.get("code")
    error = request.args.get("error")
    if error:
        return jsonify({"error": error}), 400
    if not code:
        return jsonify({"error": "No code received"}), 400
    
    import requests as req
    resp = req.post("https://accounts.spotify.com/api/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET,
    }, timeout=10)
    
    if resp.status_code != 200:
        return jsonify({"error": f"Token exchange failed: {resp.text}"}), 500
    
    data = resp.json()
    spotify_tokens = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_at": time.time() + data.get("expires_in", 3600) - 60,
    }
    save_json(SPOTIFY_TOKEN_FILE, spotify_tokens)
    return "<h1>Spotify connected to NEXUS!</h1><p>You can close this window.</p>"

# --- Spotify Playback Endpoints ---

@app.route('/spotify/play', methods=['POST'])
@require_auth
def spotify_play():
    """Search and play a song on Spotify."""
    try:
        data = request.json
        query = data.get("query", "")
        if not query:
            return jsonify({"error": "No query provided"}), 400
        
        # Search for the track
        search_result = spotify_api("GET", "/search", params={"q": query, "type": "track", "limit": 5})
        if "error" in search_result:
            return jsonify(search_result), 500
        
        tracks = search_result.get("tracks", {}).get("items", [])
        if not tracks:
            return jsonify({"error": f"No tracks found for '{query}'"}), 404
        
        # Prefer an exact title match if available
        query_lower = query.lower().strip()
        track = tracks[0]
        for t in tracks:
            if t["name"].lower() == query_lower:
                track = t
                break
        track_uri = track["uri"]
        track_name = track["name"]
        artist_name = track["artists"][0]["name"] if track["artists"] else "Unknown"
        
        # Start playback
        play_result = spotify_api("PUT", "/me/player/play", json_data={"uris": [track_uri]})
        if "error" in play_result:
            # Try to find an active device first
            devices = spotify_api("GET", "/me/player/devices")
            device_list = devices.get("devices", [])
            if device_list:
                device_id = device_list[0]["id"]
                play_result = spotify_api("PUT", f"/me/player/play?device_id={device_id}", json_data={"uris": [track_uri]})
            if "error" in play_result:
                return jsonify({"error": "No active Spotify device found. Open Spotify on your laptop or phone first.", "details": play_result.get("error")}), 500
        
        return jsonify({
            "success": True,
            "track": track_name,
            "artist": artist_name,
            "message": f"Now playing: {track_name} by {artist_name}"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/spotify/pause', methods=['POST'])
@require_auth
def spotify_pause():
    result = spotify_api("PUT", "/me/player/pause")
    if "error" in result:
        return jsonify(result), 500
    return jsonify({"success": True, "message": "Playback paused"}), 200

@app.route('/spotify/resume', methods=['POST'])
@require_auth
def spotify_resume():
    result = spotify_api("PUT", "/me/player/play")
    if "error" in result:
        return jsonify(result), 500
    return jsonify({"success": True, "message": "Playback resumed"}), 200

@app.route('/spotify/skip', methods=['POST'])
@require_auth
def spotify_skip():
    result = spotify_api("POST", "/me/player/next")
    if "error" in result:
        return jsonify(result), 500
    return jsonify({"success": True, "message": "Skipped to next track"}), 200

@app.route('/spotify/previous', methods=['POST'])
@require_auth
def spotify_previous():
    result = spotify_api("POST", "/me/player/previous")
    if "error" in result:
        return jsonify(result), 500
    return jsonify({"success": True, "message": "Playing previous track"}), 200

@app.route('/spotify/now_playing', methods=['GET'])
def spotify_now_playing():
    result = spotify_api("GET", "/me/player/currently-playing")
    if "error" in result or not result:
        return jsonify({"playing": False}), 200
    item = result.get("item", {})
    return jsonify({
        "playing": result.get("is_playing", False),
        "track": item.get("name", "Unknown"),
        "artist": item.get("artists", [{}])[0].get("name", "Unknown"),
        "progress_ms": result.get("progress_ms", 0),
        "duration_ms": item.get("duration_ms", 0),
    }), 200

@app.route('/spotify/volume', methods=['POST'])
@require_auth
def spotify_volume():
    data = request.json
    vol = data.get("volume", 50)
    vol = max(0, min(100, int(vol)))
    result = spotify_api("PUT", f"/me/player/volume?volume_percent={vol}")
    if "error" in result:
        return jsonify(result), 500
    return jsonify({"success": True, "message": f"Volume set to {vol}%"}), 200

@app.route('/spotify/status', methods=['GET'])
def spotify_status():
    """Check if Spotify is authenticated."""
    token = spotify_get_valid_token()
    return jsonify({"authenticated": token is not None}), 200

# ==========================================
# MEMORY ENDPOINTS
# ==========================================

@app.route('/', methods=['GET'])
def index():
    return jsonify({"service": "NEXUS Laptop Server", "status": "online", "version": "3.0"}), 200

@app.route('/status', methods=['GET'])
def status():
    return jsonify({"status": "online", "memory_connected": True}), 200

@app.route('/laptop_time', methods=['POST'])
@require_auth
def laptop_time():
    now = datetime.datetime.now()
    return jsonify({
        "time": now.strftime("%I:%M %p"),
        "day": now.strftime("%A"),
        "date": now.strftime("%d %B %Y")
    }), 200

@app.route('/memory', methods=['GET'])
def get_memory():
    return jsonify(memory_state), 200

@app.route('/memory', methods=['POST'])
@require_auth
def save_memory():
    global memory_state
    try:
        data = request.json
        if data:
            memory_state = data
            save_json(MEMORY_FILE, memory_state)
            return jsonify({"status": "success"}), 200
        return jsonify({"error": "No data"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/memory/add', methods=['POST'])
@require_auth
def add_memory():
    global memory_state
    try:
        data = request.json
        if data and "item" in data:
            if "user_profile" not in memory_state:
                memory_state["user_profile"] = {}
            if "custom_facts" not in memory_state["user_profile"]:
                memory_state["user_profile"]["custom_facts"] = {}
            fact_key = f"fact_{int(time.time())}"
            memory_state["user_profile"]["custom_facts"][fact_key] = data["item"]
            save_json(MEMORY_FILE, memory_state)
            return jsonify({"status": "success"}), 200
        return jsonify({"error": "Invalid payload"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/memory', methods=['DELETE'])
@require_auth
def clear_memory():
    global memory_state
    memory_state = {"chat_history": [], "user_profile": {}}
    save_json(MEMORY_FILE, memory_state)
    return jsonify({"status": "success", "message": "Memory cleared"}), 200

# ==========================================
# NOTES ENDPOINTS
# ==========================================

@app.route('/take_note', methods=['POST'])
@require_auth
def take_note():
    try:
        data = request.json
        text = data.get('text', '')
        if not text:
            return jsonify({"error": "No text provided"}), 400
        
        # Append to notes file (primary storage)
        with open(NOTES_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} - {text}")
        
        # Also store in memory facts
        if "user_profile" not in memory_state:
            memory_state["user_profile"] = {}
        if "custom_facts" not in memory_state["user_profile"]:
            memory_state["user_profile"]["custom_facts"] = {}
        fact_key = f"note_{int(time.time())}"
        memory_state["user_profile"]["custom_facts"][fact_key] = text
        save_json(MEMORY_FILE, memory_state)
        
        return jsonify({"status": "success", "message": f"Note saved: {text[:50]}..."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/clear_notes', methods=['DELETE'])
@require_auth
def clear_notes():
    global memory_state
    try:
        if os.path.exists(NOTES_FILE):
            os.remove(NOTES_FILE)
        if "user_profile" in memory_state and "custom_facts" in memory_state["user_profile"]:
            memory_state["user_profile"]["custom_facts"] = {}
            save_json(MEMORY_FILE, memory_state)
        return jsonify({"status": "success", "message": "Notes cleared"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/read_notes', methods=['GET'])
def read_notes():
    notes_file_content = ""
    try:
        if os.path.exists(NOTES_FILE):
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                notes_file_content = f.read()
    except Exception:
        pass
    custom_facts = memory_state.get("user_profile", {}).get("custom_facts", {})
    user_name = memory_state.get("user_profile", {}).get("name", "")
    user_city = memory_state.get("user_profile", {}).get("city", "")
    return jsonify({
        "notes_file": notes_file_content,
        "custom_facts": custom_facts,
        "name": user_name,
        "city": user_city
    }), 200

# ==========================================
# REMINDERS ENDPOINTS
# ==========================================

@app.route('/reminders', methods=['GET'])
def get_reminders():
    """Get all pending reminders."""
    return jsonify({"reminders": reminders_data}), 200

@app.route('/reminders', methods=['POST'])
@require_auth
def add_reminder():
    """Add a new reminder. Stored persistently."""
    global reminders_data
    try:
        data = request.json
        message = data.get("message", "")
        minutes = data.get("minutes", 5)
        if not message:
            return jsonify({"error": "No message"}), 400
        
        trigger_time = time.time() + (minutes * 60)
        reminder = {
            "message": message,
            "trigger_at": trigger_time,
            "trigger_at_human": datetime.datetime.fromtimestamp(trigger_time).strftime("%I:%M %p"),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "triggered": False
        }
        reminders_data.append(reminder)
        save_json(REMINDERS_FILE, reminders_data)
        return jsonify({"status": "success", "trigger_at": reminder["trigger_at_human"]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/reminders/check', methods=['GET'])
def check_reminders():
    """Check for due reminders. Called by Pi periodically."""
    global reminders_data
    now = time.time()
    due = []
    updated = False
    for r in reminders_data:
        if not r.get("triggered") and r.get("trigger_at", 0) <= now:
            r["triggered"] = True
            due.append(r["message"])
            updated = True
    if updated:
        save_json(REMINDERS_FILE, reminders_data)
    return jsonify({"due_reminders": due}), 200

@app.route('/reminders', methods=['DELETE'])
@require_auth
def clear_reminders():
    global reminders_data
    reminders_data = []
    save_json(REMINDERS_FILE, reminders_data)
    return jsonify({"status": "success"}), 200

# ==========================================
# SYSTEM CONTROL ENDPOINTS
# ==========================================

# Whitelisted apps for safety
ALLOWED_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
    "explorer": "explorer.exe",
    "terminal": "wt.exe",
    "powershell": "powershell.exe",
    "cmd": "cmd.exe",
    "code": "code",
    "vscode": "code",
    "spotify": os.path.join(os.environ.get("APPDATA", ""), "Spotify", "Spotify.exe"),
    "task manager": "taskmgr.exe",
    "paint": "mspaint.exe",
    "snipping tool": "SnippingTool.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    # Additional common apps
    "discord": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Discord", "Update.exe --processStart Discord.exe"),
    "vlc": r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    "steam": r"C:\Program Files (x86)\Steam\steam.exe",
    "whatsapp": "explorer.exe shell:AppsFolder\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App",
    "telegram": os.path.join(os.environ.get("APPDATA", ""), "Telegram Desktop", "Telegram.exe"),
    "obs": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
    "brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "settings": "ms-settings:",
    "photos": "explorer.exe shell:AppsFolder\\Microsoft.Windows.Photos_8wekyb3d8bbwe!App",
}

@app.route('/open_app', methods=['POST'])
@require_auth
def open_app():
    """Open an application by name."""
    try:
        data = request.json
        app_name = data.get("app", "").lower().strip()
        if not app_name:
            return jsonify({"error": "No app specified"}), 400
        
        exe = ALLOWED_APPS.get(app_name)
        if not exe:
            return jsonify({"error": f"App '{app_name}' is not in the allowed list. Allowed apps: {', '.join(sorted(ALLOWED_APPS.keys()))}"}), 400
        
        # Handle URI schemes (ms-settings:, etc.)
        if exe.startswith("ms-") or exe.startswith("http") or exe.startswith("explorer.exe shell:"):
            subprocess.Popen(f'start "" "{exe}"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif " " in exe and ("--" in exe or "/" in exe):
            # Commands with arguments (e.g., Discord's Update.exe --processStart Discord.exe)
            subprocess.Popen(exe, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(exe, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({"success": True, "message": f"Opened {app_name}"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/close_app', methods=['POST'])
@require_auth
def close_app():
    """Close an application by process name."""
    try:
        data = request.json
        app_name = data.get("app", "").lower().strip()
        if not app_name:
            return jsonify({"error": "No app specified"}), 400
        
        # Map friendly names to process names
        process_map = {
            "chrome": "chrome.exe", "firefox": "firefox.exe", "notepad": "notepad.exe",
            "calculator": "CalculatorApp.exe", "spotify": "Spotify.exe", "code": "Code.exe",
            "vscode": "Code.exe", "word": "WINWORD.EXE", "excel": "EXCEL.EXE",
            "powerpoint": "POWERPNT.EXE", "explorer": "explorer.exe",
            "task manager": "Taskmgr.exe", "paint": "mspaint.exe",
        }
        proc_name = process_map.get(app_name, f"{app_name}.exe")
        
        result = subprocess.run(
            ["taskkill", "/F", "/IM", proc_name, "/T"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return jsonify({"success": True, "message": f"Closed {app_name}"}), 200
        return jsonify({"error": f"Could not close {app_name}: {result.stderr.strip()}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/kill_port', methods=['POST'])
@require_auth
def kill_port():
    """Kill process running on a specific port."""
    try:
        data = request.json
        port = data.get("port")
        if not port:
            return jsonify({"error": "No port specified"}), 400
        port = int(port)
        
        # Self-protect: never kill the NEXUS server itself
        if port == 5000:
            return jsonify({"error": "Cannot kill port 5000 — that's the NEXUS server itself!"}), 403
        
        # Find PID
        result = subprocess.run(
            f'netstat -ano | findstr :{port}',
            capture_output=True, text=True, shell=True, timeout=5
        )
        lines = result.stdout.strip().split('\n')
        killed = set()
        for line in lines:
            parts = line.split()
            if len(parts) >= 5:
                pid = parts[-1]
                if pid.isdigit() and pid not in killed:
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5)
                    killed.add(pid)
        
        if killed:
            return jsonify({"success": True, "message": f"Killed PIDs {', '.join(killed)} on port {port}"}), 200
        return jsonify({"error": f"No process found on port {port}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/system_stats', methods=['GET'])
def system_stats():
    """Get laptop CPU, RAM, battery, disk stats."""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        stats = {
            "cpu_percent": cpu_percent,
            "ram_total_gb": round(mem.total / (1024**3), 1),
            "ram_used_gb": round(mem.used / (1024**3), 1),
            "ram_percent": mem.percent,
            "disk_total_gb": round(disk.total / (1024**3), 1),
            "disk_used_gb": round(disk.used / (1024**3), 1),
            "disk_percent": disk.percent,
        }
        
        battery = psutil.sensors_battery()
        if battery:
            stats["battery_percent"] = battery.percent
            stats["battery_plugged"] = battery.power_plugged
            stats["battery_time_left"] = str(datetime.timedelta(seconds=battery.secsleft)) if battery.secsleft > 0 else "Charging"
        else:
            stats["battery_percent"] = None
        
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/run_command', methods=['POST'])
@require_auth
def run_command():
    """Run a whitelisted terminal command."""
    try:
        data = request.json
        command = data.get("command", "").strip()
        if not command:
            return jsonify({"error": "No command"}), 400
        
        # Whitelist of safe command prefixes
        ALLOWED_PREFIXES = [
            "git status", "git log", "git diff", "git branch", "git pull",
            "docker ps", "docker images", "docker stats",
            "systeminfo", "hostname", "whoami", "ipconfig",
            "ping", "netstat", "tasklist",
            "dir", "type", "echo",
            "python --version", "node --version", "npm --version",
            "pip list", "pip show",
            "Get-Process", "Get-Service",
        ]
        
        allowed = False
        for prefix in ALLOWED_PREFIXES:
            if command.lower().startswith(prefix.lower()):
                allowed = True
                break
        
        if not allowed:
            return jsonify({"error": f"Command not allowed. Allowed prefixes: {', '.join(ALLOWED_PREFIXES[:10])}..."}), 403
        
        result = subprocess.run(
            command, capture_output=True, text=True, shell=True, timeout=30, cwd=os.path.expanduser("~")
        )
        output = result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout
        return jsonify({
            "success": True,
            "output": output,
            "error_output": result.stderr[-500:] if result.stderr else "",
            "return_code": result.returncode
        }), 200
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Command timed out (30s limit)"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/git_status', methods=['POST'])
@require_auth
def git_status():
    """Get git status for a repo path."""
    try:
        data = request.json
        repo_path = data.get("path", os.path.expanduser("~"))
        
        # Git status
        status_result = subprocess.run(
            ["git", "status", "--short"], capture_output=True, text=True, cwd=repo_path, timeout=10
        )
        # Last 5 commits
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-5"], capture_output=True, text=True, cwd=repo_path, timeout=10
        )
        # Current branch
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"], capture_output=True, text=True, cwd=repo_path, timeout=10
        )
        
        return jsonify({
            "success": True,
            "branch": branch_result.stdout.strip(),
            "status": status_result.stdout.strip() or "Clean (no changes)",
            "recent_commits": log_result.stdout.strip(),
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# ALERTS / MONITORING
# ==========================================

@app.route('/alerts', methods=['GET'])
def get_alerts():
    """Pi polls this to get system alerts."""
    with _alerts_lock:
        alerts = list(_alerts_queue)
        _alerts_queue.clear()
    return jsonify({"alerts": alerts}), 200

def _monitoring_thread():
    """Background thread monitoring CPU, battery, internet."""
    global _alerts_queue
    last_cpu_alert = 0
    last_battery_alert = 0
    last_internet_alert = 0
    
    while not _shutdown:
        try:
            # CPU check
            cpu = psutil.cpu_percent(interval=2)
            if cpu > CPU_ALERT_THRESHOLD and time.time() - last_cpu_alert > 300:
                with _alerts_lock:
                    _alerts_queue.append({"type": "cpu_high", "message": f"Laptop CPU at {cpu}%!", "value": cpu})
                last_cpu_alert = time.time()
            
            # Battery check
            battery = psutil.sensors_battery()
            if battery and not battery.power_plugged and battery.percent < BATTERY_ALERT_THRESHOLD:
                if time.time() - last_battery_alert > 600:
                    with _alerts_lock:
                        _alerts_queue.append({"type": "battery_low", "message": f"Laptop battery at {battery.percent}%!", "value": battery.percent})
                    last_battery_alert = time.time()
            
            # Internet check
            try:
                socket.create_connection(("8.8.8.8", 53), timeout=3)
            except OSError:
                if time.time() - last_internet_alert > 120:
                    with _alerts_lock:
                        _alerts_queue.append({"type": "internet_down", "message": "Internet connection is down!"})
                    last_internet_alert = time.time()
            
        except Exception:
            pass
        
        time.sleep(10)

# ==========================================
# BROWSER AUTOMATION (Selenium) — kept for Google Search & URL opening
# ==========================================

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def open_url_selenium_flow(url):
    """Open a URL in Chrome via Selenium or native fallback."""
    global _active_driver
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        
        chrome_options = Options()
        user_data_dir = r"C:\tmp\chrome_nexus"
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        
        # Try to reuse existing driver
        if _active_driver is not None:
            try:
                _ = _active_driver.title
                driver = _active_driver
                handles = driver.window_handles
                while len(handles) > 5:
                    driver.switch_to.window(handles[0])
                    driver.close()
                    handles = driver.window_handles
                driver.switch_to.window(handles[-1])
                driver.switch_to.new_window('tab')
                driver.get(url)
                return True, "URL opened via reused driver"
            except Exception:
                _active_driver = None
        
        if not is_port_in_use(9222):
            subprocess.run(["taskkill", "/F", "/IM", "chrome.exe", "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)
            if os.path.exists(chrome_path):
                subprocess.Popen([
                    chrome_path, "--remote-debugging-port=9222",
                    f"--user-data-dir={user_data_dir}",
                    "--no-first-run", "--no-default-browser-check"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            for _ in range(20):
                if is_port_in_use(9222):
                    break
                time.sleep(0.5)
        
        if is_port_in_use(9222):
            chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
            driver = webdriver.Chrome(options=chrome_options)
            _active_driver = driver
            driver.switch_to.new_window('tab')
            driver.get(url)
            return True, "URL opened via Selenium"
        else:
            webbrowser.open(url)
            return True, "URL opened natively"
    except Exception as e:
        try:
            webbrowser.open(url)
            return True, "URL opened natively (fallback)"
        except Exception:
            return False, str(e)

@app.route('/search_google', methods=['POST'])
@require_auth
def search_google():
    try:
        data = request.json
        query = data.get('query')
        if not query:
            return jsonify({"error": "Missing query"}), 400
        url = f"https://google.com/search?q={urllib.parse.quote(query)}"
        threading.Thread(target=open_url_selenium_flow, args=(url,), daemon=True).start()
        return jsonify({"success": True, "message": "Opening Google search"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/open_url', methods=['POST'])
@require_auth
def open_url():
    try:
        data = request.json
        url = data.get('url')
        if not url:
            return jsonify({"error": "Missing url"}), 400
        threading.Thread(target=open_url_selenium_flow, args=(url,), daemon=True).start()
        return jsonify({"success": True, "message": "Opening URL"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/open_youtube', methods=['POST'])
@require_auth
def open_youtube():
    try:
        data = request.json
        query = data.get('query')
        if not query:
            return jsonify({"error": "Missing query"}), 400
        url = f"https://youtube.com/results?search_query={urllib.parse.quote(query)}"
        threading.Thread(target=open_url_selenium_flow, args=(url,), daemon=True).start()
        return jsonify({"success": True, "message": "Opening YouTube"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ==========================================
# YT MUSIC (Selenium fallback — kept for non-Spotify music)
# ==========================================
@app.route('/play_music', methods=['POST'])
@require_auth
def play_music():
    """Play music via Selenium URL open. Used as fallback when Spotify isn't available."""
    try:
        data = request.json
        url = data.get('url')
        platform = data.get('platform', 'ytmusic')
        if not url:
            return jsonify({"error": "Missing url"}), 400
        threading.Thread(target=open_url_selenium_flow, args=(url,), daemon=True).start()
        return jsonify({"success": True, "message": f"Opening {platform} in browser"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ==========================================
# YT-DLP MUSIC (download + play on laptop via VLC)
# ==========================================
MUSIC_CACHE_DIR = os.path.join(BASE_DIR, "music_cache")
os.makedirs(MUSIC_CACHE_DIR, exist_ok=True)

# Resolve yt-dlp path — it may not be on the default system PATH
_YTDLP_PATH = shutil.which("yt-dlp")
if not _YTDLP_PATH:
    # Common install locations on Windows
    _candidates = [
        os.path.join(os.environ.get("APPDATA", ""), "Python", "Python313", "Scripts", "yt-dlp.exe"),
        os.path.join(os.environ.get("APPDATA", ""), "Python", "Python314", "Scripts", "yt-dlp.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python313", "Scripts", "yt-dlp.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python314", "Scripts", "yt-dlp.exe"),
        os.path.join(sys.prefix, "Scripts", "yt-dlp.exe"),
    ]
    for c in _candidates:
        if os.path.isfile(c):
            _YTDLP_PATH = c
            break
if _YTDLP_PATH:
    print(f"  [OK] yt-dlp found: {_YTDLP_PATH}")
else:
    print("  [WARN] yt-dlp not found on PATH or common locations")

# Resolve ffmpeg path — yt-dlp needs it for audio conversion
_FFMPEG_DIR = None
_ffmpeg_path = shutil.which("ffmpeg")
if _ffmpeg_path:
    _FFMPEG_DIR = os.path.dirname(_ffmpeg_path)
else:
    # Scan common WinGet / Chocolatey / manual install locations
    _ff_candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages"),
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
        os.path.join(os.environ.get("USERPROFILE", ""), "ffmpeg", "bin"),
    ]
    for base in _ff_candidates:
        if os.path.isdir(base):
            # WinGet nests inside a version folder
            for root, dirs, files in os.walk(base):
                if "ffmpeg.exe" in files:
                    _FFMPEG_DIR = root
                    break
            if _FFMPEG_DIR:
                break
if _FFMPEG_DIR:
    print(f"  [OK] ffmpeg found: {_FFMPEG_DIR}")
else:
    print("  [WARN] ffmpeg not found — yt-dlp audio conversion may fail")

@app.route('/music/ytdlp', methods=['POST'])
@require_auth
def music_ytdlp():
    """Search YouTube via yt-dlp, download audio as MP3, return stream URL."""
    if not _YTDLP_PATH:
        return jsonify({"error": "yt-dlp not found on this system. Install: pip install yt-dlp"}), 500
    try:
        data = request.json
        query = data.get("query", "").strip()
        if not query:
            return jsonify({"error": "No query provided"}), 400

        # Clean up old cached files (>10 min old)
        for f in os.listdir(MUSIC_CACHE_DIR):
            fp = os.path.join(MUSIC_CACHE_DIR, f)
            if os.path.isfile(fp) and time.time() - os.path.getmtime(fp) > 600:
                try:
                    os.remove(fp)
                except Exception:
                    pass

        # Output file path
        output_template = os.path.join(MUSIC_CACHE_DIR, "nexus_music.%(ext)s")
        final_mp3 = os.path.join(MUSIC_CACHE_DIR, "nexus_music.mp3")

        # Remove previous file
        for ext in ["mp3", "webm", "m4a", "opus", "wav", "ogg"]:
            old = os.path.join(MUSIC_CACHE_DIR, f"nexus_music.{ext}")
            if os.path.exists(old):
                try:
                    os.remove(old)
                except Exception:
                    pass

        # Build ffmpeg location args if available
        _ff_args = ["--ffmpeg-location", _FFMPEG_DIR] if _FFMPEG_DIR else []

        # Step 1: Get metadata
        meta_cmd = [
            _YTDLP_PATH, f"ytsearch1:{query}",
            "--print", "%(title)s",
            "--print", "%(uploader)s",
            "--no-download", "--no-warnings", "--no-playlist"
        ] + _ff_args
        meta_result = subprocess.run(meta_cmd, capture_output=True, text=True, timeout=20)
        meta_lines = meta_result.stdout.strip().split("\n")
        title = meta_lines[0] if meta_lines else query
        artist = meta_lines[1] if len(meta_lines) > 1 else "Unknown"

        # Step 2: Download + convert to MP3
        dl_cmd = [
            _YTDLP_PATH, f"ytsearch1:{query}",
            "-x", "--audio-format", "mp3",
            "--audio-quality", "5",
            "-o", output_template,
            "--no-playlist", "--no-warnings", "--quiet"
        ] + _ff_args
        dl_result = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=120)

        if os.path.exists(final_mp3):
            # Play locally on laptop via VLC (or default player)
            vlc_path = ALLOWED_APPS.get("vlc", "")
            try:
                if vlc_path and os.path.isfile(vlc_path):
                    subprocess.Popen([vlc_path, "--play-and-exit", final_mp3],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    # Fallback: open with default system player
                    os.startfile(final_mp3)
            except Exception as play_err:
                print(f"  [WARN] Could not auto-play: {play_err}")
            return jsonify({
                "success": True,
                "title": title,
                "artist": artist,
                "message": f"Playing on laptop: {title} by {artist}"
            }), 200
        else:
            return jsonify({
                "error": "yt-dlp download failed",
                "stderr": dl_result.stderr[:500] if dl_result.stderr else "No output file produced"
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({"error": "yt-dlp timed out (120s)"}), 500
    except FileNotFoundError:
        return jsonify({"error": "yt-dlp not installed. Run: pip install yt-dlp"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# MAIN
# ==========================================
if __name__ == '__main__':
    _port = int(os.environ.get("LAPTOP_PORT", 5000))
    print("=" * 60)
    print(f"Starting NEXUS Laptop Server on port {_port}...")
    print("=" * 60)
    print()
    print(f"  STEP 1: Open http://127.0.0.1:{_port}/spotify/login in your browser")
    print("          to connect Spotify (one-time setup).")
    print()
    print("  Available Endpoints:")
    print("    GET  /                    Server info")
    print("    GET  /status              Health check")
    print("    POST /laptop_time         System time [AUTH]")
    print()
    print("    --- Memory ---")
    print("    GET  /memory              Fetch memory")
    print("    POST /memory              Save memory [AUTH]")
    print("    POST /memory/add          Add fact [AUTH]")
    print("    DELETE /memory            Clear memory [AUTH]")
    print()
    print("    --- Notes ---")
    print("    POST /take_note           Save note [AUTH]")
    print("    GET  /read_notes          Read notes")
    print("    DELETE /clear_notes       Clear notes [AUTH]")
    print()
    print("    --- Reminders ---")
    print("    GET  /reminders           List reminders")
    print("    POST /reminders           Add reminder [AUTH]")
    print("    GET  /reminders/check     Check due reminders")
    print("    DELETE /reminders         Clear reminders [AUTH]")
    print()
    print("    --- Spotify ---")
    print("    GET  /spotify/login       OAuth login")
    print("    GET  /callback            OAuth callback")
    print("    POST /spotify/play        Play track [AUTH]")
    print("    POST /spotify/pause       Pause [AUTH]")
    print("    POST /spotify/resume      Resume [AUTH]")
    print("    POST /spotify/skip        Skip track [AUTH]")
    print("    POST /spotify/previous    Previous track [AUTH]")
    print("    GET  /spotify/now_playing  Current track")
    print("    POST /spotify/volume      Set volume [AUTH]")
    print("    GET  /spotify/status      Auth status")
    print()
    print("    --- System Control ---")
    print("    POST /open_app            Open app [AUTH]")
    print("    POST /close_app           Close app [AUTH]")
    print("    POST /kill_port           Kill by port [AUTH]")
    print("    GET  /system_stats        CPU/RAM/Battery")
    print("    POST /run_command         Run command [AUTH]")
    print("    POST /git_status          Git info [AUTH]")
    print("    GET  /alerts              Pending alerts")
    print()
    print("    --- Browser ---")
    print("    POST /search_google       Google search [AUTH]")
    print("    POST /open_url            Open URL [AUTH]")
    print("    POST /open_youtube        YouTube search [AUTH]")
    print("    POST /play_music          Play via browser [AUTH]")
    print()
    print("    --- Music (yt-dlp) ---")
    print("    POST /music/ytdlp         Download & play via VLC [AUTH]")
    print("=" * 60)

    # Start monitoring thread
    monitor_t = threading.Thread(target=_monitoring_thread, daemon=True)
    monitor_t.start()

    import signal
    def _handle_shutdown(sig, frame):
        global _shutdown
        _shutdown = True
        print("\nNEXUS Laptop Server terminated cleanly.")
        os._exit(0)

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    app.run(host='0.0.0.0', port=int(os.environ.get("LAPTOP_PORT", 5000)), threaded=True)

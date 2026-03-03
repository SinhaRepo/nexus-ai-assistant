# ════════════════════════════════════════════════════════════════
#  NEXUS — Neural Executive Unified System
#  Terminal UI Module — Rich library sci-fi aesthetic
#
#  Copyright © 2026 Ansh Sinha. All rights reserved.
#  This source code is the intellectual property of Ansh Sinha.
#  Unauthorized copying, modification, or distribution is
#  strictly prohibited.
#
#  GitHub  : https://github.com/SinhaRepo
#  LinkedIn: https://www.linkedin.com/in/sinhaansh
# ════════════════════════════════════════════════════════════════

import threading
import datetime
import zoneinfo
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich.live import Live
from rich.spinner import Spinner
from rich import box

# Thread-safe console instance
console = Console(force_terminal=True, highlight=False)

# ============================================================
# FUNCTION 1 — print_header()
# ============================================================
def print_header():
    """Startup banner. Called once before boot sequence."""
    line1 = Text("NEXUS  ::  NEURAL INTERFACE ONLINE", style="bold cyan")
    line1.align("center", console.width)
    line2 = Text(
        "NODE: RASPBERRY PI  |  ARCH: ARMv6  |  PYTHON 3.11  |  SESSION ACTIVE",
        style="dim cyan",
    )
    line2.align("center", console.width)

    credits = Text(justify="center")
    credits.append("© 2026 Ansh Sinha", style="bold white")
    credits.append("  |  ", style="dim")
    credits.append("github.com/SinhaRepo", style="underline #00afff")
    credits.append("  |  ", style="dim")
    credits.append("linkedin.com/in/sinhaansh", style="underline #00afff")
    credits.align("center", console.width)

    content = Text()
    content.append_text(line1)
    content.append("\n")
    content.append_text(line2)
    content.append("\n")
    content.append_text(credits)

    panel = Panel(
        content,
        box=box.SQUARE,
        border_style="cyan",
        expand=True,
    )
    console.print()
    console.print(panel)
    console.print(
        Rule("SUBSYSTEM INITIALIZATION SEQUENCE", style="dim cyan")
    )


# ============================================================
# FUNCTION 2 — boot_step()
# ============================================================
_STATUS_BADGE = {
    "ok":      ("[  OK  ]", "bold green"),
    "warn":    ("[ WARN ]", "bold yellow"),
    "fail":    ("[ FAIL ]", "bold red"),
    "pending": ("[ .... ]", "dim"),
}

_LABEL_STYLE = {
    "ok":   "#00ff41",
    "warn": "yellow",
    "fail": "red",
}


def boot_step(index, total, label, detail, status, sub_details=None):
    badge_text, badge_style = _STATUS_BADGE.get(status, _STATUS_BADGE["pending"])
    label_style = _LABEL_STYLE.get(status, "white")

    line = Text()
    line.append(f" {badge_text:<8}", style=badge_style)
    line.append(f" [{index}/{total}]".ljust(7), style="dim white")
    line.append(f" {label:<22}", style=label_style)
    line.append(f" {detail}", style="dim cyan")

    console.print(line)

    if sub_details:
        for sd in sub_details:
            console.print(f"          {sd}", style="dim")


def boot_done():
    """Separator after all boot steps finish."""
    console.print(Rule(style="dim cyan"))


# ============================================================
# FUNCTION 3 — print_ready()
# ============================================================
def print_ready(name):
    """Post-boot ready block with greeting."""
    console.print(Rule("READY", style="dim cyan"))
    console.print(
        '  >> SAY "HEY NEXUS" OR HOLD BUTTON OR TYPE BELOW',
        style="bold cyan",
    )
    console.print()

    greeting = f"Welcome back, {name}!" if name and name != "Boss" else "System online, Boss!"
    show_nexus_response(greeting)
    return greeting


# ============================================================
# FUNCTION 4 — show_user_input()
# ============================================================
def show_user_input(text, mode="text"):
    """Display user input line. mode is 'text' or 'voice'."""
    prefix = "[ TEXT ]" if mode == "text" else "[ VOICE ]"
    line = Text()
    line.append(f" {prefix} >> ", style="bold magenta")
    line.append(text, style="white")
    console.print()
    console.print(line)


# ============================================================
# FUNCTION 5 — show_nexus_response()
# ============================================================
def show_nexus_response(text):
    """NEXUS response inside a square-bordered cyan panel."""
    try:
        now = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata")).strftime("%H:%M:%S")
    except Exception:
        now = datetime.datetime.now().strftime("%H:%M:%S")
    panel = Panel(
        Text(text, style="white"),
        box=box.SQUARE,
        border_style="cyan",
        title="[ NEXUS ]",
        title_align="left",
        subtitle=now,
        subtitle_align="right",
        expand=True,
    )
    console.print(panel)
    console.print(Rule(style="dim"))


# ============================================================
# FUNCTION 6 — show_thinking() / hide_thinking()
# ============================================================
def show_thinking():
    spinner_text = Text()
    spinner_text.append(" PROCESSING  ::  AWAITING AI RESPONSE", style="yellow")
    spinner = Spinner("line", text=spinner_text, style="yellow")
    live = Live(spinner, console=console, refresh_per_second=8, transient=True)
    live.start()
    return live


def hide_thinking(live):
    if live is not None:
        try:
            live.stop()
        except Exception:
            pass


# ============================================================
# FUNCTION 7 — show_listening() / hide_listening()
# ============================================================
_listening_stop_event = threading.Event()
_listening_live = None


def show_listening():
    global _listening_live, _listening_stop_event
    _listening_stop_event.clear()

    rec_on = Text()
    rec_on.append(" [ REC ]  ::  LISTENING  --  RELEASE BUTTON TO PROCESS", style="bold red")
    rec_off = Text()
    rec_off.append(" [     ]  ::  LISTENING  --  RELEASE BUTTON TO PROCESS", style="bold red")

    _listening_live = Live(rec_on, console=console, refresh_per_second=4, transient=True)
    _listening_live.start()

    def _blink():
        toggle = True
        while not _listening_stop_event.is_set():
            _listening_stop_event.wait(0.5)
            toggle = not toggle
            try:
                if _listening_live is not None:
                    _listening_live.update(rec_on if toggle else rec_off)
            except Exception:
                break

    t = threading.Thread(target=_blink, daemon=True)
    t.start()


def hide_listening():
    global _listening_live
    _listening_stop_event.set()
    if _listening_live is not None:
        try:
            _listening_live.stop()
        except Exception:
            pass
        _listening_live = None


# ============================================================
# FUNCTION 8 — show_wake_word()
# ============================================================
def show_wake_word():
    """Indicator that wake word was detected."""
    line = Text()
    line.append(" [ WAKE ] ", style="bold green")
    line.append('"Hey Nexus" detected — listening...', style="green")
    console.print()
    console.print(line)


# ============================================================
# FUNCTION 9 — show_speaking()
# ============================================================
_ENGINE_LABELS = {
    "elevenlabs": "ElevenLabs",
    "deepgram":   "Deepgram Aura",
    "edge":       "Edge-TTS",
    "pyttsx3":    "pyttsx3",
}


def show_speaking(engine):
    label = _ENGINE_LABELS.get(engine, engine)
    console.print(f"  [~] Speaking  ::  {label}", style="dim")


# ============================================================
# FUNCTION 10 — show_status()
# ============================================================
def show_status(text):
    console.print(f"  [*] {text}", style="#005555")


# ============================================================
# FUNCTION 11 — show_reminder()
# ============================================================
def show_reminder(message):
    console.print("\a", end="")
    panel = Panel(
        Text(message, style="white", justify="center"),
        box=box.SQUARE,
        border_style="bold red",
        title="[ ! REMINDER ALERT ! ]",
        title_align="center",
        expand=True,
    )
    console.print(panel)


# ============================================================
# FUNCTION 12 — show_alert()
# ============================================================
def show_alert(title, message):
    """Yellow-bordered alert panel for system notifications (CPU/battery/internet)."""
    panel = Panel(
        Text(message, style="white", justify="center"),
        box=box.SQUARE,
        border_style="bold yellow",
        title=f"[ {title} ]",
        title_align="center",
        expand=True,
    )
    console.print(panel)


# ============================================================
# FUNCTION 13 — show_error()
# ============================================================
def show_error(context, message):
    line = Text()
    line.append(" [ FAIL ] ", style="dim red")
    line.append(f"{context}  ::  {message}", style="dim red")
    console.print(line)


# ============================================================
# FUNCTION 14 — show_shutdown()
# ============================================================
def show_shutdown(success=True):
    panel = Panel(
        Text("SHUTTING DOWN  ::  FORCING MEMORY SYNC TO LAPTOP", style="yellow", justify="center"),
        box=box.SQUARE,
        border_style="yellow",
        expand=True,
    )
    console.print()
    console.print(panel)

    if success:
        line = Text()
        line.append(" [  OK  ] ", style="bold green")
        line.append("Memory saved.", style="green")
        console.print(line)
    else:
        line = Text()
        line.append(" [ FAIL ] ", style="bold red")
        line.append("Memory sync failed.", style="red")
        console.print(line)

    console.print()
    copyright_line = Text("© 2026 Ansh Sinha — All rights reserved", style="dim cyan")
    copyright_line.align("center", console.width)
    console.print(copyright_line)
    console.print(Rule("SESSION TERMINATED", style="dim"))


# ============================================================
# UTILITY — prompt_input()
# ============================================================
def prompt_input():
    try:
        return console.input("[bold cyan]  >> [/bold cyan]")
    except (EOFError, KeyboardInterrupt):
        raise KeyboardInterrupt

# Security Policy

## Overview

NEXUS is a personal home assistant that runs on a Raspberry Pi and communicates with a Windows laptop over your local Wi-Fi network. Because it can open applications, run terminal commands, and control Spotify on your laptop, security is taken seriously.

This document explains the security model, what is and isn't in scope, and how to responsibly report a vulnerability.

---

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest (`main` branch) | ✅ Yes |
| Older commits | ❌ No — always use the latest version |

---

## Security Architecture

### What protects your laptop

| Layer | How It Works |
|-------|-------------|
| **Token authentication** | Every mutating request from the Pi to the laptop requires the `X-Nexus-Token` header. The token is set by you in `.env` — never hardcoded in source code. NEXUS refuses to start if the token is not set. |
| **App whitelist** | Only applications explicitly listed in `ALLOWED_APPS` in `laptop_server.py` can be launched. Requests for unlisted apps are rejected with HTTP 400 — there is no shell fallback. |
| **Command whitelist** | Terminal commands are restricted to a hardcoded list of safe prefixes (`git status`, `pip list`, `ipconfig`, etc.). Arbitrary shell commands are rejected with HTTP 403. |
| **Safe calculator** | Math expressions are evaluated using Python's `ast` module — no `eval()`, no `exec()`, no code injection possible. Only arithmetic operators are permitted. |
| **No secrets in source** | All API keys, tokens, and credentials are loaded from `.env` via `python-dotenv`. The `.env` file is in `.gitignore` and is never committed. |
| **Session security** | The Flask session secret key is a 32-byte random hex string generated fresh on every server start. |

### Known intentional limitations

- **HTTP only, not HTTPS.** Communication between the Pi and laptop is over plain HTTP on your LAN. This is an intentional tradeoff for simplicity on a home network. As a result, **NEXUS is designed for use on a trusted private network only** — never expose port 5000 to the internet via port forwarding or tunneling services.
- **Flask binds to `0.0.0.0`.** The laptop server listens on all interfaces, meaning any device on your home Wi-Fi can reach it. The token authentication protects sensitive endpoints, but unauthenticated read endpoints (`/status`, `/system_stats`) are visible to all LAN devices.

---

## Responsible Use

To keep your setup secure:

1. **Set a strong `NEXUS_TOKEN`** — use a long, random passphrase. Not `password`, not `123456`.
2. **Never expose port 5000 to the internet** — no port forwarding in your router, no ngrok tunnels.
3. **Only run on trusted Wi-Fi** — do not run the laptop server on public or shared networks.
4. **Keep your `.env` files private** — never commit them, never share them.
5. **Regularly update dependencies** — run `pip install -r requirements-laptop.txt --upgrade` periodically.

---

## Reporting a Vulnerability

If you discover a security vulnerability in NEXUS, please **do not open a public GitHub Issue**. Public disclosure before a fix is available puts all users at risk.

### How to report

**Email:** Report privately via [LinkedIn message](https://www.linkedin.com/in/sinhaansh) — request an email address to send the full details securely.

### What to include

- A clear description of the vulnerability
- Steps to reproduce it
- What an attacker could achieve by exploiting it
- Which file and approximate line number is affected
- Whether you have a suggested fix

### What to expect

- **Acknowledgement** within 48 hours
- **Assessment** (confirmed / not a vulnerability / out of scope) within 7 days
- **Fix** for confirmed vulnerabilities as soon as reasonably possible
- **Credit** in the changelog if you'd like it

---

## Out of Scope

The following are known, intentional design decisions and are **not** considered vulnerabilities:

- HTTP instead of HTTPS on the LAN
- Flask listening on `0.0.0.0`
- Unauthenticated read-only endpoints (`/status`, `/system_stats`, `/reminders/check`, `/alerts`)
- The laptop server having no rate limiting (it's a personal tool on a LAN)

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03 | Removed shell fallback in `open_app()` — unknown apps now return HTTP 400 instead of attempting `shell=True` launch |
| 2026-03 | `NEXUS_TOKEN` now raises a hard startup error if not set — no default token fallback |
| 2026-03 | All configurable values moved to `.env` — no secrets or personal defaults in source code |

---

*NEXUS — Built by [Ansh Sinha](https://www.linkedin.com/in/sinhaansh)*

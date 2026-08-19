"""Standalone watchdog: alerts via Telegram if the MusicShazamBot Windows
service stops running. Runs as its own scheduled task (see
install_watchdog_task.ps1), independent of the service it watches — a
watchdog baked into the bot process itself can't warn you about the bot
process being gone (which is exactly what happened once already: the
service was removed from Windows entirely with no trace in the event log).

stdlib only, on purpose — importing bot.py would drag in aiogram/shazamio/
yt-dlp and run its own startup side effects just to send one HTTP request.
"""
import json
import os
import subprocess
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(SCRIPT_DIR, ".env")
STATE_FILE = os.path.join(SCRIPT_DIR, "watchdog_state.json")
SERVICE_NAME = "MusicShazamBot"


def _load_env() -> dict[str, str]:
    env = {}
    with open(ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def _service_status() -> str:
    # PowerShell's Get-Service, not `sc query` — a service removed entirely
    # (not just stopped) comes back as an unambiguous empty/None instead of
    # having to parse sc's text output for a "does not exist" error.
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Get-Service -Name {SERVICE_NAME} -ErrorAction SilentlyContinue).Status"],
        capture_output=True, text=True, timeout=15,
    )
    status = out.stdout.strip()
    return status if status else "NotInstalled"


def _decide(is_up: bool, last_status: str) -> str | None:
    """Pure state-transition check, kept separate from I/O so it's testable.
    Returns "recovered", "down", or None (no change worth reporting)."""
    if is_up and last_status == "down":
        return "recovered"
    if not is_up and last_status == "ok":
        return "down"
    return None


def _send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15) as resp:
        resp.read()


def main() -> None:
    env = _load_env()
    token = env.get("BOT_TOKEN")
    chat_ids = [c.strip() for c in env.get("ALLOWED_USER_IDS", "").split(",") if c.strip()]
    if not token or not chat_ids:
        return  # nothing configured to alert to — can't do the job silently anyway

    status = _service_status()
    is_up = status == "Running"

    last_status = "ok"
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            last_status = json.load(f).get("status", "ok")

    action = _decide(is_up, last_status)
    if action == "recovered":
        text = "🟢 MusicShazamBot service is back up."
    elif action == "down":
        text = f"🔴 MusicShazamBot service is not running (status: {status})."
    if action:
        for chat_id in chat_ids:
            _send_telegram(token, chat_id, text)

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"status": "ok" if is_up else "down"}, f)


if __name__ == "__main__":
    main()

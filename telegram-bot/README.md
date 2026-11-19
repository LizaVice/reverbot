# Telegram bot

Send a voice note, audio file, video, track name, or link. The bot uses [ShazamIO](https://github.com/dotX12/ShazamIO) to recognize clips and can retry recognition at corrected speeds for slowed or sped-up edits. YouTube and TikTok downloads use `yt-dlp`. Spotify and Apple Music links supply metadata for a YouTube search.

- **Remix:** Combine compatible effects, with one reverb preset at a time, and set playback speed from **0.50× to 1.50×**.
- **Receive:** Get the finished MP3 or choose delivery as a voice note. Cover art and lyrics appear when available.
- **Revisit:** Use `/history` to choose a recent track again, `/start` for help, and `/terms` for usage terms.

The bot's reverb uses separate dry, early-reflection, and late-reflection paths in FFmpeg. The late reflections are low-pass filtered, and the result is mastered using two-pass loudness normalization.

## Setup on Windows

Install Python 3.12, FFmpeg with `ffprobe`, and Deno. From the repository directory, install the Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

Configure the following environment variables. For the Windows service installer, place them in a local `.env` file next to `bot.py`. For a manual run, set them in the shell before running `python bot.py`.

| Variable | Value |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token from [BotFather](https://t.me/BotFather). |
| `ALLOWED_USER_IDS` | Comma-separated numeric Telegram user IDs. Set this before starting the bot. An empty list allows anyone who finds the bot to use it. |
| `FFMPEG_DIR` | Directory containing `ffmpeg.exe` and `ffprobe.exe`. |
| `DENO_DIR` | Directory containing `deno.exe`. |

This bot version also expects a local Netscape-format `cookies.txt` beside `bot.py` for YouTube requests. Keep the cookie file and `.env` out of Git.

## Service and watchdog

- [`install_service.ps1`](../install_service.ps1) installs or updates the Windows service using [NSSM](https://nssm.cc/). [`setup_service_account.ps1`](../setup_service_account.ps1) can set up a dedicated local service account.
- [`install_watchdog_task.ps1`](../install_watchdog_task.ps1) registers a scheduled task that runs every 15 minutes. [`watchdog.py`](../watchdog.py) sends a Telegram alert when the service stops or recovers. The default scheduled task runs while the installing user is signed in.
- [`restart.sh`](../restart.sh) stops the current bot process so the service supervisor can restart it.

## Repository guide

| Path | Purpose |
| --- | --- |
| [`bot.py`](../bot.py) | Telegram handlers, track recognition, audio downloads, and effect processing. |
| [`requirements.txt`](../requirements.txt) | Python dependencies for the bot. |
| [`test_bot_logic.py`](../test_bot_logic.py) and [`test_watchdog.py`](../test_watchdog.py) | Checks for bot logic and watchdog alerts. |
| [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | Checks Python syntax and runs both test files on pull requests and pushes to `main`. |

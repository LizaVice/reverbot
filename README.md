# Reverbot

Reverbot identifies music and turns it into a custom audio export. Use the **Telegram bot** to recognize clips and receive audio in chat, or **Shazam Desktop** to process tracks and local media on Windows.

| | Telegram bot | Shazam Desktop for Windows |
| --- | --- | --- |
| Input | Voice notes, audio, video, track names, and supported links | Local audio and video, track names, and supported links |
| Effects | Nightcore, Bass Boosted, 8D Audio, and light, medium, or heavy reverb | The same effect types, plus St Paul’s Atmospheric Hall |
| Output | MP3 or Telegram voice note | MP3 with optional custom cover art and volume boost |
| Get started | [Run the Telegram bot](#telegram-bot) | [Download ShazamDesktop.exe](https://github.com/LizaVice/reverbot/releases/download/desktop-2026.11.19/ShazamDesktop.exe) |

## Shazam Desktop

[Download the Windows build](https://github.com/LizaVice/reverbot/releases/download/desktop-2026.11.19/ShazamDesktop.exe) · [Read the release notes](https://github.com/LizaVice/reverbot/releases/tag/desktop-2026.11.19)

### What it can do

- **Identify music and select a source.** Open a local audio or video file, search by track name, or paste a supported link. A selected local file is used directly for processing without a YouTube download. Track recognition and online lyrics lookup can still use the network.
- **Work with links.** YouTube and TikTok links can be opened directly. Spotify and Apple Music links provide track metadata for a matching search on YouTube.
- **Combine effects.** Choose Nightcore, Bass Boosted, 8D Audio, or **St Paul’s Atmospheric Hall**, which uses recorded impulse responses. Add one of three reverb presets per export. Use **Original** when you want no effects.
- **Adjust the export.** Set speed from **0.50× to 1.50×** in **0.01×** steps, choose **192 or 320 kbps**, apply up to **+12 dB** of volume boost with peak limiting, and optionally embed a **JPG or PNG** cover.
- **Read lyrics.** The app can use lyrics returned with recognition or look for a match in **LRCLIB** by title and artist. The Lyrics button (**Текст песни**) becomes available when lyrics are found. Lyrics lookup runs independently of the audio download.
- **Reuse tracks.** Open recent tracks from history. The app caches downloaded audio and saves finished files in the `output` folder next to the executable.

### Run on Windows

1. Install [FFmpeg](https://ffmpeg.org/download.html) (including `ffprobe`) and [Deno](https://deno.com/), and add both tools to your Windows PATH.
2. Download `ShazamDesktop.exe` and put it in a folder you can write to.
3. Launch the EXE, choose a track or a local file, select your effects and export settings, then click **Собрать** to export.

If YouTube temporarily blocks a download or asks for sign-in, you can still process a local file. The Windows executable is distributed through [GitHub Releases](https://github.com/LizaVice/reverbot/releases). This repository contains the Telegram bot source and deployment scripts.

## Telegram bot

Send a voice note, audio file, video, track name, or link. The bot uses [ShazamIO](https://github.com/dotX12/ShazamIO) to recognize clips and can retry recognition at corrected speeds for slowed or sped-up edits. YouTube and TikTok downloads use `yt-dlp`. Spotify and Apple Music links supply metadata for a YouTube search.

- **Remix:** Combine compatible effects, with one reverb preset at a time, and set playback speed from **0.50× to 1.50×**.
- **Receive:** Get the finished MP3 or choose delivery as a voice note. Cover art and lyrics appear when available.
- **Revisit:** Use `/history` to choose a recent track again, `/start` for help, and `/terms` for usage terms.

The bot's reverb uses separate dry, early-reflection, and late-reflection paths in FFmpeg. The late reflections are low-pass filtered, and the result is mastered using two-pass loudness normalization.

### Setup on Windows

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

### Service and watchdog

- [`install_service.ps1`](./install_service.ps1) installs or updates the Windows service using [NSSM](https://nssm.cc/). [`setup_service_account.ps1`](./setup_service_account.ps1) can set up a dedicated local service account.
- [`install_watchdog_task.ps1`](./install_watchdog_task.ps1) registers a scheduled task that runs every 15 minutes. [`watchdog.py`](./watchdog.py) sends a Telegram alert when the service stops or recovers. The default scheduled task runs while the installing user is signed in.
- [`restart.sh`](./restart.sh) stops the current bot process so the service supervisor can restart it.

## Repository guide

| Path | Purpose |
| --- | --- |
| [`bot.py`](./bot.py) | Telegram handlers, track recognition, audio downloads, and effect processing. |
| [`requirements.txt`](./requirements.txt) | Python dependencies for the bot. |
| [`test_bot_logic.py`](./test_bot_logic.py) and [`test_watchdog.py`](./test_watchdog.py) | Checks for bot logic and watchdog alerts. |
| [`.github/workflows/ci.yml`](./.github/workflows/ci.yml) | Checks Python syntax and runs both test files on pull requests and pushes to `main`. |

## Disclaimer

Reverbot is a personal project and is not affiliated with the services it uses. See [DISCLAIMER.md](./DISCLAIMER.md).

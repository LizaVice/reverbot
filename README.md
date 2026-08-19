# 🎧 music_shazam_bot

![Python](https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0?logo=telegram&logoColor=white)
![ffmpeg](https://img.shields.io/badge/audio-ffmpeg-007808?logo=ffmpeg&logoColor=white)
![platform](https://img.shields.io/badge/runs%20as-Windows%20service-0078D6?logo=windows&logoColor=white)
![status](https://img.shields.io/badge/status-personal%20project-lightgrey)

A personal Telegram bot that turns "what song is this?" into a mastered,
effect-laden mp3 in one chat. Send it a voice note, an audio/video clip, a
song name, or a YouTube/TikTok/Spotify/Apple Music link — it identifies the
track via Shazam, downloads it, and lets you remix it before sending it back.

## 💬 What it looks like in chat

```
you:  [forwards a 10-second video with music in the background]

bot:  🔎 Listening...
bot:  🎵 Found: Tame Impala — The Less I Know The Better
      [cover art]
      Pick effect(s) — combinable:
      ☐ Nightcore   ☐ Bass Boosted   ☐ 8D Audio
      ☐ Reverb: Light  ☐ Reverb: Medium  ☐ Reverb: Heavy
      [ Lyrics ]  [ ▶ Go ]

you:  [checks Nightcore + Reverb: Light, taps Go]

bot:  Speed?  [0.5x] [0.75x] [1.0x] [1.25x] [1.5x]  [🎯 fine-tune]

you:  [taps 1.25x]

bot:  🎛 Mastering...
bot:  [sends back the finished mp3, or as a voice note if you asked for one]
```

`/history` re-lists your last requests with one tap to re-deliver any of
them in a different effect/speed combo without re-searching.

## ✨ Features

| Area | Details |
|---|---|
| 🔍 Recognition | [`shazamio`](https://github.com/dotX12/ShazamIO), with speed-corrected retries so "slowed"/"sped up" trend edits don't throw off Shazam's fingerprint match |
| ⬇️ Download | `yt-dlp` — YouTube & TikTok natively; Spotify/Apple Music via page-title metadata scraping, then a YouTube search |
| 🎚 Effects | Nightcore, Bass Boosted, 8D Audio, plus three reverb presets (Light/Medium/Heavy) — all combinable with each other |
| ⏩ Speed | 0.5x–1.5x, adjustable down to 0.01x precision, or type an exact number |
| 🎧 Delivery | Mastered mp3, or as a Telegram voice note |
| 🖼 Extras | Cover art thumbnail, on-demand lyrics, `/history` with one-tap re-delivery |
| 🪟 Deployment | Runs as a Windows service via [NSSM](https://nssm.cc/), auto-restarts on crash |
| 🐶 Watchdog | Separate scheduled task pings the service every 15 min and Telegrams you if it stops — see `watchdog.py` |

### About that reverb

The reverb isn't a single `aecho` call. An earlier version was, and it had
two audible problems, both confirmed by measuring impulse responses and
spectrograms rather than guessing: `aecho`'s gain settings scale the *entire*
output (dry signal included — measured at **-46% dry attenuation** on the
Medium preset before any echo was even mixed in), and it has no per-tap
filtering, so cymbals and vocal sibilance ring on unchanged through the whole
tail instead of darkening like a real room would.

`master_reverb()` in `bot.py` now builds a proper dry/wet `ffmpeg`
`filter_complex` graph instead: the signal is split three ways, the dry copy
passes through at unity gain, an early-reflections branch gets a few taps,
and a late-reflections branch gets a longer tap chain **plus a low-pass
filter** so the tail darkens the way a real space does. Two-pass `loudnorm`
mastering (measured, then linear-normalized) runs afterward, tuned per
effect.

## 🛠 Setup

```bash
pip install -r requirements.txt
```

Create a `.env` next to `bot.py`:

```dotenv
BOT_TOKEN=<your Telegram bot token>
ALLOWED_USER_IDS=<your numeric Telegram user id>
FFMPEG_DIR=<folder containing ffmpeg.exe and ffprobe.exe>
DENO_DIR=<folder containing deno.exe>
```

| Variable | Required? | Notes |
|---|---|---|
| `BOT_TOKEN` | ✅ | from [@BotFather](https://t.me/BotFather) |
| `ALLOWED_USER_IDS` | Strongly recommended | without it, the bot answers *any* Telegram user who finds it — see the comment above `BOT_TOKEN` in `bot.py`. Get your own id from [@userinfobot](https://t.me/userinfobot) |
| `FFMPEG_DIR` / `DENO_DIR` | ✅ | the bot won't start without them — read from the environment rather than hardcoded because winget installs per-user, and this typically runs as a Windows service under an account that isn't the one that ran winget (see the comment above them in `bot.py`) |

You'll also need a `cookies.txt` (Netscape format, exported from a logged-in
YouTube session — needed to dodge YouTube's bot checks). None of `.env`,
`cookies.txt`, or anything else secret is committed.

Run directly:

```bash
python bot.py
```

Or install as a Windows service — see `install_service.ps1` (uses NSSM;
optionally pair with `setup_service_account.ps1` to run it under a
dedicated low-privilege local account instead of your own).

Optionally, register the watchdog so you get a Telegram message if the
service ever stops (this is what caught nothing, before — it went down
silently once with no trace anywhere):

```
.\install_watchdog_task.ps1
```

No elevation needed — it's a per-user Scheduled Task, not another Windows
service. Runs only while you're logged in; if you need it to run logged-out
too, that needs a saved password on the task (`schtasks /change ... /RP`).

## 📁 Project layout

```
bot.py                      the whole bot (single file, by design — see below)
install_service.ps1         Windows service install/update (NSSM)
setup_service_account.ps1   optional: creates a dedicated low-privilege
                             service account instead of running as you
restart.sh                  kills the running instance so the service
                             supervisor relaunches it with fresh code
watchdog.py                 checks the service every run, Telegrams you on
                             a down/recovered transition (stdlib only)
install_watchdog_task.ps1   registers watchdog.py as a 15-min Scheduled Task
test_watchdog.py            self-check for watchdog.py's alert logic
```

## ⚖️ Disclaimer

Personal, non-commercial tool — not affiliated with Shazam, Spotify, Apple
Music, YouTube, or TikTok. See [`DISCLAIMER.md`](./DISCLAIMER.md) for what
it actually does and who's responsible for how it's used.

## 💡 Ideas for extending this

- Split `bot.py` into modules (recognition / download / mastering /
  handlers) once it grows past comfortable single-file size
- Tests around the pure logic (`_looks_like_match`, `_bucket`,
  `_parse_spotify_title` / `_parse_apple_music_title`) — no network or
  ffmpeg needed, cheap to cover
- A GitHub Actions workflow that at least runs `python -m py_compile bot.py`
  and any added tests on push
- Karaoke/instrumental (naive center-channel cancellation), custom clip
  trimming by timestamp, combining multiple effects with independently
  chosen speeds in one request

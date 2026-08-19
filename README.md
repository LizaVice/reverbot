# music_shazam_bot

A personal Telegram bot: send a voice note / audio / video clip (or a song
name, or a YouTube/TikTok/Spotify/Apple Music link) and it identifies the
track via Shazam, downloads it, and lets you pick one or more audio effects
(nightcore, bass boosted, 8D audio, three reverb presets — combinable) plus
an exact playback speed (0.5x–1.5x, adjustable down to 0.01x precision)
before sending back a mastered mp3 or voice note.

## Features

- Track recognition via [shazamio](https://github.com/dotX12/ShazamIO),
  with speed-corrected retries for "slowed"/"sped up" trend edits that shift
  Shazam's fingerprint match
- Download via `yt-dlp` (YouTube, TikTok natively; Spotify/Apple Music via
  page-title metadata scraping, then a YouTube search)
- Effects: Nightcore, Bass Boosted, 8D Audio, and three reverb presets built
  as a true dry/wet `ffmpeg` filter_complex graph (not a single `aecho` —
  see the comments above `REVERB_PRESETS` in `bot.py` for why), combinable
  with each other
- Two-pass `loudnorm` mastering (EQ/compression tuned per effect, then
  measured + linear loudness normalization)
- Cover art thumbnails, on-demand lyrics, `/history` with one-tap re-delivery
- Runs as a Windows service via [NSSM](https://nssm.cc/)

## Setup

```
pip install -r requirements.txt
```

Create a `.env` next to `bot.py`:

```
BOT_TOKEN=<your Telegram bot token>
ALLOWED_USER_IDS=<your numeric Telegram user id>
FFMPEG_DIR=<folder containing ffmpeg.exe and ffprobe.exe>
DENO_DIR=<folder containing deno.exe>
```

`ALLOWED_USER_IDS` is optional but strongly recommended — without it the bot
answers any Telegram user who finds it (see the comment above `BOT_TOKEN` in
`bot.py`). Get your own numeric id by messaging
[@userinfobot](https://t.me/userinfobot).

`FFMPEG_DIR`/`DENO_DIR` are required — the bot won't start without them (see
the comment above them in `bot.py` for why they're read from the environment
instead of a hardcoded path: winget installs per-user, and this typically
runs as a Windows service under an account that isn't the one that ran
winget). You'll also need a `cookies.txt` (Netscape format, exported from a
logged-in YouTube session — needed to avoid YouTube's bot checks). None of
these are committed.

Run directly:

```
python bot.py
```

Or install as a Windows service — see `install_service.ps1` (uses NSSM;
optionally pair with `setup_service_account.ps1` to run it under a
dedicated low-privilege local account instead of your own).

## Project layout

- `bot.py` — the whole bot (single file by design — see below)
- `install_service.ps1`, `setup_service_account.ps1` — Windows service
  deployment (the latter is optional, for running under a dedicated
  low-privilege account instead of your own)
- `restart.sh` — kills the running instance so the service supervisor
  relaunches it with fresh code

## Ideas for extending this

- Split `bot.py` into modules (recognition / download / mastering / handlers)
  once it grows past comfortable single-file size
- Tests around the pure logic (`_looks_like_match`, `_bucket`,
  `_parse_spotify_title`/`_parse_apple_music_title`) — these don't need
  network or ffmpeg and are cheap to cover
- A GitHub Actions workflow that at least runs `python -m py_compile bot.py`
  and any added tests on push
- Karaoke/instrumental (naive center-channel cancellation), custom clip
  trimming by timestamp, combining multiple effects with independently
  chosen speeds in one request

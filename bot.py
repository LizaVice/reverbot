import asyncio
import html
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
    URLInputFile,
    User,
)
from shazamio import Shazam
from yt_dlp import YoutubeDL

# Windows picks the console codepage (cp1251 here) for redirected
# stdout/stderr, not UTF-8 — track titles and this repo's own Cyrillic path
# were coming out as mangled bytes in the log. Force UTF-8 before logging is set up.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

BOT_TOKEN = os.environ["BOT_TOKEN"]

# TODO(personal single-user bot): this bot has no auth of its own besides
# BOT_TOKEN secrecy. To restrict it to just you: find your numeric Telegram
# user_id (easiest way — message @userinfobot on Telegram, it replies with
# your id), then set it via ALLOWED_USER_IDS=<your_id> (comma-separated if
# more than one) either as a real environment variable, or as a line in the
# local .env file next to this script (same file install_service.ps1 reads
# BOT_TOKEN from). Until you do, the bot answers ANY Telegram user who finds
# it — that's logged as a warning below on every startup so it isn't silently
# forgotten, but it does NOT block startup or stop the bot from working.
def _parse_allowed_user_ids() -> set[int]:
    raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            logging.warning("ALLOWED_USER_IDS: skipping non-numeric entry %r", part)
    return ids


ALLOWED_USER_IDS = _parse_allowed_user_ids()
if not ALLOWED_USER_IDS:
    logging.warning(
        "ALLOWED_USER_IDS is not set - this bot will respond to ANY Telegram "
        "user who messages it. See the TODO above BOT_TOKEN in bot.py to lock "
        "it down to your own account."
    )

# self-register the real Windows PID so restart.sh can find and kill this
# process without grepping `ps aux` (whose PIDs don't match Windows' own).
with open(os.path.join(os.path.dirname(__file__), "bot.pid"), "w") as _f:
    _f.write(str(os.getpid()))

# winget installs per-user, and this runs as a Windows service
# (frequently under LocalSystem or a dedicated service account, NOT
# necessarily the account that ran winget) - os.environ["LOCALAPPDATA"] at
# runtime points at whichever account is running the process, which is not
# reliably the one with these packages installed. Read from .env instead of
# hardcoding a path tied to one specific Windows account.
FFMPEG_DIR = os.environ.get("FFMPEG_DIR", "")
DENO_DIR = os.environ.get("DENO_DIR", "")
if not FFMPEG_DIR or not DENO_DIR:
    raise SystemExit("FFMPEG_DIR and DENO_DIR must be set in .env - see README for what they should point to.")
FFMPEG_BIN = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
FFPROBE_BIN = os.path.join(FFMPEG_DIR, "ffprobe.exe")
for _dir in (FFMPEG_DIR, DENO_DIR):
    if _dir not in os.environ["PATH"]:
        os.environ["PATH"] += os.pathsep + _dir

# --cookies-from-browser chrome hits an open yt-dlp bug (DPAPI
# decrypt fails against Chrome's newer cookie encryption). Firefox cookies
# aren't OS-encrypted, so exported once to a static file instead (doesn't
# depend on Firefox staying open, and dodges YouTube's bot-check).
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies.txt")
YTDLP_COMMON_OPTS = {
    "js_runtimes": {"deno": {}},
    "cookiefile": COOKIES_FILE,
}

logging.basicConfig(level=logging.INFO)
bot = Bot(BOT_TOKEN)
dp = Dispatcher()


class AllowlistMiddleware(BaseMiddleware):
    """Silently drops updates from anyone not in ALLOWED_USER_IDS.

    "Silently" on purpose - a personal bot replying "access denied" to a
    stranger just confirms it's alive and worth poking at. If the allowlist
    is empty (not configured yet) this lets everyone through, matching the
    warning logged at startup.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not ALLOWED_USER_IDS:
            return await handler(event, data)
        user: User | None = data.get("event_from_user")
        if user is not None and user.id not in ALLOWED_USER_IDS:
            logging.warning("ignoring update from unauthorized user_id=%s (@%s)", user.id, user.username)
            return None
        return await handler(event, data)


dp.message.middleware(AllowlistMiddleware())
dp.callback_query.middleware(AllowlistMiddleware())
# default endpoint_country="GB" 404s on track_about for a large
# fraction of matched ids (catalog entry not in the GB regional index even
# though the fingerprint matched) - silently drops real matches down to
# "couldn't recognize". US is Shazam's most complete catalog.
shazam = Shazam(endpoint_country="US")


async def safe_edit_text(message: Message, text: str, **kwargs):
    # Telegram rejects an edit whose text+markup exactly match what's
    # already there (e.g. a double-tapped button) with a 400 that otherwise
    # crashes the handler. Harmless — the message already says what we wanted.
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise

# trimming blindly to the first N seconds cut into intro talk/silence
# on short clips and gave Shazam a wrong match. Only trim genuinely long input
# (multi-minute video), and pull the sample from the middle, not the start.
NO_TRIM_UNDER_SECONDS = 40
RECOGNIZE_CLIP_SECONDS = 25

# kind -> ffmpeg audio filter (None = no pitch/time/spatial effect, mastering
# chain still runs). asetrate+aresample shifts pitch together with speed (the
# actual "sped up"/"slowed" trend sound), not just tempo.
#
# tried afir convolution reverb with a synthetic (noise-burst +
# exponential decay) impulse response here — spectrogram looked like a real
# decaying tail, but live it sounded hollow/phasey (like being underwater): a fake
# IR built from raw noise has no clean initial impulse, so afir's convolution
# smears and partially cancels the *dry* signal's own transients, not just
# adding a tail on top. Real convolution reverb needs an actual recorded IR,
# not a synthesized one; not worth it for what this gets used for.
#
# a single aecho call (tried first, then a denser-tap version of
# the same thing) turned out to have two real problems, both confirmed with
# an impulse test (astats measured peak level; a noise-burst spectrogram
# measured the tail's frequency content):
#   1. aecho's in_gain*out_gain scales the WHOLE output, dry included — not
#      just the echoes. Measured: with in_gain=0.75/out_gain=0.72 the dry
#      passthrough was already -46% before any echo was even added. That's
#      the "boxed-in" muffling — the direct signal was never actually 100%.
#   2. aecho has no per-tap filtering — every repeat carries the exact same
#      frequency content as the original, just quieter. Real reverb's later
#      reflections lose highs (air/material absorption); ours didn't, so
#      bright content (hi-hats, vocal sibilance) rang on for the whole tail —
#      the "electric shimmer" complaint.
#
# Fixed by building the wet path as its own filter_complex graph instead of
# a single aecho string (see REVERB_PRESETS / master_reverb): the dry
# branch is a true unprocessed asplit copy (in_gain/out_gain forced to 1:1,
# so nothing scales it), and the taps are split into an early cluster (dense,
# full-band — real early reflections are still broadband) and a late cluster
# that gets an explicit lowpass so the tail actually darkens over time.
# key -> (label, early_delays, early_decays, late_delays, late_decays,
#          late_lowpass_hz, pre-master chain key). *_delays/*_decays are
# pipe-separated strings ready to drop into aecho's delays:/decays: args.
REVERB_PRESETS = {
    "reverb_light": (
        "Reverb (Light)",
        "8|11|14|19", "0.16|0.115|0.083|0.06",
        "25|34|45|60", "0.043|0.031|0.022|0.016",
        9000, "warm",
    ),
    "reverb_medium": (
        "Reverb (Medium)",
        "10|13|17|22|28|37|48", "0.24|0.192|0.154|0.123|0.098|0.079|0.063",
        "62|81|105|137|178|231|300", "0.05|0.04|0.032|0.026|0.021|0.016|0.013",
        5500, "warm",
    ),
    "reverb_heavy": (
        "Reverb (Heavy)",
        "12|14|17|21|25|30|36|43|52|62|74", "0.32|0.275|0.237|0.204|0.175|0.151|0.129|0.111|0.096|0.082|0.071",
        "89|107|128|154|184|221|265|318|382|458|550", "0.061|0.052|0.045|0.039|0.033|0.029|0.025|0.021|0.018|0.016|0.013",
        3200, "warm",
    ),
}

# Speed and "effect" are independent choices — pick one or more effects
# first, then a speed 0.5x-1.5x to apply them at. Every effect gets the
# asetrate speed change prepended at send time (see handle_speed).
#
# key -> (label, ffmpeg audio filter or None, pre-master chain key). Simple
# effects run through the normal linear -filter:a chain; reverb effects (in
# REVERB_PRESETS above) need the dry/wet filter_complex graph instead — see
# _generate_and_send, which picks the right path depending on what's selected.
#
# "8D audio" trend edits are really just a slow amplitude pan
# between channels — ffmpeg's apulsator does exactly that (no real binaural
# HRTF processing, which is what actual 8D would need). It no longer bundles
# a baked-in reverb tail — select a Reverb preset alongside it if you want both.
SIMPLE_EFFECTS = {
    "original": ("Original", None, "bright"),
    "nightcore": ("Nightcore", None, "nightcore"),
    "bass_boosted": ("Bass Boosted", "bass=g=14:f=60:w=0.9", "bright"),
    "8d": ("8D Audio", "apulsator=hz=0.08:amount=1", "bright"),
}

# key -> label, for keyboard building / combo labels. Detailed per-kind data
# (filter chains, chain keys) lives in SIMPLE_EFFECTS / REVERB_PRESETS above.
EFFECTS = {k: v[0] for k, v in {**SIMPLE_EFFECTS, **REVERB_PRESETS}.items()}
SPEEDS = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]

# raw yt-dlp extraction and the pitch-shifted variants both sound
# thin/quiet next to an actual release. First attempt (one-shot compressor +
# EQ + single-pass loudnorm) came back sounding muffled — single-
# pass loudnorm's dynamic gain-riding smears transients, a 3:1 compressor was
# squashing punch, and there was no midrange presence to counter the added
# bass, so the mix masked itself. Fixed: gentler glue compression, a presence
# bump at 3.5kHz (exactly the band that reads as "clarity" and was missing),
# and real two-pass loudnorm (measure, then apply with linear=true) instead
# of the smeary single-pass "dynamic" mode.
PRE_MASTER_CHAIN = (
    "acompressor=threshold=-20dB:ratio=2:attack=20:release=300,"
    "bass=g=2.5:f=90,"
    "equalizer=f=3500:t=q:w=1.2:g=2,"
    "treble=g=3:f=9000"
)
# same glue compression and bass warmth, but no presence/treble push — the
# reverb tail's own lowpass already darkens the top end on purpose.
PRE_MASTER_CHAIN_WARM = "acompressor=threshold=-20dB:ratio=2:attack=20:release=300,bass=g=3:f=90"
LOUDNORM_TARGET = "I=-11:TP=-1:LRA=8"

PRE_CHAINS = {
    "bright": PRE_MASTER_CHAIN,
    "warm": PRE_MASTER_CHAIN_WARM,
    # nightcore wants brighter/crisper than the default bright chain, not just
    # "sped up" — an extra treble push is what actually separates it from
    # picking "Original" at the same speed.
    "nightcore": PRE_MASTER_CHAIN + ",treble=g=2:f=11000",
}


# a stuck/hung ffmpeg process (bad input, weird codec, whatever)
# would otherwise block the handler forever - Telegram's "Listening..." status
# never updates and the whole request just hangs. Fail it loudly instead.
FFMPEG_TIMEOUT_SECONDS = 60


def run_ffmpeg(args: list[str]):
    try:
        subprocess.run(
            [FFMPEG_BIN, "-y", "-hide_banner", "-loglevel", "error", *args],
            check=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg timed out after {FFMPEG_TIMEOUT_SECONDS}s: {args}")


def _measure_loudness(path: str) -> dict:
    try:
        out = subprocess.run(
            [FFMPEG_BIN, "-hide_banner", "-i", path, "-af", f"loudnorm={LOUDNORM_TARGET}:print_format=json", "-f", "null", "-"],
            capture_output=True, text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg (loudness measure) timed out after {FFMPEG_TIMEOUT_SECONDS}s: {path}")
    text = out.stderr
    return json.loads(text[text.rfind("{"):text.rfind("}") + 1])


def master_audio(src: str, dst: str, pre_chain: str = PRE_MASTER_CHAIN, effect_filter: str | None = None, bitrate: int = 320):
    """EQ/compress, measure true loudness, then apply a real two-pass loudnorm.

    A variant used to run its pitch/reverb effect as its own ffmpeg
    pass into an intermediate file, then master_audio ran a *separate* EQ
    pass on that file — two subprocess spawns + an extra disk round-trip for
    what ffmpeg can do in one filter chain (`a,b,c` applies identically to
    separate invocations for these stateless filters). Folding the effect
    into this first pass cuts a full subprocess+file-write out of every
    variant's chain for free — same output, less overhead.
    """
    pre = dst + ".pre.wav"
    filters = f"{effect_filter},{pre_chain}" if effect_filter else pre_chain
    try:
        run_ffmpeg(["-i", src, "-filter:a", filters, pre])
        m = _measure_loudness(pre)
        loudnorm = (
            f"loudnorm={LOUDNORM_TARGET}:linear=true:"
            f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
        )
        run_ffmpeg(["-i", pre, "-filter:a", loudnorm, "-b:a", f"{bitrate}k", dst])
    finally:
        if os.path.exists(pre):
            os.remove(pre)


def master_reverb(
    src: str, dst: str, speed_filter: str, preset: tuple, extra_filters: list[str], pre_chain: str, bitrate: int
) -> None:
    """Same two-pass loudnorm mastering as master_audio, but builds the wet
    signal as a filter_complex graph instead of a single aecho string — see
    the REVERB_PRESETS comment for why (dry needs to stay untouched, and the
    late reflections need their own lowpass, neither of which one aecho call
    can do on its own).
    """
    _label, early_d, early_g, late_d, late_g, late_lp, _chain = preset
    post = ",".join(extra_filters + [pre_chain]) if extra_filters else pre_chain
    graph = (
        f"[0:a]{speed_filter},asplit=3[dry][e_src][l_src];"
        f"[e_src]aecho=1:1:{early_d}:{early_g}[early];"
        f"[l_src]aecho=1:1:{late_d}:{late_g},lowpass=f={late_lp}[late];"
        f"[dry][early][late]amix=inputs=3:weights=1 1 1:normalize=0,{post}[out]"
    )
    pre = dst + ".pre.wav"
    try:
        run_ffmpeg(["-i", src, "-filter_complex", graph, "-map", "[out]", pre])
        m = _measure_loudness(pre)
        loudnorm = (
            f"loudnorm={LOUDNORM_TARGET}:linear=true:"
            f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
        )
        run_ffmpeg(["-i", pre, "-filter:a", loudnorm, "-b:a", f"{bitrate}k", dst])
    finally:
        if os.path.exists(pre):
            os.remove(pre)


def probe_duration(path: str) -> float:
    try:
        out = subprocess.run(
            [FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe timed out after {FFMPEG_TIMEOUT_SECONDS}s: {path}")
    return float(out.stdout.strip())


def trim_for_recognition(src: str, dst: str):
    # dynaudnorm: phone/video audio is often quiet or has an uneven level,
    # which hurts Shazam's fingerprint matching more than it hurts human ears.
    duration = probe_duration(src)
    if duration <= NO_TRIM_UNDER_SECONDS:
        run_ffmpeg(["-i", src, "-ac", "1", "-ar", "44100", "-af", "dynaudnorm", dst])
        return
    offset = (duration - RECOGNIZE_CLIP_SECONDS) / 2  # middle of the file, skips likely intro talk
    run_ffmpeg(["-ss", str(offset), "-i", src, "-t", str(RECOGNIZE_CLIP_SECONDS), "-ac", "1", "-ar", "44100", "-af", "dynaudnorm", dst])


MAX_CANDIDATES = 3
SHAZAM_TIMEOUT = 20  # seconds — a hung Shazam request shouldn't freeze the chat forever

# (title, artist, coverart url or None, lyrics text or None)
TrackTuple = tuple[str, str | None, str | None, str | None]


def _track_tuple(track: dict) -> TrackTuple | None:
    """Pulls the fields we care about out of a Shazam track object.

    Same shape comes back from both recognize()'s "track" field and
    track_about() — both are Shazam "Track" objects.
    """
    title = track.get("title")
    if not title:
        return None
    artist = track.get("subtitle")
    coverart = (track.get("images") or {}).get("coverart")
    lyrics = None
    for section in track.get("sections", []):
        if section.get("type") == "LYRICS":
            lines = section.get("text") or []
            if lines:
                lyrics = "\n".join(lines)
            break
    return (title, artist, coverart, lyrics)


async def _recognize_once(file_path: str) -> list[TrackTuple]:
    # shazamio's "track" (its own top pick) has occasionally been
    # wrong on short/noisy clips, but it comes free with the recognize() call
    # — no extra request. Seed candidates with it, then use the raw "matches"
    # list (other fingerprint hits, possibly different songs) via track_about
    # to fill in real alternatives. This means a track_about outage (has
    # happened — Shazam's catalog lookup 404ing independent of anything we
    # do) degrades to "just the free top pick" instead of total failure.
    # "retryms" in the response means Shazam's signal from this exact
    # clip was too ambiguous, not "server busy" — resending the identical bytes
    # gets the identical answer. recognize_candidates() below already retries
    # with speed-corrected variants, which is a real second chance; waiting on
    # the same bytes here was not.
    result = await asyncio.wait_for(shazam.recognize(file_path), timeout=SHAZAM_TIMEOUT)

    candidates: list[TrackTuple] = []
    seen_titles = set()
    track = result.get("track")
    if track:
        tup = _track_tuple(track)
        if tup:
            key = (tup[0], tup[1])
            seen_titles.add(key)
            candidates.append(tup)

    seen_ids, ids = set(), []
    for m in result.get("matches", []):
        tid = m.get("id")
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            ids.append(tid)

    async def _lookup(tid: str):
        try:
            return await asyncio.wait_for(shazam.track_about(track_id=tid), timeout=SHAZAM_TIMEOUT)
        except Exception:
            # one bad lookup shouldn't discard the candidates already found
            logging.exception("track_about failed for id=%s", tid)
            return None

    # these lookups are independent — firing them together instead of one at a
    # time is the single biggest latency win when Shazam returns multiple ids.
    if len(candidates) < MAX_CANDIDATES and ids:
        infos = await asyncio.gather(*(_lookup(tid) for tid in ids))
        for info in infos:
            if not info:
                continue
            tup = _track_tuple(info)
            if not tup:
                continue
            key = (tup[0], tup[1])
            if key not in seen_titles:
                seen_titles.add(key)
                candidates.append(tup)
            if len(candidates) >= MAX_CANDIDATES:
                break

    logging.info("shazam candidates for %s: %s", file_path, [(t, a) for t, a, _, _ in candidates])
    return candidates


# "slowed"/"sped up" trend edits shift both tempo and pitch together
# (asetrate-style), which moves the fingerprint just enough that Shazam's own
# tolerance for timeskew/frequencyskew doesn't cover it. If the clip as-is
# gets nothing, try re-speeding it by a few common trend ratios and see if
# any of them lands back on the original's fingerprint.
SPEED_CORRECTIONS = [1.06, 0.94, 1.12, 0.88]


async def recognize_candidates(file_path: str, tmp_dir: str) -> list[TrackTuple]:
    # the raw clip alone can spuriously match a WRONG track (seen live:
    # a "slowed + reverb" edit matched something else entirely on the raw pass,
    # and since raw returned *something*, the speed-corrected passes — one of
    # which held the actual right answer — never even ran). Always run raw +
    # every speed correction concurrently and merge every distinct match instead
    # of trusting whichever pass happens to answer first; 2+ genuinely different
    # answers falls through to the existing "which track?" picker instead of
    # silently delivering one of them.
    async def _try_correction(factor: float):
        corrected = os.path.join(tmp_dir, f"corrected_{factor}.wav")
        await asyncio.to_thread(run_ffmpeg, ["-i", file_path, "-af", f"asetrate=44100*{factor},aresample=44100", corrected])
        return await _recognize_once(corrected)

    all_results = await asyncio.gather(_recognize_once(file_path), *(_try_correction(f) for f in SPEED_CORRECTIONS))

    merged: list[TrackTuple] = []
    seen = set()
    for candidates in all_results:
        for tup in candidates:
            key = (tup[0], tup[1])
            if key not in seen:
                seen.add(key)
                merged.append(tup)
    return merged[:MAX_CANDIDATES]


MIN_TRACK_SECONDS = 45  # filters out ringtones/shorts/teasers that "ytsearch1" sometimes ranks first
DOWNLOAD_TIMEOUT = 90  # seconds — search + up to 3 download attempts, shouldn't normally take this long
TITLE_MATCH_MIN_OVERLAP = 0.5  # fraction of significant target words a candidate's title must contain


class NoMatchingVideoError(RuntimeError):
    """Raised when YouTube results exist but none plausibly match the identified track."""


YOUTUBE_URL_RE = re.compile(
    r"^(https?://)?(www\.|m\.)?(youtube\.com/(watch\?|shorts/|live/)|youtu\.be/)", re.IGNORECASE
)
# TikTok is handled the same way as a direct YouTube link (yt-dlp
# has a native extractor for both) — no Shazam involved, no search, whatever
# the link points to IS the answer.
TIKTOK_URL_RE = re.compile(r"^(https?://)?(www\.|vm\.|vt\.|m\.)?tiktok\.com/", re.IGNORECASE)
DIRECT_DOWNLOAD_RE = re.compile(f"(?:{YOUTUBE_URL_RE.pattern})|(?:{TIKTOK_URL_RE.pattern})", re.IGNORECASE)

# Spotify/Apple Music don't let yt-dlp pull audio (DRM) — these are only used
# to scrape a title+artist off the page, then the normal YouTube search path
# takes over, same as if you'd typed the song name yourself.
SPOTIFY_URL_RE = re.compile(r"^(https?://)?open\.spotify\.com/(intl-\w+/)?track/", re.IGNORECASE)
APPLE_MUSIC_URL_RE = re.compile(r"^(https?://)?music\.apple\.com/", re.IGNORECASE)
PAGE_FETCH_TIMEOUT = 10


def _probe_media_url(url: str) -> dict:
    """Just enough metadata (title, uploader) to label the quality-picker message."""
    with YoutubeDL({"quiet": True, "noplaylist": True, "extract_flat": "in_playlist", **YTDLP_COMMON_OPTS}) as ydl:
        return ydl.extract_info(url, download=False)


def _fetch_page_title(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=PAGE_FETCH_TIMEOUT) as resp:
        page = resp.read().decode("utf-8", errors="replace")
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.IGNORECASE | re.DOTALL)
    if not m:
        raise RuntimeError("no <title> tag found")
    return html.unescape(m.group(1)).strip()


# scraping the <title> tag's current wording is fragile — Spotify/
# Apple can and do change this format, silently breaking the regex below. No
# real fix without an API key (out of scope for a personal bot); ceiling is
# "falls back to asking for the song name as text", not a crash.
def _parse_spotify_title(page_title: str) -> tuple[str, str] | None:
    m = re.match(r"^(.*?)\s*[-–]\s*song(?: and lyrics)? by (.*?)\s*\|\s*Spotify$", page_title, re.IGNORECASE)
    return (m.group(1).strip(), m.group(2).strip()) if m else None


def _parse_apple_music_title(page_title: str) -> tuple[str, str] | None:
    m = re.match(r"^(.*?)\s*[-–]\s*[Ss]ong by (.*?)\s*[-–]\s*Apple Music$", page_title)
    return (m.group(1).strip(), m.group(2).strip()) if m else None


def _title_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", text.lower()) if len(w) >= 3}


def _looks_like_match(candidate_title: str, target: str) -> bool:
    # naive word-overlap, not audio fingerprinting — good enough to
    # catch "completely different song" (the actual failure mode seen), not
    # meant to catch subtly-wrong remixes/covers.
    target_words = _title_words(target)
    if not target_words:
        return True
    overlap = len(_title_words(candidate_title) & target_words)
    return overlap / len(target_words) >= TITLE_MATCH_MIN_OVERLAP


def download_mp3(query: str, out_dir: str, match_target: str | None = None, bitrate: int = 320) -> str:
    outtmpl = os.path.join(out_dir, "%(title)s.%(ext)s")
    is_direct_link = bool(DIRECT_DOWNLOAD_RE.match(query))
    # without extract_flat, ytsearch resolves full formats (incl. the
    # JS signature challenge) for all 5 results just to read their duration —
    # flat listing gets the same metadata without the per-video resolution cost.
    #
    # SoundCloud (scsearch) and Mail.ru Music were both tried as extra sources
    # and both failed for real reasons, not laziness: SoundCloud's client_id
    # bootstrap needs soundcloud.com itself, which resets connections on this
    # network (SNI-level block, confirmed via curl/WebFetch — the API subdomain
    # is reachable, the bootstrap page isn't); Mail.ru Music's search hits work
    # but return short-lived signed CDN URLs that 404 by the time the two-step
    # search-then-download flow (with a quality-picker pause in between) tries
    # to fetch them. YouTube alone, kept. (TikTok/YouTube direct links skip
    # search entirely — see is_direct_link above.)
    if is_direct_link:
        # a direct link IS the target — no search, no duration floor
        # (an explicitly-linked short is still what was asked for), no title-
        # match sanity check (there's no candidate list to be wrong about).
        candidates = [{"url": query}]
    else:
        search_opts = {
            "quiet": True, "default_search": "ytsearch5", "noplaylist": True,
            "extract_flat": "in_playlist", **YTDLP_COMMON_OPTS,
        }
        with YoutubeDL(search_opts) as ydl:
            results = ydl.extract_info(query, download=False)
            candidates = [e for e in results.get("entries", []) if e and (e.get("duration") or 0) >= MIN_TRACK_SECONDS]
        if not candidates:
            raise RuntimeError(f"no full-length youtube result for query: {query!r}")

    if match_target is not None and not is_direct_link:
        matched = [c for c in candidates if _looks_like_match(c.get("title", ""), match_target)]
        if not matched:
            raise NoMatchingVideoError(
                f"no result title matches {match_target!r} (got: "
                f"{[c.get('title') for c in candidates[:5]]!r})"
            )
        candidates = matched

    dl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": str(bitrate),  # kbps; master_audio re-encodes anyway, this just avoids extra loss in between
        }],
        "noplaylist": True,
        "quiet": True,
        "ffmpeg_location": FFMPEG_DIR,
        **YTDLP_COMMON_OPTS,
    }
    last_error = None
    for candidate in candidates[:3]:  # a blocked/removed top result shouldn't kill the whole search
        logging.info("query=%r -> trying %r (%ss, %s)", query, candidate.get("title"), candidate.get("duration"), candidate.get("url"))
        try:
            with YoutubeDL(dl_opts) as ydl:
                info = ydl.extract_info(candidate["url"], download=True)
                path = ydl.prepare_filename(info)
                return os.path.splitext(path)[0] + ".mp3"
        except Exception as e:
            logging.warning("candidate failed: %s", e)
            last_error = e
    raise last_error


def is_auth_error(exc: Exception) -> bool:
    # cookies.txt was exported once from a live Firefox session and
    # will eventually expire — when it does, yt-dlp's error is distinctive
    # enough to tell the user what's actually wrong instead of a generic fail.
    text = str(exc).lower()
    return any(s in text for s in ("sign in to confirm", "cookies", "not a bot"))


@dataclass
class DeliveryState:
    """One recognized track, waiting for the user to pick which version(s) to get.

    The source mp3 has to survive across multiple separate button
    clicks (each a fresh callback handler invocation), so its temp dir can't
    be a `with tempfile.TemporaryDirectory()` scoped to one call like the old
    single-shot deliver_track was — it's a plain mkdtemp() that outlives the
    handler, cleaned up later by _sweep_stale_deliveries() instead of a
    context manager. Ceiling: a crash between mkdtemp and the sweep leaks a
    temp dir; acceptable for a personal bot, not something worth a proper
    on-shutdown cleanup pass for.
    """
    dir: str
    mp3_path: str
    title: str
    artist: str
    bitrate: int
    coverart: str | None
    lyrics: str | None
    sent: set[str]
    created_at: float
    selected: set[str]  # effect keys currently checked, combined together on "go"
    as_voice: bool = False  # deliver as a Telegram voice note (OGG/Opus) instead of an mp3 audio file


DELIVERY: dict[str, DeliveryState] = {}
DELIVERY_TTL_SECONDS = 1800  # 30 min — enough to click through several versions
# the most recent token that has an effect combo picked and is waiting on a
# speed — lets a typed number like "0.837" work as a speed shortcut (see
# handle_text_query) without the user having to tap through the buttons.
LAST_SPEED_TOKEN: str | None = None


def _sweep_stale_deliveries() -> None:
    now = time.time()
    stale = [tok for tok, st in DELIVERY.items() if now - st.created_at > DELIVERY_TTL_SECONDS]
    for tok in stale:
        st = DELIVERY.pop(tok)
        shutil.rmtree(st.dir, ignore_errors=True)


@dataclass
class HistoryEntry:
    title: str
    artist: str
    search_query: str | None
    coverart: str | None
    lyrics: str | None


# keyed by an ever-incrementing id instead of list position, so a
# "resend this" button from an old /history message still points at the
# right track even after older entries get trimmed off (a list index would
# silently shift to point at a DIFFERENT track once the front is trimmed).
HISTORY: dict[int, HistoryEntry] = {}
HISTORY_NEXT_ID = 0
HISTORY_MAX = 20


def _add_history(entry: HistoryEntry) -> None:
    global HISTORY_NEXT_ID
    HISTORY[HISTORY_NEXT_ID] = entry
    HISTORY_NEXT_ID += 1
    if len(HISTORY) > HISTORY_MAX:
        del HISTORY[min(HISTORY)]


def _effect_keyboard(token: str) -> InlineKeyboardMarkup:
    """Step 1: check off one or more effects (combined together), then "Next"."""
    state = DELIVERY.get(token)
    selected = state.selected if state else set()
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for key, label in EFFECTS.items():
        mark = "☑️ " if key in selected else "▫️ "
        row.append(InlineKeyboardButton(text=mark + label, callback_data=f"tgl:{token}:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if state:
        voice_mark = "☑️ " if state.as_voice else "▫️ "
        rows.append([InlineKeyboardButton(text=voice_mark + "🎙 As voice note", callback_data=f"voicetgl:{token}")])
    if selected:
        rows.append([InlineKeyboardButton(text="▶️ Next — pick a speed", callback_data=f"go:{token}")])
    if state and state.lyrics:
        text = ("✅ " if "lyrics" in state.sent else "") + "📄 Lyrics"
        rows.append([InlineKeyboardButton(text=text, callback_data=f"lyr:{token}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _combo_label(state: DeliveryState) -> str:
    return " + ".join(EFFECTS[k] for k in sorted(state.selected))


def _speed_keyboard(token: str) -> InlineKeyboardMarkup:
    """Step 2: pick a speed bucket (0.5x-1.5x, 0.1 steps) for the effect combo
    picked in step 1 (state.selected). Each bucket drills into a 0.01-step
    submenu (_fine_speed_keyboard) rather than sending directly."""
    state = DELIVERY.get(token)
    sent = state.sent if state else set()
    combo_key = "+".join(sorted(state.selected)) if state else ""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for speed in SPEEDS:
        # a bucket is "done" if any fine value inside it was sent — e.g. sent
        # key "nightcore:0.85" starts with the same "0.8"/"1.1"/etc prefix as
        # every value in that bucket's own str(), including the bucket's own
        # str(speed) itself (0.8 -> "0.8", which 0.85's "0.85" also starts with).
        done = any(s.startswith(f"{combo_key}:") and s.split(":", 1)[1].startswith(str(speed)) for s in sent)
        text = ("✅ " if done else "") + f"{speed}x"
        row.append(InlineKeyboardButton(text=text, callback_data=f"spdrange:{token}:{speed}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅ Back", callback_data=f"back:{token}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _fine_speed_keyboard(token: str, base: float) -> InlineKeyboardMarkup:
    """Step 3: pick an exact speed within [base, base+0.09], 0.01 steps."""
    state = DELIVERY.get(token)
    sent = state.sent if state else set()
    combo_key = "+".join(sorted(state.selected)) if state else ""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i in range(10):
        speed = round(base + i * 0.01, 2)
        done = f"{combo_key}:{speed}" in sent
        text = ("✅ " if done else "") + f"{speed}x"
        row.append(InlineKeyboardButton(text=text, callback_data=f"spd:{token}:{speed}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅ Back", callback_data=f"backspd:{token}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _bucket(speed: float) -> float:
    """Rounds a precise speed (e.g. 0.85) down to its 0.1 bucket start (0.8)."""
    return round((int(round(speed * 100)) // 10) * 10 / 100, 2)


async def start_delivery(
    status: Message, title: str, artist: str, search_query: str | None, bitrate: int,
    coverart: str | None = None, lyrics: str | None = None,
) -> None:
    """Downloads the source track once, then hands off to the effect/speed buttons."""
    _sweep_stale_deliveries()
    label = f"{artist} — {title}" if artist else title
    query = search_query if search_query is not None else f"{artist} {title}"
    await safe_edit_text(status, f"Found: {label}\nDownloading mp3...")

    tmp_dir = tempfile.mkdtemp(prefix="szm_")
    try:
        mp3_path = await asyncio.wait_for(
            asyncio.to_thread(download_mp3, query, tmp_dir, label, bitrate), timeout=DOWNLOAD_TIMEOUT
        )
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logging.exception("download failed")
        if isinstance(e, NoMatchingVideoError):
            await safe_edit_text(
                status,
                f"Identified as {label}, but the YouTube results didn't match the title closely enough — didn't want to risk sending the wrong track.",
            )
        elif is_auth_error(e):
            await safe_edit_text(
                status,
                f"Identified as {label}, but YouTube is asking for authentication — cookies.txt is stale and needs refreshing.",
            )
        else:
            await safe_edit_text(status, f"Identified as {label}, but couldn't download the file.")
        return

    token = uuid.uuid4().hex[:12]
    DELIVERY[token] = DeliveryState(
        dir=tmp_dir, mp3_path=mp3_path, title=title, artist=artist, bitrate=bitrate,
        coverart=coverart, lyrics=lyrics, sent=set(), created_at=time.time(), selected=set(),
    )
    _add_history(HistoryEntry(title=title, artist=artist, search_query=search_query, coverart=coverart, lyrics=lyrics))

    await safe_edit_text(status, f"Found: {label}\nWhich effect? (pick one or more)", reply_markup=_effect_keyboard(token))


@dp.callback_query(F.data.startswith("tgl:"))
async def handle_toggle(callback: CallbackQuery) -> None:
    _, token, key = callback.data.split(":", 2)
    await callback.answer()
    state = DELIVERY.get(token)
    if not state or key not in EFFECTS:
        await safe_edit_text(callback.message, "This card expired, send the clip again.")
        return
    # "Original" (no filter) doesn't combine with anything — picking it clears
    # the rest, and picking anything else drops it. Two reverb presets at once
    # doesn't mean anything either (only one dry/wet graph gets built) — picking
    # one drops any other reverb preset already selected.
    if key == "original":
        state.selected = set() if "original" in state.selected else {"original"}
    else:
        state.selected.discard("original")
        if key in state.selected:
            state.selected.discard(key)
        else:
            if key in REVERB_PRESETS:
                state.selected -= set(REVERB_PRESETS)
            state.selected.add(key)
    try:
        await callback.message.edit_reply_markup(reply_markup=_effect_keyboard(token))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("voicetgl:"))
async def handle_voice_toggle(callback: CallbackQuery) -> None:
    _, token = callback.data.split(":", 1)
    await callback.answer()
    state = DELIVERY.get(token)
    if not state:
        await safe_edit_text(callback.message, "This card expired, send the clip again.")
        return
    state.as_voice = not state.as_voice
    try:
        await callback.message.edit_reply_markup(reply_markup=_effect_keyboard(token))
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data.startswith("go:"))
async def handle_go(callback: CallbackQuery) -> None:
    global LAST_SPEED_TOKEN
    _, token = callback.data.split(":", 1)
    await callback.answer()
    state = DELIVERY.get(token)
    if not state or not state.selected:
        await safe_edit_text(callback.message, "This card expired, send the clip again.")
        return
    LAST_SPEED_TOKEN = token
    label = f"{state.artist} — {state.title}" if state.artist else state.title
    await safe_edit_text(
        callback.message, f"{label}\n{_combo_label(state)} — what speed?", reply_markup=_speed_keyboard(token)
    )


@dp.callback_query(F.data.startswith("back:"))
async def handle_back(callback: CallbackQuery) -> None:
    _, token = callback.data.split(":", 1)
    await callback.answer()
    state = DELIVERY.get(token)
    if not state:
        await safe_edit_text(callback.message, "This card expired, send the clip again.")
        return
    label = f"{state.artist} — {state.title}" if state.artist else state.title
    await safe_edit_text(callback.message, f"Found: {label}\nWhich effect? (pick one or more)", reply_markup=_effect_keyboard(token))


@dp.callback_query(F.data.startswith("lyr:"))
async def handle_lyrics(callback: CallbackQuery) -> None:
    _, token = callback.data.split(":", 1)
    await callback.answer()
    state = DELIVERY.get(token)
    if not state:
        await safe_edit_text(callback.message, "This card expired, send the clip again.")
        return
    if state.lyrics:
        await callback.message.answer(f"📄 {state.artist} — {state.title}\n\n{state.lyrics[:4000]}")
        state.sent.add("lyrics")
        try:
            await callback.message.edit_reply_markup(reply_markup=_effect_keyboard(token))
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data.startswith("spdrange:"))
async def handle_speed_range(callback: CallbackQuery) -> None:
    _, token, base_str = callback.data.split(":", 2)
    await callback.answer()
    state = DELIVERY.get(token)
    if not state or not state.selected:
        await safe_edit_text(callback.message, "This card expired, send the clip again.")
        return
    base = float(base_str)
    label = f"{state.artist} — {state.title}" if state.artist else state.title
    await safe_edit_text(
        callback.message,
        f"{label}\n{_combo_label(state)} — exact speed ({base:.2f}–{base + 0.09:.2f}x)?",
        reply_markup=_fine_speed_keyboard(token, base),
    )


@dp.callback_query(F.data.startswith("backspd:"))
async def handle_back_speed(callback: CallbackQuery) -> None:
    _, token = callback.data.split(":", 1)
    await callback.answer()
    state = DELIVERY.get(token)
    if not state or not state.selected:
        await safe_edit_text(callback.message, "This card expired, send the clip again.")
        return
    label = f"{state.artist} — {state.title}" if state.artist else state.title
    await safe_edit_text(
        callback.message, f"{label}\n{_combo_label(state)} — what speed?", reply_markup=_speed_keyboard(token)
    )


async def _generate_and_send(target: Message, token: str, speed: float) -> bool:
    """Masters the current effect combo (state.selected) at `speed` and sends
    it (as a voice note if state.as_voice, else as an audio file). Returns
    False if the delivery card is gone/empty (caller decides how to react)."""
    state = DELIVERY.get(token)
    if not state or not state.selected:
        return False

    combo = sorted(state.selected)
    label = _combo_label(state)
    simple_keys = [k for k in combo if k in SIMPLE_EFFECTS]
    reverb_keys = [k for k in combo if k in REVERB_PRESETS]
    reverb_key = reverb_keys[0] if reverb_keys else None  # mutual exclusivity enforced in handle_toggle

    extra_filters = [f for f in (SIMPLE_EFFECTS[k][1] for k in simple_keys) if f]
    chains = {SIMPLE_EFFECTS[k][2] for k in simple_keys}
    if reverb_key:
        chains.add(REVERB_PRESETS[reverb_key][6])
    chain_key = "nightcore" if "nightcore" in chains else ("warm" if "warm" in chains else "bright")
    pre_chain = PRE_CHAINS[chain_key]
    speed_filter = f"asetrate=44100*{speed},aresample=44100"
    combo_key = "+".join(combo)
    sent_key = f"{combo_key}:{speed}"
    dst = os.path.join(state.dir, f"{combo_key}_{speed}.mp3".replace("+", "_"))
    display_title = f"{state.title} ({label}, {speed}x)"
    try:
        if not os.path.exists(dst):
            if reverb_key:
                await asyncio.to_thread(
                    master_reverb, state.mp3_path, dst, speed_filter,
                    REVERB_PRESETS[reverb_key], extra_filters, pre_chain, state.bitrate,
                )
            else:
                full_filter = ",".join([speed_filter] + extra_filters)
                await asyncio.to_thread(master_audio, state.mp3_path, dst, pre_chain, full_filter, state.bitrate)
        if state.as_voice:
            voice_path = dst + ".ogg"
            if not os.path.exists(voice_path):
                await asyncio.to_thread(
                    run_ffmpeg, ["-i", dst, "-c:a", "libopus", "-b:a", "64k", "-vbr", "on", voice_path]
                )
            await target.answer_voice(FSInputFile(voice_path), caption=display_title)
        else:
            thumb = URLInputFile(state.coverart) if state.coverart else None
            try:
                await target.answer_audio(FSInputFile(dst), title=display_title, performer=state.artist or None, thumbnail=thumb)
            except TelegramBadRequest:
                if thumb is None:
                    raise
                # Shazam's coverart isn't guaranteed to meet Telegram's
                # thumbnail constraints (size/aspect) — don't lose the actual
                # audio over a thumbnail Telegram didn't like.
                await target.answer_audio(FSInputFile(dst), title=display_title, performer=state.artist or None)
    except Exception:
        logging.exception("sending %s failed", sent_key)
        await target.answer(f"Couldn't put together “{label}” at {speed}x, try again.")
        return True

    state.sent.add(sent_key)
    return True


@dp.callback_query(F.data.startswith("spd:"))
async def handle_speed(callback: CallbackQuery) -> None:
    _, token, speed_str = callback.data.split(":", 2)
    state = DELIVERY.get(token)
    if not state or not state.selected:
        await callback.answer()
        await safe_edit_text(callback.message, "This card expired, send the clip again.")
        return

    await callback.answer("Putting it together...")
    speed = float(speed_str)
    await _generate_and_send(callback.message, token, speed)
    try:
        await callback.message.edit_reply_markup(reply_markup=_fine_speed_keyboard(token, _bucket(speed)))
    except TelegramBadRequest:
        pass


# token -> candidates, for the track-picker keyboard below.
# Personal single-user bot, so plain in-memory dicts are enough (no persistence needed).
PENDING: dict[str, list[TrackTuple]] = {}
PENDING_QUALITY: dict[str, tuple[str, str, str | None, str | None, str | None]] = {}


async def ask_quality(
    status: Message, title: str, artist: str, search_query: str | None = None,
    coverart: str | None = None, lyrics: str | None = None,
) -> None:
    label = f"{artist} — {title}" if artist else title
    token = uuid.uuid4().hex[:12]
    PENDING_QUALITY[token] = (title, artist, search_query, coverart, lyrics)
    buttons = [[
        InlineKeyboardButton(text="320kbps · best quality", callback_data=f"quality:{token}:320"),
        InlineKeyboardButton(text="192kbps · faster", callback_data=f"quality:{token}:192"),
    ]]
    await safe_edit_text(
        status, f"Found: {label}\nWhich quality?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data.startswith("quality:"))
async def handle_quality(callback: CallbackQuery) -> None:
    _, token, bitrate = callback.data.split(":")
    pending = PENDING_QUALITY.pop(token, None)
    await callback.answer()
    if not pending:
        await safe_edit_text(callback.message, "This button expired, send the clip again.")
        return
    title, artist, search_query, coverart, lyrics = pending
    await start_delivery(callback.message, title, artist, search_query, int(bitrate), coverart, lyrics)


@dp.message(F.voice | F.audio | F.video_note | F.video)
async def handle_audio(message: Message):
    _sweep_stale_deliveries()
    status = await message.reply("Listening...")
    with tempfile.TemporaryDirectory() as tmp:
        src = message.voice or message.audio or message.video_note or message.video
        sample_path = os.path.join(tmp, "sample")
        try:
            await bot.download(src.file_id, destination=sample_path)
        except Exception:
            logging.exception("download from telegram failed")
            await safe_edit_text(status, "File's too big (Telegram's bot limit is 20MB) or failed to download — send a different one.")
            return

        clip_path = os.path.join(tmp, "clip.wav")
        try:
            await asyncio.to_thread(trim_for_recognition, sample_path, clip_path)
            candidates = await recognize_candidates(clip_path, tmp)
        except Exception:
            logging.exception("shazam recognize failed")
            candidates = []

    if not candidates:
        await safe_edit_text(status, "Couldn't identify the track — send a different clip.")
        return

    if len(candidates) == 1:
        title, artist, coverart, lyrics = candidates[0]
        await ask_quality(status, title, artist, coverart=coverart, lyrics=lyrics)
        return

    token = uuid.uuid4().hex[:12]
    PENDING[token] = candidates
    buttons = [
        [InlineKeyboardButton(text=f"{artist} — {title}", callback_data=f"pick:{token}:{i}")]
        for i, (title, artist, _coverart, _lyrics) in enumerate(candidates)
    ]
    await safe_edit_text(
        status, "Not sure which track this is — pick one:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@dp.callback_query(F.data.startswith("pick:"))
async def handle_pick(callback: CallbackQuery):
    _, token, idx = callback.data.split(":")
    candidates = PENDING.pop(token, None)
    await callback.answer()
    if not candidates:
        await safe_edit_text(callback.message, "This button expired, send the clip again.")
        return
    title, artist, coverart, lyrics = candidates[int(idx)]
    await ask_quality(callback.message, title, artist, coverart=coverart, lyrics=lyrics)


@dp.message(F.text == "/start")
async def start(message: Message):
    await message.reply(
        "Send a voice note/audio/video with music — I'll identify the track. Then check off one or "
        "more effects (original, nightcore, bass boosted, 8D audio, reverb — 3 levels, "
        "combinable), hit \"Next\" and pick a speed: rough first (0.5x-1.5x), "
        "then exact in 0.01 steps. While a card is waiting on a speed, you can just type a number "
        "as text (e.g. 0.837) instead of tapping buttons.\n"
        "\"🎙 As voice note\" in the effects list — deliver the result as a voice message instead of mp3.\n"
        "You can also just type a song name, or send a YouTube, TikTok, "
        "Spotify, or Apple Music link.\n"
        "/history — recently identified tracks, tap any to get it again.\n"
        "/terms — a short note on what this bot does and doesn't claim."
    )


@dp.message(F.text == "/terms")
async def terms(message: Message):
    await message.reply(
        "Personal, non-commercial bot — only usable by accounts listed in "
        "ALLOWED_USER_IDS. Not affiliated with Shazam, Spotify, Apple Music, "
        "YouTube, or TikTok — it identifies a track via the public Shazam "
        "service and locates it in already-public sources via yt-dlp; it "
        "doesn't crack anything or host a media library. Whoever runs this "
        "bot is responsible for making sure that use doesn't violate "
        "copyright law or those services' terms in their own jurisdiction. "
        "No warranty — see DISCLAIMER.md in the repo for details."
    )


@dp.message(F.text == "/history")
async def history_cmd(message: Message):
    if not HISTORY:
        await message.reply("Nothing yet — haven't identified anything this session.")
        return
    rows = []
    for hid in sorted(HISTORY, reverse=True):  # newest first — ids only ever increase
        entry = HISTORY[hid]
        label = f"{entry.artist} — {entry.title}" if entry.artist else entry.title
        rows.append([InlineKeyboardButton(text=label[:60], callback_data=f"hist:{hid}")])
    await message.reply("Tap a track to get it again:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("hist:"))
async def handle_history_pick(callback: CallbackQuery) -> None:
    _, hid_str = callback.data.split(":", 1)
    await callback.answer()
    entry = HISTORY.get(int(hid_str))
    if not entry:
        await safe_edit_text(callback.message, "This entry is no longer available (too old).")
        return
    status = await callback.message.answer("Searching...")
    await ask_quality(status, entry.title, entry.artist, search_query=entry.search_query, coverart=entry.coverart, lyrics=entry.lyrics)


SPEED_TEXT_RE = re.compile(r"^\d+(\.\d+)?$")
MIN_TYPED_SPEED, MAX_TYPED_SPEED = 0.1, 3.0


@dp.message(F.text & ~F.text.startswith("/"))
async def handle_text_query(message: Message):
    _sweep_stale_deliveries()
    query = message.text.strip()

    # a bare number only means "exact speed for my last effect pick"
    # when there's actually a card waiting on a speed — otherwise (or if the
    # number is out of the sane 0.1-3.0 playback-speed range) it falls through
    # to the normal song-search path below, so a track literally titled "1999"
    # still searches normally.
    if SPEED_TEXT_RE.match(query) and LAST_SPEED_TOKEN and LAST_SPEED_TOKEN in DELIVERY:
        speed = round(float(query), 2)
        if MIN_TYPED_SPEED <= speed <= MAX_TYPED_SPEED and DELIVERY[LAST_SPEED_TOKEN].selected:
            status = await message.reply("Putting it together...")
            ok = await _generate_and_send(status, LAST_SPEED_TOKEN, speed)
            if not ok:
                await status.edit_text("This card expired, send the clip again.")
            return

    status = await message.reply(f"Searching: {query}...")

    if DIRECT_DOWNLOAD_RE.match(query):
        try:
            info = await asyncio.to_thread(_probe_media_url, query)
        except Exception:
            logging.exception("link probe failed for %r", query)
            await safe_edit_text(status, "Couldn't open that link — check that it's valid and the video/track is available.")
            return
        title = info.get("title") or query
        artist = info.get("uploader") or ""
        await ask_quality(status, title, artist, search_query=query)
        return

    if SPOTIFY_URL_RE.match(query) or APPLE_MUSIC_URL_RE.match(query):
        try:
            page_title = await asyncio.to_thread(_fetch_page_title, query)
        except Exception:
            logging.exception("page fetch failed for %r", query)
            page_title = None
        parsed = (_parse_spotify_title(page_title) or _parse_apple_music_title(page_title)) if page_title else None
        if not parsed:
            await safe_edit_text(status, "Couldn't read the track name from that link — send the name as text instead.")
            return
        title, artist = parsed
        await ask_quality(status, title, artist, search_query=f"{artist} {title}")
        return

    await ask_quality(status, query, "", search_query=query)


def preflight_check():
    # fail fast and clearly on config drift (reinstall, disk cleanup)
    # instead of a cryptic error the first time a user sends a clip.
    missing = [p for p in (FFMPEG_BIN, FFPROBE_BIN) if not os.path.exists(p)]
    if not os.path.exists(DENO_DIR):
        missing.append(DENO_DIR)
    if not os.path.exists(COOKIES_FILE):
        missing.append(COOKIES_FILE)
    if missing:
        raise SystemExit(f"Missing required file(s), fix before running the bot: {missing}")


async def main():
    preflight_check()
    await bot.set_my_commands([
        BotCommand(command="start", description="How to use this bot"),
        BotCommand(command="history", description="Recently identified tracks"),
        BotCommand(command="terms", description="Usage terms / disclaimer"),
    ])
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

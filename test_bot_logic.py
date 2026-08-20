# ponytail: self-check for bot.py's pure string/logic helpers — no network,
# no ffmpeg, no real Telegram token needed. bot.py requires BOT_TOKEN/
# FFMPEG_DIR/DENO_DIR just to import (module-level checks), so dummy values
# are set here before the import — none of the functions tested below ever
# touch them.
import os

os.environ.setdefault("BOT_TOKEN", "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
os.environ.setdefault("FFMPEG_DIR", os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DENO_DIR", os.path.dirname(os.path.abspath(__file__)))

from bot import _bucket, _looks_like_match, _parse_apple_music_title, _parse_spotify_title

# _bucket: rounds a precise speed down to its 0.1 bucket start
assert _bucket(0.5) == 0.5
assert _bucket(0.85) == 0.8
assert _bucket(0.99) == 0.9
assert _bucket(1.5) == 1.5
assert _bucket(1.23) == 1.2

# _looks_like_match: word-overlap sanity check against a wrong YouTube result
assert _looks_like_match("Tame Impala - The Less I Know The Better (Official Audio)", "Tame Impala The Less I Know The Better")
assert not _looks_like_match("Some Completely Different Song", "Tame Impala The Less I Know The Better")
assert _looks_like_match("anything at all", "")  # no target words -> nothing to reject

# _parse_spotify_title: scrapes artist/title out of Spotify's <title> tag
assert _parse_spotify_title("Blinding Lights - song by The Weeknd | Spotify") == ("Blinding Lights", "The Weeknd")
assert _parse_spotify_title("Song Title - song and lyrics by Artist Name | Spotify") == ("Song Title", "Artist Name")
assert _parse_spotify_title("Spotify - Web Player") is None

# _parse_apple_music_title: same idea for Apple Music's <title> format
assert _parse_apple_music_title("Blinding Lights - Song by The Weeknd - Apple Music") == ("Blinding Lights", "The Weeknd")
assert _parse_apple_music_title("Apple Music") is None

print("ok")

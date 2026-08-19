# Disclaimer

`music_shazam_bot` is a personal, non-commercial tool. It is not affiliated
with, endorsed by, or sponsored by Apple/Shazam, Spotify, YouTube, or
TikTok. All product names and trademarks belong to their respective owners.

## What it actually does

- Identifies audio using the public Shazam-compatible recognition service
  ([`shazamio`](https://github.com/dotX12/ShazamIO))
- Locates and downloads a matching copy of the identified track via
  `yt-dlp`, from sources that were already publicly available
- Applies audio effects/mastering locally and returns the result to the
  Telegram user who asked for it

It does not crack, strip, or bypass DRM, and does not host, index, or
redistribute a library of media — every result is generated on request, for
the requesting user, and nothing is retained beyond the in-memory
`/history` list of the running process.

## Access and responsibility

Access is gated by `ALLOWED_USER_IDS` in `.env` — only Telegram accounts the
operator explicitly allow-lists can use the bot at all; everyone else is
silently ignored (see `AllowlistMiddleware` in `bot.py`).

Whoever runs an instance of this bot (the "operator") is responsible for
making sure their own use — and the use of anyone they grant access to —
complies with copyright law and the terms of service of Shazam, YouTube,
TikTok, Spotify, and Apple Music in their own jurisdiction. This is
personal-use tooling, not a distribution platform, and is not intended for
commercial use, public/open access, or bulk downloading.

## No warranty

This software is provided "as is," without warranty of any kind. The
author(s) are not liable for any claim, damages, or other liability arising
from its use. See the code itself for exactly what it does — there is no
hidden behavior beyond what's in `bot.py`.

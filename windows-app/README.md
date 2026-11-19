# Shazam Desktop

[Download the Windows build](https://github.com/LizaVice/reverbot/releases/download/desktop-2026.11.19/ShazamDesktop.exe) · [Read the release notes](https://github.com/LizaVice/reverbot/releases/tag/desktop-2026.11.19)

## What it can do

- **Identify music and select a source.** Open a local audio or video file, search by track name, or paste a supported link. A selected local file is used directly for processing without a YouTube download. Track recognition and online lyrics lookup can still use the network.
- **Work with links.** YouTube and TikTok links can be opened directly. Spotify and Apple Music links provide track metadata for a matching search on YouTube.
- **Combine effects.** Choose Nightcore, Bass Boosted, 8D Audio, or **St Paul’s Atmospheric Hall**, which uses recorded impulse responses. Add one of three reverb presets per export. Use **Original** when you want no effects.
- **Adjust the export.** Set speed from **0.50× to 1.50×** in **0.01×** steps, choose **192 or 320 kbps**, apply up to **+12 dB** of volume boost with peak limiting, and optionally embed a **JPG or PNG** cover.
- **Read lyrics.** The app can use lyrics returned with recognition or look for a match in **LRCLIB** by title and artist. The Lyrics button (**Текст песни**) becomes available when lyrics are found. Lyrics lookup runs independently of the audio download.
- **Reuse tracks.** Open recent tracks from history. The app caches downloaded audio and saves finished files in the `output` folder next to the executable.

## Run on Windows

1. Install [FFmpeg](https://ffmpeg.org/download.html) (including `ffprobe`) and [Deno](https://deno.com/), and add both tools to your Windows PATH.
2. Download `ShazamDesktop.exe` and put it in a folder you can write to.
3. Launch the EXE, choose a track or a local file, select your effects and export settings, then click **Собрать** to export.

If YouTube temporarily blocks a download or asks for sign-in, you can still process a local file. The Windows executable is distributed through [GitHub Releases](https://github.com/LizaVice/reverbot/releases). This repository contains the Telegram bot source and deployment scripts.

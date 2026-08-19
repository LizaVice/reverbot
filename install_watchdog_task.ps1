$ErrorActionPreference = "Stop"
$botDir = $PSScriptRoot
$pyExe = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\pythonw.exe"
$watchdog = Join-Path $botDir "watchdog.py"

# Runs as the current user, only while logged in (no stored password needed,
# so this doesn't require an elevated PowerShell). ponytail: good enough for
# a personal desktop that's normally logged in; upgrade path if that's not
# true for you is /RU/<RP> with a saved password so it runs logged-out too.
$trArg = "`"$pyExe`" `"$watchdog`""
schtasks /create /tn "MusicShazamBotWatchdog" /tr $trArg /sc minute /mo 15 /f

Write-Output "Registered. Test it once manually:"
Write-Output "  schtasks /run /tn MusicShazamBotWatchdog"

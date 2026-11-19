$ErrorActionPreference = "Stop"
$nssm = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
$botDir = $PSScriptRoot
$pyExe = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"

# Secrets (BOT_TOKEN, optionally ALLOWED_USER_IDS) live in .env next to this
# script, NOT hardcoded here. .env is gitignored — never commit or share it.
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) {
    throw ".env not found at $envFile - create it with BOT_TOKEN=<your token> before installing the service."
}

$envVars = @{}
foreach ($line in Get-Content $envFile) {
    $trimmed = $line.Trim()
    if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
    $parts = $trimmed.Split("=", 2)
    if ($parts.Count -eq 2) {
        $envVars[$parts[0].Trim()] = $parts[1].Trim()
    }
}

if (-not $envVars.ContainsKey("BOT_TOKEN") -or [string]::IsNullOrWhiteSpace($envVars["BOT_TOKEN"])) {
    throw "BOT_TOKEN missing/empty in $envFile - the service needs it to start."
}

# Build the multi-line AppEnvironmentExtra value NSSM expects (one KEY=VALUE
# per line -> stored as REG_MULTI_SZ, injected into the service process env).
$envLines = $envVars.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }
$envExtra = $envLines -join "`n"

& $nssm remove MusicShazamBot confirm
& $nssm install MusicShazamBot $pyExe "-u bot.py"
& $nssm set MusicShazamBot AppDirectory $botDir
& $nssm set MusicShazamBot AppStdout "$botDir\bot.log"
& $nssm set MusicShazamBot AppStderr "$botDir\bot.log"
& $nssm set MusicShazamBot AppEnvironmentExtra $envExtra
& $nssm set MusicShazamBot Start SERVICE_AUTO_START
& $nssm set MusicShazamBot AppRestartDelay 3000
& $nssm start MusicShazamBot

Start-Sleep -Seconds 4
& $nssm status MusicShazamBot | Out-File "$botDir\service_install_result.txt"
Get-Process python -ErrorAction SilentlyContinue | Select-Object Id,StartTime | Out-File -Append "$botDir\service_install_result.txt"
"DONE" | Out-File -Append "$botDir\service_install_result.txt"

$ErrorActionPreference = "Stop"
$botDir = $PSScriptRoot
$pyDir = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312"
$ffmpegDir = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
$denoDir = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe"
$nssm = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
$outFile = Join-Path $botDir "setup_account_result.txt"
$acctName = "MusicShazamBotSvc"

"=== start ===" | Out-File $outFile
try {

# 1. Generate a strong random password and create the local account (or reset
# password if it already exists from a previous run).
$chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
$plainPassword = -join ((1..24) | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
$securePassword = ConvertTo-SecureString $plainPassword -AsPlainText -Force

$existing = Get-LocalUser -Name $acctName -ErrorAction SilentlyContinue
if ($existing) {
    Set-LocalUser -Name $acctName -Password $securePassword -PasswordNeverExpires $true
    "account already existed, password reset" | Out-File -Append $outFile
} else {
    New-LocalUser -Name $acctName -Password $securePassword -PasswordNeverExpires -AccountNeverExpires -Description "MusicShazamBot service account" | Out-Null
    "account created" | Out-File -Append $outFile
}

$sid = (Get-LocalUser -Name $acctName).SID.Value
"sid: $sid" | Out-File -Append $outFile

# 2. Grant "Log on as a service" right via secedit (no GUI snap-in needed, works on Home).
$cfgPath = "$env:TEMP\secpol_export2.cfg"
$dbPath = "$env:TEMP\secpol_import2.sdb"
secedit /export /cfg $cfgPath /quiet
$content = Get-Content $cfgPath
$found = $false
$newContent = $content | ForEach-Object {
    if ($_ -match '^SeServiceLogonRight\s*=\s*(.*)$') {
        $found = $true
        $existingRight = $matches[1]
        if ($existingRight -notmatch [regex]::Escape("*$sid")) {
            "SeServiceLogonRight = $existingRight,*$sid"
        } else { $_ }
    } else { $_ }
}
if (-not $found) {
    $newContent = $newContent | ForEach-Object {
        $_
        if ($_ -match '^\[Privilege Rights\]') { "SeServiceLogonRight = *$sid" }
    }
}
Set-Content -Path $cfgPath -Value $newContent -Encoding Unicode
secedit /configure /db $dbPath /cfg $cfgPath /quiet
"service logon right granted" | Out-File -Append $outFile

# 3. Grant read+execute on the directories the bot actually needs, full
# control only on its own project dir (needs to write bot.log/bot.pid/temp files).
icacls $botDir /grant "${acctName}:(OI)(CI)F" | Out-Null
icacls $pyDir /grant "${acctName}:(OI)(CI)RX" | Out-Null
icacls $ffmpegDir /grant "${acctName}:(OI)(CI)RX" | Out-Null
icacls $denoDir /grant "${acctName}:(OI)(CI)RX" | Out-Null
"acls granted" | Out-File -Append $outFile

# 4. Point the NSSM service at the new account.
& $nssm set MusicShazamBot ObjectName ".\$acctName" $plainPassword
"nssm ObjectName set" | Out-File -Append $outFile

# 5. Restart to apply.
Restart-Service -Name MusicShazamBot -Force
Start-Sleep -Seconds 4
$svc = Get-Service -Name MusicShazamBot
"service status: $($svc.Status)" | Out-File -Append $outFile
Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, StartTime | Out-File -Append $outFile
& $nssm get MusicShazamBot ObjectName | Out-File -Append $outFile
"=== done ===" | Out-File -Append $outFile

} catch {
    "=== ERROR ===" | Out-File -Append $outFile
    $_ | Out-String | Out-File -Append $outFile
    $_.ScriptStackTrace | Out-File -Append $outFile
}

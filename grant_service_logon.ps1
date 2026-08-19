$ErrorActionPreference = "Stop"
$sid = "S-1-5-21-2911866451-1798534887-2983103876-1001"
$cfgPath = "$env:TEMP\secpol_export.cfg"
$dbPath = "$env:TEMP\secpol_import.sdb"
$logPath = "$env:TEMP\secpol_import.log"

secedit /export /cfg $cfgPath /quiet
$content = Get-Content $cfgPath

$found = $false
$newContent = $content | ForEach-Object {
    if ($_ -match '^SeServiceLogonRight\s*=\s*(.*)$') {
        $found = $true
        $existing = $matches[1]
        if ($existing -notmatch [regex]::Escape("*$sid")) {
            "SeServiceLogonRight = $existing,*$sid"
        } else {
            $_
        }
    } else {
        $_
    }
}
if (-not $found) {
    # no existing line for this right - insert one right after [Privilege Rights]
    $newContent = $newContent | ForEach-Object {
        $_
        if ($_ -match '^\[Privilege Rights\]') {
            "SeServiceLogonRight = *$sid"
        }
    }
}
Set-Content -Path $cfgPath -Value $newContent -Encoding Unicode

secedit /configure /db $dbPath /cfg $cfgPath /quiet /log $logPath

"DONE" | Out-File "C:\Users\blood\DOWNLO~1\7B76~1\MUSIC_~1\grant_result.txt"
Get-Content $cfgPath | Select-String "SeServiceLogonRight" | Out-File -Append "C:\Users\blood\DOWNLO~1\7B76~1\MUSIC_~1\grant_result.txt"

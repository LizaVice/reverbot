@echo off
rem MOVED to unused\watchdog.bat - disabled here on purpose. The NSSM
rem service (install_service.ps1) handles restarts now; running this
rem alongside it risks a second bot process fighting over BOT_TOKEN/getUpdates.
echo This script has moved to unused\watchdog.bat and is disabled here on purpose.
exit /b 1

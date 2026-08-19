@echo off
rem MOVED to unused\supervisor.bat - this file is intentionally disabled to
rem avoid ever double-running the bot against the same BOT_TOKEN as the
rem NSSM service (install_service.ps1), which would fight over getUpdates.
rem The working copy (now reading BOT_TOKEN from ..\.env) lives in unused\.
echo This script has moved to unused\supervisor.bat and is disabled here on purpose.
echo Do not run it while the MusicShazamBot NSSM service is active.
exit /b 1

#!/bin/bash
# Applies a code edit: kills the running bot.py so supervisor.bat's loop
# (already running in the background, started at logon from the Startup
# folder) notices and relaunches it within ~3s, picking up the new code.
# Does NOT start python itself — that would race with the supervisor and
# produce two instances fighting over the same Telegram getUpdates session.
cd "$(dirname "$0")"

if [ -f bot.pid ]; then
    OLD_WINPID=$(cat bot.pid)
    taskkill //PID "$OLD_WINPID" //F 2>/dev/null && echo "killed winpid $OLD_WINPID, supervisor will relaunch it"
fi

# fallback in case the pidfile is stale/missing — match by command line so
# this doesn't accidentally kill an unrelated python.exe process.
STRAY=$(powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*bot.py*' } | Select-Object -ExpandProperty ProcessId" 2>/dev/null | tr -d '\r')
for WINPID in $STRAY; do
    taskkill //PID "$WINPID" //F 2>/dev/null && echo "killed stray winpid $WINPID"
done

sleep 4
echo "--- tail of bot.log ---"
tail -6 bot.log

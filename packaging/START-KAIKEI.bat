@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist "runtime\python\python.exe" (
  echo [ERROR] runtime\python\python.exe was not found.
  echo The package may be incomplete. Please extract the whole ZIP again.
  pause
  exit /b 1
)
echo Starting kAIkei. The browser will open automatically.
echo Keep this window open while using kAIkei. Close it to stop.
runtime\python\python.exe -u launch.py > kaikei-run.log 2>&1
set RC=%ERRORLEVEL%
echo.
echo kAIkei has stopped. Exit code: %RC%
echo ----- kaikei-run.log -----
type kaikei-run.log
echo --------------------------
pause

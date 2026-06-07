@echo off
cd /d "%~dp0"
echo.
echo ========================================
echo   Claude Code WebUI Starting...
echo ========================================

REM Check if MCP already running
netstat -an 2>nul | find ":5173 " >nul
if %errorlevel%==0 (
    echo [1/2] MCP Sessions already running on port 5173
) else (
    echo [1/2] Starting MCP Sessions (port 5173)...
    start "MCP Sessions" /MIN cmd /c "cd /d \"%~dp0\" && node node_modules/@claude-sessions/web/dist/cli.js --port 5173"
)

echo [2/2] Starting WebUI server (port 19876)...
echo.
echo   Browser will open automatically.
echo   Close this window to stop all services.
echo.
python server.py
taskkill /FI "WINDOWTITLE eq MCP Sessions" /F 2>nul
pause

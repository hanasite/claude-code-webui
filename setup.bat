@echo off
chcp 65001 >nul
echo.
echo ╔══════════════════════════════════════╗
echo ║  Claude Code 对话管理 WebUI 部署  ║
echo ╚══════════════════════════════════════╝
echo.

:: 1. Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装: https://python.org
    pause
    exit /b 1
)
echo [1/3] Python 已就绪:
python --version 2>&1

:: 2. Install Flask
echo [2/3] 安装 Flask...
pip install flask -q 2>&1
if %errorlevel% neq 0 (
    echo [警告] Flask 安装失败，尝试使用镜像...
    pip install flask -q -i https://pypi.tuna.tsinghua.edu.cn/simple 2>&1
)
echo        Flask 已就绪

:: 3. Create desktop shortcut
echo [3/3] 创建桌面快捷方式...
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $sc = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Claude Code WebUI.lnk'); ^
   $sc.TargetPath = '%~dp0start.bat'; ^
   $sc.WorkingDirectory = '%~dp0'; ^
   $sc.IconLocation = 'powershell.exe,0'; ^
   $sc.Description = 'Claude Code 对话管理 WebUI'; ^
   $sc.Save()" 2>&1
echo       桌面快捷方式已创建

echo.
echo ╔══════════════════════════════════════╗
echo ║  ✅ 部署完成！                      ║
echo ║                                    ║
echo ║  桌面快捷方式: Claude Code WebUI   ║
echo ║  或直接访问: http://127.0.0.1:19876 ║
echo ╚══════════════════════════════════════╝
echo.
echo 正在启动 WebUI...

:: 4. Launch
start "" pythonw "%~dp0server.py" --no-browser
timeout /t 3 >nul
start "" http://127.0.0.1:19876

pause

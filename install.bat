@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Cai dat thu vien ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || goto :err
echo === Cai trinh duyet Chromium cho Playwright ===
python -m playwright install chromium || goto :err
echo.
echo Cai dat xong! Chay file run.bat de mo ung dung.
pause
exit /b 0
:err
echo Co loi khi cai dat. Kiem tra da cai Python 3.10+ va tick "Add Python to PATH".
pause

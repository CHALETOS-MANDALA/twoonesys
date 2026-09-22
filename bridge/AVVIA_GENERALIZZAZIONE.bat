@echo off
cd /d "%~dp0.."
echo === GENERALIZZAZIONE mondo reale (n=24, pre-registrata) ===
echo Serve engine :8017
python bridge\generalizzazione_run.py
echo.
pause

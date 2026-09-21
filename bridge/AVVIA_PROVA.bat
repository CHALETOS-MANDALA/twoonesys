@echo off
chcp 65001 >nul
cd /d "%~dp0.."

echo.
echo === TWOONESYS — prova tu nel mondo reale ===
echo Serve l'engine su :8017 (AVVIA_ENGINE.bat in un'altra finestra).
echo.

python bridge\prova_tu.py
echo.
pause

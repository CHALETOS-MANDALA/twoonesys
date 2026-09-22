@echo off
cd /d "%~dp0.."
echo === TWOONESYS Gate :8018 (per SIX-IDE) ===
echo Engine :8017 consigliato in altra finestra (AVVIA_ENGINE.bat).
python bridge\six_gate_server.py
pause

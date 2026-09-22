@echo off
cd /d "%~dp0.."
echo.
echo === TWOONESYS E2E — conoscenza + tecnologia ===
echo Serve engine :8017 (AVVIA_ENGINE.bat in altra finestra se non gia pronto).
echo.
python bridge\e2e_chiudi.py
echo.
pause

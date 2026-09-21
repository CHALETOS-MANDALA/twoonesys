@echo off
chcp 65001 >nul
cd /d "%~dp0.."

echo.
echo === TWOONESYS engine (4B Q8) su :8017 ===
echo Se Ollama sta usando la GPU, fermalo prima:  ollama stop ^<modello^>
echo.

cd engine
uv run rizzo serve --size 4b --bits 8
pause

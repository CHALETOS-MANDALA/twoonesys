@echo off
cd /d "%~dp0.."
cd engine
uv run rizzo serve --size 4b --bits 8
pause

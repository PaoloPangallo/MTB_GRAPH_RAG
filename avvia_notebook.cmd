@echo off
cd /d "%~dp0"
echo Attivazione del virtual environment...
call .venv\Scripts\activate.bat
echo Avvio di Jupyter Lab...
call jupyter lab
pause

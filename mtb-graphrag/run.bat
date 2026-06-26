@echo off
title MTB GraphRAG Launcher
echo ===================================================
echo   MTB GraphRAG - Avvio Backend e Frontend
echo ===================================================
echo.

:: Imposta la directory di lavoro sul percorso dello script
set PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"

:: Avvio Backend in una nuova finestra
echo [1/2] Avvio del server Backend (FastAPI)...
start "MTB GraphRAG Backend" cmd /k "title MTB Backend && set PYTHONPATH=%PROJECT_DIR%&& ..\.venv\Scripts\python.exe -m uvicorn backend.api.main:app --reload --port 8000"

:: Attendi 2 secondi prima di avviare il frontend per dare tempo al backend di partire
timeout /t 2 /nobreak >nul

:: Avvio Frontend in una nuova finestra
echo [2/2] Avvio del server Frontend (React + Vite)...
cd frontend
start "MTB GraphRAG Frontend" cmd /k "title MTB Frontend && npm run dev"

echo.
echo ===================================================
echo   Entrambi i server sono stati avviati!
echo   - Backend: http://localhost:8000
echo   - Frontend: Controlla la finestra del frontend per l'URL (solitamente http://localhost:5173)
echo ===================================================
echo.
pause

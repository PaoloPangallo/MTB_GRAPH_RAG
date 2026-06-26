# MTB GraphRAG PowerShell Launcher

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  MTB GraphRAG - Avvio Backend e Frontend" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrEmpty($ProjectDir)) {
    $ProjectDir = Get-Location
}

# Imposta PYTHONPATH
$env:PYTHONPATH = $ProjectDir

# Avvia il Backend in una nuova finestra PowerShell
Write-Host "[1/2] Avvio del server Backend (FastAPI)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle = 'MTB Backend'; cd '$ProjectDir'; `$env:PYTHONPATH = '$ProjectDir'; ..\.venv\Scripts\python.exe -m uvicorn backend.api.main:app --reload --port 8000"

# Attendi 2 secondi
Start-Sleep -Seconds 2

# Avvia il Frontend in una nuova finestra PowerShell
Write-Host "[2/2] Avvio del server Frontend (React + Vite)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle = 'MTB Frontend'; cd '$ProjectDir\frontend'; npm run dev"

Write-Host ""
Write-Host "===================================================" -ForegroundColor Green
Write-Host "  Entrambi i server sono stati avviati!" -ForegroundColor Green
Write-Host "  - Backend: http://localhost:8000" -ForegroundColor Green
Write-Host "  - Frontend: Controlla la nuova finestra per l'indirizzo" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Green
Write-Host ""

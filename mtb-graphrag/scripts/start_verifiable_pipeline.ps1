<#!
.SYNOPSIS
    Avvia backend e frontend della Verifiable Research Pipeline in modalità LIVE.

.DESCRIPTION
    La pipeline live richiede tre cose che il launcher di prodotto non imposta:
    il flag del research runtime, il percorso della cache documentale e
    l'endpoint del modello. Senza la cache una run LIVE si ferma allo stage 6 con
    DOCUMENT_CACHE_UNAVAILABLE — deliberatamente, perché non ripiega su artefatti
    registrati.

    Il frontend riceve VITE_API_BASE_URL: senza, punta a localhost:8000, che di
    norma ospita un backend diverso e possibilmente più vecchio. È l'origine più
    comune di errori che sembrano difetti della pipeline e sono disallineamenti
    di processo.

    NON è un runtime clinico validato. Nessun endpoint di prodotto viene toccato.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\start_verifiable_pipeline.ps1 `
        -DocumentCachePath 'C:\percorso\data_cache\document_grounding'

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\start_verifiable_pipeline.ps1 -CheckOnly
#>

[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8010,

    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 5180,

    # Cache documentale autorizzata. Fuori dal repository: contiene testo di terzi.
    [string]$DocumentCachePath = $env:RESEARCH_DOCUMENT_CACHE_PATH,

    # Ollama locale come proxy autenticato verso Ollama Cloud, come nel pilot.
    [string]$LlmBaseUrl = 'http://localhost:11434',

    [string]$Model = 'gemma4:cloud',

    [ValidateRange(5, 300)]
    [int]$StartupTimeoutSeconds = 60,

    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root 'logs'

function Write-Step($message) { Write-Host "  $message" }

Write-Host ''
Write-Host 'VERIFIABLE RESEARCH PIPELINE - NOT CLINICALLY VALIDATED'
Write-Host ''

# --- Prerequisiti -----------------------------------------------------------

Write-Host 'Prerequisiti'

if (-not $DocumentCachePath) {
    Write-Step 'cache documentale : NON CONFIGURATA'
    Write-Host ''
    Write-Host 'Passa -DocumentCachePath oppure imposta RESEARCH_DOCUMENT_CACHE_PATH.'
    Write-Host 'Senza cache le run LIVE falliscono con DOCUMENT_CACHE_UNAVAILABLE'
    Write-Host 'invece di ripiegare sul replay. La modalita REPLAY resta usabile.'
    Write-Host ''
}
elseif (Test-Path -LiteralPath $DocumentCachePath) {
    $documents =
        @(Get-ChildItem -LiteralPath $DocumentCachePath -Recurse -File -ErrorAction SilentlyContinue).Count
    Write-Step "cache documentale : OK ($documents file)"
}
else {
    Write-Step "cache documentale : PERCORSO INESISTENTE ($DocumentCachePath)"
}

# gemma4:cloud e' un modello cloud servito attraverso l'app Ollama locale: non
# compare in `ollama list` finche' non e' stato usato, quindi si interroga
# direttamente il resolver invece di cercarlo nell'elenco.
try {
    $body = @{ model = $Model } | ConvertTo-Json -Compress
    $null = Invoke-RestMethod -Uri "$LlmBaseUrl/api/show" -Method Post -Body $body `
        -ContentType 'application/json' -TimeoutSec 15
    Write-Step "modello           : OK ($Model via $LlmBaseUrl)"
}
catch {
    Write-Step "modello           : NON RAGGIUNGIBILE ($Model via $LlmBaseUrl)"
    Write-Host '    Avvia l app Ollama, oppure punta -LlmBaseUrl a https://api.ollama.com'
    Write-Host '    con OLLAMA_API_KEY impostata.'
}

foreach ($port in @($BackendPort, $FrontendPort)) {
    $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($busy) {
        Write-Step "porta $port      : GIA IN USO (pid $($busy[0].OwningProcess))"
    }
}

if ($CheckOnly) {
    Write-Host ''
    Write-Host 'Solo verifica: nessun processo avviato.'
    return
}

# --- Avvio ------------------------------------------------------------------

if (-not (Test-Path -LiteralPath $logDir)) {
    $null = New-Item -ItemType Directory -Path $logDir
}

$env:VERIFIABLE_PIPELINE_RESEARCH_ENABLED = '1'
$env:RESEARCH_PIPELINE_LLM_BASE_URL = $LlmBaseUrl
$env:RESEARCH_PIPELINE_MODEL = $Model
if ($DocumentCachePath) {
    $env:RESEARCH_DOCUMENT_CACHE_PATH = $DocumentCachePath
}

Write-Host ''
Write-Host 'Avvio'

$backend = Start-Process -PassThru -NoNewWindow -WorkingDirectory $root `
    -FilePath 'python' `
    -ArgumentList @('-m', 'uvicorn', 'backend.api.main:app',
                    '--host', '127.0.0.1', '--port', $BackendPort, '--log-level', 'warning') `
    -RedirectStandardOutput (Join-Path $logDir 'verifiable_backend.out.log') `
    -RedirectStandardError  (Join-Path $logDir 'verifiable_backend.err.log')
Write-Step "backend  : pid $($backend.Id) su http://127.0.0.1:$BackendPort"

$healthy = $false
$deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    try {
        $config = Invoke-RestMethod -TimeoutSec 3 `
            -Uri "http://127.0.0.1:$BackendPort/api/v1/research/pipeline/config"
        $healthy = $true
        break
    }
    catch { Start-Sleep -Milliseconds 500 }
}

if (-not $healthy) {
    Write-Step 'backend  : NON RISPONDE - vedi logs\verifiable_backend.err.log'
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    return
}

$cacheState = if ($config.document_cache.document_cache_available) { 'AVAILABLE' } else { 'UNAVAILABLE' }
Write-Step "cache    : $cacheState ($($config.document_cache.document_count) documenti, $($config.document_cache.source_unit_count) source unit)"
Write-Step "modello  : $($config.llm.model)"

# Il frontend deve puntare a QUESTO backend. Senza questa variabile userebbe
# localhost:8000 e mostrerebbe gli esiti di un processo diverso.
$env:VITE_API_BASE_URL = "http://127.0.0.1:$BackendPort"

$frontend = Start-Process -PassThru -NoNewWindow `
    -WorkingDirectory (Join-Path $root 'frontend') `
    -FilePath 'npx' `
    -ArgumentList @('vite', '--port', $FrontendPort, '--strictPort') `
    -RedirectStandardOutput (Join-Path $logDir 'verifiable_frontend.out.log') `
    -RedirectStandardError  (Join-Path $logDir 'verifiable_frontend.err.log')
Write-Step "frontend : pid $($frontend.Id) su http://localhost:$FrontendPort"

Write-Host ''
Write-Host "  Console: http://localhost:$FrontendPort/research/verifiable-pipeline"
Write-Host '  Ctrl+C per terminare entrambi i processi.'
Write-Host ''

try {
    while (-not $backend.HasExited -and -not $frontend.HasExited) { Start-Sleep -Seconds 1 }
}
finally {
    foreach ($process in @($backend, $frontend)) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Host 'Processi terminati.'
}

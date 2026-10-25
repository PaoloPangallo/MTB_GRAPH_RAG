<#
.SYNOPSIS
    Avvia il runtime finale MTB GraphRAG dal worktree relation-aware canonico.

.DESCRIPTION
    Avvia backend e frontend dal progetto accanto a questo script. Il launcher
    puo' anche essere usato dal checkout di valutazione, nel qual caso cerca il
    worktree relation-aware canonico come checkout fratello.

    Prima dell'avvio il launcher verifica le versioni attese di Case Parser,
    Paper Context Enricher e Narrator. Un checkout di valutazione o una copia
    parzialmente aggiornata non puo' quindi essere avviata per errore come
    pipeline finale.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\run.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\run.ps1 -CheckOnly
#>

[CmdletBinding()]
param(
    [string]$DocumentCachePath = $env:RESEARCH_DOCUMENT_CACHE_PATH,

    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,

    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 5173,

    [switch]$AllowRetrievalFallback,

    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'

Write-Host '===================================================' -ForegroundColor Cyan
Write-Host '  MTB GraphRAG - Runtime relation-aware finale' -ForegroundColor Cyan
Write-Host '===================================================' -ForegroundColor Cyan
Write-Host ''

$LauncherProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($LauncherProjectDir)) {
    $LauncherProjectDir = (Get-Location).Path
}
$LauncherProjectDir = (Resolve-Path -LiteralPath $LauncherProjectDir).Path

$ProjectDir = $LauncherProjectDir
if (-not (Test-Path -LiteralPath (Join-Path $ProjectDir 'backend\api\main.py') -PathType Leaf)) {
    # Compatibilita' con il vecchio launcher conservato nel checkout di
    # valutazione: usa il worktree canonico solo se lo script non e' gia' li'.
    $desktopDir = Split-Path -Parent (Split-Path -Parent $LauncherProjectDir)
    $siblingProject = Join-Path $desktopDir 'mtb-relation-aware-core\mtb-graphrag'
    if (Test-Path -LiteralPath (Join-Path $siblingProject 'backend\api\main.py') -PathType Leaf) {
        $ProjectDir = $siblingProject
    }
    else {
        throw "Backend non trovato accanto a run.ps1 e worktree canonico non trovato: $siblingProject"
    }
}
$ProjectDir = (Resolve-Path -LiteralPath $ProjectDir).Path

# Le variabili sono caricate nel processo del launcher e passate ai processi
# figli. Il contenuto del file non viene mai stampato.
$EnvFilePath = $env:MTB_GRAPHRAG_ENV_FILE
if ([string]::IsNullOrWhiteSpace($EnvFilePath)) {
    $envCandidates = @(
        (Join-Path (Split-Path -Parent $ProjectDir) '.env'),
        (Join-Path $ProjectDir '.env'),
        (Join-Path (Split-Path -Parent $LauncherProjectDir) '.env'),
        (Join-Path $LauncherProjectDir '.env')
    ) | Select-Object -Unique
    $EnvFilePath = $envCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
if (-not (Test-Path -LiteralPath $EnvFilePath -PathType Leaf)) {
    throw 'File .env non trovato. Crea mtb-graphrag/.env o imposta MTB_GRAPHRAG_ENV_FILE.'
}

foreach ($line in Get-Content -LiteralPath $EnvFilePath) {
    $trimmed = $line.Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith('#')) {
        continue
    }
    if ($trimmed -match '^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $name = $matches[1]
        $value = $matches[2].Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}

if ([string]::IsNullOrWhiteSpace($env:OLLAMA_API_KEY) -and [string]::IsNullOrWhiteSpace($env:RESEARCH_PIPELINE_LLM_API_KEY)) {
    throw 'Credenziale LLM assente: configura OLLAMA_API_KEY o RESEARCH_PIPELINE_LLM_API_KEY nel file .env.'
}

# La cache documentale contiene testi di terzi. Riusa prima quella del runtime,
# poi quella del checkout da cui potrebbe essere stato richiamato il launcher.
if ([string]::IsNullOrWhiteSpace($DocumentCachePath)) {
    $cacheCandidates = @(
        (Join-Path $ProjectDir 'data_cache\document_grounding'),
        (Join-Path $LauncherProjectDir 'data_cache\document_grounding')
    ) | Select-Object -Unique
    $DocumentCachePath = $cacheCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Container } | Select-Object -First 1
}
if (-not (Test-Path -LiteralPath $DocumentCachePath -PathType Container)) {
    throw "Cache documentale autorizzata non trovata: $DocumentCachePath"
}
$DocumentCachePath = (Resolve-Path -LiteralPath $DocumentCachePath).Path

$contracts = @(
    @{
        Name = 'Case Parser'
        File = 'backend\research_pipeline\casecontext\prompt.py'
        Expected = 'casecontext-parser-prompt'
    },
    @{
        Name = 'Paper Context Enricher'
        File = 'backend\research_pipeline\enrichment\prompt_v3.py'
        Expected = 'paper-context-enricher-prompt'
    },
    @{
        Name = 'Narrator'
        File = 'backend\research_pipeline\narrative\prompt.py'
        Expected = 'dossier-narrator-prompt'
    }
)

Write-Host 'Runtime selezionato' -ForegroundColor Yellow
Write-Host "  $ProjectDir"
Write-Host "  Configurazione: $EnvFilePath"
Write-Host ''
Write-Host 'Contratti LLM' -ForegroundColor Yellow

foreach ($contract in $contracts) {
    $contractPath = Join-Path $ProjectDir $contract.File
    if (-not (Test-Path -LiteralPath $contractPath -PathType Leaf)) {
        throw "$($contract.Name): file non trovato ($contractPath)"
    }

    $contractSource = Get-Content -Raw -LiteralPath $contractPath
    if ($contractSource -notmatch [regex]::Escape($contract.Expected)) {
        throw "$($contract.Name): atteso $($contract.Expected), runtime non coerente"
    }

    Write-Host "  $($contract.Name): $($contract.Expected)" -ForegroundColor Green
}

# Permette di scegliere esplicitamente l'interprete senza cablare un ambiente
# virtuale specifico. In assenza della variabile, prova gli ambienti locali e
# infine il Python disponibile nel PATH.
$pythonCandidates = @()
if (-not [string]::IsNullOrWhiteSpace($env:MTB_GRAPHRAG_PYTHON)) {
    if (-not (Test-Path -LiteralPath $env:MTB_GRAPHRAG_PYTHON -PathType Leaf)) {
        throw 'MTB_GRAPHRAG_PYTHON indica un interprete inesistente.'
    }
    $pythonCandidates += $env:MTB_GRAPHRAG_PYTHON
}
$pythonCandidates += Join-Path (Split-Path -Parent $ProjectDir) '.venv\Scripts\python.exe'
$pythonCandidates += Join-Path (Split-Path -Parent $LauncherProjectDir) '.venv\Scripts\python.exe'
$pythonCandidates += Join-Path $ProjectDir '.venv\Scripts\python.exe'

$pathPython = Get-Command python -ErrorAction SilentlyContinue
if ($pathPython) {
    $pythonCandidates += $pathPython.Source
}

$PythonExe = $pythonCandidates |
    Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
    Select-Object -First 1

if (-not $PythonExe) {
    throw 'Interprete Python non trovato. Imposta MTB_GRAPHRAG_PYTHON con il percorso di python.exe.'
}
$PythonExe = (Resolve-Path -LiteralPath $PythonExe).Path

$frontendDir = Join-Path $ProjectDir 'frontend'
$viteCmd = Join-Path $frontendDir 'node_modules\.bin\vite.cmd'
if (-not (Test-Path -LiteralPath $viteCmd -PathType Leaf)) {
    throw "Vite non installato nel frontend ($viteCmd). Esegui 'npm ci' nella cartella frontend e rilancia run.ps1."
}

Write-Host ''
Write-Host 'Prerequisiti' -ForegroundColor Yellow
Write-Host "  Python: $PythonExe" -ForegroundColor Green
Write-Host "  Vite:   $viteCmd" -ForegroundColor Green
Write-Host '  Credenziali LLM: configurate' -ForegroundColor Green

# Usa il validatore del runtime finale: l'esistenza della directory da sola non
# garantisce manifest, payload e layout coerenti.
$env:PYTHONPATH = $ProjectDir
$env:RESEARCH_DOCUMENT_CACHE_PATH = $DocumentCachePath
$strategy = if ($env:RESEARCH_PIPELINE_SOURCEUNIT_STRATEGY) { $env:RESEARCH_PIPELINE_SOURCEUNIT_STRATEGY.Trim() } else { 'RRF_STRUCTURE_MEDCPT' }
if ($strategy -eq 'RRF_STRUCTURE_MEDCPT') {
    $medcptProbe = & $PythonExe -m backend.research_pipeline.retrieval.medcpt_preflight
    $medcptExit = $LASTEXITCODE
    $medcptState = $medcptProbe | ConvertFrom-Json
    if ($medcptExit -ne 0 -or -not $medcptState.ready) {
        $message = "MedCPT non pronto: $($medcptState.error). Usa MTB_GRAPHRAG_PYTHON per scegliere l'ambiente corretto oppure installa backend/config/requirements-medcpt.txt con quell'interprete."
        if (-not $AllowRetrievalFallback) { throw $message }
        Write-Warning "$message Avvio autorizzato con possibile fallback tracciato BM25_STRUCTURE."
    }
    else {
        Write-Host "  MedCPT: checkpoint e tokenizer locali verificati; torch $($medcptState.versions.torch), transformers $($medcptState.versions.transformers)" -ForegroundColor Green
    }
}
elseif ($strategy -ne 'BM25_STRUCTURE') {
    throw "Strategia retrieval non valida: $strategy"
}
Write-Host "  Retrieval richiesto: $strategy" -ForegroundColor Green
$cacheProbe = & $PythonExe -c 'from backend.research_pipeline.documents.cache_runtime import describe; import json; print(json.dumps(describe().to_dict()))'
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($cacheProbe)) {
    throw 'Impossibile validare la cache documentale con il runtime relation-aware.'
}
$cacheState = $cacheProbe | ConvertFrom-Json
if (-not $cacheState.document_cache_available) {
    $cacheReasons = ($cacheState.reason_codes -join ', ')
    throw "Cache documentale non utilizzabile: $cacheReasons"
}
Write-Host "  Cache:  $DocumentCachePath" -ForegroundColor Green
Write-Host "          $($cacheState.document_count) documenti, $($cacheState.source_unit_count) SourceUnit" -ForegroundColor Green

if ($CheckOnly) {
    Write-Host ''
    Write-Host 'CHECK PASSED - nessun processo avviato.' -ForegroundColor Green
    return
}

function Get-AvailablePort([int]$PreferredPort) {
    $port = $PreferredPort
    while ($port -le 65535) {
        $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
        if ($listeners.Port -notcontains $port) {
            if ($port -ne $PreferredPort) {
                Write-Host "  Porta $PreferredPort occupata; usero' $port." -ForegroundColor Yellow
            }
            return $port
        }
        $port++
    }
    throw "Nessuna porta libera trovata a partire da $PreferredPort."
}

$BackendPort = Get-AvailablePort $BackendPort
$FrontendPort = Get-AvailablePort $FrontendPort
if ($FrontendPort -eq $BackendPort) {
    $FrontendPort = Get-AvailablePort ($BackendPort + 1)
}

function ConvertTo-SingleQuotedPowerShellLiteral([string]$Value) {
    return "'$($Value.Replace("'", "''"))'"
}

$quotedProjectDir = ConvertTo-SingleQuotedPowerShellLiteral $ProjectDir
$quotedPythonExe = ConvertTo-SingleQuotedPowerShellLiteral $PythonExe
$quotedViteCmd = ConvertTo-SingleQuotedPowerShellLiteral $viteCmd
$backendUrl = "http://127.0.0.1:$BackendPort"
$frontendUrl = "http://127.0.0.1:$FrontendPort"

$env:VERIFIABLE_PIPELINE_RESEARCH_ENABLED = '1'
$env:RESEARCH_NARRATOR_ENABLED = '1'
$env:CORS_ORIGINS = "http://localhost:$FrontendPort,http://127.0.0.1:$FrontendPort"
$env:PYTHONPATH = $ProjectDir
$env:RESEARCH_DOCUMENT_CACHE_PATH = $DocumentCachePath
$env:VITE_API_BASE_URL = $backendUrl

$backendCommand = @"
`$Host.UI.RawUI.WindowTitle = 'MTB Backend - relation-aware'
Set-Location -LiteralPath $quotedProjectDir
& $quotedPythonExe -m uvicorn backend.api.main:app --reload --host 127.0.0.1 --port $BackendPort
"@

Write-Host ''
Write-Host '[1/2] Avvio Backend relation-aware...' -ForegroundColor Yellow
Start-Process powershell -ArgumentList @('-NoExit', '-Command', $backendCommand)

$quotedFrontendDir = ConvertTo-SingleQuotedPowerShellLiteral (Join-Path $ProjectDir 'frontend')
$frontendCommand = @"
`$Host.UI.RawUI.WindowTitle = 'MTB Frontend - relation-aware'
Set-Location -LiteralPath $quotedFrontendDir
& $quotedViteCmd --host 127.0.0.1 --port $FrontendPort --strictPort
"@

Write-Host '[2/2] Avvio Frontend relation-aware...' -ForegroundColor Yellow
Start-Process powershell -ArgumentList @('-NoExit', '-Command', $frontendCommand)

# Aspetta gli endpoint locali e non dichiara l'avvio riuscito solo perche' le
# finestre dei processi figli sono state aperte. Nessuna richiesta esce dal PC.
$backendReady = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $null = Invoke-RestMethod -Uri "$backendUrl/health" -TimeoutSec 2
        $backendReady = $true
        break
    }
    catch { Start-Sleep -Seconds 1 }
}
if (-not $backendReady) {
    throw "Backend non risponde su $backendUrl/health. Controlla la finestra MTB Backend."
}

$frontendReady = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $response = Invoke-WebRequest -Uri $frontendUrl -TimeoutSec 2 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            $frontendReady = $true
            break
        }
    }
    catch { Start-Sleep -Seconds 1 }
}
if (-not $frontendReady) {
    throw "Frontend non risponde su $frontendUrl. Controlla la finestra MTB Frontend."
}

Write-Host ''
Write-Host '===================================================' -ForegroundColor Green
Write-Host '  Runtime relation-aware avviato' -ForegroundColor Green
Write-Host "  Backend: $backendUrl" -ForegroundColor Green
Write-Host "  Frontend: $frontendUrl" -ForegroundColor Green
Write-Host "  Console: $frontendUrl/research/verifiable-pipeline" -ForegroundColor Green
Write-Host "  Architettura: $frontendUrl/architecture" -ForegroundColor Green
Write-Host '===================================================' -ForegroundColor Green
Write-Host ''

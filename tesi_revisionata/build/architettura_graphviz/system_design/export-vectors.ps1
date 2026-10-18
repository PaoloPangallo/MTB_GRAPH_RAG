param([string]$Graphviz = 'C:\Program Files\Graphviz\bin\dot.exe')
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Graphviz)) { throw 'Indicare il percorso di Graphviz con -Graphviz.' }
Push-Location $PSScriptRoot
try {
    node build.cjs
    if ($LASTEXITCODE -ne 0) { throw 'Generazione degli approfondimenti fallita.' }
    $detailFiles = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'figure') -Filter '*.dot' | Sort-Object Name
    foreach ($figure in $detailFiles) {
        & $Graphviz -Tsvg $figure.FullName -o ([IO.Path]::ChangeExtension($figure.FullName, '.svg'))
        if ($LASTEXITCODE -ne 0) { throw "Esportazione SVG fallita: $($figure.Name)" }
        & $Graphviz -Tpdf $figure.FullName -o ([IO.Path]::ChangeExtension($figure.FullName, '.pdf'))
        if ($LASTEXITCODE -ne 0) { throw "Esportazione PDF fallita: $($figure.Name)" }
    }
    node macro-build.cjs
    if ($LASTEXITCODE -ne 0) { throw 'Generazione dei sorgenti fallita.' }
    $vectorFiles = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'figure/macrofasi') -Filter '*.dot' | Sort-Object Name
    foreach ($figure in $vectorFiles) {
        & $Graphviz -Tsvg $figure.FullName -o ([IO.Path]::ChangeExtension($figure.FullName, '.svg'))
        if ($LASTEXITCODE -ne 0) { throw "Esportazione SVG fallita: $($figure.Name)" }
        & $Graphviz -Tpdf $figure.FullName -o ([IO.Path]::ChangeExtension($figure.FullName, '.pdf'))
        if ($LASTEXITCODE -ne 0) { throw "Esportazione PDF fallita: $($figure.Name)" }
    }
    node path-build.cjs
    if ($LASTEXITCODE -ne 0) { throw 'Generazione dei percorsi fallita.' }
    Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'figure/percorsi') -Filter '*.dot' | ForEach-Object {
        & $Graphviz -Tsvg $_.FullName -o ([IO.Path]::ChangeExtension($_.FullName, '.svg'))
        if ($LASTEXITCODE -ne 0) { throw "Esportazione SVG fallita: $($_.Name)" }
        & $Graphviz -Tpdf $_.FullName -o ([IO.Path]::ChangeExtension($_.FullName, '.pdf'))
        if ($LASTEXITCODE -ne 0) { throw "Esportazione PDF fallita: $($_.Name)" }
    }
    python build-brief.py
    if ($LASTEXITCODE -ne 0) { throw 'Composizione della versione breve fallita.' }
    $delivery = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../../output/pdf/architettura'))
    New-Item -ItemType Directory -Path $delivery -Force | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'figure/macrofasi') -Filter '*.pdf' | Copy-Item -Destination $delivery
    $detailDelivery = Join-Path $delivery 'approfondimenti'
    New-Item -ItemType Directory -Path $detailDelivery -Force | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'figure') -Filter '*.pdf' | Copy-Item -Destination $detailDelivery
    @'
import sys, json
from pathlib import Path
from pypdf import PdfReader, PdfWriter
base = Path(sys.argv[1])
writer = PdfWriter()
for name in ['macro-caso','macro-recupero','macro-fonti','rrf','macro-verifiche','macro-dossier','macro-presentazione']:
    writer.append(PdfReader(base / (name + '.pdf')))
writer.write(base / 'Schemi_architettura.pdf')
writer = PdfWriter()
source = Path(sys.argv[2])
for row in json.loads((source / 'presenter-content.json').read_text(encoding='utf-8'))['rows']:
    writer.append(PdfReader(source / 'figure' / (row['id'] + '.pdf')))
writer.write(base / 'Approfondimenti_architettura.pdf')
'@ | python - $delivery $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { throw 'Raccolta PDF fallita.' }
    python build-gca-audit.py
    python build-prompts.py --graphviz $Graphviz
    if ($LASTEXITCODE -ne 0) { throw 'Esportazione guida prompt fallita' }
    if ($LASTEXITCODE -ne 0) { throw 'Audit GCA fallito.' }
    node build.cjs --assemble
    if ($LASTEXITCODE -ne 0) { throw 'Assemblaggio HTML fallito.' }
} finally { Pop-Location }

param(
    [string]$Python = "",
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $projectRoot "venv\Scripts\python.exe" }
if (-not $Destination) { $Destination = Join-Path $projectRoot ".sandbox\wheels" }
$requirementsPath = Join-Path $PSScriptRoot "requirements-qt-sandbox.txt"

& $Python -m pip download `
    --platform manylinux_2_28_x86_64 `
    --platform manylinux2014_x86_64 `
    --platform manylinux_2_17_x86_64 `
    --python-version 3.10 --implementation cp `
    --abi cp310 --abi abi3 --abi none --only-binary=:all: `
    --dest $Destination --requirement $requirementsPath
if ($LASTEXITCODE -ne 0) { throw "Linux wheel download failed (exit $LASTEXITCODE)." }

$manifest = Get-ChildItem -LiteralPath $Destination -Filter *.whl | Sort-Object Name | ForEach-Object {
    [ordered]@{
        file = $_.Name
        bytes = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
ConvertTo-Json -InputObject @($manifest) -Depth 3 | Set-Content -LiteralPath (Join-Path $Destination "manifest.json") -Encoding utf8
Write-Output "Linux CPython 3.10 wheelhouse ready: $Destination"

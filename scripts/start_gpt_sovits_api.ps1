[CmdletBinding()]
param(
    [string]$ConfigPath = '',
    [string]$PackageRoot = '',
    [string]$BindAddress = '127.0.0.1',
    [int]$Port = 9880,
    [switch]$ValidateOnly
)

$projectRoot = Split-Path $PSScriptRoot -Parent
if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $projectRoot 'data\config\gpt_sovits_api.local.yaml'
}
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)

if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw @"
GPT-SoVITS local API config was not found:
$ConfigPath

Create it from a working GPT-SoVITS tts_infer.yaml and set the custom section
to the exact GPT and SoVITS weights this API should use. Yayu sends
text and reference audio only; it never changes the loaded model.
"@
}

if ([string]::IsNullOrWhiteSpace($PackageRoot)) {
    $bertLine = Select-String -LiteralPath $ConfigPath -Pattern '^\s*bert_base_path:\s*(.+?)\s*$' |
        Select-Object -First 1
    if ($null -eq $bertLine) {
        throw 'Cannot infer GPT-SoVITS package root: custom.bert_base_path is missing.'
    }
    $bertBasePath = $bertLine.Matches[0].Groups[1].Value.Trim().Trim([char[]]@([char]39, [char]34))
    $PackageRoot = [System.IO.Path]::GetFullPath(
        (Join-Path $bertBasePath '..\..\..')
    )
}
else {
    $PackageRoot = [System.IO.Path]::GetFullPath($PackageRoot)
}

$pythonPath = Join-Path $PackageRoot 'runtime\python.exe'
$apiPath = Join-Path $PackageRoot 'api_v2.py'
foreach ($requiredPath in @($pythonPath, $apiPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required GPT-SoVITS file not found: $requiredPath"
    }
}

Write-Host ("Starting GPT-SoVITS API at http://{0}:{1}" -f $BindAddress, $Port)
Write-Host "Package: $PackageRoot"
Write-Host "Local config: $ConfigPath"
Write-Host 'Yayu will use the model already loaded by this API.'
Write-Host 'Keep this window open while Yayu is running.'

if ($ValidateOnly) {
    Write-Host 'GPT-SoVITS launcher validation succeeded.'
    return
}

Push-Location $PackageRoot
try {
    & $pythonPath $apiPath -c $ConfigPath -a $BindAddress -p $Port
}
finally {
    Pop-Location
}

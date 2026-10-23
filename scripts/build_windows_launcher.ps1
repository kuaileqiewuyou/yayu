param(
    [switch]$DesktopShortcut,
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = $projectRoot
} else {
    $OutputDirectory = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
}
[System.IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
}
if (-not (Test-Path -LiteralPath $compiler)) {
    throw 'Windows .NET Framework 4.x C# compiler was not found.'
}

$source = Join-Path $PSScriptRoot 'windows_launcher.cs'
$icon = Join-Path $projectRoot 'ui\assets\yayu.ico'
if (-not (Test-Path -LiteralPath $icon)) {
    throw "Launcher icon was not found: $icon"
}
$chatExe = Join-Path $OutputDirectory 'Yayu.exe'
$settingsExe = Join-Path $OutputDirectory 'Yayu Settings.exe'
foreach ($target in @($chatExe, $settingsExe)) {
    $compilerArgs = @('/nologo', '/target:winexe', '/optimize+',
        '/reference:System.Windows.Forms.dll', '/reference:System.Web.Extensions.dll', "/win32icon:$icon", "/out:$target")
    if ($target -eq $settingsExe) { $compilerArgs += '/define:SETTINGS' }
    & $compiler @compilerArgs $source
    if ($LASTEXITCODE -ne 0) { throw "Failed to build $target" }
    Write-Output "Built: $target"
}

if ($DesktopShortcut) {
    $desktop = [Environment]::GetFolderPath('DesktopDirectory')
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path $desktop '芽语.lnk'))
    $shortcut.TargetPath = $chatExe
    $shortcut.WorkingDirectory = $OutputDirectory
    $shortcut.Description = '启动芽语 / Yayu'
    $shortcut.IconLocation = "$chatExe,0"
    $shortcut.Save()
    Write-Output "Desktop shortcut: $desktop\芽语.lnk"
}

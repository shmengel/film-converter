# Builds the installer for people without Python:
#   powershell -ExecutionPolicy Bypass -File tools\build.ps1 [-TestRoll <folder with a few RAWs>]
# Steps: tests -> PyInstaller folder build -> self-test of the built exe -> Inno Setup.
# Result: build\installer\FilmConverter-Setup-<version>.exe
# Needs: .venv with requirements.txt + requirements-build.txt, and Inno Setup 6
# (winget install JRSoftware.InnoSetup --scope user).
param([string]$TestRoll = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"

$version = & $py -c "import filmconv; print(filmconv.__version__)"
Write-Output "== Film Converter $version"

Write-Output "== Tests"
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }

Write-Output "== PyInstaller"
& $py -m PyInstaller --noconfirm --clean --log-level WARN --distpath build\dist --workpath build\work packaging\film_converter.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
$exe = Join-Path $root "build\dist\Film Converter\Film Converter.exe"

if ($TestRoll) {
    Write-Output "== Self-test of the built exe on $TestRoll"
    $tmp = Join-Path $env:TEMP "filmconv-selftest"
    $roll = Join-Path $tmp "roll"
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    New-Item -ItemType Directory -Force $roll | Out-Null
    Get-ChildItem $TestRoll -File | Where-Object { $_.Extension -match '^\.(nef|NEF|dng|DNG)$' } |
        Select-Object -First 2 | Copy-Item -Destination $roll
    $p = Start-Process -FilePath $exe -ArgumentList "--self-test", "`"$roll`"", "`"$tmp\out`"" -Wait -PassThru
    Get-Content "$tmp\out\self-test.txt"
    if ($p.ExitCode -ne 0) { throw "Self-test of the built exe failed" }
}

Write-Output "== Inno Setup"
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found (winget install JRSoftware.InnoSetup --scope user)" }
& $iscc /Q "/DAppVersion=$version" packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Get-Item "build\installer\FilmConverter-Setup-$version.exe" | ForEach-Object {
    Write-Output ("== Done: {0} ({1:N0} MB)" -f $_.FullName, ($_.Length / 1MB)) }

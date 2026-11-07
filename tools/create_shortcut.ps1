# Creates a "Film Converter" shortcut on the desktop and in the Start menu.
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File tools\create_shortcut.ps1
# (Recreate it if the project folder moves.)
$project = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $project ".venv\Scripts\pythonw.exe"
$app = Join-Path $project "app.py"
$icon = Join-Path $project "filmconv_gui\icon.ico"
if (-not (Test-Path $pythonw)) { throw "Missing $pythonw - create the .venv first." }

$shell = New-Object -ComObject WScript.Shell
$targets = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs")
)
foreach ($dir in $targets) {
    $lnk = $shell.CreateShortcut((Join-Path $dir "Film Converter.lnk"))
    $lnk.TargetPath = $pythonw
    $lnk.Arguments = "`"$app`""
    $lnk.WorkingDirectory = $project
    $lnk.IconLocation = "$icon,0"
    $lnk.Description = "Convert B&W film negative scans to positives"
    $lnk.Save()
    Write-Output "Created $($lnk.FullName)"
}

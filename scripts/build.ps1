# Builds dist\Snap\Snap.exe, checks it with --selftest and zips it for a release.
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Creating .venv ..."
    python -m venv .venv
}
& $py -m pip install -q -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

if (-not (Test-Path "assets\icon.ico")) { & $py scripts\make_icon.py }

& $py -m PyInstaller snap.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path $root "dist\Snap\Snap.exe"
$log = Join-Path $root "dist\selftest.log"
$env:SNAP_DATA_DIR = Join-Path $root "dist\selftest-data"
$proc = Start-Process -FilePath $exe -ArgumentList "--selftest" -Wait -PassThru
Remove-Item Env:\SNAP_DATA_DIR
Copy-Item (Join-Path $root "dist\selftest-data\selftest.log") $log -Force
Get-Content $log
if ($proc.ExitCode -ne 0) { throw "Snap.exe --selftest failed (exit $($proc.ExitCode))" }

$version = & $py -c "import snap; print(snap.__version__)"
$zip = Join-Path $root "dist\Snap-v$version-win64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path (Join-Path $root "dist\Snap") -DestinationPath $zip
$sizeMb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "Built $zip ($sizeMb MB)"

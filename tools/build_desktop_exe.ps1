$ErrorActionPreference = 'Stop'
$kitRoot = Split-Path -Parent $PSScriptRoot
# Look beside the extracted kit, and one level higher if Windows extracted a
# ZIP folder inside another folder of the same name.
$parent = Split-Path -Parent $kitRoot
$grandparent = Split-Path -Parent $parent
$candidates = @( (Join-Path $parent 'C130J_Reference'), (Join-Path $grandparent 'C130J_Reference') )
$projectRoot = $candidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'data\caucasus.sqlite') -PathType Leaf } | Select-Object -First 1
if ($env:C130J_REFERENCE_PATH) { $projectRoot = $env:C130J_REFERENCE_PATH }
if (-not $projectRoot) { throw 'C130J_Reference was not found beside the extracted kit. Put them together, or set C130J_REFERENCE_PATH.' }
$sourceDb = Join-Path $projectRoot 'data\caucasus.sqlite'
$sourceTemplate = Join-Path $projectRoot 'app\template.html'
$bundledDb = Join-Path $kitRoot 'assets\caucasus.sqlite'
$bundledTemplate = Join-Path $kitRoot 'assets\template.html'
$venv = Join-Path $kitRoot '.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'

Write-Host 'C-130J / Windows Desktop EXE Builder' -ForegroundColor Cyan
Write-Host "Source project: $projectRoot"
if (-not (Test-Path -LiteralPath $sourceDb -PathType Leaf)) {
    throw "Cannot find your database at $sourceDb. Put this kit next to C130J_Reference or set C130J_REFERENCE_PATH."
}
if (-not (Test-Path -LiteralPath $bundledTemplate -PathType Leaf) -and -not (Test-Path -LiteralPath $sourceTemplate -PathType Leaf)) {
    throw "Cannot find your HTML template at $sourceTemplate."
}

# Refresh the database; preserve the enhanced local planner and display UI.
Copy-Item -LiteralPath $sourceDb -Destination $bundledDb -Force
if (-not (Test-Path -LiteralPath $bundledTemplate)) { Copy-Item -LiteralPath $sourceTemplate -Destination $bundledTemplate }
Write-Host 'Refreshed the SQLite database; preserved the local application interface.' -ForegroundColor Green

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv $venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $venv
    } else {
        throw 'Python is not installed. Install 64-bit Python 3.11 or 3.12 from python.org, then rerun this file.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python virtual environment. Check your Python installation.' }
}
& $venvPython -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ is required"'
if ($LASTEXITCODE -ne 0) { throw 'Use Python 3.10 or later (3.11/3.12 recommended).' }

Write-Host 'Installing packaging tools into a private virtual environment...' -ForegroundColor Cyan
& $venvPython -m pip install --disable-pip-version-check --upgrade "pywebview>=5,<7" "pyinstaller>=6,<7" "pillow>=10,<13"
if ($LASTEXITCODE -ne 0) { throw 'Could not install pywebview/PyInstaller. Check Internet access, Python and pip.' }

Push-Location $kitRoot
try {
    Write-Host 'Checking your ASC data and HTML before building...' -ForegroundColor Cyan
    & $venvPython "src\desktop.py" --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Data validation failed; EXE has not been built.' }

    Write-Host 'Packaging the standalone EXE...' -ForegroundColor Cyan
    & $venvPython -m PyInstaller --noconfirm --clean --distpath "$kitRoot\dist" --workpath "$kitRoot\build" "$kitRoot\C130J_Reference.spec"
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller reported an error.' }
} finally {
    Pop-Location
}
$exe = Join-Path $kitRoot 'dist\C130J_Reference.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Build finished but EXE is missing: $exe" }
Write-Host "SUCCESS: $exe" -ForegroundColor Green
Write-Host 'Launch that EXE without Python, PowerShell, SQLite CLI or a browser tab.'
Write-Host 'Optional live update: create dist\data and copy a newer caucasus.sqlite there.'

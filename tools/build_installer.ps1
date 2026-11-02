param([switch]$SkipAppBuild)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspace '.venv\Scripts\python.exe'
Push-Location $workspace
try {
    & $python tools/collect_third_party_notices.py
    if ($LASTEXITCODE -ne 0) { throw 'Third-party notice collection failed.' }
    if (-not $SkipAppBuild) {
        & $python tools/update_airport_reference.py --if-available
        if ($LASTEXITCODE -ne 0) { throw 'Airport reference refresh failed.' }
        & $python -m PyInstaller --noconfirm C130J_Reference.spec
        if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
    }
    $runtime = Join-Path $workspace 'build\installer-deps\MicrosoftEdgeWebview2Setup.exe'
    if (-not (Test-Path -LiteralPath $runtime)) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $runtime) -Force | Out-Null
        Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $runtime
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $runtime
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
        throw 'WebView2 bootstrapper signature did not validate as Microsoft.'
    }
    $payload = Join-Path $workspace 'build\installer\payload'
    New-Item -ItemType Directory -Path $payload -Force | Out-Null
    Copy-Item -LiteralPath 'dist\C130J_Reference.exe' -Destination $payload -Force
    Copy-Item -LiteralPath 'assets\C130J_Helper.lua' -Destination $payload -Force
    Copy-Item -LiteralPath 'assets\C130J_KneeboardBridge.lua' -Destination $payload -Force
    Copy-Item -LiteralPath 'assets\C130J_KneeboardPage.lua' -Destination $payload -Force
    Copy-Item -LiteralPath 'assets\C130J.ico' -Destination $payload -Force
    Copy-Item -LiteralPath 'CDU_HELPER.md' -Destination $payload -Force
    Copy-Item -LiteralPath 'output\pdf\C130J_CDU_Helper_User_Guide.pdf' -Destination $payload -Force
    Copy-Item -LiteralPath 'LICENSE.txt' -Destination $payload -Force
    Copy-Item -LiteralPath 'THIRD_PARTY_NOTICES.txt' -Destination $payload -Force
    Copy-Item -LiteralPath $runtime -Destination $payload -Force
    $manifest = [ordered]@{}
    Get-ChildItem -LiteralPath $payload -File | Where-Object Name -ne 'payload.json' | ForEach-Object {
        $manifest[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    [IO.File]::WriteAllText((Join-Path $payload 'payload.json'), ($manifest | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    & $python -m PyInstaller --noconfirm C130J_Setup.spec
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
    Write-Host "Installer: $workspace\dist\C130J_CDU_Helper_Setup.exe"
} finally { Pop-Location }

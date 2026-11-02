param([string]$SavedGames = "$env:USERPROFILE\Saved Games\DCS")
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $SavedGames -PathType Container)) { throw "DCS profile not found: $SavedGames" }
$scripts = Join-Path $SavedGames 'Scripts'
New-Item -ItemType Directory -Path $scripts -Force | Out-Null
$export = Join-Path $scripts 'Export.lua'
$bridge = Join-Path $scripts 'C130J_Helper.lua'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
if (Test-Path -LiteralPath $bridge) { Copy-Item -LiteralPath $bridge -Destination "$bridge.$stamp.bak" }
Copy-Item -LiteralPath (Join-Path $root 'assets\C130J_Helper.lua') -Destination $bridge -Force
foreach ($asset in @('C130J_KneeboardBridge.lua', 'C130J_KneeboardPage.lua')) {
    $destination = Join-Path $scripts $asset
    if (Test-Path -LiteralPath $destination) { Copy-Item -LiteralPath $destination -Destination "$destination.$stamp.bak" }
    Copy-Item -LiteralPath (Join-Path $root "assets\$asset") -Destination $destination -Force
}
$kneeboard = Join-Path $SavedGames 'Kneeboard\C-130J-30'
New-Item -ItemType Directory -Path $kneeboard -Force | Out-Null
for ($page = 1; $page -le 20; $page++) {
    $destination = Join-Path $kneeboard ('C130J_CDU_Helper_{0:00}.lua' -f $page)
    if (Test-Path -LiteralPath $destination) { Copy-Item -LiteralPath $destination -Destination "$destination.$stamp.bak" }
    $content = "-- C130J_CDU_HELPER_LIVE_KNEEBOARD`nC130J_HELPER_KB_PAGE = $page`ndofile(require('lfs').writedir() .. 'Scripts/C130J_KneeboardPage.lua')`n"
    [IO.File]::WriteAllText($destination, $content, [Text.UTF8Encoding]::new($false))
}
$loader = "pcall(function() dofile(require('lfs').writedir() .. 'Scripts/C130J_Helper.lua') end) -- C130J_HELPER"
if (Test-Path -LiteralPath $export) {
    $contents = [IO.File]::ReadAllText($export)
    if ($contents -notmatch 'C130J_HELPER') {
        Copy-Item -LiteralPath $export -Destination "$export.$stamp.bak"
        [IO.File]::AppendAllText($export, "`r`n$loader`r`n", [Text.UTF8Encoding]::new($false))
    }
} else {
    [IO.File]::WriteAllText($export, "$loader`r`n", [Text.UTF8Encoding]::new($false))
}
Write-Host "Installed CDU bridge in $scripts. Start DCS once to load the updated bridge and live kneeboard; later plan sends need no re-slotting. Existing exporters preserved."

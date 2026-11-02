# C-130J CDU Helper

Flight planning and CDU entry assistance for the ASC C-130J in DCS World.

**Free to use under the supplied licence.**

## Download

**[Download the Windows installer](https://github.com/Yeeeeet0/C130-Helper/releases/latest/download/C130J_CDU_Helper_Setup.exe)**

[Read the PDF user guide](https://github.com/Yeeeeet0/C130-Helper/releases/latest/download/C130J_CDU_Helper_User_Guide.pdf) | [All release files](https://github.com/Yeeeeet0/C130-Helper/releases/latest)

On the release page, scroll to **Assets** and expand it if needed. Download `C130J_CDU_Helper_Setup.exe` to install the app.

## Download and install

1. Open **Releases** on this repository and select the latest release.
2. Download **C130J_CDU_Helper_Setup.exe**.
3. Run setup, choose an installation folder and select whether to create a desktop shortcut.
4. Select your DCS installation folder if it is not detected automatically.
5. Start DCS once after installing so the bridge and kneeboard pages load.

The installer includes the app, PDF guide, DCS bridge and native kneeboard pages.
No separate Python installation is required. If WebView2 is missing, its setup needs internet access.
GitHub's automatically generated source archives contain source code, not the Windows installer.

## Features

- Departure and arrival selection with runway direction arrows and ILS information.
- ASC SID/STAR choices, previews and conditional terminal-fix planning alternatives.
- Fix, airway and draggable custom waypoint route editing.
- Named flight-plan library and DD/DDM, imperial/metric display controls.
- Compact manual entry plan, text/print export and live DCS kneeboard reference pages.
- Automatic entry into RTE 1 or RTE 2, with optional replacement and two input speeds.
- Verified LEGS discontinuity and consecutive-duplicate cleanup.
- Arrival ILS/TACAN tuning and ILS identifier entry when suitable data is available.
- Full PDF Help and one-page section help inside the app.

## Quick start

Select a terrain, then work through **Departure -> Arrival -> Procedures -> Route -> Review -> CDU input**.
Confirm each stage and select **Route reviewed** before entering the plan.

**Manual:** choose the route slot and follow the complete table, or send it to the kneeboard.

**Automatic:** select Pilot/Copilot, route slot and speed. Enable **Replace route** only when you intend
to clear that slot. Connect, Arm, return to DCS and double-click the selected cockpit CDU **CAPS** key.
Double-click again to stop. For a proposed replacement procedure, hold CAPS for **1.5 seconds and release**
to accept, or choose **Deny** in the app.

Always review the finished CDU route before activation / EXEC. Those actions remain manual.
Procedure previews and navigation-aid briefings do not replace published procedures or approach minima.

## Requirements and data

Windows 10/11 x64 and your own installed DCS ASC C-130J are required. Available navigation data
and chart coverage depend on your installation. The app reads local DCS/ASC files; it does not
download terrain charts. Confirmed runway labels on the map can differ from ASC's CDU labels;
the helper uses the associated CDU designation internally.

Open **Help** at the top of the app for the full guide. Section Help opens a matching one-page extract.
The standalone PDF guide is also attached to each release.

## Verify a download

Release assets include **SHA256SUMS.txt**. In PowerShell, use:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\C130J_CDU_Helper_Setup.exe
```

Compare the result with the installer entry in SHA256SUMS.txt from the official release.
A matching checksum verifies that the files match; it is not a digital publisher signature.

## Report a problem

Use this repository's **Issues** tab. Include the release version, terrain, airport/runway,
selected RTE slot, exact app message and a CDU screenshot. Automatic-entry diagnostics are saved
as **cdu-route-diagnostic.jsonl** beside the installed executable. Review logs/screenshots for
personal information before attaching them publicly.

## Licence

Authorised recipients may use the app free of charge. Redistribution, mirrors, repackaging and sale
require prior written permission from the rights holder. See [LICENSE.txt](LICENSE.txt) for the full terms.
Third-party components retain their separate terms in [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).

This repository provides application source, official downloads, documentation and issue tracking. DCS, ASC and other third-party names remain their owners' property.

## Development source

The current application source is in [src/](src), its interface and bridges in [assets/](assets),
and automated checks in [tests/](tests). See [DEVELOPMENT.md](DEVELOPMENT.md) for setup,
private data requirements, build instructions and known limitations. The existing licence applies.

Source on `main` is ahead of the published v1.0.0 installer. Source updates do not replace release assets.
Automatic speed/altitude entry is under development: ASC can carry cruise altitude into STAR legs;
protection/restoration of published procedure restrictions remains outstanding.
DCS/ASC databases, terrain charts, local settings, logs and saved flight plans are excluded.

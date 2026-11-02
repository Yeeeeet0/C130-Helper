# Developing C-130J CDU Helper

Application source is available under the existing proprietary free-use licence in
[LICENSE.txt](LICENSE.txt). Public visibility does not grant additional redistribution rights.
Third-party components retain their own licences.

## Source and release status

The source on `main` tracks the local development version. The published v1.0.0 installer
is an earlier snapshot; this source upload does not replace release assets.

The latest local run passed 229 automated tests, planner browser checks and packaged startup checks.
These are not a complete live-cockpit validation of automatic speed/altitude entry.

**Known limitation:** ASC propagates an entered altitude to later legs, including displayed
STAR restrictions. The current loader permits that propagation and then enters later planned
targets. It does not yet preserve or restore all published procedure restrictions. Check the
actual route against the applicable procedure before EXEC. Complete instrument-approach
restrictions are not supplied by the app's navigation-aid briefings. The next implementation
task is to protect procedure restrictions from cruise entries.

## Layout

- `src/`: desktop host, CDU automation, data readers, installer and kneeboard plan generation.
- `assets/`: application HTML/JavaScript, original Lua bridges and application icon.
- `tests/`: automated tests and small CDU display fixtures.
- `tools/`: build, help generation, local UI verification and data-audit utilities.
- `legal/`, `LICENSE.txt`, `THIRD_PARTY_NOTICES.txt`: licence material.
- `AUTO_CONSTRAINT_ENTRY_PLAN.md`: current constraint-entry design and validation status.

Generated executables, virtual environments, logs, saved flights, DCS location settings,
third-party navigation databases and terrain charts are excluded from Git.

## Local setup

Use Windows 10/11 x64, Python 3.12 and your own installed DCS ASC C-130J.
Run these commands from the repository root in PowerShell:

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
New-Item -ItemType Directory -Force build | Out-Null
$env:DCS_INSTALL_DIR = 'D:\DCS World'
```

Set the DCS path to your actual installation. The app also has local discovery and saved
installation settings. Do not commit machine-specific settings or local databases.

### Required private reference data

The desktop host needs `assets/caucasus.sqlite`, the Helper's processed airfield-reference
database. Supply an authorised local copy from the existing Helper development package
(`assets/caucasus.sqlite`) or the sibling reference project (`data/caucasus.sqlite`).
The ASC `nav_data.db` is a different database and cannot simply be renamed to this file.
This repository currently does not contain a generator for that processed reference database;
cloning the source alone is therefore insufficient to launch or package the full app.

Generate the terrain airport reference from your own DCS installation:

```powershell
.venv/Scripts/python.exe tools/update_airport_reference.py --dcs $env:DCS_INSTALL_DIR
```

Navigation procedures and raster charts are read locally from the installed module/terrains.
They are not included in the source repository.

## Run, test and build

Generate the full guide and its section PDFs before packaging or running help-document tests:

```powershell
.venv/Scripts/python.exe tools/create_user_guide.py
.venv/Scripts/python.exe src/desktop.py --self-test
.venv/Scripts/python.exe src/desktop.py
```

With private reference data available, run the full suite and optional local Edge UI checks:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests
.venv/Scripts/python.exe -u tools/verify_planner_ui.py --route-only
```

Some tests use local UDP mock servers and temporary installer test registry entries.
The planner check requires Microsoft Edge and a working local DCS data installation.
The isolated constraint-runner tests do not require DCS or the private databases:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_auto_constraints.py
```

Build the app and single-file installer using the current script:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_installer.ps1
```

Outputs are `dist/C130J_Reference.exe` and `dist/C130J_CDU_Helper_Setup.exe`.
The build refreshes local airport data when available, collects dependency notices and
downloads Microsoft's WebView2 bootstrapper if absent. It validates the bootstrapper's
Microsoft signature before including it. The legacy `Build_Desktop_EXE.cmd` and
`tools/build_desktop_exe.ps1` expect the older sibling-reference-project layout.

Publishing source, installers or releases is a separate explicit action. A local build
does not automatically push to GitHub or replace published release files.

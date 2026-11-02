C-130J CDU Helper

INSTALL
Run dist/C130J_CDU_Helper_Setup.exe.
Choose the app folder, optionally untick Create desktop shortcut, then Install.
DCS profiles and the Start menu shortcut are configured automatically.
If DCS is not detected, select its installation folder; setup remembers it.
The installer includes the app, navigation reference, bridge and shortcuts.
WebView2 is installed only if missing (internet required for that step).
Restart DCS once after bridge installation.

USE
The concise PDF user guide is installed beside the app as
C130J_CDU_Helper_User_Guide.pdf. It covers every workflow and troubleshooting.
Help at the top opens the full PDF. Section Help opens its one-page extract.
Plan departure, arrival and SID/STAR. En-route selection has Fixes (default),
Airways, and Custom waypoints modes. Click/drag to place custom points, drag
them to move, or middle-drag to pan. Custom points can be renamed and saved.
Automatic loading creates their DDM positions before inserting route fixes.
Review the route.
Save flight plan stores a named complete plan inside the app. Saved plans
opens the searchable library without a file browser. Select a name to load
or update it; use a different name to save another copy. All airports,
runways, procedures, approach, fixes, custom coordinates and preferences
are restored. Review again before CDU input. Updates/uninstall keep saved
flights. More > Import plan file opens older external JSON plans.
Manual mode shows a complete CDU entry plan with no per-field confirmations.
Choose its RTE 1/2, then Copy plan, Save text, or Save / print plan.
The printable HTML opens in your browser for printing or saving as PDF;
use it on another display/device or on paper while staying in DCS.
Send to kneeboard publishes the plan to native C-130J CDU PLAN pages.
Install this update and start DCS once to load the new Lua pages. Later
plan sends update live without re-slotting; DCS must be unpaused to reply.
Use normal kneeboard page bindings. Twenty slots are reserved so longer
plans can arrive without a reload; the footer shows current used pages.
Choose Manual or Automatic. In Automatic, choose RTE 1 or RTE 2 and
Default or Accelerated input speed. The starting scratchpad clears automatically.
Replace route clears the selected origin and legs before loading.
Arm, then double-click the selected CDU CAPS key to start/stop.
For a proposed replacement, hold CAPS for 1.5 seconds and release to accept.
The app shows verified completed entries and percentage. Review before EXEC.
LEGS cleanup removes gaps and consecutive duplicates; later returns remain.
Use More > Airfield reference for current-terrain airport details.
Use More > Refresh DCS airports after terrain updates.
The reference includes DCS navaids independently of ASC identifiers.
Kola only: overview charts appear on zoom-out; native charts appear closer in.
First overview generation is cached and can take time.

REQUIREMENTS
Windows 10/11 x64 and a local DCS C-130J installation.
DCS navigation data and installed terrain charts are read from that installation.
No Python or build tools are needed on the receiving PC.

UNINSTALL
Use Windows Settings > Apps > C-130J CDU Helper, or Uninstall.exe in the app folder.
Other DCS exporters and user plans/logs are preserved.

BUILD FROM SOURCE
Run tools/build_installer.ps1 with the local Python virtual environment present.
This rebuilds the app and creates the single setup EXE.
CDU_HELPER.md contains detailed controls and data notes.

LICENCE AND DISTRIBUTION
Authorised recipients may use the app free of charge. Distribution requires
prior written permission from the rights holder. Free redistribution,
paid copies, mirrors, bundles and repackaging are all covered.
Read LICENSE.txt for the complete terms and THIRD_PARTY_NOTICES.txt for
separate component licences. Both are installed with the app and readable
from its Licence and notices section. Third-party rights are unaffected.
DISTRIBUTION.md contains additional notes for the publisher.

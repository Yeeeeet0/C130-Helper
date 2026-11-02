# CDU page reuse and Kola chart overview test

The loader checks the current display before navigating. It reuses the selected RTE page for DEP/ARR and LEGS when the required prompt is present, reuses an already-open LEGS page, and uses L6 `<ROUTE n` on terminal menus/review or R6 `ROUTE n>` on main LEGS to return directly. INDEX route choices retain their own R1/R2 mapping. Returning to a required route header uses PREV for nearby pages and INDEX for deep pages. Wrong-route/unknown layouts and scratchpad errors still stop entry. `tools/audit_cdu_pages.py` records avoidable round trips from the diagnostic log; the reviewed log contained 98 across its recorded runs. Simulated SID → STAR → LEGS checks now perform no INDEX round trips when starting on the selected route.

Kola alone now has experimental 128 and 512 m/pixel overview tiers generated from the existing 32 m/pixel charts' DDS mipmaps. Zooming in selects the original sheets; zooming out selects larger overview tiles and permits a wider view. The compositor preserves the sheets' native one-pixel overlap and world bounds. Native thumbnails and completed overview PNGs are cached locally; first-time generation takes time, subsequent views use the cache. Changes to archive data or sheet placement invalidate the relevant cached overviews. Other terrains retain their existing map behavior.

Confirmed Caucasus map identifiers/headings use the user-annotated DCS runway values. CDU menu choices and procedure associations retain their separate ASC values. Other terrains retain their installed navigation data until a DCS mapping is confirmed. Unconfirmed DCS-only runway records are not promoted into ASC CDU choices; user-confirmed runway pairs can be selected even when the ASC runway table is empty. Airports without ASC runway data can be planned with a conditional alternative; runway selection remains a cockpit action. The reference view shows the ASC course without assuming a true/magnetic conversion. DCS VOR/TACAN/ILS/NDB and standalone/world beacons are stored independently, including identifiers absent from ASC; these are available under the reference screen's DCS navaids list. Raw tuning values are preserved and range issues flagged. They are not silently inserted as ASC route fixes.

# Route cleanup and DCS airport references

LEGS cleanup also removes consecutive duplicate waypoint identifiers, including across page boundaries and duplicates exposed by removing a gap. Non-consecutive returns (A → B → A) are preserved. It remains on LEGS, verifies each deletion and protects the remaining waypoint sequence. A duplicate deletion that creates a discontinuity is followed by normal discontinuity removal. Stops and verification failures do not count cleanup as completed progress.

Airport names, communication frequencies and associated beacon records are imported from readable `radio.lua` / `beacons.lua` files in installed DCS terrains. They are stored in the app's separate SQLite reference cache and matched to existing ASC airports using an explicit identifier or a unique nearby position. The ASC module database is read-only. ASC airport codes, runway choices and SID/STAR data remain authoritative; Out-of-range localizer frequencies in DCS source records are flagged and retained as source data, never guessed or automatically tuned. DCS beacon listings do not by themselves authorize CDU tuning or establish a runway approach. Missing or ambiguous details are not invented. Encrypted terrain configuration is not read or decoded.

The bundled reference currently contains 108 associated airports from the available installed sources, including 26 Kola airports. More → Airfield reference now follows the selected terrain. More → Refresh DCS airports refreshes the installed-source cache while preserving the current plan. File changes are detected on the next app launch. Other terrain data remains ASC-only where no readable DCS reference sources are installed. `tools/update_airport_reference.py` refreshes the bundled database before packaging; the installer includes it automatically.

# Install and use

Help at the top opens the full local PDF guide. Help in each section opens the matching single-page extract; CDU input selects Manual, Automatic or Advanced help from the current settings. The PDFs open in the Windows default PDF viewer and work offline. Section help remains accessible before a stage is unlocked. Copies are bundled with the EXE, so no separate download is required.

Run `C130J_CDU_Helper_Setup.exe`. Select an install folder. Setup finds DCS automatically and asks for its installation folder only when detection fails. It remembers this location for the app. DCS Saved Games profiles are detected automatically; if none exist, the standard DCS profile is prepared. Setup installs the app, bridge, Start menu shortcut and Windows uninstall entry. Create desktop shortcut is checked by default and can be turned off. On an update, turning it off removes an unchanged desktop shortcut previously created by this installer; user-modified shortcuts are preserved. It includes Microsoft's signed WebView2 bootstrapper and runs it only if the runtime is absent (internet required in that case). Python and build tools are bundled; the receiving PC still needs its own DCS C-130J installation for ASC navigation and terrain charts. Restart DCS once after installing the bridge.

Main screens now use short labels; extended guidance is under Help. Automatic progress counts verified airports, fixes, runway/procedure/transition selections and radio entries, plus reset (when selected) and final LEGS cleanup as operations. Typing/navigation alone does not advance progress. Waiting for approval or stopping preserves the completed percentage. A failed or unverified entry is not counted. Reaching 100% means the required inputs and cleanup checks completed; activation/EXEC remains manual.

Setup updates an existing installation, preserves/backups other exporters and rolls back app/profile file changes on an installation error. Uninstall restores the previous bridge only if the installed bridge is unchanged, removes only its added loader line, and keeps user plans/logs and modified files.

# Efficient LEGS discontinuity cleanup

After SID and STAR loading, the helper enters LEGS once and moves forward through the main route. On each page it deletes discontinuities with DEL + the matching left line-select key (L1–L5), verifies the expected row shift and named waypoint order on that page, then rechecks the same page before advancing. There is no preliminary full-route scan or repeated reopening through INDEX / RTE. It finishes on the last verified main LEGS page.

A gap at a page boundary can require a brief look at the following page to distinguish a failed deletion from another gap shifting into the identical position. This check stays within LEGS. If the last page collapses after deletion, the helper verifies the previous page in place. History and alternate pages are excluded. Unexpected layout, failed deletion or a changed visible waypoint sequence stops the run.

The inverted `*DELETE*` prompt is recognized even when exported under a GUID-named scratch-error element. Captured native before/after pages are retained as regression fixtures. Tests also cover a five-page route that now enters LEGS only once, consecutive boundary gaps, page collapse, stopping and preserving named waypoints. The bridge is unchanged.

# Runway designation and course alignment

Beslan URMO uses CDU runways 10/28 while ASC procedure records use 09/27. Both ends are now mapped, and old saved plans that retained the ASC value as their CDU designation are migrated. An opposite-end designation override is rejected for a confirmed mapping. Gelendzhik URKG CDU menu designations 01/19 are also confirmed by the recorded live export.

The planner has one floating map runway selector per airport, showing the DCS designation for confirmed Caucasus mappings and retaining the corresponding ASC CDU designation internally. The source runway association is retained internally for SID/STAR data; there is no separate cockpit override selector. Airport summaries and review use the same designation and omit the conflicting ASC/DCS runway course displays. Source-course diagnostics remain available in the runway audit. Confirm is disabled while runway data loads. Changing an arrival runway clears its STAR and approach confirmation while preserving departure and en-route fixes; changing a departure runway clears its SID confirmation.

Run `tools/audit_runways.py` to regenerate `build/runway-alignment.md`, `.csv` and `.json`. The audit covers all 21 bundled Caucasus airfield references and 34 matching ASC runway ends. Other terrains lack this bundled runway reference; their runway designations remain unverified until live CDU data is available. Nearby reference matches require either a unique field within 3 NM, or a nearest field within 1 NM with more than 0.5 NM separation from the next candidate.

# ASC coverage across DCS terrains

Choose a terrain / ASC planning area on the main screen. Supported planning areas are Caucasus, Nevada, Persian Gulf, Syria, Sinai, Mariana Islands, Kola, South Atlantic / Falklands, Normandy, The Channel, Afghanistan, Iraq and Cold War Germany. Airports, compatible fixes, navaids and continuous airway sections are read from the installed ASC navigation database for the selected geographic window. SID and STAR records are queried for each selected airport/runway. These windows include surrounding geography and are not exact playable-area borders.

The app now reads the global ASC airports table as well as the terrain navaid records. Field references with identifiers unsupported by the CDU remain visible as references but cannot be selected as CDU departure/arrival codes. Navaid identifiers are taken from the identifier field rather than frequency/channel values. Ambiguous source classifications are labelled as generic aids; nearby aids do not establish runway association or a published approach.

Local DCS raster charts are discovered per installed terrain. This installation successfully loads charts for Caucasus, Nevada, Persian Gulf, Syria, Mariana Islands and Kola. Other planning areas work without a chart underlay. No paid terrain content is downloaded or redistributed. Published approach legs/minima are still absent from this ASC database.

Changing terrain asks before clearing a current plan. Save before switching to keep that plan. Saved plans retain their terrain, and loading them selects the appropriate projection and dataset. Older saved plans default to Caucasus. Terrain datasets are cached separately; chart IDs are isolated between terrains to prevent stale tiles being drawn after a switch.

Projection data references: [dcs-projections](https://github.com/JonathanTurnock/dcs-projections) and [Skyeye terrain projections](https://github.com/dharmab/skyeye/blob/main/pkg/encyclopedia/terrains/terrains.go), whose parameters cite pydcs and DCS Web Editor.

# Arrival radio setup

If a planned SID or STAR name is absent from the CDU's list for the selected runway, automatic loading pauses and suggests the closest **name match** from that list. The suggestion and confirmation instructions appear only in the app. Hold the selected CDU's CAPS key for 1.5 seconds, then release to accept and resume. The helper reopens the correct SID/STAR list for the selected runway before selecting the agreed procedure. Use Deny replacement / Stop in the app to reject and halt loading. No suggestion text is typed into the CDU scratchpad. No further CDU keys are sent while waiting. There is no automatic acceptance or timeout approval. This compares procedure names, not flight-path suitability; review the substituted legs and restrictions. The accepted name is checked in procedure review and RTE 1 and recorded in the diagnostic log. Outside this confirmation pause, double-clicking CAPS starts an armed entry or stops loading.

After automatic route entry and LEGS discontinuity cleanup, the helper tunes the destination runway's associated ILS frequency into VOR1 and the destination airport's TACAN channel/band into TAC1 when verified data is available. It then opens INDEX page 2 → NAV DATA and enters the ILS identifier in IDENT, leaving that page visible. Each receiver and the NAV DATA identifier are checked after entry. If a radio entry is rejected, the status reports that the route and LEGS cleanup are complete and identifies the radio step that stopped.

The manual plan and route handover summary show the same arrival aids. Automatic tuning uses the bundled Caucasus associations and imported DCS airport aids across terrains. Imported ILS ends are matched to ASC runway thresholds using the paired glideslope position and localizer direction; ambiguous matches are skipped and reported. TACAN requires a unique airport channel and known band (DCS's default ground TACAN system uses X). An ILS on the opposite runway is not reused. For Bodø, runway 07 uses BO / 110.30, runway 25 uses BD / 108.70, and both use BOO / 45X. Receiver power, pairing and operating modes are not changed.

This update adds the NAV TUNE key to the export bridge. Run `tools/install_cdu_bridge.ps1` and restart DCS once to load it; the connection check rejects an older bridge before arming. Subsequent plan changes do not require a DCS restart.

# Progressive flight-plan builder

The main screen follows Departure → Arrival → Procedures → Route → Review → Manual / Automatic Input. Unavailable stages remain visible. Confirm a runway for each airport before choosing SID, STAR and approach planning separately. The map opens as a selection dialog; changes remain drafts until confirmed. Cancel restores the prior plan.

Airport summaries use native ASC identifiers and runway data, with DCS reference details where available. The supplied reference has no ICAO codes, so reference airport names / aids are associated only when a single reference field lies within 3 NM of the ASC airport. Native and DCS runway designators can differ; runway-specific reference details are used only for matching designators.

SID/STAR previews stay centred on the selected runway threshold when cycling procedures or selecting Show preview, preserving the current zoom. When no runway position is available, the airport position is used. Procedure previews show numbered fixed endpoints, constraints and courses where supplied. White dotted lines retain the previously confirmed procedures while the colored preview changes. Non-position legs remain gaps. The installed ASC database does not supply published approach legs or minima. The approach stage therefore offers available runway/airport navigation aid briefings and ATC / visual planning alternatives, requiring explicit confirmation. These are not reconstructed instrument approaches.

Route editing supports click to add/select, a right-click waypoint menu (remove, insert before/after, replace, start reroute), undo/redo and Cancel/Confirm. Start reroute inserts a new sequence while preserving the downstream route; confirm or press Escape when finished. Airways expand between selected entry and exit fixes. Editing an airport/runway preserves en-route fixes and the unaffected terminal procedure; the affected procedure requires reconfirmation.

Review lists each section and manual-only items. Reviewing is required before input. The three lights report bridge connection, armed state and execution separately. A green connection requires PING plus a readable CDU page. The loader stops on lost transport, unexpected pages, failed acceptance or missing exact menu choices. SID/STAR menu searches use displayed page numbers, verify NEXT advances and stop at the last page. No EXEC or route activation is sent. Diagnostic reads and commands are recorded in `cdu-route-diagnostic.jsonl` beside the EXE.

The route loader supports the VIA/TO page when available and the documented LEGS page otherwise. Live cockpit validation remains necessary: simulated display tests and UI checks cannot prove CDU acceptance for all aircraft/database versions.

# C-130J CDU entry helper

Launch `dist/C130J_Reference.exe`. The app now opens on **Plan on map**. Switch between the map, CDU entry and airfield reference with the tabs at the top.

## Build a route on the DCS map

The underlay uses **DCS's installed Caucasus raster charts**, read directly from `Mods/terrains/Caucasus/RasterCharts`. It works offline and does not use an external map provider. It is the DCS raster chart layer, not a live capture of the F10 map or the 3D terrain. Chart detail is limited to the installed raster resolution. This version supports Caucasus.

The app discovers DCS from the latest Saved Games log; **Locate DCS** lets you select another installation. `DCS_INSTALL_DIR` can also specify the root folder. The selected folder must contain the C-130J navigation database and the Caucasus charts. Neither source is changed or copied into the EXE.

1. Click an airport on the map and choose **Set departure / Set arrival**, or use the airport dropdowns. Search supports identifiers such as **UGKO**, **IBERI** or **B143**. Drag to pan and scroll to zoom; airport markers are squares and fixes are triangles.
2. Select the departure and arrival runways. Choose a matching **SID** and **STAR**, including the desired transition. Choices are read from the installed ASC database and combine runway, common and en-route components in the correct order.
3. If ASC has no matching procedure, select a conditional **ATC-cleared route / vectors** or **Visual / VMC planning** alternative. Guidance explains prerequisites; it does not manufacture obstacle-clearance headings, altitudes or instrument procedures. Absence from ASC's database is not proof that no real-world procedure exists.
4. The map previews the selected SID/STAR immediately, before route creation. **Previous / Next** cycles the available procedures; **Show preview** frames the selection. Departure is blue and arrival is pink, with numbered fixed positions and an ordered leg list. The controls sit beside the map so the chart stays visible while browsing. Dashed lines are schematic, not exact turns/arcs or altitude/vector legs; missing-position legs remain gaps and the map banner reports their count. Click **Create departure & arrival routes** to confirm the choices and unlock en-route planning. Load actual published procedures through CDU DEP/ARR.
5. Build the en-route connection between the SID exit and STAR entry. Click fixes or select an airway's entry/exit points; the helper expands the intervening fixes and checks ASC one-way restrictions. Alternatively, explicitly select **Use direct connection** for planning, subject to the chosen terminal method and applicable clearance. Layer checkboxes and the airway level filter reduce clutter.
6. Reorder or remove connecting fixes. **Fit route** includes the terminal previews. **Save route / Load route** preserve airport, runway, procedure, transition, en-route and display selections. Changing a terminal choice requires rebuilding the preview; existing connecting fixes are retained for review.
7. Choose **Use route in CDU helper**. The checklist covers origin/destination, procedure selections, then connecting fixes. **SID/STAR menu selections and alternative briefings are manual-only checklist steps even in automatic mode**; they are not typed as scratchpad text or flattened into direct waypoints. Automatic entry remains available for normal identifier/coordinate fields.

The conditional alternatives follow general [FAA departure planning principles](https://www.faa.gov/air_traffic/publications/atpubs/aim_html/chap5_section_2.html) and [visual approach responsibilities](https://www.faa.gov/air_traffic/publications/atpubs/aim_html/chap5_section_5.html). Local published procedures and applicable ATC instructions govern; these options are simulation planning prompts, not certified replacement procedures.

### Using terminal fixes when there is no matching procedure

Choose **Custom terminal-fix routing (planning only)** in the SID/STAR selector. Select an ATC-cleared or visual/VMC planning basis, then add up to 12 terminal fixes in flight order. You can reorder/remove them, preview the sequence, or click a displayed terminal fix and add it to the custom departure/arrival.

The list initially shows only ASC terminal fixes associated with the selected airport. If none are available, it says so. **Show nearby fixes belonging to other airports** reveals additional geographic references within 80 NM, labelled with their airport and distance. This radius is a search limit, not a procedure-design or terrain-clearance criterion. A fix from another airport does not become an approach fix for the selected airport.

Departure ordering is airport → selected fixes → en-route; arrival ordering is en-route → selected fixes → airport. The last departure fix and first arrival fix become the connection anchors. Saving a route preserves these choices. The CDU checklist includes a manual planning briefing followed by the selected identifiers in the appropriate flight-order section; they are not labelled as a published SID/STAR.

Terminal fixes can help organise a route, but do not by themselves provide obstacle clearance, approach minima, altitude restrictions or runway suitability. Use published procedures and applicable clearances where available; the custom line is a planning aid rather than a validated instrument approach/departure.

## Master coordinate and unit controls

The two controls at the top apply across the map, procedure summaries, airway restrictions, airfield/runway reference and helper input fields:

- **Coordinates: DDM / DD** — DDM is the default. Custom waypoint inputs accept both compact DDM (`N4230.00`, `E04143.00`) and decimal degrees. Hemisphere, degree and minute bounds are validated.
- **Units: Imperial / aviation / Metric** — switches feet/metres, nautical miles/kilometres and knots/km/h, including converting entered IPRA values. Custom CSV elevation headers switch between `elevation_ft` and `elevation_m`.

The CDU entry field always shows what will actually be typed: **DDM coordinates and native CDU units (ft/NM)**. A converted display equivalent accompanies numeric entries. Changing display preferences never switches the CDU payload to DD or metric. Printed text within DCS raster chart images stays in the chart's original units. Preferences are stored locally when available and saved with plans; older plans default to imperial input units.

Duplicate identifiers are kept separate by geographic position. If the CDU displays a disambiguation page, select the position shown in the checklist before continuing. After a navigation database update, saved point identities/coordinates are checked again; re-select a point if it no longer matches.

Airways are expanded into route fixes for entry; they do not automatically set flight altitude or apply SID/STAR leg logic. Changing a route in the helper does not change the CDU until you explicitly enter it. No DCS restart is needed for route edits or this map feature.

Technical projection reference: [DCS Caucasus coordinate parameters and control point](https://github.com/JonathanTurnock/dcs-projections). Chart geometry and texture orientation are validated from the installed placement file before display. Unsupported chart formats produce a visible message rather than an assumed placement.

## Manual mode

1. Select **Selected map route**, **Custom waypoints (advanced)** or **Runway / IPRA**.
2. For custom waypoints, paste CSV with `ident,lat,lon,elevation_ft` or `ident,lat,lon,elevation_m` headers. Latitude and longitude accept DD or DDM. In DD, south/west are negative; in DDM, use S/W. Elevation is optional. The advanced editor can also copy procedure fix positions, but the normal planner selects the actual SID/STAR for DEP/ARR loading.
3. For IPRA, load the selected arrival runway or enter values directly. Optional blank fields are omitted. Check the north reference of the runway orientation in the CDU before choosing the true or magnetic course shown by the helper.
4. Reviewing a complete map route prepares its full manual plan automatically. For waypoint CSV or IPRA data, select **Prepare manual plan**.
5. Choose **RTE 1** or **RTE 2** in the manual plan. Read all entries in one list, grouped by route setup, departure, connecting fixes, arrival, approach briefing and radio tuning. Custom identifiers and coordinates appear once in the Fixes section; the separate Custom section is omitted. CDU values use DDM and CDU numeric units; runway selections use the confirmed ASC menu designation. The app displays the compact plan directly in manual mode using the existing dark theme; printed exports use a light background. The plan uses one compact table with Page and CDU value columns, short section headers and DDM positions beside fix identifiers. Repeated headers, setup/review-only rows and long LEGS page descriptions are omitted to reduce scrolling. Page and its short field descriptor occupy separate aligned subcolumns under the Page heading: for example RTE 1 / Origin, RTE 1 / Destination, DEP/ARR ARR / Runway, NAV TUNE INDEX / VOR 1 or CUSTOM DATA / Position. Notes, step numbers, separate entry-label and line-select-key columns are omitted. Choose the appropriate fields and insertion rows in the cockpit.
6. Use **Copy plan**, **Save text**, or **Save / print plan**. The last option saves a self-contained HTML file and opens it in your browser. Its **Print / Save as PDF** button uses the browser print dialog. Keep the file on another display/device, save as PDF, or print it before entering DCS. The file has no map, app or internet dependency.
7. Enter the plan entirely in the cockpit. No individual checkbox, Next button, app confirmation or bridge connection is required. Verify LEGS, remove discontinuities and consecutive repeats, and decide whether to EXEC yourself.

Use **Save flight plan / Saved plans** to store and reopen the complete flight plan inside the app. No DCS connection is required for manual mode.

## Automatic mode

Install the included bridge once, with DCS closed:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\install_cdu_bridge.ps1
```

For another Saved Games profile, supply `-SavedGames 'C:\Users\yourname\Saved Games\DCS.C130J'`.
The installer copies `assets/C130J_Helper.lua` into that profile's Scripts folder, backs up existing files before changing them, and appends one marked loader to Export.lua. Existing exporters remain in place. Restart DCS after installation.

1. Review the completed map plan and select Automatic mode.
2. Enter an unpaused C-130J cockpit with a powered CDU and an empty RTE 1.
3. Select pilot or copilot and Check DCS connection. A valid bridge and readable CDU are required.
4. Select Arm full map route, return to DCS and double-click the selected CDU CAPS key.
5. The helper loads airports, en-route fixes and terminal selections, then clears discontinuities on LEGS page by page.
6. Review the finished route and use activation / EXEC in the cockpit. Double-click CAPS again or use Stop / Disarm to abort.

Each command is checked against the current CDU state. A stopped or failed run does not automatically restart. Custom waypoint creation and IPRA use the manual plan.

## Runway / IPRA workflow

The installed ASC manual v1.9.4, pages 320–322, specifies an RPI **identifier already inside the active flight plan**, not the origin or destination. To use a runway position:

1. Load the arrival runway and choose a distinct RPI identifier.
2. Select **Prepare runway position as a waypoint** and complete its custom-waypoint plan.
3. Insert that waypoint as an intermediate point in the route and review/execute the route in the cockpit.
4. Switch back to IPRA, prepare its manual plan, and enter the RPI identifier and approach parameters.
5. On IPRA 2/2, select approach category C or D in the cockpit; review the approach before START.

The reference database includes derived threshold positions. These are estimates, not verified IPRA RPI locations. Missing threshold elevation is left blank; runway centre elevation is not substituted. No approach distances, HAT or glideslope defaults are invented. SID/STAR imports copy positions only; use CDU DEP/ARR to load procedure leg semantics and restrictions.

## Validation and limitations

Validated locally: coordinate bounds/rounding and hemispheres, input rejection, waypoint/IPRA checklist generation, loopback acknowledgements and stop handling, Lua bridge press/release and exporter chaining, installed C-130J device/control loading, navigation projection against a published control point, airway discontinuities/direction restrictions, saved-point identity checks, desktop database packaging, and a headless browser test of actual DCS chart decoding, map selection and route-to-CDU handoff.

The user has confirmed full route loading and LEGS discontinuity deletion in the live cockpit. The optimized forward traversal is covered by captured-page and simulated-CDU regression tests. The bridge reads the installed module's control definitions rather than hard-coding key numbers. It binds only to 127.0.0.1:31330 and accepts only the supported CDU typing, navigation, deletion and line-select keys while the player aircraft is C-130J. Multiplayer export restrictions or a paused mission can prevent communication.

To uninstall, remove the line containing `C130J_HELPER` from your profile's Export.lua and remove Scripts/C130J_Helper.lua, then restart DCS. Timestamped backups are retained alongside files changed by the installer.

Rebuild with the existing build command, or use the already-installed packaging tools without downloads:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm C130J_Reference.spec
```

The helper is a separate bundled asset, so refreshing the original reference HTML during the standard build does not overwrite it.

## Cockpit-triggered full route loader

Choose Automatic mode after sending a complete map route to the helper, then select **Arm full map route**. Return to DCS and double-click the selected pilot or copilot CDU **CAPS** key. The helper can wait for the simulator to resume after focus loss. CAPS still opens its normal page; the runner then navigates INDEX to RTE 1. Choose RTE 1 or RTE 2. With overwrite off, that route must be empty. Double-click CAPS again to stop, or use Stop in the helper.

The loader enters airports and ordered database fixes, then selects runway / published SID / STAR / transition through the native menus. It checks exported CDU titles, scratchpad messages, entered identifiers and menu choices; an unexpected page or duplicate-identifier prompt stops the sequence for inspection. Custom terminal fixes are entered as direct fixes. Custom waypoint creation and IPRA remain individual-field operations. The runner finishes before route activation and EXEC; review the full route in the cockpit.

Live route loading and LEGS deletion have been confirmed by the user; further aircraft/database variations can still require validation. Automated tests exercise simulated display output, native installed command definitions, trigger edges, stopping and failure guards; they cannot establish live CDU acceptance. The updated Export bridge requires a one-time DCS restart after installation. Subsequent route changes only require disarming, updating the map plan, preparing an empty RTE 1, and rearming.

## ASC and cockpit runway designations

Airport selection uses the floating runway direction box on the map. Confirmed DCS labels are shown there: Beslan URMO shows 09/27 and maps internally to ASC CDU 10/28. There is no right-side runway dropdown. Changing the runway reloads matching procedures and requires confirmation of the affected routing. Missing SID/STAR names can be replaced only through the explicit CAPS confirmation workflow described above.

The CAPS long-press update requires reinstalling the included export bridge and restarting DCS once. Double-click CAPS to start/stop; while a replacement is pending, only a 1.5-second hold followed by release accepts it. Each new action requires a fresh press; a button already held when arming cannot trigger it. Actions trigger on release, leaving the button released before menu navigation.

## Route target and overwrite

Automatic input offers RTE 1 or RTE 2 and an Overwrite selected route checkbox (off by default). These options are frozen when arming. With overwrite off, an occupied selected route stops loading without deletion. With overwrite on, the helper deletes the selected route's ORIGIN through DEL → L1, clears a retained destination if necessary, and verifies both empty airport fields and every main LEGS page empty (multiple blank pages are valid) before typing the new plan. If old legs remain or the CDU rejects deletion, loading stops. All subsequent route, terminal and LEGS operations use the selected route slot. The other slot is not selected or cleared; route activation and EXEC remain cockpit actions.

The bridge now supports separate DOUBLE and HOLD modes. Install the included bridge and restart DCS once after this update. Starting/stopping uses a double-click (two short releases within two seconds); accepting a replacement uses a fresh 1.5-second hold and release. Confirmation messages appear only in the app. Acceptance returns through DEP/ARR and the selected runway to the correct SID/STAR list.


# Route selection modes

Speed and altitude use one canonical representation: speed_kt and altitude_ft. Fractional base-unit precision is retained; manual/CDU and kneeboard values round only for display to whole knots and feet. Mach, FL and metric are input/display conversions, with button preferences stored separately from the numeric constraint. The popup has Altitude / FL above Speed / Mach. Legacy saved plans are normalised in memory on load and written in the canonical format when saved again. Mach input requires altitude and uses subsonic ISA/CAS conversion; automatic entry remains unchanged. Equations: https://society-of-flight-test-engineers.github.io/quarto-handbook/04-pitot-statics.html (sections 4.1 and 4.6).

Selected en-route fixes now open a map-anchored speed/altitude popup. Type values, scroll the numeric fields, or use the +/- controls (5 kt / 100 ft / 1 FL steps; Shift-scroll gives 1 kt / 10 ft). Apply saves and Clear removes. The manual planner and printable export place speed and altitude in dedicated columns within the Fixes section only, keeping one row per fix. Text and native kneeboard exports retain the same values. Automatic entry remains unchanged.

Local development: SPD/ALT beside an en-route fix edits optional per-waypoint speed (knots) and altitude (feet or flight level). The master units control converts speed/altitude displays to km/h and metres; flight levels retain their pressure-level meaning. Apply stores values at that particular waypoint occurrence; Clear removes them. Undo/redo, dialog Cancel, reordering, custom-point moves/renames and named saved plans preserve the intended association. Manual plans and printable exports show the values beside the fix; text and kneeboard output retain the same canonical units. Automatic route loading enters configured speed/altitude after LEGS cleanup and before arrival radios. It matches the complete planned fix order against final LEGS, stops on ambiguous constrained occurrences, and verifies every write while preserving unspecified fields at the selected fix. ASC applies entered altitude to following legs, including arrival procedure rows; later planned values are entered in flight order. The helper permits only that specific forward altitude change while continuing to check waypoint identity and unchanged speeds. Check arrival restrictions before EXEC. Already-correct values need no typing. Negative altitudes require Manual. The installed ASC manual page 265 associates constraints with waypoint rows on LEGS, and Cockpit/Scripts/CNI_MU/pages/legs_progress.lua displays knots and feet/FL. Local test build: a captured cockpit run confirms combined speed/altitude entry at the fix's right key and forward altitude propagation. Partial forms speed/ and /altitude still need cockpit confirmation. Rejections or failed readback stop the run without retries or EXEC. A stop may leave a partial route; inspect the CDU before deliberately starting again. Broader restriction types are not supported.

En-route opens in **Fixes** mode: click ASC fixes to add them. **Airways** mode selects the airway beneath the pointer, including at waypoint intersections; choose its entry and exit to add the ordered segment. Search follows the selected mode. Existing route points are retained when switching modes.

**Custom waypoints** mode lets you click or click-drag to place a waypoint, then drag its marker to move it. Middle-drag pans the map. Select a custom marker to rename it. Undo/redo includes placement, movement, renaming and deletion; Cancel restores the previous route. Saved plans retain coordinates and custom markers. The master coordinate and unit controls apply to their displays.

Custom route points are validated separately from ASC fixes. The automatic loader opens INDEX 2 → CUSTOM DATA, creates the identifiers, enters DDM coordinates into POSITION at L2, verifies the LAT/LON readout, then loads their identifiers with the route. L1 LAT/LON is display-only. Character entry waits 30 ms after each bridge-confirmed key release instead of 350 ms, and the complete scratchpad is checked before submission. The helper opens identifiers directly without scanning all custom-list pages, reuses CUSTOM LIST and an already-open matching detail page, and skips writing a matching stored position. Blank custom records left by a previous failed attempt can be completed. Custom identifier and position entry count toward progress. An existing custom identifier is reused and its coordinates are updated to the planned position through L2. The resulting LAT/LON readout must match; already-correct positions need no typing. The separate Waypoints manual workflow includes the creation and position steps. The map-route manual plan shows custom identifiers and coordinates in Fixes without a duplicated Custom section.


# Unknown airport coordinate fallback

If entering an origin/destination opens that identifier's CUSTOM DATA page, or returns NOT IN DATABASE, the loader uses the geographic midpoint of the selected ASC runway's two reciprocal ends. It keeps the original airfield code, such as UG26, with no suffix. Missing, ambiguous or invalid runway ends stop the fallback; the airport reference point is not substituted.

The helper fills POSITION at L2, verifies LAT/LON, returns to the selected RTE, and enters the original code into ORIGIN/DEST. Existing custom coordinates are replaced with the current plan's values. Airfield codes created this way are remembered locally per terrain and installed ASC database version, so later loads update their runway-centre positions before entering them into RTE. Changing between parallel or intersecting runways therefore refreshes the same airfield record. Progress includes the custom-data fields and omits the unavailable native runway menu selection. The other RTE is untouched.

An airport unknown to the CDU cannot supply native SID/STAR selections. If a published procedure was selected on that side, loading stops and asks for a terminal-fix or ATC alternative instead of silently omitting it. Custom endpoint sides otherwise bypass their native DEP/ARR runway menu; the planned en-route/custom terminal fixes and other airport selections are retained. The manual plan includes the same fallback coordinates and original identifier.


# Runway direction overlay

Departure and Arrival selection show a floating direction box beside the selected physical runway. The box lists every runway end at the airport, including parallel and intersecting runways, in a scrollable grid. Choose any direction in the box; the CDU designation, procedures and final plan use that selection. The old right-side runway dropdown is removed; runway selection is available in the map box. A solid cyan pointer with a dark border on the map and matching button icons show the selected flight direction. Confirmed Caucasus labels use the DCS heading and map designation from the annotated sheet; the map arrow follows the corresponding DCS runway-end geometry. The loader uses the separate confirmed ASC CDU designation. Selecting another physical runway centres the view on it, while panning and zooming keep the box anchored beside it.

Each direction shows its associated ILS identifier and frequency when available. ILS not listed means no confirmed runway-end ILS is available in the imported reference; nearby aids and the opposite end's ILS are not treated as that direction's ILS. The box is confined to airport/runway selection, so SID/STAR previews retain their existing centred behaviour.


# Automatic input speed and starting scratchpad

The Auto section has one Input speed selector. Default applies the existing custom-waypoint typing pace (30 ms after each bridge-confirmed character key release) to all automatic typing, retaining normal menu settling. Accelerated removes extra post-key delays and polls ordinary page transitions more frequently. Both profiles wait for the bridge's key-release acknowledgement (the current bridge uses a 100 ms key pulse), verify the complete scratchpad before submitting typed fields, and verify accepted values/pages. The selected speed is frozen when arming. Display or entry errors still stop the run; no uncertain key is blindly retried.

After double-click CAPS starts the sequence, the loader clears starting scratchpad text, DELETE prompts and native error messages with CLR and confirms the scratchpad is empty before navigation or route entry. A failed clear stops the sequence. Clearing runs only at the start; unexpected scratchpad content during loading still stops the run. Departure and arrival map selection use the full map width, with no right-hand panel. Select airports on the map or through map search, then choose runway direction in the floating box. Airport details remain on the main flight-planning screen. Approach type is selected and confirmed directly on the main Procedures card, without opening a map.


# Annotated Caucasus runway confirmations (29 October 2026)

The user-marked CaucasusAirfields (1).pdf confirms 42 runway ends at 21 airfields. Map selectors, summaries and direction arrows use the DCS label and geometry; CDU menu searches use the separately confirmed ASC designation. Internal ASC runway-table keys are preserved for SID/STAR association, including keys that differ from both displayed labels. The source PDF hash and explicit mapping are documented in src/runway_mappings.py. No magnetic/true conversion or generic numbering offset is inferred.

Examples (DCS map → ASC CDU): Batumi 12/30 → 13/31; Beslan 09/27 → 10/28; Gelendzhik 04/22 → 01/19; Kutaisi 08/26 → 07/25; Soganlug 13/31 → 14/32. Ticked Vaziani 13/31 uses native source keys 14/32 and CDU 13/31. Krasnodar-Pashkovsky uses its single DCS 05/23 strip and CDU 05/23; native source keys 05R/23L preserve the active long-strip associations. Crossed-out Sochi 02/20 and Tbilisi-Lochini 13L/31R are excluded from selectable directions. Current radio/beacon identifiers and frequencies are retained rather than replaced with this older sheet's values.

Confirmed DCS geometry also supplies runway centres for missing-airport custom data. The Soganlug reference's inverted end labels are resolved by their physical course, so DCS 13 points southeast and DCS 31 northwest. Runway-specific ILS association follows the same mapped physical end.

Route selection uses three directly accessible toggle buttons: Fixes, Airways and Custom waypoints. Exactly one mode is active and highlighted; opening route editing starts in Fixes.

# Licence and distribution

Authorised copies are free to use. Distribution requires the rights holder's prior written permission. LICENSE.txt contains the complete terms; third-party rights and licences are unaffected. The installer provides read-only licence readers. LICENSE.txt and THIRD_PARTY_NOTICES.txt are installed beside the EXE and are readable inside the app under Licence and notices.

# In-app flight-plan library

Save flight plan and Saved plans are available at the top of the planner. Complete and confirm the route, then name and save it. The library stores the whole flight plan: terrain, departure/arrival airports and ASC runway selections, SID/STAR and transitions or terminal alternatives, approach basis, en-route and custom waypoint coordinates, manual editor data, display preferences and CDU input settings. It does not save or resume an armed/executing operation.

Select a saved name and Load selected to restore the plan without a file browser. Search by name, airport or terrain. An unchanged selected name offers Update selected; changing the name saves a new copy. Duplicate names require selection of the existing record before updating it. Loaded plans are checked against the installed navigation data and must be reviewed again before CDU entry. A failed validation/load restores the current preview rather than replacing it with a partial plan.

Packaged installations keep the library in %LOCALAPPDATA%/C130JCDUHelper/flight-plans, outside the installation directory, so app updates and uninstall preserve saved flights. The source checkout uses build/flight-plans. Files use internal identifiers, not user-supplied names, and updates use atomic replacement. More → Import plan file remains available for older JSON plans; normal saving and loading need no external folder navigation. Manual printable/text exports remain separate from the flight-plan library.

# Live native C-130J kneeboard

The native page uses the app's dark table styling: shaded section bands, PAGE / FIELD / CDU VALUE columns and row borders. Wrapped entries share one cell without a rule between continuation lines. Empty rows are hidden. Install the update and start DCS once to load changed page artwork; later plan sends still update live.

ASC uses the standard DCS kneeboard indicator (including its render target for the cockpit kneeboard). The Helper now supplies native Lua CDU PLAN pages in Saved Games/Kneeboard/C-130J-30. The existing Saved Games export bridge writes named cockpit text parameters; the pages use text_using_parameter controllers. No ASC/DCS installation files are patched and no VAICOM code is included.

Install this update with the Helper closed, then start DCS once so the updated export bridge and native pages are loaded. This initial load is necessary; merely adding files cannot inject an indicator into an already loaded cockpit. Once loaded, Manual → Send to kneeboard updates the current plan without restarting DCS, re-slotting or reloading the mission. DCS must be unpaused to process the send. Open the normal kneeboard and navigate to CDU PLAN using your configured DCS kneeboard controls. It is a live reference for manual CDU entry; automatic loading continues to use the existing CAPS trigger.

Twenty page slots are preinstalled to accommodate larger plans without creating new pages during a mission. Each carries up to 24 wrapped lines, with Page, Field and CDU Value columns. The footer identifies used pages; reserved pages after the plan show END OF PLAN. The sender refuses an over-capacity plan rather than truncating it. Values remain CDU identifiers and DDM coordinates; custom waypoint creation, runway choices, SID/STAR selections and radio fields follow the same validated manual report.

Send checks that the DCS export parameter API and a loaded Helper page are available. Text is staged under a transaction ID; a commit is acknowledged only after all parameter values read back correctly. Incomplete/expired transfers do not replace the current plan, and failed readback attempts restore previous parameter values. Publishing issues no CDU key commands and is blocked while automatic entry is running. Other Saved Games exporters and personal kneeboard pages are preserved. Installer updates/uninstall track the specific Helper files, restore originals and preserve user-modified files.

The protocol, bounds, readback, rollback, drawing-controller wiring and installer ownership are verified with tests and a mocked DCS Lua environment. Actual C-130J cockpit rendering and shared Export/indicator parameter visibility still require an in-game check; a successful mock test is not live DCS verification. Unsupported DCS parameter APIs or a page not loaded in the current cockpit produce an error rather than a false successful send.

Technical references: the installed DCS Scripts/Export.lua documents get_param_handle(name) with get/set methods; ASC Cockpit/Scripts/Kneeboard_init.lua uses the standard common kneeboard indicator. Standard custom folder reference: https://forum.dcs.world/topic/382055-kneeboard-folder-is-c-130j-30/ .

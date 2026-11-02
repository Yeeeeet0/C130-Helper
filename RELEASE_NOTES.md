# C-130J CDU Helper v1.0.0

Initial GitHub download package for the current desktop build.

## Included

- Single Windows installer with optional desktop shortcut and automatic DCS profile setup.
- Terrain-based flight planning, runway direction selection and SID/STAR previews.
- Fixes, airways and custom waypoints; named in-app flight-plan saving/loading.
- Manual and automatic CDU input, route-slot selection, replacement and two input speeds.
- Discontinuity and consecutive-duplicate cleanup, plus available arrival radio setup.
- Live native C-130J kneeboard plan pages.
- Full eight-page PDF guide and contextual section Help buttons.

## Install or update

Close the Helper and run C130J_CDU_Helper_Setup.exe. Start DCS once after installation to load
the bridge and kneeboard scripts. Later plan changes and kneeboard sends do not require re-slotting.
The receiving PC needs its own DCS ASC C-130J installation.

## Downloads

- C130J_CDU_Helper_Setup.exe: install this file.
- C130J_CDU_Helper_User_Guide.pdf: standalone user guide (also included in setup).
- LICENSE.txt and THIRD_PARTY_NOTICES.txt: distribution and component terms.
- SHA256SUMS.txt: checksums for these files.

## Checks and limitations

The current build passed 194 automated tests, local browser checks, and packaged app/installer
self-checks. Tests do not establish live acceptance for every DCS/ASC database version.
Chart, runway, procedure and radio availability depend on the installed data. Review the actual
CDU route and radios before flight; activation / EXEC remain manual. The installer is not digitally signed.

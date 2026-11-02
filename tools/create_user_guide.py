"""Build the concise end-user PDF. Requires ReportLab (authoring only)."""
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/pdf/C130J_CDU_Helper_User_Guide.pdf'
NAVY = colors.HexColor('#11202e')
TEAL = colors.HexColor('#137d70')
INK = colors.HexColor('#243746')
MUTED = colors.HexColor('#536977')
RULE = colors.HexColor('#cbd8df')
PALE = colors.HexColor('#edf5f3')
WIDTH = A4[0] - 36*mm
styles = {
    'title': ParagraphStyle('title',fontName='Helvetica-Bold',fontSize=26,leading=31,textColor=NAVY,spaceAfter=5*mm),
    'h': ParagraphStyle('h',fontName='Helvetica-Bold',fontSize=12,leading=16,textColor=TEAL,spaceBefore=3.8*mm,spaceAfter=1.5*mm),
    'body': ParagraphStyle('body',fontName='Helvetica',fontSize=10,leading=13.4,textColor=INK,spaceAfter=2*mm),
    'small': ParagraphStyle('small',fontName='Helvetica',fontSize=9,leading=12.5,textColor=MUTED,spaceAfter=2*mm),
    'cell': ParagraphStyle('cell',fontName='Helvetica',fontSize=9.2,leading=12.5,textColor=INK),
    'head': ParagraphStyle('head',fontName='Helvetica-Bold',fontSize=9,leading=12,textColor=colors.white),
    'code': ParagraphStyle('code',fontName='Courier',fontSize=9,leading=13,textColor=NAVY,spaceAfter=3*mm),
}
story=[]
def p(text,kind='body'):
    story.append(Paragraph(text,styles[kind]))
def h(text): p(text,'h')
def step(number,title,text): p(f'<b>{number}. {title}</b> {text}')
def table(headers,rows,ratio=.32):
    cells=[[Paragraph(escape(c),styles['head']) for c in headers]]
    cells += [[Paragraph(c,styles['cell']) for c in row] for row in rows]
    grid=Table(cells,colWidths=[WIDTH*ratio,WIDTH*(1-ratio)],hAlign='LEFT',repeatRows=1)
    grid.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),
        ('TOPPADDING',(0,0),(-1,-1),5.3),('BOTTOMPADDING',(0,0),(-1,-1),5.3),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f3f6f8')]),
        ('GRID',(0,0),(-1,-1),.45,RULE),
    ]))
    story.append(grid);story.append(Spacer(1,3*mm))
def note(text):
    box=Table([[Paragraph(text,styles['body'])]],colWidths=[WIDTH])
    box.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),.6,RULE),
        ('LEFTPADDING',(0,0),(-1,-1),11),('RIGHTPADDING',(0,0),(-1,-1),11),
        ('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story.append(box)
def page(number,title,subtitle):
    if story:story.append(PageBreak())
    p(f'{number:02d} / USER GUIDE','small');p(title,'title');p(subtitle)

page(1,'C-130J CDU Helper','Plan a flight, review it, then enter it manually or load it automatically into the ASC C-130J in DCS.')
h('Install and start')
step(1,'Run the installer.','Choose the app folder and whether to create a desktop shortcut. Select the DCS installation folder only if asked.')
step(2,'Let setup finish.','It installs the app, Saved Games bridge and kneeboard pages. If WebView2 is missing, setup downloads it; that step needs internet access.')
step(3,'Start DCS once after installation.','This loads new bridge and kneeboard scripts. Later flight-plan changes do not need a restart or re-slot.')
p('You need Windows 10/11 x64 and your own installed DCS ASC C-130J. No separate Python installation is needed. Charts and navigation data come from your local DCS installation.','small')
h('Your first flight')
table(['Stage','What to do'],[
    ('1 / Departure','Choose an airport and runway direction on the map; <b>Confirm</b>.'),
    ('2 / Arrival','Choose the destination and runway direction; <b>Confirm</b>.'),
    ('3 / Procedures','Confirm departure routing, arrival routing and approach type.'),
    ('4 / En-route','Build the connection using fixes, airways or custom points.'),
    ('5 / Review','Check the complete plan and select <b>Route reviewed</b>.'),
    ('6 / CDU input','Choose <b>Manual</b> or <b>Automatic</b>. See pages 4-5.'),
])
note('<b>Before flying:</b> Review the actual CDU route, restrictions and navigation aids. Automatic entry stops before route activation / EXEC; those remain your cockpit actions.')
h('Find a feature')
p('<b>Review:</b> Check each route section, airport/runway, procedure and warning. Use its Edit button to correct a choice. Select <b>Route reviewed</b> to unlock CDU input; later plan changes require a fresh review.','small')
p('Airports and procedures 2 &nbsp; / &nbsp; Map and route editing 3<br/>Automatic entry 4 &nbsp; / &nbsp; Manual and kneeboard 5<br/>Saved plans, display and data 6 &nbsp; / &nbsp; Advanced inputs 7<br/>Troubleshooting and reference 8','small')

page(2,'Airports &amp; procedures','The planner opens each choice on the map. Confirm saves the draft; Cancel restores the previous selection.')
h('Airport and runway selection')
step(1,'Select departure or arrival.','Search for an airport or click its map marker. The floating box near the runway lists available runway directions.')
step(2,'Choose the direction.','The arrow shows the runway direction. Each choice shows its heading and associated ILS, where listed. Airports with several runways show all available choices.')
step(3,'Confirm.','The main screen shows the chosen airport/runway. Expand <b>Navigation aids</b> or <b>Airport frequencies</b> for details.')
note('<b>Map versus CDU:</b> Confirmed map runway labels follow DCS. The helper uses the matching ASC designation inside the CDU. A different number in the manual plan or CDU can therefore be intentional; do not replace it just to match the map.')
h('SID, STAR and approach')
p('<b>Choose departure routing</b> opens SID choices; <b>Choose arrival routing</b> opens STAR choices. Select the runway-compatible procedure and transition. Use <b>Previous</b>, <b>Next</b> or <b>Show preview</b> to compare choices. The view stays centred on the runway at the current zoom.')
p('Previews show known fix positions and available constraints. Gaps indicate legs without a position; connecting lines do not reproduce every vector, turn or arc. Confirmed valid SID, STAR and approach choices turn green on the main screen.')
p('Select <b>Approach type</b> on the main screen, then <b>Confirm approach</b>. Available ILS/TACAN or other aid details are briefings. The app does not supply a complete published instrument approach or its minima.')
h('When no matching SID or STAR is available')
table(['Choice','Use'],[
    ('ATC-cleared route / vectors','Plan subject to the applicable clearance. Follow ATC instructions in the cockpit.'),
    ('Visual / VMC planning','Plan subject to suitable visual conditions and your own terrain/obstacle review.'),
    ('Custom terminal-fix routing','Choose the planning basis, then add up to 12 terminal fixes in flight order. Reorder or remove them before confirming.'),
])
p('The terminal-fix list initially uses the selected airport. <b>Include nearby airports</b> adds labelled references from surrounding airports. A nearby fix does not become a published procedure or approach for your airport.','small')
p('Editing an airport or runway keeps en-route fixes where possible, but invalidates the affected procedure and review. Reconfirm them before loading.','small')

page(3,'Map &amp; route editing','Build the en-route connection between the confirmed departure and arrival routes. Switch selection modes with the three toggle buttons.')
table(['Mode','How to use it'],[
    ('Fixes / default','Click ASC fixes to add them to the route. Search for identifiers to find specific fixes.'),
    ('Airways','Click or search for an airway. Choose an entry and exit fix; the app expands the intervening segment and checks available direction restrictions.'),
    ('Custom waypoints','Click or click-drag to place a point. Drag its marker to move it. Select it, edit its identifier and choose <b>Rename</b>. Use a unique identifier.'),
])
p('Switching modes keeps existing route points. Airways become ordered fixes for CDU entry; they do not automatically select a cruise altitude.')
h('Map controls')
table(['Control','Action'],[
    ('Drag / mouse wheel','Drag to pan in normal selection modes; scroll to zoom. In Custom waypoints mode, <b>middle-drag</b> pans without placing a point.'),
    ('Search','Find airports, fixes or airways in the active mode.'),
    ('Home terrain / Fit route','Return to the terrain view, or frame the current route and terminal previews.'),
    ('Layer checkboxes','Show or hide en-route fixes, terminal fixes, airports/navaids, airways and labels.'),
    ('Airway level','Filter all, low-level or high-level airways. This changes the displayed choices, not the aircraft altitude.'),
])
h('Change an existing route')
p('Select a route fix or <b>SPD/ALT</b> for its popup. <b>Altitude / FL</b> share the upper input; <b>Speed / Mach</b> share the lower input. Scroll, use +/- or type, then <b>Apply</b>. Saved values always use knots and feet; buttons and master units change the display only. Mach needs altitude and uses an ISA/CAS estimate. Manual plans and kneeboard output use whole knots and feet.','small')
p('Right-click a route waypoint for <b>Remove waypoint</b>, <b>Insert before</b>, <b>Insert after</b>, <b>Replace waypoint</b> or <b>Start reroute from here</b>. Rerouting preserves the downstream route. Press <b>Escape</b> to end the insertion/reroute action.')
p('Use <b>Undo</b> / <b>Redo</b> for route edits, including custom point changes. <b>Ctrl+Z</b> undoes; <b>Ctrl+Shift+Z</b> redoes. <b>Cancel</b> discards the dialog draft; <b>Confirm</b> keeps it.')
p('For an intentional connection without intermediate fixes, select <b>Direct route</b>. Check that it suits your terminal routing and clearance. Review the complete route after any change.')
p('<b>Charts:</b> Installed local charts work offline; some areas have no underlay. Kola uses overview tiles when zoomed out and detailed sheets close up. First overview generation can take time. Use <b>Locate DCS</b> if the installation is not found.','small')

page(4,'Automatic CDU entry','Complete Review first. Load an unpaused C-130J cockpit with a powered, readable CDU, then choose Automatic in the app.')
table(['Setting','Effect'],[
    ('CDU / Pilot or Copilot','Chooses the CDU used for entry and the cockpit CAPS trigger.'),
    ('Input route / RTE 1 or 2','Chooses the route slot to load. Check it before arming.'),
    ('Replace route / off','Loads only an empty selected route. Existing route data stops the run.'),
    ('Replace route / on','Deletes the selected origin and legs, then verifies the route is empty before loading. The other route slot is retained.'),
    ('Input speed','<b>Default</b> uses the normal fast entry timing. <b>Accelerated</b> shortens allowable delays; acceptance checks still apply.'),
])
h('Start, stop and approve')
step(1,'Connect.','Check <b>DCS connected</b>, or choose <b>Connect</b>. Then select <b>Arm</b>. The route and settings are fixed for that run.')
step(2,'Return to DCS.','Double-click the selected CDU\'s <b>CAPS</b> key: two short presses/releases within two seconds. This starts entry without using the app again.')
step(3,'Let the helper work.','Avoid operating the selected CDU during entry. Double-click CAPS again, or select <b>Stop</b> in the app, to stop.')
step(4,'Approve a replacement only after checking it.','If a SID/STAR name is missing, entry pauses and the app proposes the closest name match. Hold the selected CDU CAPS key for <b>1.5 seconds, then release</b> to accept. Choose <b>Deny</b> in the app to reject and stop. There is no automatic acceptance.')
p('A name match does not establish equivalent routing. The message appears only in the app; no prompt text is typed into the CDU. Acceptance returns to the appropriate SID/STAR selection page.','small')
h('What happens automatically')
p('The helper clears the starting scratchpad, enters airports and route fixes, creates or updates custom point coordinates, selects available runway/procedure/transition menu items, then cleans LEGS. Cleanup removes discontinuities and <b>consecutive</b> repeats (A - A); later returns (A - B - A) remain.')
p('After cleanup, it matches fixes and enters optional <b>speed / altitude</b> in knots / feet, verifying each value. ASC applies altitude to later legs too; check arrival restrictions. Later planned values are entered in order. Ambiguity, rejection or failed readback stops loading. <b>Local test:</b> partial-entry syntax needs cockpit confirmation; negative altitudes require Manual.')
p('It then tunes destination ILS into <b>VOR 1</b>, TACAN into <b>TACAN 1</b>, and the ILS identifier into <b>INDEX 2 / NAV DATA / IDENT</b>. Missing or ambiguous aids are skipped. Receiver power and modes remain cockpit tasks.')
note('<b>Progress:</b> The percentage counts verified completed entries, not key presses. At 100%, review the CDU route, cleanup and radios before activation / EXEC. After a stop or error, review what is already loaded and deliberately re-arm a suitable empty/replacement route; loading does not resume by itself.')

page(5,'Manual plan &amp; kneeboard','Manual mode gives you the entire entry plan. There are no per-field checkboxes, Next buttons or confirmations.')
h('Read and use the plan')
step(1,'Select Manual.','A reviewed map route prepares its plan automatically. For Waypoints or IPRA, choose <b>Prepare manual plan</b>.')
step(2,'Choose RTE 1 or RTE 2.','Use the matching slot in the cockpit. Read route setup, departure, fixes, arrival, approach and radios. Custom identifiers and coordinates appear in Fixes; there is no separate Custom section.')
step(3,'Enter the values in DCS.','The Page column names the CDU page; the descriptor identifies Origin, Destination, Runway or Position. Fix coordinates identify database matches. Only the Fixes section has Speed and Altitude columns, with each fix kept on one row. Other sections retain the compact layout.')
step(4,'Review LEGS.','Remove discontinuities and consecutive duplicate fixes yourself, verify radios and restrictions, then decide whether to activate / EXEC.')
table(['Action','Result'],[
    ('Copy plan','Copies the complete text to the clipboard.'),
    ('Save text','Saves a plain-text copy for another screen or device.'),
    ('Save / print plan','Saves a self-contained HTML plan and opens it in your browser. Use its <b>Print / Save as PDF</b> control for paper or a PDF.'),
    ('Send to kneeboard','Publishes the current manual plan to the native C-130J CDU PLAN pages in DCS.'),
])
h('Use the live DCS kneeboard')
step(1,'Install once, then start DCS.','New or changed kneeboard scripts need an initial DCS load. Open the C-130J kneeboard using your normal DCS bindings and navigate to <b>CDU PLAN</b>.')
step(2,'Send the plan.','With the C-130J mission unpaused, choose <b>Send to kneeboard</b>. The app confirms an accepted transfer or explains why it failed.')
step(3,'Read it in the cockpit.','The page uses section bands and PAGE / FIELD / CDU VALUE columns with row borders. Wrapped values remain in one cell.')
step(4,'Change plans as needed.','Review and send the new plan. Once the scripts are loaded, later sends update the pages without restarting, re-slotting or reloading the mission.')
note('<b>Page slots:</b> Twenty kneeboard slots are reserved so long plans can arrive live. The footer shows the used-page count; unused slots show END OF PLAN. This is a reference page for manual entry. Sending it does not press CDU keys.')
p('Manual reading, copying and exporting do not need a DCS connection. Live kneeboard sending does need the installed bridge and a loaded page, and is blocked during automatic entry.','small')

page(6,'Saved plans, display &amp; data','Save the complete flight inside the app, then reload it without searching external folders.')
h('Save and load a flight')
step(1,'Save flight plan.','Enter a meaningful plan name and save. To update a stored flight, select it and use the save/update action. Use a different name for another copy.')
step(2,'Saved plans.','Search by plan name, airport or terrain. Select the flight, then choose <b>Load selected</b>.')
step(3,'Review again.','Loading restores terrain, airports, runways, procedures, approach, route/custom points and input/display preferences. It does not restart automatic entry or bypass review.')
p('Saved plans are retained during app updates and uninstall. After navigation data changes, a stored fix may need to be selected again. Save the current flight before changing terrain. <b>More / Import plan file</b> opens older external JSON plans.')
h('Master display controls')
table(['Control','Effect'],[
    ('Coordinates / DDM or DD','Switches coordinate displays and compatible input formatting. DDM means degrees and decimal minutes; DD means decimal degrees.'),
    ('Units / Imperial or Metric','Switches displayed altitude, distance and speed, and converts supported IPRA inputs and CSV elevation headings.'),
])
note('<b>CDU values stay native:</b> CDU coordinates are always DDM and numeric entries retain CDU units such as feet and nautical miles. Display preferences do not change the CDU payload. Printed labels inside raster charts remain in their original units.')
h('Terrain and reference data')
p('Choose <b>Terrain / ASC planning area</b> before planning. Supported areas include Caucasus, Nevada, Persian Gulf, Syria, Sinai, Mariana Islands, Kola, South Atlantic, Normandy, The Channel, Afghanistan, Iraq and Cold War Germany. Available data and chart coverage depend on your local installation.')
table(['More menu','Use'],[
    ('Airfield reference','View airport/runway details, communications and navigation aids for the current terrain.'),
    ('Refresh DCS airports','Refresh readable airport and beacon data after terrain updates. The current flight plan is retained.'),
    ('Import plan file','Import a legacy externally saved plan, then review it.'),
])
p('ASC data governs CDU runway and procedure selections, with confirmed DCS-to-ASC mappings where supplied. DCS navigation aids are stored separately and may have identifiers absent from ASC. Missing or ambiguous data is not guessed.','small')

page(7,'Advanced inputs','Use Entry data to choose Selected map route, Waypoints or IPRA. Automatic full-route loading uses the reviewed map route; the advanced editors prepare manual plans.')
h('Waypoint CSV')
p('Paste a CSV with <b>ident,lat,lon</b> and an optional <b>elevation_ft</b> or <b>elevation_m</b> column. Coordinates accept decimal degrees or compact DDM. Use negative DD for south/west, or S/W in DDM. Choose <b>Prepare manual plan</b>.')
p('ident,lat,lon,elevation_ft<br/>POINT1,42.5,43.5,1000<br/>POINT2,N4231.20,E04334.50,','code')
p('<b>Load fixes into editor</b> copies coordinate-bearing fixes from the selected ASC SID/STAR. It omits legs without coordinates and does not recreate restrictions, vectors or turn logic. Select actual published procedures through the normal planner/CDU DEP/ARR menus.')
p('<b>Save plan / Load plan</b> use external JSON. <b>Save flight plan / Saved plans</b> use the in-app library.','small')
h('Runway / IPRA')
p('IPRA is a manual approach-data plan. <b>Use selected arrival runway</b> fills available reference information. Enter and verify the remaining values; blank optional fields are omitted.')
table(['Field','Meaning'],[
    ('RPI identifier','A waypoint already in the active route as an intermediate point, not the origin or destination.'),
    ('Runway orientation','Course in degrees; match the CDU north reference.'),
    ('RPI elevation / MAP height','Reference-point elevation and height above threshold. CDU entry uses feet.'),
    ('RPI to FAF / FAF to IAF','Approach distances. CDU entry uses nautical miles.'),
    ('Glideslope / MAP to turn','Glideslope angle in degrees, plus missed-approach turn distance on IPRA page 2.'),
])
p('<b>Prepare runway position as a waypoint</b> moves its position to the Waypoints editor. Create and insert that point as an intermediate route waypoint first, review/execute it in the cockpit, then prepare the IPRA plan. On IPRA page 2, select category C or D in the cockpit and review before START.')
note('<b>Check the source:</b> Derived runway threshold positions are estimates. Missing elevation, distances, HAT and glideslope values are not invented. The app does not design or validate an instrument approach.')
h('Custom records and unknown airports')
p('Automatic loading creates or updates CUSTOM DATA positions under the same identifier, reusing correct positions. For a rejected airport code, it can use an unambiguous selected runway centre under the original code. Unavailable native runway/SID/STAR selections remain cockpit/planning decisions.')

page(8,'Troubleshooting &amp; reference','If automatic entry stops, read the app message and inspect the CDU before starting another run.')
table(['Symptom','Check / action'],[
    ('DCS not connected','Use the updated installer, start DCS once, enter the C-130J cockpit, unpause and power the selected CDU. Check the Pilot/Copilot setting. Export restrictions can block communication.'),
    ('Nothing happens after Arm','Double-click the selected <b>cockpit CDU CAPS</b> key, not the computer Caps Lock key. Fully release each press. Ensure DCS is running and unpaused.'),
    ('RTE must be empty','Check the selected route slot. Clear it in the cockpit, or deliberately enable <b>Replace route</b> to erase that slot before loading.'),
    ('SID/STAR replacement waiting','Read the app proposal. Hold CDU CAPS for 1.5 seconds and release to accept, or choose <b>Deny</b>. It will not accept itself.'),
    ('Unexpected page / rejected entry','Stop, inspect the CDU title, scratchpad and remaining route. Correct the plan or resolve the cockpit condition, then review and re-arm. Avoid pressing CDU keys during loading.'),
    ('Runway numbers differ','Map labels can use DCS while CDU input uses ASC. Check the confirmed runway mapping; do not assume both numbers must match.'),
    ('No chart or navigation aids','Check the terrain and <b>Locate DCS</b>. Use <b>More / Refresh DCS airports</b>. Some local sources are absent, encrypted or have no reliable association.'),
    ('Kneeboard page not loaded','Install the update and start DCS once. Open the C-130J kneeboard and find CDU PLAN, then send again while unpaused.'),
    ('No kneeboard reply / END OF PLAN','Unpause and check installation. END OF PLAN on reserved unused pages is normal; use the footer count to return to a used page.'),
    ('Stops during radio setup','Route entry may already be complete. Read the reported failed radio step; inspect VOR 1, TACAN 1 and NAV DATA separately before retrying.'),
],ratio=.29)
h('Status lights and support')
p('<b>DCS connected</b> means the bridge/CDU check passed. <b>Armed</b> means ready for the cockpit trigger. <b>Executing</b> means entry is running. A green planning choice indicates confirmed valid input, not flight clearance.')
p('For a fault report, include the app message, terrain, airport/runway, chosen route slot and a CDU screenshot. Automatic diagnostics are saved as <b>cdu-route-diagnostic.jsonl</b> beside the installed app executable.','small')
p('<b>Update / uninstall:</b> Run the new installer to update. Uninstall through Windows Settings / Apps or Uninstall.exe. Saved flights/logs and other exporters are preserved; modified user files are retained.','small')
p('<b>Licence:</b> Authorised recipients may use the app free of charge. Distribution requires the rights holder\'s permission. See the installed licence and third-party notices for full terms.','small')

def furniture(canvas,doc):
    canvas.saveState()
    w,h=A4
    canvas.setFillColor(NAVY);canvas.rect(0,h-14*mm,w,14*mm,fill=1,stroke=0)
    canvas.setFont('Helvetica-Bold',8);canvas.setFillColor(colors.white)
    canvas.drawString(18*mm,h-9*mm,'C-130J CDU HELPER')
    canvas.setFont('Helvetica',8);canvas.drawRightString(w-18*mm,h-9*mm,'PLAN  /  REVIEW  /  LOAD')
    canvas.setStrokeColor(RULE);canvas.line(18*mm,17*mm,w-18*mm,17*mm)
    canvas.setFillColor(MUTED);canvas.setFont('Helvetica',8)
    canvas.drawString(18*mm,11*mm,'C-130J CDU Helper  |  User guide  |  2 November 2026')
    canvas.drawRightString(w-18*mm,11*mm,f'{doc.page} / 8')
    canvas.bookmarkPage(f'page{doc.page}')
    titles=['Getting started','Airports and procedures','Map and route editing','Automatic CDU entry',
            'Manual plan and kneeboard','Saved plans, display and data','Advanced inputs','Troubleshooting']
    if doc.page<=len(titles):canvas.addOutlineEntry(titles[doc.page-1],f'page{doc.page}',level=0)
    canvas.restoreState()

if __name__=='__main__':
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    doc=SimpleDocTemplate(str(OUTPUT),pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,
        topMargin=23*mm,bottomMargin=23*mm,title='C-130J CDU Helper - User Guide',
        author='C-130J CDU Helper',subject='Flight planning, CDU loading and live kneeboard help')
    doc.build(story,onFirstPage=furniture,onLaterPages=furniture)
    from pypdf import PdfReader
    reader=PdfReader(OUTPUT)
    assert len(reader.pages)==8, f'Unexpected page overflow: {len(reader.pages)} pages'
    from pypdf import PdfWriter
    sections=OUTPUT.parent/'help'
    sections.mkdir(exist_ok=True)
    for index,page in enumerate(reader.pages,1):
        writer=PdfWriter();writer.add_page(page)
        writer.add_metadata({'/Title':f'C-130J CDU Helper - {index:02d} - '+[
            'Getting started and review','Airports and procedures','Map and route editing',
            'Automatic entry','Manual entry and kneeboard','Saved plans, display and data',
            'Advanced inputs','Troubleshooting'][index-1],'/Author':'C-130J CDU Helper'})
        writer.write(sections/f'C130J_Help_{index:02d}.pdf')
    print(OUTPUT)

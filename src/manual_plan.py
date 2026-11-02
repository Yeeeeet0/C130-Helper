"""Read-only manual CDU plans, rendered from validated entry data."""
from html import escape


def entry_descriptor(label):
    """Add a short field name where the page alone would be ambiguous."""
    descriptor={
        'Departure runway':'Runway','Arrival runway':'Runway',
        'SID alternative':'Routing','STAR alternative':'Routing',
        'Approach / manual briefing':'Basis',
        'Arrival ILS / VOR1':'VOR 1','Arrival TACAN / TAC1':'TACAN 1',
        'Arrival ILS / NAV DATA':'Ident',
        'RPI identifier':'RPI','Runway orientation (degrees; match CDU reference)':'Orientation',
        'RPI to FAF (NM)':'FAF (NM)','FAF to IAF (NM)':'IAF (NM)',
        'RPI elevation (ft)':'Elevation (ft)',
        'MAP height above threshold (ft)':'Height (ft)',
        'Glideslope angle (degrees)':'Slope','MAP to MAP turn (NM)':'Turn (NM)',
        'Connection':'Direct',
    }.get(label)
    if label.startswith('Departure /'):descriptor='Origin'
    elif label.startswith('Arrival /'):descriptor='Destination'
    elif label.startswith('SID /'):descriptor='SID'
    elif label.startswith('STAR /'):descriptor='STAR'
    if not descriptor:
        descriptor={'create':'Ident','identifier':'Ident','custom position':'Position',
            'position':'Position','elevation':'Elevation','route insertion':'Insert',
            'en-route fix':'Fix','custom departure fix':'Dep fix',
            'custom arrival fix':'Arr fix'}.get(label.partition(' / ')[2])
    return descriptor or ''


def build_report(prepared,kind,source,route=1):
    if route not in (1,2):raise ValueError('Choose RTE 1 or RTE 2')
    rows=[dict(r) for r in prepared['rows']]
    for row in rows:
        if row['label'].endswith(('/ create','/ identifier')) and 'CUSTOM DATA LIST' in row['page']:
            row['instruction']='Create this identifier, or open its existing record. Update POSITION (L2) with the planned coordinates and verify LAT/LON before route insertion.'
        if row.get('airport_fallback'):
            fallback=row['airport_fallback']
            row['instruction']='Use the ASC identifier. If unknown: open/create '+fallback['custom_ident']+' in CUSTOM DATA LIST, enter runway-centre '+fallback['position']+' in POSITION (L2), then return to RTE and enter the identifier.'
    sections=[]
    def section(title,items):
        if items:sections.append(dict(title=title,rows=items))
    def action(label,value,page,key='',instruction=''):
        return dict(label=label,value=value,page=page,key=key,instruction=instruction)
    def take(test):
        selected=[r for r in rows if test(r)]
        rows[:]=[r for r in rows if not test(r)]
        return selected
    title='CDU manual entry plan'
    subtitle={'navigation':'Route','waypoints':'Custom waypoints','ipra':'IPRA'}[kind]+f' · RTE {route}'
    section('Before entry',[action('Select route',f'RTE {route}','RTE',instruction=
        'Check the selected route and any existing legs before editing. Clear the scratchpad. This plan does not send keys to DCS.')])
    if kind=='navigation':
        airports=take(lambda r:r['label'].startswith(('Departure /','Arrival /')))
        subtitle=' → '.join(r['value'] for r in airports)+f' · RTE {route}'
        section('Route setup',airports)
        # Route fixes already include custom identifiers and coordinates.
        # Record creation stays available in the separate Waypoints workflow.
        take(lambda r:r['label'].endswith(('/ create','/ custom position')))
        runway_note='Select this ASC CDU runway designation for a recognised airport. If created as custom airport data, use terminal fixes or ATC guidance when native DEP/ARR menus are unavailable.'
        runway=prepared.get('manual_runways',{}).get('departure')
        menu=take(lambda r:r['label'].startswith('SID /') or r['label']=='SID alternative')
        if runway:menu.insert(0,action('Departure runway',runway,'DEP/ARR — departure',instruction=runway_note))
        section('Departure',menu)
        fixes=take(lambda r:r['page'].startswith('LEGS'))
        from route_constraints import manual_values
        for row in fixes:
            values=dict(manual_values(row.get('constraint')))
            row.update(speed=values.get('Speed',''),altitude=values.get('Altitude',''))
        if not fixes and source.get('connection')=='direct':
            fixes=[action('Connection','DIRECT','LEGS',instruction='No additional connecting fixes selected. Verify the connection between the terminal routes.')]
        section('Connecting fixes — in flight order',fixes)
        runway=prepared.get('manual_runways',{}).get('arrival')
        arrival=take(lambda r:r['label'].startswith('STAR /') or r['label']=='STAR alternative')
        if runway:arrival.insert(0,action('Arrival runway',runway,'DEP/ARR — arrival',instruction=runway_note))
        section('Arrival',arrival)
        section('Approach briefing',take(lambda r:r['label'].startswith('Approach /')))
        section('Arrival radios and navigation data',take(lambda r:r['label'].startswith(('Arrival ILS /','Arrival TACAN /'))))
    section({'navigation':'Additional entries','waypoints':'Waypoint entries — in order','ipra':'IPRA entries — in order'}[kind],rows)
    if kind!='ipra':
        section('Final route review',[action('Review every LEGS page','LEGS','LEGS',instruction=
            'Remove route discontinuities and consecutive duplicate waypoints. Preserve intentional later returns to a fix. Verify airports, runways, procedures, fixes and radios before deciding whether to EXEC in the cockpit.')])
    else:
        section('Final IPRA review',[action('Review IPRA','IPRA 1/2 → 2/2','IPRA',instruction=
            'The RPI must be an intermediate route waypoint. Select category C or D on page 2 and verify the complete procedure before deciding whether to START in the cockpit.')])
    compact_names={'Route setup':'Route',
        'Connecting fixes — in flight order':'Fixes','Approach briefing':'Approach',
        'Arrival radios and navigation data':'Radios','Additional entries':'Other',
        'Waypoint entries — in order':'Waypoints','IPRA entries — in order':'IPRA'}
    sections=[s for s in sections if s['title'] not in ('Before entry','Final route review','Final IPRA review')]
    for group in sections:
        group['title']=compact_names.get(group['title'],group['title'])
        group['fix_columns']=group['title']=='Fixes' and any(r['label']!='Connection' for r in group['rows'])
    step=0
    for group in sections:
        for row in group['rows']:
            step+=1;row['step']=step
            row['page']=row['page'].replace('RTE 1 (or your chosen standby route)',f'RTE {route}')
            if row['page'].startswith('LEGS'):row['page']='LEGS'
            row['page']={'DEP/ARR — departure':'DEP/ARR DEP','DEP/ARR — arrival':'DEP/ARR ARR',
                'Arrival briefing / manual approach selection':'Approach',
                'Departure/arrival briefing':'DEP/ARR',
                'INDEX page 2 → NAV DATA':'INDEX 2 → NAV DATA'}.get(row['page'],row['page'])
            row['entry']=row.get('entry') or entry_descriptor(row['label'])
            if row.get('manual_only'):row['key']='Cockpit selection'
            elif not row.get('key'):row['key']='Choose insertion row' if row['page'].startswith('LEGS') else '—'
    report=dict(title=title,subtitle=subtitle,route=route,sections=sections,
        note='All CDU coordinate entries are DDM. Numeric entries use the CDU units shown. Simulation use only. Verify in the cockpit.')
    report['text']=render_text(report)
    report['table_html']=render_table(report)
    report['html']=render_html(report)
    return report


def render_text(report):
    lines=[report['title'],report['subtitle'],'']
    rows=[r for group in report['sections'] for r in group['rows']]
    page_width=max([len(r['page']) for r in rows]+[4])
    field_width=max([len(r['entry']) for r in rows]+[5])
    lines.append(f'{"Page":<{page_width}} | {"Field":<{field_width}} | CDU value')
    for section in report['sections']:
        lines.append(section['title'].upper())
        if section.get('fix_columns'):lines.append(f'{"Page":<{page_width}} | {"Field":<{field_width}} | Fix / CDU value | Speed (kt) | Altitude (ft)')
        for row in section['rows']:
            line=f'{row["page"]:<{page_width}} | {row["entry"]:<{field_width}} | '+row['value']+('  '+row['position_ddm'] if row.get('position_ddm') else '')
            if section.get('fix_columns'):line+=' | '+(row.get('speed') or '—')+' | '+(row.get('altitude') or '—')
            lines.append(line)
    return '\n'.join(lines)


def render_table(report):
    esc=lambda value:escape(str(value),quote=True)
    body=''
    for section in report['sections']:
        body+='<tr class="manual-section"><th colspan="3">'+esc(section['title'])+'</th></tr>'
        if section.get('fix_columns'):
            body+='<tr class="fixes-container"><td colspan="3" class="fixes-wrap"><table class="fixes-table" aria-label="Fixes with speed and altitude"><colgroup><col class="page"><col class="field"><col class="fix-value"><col class="fix-speed"><col class="fix-altitude"></colgroup><thead><tr><th colspan="2">Page</th><th>Fix / CDU value</th><th>Speed (kt)</th><th>Altitude (ft)</th></tr></thead><tbody>'
        for row in section['rows']:
            position=' <small>'+esc(row['position_ddm'])+'</small>' if row.get('position_ddm') else ''
            cells=f'<td>{esc(row["page"])}</td><td>{esc(row["entry"])}</td><td><code>{esc(row["value"])}</code>{position}</td>'
            if section.get('fix_columns'):
                cells+='<td class="fix-speed-cell"><code>'+esc(row.get('speed') or '—')+'</code></td><td class="fix-altitude-cell"><code>'+esc(row.get('altitude') or '—')+'</code></td>'
            body+='<tr>'+cells+'</tr>'
        if section.get('fix_columns'):body+='</tbody></table></td></tr>'
    return '<table class="manual-main-table"><colgroup><col class="page"><col class="field"><col></colgroup><thead><tr><th colspan="2">Page</th><th>CDU value</th></tr></thead><tbody>'+body+'</tbody></table>'


def render_html(report):
    esc=lambda value:escape(str(value),quote=True)
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(report['subtitle'])+' — CDU plan</title><style>'+'''
body{font:13px/1.3 system-ui,sans-serif;color:#152535;background:#fff;margin:16px auto;padding:0 12px;max-width:1000px}h1{font-size:20px;margin:0 0 3px}p{margin:3px 0 8px}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{padding:4px 6px;text-align:left;border:1px solid #b8c5ce;vertical-align:top;overflow-wrap:anywhere}thead th{background:#dce8ee;font-size:11px}col.page{width:24%}col.field{width:14%}.manual-section th{padding:4px 6px;background:#edf2f5;font-size:12px}code{font:bold 14px/1.3 monospace;white-space:pre-wrap}small{font:11px/1.3 monospace;margin-left:8px;color:#415568}.tools{margin:8px 0}button{padding:7px 12px;cursor:pointer}@media(max-width:650px){body{padding:0 8px;margin:10px auto}code{font-size:13px}small{margin-left:4px;font-size:10px}}@page{size:A4 portrait;margin:10mm}@media print{body{max-width:none;margin:0;padding:0;font-size:10pt}.tools{display:none}h1{font-size:15pt}th,td{padding:3px 5px}code{font-size:10pt}small{font-size:8pt}thead{display:table-header-group}tr{break-inside:avoid}.manual-section{break-after:avoid}}
td.fixes-wrap{padding:0;border:0}.fixes-table{margin:0}.fixes-container{break-inside:auto}.fix-value{width:34%}.fix-speed{width:12%}.fix-altitude{width:16%}
'''+'</style></head><body><h1>'+esc(report['title'])+'</h1><p>'+esc(report['subtitle'])+'</p><div class="tools"><button onclick="window.print()">Print / Save as PDF</button></div>'+render_table(report)+'</body></html>'

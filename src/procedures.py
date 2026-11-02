"""Compose ASC runway/common/en-route procedure segments for the planner."""
import hashlib
from contextlib import closing
import itertools
import math
import json
import re
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict
from navigation import NAV_RELATIVE, finite_position, project
from runway_mappings import CONFIRMED,AIRFIELDS,confirmed_runway,map_runway_for,reference_runway_for

ALTERNATIVES = {
    'SID': {
        'atc': 'Plan a published obstacle departure if available, then join the ATC-cleared route. Obtain headings, altitude and clearance from the controller; no terrain-clearance route is generated here.',
        'visual': 'Plan a visual departure only in suitable VMC, maintaining terrain/obstacle clearance and complying with local procedures and ATC instructions before joining the en-route fix.',
    },
    'STAR': {
        'atc': 'Request ATC vectors or a cleared route to an appropriate published approach/IAF. Obtain the approach clearance and assigned altitudes; a direct airport line is not an instrument approach.',
        'visual': 'Plan a visual arrival only when weather, visibility and terrain permit; comply with local circuit/ATC instructions. Obtain a visual approach clearance when required.',
    },
}

# Confirmed from the user's live URMO ARRIVAL RWYS export and DCS reference.
# Keep the ASC procedure association intact; this is a cockpit menu alias.
CDU_RUNWAY_ALIASES = {(airport,r['source']):r['cdu'] for airport,rows in CONFIRMED.items() for r in rows if r['source']!=r['cdu']}
LIVE_CDU_RUNWAYS = {airport:{r['cdu'] for r in rows} for airport,rows in CONFIRMED.items()}


def reference_runway_details(airport_point):
    reference=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'assets/caucasus.sqlite'
    if not reference.is_file():return []
    with closing(sqlite3.connect(reference.as_uri()+'?mode=ro',uri=True)) as con:
        con.row_factory=sqlite3.Row
        fields=[dict(a) for a in con.execute('SELECT * FROM airfields')]
        exact=next((a for a in fields if a.get('airfield_id')==AIRFIELDS.get(airport_point['ident']) or a.get('icao_code')==airport_point['ident']),None)
        if exact and distance_nm(airport_point,dict(lat=exact['reference_lat_deg'],lon=exact['reference_lon_deg']))>=3:exact=None
        nearby=sorted([(distance_nm(airport_point,dict(lat=a['reference_lat_deg'],lon=a['reference_lon_deg'])),a)
                       for a in fields if finite_position(a.get('reference_lat_deg'),a.get('reference_lon_deg'))],key=lambda item:item[0])
        match=exact or (nearby[0][1] if nearby and nearby[0][0]<3 and (len(nearby)==1 or nearby[1][0]>=3 or nearby[0][0]<1 and nearby[1][0]-nearby[0][0]>.5) else None)
        if not match:return []
        return [dict(r) for r in con.execute('''SELECT e.*,r.length_m,r.airfield_id FROM runway_ends e JOIN runways r
            ON r.runway_id=e.runway_id WHERE r.airfield_id=?''',(match['airfield_id'],))]


def reference_runways(airport_point):
    return sorted({r['designator'] for r in reference_runway_details(airport_point)})


def cdu_runway_for(airport,source,saved=None):
    row=confirmed_runway(airport,source)
    verified=row['cdu'] if row else CDU_RUNWAY_ALIASES.get((airport,source)) or (source if source in LIVE_CDU_RUNWAYS.get(airport,set()) else None)
    if verified:
        if saved and saved not in (source,verified):
            raise ValueError('ASC RW'+source+' at '+airport+' corresponds to CDU RW'+verified+', not RW'+saved)
        return verified
    return saved or source


def runway_alignment(airport_point,asc_rows,reference_rows):
    result=[]
    for row in asc_rows:
        source=row['name']
        cdu=cdu_runway_for(airport_point['ident'],source)
        match=next((r for r in reference_rows if r['designator']==reference_runway_for(airport_point['ident'],source,cdu)),None)
        try:course=float(row['hdg']) if row['hdg'] not in (None,'') else None
        except (ValueError,TypeError):course=None
        if course is not None and not math.isfinite(course):course=None
        ref_course=match.get('true_course_deg') if match else None
        delta=abs((course-ref_course+180)%360-180) if course is not None and ref_course is not None else None
        known=cdu in LIVE_CDU_RUNWAYS.get(airport_point['ident'],set())
        status='Live CDU designation confirmed' if known else 'Designation agrees with DCS reference; not live-verified' if match else 'CDU designation not verified'
        if delta is not None and delta>15:status+='; course sources disagree — check reference'
        candidate=None
        if match is None:
            try:
                position=dict(lat=float(row['lat']),lon=float(row['lon']))
                candidates=[r for r in reference_rows if finite_position(r.get('threshold_lat_deg'),r.get('threshold_lon_deg'))]
                candidates.sort(key=lambda r:distance_nm(position,dict(lat=r['threshold_lat_deg'],lon=r['threshold_lon_deg'])))
                if candidates:
                    near=candidates[0];dist=distance_nm(position,dict(lat=near['threshold_lat_deg'],lon=near['threshold_lon_deg']))
                    angle=abs((course-near['true_course_deg']+180)%360-180) if course is not None and near.get('true_course_deg') is not None else 180
                    if dist<1.5 and angle<15:candidate=near['designator']
            except (ValueError,TypeError,KeyError):pass
        result.append(dict(airport=airport_point['ident'],asc_runway=source,cdu_runway=cdu,
                           live_verified=known,asc_course=course,asc_course_reference='unspecified',
                           dcs_true_course=ref_course,course_difference=delta,status=status,
                           reference_candidate=candidate))
    return result


def distance_nm(a,b):
    lat1,lat2=math.radians(a['lat']),math.radians(b['lat'])
    dlat=lat2-lat1;dlon=math.radians(b['lon']-a['lon'])
    h=math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 3440.065*2*math.asin(math.sqrt(min(1,max(0,h))))


def terminal_candidates(nav,airport):
    results=[]
    for point in nav.points.values():
        if point['kind']!='TERMINAL':
            continue
        distance=distance_nm(airport,point)
        if distance<=80:
            results.append(dict(point=point,distance_nm=distance,associated=point.get('airport')==airport['ident']))
    return sorted(results,key=lambda r:(not r['associated'],r['distance_nm'],r['point']['ident']))


def runway_match(transition, runway):
    transition = (transition or '').strip().upper()
    if not transition.startswith('RW') or transition in ('RWALL', 'RW'):
        return True
    value = transition[2:]
    return value == runway or (value.endswith('B') and runway[:2] == value[:2] and runway[-1:] in ('L','R'))


def compose(records, kind, runway, theatre='Caucasus'):
    groups = defaultdict(lambda: defaultdict(list))
    for row in records:
        groups[row['procedure_identifier']][(str(row['route_type']), row['transition_identifier'] or '')].append(row)
    variants = []
    for name, parts in groups.items():
        for family in [(1,2,3),(4,5,6)]:
            ordered = []
            for route_type in family:
                options = [(key,legs) for key,legs in parts.items() if key[0] == str(route_type) and runway_match(key[1],runway)]
                # A runway-specific component exists but is incompatible: do not
                # silently offer the remaining common/en-route portion alone.
                if not options and any(key[0] == str(route_type) for key in parts):
                    ordered=[];break
                ordered.append(options or [(None,[])])
            if not ordered:
                continue
            for combination in itertools.product(*ordered):
                if not any(key is not None for key,_ in combination):
                    continue
                legs=[]
                for key,segment in combination:
                    legs.extend(sorted(segment,key=lambda r:r['seqno']))
                # SID: runway/common/enroute; STAR: enroute/common/runway.
                transitions=[key[1] for key,_ in combination if key and key[1] and not key[1].startswith('RW') and key[1]!='ALL']
                serial=json.dumps(legs,sort_keys=True,separators=(',',':'))
                uid=hashlib.sha256((kind+runway+serial).encode()).hexdigest()[:24]
                points=[]
                preview=[]
                for leg in legs:
                    lat,lon=leg['waypoint_latitude'],leg['waypoint_longitude']
                    if finite_position(lat,lon):
                        east,north=project(lat,lon,theatre)
                        p=dict(id='proc:'+uid+':'+str(len(preview)),ident=leg['waypoint_identifier'] or '?',lat=lat,lon=lon,x=east,y=north,kind='PROCEDURE')
                        points.append(p)
                    else:
                        p=None
                    preview.append(dict(point=p,path=leg['path_termination'],altitude1=leg['altitude1'],altitude2=leg['altitude2'],altitude_description=leg['altitude_description'],speed=leg['speed_limit'],course=leg.get('magnetic_course')))
                if not points:
                    continue
                variants.append(dict(id=uid,name=name,kind=kind,runway=runway,transition=' / '.join(dict.fromkeys(transitions)),
                                     legs=preview,points=points,anchor=points[-1] if kind=='SID' else points[0],
                                     schematic=True))
    return sorted(variants,key=lambda v:(v['name'],v['transition']))


def airport_options(nav, airport, kind, runway=''):
    nav.load()
    if kind not in ('SID','STAR') or not re.fullmatch('[A-Z0-9]{1,8}',airport):
        raise ValueError('Select an airport and SID or STAR')
    if not any(p['kind']=='AIRPORT' and p['ident']==airport for p in nav.points.values()):
        raise ValueError('Departure and arrival must be ASC airports')
    with closing(sqlite3.connect((nav.root/NAV_RELATIVE).as_uri()+'?mode=ro',uri=True)) as con:
        con.row_factory=sqlite3.Row
        runways={str(r[0]).strip().upper() for r in con.execute('SELECT name FROM runways WHERE icao=?',(airport,))}
        runway_details=[dict(r) for r in con.execute('SELECT * FROM runways WHERE icao=?',(airport,))]
        airport_details=dict(con.execute('SELECT * FROM airports WHERE icao=?',(airport,)).fetchone() or {})
        table='sids' if kind=='SID' else 'stars'
        records=[dict(r) for r in con.execute(f'SELECT * FROM {table} WHERE airport_identifier=? ORDER BY procedure_identifier,route_type,transition_identifier,seqno',(airport,))]
        runways.update((r['transition_identifier'] or '')[2:] for r in records if re.fullmatch(r'RW\d{2}[LRC]?',r['transition_identifier'] or ''))
    runways=sorted(runways)
    if nav.theatre=='Caucasus' and airport in CONFIRMED:runways=[r['source'] for r in CONFIRMED[airport]]
    if not runways:runways=sorted(LIVE_CDU_RUNWAYS.get(airport,set()))
    if runway and runway not in runways:
        raise ValueError('Runway is not available for this airport')
    variants=compose(records,kind,runway,nav.theatre) if runway else []
    airport_point=next(p for p in nav.points.values() if p['kind']=='AIRPORT' and p['ident']==airport)
    reference_details=reference_runway_details(airport_point)
    # Use the selected runway threshold as the stable procedure-preview centre.
    cdu_runway=cdu_runway_for(airport,runway)
    reference_end=next((r for r in reference_details if r['designator']==reference_runway_for(airport,runway,cdu_runway)),{})
    native_end=next((r for r in runway_details if r['name']==runway),{})
    focus=airport_point
    positions=[(native_end.get('lat'),native_end.get('lon')),(reference_end.get('threshold_lat_deg'),reference_end.get('threshold_lon_deg'))]
    if confirmed_runway(airport,runway):positions.reverse()
    for lat,lon in positions:
        try:lat,lon=float(lat),float(lon)
        except (TypeError,ValueError):continue
        if finite_position(lat,lon):
            x,y=project(lat,lon,nav.theatre)
            focus=dict(lat=lat,lon=lon,x=x,y=y)
            break
    cockpit_runways=sorted(LIVE_CDU_RUNWAYS.get(airport,{r['designator'] for r in reference_details}))
    nearby_navaids=[]
    for point in nav.points.values():
        if point['id'].startswith('n:') and point['kind'] in ('VOR','TACAN','NDB','ILS','DME'):
            distance=distance_nm(airport_point,point)
            if distance<=15:
                nearby_navaids.append(dict(point=point,distance_nm=distance))
    nearby_navaids.sort(key=lambda n:n['distance_nm'])
    directions=runway_direction_options(airport_point,runways,runway_details,reference_details,nav.theatre)
    return dict(airport=airport,kind=kind,runways=runways,runway=runway,procedures=variants,alternatives=ALTERNATIVES[kind],
                runway_choices=[dict(source=r,designation=map_runway_for(airport,r),cdu_designation=cdu_runway_for(airport,r)) for r in runways],
                runway_focus={k:focus[k] for k in ('lat','lon','x','y')},runway_directions=directions,
                dcs_reference=airport_point.get('dcs_airport'),
                terminal_fixes=terminal_candidates(nav,airport_point),runway_details=runway_details,airport_details=airport_details,
                cockpit_runways=cockpit_runways,suggested_cdu_runway=cdu_runway_for(airport,runway),nearby_navaids=nearby_navaids,
                runway_alignment=runway_alignment(airport_point,runway_details,reference_details))


def runway_direction_options(airport,runways,details,references,theatre):
    from arrival_radios import arrival_radios
    result=[]
    for source in runways:
        cdu=cdu_runway_for(airport['ident'],source)
        designation=map_runway_for(airport['ident'],source)
        confirmed=confirmed_runway(airport['ident'],source)
        native=next((r for r in details if r['name']==source),{})
        ref_designator=reference_runway_for(airport['ident'],source,cdu)
        reference=next((r for r in references if r['designator']==ref_designator),{})
        point=None
        positions=[(native.get('lat'),native.get('lon')),(reference.get('threshold_lat_deg'),reference.get('threshold_lon_deg'))]
        if confirmed:positions.reverse()
        for lat,lon in positions:
            try:lat,lon=float(lat),float(lon)
            except (ValueError,TypeError):continue
            if finite_position(lat,lon):
                x,y=project(lat,lon,theatre);point=dict(lat=lat,lon=lon,x=x,y=y);break
        try:heading=float(native.get('hdg'))
        except (ValueError,TypeError):heading=None
        if heading is not None and not math.isfinite(heading):heading=None
        if confirmed:heading=confirmed['true_heading']
        ils=arrival_radios(airport,dict(runway=source,cdu_runway=cdu))['ils']
        result.append(dict(source=source,designation=designation,cdu_designation=cdu,reference_designator=ref_designator,confirmed=bool(confirmed),heading=heading,threshold=point,ils=ils,opposite=None))
    for direction in result:
        match=re.fullmatch(r'(\d{1,2})([LRC]?)',direction['source'])
        if not match or not 1<=int(match[1])<=36:continue
        number=(int(match[1])+17)%36+1;suffix={'L':'R','R':'L','C':'C','':''}[match[2]]
        candidates=[r for r in result if (m:=re.fullmatch(r'(\d{1,2})([LRC]?)',r['source'])) and int(m[1])==number and m[2]==suffix]
        if len(candidates)==1:direction['opposite']=candidates[0]['source']
    return result


def selected_runway_position(nav,airport,terminal):
    """Use the geographic midpoint of the selected ASC runway's two ends."""
    runway=terminal.get('runway')
    if not runway:return None
    database=nav.root/NAV_RELATIVE
    if not database.is_file():return None
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as con:
        con.row_factory=sqlite3.Row
        rows=[dict(r) for r in con.execute('SELECT * FROM runways WHERE icao=?',(airport['ident'],))]
    if confirmed_runway(airport['ident'],runway):
        references=reference_runway_details(airport)
        native={r['name']:r for r in rows};mapped=[]
        for mapping in CONFIRMED[airport['ident']]:
            ref=next((r for r in references if r['designator']==mapping['reference']),{})
            row=native.get(mapping['source'],{})
            mapped.append(dict(name=mapping['source'],lat=ref.get('threshold_lat_deg',row.get('lat')),lon=ref.get('threshold_lon_deg',row.get('lon'))))
        rows=mapped
    selected=[r for r in rows if r['name']==runway]
    match=re.fullmatch(r'(\d{1,2})([LRC]?)',runway)
    if len(selected)!=1 or not match or not 1<=int(match[1])<=36:return None
    opposite=(int(match[1])+17)%36+1
    suffix={'L':'R','R':'L','C':'C','':''}[match[2]]
    paired=[r for r in rows if (m:=re.fullmatch(r'(\d{1,2})([LRC]?)',r['name'])) and int(m[1])==opposite and m[2]==suffix]
    if len(paired)!=1:return None
    try:ends=[dict(lat=float(r['lat']),lon=float(r['lon'])) for r in [selected[0],paired[0]]]
    except (TypeError,ValueError):return None
    if any(not finite_position(p['lat'],p['lon']) or distance_nm(airport,p)>5 for p in ends):return None
    if not .01<distance_nm(*ends)<6.5:return None
    vectors=[(math.cos(math.radians(p['lat']))*math.cos(math.radians(p['lon'])),
              math.cos(math.radians(p['lat']))*math.sin(math.radians(p['lon'])),math.sin(math.radians(p['lat']))) for p in ends]
    x,y,z=[sum(v[i] for v in vectors) for i in range(3)]
    lat=math.degrees(math.atan2(z,math.hypot(x,y)));lon=math.degrees(math.atan2(y,x))
    return dict(ident=airport['ident'],custom_ident=airport['ident'],runway=terminal.get('cdu_runway') or runway,lat=lat,lon=lon)


def validate_terminal(nav, airport, choice, kind):
    if not airport or airport['kind']!='AIRPORT':
        raise ValueError('Select departure and arrival airports first')
    if not isinstance(choice,dict):
        raise ValueError('Select a runway and procedure or alternative for both airports')
    options=airport_options(nav,airport['ident'],kind,choice.get('runway',''))
    cdu_runway=cdu_runway_for(airport['ident'],options['runway'],choice.get('cdu_runway'))
    if cdu_runway and cdu_runway not in set(options['runways'])|set(options.get('cockpit_runways',[])):
        raise ValueError('CDU runway is not in the ASC or DCS reference choices')
    if options['runways'] and not options['runway']:
        raise ValueError('Select a runway for '+airport['ident'])
    if choice.get('mode')=='procedure':
        variant=next((p for p in options['procedures'] if p['id']==choice.get('procedure_id')),None)
        if not variant:
            raise ValueError('The selected procedure no longer matches the airport/runway. Re-select it.')
        return dict(mode='procedure',runway=options['runway'],cdu_runway=cdu_runway,procedure=variant)
    if choice.get('mode')=='terminal':
        basis=choice.get('basis','atc')
        if basis not in ALTERNATIVES[kind]:
            raise ValueError('Choose ATC-cleared or visual/VMC planning for terminal fixes')
        saved_points=choice.get('fixes')
        if not isinstance(saved_points,list) or not 1<=len(saved_points)<=12:
            raise ValueError('Choose 1–12 terminal fixes in flight order')
        points=[nav.resolve(p) for p in saved_points]
        for i,point in enumerate(points):
            if point['kind']!='TERMINAL' or distance_nm(airport,point)>80:
                raise ValueError('Choose terminal fixes from the local planning area (within 80 NM)')
            if i and point['id']==points[i-1]['id']:
                raise ValueError('Remove consecutive duplicate terminal fixes')
        guidance=ALTERNATIVES[kind][basis]+' Selected terminal fixes are custom planning points, not a published SID, STAR or approach. Their presence does not establish terrain clearance, altitude minima or runway suitability.'
        return dict(mode='terminal',runway=options['runway'],cdu_runway=cdu_runway,basis=basis,guidance=guidance,fixes=points,
                    anchor=points[-1] if kind=='SID' else points[0])
    mode=choice.get('mode')
    if mode not in ALTERNATIVES[kind]:
        raise ValueError('Choose a published procedure or an alternative planning method')
    return dict(mode=mode,runway=options['runway'],cdu_runway=cdu_runway,guidance=ALTERNATIVES[kind][mode])


def validate_plan(nav,plan):
    origin=nav.resolve(plan.get('origin'));destination=nav.resolve(plan.get('destination'))
    if origin['id']==destination['id']:
        raise ValueError('Choose different departure and arrival airports')
    return dict(departure=validate_terminal(nav,origin,plan.get('departure'),'SID'),
                arrival=validate_terminal(nav,destination,plan.get('arrival'),'STAR'))

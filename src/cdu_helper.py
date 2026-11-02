"""CNI entry and cockpit-triggered route loading."""
from __future__ import annotations

import csv
import io
import json
import math
import re
import socket
import sqlite3
import threading
import uuid
import time
import sys
from pathlib import Path
from navigation import Navigation,unproject
from procedures import airport_options, validate_plan,selected_runway_position
from arrival_radios import arrival_radios

ADDRESS = ('127.0.0.1', 31330)


def number(value, label, minimum, maximum):
    if value is None or str(value).strip() == '':
        raise ValueError(f'{label} is required')
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f'{label} must be between {minimum} and {maximum}')
    return result


def coordinate(value, latitude):
    value = parse_coordinate(value, latitude)
    value = number(value, 'Latitude' if latitude else 'Longitude', -90 if latitude else -180, 90 if latitude else 180)
    # Round total minutes first so 59.999 minutes carries into the degree.
    hundredths = int(math.floor(abs(value) * 6000 + 0.5))
    degrees, minutes = divmod(hundredths, 6000)
    hemisphere = ('S' if value < 0 else 'N') if latitude else ('W' if value < 0 else 'E')
    return f'{hemisphere}{degrees:0{2 if latitude else 3}d}{minutes / 100:05.2f}'


def parse_coordinate(value, latitude):
    text = re.sub(r"[°′'\s]", '', str(value).upper())
    if text[:1] in ('N','S','E','W'):
        pattern = r'([NS])(\d{2})(\d{2}(?:\.\d+)?)' if latitude else r'([EW])(\d{3})(\d{2}(?:\.\d+)?)'
        match = re.fullmatch(pattern,text)
        if not match or float(match[3]) >= 60:
            raise ValueError('Invalid DDM coordinate; use N4230.00 or E04143.00')
        value = (int(match[2])+float(match[3])/60)*(-1 if match[1] in ('S','W') else 1)
    return number(value,'Latitude' if latitude else 'Longitude',-90 if latitude else -180,90 if latitude else 180)


def identifier(value):
    value = str(value).strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{1,8}', value):
        raise ValueError('Use an identifier of 1–8 letters or digits; check availability in the CDU')
    return value


def field(label, value, page, key, instruction):
    return dict(label=label, value=value, page=page, key=key, instruction=instruction)


def waypoint_rows(text):
    rows = []
    reader = csv.DictReader(io.StringIO(text.strip()))
    if not reader.fieldnames or not {'ident', 'lat', 'lon'}.issubset(reader.fieldnames):
        raise ValueError('CSV needs headers ident,lat,lon,elevation_ft (elevation is optional)')
    for line, row in enumerate(reader, 2):
        if line > 101:
            raise ValueError('Prepare at most 100 waypoints at a time')
        try:
            name = identifier(row['ident'])
            position = coordinate(row['lat'], True) + coordinate(row['lon'], False)
            rows.append(field(name + ' / identifier', name, 'CUSTOM DATA LIST', 'L1',
                              'Open INDEX → CUSTOM DATA LIST. Use a new identifier; an existing identifier may open stored data.'))
            position_row=field(name + ' / position', position, name + ' CUSTOM DATA', 'L2',
                               'Enter coordinates into POSITION (L2), then verify LAT/LON. CDU entry is always DDM.')
            position_row['position']={'lat':parse_coordinate(row['lat'],True),'lon':parse_coordinate(row['lon'],False)}
            rows.append(position_row)
            elevation_text = row.get('elevation_m') if 'elevation_m' in row else row.get('elevation_ft','')
            if elevation_text and elevation_text.strip():
                elevation = number(float(elevation_text)/.3048 if 'elevation_m' in row else elevation_text, 'Elevation (ft)', -1500, 60000)
                elevation_row=field(name + ' / elevation', str(round(elevation)), name + ' CUSTOM DATA', 'L3', 'CDU entry is in feet.')
                elevation_row['measurement']={'value':round(elevation),'type':'alt'}
                rows.append(elevation_row)
            rows.append(field(name + ' / route insertion', name, 'LEGS — choose insertion row', '',
                              'Open the desired route LEGS page. Select the left key for the insertion position after checking the route.'))
        except (ValueError, TypeError, AttributeError) as ex:
            raise ValueError(f'CSV row {line}: {ex}') from ex
    if not rows:
        raise ValueError('Add at least one waypoint')
    return rows


def ipra_rows(data):
    name = identifier(data.get('rpi', ''))
    rows = [field('RPI identifier', name, 'IPRA 1/2', 'L1',
                  'First add this waypoint to the active route as an intermediate point, not the origin or destination. Open MC INDX → IPRA.')]
    for key, label, lsk, low, high in [
        ('course', 'Runway orientation (degrees; match CDU reference)', 'L2', 0, 360),
        ('faf', 'RPI to FAF (NM)', 'L3', 0.1, 99.9),
        ('iaf', 'FAF to IAF (NM)', 'L4', 0.1, 99.9),
        ('elevation', 'RPI elevation (ft)', 'R1', -1500, 60000),
        ('hat', 'MAP height above threshold (ft)', 'R2', 0, 10000),
        ('slope', 'Glideslope angle (degrees)', 'R3', 0.1, 10),
        ('map', 'MAP to MAP turn (NM)', 'L1', 0.1, 99.9),
    ]:
        value = data.get(key, '')
        if str(value).strip():
            value = number(value, label, low, high)
            rows.append(field(label, f'{value:g}', 'IPRA 2/2' if key == 'map' else 'IPRA 1/2', lsk,
                              'Check units and displayed value in the CDU. Limits here are input sanity checks, not aircraft performance limits.'))
            if key in ('faf','iaf','map','elevation','hat'):
                rows[-1]['measurement']={'value':value,'type':'alt' if key in ('elevation','hat') else 'distance'}
    return rows


def key_sequence(text, lsk=''):
    if not isinstance(text, str) or not 1 <= len(text) <= 48 or not re.fullmatch(r'[A-Z0-9./ +\-]+', text):
        raise ValueError('Entry must contain 1–48 CDU characters (A–Z, digits, space, . / + -)')
    if lsk and not re.fullmatch(r'[LR][1-6]', lsk):
        raise ValueError('Choose L1–L6, R1–R6 or scratchpad only')
    special = {'.': 'KBD_DOT', '/': 'KBD_SLASH', ' ': 'KBD_SPACE', '+': 'KBD_PLUSMINUS', '-': 'KBD_PLUSMINUS'}
    keys = [special.get(char, 'KBD_' + char) for char in text]
    if lsk:
        keys.append('SELECT_' + str(int(lsk[1]) + (6 if lsk[0] == 'R' else 0)))
    return keys


class CduApi:
    def open_help(self,topic='all'):
        from help_documents import open_document
        try:return open_document(topic)
        except (ValueError,OSError) as ex:return {'error':str(ex)}

    def __init__(self):
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._state = dict(running=False, connected=False, armed=False, executing=False, sent=0, total=0, message='Ready.')
        self._navigation = Navigation()

    def navigation_data(self, theatre=None):
        try:
            return self._navigation.load(theatre)
        except Exception as ex:
            return {'error': str(ex)}

    def airport_procedures(self, airport, kind, runway=''):
        try:
            return airport_options(self._navigation, airport, kind, runway)
        except Exception as ex:
            return {'error':str(ex)}

    def preview_flight_plan(self, plan):
        try:
            self._navigation.load(plan.get('terrain','Caucasus'))
            return validate_plan(self._navigation,plan)
        except (ValueError,TypeError,KeyError) as ex:
            return {'error':str(ex)}

    def chart_tile(self, key):
        try:
            return self._navigation.tile(key)
        except Exception as ex:
            return {'error': str(ex)}

    def choose_dcs(self):
        import webview
        paths = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not paths:
            return {'cancelled': True}
        candidate = Navigation(paths[0])
        try:
            result = candidate.load()
            self._navigation = candidate
            return result
        except Exception as ex:
            return {'error': str(ex)}

    def airway_segment(self, key, start, end):
        try:
            return self._navigation.airway_slice(key, start, end)
        except (ValueError, TypeError) as ex:
            return {'error': str(ex)}

    def custom_waypoint(self,x,y,ident):
        try:
            self._navigation.load()
            x=number(x,'Map easting',-20000000,20000000);y=number(y,'Map northing',-20000000,20000000)
            lat,lon=unproject(x,y,self._navigation.theatre)
            return self._navigation.resolve(dict(id='custom:'+ident,ident=ident,kind='CUSTOM',lat=lat,lon=lon),allow_custom=True)
        except (ValueError,TypeError,KeyError) as ex:return {'error':str(ex)}

    def prepare_database_route(self, plan):
        try:
            if not isinstance(plan, dict) or not isinstance(plan.get('points'), list) or len(plan['points']) > 100:
                raise ValueError('A route can contain at most 100 intermediate fixes')
            if plan.get('terrain'):
                self._navigation.load(plan['terrain'])
            rows = []
            terminals = validate_plan(self._navigation, plan) if plan.get('workflow') == 2 else None
            if terminals and not plan['points'] and plan.get('connection')!='direct':
                raise ValueError('Choose connecting fixes/airways or explicitly select a direct connection')
            airport_fallbacks={}
            for role, label, key in [('origin', 'Departure', 'L1'), ('destination', 'Arrival', 'R1')]:
                if plan.get(role):
                    point = self._navigation.resolve(plan[role])
                    rows.append(field(label+' / '+point['ident'], identifier(point['ident']), 'RTE 1 (or your chosen standby route)', key,
                                      'Use the existing ASC database identifier. Check any CDU identifier-selection page against the selected coordinates. Enter an origin before the destination.'))
                    if terminals:
                        fallback=selected_runway_position(self._navigation,point,terminals['departure' if role=='origin' else 'arrival'])
                        if fallback:
                            fallback['position']=coordinate(fallback['lat'],True)+coordinate(fallback['lon'],False)
                            airport_fallbacks[role]=fallback
                            rows[-1]['airport_fallback']=fallback
                            rows[-1]['instruction']+=' If this airport is unknown, create '+fallback['custom_ident']+' via CUSTOM DATA LIST using runway '+fallback['runway']+' centre '+fallback['position']+' in POSITION (L2), then use '+fallback['custom_ident']+' in RTE.'
            if terminals:
                for side,kind in [('departure','SID'),('arrival','STAR')]:
                    terminal=terminals[side]
                    if terminal['mode']=='procedure':
                        p=terminal['procedure']
                        row=field(kind+' / '+p['name'],p['name']+' · RW'+(terminal.get('cdu_runway') or terminal['runway'])+(' · '+p['transition'] if p['transition'] else ''),'DEP/ARR — '+side,'',
                                  'Select this published procedure and transition in the CDU DEP/ARR menus, then verify the legs and restrictions. This is a cockpit selection step, not scratchpad text; do not recreate its legs as direct waypoints.')
                    else:
                        row=field(kind+' alternative',terminal['mode'].upper()+(' · RW'+terminal['runway'] if terminal['runway'] else ''),'Departure/arrival briefing','',terminal['guidance'])
                    row['manual_only']=True
                    rows.append(row)
            ordered=[]
            if terminals and terminals['departure']['mode']=='terminal':
                ordered.extend((p,'custom departure') for p in terminals['departure']['fixes'])
            ordered.extend((p,'en-route') for p in plan['points'])
            if terminals and terminals['arrival']['mode']=='terminal':
                ordered.extend((p,'custom arrival') for p in terminals['arrival']['fixes'])
            previous=None
            previous_constraint={}
            custom_positions={}
            for saved,role in ordered:
                from route_constraints import normalise_constraint
                constraint=normalise_constraint(saved.get('constraint'))
                point = self._navigation.resolve(saved,allow_custom=True)
                if previous==point['id']:
                    if constraint!=previous_constraint:raise ValueError('Consecutive duplicate fixes have different speed/altitude entries. Remove the duplicate or match the entries.')
                    continue
                previous=point['id']
                previous_constraint=constraint
                if point.get('kind')=='CUSTOM':
                    pos=coordinate(point['lat'],True)+coordinate(point['lon'],False)
                    if point['ident'] in custom_positions and custom_positions[point['ident']]!=pos:raise ValueError('Custom waypoint identifier has multiple positions: '+point['ident'])
                    custom_positions[point['ident']]=pos
                    rows.append(field(point['ident']+' / create',point['ident'],'INDEX 2 → CUSTOM DATA LIST','L1','Create or open this custom waypoint; verify the identifier.'))
                    rows.append(field(point['ident']+' / custom position',coordinate(point['lat'],True)+coordinate(point['lon'],False),point['ident']+' CUSTOM DATA','L2','Enter the planned position in DDM, then insert the identifier into the route.'))
                row=field(point['ident']+' / '+role+' fix', identifier(point['ident']), 'LEGS — '+role+' section', '',
                          'Insert in flight order in the indicated route section. If the CDU offers duplicate identifiers, select the matching position. Custom terminal fixes are not a published procedure or an obstacle-cleared approach.')
                row['position']={'lat':point['lat'],'lon':point['lon']}
                if constraint:row['constraint']=constraint
                if point.get('kind')=='CUSTOM':row['custom_waypoint']=dict(ident=point['ident'],position=coordinate(point['lat'],True)+coordinate(point['lon'],False))
                rows.append(row)
            if not rows:
                raise ValueError('Select at least one route point on the map')
            if plan.get('approach'):
                approach=plan['approach']
                if not isinstance(approach,dict) or approach.get('mode') not in ('atc','visual','aid'):
                    raise ValueError('Choose an approach planning basis')
                row=field('Approach / manual briefing',str(approach.get('label','Approach planning'))[:200],
                          'Arrival briefing / manual approach selection','',
                          'No published approach legs or minima are supplied by this dataset. Verify the selected aid / clearance and configure the approach manually in the cockpit.')
                row['manual_only']=True
                rows.append(row)
            radios = arrival_radios(self._navigation.resolve(plan['destination']), terminals['arrival']) if terminals and plan.get('destination') else {}
            if radios.get('ils'):
                aid=radios['ils']
                rows.append(field('Arrival ILS / VOR1', aid['frequency'], 'NAV TUNE INDEX', 'R1', 'Destination runway '+aid['runway']+' ILS '+aid['ident']+'. Verify VOR1 active frequency.'))
            if radios.get('tacan'):
                aid=radios['tacan']
                rows.append(field('Arrival TACAN / TAC1', aid['channel'], 'NAV TUNE INDEX', 'R3', 'Destination TACAN '+str(aid['ident'] or '')+'. Verify TAC1 active channel and band.'))
            if radios.get('ils'):
                rows.append(field('Arrival ILS / NAV DATA', radios['ils']['ident'], 'INDEX page 2 → NAV DATA', 'L1', 'Enter the ILS identifier in IDENT and verify the station details.'))
            return {'rows': rows, 'arrival_radios': radios,'custom_waypoints':[dict(ident=ident,position=pos) for ident,pos in custom_positions.items()],'airport_fallbacks':airport_fallbacks,
                    'manual_runways':{side:(terminals[side].get('cdu_runway') or terminals[side]['runway']) for side in ('departure','arrival')} if terminals else {}}
        except (ValueError, TypeError, KeyError) as ex:
            return {'error': str(ex)}

    def prepare_manual_plan(self,request):
        try:
            from manual_plan import build_report
            if not isinstance(request,dict):raise ValueError('Choose data for the manual plan')
            kind=request.get('kind');route=request.get('route',1)
            if route not in (1,2):raise ValueError('Choose RTE 1 or RTE 2')
            source=request.get('plan',{})
            if kind=='navigation':prepared=self.prepare_database_route(source)
            elif kind=='waypoints':
                if not isinstance(request.get('text'),str):raise ValueError('Enter waypoint CSV text')
                prepared=self.prepare_waypoints(request['text'])
            elif kind=='ipra':prepared=self.prepare_ipra(request.get('data',{}),request.get('units','imperial'))
            else:raise ValueError('Choose route, waypoints or IPRA')
            if 'error' in prepared:return prepared
            for row in prepared['rows']:
                if row.get('position'):
                    row['position_ddm']=coordinate(row['position']['lat'],True)+' '+coordinate(row['position']['lon'],False)
            return {'report':build_report(prepared,kind,source,route)}
        except (ValueError,TypeError,KeyError) as ex:return {'error':str(ex)}

    def export_manual_plan(self,request,format='html'):
        try:
            if format not in ('html','txt'):raise ValueError('Choose printable HTML or plain text')
            result=self.prepare_manual_plan(request)
            if 'error' in result:return result
            import webview
            target=self._window.create_file_dialog(webview.FileDialog.SAVE,
                save_filename='c130j-manual-plan.'+format,
                file_types=(('HTML (*.html)' if format=='html' else 'Text (*.txt)'),))
            if not target:return {'cancelled':True,'message':'Save cancelled'}
            path=Path(target if isinstance(target,str) else target[0])
            if not path.suffix:path=path.with_suffix('.'+format)
            if path.suffix.lower()!='.'+format:raise ValueError('Save the manual plan as .'+format)
            path.write_text(result['report']['html' if format=='html' else 'text'],encoding='utf-8')
            opened=False
            if format=='html':
                try:
                    import os
                    os.startfile(str(path.resolve()));opened=True
                except OSError:pass
            return {'message':'Manual plan saved: '+str(path)+
                    (' · Use Print / Save as PDF in your browser.' if format=='html' else ''),
                    'path':str(path),'opened':opened}
        except (ValueError,TypeError,KeyError,OSError) as ex:return {'error':str(ex)}

    def kneeboard_status(self):
        try:
            from live_kneeboard import parse_status
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                sock.settimeout(2)
                return parse_status(self._exchange(sock,'KB_STATUS'))
        except (ValueError,RuntimeError,OSError) as ex:
            message=str(ex)
            if 'unsupported request' in message:message='Updated live-kneeboard bridge required. Install the update and start DCS once.'
            elif message.startswith('No bridge reply.'):message='No live-kneeboard reply. Check installation and an unpaused C-130J mission.'
            return {'error':message}

    def send_manual_kneeboard(self,request):
        acquired=False
        try:
            from live_kneeboard import publish
            with self._lock:
                if self._state['running'] or self._state.get('kneeboard_sending'):
                    raise ValueError('Stop automatic input or wait for the current kneeboard update first')
                self._state['kneeboard_sending']=True;acquired=True
            result=self.prepare_manual_plan(request)
            if 'error' in result:return result
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                sock.settimeout(2)
                return publish(lambda command:self._exchange(sock,command),result['report'])
        except (ValueError,RuntimeError,OSError,TypeError,KeyError) as ex:
            message=str(ex)
            if 'unsupported request' in message:message='Updated live-kneeboard bridge required. Install the update and start DCS once.'
            elif message.startswith('No bridge reply.'):message='No live-kneeboard reply. Check installation and an unpaused C-130J mission.'
            return {'error':message}
        finally:
            if acquired:
                with self._lock:self._state['kneeboard_sending']=False

    def save_plan(self, plan):
        import webview
        from copy import deepcopy
        from route_constraints import normalise_route_constraints
        plan=deepcopy(plan)
        if isinstance(plan.get('navigation'),dict):plan['navigation']=normalise_route_constraints(plan['navigation'])
        target = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename='c130j-entry-plan.json', file_types=('JSON (*.json)',))
        if not target:
            return {'message': 'Save cancelled'}
        path = target if isinstance(target, str) else target[0]
        Path(path).write_text(json.dumps(plan, indent=2), encoding='utf-8')
        return {'message': 'Plan saved: ' + path}

    def _stored_plans(self):
        from flight_plan_library import FlightPlanLibrary
        if not hasattr(self,'_plan_library'):self._plan_library=FlightPlanLibrary()
        return self._plan_library

    def list_flight_plans(self):
        try:return self._stored_plans().list()
        except (OSError,ValueError) as ex:return {'error':str(ex)}

    def save_flight_plan(self,name,plan,key=None):
        try:return self._stored_plans().save(name,plan,key)
        except (OSError,ValueError,TypeError,KeyError) as ex:return {'error':str(ex)}

    def load_flight_plan(self,key):
        try:return self._stored_plans().load(key)
        except (OSError,ValueError,TypeError,KeyError) as ex:return {'error':str(ex)}

    def load_plan(self):
        import webview
        paths = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=('JSON (*.json)',))
        if not paths:
            return {'cancelled': True}
        path = Path(paths[0])
        if path.stat().st_size > 1000000:
            return {'error': 'Plan file is too large'}
        try:
            plan = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(plan, dict) or plan.get('version') != 1 or not isinstance(plan.get('waypoints'), str) or not isinstance(plan.get('ipra'), dict):
                raise ValueError('Not a supported entry plan')
            from route_constraints import normalise_route_constraints
            if isinstance(plan.get('navigation'),dict):plan['navigation']=normalise_route_constraints(plan['navigation'])
            return {'plan': plan}
        except (ValueError, OSError) as ex:
            return {'error': str(ex)}

    def prepare_waypoints(self, text):
        try:
            return {'rows': waypoint_rows(text)}
        except (ValueError, TypeError) as ex:
            return {'error': str(ex)}

    def prepare_ipra(self, data, units='imperial'):
        try:
            data=dict(data)
            if units not in ('imperial','metric'):
                raise ValueError('Unknown unit system')
            if units=='metric':
                for key in ['elevation','hat','faf','iaf','map']:
                    if str(data.get(key,'')).strip():
                        data[key]=float(data[key])/(.3048 if key in ('elevation','hat') else 1.852)
            return {'rows': ipra_rows(data)}
        except (ValueError, TypeError) as ex:
            return {'error': str(ex)}

    def _exchange(self, sock, command):
        request = uuid.uuid4().hex
        sock.sendto(f'{request}|{command}'.encode('ascii'), ADDRESS)
        # Do not retry uncertain key presses: duplication could corrupt an entry.
        while True:
            try:
                packet, source = sock.recvfrom(65535)
            except socket.timeout as ex:
                raise RuntimeError('No bridge reply. Check installation and an unpaused C-130J mission. Inspect/clear the scratchpad before retrying.') from ex
            if source != ADDRESS:
                continue
            response = packet.decode('ascii', errors='replace')
            if not response.startswith(request + '|'):
                continue
            result = response.split('|', 1)[1]
            if not result.startswith('OK'):
                raise RuntimeError(result)
            return result

    def connection(self, seat='pilot'):
        try:
            from route_runner import indication
            if seat not in ('pilot','copilot'):
                raise RuntimeError('Choose pilot or copilot')
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(2)
                self._exchange(sock, 'PING')
                try:
                    capabilities=self._exchange(sock,'CAPABILITIES')
                except RuntimeError as ex:
                    if 'unsupported request' in str(ex):
                        raise RuntimeError('Updated CDU bridge required for discontinuity cleanup. Restart DCS to load the installed update.') from ex
                    raise
                if not {'DEL','NAV_TUNE','HOLD_CAPS','GESTURE_MODES'}.issubset(capabilities.split()):
                    raise RuntimeError('Updated CDU bridge required for double-click start and long-press confirmation. Restart DCS with the updated bridge.')
                named,_=indication(self._exchange(sock,'READ|'+seat).split('\n',1)[1])
                with self._lock:
                    self._state['connected']=True
                return {'message':'Connected — '+seat+' CDU: '+named['cni_title'],'connected':True}
        except (OSError, RuntimeError) as ex:
            with self._lock:
                self._state['connected']=False
            return {'error': str(ex)}

    def status(self):
        with self._lock:
            return dict(self._state)

    def refresh_airport_reference(self):
        try:
            with self._lock:
                if self._state['running']:raise ValueError('Stop CDU input before refreshing airport data')
            return self._navigation.refresh_airport_reference()
        except (OSError,ValueError,sqlite3.Error) as ex:return {'error':str(ex)}

    def stop(self):
        self._stop.set()
        with self._lock:
            self._state.update(armed=False,executing=False)
        return {'message': 'Stopping after the current key releases; check the partial scratchpad.'}

    def arm_route(self, plan, seat, options=None):
        try:
            from route_runner import RouteRunner, route_input_count, constraint_fixes
            options={} if options is None else options
            if not isinstance(options,dict):raise ValueError('Invalid route input options')
            route_number=options.get('route',1);overwrite=options.get('overwrite',False)
            input_speed=options.get('speed','default')
            if input_speed not in ('default','accelerated'):raise ValueError('Choose Default or Accelerated input speed')
            if type(route_number) is not int or route_number not in (1,2):raise ValueError('Choose RTE 1 or RTE 2')
            if type(overwrite) is not bool:raise ValueError('Invalid overwrite selection')
            if seat not in ('pilot', 'copilot'):
                raise ValueError('Choose pilot or copilot')
            if not isinstance(plan, dict) or plan.get('workflow') != 2:
                raise ValueError('Prepare a complete map flight plan first')
            checked = self.prepare_database_route(plan)
            if 'error' in checked:
                raise ValueError(checked['error'])
            terminals = validate_plan(self._navigation, plan)
            route = dict(route_number=route_number, overwrite=overwrite,input_speed=input_speed, origin=identifier(plan['origin']['ident']), destination=identifier(plan['destination']['ident']),
                         departure=terminals['departure'], arrival=terminals['arrival'],
                         arrival_radios=checked['arrival_radios'],
                         custom_waypoints=checked.get('custom_waypoints',[]),
                         airport_fallbacks=checked.get('airport_fallbacks',{}),
                         fixes=[r['value'] for r in checked['rows'] if r.get('position')],
                         constraint_fixes=constraint_fixes(checked['rows']),
                         identifiers=list({p['ident'] for p in self._navigation.points.values()}))
            with self._lock:
                if self._state['running']:
                    raise ValueError('Stop or disarm the current entry first')
                if self._state.get('kneeboard_sending'):
                    raise ValueError('Wait for the kneeboard update to finish first')
                if not self._state.get('connected'):
                    raise ValueError('Check the DCS connection and CDU display before arming')
                self._stop.clear()
                self._state.update(running=True,armed=False,executing=False,sent=0,total=route_input_count(route),percent=0,message='Arming…')
            threading.Thread(target=self._run_route, args=(route, seat, json.loads(json.dumps(plan))), daemon=True).start()
            return {'message':'Armed · RTE '+str(route_number)+' · Double-click CAPS to start.'}
        except (ValueError, TypeError, KeyError) as ex:
            return {'error':str(ex)}

    def _run_route(self, route, seat, original_plan):
        from route_runner import RouteRunner
        def report(message):
            with self._lock:
                self._state['message']=message
        log_path=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'build')/'cdu-route-diagnostic.jsonl'
        def trace(command,response):
            try:
                with log_path.open('a',encoding='utf-8') as log:
                    log.write(json.dumps(dict(time=time.time(),seat=seat,command=command,response=response))+'\n')
            except OSError:
                pass
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(2)
                baseline=int(self._exchange(sock,'ARM|'+seat+'|DOUBLE').split()[-1])
                with self._lock:
                    self._state.update(armed=True,connected=True)
                report('Armed · RTE '+str(route.get('route_number',1))+' · Double-click CAPS to start.')
                while not self._stop.wait(.25):
                    try:
                        count=int(self._exchange(sock,'TRIGGER').split()[-1])
                    except RuntimeError:
                        raise RuntimeError('Connection lost while armed. Check DCS, then explicitly re-arm.')
                    if count!=baseline:
                        break
                if not self._stop.is_set():
                    validated=self.prepare_database_route(original_plan)
                    if 'error' in validated:
                        raise RuntimeError(validated['error'])
                    route['arrival_radios']=validated['arrival_radios']
                    route['custom_waypoints']=validated.get('custom_waypoints',[])
                    route['airport_fallbacks']=validated.get('airport_fallbacks',{})
                    with self._lock:
                        self._state.update(armed=False,executing=True)
                    baseline=int(self._exchange(sock,'ARM|'+seat+'|DOUBLE').split()[-1])
                    def exchange(command):
                        if int(self._exchange(sock,'TRIGGER').split()[-1])!=baseline:
                            raise RuntimeError('Stopped by cockpit CAPS trigger; inspect partial route')
                        if command=='READ': command='READ|'+seat
                        elif command.startswith('KEY|'): command='KEY|'+seat+'|'+command[4:]
                        response=self._exchange(sock,command)
                        trace(command,response)
                        return response
                    def confirm_procedure(requested,suggested):
                        nonlocal baseline
                        from route_runner import indication
                        # ARM requires a fresh hold/release, so an earlier
                        # loading/stop gesture cannot approve this suggestion.
                        baseline=int(self._exchange(sock,'ARM|'+seat+'|HOLD').split()[-1])
                        with self._lock:
                            self._state.update(executing=False,awaiting_confirmation=True)
                        report(requested+' unavailable. Use '+suggested+'? Hold CAPS 1.5s and release to accept, or Deny.')
                        trace('WAIT_PROCEDURE',requested+' -> '+suggested)
                        accepted=False
                        try:
                            while not self._stop.wait(.25):
                                count=int(self._exchange(sock,'TRIGGER').split()[-1])
                                response=self._exchange(sock,'READ|'+seat)
                                shown,_=indication(response.split('\n',1)[1])
                                if shown.get('cni_scratchpad','').strip(' []_'):
                                    raise RuntimeError('Procedure replacement denied or CDU changed; route loading halted. Inspect the partial route.')
                                if count!=baseline:
                                    if self._stop.is_set():
                                        raise RuntimeError('Procedure replacement denied; route loading halted')
                                    baseline=int(self._exchange(sock,'ARM|'+seat+'|DOUBLE').split()[-1])
                                    trace('ACCEPT_PROCEDURE',requested+' -> '+suggested)
                                    accepted=True
                                    return True
                            raise RuntimeError('Procedure replacement cancelled; route loading halted; inspect the partial route')
                        finally:
                            with self._lock:
                                self._state.update(executing=accepted and not self._stop.is_set(),awaiting_confirmation=False)
                    runner=RouteRunner(exchange,self._stop.wait,report,confirm_procedure)
                    reference=self._navigation._airport_reference
                    if reference is not None:
                        terrain=self._navigation.theatre
                        runner.custom_airports=reference.custom_airfields(terrain)
                        runner.record_custom_airport=lambda ident:reference.record_custom_airfield(terrain,ident)
                    def progress(completed,total,label):
                        with self._lock:
                            self._state.update(sent=completed,total=total,percent=completed*100//total,progress_label=label)
                    runner.progress=progress
                    runner.run(route)
                else:
                    report('Disarmed / stopped. Inspect any partial route before retrying.')
                self._exchange(sock,'DISARM')
        except Exception as ex:
            trace('STOP',str(ex))
            if isinstance(ex,OSError) or any(text in str(ex) for text in ('No bridge reply','Connection lost','cockpit required')):
                with self._lock:
                    self._state['connected']=False
            report(str(ex))
        finally:
            # Best effort disarm even after display or transport failure.
            try:
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as cleanup:
                    cleanup.settimeout(.5)
                    self._exchange(cleanup,'DISARM')
            except (OSError,RuntimeError):
                pass
            with self._lock:
                self._state.update(running=False,armed=False,executing=False,awaiting_confirmation=False)

    def send_field(self, text, lsk, seat, ready):
        try:
            if ready is not True:
                raise ValueError('Confirm the correct page and an empty scratchpad first')
            keys = key_sequence(text, lsk)
            if seat not in ('pilot', 'copilot'):
                raise ValueError('Choose pilot or copilot')
            with self._lock:
                if self._state['running']:
                    raise ValueError('An entry is already running')
                if self._state.get('kneeboard_sending'):
                    raise ValueError('Wait for the kneeboard update to finish first')
                self._stop.clear()
                self._state.update(running=True,armed=False,executing=True,sent=0,total=len(keys),message='Entering field…')
            threading.Thread(target=self._send, args=(keys, seat), daemon=True).start()
            return {'message': 'Entry started'}
        except (ValueError, TypeError) as ex:
            return {'error': str(ex)}

    def _send(self, keys, seat):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(2)
                self._exchange(sock, 'PING')
                for key in keys:
                    if self._stop.is_set():
                        break
                    self._exchange(sock, f'KEY|{seat}|{key}')
                    with self._lock:
                        self._state['sent'] += 1
                    if self._stop.wait(0.12):
                        break
            message = ('Stopped — inspect/clear the partial entry before retrying.' if self._stop.is_set()
                       else 'Key presses acknowledged. Verify CDU acceptance, then mark this field complete.')
        except (OSError, RuntimeError) as ex:
            message = str(ex)
        finally:
            with self._lock:
                self._state.update(running=False,executing=False, message=message)

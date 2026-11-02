"""Read ASC navigation records and DCS raster charts without modifying either."""
from __future__ import annotations

import base64
import json
import math
import os
import sys
from pathlib import Path
import re
import sqlite3
import struct
import threading
import zipfile
from terrains import TERRAINS, LABELS, NAVAID_NAMES

NAV_RELATIVE = Path('Mods/aircraft/C130J/Cockpit/Resources/nav_data.db')
CHART_RELATIVE = Path('Mods/terrains/Caucasus/RasterCharts')
REGION = (37, 48, 27, 51)


def discover_dcs():
    candidates = []
    config=Path(sys.executable).parent/'dcs-location.json' if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'dcs-location.json'
    try:candidates.append(Path(json.loads(config.read_text(encoding='utf-8'))['dcs_root']))
    except (OSError,ValueError,KeyError,TypeError):pass
    if os.environ.get('DCS_INSTALL_DIR'):
        candidates.append(Path(os.environ['DCS_INSTALL_DIR']))
    from setup_support import shell_folder
    saved = shell_folder('{4C5C32FF-BB9D-43B0-BF18-EE15F81E0DF8}',Path.home()/'Saved Games')
    logs = sorted(saved.glob('DCS*/Logs/dcs.log'), key=lambda p: p.stat().st_mtime, reverse=True)
    for log in logs:
        with log.open(encoding='utf-8', errors='replace') as stream:
            header = stream.read(12000)
        match = re.search(r'Command line: "([^"]+[/\\]bin(?:-mt)?[/\\]DCS\.exe)"', header, re.I)
        if match:
            candidates.append(Path(match.group(1)).parent.parent)
    for folder in ['C:/Program Files/Eagle Dynamics/DCS World', 'C:/Program Files/Eagle Dynamics/DCS World OpenBeta']:
        candidates.append(Path(folder))
    return next((p for p in candidates if (p / NAV_RELATIVE).is_file()), None)


def unproject(x,y,theatre='Caucasus'):
    """Invert the same local map projection used for ASC points and charts."""
    bounds=TERRAINS[theatre][3];lat=(bounds[0]+bounds[1])/2;lon=(bounds[2]+bounds[3])/2
    for _ in range(15):
        east,north=project(lat,lon,theatre);dx=x-east;dy=y-north
        if math.hypot(dx,dy)<.01:return lat,lon
        ex,ny=project(lat+.00001,lon,theatre);fx,fy=project(lat,lon+.00001,theatre)
        a,b,c,d=(ex-east)/.00001,(fx-east)/.00001,(ny-north)/.00001,(fy-north)/.00001
        determinant=a*d-b*c
        if abs(determinant)<1:break
        lat+=(dx*d-b*dy)/determinant;lon+=(a*dy-dx*c)/determinant
        if not finite_position(lat,lon):break
    raise ValueError('Choose a custom waypoint within the terrain map')


def project(lat, lon, theatre="Caucasus"):
    """WGS84 to a DCS terrain's northing/easting (Transverse Mercator).

    Parameters documented by dcs-projections; Snyder series through A^6.
    Returns east, north for map canvas axes within the selected terrain region.
    """
    meridian,false_east,false_north,_,_=TERRAINS[theatre]
    lat, lon = math.radians(lat), math.radians(lon)
    e2 = 0.0066943799901413165
    a = 6378137.0
    ep2 = e2 / (1 - e2)
    n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    t = math.tan(lat) ** 2
    c = ep2 * math.cos(lat) ** 2
    aa = math.cos(lat) * (lon - math.radians(meridian))
    m = a * ((1-e2/4-3*e2**2/64-5*e2**3/256)*lat
             -(3*e2/8+3*e2**2/32+45*e2**3/1024)*math.sin(2*lat)
             +(15*e2**2/256+45*e2**3/1024)*math.sin(4*lat)
             -(35*e2**3/3072)*math.sin(6*lat))
    east = false_east + .9996*n*(aa+(1-t+c)*aa**3/6+(5-18*t+t*t+72*c-58*ep2)*aa**5/120)
    north = false_north + .9996*(m+n*math.tan(lat)*(aa*aa/2+(5-t+9*c+4*c*c)*aa**4/24
                                              +(61-58*t+t*t+600*c-330*ep2)*aa**6/720))
    return east, north


def finite_position(lat, lon):
    return isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180


def navaid_identity(row):
    name=str(row['name'] or '').strip().upper()
    code=str(row['channel'] or '').strip().upper()
    kind=row['type']
    if kind=='AIRPORT':
        if re.fullmatch(r'[A-Z0-9]{1,8}',name) and re.search('[A-Z]',name):return name,kind
        # Some ASC Syria rows contain a frequency in name despite AIRPORT type.
        # Preserve them as generic aids; never invent an airport from that value.
        return (code,'NAVAID') if re.fullmatch(r'[A-Z0-9]{1,8}',code) else (None,kind)
    return (code,kind) if re.fullmatch(r'[A-Z0-9]{1,8}',code) else (None,kind)


def airway_sections(records):
    """Keep ARINC end-of-route markers and missing positions as discontinuities."""
    groups, current, previous_group, previous_seq = [], [], None, None
    for row in records:
        group = (row['area_code'], row['route_identifier'])
        seq = row['seqno']
        if group != previous_group or (previous_seq is not None and seq <= previous_seq):
            if len(current) > 1:
                groups.append(current)
            current = []
        previous_group, previous_seq = group, seq
        if not finite_position(row['waypoint_latitude'], row['waypoint_longitude']):
            if len(current) > 1:
                groups.append(current)
            current = []
            continue
        current.append(row)
        description = row['waypoint_description_code'] or ''
        if len(description) > 1 and description[1] == 'E':
            if len(current) > 1:
                groups.append(current)
            current = []
    if len(current) > 1:
        groups.append(current)
    return groups


class Navigation:
    def __init__(self, root=None, theatre="Caucasus"):
        self.root = Path(root) if root else discover_dcs()
        self.theatre=theatre
        self._cache={}
        self._lock = threading.RLock()
        self._data = None
        self._airport_reference = None
        self._chart_pyramids = {}
        self.points = {}
        self.sections = {}
        self.tiles = {}

    def load(self, theatre=None):
        with self._lock:
            if theatre is not None and theatre not in TERRAINS:
                raise ValueError("Unknown terrain")
            if theatre and theatre!=self.theatre:
                if self._data is not None:self._cache[self.theatre]=(self._data,self.points,self.sections,self.tiles)
                self.theatre=theatre
                self._data=None
                self.points,self.sections,self.tiles={},{},{}
                if theatre in self._cache:
                    self._data,self.points,self.sections,self.tiles=self._cache[theatre]
            region=TERRAINS[self.theatre][3]
            if self._data is not None:
                return self._data
            if not self.root or not (self.root / NAV_RELATIVE).is_file():
                raise ValueError('Choose your DCS installation folder to load the ASC navigation database.')
            path = self.root / NAV_RELATIVE
            points, lookup = {}, {}

            def add(key, ident, lat, lon, kind, region='', airport=''):
                if not ident or not finite_position(lat, lon):
                    return None
                signature = (ident, round(lat, 5), round(lon, 5))
                if signature in lookup:
                    return lookup[signature]
                east, north = project(lat, lon,self.theatre)
                point = dict(id=key, ident=ident, lat=lat, lon=lon, x=east, y=north,
                             kind=kind, region=region or '', airport=airport or '')
                points[key] = point
                lookup[signature] = key
                return key

            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as con:
                con.row_factory = sqlite3.Row
                con.execute('PRAGMA query_only=ON')
                required = {'fixes', 'airways', 'navaids'}
                tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not required <= tables:
                    raise ValueError('The selected ASC database does not contain fixes, airways and navaids.')
                for r in con.execute("SELECT rowid,* FROM navaids WHERE terrain=?",(NAVAID_NAMES.get(self.theatre,self.theatre),)):
                    ident,kind=navaid_identity(r)
                    key=add('n:'+str(r['rowid']),ident,r['lat'],r['lon'],kind)
                    if key:
                        points[key].update(asc_tuning=r['name'],source_type=r['type'],elevation_ft=r['alt'])
                airport_idents={p['ident'] for p in points.values() if p['kind']=='AIRPORT'}
                for r in con.execute('SELECT rowid,* FROM airports WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?',region):
                    ident=str(r['icao'] or '').upper()
                    if ident not in airport_idents:
                        compatible=bool(re.fullmatch(r'[A-Z0-9]{1,8}',ident))
                        key=add('airport:'+str(r['rowid']),ident,r['lat'],r['lon'],'AIRPORT' if compatible else 'AIRFIELD')
                        if key:points[key].update(elevation_ft=r['elevation'],cdu_compatible=compatible)
                        airport_idents.add(ident)
                for r in con.execute('SELECT rowid,* FROM fixes WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? ORDER BY ident', region):
                    add('f:'+str(r['rowid']), r['ident'], r['lat'], r['lon'],
                        'FIX' if r['airport_identifier'] == 'ENRT' else 'TERMINAL', r['short_region'], r['airport_identifier'])
                # Read complete named routes before clipping, so no artificial links
                # are introduced between separate fragments at the viewport edge.
                records = list(con.execute('''SELECT rowid,* FROM airways WHERE (area_code,route_identifier) IN
                    (SELECT area_code,route_identifier FROM airways WHERE waypoint_latitude BETWEEN ? AND ?
                     AND waypoint_longitude BETWEEN ? AND ?) ORDER BY area_code,route_identifier,seqno''', region))
            sections = {}
            for section in airway_sections(records):
                # Clip to supported geography, retaining actual contiguous subsequences.
                runs, run = [], []
                for r in section:
                    if region[0] <= r['waypoint_latitude'] <= region[1] and region[2] <= r['waypoint_longitude'] <= region[3]:
                        run.append(r)
                    else:
                        if len(run) > 1:
                            runs.append(run)
                        run = []
                if len(run) > 1:
                    runs.append(run)
                for run in runs:
                    legs = []
                    for r in run:
                        key = add('a:'+str(r['rowid']), r['waypoint_identifier'], r['waypoint_latitude'], r['waypoint_longitude'], 'FIX', r['icao_code'])
                        if key is None:
                            break
                        legs.append(dict(point=key, direction=r['direction_restriction'] or '', level=r['flightlevel'] or '',
                                         minimum=r['minimum_altitude1'], minimum2=r['minimum_altitude2'], maximum=r['maximum_altitude'], seq=r['seqno']))
                    if len(legs) == len(run):
                        key = 'route:'+str(run[0]['rowid'])
                        sections[key] = dict(id=key, name=run[0]['route_identifier'], area=run[0]['area_code'], legs=legs)
            self.points, self.sections = points, sections
            charts, chart_error = [], ''
            try:
                charts = self._charts()
            except FileNotFoundError:
                chart_error = 'No local chart underlay installed for '+self.theatre+'. ASC navigation planning remains available.'
            except (OSError, ValueError, struct.error, zipfile.BadZipFile) as ex:
                chart_error = 'DCS raster charts unavailable: ' + str(ex)
            from airport_reference import AirportReference,distance as reference_distance
            reference_error=''
            dcs_navaids=[]
            try:
                if self._airport_reference is None:self._airport_reference=AirportReference(self.root)
                references=self._airport_reference.load(self.theatre)
                dcs_navaids=self._airport_reference.navaids(self.theatre)
                for point in points.values():
                    if point['kind']=='AIRPORT' and point['ident'] in references and reference_distance(point,references[point['ident']])<3:
                        point['dcs_airport']=references[point['ident']]
            except (OSError,ValueError,sqlite3.Error) as ex:reference_error=str(ex)
            self._data = dict(source=str(path), modified=path.stat().st_mtime, theatre=self.theatre,terrain_catalog=self.catalog(),home=dict(zip(('x','y'),project(*TERRAINS[self.theatre][4],self.theatre))),points=list(points.values()),airport_reference_error=reference_error,
                              airways=list(sections.values()), tiles=charts, chart_error=chart_error,dcs_navaids=dcs_navaids)
            return self._data

    def refresh_airport_reference(self):
        from airport_reference import distance as reference_distance
        with self._lock:
            self.load()
            if self._airport_reference is None:raise ValueError('DCS airport reference is unavailable')
            counts=self._airport_reference.refresh_all()
            collections={self.theatre:self.points}
            collections.update({terrain:cached[1] for terrain,cached in self._cache.items() if terrain!=self.theatre})
            for terrain,points in collections.items():
                records=self._airport_reference.load(terrain)
                data=self._data if terrain==self.theatre else self._cache[terrain][0]
                data['dcs_navaids']=self._airport_reference.navaids(terrain)
                for p in points.values():
                    if p['kind']=='AIRPORT':
                        p.pop('dcs_airport',None)
                        if p['ident'] in records and reference_distance(p,records[p['ident']])<3:p['dcs_airport']=records[p['ident']]
            return dict(counts=counts,updated=sum(counts.values()),navaids=self._data['dcs_navaids'],airports=[dict(id=p['id'],reference=p.get('dcs_airport')) for p in self.points.values() if p['kind']=='AIRPORT'])

    def catalog(self):
        result=[]
        for name in TERRAINS:
            folder=self.root/'Mods/terrains'/name if self.root else None
            result.append(dict(id=name,name=LABELS.get(name,name),installed=bool(folder and (folder/'entry.lua').is_file()),
                               charts=bool(folder and (folder/'RasterCharts/rasterCharts.sup5').is_file())))
        return result

    def _charts(self):
        root = self.root / 'Mods/terrains' / self.theatre / 'RasterCharts'
        raw = (root / 'rasterCharts.sup5').read_bytes()
        if raw[:4] != b'\x02\x00\x00\x00' or b'landscape5::sup5File' not in raw[:64]:
            raise ValueError('Unsupported DCS raster placement format')
        buffers = struct.unpack_from('<Q', raw, 8)[0]
        names = {}
        for archive in sorted(root.rglob('*.zip')):
            with zipfile.ZipFile(archive) as z:
                for name in z.namelist():
                    if name.lower().endswith('.tif.dds'):
                        names[name[:-4].lower()] = (archive, name)
        tiles = {}
        for match in re.finditer(rb'(?<![A-Za-z0-9_\-])[A-Za-z0-9_\-]+\.tif', raw, re.I):
            name = match.group().decode('ascii').lower()
            if name not in names:
                continue
            start = match.start()
            low_n, low_h, low_e, high_n, high_h, high_e = struct.unpack_from('<6f', raw, start-214)
            # Confirm both geometry and UVs; reject changed layouts rather than
            # silently placing a chart in the wrong location.
            offset = struct.unpack_from('<I', raw, start-145)[0]
            vertices = struct.unpack_from('<12f', raw, buffers+offset)
            uv = struct.unpack_from('<8f', raw, buffers+offset+48)
            expected = (high_n, 0, low_e, low_n, 0, low_e, low_n, 0, high_e, high_n, 0, high_e)
            if vertices != expected or uv != (0, 0, 0, 1, 1, 1, 1, 0):
                raise ValueError('Unsupported raster geometry/UV layout')
            if not all(math.isfinite(v) for v in vertices) or not 1000 < high_e-low_e < 300000 or not 1000 < high_n-low_n < 300000:
                raise ValueError('Invalid raster chart bounds')
            match_scale=re.match(r'(?:m)?(16|32|64|128|256)(?:m|_)',name)
            scale=int(match_scale[1]) if match_scale else round(max(high_e-low_e,high_n-low_n)/1024,3)
            key = self.theatre+':'+str(len(tiles))
            archive, member = names[name]
            tiles[key] = dict(id=key, name=name, scale=scale, bounds=[low_e, low_n, high_e, high_n], archive=archive, member=member)
        if not tiles:
            raise ValueError('No supported local raster tiles found')
        if self.theatre=='Kola':
            try:
                from kola_charts import KolaChartPyramid
                base=(Path(os.environ.get('LOCALAPPDATA',Path.home()))/'C130JCDUHelper') if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'build'
                pyramid=KolaChartPyramid(tiles.values(),base/'chart-cache/Kola')
                self._chart_pyramids['Kola']=pyramid
                tiles.update(pyramid.tiles)
            except (OSError,ValueError,ImportError):
                # The prototype must never remove working native charts.
                self._chart_pyramids.pop('Kola',None)
        self.tiles = tiles
        return [{k:t[k] for k in ('id','name','scale','bounds')} for t in tiles.values()]

    def tile(self, key):
        self.load()
        tile = self.tiles.get(str(key))
        if not tile:
            raise ValueError('Unknown chart tile')
        if tile.get('overview'):
            return {'png':base64.b64encode(self._chart_pyramids['Kola'].tile(tile['id'])).decode('ascii')}
        with zipfile.ZipFile(tile['archive']) as z:
            data = z.read(tile['member'])
        if data[:4] != b'DDS ' or data[84:88] not in (b'DXT1', b'DXT3', b'DXT5'):
            raise ValueError('Unsupported chart image encoding')
        height, width = struct.unpack_from('<2I', data, 12)
        if not (0 < width <= 4096 and 0 < height <= 4096):
            raise ValueError('Invalid chart image size')
        size = ((width+3)//4)*((height+3)//4)*(8 if data[84:88] == b'DXT1' else 16)
        if len(data) < 128+size:
            raise ValueError('Truncated chart image')
        return {'dds': base64.b64encode(data[:128+size]).decode('ascii')}

    def resolve(self, saved, allow_custom=False):
        self.load()
        if not isinstance(saved, dict):
            raise ValueError('Invalid route point')
        if allow_custom and saved.get('kind')=='CUSTOM':
            ident=saved.get('ident','')
            lat,lon=float(saved.get('lat',999)),float(saved.get('lon',999))
            if not re.fullmatch(r'[A-Z][A-Z0-9]{0,7}',ident) or saved.get('id')!='custom:'+ident or not finite_position(lat,lon):
                raise ValueError('Invalid custom waypoint identifier or position')
            if any(p['ident']==ident for p in self.points.values()):raise ValueError('Custom waypoint identifier already exists in ASC: '+ident)
            x,y=project(lat,lon,self.theatre)
            return dict(id='custom:'+ident,ident=ident,kind='CUSTOM',lat=lat,lon=lon,x=x,y=y,region='Custom')
        point = self.points.get(saved.get('id'))
        lat, lon = float(saved.get('lat', 999)), float(saved.get('lon', 999))
        if not finite_position(lat, lon) or not point or point['ident'] != saved.get('ident') or abs(point['lat']-lat) > .00001 or abs(point['lon']-lon) > .00001:
            raise ValueError('A saved point no longer matches the installed database. Re-select it on the map.')
        return point

    def airway_slice(self, key, start, end):
        self.load()
        section = self.sections.get(key)
        if not section or isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
            raise ValueError('Select an airway, entry fix and exit fix')
        legs = section['legs']
        if start == end or min(start,end) < 0 or max(start,end) >= len(legs):
            raise ValueError('Choose two different fixes on this airway section')
        backward = end < start
        traversed = legs[min(start,end):max(start,end)]
        prohibited = 'F' if backward else 'B'
        if any(l['direction'] == prohibited for l in traversed):
            raise ValueError('This direction conflicts with an ASC one-way airway restriction. Reverse the entry/exit or choose another segment.')
        indices = range(start, end+(-1 if backward else 1), -1 if backward else 1)
        return {'points':[self.points[legs[i]['point']] for i in indices], 'name':section['name'], 'restrictions':traversed}

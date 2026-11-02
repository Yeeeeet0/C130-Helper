from contextlib import closing
"""Read DCS radio/beacon reference data without executing Lua or changing ASC."""
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
from terrains import TERRAINS

ASC_NAV=Path('Mods/aircraft/C130J/Cockpit/Resources/nav_data.db')


def distance(a,b):
    lat1,lat2=math.radians(a['lat']),math.radians(b['lat'])
    h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(math.radians(b['lon']-a['lon'])/2)**2
    return 3440.065*2*math.asin(min(1,math.sqrt(h)))


def records(text,table):
    """Extract top-level literal records, respecting Lua strings and comments."""
    start=re.search(r'\b'+re.escape(table)+r'\s*=\s*\{',text)
    if not start:return []
    result=[];depth=1;i=start.end();begin=None
    while i<len(text) and depth:
        char=text[i]
        if text.startswith('--[[',i):
            end=text.find(']]',i+4);i=len(text) if end<0 else end+2;continue
        if text.startswith('--',i):
            end=text.find('\n',i+2);i=len(text) if end<0 else end+1;continue
        if char in ('"',"'"):
            quote=char;i+=1
            while i<len(text):
                if text[i]=='\\':i+=2;continue
                if text[i]==quote:i+=1;break
                i+=1
            continue
        if char=='{':
            depth+=1
            if depth==2:begin=i+1
        elif char=='}':
            if depth==2:result.append(text[begin:i])
            depth-=1
        i+=1
    return result


def value(record,key,pattern):
    prefix=r'(?:\b'+re.escape(key)+r'\b|\[\s*[\'"]'+re.escape(key)+r'[\'"]\s*\])\s*=\s*'
    found=re.search(prefix+pattern,record)
    return found.group(1) if found else None


STRING=r'''(?:_\(\s*)?(?P<q>['"])(?P<s>(?:\\.|(?!(?P=q))[^\\])*)(?P=q)'''
NUMBER=r'([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)'


def text_value(record,key):
    prefix=r'(?:\b'+re.escape(key)+r'\b|\[\s*[\'"]'+re.escape(key)+r'[\'"]\s*\])\s*=\s*'
    found=re.search(prefix+STRING,record)
    result=found['s'] if found else None
    return re.sub(r'\\([\\\'"nrt])',lambda m:{'n':'\n','r':'\r','t':'\t'}.get(m[1],m[1]),result) if result is not None else None


def parse_sources(radio_text,beacon_text):
    groups=defaultdict(lambda:dict(names=[],codes=[],radios=[],aids=[]))
    for record in records(radio_text,'radio'):
        identifier=text_value(record,'radioId') or ''
        match=re.fullmatch(r'airfield(\d+)_\d+',identifier)
        if not match:continue
        group=groups[match[1]]
        comment=re.search(r'^\s*--\s*([^\r\n]+)',record,re.M)
        translated=re.search(r'_\(\s*'+STRING,record)
        name=comment[1].strip() if comment else translated['s'] if translated else ''
        if name:
            token=re.split(r'[_\s-]',name)[0].upper();group['codes'].append(token)
            friendly=re.sub(r'^[A-Z]{4}[_ -]+','',name).replace('_',' ').strip()
            group['names'].append(friendly)
        # A callsign can contain an explicit airport identifier even without a comment.
        for quoted in re.findall(r'\(\s*[\'"]([A-Z0-9]{1,8})[\'"]\s*\)',record):group['codes'].append(quoted)
        roles=value(record,'role',r'\{([^}]+)\}') or ''
        roles=re.findall(r'[\'"]([^\'"]+)[\'"]',roles)
        for band,modulation,hz in re.findall(r'\[([A-Z_]+)\]\s*=\s*\{\s*([A-Z_]+)\s*,\s*([-+\d.]+)',record):
            hz=float(hz)
            if math.isfinite(hz) and 100000<=hz<=500000000:
                group['radios'].append(dict(band=band,modulation=modulation.replace('MODULATIONTYPE_',''),frequency_hz=hz,roles=roles))
    for record in records(beacon_text,'beacons'):
        identifier=text_value(record,'beaconId') or ''
        match=re.fullmatch(r'airfield(\d+)_\d+',identifier)
        if not identifier:continue
        key=match[1] if match else 'standalone:'+identifier
        lat,lon=value(record,'latitude',NUMBER),value(record,'longitude',NUMBER)
        frequency=value(record,'frequency',NUMBER)
        if lat is None or lon is None:continue
        lat,lon=float(lat),float(lon)
        if not (-90<=lat<=90 and -180<=lon<=180):continue
        kind=value(record,'type',r'(BEACON_TYPE_[A-Z_]+)') or 'UNKNOWN'
        aid=dict(id=identifier,kind=kind.replace('BEACON_TYPE_',''),ident=text_value(record,'callsign') or '',
                 name=text_value(record,'display_name') or '',lat=lat,lon=lon)
        if frequency is not None and math.isfinite(float(frequency)):aid['frequency_hz']=float(frequency)
        if aid['kind']=='ILS_LOCALIZER' and not 108100000<=aid.get('frequency_hz',0)<=111950000:
            aid['tuning_issue']='Outside VOR1/ILS frequency range'
        channel=value(record,'channel',NUMBER)
        if channel is not None:aid['channel']=float(channel)
        direction=value(record,'direction',NUMBER)
        if direction is not None and math.isfinite(float(direction)):aid['direction_deg']=float(direction)%360
        if aid['kind']=='TACAN':
            explicit=text_value(record,'channelTACAN') or ''
            if re.fullmatch(r'\d{1,3}[XY]',explicit):
                aid['channel']=int(explicit[:-1]);aid['band']=explicit[-1]
            elif not re.search(r'\bsystem\s*=',record) or re.search(r'\bsystem\s*=\s*SystemName\.TACAN\s*[;,}]',record):
                # DCS Scripts/World/Radio/BeaconSites.lua: the default ground
                # BEACON_TYPE_TACAN uses SystemName.TACAN / SIGNAL_TACAN_X.
                aid['band']='X'
        group=groups[key];group['aids'].append(aid)
        if not match:group['standalone']=True
        if not group['names'] and aid['name']:group['names'].append(aid['name'].replace('_',' '))
    return dict(groups)


def associate_runway_aids(airport,runways):
    """Match paired ILS transmitters to ASC thresholds without renaming runways."""
    for loc in airport['aids']:
        if loc['kind']!='ILS_LOCALIZER' or 'direction_deg' not in loc:continue
        gs=[a for a in airport['aids'] if a['kind']=='ILS_GLIDESLOPE' and a['ident']==loc['ident']
            and a.get('frequency_hz')==loc.get('frequency_hz')]
        if len(gs)!=1:continue
        candidates=[]
        for runway in runways:
            try:
                heading=float(runway['hdg']);position=dict(lat=float(runway['lat']),lon=float(runway['lon']))
                if not all(math.isfinite(v) for v in (heading,position['lat'],position['lon'])):continue
                # DCS localizer direction faces approaching aircraft, opposite
                # the inbound runway course. Position resolves parallel ends.
                angle=abs((loc['direction_deg']+180-heading+180)%360-180)
                proximity=distance(gs[0],position)
                if angle<=30 and proximity<=1:candidates.append((proximity,str(runway['name'])))
            except (ValueError,TypeError,KeyError):continue
        candidates.sort()
        if candidates and (len(candidates)==1 or candidates[1][0]-candidates[0][0]>.15):
            loc['runway']=candidates[0][1]
            loc['runway_match']='ASC threshold / paired DCS glideslope and localizer direction'


def associate(groups,airports,terrain,sources):
    candidates={a['icao']:dict(lat=float(a['lat']),lon=float(a['lon'])) for a in airports}
    proposals=defaultdict(list)
    for dcs_id,group in groups.items():
        if group.get('standalone'):continue
        exact={code for code in group['codes'] if code in candidates}
        if len(exact)>1:continue
        positions=[a for a in group['aids']]
        method=None;icao=None
        if len(exact)==1:
            icao=next(iter(exact));method='identifier'
            if positions and min(distance(candidates[icao],p) for p in positions)>10:continue
        elif positions:
            nearby=sorted((min(distance(point,p) for p in positions),code) for code,point in candidates.items())
            if nearby and nearby[0][0]<3 and (len(nearby)==1 or nearby[1][0]-nearby[0][0]>.5):
                icao=nearby[0][1];method='position'
        if not icao:continue
        row=dict(terrain=terrain,icao=icao,dcs_airfield_id=dcs_id,name=group['names'][0] if group['names'] else icao,
                 lat=candidates[icao]['lat'],lon=candidates[icao]['lon'],match_method=method,
                 radios=list({json.dumps(r,sort_keys=True):r for r in group['radios']}.values()),aids=group['aids'],sources=sources)
        proposals[icao].append(row)
    result={}
    for icao,rows in proposals.items():
        exact=[r for r in rows if r['match_method']=='identifier']
        if len(exact)==1:result[icao]=exact[0]
        elif len(rows)==1:result[icao]=rows[0]
    return result


class AirportReference:
    def __init__(self,root,database=None):
        self.root=Path(root)
        base=(Path(os.environ.get('LOCALAPPDATA',Path.home()))/'C130JCDUHelper') if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'build'
        self.database=Path(database or base/'airport-reference.sqlite')
        self.database.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.database)) as con, con:
            con.executescript('''CREATE TABLE IF NOT EXISTS airports(terrain TEXT,icao TEXT,data TEXT,PRIMARY KEY(terrain,icao));
                CREATE TABLE IF NOT EXISTS sources(terrain TEXT PRIMARY KEY,fingerprint TEXT);
                CREATE TABLE IF NOT EXISTS navaids(terrain TEXT,id TEXT,data TEXT,PRIMARY KEY(terrain,id));
                CREATE TABLE IF NOT EXISTS custom_airfields(terrain TEXT,ident TEXT,nav_signature TEXT,PRIMARY KEY(terrain,ident,nav_signature));''')

    def nav_signature(self):
        source=self.root/ASC_NAV;stat=source.stat()
        return hashlib.sha256(json.dumps([str(source.resolve()),stat.st_mtime_ns,stat.st_size]).encode()).hexdigest()

    def custom_airfields(self,terrain):
        with closing(sqlite3.connect(self.database)) as con:
            return {r[0] for r in con.execute('SELECT ident FROM custom_airfields WHERE terrain=? AND nav_signature=?',(terrain,self.nav_signature()))}

    def record_custom_airfield(self,terrain,ident):
        with closing(sqlite3.connect(self.database)) as con,con:
            con.execute('INSERT OR IGNORE INTO custom_airfields VALUES(?,?,?)',(terrain,ident,self.nav_signature()))

    def source_files(self,terrain):
        folder=self.root/'Mods/terrains'/terrain
        files={p.name.lower():p for p in folder.glob('*.lua')} if folder.is_dir() else {}
        return {kind:files[kind+'.lua'] for kind in ('radio','beacons') if kind+'.lua' in files}

    def load(self,terrain,force=False):
        files=self.source_files(terrain)
        asc=self.root/ASC_NAV
        bundled=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'assets/dcs_airports.sqlite'
        signature=[(str(p.resolve()),p.stat().st_mtime_ns,p.stat().st_size) for p in [asc,*files.values()]]
        signature.append(('parser',4))
        if not files and bundled.is_file():signature.append(('bundled',hashlib.sha256(bundled.read_bytes()).hexdigest()))
        fingerprint=hashlib.sha256(json.dumps(signature).encode()).hexdigest()
        with closing(sqlite3.connect(self.database)) as con, con:
            prior=con.execute('SELECT fingerprint FROM sources WHERE terrain=?',(terrain,)).fetchone()
            if not force and prior and prior[0]==fingerprint:
                return {r[0]:json.loads(r[1]) for r in con.execute('SELECT icao,data FROM airports WHERE terrain=?',(terrain,))}
        bounds=TERRAINS[terrain][3]
        with closing(sqlite3.connect(asc.as_uri()+'?mode=ro',uri=True)) as con, con:
            con.row_factory=sqlite3.Row
            airports=[dict(r) for r in con.execute('SELECT icao,lat,lon FROM airports WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?',bounds)
                      if re.fullmatch('[A-Z0-9]{1,8}',str(r['icao'] or ''))]
            runways=[dict(r) for r in con.execute('SELECT * FROM runways')] if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='runways'").fetchone() else []
        groups=parse_sources(*(files[k].read_text(encoding='utf-8-sig',errors='replace') if k in files else '' for k in ('radio','beacons')))
        rows=associate(groups,airports,terrain,[str(p.relative_to(self.root)) for p in files.values()])
        for code,airport in rows.items():associate_runway_aids(airport,[r for r in runways if r['icao']==code])
        navaids={aid['id']:aid for group in groups.values() for aid in group['aids']}
        if not files:
            if bundled.is_file() and bundled.resolve()!=self.database.resolve():
                with closing(sqlite3.connect(bundled.as_uri()+'?mode=ro',uri=True)) as con, con:
                    lookup={a['icao']:a for a in airports}
                    for code,data in con.execute('SELECT icao,data FROM airports WHERE terrain=?',(terrain,)):
                        record=json.loads(data)
                        if code in lookup and distance(lookup[code],record)<3:
                            record['bundled']=True;rows[code]=record
                    if con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='navaids'").fetchone():
                        navaids.update({identifier:json.loads(data) for identifier,data in con.execute('SELECT id,data FROM navaids WHERE terrain=?',(terrain,))})
        with closing(sqlite3.connect(self.database)) as con, con:
            con.execute('DELETE FROM airports WHERE terrain=?',(terrain,))
            con.executemany('INSERT INTO airports VALUES(?,?,?)',[(terrain,code,json.dumps(row,ensure_ascii=False)) for code,row in rows.items()])
            con.execute('INSERT OR REPLACE INTO sources VALUES(?,?)',(terrain,fingerprint))
            con.execute('DELETE FROM navaids WHERE terrain=?',(terrain,))
            con.executemany('INSERT INTO navaids VALUES(?,?,?)',[(terrain,identifier,json.dumps(aid,ensure_ascii=False)) for identifier,aid in navaids.items()])
        return rows

    def navaids(self,terrain):
        with closing(sqlite3.connect(self.database)) as con:
            return [json.loads(row[0]) for row in con.execute('SELECT data FROM navaids WHERE terrain=? ORDER BY id',(terrain,))]

    def refresh_all(self):return {terrain:len(self.load(terrain,force=True)) for terrain in TERRAINS}

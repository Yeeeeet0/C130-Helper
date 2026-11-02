"""Named full-flight plans in app storage, independent of the install folder."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import sys
import threading
import uuid
from copy import deepcopy
from route_constraints import normalise_route_constraints


def default_root():
    base=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'C130JCDUHelper' if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'build'
    return base/'flight-plans'


def validate_plan(plan):
    if not isinstance(plan,dict) or plan.get('version')!=1:raise ValueError('Unsupported flight plan')
    route=plan.get('navigation')
    if not isinstance(route,dict) or route.get('workflow')!=2:raise ValueError('Save a complete map flight plan')
    if not isinstance(route.get('points'),list) or len(route['points'])>100:raise ValueError('Invalid flight-plan fixes')
    from route_constraints import normalise_constraint
    for point in route['points']:
        if not isinstance(point,dict):raise ValueError('Invalid flight-plan fix')
        normalise_constraint(point.get('constraint'))
    for key in ('origin','destination','departure','arrival','approach'):
        if not isinstance(route.get(key),dict):raise ValueError('Complete the airports, procedures and approach first')
    for key in ('origin','destination'):
        if not isinstance(route[key].get('ident'),str) or not route[key]['ident']:raise ValueError('Missing airport identifier')
    if not isinstance(plan.get('waypoints',''),str) or not isinstance(plan.get('ipra',{}),dict):raise ValueError('Invalid manual entry data')
    encoded=json.dumps(plan,ensure_ascii=False,allow_nan=False)
    if len(encoded.encode('utf-8'))>2000000:raise ValueError('Flight plan is too large')


class FlightPlanLibrary:
    def __init__(self,root=None):
        self.root=Path(root) if root is not None else default_root()
        self.lock=threading.RLock()

    def path(self,key):
        if not isinstance(key,str) or not re.fullmatch('[0-9a-f]{32}',key):raise ValueError('Invalid saved-plan identifier')
        path=self.root/(key+'.json')
        if path.resolve().parent!=self.root.resolve():raise ValueError('Invalid saved-plan path')
        return path

    def read(self,key):
        path=self.path(key)
        if path.stat().st_size>2100000:raise ValueError('Saved plan is too large')
        record=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(record,dict) or record.get('library_version')!=1 or record.get('id')!=key:raise ValueError('Invalid saved plan')
        if not isinstance(record.get('name'),str) or not record['name'].strip():raise ValueError('Invalid saved-plan name')
        validate_plan(record.get('plan'))
        record['plan']['navigation']=normalise_route_constraints(record['plan']['navigation'])
        return record

    @staticmethod
    def summary(record):
        route=record['plan']['navigation']
        return {k:record[k] for k in ('id','name','created_utc','updated_utc')} | dict(
            terrain=route.get('terrain','Caucasus'),origin=route['origin']['ident'],
            destination=route['destination']['ident'],fixes=len(route['points']))

    def list(self):
        with self.lock:
            records=[];unavailable=0
            for path in self.root.glob('*.json'):
                try:records.append(self.summary(self.read(path.stem)))
                except (OSError,ValueError,TypeError,KeyError):unavailable+=1
            records.sort(key=lambda r:r['name'].casefold())
            return dict(plans=records,unavailable=unavailable)

    def save(self,name,plan,key=None):
        if not isinstance(name,str) or not 1<=len(name.strip())<=80 or any(ord(c)<32 for c in name):raise ValueError('Use a plan name of 1–80 characters')
        name=name.strip();validate_plan(plan)
        plan=deepcopy(plan)
        plan['navigation']=normalise_route_constraints(plan['navigation'])
        with self.lock:
            previous=self.read(key) if key else None
            for other in self.list()['plans']:
                if other['name'].casefold()==name.casefold() and other['id']!=key:
                    raise ValueError('That name is already saved. Select it to update, or use a different name.')
            key=key or uuid.uuid4().hex
            now=datetime.now(timezone.utc).isoformat(timespec='microseconds')
            record=dict(library_version=1,id=key,name=name,created_utc=previous['created_utc'] if previous else now,
                        updated_utc=now,plan=plan)
            encoded=json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False)
            if len(encoded.encode('utf-8'))>2100000:raise ValueError('Flight plan is too large')
            target=self.path(key);self.root.mkdir(parents=True,exist_ok=True)
            temp=self.root/('.'+key+'.tmp-'+uuid.uuid4().hex)
            try:
                temp.write_text(encoded,encoding='utf-8')
                temp.replace(target)
            finally:temp.unlink(missing_ok=True)
            return dict(saved=self.summary(record),message='Flight plan saved.')

    def load(self,key):
        with self.lock:
            record=self.read(key)
            return dict(plan=record['plan'],saved=self.summary(record))

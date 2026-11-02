"""Validated per-waypoint constraints in canonical knots and feet."""
import math
from copy import deepcopy


def normalise_constraint(value):
    if value is None:return {}
    if not isinstance(value,dict) or set(value)-{'speed_kt','altitude_ft','altitude_type','speed_mach','speed_mode'}:
        raise ValueError('Invalid fix speed/altitude entry')
    result={}
    for key,label,low,high in [('speed_kt','Speed (kt)',1,999),('altitude_ft','Altitude (ft)',-1500,60000)]:
        number=value.get(key)
        if number is None:continue
        if isinstance(number,bool) or not isinstance(number,(int,float)) or not math.isfinite(number) or not low<=number<=high:
            raise ValueError(f'{label}: use a number from {low} to {high}')
        result[key]=number
    kind=value.get('altitude_type','altitude')
    if kind not in ('altitude','flight_level'):raise ValueError('Choose altitude or flight level')
    if 'altitude_ft' in result:
        if kind=='flight_level' and (result['altitude_ft']<0 or result['altitude_ft']%100):
            raise ValueError('Flight level must be a whole number from FL000 to FL600')
    mode=value.get('speed_mode','knots')
    if mode not in ('knots','mach'):raise ValueError('Choose speed or Mach')
    if value.get('speed_mach') is not None:
        from airspeed import mach_to_knots
        mach=value['speed_mach']
        if 'altitude_ft' not in result:raise ValueError('Enter altitude before saving a Mach speed')
        speed=mach_to_knots(mach,result['altitude_ft'])
        if not 1<=speed<=999:raise ValueError('Converted speed must be from 1 to 999 kt')
        result['speed_kt']=speed
    if mode=='mach' and 'speed_kt' in result:
        from airspeed import knots_to_mach
        if 'altitude_ft' not in result:raise ValueError('Enter altitude before saving a Mach speed')
        if value.get('speed_mach') is None:knots_to_mach(result['speed_kt'],result['altitude_ft'])
    return result


def manual_values(value):
    result=normalise_constraint(value);rows=[]
    if 'speed_kt' in result:rows.append(('Speed',str(math.floor(result['speed_kt']+.5))))
    if 'altitude_ft' in result:
        altitude=result['altitude_ft']
        rows.append(('Altitude',str(math.floor(altitude+.5))))
    return rows


def normalise_route_constraints(route):
    """Migrate old units/references without changing the caller or stored files."""
    if not isinstance(route,dict) or not isinstance(route.get('points',[]),list):raise ValueError('Invalid flight-plan fixes')
    result=deepcopy(route)
    points=list(result.get('points',[]))
    for side in ('departure','arrival'):
        terminal=result.get(side)
        if isinstance(terminal,dict) and terminal.get('mode')=='terminal':points.extend(terminal.get('fixes',[]))
    for point in points:
        if not isinstance(point,dict):raise ValueError('Invalid flight-plan fix')
        raw=point.get('constraint');canonical=normalise_constraint(raw)
        view=point.get('constraint_view')
        if view is not None:
            if not isinstance(view,dict) or set(view)-{'speed','altitude'} or view.get('speed','knots') not in ('knots','mach') or view.get('altitude','altitude') not in ('altitude','flight_level'):
                raise ValueError('Invalid speed/altitude display preference')
        elif isinstance(raw,dict):
            view={}
            if 'speed_mode' in raw:view['speed']=raw['speed_mode']
            if 'altitude_type' in raw:view['altitude']=raw['altitude_type']
        if canonical:
            point['constraint']=canonical
            if view:point['constraint_view']=view
        else:
            point.pop('constraint',None);point.pop('constraint_view',None)
    return result

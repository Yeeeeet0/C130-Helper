"""Arrival aids with explicit airport/runway associations in the DCS reference."""
import re
import math
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from procedures import reference_runway_details
from runway_mappings import reference_runway_for


def arrival_radios(airport, terminal):
    result = dict(ils=None, tacan=None, notes=[])
    ends = reference_runway_details(airport)
    runway = terminal.get('cdu_runway') or terminal.get('runway')
    reference_designation=reference_runway_for(airport.get('ident'),terminal.get('runway'),runway)
    selected = [e for e in ends if e['designator'] == reference_designation]
    reference = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))/'assets/caucasus.sqlite'
    aids=[]
    if ends:
        with closing(sqlite3.connect(reference.as_uri()+'?mode=ro', uri=True)) as con:
            con.row_factory = sqlite3.Row
            aids = [dict(r) for r in con.execute('SELECT * FROM navaids WHERE airfield_id=?', (ends[0]['airfield_id'],))]
    # resolve() supplies trusted installed data, rather than the saved plan's
    # copy of airport metadata. Imported aids remain independent of ASC tuning.
    imported=airport.get('dcs_airport',{}).get('aids',[])
    ils = {(a['ident'], float(a['frequency_value'])) for a in aids
           if len(selected) == 1 and a['runway_end_id'] == selected[0]['runway_end_id']
           and a['aid_type'] == 'ILS' and a['frequency_unit'] == 'MHz'
           and a['frequency_value'] is not None and 108.1 <= float(a['frequency_value']) <= 111.95
           and re.fullmatch(r'[A-Z0-9]{1,8}', a['ident'] or '')}
    if not ils:
        ils={(a['ident'],float(a['frequency_hz'])/1000000) for a in imported
             if a['kind']=='ILS_LOCALIZER' and a.get('runway')==(terminal.get('runway') or runway)
             and a.get('runway') and not a.get('tuning_issue')
             and 108100000<=a.get('frequency_hz',0)<=111950000
             and re.fullmatch(r'[A-Z0-9]{1,8}',a.get('ident',''))}
    if len(ils) == 1:
        ident, frequency = next(iter(ils))
        result['ils'] = dict(ident=ident, frequency=f'{frequency:.2f}', runway=runway)
    else:
        result['notes'].append('ILS skipped: no unique verified ILS for destination runway '+str(runway or '(not selected)')+'.')
    tacans = {(a['ident'], str(a['channel']).strip().upper()) for a in aids
              if a['aid_type'] == 'TACAN' and re.fullmatch(r'(?:[1-9]|[1-9][0-9]|1[01][0-9]|12[0-6])[XY]', str(a['channel']).strip().upper())}
    if not tacans:
        for aid in imported:
            channel=aid.get('channel')
            if aid['kind']=='TACAN' and isinstance(channel,(int,float)) and math.isfinite(channel) and channel==int(channel) and 1<=channel<=126 and aid.get('band') in ('X','Y'):
                tacans.add((aid.get('ident',''),str(int(channel))+aid['band']))
    if len(tacans) == 1:
        ident, channel = next(iter(tacans))
        result['tacan'] = dict(ident=ident, channel=channel)
    else:
        result['notes'].append('TACAN skipped: no unique verified destination TACAN channel and band.')
    return result

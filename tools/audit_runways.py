"""Read-only comparison of installed ASC runways and bundled DCS references."""
import csv
import json
import sqlite3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from navigation import Navigation,NAV_RELATIVE
from procedures import reference_runway_details,runway_alignment


def main():
    nav=Navigation();nav.load('Caucasus');rows=[];fields=set()
    with sqlite3.connect((nav.root/NAV_RELATIVE).as_uri()+'?mode=ro',uri=True) as con:
        con.row_factory=sqlite3.Row
        for airport in nav.points.values():
            if airport['kind']!='AIRPORT':continue
            reference=reference_runway_details(airport)
            if not reference:continue
            fields.add(reference[0]['airfield_id'])
            native=[dict(r) for r in con.execute('SELECT * FROM runways WHERE icao=?',(airport['ident'],))]
            rows.extend(runway_alignment(airport,native,reference))
    output=ROOT/'build/runway-alignment.csv';output.parent.mkdir(exist_ok=True)
    with output.open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    summary=dict(reference_airfields=len(fields),asc_runway_ends=len(rows),
                 corrected_designations=[r for r in rows if r['asc_runway']!=r['cdu_runway']],
                 course_conflicts=[r for r in rows if r['course_difference'] is not None and r['course_difference']>15],
                 missing_designation_reference=[r for r in rows if r['dcs_true_course'] is None],
                 note='Only URMO and URKG menu designations are live-confirmed. Course differences compare raw values whose north references may differ. Other terrains lack the bundled DCS runway reference.')
    (ROOT/'build/runway-alignment.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    lines=['# Runway alignment audit','',
           'Scope: '+str(len(fields))+' bundled Caucasus DCS airfield references; '+str(len(rows))+' matching ASC runway ends.',
           'Live CDU menu designations are confirmed only for URMO (10/28) and URKG (01/19). Other rows compare local data sources and are not live-cockpit verification.',
           'ASC does not label the north reference of its course field. DCS reference values are true headings. Differences below compare raw source values; no magnetic conversion is inferred.','',
           '| Airport | ASC runway | CDU choice | ASC course (reference unspecified) | DCS reference °T | Check |',
           '| --- | --- | --- | --- | --- | --- |']
    for row in rows:
        status=row['status']+(' · unverified nearby candidate '+row['reference_candidate'] if row['reference_candidate'] else '')
        lines.append('| '+' | '.join(str(v) if v is not None else '—' for v in (row['airport'],row['asc_runway'],row['cdu_runway'],row['asc_course'],row['dcs_true_course'],status))+' |')
    (ROOT/'build/runway-alignment.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2));print(output)


if __name__=='__main__':main()

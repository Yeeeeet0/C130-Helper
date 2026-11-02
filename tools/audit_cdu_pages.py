"""Report logged INDEX round trips that had a direct same-route alternative."""
import argparse
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from route_runner import indication,page_number


def audit(rows):
    current=None;pending=None;results=[]
    for row in rows:
        command=row['command']
        if command.startswith('READ') and row['response'].startswith('OK DISPLAY\n'):
            named,values=indication(row['response'].split('\n',1)[1]);current=(named['cni_title'],values)
            if pending and re.search(r'RTE [12]$',current[0]):
                number=re.search(r'RTE ([12])$',current[0])[1]
                title,previous=pending['before']
                direct=(re.search(r'RTE '+number+'$',title) and (page_number(previous) or (1,1))[0]<=3) or '<ROUTE '+number in previous or 'ROUTE '+number+'>' in previous
                if direct:results.append(dict(time=pending['time'],from_page=title,to_page=current[0],from_counter=page_number(previous)))
                pending=None
        elif command.endswith('|INDEX') and current:pending=dict(before=current,time=row['time'])
        elif command=='STOP':pending=None
    return dict(avoidable_index_round_trips=len(results),examples=results[-20:])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('log',nargs='?',default='dist/cdu-route-diagnostic.jsonl')
    parser.add_argument('--output',default='build/cdu-page-audit.json');args=parser.parse_args()
    report=audit(json.loads(line) for line in Path(args.log).read_text(encoding='utf-8').splitlines())
    Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Avoidable logged INDEX round trips:',report['avoidable_index_round_trips'])

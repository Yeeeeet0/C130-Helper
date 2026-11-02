"""Refresh the distributable DCS airport reference from installed terrain files."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from airport_reference import AirportReference
from navigation import discover_dcs

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dcs');parser.add_argument('--if-available',action='store_true');parser.add_argument('--output',default='assets/dcs_airports.sqlite')
    args=parser.parse_args();root=Path(args.dcs) if args.dcs else discover_dcs()
    if root is None:
        if args.if_available:print('DCS not found; retaining bundled airport reference.');raise SystemExit(0)
        raise SystemExit('DCS not found; keep the bundled airport reference or use --dcs.')
    counts=AirportReference(root,args.output).refresh_all()
    print(json.dumps(dict(airports=sum(counts.values()),terrains=counts),indent=2))

from contextlib import closing
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from airport_reference import AirportReference,ASC_NAV,associate,parse_sources,records,text_value

ROOT=Path(__file__).resolve().parents[1]

RADIO='''error("This Lua must not execute")
radio={
 { -- EFIV_Ivalo
 radioId='airfield18_0';callsign={{["common"]={_("Ivalo"),"Ivalo"}}};
 role={"tower","approach"};frequency={[VHF_HI]={MODULATIONTYPE_AM,118000000}};
 },
}'''
BEACONS='''beacons={{display_name=_("Ivalo");beaconId='airfield18_0';type=BEACON_TYPE_ILS_LOCALIZER;
 callsign='IV';frequency=111300000;positionGeo={latitude=68.6073,longitude=27.4053};}}'''


class AirportReferenceTests(unittest.TestCase):
    def test_custom_airfield_registration_survives_refresh_but_is_scoped_to_nav_data(self):
        self.ref.record_custom_airfield('Kola','EFIV')
        self.assertEqual(self.ref.custom_airfields('Kola'),{'EFIV'})
        self.assertEqual(self.ref.custom_airfields('Caucasus'),set())
        self.ref.load('Kola',force=True)
        self.assertEqual(AirportReference(self.root,self.ref.database).custom_airfields('Kola'),{'EFIV'})
        with closing(sqlite3.connect(self.root/ASC_NAV)) as con,con:
            con.execute("INSERT INTO airports VALUES('TEST',68,27)")
        self.assertEqual(self.ref.custom_airfields('Kola'),set())

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='airport-test-',dir=ROOT/'build')
        self.root=Path(self.temp.name).resolve();assert self.root.is_relative_to((ROOT/'build').resolve())
        self.addCleanup(self.temp.cleanup)
        asc=self.root/ASC_NAV;asc.parent.mkdir(parents=True)
        with closing(sqlite3.connect(asc)) as con, con:
            con.execute('CREATE TABLE airports(icao TEXT,lat REAL,lon REAL)')
            con.execute("INSERT INTO airports VALUES('EFIV',68.6073,27.4053)")
        self.folder=self.root/'Mods/terrains/Kola';self.folder.mkdir(parents=True)
        (self.folder/'radio.lua').write_text(RADIO)
        (self.folder/'beacons.lua').write_text(BEACONS)
        self.ref=AirportReference(self.root,self.root/'reference.sqlite')

    def test_imports_names_and_radios_without_changing_asc(self):
        before=(self.root/ASC_NAV).read_bytes()
        result=self.ref.load('Kola')['EFIV']
        self.assertEqual(result['name'],'Ivalo')
        self.assertEqual(result['icao'],'EFIV')
        self.assertEqual(result['radios'][0]['frequency_hz'],118000000)
        self.assertEqual(result['aids'][0]['ident'],'IV')
        self.assertEqual((self.root/ASC_NAV).read_bytes(),before)
        with closing(sqlite3.connect(self.ref.database)) as con, con:
            self.assertEqual(con.execute("SELECT icao FROM airports WHERE terrain='Kola'").fetchone()[0],'EFIV')

    def test_changed_dcs_file_refreshes_cached_reference(self):
        self.ref.load('Kola')
        (self.folder/'radio.lua').write_text(RADIO.replace('118000000','119100000'))
        self.assertEqual(self.ref.load('Kola')['EFIV']['radios'][0]['frequency_hz'],119100000)

    def test_braces_inside_lua_strings_and_comments_do_not_split_records(self):
        raw='radio={{radioId="airfield1_0";value="} {";-- }\n},{radioId="airfield2_0";}}'
        self.assertEqual(len(records(raw,'radio')),2)

    def test_quoted_names_preserve_apostrophes(self):
        self.assertEqual(text_value('display_name=_("King Hussein\'s");','display_name'),"King Hussein's")

    def test_ambiguous_position_match_is_skipped(self):
        groups=parse_sources(RADIO.replace('EFIV_Ivalo','Ivalo'),BEACONS)
        airports=[dict(icao='AAAA',lat=68.6073,lon=27.4053),dict(icao='BBBB',lat=68.6074,lon=27.4054)]
        self.assertEqual(associate(groups,airports,'Kola',[]),{})

    def test_conflicting_explicit_airport_codes_are_skipped(self):
        groups=parse_sources(RADIO,BEACONS);groups['18']['codes'].append('OTHER')
        airports=[dict(icao='EFIV',lat=68.6073,lon=27.4053),dict(icao='OTHER',lat=70,lon=28)]
        self.assertEqual(associate(groups,airports,'Kola',[]),{})

    def test_airport_identifier_with_far_away_beacons_is_skipped(self):
        groups=parse_sources(RADIO,BEACONS)
        self.assertEqual(associate(groups,[dict(icao='EFIV',lat=60,lon=20)],'Kola',[]),{})

    def test_invalid_dcs_ils_frequency_is_flagged_without_guessing(self):
        aid=parse_sources(RADIO,BEACONS.replace('111300000','212000000'))['18']['aids'][0]
        self.assertEqual(aid['frequency_hz'],212000000)
        self.assertIn('Outside',aid['tuning_issue'])

    def test_reference_import_does_not_add_airports_absent_from_asc(self):
        groups=parse_sources(RADIO,'')
        self.assertEqual(associate(groups,[dict(icao='OTHER',lat=68.6073,lon=27.4053)],'Kola',[]),{})

    def test_non_asc_and_world_navaids_are_stored_independently(self):
        (self.folder/'beacons.lua').write_text(BEACONS.replace('airfield18_0','world_999').replace("callsign='IV'","callsign='notASC'"))
        with closing(sqlite3.connect(self.root/ASC_NAV)) as con,con:con.execute('DELETE FROM airports')
        self.assertEqual(self.ref.load('Kola'),{})
        self.assertEqual(self.ref.navaids('Kola')[0]['ident'],'notASC')

    def test_dcs_only_runways_are_not_promoted_to_asc_choices(self):
        from contextlib import closing
        from types import SimpleNamespace
        from procedures import airport_options
        with closing(sqlite3.connect(self.root/ASC_NAV)) as con,con:
            con.executescript('''CREATE TABLE runways(name TEXT,icao TEXT);
              CREATE TABLE sids(airport_identifier TEXT,procedure_identifier TEXT,route_type TEXT,transition_identifier TEXT,seqno INTEGER);''')
        point=dict(id='a:1',ident='EFIV',kind='AIRPORT',lat=41.929,lon=41.863,x=0,y=0)
        nav=SimpleNamespace(root=self.root,points={'a:1':point},theatre='Caucasus',load=lambda:None)
        self.assertEqual(airport_options(nav,point['ident'],'SID')['runways'],[])


if __name__=='__main__':unittest.main()

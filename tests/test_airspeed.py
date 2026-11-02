import json
import math
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from airspeed import A0_KT,pressure_ratio,mach_to_knots,knots_to_mach

class AirspeedTests(unittest.TestCase):
    def test_sea_level_identity_and_altitude_dependence(self):
        self.assertAlmostEqual(pressure_ratio(0),1)
        self.assertAlmostEqual(mach_to_knots(.8,0),.8*A0_KT,places=8)
        self.assertAlmostEqual(mach_to_knots(.8,10000),448.5461,places=3)
        self.assertAlmostEqual(mach_to_knots(.8,35000),271.9281,places=3)
        self.assertGreater(mach_to_knots(.8,10000),mach_to_knots(.8,20000))

    def test_round_trip_across_troposphere_and_stratosphere(self):
        for altitude in [-1500,0,10000,35000,36089.24,40000,60000]:
            for mach in [.05,.2,.5,.8,.99]:
                self.assertAlmostEqual(knots_to_mach(mach_to_knots(mach,altitude),altitude),mach,places=10)
        self.assertAlmostEqual(pressure_ratio(36089.2388-.01),pressure_ratio(36089.2388+.01),places=6)

    def test_rejects_missing_altitude_and_unsupported_inputs(self):
        for altitude in [None,True,float('nan'),-1501,60001]:
            with self.subTest(altitude=altitude),self.assertRaises(ValueError):mach_to_knots(.8,altitude)
        for mach in [True,0,-.5,1,1.2,float('inf')]:
            with self.subTest(mach=mach),self.assertRaises(ValueError):mach_to_knots(mach,10000)
        with self.assertRaises(ValueError):knots_to_mach(600,60000)

    def test_pressure_at_standard_layer_boundary(self):
        self.assertAlmostEqual(pressure_ratio(11000/.3048),22632.04/101325,places=6)
        self.assertLess(pressure_ratio(60000),pressure_ratio(40000))

    def test_frontend_and_backend_use_identical_conversions(self):
        pairs=[[m,h] for m in [.2,.5,.8,.99] for h in [-1500,0,10000,36089.24,60000]]
        code="global.window=globalThis;require('./assets/airspeed.js');const p=JSON.parse(process.argv[1]);console.log(JSON.stringify(p.map(([m,h])=>[Airspeed.machToKnots(m,h),Airspeed.knotsToMach(Airspeed.machToKnots(m,h),h)])));"
        values=json.loads(subprocess.check_output(['node','-e',code,json.dumps(pairs)],cwd=ROOT,text=True))
        for (mach,altitude),(knots,inverse) in zip(pairs,values):
            self.assertAlmostEqual(knots,mach_to_knots(mach,altitude),places=9)
            self.assertAlmostEqual(inverse,mach,places=10)

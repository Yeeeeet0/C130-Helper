import io
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from kola_charts import KolaChartPyramid,dds_mip

ROOT=Path(__file__).resolve().parents[1]


def dds(color):
    header=bytearray(128);header[:4]=b'DDS '
    struct.pack_into('<I',header,4,124);struct.pack_into('<I',header,8,0xA1007)
    struct.pack_into('<II',header,12,1024,1024);struct.pack_into('<I',header,28,11)
    struct.pack_into('<II',header,76,32,4);header[84:88]=b'DXT1';struct.pack_into('<I',header,108,0x401008)
    block=struct.pack('<HHI',color,color,0)
    return bytes(header)+b''.join(block*(((max(1,1024>>i)+3)//4)**2) for i in range(11))


class ChartTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='chart-test-',dir=ROOT/'build')
        self.root=Path(self.temp.name).resolve();assert self.root.is_relative_to((ROOT/'build').resolve())
        self.addCleanup(self.temp.cleanup)

    def test_mip_uses_its_own_header_and_size(self):
        raw=dds_mip(dds(0xF800),4)
        self.assertEqual(struct.unpack_from('<II',raw,12),(64,64))
        with Image.open(io.BytesIO(raw)) as image:self.assertEqual(image.convert('RGB').getpixel((10,10)),(255,0,0))

    def test_truncated_mip_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Truncated'):dds_mip(dds(0)[:150],4)

    def test_overview_preserves_geographic_rows_overlap_and_empty_coverage(self):
        archive=self.root/'charts.zip'
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('south.dds',dds(0xF800));z.writestr('north.dds',dds(0x001F))
        tiles=[dict(id=name,archive=archive,member=name+'.dds',scale=32,bounds=[0,row*32736,32768,row*32736+32768]) for row,name in enumerate(('south','north'))]
        pyramid=KolaChartPyramid(tiles,self.root/'cache');key=next(k for k,t in pyramid.tiles.items() if t['factor']==4)
        result=pyramid.tile(key)
        with Image.open(io.BytesIO(result)) as image:
            self.assertEqual(image.getpixel((30,950))[:3],(255,0,0))
            self.assertEqual(image.getpixel((30,700))[:3],(0,0,255))
            self.assertEqual(image.getpixel((900,50))[3],0)
        self.assertEqual(pyramid.tiles[key]['bounds'],[0,0,131072,130976])
        self.assertEqual(pyramid.tile(key),result)


if __name__=='__main__':unittest.main()

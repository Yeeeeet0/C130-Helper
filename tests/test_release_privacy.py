import hashlib
import html
from pathlib import Path
import sys
import unittest
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from desktop import build_page,locate_files


class ReleasePrivacyTests(unittest.TestCase):
    def setUp(self):
        self.licence=(ROOT/'LICENSE.txt').read_text(encoding='utf-8')
        self.owner=next(line for line in self.licence.splitlines() if line.startswith('Copyright')).split('2026 ',1)[1].split('. All rights reserved',1)[0]

    def test_actual_licence_is_unchanged(self):
        self.assertEqual(hashlib.sha256((ROOT/'LICENSE.txt').read_bytes()).hexdigest(),
                         '707aae2e373092f8cd0d0497f2a853a98c7f6d8c4e5e6b54b0137ab7ad08772e')

    def test_name_occurs_only_inside_the_actual_app_licence(self):
        page,_=build_page(*locate_files())
        self.assertIn(html.escape(self.licence),page)
        self.assertNotIn(self.owner,page.replace(html.escape(self.licence),''))
        for file in ['src/installer.py','src/setup_support.py','README.txt','CDU_HELPER.md','DISTRIBUTION.md','THIRD_PARTY_NOTICES.txt']:
            self.assertNotIn(self.owner,(ROOT/file).read_text(encoding='utf-8'),file)

    def test_guides_and_pdf_metadata_do_not_contain_personal_name(self):
        files=[ROOT/'output/pdf/C130J_CDU_Helper_User_Guide.pdf',*sorted((ROOT/'output/pdf/help').glob('*.pdf'))]
        self.assertEqual(len(files),9)
        for file in files:
            reader=PdfReader(file)
            self.assertNotIn(self.owner,str(reader.metadata),str(file))
            for page in reader.pages:self.assertNotIn(self.owner,page.extract_text(),str(file))

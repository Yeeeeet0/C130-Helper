import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import help_documents
from cdu_helper import CduApi


class HelpDocumentsTests(unittest.TestCase):
    def test_section_pdfs_are_exact_pages_from_the_full_guide(self):
        main=PdfReader(help_documents.document_path('all'))
        self.assertEqual(len(main.pages),8)
        for number,topic in enumerate(list(help_documents.TOPICS)[1:]):
            section=PdfReader(help_documents.document_path(topic))
            self.assertEqual(len(section.pages),1)
            self.assertEqual(section.pages[0].extract_text(),main.pages[number].extract_text())

    def test_api_launches_only_whitelisted_local_documents(self):
        with patch('help_documents.os.startfile') as launch:
            self.assertIn('message',CduApi().open_help('automatic'))
            launch.assert_called_once_with(str(help_documents.document_path('automatic')))
            launch.reset_mock()
            for topic in ['../LICENSE.txt','https://example.com',None,{},'']:
                self.assertIn('error',CduApi().open_help(topic))
            launch.assert_not_called()

    def test_viewer_failure_is_reported_to_the_ui(self):
        with patch('help_documents.os.startfile',side_effect=OSError('No PDF viewer available')):
            self.assertIn('No PDF viewer',CduApi().open_help()['error'])

    def test_frozen_app_uses_bundled_help_without_install_location_dependency(self):
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'_MEIPASS',str(ROOT/'build/help-test-bundle'),create=True):
            with patch('help_documents.Path.is_file',return_value=True):
                self.assertEqual(help_documents.document_path('map'),ROOT/'build/help-test-bundle/assets/help/C130J_Help_03.pdf')
            self.assertIn('missing',CduApi().open_help('map')['error'])

import json
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from setup_support import install,uninstall,LOADER,MANIFEST,shortcut_bytes,automatic_profiles

ROOT=Path(__file__).resolve().parents[1]


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='setup-test-',dir=ROOT/'build')
        self.root=Path(self.temp.name).resolve()
        assert self.root.is_relative_to((ROOT/'build').resolve())
        self.addCleanup(self.temp.cleanup)
        self.payload=self.root/'payload';self.payload.mkdir()
        for name in ('C130J_Reference.exe','C130J.ico','CDU_HELPER.md','C130J_CDU_Helper_User_Guide.pdf','C130J_Helper.lua','setup.exe',
                     'LICENSE.txt','THIRD_PARTY_NOTICES.txt','C130J_KneeboardBridge.lua','C130J_KneeboardPage.lua'):
            (self.payload/name).write_bytes(('new '+name).encode())
        self.target=self.root/'installed';self.profile=self.root/'DCS';(self.profile/'Scripts').mkdir(parents=True)
        self.export=self.profile/'Scripts/Export.lua';self.bridge=self.profile/'Scripts/C130J_Helper.lua'
        self.export.write_bytes(b'-- existing exporter\r\n');self.bridge.write_bytes(b'old bridge')

    def install(self,profiles=None):
        return install(self.payload,self.target,[self.profile] if profiles is None else profiles,
                       setup_exe=self.payload/'setup.exe',register=False,make_shortcuts=False)

    def test_install_update_uninstall_restores_existing_exporter_and_bridge(self):
        self.install();self.assertIn(LOADER.encode(),self.export.read_bytes())
        self.assertEqual(self.bridge.read_bytes(),b'new C130J_Helper.lua')
        (self.payload/'C130J_Helper.lua').write_bytes(b'updated bridge')
        self.install()
        self.assertEqual(self.export.read_bytes().count(LOADER.encode()),1)
        self.export.write_bytes(self.export.read_bytes()+b'-- added later\r\n')
        (self.target/'my-plan.json').write_text('{}')
        uninstall(self.target,register=False)
        self.assertEqual(self.bridge.read_bytes(),b'old bridge')
        self.assertIn(b'-- existing exporter',self.export.read_bytes())
        self.assertIn(b'-- added later',self.export.read_bytes())
        self.assertNotIn(LOADER.encode(),self.export.read_bytes())
        self.assertTrue((self.target/'my-plan.json').is_file())
        self.assertFalse((self.target/'C130J_Reference.exe').exists())

    def test_licence_documents_are_installed_and_owned(self):
        self.install([])
        manifest=json.loads((self.target/MANIFEST).read_text())
        for name in ('LICENSE.txt','THIRD_PARTY_NOTICES.txt'):
            self.assertEqual((self.target/name).read_bytes(),(self.payload/name).read_bytes())
            self.assertIn(name,manifest['files'])
        uninstall(self.target,register=False)
        self.assertFalse((self.target/'LICENSE.txt').exists())
        self.assertFalse((self.target/'THIRD_PARTY_NOTICES.txt').exists())

    def test_live_kneeboard_installs_only_profile_files_and_restores_originals(self):
        from setup_support import KNEEBOARD_FILES
        folder=self.profile/'Kneeboard/C-130J-30';folder.mkdir(parents=True)
        user=folder/'my-checklist.lua';user.write_bytes(b'personal checklist')
        original=folder/'C130J_CDU_Helper_01.lua';original.write_bytes(b'previous manual page')
        self.install()
        manifest=json.loads((self.target/MANIFEST).read_text())
        self.assertEqual(len(manifest['profiles'][0]['kneeboard']),22)
        self.assertTrue(all((self.profile/name).is_file() for name in KNEEBOARD_FILES))
        self.assertIn(b'C130J_HELPER_KB_PAGE = 20',(folder/'C130J_CDU_Helper_20.lua').read_bytes())
        self.install();uninstall(self.target,register=False)
        self.assertEqual(original.read_bytes(),b'previous manual page')
        self.assertEqual(user.read_bytes(),b'personal checklist')
        self.assertFalse((folder/'C130J_CDU_Helper_20.lua').exists())
        self.assertFalse((self.profile/'Scripts/C130J_KneeboardPage.lua').exists())

    def test_modified_live_kneeboard_is_preserved(self):
        self.install()
        page=self.profile/'Kneeboard/C-130J-30/C130J_CDU_Helper_01.lua';page.write_bytes(b'my modified page')
        kept=uninstall(self.target,register=False)
        self.assertEqual(page.read_bytes(),b'my modified page')
        self.assertIn(str(page),kept)

    def test_tampered_kneeboard_manifest_is_rejected_before_uninstall(self):
        self.install();path=self.target/MANIFEST;manifest=json.loads(path.read_text())
        manifest['profiles'][0]['kneeboard'][0]['relative']='../outside.lua'
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'kneeboard file list'):uninstall(self.target,register=False)
        self.assertTrue(self.bridge.exists())

    def test_failed_update_rolls_back_app_and_profile(self):
        self.install();before={p:p.read_bytes() for p in [self.target/'C130J_Reference.exe',self.target/MANIFEST,self.export,self.bridge]}
        (self.payload/'C130J_Reference.exe').write_bytes(b'updated app')
        with self.assertRaisesRegex(ValueError,'profile not found'):
            self.install([self.profile,self.root/'Z-missing-profile'])
        for path,content in before.items():self.assertEqual(path.read_bytes(),content)

    def test_modified_bridge_is_preserved_on_uninstall(self):
        self.install();self.bridge.write_bytes(b'user edited bridge')
        kept=uninstall(self.target,register=False)
        self.assertIn(str(self.bridge),kept)
        self.assertEqual(self.bridge.read_bytes(),b'user edited bridge')
        self.assertIn(LOADER.encode(),self.export.read_bytes())

    def test_new_bridge_is_removed_without_touching_other_exporters(self):
        self.bridge.unlink();self.install();uninstall(self.target,register=False)
        self.assertFalse(self.bridge.exists());self.assertIn(b'existing exporter',self.export.read_bytes())

    def test_unrelated_existing_app_file_is_not_overwritten(self):
        self.target.mkdir();(self.target/'C130J_Reference.exe').write_bytes(b'unrelated')
        with self.assertRaisesRegex(ValueError,'empty app folder'):self.install()
        self.assertEqual((self.target/'C130J_Reference.exe').read_bytes(),b'unrelated')

    def test_manifest_cannot_delete_a_file_outside_owned_names(self):
        self.install();manifest=json.loads((self.target/MANIFEST).read_text())
        manifest['files']['../outside.txt']='anything'
        (self.target/MANIFEST).write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'file list'):uninstall(self.target,register=False)

    def test_native_shortcut_can_be_created_in_temporary_folder(self):
        self.install([])
        data=shortcut_bytes(self.target,self.root/'shortcuts/C130J.lnk')
        self.assertGreater(len(data),100)

    def test_automatic_profiles_detects_existing_or_uses_standard_profile(self):
        saved=self.root/'Saved Games'
        self.assertEqual(automatic_profiles(saved),[saved/'DCS'])
        for name in ['DCS','DCS.openbeta','Other']:(saved/name).mkdir(parents=True)
        self.assertEqual(automatic_profiles(saved),[saved/'DCS',saved/'DCS.openbeta'])

    def test_desktop_shortcut_can_be_omitted_and_removed_on_update(self):
        from setup_support import APP_NAME
        desktop=self.root/'Desktop'/(APP_NAME+'.lnk')
        def shortcut(target,path):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'owned shortcut');return path.read_bytes()
        with patch('setup_support.shell_folder',side_effect=lambda name,fallback:self.root/name),patch('setup_support.shortcut_bytes',side_effect=shortcut):
            def setup(enabled,**kwargs):return install(self.payload,self.target,[],setup_exe=self.payload/'setup.exe',register=False,desktop=enabled,**kwargs)
            setup(False);self.assertFalse(desktop.exists())
            setup(True);self.assertTrue(desktop.exists())
            def fail(n,text):
                if n==100:raise RuntimeError('Simulated failure')
            with self.assertRaisesRegex(RuntimeError,'Simulated failure'):setup(False,progress=fail)
            self.assertEqual(desktop.read_bytes(),b'owned shortcut')
            result=setup(False)
            self.assertFalse(desktop.exists())
            self.assertEqual(len(result['shortcuts']),1)

    def test_unchecking_desktop_preserves_user_modified_shortcut(self):
        from setup_support import APP_NAME
        desktop=self.root/'Desktop'/(APP_NAME+'.lnk')
        def shortcut(target,path):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'owned shortcut');return path.read_bytes()
        with patch('setup_support.shell_folder',side_effect=lambda name,fallback:self.root/name),patch('setup_support.shortcut_bytes',side_effect=shortcut):
            install(self.payload,self.target,[],setup_exe=self.payload/'setup.exe',register=False,desktop=True)
            desktop.write_bytes(b'user modified shortcut')
            install(self.payload,self.target,[],setup_exe=self.payload/'setup.exe',register=False,desktop=False)
        self.assertEqual(desktop.read_bytes(),b'user modified shortcut')

    def test_automatic_install_remembers_dcs_and_creates_bridge_profile(self):
        dcs=self.root/'DCS Install';database=dcs/'Mods/aircraft/C130J/Cockpit/Resources/nav_data.db'
        database.parent.mkdir(parents=True);database.write_bytes(b'reference')
        profile=self.root/'Saved Games/DCS'
        install(self.payload,self.target,[profile],setup_exe=self.payload/'setup.exe',register=False,make_shortcuts=False,dcs_root=dcs,create_profiles=True)
        config=self.target/'dcs-location.json'
        self.assertEqual(json.loads(config.read_text())['dcs_root'],str(dcs.resolve()))
        self.assertIn(LOADER,(profile/'Scripts/Export.lua').read_text())
        self.install([])
        self.assertTrue(config.exists())
        uninstall(self.target,register=False)
        self.assertFalse(config.exists())
        self.assertFalse((profile/'Scripts/C130J_Helper.lua').exists())

    def test_windows_registration_and_removal_use_the_install_location(self):
        import winreg
        from setup_support import register_app,unregister_app
        key_path='Software\\CodexInstallerTests\\'+uuid.uuid4().hex
        with patch('setup_support.REGISTRY_KEY',key_path):
            try:
                register_app(self.target)
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key_path) as key:
                    command=winreg.QueryValueEx(key,'UninstallString')[0]
                    self.assertEqual(winreg.QueryValueEx(key,'Publisher')[0],'C-130J CDU Helper')
                self.assertIn(str(self.target/'Uninstall.exe'),command)
                self.assertIn('--uninstall',command)
                unregister_app(self.root/'different-folder')
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key_path):pass
                unregister_app(self.target)
                with self.assertRaises(FileNotFoundError):winreg.OpenKey(winreg.HKEY_CURRENT_USER,key_path)
            finally:
                try:winreg.DeleteKey(winreg.HKEY_CURRENT_USER,key_path)
                except FileNotFoundError:pass


if __name__=='__main__':unittest.main()

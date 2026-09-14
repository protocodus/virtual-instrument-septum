#!/usr/bin/env python3
"""Exercise macOS packaging control flow with fake signing/notary tools.

No certificates, Keychain access, network requests, or real packages are used.
"""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]

MOCK_TOOL = r'''#!/usr/bin/env python3
import json, os, pathlib, plistlib, shutil, sys, zipfile
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['MOCK_LOG'], 'a') as log:
    log.write(json.dumps([name, *args]) + '\n')
if name == 'uname':
    print('Darwin')
elif name == 'lipo':
    print('x86_64 arm64')
elif name == 'PlistBuddy':
    key = args[1].split(':', 1)[1]
    with open(args[2], 'rb') as source:
        print(plistlib.load(source)[key])
elif name == 'ditto':
    source, output = map(pathlib.Path, args[-2:])
    if '-c' in args:
        with zipfile.ZipFile(output, 'w') as archive:
            for entry in sorted(source.rglob('*')):
                if entry.is_file(): archive.write(entry, entry.relative_to(source))
    elif '-x' in args:
        with zipfile.ZipFile(source) as archive: archive.extractall(output)
    elif source.is_dir():
        shutil.copytree(source, output, dirs_exist_ok=True)
    else:
        shutil.copy2(source, output)
elif name == 'pkgbuild':
    source = pathlib.Path(args[args.index('--root') + 1])
    pathlib.Path(args[-1]).write_text(json.dumps(sorted(str(p.relative_to(source)) for p in source.rglob('*'))))
elif name == 'productsign':
    shutil.copy2(args[-2], args[-1])
elif name == 'xcrun':
    if args[0] == '--find':
        print('/mock/' + args[1])
    elif args[:2] == ['notarytool', 'submit']:
        status = os.environ.get('MOCK_NOTARY_STATUS', 'Accepted')
        if os.environ.get('MOCK_REJECT_PKG') and args[2].endswith('.pkg'): status = 'Invalid'
        sys.stdout.buffer.write(plistlib.dumps({'status': status, 'id': 'mock-submission'}))
    elif args[:2] == ['stapler', 'staple']:
        target = pathlib.Path(args[-1])
        if os.environ.get('MOCK_STAPLE_FAIL'): sys.exit(65)
        if target.is_dir(): (target / 'Contents' / 'stapled-ticket').write_text('ticket')
        else:
            with target.open('a') as output: output.write('\nstapled-ticket')
    elif args[:2] == ['stapler', 'validate']:
        target = pathlib.Path(args[-1])
        if target.is_dir() and not (target / 'Contents' / 'stapled-ticket').exists(): sys.exit(65)
elif name == 'codesign':
    if os.environ.get('MOCK_SIGN_FAIL'): sys.exit(1)
else:
    raise SystemExit('Unexpected mock tool: ' + name)
'''


class PackagingTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            self.skipTest('The packaging script requires a POSIX shell')
        self.folder = tempfile.TemporaryDirectory(prefix='septum-package-test-')
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)
        self.project = self.path / 'project'
        (self.project / 'scripts').mkdir(parents=True)
        self.script = self.project / 'scripts/sign-and-package-macos.sh'
        shutil.copy2(ROOT / 'scripts/sign-and-package-macos.sh', self.script)
        (self.project / 'ThirdParty').mkdir()
        for notice in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'ThirdParty/JUCE-LICENSE.md',
                       'ThirdParty/JUCE-DEPENDENCY-NOTICES.txt'):
            (self.project / notice).write_text('Fixture notice\n')
        self.build = self.path / 'build'
        for kind, name, package in (('VST3', 'Septum.vst3', 'BNDL'),
                                    ('AU', 'Septum.component', 'BNDL'),
                                    ('Standalone', 'Septum.app', 'APPL')):
            bundle = self.build / 'Septum_artefacts/Release' / kind / name / 'Contents'
            (bundle / 'MacOS').mkdir(parents=True)
            (bundle / 'MacOS/Septum').write_bytes(b'fixture')
            (bundle / 'Info.plist').write_bytes(plistlib.dumps({
                'CFBundleShortVersionString': '1.2.3', 'CFBundlePackageType': package}))
        self.staging = self.build / 'package-root'
        self.staging.mkdir()
        (self.staging / 'prior-staging').write_text('keep before preflight')
        self.dist = self.build / 'dist'
        self.dist.mkdir()
        self.old = self.dist / 'Septum-old-macOS-universal.zip'
        self.old.write_bytes(b'last good release')
        self.bin = self.path / 'bin'
        self.bin.mkdir()
        for name in ('uname', 'codesign', 'ditto', 'lipo', 'pkgbuild', 'productsign', 'xcrun', 'PlistBuddy'):
            tool = self.bin / name
            tool.write_text(MOCK_TOOL)
            tool.chmod(0o755)
        self.log = self.path / 'commands.jsonl'
        self.env = {**os.environ, 'BUILD_DIR': str(self.build), 'BUILD_NUMBER': '42',
                    'APP_SIGN_IDENTITY': '-', 'INSTALLER_SIGN_IDENTITY': '', 'NOTARY_PROFILE': '',
                    'COMMERCIAL_RELEASE': '0', 'CONFIG': 'Release', 'VERSION': '',
                    'PLIST_BUDDY': str(self.bin / 'PlistBuddy'), 'MOCK_LOG': str(self.log),
                    'PATH': os.pathsep.join((str(self.bin), str(Path(sys.executable).parent), os.environ['PATH']))}
        for variable in ('MOCK_NOTARY_STATUS', 'MOCK_REJECT_PKG', 'MOCK_STAPLE_FAIL', 'MOCK_SIGN_FAIL'):
            self.env.pop(variable, None)

    def run_script(self, **changes):
        return subprocess.run(['bash', str(self.script)], env={**self.env, **changes},
                              capture_output=True, text=True, timeout=30)

    def commercial(self, **changes):
        return self.run_script(COMMERCIAL_RELEASE='1', NOTARY_PROFILE='test-profile',
                               APP_SIGN_IDENTITY='Developer ID Application: Fixture',
                               INSTALLER_SIGN_IDENTITY='Developer ID Installer: Fixture', **changes)

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_preflight_keeps_prior_staging_and_release(self):
        for settings in ({'COMMERCIAL_RELEASE': '1'}, {'COMMERCIAL_RELEASE': 'yes'},
                         {'NOTARY_PROFILE': 'test-profile'},
                         {'NOTARY_PROFILE': 'test-profile', 'APP_SIGN_IDENTITY': 'Developer ID Application: Fixture'},
                         {'NOTARY_PROFILE': 'test-profile', 'INSTALLER_SIGN_IDENTITY': '-'}):
            with self.subTest(settings=settings):
                result = self.run_script(**settings)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertTrue((self.staging / 'prior-staging').exists())
                self.assertEqual(self.old.read_bytes(), b'last good release')

    def test_missing_notice_fails_before_clearing_staging(self):
        (self.project / 'LICENSE').unlink()
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn('missing distribution notice', result.stderr)
        self.assertTrue((self.staging / 'prior-staging').exists())

    def test_adhoc_ci_packaging_remains_available(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.old.exists())
        self.assertEqual(len(list(self.dist.glob('*.zip'))), 1)
        self.assertEqual(len(list(self.dist.glob('*.pkg'))), 1)
        self.assertFalse(any(command[:2] == ['xcrun', 'notarytool'] for command in self.commands()))
        with zipfile.ZipFile(next(self.dist.glob('*.zip'))) as archive:
            self.assertIn('Applications/Septum.app/Contents/Resources/Documentation/Septum-LICENSE.txt', archive.namelist())
            self.assertEqual(sum(name.endswith('/JUCE-DEPENDENCY-NOTICES.txt')
                                 for name in archive.namelist()), 4)

    def test_commercial_staples_all_bundles_before_zip_and_installer(self):
        result = self.commercial()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = self.commands()
        submissions = [command for command in commands if command[:3] == ['xcrun', 'notarytool', 'submit']]
        self.assertEqual([Path(command[3]).suffix for command in submissions], ['.zip', '.pkg'])
        staples = [command for command in commands if command[:3] == ['xcrun', 'stapler', 'staple']]
        self.assertEqual([Path(command[-1]).suffix for command in staples], ['.vst3', '.component', '.app', '.pkg'])
        with zipfile.ZipFile(next(self.dist.glob('*.zip'))) as archive:
            self.assertEqual(sum(name.endswith('/stapled-ticket') for name in archive.namelist()), 3)
        package = next(self.dist.glob('*.pkg')).read_text()
        self.assertEqual(package.count('/stapled-ticket'), 3)
        self.assertTrue(package.endswith('\nstapled-ticket'))
        self.assertFalse(list(self.build.glob('package-release.*')))

    def test_rejected_notary_response_preserves_prior_release(self):
        # A zero tool exit code must not turn an Invalid/Rejected status into success.
        for status in ('Invalid', 'Rejected', 'In Progress'):
            with self.subTest(status=status):
                result = self.commercial(MOCK_NOTARY_STATUS=status)
                self.assertEqual(result.returncode, 1)
                self.assertIn('did not accept', result.stderr)
                self.assertEqual(self.old.read_bytes(), b'last good release')
                self.assertEqual(len(list(self.dist.iterdir())), 1)

    def test_late_notarization_signing_and_stapling_failures_preserve_prior_release(self):
        for failure in ('MOCK_REJECT_PKG', 'MOCK_SIGN_FAIL', 'MOCK_STAPLE_FAIL'):
            with self.subTest(failure=failure):
                result = self.commercial(**{failure: '1'})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.old.read_bytes(), b'last good release')
                self.assertEqual(len(list(self.dist.iterdir())), 1)
                self.assertFalse(list(self.build.glob('package-release.*')))


if __name__ == '__main__':
    unittest.main()

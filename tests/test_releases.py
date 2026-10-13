"""No network, GitHub writes or hardware required."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('releases', ROOT / 'scripts/releases.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / 'build/r60abd1-ESP32-C3'
        self.build.mkdir(parents=True)
        self.version = 'v1.0.0-alpha.1'
        self.manifest = {'name': 'R60ABD1', 'version': self.version, 'builds': [{'chipFamily': 'ESP32-C3', 'parts': [{'path': 'factory.bin', 'offset': 0}], 'ota': {'path': 'ota.bin', 'md5': r.hashlib.md5(b'ota').hexdigest()}}]}
        r.write(self.build / 'manifest.json', self.manifest)
        (self.build / 'factory.bin').write_bytes(b'factory')
        (self.build / 'ota.bin').write_bytes(b'ota')

    def package(self):
        dest = self.root / 'alpha'
        r.package(self.root / 'build', dest, self.version, 'a' * 40, '2026.9.0')
        return dest

    def test_catalog_agrees_with_readme_and_uart(self):
        models, boards = r.catalog()
        self.assertEqual([m['id'] for m in models], ['r60abd1'])
        self.assertTrue(all(b['uart'] == {'tx': 21, 'rx': 20} for b in boards))

    def test_version_validation(self):
        for value in ('dev', 'latest', 'v1.0.0', 'v1.0.0-nightly.1', '../alpha', 'v1.0.0-alpha.1;echo hi'):
            with self.subTest(value=value), self.assertRaises(ValueError): r.channel(value)

    def test_all_shared_radar_configs_use_the_same_c3_uart(self):
        for core in (ROOT / 'tests/common').glob('*.yaml'):
            if core.name.startswith('_'):
                continue  # Reusable helpers are not radar UART configurations.
            content = core.read_text(encoding='utf-8')
            with self.subTest(model=core.stem):
                self.assertRegex(content, r'(?m)^\s+tx_pin:\s+GPIO21\b')
                self.assertRegex(content, r'(?m)^\s+rx_pin:\s+GPIO20\b')

    def test_package_checks_factory_and_ota(self):
        dest = self.package()
        meta = r.read(dest / 'release.json')
        self.assertEqual(meta['channel'], 'alpha')
        self.assertEqual(len(meta['files']), 3)
        r.validate_bundle(meta, dest / 'firmware-bundle.zip')

    def test_build_action_v7_lowercase_download_layouts(self):
        for folder in ('r60abd1-esp32c3', 'firmware-r60abd1-esp32c3',
                       'firmware-r60abd1-esp32c3/r60abd1-esp32c3'):
            with self.subTest(folder=folder), tempfile.TemporaryDirectory() as temp:
                build = Path(temp) / 'build'
                r.shutil.copytree(self.build, build / folder)
                manifest = r.read(build / folder / 'manifest.json')
                for entry, old in ((manifest['builds'][0]['parts'][0], 'factory.bin'),
                                   (manifest['builds'][0]['ota'], 'ota.bin')):
                    entry['path'] = f'r60abd1-esp32c3.{old}'
                    (build / folder / old).rename(build / folder / entry['path'])
                r.write(build / folder / 'manifest.json', manifest)
                dest = Path(temp) / 'release'
                r.package(build, dest, self.version, 'a' * 40, '2026.9.0')
                meta = r.read(dest / 'release.json')
                self.assertIn('/r60abd1-ESP32-C3/manifest.json', meta['firmware'][0]['manifest'])
                self.assertIn('r60abd1-ESP32-C3/r60abd1-esp32c3.factory.bin', meta['files'])

    def test_manifest_factory_checksum_must_match_packaged_bytes(self):
        self.manifest['builds'][0]['parts'][0]['sha256'] = '0' * 64
        r.write(self.build / 'manifest.json', self.manifest)
        with self.assertRaisesRegex(ValueError, 'checksum'): self.package()

    def test_duplicate_build_manifests_are_rejected(self):
        r.shutil.copytree(self.build, self.root / 'build/firmware-r60abd1-esp32c3')
        with self.assertRaisesRegex(ValueError, 'Expected one manifest'): self.package()

    def test_build_action_hashes_validate_both_binary_kinds(self):
        build = self.manifest['builds'][0]
        build['parts'][0].update(md5=r.hashlib.md5(b'factory').hexdigest(), sha256=r.sha(b'factory'))
        build['ota']['sha256'] = r.sha(b'ota')
        r.write(self.build / 'manifest.json', self.manifest)
        self.package()
        build['ota']['sha256'] = '0' * 64
        r.write(self.build / 'manifest.json', self.manifest)
        with self.assertRaisesRegex(ValueError, 'checksum'): self.package()

    def test_legacy_corrupt_ota_fails_before_writing_alias(self):
        output = self.root / 'legacy-corrupt'
        responses = {'models.json': json.dumps([{'manifest': 'old/manifest.json'}]).encode(),
                     'old/manifest.json': json.dumps(self.manifest).encode(),
                     'old/factory.bin': b'factory', 'old/ota.bin': b'corrupt'}
        base = 'https://example.com/'
        with patch.object(r, 'urlopen', side_effect=lambda url, timeout: io.BytesIO(responses[url.removeprefix(base)])):
            with self.assertRaisesRegex(ValueError, 'checksum'): r.preserve_legacy(base, output)
        self.assertFalse((output / 'old/manifest.json').exists())

    def test_beta_preserves_every_tested_byte_and_source(self):
        alpha = self.package()
        beta = self.root / 'beta'
        r.promote(alpha, beta, 'v1.0.0-beta.1', 'R60ABD1 + C3: USB, HA, card walk test passed')
        self.assertEqual((alpha / 'firmware-bundle.zip').read_bytes(), (beta / 'firmware-bundle.zip').read_bytes())
        a, b = r.read(alpha / 'release.json'), r.read(beta / 'release.json')
        self.assertEqual(b['binaryVersion'], self.version)
        self.assertEqual(b['files'], a['files'])
        self.assertEqual(b['sourceCommit'], a['sourceCommit'])
        self.assertIn('/v1.0.0-beta.1/', b['firmware'][0]['manifest'])

    def test_promotion_rejects_missing_evidence_or_wrong_version(self):
        alpha = self.package()
        for version, evidence in [('v1.0.0-beta.1', ''), ('v2.0.0-beta.1', 'passed'), ('v1.0.0-alpha.2', 'passed')]:
            with self.subTest(version=version), self.assertRaises(ValueError): r.promote(alpha, self.root / 'bad', version, evidence)

    def test_corrupt_bundle_rejected(self):
        alpha = self.package()
        meta = r.read(alpha / 'release.json')
        with (alpha / 'firmware-bundle.zip').open('ab') as f: f.write(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'): r.validate_bundle(meta, alpha / 'firmware-bundle.zip')

    def test_path_traversal_rejected(self):
        for path in ('../a.bin', '/a.bin', 'https://x/a', 'a/./b', 'a//b', 'a\\b'):
            with self.subTest(path=path), self.assertRaises(ValueError): r.safe_path(path)

    def test_missing_ota_rejected(self):
        del self.manifest['builds'][0]['ota']
        r.write(self.build / 'manifest.json', self.manifest)
        with self.assertRaises(ValueError): self.package()

    def test_wrong_build_version_rejected(self):
        self.manifest['version'] = 'dev'
        r.write(self.build / 'manifest.json', self.manifest)
        with self.assertRaises(ValueError): self.package()

    def test_assemble_empty_history_keeps_legacy_only(self):
        output = self.root / 'site'
        output.mkdir()
        r.write(output / 'models.json', [{'id': 'old', 'manifest': 'old/manifest.json'}])
        with patch.object(r, 'gh', return_value='[]'), patch.object(r, 'preserve_legacy'):
            r.assemble('owner/repo', output, 'https://owner.github.io/repo/')
        self.assertEqual(r.read(output / 'releases.json')['releases'], [])
        self.assertEqual(r.read(output / 'models.json')[0]['id'], 'old')

    def test_stamp_changes_only_the_project_version(self):
        config = self.root / 'factory.yaml'
        config.write_text('esphome:\n  project:\n    version: dev # release\n', encoding='utf-8')
        with patch.object(r, 'ROOT', self.root):
            r.stamp('factory.yaml', self.version)
            self.assertIn(f'version: "{self.version}" # release', config.read_text())
            with self.assertRaises(ValueError): r.stamp('factory.yaml', self.version)
            with self.assertRaises(ValueError): r.stamp('factory.yaml', 'v1.0.0-beta.1')

    def test_beta_requires_acceptance_and_alpha_provenance(self):
        alpha = self.package()
        beta = self.root / 'beta'
        r.promote(alpha, beta, 'v1.0.0-beta.1', 'hardware passed')
        meta = r.read(beta / 'release.json')
        for field in ('promotedFrom', 'hardwareTestEvidence'):
            invalid = {**meta, field: ''}
            with self.subTest(field=field), self.assertRaises(ValueError):
                r.validate_bundle(invalid, beta / 'firmware-bundle.zip')

    def test_history_keeps_versions_and_only_latest_beta_updates_ota(self):
        alpha = self.package()
        beta1, beta2 = self.root / 'beta1', self.root / 'beta2'
        r.promote(alpha, beta1, 'v1.0.0-beta.1', 'hardware passed')
        self.manifest['version'] = 'v1.0.0-alpha.2'
        r.write(self.build / 'manifest.json', self.manifest)
        (self.build / 'factory.bin').write_bytes(b'tested-second-factory')
        second = self.root / 'second'
        r.package(self.root / 'build', second, 'v1.0.0-alpha.2', 'b' * 40, '2026.9.0')
        r.promote(second, beta2, 'v1.0.0-beta.2', 'second hardware passed')
        self.manifest['version'] = 'v1.0.0-alpha.3'
        r.write(self.build / 'manifest.json', self.manifest)
        (self.build / 'factory.bin').write_bytes(b'UNTESTED-third-factory')
        third = self.root / 'third'
        r.package(self.root / 'build', third, 'v1.0.0-alpha.3', 'c' * 40, '2026.9.0')
        bundles = {r.read(d / 'release.json')['version']: d for d in (beta1, beta2, third)}
        history = [{'tag_name': tag, 'draft': False, 'published_at': f'2026-10-{10 + i:02d}T10:00:00Z',
                    'assets': [{'name': n} for n in ('release.json', 'firmware-bundle.zip')]}
                   for i, tag in enumerate(bundles)]
        def download(repo, tag, dest):
            r.shutil.copytree(bundles[tag], dest)
            return r.validate_bundle(r.read(dest / 'release.json'), dest / 'firmware-bundle.zip')
        output = self.root / 'site'
        with patch.object(r, 'gh', return_value=json.dumps(history)), patch.object(r, 'download_release', side_effect=download):
            r.assemble('owner/repo', output, '')
        self.assertEqual(len(r.read(output / 'releases.json')['releases']), 3)
        self.assertEqual((output / 'r60abd1-ESP32-C3/factory.bin').read_bytes(), b'tested-second-factory')
        self.assertEqual(r.read(output / 'r60abd1-ESP32-C3/manifest.json')['version'], 'v1.0.0-alpha.2')
        self.assertTrue((output / 'firmware/v1.0.0-alpha.3/r60abd1-ESP32-C3/factory.bin').exists())

    def test_preserve_legacy_copies_factory_and_ota_without_classifying(self):
        base, output = 'https://owner.github.io/repo/', self.root / 'legacy'
        model = {'id': 'old', 'manifest': 'old/manifest.json'}
        responses = {'models.json': json.dumps([model]).encode(), 'old/manifest.json': json.dumps(self.manifest).encode(),
                     'old/factory.bin': b'factory', 'old/ota.bin': b'ota'}
        with patch.object(r, 'urlopen', side_effect=lambda url, timeout: io.BytesIO(responses[url.removeprefix(base)])):
            r.preserve_legacy(base, output)
        self.assertEqual((output / 'old/ota.bin').read_bytes(), b'ota')
        self.assertEqual(r.read(output / 'models.json'), [model])
        self.assertFalse((output / 'releases.json').exists())

    def test_legacy_errors_fail_closed_except_missing_index(self):
        for code in (403, 404, 500):
            with patch.object(r, 'urlopen', side_effect=HTTPError('https://example.com/models.json', code, 'test', {}, None)):
                if code == 404:
                    r.preserve_legacy('https://example.com/', self.root / 'empty')
                else:
                    with self.assertRaises(HTTPError): r.preserve_legacy('https://example.com/', self.root / 'empty')


if __name__ == '__main__':
    unittest.main()

"""No network, GitHub writes or hardware required."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

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

    def test_single_download_artifact_at_root_uses_project_identity(self):
        flat = self.root / 'flat'
        r.shutil.copytree(self.build, flat)
        manifest = {**self.manifest, 'name': 'mmwave.r60abd1'}
        r.write(flat / 'manifest.json', manifest)
        dest = self.root / 'flat-release'
        r.package(flat, dest, self.version, 'a' * 40, '2026.9.1')
        r.validate_bundle(r.read(dest / 'release.json'), dest / 'firmware-bundle.zip')
        with zipfile.ZipFile(dest / 'firmware-bundle.zip') as bundle:
            self.assertEqual(bundle.read('r60abd1-ESP32-C3/factory.bin'), b'factory')
        # A root manifest must never satisfy a different model's lookup.
        with self.assertRaisesRegex(ValueError, 'Expected one manifest'):
            r.find_build_manifest(flat, 'ld2450')
        for name in ('mmwave.ld2450', 'R60ABD1', ''):
            r.write(flat / 'manifest.json', {**manifest, 'name': name})
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Expected one manifest'):
                r.package(flat, self.root / 'bad-flat', self.version, 'a' * 40, '2026.9.1')

    def test_flat_and_nested_duplicate_is_ambiguous(self):
        r.write(self.root / 'build/manifest.json', {**self.manifest, 'name': 'mmwave.r60abd1'})
        with self.assertRaisesRegex(ValueError, 'Expected one manifest'):
            self.package()

    def test_flat_artifact_still_checks_ota_bytes(self):
        flat = self.root / 'flat'
        r.shutil.copytree(self.build, flat)
        r.write(flat / 'manifest.json', {**self.manifest, 'name': 'mmwave.r60abd1'})
        (flat / 'ota.bin').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            r.package(flat, self.root / 'bad-flat', self.version, 'a' * 40, '2026.9.1')

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




    def test_stamp_updates_project_version_and_release_channel(self):
        config = self.root / 'factory.yaml'
        config.write_text('esphome:\n  project:\n    version: dev # release\n\nmmwave_host:\n  release_channel: dev\n', encoding='utf-8')
        with patch.object(r, 'ROOT', self.root):
            r.stamp('factory.yaml', self.version)
            content = config.read_text()
            self.assertIn(f'version: "{self.version}" # release', content)
            self.assertIn('release_channel: alpha', content)
            self.assertNotIn('release_channel: dev', content)
            # Re-stamping already stamped config must fail
            with self.assertRaises(ValueError): r.stamp('factory.yaml', self.version)
            # Stamping with beta tag must fail
            with self.assertRaises(ValueError): r.stamp('factory.yaml', 'v1.0.0-beta.1')
            # Stamping with nightly or invalid tag must fail
            with self.assertRaises(ValueError): r.stamp('factory.yaml', 'v1.0.0-nightly.1')


    def test_stamp_rejects_host_without_a_dev_channel_placeholder(self):
        # A factory without mmwave_host is covered by the version-only test;
        # both host variants here must be refused instead of guessing.
        for suffix in ('mmwave_host:\n  id: host_link\n', 'mmwave_host:\n  release_channel: beta\n'):
            config = self.root / 'host.yaml'
            original = 'esphome:\n  project:\n    version: dev\n' + suffix
            config.write_text(original, encoding='utf-8')
            with self.subTest(suffix=suffix.splitlines()[-1:]):
                with patch.object(r, 'ROOT', self.root), self.assertRaises(ValueError):
                    r.stamp('host.yaml', self.version)
                self.assertEqual(config.read_text(encoding='utf-8'), original,
                                 'a refused stamp must keep the file byte-identical')

    def test_stamp_leaves_factories_without_mmwave_host_alone(self):
        config = self.root / 'plain.yaml'
        config.write_text('esphome:\n  project:\n    version: dev\n', encoding='utf-8')
        with patch.object(r, 'ROOT', self.root):
            r.stamp('plain.yaml', self.version)
        self.assertEqual(
            config.read_text(encoding='utf-8'),
            'esphome:\n  project:\n    version: "v1.0.0-alpha.1"\n',
            'a non-MWCP factory only takes the project version, no host block',
        )

    def test_beta_requires_acceptance_and_alpha_provenance(self):
        alpha = self.package()
        beta = self.root / 'beta'
        r.promote(alpha, beta, 'v1.0.0-beta.1', 'hardware passed')
        meta = r.read(beta / 'release.json')
        for field in ('promotedFrom', 'hardwareTestEvidence'):
            invalid = {**meta, field: ''}
            with self.subTest(field=field), self.assertRaises(ValueError):
                r.validate_bundle(invalid, beta / 'firmware-bundle.zip')



if __name__ == '__main__':
    unittest.main()

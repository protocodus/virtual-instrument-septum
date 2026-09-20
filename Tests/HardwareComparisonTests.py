#!/usr/bin/env python3
"""Audio and frozen-renderer integrity for the optional hardware benchmark."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

if any(importlib.util.find_spec(name) is None for name in ('numpy', 'scipy', 'matplotlib')):
    print('Hardware comparison tests skipped: install Tools/requirements-hardware.txt')
    raise SystemExit(77)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))
import compare_hardware as comparison
import numpy as np


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.rate = 44100
        t = np.arange(self.rate) / self.rate
        self.audio = np.repeat((0.1 * np.sin(2 * np.pi * 440 * t))[:, None], 2, axis=1)

    def test_invalid_audio_cannot_publish_misleading_metrics_or_listening_copy(self):
        invalid = [np.empty((0, 2)), np.zeros((100, 2)), np.ones((100, 1)),
                   np.ones(100), np.ones((100, 2), dtype=np.int16)]
        for value in (np.nan, np.inf, -np.inf):
            y = self.audio.copy()
            y[10, 1] = value
            invalid.append(y)
        for audio in invalid:
            with self.subTest(shape=audio.shape):
                for operation in (lambda: comparison.audio_stats(audio, self.rate),
                                  lambda: comparison.listening_copy(audio)):
                    with self.assertRaises(ValueError):
                        operation()

    def test_known_tone_has_expected_centroid_level_and_scalar_only_matching(self):
        stats = comparison.audio_stats(self.audio, self.rate)
        self.assertAlmostEqual(stats['power_spectral_centroid_20_16000_hz'], 440, places=3)
        self.assertAlmostEqual(stats['rms_dbfs'], -23.0102999566, places=8)
        self.assertTrue(stats['identical_stereo_channels'])
        self.assertIsNone(stats['side_to_mid_db'])
        matched, gain = comparison.listening_copy(self.audio)
        np.testing.assert_array_equal(matched, self.audio * gain)
        self.assertAlmostEqual(np.sqrt(np.mean(matched ** 2)), 0.1, places=12)
        matched_stats = comparison.audio_stats(matched, self.rate)
        self.assertAlmostEqual(matched_stats['power_spectral_centroid_20_16000_hz'],
                               stats['power_spectral_centroid_20_16000_hz'], places=10)

    def test_stereo_antiphase_is_measured_without_mono_cancellation(self):
        self.audio[:, 1] *= -1
        stats = comparison.audio_stats(self.audio, self.rate)
        self.assertAlmostEqual(stats['power_spectral_centroid_20_16000_hz'], 440, places=3)
        self.assertFalse(stats['identical_stereo_channels'])


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='septum-comparison-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.renderer = self.root / 'SeptumRenderMidi'
        self.renderer.write_bytes(b'binary identity fixture')
        self.manifest_path = self.root / 'manifest.json'
        inputs = {'Source/DSP/SeptumEngine.cpp': b'// frozen engine\n',
                  'Tools/RenderMidi.cpp': b'// adapted renderer\n',
                  'original/Tools/RenderMidi.cpp': b'// original renderer\n',
                  'CandidateProfile.h': b'// generated profile\n',
                  'profile.original.json': b'{"id":"diagnostic"}',
                  'profile.json': b'{"id": "diagnostic"}\n'}
        for name, data in inputs.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        frozen = {name: hashlib.sha256(data).hexdigest() for name, data in inputs.items()}
        self.manifest = {
            'version': 1, 'id': 'diagnostic', 'status': 'complete', 'experimental': True,
            'hardware_match_claim': False, 'frozen_inputs_verified': True,
            'renderer': {'path': self.renderer.name, 'sha256': comparison.digest(self.renderer)},
            'profile': {'canonical_sha256': frozen['profile.json'],
                        'original_sha256': frozen['profile.original.json']},
            'frozen_sha256': frozen,
        }

    def save(self, manifest=None):
        self.manifest_path.write_text(json.dumps(self.manifest if manifest is None else manifest))

    def test_arbitrary_renderer_is_identified_without_claiming_live_sources_built_it(self):
        result = comparison.renderer_provenance(self.renderer)
        self.assertEqual(result['sha256'], comparison.digest(self.renderer))
        self.assertFalse(result['build_sources_verified'])
        self.save({'unrelated': 'audio artifact manifest'})
        self.assertFalse(comparison.renderer_provenance(self.renderer)['build_sources_verified'])

    def test_complete_candidate_retains_exact_manifest_and_binary_identity(self):
        self.save()
        result = comparison.renderer_provenance(self.renderer)
        self.assertTrue(result['build_sources_verified'])
        self.assertEqual(result['build_manifest'], self.manifest)
        self.assertEqual(result['build_manifest_sha256'], comparison.digest(self.manifest_path))
        self.assertEqual(result['sha256'], comparison.digest(self.renderer))
        self.assertIn('No hardware-match claim', result['qualification'])

    def test_rebuilt_binary_is_rejected_even_with_unchanged_frozen_source_files(self):
        self.save()
        self.renderer.write_bytes(b'a different renderer')
        with self.assertRaisesRegex(ValueError, 'renderer'):
            comparison.renderer_provenance(self.renderer)

    def test_each_frozen_input_must_still_match_the_build(self):
        self.save()
        for name in self.manifest['frozen_sha256']:
            path = self.root / name
            original = path.read_bytes()
            path.write_bytes(original + b'tampered')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'frozen input'):
                comparison.renderer_provenance(self.renderer)
            path.write_bytes(original)
        (self.root / 'CandidateProfile.h').unlink()
        with self.assertRaisesRegex(ValueError, 'frozen input'):
            comparison.renderer_provenance(self.renderer)

    def test_incomplete_or_failed_candidate_build_cannot_be_used(self):
        variants = [{'status': 'failed'}, {'frozen_inputs_verified': False},
                    {'experimental': False}, {'hardware_match_claim': True},
                    {'frozen_sha256': {}}, {'profile': {'canonical_sha256': 'incorrect'}}]
        for replacement in variants:
            self.save({**self.manifest, **replacement})
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                comparison.renderer_provenance(self.renderer)

    def test_manifest_cannot_verify_paths_outside_its_frozen_directory(self):
        for name in ('../outside.cpp', str(self.root / 'CandidateProfile.h')):
            manifest = deepcopy(self.manifest)
            manifest['frozen_sha256'][name] = self.manifest['frozen_sha256']['CandidateProfile.h']
            self.save(manifest)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'frozen input'):
                comparison.renderer_provenance(self.renderer)

    def test_comparison_page_keeps_reconstructed_midi_qualification(self):
        result = {'case': {'id': 'test-case', 'title': 'Fixture', 'duration_seconds': 1,
                           'midi_status': 'reconstructed_not_original', 'uncertainties': ['Unknown velocity']},
                  'reference': {'source_page_url': 'https://example.com/reference'}}
        comparison.write_html([result], self.root)
        page = (self.root / 'index.html').read_text()
        self.assertIn('Exact original MIDI files: 0', page)
        self.assertIn('ESTIMATED', page)
        result['case']['midi_status'] = 'verified_original'
        with self.assertRaises(ValueError):
            comparison.write_html([result], self.root)

    def test_author_video_requires_observed_labels_and_matching_audio_source(self):
        reference = {'association_status': 'named_patch_in_author_video',
                     'patch_number': 2,
                     'url': 'https://example.com/video',
                     'association_evidence': {
                         'video_url': 'https://example.com/video',
                         'author_page_links_bank_and_video': True,
                         'accepted_excerpt_bounds_seconds': [20, 30],
                         'label_observations': [{'seconds': 20, 'patch_number': 2,
                                                'visible_patch_label': 'A02 Moog BASS PW'},
                                                {'seconds': 30, 'patch_number': 2,
                                                 'visible_patch_label': 'A02 Moog BASS PW'}]}}
        comparison.validate_association(reference)
        comparison.validate_association(reference, 21, 5)
        for start, duration in ((0, 5), (29, 2), (21, -1), (float('nan'), 1),
                                (21, float('inf')), (None, 1)):
            with self.subTest(start=start), self.assertRaisesRegex(ValueError, 'passage'):
                comparison.validate_association(reference, start, duration)
        for replacement in ({'video_url': 'https://example.com/other'},
                            {'author_page_links_bank_and_video': False},
                            {'author_page_links_bank_and_video': 'false'},
                            {'accepted_excerpt_bounds_seconds': [30, 20]},
                            {'label_observations': []},
                            {'label_observations': [{'seconds': float('nan'),
                                                    'visible_patch_label': 'A02'}]}):
            invalid = deepcopy(reference)
            invalid['association_evidence'].update(replacement)
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                comparison.validate_association(invalid)

    def test_author_passage_must_be_bracketed_by_observations_of_that_patch(self):
        catalog = json.loads((ROOT / 'Docs/fidelity/rcs-reference-catalog.json').read_text())
        reference = deepcopy(catalog['recordings'][1])
        comparison.validate_association(reference, 20, 10)
        for bounds in ([19, 30], [20, 31]):
            invalid = deepcopy(reference)
            invalid['association_evidence']['accepted_excerpt_bounds_seconds'] = bounds
            with self.subTest(bounds=bounds), self.assertRaisesRegex(ValueError, 'between observations'):
                comparison.validate_association(invalid, bounds[0], 1)
        for observations in (
                [reference['association_evidence']['label_observations'][0]],
                [{'seconds': 20, 'patch_number': 1, 'visible_patch_label': 'PATCH: A01 MOOG BASS'},
                 {'seconds': 30, 'patch_number': 1, 'visible_patch_label': 'PATCH: A01 MOOG BASS'}],
                [{'seconds': 20, 'patch_number': 2, 'visible_patch_label': 'PATCH: A02 MOOG BASS PW'}] * 2):
            invalid = deepcopy(reference)
            invalid['association_evidence']['label_observations'] = observations
            with self.subTest(observations=observations), self.assertRaises(ValueError):
                comparison.validate_association(invalid)

    def test_catalog_sources_and_bank_members_match_acquired_evidence(self):
        catalog = json.loads((ROOT / 'Docs/fidelity/rcs-reference-catalog.json').read_text())
        audit = json.loads((ROOT / 'Docs/fidelity/source-audits/rcs-reference-screen-2026-09-20.json').read_text())
        source = next(row for row in audit['audio_acquisition']['recordings'] if row['platform'] == 'youtube')
        for reference in catalog['recordings']:
            comparison.validate_association(reference)
            self.assertEqual(reference['sha256'], source['source_sha256'])
            self.assertEqual(reference['size_bytes'], source['source_bytes'])
            self.assertEqual(reference['url'], source['canonical_url'])
            self.assertEqual(reference['patch_name'], audit['patches'][reference['patch_number'] - 1]['patch_name'])
        bank = catalog['banks'][0]
        self.assertEqual(bank['sha256'], audit['sources']['archive']['sha256'])
        self.assertEqual(bank['bank_sha256'], audit['sources']['bank_sha256'])
        self.assertEqual(bank['archive_member'], audit['sources']['bank_member'])

    def test_audio_similarity_and_montages_cannot_establish_patch_identity(self):
        for status in ('category_montage', 'inferred_by_audio_similarity', None):
            with self.subTest(status=status), self.assertRaises(ValueError):
                comparison.validate_association({'association_status': status})
        comparison.validate_association({'association_status': 'named_patch_on_official_page'})


if __name__ == '__main__':
    unittest.main()

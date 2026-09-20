#!/usr/bin/env python3
"""Independent scoring and provenance checks for hardware candidate matrices."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

if any(importlib.util.find_spec(name) is None for name in ('numpy', 'scipy', 'matplotlib')):
    print('Timbre matrix tests skipped: install Tools/requirements-hardware.txt')
    raise SystemExit(77)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))
import evaluate_timbre_matrix as matrix
import numpy as np
from scipy.io import wavfile


RATE = 44100


def tone(overtone=0.1, gain=1.0):
    t = np.arange(RATE) / RATE
    signal = gain * (0.2 * np.sin(2 * np.pi * 220 * t)
                     + overtone * np.sin(2 * np.pi * 2200 * t))
    return np.repeat(signal[:, None], 2, axis=1).astype(np.float32)


def save_row(root, row):
    (root / row['case']['id'] / 'comparison.json').write_text(json.dumps(row))
    (root / 'summary.json').write_text(json.dumps([row]))


def make_run(root, audio):
    directory = root / 'test-case'
    directory.mkdir(parents=True)
    wavfile.write(directory / 'hardware-excerpt-raw.wav', RATE, tone())
    wavfile.write(directory / 'septum-raw.wav', RATE, audio)
    (directory / 'original-patch.syx').write_bytes(b'unchanged preset fixture')
    (directory / 'reconstructed-performance.mid').write_bytes(b'estimated MIDI fixture')
    hashes = {p.name: matrix.sha(p) for p in directory.iterdir()}
    renderer_hash = '1' * 64
    render = {'inputs': {'renderer': {'sha256': renderer_hash},
                         'midi': {'sha256': hashes['reconstructed-performance.mid']},
                         'sysex': {'sha256': hashes['original-patch.syx']}},
              'output': {'sha256': hashes['septum-raw.wav'], 'latency_samples': 93},
              'degraded_replay': False,
              'settings': {'sample_rate': RATE, 'master_level': 100,
                           'tempo_policy': 'preserve-patch', 'midi_channel': 1}}
    (directory / 'septum-raw.render.json').write_text(json.dumps(render))
    hashes['septum-raw.render.json'] = matrix.sha(directory / 'septum-raw.render.json')
    row = {'case': {'id': 'test-case', 'title': 'Fixture', 'midi_status': 'reconstructed_not_original'},
           'reference': {'source_page_url': 'https://example.com/recording'},
           'bank': {'sha256': 'bank identity fixture'}, 'hardware_start_sample': 0,
           'comparison_frames': RATE, 'retained_engine_latency_samples': 93,
           'qualification': 'Published preset; reconstructed MIDI; recorded revision unknown',
           'files': hashes,
           'renderer_provenance': {'build_sources_verified': True, 'sha256': renderer_hash,
                                   'build_manifest_sha256': '2' * 64,
                                   'build_manifest': {'status': 'complete', 'experimental': True,
                                                      'hardware_match_claim': False,
                                                      'frozen_inputs_verified': True,
                                                      'renderer': {'sha256': renderer_hash}}}}
    save_row(root, row)
    return row


class ScoreTests(unittest.TestCase):
    def test_band_shape_preserves_gain_and_stereo_polarity_invariance(self):
        audio = tone().astype(np.float64)
        shape = matrix.band_shape(audio, RATE)
        self.assertAlmostEqual(shape.sum(), 1.0)
        for gain in (1e-6, 10):
            np.testing.assert_allclose(shape, matrix.band_shape(audio * gain, RATE), atol=1e-12)
        audio[:, 1] *= -1
        np.testing.assert_allclose(shape, matrix.band_shape(audio, RATE), atol=1e-12)

    def test_known_band_ratios_give_the_expected_decibel_residual(self):
        reference = np.array([0.9, 0.1] + [0.0] * 30)
        candidate = np.array([0.1, 0.9] + [0.0] * 30)
        score = matrix.spectral_residual(reference, candidate)
        self.assertEqual(score['included_band_count'], 2)
        self.assertAlmostEqual(score['band_shape_rmse_db'], 10 * np.log10(9))
        self.assertAlmostEqual(matrix.spectral_residual(reference, reference)['band_shape_rmse_db'], 0)

    def test_reference_alone_selects_scored_bands(self):
        reference = np.array([1., 1e-5, 0.9e-5] + [0.] * 29)
        candidate = np.ones(32) / 32
        score = matrix.spectral_residual(reference, candidate)
        self.assertEqual(score['included_bands'], [True, True] + [False] * 30)

    def test_silent_nonfinite_and_mono_audio_are_rejected(self):
        for audio in (np.zeros((RATE, 2)), np.full((RATE, 2), np.nan), np.ones(RATE)):
            with self.assertRaises(ValueError):
                matrix.band_shape(audio, RATE)


class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='septum-matrix-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.baseline, self.candidate, self.output = [self.root / name for name in ('base', 'trial', 'matrix')]
        self.base_row = make_run(self.baseline, tone(0.2))
        self.trial_row = make_run(self.candidate, tone(0.2))

    def evaluate(self):
        return matrix.evaluate(self.baseline, self.candidate, self.output)

    def change_render(self, change):
        path = self.candidate / 'test-case' / 'septum-raw.render.json'
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value))
        self.trial_row['files'][path.name] = matrix.sha(path)
        save_row(self.candidate, self.trial_row)

    def test_identity_control_emits_identical_baseline_candidate_audio_and_zero_delta(self):
        report = self.evaluate()
        row = report['cases'][0]
        self.assertTrue(row['raw_render_identical'])
        self.assertEqual(row['delta_rmse_db'], 0)
        self.assertEqual(row['listening_sha256']['baseline.wav'], row['listening_sha256']['candidate.wav'])
        self.assertEqual(report['models']['baseline'], self.base_row['renderer_provenance'])
        self.assertFalse(report['hardware_match_claim'])
        for name in ('hardware', 'baseline', 'candidate'):
            rate, audio = wavfile.read(self.output / 'test-case' / (name + '.wav'))
            self.assertEqual(rate, RATE)
            self.assertTrue(np.isfinite(audio).all())
            self.assertLessEqual(np.max(np.abs(audio)), 0.950001)
            self.assertAlmostEqual(float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))), .1, places=7)
        page = (self.output / 'index.html').read_text()
        self.assertIn('no original performance MIDI', page)
        self.assertIn('exact recorded revision is unverified', page)
        with self.assertRaisesRegex(ValueError, 'Output exists'):
            self.evaluate()

    def test_identical_hardware_candidate_improves_the_broad_spectral_residual(self):
        candidate = self.root / 'closer'
        make_run(candidate, tone())
        report = matrix.evaluate(self.baseline, candidate, self.output)
        row = report['cases'][0]
        self.assertGreater(row['before']['band_shape_rmse_db'], 0)
        self.assertEqual(row['candidate']['band_shape_rmse_db'], 0)
        self.assertLess(row['delta_rmse_db'], 0)

    def test_summary_cannot_diverge_from_the_cited_per_case_provenance(self):
        self.trial_row['case']['title'] = 'changed summary only'
        (self.candidate / 'summary.json').write_text(json.dumps([self.trial_row]))
        with self.assertRaisesRegex(ValueError, 'Summary disagrees'):
            self.evaluate()
        self.assertFalse(self.output.exists())

    def test_tampered_audio_is_rejected_before_creating_output(self):
        wavfile.write(self.candidate / 'test-case/septum-raw.wav', RATE, tone(.3))
        with self.assertRaisesRegex(ValueError, 'artifact hash mismatch'):
            self.evaluate()
        self.assertFalse(self.output.exists())

    def test_different_performance_or_preset_is_not_a_model_comparison(self):
        self.trial_row['case']['note'] = 72
        save_row(self.candidate, self.trial_row)
        with self.assertRaisesRegex(ValueError, 'Comparison input mismatch'):
            self.evaluate()

    def test_master_level_and_other_replay_settings_must_match(self):
        self.change_render(lambda render: render['settings'].update(master_level=90))
        with self.assertRaisesRegex(ValueError, 'render settings differ'):
            self.evaluate()

    def test_pcm_rate_must_match_manifest_not_just_the_other_pcm(self):
        for root, row in ((self.baseline, self.base_row), (self.candidate, self.trial_row)):
            path = root / 'test-case/septum-raw.render.json'
            render = json.loads(path.read_text())
            render['settings']['sample_rate'] = 48000
            path.write_text(json.dumps(render))
            row['files'][path.name] = matrix.sha(path)
            save_row(root, row)
        with self.assertRaisesRegex(ValueError, 'sample rate disagrees'):
            self.evaluate()

    def test_renderer_identity_and_undegraded_replay_are_required(self):
        for change in (lambda render: render.update(degraded_replay=True),
                       lambda render: render['inputs']['renderer'].update(sha256='wrong')):
            self.change_render(lambda render: (render.update(degraded_replay=False),
                                                render['inputs']['renderer'].update(sha256='1' * 64)))
            self.change_render(change)
            with self.assertRaisesRegex(ValueError, 'Render identity'):
                self.evaluate()

    def test_path_escape_and_false_original_midi_claim_are_rejected(self):
        self.trial_row['case']['midi_status'] = 'original'
        save_row(self.candidate, self.trial_row)
        with self.assertRaisesRegex(ValueError, 'explicitly reconstructed'):
            self.evaluate()
        self.trial_row['case']['midi_status'] = 'reconstructed_not_original'
        self.trial_row['files']['../outside.wav'] = 'incorrect'
        save_row(self.candidate, self.trial_row)
        with self.assertRaisesRegex(ValueError, 'artifact filename'):
            self.evaluate()


if __name__ == '__main__':
    unittest.main()

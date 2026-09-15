#!/usr/bin/env python3
"""Adversarial tests for audio measurements and the evidence gate (NumPy/SciPy)."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))
import assess_hardware_equivalence as assess


class HardwareEquivalenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="septum-equivalence-")
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)
        self.sr = 16000
        self.t = np.arange(self.sr * 2) / self.sr
        envelope = .05 + .7 * np.exp(-((self.t - .2) / .04) ** 2)
        envelope += .4 * np.exp(-((self.t - .65) / .12) ** 2)
        envelope += .6 * np.exp(-((self.t - 1.4) / .15) ** 2)
        self.mono = envelope * np.sin(2 * np.pi * 220 * self.t)
        self.audio = np.column_stack((self.mono, self.mono))

    def write(self, name, audio):
        path = self.path / name
        wavfile.write(path, self.sr, audio.astype(np.float32))
        return path

    def pair(self, reference, candidate, **kwargs):
        return assess.evaluate(self.write("reference.wav", reference),
                               self.write("candidate.wav", candidate), **kwargs)

    def test_identical_audio_is_zero_distance_but_not_proof(self):
        result = self.pair(self.audio, self.audio)
        self.assertEqual(result["acceptance_gate"]["status"], "not_established")
        self.assertIsNone(result["acceptance_gate"]["within_registered_bounds"])
        for value in result["calibrated_measurements"]["summary"].values():
            self.assertEqual(value, 0)
        self.assertFalse(result["calibration"]["separate_prefix"])

    def test_different_harmonics_with_same_rms_and_centroid_do_not_match(self):
        a = (np.sin(2 * np.pi * 220 * self.t) + np.sin(2 * np.pi * 880 * self.t)) / 2
        b = np.sin(2 * np.pi * 550 * self.t) / np.sqrt(2)
        result = self.pair(np.column_stack((a, a)), np.column_stack((b, b)))
        metrics = result["calibrated_measurements"]["summary"]
        self.assertGreater(metrics["spectral_convergence_mean"], 1.0)
        self.assertGreater(metrics["log_spectral_error_db_mean"], 20)

    def test_same_long_term_spectrum_with_reordered_notes_is_detected(self):
        a = np.concatenate((np.sin(2 * np.pi * 220 * self.t[:self.sr]),
                            np.sin(2 * np.pi * 440 * self.t[:self.sr])))
        b = np.concatenate((a[self.sr:], a[:self.sr]))
        self.assertAlmostEqual(assess.rms(a), assess.rms(b), places=12)
        self.assertGreater(assess.measure(a[:, None], b[:, None], self.sr)
                           ["summary"]["spectral_convergence_mean"], 1)

    def test_global_gain_and_delay_fit_only_prefix(self):
        delay = 137
        shifted = np.concatenate((np.zeros((delay, 2)), self.audio[:-delay])) / 3
        result = self.pair(self.audio, shifted, calibration_seconds=.9, max_lag_seconds=.02)
        self.assertEqual(result["calibration"]["candidate_lag_samples"], delay)
        self.assertAlmostEqual(result["calibration"]["candidate_gain"], 3, places=6)
        self.assertLess(result["calibrated_measurements"]["summary"]["spectral_convergence_mean"], 1e-6)
        self.assertGreater(result["raw_measurements"]["summary"]["spectral_convergence_mean"], .5)
        shifted[self.sr:] *= .5
        changed = self.pair(self.audio, shifted, calibration_seconds=.9, max_lag_seconds=.02)
        self.assertEqual(changed["calibration"], result["calibration"])
        self.assertGreater(changed["calibrated_measurements"]["summary"]["envelope_error_db_p95_max"], 5)

    def test_late_attack_does_not_align_to_numerical_noise_in_silence(self):
        # Most of this prefix precedes the first note. FFT correlation error
        # must not beat the real attack when divided by near-zero variance.
        sr = 44100
        t = np.arange(sr) / sr
        envelope = np.where(t >= .320,
                            .5 * (1 - np.exp(-np.maximum(t - .320, 0) / .01)), 0)
        wave = envelope * (np.sin(2 * np.pi * 130.81 * t)
                           + .25 * np.sin(2 * np.pi * 261.62 * t))
        reference = np.column_stack((wave, wave))
        for delay in (-137, 0, 132, 441):
            candidate = np.zeros_like(reference)
            if delay < 0:
                candidate[:delay] = reference[-delay:]
            elif delay > 0:
                candidate[delay:] = reference[:-delay]
            else:
                candidate[:] = reference
            quiet = round(.310 * sr)
            candidate[:quiet] += 1e-18 * np.sin(2 * np.pi * 37 * t[:quiet, None])
            for scale in (.001, 1, 1000):
                with self.subTest(delay=delay, scale=scale):
                    result = assess.fit_transform(reference, candidate * scale,
                                                  sr, round(.4 * sr), .05)
                    self.assertEqual(result["candidate_lag_samples"], delay)
                    self.assertAlmostEqual(result["candidate_gain"] * scale, 1, places=10)
                    self.assertGreater(result["alignment_correlation"], .999999)

    def test_constant_candidate_prefix_does_not_identify_a_delay(self):
        result = assess.fit_transform(self.audio, np.full_like(self.audio, .2),
                                      self.sr, round(.9 * self.sr), .02)
        self.assertFalse(result["alignment_identifiable"])
        self.assertEqual(result["candidate_lag_samples"], 0)
        self.assertIsNone(result["alignment_correlation"])

    def test_stereo_phase_collapse_is_detected_without_requiring_waveform_null(self):
        anti = self.audio.copy()
        anti[:, 1] *= -1
        result = self.pair(self.audio, anti)
        metrics = result["calibrated_measurements"]
        self.assertEqual(metrics["summary"]["spectral_convergence_mean"], 0)
        self.assertEqual(metrics["summary"]["stereo_side_fraction_error"], 1)
        self.assertFalse(metrics["waveform_diagnostic"]["used_for_bounds"])

    def test_silence_and_invalid_audio_do_not_score_as_equivalent(self):
        with self.assertRaisesRegex(ValueError, "Silent"):
            self.pair(np.zeros_like(self.audio), np.zeros_like(self.audio))
        broken = self.audio.copy()
        broken[0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "Nonfinite"):
            self.pair(self.audio, broken)
        with self.assertRaisesRegex(ValueError, "Channel layouts"):
            self.pair(self.audio, self.mono)
        with self.assertRaisesRegex(ValueError, "lengths differ"):
            self.pair(self.audio, self.audio[:-1])
        with self.assertRaisesRegex(ValueError, "Lag fitting requires"):
            self.pair(self.audio, self.audio, max_lag_seconds=.02)

    def test_manifest_frames_and_audio_hashes_are_enforced(self):
        reference = self.write("hardware-excerpt-raw.wav", self.audio)
        candidate = self.write("septum-raw.wav", np.concatenate((self.audio, self.audio)))
        manifest = {"comparison_frames": len(self.audio),
                    "files": {reference.name: assess.digest(reference), candidate.name: assess.digest(candidate)},
                    "qualification": "same published preset; reconstructed MIDI",
                    "case": {"midi_status": "reconstructed_not_original"},
                    "comparison_limits": ["Unknown original velocity"]}
        path = self.path / "comparison.json"
        path.write_text(json.dumps(manifest))
        result = assess.evaluate(reference, candidate, comparison_path=path)
        self.assertEqual(result["qualification"]["midi_status"], "reconstructed_not_original")
        self.assertEqual(result["acceptance_gate"]["status"], "not_established")
        self.assertEqual(result["calibrated_measurements"]["summary"]["spectral_convergence_mean"], 0)
        self.write(candidate.name, self.audio * .5)
        with self.assertRaisesRegex(ValueError, "manifest"):
            assess.evaluate(reference, candidate, comparison_path=path)

    def test_unjustified_loose_margins_cannot_pass_gate(self):
        protocol = {"schema_version": 1, "maximum_errors": {key: 1e6 for key in assess.REQUIRED_BOUNDS}}
        path = self.path / "protocol.json"
        path.write_text(json.dumps(protocol))
        result = self.pair(self.audio, self.audio, calibration_seconds=.9, protocol_path=path)
        self.assertTrue(result["acceptance_gate"]["within_registered_bounds"])
        self.assertEqual(result["acceptance_gate"]["status"], "not_established")
        self.assertIn("Missing hardware_repeatability_evidence", result["acceptance_gate"]["reasons"])

    def test_registered_gate_checks_all_metrics_and_binds_evaluation_identity(self):
        initial = self.pair(self.audio, self.audio, calibration_seconds=.9)
        evidence = self.path / "synthetic-test-evidence.txt"
        evidence.write_text("Synthetic unit-test fixture only; not hardware or perceptual evidence.")
        protocol = {"schema_version": 1, "scope": "Synthetic software test",
                    "margin_justification": "Zero margin tests gate mechanics, not perception",
                    "public_input_uncertainty_assessment": "Synthetic inputs",
                    "registered_before_evaluation": True, "evaluation_not_used_for_dsp_tuning": True,
                    "evaluation": initial["evaluation_identity"],
                    "maximum_errors": {key: 0 for key in assess.REQUIRED_BOUNDS}}
        for field in ("hardware_repeatability_evidence", "perceptual_validation_evidence", "registration_evidence"):
            protocol[field] = [{"path": evidence.name, "sha256": assess.digest(evidence)}]
        path = self.path / "protocol.json"
        path.write_text(json.dumps(protocol))
        good = self.pair(self.audio, self.audio, calibration_seconds=.9, protocol_path=path)
        self.assertEqual(good["acceptance_gate"]["status"], "within_registered_bounds")
        bad_audio = self.audio.copy()
        bad_audio[self.sr:] *= .5
        bad = self.pair(self.audio, bad_audio, calibration_seconds=.9, protocol_path=path)
        self.assertEqual(bad["acceptance_gate"]["status"], "outside_registered_bounds")
        self.assertTrue(any(not c["within_bound"] for c in bad["acceptance_gate"]["checks"].values()))
        changed_split = self.pair(self.audio, self.audio, calibration_seconds=.8, protocol_path=path)
        self.assertEqual(changed_split["acceptance_gate"]["status"], "not_established")
        evidence.write_text("Modified evidence")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.pair(self.audio, self.audio, calibration_seconds=.9, protocol_path=path)

    def test_pcm_integer_conversion_and_stereo_balance(self):
        path = self.path / "integer.wav"
        wavfile.write(path, self.sr, np.round(self.audio * 32767).astype(np.int16))
        sr, audio = assess.read_audio(path)
        self.assertEqual(sr, self.sr)
        self.assertLess(np.max(abs(audio - self.audio)), 5e-5)
        b = self.audio.copy()
        b[:, 1] *= .5
        measured = assess.measure(self.audio, b, self.sr)
        self.assertAlmostEqual(measured["summary"]["stereo_balance_error_db"], 6.020599913, places=7)

    def test_original_midi_does_not_upgrade_documented_recipe_to_exact_patch(self):
        midi, recipe = self.path / "original.mid", self.path / "recipe.txt"
        midi.write_bytes(b"synthetic test artifact")
        recipe.write_text("Synthetic recipe: saw oscillator, lowpass filter")
        provenance = {"schema_version": 1, "source_url": "https://example.invalid/synthetic-fixture",
                      "midi": {"status": "original_performance", "artifact": {"path": midi.name, "sha256": assess.digest(midi)}},
                      "preset": {"status": "documented_recipe_reconstruction", "artifact": {"path": recipe.name, "sha256": assess.digest(recipe)}},
                      "uncertainties": ["No recording-specific SysEx dump"]}
        path = self.path / "provenance.json"
        path.write_text(json.dumps(provenance))
        result = self.pair(self.audio, self.audio, provenance_path=path)
        inputs = result["qualification"]["inputs"]
        self.assertEqual(inputs["midi"]["status"], "original_performance")
        self.assertEqual(inputs["preset"]["status"], "documented_recipe_reconstruction")
        self.assertEqual(result["acceptance_gate"]["status"], "not_established")

    def test_uniform_fraction_split_and_invalid_split(self):
        result = self.pair(self.audio, self.audio, calibration_fraction=.25)
        self.assertEqual(result["calibration"]["calibration_frames"], self.sr // 2)
        self.assertEqual(result["audio"]["evaluation_reference_start_sample"], self.sr // 2)
        for fraction in (0, 1, float("nan")):
            with self.assertRaisesRegex(ValueError, "fraction"):
                self.pair(self.audio, self.audio, calibration_fraction=fraction)


if __name__ == "__main__":
    unittest.main()

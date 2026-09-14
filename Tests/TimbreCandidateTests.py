#!/usr/bin/env python3
"""Strict experimental-profile validation and isolated renderer integration."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_timbre_candidate", ROOT / "Tools/build_timbre_candidate.py")
candidate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(candidate)


def baseline():
    return {"version": 1, "id": "diagnostic-baseline",
            "evidence": "Experimental diagnostic control; no hardware-match claim."}


def complete():
    result = baseline()
    for section, fields in candidate.FIELDS.items():
        result[section] = {}
        for field, (_, count, lo, hi, order) in fields.items():
            if count is None:
                value = (lo + hi) / 2
            elif field == "phase_cycles":
                value = [0.0, 0.125, 0.25, 0.5, 0.75]
            elif field == "offsets":
                value = [-0.25, -0.16, -0.08, 0, 0.08, 0.16, 0.25]
            else:
                value = [lo + (hi - lo) * i / (count - 1) for i in range(count)]
                value[0], value[-1] = lo, hi
                if order == "nonincreasing":
                    value.reverse()
            result[section][field] = value
    result["reference_rate_hz"] = 32000
    return result


class SchemaTests(unittest.TestCase):
    def test_baseline_partial_empty_sections_and_complete_profiles(self):
        for profile in [baseline(), complete(), {**baseline(), "waves": {}},
                        {**baseline(), "filter": {"cutoff_hz": [1000] * 128}},
                        {**baseline(), "supersaw": {"normalization": 0.4}}]:
            self.assertIs(candidate.validate_profile(profile), profile)

    def test_required_metadata_and_unknown_keys(self):
        invalid = [None, [], {}, {**baseline(), "version": True},
                   {**baseline(), "version": 1.0}, {**baseline(), "version": 2},
                   {**baseline(), "id": "../replace-engine"}, {**baseline(), "id": ""},
                   {**baseline(), "evidence": "Hardware verified"},
                   {**baseline(), "evidence": "Unexperimental"},
                   {**baseline(), "evidence": False}, {**baseline(), "extra": 1},
                   {**baseline(), "filter": {"cutoff": [1000] * 128}},
                   {**baseline(), "envelope": []}]
        for name in ("version", "id", "evidence"):
            profile = baseline(); del profile[name]; invalid.append(profile)
        for profile in invalid:
            with self.subTest(profile=profile):
                with self.assertRaises(candidate.CandidateError):
                    candidate.validate_profile(profile)

    def test_every_numeric_field_rejects_bad_types_nonfinite_and_bounds(self):
        for section, fields in candidate.FIELDS.items():
            for field, (_, count, lo, hi, _) in fields.items():
                for invalid in (None, True, "1", float("nan"), float("inf"),
                                -float("inf"), lo - 1, hi + 1, 10**400):
                    profile = complete()
                    if count is None:
                        profile[section][field] = invalid
                    else:
                        profile[section][field][count // 2] = invalid
                    with self.subTest(section=section, field=field, invalid=str(invalid)):
                        with self.assertRaises(candidate.CandidateError):
                            candidate.validate_profile(profile)
                if count is not None:
                    for invalid in (0, {}, "123", [0] * (count - 1), [0] * (count + 1)):
                        profile = complete(); profile[section][field] = invalid
                        with self.subTest(section=section, field=field, shape=type(invalid)):
                            with self.assertRaises(candidate.CandidateError):
                                candidate.validate_profile(profile)

    def test_monotonicity_and_required_exact_endpoints(self):
        for section, fields in candidate.FIELDS.items():
            for field, (_, count, _, _, order) in fields.items():
                if not order:
                    continue
                profile = complete()
                values = profile[section][field]
                values[1], values[2] = values[2], values[1]
                with self.subTest(field=field):
                    with self.assertRaisesRegex(candidate.CandidateError, "must be"):
                        candidate.validate_profile(profile)
        for field, value in (("phase_cycles", [0, 0, 0, 0, 1]),
                             ("pulse_duty", [0.5] * 127 + [1.0])):
            with self.assertRaises(candidate.CandidateError):
                candidate.validate_profile({**baseline(), "waves": {field: value}})
        for values in ([0.1] * 127 + [1], [0] + [0.9] * 127):
            with self.assertRaisesRegex(candidate.CandidateError, "endpoints"):
                candidate.validate_profile({**baseline(), "envelope": {"sustain_level": values}})
        for offsets in ([-.2, -.1, -.05, .01, .05, .1, .2], [-.2, -.1, 0, 0, .05, .1, .2]):
            with self.assertRaises(candidate.CandidateError):
                candidate.validate_profile({**baseline(), "supersaw": {"offsets": offsets}})

    def test_reference_rate_bounds_and_types(self):
        for value in (8000, 44100.5, 192000):
            candidate.validate_profile({**baseline(), "reference_rate_hz": value})
        for value in (7999, 192001, True, None, "44100", float("nan")):
            with self.assertRaises(candidate.CandidateError):
                candidate.validate_profile({**baseline(), "reference_rate_hz": value})

    def test_supersaw_detune_allows_the_incumbent_local_decrease(self):
        values = [i / 127 for i in range(128)]
        values[5] = values[4] * 0.999
        candidate.validate_profile({**baseline(), "supersaw": {"detune": values}})

    def test_invalid_json_and_duplicate_keys_before_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, output = root / "profile.json", root / "must-not-exist"
            for contents in (b"{", b"\xff", b"{}", b"[]", b'{"version":1,"version":1}',
                             b'{"version":1,"id":"x","evidence":"experimental","waves":{"wave_gain":[1,1,NaN,1,1]}}',
                             b'{"version":1,"id":"x","evidence":"experimental","waves":{"wave_gain":[],"wave_gain":[]}}',
                             b" " * (candidate.MAX_PROFILE_BYTES + 1)):
                path.write_bytes(contents)
                with self.subTest(contents=contents[:80]):
                    with self.assertRaises(candidate.CandidateError):
                        candidate.build_candidate(path, output, compiler="definitely-missing-compiler")
                    self.assertFalse(output.exists())

    def test_overwrite_and_shipping_source_output_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "profile.json"; path.write_text(json.dumps(baseline()))
            output = root / "existing"; output.mkdir()
            marker = output / "keep"; marker.write_text("existing work")
            with self.assertRaisesRegex(candidate.CandidateError, "already exists"):
                candidate.build_candidate(path, output)
            self.assertEqual(marker.read_text(), "existing work")
            broken = root / "broken-link"; broken.symlink_to(root / "missing")
            with self.assertRaisesRegex(candidate.CandidateError, "already exists"):
                candidate.build_candidate(path, broken)
            with self.assertRaisesRegex(candidate.CandidateError, "outside shipping"):
                candidate.build_candidate(path, ROOT / "Source/must-not-create")
            self.assertFalse((ROOT / "Source/must-not-create").exists())

    def test_renderer_integration_fails_closed_if_anchor_changes(self):
        text = (ROOT / "Tools/RenderMidi.cpp").read_text()
        for broken in ("", text + text,
                       text.replace("engine->prepare (rate, blockSize);", "engine->prepare (rate, 512);")):
            with self.assertRaisesRegex(candidate.CandidateError, "integration point"):
                candidate.candidate_renderer(broken, baseline())

    def test_failed_or_tampered_build_retains_failure_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input"
            (source / "Source/DSP").mkdir(parents=True)
            (source / "Tools").mkdir()
            (source / "Source/DSP/TimbreCalibration.h").write_text("// fixture\n")
            (source / "Source/DSP/SeptumEngine.cpp").write_text("// fixture\n")
            (source / "Tools/RenderMidi.cpp").write_text((ROOT / "Tools/RenderMidi.cpp").read_text())
            profile = root / "profile.json"; profile.write_text(json.dumps(baseline()))
            for tamper in (False, True):
                output = root / ("tamper" if tamper else "failed")

                def simulated_compiler(command, **kwargs):
                    if "--version" in command:
                        return subprocess.CompletedProcess(command, 0, "Test compiler fixture")
                    if tamper:
                        (output / "CandidateProfile.h").write_text("changed during build")
                    return subprocess.CompletedProcess(command, 0 if tamper else 3)

                with mock.patch.object(candidate, "_git", return_value=None), \
                        mock.patch.object(candidate.subprocess, "run", side_effect=simulated_compiler):
                    with self.assertRaises(candidate.CandidateError):
                        candidate.build_candidate(profile, output, source_root=source, compiler=sys.executable)
                manifest = json.loads((output / "manifest.json").read_text())
                self.assertEqual(manifest["status"], "failed")
                self.assertIn("changed" if tamper else "Compiler failed", manifest["error"])
                self.assertEqual(manifest["frozen_inputs_verified"], not tamper)
                self.assertTrue((output / "build.log").exists())


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("c++"):
            raise unittest.SkipTest("C++20 compiler unavailable")
        cls.temporary = tempfile.TemporaryDirectory(prefix="septum-candidate-tests-")
        cls.path = Path(cls.temporary.name)
        cls.results = {}
        cls.before = candidate._sources(ROOT)
        profiles = {
            "baseline": baseline(),
            "triangle": {**baseline(), "id": "triangle-inverted",
                         "waves": {"wave_gain": [1, 1, 1, -1, 1]}},
            "filter": {**baseline(), "id": "cutoff-octave-down",
                       "filter": {"cutoff_hz": [10 * 2**(i * 10 / 127) for i in range(128)]}},
            "reference": {**baseline(), "id": "reference-diagnostic", "reference_rate_hz": 32000,
                          "filter": {}, "envelope": {}, "waves": {}, "supersaw": {}},
        }
        for name, profile in profiles.items():
            file = cls.path / (name + ".json"); file.write_text(json.dumps(profile))
            output = cls.path / name
            try:
                cls.results[name] = candidate.build_candidate(file, output)
            except candidate.CandidateError as error:
                log = output / "build.log"
                raise RuntimeError(str(error) + ("\n" + log.read_text() if log.exists() else "")) from error
        # A separately compiled shipping renderer verifies the disabled-section
        # baseline against the original entry point, not another candidate.
        source = cls.path / "baseline"
        cls.native = cls.path / "native-renderer"
        sources = sorted((source / "Source/DSP").glob("*.cpp"))
        subprocess.run(["c++", "-std=c++20", "-O2", "-fno-fast-math", "-I" + str(source / "Source"),
                        str(source / "original/Tools/RenderMidi.cpp"), *map(str, sources),
                        "-o", str(cls.native)], check=True, capture_output=True, timeout=240)
        init = cls.path / "init.syx"
        subprocess.run([str(cls.native), "--write-init-patch", str(init)], check=True, capture_output=True)
        packets = [bytearray(frame + b"\xf7") for frame in init.read_bytes().split(b"\xf7") if frame]
        upper = next(packet for packet in packets if packet[9] == 1)
        upper[11] = 3  # OSC1 triangle, native waveform enumeration.
        upper[11 + 0x11] = 0  # Filter bypass: isolate waveform polarity.
        upper[-2] = (-sum(upper[7:-2])) & 127
        cls.patch = cls.path / "triangle.syx"
        cls.patch.write_bytes(b"".join(packets))
        upper[11 + 0x11] = 1  # LPF for the independent cutoff-table fixture.
        upper[11 + 0x13] = 80
        upper[-2] = (-sum(upper[7:-2])) & 127
        cls.filtered_patch = cls.path / "filtered.syx"
        cls.filtered_patch.write_bytes(b"".join(packets))
        cls.events = cls.path / "notes.events"
        cls.events.write_text("SEPTUM_RENDER_EVENTS 1 12000\n0 midi 903c64\n10000 midi 803c00\n")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def render(self, name, binary, patch=None):
        target = self.path / (name + ".wav")
        result = subprocess.run([str(binary), "--syx", str(patch or self.patch), "--events", str(self.events),
                                 "--sample-rate", "48000", "--tail", "0.1", "--output", str(target)],
                                capture_output=True, text=True, check=True, timeout=30)
        report = json.loads(result.stdout)
        content = target.read_bytes()
        audio = struct.unpack("<" + "f" * ((len(content) - 56) // 4), content[56:])
        self.assertTrue(all(math.isfinite(value) for value in audio))
        self.assertGreater(report["peak"], 1e-5)
        self.assertEqual(report["frames"], 16800)
        return content, audio, report

    def test_disabled_profile_is_bit_identical_to_shipping_renderer(self):
        native, _, _ = self.render("native", self.native)
        built, _, _ = self.render("baseline", self.path / "baseline/SeptumRenderMidi")
        self.assertEqual(native, built)

    def test_emitted_profile_changes_audio_and_reference_rate_renders(self):
        _, normal, report = self.render("normal", self.path / "baseline/SeptumRenderMidi")
        _, inverted, _ = self.render("inverted", self.path / "triangle/SeptumRenderMidi")
        energy = sum(x*x for x in normal)
        relative = math.sqrt(sum((a+b)**2 for a, b in zip(normal, inverted)) / energy)
        self.assertLess(relative, 1e-5, "emitted triangle gain must invert actual rendered audio")
        _, converted, reference_report = self.render("reference", self.path / "reference/SeptumRenderMidi")
        self.assertNotEqual(converted, normal)
        self.assertGreater(reference_report["latency_samples"], report["latency_samples"])

    def test_emitted_cutoff_table_changes_audible_filter_response(self):
        _, normal, _ = self.render("filter-control", self.path / "baseline/SeptumRenderMidi", self.filtered_patch)
        _, changed, _ = self.render("filter-candidate", self.path / "filter/SeptumRenderMidi", self.filtered_patch)
        energy = sum(value * value for value in normal)
        relative = math.sqrt(sum((a-b)**2 for a, b in zip(normal, changed)) / energy)
        self.assertGreater(relative, 0.02, "generated cutoff_hz assignments must reach the voice filter")

    def test_empty_supersaw_section_preserves_factory_raw_detune_points(self):
        source = self.path / "reference"
        probe = self.path / "factory-probe.cpp"
        full_profile = self.path / "FullCandidateProfile.h"
        full_profile.write_text(candidate.candidate_header(complete()).replace(
            "makeCandidateProfile", "makeFullCandidateProfile"))
        probe.write_text('''#include "CandidateProfile.h"
#include "FullCandidateProfile.h"
int main() {
    const auto profile = makeCandidateProfile();
    if (!profile.valid() || !profile.superSawEnabled) return 1;
    if (profile.secondStageIndependent || profile.superDetuneTableEnabled) return 2;
    for (int raw = 0; raw < 128; ++raw)
        if (profile.superDetune[raw] != septum::mapping::superSawDetuneAmount(raw / 127.0)) return 3;
    const auto full = makeFullCandidateProfile();
    if (!full.valid() || !full.secondStageIndependent || !full.superDetuneTableEnabled) return 4;
    return 0;
}
''')
        binary = self.path / "factory-probe"
        subprocess.run(["c++", "-std=c++20", "-O2", "-I" + str(source / "Source"),
                        "-I" + str(source), str(probe), str(source / "Source/DSP/SeptumEngine.cpp"),
                        "-o", str(binary)], check=True, capture_output=True, timeout=120)
        subprocess.run([str(binary)], check=True, capture_output=True, timeout=30)

    def test_frozen_sources_and_full_provenance_are_verifiable(self):
        self.assertEqual(self.before, candidate._sources(ROOT), "candidate build must leave shipping DSP untouched")
        for name, manifest in self.results.items():
            output = self.path / name
            self.assertEqual(manifest["status"], "complete")
            self.assertTrue(manifest["experimental"])
            self.assertFalse(manifest["hardware_match_claim"])
            self.assertTrue(manifest["frozen_inputs_verified"])
            for file, digest in manifest["frozen_sha256"].items():
                self.assertEqual(hashlib.sha256((output / file).read_bytes()).hexdigest(), digest)
            for file, digest in manifest["source"]["input_sha256"].items():
                if file.startswith("Source/DSP/"):
                    self.assertEqual(hashlib.sha256((output / file).read_bytes()).hexdigest(), digest)
            self.assertEqual(hashlib.sha256((output / "SeptumRenderMidi").read_bytes()).hexdigest(),
                             manifest["renderer"]["sha256"])
            self.assertTrue(manifest["compiler"]["version"])
            self.assertFalse(any(argument.endswith(".a") for argument in manifest["compiler"]["command"]))
            self.assertLess((output / "Tools/RenderMidi.cpp").read_text().index("setTimbreCalibration"),
                            (output / "Tools/RenderMidi.cpp").read_text().index("engine->prepare"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema-only", action="store_true", help="Validate JSON/error policy without compiling renderers")
    args, extra = parser.parse_known_args()
    if args.schema_only:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(SchemaTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(not result.wasSuccessful())
    unittest.main(argv=[sys.argv[0], *extra])

#!/usr/bin/env python3
"""Compile exact frozen envelope methods and cutoff expression as a small probe.

The probe uses the built renderer's actual CandidateProfile.h and mappings.
Only private visibility changes in a separate header copy. It checks control
targets at eight-sample ticks; it does not substitute for the complete audio
renderer, which additionally interpolates filter coefficients within ticks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def function(text, marker):
    start = text.index(marker)
    opening = text.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


MAIN = r'''
#include <iostream>
#include <iomanip>
#include <set>
#include "CandidateProfile.h"
namespace septum {
METHODS
}
double cutoff(double filterEnvLevel, int note, const septum::TimbreCalibration& profile) {
    using namespace septum;
    const double sampleRate_ = 44100;
    struct Voice { double cutoffParamOctSlewed, filterEnvOctSlewed; } voice;
    voice.cutoffParamOctSlewed = std::log2(profile.filterEnabled
        ? TimbreCalibration::lookup(profile.cutoffHz, 47) : mapping::cutoffHz(47))
        + mapping::keyFollowOctavesPerOctave(100) * (note - 60.0) / 12.0;
    voice.filterEnvOctSlewed = mapping::filterEnvOctaves(16);
    FC_EXPRESSION
    return fc;
}
int main(int argc, char** argv) {
    using namespace septum;
    const double delay = std::stod(argv[1]);
    auto profile = makeCandidateProfile();
    const auto* ptr = profile.envelopeEnabled ? &profile : nullptr;
    Engine::Envelope attack;
    attack.configure(44100, 0, 53, 0, 0, Engine::Envelope::DecayShape::SHAPE, ptr);
    attack.trigger();
    int attackSamples = 0;
    while (attack.stage == Engine::Envelope::Stage::Attack) { attack.advance(1); ++attackSamples; }
    std::set<int> wanted;
    for (double t : {.04, .10, .18, .26, .34, 1., 2.5, 4., 20.})
        wanted.insert(8 * static_cast<int>(std::ceil(((t-delay)*44100+attackSamples)/8)));
    Engine::Envelope env;
    env.configure(44100, 0, 53, 0, 0, Engine::Envelope::DecayShape::SHAPE, ptr);
    env.trigger();
    int settle = -1;
    std::cout << std::setprecision(17);
    for (int n=8; n <= *wanted.rbegin(); n+=8) {
        const double level = env.advance(8);
        if (settle < 0 && env.stage == Engine::Envelope::Stage::Sustain) settle=n;
        if (wanted.count(n)) std::cout << "sample " << n << " " << level << " "
            << cutoff(level,24,profile) << " " << cutoff(level,36,profile) << " "
            << cutoff(level,57,profile) << " " << static_cast<int>(env.stage) << "\n";
    }
    std::cout << "meta " << attackSamples << " " << env.decayCoeff << " " << env.settled
              << " " << settle << " " << cutoff(0,60,profile) << " "
              << mapping::filterEnvOctaves(16) << " " << mapping::filterDecaySeconds(53) << "\n";
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, out = args.experiment_dir.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    renders = json.loads((root / "renders.json").read_text())
    definitions = renders["definitions"]
    trajectory = Path(__file__).resolve().parents[1] / "Docs/fidelity/source-audits/deepsonic-envelope-shape-2026-09-15.json"
    targets = json.loads(trajectory.read_text())["models"]
    compiler = shutil.which("c++")
    if compiler is None:
        raise ValueError("A C++20 compiler is required")
    compiler_info = {"path": compiler, "sha256": sha(compiler),
                     "version": subprocess.check_output([compiler, "--version"], text=True)}
    reports = []
    for definition in definitions:
        name, kind = definition["id"], definition["kind"]
        folder = root / "renderers" / name
        manifest = json.loads((folder / "manifest.json").read_text())
        for filename, expected in manifest["frozen_sha256"].items():
            if sha(folder / filename) != expected:
                raise ValueError("Changed frozen input: " + filename)
        if kind != "production" and sha(trajectory) != definition["trajectory_source_sha256"]:
            raise ValueError("Changed fitted trajectory source")
        cpp = (folder / "Source/DSP/SeptumEngine.cpp").read_text()
        markers = ("void Engine::Envelope::configure", "double Engine::Envelope::advance",
                   "TimbreCalibration Engine::defaultTimbreCalibration")
        methods = "\n\n".join(function(cpp, marker) for marker in markers)
        start = cpp.index("const double fc = std::clamp (", cpp.index("void Engine::updateVoiceControls"))
        fc = cpp[start:cpp.index(";", start) + 1]
        shapes = re.findall(r"tone\.filterEnvRelease, Envelope::DecayShape::(\w+),", cpp)
        if len(shapes) != 2 or len(set(shapes)) != 1:
            raise ValueError("Ambiguous filter decay-shape call sites")
        fixture = out / name
        fixture.mkdir()
        shutil.copytree(folder / "Source/DSP", fixture / "DSP")
        header = fixture / "DSP/SeptumEngine.h"
        header.write_text(header.read_text().replace("private:", "public:"))
        shutil.copyfile(folder / "CandidateProfile.h", fixture / "CandidateProfile.h")
        source = MAIN.replace("METHODS", methods).replace("FC_EXPRESSION", fc).replace("SHAPE", shapes[0])
        (fixture / "probe.cpp").write_text(source)
        command = [compiler, "-std=c++20", "-O2", "-fno-fast-math", "probe.cpp", "-o", "probe"]
        run = subprocess.run(command, cwd=fixture, capture_output=True, text=True)
        (fixture / "build.log").write_text(run.stdout + run.stderr)
        if run.returncode:
            raise RuntimeError("Probe compilation failed: " + name + "\n" + run.stderr)
        delay = definition.get("effective_hardware_decay_start_seconds", .035)
        raw = subprocess.check_output([str(fixture / "probe"), str(delay)], text=True)
        (fixture / "measurements.txt").write_text(raw)
        lines = [line.split() for line in raw.splitlines()]
        meta = next(line for line in lines if line[0] == "meta")
        attack, coefficient, threshold, settle, base60, depth, linear_duration = map(float, meta[1:])
        errors, observations = [], []
        if kind != "production":
            model = "exponential_hz_with_floor" if kind == "hz" else "exponential_log_cutoff"
            a, b, tau = targets[model]["parameters"]
        requested_times = iter((.04, .10, .18, .26, .34, 1., 2.5, 4., 20.))
        for line in lines:
            if line[0] != "sample":
                continue
            n, level, *tail = map(float, line[1:])
            age, hardware_time = (n - attack) / 44100, delay + (n - attack) / 44100
            requested_time = next(requested_times)
            expected_level = (max(0., 1-age/linear_duration) if kind == "production"
                              else math.exp(-age/tau))
            row = {"sample": int(n), "decay_age_seconds": age,
                   "paired_hardware_seconds_after_midi": hardware_time,
                   "requested_hardware_seconds_after_midi": requested_time,
                   "tick_quantization_seconds": hardware_time-requested_time,
                   "level": level, "expected_level": expected_level,
                   "level_absolute_error": abs(level-expected_level), "cutoffs": []}
            for note, actual in zip((24, 36, 57), tail[:3]):
                f0 = 440 * 2**((note-69)/12)
                if kind == "production":
                    expected = base60 * 2**((note-60)/12) * 2**(depth*expected_level)
                elif kind == "hz":
                    expected = f0 * (a+b*math.exp(-hardware_time/tau))
                else:
                    expected = f0 * math.exp(a+b*math.exp(-hardware_time/tau))
                expected = min(.45*44100, max(5., expected))
                cents = 1200 * math.log2(actual/expected)
                errors.append(abs(cents))
                row["cutoffs"].append({"note": note, "actual_hz": actual,
                                       "expected_hz": expected, "error_cents": cents})
            observations.append(row)
        maximum = max(errors)
        if maximum > .001 or max(row["level_absolute_error"] for row in observations) > 1.1e-8:
            raise ValueError(f"Integration guard failed: {name}: {maximum} cents")
        report = {"id": name, "kind": kind, "manifest_sha256": sha(folder / "manifest.json"),
                  "profile_header_sha256": sha(folder / "CandidateProfile.h"),
                  "extracted_probe_sha256": sha(fixture / "probe.cpp"), "compiler_command": command,
                  "probe_sha256": sha(fixture / "probe"), "raw_measurements_sha256": sha(fixture / "measurements.txt"),
                  "attack_samples": int(attack), "nominal_attack_samples": 44.1,
                  "attack_rounding_seconds": (attack-44.1)/44100,
                  "tick_samples": 8, "tick_interval_seconds": 8/44100,
                  "maximum_evaluation_tick_rounding_seconds": max(r["tick_quantization_seconds"] for r in observations),
                  "predeclared_audio_lag_samples": round(93+44.1-delay*44100),
                  "predeclared_audio_lag_minus_actual_attack_target_samples": round(93+44.1-delay*44100)-(93+attack-delay*44100),
                  "first_observed_sustain_sample": int(settle),
                  "first_observed_sustain_seconds": settle/44100,
                  "decay_coefficient": coefficient, "termination_amount_threshold": threshold,
                  "maximum_cutoff_error_cents": maximum,
                  "maximum_level_absolute_error": max(row["level_absolute_error"] for row in observations),
                  "observations": observations}
        reports.append(report)
        print(name, "max cutoff error cents", maximum, flush=True)
    result = {"schema_version": 1, "status": "passed_extracted_method_control_target_guard",
              "renders_sha256": sha(root / "renders.json"), "tool_sha256": sha(__file__),
              "trajectory_source_sha256": sha(trajectory), "models": reports,
              "compiler": compiler_info,
              "method": "Compile exact frozen Envelope configure/advance/default calibration methods, actual CandidateProfile.h, mappings and cutoff expression; only separate copied-header private visibility changes.",
              "alignment": "Paired hardware age L+(n-actual_attack_samples)/44100; L is the frozen 30/35/40ms convention. Output transport latency is not applied to this internal control target and must be handled once by full-audio comparison.",
              "scope": "Eight-sample control-target endpoints, not full audio or within-tick g interpolation; zero sustain/positive depth fixture only. Late sustained synthetic probes continue beyond original MIDI gates to expose termination.",
              "acceptance_bounds": {"maximum_cutoff_error_cents": .001, "maximum_level_absolute_error": 1.1e-8}}
    (out / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()

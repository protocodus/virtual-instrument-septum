#!/usr/bin/env python3
"""Build frozen, experimental filter-envelope renderers; never edit shipping DSP.

The dry stage integrates two previously fitted physical trajectories. The
factory stage retains published preset bytes and tests a predeclared time grid.
These are hypotheses, not recovered Roland algorithms or calibration tables.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REVISION = "b0f6c03"
GRID = (.08, .11, .15, .20, .27)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError(f"Expected {count} integration points: {old}")
    return text.replace(old, new)


def freeze(out):
    names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", REVISION,
                                     "Source/DSP"], cwd=ROOT, text=True).splitlines()
    names += ["Tools/" + x for x in ("RenderMidi.cpp", "build_timbre_candidate.py", "render_midi.py")]
    frozen = out / "checkpoint-source"
    hashes = {}
    for name in names:
        data = subprocess.check_output(["git", "show", f"{REVISION}:{name}"], cwd=ROOT)
        target = frozen / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        hashes[name] = sha(target)
    (out / "experiment-script.py").write_bytes(Path(__file__).read_bytes())
    save(out / "checkpoint.json", {"revision": REVISION, "source_sha256": hashes,
                                  "script_sha256": sha(__file__)})
    return frozen


def prototype(frozen, target, kind, depth_per_raw=None):
    shutil.copytree(frozen, target)
    if kind == "production":
        return target
    cpp, header = target / "Source/DSP/SeptumEngine.cpp", target / "Source/DSP/SeptumEngine.h"
    text = cpp.read_text()
    text = replace(text, "tone.filterEnvRelease, Envelope::DecayShape::Linear,",
                   "tone.filterEnvRelease, Envelope::DecayShape::Exponential,", 2)
    text = replace(text,
        "decayCoeff = std::exp (-6.907755 / std::max (1.0, mapping::decaySeconds (d) * sr));",
        """// EXPERIMENTAL: calibration is passed only by the filter envelope.
    const double decayTime = calibration != nullptr
        ? calibration->decaySeconds[static_cast<std::size_t> (d)] : mapping::decaySeconds (d);
    const double decayLogRange = calibration != nullptr ? std::log (1000.0) : 6.907755;
    decayCoeff = std::exp (-decayLogRange / std::max (1.0, decayTime * sr));
    settled = calibration != nullptr ? 1.0e-8 : 1.0e-4;
    releaseSettled = calibration != nullptr ? 1.0e-8 : 1.0e-5;""", 2)
    # The matching line also occurs in PitchEnvelope::configure. Restore that
    # entire replacement there: pitch has no calibration and must stay identical.
    start = text.index("void Engine::PitchEnvelope::configure")
    end = text.index("double Engine::PitchEnvelope::advance", start)
    original = frozen / "Source/DSP/SeptumEngine.cpp"
    orig = original.read_text()
    a, b = orig.index("void Engine::PitchEnvelope::configure"), orig.index("double Engine::PitchEnvelope::advance")
    text = text[:start] + orig[a:b] + text[end:]
    text = replace(text, "if (level < 1.0e-5)", "if (level < releaseSettled)")
    if kind == "hz":
        text = replace(text,
            "std::exp2 (voice.cutoffParamOctSlewed + filterEnvLevel * voice.filterEnvOctSlewed)",
            "std::exp2 (voice.cutoffParamOctSlewed)\n"
            "            * (1.0 + (std::exp2 (voice.filterEnvOctSlewed) - 1.0) * filterEnvLevel)")
    elif kind != "log":
        raise ValueError(kind)
    cpp.write_text(text)
    text = replace(header.read_text(), "static constexpr double settled = 1.0e-4;",
                   "double settled { 1.0e-4 };\n        double releaseSettled { 1.0e-5 };")
    if depth_per_raw is not None:
        text = replace(text, "filterEnvOctaves (int depth) noexcept\n    {\n        return depth * (12.0 / 63.0);",
                       "filterEnvOctaves (int depth) noexcept\n    {\n"
                       f"        return depth * {depth_per_raw:.17g}; // Experimental dry physical fixture only")
    header.write_text(text)
    # Human-readable, exact patch accompanies every source snapshot.
    diff = subprocess.run(["diff", "-ru", str(frozen / "Source/DSP"), str(target / "Source/DSP")],
                          capture_output=True, text=True)
    if diff.returncode not in (0, 1):
        raise RuntimeError(diff.stderr)
    (target / "experimental-dsp.diff").write_text(diff.stdout)
    return target


def default_filter_time(v):
    power = math.log((.4189852819747085 - .002) / (12 - .002)) / math.log(49 / 127)
    return .002 + (12 - .002) * (v / 127) ** power


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("dry", "factory"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--comparison-root", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.jobs not in (1, 2, 3, 4):
        parser.error("jobs must be 1..4")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    frozen = freeze(out)
    spec = importlib.util.spec_from_file_location("frozen_builder", frozen / "Tools/build_timbre_candidate.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    profiles = out / "profiles"
    profiles.mkdir()
    definitions = [{"id": "production", "kind": "production", "fields": {}}]
    if args.stage == "factory":
        # The same predeclared scale grid also supplies a geometric-cutoff
        # control, separating decay shape from interpolation domain.
        for kind in ("hz", "log"):
            for tau in GRID:
                times = [tau * math.log(1000) * default_filter_time(v) / default_filter_time(49)
                         for v in range(128)]
                definitions.append({"id": f"{kind}-tau49-{tau:.2f}", "kind": kind,
                    "tau49_seconds": tau, "T60_raw49_seconds": tau * math.log(1000),
                    "fields": {"envelope": {"decay_seconds": times}}})
    else:
        source = ROOT / "Docs/fidelity/source-audits/deepsonic-envelope-shape-2026-09-15.json"
        data = json.loads(source.read_text())
        for kind, model in (("hz", "exponential_hz_with_floor"), ("log", "exponential_log_cutoff")):
            a, b, tau = data["models"][model]["parameters"]
            for delay in (.030, .035, .040):
                base = a if kind == "hz" else math.exp(a)
                depth = (math.log2((a + b * math.exp(-delay / tau)) / a) if kind == "hz"
                         else b * math.exp(-delay / tau) / math.log(2))
                base_hz = 440 * 2 ** ((60 - 69) / 12) * base
                scale = base_hz / (20 * 2 ** (10 * 47 / 127))
                definitions.append({"id": f"dry-{kind}-{round(delay * 1000)}ms", "kind": kind,
                    "effective_hardware_decay_start_seconds": delay, "tau_seconds": tau,
                    "base_cutoff_over_f0": base, "base_cutoff_hz_at_midi60": base_hz,
                    "depth_octaves": depth, "depth_per_raw": depth / 16,
                    "trajectory_source_sha256": sha(source),
                    "fields": {"envelope": {"decay_seconds": [tau * math.log(1000)] * 128},
                               "filter": {"cutoff_hz": [max(5., 20 * 2 ** (10 * v / 127) * scale)
                                                        for v in range(128)]}}})
    save(out / "predeclared-definitions.json", definitions)

    def build(d):
        source = prototype(frozen, out / ("prototype-" + d["id"]), d["kind"], d.get("depth_per_raw"))
        profile = {"version": 1, "id": d["id"], "evidence": "Experimental envelope-domain hypothesis; no hardware-match claim.", **d["fields"]}
        path = profiles / (d["id"] + ".json")
        save(path, profile)
        directory = out / "renderers" / d["id"]
        manifest = builder.build_candidate(path, directory, source_root=source)
        print("Built " + d["id"], flush=True)
        return d["id"], directory / manifest["renderer"]["path"]

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        renderers = dict(pool.map(build, definitions))
    q0_record = None
    if args.stage == "dry":
        q0_data = subprocess.check_output(["git", "show", REVISION +
            ":Docs/fidelity/source-audits/dry-end-to-end-2026-09-15.json"], cwd=ROOT)
        (out / "pinned-q0-record.json").write_bytes(q0_data)
        q0_record = json.loads(q0_data)
    renders = []
    for d in definitions:
        cases = ["moogie-1"] if args.stage == "factory" else ["lp12", "lp24"]
        for case in cases:
            target = out / "audio" / d["id"] / case
            target.mkdir(parents=True)
            if args.stage == "factory":
                inputs = args.comparison_root / case
                midi, syx = inputs / "reconstructed-performance.mid", inputs / "original-patch.syx"
            else:
                inputs = ROOT / "build-fidelity/hardware-benchmark/zero-resonance-candidate/dry-end-to-end/onset-calibrated" / ("onset-corrected-trajectory-" + case)
                syx = inputs / "recipe-reconstruction.syx"
                midi = ROOT / "build-fidelity/deepsonic/deepsonic_-_filter_demo_-_comparsion_sequence.mid"
            # Hash and retain the exact input bytes before rendering.
            shutil.copyfile(midi, target / "performance.mid")
            shutil.copyfile(syx, target / "patch.syx")
            wav = target / "candidate.wav"
            command = [sys.executable, str(frozen / "Tools/render_midi.py"), "--renderer", str(renderers[d["id"]]),
                       "--midi", str(target / "performance.mid"), "--syx", str(target / "patch.syx"),
                       "--output", str(wav), "--tempo-policy", "preserve-patch"]
            if args.stage == "dry":
                command += ["--allow-unsupported"]
            run = subprocess.run(command, capture_output=True, text=True)
            (target / "render.log").write_text(run.stdout + run.stderr)
            if run.returncode:
                raise RuntimeError("Render failed: " + str(target))
            receipt = json.loads(wav.with_suffix(".render.json").read_text())
            if (receipt["output"]["active_voices_at_end"] != 0
                    or not math.isfinite(receipt["output"]["peak"])):
                raise ValueError("Invalid output or unfinished voices: " + str(target))
            if args.stage == "dry":
                omitted = receipt["ignored_events"]
                if (sha(midi) != "21ea21b9ba3ba14cc205931134fb7a320b09e67821bd3a3c70f97fa2e8b5d99a"
                        or receipt["replay_event_counts"] != {"note_on": 124, "note_off": 124}
                        or len(omitted) != 1 or omitted[0].get("meta_type") != 32
                        or omitted[0].get("hex") != "00"):
                    raise ValueError("Original MIDI identity or permitted metadata omission changed")
                if d["id"] == "production":
                    expected = next(r["raw_render_sha256"] for r in q0_record["results"]
                                    if r["recipe"] == "onset-corrected-trajectory"
                                    and r["slope"] == int(case[2:])
                                    and r["family"] == "zero-resonance-k1p2")
                    if sha(wav) != expected:
                        raise ValueError("Pinned Q0 production identity guard failed")
            if args.stage == "factory" and d["id"] == "production":
                if sha(wav) != sha(inputs / "septum-raw.wav"):
                    raise ValueError("Production identity guard failed")
            renders.append({"id": d["id"], "case": case, "wav": str(wav), "sha256": sha(wav),
                            "midi_sha256": sha(midi), "sysex_sha256": sha(syx), "command": command,
                            "peak": receipt["output"]["peak"], "latency_samples": receipt["output"]["latency_samples"]})
            print("Rendered " + d["id"] + "/" + case, flush=True)
    save(out / "renders.json", {"experimental": True, "source_revision": REVISION,
                                "definitions": definitions, "renders": renders})
    if args.stage == "factory":
        case = args.comparison_root / "moogie-1"
        base = {"hardware_wav": str((case / "hardware-excerpt-raw.wav").resolve()),
                "production_wav": next(r["wav"] for r in renders if r["id"] == "production"),
                "sysex": str((case / "original-patch.syx").resolve()),
                "midi": str((case / "reconstructed-performance.mid").resolve()), "renderer_latency_samples": 93}
        for kind in ("hz", "log"):
            candidates = [{k: d[k] for k in ("id", "tau49_seconds", "T60_raw49_seconds")} |
                          {"wav": next(r["wav"] for r in renders if r["id"] == d["id"])}
                          for d in definitions if d["kind"] == kind]
            save(out / (kind + "-score-input.json"), {**base, "candidates": candidates})


if __name__ == "__main__":
    main()

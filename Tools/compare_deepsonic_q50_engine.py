#!/usr/bin/env python3
"""Reproduce a conditional full-engine nominal-50%-resonance experiment.

Requires original cached deepsonic MIDI/MP3s, NumPy, SciPy, ffmpeg, C++20,
and repository history at the pinned checkpoint. Never changes shipping DSP.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
REVISION = "b0f6c03"
Q0_RECORD = "Docs/fidelity/source-audits/dry-end-to-end-2026-09-15.json"
SOURCES = {
    "deepsonic_-_filter_demo_-_comparsion_sequence.mid": "21ea21b9ba3ba14cc205931134fb7a320b09e67821bd3a3c70f97fa2e8b5d99a",
    "roland_sh-201_-_filter_demo_-_lpf12_q050.mp3": "eada93d2d7330a573bf5166244d8b9cb6a4d55fb49f0c1d6bd18197b5a9529ca",
    "roland_sh-201_-_filter_demo_-_lpf24_q050.mp3": "57dabaf9090e306913f05e3fc03fbcff60f01cb04bd05851f73536c5fc54809c",
}
TRAINING = (1.5, 1.9375056689342403)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def historical_file(name):
    return subprocess.check_output(["git", "show", f"{REVISION}:{name}"], cwd=ROOT)


def freeze(output):
    frozen = output / "frozen-source"
    (output / "experiment-script.py").write_bytes(Path(__file__).read_bytes())
    files = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", REVISION,
                                     "Source/DSP"], cwd=ROOT, text=True).splitlines()
    files += ["Tools/" + name for name in ("RenderMidi.cpp", "build_timbre_candidate.py",
              "render_midi.py", "generate_timbre_capture.py", "assess_hardware_equivalence.py")]
    hashes = {}
    for name in files:
        path = frozen / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(historical_file(name))
        hashes[name] = sha(path)
    data = historical_file(Q0_RECORD)
    (output / "q0-recipe-source.json").write_bytes(data)
    write_json(output / "source-manifest.json", {"revision": REVISION, "input_sha256": hashes,
               "q0_record_sha256": hashlib.sha256(data).hexdigest(), "script_sha256": sha(__file__)})
    return frozen, json.loads(data)


def onset(audio, sr, threshold):
    start, end = round(1.49 * sr), round(1.56 * sr)
    peak = float(np.max(abs(audio[round(1.53 * sr):round(1.66 * sr)])))
    crossings = np.flatnonzero(abs(np.diff(audio)[start:end]) > threshold * peak)
    if not len(crossings):
        raise ValueError("No training-note onset within the declared search interval")
    return start + int(crossings[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--nominal-one-second", action="store_true",
                        help="Use fixed decay raw63 for Q50 sensitivity; retain raw53 for Q0 identity guards")
    parser.add_argument("--alignment-from", type=Path,
                        help="Freeze lag from a previous same-source Q50 result for recipe sensitivity")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("Choose a new output directory")
    output.mkdir(parents=True)
    frozen, q0 = freeze(output)
    sys.path.insert(0, str(frozen / "Tools"))
    import build_timbre_candidate as builder
    import generate_timbre_capture as capture
    import assess_hardware_equivalence as assessor
    import render_midi

    private = output / "source-cache"
    private.mkdir()
    identities = {}
    for name, expected in SOURCES.items():
        original = args.sources / name
        if sha(original) != expected:
            raise ValueError(f"Original source identity mismatch: {original}")
        shutil.copyfile(original, private / name)
        identities[name] = expected
    midi = private / "deepsonic_-_filter_demo_-_comparsion_sequence.mid"
    parsed = render_midi.parse_smf(midi.read_bytes())
    messages = [bytes.fromhex(event["hex"]) for event in parsed["events"] if event["kind"] == "midi"]
    if not all(len(m) == 3 and m[0] in (0x80, 0x90) for m in messages):
        raise ValueError("Expected channel-1 notes only; a controller could invalidate flat damping tables")
    if sum(m[0] == 0x90 and m[2] > 0 for m in messages) != 124:
        raise ValueError("Original positive note count changed")
    decoder = shutil.which("ffmpeg")
    if not decoder:
        raise ValueError("ffmpeg is required")
    decode_info = {"decoder": decoder, "binary_sha256": sha(decoder),
                   "version": subprocess.check_output([decoder, "-version"], text=True).splitlines()[0], "files": []}
    hardware = {}
    for slope in (12, 24):
        mp3 = private / f"roland_sh-201_-_filter_demo_-_lpf{slope}_q050.mp3"
        wav = mp3.with_suffix(".wav")
        command = [decoder, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(mp3),
                   "-c:a", "pcm_f32le", str(wav)]
        subprocess.run(command, check=True)
        sr, h = wavfile.read(wav)
        if sr != 44100 or h.ndim != 1 or not np.isfinite(h).all():
            raise ValueError("Expected finite 44.1 kHz mono hardware decode")
        hardware[slope] = h.astype(np.float64)
        decode_info["files"].append({"command": command, "source_sha256": sha(mp3), "decoded_sha256": sha(wav)})
    write_json(private / "decode-manifest.json", decode_info)

    definitions = {
        "checkpoint": {},
        "calibrated-identity": {"filter": {}},
        "lp12-stronger": {"filter": {"resonance_damping": [.16628] * 128}},
        "lp24-equal": {"filter": {"resonance_damping": [.29379] * 128,
                                   "second_stage_damping": [.29379] * 128}},
        "lp24-split": {"filter": {"resonance_damping": [.17533] * 128,
                                   "second_stage_damping": [.42962] * 128}},
    }
    profile_dir = output / "profiles"
    profile_dir.mkdir()
    manifests = {}
    for family, fields in definitions.items():
        profile = {"version": 1, "id": "q50-" + family,
                   "evidence": "Experimental conditional Q50 diagnostic; flat damping tables apply only to fixed raw resonance64, not a proposed production curve.", **fields}
        profile_path = profile_dir / (family + ".json")
        write_json(profile_path, profile)
        manifests[family] = builder.build_candidate(profile_path, output / "builds" / family, source_root=frozen)
        if manifests[family]["source"]["input_sha256"] != manifests["checkpoint"]["source"]["input_sha256"]:
            raise ValueError("Renderer source inputs drifted")
        print("Built", family, flush=True)

    init = output / "engine-init.syx"
    subprocess.run([str(output / "builds/checkpoint/SeptumRenderMidi"), "--write-init-patch", str(init)], check=True)
    original = capture.decode_syx(init.read_bytes())
    recipe_dir = output / "recipes"
    recipe_dir.mkdir()
    patch_paths = {}
    for slope in (12, 24):
        recipe = q0["recipes"][f"onset-corrected-trajectory-lp{slope}"]
        for resonance in (0, 63, 64):
            blocks = [bytearray(b) for b in original]
            blocks[0] = bytearray.fromhex(recipe["common_hex"])
            blocks[1] = bytearray.fromhex(recipe["upper_tone_hex"])
            blocks[1][0x16] = resonance
            if args.nominal_one_second and resonance > 0:
                blocks[1][0x18] = 63
            blocks[2] = bytearray(blocks[1])
            capture.validate_blocks(blocks)
            path = recipe_dir / f"lp{slope}-raw{resonance}.syx"
            path.write_bytes(capture.encode_syx(blocks, 0x10))
            patch_paths[slope, resonance] = path
            write_json(path.with_suffix(".json"), {"patch_status": "documented_recipe_reconstruction",
                       "patch_sha256": sha(path), "source_q0_recipe": recipe,
                       "raw_resonance": resonance, "raw_filter_decay": blocks[1][0x18], "common_hex": blocks[0].hex(),
                       "upper_tone_hex": blocks[1].hex(), "inactive_blocks": "Generated engine INIT; Lower duplicates Upper but is inactive"})

    cases = [("checkpoint", slope, raw) for slope in (12, 24) for raw in (0, 63, 64)]
    cases += [("calibrated-identity", slope, 64) for slope in (12, 24)]
    cases += [("lp12-stronger", 12, 64), ("lp24-equal", 24, 64), ("lp24-split", 24, 64)]
    protocol = {"schema_version": 1, "status": "conditional_diagnostic_not_equivalence",
                "training_note": {"note": 36, "on": TRAINING[0], "off": TRAINING[1], "velocity": 127},
                "recipe_policy": ("Nominal one-second sensitivity (raw63); no Q50 recipe or envelope refit" if args.nominal_one_second else
                                  "Q0 onset-corrected recipe learned solely from note36; no Q50 recipe or envelope refit"),
                "raw_parameters": {"cutoff": 47, "key_follow": 74, "filter_depth": 80,
                                   "filter_decay": 63 if args.nominal_one_second else 53},
                "nominal_resonance": "Author's 50% knob label; raw64 is a hypothesis, raw63 is an adjacent-code sensitivity",
                "damping_diagnostics": definitions, "source_revision": REVISION,
                "original_sources_sha256": identities,
                "timing_policy": "Training-note first sample-difference threshold0.001 of local peak; thresholds0.003 and0.01 recorded as sensitivity only. Lag from checkpoint raw64 is shared by every Q50 model at the same slope.",
                "gain_policy": "One RMS scalar per whole render, fitted only from training note at fixed shared lag; also report candidate using exact baseline gain",
                "evaluation_segments_seconds": [[0, 1.45], [2, "decoded hardware end"]],
                "no_per_note_adjustment": True, "no_eq_or_timewarp": True,
                "waveform_null_is_acceptance_measure": False, "stationary_harmonic_estimator_used": False,
                "qualification": "No recording-specific SysEx; original MP3/capture chain unknown; heldout here means excluded from nuisance fitting, not never inspected by DSP development. No validated perceptual pass margins."}
    write_json(output / "protocol-before-rendering.json", protocol)
    audio, receipts = {}, {}
    for family, slope, raw_resonance in cases:
        label = f"{family}-lp{slope}-raw{raw_resonance}"
        folder = output / "renders" / label
        folder.mkdir(parents=True)
        raw = folder / "raw.wav"
        renderer = output / "builds" / family / "SeptumRenderMidi"
        command = [sys.executable, "-B", str(frozen / "Tools/render_midi.py"), "--renderer", str(renderer),
                   "--midi", str(midi), "--syx", str(patch_paths[slope, raw_resonance]), "--output", str(raw),
                   "--tail", "2", "--master-level", "100", "--tempo-policy", "follow-midi", "--allow-unsupported"]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        receipt = json.loads(raw.with_suffix(".render.json").read_text())
        if receipt["replay_event_counts"] != {"note_on": 124, "note_off": 124}:
            raise ValueError("Unexpected note replay counts")
        omitted = receipt["ignored_events"]
        if len(omitted) != 1 or omitted[0]["meta_type"] != 32 or omitted[0]["hex"] != "00":
            raise ValueError("Unexpected omitted event; stop rather than assume identical performance")
        sr, stereo = wavfile.read(raw)
        difference = float(np.max(abs(stereo[:, 0] - stereo[:, 1])))
        if sr != 44100 or not np.isfinite(stereo).all() or difference > np.finfo(np.float32).eps * np.max(abs(stereo)):
            raise ValueError("Raw output failed finite/mono/sample-rate guard")
        audio[family, slope, raw_resonance] = stereo[:, 0].astype(np.float64)
        receipts[family, slope, raw_resonance] = {"render_sha256": sha(raw), "render_manifest_sha256": sha(raw.with_suffix(".render.json")),
                  "renderer_sha256": sha(renderer), "patch_sha256": sha(patch_paths[slope, raw_resonance]),
                  "maximum_channel_difference": difference, "finite": True,
                  "full_scale_samples": int(np.count_nonzero(abs(stereo) >= 1)),
                  "peak": receipt["output"]["peak"], "active_voices_at_end": receipt["output"]["active_voices_at_end"],
                  "frames": len(stereo), "sample_rate": sr, "latency_samples": receipt["output"]["latency_samples"],
                  "degraded_replay": receipt["degraded_replay"], "ignored_events": omitted}
        print("Rendered", label, flush=True)

    guards, lags, onsets = {}, {}, {}
    for slope in (12, 24):
        base = receipts["checkpoint", slope, 64]["render_sha256"]
        calibrated = receipts["calibrated-identity", slope, 64]["render_sha256"]
        if base != calibrated:
            raise ValueError("Calibrated baseline is not byte-identical to checkpoint")
        old = next(r for r in q0["results"] if r["recipe"] == "onset-corrected-trajectory"
                   and r["slope"] == slope and r["family"] == "zero-resonance-k1p2")
        if receipts["checkpoint", slope, 0]["render_sha256"] != old["raw_render_sha256"]:
            raise ValueError("Generated INIT recipe changed effective Q0 audio")
        guards[slope] = {"calibrated_identity_raw_sha256": base, "q0_recipe_identity_raw_sha256": old["raw_render_sha256"]}
        h, c = hardware[slope], audio["checkpoint", slope, 64]
        onsets[slope] = [{"threshold": t, "hardware_sample": onset(h, 44100, t), "baseline_sample": onset(c, 44100, t)}
                         for t in (.001, .003, .01)]
        lags[slope] = onsets[slope][0]["baseline_sample"] - onsets[slope][0]["hardware_sample"]
        if abs(lags[slope]) >= round(.05 * 44100):
            raise ValueError("Training onset lies outside 50ms alignment bound")
    if args.alignment_from:
        prior = json.loads(args.alignment_from.read_text())
        if prior["protocol"]["original_sources_sha256"] != identities or prior["protocol"]["training_note"] != protocol["training_note"]:
            raise ValueError("Supplied alignment does not identify the same sources and training note")
        inherited = prior["protocol"]["shared_candidate_lag_samples"]
        for slope in (12, 24):
            lag = inherited[str(slope)]
            if type(lag) is not int or abs(lag) >= round(.05 * 44100):
                raise ValueError("Invalid inherited alignment")
            lags[slope] = lag
        protocol["alignment_inherited_from"] = {"path": str(args.alignment_from.resolve()), "sha256": sha(args.alignment_from)}
    protocol.update({"shared_candidate_lag_samples": lags, "onset_observations": onsets, "identity_guards": guards})
    write_json(output / "protocol-before-assessment.json", protocol)

    results = []
    for family, slope, resonance in cases:
        if resonance == 0 or family == "calibrated-identity":
            continue
        h, c, lag = hardware[slope], audio[family, slope, resonance], lags[slope]
        a, b = [round(t * 44100) for t in TRAINING]
        gain = assessor.rms(h[a:b]) / assessor.rms(c[a+lag:b+lag])
        control = audio["checkpoint", slope, 64]
        fixed_gain = assessor.rms(h[a:b]) / assessor.rms(control[a+lag:b+lag])
        metrics = {}
        for label, start, end in (("before_training", 0, round(1.45 * 44100)), ("after_training", round(2 * 44100), len(h))):
            start, end = max(start, -lag), min(end, len(c) - lag)
            metrics[label] = {"reference_samples": [start, end],
                "raw": assessor.measure(h[start:end, None], c[start+lag:end+lag, None], 44100),
                "training_gain": assessor.measure(h[start:end, None], c[start+lag:end+lag, None] * gain, 44100),
                "baseline_gain": assessor.measure(h[start:end, None], c[start+lag:end+lag, None] * fixed_gain, 44100)}
        result = {"family": family, "slope": slope, "raw_resonance": resonance,
                  "lag_samples": lag, "gain": gain, "gain_db": 20 * math.log10(gain),
                  "baseline_gain": fixed_gain, "baseline_gain_db": 20 * math.log10(fixed_gain),
                  "receipt": receipts[family, slope, resonance], "metrics": metrics}
        results.append(result)
        write_json(output / "renders" / f"{family}-lp{slope}-raw{resonance}" / "assessment.json", result)
        print(family, slope, resonance, "SC", metrics["after_training"]["training_gain"]["summary"]["spectral_convergence_mean"], flush=True)
    write_json(output / "results.json", {"schema_version": 1, "equivalence_status": "not_established", "protocol": protocol,
               "source_manifest_sha256": sha(output / "source-manifest.json"), "decode_manifest_sha256": sha(private / "decode-manifest.json"),
               "results": results})
    print(output / "results.json")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Bounded common classic-wave phase sensitivity on two frozen DUAL presets.

Eight isolated builds; no shipping changes or best-phase selection. Compare
previous/half return under each identical phase and frozen prefix transform.
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
REVISION = "b0f6c03"
PHASES = (0., .25, .5, .75)
RETURNS = (1., .5)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def prepare_case(cohort, root, identity, out, sources, catalog):
    result_path = root/"results.json"
    result = json.loads(result_path.read_text())
    old = next(c for c in result["cases"] if c["id"] == identity)
    if cohort == "legacy":
        case = old["case"]
        src = root/"cases"/identity
        hardware_hash = old["input_sha256"]["hardware-excerpt-raw.wav"]
    else:
        case = old["comparison"]["case"]
        src = root/"baseline-corpus"/identity
        hardware_hash = old["comparison"]["files"]["hardware-excerpt-raw.wav"]
    dst = out/"inputs"/identity
    dst.mkdir(parents=True)
    candidate = root/"cases"/identity/"gain-0.5.wav"
    previous = root/"cases"/identity/"gain-1.wav"
    receipt_path = candidate.with_suffix(".render.json")
    expected = old["models"]["gain-0.5"]
    audio_key = "raw_sha256" if cohort == "legacy" else "wav_sha256"
    if (sha(candidate) != expected[audio_key] or sha(previous) != old["models"]["gain-1"][audio_key]
            or sha(receipt_path) != expected["receipt_sha256"]):
        raise ValueError("Frozen candidate pin changed")
    receipt = json.loads(receipt_path.read_text())
    for filename, key in (("original-patch.syx", "sysex"), ("reconstructed-performance.mid", "midi")):
        if sha(src/filename) != receipt["inputs"][key]["sha256"]:
            raise ValueError("Frozen input changed")
        shutil.copyfile(src/filename, dst/filename)
    ref = next(r for r in catalog["recordings"] if r["id"] == case["reference_id"])
    mp3 = sources/ref["local_filename"]
    if sha(mp3) != ref["sha256"]:
        raise ValueError("Original MP3 changed")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(mp3), "-ar", "44100", "-ac", "2", "-c:a", "pcm_f32le", str(dst/"hardware-full.wav")]
    subprocess.run(command, check=True)
    sr, audio = wavfile.read(dst/"hardware-full.wav")
    n = round(case["duration_seconds"]*sr)
    if sr != 44100 or case["source_start_seconds"] != 0:
        raise ValueError("Expected original-clock44100Hz inputs")
    wavfile.write(dst/"hardware-excerpt-raw.wav", sr, audio[:n].astype(np.float32))
    if sha(dst/"hardware-excerpt-raw.wav") != hardware_hash:
        raise ValueError("Fresh original excerpt differs from frozen source")
    cal = old["calibration"]["calibration_frames"]
    if cohort == "legacy" and cal != round(n*.25) or cohort == "prospective" and cal != round(.405*sr):
        raise ValueError("Calibration split changed")
    return dict(id=identity, cohort=cohort, case=case, input_directory=str(dst), source_results_sha256=sha(result_path),
                source_reference=ref, source_mp3_sha256=sha(mp3), hardware_excerpt_sha256=hardware_hash,
                decode_command=command, fresh_full_decode_sha256=sha(dst/"hardware-full.wav"),
                input_sha256={key:receipt["inputs"][key]["sha256"] for key in ("midi", "sysex")},
                settings=receipt["settings"], previous_candidate_path=str(previous), half_candidate_path=str(candidate),
                previous_candidate_sha256=sha(previous), half_candidate_sha256=sha(candidate),
                comparison_frames=n, calibration_frames=cal), old


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-run", type=Path, required=True)
    parser.add_argument("--new-run", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    frozen = out/"frozen-source"
    names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", REVISION, "Source/DSP"], cwd=ROOT, text=True).splitlines()
    names += ["Tools/"+name for name in ("RenderMidi.cpp", "build_timbre_candidate.py", "render_midi.py", "assess_hardware_equivalence.py")]
    hashes = {}
    for name in names:
        path = frozen/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(subprocess.check_output(["git", "show", f"{REVISION}:{name}"], cwd=ROOT))
        hashes[name] = sha(path)
    # Existing identical-reference-mask helper is copied and hashed; it is a
    # predeclared diagnostic here, not selected after seeing phase outcomes.
    extra = frozen/"Tools/summarize_reverb_validation.py"
    shutil.copyfile(ROOT/"Tools/summarize_reverb_validation.py", extra)
    hashes["Tools/summarize_reverb_validation.py"] = sha(extra)
    builder = module(frozen/"Tools/build_timbre_candidate.py", "phase_frozen_builder")
    assess = module(frozen/"Tools/assess_hardware_equivalence.py", "assess_hardware_equivalence")
    sys.modules["assess_hardware_equivalence"] = assess
    supplementary = module(extra, "phase_frozen_reference_masks")
    catalog_path = ROOT/"Docs/fidelity/hardware-reference-catalog.json"
    catalog = json.loads(catalog_path.read_text())
    inputs, previous_results = [], {}
    for cohort, directory, name in (("legacy", args.legacy_run.resolve(), "club-bass"),
                                     ("prospective", args.new_run.resolve(), "ambient-sqr-nominal-v100")):
        item, old = prepare_case(cohort, directory, name, out, args.sources.resolve(), catalog)
        inputs.append(item)
        previous_results[name] = old
    inventory_path = ROOT/"Docs/fidelity/source-audits/static-filter-reference-inventory-2026-09-15.json"
    inventory = json.loads(inventory_path.read_text())
    structure = []
    for item, name in zip(inputs, ("Club Bass", "Ambient SQR")):
        row = next(r for r in inventory["references"] if r["name"] == name)
        if row["unmodified_sysex_sha256"] != item["input_sha256"]["sysex"] or row["decoded"]["keyboardMode"] != 1:
            raise ValueError("Expected pinned DUAL patch")
        parts = {}
        for part in ("upper", "lower"):
            tone = row["decoded"][part]
            if tone["mixType"] != 0 or any(tone[o]["wave"] not in range(5) for o in ("osc1", "osc2")):
                raise ValueError("Phase interpretation requires classic MIX oscillators")
            parts[part] = {k:tone[k] for k in ("osc1", "osc2", "balance", "mono", "level", "pan", "delayDepth", "reverbDepth")}
        structure.append(dict(id=item["id"], parts=parts, tone_balance=row["decoded"]["toneBalance"]))
    source_audit = dict(source_sha256=hashes["Source/DSP/SeptumEngine.cpp"],
        accumulation="One already panned/leveled voice sample l/r enters dry once and each effect bus once multiplied by that voice's depth/127. Part enable, expression, tone balance and patch level precede both dry/send paths; no extra DUAL-only gain in accumulation. Reverb takes the summed stereo send and summed wet delay once.",
        cancellation="D=U+L while direct reverb input uses sU*U+sL*L. Unequal sends mean phase cancellation in dry need not cancel the effects input; this is a signal relationship, not evidence of a DUAL scaling bug.",
        policy="reset initializes classic clocks to0 once; note triggering does not reset them. Classic waveform-origin offsets preserve that note-to-note policy, while shifting waveform and BLEP/BLAMP together. Both selected presets use MIX, so canonical SYNC clock is not involved.",
        limits="Code inspection rules out an obvious extra DUAL-only multiplier, not an unmeasured Roland layer/headroom/send conversion.")
    protocol = dict(status="exploratory_phase_sensitivity_after_known_gain_outcomes_no_phase_selection", source_revision=REVISION,
        phases_cycles=PHASES, return_multipliers=RETURNS, classic_phase_vector="All five classic waveform origins set together to the same phase; all other profile fields default.",
        alignment="One previous-return prefix envelope lag bounded±50ms and one prefix RMS gain PER phase; freeze both across the previous/half pair. No candidate-specific gain, no per-note phase/timing fit.",
        evaluation="Primary keeps original per-case split, with identical later support inside each phase pair. Conservative cross-phase-support diagnostic uses reference[cal+2205:n-2205], chosen before scores from the allowed lag bound; no frame crosses calibration.",
        objectives="Retain all five existing summary errors, full measures and reference-only activity-mask diagnostics for every phase/return; no phase is selected. Paired half-minus-previous changes are descriptive.",
        controls="Phase0 previous and half complete WAVs must each be byte-identical to their earlier frozen candidate. Phase0 primary metrics must match existing frozen fixed-previous-gain values.",
        unchanged="Original MP3/excerpt, original complete SysEx, frozen MIDI/events/tempo/master, filters/envelopes/FX network/damping/width/normal note-to-note phase policy; no shipping source edits.",
        limits="Four common phase rotations do not bound all oscillator uncertainty, especially independent oscillator/layer relative phases. Two selected contrary DUAL presets do not disentangle keyboard mode from damping or source/patch/controller/capture uncertainty.",
        inputs=inputs, source_audit=source_audit, patch_structure=structure, catalog_sha256=sha(catalog_path), inventory_sha256=sha(inventory_path),
        source_sha256=hashes, experiment_tool_sha256=sha(__file__))
    save(out/"protocol-before-build-and-score.json", protocol)
    builds = {}
    for phase in PHASES:
        for gain in RETURNS:
            name = f"phase-{round(phase*100):02d}-gain-{gain:g}"
            variant = out/"variant-sources"/name
            shutil.copytree(frozen, variant)
            header = variant/"Source/DSP/SeptumEngine.h"
            original = header.read_text()
            if original.count("reverbWetReturn = 0.8;") != 1:
                raise ValueError("Return anchor changed")
            if gain == .5:
                header.write_text(original.replace("reverbWetReturn = 0.8;", "reverbWetReturn = 0.4;"))
            (out/(name+".diff")).write_text("".join(difflib.unified_diff(original.splitlines(True), header.read_text().splitlines(True), fromfile="b0f6c03/SeptumEngine.h", tofile=name+"/SeptumEngine.h")))
            changed = [path for path in hashes if sha(variant/path) != hashes[path]]
            if changed != ([] if gain == 1 else ["Source/DSP/SeptumEngine.h"]):
                raise ValueError("Unexpected frozen source change")
            profile = out/(name+".json")
            save(profile, dict(version=1, id=name, evidence="Experimental common classic-wave origin sensitivity; original presets and normal phase policy preserved; no selected phase or hardware claim.", waves=dict(phase_cycles=[phase]*5)))
            builder.build_candidate(profile, out/"builds"/name, source_root=variant)
            builds[name] = dict(profile_sha256=sha(profile), manifest_sha256=sha(out/"builds"/name/"manifest.json"), renderer_sha256=sha(out/"builds"/name/"SeptumRenderMidi"))
            print("Built", name, flush=True)
    records = []
    for item in inputs:
        src = Path(item["input_directory"])
        sr, hardware = assess.read_audio(src/"hardware-excerpt-raw.wav")
        n, cal = item["comparison_frames"], item["calibration_frames"]
        for phase in PHASES:
            raw, model_rows = {}, {}
            for gain in RETURNS:
                name = f"phase-{round(phase*100):02d}-gain-{gain:g}"
                dst = out/"audio"/item["id"]/name
                dst.mkdir(parents=True)
                wav = dst/"candidate.wav"
                settings = item["settings"]
                command = [sys.executable, str(frozen/"Tools/render_midi.py"), "--renderer", str(out/"builds"/name/"SeptumRenderMidi"),
                           "--midi", str(src/"reconstructed-performance.mid"), "--syx", str(src/"original-patch.syx"), "--output", str(wav),
                           "--sample-rate", str(settings["sample_rate"]), "--tail", str(settings["tail_seconds"]), "--master-level", str(settings["master_level"]),
                           "--channel", str(settings["midi_channel"]), "--tempo-policy", settings["tempo_policy"]]
                subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
                rate, y = assess.read_audio(wav)
                receipt = json.loads(wav.with_suffix(".render.json").read_text())
                if (rate != sr or len(y) < n or not np.isfinite(y).all() or abs(y).max() >= 1
                        or receipt["ignored_events"] or receipt["output"]["active_voices_at_end"] or receipt["settings"] != settings):
                    raise ValueError("Invalid replay")
                for key in ("midi", "sysex"):
                    if receipt["inputs"][key]["sha256"] != item["input_sha256"][key]:
                        raise ValueError("Input identity changed")
                expected = item["previous_candidate_sha256"] if gain == 1 else item["half_candidate_sha256"]
                if phase == 0 and sha(wav) != expected:
                    raise ValueError("Phase0 is not byte-identical to frozen candidate")
                raw[gain] = y
                model_rows[str(gain)] = dict(wav_sha256=sha(wav), receipt_sha256=sha(wav.with_suffix(".render.json")), renderer_sha256=builds[name]["renderer_sha256"],
                                            command=command, phase0_byte_control=sha(wav)==expected if phase == 0 else None,
                                            complete_frames=len(y), peak=float(abs(y).max()), finite=True, active_voices_at_end=0)
            if raw[1.].shape != raw[.5].shape:
                raise ValueError("Paired output shape changed")
            transform = assess.fit_transform(hardware, raw[1.][:n], sr, cal, .05)
            lag, gain = transform["candidate_lag_samples"], transform["candidate_gain"]
            start, end = max(cal, cal-lag), min(n, n-lag)
            ca, cb = max(0, -lag), min(cal, cal-lag)
            common_start, common_end = cal+2205, n-2205
            if common_end-common_start < sr/4:
                raise ValueError("Conservative phase-common evaluation too short")
            aligned = {str(k):y[start+lag:end+lag]*gain for k, y in raw.items()}
            fixed_mask = supplementary.reference_mask_diagnostics(hardware[start:end], aligned, sr)
            for multiplier, y in raw.items():
                key = str(multiplier)
                model_rows[key]["measurements"] = assess.measure(hardware[start:end], aligned[key], sr)
                model_rows[key]["reference_only_activity"] = fixed_mask[key]
                model_rows[key]["phase_common_reference_support"] = assess.measure(hardware[common_start:common_end], y[common_start+lag:common_end+lag]*gain, sr)
                if phase == 0:
                    old = previous_results[item["id"]]["models"][f"gain-{multiplier:g}"]
                    expected = old["measurements"] if item["cohort"] == "prospective" or multiplier == 1 else old["fixed_production_gain"]
                    if model_rows[key]["measurements"] != expected:
                        raise ValueError("Phase0 metrics differ from frozen fixed-previous-gain scores")
            old_summary = model_rows["1.0"]["measurements"]["summary"]
            half_summary = model_rows["0.5"]["measurements"]["summary"]
            record = dict(id=item["id"], phase_cycles=phase, calibration=transform,
                          calibration_reference_samples=[ca, cb], calibration_candidate_samples=[ca+lag, cb+lag],
                          evaluation_reference_samples=[start, end], evaluation_candidate_samples=[start+lag, end+lag],
                          conservative_phase_common_reference_samples=[common_start, common_end], models=model_rows,
                          paired_half_minus_previous={k:half_summary[k]-old_summary[k] for k in old_summary})
            records.append(record)
            save(out/"results-partial.json", dict(protocol=protocol, builds=builds, comparisons=records))
            print(item["id"], phase, record["paired_half_minus_previous"], flush=True)
    result = dict(protocol=protocol, builds=builds, comparisons=records, all_four_phase0_wavs_byte_identical=True,
                  all_phase0_primary_measures_equal_frozen=True, selected_phase=None, shipping_source_changes=False, equivalence_status="not_established")
    save(out/"results.json", result)
    plot(result, out)


def plot(result, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 2, figsize=(12, 10), constrained_layout=True)
    keys = (("spectral_convergence_mean", "Unmasked spectral convergence"),
            ("envelope_error_db_p95_max", "Envelope P95 error (dB)"),
            ("stereo_side_fraction_error", "Stereo side-fraction error"))
    for col, identity in enumerate(("club-bass", "ambient-sqr-nominal-v100")):
        rows = [r for r in result["comparisons"] if r["id"] == identity]
        for axis, (key, label) in zip(axes[:, col], keys):
            for gain, name in (("1.0", "Previous return"), ("0.5", "Half return")):
                axis.plot(PHASES, [r["models"][gain]["measurements"]["summary"][key] for r in rows], "o-", label=name)
            axis.set(xlabel="Common classic-wave phase (cycles)", ylabel=label, title=identity)
            axis.grid(alpha=.2)
            axis.legend(fontsize=8)
    fig.suptitle("DUAL reverb sensitivity: all frozen phases retained; no phase selection", fontsize=14)
    fig.savefig(out/"phase-sensitivity.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()

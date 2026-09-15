#!/usr/bin/env python3
"""Full4x4 independent Upper/Lower common-wave-origin grid; frozen DSP only."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile
import compare_dual_reverb_phase_sensitivity as common

ROOT = Path(__file__).resolve().parents[1]
PHASES = (0., .25, .5, .75)
RETURNS = (1., .5)
REVISION = "b0f6c03"
sha, save, module = common.sha, common.save, common.module
ANCHOR = """    const double phaseOffset1 = classicParameter (wave1, timbre_.phaseCycles, 0.0);
    const double phaseOffset2 = classicParameter (wave2, timbre_.phaseCycles, 0.0);"""
REPLACEMENT = r'''    // Isolated audit only: two process-fixed layer origins. No note reset.
    const auto auditPhase = [] (const char* name) {
        const char* text = std::getenv (name);
        if (text == nullptr) return 0.0;
        char* end = nullptr;
        const double value = std::strtod (text, &end);
        if (end == text || *end != '\0'
            || (value != 0.0 && value != 0.25 && value != 0.5 && value != 0.75))
            throw std::runtime_error ("Invalid isolated audit phase");
        return value;
    };
    static const double upperOrigin = auditPhase ("SEPTUM_AUDIT_UPPER_PHASE");
    static const double lowerOrigin = auditPhase ("SEPTUM_AUDIT_LOWER_PHASE");
    const double origin = voice.part == Part::Upper ? upperOrigin : lowerOrigin;
    const double originalPhase1 = classicParameter (wave1, timbre_.phaseCycles, 0.0);
    const double originalPhase2 = classicParameter (wave2, timbre_.phaseCycles, 0.0);
    const double phaseOffset1 = origin == 0.0 ? originalPhase1 : frac (originalPhase1 + origin);
    const double phaseOffset2 = origin == 0.0 ? originalPhase2 : frac (originalPhase2 + origin);'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--common-phase-run", type=Path, required=True)
    parser.add_argument("--legacy-run", type=Path, required=True)
    parser.add_argument("--new-run", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    old_root = args.common_phase_run.resolve()
    old_path = old_root/"results.json"
    old = json.loads(old_path.read_text())
    if old["protocol"]["source_revision"] != REVISION or tuple(old["protocol"]["phases_cycles"]) != PHASES:
        raise ValueError("Unexpected earlier common-phase run")
    if sha(ROOT/"Tools/compare_dual_reverb_phase_sensitivity.py") != old["protocol"]["experiment_tool_sha256"]:
        raise ValueError("Shared source/input helpers changed")
    frozen = out/"frozen-source"
    hashes = old["protocol"]["source_sha256"]
    for name, expected in hashes.items():
        src = old_root/"frozen-source"/name
        if sha(src) != expected:
            raise ValueError("Frozen source/helper changed: "+name)
        dst = frozen/name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    builder = module(frozen/"Tools/build_timbre_candidate.py", "layer_phase_builder")
    assess = module(frozen/"Tools/assess_hardware_equivalence.py", "assess_hardware_equivalence")
    sys.modules["assess_hardware_equivalence"] = assess
    supplemental = module(frozen/"Tools/summarize_reverb_validation.py", "layer_phase_masks")
    catalog_path = ROOT/"Docs/fidelity/hardware-reference-catalog.json"
    catalog = json.loads(catalog_path.read_text())
    inputs = []
    for cohort, directory, identity in (("legacy", args.legacy_run.resolve(), "club-bass"),
                                         ("prospective", args.new_run.resolve(), "ambient-sqr-nominal-v100")):
        item, _ = common.prepare_case(cohort, directory, identity, out, args.sources.resolve(), catalog)
        previous = next(r for r in old["protocol"]["inputs"] if r["id"] == identity)
        for key in ("input_sha256", "settings", "hardware_excerpt_sha256", "comparison_frames", "calibration_frames"):
            if item[key] != previous[key]:
                raise ValueError("Inherited input/protocol changed")
        inputs.append(item)
    protocol = dict(status="exploratory_full_layer_phase_grid_after_known_outcomes_no_selection", source_revision=REVISION,
                    phases_upper_cycles=PHASES, phases_lower_cycles=PHASES, return_multipliers=RETURNS,
                    scheduled_render_count=64, symmetry_reduction="None: all16layer pairs at both returns and both presets are rendered. Simultaneous half-cycle inversion is checked afterward without omitting states.",
                    oscillator_scope="Each layer's two classic oscillators share that layer's waveform-origin shift. Normal clocks/note-to-note phase behavior remain unchanged; individual oscillator-relative phases are untested.",
                    build_strategy="Two isolated frozen renderers, differing only in previous0.8 versus half0.4 wet return. Two explicit audit environment values are read once per process and select the Upper/Lower origins. Shipping source/API untouched.",
                    environment_variables=["SEPTUM_AUDIT_UPPER_PHASE", "SEPTUM_AUDIT_LOWER_PHASE"],
                    source_insertion=dict(original=ANCHOR, replacement=REPLACEMENT, extra_includes=["cstdlib", "stdexcept"]),
                    calibration=old["protocol"]["alignment"], evaluation=old["protocol"]["evaluation"], objectives=old["protocol"]["objectives"],
                    controls="All four diagonal common phases at both returns/presets must reproduce the earlier16WAVs and metrics exactly; this includes the original zero-phase fourWAV controls.",
                    limits="No phase selection or source/candidate matching. Two fixed reconstructed DUAL performances; recorded raw revision/controllers/capture and exact performance unknown. Grid does not bound all phases, especially individual oscillator phases.",
                    inherited_source_audit=old["protocol"]["source_audit"], patch_structure=old["protocol"]["patch_structure"],
                    common_phase_result_sha256=sha(old_path), source_sha256=hashes, inputs=inputs,
                    tool_sha256=sha(__file__), shared_helper_sha256=sha(ROOT/"Tools/compare_dual_reverb_phase_sensitivity.py"))
    save(out/"protocol-before-build-and-score.json", protocol)
    builds = {}
    for multiplier in RETURNS:
        identity = f"gain-{multiplier:g}"
        variant = out/"variant-sources"/identity
        shutil.copytree(frozen, variant)
        engine = variant/"Source/DSP/SeptumEngine.cpp"
        original = engine.read_text()
        if original.count(ANCHOR) != 1:
            raise ValueError("Layer phase insertion anchor changed")
        changed = original.replace('#include "ReverbDamping.h"', '#include "ReverbDamping.h"\n#include <cstdlib>\n#include <stdexcept>')
        changed = changed.replace(ANCHOR, REPLACEMENT)
        engine.write_text(changed)
        header = variant/"Source/DSP/SeptumEngine.h"
        before = header.read_text()
        if before.count("reverbWetReturn = 0.8;") != 1:
            raise ValueError("Return anchor changed")
        if multiplier == .5:
            header.write_text(before.replace("reverbWetReturn = 0.8;", "reverbWetReturn = 0.4;"))
        expected_changes = {"Source/DSP/SeptumEngine.cpp"} | ({"Source/DSP/SeptumEngine.h"} if multiplier == .5 else set())
        actual_changes = {name for name in hashes if sha(variant/name) != hashes[name]}
        if actual_changes != expected_changes:
            raise ValueError("Unexpected isolated source mutation")
        diff = "".join(difflib.unified_diff(original.splitlines(True), changed.splitlines(True), fromfile="b0f6c03/SeptumEngine.cpp", tofile=identity+"/SeptumEngine.cpp"))
        diff += "".join(difflib.unified_diff(before.splitlines(True), header.read_text().splitlines(True), fromfile="b0f6c03/SeptumEngine.h", tofile=identity+"/SeptumEngine.h"))
        (out/(identity+".diff")).write_text(diff)
        profile = out/(identity+".json")
        save(profile, dict(version=1, id="layer-phase-"+identity, evidence="Experimental isolated layer waveform origins supplied by two pinned process environment values; no other timbre profile fields."))
        builder.build_candidate(profile, out/"builds"/identity, source_root=variant)
        builds[identity] = dict(manifest_sha256=sha(out/"builds"/identity/"manifest.json"), renderer_sha256=sha(out/"builds"/identity/"SeptumRenderMidi"), diff_sha256=sha(out/(identity+".diff")), profile_sha256=sha(profile))
        print("Built", identity, flush=True)
    records = []
    for item in inputs:
        src = Path(item["input_directory"])
        sr, hardware = assess.read_audio(src/"hardware-excerpt-raw.wav")
        n, cal = item["comparison_frames"], item["calibration_frames"]
        for upper in PHASES:
            for lower in PHASES:
                phase_name = f"upper-{round(upper*100):02d}-lower-{round(lower*100):02d}"
                rows, raw = {}, {}
                for multiplier in RETURNS:
                    model = f"gain-{multiplier:g}"
                    dst = out/"audio"/item["id"]/phase_name/model
                    dst.mkdir(parents=True)
                    wav = dst/"candidate.wav"
                    settings = item["settings"]
                    command = [sys.executable, str(frozen/"Tools/render_midi.py"), "--renderer", str(out/"builds"/model/"SeptumRenderMidi"),
                               "--midi", str(src/"reconstructed-performance.mid"), "--syx", str(src/"original-patch.syx"), "--output", str(wav),
                               "--sample-rate", str(settings["sample_rate"]), "--tail", str(settings["tail_seconds"]), "--master-level", str(settings["master_level"]),
                               "--channel", str(settings["midi_channel"]), "--tempo-policy", settings["tempo_policy"]]
                    environment = {"SEPTUM_AUDIT_UPPER_PHASE":format(upper, ".17g"), "SEPTUM_AUDIT_LOWER_PHASE":format(lower, ".17g")}
                    subprocess.run(command, env={**os.environ, **environment}, check=True, stdout=subprocess.DEVNULL)
                    rate, y = assess.read_audio(wav)
                    receipt = json.loads(wav.with_suffix(".render.json").read_text())
                    if (rate != sr or len(y) < n or not np.isfinite(y).all() or receipt["ignored_events"]
                            or receipt["output"]["active_voices_at_end"] or receipt["settings"] != settings):
                        raise ValueError("Invalid grid replay")
                    for key in ("midi", "sysex"):
                        if receipt["inputs"][key]["sha256"] != item["input_sha256"][key]:
                            raise ValueError("Input identity changed")
                    diagonal = None
                    if upper == lower:
                        previous = next(r for r in old["comparisons"] if r["id"] == item["id"] and r["phase_cycles"] == upper)
                        diagonal = sha(wav) == previous["models"][str(multiplier)]["wav_sha256"]
                        if not diagonal:
                            raise ValueError("Diagonal phase failed complete PCM identity")
                    raw[multiplier] = y
                    rows[str(multiplier)] = dict(command=command, experiment_environment=environment, wav_sha256=sha(wav), receipt_sha256=sha(wav.with_suffix(".render.json")),
                                                renderer_sha256=builds[model]["renderer_sha256"], diagonal_byte_control=diagonal,
                                                frames=len(y), peak=float(abs(y).max()), finite=True, active_voices_at_end=0,
                                                samples_at_or_above_full_scale=int(np.count_nonzero(abs(y) >= 1)), reaches_output_limiter_knee=bool(abs(y).max() > .9))
                if raw[1.].shape != raw[.5].shape:
                    raise ValueError("Grid pair shape differs")
                transform = assess.fit_transform(hardware, raw[1.][:n], sr, cal, .05)
                lag, gain = transform["candidate_lag_samples"], transform["candidate_gain"]
                start, end = max(cal, cal-lag), min(n, n-lag)
                ca, cb = max(0, -lag), min(cal, cal-lag)
                common_start, common_end = cal+2205, n-2205
                aligned = {str(k):y[start+lag:end+lag]*gain for k, y in raw.items()}
                masks = supplemental.reference_mask_diagnostics(hardware[start:end], aligned, sr)
                for multiplier, y in raw.items():
                    key = str(multiplier)
                    rows[key]["measurements"] = assess.measure(hardware[start:end], aligned[key], sr)
                    rows[key]["reference_only_activity"] = masks[key]
                    rows[key]["phase_common_reference_support"] = assess.measure(hardware[common_start:common_end], y[common_start+lag:common_end+lag]*gain, sr)
                    if upper == lower and rows[key]["measurements"] != previous["models"][key]["measurements"]:
                        raise ValueError("Diagonal phase metrics changed")
                baseline, half = rows["1.0"]["measurements"]["summary"], rows["0.5"]["measurements"]["summary"]
                record = dict(id=item["id"], upper_phase_cycles=upper, lower_phase_cycles=lower, calibration=transform,
                              calibration_reference_samples=[ca, cb], calibration_candidate_samples=[ca+lag, cb+lag],
                              evaluation_reference_samples=[start, end], evaluation_candidate_samples=[start+lag, end+lag],
                              conservative_phase_common_reference_samples=[common_start, common_end], models=rows,
                              paired_half_minus_previous={k:half[k]-baseline[k] for k in baseline})
                records.append(record)
                save(out/"results-partial.json", dict(protocol=protocol, builds=builds, comparisons=records))
                print(item["id"], upper, lower, "P95delta", record["paired_half_minus_previous"]["envelope_error_db_p95_max"], flush=True)
    symmetry = []
    for identity in ("club-bass", "ambient-sqr-nominal-v100"):
        for upper in (0., .25):
            for lower in PHASES:
                mirror = ((upper+.5)%1, (lower+.5)%1)
                for multiplier in RETURNS:
                    waves = []
                    for u, l in ((upper, lower), mirror):
                        path = out/"audio"/identity/f"upper-{round(u*100):02d}-lower-{round(l*100):02d}"/f"gain-{multiplier:g}"/"candidate.wav"
                        _, y = wavfile.read(path)
                        waves.append(y)
                    a, b = waves
                    symmetry.append(dict(id=identity, return_multiplier=multiplier, first_pair=[upper, lower], simultaneous_half_cycle_pair=mirror,
                                         exact_opposite_pcm=bool(np.array_equal(a, -b)), maximum_absolute_pcm_sum=float(abs(a.astype(float)+b.astype(float)).max())))
    result = dict(protocol=protocol, builds=builds, comparisons=records, polarity_symmetry=symmetry,
                  all16_diagonal_wavs_and_scores_equal_prior=True, total_renders=64, selected_phase=None,
                  shipping_source_changes=False, equivalence_status="not_established")
    save(out/"results.json", result)
    plot(result, out)


def plot(result, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 2, figsize=(11, 11), constrained_layout=True)
    for col, identity in enumerate(("club-bass", "ambient-sqr-nominal-v100")):
        rows = [r for r in result["comparisons"] if r["id"] == identity]
        for axis, metric, label in zip(axes[:, col], ("spectral_convergence_mean", "envelope_error_db_p95_max", "reference_only_log"),
                                       ("SC change", "Envelope P95 change (dB)", "Reference-only log error change (dB)")):
            values = np.empty((4, 4))
            for row in rows:
                u, l = PHASES.index(row["upper_phase_cycles"]), PHASES.index(row["lower_phase_cycles"])
                values[l, u] = (row["paired_half_minus_previous"][metric] if metric != "reference_only_log" else
                                row["models"]["0.5"]["reference_only_activity"]["summary"]["log_spectral_error_db_mean"]-row["models"]["1.0"]["reference_only_activity"]["summary"]["log_spectral_error_db_mean"])
            limit = max(abs(values).max(), 1e-8)
            picture = axis.imshow(values, vmin=-limit, vmax=limit, cmap="RdBu_r", origin="lower")
            for l in range(4):
                for u in range(4):
                    axis.text(u, l, f"{values[l,u]:.3g}", ha="center", va="center", color="white" if abs(values[l,u]) > limit*.55 else "black", fontsize=9)
            axis.set(xticks=range(4), yticks=range(4), xticklabels=PHASES, yticklabels=PHASES,
                     xlabel="Upper common phase", ylabel="Lower common phase", title=identity+"\n"+label)
            fig.colorbar(picture, ax=axis, shrink=.7)
    fig.suptitle("Half minus previous return across the full layer-phase grid\nNegative is closer; all states retained, no phase selection", fontsize=14)
    fig.savefig(out/"layer-phase-sensitivity.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()

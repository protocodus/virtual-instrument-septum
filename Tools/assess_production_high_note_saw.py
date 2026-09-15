#!/usr/bin/env python3
"""Measure existing full-engine dry outputs on the frozen five W4 passages.

Read/decode/measure only: no rendering, phase/frequency/gain search or candidate
coefficient fitting. Original hardware masks are reused without model selection.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile
import analyze_deepsonic_saw_aliases as alias
import fit_high_note_saw_wrap_kernels as wrap
from render_midi import parse_smf
from generate_timbre_capture import decode_syx

ROOT = Path(__file__).resolve().parents[1]
AUDITS = ROOT / "Docs/fidelity/source-audits"
W4 = AUDITS / "deepsonic-saw-asymmetric-kernels-2026-09-15.json"
PHASE = AUDITS / "dry-phase-sensitivity-2026-09-15.json"
CATALOG = AUDITS / "deepsonic-acquisition-2026-09-15.json"
RECIPE = AUDITS / "dry-end-to-end-2026-09-15.json"
WAV_HASH = {12: "e960507e6c9404554980eceae90d51e1253347d22fbe7e661f48730dce7484da",
            24: "dd505cd6a020417a5b86c52083a8dd6091b3f18edbad7c28a0de431df2356a33"}
PATCH_HASH = {12: "25eeed2e391f033894a009d3d6c6f3289d35f1a01f323a8ade63c029e03ba003",
              24: "c5d12851f4798e8300341a3ccd0b8abe46782f82b3b38cbcc5c4204fd04a173e"}
RENDERER_HASH = "0e69118d0dab0928793ef3b59208fddf43b7bd56d982f2c053d3c0ad9f15b646"
MIDI_HASH = "21ea21b9ba3ba14cc205931134fb7a320b09e67821bd3a3c70f97fa2e8b5d99a"
SR = 44100


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def checked(path, expected=None):
    path = Path(path).resolve()
    actual = sha(path)
    if expected is not None and actual != expected:
        raise ValueError(f"Hash mismatch: {path}")
    return {"path": str(path), "sha256": actual, "bytes": path.stat().st_size}


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def source_provenance(engine):
    checkpoint = json.loads((engine / "checkpoint.json").read_text())
    renderer_root = engine / "renderers/production"
    manifest = json.loads((renderer_root / "manifest.json").read_text())
    if checkpoint["revision"] != "b0f6c03" or manifest["profile"]["enabled_sections"]:
        raise ValueError("Not the frozen default production baseline")
    frozen = {p: checked(renderer_root / p, h)
              for p, h in manifest["frozen_sha256"].items()}
    differences = {}
    current = {}
    for path, expected in manifest["source"]["input_sha256"].items():
        original = subprocess.check_output(["git", "show", f"b0f6c03:{path}"], cwd=ROOT)
        if digest(original) != expected or checkpoint["source_sha256"][path] != expected:
            raise ValueError(f"Checkpoint source mismatch: {path}")
        value = (ROOT / path).read_bytes()
        current[path] = digest(value)
        if value == original:
            continue
        # Only the known, inactive dry-patch return correction is permitted.
        def without_comments(b):
            return re.sub(r"//[^\n]*", "", b.decode()).split()
        corrected = original.replace(b"reverbWetReturn = 0.8", b"reverbWetReturn = 0.4")
        if path != "Source/DSP/SeptumEngine.h" or without_comments(value) != without_comments(corrected):
            raise ValueError(f"Current DSP has another change: {path}")
        differences[path] = "".join(difflib.unified_diff(original.decode().splitlines(True),
                                      value.decode().splitlines(True), fromfile="b0f6c03", tofile="current"))
    return dict(checkpoint=checked(engine / "checkpoint.json"),
                build_manifest=checked(renderer_root / "manifest.json"),
                checkpoint_revision=manifest["source"]["head"],
                current_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                frozen_inputs=frozen, original_input_sha256=manifest["source"]["input_sha256"],
                current_input_sha256=current, allowed_inactive_dry_difference=differences,
                renderer=checked(renderer_root / "SeptumRenderMidi", RENDERER_HASH),
                integration=manifest["integration"], profile=manifest["profile"])


def fixed_aliases(hardware, model, frozen_lines):
    def index(observation):
        return {r["parent_harmonic"]: r for r in observation["tested_alias_lines"]
                if r["rate_hypothesis_hz"] == 44100}
    a, b = index(hardware), index(model)
    rows = []
    for frozen in frozen_lines:
        h = frozen["parent_harmonic"]
        x, y = a[h], b[h]
        rows.append(dict(parent_harmonic=h, expected_hz=frozen["expected_hz"],
                         hardware=x, engine=y,
                         engine_minus_hardware_db=y["relative_h1_db"]-x["relative_h1_db"],
                         interpretation="resolved_line_pair" if x["passes_line_threshold"] and y["passes_line_threshold"]
                         else "fixed_search_maximum_proxy; unresolved observation retained"))
    differences = np.array([r["engine_minus_hardware_db"] for r in rows])
    return dict(mask="unchanged prior LP12 hardware-qualified 44.1 kHz first-fold line IDs",
                line_count=len(rows), hardware_resolved_count=sum(r["hardware"]["passes_line_threshold"] for r in rows),
                engine_resolved_count=sum(r["engine"]["passes_line_threshold"] for r in rows),
                complete_mask_search_maximum_rms_difference_db=float(np.sqrt(np.mean(differences**2))),
                complete_mask_search_maximum_median_signed_difference_db=float(np.median(differences)),
                lines=rows)


def spectral_observation(x, note):
    result = alias.measure(x, .04, note, 0.)
    # All 44.1 kHz observations remain, including failed/masked-out lines.
    return {k: ([r for r in v if r["rate_hypothesis_hz"] == 44100]
                if k == "tested_alias_lines" else v)
            for k, v in result.items()
            if k not in ("null_lines_passing", "diagnostic_nonharmonic_peaks")}


def plot(result, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 5, figsize=(15, 6.4), sharex=True, sharey=True,
                             constrained_layout=True)
    for row, slope in enumerate(result["slopes"]):
        for col, window in enumerate(slope["windows"]):
            ax = axes[row, col]
            values = window["harmonics"]
            ax.plot(range(1, 9), values["hardware_relative_h1_db"], "o-", color="#212121", label="Hardware")
            ax.plot(range(1, 9), values["model_relative_h1_db"], "o-", color="#c04e28", label="Full production")
            passage = window["passage"]
            ax.set_title(f"MIDI {passage['note']} +{round(1000*passage['offset_seconds'])} ms\n"
                         f"H2–H8 RMS {values['h2_to_h8_rms_error_db']:.2f} dB", fontsize=10)
            ax.set_ylim(-50, 2)
            ax.set_xticks(range(1, 9))
            ax.grid(alpha=.2)
            if col == 0:
                ax.set_ylabel(f"LP{slope['slope']} · dB relative to H1")
            if row == 1:
                ax.set_xlabel("Harmonic")
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Existing full-engine dry Saw baseline · frozen original-MIDI windows\n"
                 "Quadrature magnitudes; no phase/gain/frequency fit. Second note91 window overlaps first by20 ms.", fontsize=12)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources", type=Path, required=True, help="Cached hash-pinned original MP3 and MIDI")
    p.add_argument("--engine-root", type=Path, required=True, help="Existing envelope-hypothesis/dry-v2 directory")
    p.add_argument("--output", type=Path, required=True, help="New output directory; never overwrites audio")
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    engine = args.engine_root.resolve()
    prior = json.loads(W4.read_text())
    phase = json.loads(PHASE.read_text())
    catalog = json.loads(CATALOG.read_text())
    recipes = json.loads(RECIPE.read_text())["recipes"]
    passages = [prior["protocol"]["training"]] + prior["protocol"]["evaluation"]
    old_poly = next(r for r in prior["baseline_models"] if r["id"] == "polyblep")
    masks = [s["aliases"]["lines"] for s in old_poly["scores"]]
    if [len(m) for m in masks] != [9, 9, 8, 11, 13]:
        raise ValueError("Frozen mask changed")
    dependencies = {name: checked(ROOT / "Tools" / name, h)
                    for name, h in prior["dependency_sha256"].items()}
    dependencies["generate_timbre_capture.py"] = checked(ROOT / "Tools/generate_timbre_capture.py")
    controls = source_provenance(engine)
    calibrations = {r["slope"]: dict(gain=r["hardware_training_gain"], lag_samples=r["hardware_lag_samples"])
                    for r in phase["results"] if r["phase_cycles"] == 0}
    if calibrations != {12: dict(gain=4.137125725839024, lag_samples=-1406),
                         24: dict(gain=3.870462967942607, lag_samples=-1406)}:
        raise ValueError("Frozen calibration changed")
    protocol = dict(status="existing_full_engine_baseline_only; exploratory_windows; no equivalence claim",
                    sample_rate=SR, window_samples=3528, passages=passages, calibrations=calibrations,
                    timing="hardware[a:b] versus gain*engine[a-1406:b-1406,0]; no further 93-sample shift",
                    physical_lag="round(93 renderer latency + 44.1 nominal1ms filter attack - .035*44100 physical source decay-start convention) = -1406",
                    calibration_hardware_samples=[66150, 85444], calibration_engine_samples=[64744, 84038],
                    channel="Original mono versus engine left; no stereo downmix, phase fit or output normalization",
                    fundamental="Fixed nominal equal-tempered original MIDI; no local frequency refinement",
                    harmonics="Unchanged quadrature/quadratic-ramp fit below20kHz; H2-H8/H1 fixed in every window",
                    aliases="Inherited residual-Hann NFFT262144; +/-6Hz local maximum; >37.5Hz harmonic exclusion; original LP12 mask",
                    alias_guard="interior maximum, prominence >=12dB, >=-75dBc; retain all failures and counts",
                    lp24="Secondary same-window/same-LP12-mask observation; LP24 hardware validity independently retained",
                    raw_residual="Direct fixed-gain/fixed-phase mean squared error divided by hardware mean square; phase-sensitive diagnostic only",
                    overlap="Second note91 window overlaps first by882samples/20ms; not independent held-out validation",
                    forbidden_actions=["new rendering", "frequency/phase/timing/gain optimization", "W4 coefficient fit", "DSP edits"],
                    recipe_status="original performance MIDI plus reconstructed physical patch; no original SysEx or capture transfer known")
    dump(out / "protocol-before-measurement.json", protocol)
    ffmpeg = Path(shutil.which("ffmpeg")).resolve()
    provenance = dict(script=checked(__file__), command=[sys.executable, *sys.argv], dependencies=dependencies,
                      prior_w4=checked(W4), frozen_calibration=checked(PHASE), catalog=checked(CATALOG), recipe_source=checked(RECIPE),
                      production=controls, decoder=dict(**checked(ffmpeg), version=subprocess.check_output(
                          [str(ffmpeg), "-version"], text=True).splitlines()[0]))
    midi = checked(args.sources / Path(prior["original_midi"]["path"]).name, MIDI_HASH)
    provenance["original_midi"] = midi
    active, notes = {}, []
    parsed = parse_smf(Path(midi["path"]).read_bytes())
    for event in parsed["events"]:
        if event["kind"] != "midi":
            continue
        message = bytes.fromhex(event["hex"])
        status, key = message[0] & 240, (message[0] & 15, message[1])
        if status == 144 and message[2]:
            if key in active:
                raise ValueError("Overlapping same-key MIDI")
            active[key] = (event["sample"], message[2])
        elif status in (128, 144):
            on, velocity = active.pop(key)
            notes.append(dict(note=key[1], on=on, off=event["sample"], velocity=velocity))
        else:
            raise ValueError("Unexpected non-note performance message")
    if active or len(notes) != 124:
        raise ValueError("Original finite note sequence changed")
    for passage in passages:
        expected = dict(note=passage["note"], on=round(passage["midi_onset_seconds"]*SR),
                        off=round(passage["midi_off_seconds"]*SR), velocity=passage["velocity"])
        if notes.count(expected) != 1:
            raise ValueError("Frozen passage MIDI gate mismatch")
    result = dict(protocol=protocol, provenance=provenance, slopes=[],
                  prior_oscillator_only_polyblep=dict(qualification="Copied prior fitted gain/phase/DC oscillator-only comparator; NOT full production; no refit",
                                                     scores=old_poly["scores"]), equivalence_status="not_established")
    for slope in (12, 24):
        name = f"roland_sh-201_-_filter_demo_-_lpf{slope}_q000.mp3"
        asset = next(a for a in catalog["assets"] if Path(a["path"]).name == name)
        original = checked(args.sources / name, asset["sha256"])
        original["url"] = asset["url"]
        decoded = out / f"hardware-lp{slope}.wav"
        command = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-i", original["path"], "-c:a", "pcm_f32le", str(decoded)]
        subprocess.run(command, check=True)
        sr, hardware = wavfile.read(decoded)
        if sr != SR or hardware.ndim != 1 or hardware.dtype != np.float32 or not np.isfinite(hardware).all():
            raise ValueError("Unexpected original decode")
        folder = engine / f"audio/production/lp{slope}"
        receipt = json.loads((folder / "candidate.render.json").read_text())
        wave_info = checked(folder / "candidate.wav", WAV_HASH[slope])
        patch_info = checked(folder / "patch.syx", PATCH_HASH[slope])
        recipe = recipes[f"onset-corrected-trajectory-lp{slope}"]
        blocks = decode_syx((folder / "patch.syx").read_bytes())
        if bytes(blocks[0]).hex() != recipe["common_hex"] or bytes(blocks[1]).hex() != recipe["upper_tone_hex"]:
            raise ValueError("Exact reconstructed raw recipe changed")
        performance = checked(folder / "performance.mid", MIDI_HASH)
        for name, item in (("midi", performance), ("sysex", patch_info), ("renderer", controls["renderer"])):
            if receipt["inputs"][name]["sha256"] != item["sha256"]:
                raise ValueError("Receipt input identity mismatch")
        if receipt["output"]["sha256"] != wave_info["sha256"] or receipt["output"]["active_voices_at_end"] != 0:
            raise ValueError("Receipt output mismatch")
        ignored = receipt["ignored_events"]
        if len(ignored) != 1 or ignored[0]["meta_type"] != 32 or ignored[0]["hex"] != "00":
            raise ValueError("Unexpected omitted performance data")
        patch = receipt["output"]["initial_patch"]
        if patch["delay_on"] or patch["reverb_on"] or patch["arpeggio_on"]:
            raise ValueError("Expected dry non-arpeggiated patch")
        sr, audio = wavfile.read(folder / "candidate.wav")
        if sr != SR or audio.dtype != np.float32 or audio.ndim != 2 or audio.shape[1] != 2 or not np.isfinite(audio).all():
            raise ValueError("Unexpected full-engine audio")
        if len(audio) != receipt["output"]["frames"] or receipt["replay_event_counts"] != {"note_on": 124, "note_off": 124}:
            raise ValueError("Finite performance coverage changed")
        gain, lag = calibrations[slope]["gain"], calibrations[slope]["lag_samples"]
        rows = []
        for i, passage in enumerate(passages):
            a, b = passage["start_sample"], passage["end_sample"]
            x = hardware[a:b].astype(np.float64)
            y = audio[a+lag:b+lag, 0].astype(np.float64)*gain
            if len(x) != 3528 or len(y) != 3528:
                raise ValueError("Changed paired support")
            sample_hash = digest(x.tobytes())
            if slope == 12 and sample_hash != passage["sample_sha256"]:
                raise ValueError("Original W4 hardware samples changed")
            harmonics = wrap.compare_harmonics(x, y, passage["note"])
            hx, hy = spectral_observation(x, passage["note"]), spectral_observation(y, passage["note"])
            lines = fixed_aliases(hx, hy, masks[i])
            if slope == 12:
                old = old_poly["scores"][i]
                if not np.allclose(harmonics["hardware_relative_h1_db"], old["harmonics"]["hardware_relative_h1_db"], atol=1e-9, rtol=0):
                    raise ValueError("Hardware harmonic estimator changed")
                for fresh, saved in zip(lines["lines"], masks[i]):
                    if abs(fresh["hardware"]["relative_h1_db"]-saved["hardware_dbc"]) > 1e-9:
                        raise ValueError("Hardware alias estimator changed")
            rows.append(dict(passage=passage, hardware_float64_sample_sha256=sample_hash,
                             engine_raw_float32_sample_sha256=digest(audio[a+lag:b+lag, 0].tobytes()),
                             engine_samples=[a+lag, b+lag], hardware_observation=hx, engine_observation=hy,
                             harmonics=harmonics, aliases=lines,
                             fixed_gain_h1_engine_minus_hardware_db=float(20*np.log10(hy["fitted_h1_amplitude"]/hx["fitted_h1_amplitude"])),
                             fixed_phase_relative_error_power=float(np.mean((y-x)**2)/np.mean(x*x)),
                             fixed_phase_mean_removed_relative_error_power=float(np.mean(((y-y.mean())-(x-x.mean()))**2)/np.var(x)),
                             window_rms_engine_over_hardware=float(np.sqrt(np.mean(y*y)/np.mean(x*x)))))
        result["slopes"].append(dict(slope=slope, original_mp3=original, decoded=checked(decoded), decode_command=command,
                engine_wav=wave_info, engine_pcm_float32_sha256=digest(audio.tobytes()),
                engine_peak=float(np.max(np.abs(audio))), engine_max_channel_difference=float(np.max(np.abs(audio[:,0]-audio[:,1]))),
                engine_patch=dict(**patch_info, exact_bytes_hex=(folder / "patch.syx").read_bytes().hex(), decoded_summary=patch, reconstructed_recipe=recipe),
                render_receipt=checked(folder / "candidate.render.json"), original_midi_copy=performance,
                settings=receipt["settings"], event_counts=receipt["replay_event_counts"], midi_metadata=receipt["midi"],
                omitted_events=ignored, no_future_queued_midi=receipt["midi"]["end_sample"] < len(audio), windows=rows))
    plot(result, out / "harmonics.png")
    result["plot"] = checked(out / "harmonics.png")
    dump(out / "results.json", result)
    for slope in result["slopes"]:
        print(slope["slope"], [(r["passage"]["note"], round(r["harmonics"]["h2_to_h8_rms_error_db"], 3),
                                  round(r["aliases"]["complete_mask_search_maximum_rms_difference_db"], 3),
                                  r["aliases"]["engine_resolved_count"]) for r in slope["windows"]])


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Assess frozen dry-envelope renderers with physical delay and training-only gain.

No curve, event, pitch, per-note gain or recording EQ is fitted. Mathematical
integration verification is a separate required evidence artifact.
"""
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
SOURCE_HASHES = {
    12: "28e241247a0efb217eb4cb7154cc3b69713fcebca781639c45b8904b3dc8615b",
    24: "ebb6fa4e12136028bbff614633095aa510c31654fcce840af5e3a85b3a469d90",
}
MIDI_HASH = "21ea21b9ba3ba14cc205931134fb7a320b09e67821bd3a3c70f97fa2e8b5d99a"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--renders", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads(args.renders.read_text())
    analysis_tools = out / "analysis-tools"
    analysis_tools.mkdir()
    tool_hashes = {}
    for name in ("assess_hardware_equivalence.py", "analyze_deepsonic_filter.py",
                 "analyze_deepsonic_chord_envelope.py", "render_midi.py"):
        path = analysis_tools / name
        shutil.copyfile(ROOT / "Tools" / name, path)
        tool_hashes[name] = sha(path)
    (out / "experiment-script.py").write_bytes(Path(__file__).read_bytes())
    sys.path.insert(0, str(analysis_tools))
    import assess_hardware_equivalence as assessor
    import analyze_deepsonic_filter as harmonics
    import analyze_deepsonic_chord_envelope as chords
    import render_midi

    q0 = json.loads((ROOT / "Docs/fidelity/source-audits/dry-end-to-end-2026-09-15.json").read_text())
    train = q0["protocol"]["training_note"]
    isolated = q0["protocol"]["isolated_validation_notes"]
    midi = args.sources / "deepsonic_-_filter_demo_-_comparsion_sequence.mid"
    if sha(midi) != MIDI_HASH:
        raise ValueError("Original MIDI identity changed")
    parsed = render_midi.parse_smf(midi.read_bytes())
    held, notes = {}, []
    for event in parsed["events"]:
        if event["kind"] != "midi":
            continue
        m = bytes.fromhex(event["hex"])
        if m[0] == 0x90 and m[2]:
            held[m[1]] = event["sample"] / 44100
        elif m[0] in (0x80, 0x90):
            notes.append({"note": m[1], "on": held.pop(m[1]), "off": event["sample"] / 44100})
        else:
            raise ValueError("Unexpected channel message in original MIDI")
    chord_intervals = []
    for on, pitches, target in chords.CHORDS:
        matching = [n for n in notes if n["on"] == on and n["note"] in pitches]
        if len(matching) != 3 or len({n["off"] for n in matching}) != 1:
            raise ValueError("Declared chord does not match original MIDI")
        chord_intervals.append({"on": on, "off": matching[0]["off"], "notes": pitches, "target": target})
    hardware, decode = {}, {"files": []}
    decoder = shutil.which("ffmpeg")
    if not decoder:
        raise ValueError("ffmpeg required")
    decode.update({"binary": decoder, "binary_sha256": sha(decoder),
                   "version": subprocess.check_output([decoder, "-version"], text=True).splitlines()[0]})
    cache = out / "source-cache"
    cache.mkdir()
    for slope in (12, 24):
        mp3 = args.sources / f"roland_sh-201_-_filter_demo_-_lpf{slope}_q000.mp3"
        if sha(mp3) != SOURCE_HASHES[slope]:
            raise ValueError("Original MP3 identity changed")
        path = cache / mp3.with_suffix(".wav").name
        command = [decoder, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(mp3), "-c:a", "pcm_f32le", str(path)]
        subprocess.run(command, check=True)
        sr, audio = wavfile.read(path)
        if sr != 44100 or audio.ndim != 1 or not np.isfinite(audio).all():
            raise ValueError("Unexpected hardware WAV format")
        hardware[slope] = audio.astype(float)
        decode["files"].append({"command": command, "source_sha256": sha(mp3), "decoded_sha256": sha(path)})
    save(cache / "decode-manifest.json", decode)

    protocol = {"source_render_manifest_sha256": sha(args.renders), "definitions": manifest["definitions"],
        "q0_protocol_source_sha256": sha(ROOT / "Docs/fidelity/source-audits/dry-end-to-end-2026-09-15.json"),
        "midi_sha256": MIDI_HASH, "tool_sha256": tool_hashes, "script_sha256": sha(__file__),
        "training_note": train, "isolated_notes": isolated, "chords": chord_intervals,
        "alignment": "Lag=round(renderer latency93 + nominal attack44.1 - physical decay start delay*44100). Production uses35ms; each30/35/40ms fixture uses its paired physical delay. No delay is fitted from validation.",
        "gain": "One RMS scalar per complete render from original note36 only; fixed throughout other notes, chords and whole-sequence comparison",
        "old_onset_lag_sensitivity": {"12": -1375, "24": -1438},
        "harmonic_policy": "Independent 80ms harmonic/chord quadrature fits to hardware and candidate. Power residual<=1% and condition<=100. Hardware-only harmonic floor-45dB. Chords additionally require isolated H1/H2/H3 with noise-proxySNR>=20dB. No harmonic determines a gain or curve.",
        "equivalence_status": "not_established", "integration_verification": "Required separately before interpreting physical-model scores"}
    save(out / "protocol-before-assessment.json", protocol)
    definitions = {d["id"]: d for d in manifest["definitions"]}
    all_audio, results = {}, []

    def score(h, c, gain, lag, start, end):
        a, b = max(round(start * 44100), -lag), min(round(end * 44100), len(c) - lag, len(h))
        return {"reference_samples": [a, b], "measurements": assessor.measure(h[a:b, None], c[a+lag:b+lag, None] * gain, 44100)}

    for item in manifest["renders"]:
        name, slope = item["id"], int(item["case"][2:])
        path = Path(item["wav"])
        if sha(path) != item["sha256"] or item["midi_sha256"] != MIDI_HASH:
            raise ValueError("Render or MIDI identity changed")
        receipt = json.loads(path.with_suffix(".render.json").read_text())
        omitted = receipt["ignored_events"]
        if len(omitted) != 1 or omitted[0]["meta_type"] != 32 or omitted[0]["hex"] != "00":
            raise ValueError("Unexpected omitted event")
        if receipt["output"]["active_voices_at_end"] or receipt["replay_event_counts"] != {"note_on": 124, "note_off": 124}:
            raise ValueError("Invalid note replay/tail")
        sr, stereo = wavfile.read(path)
        difference = float(np.max(abs(stereo[:, 0] - stereo[:, 1])))
        if sr != 44100 or not np.isfinite(stereo).all() or difference > np.finfo(np.float32).eps * np.max(abs(stereo)):
            raise ValueError("Render audio format failed")
        c, h = stereo[:, 0].astype(float), hardware[slope]
        delay = definitions[name].get("effective_hardware_decay_start_seconds", .035)
        exact_lag = receipt["output"]["latency_samples"] + .001 * sr - delay * sr
        lag = round(exact_lag)
        a, b = round(train["on"] * sr), round(train["off"] * sr)
        gain = assessor.rms(h[a:b]) / assessor.rms(c[a+lag:b+lag])
        row = {"id": name, "slope": slope, "kind": definitions[name]["kind"], "gain": gain,
               "gain_db": 20 * math.log10(gain), "lag_samples": lag, "exact_physical_lag_samples": exact_lag,
               "rounding_error_samples": lag-exact_lag, "training_reference_samples": [a, b],
               "training_candidate_samples": [a+lag,b+lag], "render_sha256": sha(path),
               "render_manifest_sha256": sha(path.with_suffix(".render.json")), "patch_sha256": item["sysex_sha256"],
               "finite": True, "full_scale_samples": int(np.count_nonzero(abs(stereo)>=1)),
               "maximum_channel_difference": difference, "peak": receipt["output"]["peak"],
               "whole_sequence": {label: score(h,c,gain,lag,start,end) for label,start,end in (
                   ("before_training",0,1.45),("after_training",2,len(h)/sr))},
               "isolated_notes": [{"note": n, **score(h,c,gain,lag,n["on"],n["off"])} for n in isolated],
               "chords": [{"chord": n, "full": score(h,c,gain,lag,n["on"],n["off"]),
                           "late": score(h,c,gain,lag,n["on"]+.41,n["on"]+.67)} for n in chord_intervals]}
        if name in ("production", "dry-hz-35ms", "dry-log-35ms"):
            oldlag = protocol["old_onset_lag_sensitivity"][str(slope)]
            oldgain = assessor.rms(h[a:b]) / assessor.rms(c[a+oldlag:b+oldlag])
            row["old_onset_sensitivity"] = {"lag_samples": oldlag, "gain": oldgain,
                "after_training": score(h,c,oldgain,oldlag,2,len(h)/sr)}
        results.append(row)
        all_audio[name,slope] = c
        print(name,slope,"SC",row["whole_sequence"]["after_training"]["measurements"]["summary"]["spectral_convergence_mean"],flush=True)
    save(out / "audio-results.json", {"protocol": protocol, "results": results})

    # Independent harmonic observations never feed the nuisance fit above.
    observed_hardware = {}
    def observe(y, center, spec):
        try:
            if spec["type"] == "single":
                m = harmonics.measure(y,44100,center,.08,440*2**((spec["note"]-69)/12))
                reasons = [] if m["fit_residual_power"] <= .01 else ["over_1_percent_unexplained_power"]
            else:
                m = chords.measure_chord(y,44100,center,.08,spec["notes"],spec["target"])
                reasons = [] if m["fit_residual_power"] <= .01 else ["over_1_percent_unexplained_power"]
                for partial in (1,2,3):
                    if partial not in m["harmonics"]:
                        reasons.append(f"H{partial}_not_isolated")
                        continue
                    index = m["harmonics"].index(partial)
                    if m["snr_proxy_db"][index] < 20:
                        reasons.append(f"H{partial}_under_20dB_noise_proxy")
                    if partial > 1 and m["harmonic_ratio_db"][index] <= -45:
                        reasons.append(f"H{partial}_under_relative_floor")
            return {"valid": not reasons,"rejections":reasons,"observation":m}
        except ValueError as error:
            return {"valid": False,"rejections":[str(error)]}
    specs = [{"type":"single","training":n==train,"note":n["note"],"on":n["on"],"offset":offset}
             for n in [train,*isolated] for offset in (.1,.18,.26,.34)]
    specs += [{"type":"chord","training":False,"on":n["on"],"notes":n["notes"],"target":n["target"],"offset":offset}
              for n in chord_intervals for offset in (.46,.54,.62)]
    harmonic_results = []
    for row in results:
        if row["id"] not in ("production","dry-hz-35ms","dry-log-35ms"):
            continue
        name,slope,gain,lag=row["id"],row["slope"],row["gain"],row["lag_samples"]
        for i,spec in enumerate(specs):
            spec={**spec,"slope":slope};center=spec["on"]+spec["offset"]
            if (slope,i) not in observed_hardware:
                observed_hardware[slope,i]=observe(hardware[slope],center,spec)
            h=observed_hardware[slope,i]
            c=observe(all_audio[name,slope]*gain,center+lag/44100,spec)
            item={"id":name,**spec,"hardware":h,"candidate":c,"valid_pair":h["valid"] and c["valid"]}
            if item["valid_pair"]:
                hm,cm=h["observation"],c["observation"]
                hs=np.array(hm["harmonics"])
                if hm["harmonics"] != cm["harmonics"]:
                    raise ValueError("Different harmonic identities at same pitches")
                active=np.array(hm["harmonic_ratio_db"])>-45
                if spec["type"]=="chord":
                    active &= np.array(hm["snr_proxy_db"])>=20
                ratios=np.array(cm["harmonic_ratio_db"])-hm["harmonic_ratio_db"]
                absolute=20*np.log10(np.maximum(cm["amplitude"],1e-30)/np.maximum(hm["amplitude"],1e-30))
                for label,low,high in (("h2_h8",2,8),("h9_h16",9,16)):
                    select=active&(hs>=low)&(hs<=high)
                    item["ratio_"+label]=ratios[select].tolist()
                    item["absolute_"+label]=absolute[select].tolist()
            harmonic_results.append(item)
        print("Harmonics",name,slope,flush=True)
    save(out / "harmonic-observations.json", {"protocol":protocol,"results":harmonic_results})
    primary = ("production","dry-hz-35ms","dry-log-35ms")
    def window_key(row):
        return (row["slope"],row["type"],row["on"],row["offset"])
    shared_valid = {window_key(row) for row in harmonic_results
                    if all(any(other["id"] == name and window_key(other) == window_key(row)
                               and other["valid_pair"] for other in harmonic_results) for name in primary)}
    summaries = []
    for name in primary:
        for slope in (12,24):
            for group in ("training_single","validation_single","validation_chord"):
                selected = [r for r in harmonic_results if r["id"]==name and r["slope"]==slope
                            and r["type"]==("chord" if group.endswith("chord") else "single")
                            and r["training"]==group.startswith("training")]
                common = [r for r in selected if window_key(r) in shared_valid]
                summary = {"id":name,"slope":slope,"group":group,"attempted_windows":len(selected),
                           "individually_valid_windows":sum(r["valid_pair"] for r in selected),
                           "common_valid_windows":len(common)}
                for metric in ("ratio_h2_h8","ratio_h9_h16","absolute_h2_h8","absolute_h9_h16"):
                    values = [v for r in common for v in r[metric]]
                    summary[metric] = {"observations":len(values),
                                      "rmse_db":float(np.sqrt(np.mean(np.square(values)))) if values else None}
                summaries.append(summary)
    save(out / "harmonic-summary.json", {"status":"diagnostic_not_equivalence",
         "policy":"Only windows valid for hardware and every primary model enter comparative RMS errors; same hardware-defined active harmonic mask. No candidate cutoff fit or other curve fit is used.",
         "observations_sha256":sha(out / "harmonic-observations.json"),"results":summaries})
    print(out / "audio-results.json")


if __name__ == "__main__":
    main()

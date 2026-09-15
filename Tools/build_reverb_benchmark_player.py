#!/usr/bin/env python3
"""Export seven synchronized original/before/after reverb listening comparisons.

Uses existing frozen production-prefix lag AND gain for both model tracks.
No timing, gain, MIDI or DSP fitting. Only new listening copies are written.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import wavfile
import assess_hardware_equivalence as assess

ROOT = Path(__file__).resolve().parents[1]
CASE_ORDER = ["air-lead-1", "brassy-ld-1", "club-bass", "cotton-wool", "supa-juce-1", "class-a-nominal", "ambient-sqr-nominal-v100"]
NEW = {"class-a-nominal", "ambient-sqr-nominal-v100"}
NOTES = {
    "air-lead-1": "Melodic gates and portamento are approximate; the excerpt stops during a held note.",
    "brassy-ld-1": "Short note releases and velocity are reconstructed; delay and reverb are both active.",
    "club-bass": "Counterexample: reducing the return worsens the measured level envelope. Strong HF damping differs from most cases.",
    "cotton-wool": "Exploratory context for the change. Reconstructed chord gates and overlapping releases remain uncertain.",
    "supa-juce-1": "The stored preset is unchanged; pitch, articulation and velocity come from a short source reconstruction.",
    "class-a-nominal": "Source-only note and pitch-bend reconstruction was frozen before scoring. Short gates remain uncertain; the end is a crop.",
    "ambient-sqr-nominal-v100": "Counterexample: some measured errors worsen. Dual layers and uncertain gates/velocity remain; alignment reaches the 50 ms search limit.",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(path, expected):
    actual = sha(path)
    if actual != expected:
        raise ValueError("Identity changed: " + str(path))
    return actual


def read(path, expected):
    checked(path, expected)
    sr, y = assess.read_audio(path)
    if sr != 44100 or y.ndim != 2 or y.shape[1] != 2 or not np.isfinite(y).all():
        raise ValueError("Expected finite 44.1 kHz stereo audio: " + str(path))
    return sr, y


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gain-run", type=Path, required=True)
    p.add_argument("--new-cases-run", type=Path, required=True)
    p.add_argument("--production-corpus", type=Path, required=True)
    p.add_argument("--sources", type=Path, required=True, help="Original official MP3 cache; read only")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    gain_path, new_path = a.gain_run/"results.json", a.new_cases_run/"results.json"
    old, new = json.loads(gain_path.read_text()), json.loads(new_path.read_text())
    if old["protocol"]["mode"] != "gain" or old["protocol"]["source_revision"] != "b0f6c03":
        raise ValueError("Expected frozen b0f6c03 gain experiment")
    if new["protocol"]["model_result_sha256"] != sha(gain_path):
        raise ValueError("New validation used another model family")
    if new["protocol"]["primary_hypothesis"] != "gain-0.5":
        raise ValueError("Unexpected primary hypothesis")
    old_cases = {r["id"]:r for r in old["cases"]}
    new_cases = {r["id"]:r for r in new["cases"]}
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    groups = []
    for identity in CASE_ORDER:
        is_new = identity in NEW
        row = (new_cases if is_new else old_cases)[identity]
        run = a.new_cases_run if is_new else a.gain_run
        directory = run/"cases"/identity
        if json.loads((directory/"result.json").read_text()) != row:
            raise ValueError("Per-case and aggregate receipts differ")
        source = a.new_cases_run/"baseline-corpus"/identity if is_new else a.production_corpus/identity
        comparison_path = source/"comparison.json"
        checked(comparison_path, row["comparison_sha256"])
        meta = json.loads(comparison_path.read_text())
        if is_new and meta != row["comparison"]:
            raise ValueError("Embedded comparison differs")
        spec = meta["case"]
        if spec["midi_status"] != "reconstructed_not_original" or spec.get("source_start_seconds",0) != 0:
            raise ValueError("Unexpected source clock or performance provenance")
        original = a.sources/meta["reference"]["local_filename"]
        checked(original, meta["reference"]["sha256"])
        inputs = {}
        for filename in ["hardware-excerpt-raw.wav", "original-patch.syx", "reconstructed-performance.mid"]:
            expected = meta["files"][filename] if is_new else row["input_sha256"][filename]
            inputs[filename] = dict(path=str((source/filename).resolve()), sha256=checked(source/filename, expected))
        sr, hardware = read(source/"hardware-excerpt-raw.wav", inputs["hardware-excerpt-raw.wav"]["sha256"])
        if len(hardware) != meta["comparison_frames"]:
            raise ValueError("Hardware excerpt length changed")
        signals = {}
        receipts = {}
        for key, model in [("before", "gain-1"), ("after", "gain-0.5")]:
            value = row["models"][model]
            expected = value["wav_sha256"] if is_new else value["raw_sha256"]
            raw = directory/(model+".wav")
            _, y = read(raw, expected)
            receipt_path = raw.with_suffix(".render.json")
            checked(receipt_path, value["receipt_sha256"])
            receipt = json.loads(receipt_path.read_text())
            expected_renderer = new["protocol"]["models"][model]["renderer_sha256"]
            if (receipt["inputs"]["renderer"]["sha256"] != expected_renderer
                    or receipt["output"]["sha256"] != expected or receipt["ignored_events"]
                    or receipt["output"]["active_voices_at_end"]
                    or receipt["inputs"]["sysex"]["sha256"] != inputs["original-patch.syx"]["sha256"]
                    or receipt["inputs"]["midi"]["sha256"] != inputs["reconstructed-performance.mid"]["sha256"]):
                raise ValueError("Raw render/input guard failed: "+identity)
            signals[key] = y
            receipts[key] = dict(path=str(raw.resolve()), raw_sha256=expected,
                render_receipt_sha256=sha(receipt_path), renderer_sha256=receipt["inputs"]["renderer"]["sha256"])
        if signals["before"].shape != signals["after"].shape:
            raise ValueError("Model frame coverage differs")
        if not is_new and receipts["before"]["raw_sha256"] != row["input_sha256"]["septum-raw.wav"]:
            raise ValueError("Before control differs from frozen production")
        lag = row["calibration"]["candidate_lag_samples"]
        gain = row["calibration"]["candidate_gain"]
        if not isinstance(lag,int) or abs(lag)>2205 or not np.isfinite(gain) or gain<=0:
            raise ValueError("Invalid frozen calibration")
        # Match assessed common coverage; retain its excluded edge for all tracks.
        n = len(hardware)
        begin, end = max(0,-lag), min(n,n-lag,*[len(y)-lag for y in signals.values()])
        ea, eb = row["evaluation_samples"]
        if not begin <= ea < eb <= end:
            raise ValueError("Evaluation interval is outside common playback coverage")
        aligned = {"hardware":hardware[begin:end], **{key:y[begin+lag:end+lag]*gain for key,y in signals.items()}}
        if len({x.shape for x in aligned.values()}) != 1:
            raise ValueError("Aligned frame coverage differs")
        attenuation = min(1., .1/assess.rms(aligned["hardware"]), .98/max(float(abs(x).max()) for x in aligned.values()))
        case_out = out/identity
        case_out.mkdir()
        tracks = []
        for key, x in aligned.items():
            data = (x*attenuation).astype(np.float32)
            path = case_out/(key+".wav")
            wavfile.write(path, sr, data)
            rate, decoded = wavfile.read(path)
            if rate != sr or not np.array_equal(decoded,data) or not np.isfinite(decoded).all() or abs(decoded).max()>=1:
                raise ValueError("Listening export verification failed")
            tracks.append(dict(id=key, file=f"{identity}/{key}.wav", sha256=sha(path),
                frames=len(data), peak=float(abs(data).max()), rms_dbfs=float(20*np.log10(assess.rms(data))),
                applied_model_gain=1. if key=="hardware" else gain,
                raw_source=inputs["hardware-excerpt-raw.wav"] if key=="hardware" else receipts[key]))
        ca, cb = row["calibration_reference_samples"]
        group = dict(id=identity, title=meta["reference"]["title"], original_url=meta["reference"]["url"], counterexample=identity in {"club-bass","ambient-sqr-nominal-v100"},
            note=NOTES[identity], sample_rate=sr, frames=end-begin, hardware_start_sample=begin, hardware_end_sample=end,
            model_start_sample=begin+lag, model_end_sample=end+lag, common_attenuation=attenuation,
            calibration=row["calibration"], calibration_reference_samples=[ca,cb],
            calibration_candidate_samples=row["calibration_candidate_samples"],
            evaluation_reference_samples=[ea,eb], evaluation_playback_seconds=[(ea-begin)/sr,(eb-begin)/sr],
            calibration_playback_seconds=[(ca-begin)/sr,(cb-begin)/sr],
            tracks=tracks, original_recording=dict(path=str(original.resolve()), **meta["reference"]),
            input_files=inputs, comparison_sha256=sha(comparison_path), case_result_sha256=sha(directory/"result.json"),
            reconstruction=spec, limitations=meta["comparison_limits"])
        groups.append(group)
        print(identity, f"{end-begin} identical frames; lag {lag}; shared gain {gain:.9f}; attenuation {attenuation:.9f}")
    template = Path(__file__).with_name("reverb_benchmark_player.html")
    manifest = dict(schema_version=1, status="Selected half-return correction; synchronized listening, not whole-instrument equivalence.",
        models=dict(before="Frozen gain-1 renderer: prior reverb return 0.8.", after="Frozen gain-0.5 renderer: selected reverb return 0.4; production rebuild identity is audited separately."),
        policy="Use only previously frozen production-prefix lag AND gain for both model tracks. No candidate-specific gain, EQ, dynamics, phase fit or time warp. Maximal common assessed excerpt coverage includes training; one common attenuation targets hardware at most −20dBFS RMS and all peaks<=.98. Page switches with a12ms fade only during playback.",
        input_manifests=dict(gain_run=dict(path=str(gain_path.resolve()),sha256=sha(gain_path)),new_cases_run=dict(path=str(new_path.resolve()),sha256=sha(new_path))),
        script_sha256=sha(__file__), template_sha256=sha(template), assessor_sha256=sha(ROOT/"Tools/assess_hardware_equivalence.py"),groups=groups)
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2,allow_nan=False)+"\n")
    ui_keys = ["id","title","original_url","counterexample","note","sample_rate","frames","hardware_start_sample","evaluation_playback_seconds","calibration_playback_seconds"]
    ui = dict(groups=[{**{key:g[key] for key in ui_keys}, "tracks":[{key:t[key] for key in ["id","file","sha256"]} for t in g["tracks"]]} for g in groups])
    # Escape '<' so user/source strings cannot terminate the embedded JSON script.
    embedded = json.dumps(ui,allow_nan=False).replace("<","\\u003c")
    (out/"index.html").write_text(template.read_text().replace("__MANIFEST__",embedded))
    print(out/"index.html")


if __name__ == "__main__":
    main()

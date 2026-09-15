#!/usr/bin/env python3
"""Codec-only sensitivity of an already frozen asymmetric W4 Saw prediction."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile
from scipy.signal import correlate
import fit_high_note_saw_asymmetric_kernels as fitter
import fit_high_note_saw_wrap_kernels as symmetric
import analyze_deepsonic_saw_aliases as aliases

ROOT, SR, SIZE = fitter.ROOT, fitter.SR, fitter.SIZE
PADDING = SR//2


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.experiment/"results.json"
    original = json.loads(source.read_text())
    if original["script_sha256"] != sha(fitter.__file__):
        raise ValueError("Frozen fitter implementation changed")
    for name, expected in original["dependency_sha256"].items():
        if sha(ROOT/"Tools"/name) != expected:
            raise ValueError("Frozen fitter dependency changed")
    for key in ("source", "original_midi"):
        if sha(ROOT/original[key]["path"]) != original[key]["sha256"]:
            raise ValueError("Original source identity changed")
    hardware_wav = args.experiment/"hardware-lp12.wav"
    if sha(hardware_wav) != original["decoded_wav_sha256"]:
        raise ValueError("Verified hardware decode changed")
    rate, audio = wavfile.read(hardware_wav)
    if rate != SR or audio.ndim != 1:
        raise ValueError("Unexpected hardware decode")
    model = next(r for r in original["models"] if r["id"] == "asymmetric-W4")
    coefficients = np.array(model["training"]["coefficients"])
    phases = [model["training"]]+model["evaluations"]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    protocol = dict(status="frozen_candidate_codec_sensitivity_not_model_selection",
                    model_id=model["id"], experiment_sha256=sha(source), padding_samples_each_side=PADDING,
                    sample_rate=SR, channels=1, codec="libmp3lame", bitrate_bps=320000,
                    scoring="Original unchanged hardware-only alias mask. Compare float32 clean prediction with320kbps MP3 roundtrip using identical central80ms indices.",
                    alignment="No phase/parameter/offset fitting. Require gapless decode length equality; check integer cross-correlation over+/-1152samples diagnostically, without applying a lag.",
                    limitation="This controlled libmp3lame encode cannot identify the original MP3 encoder or recording path.")
    (out/"protocol.json").write_text(json.dumps(protocol, indent=2)+"\n")
    rows = []
    for index, (score, fit) in enumerate(zip(model["scores"], phases)):
        passage = score["passage"]
        note, phase = passage["note"], fit["phase"]
        x = audio[passage["start_sample"]:passage["end_sample"]].astype(float)
        if hashlib.sha256(x.astype("<f8").tobytes()).hexdigest() != passage["sample_sha256"]:
            raise ValueError("Original hardware window changed")
        size = SIZE+2*PADDING
        increment = aliases.f0(note)/SR
        extended = np.concatenate([fitter.design(phase+(start-PADDING)*increment, note, 4.)@coefficients
                                   for start in range(0, size, SIZE)])[:size]
        direct = fitter.design(phase, note, 4.)@coefficients
        context_error = float(np.max(np.abs(extended[PADDING:PADDING+SIZE]-direct)))
        if context_error > 1e-10:
            raise ValueError("Context synthesis changed frozen central prediction")
        stem = out/f"passage-{index}-note-{note}"
        clean_path, mp3, decoded_path = stem.with_suffix(".wav"), stem.with_suffix(".mp3"), stem.with_name(stem.name+"-decoded").with_suffix(".wav")
        wavfile.write(clean_path, SR, extended.astype(np.float32))
        encode = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(clean_path),
                  "-c:a", "libmp3lame", "-b:a", "320k", str(mp3)]
        decode = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(mp3),
                  "-c:a", "pcm_f32le", str(decoded_path)]
        subprocess.run(encode, check=True)
        subprocess.run(decode, check=True)
        probe_command = ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,sample_rate,channels,bit_rate", "-of", "json", str(mp3)]
        probe = json.loads(subprocess.check_output(probe_command))
        stream = probe["streams"][0]
        if (stream["codec_name"], int(stream["sample_rate"]), stream["channels"], int(stream["bit_rate"])) != ("mp3", SR, 1, 320000):
            raise ValueError("Codec format mismatch")
        rate, clean = wavfile.read(clean_path)
        decoded_rate, decoded = wavfile.read(decoded_path)
        if rate != SR or decoded_rate != SR or len(clean) != size or len(decoded) != size or decoded.ndim != 1:
            raise ValueError("Gapless decode length or format changed")
        clean_center = clean[PADDING:PADDING+SIZE].astype(float)
        clean_center -= clean_center.mean()
        lags = np.arange(-1152, 1153)
        segment = decoded[PADDING-1152:PADDING+SIZE+1152].astype(float)
        numerator = correlate(segment, clean_center, mode="valid", method="fft")
        sums = np.r_[0., np.cumsum(segment)]
        sums2 = np.r_[0., np.cumsum(segment**2)]
        energy = sums2[SIZE:]-sums2[:-SIZE]-(sums[SIZE:]-sums[:-SIZE])**2/SIZE
        correlations = numerator/np.sqrt(np.maximum(energy, 1e-30)*np.sum(clean_center**2))
        lag_check = dict(search_samples=[-1152, 1152], best_integer_lag=int(lags[np.argmax(correlations)]),
                         best_correlation=float(np.max(correlations)), zero_lag_correlation=float(correlations[1152]), applied_lag=0)
        if lag_check["best_integer_lag"] != 0:
            raise ValueError("Gapless central correlation is not maximized at zero; investigate without offset fitting")
        reference = aliases.measure(x, .04, note, 0.)
        clean_score = symmetric.compare_aliases(reference, aliases.measure(clean, PADDING/SR+.04, note, 0.))
        encoded_score = symmetric.compare_aliases(reference, aliases.measure(decoded, PADDING/SR+.04, note, 0.))
        lines = []
        for before, after in zip(clean_score["lines"], encoded_score["lines"]):
            if before["parent_harmonic"] != after["parent_harmonic"]:
                raise ValueError("Hardware mask changed")
            lines.append(dict(parent_harmonic=before["parent_harmonic"], expected_hz=before["expected_hz"],
                              hardware_dbc=before["hardware_dbc"], clean_dbc=before["model_dbc"], encoded_dbc=after["model_dbc"],
                              encoded_minus_clean_db=after["model_dbc"]-before["model_dbc"],
                              clean_minus_hardware_db=before["model_minus_hardware_db"], encoded_minus_hardware_db=after["model_minus_hardware_db"],
                              encoded_interior_peak=after["model_interior_peak"], encoded_prominence_db=after["model_prominence_db"]))
        delta = np.array([r["encoded_minus_clean_db"] for r in lines])
        rows.append(dict(passage=passage, frozen_phase=phase, context_center_max_absolute_difference=context_error,
                         clean_peak=float(np.max(np.abs(clean))), gapless_samples=size, lag_check=lag_check,
                         encode_command=encode, decode_command=decode, probe_command=probe_command, probe=probe,
                         clean_sha256=sha(clean_path), mp3_sha256=sha(mp3), decoded_sha256=sha(decoded_path),
                         codec_change_rms_db=float(np.sqrt(np.mean(delta**2))), codec_change_max_absolute_db=float(np.max(np.abs(delta))),
                         clean_alias_rms_error_db=clean_score["rms_error_db"], encoded_alias_rms_error_db=encoded_score["rms_error_db"],
                         hardware_eligible_line_count=len(lines), lines=lines))
        print(note, passage["offset_seconds"], "codec RMS/max dB", rows[-1]["codec_change_rms_db"], rows[-1]["codec_change_max_absolute_db"], flush=True)
    result = dict(protocol=protocol, script_sha256=sha(__file__), fitter_sha256=sha(fitter.__file__),
                  dependencies=original["dependency_sha256"], original_source=original["source"], original_midi=original["original_midi"],
                  coefficient_sha256=hashlib.sha256(coefficients.astype("<f8").tobytes()).hexdigest(), passages=rows)
    (out/"results.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")


if __name__ == "__main__":
    main()

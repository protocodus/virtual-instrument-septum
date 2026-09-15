#!/usr/bin/env python3
"""Bounded spectral feasibility of two visually chosen synth-love passages.

No oscillator, note, spread value or endpoint is fitted. Native 48 kHz stereo
decode; channel powers are averaged so stereo cancellation cannot erase lines.
One predeclared nearby reference is inspected, with no adaptive window search.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.io import wavfile
from scipy.signal import find_peaks, spectrogram

SOURCE_SHA = "6ed77a823dde937f4bf87bf9cf803a7293dd21a97056f36694704355b8b15f4c"
WINDOWS = [("visual-a", 589.2, 591.0), ("visual-b", 598.5, 601.3),
           ("nearby-reference", 591.5, 593.3)]
BANDS = [(100, 145), (155, 180), (250, 290), (320, 360)]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def spectrum(x, fs):
    n = len(x)
    z = np.fft.rfft(x * np.hanning(n)[:, None], n=8*n, axis=0)
    power = np.mean(abs(z)**2, axis=1) / np.hanning(n).sum()**2
    f = np.fft.rfftfreq(8*n, 1/fs)
    db = 10*np.log10(np.maximum(power, 1e-30))
    return f, db


def peaks(x, fs):
    f, db = spectrum(x, fs)
    step = f[1] - f[0]
    ids, props = find_peaks(db, prominence=8, distance=max(1, round(.5/step)))
    found = []
    for i, prominence in zip(ids, props["prominences"]):
        if not 40 <= f[i] <= 8000 or db[i] - db.max() < -50:
            continue
        # Local -3 dB crossings. Neighbour overlap can broaden this descriptive
        # width; it is not a fitted sinusoid uncertainty or confidence interval.
        lo = hi = i
        target = db[i]-3
        while lo > 0 and db[lo] > target:
            lo -= 1
        while hi+1 < len(f) and db[hi] > target:
            hi += 1
        left = np.interp(target, db[lo:lo+2], f[lo:lo+2])
        right = np.interp(target, db[hi-1:hi+1][::-1], f[hi-1:hi+1][::-1])
        found.append({"frequency_hz": float(f[i]),
                      "relative_db": float(db[i]-db.max()),
                      "prominence_db": float(prominence),
                      "local_3db_width_hz": float(right-left)})
    return sorted(found, key=lambda p: p["frequency_hz"])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=Path("build-fidelity/public-waveforms/synth-love/OB3J7AQBla0.f251.webm"))
    ap.add_argument("--out", type=Path, default=Path("build-fidelity/public-waveforms/synth-love/supersaw-feasibility/run-01"))
    args = ap.parse_args()
    assert sha(args.source) == SOURCE_SHA, "Pinned original audio hash mismatch"
    controls = []
    for duration in (1.8, 2.8):
        rate = 48000
        t = np.arange(round(duration*rate))/rate
        tone = np.sin(2*np.pi*131.125*t)
        # Opposite channels would disappear in an accidental mono downmix.
        measured = min(peaks(np.column_stack((tone, -tone)), rate),
                       key=lambda p: abs(p["frequency_hz"]-131.125))
        assert abs(measured["frequency_hz"]-131.125) <= .5/(8*duration)+1e-9
        assert abs(measured["local_3db_width_hz"]-1.44/duration) < .02
        controls.append({"seconds":duration,"frequency_hz":131.125,
                         "opposite_channel_phase":True,"measured":measured})
    args.out.mkdir(parents=True, exist_ok=True)
    wav = args.out/"chapter-native-48k.wav"
    command = ["ffmpeg", "-v", "error", "-i", str(args.source), "-ss", "540",
               "-t", "64.9", "-c:a", "pcm_f32le", "-y", str(wav)]
    subprocess.run(command, check=True)
    fs, audio = wavfile.read(wav)
    assert fs == 48000 and audio.ndim == 2 and audio.shape[1] == 2
    assert audio.dtype == np.float32 and np.isfinite(audio).all()
    rows = []
    fig, axes = plt.subplots(3, 5, figsize=(19, 11), constrained_layout=True)
    for ri, (name, start, end) in enumerate(WINDOWS):
        x = audio[round((start-540)*fs):round((end-540)*fs)].astype(np.float64)
        cuts = [x, x[:len(x)//2], x[len(x)//2:]]
        tables = [peaks(c, fs) for c in cuts]
        # Correspondence is descriptive only; nearest-half peaks may represent
        # different unresolved components. No accepted component count results.
        for p in tables[0]:
            nearest = []
            for table in tables[1:]:
                q = min(table, key=lambda q: abs(q["frequency_hz"]-p["frequency_hz"])) if table else None
                nearest.append(None if q is None else {
                    "frequency_hz": q["frequency_hz"],
                    "difference_hz": q["frequency_hz"]-p["frequency_hz"],
                    "local_3db_width_hz": q["local_3db_width_hz"],
                    "relative_db": q["relative_db"]})
            p["nearest_half_window_peaks"] = nearest
        full_f, full_db = spectrum(x, fs)
        for bi, (low, high) in enumerate(BANDS):
            ax = axes[ri, bi]
            for c, label, color in zip(cuts, ["whole", "first half", "second half"], ["black", "tab:blue", "tab:orange"]):
                f, db = spectrum(c, fs)
                select = (f>=low)&(f<=high)
                # Each trace has one broadband normalization, never per band.
                ax.plot(f[select], db[select]-db.max(), label=label, color=color, lw=.8)
            ax.set(xlim=(low,high), ylim=(-55,3), title=f"{low}–{high} Hz", xlabel="Hz", ylabel="dB / whole-spectrum maximum")
            ax.grid(alpha=.2)
        # Native audio, stereo power-average STFT; 0.5 s Hann windows make
        # 2 Hz bin spacing. This view diagnoses motion, not sub-bin detune.
        f, t, z = spectrogram(x.T, fs, window="hann", nperseg=24000,
                             noverlap=21600, scaling="spectrum", mode="psd", axis=-1)
        power = z.mean(axis=0)
        keep = (f>=90)&(f<=430)
        db = 10*np.log10(np.maximum(power,1e-30)/power.max())
        axes[ri,4].pcolormesh(start+t, f[keep], db[keep], shading="auto", vmin=-45, vmax=0, cmap="magma")
        axes[ri,4].set(title=f"{name}: {start}–{end} s", xlabel="Source seconds", ylabel="Hz")
        quarters = [float(np.sqrt(np.mean(q*q))) for q in np.array_split(x,4)]
        rows.append({"id":name,"source_seconds":[start,end],"samples":len(x),
                     "rms":float(np.sqrt(np.mean(x*x))),"quarter_rms":quarters,
                     "whole_unpadded_bin_hz":fs/len(x),
                     "approx_isolated_hann_3db_width_hz":1.44*fs/len(x),
                     "whole_peaks":tables[0],"half_peaks":tables[1:]})
    axes[0,0].legend(fontsize=8)
    fig.suptitle("Original SH-201 Super Saw chapter: exploratory spectral feasibility\nNative 48 kHz stereo power; no single-note, dry, oscillator-count or knob-value assumption")
    plot=args.out/"spectral-feasibility.png";fig.savefig(plot,dpi=140);plt.close(fig)
    result={"schema_version":1,"source":{"path":str(args.source),"sha256":SOURCE_SHA},
            "tool_sha256":sha(Path(__file__)),"decode":{"command":command,"wav":str(wav),"sha256":sha(wav),"rate_hz":fs,"channels":2,"no_resampling":True,"no_downmix":True,"chapter_origin_seconds":540},
            "protocol":{"windows":WINDOWS,"extra_reference_count":1,"amplitude_policy":"mean of left/right spectral powers, never mono sample averaging","window":"Hann; 8x zero padding only interpolates spectrum and does not improve resolving power","peaks":"40–8000 Hz; >=8 dB local prominence; >=-50 dB from spectrum maximum; >=0.5 Hz grid-peak spacing","width":"local -3 dB crossings; may include unresolved neighbouring lines","half_comparison":"nearest detected peak, descriptive only, not component identity","stft":"0.5-second Hann, 50 ms hop, 2 Hz native bin spacing","bands_hz":BANDS,"no_adaptive_window_search":True,"no_model_or_detune_fit":True},
            "windows":rows,"plot":{"path":str(plot),"sha256":sha(plot)},
            "synthetic_peak_width_controls":controls,
            "scope":"Descriptive feasibility only. Multiple notes/oscillators, modulation, effects and platform encoding may contribute. Detected spectral peaks are not automatically Super Saw components."}
    (args.out/"results.json").write_text(json.dumps(result,indent=2)+"\n")
    for r in rows:
        subset=[p for p in r["whole_peaks"] if 100<=p["frequency_hz"]<=180]
        print(r["id"], "quarter RMS", r["quarter_rms"])
        print(json.dumps(subset,indent=2))


if __name__ == "__main__":
    main()

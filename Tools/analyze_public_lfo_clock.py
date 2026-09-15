#!/usr/bin/env python3
"""Explore pitch-step clock evidence in the first 50 s of a public SH-201 video.

Requires the hash-pinned original offered Opus/WebM, ffmpeg, NumPy/SciPy and
matplotlib. The passage and split are exploratory, not preregistered. This
does not identify the raw LFO setting, waveform enum or tempo-sync state.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy import optimize, signal
from scipy.io import wavfile

SOURCE_SHA = "6ed77a823dde937f4bf87bf9cf803a7293dd21a97056f36694704355b8b15f4c"
SOURCE_URL = "https://www.youtube.com/watch?v=OB3J7AQBla0"
ROOT = Path(__file__).resolve().parents[1]
TRACKS = ((349.2, 50), (440., 35), (1047.5, 150), (1320., 150))
BANDS = ((100, 400), (400, 1000), (1000, 2500), (2500, 6000), (6000, 12000))
TRAIN = (3.35, 4.35)
HOLD = (4.35, 5.35)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def pitch_track(audio, center, width):
    filtered = signal.sosfiltfilt(signal.butter(
        6, [center-width, center+width], btype="bandpass", fs=48000,
        output="sos"), audio)
    phase = np.unwrap(np.angle(signal.hilbert(filtered)))
    frequency = signal.savgol_filter(phase, 241, 2, deriv=1, delta=1/48000)/(2*np.pi)
    frequency = signal.resample_poly(frequency, 1, 48)
    return 1200*np.log2(np.maximum(frequency, 1)/center)


def spectrum_peaks(x, fs, bounds=(2, 100), count=5):
    f, p = signal.periodogram(x, fs, window="hann", nfft=65536)
    ix = signal.find_peaks(p)[0]
    ix = ix[(f[ix] >= bounds[0]) & (f[ix] <= bounds[1])]
    ix = sorted(ix, key=lambda k: p[k], reverse=True)[:count]
    return [dict(frequency_hz=float(f[k]), power=float(p[k])) for k in ix]


def clock_fit(cents, prominence=1500):
    """Fit one frequency/phase from training; keep it frozen on later edges."""
    t = np.arange(len(cents))/1000
    derivative = signal.savgol_filter(cents, 7, 2, deriv=1, delta=.001)
    energy = derivative**2
    train = (t >= TRAIN[0]) & (t < TRAIN[1])
    held = (t >= HOLD[0]) & (t < HOLD[1])
    train_peaks = spectrum_peaks(energy[train], 1000)
    peak = train_peaks[0]["frequency_hz"]
    tt = t[train]
    weighted = (energy[train]-energy[train].mean())*np.hanning(train.sum())
    def coefficient(f):
        return np.sum(weighted*np.exp(-2j*np.pi*f*tt))
    fit = optimize.minimize_scalar(lambda f: -abs(coefficient(f))**2,
                                  bounds=(max(2, peak-.5), min(100, peak+.5)),
                                  method="bounded", options={"xatol":1e-9})
    hz = float(fit.x)
    origin = float((-np.angle(coefficient(hz))/(2*np.pi*hz)) % (1/hz))
    all_edges = signal.find_peaks(abs(derivative), distance=20, prominence=prominence)[0]
    regions = {}
    for name, bounds in (("training", TRAIN), ("held_out", HOLD)):
        idx = all_edges[(t[all_edges] >= bounds[0]) & (t[all_edges] < bounds[1])]
        times = t[idx]
        residual = ((times-origin+.5/hz) % (1/hz)-.5/hz)*1000
        regions[name] = dict(edges=len(times), times_seconds=times.tolist(),
            grid_residual_ms=residual.tolist(),
            median_absolute_residual_ms=float(np.median(abs(residual))) if len(times) else None,
            p95_absolute_residual_ms=float(np.percentile(abs(residual), 95)) if len(times) else None,
            maximum_absolute_residual_ms=float(max(abs(residual))) if len(times) else None)
    return dict(training_frequency_hz=hz, training_period_ms=1000/hz,
                training_grid_origin_seconds=origin,
                training_derivative_energy_peaks=train_peaks,
                held_out_derivative_energy_peaks=spectrum_peaks(energy[held], 1000),
                training_derivative_rms_cents_per_second=float(np.sqrt(energy[train].mean())),
                held_out_derivative_rms_cents_per_second=float(np.sqrt(energy[held].mean())),
                edge_prominence_cents_per_second=prominence,
                minimum_edge_separation_ms=20, regions=regions)


def controls():
    t = np.arange(7*48000)/48000
    rng = np.random.default_rng(201)
    control_hz = 17.3
    values = rng.uniform(-90, 90, int(np.ceil(7*control_hz))+1)
    stepped = values[np.floor(t*control_hz).astype(int)]
    output = {}
    for name, cents in (("known_17p3_hz_step_clock", stepped),
                        ("static_two_tone_beating_no_lfo", np.zeros(len(t)))):
        ratio = 2**(cents/1200)
        phases = [2*np.pi*np.cumsum(f*ratio)/48000 for f in (349.2, 440.)]
        y = .12*np.sin(phases[0]) + .1*np.sin(phases[1])
        y += .003*np.sin(3*phases[0]) + .003*np.sin(3*phases[1])
        track = pitch_track(y, 1320., 150)
        output[name] = clock_fit(track)
        low = signal.sosfiltfilt(signal.butter(4, [100, 500], btype="bandpass",
                                             fs=48000, output="sos"), y)
        amplitude = signal.resample_poly(abs(signal.hilbert(low)), 1, 48)
        output[name]["band_amplitude_peaks"] = spectrum_peaks(amplitude[3350:4350], 1000)
    positive = output["known_17p3_hz_step_clock"]
    negative = output["static_two_tone_beating_no_lfo"]
    passed = (abs(positive["training_frequency_hz"]-control_hz) < .3
              and positive["regions"]["held_out"]["edges"] >= 10
              and positive["regions"]["held_out"]["p95_absolute_residual_ms"] < 3
              and negative["regions"]["held_out"]["edges"] == 0)
    if not passed:
        raise ValueError("Synthetic control failed; do not interpret hardware clock result")
    return dict(known_clock_hz=control_hz, rng_seed=201, checks_passed=passed, results=output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-webm", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if sha(args.source_webm) != SOURCE_SHA:
        raise ValueError("Original offered Opus/WebM identity changed")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    decoder = shutil.which("ffmpeg")
    if not decoder:
        raise ValueError("ffmpeg is required")
    wav = out/"source-first-50s.wav"
    command = [decoder, "-hide_banner", "-loglevel", "error", "-nostdin",
               "-i", str(args.source_webm.resolve()), "-t", "50", "-c:a", "pcm_f32le", str(wav)]
    subprocess.run(command, check=True)
    sr, stereo = wavfile.read(wav)
    if sr != 48000 or stereo.shape != (2400000, 2) or not np.isfinite(stereo).all():
        raise ValueError("Unexpected public audio format")
    mono = stereo.mean(axis=1).astype(float)
    frames = args.source_webm.parent/"frames"
    frame_hashes = {p.name:sha(p) for p in sorted(frames.glob("part2-*.png"))
                    if p.stem in {"part2-000", "part2-004", "part2-005", "part2-010", "part2-020", "part2-030", "part2-040", "part2-049"}}
    visual_report = ROOT/"Docs/fidelity/source-audits/synth-love-video-acquisition-2026-09-15.json"
    result = dict(status="exploratory_clock_corroboration_only", source_url=SOURCE_URL,
        source_sha256=SOURCE_SHA, decoded_wav_sha256=sha(wav), tool_sha256=sha(__file__),
        decoder=dict(command=command, binary_sha256=sha(decoder),
                     version=subprocess.check_output([decoder,"-version"],text=True).splitlines()[0]),
        source_frame_sha256=frame_hashes,
        independent_visual_audit=dict(path=str(visual_report.relative_to(ROOT)),
            sha256=sha(visual_report),
            finding="The selected LED at 4 s maps positionally to S&H in the official manual p40, with moderate-high confidence. The manual states one new S&H value per cycle. Raw RATE, routing and sync are unresolved."),
        protocol=dict(training_seconds=TRAIN, held_out_seconds=HOLD,
            passage_selection="Exploratory after inspecting the first 50 s and cross-partial pitch traces; split validation is internal, not untouched external validation.",
            primary_track_hz=1320, bandpass="Sixth-order zero-phase Butterworth, listed center/half-width; Hilbert phase, 241-sample quadratic Savitzky-Golay derivative at 48 kHz; resample to 1 kHz; cents derivative uses a 7-sample quadratic.",
            clock_fit="Largest squared-pitch-derivative periodogram peak over 2–100 Hz in training; continuous frequency refinement ±.5 Hz and one phase fit from training only. Frozen grid is tested on later detected edges.",
            frequency_precision="Zero padding and numerical refinement interpolate the spectrum; decimal places are not a calibrated confidence interval.",
            no_raw_setting_or_default_selection=True),
        tracks=[], width_sensitivity=[], prominence_sensitivity=[], broad_band_scan=[])
    tracks = []
    for center, width in TRACKS:
        track = pitch_track(mono[:7*sr], center, width)
        tracks.append(track)
        result["tracks"].append(dict(center_hz=center, half_width_hz=width, **clock_fit(track)))
    for width in (100, 150, 200):
        track = pitch_track(mono[:7*sr], 1320, width)
        result["width_sensitivity"].append(dict(half_width_hz=width, **clock_fit(track)))
    for prominence in (750, 1500, 3000):
        result["prominence_sensitivity"].append(clock_fit(tracks[-1], prominence))
    for low, high in BANDS:
        filtered = signal.sosfiltfilt(signal.butter(4, [low, high], btype="bandpass",
                                                  fs=sr, output="sos"), mono)
        amplitude = signal.resample_poly(abs(signal.hilbert(filtered)), 1, 48)
        for start in range(0, 50, 2):
            region = amplitude[start*1000:(start+2)*1000]
            result["broad_band_scan"].append(dict(band_hz=[low,high],
                interval_seconds=[start,start+2], rms_band_amplitude=float(np.sqrt(np.mean(region**2))),
                peaks=spectrum_peaks(region, 1000, count=3)))
    result["synthetic_controls"] = controls()
    result["limitations"] = [
        "Shared stepped pitch and independent positional LED mapping support an S&H clock interpretation; waveform/routing identification is not an exact patch capture.",
        "Author's maximum-LFO chapter label and sparse visible knob state do not prove raw 127, free-running mode or the full rate table.",
        "The source is a compressed public performance with parameter edits, multiple carrier families and unknown MIDI/patch.",
        "The rest of the 50 s is not a stationary patch. A spectral peak can be beating, event cadence, modulation harmonic or noise.",
        "This analysis does not exclude small rate variation or calibrate source/capture clock error."]
    save(out/"results.json", result)
    (out/"experiment-script.py").write_bytes(Path(__file__).read_bytes())

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(3,1,figsize=(12,9))
    t = np.arange(len(tracks[0]))/1000
    for (center,_), track in zip(TRACKS, tracks):
        ax[0].plot(t, track, lw=.9, label=f"{center:g} Hz partial")
        ax[1].plot(t, track, lw=.9)
    ax[0].set(xlim=(1.5,6.5), ylim=(-115,115), ylabel="Pitch offset (cents)")
    ax[0].legend(ncol=2, fontsize=9)
    ax[1].set(xlim=(4.35,4.85), ylim=(-115,115), ylabel="Held-out pitch (cents)", xlabel="Seconds")
    primary = result["tracks"][-1]
    period = 1/primary["training_frequency_hz"]
    for tt in np.arange(primary["training_grid_origin_seconds"], 7, period):
        if 4.35 <= tt <= 4.85:
            ax[1].axvline(tt, color="black", alpha=.2, lw=.8)
    d = signal.savgol_filter(tracks[-1],7,2,deriv=1,delta=.001)**2
    for bounds, label in ((TRAIN,"Training"),(HOLD,"Held out")):
        select = (t >= bounds[0]) & (t < bounds[1])
        f,p = signal.periodogram(d[select],1000,window="hann",nfft=65536)
        ax[2].plot(f,10*np.log10(np.maximum(p,1e-30)/max(p)),label=label)
    ax[2].set(xlim=(2,100), ylim=(-45,1), xlabel="Pitch-edge energy frequency (Hz)", ylabel="Relative power (dB)")
    ax[2].legend()
    fig.suptitle("Public SH-201 clip: approximately 40.2 ms pitch-step cadence", fontsize=14)
    fig.text(.5,.012,"Exploratory split validation; S&H supported by panel mapping; raw RATE / sync unresolved. No DSP setting selected.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0,.035,1,.965))
    fig.savefig(out/"clock-diagnostic.png",dpi=140)
    print(out/"results.json")


if __name__ == "__main__":
    main()

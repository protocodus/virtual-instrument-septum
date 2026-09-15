#!/usr/bin/env python3
"""Source-only Ambient SQR first-note articulation feasibility; no renderer.

Window choices are supplied before inspection. Harmonic persistence and
stereo coherence do not distinguish a held oscillator from its wet return.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import numpy as np
from scipy.io import wavfile
from scipy.signal import find_peaks
from extract_reference_patch import read_bank, parse_bank, encode_syx
from compare_hardware import write_midi
from render_midi import parse_smf, replay_events

ROOT = Path(__file__).resolve().parents[1]
SR = 44100
MP3_SHA = "d113bb3d65c34bb6827d29561e29dd9c9d4a6236143d5528685643f84a86e565"
BANK_SHA = "102c47ee393c09115779172b8cbbb2c2f2563e0b4fdb2f57e0c8fca2a23c3b29"
SYX_SHA = "1e420e8a04502d790a1018f4547167377bdfd4470e21bb6602853d09218aff07"
WINDOWS = ((.11, .16), (.22, .27), (.30, .35), (.36, .40))
HARMONICS = (1, 3, 5, 7, 9, 11, 13, 15)
F0 = 440*2**((74-69)/12)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def ratio_db(a, b=1.):
    return float(10*np.log10(max(a, 1e-30)/max(b, 1e-30)))


def stereo(y):
    power = np.mean(y*y, axis=0)
    mid, side = y.mean(axis=1), .5*(y[:, 0]-y[:, 1])
    m, s = np.mean(mid*mid), np.mean(side*side)
    return dict(rms_dbfs=ratio_db(power.mean()), right_minus_left_db=ratio_db(power[1], power[0]),
                side_fraction=float(s/(m+s)), side_to_mid_db=ratio_db(s, m),
                zero_lag_channel_correlation=float(np.corrcoef(y.T)[0, 1]))


def linewidth(f, power, expected):
    interior = np.flatnonzero(abs(f-expected) < 100)
    peaks, _ = find_peaks(power)
    peaks = np.intersect1d(peaks, interior)
    if not len(peaks):
        return dict(identified=False)
    p = int(peaks[np.argmax(power[peaks])])
    half = power[p]/2
    lo, hi = p, p
    while lo > interior[0] and power[lo] > half:
        lo -= 1
    while hi < interior[-1] and power[hi] > half:
        hi += 1
    if lo == interior[0] or hi == interior[-1]:
        width = None
    else:
        left = f[lo]+(half-power[lo])/(power[lo+1]-power[lo])*(f[lo+1]-f[lo])
        right = f[hi-1]+(half-power[hi-1])/(power[hi]-power[hi-1])*(f[hi]-f[hi-1])
        width = float(right-left)
    background = np.median(power[(abs(f-expected) > 120)&(abs(f-expected) < 220)])
    return dict(identified=True, peak_frequency_hz=float(f[p]), half_power_width_hz=width,
                peak_to_local_median_db=ratio_db(power[p], background))


def measure(audio, start, end):
    a, b = round(start*SR), round(end*SR)
    y = audio[a:b].astype(float)
    n = len(y)
    hann = np.hanning(n)
    nfft = 262144
    f = np.fft.rfftfreq(nfft, 1/SR)
    z = np.fft.rfft(y*hann[:, None], n=nfft, axis=0)
    p = np.mean(abs(z)**2, axis=1)/(nfft*np.sum(hann**2))
    p[1:-1] *= 2
    t = np.arange(a, b)/SR
    local = (t-t.mean())/(end-start)
    # Nominal harmonic families and linearly moving amplitudes, jointly fit.
    # Detuned individual oscillators are NOT fitted as separable columns.
    columns = [np.ones(n), local]
    for h in range(1, 16):
        angle = 2*np.pi*h*F0*t
        for amplitude in (np.ones(n), local):
            columns += [np.cos(angle)*amplitude, np.sin(angle)*amplitude]
    matrix = np.array(columns).T
    weights = np.sqrt(hann)
    coef, _, rank, singular = np.linalg.lstsq(matrix*weights[:, None], y*weights[:, None], rcond=None)
    residual = y-matrix@coef
    rows = []
    for h in HARMONICS:
        family_power = float(p[abs(f-h*F0) < 100].sum())
        cos, sin = coef[2+4*(h-1):4+4*(h-1)]
        phasor = cos-1j*sin
        mid, side = phasor.mean(), (phasor[0]-phasor[1])/2
        line = linewidth(f, p, h*F0)
        rows.append(dict(harmonic=h, frequency_hypothesis_hz=h*F0, band_power=family_power,
                         band_rms_dbfs=ratio_db(family_power),
                         right_minus_left_db=ratio_db(abs(phasor[1])**2, abs(phasor[0])**2),
                         right_minus_left_phase_degrees=float(np.angle(phasor[1]*phasor[0].conjugate(), deg=True)),
                         center_side_fraction=float(abs(side)**2/(abs(mid)**2+abs(side)**2)),
                         center_phasor_real=phasor.real.tolist(), center_phasor_imaginary=phasor.imag.tolist(),
                         **line))
    for row in rows:
        row["level_relative_to_h1_db"] = ratio_db(row["band_power"], rows[0]["band_power"])
        row["eligible_line"] = row["identified"] and row["peak_to_local_median_db"] >= 12 and row["level_relative_to_h1_db"] >= -55
    return dict(start_seconds=start, end_seconds=end, sample_count=n, native_bin_hz=SR/n,
                stereo=stereo(y), right_minus0p6db_sensitivity=stereo(y*np.array([1, 10**(-.6/20)])),
                harmonic_fit=dict(rank=int(rank), columns=matrix.shape[1], condition=float(singular[0]/singular[-1]),
                                  weighted_explained_power=float(1-np.sum(residual**2*hann[:, None])/np.sum(y*y*hann[:, None])),
                                  residual_stereo=stereo(residual)), harmonics=rows)


def controls():
    rows = []
    for start, end in WINDOWS:
        t = np.arange(round(.45*SR))/SR
        # A single tone with unequal gain and a fixed3-sample relative delay
        # also describes a narrowband wet echo; coherence alone is ambiguous.
        tone = np.stack([.1*np.sin(2*np.pi*F0*t), .083*np.sin(2*np.pi*F0*(t-3/SR))], axis=1)
        measured = measure(tone, start, end)
        rows.append(dict(window_seconds=[start, end], single_tone=measured,
                         expected_channel_phase_degrees=-360*F0*3/SR,
                         expected_right_minus_left_db=20*np.log10(.83),
                         interpretation="A deterministic delayed tone can stand for dry channel delay or a wet echo; this measurement cannot decide which."))
    beats = []
    for name, cents in (("Upper square pair", (1, -3)), ("Lower sine pair", (-5, 6))):
        frequencies = F0*2**(np.array(cents)/1200)
        spacing = float(abs(np.diff(frequencies)[0]))
        beats.append(dict(name=name, fine_cents=list(cents), frequencies_hz=frequencies.tolist(),
                          fundamental_spacing_hz=spacing, fundamental_beat_period_seconds=1/spacing,
                          harmonic_period_seconds={str(h):1/(h*spacing) for h in ((1, 3, 5, 7) if name.startswith("Upper") else (1,))},
                          fixed_zero_phase_first_minimum_seconds=.085+.5/spacing,
                          phase_caveat="Unknown oscillator phases move minima; values are arithmetic possibilities, not fitted source events or DSP renders."))
    return dict(single_tone_width_and_phase=rows, detuning_arithmetic=beats)


def plot(result, audio, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.signal import stft
    fig, ax = plt.subplots(3, 2, figsize=(12, 10), constrained_layout=True)
    t = np.arange(round(.445*SR))/SR
    x = audio[:len(t)]
    times = np.arange(.08, .421, .005)
    rms = [stereo(audio[round((c-.005)*SR):round((c+.005)*SR)]) for c in times]
    ax[0, 0].plot(times, [r["rms_dbfs"] for r in rms], color="black")
    ax[0, 0].set(title="Source10ms RMS; no key-up detector", ylabel="dBFS", xlabel="Source time (s)")
    f, tt, z = stft(x.mean(axis=1), SR, nperseg=1024, noverlap=980, nfft=8192, boundary=None, padded=False)
    selected = (f >= 480)&(f <= 760)
    ax[0, 1].pcolormesh(tt, f[selected], 20*np.log10(np.maximum(abs(z[selected]), 1e-15)), cmap="magma", vmin=-60, vmax=-12)
    ax[0, 1].axhline(F0, color="cyan", lw=.5)
    ax[0, 1].set(title="Fundamental-family context", ylabel="Hz", xlabel="Source time (s)")
    for axis in ax[0]:
        axis.axvspan(.16, .24, color="gray", alpha=.15)
        for start, end in WINDOWS:
            axis.axvspan(start, end, color="green", alpha=.12)
        axis.set_xlim(.075, .445)
    centers = [(a+b)/2 for a, b in WINDOWS]
    for h in (1, 3, 5, 7):
        rows = [next(x for x in w["harmonics"] if x["harmonic"] == h) for w in result["windows"]]
        ax[1, 0].plot(centers, [x["band_rms_dbfs"] for x in rows], "o-", label=f"H{h}")
        ax[1, 1].plot(centers, [x["right_minus_left_phase_degrees"] for x in rows], "o-", label=f"H{h}")
        ax[2, 0].plot(centers, [x["center_side_fraction"] for x in rows], "o-", label=f"H{h}")
    ax[1, 0].set(title="Harmonic-family energy ±100Hz", ylabel="dBFS", xlabel="Window center (s)")
    ax[1, 1].set(title="Center phasor R−L phase", ylabel="Degrees", xlabel="Window center (s)")
    ax[2, 0].set(title="Harmonic center side fraction", ylabel="S² / (M²+S²)", xlabel="Window center (s)")
    for w in result["windows"]:
        rows = [r for r in w["harmonics"] if r["eligible_line"]]
        ax[2, 1].plot([r["harmonic"] for r in rows], [r["half_power_width_hz"] for r in rows], "o-", label=f"{w['start_seconds']}–{w['end_seconds']}s")
    for row in result["controls"]["single_tone_width_and_phase"]:
        ax[2, 1].axhline(row["single_tone"]["harmonics"][0]["half_power_width_hz"], color="black", ls="--", alpha=.3)
    ax[2, 1].set(title="Linewidth versus window-limited pure tones", ylabel="Half-power width (Hz)", xlabel="Harmonic")
    for axis in ax[1:].flat:
        axis.legend(fontsize=8)
        axis.grid(alpha=.2)
    fig.suptitle("Ambient SQR first note: persistent pitched energy does not authenticate a key gate", fontsize=13)
    fig.savefig(out/"first-note-articulation.png", dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    mp3, bank = args.sources/"TOP8_AmbientSQR.mp3", args.sources/"SH-201_Patch_LEAD.zip"
    if sha(mp3) != MP3_SHA or sha(bank) != BANK_SHA:
        raise ValueError("Original source changed")
    data, member = read_bank(bank)
    name, blocks = parse_bank(data)[6]
    syx = out/"original-patch.syx"
    syx.write_bytes(encode_syx(blocks))
    if name != "Ambient SQR" or sha(syx) != SYX_SHA:
        raise ValueError("Published patch changed")
    inventory = ROOT/"Docs/fidelity/source-audits/reverb-reference-openings-2026-09-15.json"
    raw = next(r for r in json.loads(inventory.read_text())["references"] if r["id"] == "lead-07")
    if raw["patch_sha256"] != SYX_SHA:
        raise ValueError("Native control inventory does not match patch")
    decoded = copy.deepcopy(raw["decoded"])
    for part in ("upper", "lower"):
        for key in ("model_base_cutoff_hz_diagnostic", "model_base_cutoff_status"):
            decoded[part].pop(key, None)
    protocol = dict(windows_seconds=WINDOWS, note_hypothesis=74, f0_hz=F0,
                    candidate_audio_or_new_candidate_scores_consulted=False,
                    context="Source-only follow-up after earlier gain outcomes existed; no engine/candidate audio or scores read for this task, no canonical MIDI edit.",
                    measurement="Fixed full-rate stereo windows. Harmonic-family energy ±100Hz; interpolated interior FFT peak and half-power width. Joint nominal harmonics H1–15 with linear complex amplitude and DC/slope, without separating unresolved fine-tuned oscillators.",
                    eligibility="At least12dB peak above median bins120–220Hz away, and family level at least−55dB relative toH1. Weak rows retained.",
                    uncertainty="40–50ms windows have20–25Hz native bins; zero padding does not improve resolving power. Fitted L/R phase and side fraction are descriptions, not a dry/wet separator. Raw release values have no identified seconds mapping here.")
    save(out/"protocol-before-analysis.json", protocol)
    wav = out/"hardware-full.wav"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(mp3), "-c:a", "pcm_f32le", str(wav)]
    subprocess.run(command, check=True)
    sr, audio = wavfile.read(wav)
    if sr != SR or audio.ndim != 2 or audio.shape[1] != 2 or not np.isfinite(audio).all():
        raise ValueError("Unexpected original decode")
    audio = audio.astype(float)
    result = dict(schema_version=1, protocol=protocol, source=dict(path=str(mp3), sha256=sha(mp3), url="https://www.rolandus.com/go/sh-201_patches/mp3/LEAD/TOP8_AmbientSQR.mp3"),
                  bank=dict(path=str(bank), sha256=sha(bank), member=member, member_sha256=hashlib.sha256(data).hexdigest()),
                  patch=dict(path=str(syx), sha256=sha(syx), raw_reverb=raw["raw_reverb"], decoded=decoded),
                  inventory=dict(path=str(inventory), sha256=sha(inventory)),
                  decoder=dict(command=command, binary_sha256=sha(shutil.which("ffmpeg")), version=subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0], wav_sha256=sha(wav)),
                  tools={n:sha(ROOT/"Tools"/n) for n in (Path(__file__).name, "extract_reference_patch.py", "compare_hardware.py", "render_midi.py")},
                  windows=[measure(audio, start, end) for start, end in WINDOWS], controls=controls(),
                  gate_identification_status="unrecovered", equivalence_status="not_established")
    for h in HARMONICS:
        baseline = result["windows"][0]["harmonics"][HARMONICS.index(h)]["band_power"]
        for w in result["windows"]:
            row = w["harmonics"][HARMONICS.index(h)]
            row["level_relative_to_first_window_db"] = ratio_db(row["band_power"], baseline)
    canonical = ROOT/"Docs/fidelity/reconstructions/reverb-validation/ambient-sqr.json"
    proposal = json.loads(canonical.read_text())
    if (proposal["source_start_seconds"] != 0 or proposal["calibration_end_seconds"] != .405 or proposal["duration_seconds"] != .775
            or proposal["original_mp3_sha256"] != MP3_SHA or proposal["unmodified_sysex_sha256"] != SYX_SHA
            or [n["on"] for n in proposal["notes"]] != [.085, .418, .618]
            or [n["off"] for n in proposal["notes"]] != [.2, .53, .73]
            or any(n["velocity"] != 100 for n in proposal["notes"])):
        raise ValueError("Canonical source-only performance changed")
    proposal["id"] = "ambient-sqr-first-held-until-next"
    proposal["title"] = "Ambient SQR — exploratory first note held until next onset"
    proposal["notes"][0]["off"] = .418
    # The old operational bracket belongs to the earlier canonical case;
    # retaining it as the proposed note's off sensitivity would contradict
    # the explicit new0.418s gate. Its prior values are kept in metadata.
    proposal["notes"][0].pop("off_sensitivity_seconds")
    proposal["method"] = "Exploratory source-only articulation follow-up after earlier reverb candidate outcomes were known. Original MP3 measurements in fixed first-note windows show persistent narrow harmonic families through0.40s, changing harmonic balance and increasing stereo side energy. These cannot identify a key release or separate beating from releasing/wet tone. Extend only first D5 key-up to the already frozen next onset0.418s; retain all other canonical event times, velocity100, original complete patch, crop and calibration. No candidate audio or new candidate scores were used for this source analysis."
    proposal["reconstruction_parent_sha256"] = sha(canonical)
    proposal["sensitivity"] = dict(status="exploratory_after_known_candidate_outcomes_not_prospective_independent_validation",
                                   changed_event="Only note74 key-up:0.200→0.418s; same-time note-off is emitted before note76 note-on. This is a contiguous-gate sensitivity, not a held-key overlap/legato claim.",
                                   original_operational_off_bracket_seconds=[.16, .24], chosen_off_seconds=.418,
                                   rationale="Use the already frozen second onset as a bounded alternative; spectral persistence cannot prove this gate. Do not replace canonical cases or select the best-performing reconstruction.")
    proposal["validation_plan"]["frozen_before_candidate_render_or_score_inspection"] = False
    proposal["validation_plan"]["exploratory_variant_frozen_before_its_own_render_or_score"] = True
    proposal["validation_plan"]["comparison_policy"] = "Exploratory single first-gate extension after known earlier outcomes. Retain all earlier nine scenarios and this one; compare equal frozen inputs across DSP models without selecting the best reconstruction. Keep source_start0, calibration_end0.405, duration0.775; first held gate crosses calibration boundary by design."
    proposal["validation_plan"]["gate_sensitivity_suggestion"] = "This single additional0.418s first-note key-up; later key-ups0.530/0.730s unchanged. No additional fitted offsets or best-case selection."
    proposal["uncertainties"].append("This exploratory first-key-up extends beyond the original0.160–0.240s operational bracket because that bracket was not a recovered MIDI bound. Strong late narrow harmonics can be held/releasing oscillators or coherent effects; the source does not select among them. The new gate is frozen before its own render, after earlier model outcomes were known.")
    case = out/(proposal["id"]+".json")
    midi = case.with_suffix(".mid")
    save(case, proposal)
    write_midi(midi, proposal)
    parsed = parse_smf(midi.read_bytes(), SR)
    events, ignored = replay_events(parsed, tempo_policy="preserve-patch")
    old_parsed = parse_smf(canonical.with_suffix(".mid").read_bytes(), SR)
    old_events, old_ignored = replay_events(old_parsed, tempo_policy="preserve-patch")
    expected_events = copy.deepcopy(old_events)
    matches = [r for r in expected_events if r["kind"] == "midi" and r["value"] == "804a00"]
    if len(matches) != 1:
        raise ValueError("Unexpected first key-up identity")
    matches[0]["sample"] = round(.418*SR)
    if events != expected_events or ignored or old_ignored or parsed["end_sample"] != old_parsed["end_sample"]:
        raise ValueError("Exploratory MIDI changed more than the single first key-up")
    result["exploratory_articulation"] = dict(canonical_path=str(canonical), canonical_sha256=sha(canonical),
                                            canonical_midi_sha256=sha(canonical.with_suffix(".mid")),
                                            case_path=str(case), case_sha256=sha(case), midi_path=str(midi), midi_sha256=sha(midi), case_definition=proposal,
                                            midi_verification=dict(events=events, end_sample=parsed["end_sample"], sample_rate=SR,
                                                                   exactly_one_key_up_sample_changed=True, ignored_events=ignored))
    save(out/"results.json", result)
    plot(result, audio, out)
    print(json.dumps({"stereo":[w["stereo"] for w in result["windows"]], "beat_arithmetic":result["controls"]["detuning_arithmetic"]}, indent=2))


if __name__ == "__main__":
    main()

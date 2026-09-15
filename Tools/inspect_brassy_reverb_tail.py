#!/usr/bin/env python3
"""Source-only Brassy tail coverage, repetition and noise receipt; no decay fit.

Requires only original hash-pinned MP3/ZIP plus the tracked native patch audit.
Decodes a private WAV and records decoder identity. No model audio is opened.
Intervals below were frozen after complete-source spectrogram/RMS inspection,
before any decay regression or candidate score. They are conditional combined-FX
support, not a declaration that delay, AMP release or mastering is absent.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy import signal
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import assess_hardware_equivalence as assess
from extract_reference_patch import read_bank, parse_bank, encode_syx

ROOT = Path(__file__).resolve().parents[1]
MP3 = "TOP8_BrassyLd1.mp3"
MP3_SHA = "37b1c739ad3e1df4611b542f745111b78b51d9b372034275f5f1ceab48ed4c00"
ZIP = "SH-201_Patch_LEAD.zip"
ZIP_SHA = "102c47ee393c09115779172b8cbbb2c2f2563e0b4fdb2f57e0c8fca2a23c3b29"
BANK_SHA = "d6649236cd89c1652480f9ae194bc20f0a3e33e147cb16828216871fba35b26c"
SYX_SHA = "daba0b97a4b9e2674c4832050bbd0d8e869a3b61e9ce867c7055d21b0f4a6f5a"
BANDS = np.array([80, 160, 320, 640, 1280, 2560, 5120, 10240])
NOISE = [7.95, 8.30]
SUPPORT = {
    "early_echo_diagnostic": [14.65, 14.90],
    "conditional_training": [14.90, 15.20],
    "conditional_later_check": [15.20, 15.50],
    "low_level_sensitivity": [15.50, 15.80],
    "terminal_floor_diagnostic": [15.95, 16.03918367346939],
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def db(power):
    return float(10 * np.log10(max(float(power), 1e-30)))


def crop(y, sr, seconds):
    lo, hi = [round(t * sr) for t in seconds]
    if not 0 <= lo < hi <= len(y):
        raise ValueError("Invalid source interval")
    return y[lo:hi]


def rms_history(y, sr, width):
    n = round(width * sr)
    z = y[:len(y)//n*n].reshape(-1, n, 2)
    return dict(width_samples=n, midpoints_seconds=((np.arange(len(z))+.5)*n/sr).tolist(),
                stereo_rms_dbfs=(10*np.log10(np.maximum(np.mean(z*z, axis=(1, 2)), 1e-30))).tolist(),
                channel_rms_dbfs=(10*np.log10(np.maximum(np.mean(z*z, axis=1), 1e-30))).tolist())


def band_power(y, sr, nperseg):
    f, _, z = signal.stft(y, sr, nperseg=nperseg, noverlap=nperseg*3//4,
                         axis=0, boundary=None, padded=False)
    p = np.mean(abs(z)**2, axis=(1, 2))
    band = np.array([p[(f >= lo) & (f < hi)].sum() for lo, hi in zip(BANDS[:-1], BANDS[1:])])
    return band / max(band.sum(), 1e-30), z.shape[-1]


def describe(y, sr, seconds, floor):
    x = crop(y, sr, seconds)
    power = np.mean(x*x)
    channel_power = np.mean(x*x, axis=0)
    mid, side = (x[:, 0]+x[:, 1])/2, (x[:, 0]-x[:, 1])/2
    h = rms_history(x, sr, .01)
    minimum = min(h["stereo_rms_dbfs"])
    result = dict(seconds=seconds, samples=[round(t*sr) for t in seconds],
        rms_dbfs=db(power), channel_rms_dbfs=[db(p) for p in channel_power],
        level_above_quiet_reference_db=db(power)-floor,
        minimum_10ms_level_above_quiet_reference_db=minimum-floor,
        all_complete_10ms_bins_at_least_20db_above_quiet_reference=minimum-floor >= 20,
        side_over_mid_db=db(np.mean(side*side))-db(np.mean(mid*mid)),
        peak=float(abs(x).max()), exact_zero_samples=int(np.count_nonzero(x == 0)))
    if len(x) >= 8192:
        band, frames = band_power(x, sr, 4096)
        half = len(x)//2
        a, _ = band_power(x[:half], sr, 2048)
        b, _ = band_power(x[half:], sr, 2048)
        result.update(octave_power_fractions=band.tolist(), stft_frames=frames,
            half_octave_distribution_cosine=float(np.dot(a, b)/max(np.linalg.norm(a)*np.linalg.norm(b), 1e-30)),
            half_octave_distribution_L1=float(abs(a-b).sum()),
            second_over_first_half_rms_db=db(np.mean(x[half:]**2))-db(np.mean(x[:half]**2)))
    return result


def duplication(y, sr):
    # This diagnostic searches a single sample delay to test duplicated media.
    # It is never used to align a synthesizer, choose a decay window or fit T60.
    start, stop, search_start, search_stop = .1, 6.1, 8.35, 14.5
    x = crop(y, sr, [start, stop]).mean(axis=1)
    z = crop(y, sr, [search_start, search_stop]).mean(axis=1)
    cross = signal.correlate(z, x, mode="valid", method="fft")
    offset = round(search_start*sr) + int(np.argmax(cross)) - round(start*sr)
    rows = []
    for lo, hi in [[.1, 6.1], [5.9, 6.2], [6.25, 7.60]]:
        x = crop(y, sr, [lo, hi])
        z = y[round(lo*sr)+offset:round(hi*sr)+offset]
        if len(x) != len(z):
            raise ValueError("Repetition check exceeds source coverage")
        gain = float(np.sum(x*z)/np.sum(x*x))
        rows.append(dict(first_seconds=[lo, hi], second_samples=[round(lo*sr)+offset, round(hi*sr)+offset],
            stereo_waveform_cosine=float(np.sum(x*z)/(np.linalg.norm(x)*np.linalg.norm(z))),
            least_squares_scalar_gain_second_over_first=gain,
            gain_adjusted_relative_waveform_residual=float(np.linalg.norm(z-gain*x)/np.linalg.norm(z)),
            fixed_gain_one_relative_waveform_residual=float(np.linalg.norm(z-x)/np.linalg.norm(z))))
    return dict(method="Single integer-lag unnormalized waveform correlation, first .1–6.1 s within second 8.35–14.5 s; one scalar diagnostic gain per declared check only.",
        offset_samples=offset, offset_seconds=offset/sr, checks=rows,
        interpretation="Near-duplicate phrase and tail; do not count these as independent performances or independent excitation checks.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources", type=Path, required=True)
    p.add_argument("--inventory", type=Path, default=ROOT/"Docs/fidelity/source-audits/static-filter-reference-inventory-2026-09-15.json")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    inv = json.loads(a.inventory.read_text())
    reference = next(r for r in inv["references"] if r["id"] == "lead-08")
    mp3, bank = a.sources/MP3, a.sources/ZIP
    if sha(mp3) != MP3_SHA or sha(bank) != ZIP_SHA:
        raise ValueError("Original media/archive identity changed")
    data, member = read_bank(bank)
    if hashlib.sha256(data).hexdigest() != BANK_SHA or member != "SH-201_Patch_LEAD/100_LEAD.shl":
        raise ValueError("Bank member changed")
    name, blocks = parse_bank(data)[7]
    syx = encode_syx(blocks)
    if name != "Brassy Ld 1" or hashlib.sha256(syx).hexdigest() != SYX_SHA or reference["unmodified_sysex_sha256"] != SYX_SHA:
        raise ValueError("Original patch/native decoding audit differs")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("ffmpeg required")
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    wav = out/"hardware-full.wav"
    (out/"original-patch.syx").write_bytes(syx)
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(mp3.resolve()),
               "-ar", "44100", "-ac", "2", "-c:a", "pcm_f32le", str(wav)]
    subprocess.run(command, check=True)
    sr, y = assess.read_audio(wav)
    if sr != 44100 or y.shape[1] != 2 or not np.isfinite(y).all():
        raise ValueError("Unexpected decoded audio")
    quiet = crop(y, sr, NOISE)
    floor = db(np.mean(quiet*quiet))
    upper = reference["decoded"]["upper"]
    result = dict(schema_version=1,
        status="Isolated reverb-time anchor not identified: strong delay structure, duplicate earlier tail and a later-check level-guard failure. Retained windows support a qualified combined-effects diagnostic.",
        prohibited_inference="No decay slope/T60 fit, parameter estimate, candidate score or hardware-equivalence claim. No model audio opened.",
        selection="Brassy selected before source analysis as a third neutral-damping raw TIME64/SIZE7 anchor. Intervals frozen after complete-source RMS/spectrogram inspection, before any decay fit or candidate comparison.",
        reference=reference, source_paths=dict(mp3=str(mp3.resolve()), bank=str(bank.resolve())),
        source_sha256=dict(mp3=MP3_SHA, bank_zip=ZIP_SHA, bank_member=BANK_SHA, original_patch_syx=SYX_SHA),
        inventory_sha256=sha(a.inventory),
        raw_blocks={"common":list(blocks[0]), "upper":list(blocks[1]), "delay":list(blocks[3]), "reverb":list(blocks[4])},
        active_effect_controls=dict(delay_enabled=True, reverb_enabled=True, upper_delay_send=upper["delayDepth"],
            upper_reverb_send=upper["reverbDepth"], delay_time_raw=blocks[3][0], delay_feedback_percent=reference["decoded"]["delayFeedback"],
            delay_hf_damp_raw=blocks[3][2], delay_hf_damp_hz=3150, delay_mod_rate_raw=blocks[3][3], delay_mod_depth_raw=blocks[3][4],
            reverb_time_raw=blocks[4][0], reverb_size_raw=blocks[4][2], reverb_size_display=blocks[4][2]+1,
            reverb_predelay_raw=blocks[4][1], reverb_predelay_ms=1, reverb_high_cut_raw=blocks[4][3], reverb_high_cut_hz=12500,
            reverb_density_raw=blocks[4][4], reverb_diffusion_raw=blocks[4][5],
            reverb_lf_frequency_raw=blocks[4][6], reverb_lf_frequency_hz=4000, reverb_lf_gain_db=blocks[4][7]-36,
            reverb_hf_frequency_raw=blocks[4][8], reverb_hf_frequency_hz=4000, reverb_hf_gain_db=blocks[4][9]-36,
            mapping_basis="Native SysEx audit; physical enumeration labels corroborated by official editor tables retained in SeptumPatch.h. Raw TIME is not converted to a measured hardware decay."),
        decoder=dict(path=ffmpeg, sha256=sha(ffmpeg), version=subprocess.check_output([ffmpeg,"-version"], text=True).splitlines()[0]),
        decode_command=command, decoded_sha256=sha(wav), sample_rate=sr, sample_count=len(y), duration_seconds=len(y)/sr,
        peak=float(abs(y).max()), samples_at_or_above_full_scale=int(np.count_nonzero(abs(y)>=1)),
        tool_sha256={n:sha(ROOT/"Tools"/n) for n in [Path(__file__).name,"extract_reference_patch.py","assess_hardware_equivalence.py"]},
        physical_enumeration_header_sha256=sha(ROOT/"Source/DSP/SeptumPatch.h"),
        source_inspection=dict(last_obvious_new_pitch_onset_bracket_seconds=[14.34,14.41],
            final_direct_level_break_bracket_seconds=[14.55,14.61], conservative_obvious_direct_excitation_upper_bound_seconds=14.65,
            note_off_status="Unrecovered; brackets concern recorded pitch/energy changes, not exact MIDI note-off or absence of later delay excitation.",
            tail_structure="Renewed level lobes after direct break, visually repeating near .30 s spacing; retain full history. Active delay makes this a combined-effects tail, not an isolated reverb impulse response.",
            ending_status="File reaches near the inter-phrase quiet reference; final samples are nonzero. No obvious abrupt edit or forced digital silence in selected support. An undocumented smooth recording fade cannot be ruled out.",
            independent_check_status="Earlier quiet-tail section is near-duplicate source audio, not a new excitation."),
        quiet_reference=dict(seconds=NOISE, samples=[round(t*sr) for t in NOISE], rms_dbfs=floor,
            note="Empirical same-file quiet reference, not proven stationary hardware self-noise. Do not subtract it here.", history_10ms=rms_history(quiet,sr,.01)),
        support_policy=dict(intervals=SUPPORT, training_and_check_seconds=.30,
            level_guard="Every complete 10ms bin >=20dB above quiet-reference RMS. Measurement quality flag only, not perceptual equivalence.",
            use="Freeze these two .30s train/later-check supports only for a subsequently specified joint delay/reverb hypothesis. No best-region selection after scores. Earlier duplicate can test encoding repeatability only.",
            limitation="Each train/check is only about one visible echo step. A one-pole fit to their broadband slope cannot by itself identify reverb TIME64, regardless of fit precision."),
        octave_band_edges_hz=BANDS.tolist(),
        support={name:describe(y,sr,times,floor) for name,times in SUPPORT.items()},
        full_history_25ms=rms_history(y,sr,.025), final_tail_history_10ms=dict(start_seconds=14.4, **rms_history(crop(y,sr,[14.4,len(y)/sr]),sr,.01)),
        repetition=duplication(y,sr),
        final_10_stereo_samples=y[-10:].tolist())
    (out/"results.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    fig, axes = plt.subplots(2,2,figsize=(13,7.8),layout="constrained")
    for row,(lo,hi) in enumerate([(0,len(y)/sr),(13.8,len(y)/sr)]):
        x=crop(y,sr,[lo,hi])
        f,t,z=signal.stft(x,sr,nperseg=2048,noverlap=1536,axis=0,boundary=None,padded=False)
        axes[row,0].pcolormesh(t+lo,f,10*np.log10(np.maximum(np.mean(abs(z)**2,axis=1),1e-20)),vmin=-95,vmax=-25,cmap="magma",shading="auto")
        axes[row,0].set(xlim=(lo,hi),yscale="log",ylim=(80,6000),xlabel="Original recording time / s",ylabel="Hz")
        hist=rms_history(x,sr,.01)
        axes[row,1].plot(np.array(hist["midpoints_seconds"])+lo,hist["channel_rms_dbfs"],lw=.9)
        axes[row,1].axhline(floor,color="gray",ls=":",label="Quiet reference")
        axes[row,1].set(xlim=(lo,hi),ylim=(-100,0),xlabel="Original recording time / s",ylabel="L/R 10 ms RMS / dBFS")
        for key,color in [("conditional_training","#198b60"),("conditional_later_check","#2877be")]:
            a0,b0=SUPPORT[key]
            for ax in axes[row]: ax.axvspan(a0,b0,color=color,alpha=.2)
    axes[0,0].set_title("Complete source: near-duplicate phrases 8.356 s apart")
    axes[0,1].set_title("Earlier tail is not an independent excitation")
    axes[1,0].set_title("Final direct break around 14.56 s; echo structure remains")
    axes[1,1].set_title("Green training / blue check: combined-FX support only")
    fig.savefig(out/"feasibility.png",dpi=150)
    plt.close(fig)
    print(out/"results.json")


if __name__ == "__main__":
    main()

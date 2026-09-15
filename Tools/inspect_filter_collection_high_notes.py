#!/usr/bin/env python3
"""Descriptive same-collection high-note check, not capture-EQ identification."""
import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile
from scipy.optimize import minimize_scalar
from render_midi import parse_smf

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT/"Docs/fidelity/source-audits/deepsonic-acquisition-2026-09-15.json"
SR = 44100
NOTES = ((93, 18.25), (91, 18.75))
OFFSETS, WIDTHS = (.10, .16), (.06, .08)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract(audio, center, width):
    a, b = round((center-width/2)*SR), round((center+width/2)*SR)
    if a < 0 or b > len(audio):
        raise ValueError("Missing source coverage")
    return audio[a:b].astype(float)


def refine(x, nominal):
    t = (np.arange(len(x))-(len(x)-1)/2)/SR
    window = np.hanning(len(x))
    result = minimize_scalar(lambda f: -abs(np.dot(x*window, np.exp(-2j*np.pi*f*t))),
                             bounds=(nominal*.99, nominal*1.01), method="bounded",
                             options={"xatol": 1e-8})
    if abs(result.x/nominal-1) > .0099:
        raise ValueError("Local fundamental refinement hit its search bound")
    return float(result.x)


@lru_cache(maxsize=24)
def design(size, base):
    t = (np.arange(size)-(size-1)/2)/SR
    u = t/(size/SR/2)
    columns = [np.ones(size), u, u*u]
    for h in range(1, int(20000/base)+1):
        co, si = np.cos(2*np.pi*h*base*t), np.sin(2*np.pi*h*base*t)
        columns.extend((co, si, u*co, u*si, u*u*co, u*u*si))
    matrix = np.column_stack(columns)
    left, singular, right = np.linalg.svd(matrix, full_matrices=False)
    condition = float(singular[0]/singular[-1])
    if condition > 100:
        raise ValueError("Ill-conditioned harmonic estimate")
    return matrix, (right.T/singular)@left.T, condition


def measure(x, base):
    matrix, inverse, condition = design(len(x), base)
    coefficient = inverse@x
    residual = x-matrix@coefficient
    amplitude = np.hypot(coefficient[3::6], coefficient[4::6])
    power = np.dot(residual, residual)/(len(x)-len(coefficient))
    inverse_power = np.sum(inverse*inverse, axis=1)
    noise = np.sqrt(power*(inverse_power[3::6]+inverse_power[4::6]))
    h = np.arange(1, len(amplitude)+1)
    relative = 20*np.log10(np.maximum(amplitude, 1e-30)/amplitude[0])
    removed = relative+20*np.log10(h)
    return dict(base_hz=base, condition=condition,
                sample_sha256=hashlib.sha256(x.astype("<f8").tobytes()).hexdigest(),
                residual_power_fraction=float(np.mean(residual**2)/np.var(x)),
                harmonics=[dict(harmonic=int(i), frequency_hz=float(i*base), relative_h1_db=float(db),
                                saw_removed_db=float(db+20*np.log10(i)),
                                coefficient_snr_proxy_db=float(20*np.log10(max(amp, 1e-30)/max(n, 1e-30))))
                           for i, db, amp, n in zip(h, relative, amplitude, noise)],
                # Fixed neighboring-harmonic contrasts describe the SH dips;
                # they do not estimate a continuous notch frequency or Q.
                h6_minus_h5_removed_db=float(removed[5]-removed[4]),
                h7_minus_h6_removed_db=float(removed[6]-removed[5]),
                h8_minus_h7_removed_db=float(removed[7]-removed[6]))


def controls():
    rows = []
    for note, _ in NOTES:
        nominal = 440*2**((note-69)/12)
        base = nominal*1.005
        for notched in (False, True):
            profile = np.array([0., -1., -3., -6., -17., -23., -13., -16.]) if notched else -np.arange(8)*1.5
            # More context permits the same independently frozen refinement
            # and all width/offset combinations as the original audio.
            t = np.arange(round(.3*SR))/SR
            x = sum(.1/h*10**((profile[h-1] if h <= 8 else -30)/20)*
                    np.cos(2*np.pi*h*base*t+.173*h)
                    for h in range(1, int(20000/base)+1))
            measured_base = refine(extract(x, .10, .08), nominal)
            errors = []
            for offset in OFFSETS:
                for width in WIDTHS:
                    m = measure(extract(x, offset, width), measured_base)
                    errors.extend(r["saw_removed_db"]-p for r, p in zip(m["harmonics"], profile))
            if max(abs(np.array(errors))) > .001:
                raise ValueError("Independent additive harmonic control failed")
            rows.append(dict(note=note, notched=notched, actual_base_hz=base,
                             refined_base_hz=measured_base, max_h1_h8_error_db=float(max(abs(np.array(errors))))))
    return rows


def plot(result, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharey=True)
    labels = ("SH-201", "Tassmann 4", "Virus C", "Nord Modular", "Juno-106")
    for ax, (note, _) in zip(axes, NOTES):
        for source, label in zip(result["sources"], labels):
            row = next(w for w in source["windows"] if w["note"] == note
                       and w["offset_seconds"] == .10 and w["width_seconds"] == .08)
            selected = row["harmonics"][1:8]
            ax.plot([h["frequency_hz"]/1000 for h in selected],
                    [h["saw_removed_db"] for h in selected], "o-", label=label,
                    linewidth=2 if label == "SH-201" else 1)
        ax.set_title(f"Original MIDI note {note}, +100 ms / 80 ms")
        ax.set_xlabel("Measured harmonic frequency (kHz)")
        ax.grid(alpha=.2)
        ax.set_ylim(-30, 1)
    axes[0].set_ylabel("Harmonic / H1 after removing ideal Saw slope (dB)")
    axes[1].legend(fontsize=9)
    fig.suptitle("The SH-201 dip is absent from four same-collection comparisons", fontsize=13)
    fig.text(.5, .025, "Different synthesis/filter responses and unknown capture sessions; this does not identify capture EQ.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, .95))
    fig.savefig(destination, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--comparators", type=Path, required=True, help="Acquisition receipt JSON")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    protocol = dict(status="exploratory_collection_comparison_not_capture_transfer",
        selection="Four sources selected by primary-source inventory before measurement: software Tassmann, VA Virus/Nord, analog Juno. All share published saw/filter MIDI recipe; no matching raw patch, response or session is established.",
        notes=NOTES, offsets_seconds=OFFSETS, widths_seconds=WIDTHS,
        frequency_policy="Octave-unshifted fundamental confirmed in an exploratory spectrum inspection; local H1 peak within +/-1% of nominal is frozen on +100ms/80ms for each note/source. Same carrier used at later times and widths. Refinement includes moving-filter phase and is not a tuning measurement.",
        comparison="Fit quadratic complex amplitudes for all harmonics below20kHz. Fixed H5-H8 ratios describe the already observed SH notch/rebound. No equalization, source response fit, per-passage gain, alignment or SH DSP candidate.",
        limits="Recording-date tags are not same-session proof. Hardware and software source/filter responses and audio onset offsets differ. Absence of a shared dip cannot identify the SH capture chain or its oscillator. Residual-based SNR proxies include unresolved aliases and are not confidence intervals.")
    (out/"protocol.json").write_text(json.dumps(protocol, indent=2)+"\n")
    catalog = json.loads(CATALOG.read_text())
    midi_item = next(a for a in catalog["assets"] if Path(a["path"]).suffix == ".mid")
    midi = args.sources/Path(midi_item["path"]).name
    if sha(midi) != midi_item["sha256"]:
        raise ValueError("Original MIDI changed")
    events = parse_smf(midi.read_bytes())["events"]
    for note, on in NOTES:
        matches = [e for e in events if e["kind"] == "midi" and e["sample"] == round(on*SR)
                   and (bytes.fromhex(e["hex"])[0]&240) == 144
                   and bytes.fromhex(e["hex"])[1:] == bytes([note, 127])]
        if len(matches) != 1:
            raise ValueError("Original MIDI note identity changed")
    comparator_items = json.loads(args.comparators.read_text())
    if len(comparator_items) != 4:
        raise ValueError("Comparator count changed")
    identities = [dict(id="SH-201 LP12", path=str(args.sources/Path(a["path"]).name),
                       sha256=a["sha256"], url=a["url"])
                  for a in catalog["assets"] if Path(a["path"]).name == "roland_sh-201_-_filter_demo_-_lpf12_q000.mp3"]
    identities.extend(dict(id=a["probe"]["format"]["tags"]["title"], path=a["path"],
                           sha256=a["sha256"], url=a["url"]) for a in comparator_items)
    if len(identities) != 5:
        raise ValueError("Source count changed")
    result = dict(schema_version=1, protocol=protocol, tool_sha256=sha(__file__),
        comparator_receipt_sha256=sha(args.comparators), comparator_receipt=comparator_items,
        catalog_sha256=sha(CATALOG), midi_parser_sha256=sha(ROOT/"Tools/render_midi.py"),
        original_midi=midi_item, controls=controls(), sources=[])
    for i, identity in enumerate(identities):
        mp3 = Path(identity["path"])
        if sha(mp3) != identity["sha256"]:
            raise ValueError("Original audio changed")
        wav = out/f"source-{i}.wav"
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(mp3), "-c:a", "pcm_f32le", str(wav)]
        subprocess.run(command, check=True)
        rate, y = wavfile.read(wav)
        if rate != SR or y.ndim != 1 or not np.isfinite(y).all():
            raise ValueError("Unexpected original decode")
        rows = []
        for note, on in NOTES:
            nominal = 440*2**((note-69)/12)
            base = refine(extract(y, on+.10, .08), nominal)
            for offset in OFFSETS:
                for width in WIDTHS:
                    rows.append(dict(note=note, midi_onset_seconds=on, offset_seconds=offset,
                                     width_seconds=width, **measure(extract(y, on+offset, width), base)))
        result["sources"].append(dict(original=identity, decode_command=command,
                                       decoded_sha256=sha(wav), windows=rows))
        print(identity["id"], "complete", flush=True)
    plot(result, out/"comparison.png")
    result["plot_sha256"] = sha(out/"comparison.png")
    (out/"results.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(out/"results.json")


if __name__ == "__main__":
    main()

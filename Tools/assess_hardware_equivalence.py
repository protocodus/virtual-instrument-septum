#!/usr/bin/env python3
"""Measure raw hardware/render audio agreement without certifying synth identity.

The public-demo mode reads a compare_hardware.py comparison.json, checks its raw
audio hashes, and reports time-resolved spectral, envelope and stereo errors.
No default perceptual pass margin exists. A separate, previously registered
protocol may supply justified bounds; a bounds pass remains limited to these
inputs and is never a market-ranking or whole-instrument equivalence claim.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import sys

import numpy as np
import scipy
from scipy import signal
from scipy.io import wavfile


FLOOR_DB = -80.0
ACTIVE_DB = -60.0
REQUIRED_BOUNDS = (
    "spectral_convergence_mean", "log_spectral_error_db_mean",
    "envelope_error_db_p95_max", "stereo_side_fraction_error",
    "stereo_balance_error_db",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_audio(path):
    sr, samples = wavfile.read(path)
    if samples.dtype.kind == "u" and samples.dtype.itemsize == 1:
        samples = (samples.astype(np.float64) - 128.0) / 128.0
    elif samples.dtype.kind == "i":
        samples = samples.astype(np.float64) / (2 ** (samples.dtype.itemsize * 8 - 1))
    elif samples.dtype.kind == "f":
        samples = samples.astype(np.float64)
    else:
        raise ValueError(f"Unsupported WAV encoding: {path}")
    if samples.ndim == 1:
        samples = samples[:, None]
    if samples.ndim != 2 or samples.shape[1] not in (1, 2):
        raise ValueError("Audio must have one or two channels")
    if not np.isfinite(samples).all():
        raise ValueError(f"Nonfinite audio: {path}")
    if len(samples) < sr / 4:
        raise ValueError("A measurement needs at least 250 ms of audio")
    if not np.any(samples):
        raise ValueError(f"Silent audio is not an equivalence benchmark: {path}")
    return int(sr), samples


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


def rms_envelope(x, window, hop=1):
    power = np.mean(x * x, axis=1)
    # Cumulative subtraction avoids FFT round-off lifting truly silent tails.
    cumulative = np.concatenate(([0.0], np.cumsum(power)))
    return np.sqrt(np.maximum((cumulative[window:] - cumulative[:-window]) / window, 0))[::hop]


def fit_transform(reference, candidate, sr, calibration_frames, max_lag_seconds):
    """Fit one integer delay using envelope correlation, then one RMS gain.

    candidate[t + lag] is paired with reference[t]. No per-note gains, pitch
    changes, polarity inversion, EQ, resampling or time warping are fitted.
    """
    bound = round(max_lag_seconds * sr)
    window = max(1, round(.01 * sr))
    if calibration_frames < 2 * bound + window + round(.05 * sr):
        raise ValueError("Calibration is too short for the requested lag search")
    lag = 0
    score = None
    identifiable = None
    if bound:
        a = rms_envelope(reference[:calibration_frames], window)
        b = rms_envelope(candidate[:calibration_frames], window)
        fixed = a[bound:len(a) - bound]
        centered = fixed - fixed.mean()
        ref_var = float(np.dot(centered, centered))
        size = len(fixed)
        # Remove the common DC before rolling variance/correlation. Otherwise
        # subtracting large nearly equal sums can invent variance in a flat
        # envelope. Centering does not change Pearson correlation.
        centered_candidate = b - b.mean()
        sums = np.concatenate(([0.0], np.cumsum(centered_candidate)))
        squares = np.concatenate(([0.0], np.cumsum(centered_candidate * centered_candidate)))
        variances = np.maximum(squares[size:] - squares[:-size]
                               - (sums[size:] - sums[:-size]) ** 2 / size, 0)
        denominator = np.sqrt(variances * ref_var)
        # A prefix can be mostly silence before its first attack. FFT error
        # divided by a near-silent window's tiny variance can exceed 1 and
        # select a false "perfect" match. Require supported variation relative
        # to this candidate's whole prefix energy; the guard is gain invariant.
        variance_floor = 1e-12 * max(float(np.dot(b, b)), 1e-30)
        supported = (variances > variance_floor) & (denominator > 1e-30)
        identifiable = bool(ref_var > 1e-12 * max(float(np.dot(fixed, fixed)), 1e-30))
        if identifiable:
            correlations = signal.correlate(centered_candidate, centered, mode="valid", method="fft")
            normalized = np.divide(correlations, denominator,
                                   out=np.full_like(correlations, -np.inf),
                                   where=supported)
            index = int(np.argmax(normalized))
            if math.isfinite(float(normalized[index])):
                lag = index - bound
                score = float(np.clip(normalized[index], -1, 1))
            else:
                identifiable = False
    start, end = max(0, -lag), min(calibration_frames, calibration_frames - lag)
    a, b = reference[start:end], candidate[start + lag:end + lag]
    if rms(a) <= 1e-12 or rms(b) <= 1e-12:
        raise ValueError("The calibration interval must contain audible audio in both files")
    gain = rms(a) / rms(b)
    return {"candidate_lag_samples": lag, "candidate_lag_seconds": lag / sr,
            "candidate_gain": gain, "candidate_gain_db": 20 * math.log10(gain),
            "calibration_frames": calibration_frames,
            "max_lag_seconds": max_lag_seconds,
            "alignment_method": "10 ms RMS-envelope normalized correlation; integer sample grid",
            "alignment_correlation": score, "alignment_identifiable": identifiable,
            "alignment_at_search_boundary": bool(bound and abs(lag) == bound),
            "gain_method": "one scalar RMS gain over calibration interval after alignment",
            "allowed_transforms": ["one global integer delay", "one positive scalar gain"]}


def stereo_stats(y):
    if y.shape[1] == 1:
        return None
    left, right = y.T
    power = float(np.mean(y * y))
    floor = max(power * 10 ** (FLOOR_DB / 10), 1e-30)
    mid, side = (left + right) / 2, (left - right) / 2
    mp, sp = float(np.mean(mid * mid)), float(np.mean(side * side))
    lp, rp = float(np.mean(left * left)), float(np.mean(right * right))
    correlation = float(np.mean(left * right) / max(math.sqrt(lp * rp), 1e-30))
    return {"side_fraction": sp / max(mp + sp, 1e-30),
            "side_to_mid_db": 10 * math.log10(max(sp, floor) / max(mp, floor)),
            "balance_db": 10 * math.log10(max(lp, floor) / max(rp, floor)),
            "uncentered_channel_correlation": float(np.clip(correlation, -1, 1))}


def measure(reference, candidate, sr):
    if reference.shape != candidate.shape:
        raise ValueError("Paired audio must have identical frames and channel layouts")
    if len(reference) < sr / 4:
        raise ValueError("Evaluation must contain at least 250 ms")
    if rms(reference) <= 1e-12:
        raise ValueError("Reference evaluation interval is silent")
    resolutions = []
    # Long windows separate low bass harmonics; short windows preserve attacks.
    for seconds in (512 / 44100, 2048 / 44100, 8192 / 44100):
        nfft = 2 ** round(math.log2(seconds * sr))
        if nfft > len(reference):
            continue
        spectra = []
        for audio in (reference, candidate):
            _, _, z = signal.stft(audio, fs=sr, window="hann", nperseg=nfft,
                                   noverlap=nfft * 3 // 4, boundary=None,
                                   padded=False, axis=0)
            spectra.append(np.abs(z))
        a, b = spectra
        peak = float(np.max(a))
        floor = max(peak * 10 ** (FLOOR_DB / 20), 1e-30)
        active = np.maximum(a, b) >= max(peak * 10 ** (ACTIVE_DB / 20), 1e-30)
        differences = np.abs(20 * np.log10(np.maximum(b, floor) / np.maximum(a, floor)))
        resolutions.append({
            "window_samples": nfft, "hop_samples": nfft // 4,
            "frames": int(a.shape[-1]), "frequency_resolution_hz": sr / nfft,
            "spectral_convergence": float(np.linalg.norm(b - a) / max(np.linalg.norm(a), 1e-30)),
            "log_spectral_error_db_mean": float(np.mean(differences[active])),
            "log_spectral_error_db_p95": float(np.percentile(differences[active], 95)),
            "active_time_frequency_channel_bins": int(np.count_nonzero(active)),
        })
    envelopes = []
    ref_peak = float(np.max(np.abs(reference)))
    floor = max(ref_peak * 10 ** (FLOOR_DB / 20), 1e-30)
    for seconds in (.01, .05):
        window, hop = round(seconds * sr), max(1, round(.005 * sr))
        a, b = (rms_envelope(x, window, hop) for x in (reference, candidate))
        active = np.maximum(a, b) >= max(float(np.max(a)) * 10 ** (ACTIVE_DB / 20), 1e-30)
        delta = np.abs(20 * np.log10(np.maximum(b, floor) / np.maximum(a, floor)))
        envelopes.append({"window_samples": window, "hop_samples": hop,
                          "error_db_mean": float(np.mean(delta[active])),
                          "error_db_p95": float(np.percentile(delta[active], 95))})
    ref_stereo, cand_stereo = stereo_stats(reference), stereo_stats(candidate)
    residual = rms(candidate - reference) / rms(reference)
    summary = {
        "spectral_convergence_mean": float(np.mean([s["spectral_convergence"] for s in resolutions])),
        "log_spectral_error_db_mean": float(np.mean([s["log_spectral_error_db_mean"] for s in resolutions])),
        "envelope_error_db_p95_max": max(e["error_db_p95"] for e in envelopes),
        "stereo_side_fraction_error": (abs(cand_stereo["side_fraction"] - ref_stereo["side_fraction"])
                                       if ref_stereo else None),
        "stereo_balance_error_db": (abs(cand_stereo["balance_db"] - ref_stereo["balance_db"])
                                    if ref_stereo else None),
    }
    return {"summary": summary, "multi_resolution_stft": resolutions,
            "rms_envelope": envelopes,
            "stereo": {"reference": ref_stereo, "candidate": cand_stereo},
            "raw_level_difference_db": 20 * math.log10(max(rms(candidate), 1e-30) / rms(reference)),
            "waveform_diagnostic": {"normalized_rms_residual": residual,
                                    "residual_db_relative_to_reference": 20 * math.log10(max(residual, 1e-30)),
                                    "used_for_bounds": False,
                                    "limitation": "Free oscillator phases, modulation and capture clocks can defeat a null despite similar sound."}}


def verify_artifact(base, item):
    path = (base / item["path"]).resolve()
    if digest(path) != item["sha256"]:
        raise ValueError(f"Artifact hash mismatch: {path}")
    return {"path": str(path), "sha256": item["sha256"]}


def read_provenance(path):
    """Keep performance and patch certainty independent, including public MIDI
    with a documented physical-panel recipe but no recording-specific dump.
    """
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported provenance schema")
    allowed = {
        "midi": {"original_performance", "reconstructed_not_original", "unknown"},
        "preset": {"recording_specific_verified_dump", "published_named_preset_recording_revision_unverified",
                   "documented_recipe_reconstruction", "unknown"},
    }
    inputs = {}
    for kind, choices in allowed.items():
        item = data.get(kind, {})
        if item.get("status") not in choices:
            raise ValueError(f"Unknown {kind} provenance status")
        inputs[kind] = dict(item)
        if item["status"] != "unknown":
            if not item.get("artifact"):
                raise ValueError(f"The stated {kind} provenance requires a hashed artifact")
            inputs[kind]["artifact"] = verify_artifact(path.parent, item["artifact"])
    if not data.get("source_url") or not isinstance(data.get("uncertainties"), list):
        raise ValueError("Provenance needs a source URL and an explicit uncertainties list")
    return {"kind": "documented_public_audio_pair", "source_url": data["source_url"],
            "inputs": inputs, "uncertainties": data["uncertainties"],
            "description": data.get("description"), "provenance_manifest_sha256": digest(path),
            "verification_limit": "Hashes establish artifact identity; author attribution and the claimed recording association require source review."}


def assess_bounds(measurements, protocol, protocol_path, has_calibration_split, evaluation_identity):
    """Bounds are externally justified, never invented from a candidate score.

    Evidence declarations are retained for human review: verifying file hashes
    does not authenticate a physical-unit recording or a preregistration date.
    """
    if protocol is None:
        return {"status": "not_established", "within_registered_bounds": None,
                "reasons": ["No independently justified, registered acceptance margins were supplied.",
                            "Feature distances have no built-in threshold for perceptual equivalence."]}
    reasons = []
    if protocol.get("schema_version") != 1:
        raise ValueError("Unsupported bounds protocol schema")
    for field in ("scope", "margin_justification", "public_input_uncertainty_assessment"):
        if not isinstance(protocol.get(field), str) or not protocol[field].strip():
            reasons.append(f"Missing {field}")
    for field in ("registered_before_evaluation", "evaluation_not_used_for_dsp_tuning"):
        if protocol.get(field) is not True:
            reasons.append(f"Missing affirmative declaration: {field}")
    if not has_calibration_split:
        reasons.append("No separate interval for nuisance calibration; evaluation was also used for gain fitting.")
    if protocol.get("evaluation") != evaluation_identity:
        reasons.append("Registered evaluation identity does not match this reference, split, lag search and analysis tool.")
    artifacts = []
    for category in ("hardware_repeatability_evidence", "perceptual_validation_evidence", "registration_evidence"):
        evidence = protocol.get(category, [])
        if not evidence:
            reasons.append(f"Missing {category}")
        for item in evidence:
            artifacts.append({"category": category, **verify_artifact(protocol_path.parent, item)})
    bounds = protocol.get("maximum_errors", {})
    checks = {}
    for key in REQUIRED_BOUNDS:
        if key not in bounds:
            reasons.append(f"Missing required margin: {key}")
            continue
        threshold = bounds[key]
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or threshold < 0:
            raise ValueError(f"Invalid maximum error for {key}")
        value = measurements["summary"][key]
        checks[key] = {"measured": value, "maximum": threshold,
                       "within_bound": value is not None and value <= threshold}
    # Report failed margins even when provenance is insufficient, without
    # attributing their cause solely to DSP or confusing absence with success.
    within = bool(checks) and all(c["within_bound"] for c in checks.values())
    return {"status": ("not_established" if reasons else
                       "within_registered_bounds" if within else "outside_registered_bounds"),
            "within_registered_bounds": within if len(checks) == len(REQUIRED_BOUNDS) else None,
            "checks": checks, "reasons": reasons, "evidence_artifacts": artifacts,
            "protocol_declarations": protocol,
            "limitation": "File hashes verify artifact identity, not provenance truth or prior registration; human evidence review is required."}


def evaluate(reference_path, candidate_path, *, comparison_path=None, calibration_seconds=None,
             max_lag_seconds=0, protocol_path=None, provenance_path=None, calibration_fraction=None):
    if comparison_path and provenance_path:
        raise ValueError("Use either comparison provenance or a separate provenance manifest")
    if not math.isfinite(max_lag_seconds) or not 0 <= max_lag_seconds <= .5:
        raise ValueError("Maximum lag must be finite and between 0 and 500 ms")
    if calibration_seconds is not None and calibration_fraction is not None:
        raise ValueError("Specify calibration seconds or fraction, not both")
    if max_lag_seconds and calibration_seconds is None and calibration_fraction is None:
        raise ValueError("Lag fitting requires an explicit, separate calibration interval")
    sr, reference = read_audio(reference_path)
    candidate_sr, candidate = read_audio(candidate_path)
    if sr != candidate_sr:
        raise ValueError("Sample rates differ; supply documented decoded PCM at a common rate")
    if reference.shape[1] != candidate.shape[1]:
        raise ValueError("Channel layouts differ; no implicit stereo downmix is allowed")
    qualification = {"kind": "unqualified_audio_pair", "uncertainties": ["No recording/input provenance supplied."]}
    if provenance_path:
        qualification = read_provenance(provenance_path)
    comparison = None
    if comparison_path:
        comparison = json.loads(comparison_path.read_text())
        for path in (reference_path, candidate_path):
            if digest(path) != comparison["files"].get(path.name):
                raise ValueError(f"Raw audio does not match comparison manifest: {path}")
        frames = comparison["comparison_frames"]
        if isinstance(frames, bool) or not isinstance(frames, int) or frames <= 0:
            raise ValueError("Invalid comparison frame count")
        if len(reference) != frames or len(candidate) < frames:
            raise ValueError("Comparison manifest frame count does not match the WAVs")
        candidate = candidate[:frames]
        qualification = {"kind": "published_preset_public_recording",
                         "description": comparison.get("qualification"),
                         "midi_status": comparison.get("case", {}).get("midi_status"),
                         "case_id": comparison.get("case", {}).get("id"),
                         "reference_id": comparison.get("reference", {}).get("id"),
                         "uncertainties": comparison.get("comparison_limits", []),
                         "comparison_manifest_sha256": digest(comparison_path)}
    if reference.shape != candidate.shape:
        raise ValueError("Audio lengths differ; crop explicitly or supply a comparison manifest")
    frames = len(reference)
    if calibration_fraction is not None:
        if not math.isfinite(calibration_fraction) or not 0 < calibration_fraction < 1:
            raise ValueError("Calibration fraction must be finite and strictly between zero and one")
        calibration_seconds = frames * calibration_fraction / sr
    split = calibration_seconds is not None
    if split:
        if not math.isfinite(calibration_seconds) or calibration_seconds <= 0:
            raise ValueError("Calibration duration must be finite and positive")
        calibration = round(calibration_seconds * sr)
        if calibration + round(.25 * sr) + round(max_lag_seconds * sr) > frames:
            raise ValueError("Calibration leaves less than 250 ms of evaluation audio")
    else:
        calibration = frames
    transform = fit_transform(reference, candidate, sr, calibration, max_lag_seconds)
    lag = transform["candidate_lag_samples"]
    # A guard keeps both analysis windows after calibration even for negative
    # lag. No feature frame ever crosses the fitted/evaluated boundary.
    start = max(calibration if split else 0, (calibration if split else 0) - lag)
    end = min(frames, frames - lag)
    raw = measure(reference[start:end], candidate[start:end], sr)
    corrected = measure(reference[start:end], candidate[start + lag:end + lag] * transform["candidate_gain"], sr)
    protocol = json.loads(protocol_path.read_text()) if protocol_path else None
    evaluation_identity = {"reference_sha256": digest(reference_path),
                           "calibration_frames": calibration,
                           "max_lag_seconds": max_lag_seconds,
                           "analysis_tool_sha256": digest(__file__)}
    gate = assess_bounds(corrected, protocol, protocol_path, split, evaluation_identity)
    return {"schema_version": 1,
            "conclusion": "No complete-instrument equivalence or market-superiority claim is made by this report.",
            "qualification": qualification,
            "acceptance_gate": gate,
            "evaluation_identity": evaluation_identity,
            "sources": {"reference": {"path": str(reference_path.resolve()), "sha256": digest(reference_path)},
                        "candidate": {"path": str(candidate_path.resolve()), "sha256": digest(candidate_path)}},
            "audio": {"sample_rate": sr, "channels": reference.shape[1], "source_comparison_frames": frames,
                      "evaluation_reference_start_sample": start, "evaluation_reference_end_sample": end,
                      "evaluation_candidate_start_sample_after_alignment": start + lag,
                      "evaluation_frames": end - start},
            "calibration": {"separate_prefix": split,
                            "held_out_from_dsp_tuning": protocol.get("evaluation_not_used_for_dsp_tuning") if protocol else None,
                            "qualification": ("The time split only separates nuisance fitting; it does not prove that DSP tuning excluded this recording."
                                              if split else "Whole-excerpt gain fitting: exploratory, not held-out validation."),
                            **transform},
            "raw_measurements": raw,
            "calibrated_measurements": corrected,
            "analysis_parameters": {"magnitude_floor_db_relative_to_reference_peak": FLOOR_DB,
                                    "active_bin_threshold_db_relative_to_reference_peak": ACTIVE_DB,
                                    "active_bin_rule": "union of reference and candidate; candidate-only energy is included",
                                    "stft_channels": "separate channels; no phase alignment or mono reduction",
                                    "frequency_range": "DC through Nyquist",
                                    "interpretation": "The numerical floor and activity threshold define measurements, not perceptual acceptance limits."},
            "limitations": [
                "Differences include reconstruction, preset revision, performance, recording-chain, codec and synthesizer effects.",
                "Similar centroids, average spectra or RMS levels alone cannot establish matching output.",
                "Magnitude spectra tolerate carrier phase but still depend on modulation phase and note timing.",
                "The measures are not a psychoacoustic model or an ABX listening test.",
                "Scalar gain hides absolute output-level error; raw measures retain that discrepancy.",
                "A positive result applies only to the registered recordings, inputs, parameter range and output path.",
            ],
            "runtime": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
            "tool_sha256": digest(__file__)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, help="Existing comparison.json; uses its raw WAVs and hashes")
    parser.add_argument("--reference", type=Path, help="Reference WAV when no comparison manifest is available")
    parser.add_argument("--candidate", type=Path, help="Candidate WAV when no comparison manifest is available")
    parser.add_argument("--calibration-seconds", type=float, help="Fit nuisance gain/delay on this prefix; evaluate after it")
    parser.add_argument("--calibration-fraction", type=float, help="Alternative prefix length as fraction of the reference excerpt")
    parser.add_argument("--max-lag-seconds", type=float, default=0, help="Bounded global delay search; default zero")
    parser.add_argument("--protocol", type=Path, help="Previously registered, evidence-backed acceptance margins")
    parser.add_argument("--provenance", type=Path, help="Public recording input provenance; MIDI and patch status are independent")
    parser.add_argument("--output", required=True, type=Path, help="New JSON report; existing files are not overwritten")
    args = parser.parse_args()
    if args.comparison:
        if args.reference or args.candidate:
            parser.error("--comparison cannot be combined with --reference/--candidate")
        args.reference = args.comparison.parent / "hardware-excerpt-raw.wav"
        args.candidate = args.comparison.parent / "septum-raw.wav"
    elif not (args.reference and args.candidate):
        parser.error("Supply --comparison, or both --reference and --candidate")
    try:
        result = evaluate(args.reference, args.candidate, comparison_path=args.comparison,
                          calibration_seconds=args.calibration_seconds,
                          max_lag_seconds=args.max_lag_seconds, protocol_path=args.protocol,
                          provenance_path=args.provenance, calibration_fraction=args.calibration_fraction)
        with args.output.open("x") as out:
            json.dump(result, out, indent=2, allow_nan=False)
            out.write("\n")
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps({"output": str(args.output), "acceptance_gate": result["acceptance_gate"]["status"],
                      "metrics": result["calibrated_measurements"]["summary"]}, indent=2))


if __name__ == "__main__":
    main()

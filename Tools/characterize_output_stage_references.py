#!/usr/bin/env python3
"""Fixed output-level/dynamics/band characterization; no DSP, patch or curve fitting.

The K-weighted sensitivity uses shared original-derived blocks, so it is not
reported as an independently gated broadcast compliance measurement.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
import numpy as np
import scipy
from scipy import signal
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
SR = 44100
BANDS = ((20, 120), (120, 500), (500, 2000), (2000, 6000), (6000, 16000))
INTEGRATION_SHA = "a96632cc2912a941ed2201835a035ecae9b4754d2627d5b3dd3e970278720ca3"
MASK_SHA = "232cfa31fe7da169a89d10a476f81f49380c42a67399c4c49b727f0617b7072b"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin(path, expected=None):
    path = Path(path).resolve()
    actual = sha(path)
    if expected is not None and actual != expected:
        raise ValueError("Changed pinned input: " + str(path))
    return dict(path=str(path), sha256=actual)


def checked(item):
    return pin(item["path"], item["sha256"])


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False)+"\n")


def db(power):
    return 10*np.log10(np.maximum(power, 1e-30))


def rms(audio):
    return float(np.sqrt(np.mean(np.square(audio))))


def k_sections(rate):
    # De Man parametrization of the BS.1770 weighting filters; the resulting
    # coefficient arrays are frozen in the protocol and checked at 48 kHz.
    corner, quality = 1681.9744509555319, .7071752369554193
    tangent = np.tan(np.pi*corner/rate)
    high_gain = 10**(3.99984385397/20)
    middle_gain = high_gain**.499666774155
    denominator = 1+tangent/quality+tangent*tangent
    shelf = [(high_gain+middle_gain*tangent/quality+tangent*tangent)/denominator,
             2*(tangent*tangent-high_gain)/denominator,
             (high_gain-middle_gain*tangent/quality+tangent*tangent)/denominator,
             1, 2*(tangent*tangent-1)/denominator,
             (1-tangent/quality+tangent*tangent)/denominator]
    tangent = np.tan(np.pi*38.13547087613982/rate)
    quality = .5003270373253953
    denominator = 1+tangent/quality+tangent*tangent
    highpass = [1, -2, 1, 1, 2*(tangent*tangent-1)/denominator,
                (1-tangent/quality+tangent*tangent)/denominator]
    return np.array([shelf, highpass])


def read(info, mono=False):
    checked(info)
    rate, audio = wavfile.read(info["path"])
    if rate != SR or audio.dtype != np.float32 or not np.isfinite(audio).all():
        raise ValueError("Unexpected pinned raw format")
    if audio.ndim == 1:
        audio = audio[:, None]
    if mono:
        audio = audio.mean(axis=1, keepdims=True)
    return audio.astype(np.float64)


def prepare(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    ip = pin(args.integration, INTEGRATION_SHA)
    integration = json.loads(args.integration.read_text())
    factory_info = checked(integration["protocol"]["official_run"])
    factory = json.loads(Path(factory_info["path"]).read_text())
    dry_info = pin(ROOT/"Docs/fidelity/source-audits/saw-w4-engine-dry-comparison-2026-09-15.json")
    dry = json.loads(Path(dry_info["path"]).read_text())
    original_masks = pin(ROOT/"build-fidelity/saw-w4-official-comparison/original-mask-01/results.json", MASK_SHA)
    masks = json.loads(Path(original_masks["path"]).read_text())
    cases = []
    for row in integration["results"]:
        if not row["byte_identical"] or not row["integration_pass"]:
            raise ValueError("Native candidate identity prerequisite failed")
        checked(row["production"])
        if row["cohort"] == "dry":
            source = next(s for s in dry["slopes"] if "lp"+str(s["slope"]) == row["id"])
            reference = source["decoded"]
            segments = source["supports"]["primary_all"]
            gain = source["models"]["w4"]["fixed_primary_gain"]
            lag = dry["protocol"]["lag_samples"]
            spectral_controls = {r["window_samples"]: dict(bins=r["hardware_only_log_error"]["bins"])
                for r in source["models"]["w4"]["primary_fixed_gain"]["primary_all"]["stft"]}
            original = source["original"]
            context = "Original MIDI, reconstructed dry physical recipe; exclude note36 calibration and entire fitted note91 interval"
        else:
            source = next(c for c in factory["cases"] if c["id"] == row["id"])
            reference = source["input"]["hardware"]
            segments = [source["evaluated_reference_samples"]]
            gain, lag = source["fixed_gain"], source["input"]["lag_samples"]
            spectral_controls = {r["window_samples"]: dict(bins=r["original_active_bins"], mask_sha256=r["mask_packbits_sha256"])
                for r in next(c for c in masks["cases"] if c["id"] == row["id"])["resolutions"]}
            original = source["input"]["original_comparison"]
            context = "Published same-name patch; original performance, recorded patch revision and capture processing remain unverified"
        checked(reference)
        checked(original)
        cases.append(dict(id=row["id"], cohort=row["cohort"], original=original, reference=reference,
            production=row["production"], native_receipt=row["production_receipt"], native_candidate_byte_identity=True,
            reference_segments=segments, candidate_segments=[[a+lag,b+lag] for a,b in segments], lag_samples=lag,
            fixed_gain=gain, channel_policy="mean mono, matching prior dry assessment" if row["cohort"] == "dry" else "stereo channels retained",
            inherited_spectral_controls=spectral_controls, context=context))
    protocol = dict(status="frozen_before_output_characterization", tool=pin(__file__), integration=ip,
        factory_measurement=factory_info, dry_measurement=dry_info, original_mask_measurement=original_masks,
        cases=cases, expected_case_count=12,
        sample_policy="Exact existing evaluated samples, lag and fixed gain; no joins inside STFT/RMS/loudness frames. K filters process complete source/candidate streams to preserve earlier filter state.",
        primary="Saved production-prefix scalar for official cases; saved note36 scalar for dry. No new fit.",
        loudness_sensitivity="One scalar per case from all evaluated original-selected K-weighted400ms blocks, hop100ms, absolute-70 and relative-10 gates derived only from original. Post-hoc descriptive sensitivity; not a training gain, candidate fit, or independently gated LUFS compliance test.",
        weighting=dict(sos=k_sections(SR).tolist(), offset_db=-.691, channel_power_weights="unity per retained channel; no downmix for stereo", design_urls=[
            "https://github.com/csteinmetz1/pyloudnorm/blob/master/pyloudnorm/iirfilter.py",
            "https://github.com/csteinmetz1/pyloudnorm/blob/master/pyloudnorm/meter.py"]),
        dynamics="Sample peak/RMS/crest, absolute-sample percentiles and fourth moment.10/50ms RMS hop220samples; original-active threshold-60dB, magnitude floor-80dB. Original RMS quartiles fix low/high groups; no response curve fitted.",
        transients="Original-only50ms RMS rises over approximately50ms, >=3dB, current original level within30dB of peak, peaks separated>=150ms. Landmark is smoothed source rise, not known MIDI onset. Pair pre[-100,-50]ms, attack[0,50]ms and body[50,150]ms entirely within same evaluated interval. Retain all qualifying/rejected rises.",
        bands=dict(edges_hz=[list(b) for b in BANDS], windows_samples=[2048,8192], hop="N/4", window="periodic Hann", mask="Original magnitude >=peak*-60dB threshold shared across models, same inherited counts/masks. Unmasked band powers also retained to expose candidate-only artifacts.", power="One-sided STFT magnitude squared with DC/Nyquist weights1 and other bins2, Hann noise-bandwidth normalization; time/channel mean. Fixed-band ratios are diagnostic, not estimated output transfer."),
        interpretation="No memoryless compression/saturation/output-EQ curve fitted, no waveform transfer inferred from unfitted phase or unmatched performances, and no shipping change follows from these descriptive metrics.")
    if args.prior_protocol:
        prior_info=pin(args.prior_protocol)
        prior=json.loads(args.prior_protocol.read_text())
        # No metric, input, threshold or support may change in this revision.
        for key in protocol:
            if key not in ("status","tool") and json.loads(json.dumps(protocol[key]))!=prior[key]:
                raise ValueError("A reporting revision changed the frozen measurement policy: "+key)
        protocol["status"]="same_frozen_policy_reporting_revision_after_initial_statistics"
        protocol["reporting_revision"]=dict(prior_protocol=prior_info,
            reason="Zero-original-power/zero-active-bin band ratios are now null with explicit insufficient support; original band power fraction additionally reported. All valid metrics, masks, thresholds, inputs and supports unchanged.")
    save(out/"protocol.json", protocol)
    print(out/"protocol.json", flush=True)


def frame_starts(segments, length, hop):
    return np.array([s for a,b in segments for s in range(a,b-length+1,hop)], dtype=int)


def frame_power(audio, starts, length):
    cumulative = np.concatenate(([0.], np.cumsum(np.mean(audio*audio, axis=1))))
    return (cumulative[starts+length]-cumulative[starts])/length


def sample_stats(audio):
    amplitude = abs(audio)
    power = float(np.mean(audio*audio))
    peak = float(amplitude.max())
    return dict(rms=float(np.sqrt(power)), rms_dbfs=float(db(power)), sample_peak=peak,
        sample_peak_dbfs=float(db(peak*peak)), crest_db=float(db(peak*peak/power)),
        dc_by_channel=np.mean(audio, axis=0).tolist(), samples=int(audio.size),
        absolute_amplitude_quantiles={str(q):float(np.percentile(amplitude,q)) for q in (50,90,95,99,99.9)},
        normalized_fourth_moment=float(np.mean(audio**4)/(power*power)))


def describe(values):
    values = np.asarray(values)
    return dict(count=int(values.size), mean=float(np.mean(values)) if values.size else None,
                p10=float(np.percentile(values,10)) if values.size else None,
                median=float(np.median(values)) if values.size else None,
                p90=float(np.percentile(values,90)) if values.size else None,
                p95=float(np.percentile(values,95)) if values.size else None)


def loudness(reference, candidate, segments, lag):
    filtered = [signal.sosfilt(k_sections(SR), a, axis=0) for a in (reference,candidate)]
    starts = frame_starts(segments, 17640, 4410)
    # frame_power averages channels; BS.1770 sums equally weighted channels.
    powers = [frame_power(a, starts+(lag if i else 0), 17640)*a.shape[1] for i,a in enumerate(filtered)]
    levels = [db(p)-.691 for p in powers]
    absolute = levels[0] >= -70
    relative = float(db(np.mean(powers[0][absolute]))-.691-10) if absolute.any() else -70
    active = absolute & (levels[0] > relative)
    if not active.any():
        raise ValueError("No original loudness support")
    means = [float(np.mean(p[active])) for p in powers]
    adjustment = float(np.sqrt(means[0]/means[1]))
    return dict(starts=starts.tolist(), window_samples=17640, hop_samples=4410,
        original_block_levels=levels[0].tolist(), production_block_levels=levels[1].tolist(),
        original_selected=active.tolist(), selected_blocks=int(active.sum()), total_blocks=len(starts),
        original_relative_gate=relative, original_k_level=float(db(means[0])-.691), production_k_level=float(db(means[1])-.691),
        production_minus_original_db=float(db(means[1]/means[0])), matched_sensitivity_scalar=adjustment,
        matched_sensitivity_adjustment_db=float(20*np.log10(adjustment)))


def envelopes(reference, candidate, segments, lag):
    results = []
    for length in (441,2205):
        starts = frame_starts(segments,length,220)
        a = np.sqrt(np.maximum(frame_power(reference,starts,length),0))
        b = np.sqrt(np.maximum(frame_power(candidate,starts+lag,length),0))
        mask = a >= max(float(a.max())*.001,1e-30)
        floor = max(float(a.max())*.0001,1e-30)
        x,y = [20*np.log10(np.maximum(v,floor)) for v in (a,b)]
        delta = y-x
        low,high = np.percentile(x[mask],[25,75])
        groups = {"quiet_original_quartile":mask & (x<=low),"loud_original_quartile":mask & (x>=high)}
        group_results = {name:describe(delta[selection]) for name,selection in groups.items()}
        results.append(dict(window_samples=length,hop_samples=220,starts=starts.tolist(),original_active=mask.tolist(),
            original_rms_db=x.tolist(),production_rms_db=y.tolist(),original_active_count=int(mask.sum()),
            signed_error_db=describe(delta[mask]),absolute_error_db=describe(abs(delta[mask])),
            original_dynamic_range_p95_p10_db=float(np.percentile(x[mask],95)-np.percentile(x[mask],10)),
            production_dynamic_range_p95_p10_db=float(np.percentile(y[mask],95)-np.percentile(y[mask],10)),
            log_envelope_correlation=float(np.corrcoef(x[mask],y[mask])[0,1]),
            original_quartile_bounds_db=[float(low),float(high)],original_groups=group_results,
            loud_minus_quiet_error_median_db=group_results["loud_original_quartile"]["median"]-group_results["quiet_original_quartile"]["median"]))
    return results


def transient_rises(reference,candidate,segments,lag):
    observations = []
    for start,end in segments:
        starts = frame_starts([[start,end]],2205,220)
        if len(starts)<12:
            continue
        level = db(np.maximum(frame_power(reference,starts,2205),1e-30))
        strength = np.zeros(len(starts))
        strength[5:-5] = level[10:]-level[:-10]
        positions,_ = signal.find_peaks(strength,height=3.,distance=31)
        for index in positions:
            center = int(starts[index]+1102)
            item = dict(reference_landmark_sample=center,source_rise_db=float(strength[index]),
                source_rms_db=float(level[index]),source_segment=[start,end])
            bounds = {"pre":[center-4410,center-2205],"attack":[center,center+2205],"body":[center+2205,center+6615]}
            reason = "outside_same_evaluated_segment" if min(a for a,b in bounds.values())<start or max(b for a,b in bounds.values())>end else ("original_level_below_minus30db_of_segment_peak" if level[index]<level.max()-30 else None)
            item.update(windows=bounds,accepted=reason is None,rejection_reason=reason)
            if reason is None:
                levels = {}
                for name,audio,offset in (("original",reference,0),("production",candidate,lag)):
                    parts = {key:audio[a+offset:b+offset] for key,(a,b) in bounds.items()}
                    values = {key:float(db(np.mean(y*y))) for key,y in parts.items()}
                    values["attack_to_body_rms_db"] = values["attack"]-values["body"]
                    values["attack_minus_pre_rms_db"] = values["attack"]-values["pre"]
                    values["attack_peak_to_body_rms_db"] = float(db(float(abs(parts["attack"]).max())**2/max(float(np.mean(parts["body"]**2)),1e-30)))
                    levels[name] = values
                item["models"] = levels
                item["production_minus_original"] = {k:levels["production"][k]-levels["original"][k] for k in levels["original"]}
            observations.append(item)
    return dict(landmarks=observations,accepted_count=sum(x["accepted"] for x in observations),
        contrasts={k:describe([x["production_minus_original"][k] for x in observations if x["accepted"]]) for k in ("attack_to_body_rms_db","attack_minus_pre_rms_db","attack_peak_to_body_rms_db")})


def spectral_bands(reference,candidate,segments,lag,controls):
    results = []
    for n in (2048,8192):
        spectra = [[],[]]
        coverage=[]
        for a,b in segments:
            if b-a<n:
                continue
            for i,(audio,offset) in enumerate(((reference,0),(candidate,lag))):
                z=signal.stft(audio[a+offset:b+offset],fs=SR,window="hann",nperseg=n,noverlap=3*n//4,boundary=None,padded=False,axis=0)[2]
                spectra[i].append(abs(z))
            frames=spectra[0][-1].shape[-1]
            coverage.append(dict(segment=[a,b],frames=frames,last_frame_end=a+(frames-1)*(n//4)+n))
        a,b=[np.concatenate(v,axis=-1) for v in spectra]
        mask=a>=float(a.max())*.001
        actual_hash=hashlib.sha256(np.packbits(mask).tobytes()).hexdigest()
        expected=controls[str(n)]
        if int(mask.sum())!=expected["bins"] or expected.get("mask_sha256",actual_hash)!=actual_hash:
            raise ValueError("Inherited original spectral mask changed")
        weights=np.ones(a.shape[0])*2;weights[[0,-1]]=1
        window=signal.windows.hann(n,sym=False)
        correction=window.sum()**2/(n*np.sum(window*window))
        power=[v*v*weights[:,None,None]*correction for v in (a,b)]
        full_original_power=float(np.sum(power[0])/power[0].shape[1]/power[0].shape[2])
        frequency=np.fft.rfftfreq(n,1/SR)
        rows=[]
        for lo,hi in BANDS:
            select=(frequency>=lo)&(frequency<hi)
            policies={}
            for label,selection in (("original_only",mask), ("unmasked",np.ones_like(mask))):
                values=[float(np.sum(p[select]*selection[select])/p.shape[1]/p.shape[2]) for p in power]
                supported=values[0]>0 and bool(selection[select].any())
                policies[label]=dict(original_power=values[0],production_power=values[1],
                    status="measured_descriptive" if supported else "insufficient_original_support",
                    original_band_fraction_of_full_original_power=values[0]/full_original_power,
                    original_band_relative_power_db=float(db(values[0]/full_original_power)) if supported else None,
                    production_minus_original_db=float(db(values[1]/values[0])) if supported else None,bins=int(selection[select].sum()))
            rows.append(dict(band_hz=[lo,hi],policies=policies))
        results.append(dict(window_samples=n,hop_samples=n//4,coverage=coverage,
            original_active_bins=int(mask.sum()),original_mask_sha256=actual_hash,bands=rows))
    return results


def control_checks(out):
    expected=np.array([[1.53512485958697,-2.69169618940638,1.19839281085285,1,-1.69065929318241,.73248077421585],
                       [1,-2,1,1,-1.99004745483398,.99007225036621]])
    coefficient_error=float(abs(k_sections(48000)-expected).max())
    # Published gain/shape parameters and tabulated coefficients are rounded;
    # their reconstructed numerator differs by about1.05e-12 at48kHz.
    if coefficient_error>2e-12:
        raise ValueError("K weighting48k coefficient control failed")
    x=(.1*np.sin(2*np.pi*1000*np.arange(2*SR)/SR))[:,None]
    levels=loudness(x,2*x,[[0,len(x)]],0)
    if abs(levels["production_minus_original_db"]-20*np.log10(2))>1e-10 or abs(levels["matched_sensitivity_scalar"]-.5)>1e-10:
        raise ValueError("Scalar/weighting control failed")
    ffmpeg=shutil.which("ffmpeg")
    cross=[]
    for frequency in (125,1000,8000):
        audio=np.column_stack([.1*np.sin(2*np.pi*frequency*np.arange(2*SR)/SR)]*2).astype(np.float32)
        wave=out/f"control-{frequency}.wav";wavfile.write(wave,SR,audio)
        process=subprocess.run([ffmpeg,"-hide_banner","-nostats","-i",str(wave),"-af","ebur128=peak=none","-f","null","-"],capture_output=True,text=True,check=True)
        (out/f"control-{frequency}.log").write_text(process.stderr)
        measured=float(re.findall(r"\bI:\s*(-?[\d.]+) LUFS",process.stderr)[-1])
        own=loudness(audio.astype(float),audio.astype(float),[[0,len(audio)]],0)["original_k_level"]
        if abs(own-measured)>.11:
            raise ValueError("Independent ffmpeg weighting control failed")
        cross.append(dict(frequency_hz=frequency,ours=own,ffmpeg_integrated=measured,difference=own-measured,wav=pin(wave),log=pin(out/f"control-{frequency}.log")))
    return dict(coefficients48k_max_error=coefficient_error,scalar_control=levels,
        ffmpeg=pin(ffmpeg),ffmpeg_controls=cross,
        tolerance_note="ffmpeg printed integrated values have0.1LU resolution;0.11LU guard only applies to independent measurement control, not hardware acceptance")


def measure(args):
    info=pin(args.protocol);protocol=json.loads(args.protocol.read_text());checked(protocol["tool"])
    for key in ("integration","factory_measurement","dry_measurement","original_mask_measurement"):
        checked(protocol[key])
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result=dict(protocol=protocol,protocol_file=info,libraries=dict(numpy=np.__version__,scipy=scipy.__version__),
        controls=control_checks(out),cases=[],hardware_equivalence="not_established")
    for row in protocol["cases"]:
        mono=row["cohort"]=="dry"
        h=read(row["reference"],mono);c=read(row["production"],mono)*row["fixed_gain"]
        segments,lag=row["reference_segments"],row["lag_samples"]
        if h.shape[1]!=c.shape[1] or any(a<0 or a+lag<0 or b>len(h) or b+lag>len(c) for a,b in segments):
            raise ValueError("Invalid paired sample/channel support")
        h_used=np.concatenate([h[a:b] for a,b in segments]);c_used=np.concatenate([c[a+lag:b+lag] for a,b in segments])
        level=loudness(h,c,segments,lag);scalar=level["matched_sensitivity_scalar"]
        env=envelopes(h,c,segments,lag);spectra=spectral_bands(h,c,segments,lag,row["inherited_spectral_controls"])
        stats={"original":sample_stats(h_used),"production_fixed":sample_stats(c_used),"production_k_matched_sensitivity":sample_stats(c_used*scalar)}
        signed={key:stats["production_fixed"][key]-stats["original"][key] for key in ("rms_dbfs","sample_peak_dbfs","crest_db","normalized_fourth_moment")}
        for e in env:
            delta=np.array(e["production_rms_db"])-np.array(e["original_rms_db"])+level["matched_sensitivity_adjustment_db"]
            e["k_matched_signed_error_db"]=describe(delta[np.array(e["original_active"])])
            e["k_matched_absolute_error_db"]=describe(abs(delta[np.array(e["original_active"])]))
        for s in spectra:
            for band in s["bands"]:
                for p in band["policies"].values():
                    value=p["production_minus_original_db"]
                    p["k_matched_production_minus_original_db"]=None if value is None else value+level["matched_sensitivity_adjustment_db"]
        item=dict(id=row["id"],cohort=row["cohort"],source=row,sample_statistics=stats,
            fixed_production_minus_original=signed,loudness=level,envelopes=env,
            transient_rises=transient_rises(h,c,segments,lag),spectral_bands=spectra)
        result["cases"].append(item)
        save(out/"results-partial.json",result)
        print(row["id"],f"RMSdelta={signed['rms_dbfs']:+.3f}; crestDelta={signed['crest_db']:+.3f}; Kdelta={level['production_minus_original_db']:+.3f}",flush=True)
    save(out/"results.json",result)
    print(out/"results.json",flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest="stage",required=True)
    p=sub.add_parser("prepare");p.add_argument("--integration",type=Path,required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--prior-protocol",type=Path)
    p=sub.add_parser("measure");p.add_argument("--protocol",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();prepare(args) if args.stage=="prepare" else measure(args)


if __name__=="__main__":
    main()

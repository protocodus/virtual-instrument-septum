#!/usr/bin/env python3
"""Bounded source-only cadence feasibility, never a raw LFO-rate estimator."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
SR = 44100
TRAIN, CHECK = (4.5, 9.5), (10., 15.)
BANDS = ((300, 900), (900, 3000), (3000, 7000))
FREQUENCIES = np.arange(.5, 12.0001, .01)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path, value):path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def features(y, width=.06, phase=0.):
    centers = np.arange(4.3+phase, 15.2, .01)
    size = round(width*SR)
    f = np.fft.rfftfreq(size, 1/SR)
    w = np.hanning(size)
    rows = []
    for center in centers:
        start = round(center*SR)-size//2
        x = y[start:start+size]
        powers = abs(np.fft.rfft(x*w[:, None], axis=0))**2
        lo = powers[(f>=40)&(f<200)].sum(axis=0)
        values = []
        for a, b in BANDS:
            high = powers[(f>=a)&(f<b)].sum(axis=0)
            # Averaged stereo powers, then individual L/R, avoiding downmix cancellation.
            values.extend(10*np.log10(np.maximum([high.sum(), *high], 1e-30)/np.maximum([lo.sum(), *lo], 1e-30)))
        values.append(10*np.log10(max(np.mean(x*x), 1e-30)))
        mid, side = (x[:, 0]+x[:, 1])/2, (x[:, 0]-x[:, 1])/2
        values.append(float(np.mean(side*side)/max(np.mean(mid*mid+side*side), 1e-30)))
        rows.append(values)
    labels = [f"{a}_{b}_over40_200_{channel}" for a, b in BANDS for channel in ("stereo_power", "L", "R")]
    return centers, np.array(rows), labels+["stereo_rms_db", "side_power_fraction"]


def probe(times, data, labels):
    train = (times>=TRAIN[0])&(times<TRAIN[1])
    check = (times>=CHECK[0])&(times<CHECK[1])
    t = times[train]
    null = np.column_stack((np.ones(len(t)), t-t.mean()))
    residual = data[train]-null@np.linalg.lstsq(null, data[train], rcond=None)[0]
    # Descriptive sinusoid search in first support only. Remove the same trend
    # from sinusoidal columns before evaluating improvement.
    c, s = np.cos(2*np.pi*FREQUENCIES[:, None]*t), np.sin(2*np.pi*FREQUENCIES[:, None]*t)
    inv = np.linalg.pinv(null)
    c -= (c@null)@inv
    s -= (s@null)@inv
    cc, ss, cs = (c*c).sum(axis=1), (s*s).sum(axis=1), (c*s).sum(axis=1)
    cr, sr = c@residual, s@residual
    determinant = cc*ss-cs*cs
    ac = (ss[:, None]*cr-cs[:, None]*sr)/determinant[:, None]
    ass = (cc[:, None]*sr-cs[:, None]*cr)/determinant[:, None]
    improvements = ac*cr+ass*sr
    rows = []
    for i, label in enumerate(labels):
        index = int(np.argmax(improvements[:, i]))
        frequency = FREQUENCIES[index]
        matrix = np.column_stack((np.ones(len(times)), times-t.mean(), np.cos(2*np.pi*frequency*times), np.sin(2*np.pi*frequency*times)))
        coefficient = np.linalg.lstsq(matrix[train], data[train, i], rcond=None)[0]
        prediction = matrix@coefficient
        # Offset-independent check correlation only; fitted phase/amplitude stay fixed.
        oscillation = matrix[:, 2:]@coefficient[2:]
        check_null = matrix[check, :2]
        check_residual = data[check, i]-check_null@np.linalg.lstsq(check_null, data[check, i], rcond=None)[0]
        osc = oscillation[check]-check_null@np.linalg.lstsq(check_null, oscillation[check], rcond=None)[0]
        denominator = np.linalg.norm(check_residual)*np.linalg.norm(osc)
        rows.append(dict(feature=label, strongest_training_cadence_hz=float(frequency),
                         training_variance_explained=float(improvements[index, i]/max(np.sum(residual[:, i]**2), 1e-30)),
                         frozen_check_correlation=float(check_residual@osc/max(denominator, 1e-30)),
                         frozen_check_rmse=float(np.sqrt(np.mean((data[check, i]-prediction[check])**2))),
                         coefficient=coefficient.tolist(),
                         qualification="Descriptive feature cadence; not an identified LFO or hardware frequency."))
    return rows


def synthetic(sequenced, phase, modulation):
    t = np.arange(round(15.3*SR))/SR
    note_period = .48
    age = t % note_period
    if sequenced:
        pattern = np.array([110., 110., 146.8323839587038, 97.99885899543733])
        frequency = pattern[(t/note_period).astype(int)%4]
        envelope = (1-np.exp(-age/.004))*np.exp(-age/.15)
    else:
        frequency = np.full(len(t), 110.)
        envelope = np.ones(len(t))
    cycles = np.cumsum(frequency)/SR+phase
    cutoff = 900*(1+.35*np.sin(2*np.pi*3.7*t+.31) if modulation else np.ones(len(t)))
    x = np.zeros(len(t))
    for h in range(1, 33):
        x += np.sin(2*np.pi*h*cycles)/h/np.sqrt(1+(h*frequency/cutoff)**4)
    x = np.tanh(5*x*envelope)*.2
    stereo = np.column_stack((x, x))
    if sequenced:
        for channel, delay in enumerate((.27, .33)):
            for repeat in (1, 2, 3):
                n = round(delay*repeat*SR)
                stereo[n:, channel] += .18**repeat*x[:-n]
    return stereo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    catalog_path = ROOT/"Docs/fidelity/source-audits/rcs-acid-source-extraction-2026-09-15.json"
    catalog = json.loads(catalog_path.read_text())
    for name, expected in catalog["original_media_sha256"].items():
        if sha(a.sources/name)!=expected:raise ValueError("Original media mismatch")
    archive = a.sources/"rcs-acid-original.zip"
    if sha(archive)!=catalog["archive"]["sha256"]:raise ValueError("Original archive mismatch")
    patch = next(p for p in catalog["presets"] if p["member"]=="TB-303 01.she")
    with zipfile.ZipFile(archive) as z:
        if hashlib.sha256(z.read(patch["member"])).hexdigest()!=patch["sha256"]:raise ValueError("SHE identity mismatch")
    if patch["official_lfo_labels"]["upper"][0] != dict(waveform="SIN", destination1="FILTER", depth1=10,
            destination2="AMP", depth2=0, rate_raw=88, key_trigger=0, tempo_sync=0):raise ValueError("LFO routing changed")
    protocol = dict(status="Source-only exploratory feasibility; no production rate correction or MIDI reconstruction",
        source_catalog_sha256=sha(catalog_path), source_media_sha256=catalog["original_media_sha256"],
        archive_sha256=sha(archive), patch=patch, tool_sha256=sha(__file__),
        card=dict(roi_xywh=[80,220,160,40], template_frame=150, blank_frame=50, frame_rate=25,
                  first_inclusive_frame=92, last_inclusive_frame=400, support_seconds=[3.68,16.04],
                  qualification="Visible text bounds only, not authenticated patch/audio transition times"),
        training_seconds=TRAIN, check_seconds=CHECK, feature_windows_seconds=[.06,.08],
        feature_grid_phases_seconds=[0,.005], feature_hop_seconds=.01, bands_hz=BANDS,
        frequency_grid_hz=[.5,12.,.01], feature_search="Each declared feature's strongest training sinusoid retained; phase/amplitude frozen for later check. No cross-feature or offset selection.",
        controls="No-LFO sequenced saw-like additive source at0.48s note cadence, max-like tanh plus unequal stereo delays, two carrier phases; steady and sequenced known3.7Hz brightness modulation positives. These are estimator controls, not SH-201 models.",
        excluded_claims=["No brightness peak is identified as LFO rate", "No candidate DSP audio", "No recovered MIDI or phase", "No original patch state authentication"])
    save(a.output/"protocol-before-features.json", protocol)
    video = a.sources/"7jW2GIgOOv8-video.mp4"
    command = ["ffmpeg","-v","error","-nostdin","-i",str(video),"-t","20","-vf","crop=160:40:80:220,format=gray","-f","rawvideo","-"]
    pixels = np.frombuffer(subprocess.check_output(command), np.uint8).reshape(-1,6400).astype(float)
    x = pixels-pixels[50]; template=x[150]; amplitude=x@template/(template@template)
    residual=np.linalg.norm(x-amplitude[:,None]*template,axis=1)/np.linalg.norm(template)
    matched=np.flatnonzero((amplitude>.95)&(residual<.06))
    if not np.array_equal(matched,np.arange(92,401)):raise ValueError("Observed card bounds changed")
    frame_command=["ffmpeg","-v","error","-nostdin","-i",str(video),"-vf","select=eq(n\\,91)+eq(n\\,92)+eq(n\\,400)+eq(n\\,401),tile=2x2","-frames:v","1",str(a.output/"card-boundaries.png")]
    subprocess.run(frame_command,check=True)
    wav=a.output/"source-full.wav"
    decode=["ffmpeg","-v","error","-nostdin","-i",str(a.sources/"7jW2GIgOOv8.m4a"),"-c:a","pcm_f32le",str(wav)]
    subprocess.run(decode,check=True)
    sr,y=wavfile.read(wav)
    if sr!=SR or y.ndim!=2 or y.shape[1]!=2:raise ValueError("Unexpected audio")
    records=[]
    for width in (.06,.08):
        for phase in (0.,.005):
            times,data,labels=features(y,width,phase)
            records.append(dict(width_seconds=width, grid_phase_seconds=phase, probes=probe(times,data,labels),
                                feature_values_sha256=hashlib.sha256(data.astype("<f8").tobytes()).hexdigest()))
            if width==.06 and phase==0.:
                source_features=dict(times=times.tolist(), values=data.tolist(), labels=labels)
    checks=[]
    for sequenced,phase,modulation in ((True,0.,False),(True,.37,False),(False,0.,True),(True,0.,True)):
        t,d,l=features(synthetic(sequenced,phase,modulation))
        checks.append(dict(sequenced=sequenced, carrier_phase=phase, known_lfo_hz=3.7 if modulation else None,
                           probes=probe(t,d,l)))
    positive = checks[2]["probes"][:9:3]
    if any(abs(p["strongest_training_cadence_hz"]-3.7)>.011 or p["frozen_check_correlation"]<.9 for p in positive):
        raise ValueError("Known steady modulation control failed")
    fig,axes=plt.subplots(4,1,figsize=(12,8),sharex=True,layout="constrained")
    values=np.array(source_features["values"]); times=np.array(source_features["times"])
    for axis,i in zip(axes,(0,3,6,9)):
        axis.plot(times,values[:,i],lw=.8);axis.axvspan(*TRAIN,alpha=.1,color="blue");axis.axvspan(*CHECK,alpha=.1,color="orange")
        label = f"{BANDS[i//3][0]}–{BANDS[i//3][1]} /\n40–200 Hz (dB)" if i<9 else "Stereo RMS\n(dBFS)"
        axis.set_ylabel(label,fontsize=9);axis.grid(alpha=.3)
    axes[0].set_title("Patch01 source-only features: blue training, orange frozen check")
    axes[-1].set_xlabel("Original recording clock / s")
    fig.savefig(a.output/"source-features.png",dpi=140);plt.close(fig)
    result=dict(schema_version=1,protocol=protocol,protocol_before_features_sha256=sha(a.output/"protocol-before-features.json"),
        decode_command=decode,decoded_wav_sha256=sha(wav),card_extraction_command=command,frame_command=frame_command,
        card_maximum_template_residual=float(residual[matched].max()),source_features=source_features,
        feature_phase_sensitivities=records,synthetic_controls=checks,rate_selected=None,production_dsp_changed=False,
        output_sha256={n:sha(a.output/n) for n in ("card-boundaries.png","source-features.png")})
    save(a.output/"results.json",result)
    for r in records:
        print(r["width_seconds"],r["grid_phase_seconds"],[(p["feature"],round(p["strongest_training_cadence_hz"],2),round(p["training_variance_explained"],3),round(p["frozen_check_correlation"],3)) for p in r["probes"] if p["feature"].endswith("stereo_power") or p["feature"]=="stereo_rms_db"])
    for r in checks:
        print("control",r["sequenced"],r["carrier_phase"],r["known_lfo_hz"],[(p["feature"],round(p["strongest_training_cadence_hz"],2),round(p["frozen_check_correlation"],3)) for p in r["probes"][:9:3]])


if __name__=="__main__":main()

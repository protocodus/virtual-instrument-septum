#!/usr/bin/env python3
"""Conditional Cotton late-tail decay with frozen time holdout and FDN controls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
TAIL_RECEIPT = ROOT/"Docs/fidelity/source-audits/official-reverb-tails-2026-09-15.json"
STEREO_RECEIPT = ROOT/"Docs/fidelity/source-audits/official-stereo-feasibility-2026-09-15.json"
SR = 44100
EDGES = np.array([80, 160, 320, 640, 1280, 2560, 5120, 10240])
SPECS = ((.5, .5), (.5, .25), (.75, .25), (1., .25))
SPECTRA = ("white_noise", "dark_noise", "bright_noise", "harmonic_chord")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def window(y, start, duration):
    a, b = round(start*SR), round((start+duration)*SR)
    x = y[a:b].astype(float)
    if len(x) != b-a or len(x) < 20000:
        raise ValueError("Missing long-window coverage")
    hann = np.hanning(len(x))
    transformed = np.fft.rfft(x*hann[:, None], axis=0)
    power = np.mean(abs(transformed)**2, axis=1)/(len(x)*np.sum(hann**2))
    # An odd-length real FFT has no Nyquist bin; its final bin also needs
    # the conjugate partner's energy. Even windows keep Nyquist unpaired.
    power[1:-1 if len(x)%2 == 0 else None] *= 2
    frequencies = np.fft.rfftfreq(len(x), 1/SR)
    bands = np.array([power[(frequencies >= a)&(frequencies < b)].sum()
                      for a, b in zip(EDGES[:-1], EDGES[1:])])
    full = float(np.mean(x*x))
    return dict(start_seconds=start, end_seconds=start+duration, center_seconds=start+duration/2,
                sample_count=len(x), frequency_resolution_hz=SR/len(x), broadband_dbfs=float(10*np.log10(max(full, 1e-30))),
                raw_level_guard=bool(full >= 10**(-65/10)), band_power=bands.tolist(),
                band_power_fraction=(bands/max(power.sum(), 1e-30)).tolist(),
                band_dbfs=(10*np.log10(np.maximum(bands, 1e-30))).tolist(),
                channel_dbfs=(10*np.log10(np.maximum(np.mean(x*x, axis=0), 1e-30))).tolist())


def line_fit(training, evaluation, times_training, times_evaluation):
    origin = times_training[0]
    matrix = np.column_stack((np.ones(len(training)), np.array(times_training)-origin))
    coefficient = np.linalg.lstsq(matrix, training, rcond=None)[0]
    expected = coefficient[0]+coefficient[1]*(np.array(times_evaluation)-origin)
    residual = np.asarray(evaluation)-expected
    return dict(origin_seconds=origin, intercept_db=float(coefficient[0]), slope_db_per_second=float(coefficient[1]),
                rt60_seconds=float(-60/coefficient[1]) if coefficient[1] < 0 else None,
                training_residual_db=(np.asarray(training)-matrix@coefficient).tolist(),
                evaluation_prediction_db=expected.tolist(), evaluation_minus_prediction_db=residual.tolist(),
                evaluation_rmse_db=float(np.sqrt(np.mean(residual**2))), evaluation_max_absolute_error_db=float(np.max(abs(residual))))


def analyze(y, start, eligibility=None):
    split, end = start+1.5, start+4.5
    groups = []
    for duration, hop in SPECS:
        training = [window(y, float(t), duration) for t in np.arange(start, split-duration+1e-8, hop)]
        evaluation = [window(y, float(t), duration) for t in np.arange(split, end-duration+1e-8, hop)]
        if min(len(training), len(evaluation)) < 3:
            raise ValueError("Insufficient frozen fit/evaluation windows")
        if eligibility is None:
            eligibility = [bool(all(r["band_power_fraction"][i] >= .01 for r in training)) for i in range(len(EDGES)-1)]
        times_a = [r["center_seconds"] for r in training]
        times_b = [r["center_seconds"] for r in evaluation]
        bands = []
        for i, (lo, hi) in enumerate(zip(EDGES[:-1], EDGES[1:])):
            bands.append(dict(hz=[int(lo), int(hi)], hardware_training_eligible=eligibility[i],
                              **line_fit([r["band_dbfs"][i] for r in training], [r["band_dbfs"][i] for r in evaluation], times_a, times_b)))
        broad = line_fit([r["broadband_dbfs"] for r in training], [r["broadband_dbfs"] for r in evaluation], times_a, times_b)
        channel = [line_fit([r["channel_dbfs"][i] for r in training], [r["channel_dbfs"][i] for r in evaluation], times_a, times_b) for i in (0, 1)]
        groups.append(dict(duration_seconds=duration, hop_seconds=hop, role="primary" if (duration, hop) == SPECS[0] else "correlated_window_sensitivity",
                           training=training, evaluation=evaluation, broadband=broad, channels=channel, bands=bands))
    return dict(start_seconds=start, calibration_end_seconds=split, evaluation_end_seconds=end,
                hardware_training_band_eligibility=eligibility, windows=groups)


def render_controls(out, syx, revision):
    frozen = out/"frozen-source"
    names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", revision, "Source/DSP"], cwd=ROOT, text=True).splitlines()
    names += ["Tools/RenderMidi.cpp"]
    hashes = {}
    for name in names:
        path = frozen/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(subprocess.check_output(["git", "show", f"{revision}:{name}"], cwd=ROOT))
        hashes[name] = sha(path)
    render_source = (frozen/"Tools/RenderMidi.cpp").read_text()
    reader = render_source[render_source.index("septum::Patch readCompletePatch ("):render_source.index("std::string patchSummary (")]
    cpp = r'''#include "DSP/SeptumEngine.h"
#include "DSP/SeptumSysEx.h"
#include "DSP/SeptumPresets.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <vector>
using Bytes=std::vector<std::uint8_t>;
Bytes readBytes(const std::filesystem::path&path) {std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("missing patch");return Bytes(std::istreambuf_iterator<char>(f),{});}
READER
int main(int argc,char**argv) {
  if(argc!=3)return 2;
  const auto original=readCompletePatch(argv[1]);
  const auto&r=original.reverb;
  if(r.time!=104||r.size!=7||r.lfDampGain!=0||r.hfDampGain!=0)return 3;
  std::fprintf(stderr,"{\"time\":%d,\"preDelay\":%d,\"size\":%d,\"highCut\":%d,\"density\":%d,\"diffusion\":%d,\"lfDampFrequency\":%d,\"lfDampGain\":%d,\"hfDampFrequency\":%d,\"hfDampGain\":%d,\"modeled_rt60_seconds\":%.17g}\n",r.time,r.preDelay,r.size,r.highCut,r.density,r.diffusion,r.lfDampFrequency,r.lfDampGain,r.hfDampFrequency,r.hfDampGain,septum::mapping::reverbSeconds(r.time,r.size));
  constexpr int rate=44100,block=256,frames=rate*7,burst=rate/5;
  const double pi=std::acos(-1.);
  for(int shape=0;shape<4;++shape) {
    septum::Engine engine;engine.prepare(rate,block);
    septum::Patch patch;patch.reverb=original.reverb;patch.reverbOn=true;patch.delayOn=false;
    patch.upper.osc1.wave=septum::Waveform::ExtIn;patch.upper.balance=-63;
    patch.upper.filterType=septum::FilterType::Bypass;patch.upper.level=80;
    patch.upper.ampEnvAttack=patch.upper.ampEnvRelease=0;patch.upper.ampEnvSustain=127;patch.upper.reverbDepth=127;
    engine.setPatch(patch);septum::ExternalInput external;external.inputVolume=127;engine.setExternalInput(external);engine.reset();engine.noteOn(60,100);
    std::vector<float> left(frames),right(frames),input(frames);
    std::uint32_t random=0x12345678u;double low=0;
    for(int i=0;i<burst;++i) {
      random^=random<<13;random^=random>>17;random^=random<<5;
      const double white=double(random)/4294967295.*2-1;low+=.08*(white-low);
      double x=shape==0?white:shape==1?low:shape==2?white-low:0;
      if(shape==3)for(int note:{48,52,55}) {
        const double f=440*std::exp2((note-69)/12.);
        for(int h=1;h*f<16000;++h)x+=.12/h*std::sin(2*pi*h*f*i/rate+.37*h*h);
      }
      const double envelope=.5-.5*std::cos(2*pi*i/(burst-1));
      input[i]=static_cast<float>(.15*envelope*x);
    }
    for(int i=0;i<frames;i+=block)engine.process(left.data()+i,right.data()+i,std::min(block,frames-i),input.data()+i,input.data()+i);
    const auto path=std::filesystem::path(argv[2])/(std::to_string(shape)+".raw");
    std::ofstream file(path,std::ios::binary);
    for(int i=0;i<frames;++i){file.write(reinterpret_cast<char*>(&left[i]),4);file.write(reinterpret_cast<char*>(&right[i]),4);}
  }
}
'''.replace("READER", reader)
    fixture = out/"cotton-fdn-burst.cpp"
    fixture.write_text(cpp)
    binary = out/"cotton-fdn-burst"
    command = ["c++", "-O2", "-std=c++17", "-I", str(frozen/"Source"), str(fixture),
               *[str(frozen/"Source/DSP"/name) for name in ("SeptumEngine.cpp", "SeptumPresets.cpp", "SeptumSysEx.cpp")], "-o", str(binary)]
    subprocess.run(command, check=True)
    rendered = subprocess.run([str(binary), str(syx), str(out)], check=True, capture_output=True, text=True)
    parameters = json.loads(rendered.stderr)
    signals, receipts = {}, []
    for i, name in enumerate(SPECTRA):
        path = out/(str(i)+".raw")
        y = np.fromfile(path, dtype=np.float32).reshape(-1, 2)
        if len(y) != SR*7 or not np.isfinite(y).all() or abs(y).max() >= .9:
            raise ValueError("Invalid or limited FDN control")
        wav = out/(name+".wav")
        wavfile.write(wav, SR, y)
        signals[name] = y.astype(float)
        receipts.append(dict(id=name, raw_sha256=sha(path), wav_sha256=sha(wav), peak=float(abs(y).max())))
    return signals, dict(source_revision=revision, source_sha256=hashes, complete_patch_reader_sha256=hashlib.sha256(reader.encode()).hexdigest(),
                         fixture_sha256=sha(fixture), binary_sha256=sha(binary), compile_command=command,
                         parameters=parameters, stimulus="Four deterministic200ms Hann-shaped ExtIn bursts; white/dark/bright noise and C3-E3-G3 harmonic chord. Same exact native-decoded Cotton reverb block; delay off; other voice settings only route known external excitation.",
                         windows="1.25–2.75s train and2.75–5.75s evaluation in stimulus clock, plus93samples renderer/output latency once; later than1s after the200ms burst ends.",
                         audio=receipts)


def plot(result, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    primary = result["hardware"]["windows"][0]
    rows = primary["training"]+primary["evaluation"]
    time = [r["center_seconds"] for r in rows]
    for i, band in enumerate(primary["bands"]):
        if band["hardware_training_eligible"]:
            label=f"{band['hz'][0]}–{band['hz'][1]} Hz"
            axes[0, 0].plot(time,[r["band_dbfs"][i] for r in rows],"o-",label=label)
            axes[0, 1].plot([r["center_seconds"] for r in primary["evaluation"]],band["evaluation_minus_prediction_db"],"o-",label=label)
    broad=primary["broadband"]
    axes[0, 0].plot(time,[r["broadband_dbfs"] for r in rows],"k.-",label="Broadband RMS")
    axes[0, 0].axvline(18.75,color="black",ls="--",lw=1)
    axes[0, 0].set(title="Cotton complete-file late decay",xlabel="Recording time (s)",ylabel="Level (dBFS)")
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].axhline(0,color="black",lw=1)
    axes[0, 1].set(title="Frozen first1.5s line: later residual",xlabel="Recording time (s)",ylabel="Measured minus prediction (dB)")
    for name, record in result["fdn_controls"].items():
        bands=record["windows"][0]["bands"]
        axes[1, 0].plot([f"{b['hz'][0]}" for b in bands],[b["rt60_seconds"] for b in bands],"o-",label=name)
    axes[1, 0].axhline(result["control_receipt"]["parameters"]["modeled_rt60_seconds"],color="black",ls="--",label="Current target")
    axes[1, 0].set(title="Actual neutral-damping FDN controls",xlabel="Band lower edge (Hz)",ylabel="Training-derived RT60 (s)")
    axes[1, 0].legend(fontsize=8)
    for group in result["hardware"]["windows"]:
        eligible=[b for b in group["bands"] if b["hardware_training_eligible"]]
        axes[1, 1].plot([f"{b['hz'][0]}" for b in eligible],[b["rt60_seconds"] for b in eligible],"o-",label=f"{group['duration_seconds']}s / {group['hop_seconds']}s hop")
    axes[1, 1].set(title="Correlated window sensitivity; no statistical CI",xlabel="Band lower edge (Hz)",ylabel="Training-derived RT60 (s)")
    axes[1, 1].legend(fontsize=8)
    for ax in axes.flat:ax.grid(alpha=.2)
    fig.suptitle("Cotton: an effective late-tail decay, conditional on recorded patch and capture",fontsize=13)
    fig.savefig(out/"decay-analysis.png",dpi=150)
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources",type=Path,required=True)
    parser.add_argument("--corpus",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    tail=json.loads(TAIL_RECEIPT.read_text());stereo=json.loads(STEREO_RECEIPT.read_text())
    config=tail["configuration"]["cotton-wool"]
    mp3=args.sources/config["mp3"]
    syx=args.corpus/"cotton-wool/original-patch.syx"
    if sha(mp3)!=config["sha256"] or sha(syx)!=stereo["cases"]["cotton-wool"]["input_sha256"]["original-patch.syx"]:
        raise ValueError("Original MP3 or published patch changed")
    protocol=dict(training=[17.25,18.75],evaluation=[18.75,21.75],excluded_weak_window=[21.75,22.25],
                  band_edges_hz=EDGES.tolist(),window_specs=[list(v) for v in SPECS],minimum_window_samples=20000,
                  band_eligibility="Hardware only: at least1% of full Hann spectral power in EACH primary training window. All weak bands retained as diagnostics.",
                  fitting="One dB-linear slope/intercept per band on training only; frozen later prediction. Window-length/hop and band spread describe sensitivity, not statistical confidence intervals.",
                  spectral_power="Full-rate real FFT; Hann energy normalization and one-sided Parseval weighting; mean L/R power. Broadband uses unwindowed RMS to match previous guard.",
                  limits="Published patch/control values do not authenticate recorded raw revision. Unknown last input and capture processing; a smooth exponential recording fade cannot be separated from intrinsic decay. No raw control law fit or DSP changes.")
    save(out/"protocol.json",protocol)
    wav=out/"hardware-full.wav"
    command=["ffmpeg","-hide_banner","-loglevel","error","-nostdin","-i",str(mp3),"-c:a","pcm_f32le",str(wav)]
    subprocess.run(command,check=True)
    sr,y=wavfile.read(wav)
    if sr!=SR or y.ndim!=2 or y.shape[1]!=2 or not np.isfinite(y).all():raise ValueError("Unexpected source decode")
    hardware=analyze(y.astype(float),17.25)
    corrected=y.astype(float);corrected[:,1]/=10**(.6/20)
    sensitivity=analyze(corrected,17.25,hardware["hardware_training_band_eligibility"])
    signals,control_receipt=render_controls(out,syx,"b0f6c03")
    controls={name:analyze(signal,1.25+93/SR,hardware["hardware_training_band_eligibility"]) for name,signal in signals.items()}
    result=dict(protocol=protocol,tool_sha256=sha(__file__),tail_receipt_sha256=sha(TAIL_RECEIPT),stereo_receipt_sha256=sha(STEREO_RECEIPT),
                source=dict(path=str(mp3),sha256=sha(mp3),reference=tail["cases"]["cotton-wool"]["reference"]),
                published_patch=dict(path=str(syx),sha256=sha(syx)),decode_command=command,decoded_sha256=sha(wav),
                decoder=dict(path=shutil.which("ffmpeg"),sha256=sha(shutil.which("ffmpeg")),
                             version=subprocess.check_output(["ffmpeg","-version"],text=True).splitlines()[0]),
                hardware=hardware,right_minus_0p6_db_sensitivity=sensitivity,excluded_window=window(y,21.75,.5),
                control_receipt=control_receipt,fdn_controls=controls,equivalence_status="not_established")
    save(out/"results.json",result);plot(result,out)
    primary=hardware["windows"][0]
    print("broadband",primary["broadband"],flush=True)
    print("eligible bands",[(b["hz"],b["rt60_seconds"],b["evaluation_rmse_db"]) for b in primary["bands"] if b["hardware_training_eligible"]],flush=True)


if __name__=="__main__":main()

#!/usr/bin/env python3
"""Independent frozen-source, alignment and output-route audit; no DSP edits."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = (1., .5, .25)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


def output_controls(frozen, out):
    engine = frozen/"Source/DSP/SeptumEngine.cpp"
    source = engine.read_text()
    begin = source.index("    [[nodiscard]] inline double outputLimit (")
    end = source.index("    [[nodiscard]] inline double onePoleCoeff (", begin)
    limiter = source[begin:end]
    cpp = r'''#include "SeptumEngine.h"
#include "AnalogOutput.h"
#include <array>
#include <cmath>
#include <cstdio>
namespace mapping = septum::mapping;
LIMITER
int main() {
  constexpr int rate=44100, count=44100;
  constexpr std::array<double,3> variants{1,.5,.25};
  const double pi=std::acos(-1.0);
  for(int mode=0;mode<2;++mode) for(int condition=0;condition<5;++condition) {
    std::array<std::array<septum::AnalogOutput,2>,3> output;
    for(auto&pair:output)for(auto&channel:pair)channel.prepare(rate);
    double master=0;
    const double pole=1-std::exp(-1/(rate*mapping::masterSlewSeconds));
    for(int i=0;i<count;++i) {
      const double t=double(i)/rate;
      const double level=condition==3?12.:1.;
      const double mid=level*(.12*std::sin(2*pi*401*t)+.035*std::sin(2*pi*113*t));
      const double side=condition==4?0.:level*(.07*std::sin(2*pi*733*t)+.025*std::cos(2*pi*1601*t));
      const double dryL=condition==1?.08*std::sin(2*pi*233*t):0.;
      const double dryR=condition==1?.065*std::sin(2*pi*293*t+.7):0.;
      const double pan=condition==2?.4:0.;
      const double angle=(pan+1)*.25*pi;
      const double gain[2]={std::cos(angle)*mapping::partPanCentreGain,
                            std::sin(angle)*mapping::partPanCentreGain};
      master+=(.8-master)*pole;
      for(int v=0;v<3;++v) {
        double wetL=mid+side, wetR=mid-side;
        if(variants[v]!=1) {
          if(mode==0) {
            const double m=.5*(wetL+wetR), s=.5*(wetL-wetR);
            wetL=m+variants[v]*s;wetR=m-variants[v]*s;
          } else {wetL*=variants[v];wetR*=variants[v];}
        }
        const float mix[2]={static_cast<float>(dryL+wetL*mapping::reverbWetReturn),
                            static_cast<float>(dryR+wetR*mapping::reverbWetReturn)};
        for(int channel=0;channel<2;++channel) {
          const double x=mix[channel]*master*gain[channel];
          const float y=static_cast<float>(outputLimit(output[v][channel].processSample(x)));
          std::fwrite(&y,sizeof(y),1,stdout);
        }
      }
    }
  }
}
'''.replace("LIMITER", limiter)
    path = out/"actual-output-route.cpp"
    path.write_text(cpp)
    binary = out/"actual-output-route"
    command = ["c++", "-O2", "-std=c++17", "-I", str(frozen/"Source/DSP"), str(path), "-o", str(binary)]
    subprocess.run(command, check=True)
    raw = subprocess.check_output([str(binary)])
    y = np.frombuffer(raw, dtype=np.float32).astype(float).reshape(2, 5, 44100, 3, 2)
    conditions = ("wet_only_centered_small_signal", "dry_plus_wet_centered_small_signal",
                  "wet_only_offcenter_pan_small_signal", "wet_only_centered_limiter_active", "pure_mid_centered_small_signal")
    rows = []
    for mode, name in enumerate(("width", "gain")):
        for case, condition in enumerate(conditions):
            audio = y[mode, case]
            mid, side = np.mean(audio, axis=2), (audio[:, :, 0]-audio[:, :, 1])/2
            models = []
            for i, value in enumerate(WIDTHS):
                expected_mid = mid[:, 0]*(value if name == "gain" else 1.)
                models.append(dict(value=value, peak=float(np.max(np.abs(audio[:, i]))),
                                   mid_expected_error_max=float(np.max(np.abs(mid[:, i]-expected_mid))),
                                   mid_rms_ratio=rms(mid[:, i])/max(rms(mid[:, 0]), 1e-30),
                                   side_expected_error_max=float(np.max(np.abs(side[:, i]-value*side[:, 0]))),
                                   side_rms_ratio=rms(side[:, i])/max(rms(side[:, 0]), 1e-30)))
            affine = audio[:, 2]-(1.5*audio[:, 1]-.5*audio[:, 0])
            row = dict(mode=name, condition=condition, models=models, affine_max_error=float(np.max(np.abs(affine))))
            if case == 0 and max(r["mid_expected_error_max"] for r in models) > 5e-8:
                raise ValueError("Small-signal wet-only mid relationship failed")
            if case == 0 and max(r["side_expected_error_max"] for r in models) > 5e-8:
                raise ValueError("Small-signal wet-only side relationship failed")
            if case != 3 and row["affine_max_error"] > 1e-7:
                raise ValueError("Small-signal output route lost affine relationship")
            rows.append(row)
    return dict(engine_sha256=sha(engine), analog_output_sha256=sha(frozen/"Source/DSP/AnalogOutput.h"),
                engine_header_sha256=sha(frozen/"Source/DSP/SeptumEngine.h"),
                compile_command=command, fixture_sha256=sha(path), binary_sha256=sha(binary),
                raw_output_sha256=hashlib.sha256(raw).hexdigest(), limiter_source=limiter,
                method="Actual AnalogOutput implementation and verbatim outputLimit; float wet/dry mix, shared master slew, documented code pan law, final float conversion. Synthetic wet-return input, not a reverb-network model.",
                rows=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    experiment = args.experiment.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source_manifest = json.loads((experiment/"source-manifest.json").read_text())
    result = json.loads((experiment/"results.json").read_text())
    mode = result["protocol"].get("mode", "width")
    if mode not in ("width", "gain"):
        raise ValueError("Unsupported return experiment")
    snapshot = experiment/"compare_reverb_width_candidates.py"
    if sha(snapshot) != source_manifest["tool_sha256"]:
        raise ValueError("Snapshot tool identity changed")
    frozen = experiment/"frozen-source"
    for name, digest in source_manifest["input_sha256"].items():
        committed = subprocess.check_output(["git", "show", f"{source_manifest['revision']}:{name}"], cwd=ROOT)
        if sha(frozen/name) != digest or hashlib.sha256(committed).hexdigest() != digest:
            raise ValueError("Frozen source differs from pinned commit")
    source_checks = []
    anchor = "            wetReverbL = reverb_.highCutStateL;\n            wetReverbR = reverb_.highCutStateR;"
    old = (frozen/"Source/DSP/SeptumEngine.cpp").read_text()
    if old.count(anchor) != 1:
        raise ValueError("Integration point changed")
    for width in WIDTHS:
        name = mode+"-"+format(width, "g")
        variant, build = experiment/"variant-sources"/name, experiment/"builds"/name
        expected = old
        if width != 1:
            change = (f"\n            // Experimental fixed return width; wet mid and FDN remain unchanged.\n            const double reverbMid = 0.5 * (wetReverbL + wetReverbR);\n            const double reverbSide = 0.5 * (wetReverbL - wetReverbR);\n            wetReverbL = reverbMid + {width:.17g} * reverbSide;\n            wetReverbR = reverbMid - {width:.17g} * reverbSide;"
                      if mode == "width" else f"\n            // Experimental equal-channel return gain; FDN and wet width unchanged.\n            wetReverbL *= {width:.17g};\n            wetReverbR *= {width:.17g};")
            expected = old.replace(anchor, anchor+change)
        if (variant/"Source/DSP/SeptumEngine.cpp").read_text() != expected:
            raise ValueError("Unexpected candidate engine mutation")
        for path, digest in source_manifest["input_sha256"].items():
            if path != "Source/DSP/SeptumEngine.cpp" and sha(variant/path) != digest:
                raise ValueError("Unexpected non-engine mutation")
            if path.startswith("Source/DSP/") and sha(build/path) != sha(variant/path):
                raise ValueError("Compiled DSP snapshot differs from reviewed variant")
        manifest = json.loads((build/"manifest.json").read_text())
        if manifest["profile"]["enabled_sections"] or manifest["profile"]["provided_fields"] or manifest["profile"]["reference_rate_hz"] is not None:
            raise ValueError("Unexpected calibration or render-rate override")
        if (build/"CandidateProfile.h").read_text().count("profile."):
            raise ValueError("Generated profile mutates a calibration field")
        source_checks.append(dict(mode=mode, scale=width, only_expected_return_change=True, dsp_snapshot_verified=True,
                                  no_profile_or_rate_override=True, renderer_sha256=sha(build/"SeptumRenderMidi")))
    controls = output_controls(frozen, out)
    parser_module = module(frozen/"Tools/render_midi.py", "frozen_midi")
    guard_path = ROOT/"Docs/fidelity/source-audits/final-production-verification-2026-09-15.json"
    if sha(guard_path) != source_manifest["production_guard_sha256"]:
        raise ValueError("Production guard changed")
    guard = {r["id"]: r for r in json.loads(guard_path.read_text())["cases"]}
    if {r["id"] for r in result["cases"]} != set(guard):
        raise ValueError("Case set changed")
    cases = []
    for row in result["cases"]:
        directory = experiment/"cases"/row["id"]
        for name, expected in row["input_sha256"].items():
            if sha(directory/name) != expected:
                raise ValueError("Case input changed")
        for name, key in (("original-patch.syx", "patch_sha256"), ("reconstructed-performance.mid", "midi_sha256"), ("septum-raw.wav", "production_sha256")):
            if sha(directory/name) != guard[row["id"]][key]:
                raise ValueError("Production fixture mutation")
        sr, hardware = wavfile.read(directory/"hardware-excerpt-raw.wav")
        n = len(hardware)
        cal = round(n*.25)
        lag = row["calibration"]["candidate_lag_samples"]
        ca, cb = max(0, -lag), min(cal, cal-lag)
        start, end = max(cal, cal-lag), min(n, n-lag)
        if sr != 44100 or abs(lag) > 2205 or row["calibration"]["calibration_frames"] != cal:
            raise ValueError("Calibration policy changed")
        if (row["calibration_reference_samples"] != [ca, cb] or row["calibration_candidate_samples"] != [ca+lag, cb+lag]
                or row["evaluation_samples"] != [start, end] or min(start, start+lag) < cal):
            raise ValueError("Calibration/evaluation support overlaps")
        values = []
        model_rows = []
        for width in WIDTHS:
            name = mode+"-"+format(width, "g")
            model = row["models"][name]
            path = directory/(name+".wav")
            if sha(path) != model["raw_sha256"] or sha(experiment/"builds"/name/"SeptumRenderMidi") != model["renderer_sha256"]:
                raise ValueError("Rendered candidate identity changed")
            if width == 1 and sha(path) != guard[row["id"]]["production_sha256"]:
                raise ValueError("Scale1 failed byte identity")
            rate, audio = wavfile.read(path)
            if rate != sr or audio.ndim != 2 or audio.shape[1] != 2:
                raise ValueError("Unexpected stereo candidate format")
            audio = audio.astype(float)
            gain = rms(hardware[ca:cb].astype(float))/rms(audio[ca+lag:cb+lag])
            if not np.isclose(gain, model["training_gain"], rtol=1e-12, atol=0):
                raise ValueError("Candidate gain did not use frozen calibration support")
            values.append(audio)
            model_rows.append(dict(mode=mode, scale=width, peak=float(np.max(np.abs(audio))),
                                   limiter_inactive_by_peak=bool(np.max(np.abs(audio)) < .9), training_gain=gain))
        audio = np.stack(values, axis=1)
        mids = np.mean(audio, axis=2)
        affine = audio[:, 2]-(1.5*audio[:, 1]-.5*audio[:, 0])
        pan = []
        events = parser_module.parse_smf((directory/"reconstructed-performance.mid").read_bytes())["events"]
        for event in events:
            if event["kind"] == "midi":
                message = bytes.fromhex(event["hex"])
                if message[0]&240 == 176 and message[1] == 10:
                    pan.append(dict(sample=event["sample"], value=message[2]))
        cases.append(dict(id=row["id"], all_input_and_output_hashes_verified=True, scale1_byte_identical=True,
                          pan_events=pan, frozen_lag_samples=lag, calibration_frames=cal,
                          calibration_reference=[ca, cb], calibration_candidate=[ca+lag, cb+lag],
                          evaluation_reference=[start, end], evaluation_candidate=[start+lag, end+lag],
                          models=model_rows, raw_mid_max_absolute_change=float(np.max(np.abs(mids[:, 1:]-mids[:, :1]))),
                          raw_affine_max_absolute_error=float(np.max(np.abs(affine))),
                          raw_affine_rms_error=rms(affine), raw_samples=len(audio)))
    output = dict(mode=mode, script_sha256=sha(__file__), experiment_results_sha256=sha(experiment/"results.json"),
                  experiment_snapshot_sha256=sha(snapshot), source_manifest_sha256=sha(experiment/"source-manifest.json"),
                  source_checks=source_checks, controls=controls, cases=cases,
                  interpretation="Width preserves wet-return mid algebraically; gain scales wet mid/side equally. Centered unclipped isolated-wet output preserves the expected relationships within float precision. Mixed dry/delay, unequal final pan, limiting, and later per-render fitted gain must be considered for final-output relationships.")
    (out/"results.json").write_text(json.dumps(output, indent=2, allow_nan=False)+"\n")
    print("verified", len(cases), "cases; max raw mid", max(r["raw_mid_max_absolute_change"] for r in cases),
          "max affine", max(r["raw_affine_max_absolute_error"] for r in cases))


if __name__ == "__main__":
    main()

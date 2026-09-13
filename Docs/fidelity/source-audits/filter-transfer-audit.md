# Filter transfer and envelope audit

2026-09-13. Read-only diagnostic of the engine before the experimental filter-decay comparisons. The probe changes only its temporary test patch, not shipping presets or source code.

**Finding:** no cutoff-unit, coefficient, decoder, or accidental extra-filter-pass bug was found. A rendered sine sweep agrees with the intended LPF equations. The strongest identified source of premature darkness is the current envelope calibration: a filter decay value mapped to 57.38 ms actually uses an 8.31 ms time constant. Whether the longer constant matches hardware must be established separately from the recordings.

## Source semantics

The [Roland MIDI Implementation](https://static.roland.com/assets/media/pdf/SH-201_MI.pdf), p. 5, gives tone offsets `13` cutoff, `14` keyfollow, `15` velocity sensitivity, `16` resonance, `17–1A` ADSR, and `1B` envelope depth. Its filter enumeration is BYPASS/LPF/HPF/BPF and slope enumeration is −12/−24 dB. Septum decodes those correctly. The public Editor 1.10 `BufferModel.xml` lines 650–725 independently confirms the byte ranges; `PatchFilter.xml` binds these fields directly. Source downloads and original hashes are retained in [the oscillator semantics audit](oscillator-semantics.md).

The [Owner's Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), pp. 34–37 and 61, specifies filter directions, key tracking about C4, and envelope segment roles. It does **not** provide cutoff-to-Hz, envelope-to-seconds, relative oscillator levels, or the filter's digital topology. The ten-octave cutoff/depth laws and time curves are model calibrations, not official numerical specifications.

## Actual preset controls

Values come from the untouched [BASS](https://www.rolandus.com/go/sh-201_patches/shl/SH-201_Patch_BASS.zip) and [PAD](https://www.rolandus.com/go/sh-201_patches/shl/SH-201_Patch_PAD.zip) banks, decoded with `Tools/extract_reference_patch.py`. Both bass patches are Dual; Cotton Wool uses Upper only. Every listed tone selects LPF24.

| Patch / tone | Cutoff | Resonance | Keyfollow | Velocity sens | Filter A/D/S/R | Depth | Modeled base / peak cutoff |
|---|---:|---:|---:|---:|---|---:|---|
| Moogie 1 / Upper | 30 | 0 | 0 | 0 | 0/49/0/0 | +22 | 102.83 / 1157.02 Hz |
| Moogie 1 / Lower | 47 | 0 | 0 | 0 | 0/37/0/127 | +15 | 260.06 / 1354.62 Hz |
| Dist Bs 1 / Upper | 36 | 31 | 0 | 0 | 0/64/0/0 | +22 | 142.67 / 1605.31 Hz |
| Dist Bs 1 / Lower | 57 | 0 | 0 | 0 | 0/37/0/127 | +15 | 448.86 / 2338.02 Hz |
| Cotton Wool / Upper, MIDI 48, velocity 100 | 0 | 0 | +60 | +18 | 10/58/87/105 | +39 | 20.80 / 1519.44 Hz |

The two bass patches' filter brightness is independent of played velocity and keyfollow in this model because both sensitivities are zero. Cotton Wool's velocity remains a confounder. Its modeled sustained cutoff under the illustrative MIDI-48/velocity-100 input is 393.32 Hz.

## Independent transfer check

[CSV: all 72 cases](filter-transfer-audit.csv). The probe renders a held sine with filter modulation, effects, overdrive, and velocity gain disabled, then repeats with BYPASS. Projection onto sine and cosine at the known input frequency measures amplitude in the final half-second of each one-second render. The amplitude ratio cancels oscillator level, pan, transport, and the shared output circuit. It covers cutoff 30/47/57/64/95/127, notes 36/60/84, slopes 12/24, and resonance 0/31 at 44.1 kHz.

For the chosen state-variable filter, define:

```text
fc = clamp(20 * 2^(10 * cutoff / 127), 5, 0.45 * sampleRate)
g  = tan(pi * fc / sampleRate)
r  = tan(pi * sineFrequency / sampleRate) / g
k  = 2 - 2.04 * sqrt(resonance / 127)
H12 = 1 / (1 - r^2 + j*k*r)
H24 = H12 / (1 - r^2 + j*1.2*r)
```

The measured response differs by at most **0.006724 dB**, at approximately −80.7 dB attenuation where output quantization becomes relevant. For responses above −60 dB, the maximum discrepancy is **0.000409 dB**. This rules out a factor-of-two/2π/sample-rate error in this path; it does not validate the chosen topology against Roland hardware.

At resonance zero, `fc` is the filters' natural-frequency parameter, **not their −3 dB corner**. In the low-frequency limit, those corners are approximately `0.64359*fc` for LPF12 and `0.67116*fc` for LPF24. That follows from the chosen damping values. No inspected Roland source establishes which physical cutoff definition its 0–127 control follows, so this distinction alone is not a justified recalibration.

## Envelope timing lead

The current mapping is `T(D) = 0.002 * 6000^(D/127)` seconds, followed by `decayCoeff = exp(-ln(1000)/(T*sampleRate))`. Thus the time constant is `T/6.907755`, and the remaining envelope distance to sustain shrinks by 60 dB in `T`. This is shared with the amplitude envelope. The filter then exponentiates the envelope's octave offset into Hz.

| Decay value | Mapped T | Current time constant | Candidate filter-only time constant |
|---:|---:|---:|---:|
| 37 | 25.220 ms | 3.651 ms | 25.220 ms |
| 49 | 57.378 ms | 8.306 ms | 57.378 ms |
| 58 | 106.288 ms | 15.387 ms | 106.288 ms |
| 64 | 160.317 ms | 23.208 ms | 160.317 ms |

An analytic candidate using `exp(-1/(T*sampleRate))` for filter decay alone changes Moogie Upper's cutoff 50 ms after attack from about **103 to 283 Hz**, and Dist Upper from **189 to 839 Hz**. Cotton Wool's corresponding example changes **414 to 915 Hz**, but its late sustained value stays **393 Hz**. A longer decay therefore targets transient darkness; it cannot explain the whole sustained Cotton Wool discrepancy. Candidate trajectories are retained at `/tmp/septum-hw-benchmark/filter-audit/filter-envelope-timeconstant-candidate.json`.

**Follow-up:** the [conditional hardware analysis](filter-envelope-conditional-fit.md) tested this factor-of-6.907 candidate and found it worse on both held-out notes. It was therefore rejected. It is not a newly discovered documented number. Any eventual implementation must cover both `filterEnv.configure` call sites (note trigger and live patch update), preserve amp and pitch timing, and leave filter release unchanged unless separate evidence supports that change.

## Other signal-path checks

`g = tan(pi*fc/sampleRate)` and the state-variable integrator equations are internally consistent. The −24 dB selection cascades exactly two two-pole stages; BYPASS selects the input at each stage. The limiter's threshold is not implicated in these low-resonance, small-signal checks. Filter and envelope fields reach the correct Upper/Lower tone.

Both oscillator legs have unity gain at center balance in the current model. Super Saw alone receives the modeled stack normalization and tracked high-pass before the shared voice filter; sine does not. Their relative levels remain unmeasured. Moogie Upper has LOW FREQ BOOST and Lower FLAT; Dist has BOOST on both tones; Cotton Wool has FLAT. These match the raw bytes. No inspected source justifies changing FLAT into CUT, dropping Cotton Wool's sine, or reinterpreting its −36-semitone tuning to brighten the result.

## Reproduction and baseline identity

Save the C++ below as `/tmp/filter-transfer-probe.cpp`, build the repository's `SeptumDSP` target, then run:

```sh
c++ -O3 -std=c++20 -I Source /tmp/filter-transfer-probe.cpp build-fidelity/libSeptumDSP.a -o /tmp/filter-transfer-probe
/tmp/filter-transfer-probe > /tmp/filter-transfer-audit.csv
```

The recorded run used the Release arm64 build on macOS, `-mmacosx-version-min=11.0`, and these baseline source hashes:

- `Source/DSP/SeptumEngine.cpp`: `ea877fb51a26bb2d1c6544d185f33eb3f1f29dd376f25129fff781aa43d6adfd`
- `Source/DSP/SeptumEngine.h`: `2191ccfd226720fb529b4240fa5e7708fa0ba7a2e5a7a975e4f8aa9a1cc160c5`
- `Source/DSP/SeptumSysEx.cpp`: `8e08143ae64dbeded54e1846366303ae46a7aa6bbd8da4472beac67471afe17b`
- Probe source: `fd1e5b72665174f8f036be2ab1d323bd133d8cd7f18cfdc2bc5c2c479d7b79ff`

```cpp
#include "DSP/SeptumEngine.h"
#include "DSP/SeptumPresets.h"
#include <cmath>
#include <complex>
#include <cstdio>
#include <vector>

double amplitude(int cutoff, int note, int slope, bool bypass, int resonance) {
    constexpr double sr=44100;
    auto p=septum::initPatch(); auto& t=p.upper;
    t.osc1.wave=septum::Waveform::Sine; t.balance=-63;
    t.filterType=bypass?septum::FilterType::Bypass:septum::FilterType::Lpf;
    t.filterSlope=slope?septum::FilterSlope::Db24:septum::FilterSlope::Db12;
    t.cutoff=cutoff; t.resonance=resonance; t.keyFollow=0; t.cutoffVelocitySens=0;
    t.filterEnvDepth=0; t.level=28; t.levelVelocitySens=0;
    t.ampEnvAttack=0;t.ampEnvDecay=0;t.ampEnvSustain=127;
    t.lfo1.depth1=t.lfo1.depth2=t.lfo2.depth1=t.lfo2.depth2=0;
    p.delayOn=p.reverbOn=false;
    septum::Engine e;e.prepare(sr,256);e.setPatch(p);e.noteOn(note,100);
    std::vector<float> l(44100),r(l.size());
    for(int pos=0;pos<44100;pos+=256)e.process(l.data()+pos,r.data()+pos,std::min(256,44100-pos));
    double ss=0,cc=0,sc=0,sy=0,cy=0;
    double f=440*std::exp2((note-69)/12.0);
    for(int i=22050;i<44100;i++) {double s=sin(2*septum::mapping::pi*f*i/sr),c=cos(2*septum::mapping::pi*f*i/sr);ss+=s*s;cc+=c*c;sc+=s*c;sy+=s*l[i];cy+=c*l[i];}
    double d=ss*cc-sc*sc,a=(sy*cc-cy*sc)/d,b=(cy*ss-sy*sc)/d;
    return std::hypot(a,b);
}
int main(){
    double worst=0;
    std::printf("cutoff,note,slope,resonance,coefficient_hz,frequency_hz,measured_db,theory_db,error_db\n");
    for(int cutoff:{30,47,57,64,95,127})for(int note:{36,60,84})for(int slope:{0,1}) for(int resonance:{0,31}) {
        double fc=std::min(.45*44100,septum::mapping::cutoffHz(cutoff));
        double f=440*std::exp2((note-69)/12.0);
        double r=std::tan(septum::mapping::pi*f/44100)/std::tan(septum::mapping::pi*fc/44100);
        double expected=1/std::abs(std::complex<double>(1-r*r,septum::mapping::resonanceDamping(resonance)*r));
        if(slope)expected/=std::abs(std::complex<double>(1-r*r,1.2*r));
        double measured=amplitude(cutoff,note,slope,false,resonance)/amplitude(cutoff,note,slope,true,resonance);
        double db=20*log10(measured),tdb=20*log10(expected);
        worst=std::max(worst,std::abs(db-tdb));
        std::printf("%d,%d,%d,%d,%.8f,%.8f,%.8f,%.8f,%.8f\n",cutoff,note,slope?24:12,resonance,fc,f,db,tdb,db-tdb);
    }
    std::fprintf(stderr,"max error %.9f dB\n",worst);
}
```

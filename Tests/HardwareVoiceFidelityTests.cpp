// Behavioral hardware references:
// Roland SH-201 OM pp. 31, 40, 62 (pitch AD, S&H, key trigger and fade).
// https://static.roland.com/assets/media/pdf/SH-201_OM.pdf
// Jim Aikin, Electronic Musician, March 2007, pp. 92-93 (PDF pp. 100-101):
// one-octave pitch-envelope limit and polyphonic keyed LFO operation.
// https://www.worldradiohistory.com/Archive-All-Music/Electronic-Musician/2007/EM-Electronic-Musician-2007-03.pdf
// Rendered-audio comparisons validate these contracts, not Roland's unknown
// envelope time curves, LFO depth laws or random-number sequence.

#include "DSP/SeptumEngine.h"
#include "DSP/SeptumPresets.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace
{
int checks = 0;
int failures = 0;

void expect (bool ok, const std::string& message)
{
    ++checks;
    if (! ok)
    {
        ++failures;
        std::fprintf (stderr, "FAIL: %s\n", message.c_str());
    }
}

septum::Patch sinePatch()
{
    auto patch = septum::initPatch();
    auto& tone = patch.upper;
    tone.osc1.wave = septum::Waveform::Sine;
    tone.balance = -63;
    tone.filterType = septum::FilterType::Bypass;
    tone.ampEnvAttack = 0;
    tone.ampEnvDecay = 0;
    tone.ampEnvSustain = 127;
    tone.ampEnvRelease = 0;
    tone.level = 28; // Two voices and their sum stay below every limiter.
    tone.levelVelocitySens = 0;
    tone.lfo1.depth1 = tone.lfo1.depth2 = 0;
    tone.lfo2.depth1 = tone.lfo2.depth2 = 0;
    patch.delayOn = patch.reverbOn = false;
    return patch;
}

std::vector<float> render (septum::Engine& engine, int count, int blockSize = 256)
{
    std::vector<float> left (static_cast<std::size_t> (count));
    std::vector<float> right (static_cast<std::size_t> (count));
    for (int position = 0; position < count; position += blockSize)
    {
        const int n = std::min (blockSize, count - position);
        engine.process (left.data() + position, right.data() + position, n);
    }
    return left;
}

double rms (const std::vector<float>& audio, int first = 0)
{
    double energy = 0.0;
    for (std::size_t i = static_cast<std::size_t> (first); i < audio.size(); ++i)
        energy += audio[i] * static_cast<double> (audio[i]);
    return std::sqrt (energy / (audio.size() - static_cast<std::size_t> (first)));
}

// A second note must not alter the LFO on a held first note. A two-note
// performance must equal the sum of its individually played lines. Silent
// preroll is identical, so this also validates shared phase with trigger OFF.
void testIndependentNotes()
{
    for (const double sr : { 44100.0, 48000.0, 96000.0 })
        for (const bool lfo2 : { false, true })
            for (const bool keyed : { false, true })
                for (const bool synced : { false, true })
                    for (const int fade : { 0, 48 })
                    {
                        auto patch = sinePatch();
                        auto& lfo = lfo2 ? patch.upper.lfo2 : patch.upper.lfo1;
                        lfo.shape = septum::LfoShape::Sin;
                        lfo.rate = 88;
                        lfo.keyTrigger = keyed;
                        lfo.tempoSync = synced;
                        lfo.tempoSyncNote = 11;
                        lfo.fadeTime = fade;
                        lfo.destination2 = septum::LfoDest2::Amp;
                        lfo.depth2 = 55;

                        septum::Engine first, second, together;
                        for (auto* engine : { &first, &second, &together })
                        {
                            engine->prepare (sr, 256);
                            engine->setPatch (patch);
                        }
                        first.noteOn (60, 100);
                        together.noteOn (60, 100);
                        const int onset = static_cast<int> (sr * 0.27) / 8 * 8;
                        render (first, onset);
                        render (second, onset);
                        render (together, onset);
                        second.noteOn (67, 100);
                        together.noteOn (67, 100);
                        const int count = static_cast<int> (sr * 0.7);
                        const auto a = render (first, count);
                        const auto b = render (second, count);
                        const auto ab = render (together, count);
                        double maxError = 0.0;
                        for (std::size_t i = 0; i < ab.size(); ++i)
                            maxError = std::max (maxError,
                                std::abs (static_cast<double> (ab[i]) - a[i] - b[i]));
                        const std::string label = "independent LFO" + std::to_string (lfo2 ? 2 : 1)
                            + " keyed=" + std::to_string (keyed)
                            + " synced=" + std::to_string (synced)
                            + " fade=" + std::to_string (fade)
                            + " sr=" + std::to_string (sr);
                        expect (rms (ab) > 0.0001, label + " is audible");
                        expect (maxError < 2.0e-7,
                                label + " superposition error=" + std::to_string (maxError));
                    }
}

void testSampleHoldRestart()
{
    for (const bool keyed : { false, true })
        for (const bool lfo2 : { false, true })
        {
            constexpr double sr = 48000.0;
            auto patch = sinePatch();
            patch.upper.mono = septum::MonoMode::Solo;
            auto& lfo = lfo2 ? patch.upper.lfo2 : patch.upper.lfo1;
            lfo.shape = septum::LfoShape::SampleHold;
            lfo.rate = 0; // Entire fixture fits within one natural LFO cycle.
            lfo.keyTrigger = keyed;
            lfo.destination2 = septum::LfoDest2::Amp;
            lfo.depth2 = 55;
            septum::Engine engine;
            engine.prepare (sr, 256);
            engine.setPatch (patch);
            std::array<double, 6> levels {};
            for (double& level : levels)
            {
                engine.noteOn (69, 100);
                const auto audio = render (engine, 4800);
                level = rms (audio, 2400); // 22 exact 440 Hz cycles after settling.
            }
            const auto bounds = std::minmax_element (levels.begin(), levels.end());
            const double spread = *bounds.second / *bounds.first;
            expect (keyed ? spread > 1.05 : spread < 1.001,
                    std::string (keyed ? "keyed" : "free") + " S&H LFO"
                    + std::to_string (lfo2 ? 2 : 1) + " repeat spread="
                    + std::to_string (spread));
        }
}

void testPhaseAndFadeControls()
{
    constexpr double sr = 48000.0;
    for (const bool lfo2 : { false, true })
        for (const bool keyed : { false, true })
        {
            auto patch = sinePatch();
            auto& lfo = lfo2 ? patch.upper.lfo2 : patch.upper.lfo1;
            lfo.shape = septum::LfoShape::Sin;
            lfo.rate = 88;
            lfo.keyTrigger = keyed;
            lfo.destination2 = septum::LfoDest2::Amp;
            lfo.depth2 = 55;
            septum::Engine immediate, delayed;
            for (auto* engine : { &immediate, &delayed })
            {
                engine->prepare (sr, 256);
                engine->setPatch (patch);
                // Start both engines at this patch's settled gain. Otherwise
                // only the delayed engine settles the default-to-fixture
                // PATCH LEVEL edit during its LFO-phase preroll.
                engine->reset();
            }
            render (delayed, 12960);
            immediate.noteOn (69, 100);
            delayed.noteOn (69, 100);
            const auto a = render (immediate, 24000);
            const auto b = render (delayed, 24000);
            double difference = 0.0;
            for (std::size_t i = 0; i < a.size(); ++i)
                difference = std::max (difference,
                    std::abs (static_cast<double> (a[i]) - b[i]));
            expect (keyed ? difference < 2.0e-7 : difference > 0.0001,
                    "KEY TRIGGER controls LFO phase, LFO" + std::to_string (lfo2 ? 2 : 1)
                    + " keyed=" + std::to_string (keyed));

            // A separate positive control makes ignoring FADE TIME fail:
            // the faded voice initially stays closer to unmodulated audio,
            // then reaches the same modulation depth as a zero-fade voice.
            std::array<septum::Engine, 3> engines;
            std::array<std::vector<float>, 3> audio;
            for (int index = 0; index < 3; ++index)
            {
                auto version = patch;
                auto& params = lfo2 ? version.upper.lfo2 : version.upper.lfo1;
                if (index == 0)
                    params.depth2 = 0;
                params.fadeTime = index == 2 ? 48 : 0;
                engines[static_cast<std::size_t> (index)].prepare (sr, 256);
                engines[static_cast<std::size_t> (index)].setPatch (version);
                engines[static_cast<std::size_t> (index)].noteOn (69, 100);
                audio[static_cast<std::size_t> (index)] =
                    render (engines[static_cast<std::size_t> (index)], 96000);
            }
            const auto differenceEnergy = [&] (int index, int from, int to)
            {
                double sum = 0.0;
                for (int i = from; i < to; ++i)
                {
                    const double delta = audio[static_cast<std::size_t> (index)][i]
                        - static_cast<double> (audio[0][i]);
                    sum += delta * delta;
                }
                return sum;
            };
            expect (differenceEnergy (1, 480, 7200) > 1.0e-5,
                    "LFO depth produces audible modulation");
            expect (differenceEnergy (2, 480, 7200)
                        < 0.03 * differenceEnergy (1, 480, 7200),
                    "FADE TIME attenuates initial modulation independently of key trigger");
            const double lateRatio = differenceEnergy (2, 81600, 96000)
                                     / differenceEnergy (1, 81600, 96000);
            expect (lateRatio > 0.999 && lateRatio < 1.001,
                    "FADE TIME eventually reaches full modulation");
        }
}

double crossingFrequency (const std::vector<float>& audio, double sr,
                          int first, int last)
{
    std::vector<double> crossings;
    for (int i = std::max (1, first); i < last; ++i)
        if (audio[static_cast<std::size_t> (i - 1)] <= 0.0f
            && audio[static_cast<std::size_t> (i)] > 0.0f)
        {
            const double a = audio[static_cast<std::size_t> (i - 1)];
            const double b = audio[static_cast<std::size_t> (i)];
            crossings.push_back (i - 1.0 - a / (b - a));
        }
    return crossings.size() < 3 ? 0.0
        : sr * (crossings.size() - 1.0) / (crossings.back() - crossings.front());
}

void testPitchEnvelopeOctave()
{
    for (const double sr : { 44100.0, 48000.0, 96000.0 })
        for (const bool osc2 : { false, true })
            for (const int depth : { -63, 0, 63 })
            {
                auto patch = sinePatch();
                patch.upper.osc2.wave = septum::Waveform::Sine;
                patch.upper.balance = osc2 ? 63 : -63;
                auto& oscillator = osc2 ? patch.upper.osc2 : patch.upper.osc1;
                oscillator.pitchEnvDepth = depth;
                patch.upper.pitchEnvAttack = 0;
                patch.upper.pitchEnvDecay = 127;
                septum::Engine engine;
                engine.prepare (sr, 256);
                engine.setPatch (patch);
                engine.noteOn (69, 100);
                const auto audio = render (engine, static_cast<int> (sr * 0.07));
                const double hz = crossingFrequency (audio, sr,
                    static_cast<int> (sr * 0.008), static_cast<int> (sr * 0.035));
                const double expected = depth < 0 ? 220.0 : depth > 0 ? 880.0 : 440.0;
                // The reported endpoint is +/-1 octave. The observation
                // window sits just after attack, so the existing exponential
                // decay moves the pitch slightly back toward the played key.
                expect (std::abs (hz / expected - 1.0) < 0.02,
                        "pitch-envelope octave endpoint OSC" + std::to_string (osc2 ? 2 : 1)
                        + " depth=" + std::to_string (depth) + " sr="
                        + std::to_string (sr) + " frequency=" + std::to_string (hz));
            }
}

void testGlobalAudioFilterOwnership()
{
    constexpr double sr = 48000.0;
    for (const bool keyed : { false, true })
    {
        auto patch = sinePatch();
        patch.upper.level = 0;
        patch.upper.lfo1.shape = septum::LfoShape::Sin;
        patch.upper.lfo1.rate = 88;
        patch.upper.lfo1.keyTrigger = keyed;
        patch.upper.lfo1.fadeTime = 32;
        patch.upper.lfo1.destination1 = septum::LfoDest1::AudioFilter;
        patch.upper.lfo1.depth1 = 50;
        septum::ExternalInput settings;
        settings.filterOn = true;
        settings.cutoff = 76;
        std::array<septum::Engine, 2> engines;
        std::array<std::vector<float>, 2> output;
        for (int index = 0; index < 2; ++index)
        {
            auto& engine = engines[static_cast<std::size_t> (index)];
            engine.prepare (sr, 256);
            engine.setPatch (patch);
            engine.setExternalInput (settings);
            for (int note = 60; note < (index == 0 ? 61 : 65); ++note)
                engine.noteOn (note, 100);
            constexpr int count = 19200;
            auto& left = output[static_cast<std::size_t> (index)];
            left.resize (count);
            std::vector<float> right (count), input (count);
            for (int i = 0; i < count; ++i)
                input[static_cast<std::size_t> (i)] = static_cast<float> (
                    0.1 * std::sin (2.0 * septum::mapping::pi * 1400.0 * i / sr));
            for (int position = 0; position < count; position += 256)
                engine.process (left.data() + position, right.data() + position,
                    std::min (256, count - position), input.data() + position,
                    input.data() + position);
        }
        expect (rms (output[0]) > 0.0001, "global AUDIO FILTER fixture is audible");
        expect (output[0] == output[1],
                "AUDIO FILTER retains one shared modulation path with one or five voices");
    }
}

// OM p. 32, Roland's published LEAD #20 "Super Sync", and the qualified
// owner's report in oscillator-semantics.md support Super Saw sync. These
// tests validate our explicitly voiced all-seven reset contract, not a
// measured Roland phase topology or relative oscillator level.
void testSuperSawSyncBehavior()
{
    for (const double sr : { 44100.0, 48000.0, 96000.0 })
        for (const auto master : { septum::Waveform::Saw, septum::Waveform::SuperSaw })
            for (const int coarse : { -12, 7, 26 })
                for (const int width : { 0, 91 })
                {
                    auto patch = sinePatch();
                    auto& tone = patch.upper;
                    tone.osc1.wave = septum::Waveform::SuperSaw;
                    tone.osc1.coarse = coarse;
                    tone.osc1.fine = 7; // Every ratio is deliberately noninteger.
                    tone.osc1.pulseWidth = width;
                    tone.osc2.wave = master;
                    tone.osc2.pulseWidth = 103;
                    tone.mixType = septum::MixModType::Sync;
                    const auto run = [&] (const septum::Patch& version, int blockSize)
                    {
                        septum::Engine engine;
                        engine.prepare (sr, 256);
                        engine.setPatch (version);
                        engine.noteOn (69, 100);
                        return render (engine, static_cast<int> (sr * 0.3), blockSize);
                    };
                    const auto sync = run (patch, 256);
                    const auto fragmented = run (patch, 37);
                    tone.mixType = septum::MixModType::Mix;
                    const auto mix = run (patch, 256);
                    const auto settled = static_cast<std::size_t> (sr * 0.15);
                    double energy = 0.0, change = 0.0, blockError = 0.0;
                    for (std::size_t i = settled; i < sync.size(); ++i)
                    {
                        energy += sync[i] * static_cast<double> (sync[i]);
                        change += std::pow (static_cast<double> (sync[i]) - mix[i], 2.0);
                        blockError = std::max (blockError,
                            std::abs (static_cast<double> (sync[i]) - fragmented[i]));
                    }
                    const std::string label = "Super Saw SYNC master="
                        + std::to_string (static_cast<int> (master)) + " coarse="
                        + std::to_string (coarse) + " width=" + std::to_string (width)
                        + " sr=" + std::to_string (sr);
                    expect (std::all_of (sync.begin(), sync.end(),
                                        [] (float x) { return std::isfinite (x); }),
                            label + " remains finite");
                    expect (energy > 1.0e-6, label + " is audible");
                    expect (change > 0.05 * energy, label + " responds to SYNC instead of bypassing it");
                    expect (blockError < 2.0e-7,
                            label + " is invariant across irregular process blocks; error="
                            + std::to_string (blockError));
                }
}

void testSuperSawSyncFractionalLanding()
{
    // Put all seven slave frequencies below the master. Between resets none
    // can wrap: their weighted sum is therefore exactly a ramp in the
    // master's continuous phase. This closed-form identity independently
    // checks fractional reset placement, including every detuned increment.
    // A reset rounded to a sample, a center-only reset, or resetting the HPF
    // history breaks the identity. It is a model contract, not hardware data.
    for (const double sr : { 44100.0, 48000.0, 96000.0 })
    {
        auto patch = sinePatch();
        auto& tone = patch.upper;
        tone.osc1.wave = septum::Waveform::SuperSaw;
        tone.osc1.coarse = -12;
        tone.osc1.fine = 7;
        tone.osc1.pulseWidth = 127;
        tone.osc2.wave = septum::Waveform::Saw;
        tone.mixType = septum::MixModType::Sync;
        septum::Engine engine;
        engine.prepare (sr, 256);
        engine.setPatch (patch);
        // Irrational period avoids placing a reset exactly on a sample,
        // where accumulated phase and closed-form phase can round oppositely.
        constexpr int note = 68;
        const double masterHz = 440.0 * std::exp2 ((note - 69) / 12.0);
        engine.noteOn (note, 100);
        const auto audio = render (engine, static_cast<int> (sr * 0.45));

        const double ratio = std::exp2 (-1.0 + 7.0 / 1200.0);
        const double amount = septum::mapping::superSawDetuneAmount (1.0);
        double slope = 0.0, intercept = 0.0;
        for (std::size_t i = 0; i < 7; ++i)
        {
            const double gain = (i == 3 ? septum::mapping::superSawCenterGain()
                                        : septum::mapping::superSawSideGain())
                                * septum::mapping::superSawStackNormalisation;
            slope += 2.0 * gain * ratio
                     * (1.0 + septum::mapping::superSawOffsets[i] * amount);
            intercept -= gain;
        }

        // Apply the existing modeled post-stack high-pass and separately
        // tested output circuit to that independent continuous-phase ramp.
        const double w = 2.0 * septum::mapping::pi * masterHz * ratio / sr;
        const double c = std::cos (w), a = std::sin (w) / std::sqrt (2.0);
        const double b0 = (1.0 + c) / (2.0 * (1.0 + a));
        const double a1 = -2.0 * c / (1.0 + a), a2 = (1.0 - a) / (1.0 + a);
        double x1 = 0.0, x2 = 0.0, y1 = 0.0, y2 = 0.0;
        septum::AnalogOutput output;
        output.prepare (sr);
        const int transport = engine.latencySamples() - septum::AnalogOutput::latencySamples;
        std::vector<double> ideal (audio.size());
        for (std::size_t i = 0; i < ideal.size(); ++i)
        {
            double filtered = 0.0;
            if (i >= static_cast<std::size_t> (transport))
            {
                const double cycles = (i - transport + 1.0) * masterHz / sr;
                const double x = slope * (cycles - std::floor (cycles)) + intercept;
                filtered = b0 * (x - 2.0 * x1 + x2) - a1 * y1 - a2 * y2;
                x2 = x1; x1 = x; y2 = y1; y1 = filtered;
            }
            ideal[i] = output.processSample (filtered);
        }

        // Only nuisance overall gain and startup coupling state are removed;
        // no phase/time shift, oscillator, filter or EQ parameter is fitted.
        const auto first = static_cast<std::size_t> (sr * 0.2);
        double xx = 0.0, xc = 0.0, cc = 0.0, xy = 0.0, cy = 0.0, yy = 0.0;
        for (std::size_t i = first; i < audio.size(); ++i)
        {
            const double coupling = std::exp (
                -double (i - first) / (sr * septum::AnalogOutput::couplingSeconds));
            xx += ideal[i] * ideal[i]; xc += ideal[i] * coupling; cc += coupling * coupling;
            xy += ideal[i] * audio[i]; cy += coupling * audio[i]; yy += audio[i] * audio[i];
        }
        const double determinant = xx * cc - xc * xc;
        const double gain = (xy * cc - cy * xc) / determinant;
        const double dc = (cy * xx - xy * xc) / determinant;
        double error = 0.0;
        for (std::size_t i = first; i < audio.size(); ++i)
        {
            const double coupling = std::exp (
                -double (i - first) / (sr * septum::AnalogOutput::couplingSeconds));
            error += std::pow (audio[i] - gain * ideal[i] - dc * coupling, 2.0);
        }
        const double relative = std::sqrt (error / yy);
        expect (gain > 0.0 && relative < 0.002,
                "all-seven SYNC preserves fractional master timing and HPF history at "
                    + std::to_string (sr) + " Hz; relative error=" + std::to_string (relative));
    }
}

// Project over complete fundamental cycles so the other pulse harmonics
// largely cancel. This is a broad audible-behavior check, not a recorded
// hardware spectrum or a fitted transfer-function snapshot.
double harmonicAmplitude (const std::vector<float>& audio, double sr,
                          double fundamental, int harmonic, double start,
                          int cycles = 4)
{
    const int first = static_cast<int> (std::lround (start * sr));
    const int count = static_cast<int> (std::lround (cycles * sr / fundamental));
    double real = 0.0, imaginary = 0.0;
    for (int i = first; i < first + count; ++i)
    {
        const double angle = 2.0 * septum::mapping::pi * fundamental * harmonic * i / sr;
        real += audio[static_cast<std::size_t> (i)] * std::cos (angle);
        imaginary += audio[static_cast<std::size_t> (i)] * std::sin (angle);
    }
    return 2.0 * std::hypot (real, imaginary) / count;
}

septum::Patch filterDecayPatch()
{
    auto patch = sinePatch();
    auto& tone = patch.upper;
    // Moogie 1 Upper's documented oscillator/filter controls, isolated from
    // its Lower tone. Overall level is reduced to keep the fixture linear.
    tone.osc1.wave = septum::Waveform::PulseSquare;
    tone.osc1.coarse = tone.osc2.coarse = -36;
    tone.osc1.pulseWidth = 57;
    tone.osc2.wave = septum::Waveform::Sine;
    tone.balance = 0;
    tone.filterType = septum::FilterType::Lpf;
    tone.filterSlope = septum::FilterSlope::Db24;
    tone.cutoff = 30;
    tone.resonance = tone.keyFollow = tone.cutoffVelocitySens = 0;
    tone.filterEnvAttack = 0;
    tone.filterEnvDecay = 49;
    tone.filterEnvSustain = tone.filterEnvRelease = 0;
    tone.filterEnvDepth = 22;
    return patch;
}

void testFilterDecayRetainsTransient()
{
    for (const double sr : { 44100.0, 48000.0, 96000.0 })
    {
        auto patch = filterDecayPatch();
        septum::Engine steady, reconfigured;
        for (auto* engine : { &steady, &reconfigured })
        {
            engine->prepare (sr, 256);
            engine->setPatch (patch);
            engine->noteOn (69, 100); // 55 Hz after the published coarse tune.
        }
        const int count = static_cast<int> (sr * 0.65);
        const auto audio = render (steady, count);
        std::vector<float> updated (static_cast<std::size_t> (count)), right (updated.size());
        for (int at = 0; at < count; at += 256)
        {
            // Ordinary host control/tempo updates must not restart the
            // envelope or recompute a shrinking rate from its current level.
            patch.tempo = (at / 256) % 2 ? 91 : 173;
            reconfigured.setPatch (patch);
            reconfigured.process (updated.data() + at, right.data() + at,
                                  std::min (256, count - at));
        }
        double difference = 0.0;
        for (std::size_t i = 0; i < audio.size(); ++i)
            difference = std::max (difference,
                std::abs (static_cast<double> (audio[i]) - updated[i]));
        const double early = harmonicAmplitude (audio, sr, 55.0, 8, 0.11)
                             / harmonicAmplitude (audio, sr, 55.0, 2, 0.11);
        const double late = harmonicAmplitude (audio, sr, 55.0, 8, 0.54)
                            / harmonicAmplitude (audio, sr, 55.0, 2, 0.54);
        const std::string label = "linear filter decay at " + std::to_string (sr);
        expect (early > 0.05, label + " retains high harmonics after 100 ms");
        expect (late < 0.02 && early > 5.0 * late,
                label + " reaches the dark zero-sustain endpoint");
        expect (difference < 2.0e-7,
                label + " is unchanged by repeated patch/tempo updates");
        expect (std::all_of (audio.begin(), audio.end(), [] (float x) { return std::isfinite (x); }),
                label + " stays finite");
        steady.noteOff (69);
        render (steady, static_cast<int> (sr * 0.05));
        expect (steady.activeVoiceCount() == 0, label + " releases and frees its voice");
    }
}

void testLinearFilterSustainAutomation()
{
    for (const double sr : { 44100.0, 48000.0, 96000.0 })
        for (const auto transition : { std::array<int, 2> { 0, 64 },
                                       std::array<int, 2> { 64, 127 },
                                       std::array<int, 2> { 0, 127 } })
        {
            auto from = filterDecayPatch();
            from.upper.osc1.wave = septum::Waveform::Sine;
            from.upper.osc1.coarse = 0;
            from.upper.balance = -63;
            from.upper.filterEnvSustain = transition[0];
            auto to = from;
            to.upper.filterEnvSustain = transition[1];
            septum::Engine moving, unmoved, target;
            for (auto* engine : { &moving, &unmoved, &target })
            {
                engine->prepare (sr, 256);
                engine->setPatch (engine == &target ? to : from);
                engine->noteOn (69, 100);
                render (*engine, static_cast<int> (sr * 0.6));
            }
            moving.setPatch (to);
            const int count = static_cast<int> (sr * 0.6);
            const auto a = render (moving, count);
            const auto b = render (unmoved, count);
            const auto goal = render (target, count);
            const double expected = harmonicAmplitude (goal, sr, 440.0, 1, 0.5, 20);
            const double arrived = harmonicAmplitude (a, sr, 440.0, 1, 0.5, 20);
            double earlyDifference = 0.0;
            const int earlyEnd = moving.latencySamples() + static_cast<int> (sr * 0.002);
            for (int i = 0; i < earlyEnd; ++i)
                earlyDifference = std::max (earlyDifference,
                    std::abs (static_cast<double> (a[static_cast<std::size_t> (i)])
                              - b[static_cast<std::size_t> (i)]));
            const std::string label = "filter sustain " + std::to_string (transition[0])
                + " -> " + std::to_string (transition[1]) + " at " + std::to_string (sr);
            expect (expected > 1.0e-5 && std::abs (arrived / expected - 1.0) < 0.01,
                    label + " converges to the new target, including 127");
            expect (earlyDifference < 0.02 * expected,
                    label + " moves continuously instead of jumping");
            moving.noteOff (69);
            render (moving, static_cast<int> (sr * 0.05));
            expect (moving.activeVoiceCount() == 0, label + " still releases");
        }
}

void testFilterChangePreservesOtherEnvelopeTiming()
{
    for (const double sr : { 44100.0, 48000.0, 96000.0 })
    {
        auto ampPatch = sinePatch();
        ampPatch.upper.ampEnvDecay = 49;
        ampPatch.upper.ampEnvSustain = 0;
        septum::Engine amp;
        amp.prepare (sr, 256);
        amp.setPatch (ampPatch);
        amp.noteOn (69, 100);
        const auto amplitude = render (amp, static_cast<int> (sr * 0.2));
        expect (harmonicAmplitude (amplitude, sr, 440.0, 1, 0.12, 12)
                    < 0.01 * harmonicAmplitude (amplitude, sr, 440.0, 1, 0.008, 8),
                "AMP decay retains its fast exponential timing at " + std::to_string (sr));

        auto pitchPatch = sinePatch();
        pitchPatch.upper.osc1.pitchEnvDepth = 63;
        pitchPatch.upper.pitchEnvDecay = 49;
        pitchPatch.upper.ampEnvRelease = 49;
        septum::Engine pitch;
        pitch.prepare (sr, 256);
        pitch.setPatch (pitchPatch);
        pitch.noteOn (69, 100);
        const auto audio = render (pitch, static_cast<int> (sr * 0.15));
        expect (std::abs (crossingFrequency (audio, sr,
                    static_cast<int> (sr * 0.09), static_cast<int> (sr * 0.14)) - 440.0) < 1.0,
                "PITCH decay retains its fast exponential timing at " + std::to_string (sr));
        pitch.noteOff (69);
        render (pitch, static_cast<int> (sr * 0.13));
        expect (pitch.activeVoiceCount() == 0,
                "AMP release retains its exponential timing at " + std::to_string (sr));

        auto filterPatch = filterDecayPatch();
        filterPatch.upper.filterEnvSustain = 127;
        filterPatch.upper.filterEnvRelease = 49;
        filterPatch.upper.ampEnvRelease = 127; // Keep the source audible during the filter release.
        septum::Engine filter;
        filter.prepare (sr, 256);
        filter.setPatch (filterPatch);
        filter.noteOn (69, 100);
        render (filter, static_cast<int> (sr * 0.1));
        filter.noteOff (69);
        const auto release = render (filter, static_cast<int> (sr * 0.25));
        const double ratio = harmonicAmplitude (release, sr, 55.0, 8, 0.12)
                             / harmonicAmplitude (release, sr, 55.0, 2, 0.12);
        expect (filter.activeVoiceCount() == 1 && ratio < 0.02,
                "FILTER release retains its fast exponential timing at " + std::to_string (sr));
    }
}

// SupaJuce's published depth 31 needs about 5.9 octaves near the envelope peak.
// The adopted linear range gives 4 octaves at depth 21. Locate that corner
// through the complete voice path with quiet external sine input; this also
// checks signed modulation and that depth 0 leaves the cutoff knob alone.
// The range is an empirical calibration, not a documented Roland table.
void testFilterEnvelopeRange()
{
    for (const double sr : { 44100.0, 48000.0, 96000.0 })
        for (const int depth : { -21, 0, 21 })
        {
            const int cutoff = depth < 0 ? 100 : 64;
            const double baseHz = septum::mapping::cutoffHz (cutoff);
            const double frequency = baseHz * (depth < 0 ? 1.0 / 16.0
                                                       : depth > 0 ? 16.0 : 1.0);
            const auto probe = [&] (bool bypass)
            {
                auto patch = sinePatch();
                auto& tone = patch.upper;
                tone.osc1.wave = septum::Waveform::ExtIn;
                tone.filterType = bypass ? septum::FilterType::Bypass
                                         : septum::FilterType::Lpf;
                tone.filterSlope = septum::FilterSlope::Db24;
                tone.cutoff = cutoff;
                tone.resonance = 40;
                tone.filterEnvDepth = depth;
                tone.filterEnvAttack = tone.filterEnvDecay = 0;
                tone.filterEnvSustain = 127;
                tone.keyFollow = tone.cutoffVelocitySens = 0;
                septum::ExternalInput input;
                input.inputVolume = 127;
                septum::Engine engine;
                engine.prepare (sr, 256);
                engine.setPatch (patch);
                engine.setExternalInput (input);
                engine.noteOn (60, 100);
                const int count = static_cast<int> (sr * 0.3);
                std::vector<float> source (count), left (count), right (count);
                for (int i = 0; i < count; ++i)
                    source[static_cast<std::size_t> (i)] = static_cast<float> (
                        0.001 * std::sin (2.0 * septum::mapping::pi * frequency * i / sr));
                for (int at = 0; at < count; at += 256)
                    engine.process (left.data() + at, right.data() + at,
                        std::min (256, count - at), source.data() + at, source.data() + at);
                return harmonicAmplitude (left, sr, frequency, 1, 0.15, 24);
            };
            const double gain = 20.0 * std::log10 (probe (false) / probe (true));
            expect (gain > 9.0 && gain < 13.0,
                    "filter envelope depth " + std::to_string (depth)
                        + " places its sustained resonance at " + std::to_string (frequency)
                        + " Hz at sample rate " + std::to_string (sr)
                        + ": gain " + std::to_string (gain) + " dB");
        }
}

// Conditional SupaJuce/Air Lead fits support roughly Q2 per section near
// raw40/44. Measure the actual small-signal engine, not the mapping helper.
// This bounds the adopted empirical model; it is not a dry hardware sweep.
void testModerateResonanceResponse()
{
    for (const double sr : { 44100.0, 48000.0, 96000.0 })
    {
        const auto response = [&] (bool audioFilter, bool bypass, int resonance,
                                  int blockSize)
        {
            auto patch = sinePatch();
            auto& tone = patch.upper;
            tone.osc1.wave = septum::Waveform::ExtIn;
            tone.filterType = bypass || audioFilter ? septum::FilterType::Bypass
                                                   : septum::FilterType::Lpf;
            tone.filterSlope = septum::FilterSlope::Db24;
            tone.cutoff = 64;
            tone.resonance = resonance;
            tone.filterEnvDepth = tone.keyFollow = tone.cutoffVelocitySens = 0;
            septum::ExternalInput input;
            input.inputVolume = 127;
            input.filterOn = audioFilter && ! bypass;
            input.type = septum::AudioFilterType::Lpf;
            input.slope = septum::FilterSlope::Db24;
            input.cutoff = 64;
            input.resonance = resonance;
            septum::Engine engine;
            engine.prepare (sr, 256);
            engine.setPatch (patch);
            engine.setExternalInput (input);
            // EXT-IN voices tap before the AUDIO FILTER; measure that separate
            // filter through the direct monitor instead.
            if (! audioFilter)
                engine.noteOn (60, 100);
            const int count = static_cast<int> (sr * 0.2);
            std::vector<float> source (count), left (count), right (count);
            const double frequency = septum::mapping::cutoffHz (64);
            for (int i = 0; i < count; ++i)
                source[static_cast<std::size_t> (i)] = static_cast<float> (
                    0.001 * std::sin (2.0 * septum::mapping::pi * frequency * i / sr));
            for (int at = 0; at < count; at += blockSize)
                engine.process (left.data() + at, right.data() + at,
                    std::min (blockSize, count - at), source.data() + at, source.data() + at);
            return left;
        };
        const auto amplitude = [&] (const std::vector<float>& x)
        {
            return harmonicAmplitude (x, sr, septum::mapping::cutoffHz (64), 1, 0.13, 24);
        };
        const auto bypass = response (false, true, 40, 256);
        const auto resonant = response (false, false, 40, 256);
        const auto partitioned = response (false, false, 40, 37);
        const double gain = 20.0 * std::log10 (amplitude (resonant) / amplitude (bypass));
        expect (gain > 9.0 && gain < 13.0,
                "raw40 LP24 has the adopted recording-informed emphasis at "
                    + std::to_string (sr) + " Hz: " + std::to_string (gain) + " dB");
        double difference = 0.0;
        for (std::size_t i = static_cast<std::size_t> (sr * 0.1); i < resonant.size(); ++i)
            difference = std::max (difference,
                std::abs (static_cast<double> (resonant[i]) - partitioned[i]));
        expect (difference < 2.0e-8,
                "settled resonant voice response agrees across irregular process blocks: "
                    + std::to_string (difference));

        const double zero = 20.0 * std::log10 (
            amplitude (response (false, false, 0, 256)) / amplitude (bypass));
        expect (std::abs (zero - (-7.6042)) < 0.02,
                "zero-resonance LP24 response retains its prior calibration");
        const double external = 20.0 * std::log10 (
            amplitude (response (true, false, 44, 256))
                / amplitude (response (true, true, 44, 256)));
        expect (std::abs (external - 3.8936) < 0.02,
                "the separate AUDIO FILTER retains its original resonance curve: "
                    + std::to_string (external) + " dB");
    }
}
} // namespace

int main()
{
    testIndependentNotes();
    testSampleHoldRestart();
    testPhaseAndFadeControls();
    testPitchEnvelopeOctave();
    testGlobalAudioFilterOwnership();
    testSuperSawSyncBehavior();
    testSuperSawSyncFractionalLanding();
    testFilterDecayRetainsTransient();
    testLinearFilterSustainAutomation();
    testFilterChangePreservesOtherEnvelopeTiming();
    testFilterEnvelopeRange();
    testModerateResonanceResponse();
    std::printf ("Hardware voice fidelity: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}

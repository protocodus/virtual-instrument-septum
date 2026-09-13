// MIDI clocks have 24 pulses per quarter note. Estimation, dropout, and
// resume policies are plug-in behavior; this is not a firmware timing fit.
#include "DSP/MidiTempoClock.h"
#include "DSP/SeptumEngine.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <limits>
#include <string>
#include <vector>

namespace
{
int checks = 0, failures = 0;

void expect (bool condition, const std::string& message)
{
    ++checks;
    if (! condition)
    {
        ++failures;
        std::fprintf (stderr, "FAIL: %s\n", message.c_str());
    }
}

void estimatorTests()
{
    for (double rate : { 8000.0, 22050.0, 32000.0, 44100.0, 48000.0, 96000.0, 192000.0 })
        for (double bpm : { 5.0, 60.0, 120.0, 137.25, 300.0 })
        {
            septum::MidiTempoClock clock;
            clock.prepare (rate);
            expect (! clock.running(), "clock waits for an interval after preparation");
            clock.pulse();
            expect (! clock.running(), "one pulse cannot establish a tempo");
            const double period = rate * 60.0 / (24.0 * bpm);
            int previous = 0;
            for (int pulse = 1; pulse <= 240; ++pulse)
            {
                const int current = static_cast<int> (std::lround (pulse * period));
                clock.advance (current - previous);
                clock.pulse();
                previous = current;
                expect (clock.running(), "regular legal clock remains acquired including endpoints");
                // A moving window's rounded endpoints differ by at most one
                // sample. Use that independent quantization error bound.
                const int count = std::min (pulse, 6);
                const double errorBound = bpm / (count * period - 1.0) + 1.0e-9;
                expect (std::abs (clock.bpm() - bpm) <= errorBound,
                        "24 PPQN estimate retains fractional tempo without accumulating drift");
                const double beforeDuplicate = clock.bpm();
                clock.pulse();
                expect (clock.bpm() == beforeDuplicate,
                        "duplicate timestamps neither perturb tempo nor add a zero interval");
            }
        }

    septum::MidiTempoClock jitter;
    jitter.prepare (48000.0);
    jitter.pulse();
    constexpr std::array<int, 6> deviations { -4, 2, 3, -2, 4, -3 };
    for (int cycle = 0; cycle < 20; ++cycle)
    {
        for (int error : deviations)
        {
            jitter.advance (1000 + error);
            jitter.pulse();
        }
        expect (std::abs (jitter.bpm() - 120.0) < 1.0e-12,
                "balanced timestamp jitter averages to the correct six-interval tempo");
    }
    for (int i = 0; i < 6; ++i)
    {
        jitter.advance (800);
        jitter.pulse();
    }
    expect (std::abs (jitter.bpm() - 150.0) < 1.0e-12,
            "six new intervals replace the previous tempo completely");

    // Dropout occurs after the stated silence allowance, not one sample
    // earlier. Reacquisition needs two genuinely separated fresh clocks.
    for (int period : { 1000, 24000 })
    {
        septum::MidiTempoClock clock;
        clock.prepare (48000.0);
        clock.pulse();
        clock.advance (period);
        clock.pulse();
        const int deadline = std::max (24000, 3 * period) + 1;
        expect (clock.samplesUntilTimeout (100000) == deadline,
                "timeout reports the precise next dropout sample");
        clock.advance (deadline - 1);
        expect (clock.running() && clock.samplesUntilTimeout (256) == 1,
                "clock remains acquired immediately before its dropout boundary");
        clock.advance (1);
        expect (! clock.running(), "clock stops at its dropout boundary");
        clock.pulse();
        expect (! clock.running(), "first pulse after dropout cannot reuse stale tempo");
        clock.advance (period);
        clock.pulse();
        expect (clock.running(), "second valid pulse resumes the clock");
        clock.advance (1);
        clock.pulse();
        expect (! clock.running(), "an out-of-range interval clears an acquired estimate");
        clock.advance (1000);
        clock.pulse();
        expect (clock.running() && std::abs (clock.bpm() - 120.0) < 1.0e-12,
                "an invalid interval cannot contaminate the next valid tempo");
    }

    // Same absolute pulse timestamps, very different audio block partitions.
    for (int block : { 1, 17, 64, 257, 2048 })
    {
        septum::MidiTempoClock clock;
        clock.prepare (44100.0);
        clock.pulse();
        for (int pulse = 0; pulse < 12; ++pulse)
        {
            int remaining = 1000;
            while (remaining > 0)
            {
                const int count = std::min (remaining, block);
                clock.advance (count);
                remaining -= count;
            }
            clock.pulse();
        }
        expect (clock.running() && clock.bpm() == 110.25,
                "sample-clock estimation is independent of audio block segmentation");
    }
}

septum::Patch arpPatch()
{
    septum::Patch patch;
    patch.tempo = 67;
    patch.delayOn = patch.reverbOn = false;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.ampEnvRelease = 0;
    patch.arpeggio.on = true;
    patch.arpeggio.grid = septum::ArpeggioGrid::TwentyFourth;
    patch.arpeggio.duration = septum::ArpeggioDuration::P30;
    patch.arpeggio.style = septum::ArpeggioStyle {};
    patch.arpeggio.style.endStep = 1;
    patch.arpeggio.style.cells[0][0] = 100;
    return patch;
}

struct Timeline
{
    explicit Timeline (int blockSize) : block (blockSize), left (blockSize), right (blockSize) {}
    void advanceTo (septum::Engine& engine, int target)
    {
        while (position < target)
        {
            const int count = std::min (block, target - position);
            engine.process (left.data(), right.data(), count);
            position += count;
        }
    }
    void at (septum::Engine& engine, int sample, int held)
    {
        advanceTo (engine, sample);
        engine.process (left.data(), right.data(), 1);
        ++position;
        expect (engine.heldVoiceCount (true) == held,
                "external-clock arpeggio gate at sample " + std::to_string (sample)
                    + ", block " + std::to_string (block));
    }
    int block, position = 0;
    std::vector<float> left, right;
};

void arpeggioTests()
{
    constexpr double rate = 44100.0, bpm = 137.25;
    const double step = rate * 60.0 / bpm / 6.0;
    for (int block : { 7, 64, 257 })
    {
        septum::Engine engine;
        engine.prepare (rate, block);
        engine.setPatch (arpPatch());
        engine.setTempoClock (bpm);
        engine.reset();
        engine.noteOn (60, 100);
        expect (engine.tempoBpm() == bpm && engine.currentPatch().tempo == 67,
                "fractional external tempo leaves stored PATCH TEMPO untouched");
        Timeline timeline (block);
        for (int cycle = 0; cycle < 24; ++cycle)
        {
            const int on = static_cast<int> (std::ceil (cycle * step));
            const int off = static_cast<int> (std::ceil ((cycle + 0.3) * step));
            if (cycle > 0)
                timeline.at (engine, on - 1, 0);
            timeline.at (engine, on, 1);
            timeline.at (engine, off - 1, 1);
            timeline.at (engine, off, 0);
        }
        engine.setTempoClock (0.0);
        expect (engine.tempoBpm() == 67.0, "clearing an external override restores patch tempo");
        engine.setTempoClock (std::numeric_limits<double>::quiet_NaN());
        expect (engine.tempoBpm() == 67.0, "an invalid external tempo cannot poison the engine");
    }

    septum::Engine engine;
    engine.prepare (rate, 64);
    engine.setPatch (arpPatch());
    engine.setTempoClock (bpm, false);
    engine.reset();
    engine.noteOn (60, 100);
    Timeline timeline (64);
    constexpr int waiting = 11025;
    timeline.advanceTo (engine, waiting);
    expect (engine.heldVoiceCount (true) == 0 && engine.activeVoiceCount() == 0,
            "an externally clocked arpeggio waits silently when no clock is acquired");
    engine.setTempoClock (bpm, true);
    timeline.at (engine, waiting, 1);
    const int pauseAt = waiting + 200;
    timeline.advanceTo (engine, pauseAt);
    engine.setTempoClock (bpm, false);
    timeline.advanceTo (engine, pauseAt + waiting);
    expect (engine.heldVoiceCount (true) == 1,
            "dropout freezes a pending musical gate while audio rendering continues");
    engine.setTempoClock (bpm, true);
    const int off = 2 * waiting + static_cast<int> (std::ceil (step * 0.3));
    timeline.at (engine, off - 1, 1);
    timeline.at (engine, off, 0);
    const int nextOn = 2 * waiting + static_cast<int> (std::ceil (step));
    timeline.at (engine, nextOn - 1, 0);
    timeline.at (engine, nextOn, 1);

    // Tempo edits preserve the fraction of the current interval already
    // elapsed, including the shorter note gate inside it.
    septum::Engine changing;
    changing.prepare (rate, 31);
    changing.setPatch (arpPatch());
    changing.setTempoClock (120.0);
    changing.reset();
    changing.noteOn (60, 100);
    Timeline edits (31);
    constexpr int changeAt = 200;
    edits.advanceTo (changing, changeAt);
    changing.setTempoClock (240.0);
    const double originalStep = rate * 60.0 / 120.0 / 6.0;
    const int scaledOff = static_cast<int> (std::ceil (
        changeAt + (0.3 * originalStep - changeAt) * 0.5));
    const int scaledOn = static_cast<int> (std::ceil (
        changeAt + (originalStep - changeAt) * 0.5));
    edits.at (changing, scaledOff - 1, 1);
    edits.at (changing, scaledOff, 0);
    edits.at (changing, scaledOn - 1, 0);
    edits.at (changing, scaledOn, 1);
}

void pausedReleaseTests()
{
    // Pausing musical time must not pause key/pedal lifecycle handling. A
    // note-off or latch release must remain effective without another clock.
    for (int holdMode : { 0, 1, 2 })
    {
        septum::Engine engine;
        engine.prepare (44100.0, 64);
        auto patch = arpPatch();
        patch.arpeggio.hold = holdMode == 2;
        engine.setPatch (patch);
        engine.setTempoClock (120.0);
        engine.reset();
        engine.noteOn (60, 100);
        std::array<float, 64> left {}, right {};
        engine.process (left.data(), right.data(), 64);
        expect (engine.heldVoiceCount (true) == 1, "release probe starts a held arpeggiated note");
        engine.setTempoClock (120.0, false);
        if (holdMode == 1)
            engine.setHold (true);
        engine.noteOff (60);
        engine.process (left.data(), right.data(), 64);
        expect (engine.heldVoiceCount (true) == (holdMode == 0 ? 0 : 1),
                "paused clock respects a released key and active sustain/arpeggio holds");
        if (holdMode == 1)
            engine.setHold (false);
        if (holdMode == 2)
        {
            patch.arpeggio.hold = false;
            engine.setPatch (patch);
        }
        engine.process (left.data(), right.data(), 64);
        expect (engine.heldVoiceCount (true) == 0,
                "lifting a hold releases a paused arpeggio without waiting for more clocks");
        engine.setTempoClock (120.0, true);
        for (int i = 0; i < 100; ++i)
            engine.process (left.data(), right.data(), 64);
        expect (engine.heldVoiceCount (true) == 0,
                "clock reacquisition cannot resurrect keys released during a stall");
    }

    septum::Engine engine;
    engine.prepare (44100.0, 64);
    auto patch = arpPatch();
    patch.arpeggio.hold = true;
    engine.setPatch (patch);
    engine.setTempoClock (120.0);
    engine.reset();
    engine.noteOn (60, 100);
    std::array<float, 64> left {}, right {};
    engine.process (left.data(), right.data(), 64);
    engine.setTempoClock (120.0, false);
    engine.allSoundOff();
    engine.process (left.data(), right.data(), 64);
    expect (engine.activeVoiceCount() == 0, "panic clears voices even when a held arpeggio is clock-stalled");
}

std::vector<float> lfoAudio (bool synced, bool running, int storedBpm,
                              double overrideBpm, int depth = 63)
{
    constexpr int rate = 44100, frames = rate / 2;
    septum::Engine engine;
    engine.prepare (rate, 256);
    septum::Patch patch;
    patch.tempo = storedBpm;
    patch.upper.osc1.wave = septum::Waveform::Sine;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.level = 80;
    patch.upper.lfo1.shape = septum::LfoShape::Sin;
    patch.upper.lfo1.keyTrigger = true;
    patch.upper.lfo1.tempoSync = synced;
    patch.upper.lfo1.tempoSyncNote = 19; // 1/32 whole note = eight cycles per beat
    patch.upper.lfo1.destination2 = septum::LfoDest2::Amp;
    patch.upper.lfo1.depth2 = depth;
    engine.setPatch (patch);
    engine.setTempoClock (overrideBpm, running);
    engine.reset();
    engine.noteOn (69, 100);
    std::vector<float> left (frames), right (frames);
    for (int i = 0; i < frames; i += 256)
        engine.process (left.data() + i, right.data() + i, std::min (256, frames - i));
    return left;
}

void lfoTests()
{
    const auto external = lfoAudio (true, true, 67, 150.0);
    const auto internal = lfoAudio (true, true, 150, 0.0);
    expect (external == internal, "external BPM drives the same audible synced-LFO rate as PATCH TEMPO");
    const auto fractional = lfoAudio (true, true, 67, 137.25);
    const auto otherPatch = lfoAudio (true, true, 299, 137.25);
    expect (fractional == otherPatch, "external LFO timing ignores stored tempo while preserving its value");
    const auto rounded = lfoAudio (true, true, 137, 0.0);
    double difference = 0.0, signal = 0.0;
    for (std::size_t i = 0; i < fractional.size(); ++i)
    {
        difference += std::pow (double (fractional[i]) - rounded[i], 2.0);
        signal += double (fractional[i]) * fractional[i];
    }
    expect (difference / signal > 1.0e-5,
            "fractional BPM changes audible LFO phase instead of rounding to an integer");
    expect (lfoAudio (true, false, 67, 137.25)
                == lfoAudio (true, false, 67, 137.25, 0),
            "a paused synced sine LFO stays at its initial zero-modulation phase");
    expect (lfoAudio (false, false, 67, 137.25)
                == lfoAudio (false, true, 67, 137.25),
            "clock loss leaves free-running LFO audio unchanged");
}
} // namespace

int main()
{
    estimatorTests();
    arpeggioTests();
    pausedReleaseTests();
    lfoTests();
    std::printf ("Tempo clock: %d checks, %d failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}

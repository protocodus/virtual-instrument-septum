// U4 parameter-extremes matrix over the plug-in processor, through the shared
// portfolio harness (Tests/ParameterMatrix.h is a byte-identical copy of the
// master; change it in reason-rack-extensions).
//
//   SeptumParameterMatrixTests [--jobs N] [--rotation] [--shard K/N]
//                              [--case LABEL] [--count]
//
// --rotation runs each case at one rate and block size instead of all nine,
// --shard runs every Nth case starting at K (1-based), --case runs only the
// case a FAIL line names (its label, e.g. "preset 4 Upper Amp Env R=1"), and
// --count only prints how many cases there are.

#include "PluginProcessor.h"
#include "ParameterMatrix.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <map>
#include <cstdlib>
#include <string>

namespace
{
using protocodus::matrix::Case;
using protocodus::matrix::Limits;

// The 32 PRESET programs; the User slots after them are INIT copies, which
// the default-patch cases already cover.
constexpr int presetCount = 32;

class SeptumDevice final : public protocodus::matrix::JuceDevice
{
public:
    SeptumDevice() : JuceDevice (std::make_unique<SeptumAudioProcessor>())
    {
        // The same automatable parameters, in the same order, as the rows.
        for (auto* parameter : processor->getParameters())
            if (parameter->isAutomatable())
                if (auto* ranged = dynamic_cast<juce::RangedAudioParameter*> (parameter))
                    columns[ranged->paramID.toStdString()] = { automatable++, ranged };
    }

    int PresetCount() const override { return presetCount; }

    Limits LimitsFor (const Case& c) const override
    {
        Limits limits;
        // The output stage's safety knee bounds every sample below this.
        limits.ceiling = static_cast<float> (septum::mapping::outputLimitKnee
                                             + septum::mapping::outputLimitRange);
        // Automation ramps between the case and its base, so each limit
        // takes whichever of the two asks more of it.
        double release = 0.0;
        bool louderRelease = false;
        for (const auto* row : { &c.values, &c.base })
        {
            release = std::max (release, tailSeconds (*row));
            louderRelease = louderRelease || releaseMayOutsoundHeld (*row);
            if (silentByDesign (*row))
                limits.soundsWhileHeld = false;
        }
        // Moving the receive channel or REMOTE KEYBOARD releases every held
        // key (the processor's stuck-note guard), so automating either one
        // cuts the case's own chord, and the held window holds only its
        // release: an echo of the cut chord may then outsound it.
        for (const char* id : { "system_midi_channel", "system_remote_keyboard" })
            if (raw (c.values, "", id) != raw (c.base, "", id))
            {
                limits.soundsWhileHeld = false;
                louderRelease = true;
            }
        // Where silence is due within a few seconds, or the release may be
        // louder than the held window (so the harness's tail-growth check
        // would not hold), the case waits for silence. Otherwise a long tail
        // only has to stay within 3 dB of the held chord, which keeps the
        // matrix's run time bounded.
        constexpr double longTailSeconds = 6.0;
        if (std::isfinite (release) && (release <= longTailSeconds || louderRelease))
            limits.releaseSeconds = release;
        else
        {
            limits.releaseSeconds = -1.0;
            // That run stops 0.5 s after note-off, still sounding. The output
            // coupling (C216/R179) integrates to tau times the charge it holds
            // at the end, so over a run this much shorter than 3 tau its mean
            // is the charging transient of whatever DC the voices carry, up to
            // the ceiling: tau * ceiling / run seconds, not a stuck offset.
            constexpr double runSeconds = 0.8 + 0.5;
            limits.dcLimit = std::max (limits.dcLimit,
                                       static_cast<float> (couplingTau * limits.ceiling / runSeconds));
        }
        return limits;
    }

private:
    struct Column { std::size_t index; juce::RangedAudioParameter* parameter; };

    // C216/R179, 22 uF into 22 kohm (Source/DSP/AnalogOutput.h).
    static constexpr double couplingTau = 22.0e-6 * 22.0e3;

    // A row's value of one parameter in its own units. A parameter the rows
    // leave out (not automatable) keeps the processor's current value.
    int raw (const std::vector<float>& row, const char* prefix, const char* suffix) const
    {
        const auto found = columns.find (std::string (prefix) + suffix);
        if (found == columns.end())
            return 0;
        const auto& column = found->second;
        const float normalised = column.index < row.size() ? row[column.index]
                                                          : column.parameter->getValue();
        return juce::roundToInt (column.parameter->convertFrom0to1 (normalised));
    }

    // Seconds from the last note-off until the output is below -60 dBFS: the
    // amp release, reverb RT60 and delay repeats (each to -60 dB) in series,
    // half as long again for a voice driven above full scale ahead of the
    // output knee, then the output coupling capacitor discharging the DC the
    // voices left on it. Infinite while a held arpeggio keeps playing.
    double tailSeconds (const std::vector<float>& row) const
    {
        using namespace septum::mapping;
        if (raw (row, "", "arp_on") != 0 && raw (row, "", "arp_hold") != 0)
            return INFINITY;
        double amp = 0.0;
        bool reverbSend = false, delaySend = false;
        for (const char* tone : { "up_", "lo_" })
        {
            amp = std::max (amp, decaySeconds (raw (row, tone, "aenv_release")));
            reverbSend = reverbSend || raw (row, tone, "reverb_depth") > 0;
            delaySend = delaySend || raw (row, tone, "delay_depth") > 0;
        }
        double tail = amp;
        if (raw (row, "", "reverb_on") != 0 && reverbSend)
            tail += reverbSeconds (raw (row, "", "reverb_time"), raw (row, "", "reverb_size"));
        if (raw (row, "", "delay_on") != 0 && delaySend)
        {
            const double feedback = std::abs (raw (row, "", "delay_feedback")) / 100.0;
            const double repeats = feedback > 0.0 ? 3.0 / std::log10 (1.0 / feedback) : 1.0;
            tail += delaySeconds (raw (row, "", "delay_time")) * repeats;
        }
        // 6.9 coupling time constants take a full-scale DC step to -60 dB.
        return 1.5 * tail + 6.9 * couplingTau + 0.5;
    }

    // The tail-growth check compares the held window (0.55-0.8 s) with the
    // last 250 ms of a run that ends while the chord still sounds, so it
    // holds only for a sound that is steady or falling. These make a release
    // louder than the held window by design: an attack longer than that
    // window, a negative filter envelope that opens the filter as it
    // releases, an LFO moving the level between the two windows, or delay
    // repeats of the chord's onset landing on a voice that has not yet decayed.
    bool releaseMayOutsoundHeld (const std::vector<float>& row) const
    {
        if (raw (row, "", "delay_on") != 0)
            for (const char* tone : { "up_", "lo_" })
                if (raw (row, tone, "delay_depth") > 0)
                    return true;
        for (const char* tone : { "up_", "lo_" })
        {
            if (septum::mapping::attackSeconds (raw (row, tone, "aenv_attack")) > 0.45
                || raw (row, tone, "fenv_depth") < 0)
                return true;
            for (const char* depth : { "lfo1_depth1", "lfo1_depth2", "lfo2_depth1", "lfo2_depth2" })
                if (raw (row, tone, depth) != 0)
                    return true;
        }
        return false;
    }

    // The matrix plays its chord (60, 64, 67) on MIDI channel 1; this is true
    // where it is not received, or no part it reaches can sound.
    bool silentByDesign (const std::vector<float>& row) const
    {
        const int receive = raw (row, "", "system_midi_channel");   // 0 = ALL
        const bool remote = raw (row, "", "system_remote_keyboard") == 1; // any channel
        if ((receive != 0 && receive != 1 && ! remote)
            || raw (row, "", "master_level") == 0 || raw (row, "", "patch_level") == 0)
            return true;
        const bool upperSounds = raw (row, "", "upper_enabled") != 0 && raw (row, "up_", "level") > 0;
        const bool lowerSounds = raw (row, "", "lower_enabled") != 0 && raw (row, "lo_", "level") > 0;
        const int split = raw (row, "", "split_point");
        switch (raw (row, "", "keyboard_mode"))
        {
            case 0: return ! (raw (row, "", "keyboard_part") == 0 ? upperSounds : lowerSounds); // SINGLE
            case 2: return ! ((67 >= split && upperSounds) || (60 < split && lowerSounds));      // SPLIT
            default: return ! (upperSounds || lowerSounds);                                     // DUAL
        }
    }

    std::size_t automatable = 0;
    std::map<std::string, Column> columns;
};
} // namespace

int main (int argc, char** argv)
{
    juce::ScopedJuceInitialiser_GUI juce;
    protocodus::matrix::Options options;
    int shard = 1, shards = 1;
    bool countOnly = false;
    std::string only;
    for (int i = 1; i < argc; ++i)
    {
        const std::string arg = argv[i];
        if (arg == "--rotation") options.everyConfiguration = false;
        else if (arg == "--count") countOnly = true;
        else if (arg == "--jobs" && i + 1 < argc) options.jobs = std::atoi (argv[++i]);
        else if (arg == "--case" && i + 1 < argc) only = argv[++i];
        else if (arg == "--shard" && i + 1 < argc
                 && std::sscanf (argv[++i], "%d/%d", &shard, &shards) == 2
                 && shards >= 1 && shard >= 1 && shard <= shards) {}
        else
        {
            std::fprintf (stderr, "usage: %s [--jobs N] [--rotation] [--shard K/N] [--case LABEL] [--count]\n", argv[0]);
            return 2;
        }
    }
    const auto make = [] { return std::make_unique<SeptumDevice>(); };
    if (countOnly)
    {
        auto probe = make();
        probe->Prepare (48000.0, 512);
        std::printf ("%zu cases\n", protocodus::matrix::Cases (*probe).size());
        return 0;
    }
    options.select = [shard, shards, only] (std::size_t index, const Case& c)
    {
        return static_cast<int> (index % static_cast<std::size_t> (shards)) == shard - 1
            && (only.empty() || c.label == only);
    };
    return protocodus::matrix::Run (make, options) == 0 ? 0 : 1;
}

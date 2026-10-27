// U9 parameter-extremes matrix over the plug-in processor, through the shared
// portfolio harness (Tests/ParameterMatrix.h is a byte-identical copy of the
// master; change it in reason-rack-extensions).
//
//   SeptumParameterMatrixTests [--jobs N] [--rotation] [--shard K/N]
//                              [--case LABEL] [--count] [--list]
//
// The shared command line (U9): --rotation runs each case at one rate and
// block size instead of all nine, --shard K/N runs the cases whose index
// modulo N is K (numbered from 0), --case runs only the case a FAIL line
// names (its label, e.g. "preset 4 Upper Amp Env R=1"), and --count and
// --list print the cases and parameters.

#include "PluginProcessor.h"
#include "ParameterMatrix.h"

#include <algorithm>
#include <cmath>
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

    // True where a tone's low-pass is held shut by its own envelope: a
    // negative FILTER ENV DEPTH at a high SUSTAIN pulls the cutoff (12 octaves
    // at full depth, more than the whole CUTOFF range) far below the chord,
    // as a real filter would. Every term that could open the filter or lower
    // the chord is taken at its extreme, so this holds only when the lowest
    // partial is still 60 dB down, plus whatever the shelf and the post-filter
    // drive can give back, on the asymptotic slope above the cutoff. Like the
    // other design silences it is judged per row, case and base alike.
    bool filterShutWhileHeld (const std::vector<float>& row, const char* tone) const
    {
        using namespace septum::mapping;
        const int depth = raw (row, tone, "fenv_depth");
        // LPF only; and the envelope must be past its attack, which starts at
        // the last note-on (0.1 s), by the held window (0.55 s).
        if (raw (row, tone, "filter_type") != 1 || depth >= 0
            || attackSeconds (raw (row, tone, "fenv_attack")) > 0.45
            || raw (row, tone, "mix_type") == 2) // RING adds difference tones
            return false;

        // Past its attack a negative envelope sits at or above SUSTAIN, so
        // its pull is at least SUSTAIN's share of the depth.
        double openOctaves = std::log2 (cutoffHz (raw (row, tone, "cutoff")))
                             + filterEnvOctaves (depth) * raw (row, tone, "fenv_sustain") / 127.0
                             + std::max (0, raw (row, tone, "key_follow")) / 100.0 * 7.0 / 12.0
                             + std::abs (cutoffVelocityOctaves (raw (row, tone, "cutoff_vel"), 0.0));
        for (const char* lfo : { "lfo1_", "lfo2_" })
            if (raw (row, tone, (std::string (lfo) + "dest1").c_str()) == 2) // FILTER
                openOctaves += std::abs (lfoFilterOctaves (raw (row, tone, (std::string (lfo) + "depth1").c_str())));
        const double heldCutoffHz = std::max (5.0, std::exp2 (openOctaves)); // the engine's floor

        // Keyboard OCT and TRANSPOSE do not reach direct MIDI, so they count
        // only where they lower the chord.
        const double shift = raw (row, "", "system_key_shift") + 12.0 * raw (row, tone, "octave_shift")
                             + std::min (0, raw (row, "", "system_transpose") + 12 * raw (row, "", "system_octave"));
        double lowestNote = INFINITY;
        const int balance = raw (row, tone, "balance");
        for (int osc = 1; osc <= 2; ++osc)
        {
            if (balanceLegGain (balance, osc == 1) <= 0.0)
                continue;
            const std::string o = "osc" + std::to_string (osc) + "_";
            const int wave = raw (row, tone, (o + "wave").c_str());
            if (wave == 5 || wave == 8) // NOISE, EXT-IN: no lowest partial
                return false;
            double note = 60.0 + shift + raw (row, tone, (o + "pitch").c_str())
                          + std::min (0, raw (row, tone, (o + "detune").c_str())) / 100.0
                          + std::min (0.0, pitchEnvSemitones (raw (row, tone, (o + "penv_depth").c_str())));
            for (const char* lfo : { "lfo1_", "lfo2_" })
                if (raw (row, tone, (std::string (lfo) + "dest" + (osc == 1 ? "1" : "2")).c_str()) == 0) // PITCH
                    note -= std::abs (lfoPitchCents (raw (row, tone, (std::string (lfo) + "depth" + (osc == 1 ? "1" : "2")).c_str()))) / 100.0;
            if (wave == 7) // SUPER-SAW: the lowest of the stack at full detune
                note += 12.0 * std::log2 (1.0 + superSawOffsets.front() * superSawDetuneAmount (1.0));
            lowestNote = std::min (lowestNote, note);
        }
        const double lowestHz = raw (row, "", "system_master_tune") * std::exp2 ((lowestNote - 69.0) / 12.0);

        const double slopeDb = raw (row, tone, "filter_slope") == 1 ? 24.0 : 12.0;
        const double neededDb = 60.0 + (raw (row, tone, "low_freq") == 1 ? lowShelfGainDb : 0.0)
                                + (1.0 + overdriveCompensationExponent)
                                      * 20.0 * std::log10 (overdrivePreGain (raw (row, tone, "drive")));
        return slopeDb * std::log2 (lowestHz / heldCutoffHz) >= neededDb;
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
        const bool upperSounds = raw (row, "", "upper_enabled") != 0 && raw (row, "up_", "level") > 0
                                 && ! filterShutWhileHeld (row, "up_");
        const bool lowerSounds = raw (row, "", "lower_enabled") != 0 && raw (row, "lo_", "level") > 0
                                 && ! filterShutWhileHeld (row, "lo_");
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
    return protocodus::matrix::Main (argc, argv, [] { return std::make_unique<SeptumDevice>(); });
}

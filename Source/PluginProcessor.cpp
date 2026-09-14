#include "PluginProcessor.h"
#include "PluginEditor.h"
#include "DSP/SeptumSysEx.h"

#include <bit>
#include <cmath>
#include <cstring>
#include <locale>
#include <sstream>
#include <thread>
#include <vector>

namespace
{
using septum::Patch;
using septum::TonePatch;

constexpr int nativePresetVersion = 6;
constexpr std::size_t maximumPresetBytes = 1024 * 1024;

// APVTS atomics are normally range checked by JUCE, but malformed host
// automation must not reach a float-to-integer conversion with NaN/Inf or
// an out-of-range operand. The documented ranges are applied afterwards.
int roundedParameter (double value) noexcept
{
    return std::isfinite (value)
        ? static_cast<int> (std::lround (std::clamp (value, -1000000.0, 1000000.0))) : 0;
}

bool isValidLiveMidi (const juce::MidiMessageMetadata& event) noexcept
{
    if (event.data == nullptr || event.numBytes <= 0 || event.data[0] < 0x80)
        return false;
    const auto status = event.data[0];
    if (status == 0xf0)
        return event.numBytes >= 2 && event.numBytes <= 79
            && event.data[event.numBytes - 1] == 0xf7;
    // Meta messages belong to MIDI files, not a live instrument callback.
    if (status >= 0xf8)
        return event.numBytes == 1;
    int expected = 1;
    if (status < 0xf0)
        expected = (status & 0xe0) == 0xc0 ? 2 : 3;
    else if (status == 0xf1 || status == 0xf3)
        expected = 2;
    else if (status == 0xf2)
        expected = 3;
    if (event.numBytes != expected)
        return false;
    for (int i = 1; i < expected; ++i)
        if (event.data[i] >= 0x80)
            return false;
    return true;
}

bool isParameterMidi (const std::uint8_t* data) noexcept
{
    const int status = data[0] & 0xf0;
    if (data[0] == 0xf0 || status == 0xc0) return true;
    if (status != 0xb0) return false;
    switch (data[1])
    {
        case 1: case 7: case 10: case 11: case 64: case 66: case 69:
        case 84: case 120: case 121: case 123: case 124: case 125:
            return false;
        default: return true;
    }
}

bool hasSafeStateXmlStructure (const void* data, int sizeInBytes) noexcept
{
    // JUCE's XML parser is recursive. Bound nesting before it sees an
    // untrusted host blob, and disallow declarations/entity definitions:
    // native state needs only a root, PARAM children and scalar attributes.
    const auto* bytes = static_cast<const char*> (data);
    int depth = 0, elements = 0;
    for (int i = 8; i < sizeInBytes; ++i)
    {
        if (bytes[i] != '<')
            continue;
        if (++i >= sizeInBytes || bytes[i] == '!')
            return false;
        const bool closing = bytes[i] == '/';
        const bool instruction = bytes[i] == '?';
        if (! closing && ! instruction && (++depth > 16 || ++elements > 4096))
            return false;
        char quote = 0;
        for (; i < sizeInBytes; ++i)
        {
            const auto character = bytes[i];
            if (quote != 0)
            {
                if (character == quote) quote = 0;
            }
            else if (character == '\'' || character == '"')
                quote = character;
            else if (character == '>')
                break;
        }
        if (i >= sizeInBytes)
            return false;
        if (closing || (! instruction && bytes[i - 1] == '/'))
            if (--depth < 0)
                return false;
    }
    return depth == 0;
}

// Version 1 predates the MIDI receiver settings. Fill only those additions;
// native preset validation must still reject missing original parameters.
void addMissingMidiSettings (juce::ValueTree& state)
{
    for (const auto& [id, value] :
         { std::pair { "system_midi_channel", 0.0f },
           std::pair { "system_receive_program", 1.0f },
           std::pair { "system_device_id", 17.0f },
           std::pair { "system_active_sensing", 1.0f } })
        if (! state.getChildWithProperty ("id", id).isValid())
        {
            juce::ValueTree parameterState ("PARAM");
            parameterState.setProperty ("id", id, nullptr);
            parameterState.setProperty ("value", value, nullptr);
            state.addChild (parameterState, -1, nullptr);
        }
}

void addMissingRemainSettings (juce::ValueTree& state)
{
    if (! state.getChildWithProperty ("id", "system_patch_remain").isValid())
    {
        juce::ValueTree setting ("PARAM");
        setting.setProperty ("id", "system_patch_remain", nullptr);
        setting.setProperty ("value", 0.0f, nullptr);
        state.addChild (setting, -1, nullptr);
    }
}

void addMissingRemoteSettings (juce::ValueTree& state)
{
    if (! state.getChildWithProperty ("id", "system_remote_keyboard").isValid())
    {
        juce::ValueTree setting ("PARAM");
        setting.setProperty ("id", "system_remote_keyboard", nullptr);
        setting.setProperty ("value", 2.0f, nullptr);
        state.addChild (setting, -1, nullptr);
    }
}

void addMissingBankSettings (juce::ValueTree& state)
{
    if (! state.getChildWithProperty ("id", "system_receive_bank").isValid())
    {
        juce::ValueTree setting ("PARAM");
        setting.setProperty ("id", "system_receive_bank", nullptr);
        setting.setProperty ("value", 1.0f, nullptr);
        state.addChild (setting, -1, nullptr);
    }
}

void addMissingTempoSettings (juce::ValueTree& state)
{
    for (const auto& [id, value] :
         { std::pair { "system_clock_source", 0.0f },
           std::pair { "system_tempo", 120.0f } })
        if (! state.getChildWithProperty ("id", id).isValid())
        {
            juce::ValueTree parameterState ("PARAM");
            parameterState.setProperty ("id", id, nullptr);
            parameterState.setProperty ("value", value, nullptr);
            state.addChild (parameterState, -1, nullptr);
        }
}

bool readPresetNumber (const juce::var& stored, double& value)
{
    const auto text = stored.toString().trim();
    if (text.isEmpty())
        return false;
    std::istringstream parser (text.toStdString());
    parser.imbue (std::locale::classic());
    parser >> std::noskipws >> value;
    return ! parser.fail() && parser.eof() && std::isfinite (value);
}

// ---------------------------------------------------------------------------
// One binding per parameter: the same list drives layout creation, patch
// snapshots and program loading, so the three can never disagree.
// ---------------------------------------------------------------------------

enum class Kind { Int, Bool, Choice };

struct ToneBinding
{
    const char* suffix;
    const char* label;
    Kind kind;
    int low, high;           // Int range, or choice count in `high`
    const juce::StringArray* choices;
    float (*get) (const TonePatch&);
    void (*set) (TonePatch&, float);
    // The same rule PatchBinding states for the D Beam's four bytes, applied
    // to the two PITCH WIDE switches: settled patch data the replica stores,
    // saves and round-trips but never reads, published as non-automatable so a
    // host does not offer a player a lane that cannot change what they hear.
    // The manual gives PITCH WIDE as expanding the COARSE *knob's travel*, and
    // a numeric parameter that already reaches +/-36 has no travel to expand.
    bool inert { false };
};

const juce::StringArray waveChoices {
    "SAW", "SQU", "PW-SQU", "TRI", "SINE", "NOISE", "FB-OSC", "SUPER-SAW",
    "EXT-IN"
};
const juce::StringArray mixTypeChoices { "MIX", "SYNC", "RING" };
const juce::StringArray lowFreqChoices { "FLAT", "BOOST", "CUT" };
const juce::StringArray filterTypeChoices { "BYPASS", "LPF", "HPF", "BPF" };
const juce::StringArray slopeChoices { "-12 dB", "-24 dB" };
const juce::StringArray lfoShapeChoices { "TRI", "SIN", "SAW", "SQR", "TRP",
                                          "S&H", "RND" };
const juce::StringArray lfoDest1Choices { "PITCH1", "PW1", "FILTER", "AUDIO-F" };
const juce::StringArray lfoDest2Choices { "PITCH2", "PW2", "AMP" };
const juce::StringArray monoChoices { "POLY", "SOLO+LEGATO", "SOLO" };
const juce::StringArray syncNoteChoices {
    "16", "12", "8", "4", "2", "1", "3/4", "2/3", "1/2", "3/8", "1/3", "1/4",
    "3/16", "1/6", "1/8", "3/32", "1/12", "1/16", "1/24", "1/32"
};
const juce::StringArray arpGridChoices { "1/4", "1/8", "1/8L", "1/8H", "1/12",
                                         "1/16", "1/16L", "1/16H", "1/24" };
const juce::StringArray arpDurationChoices { "30%", "40%", "50%", "60%", "70%",
                                             "80%", "90%", "100%", "120%", "FUL" };
const juce::StringArray arpMotifChoices {
    "UP(L)", "UP(L&H)", "UP(-)", "DOWN(L)", "DOWN(L&H)", "DOWN(-)",
    "UP&DN(L)", "UP&DN(L&H)", "UP&DN(-)", "RAND(L)", "RAND(-)", "PHRASE"
};
const juce::StringArray arpSplitChoices { "UPPER", "LOWER", "BOTH" };
// CONTROLLER DESTINATION, the same three for every controller (OM p. 65).
const juce::StringArray toneDestinationChoices { "UPPER", "LOWER", "BOTH" };
// D BEAM: the polarity and the 37-entry assign list in the address map's own
// order (Patch Common 00 20 and 00 1F). The replica does not implement the
// beam; these name the values of two bytes it stores so a SysEx round trip
// stays lossless.
const juce::StringArray dBeamPolarityChoices { "+", "-" };
const juce::StringArray dBeamAssignChoices {
    "OSC1-PITCH", "OSC1-DETUNE", "OSC1-PW",
    "OSC2-PITCH", "OSC2-DETUNE", "OSC2-PW",
    "MIX/MOD-BALANCE",
    "FILTER-CUTOFF", "FILTER-RESONANCE", "FILTER-CUTOFF-KEYFOLLOW", "AMP-LEVEL",
    "AUDIO-FILTER-CUTOFF", "AUDIO-FILTER-RESONANCE",
    "PITCH-ENV-A", "PITCH-ENV-D",
    "OSC1-PITCH-ENV-DEPTH", "OSC2-PITCH-ENV-DEPTH",
    "LFO1-RATE", "LFO1-DEPTH1", "LFO1-DEPTH2",
    "LFO2-RATE", "LFO2-DEPTH1", "LFO2-DEPTH2",
    "FILTER-ENV-A", "FILTER-ENV-D", "FILTER-ENV-S", "FILTER-ENV-R",
    "FILTER-ENV-DEPTH",
    "AMP-ENV-A", "AMP-ENV-D", "AMP-ENV-S", "AMP-ENV-R",
    "EFFECTS-DELAY-TIME", "EFFECTS-DELAY-DEPTH",
    "EFFECTS-REVERB-TIME", "EFFECTS-REVERB-DEPTH",
    "BENDER"
};

const juce::StringArray& arpStyleChoices()
{
    static const juce::StringArray names = []
    {
        juce::StringArray list;
        for (const auto& entry : septum::arpeggioStyles())
            list.add (entry.name);
        return list;
    }();
    return names;
}

const juce::StringArray keyboardModeChoices { "SINGLE", "DUAL", "SPLIT" };
const juce::StringArray keyboardPartChoices { "UPPER", "LOWER" };
const juce::StringArray modAssignChoices { "OSC1&OSC2", "OSC1", "OSC2", "PW1",
                                           "PW2", "FILTER", "AMP", "AUDIO-FIL" };
const juce::StringArray delayHfDampChoices {
    "200 Hz", "250 Hz", "315 Hz", "400 Hz", "500 Hz", "630 Hz", "800 Hz",
    "1000 Hz", "1250 Hz", "1600 Hz", "2000 Hz", "2500 Hz", "3150 Hz",
    "4000 Hz", "5000 Hz", "6300 Hz", "8000 Hz", "BYPASS"
};
const juce::StringArray reverbHighCutChoices {
    "160 Hz", "200 Hz", "250 Hz", "320 Hz", "400 Hz", "500 Hz", "640 Hz",
    "800 Hz", "1000 Hz", "1250 Hz", "1600 Hz", "2000 Hz", "2500 Hz",
    "3200 Hz", "4000 Hz", "5000 Hz", "6400 Hz", "8000 Hz", "10000 Hz",
    "12500 Hz", "BYPASS"
};
const juce::StringArray reverbLfDampChoices {
    "50 Hz", "64 Hz", "80 Hz", "100 Hz", "125 Hz", "160 Hz", "200 Hz",
    "250 Hz", "320 Hz", "400 Hz", "500 Hz", "640 Hz", "800 Hz", "1000 Hz",
    "1250 Hz", "1600 Hz", "2000 Hz", "2500 Hz", "3200 Hz", "4000 Hz"
};
const juce::StringArray reverbHfDampChoices {
    "4000 Hz", "5000 Hz", "6400 Hz", "8000 Hz", "10000 Hz", "12500 Hz"
};

// Shorthand for the field accessors.
#define TONE_INT(field) \
    [] (const TonePatch& t) { return (float) t.field; }, \
    [] (TonePatch& t, float v) { t.field = (int) roundedParameter (v); }
#define TONE_BOOL(field) \
    [] (const TonePatch& t) { return t.field ? 1.0f : 0.0f; }, \
    [] (TonePatch& t, float v) { t.field = v >= 0.5f; }
#define TONE_ENUM(field, type) \
    [] (const TonePatch& t) { return (float) (int) t.field; }, \
    [] (TonePatch& t, float v) { t.field = (type) (int) roundedParameter (v); }

const std::vector<ToneBinding>& toneBindings()
{
    using septum::FilterSlope;
    using septum::FilterType;
    using septum::LfoDest1;
    using septum::LfoDest2;
    using septum::LfoShape;
    using septum::LowFreqMode;
    using septum::MixModType;
    using septum::MonoMode;
    using septum::Waveform;

    static const std::vector<ToneBinding> bindings {
        { "osc1_wave", "OSC1 Wave", Kind::Choice, 0, 9, &waveChoices,
          TONE_ENUM (osc1.wave, Waveform) },
        { "osc1_wide", "OSC1 Pitch Wide", Kind::Bool, 0, 1, nullptr,
          TONE_BOOL (osc1.pitchWide), true },
        { "osc1_pitch", "OSC1 Pitch", Kind::Int, -36, 36, nullptr,
          TONE_INT (osc1.coarse) },
        { "osc1_detune", "OSC1 Detune", Kind::Int, -50, 50, nullptr,
          TONE_INT (osc1.fine) },
        { "osc1_pw", "OSC1 PW/Feedback", Kind::Int, 0, 127, nullptr,
          TONE_INT (osc1.pulseWidth) },
        { "osc1_penv_depth", "OSC1 Pitch Env Depth", Kind::Int, -63, 63, nullptr,
          TONE_INT (osc1.pitchEnvDepth) },
        { "osc2_wave", "OSC2 Wave", Kind::Choice, 0, 9, &waveChoices,
          TONE_ENUM (osc2.wave, Waveform) },
        { "osc2_wide", "OSC2 Pitch Wide", Kind::Bool, 0, 1, nullptr,
          TONE_BOOL (osc2.pitchWide), true },
        { "osc2_pitch", "OSC2 Pitch", Kind::Int, -36, 36, nullptr,
          TONE_INT (osc2.coarse) },
        { "osc2_detune", "OSC2 Detune", Kind::Int, -50, 50, nullptr,
          TONE_INT (osc2.fine) },
        { "osc2_pw", "OSC2 PW/Feedback", Kind::Int, 0, 127, nullptr,
          TONE_INT (osc2.pulseWidth) },
        { "osc2_penv_depth", "OSC2 Pitch Env Depth", Kind::Int, -63, 63, nullptr,
          TONE_INT (osc2.pitchEnvDepth) },
        { "penv_attack", "Pitch Env A", Kind::Int, 0, 127, nullptr,
          TONE_INT (pitchEnvAttack) },
        { "penv_decay", "Pitch Env D", Kind::Int, 0, 127, nullptr,
          TONE_INT (pitchEnvDecay) },
        { "mix_type", "Mix/Mod Type", Kind::Choice, 0, 3, &mixTypeChoices,
          TONE_ENUM (mixType, MixModType) },
        { "balance", "Balance", Kind::Int, -63, 63, nullptr, TONE_INT (balance) },
        { "low_freq", "Low Freq", Kind::Choice, 0, 3, &lowFreqChoices,
          TONE_ENUM (lowFreq, LowFreqMode) },
        { "filter_type", "Filter Type", Kind::Choice, 0, 4, &filterTypeChoices,
          TONE_ENUM (filterType, FilterType) },
        { "filter_slope", "Filter Slope", Kind::Choice, 0, 2, &slopeChoices,
          TONE_ENUM (filterSlope, FilterSlope) },
        { "cutoff", "Cutoff", Kind::Int, 0, 127, nullptr, TONE_INT (cutoff) },
        { "key_follow", "Key Follow", Kind::Int, -200, 200, nullptr,
          TONE_INT (keyFollow) },
        { "cutoff_vel", "Cutoff Velocity Sens", Kind::Int, -63, 63, nullptr,
          TONE_INT (cutoffVelocitySens) },
        { "resonance", "Resonance", Kind::Int, 0, 127, nullptr,
          TONE_INT (resonance) },
        { "fenv_attack", "Filter Env A", Kind::Int, 0, 127, nullptr,
          TONE_INT (filterEnvAttack) },
        { "fenv_decay", "Filter Env D", Kind::Int, 0, 127, nullptr,
          TONE_INT (filterEnvDecay) },
        { "fenv_sustain", "Filter Env S", Kind::Int, 0, 127, nullptr,
          TONE_INT (filterEnvSustain) },
        { "fenv_release", "Filter Env R", Kind::Int, 0, 127, nullptr,
          TONE_INT (filterEnvRelease) },
        { "fenv_depth", "Filter Env Depth", Kind::Int, -63, 63, nullptr,
          TONE_INT (filterEnvDepth) },
        { "overdrive", "Overdrive", Kind::Bool, 0, 1, nullptr,
          TONE_BOOL (overdrive) },
        { "drive", "Drive", Kind::Int, 0, 127, nullptr, TONE_INT (drive) },
        { "level", "Level", Kind::Int, 0, 127, nullptr, TONE_INT (level) },
        { "level_vel", "Level Velocity Sens", Kind::Int, -63, 63, nullptr,
          TONE_INT (levelVelocitySens) },
        { "pan", "Pan", Kind::Int, -64, 63, nullptr, TONE_INT (pan) },
        { "aenv_attack", "Amp Env A", Kind::Int, 0, 127, nullptr,
          TONE_INT (ampEnvAttack) },
        { "aenv_decay", "Amp Env D", Kind::Int, 0, 127, nullptr,
          TONE_INT (ampEnvDecay) },
        { "aenv_sustain", "Amp Env S", Kind::Int, 0, 127, nullptr,
          TONE_INT (ampEnvSustain) },
        { "aenv_release", "Amp Env R", Kind::Int, 0, 127, nullptr,
          TONE_INT (ampEnvRelease) },
        { "delay_depth", "Delay Depth", Kind::Int, 0, 127, nullptr,
          TONE_INT (delayDepth) },
        { "reverb_depth", "Reverb Depth", Kind::Int, 0, 127, nullptr,
          TONE_INT (reverbDepth) },
        { "lfo1_shape", "LFO1 Shape", Kind::Choice, 0, 7, &lfoShapeChoices,
          TONE_ENUM (lfo1.shape, LfoShape) },
        { "lfo1_rate", "LFO1 Rate", Kind::Int, 0, 127, nullptr,
          TONE_INT (lfo1.rate) },
        { "lfo1_sync", "LFO1 Tempo Sync", Kind::Bool, 0, 1, nullptr,
          TONE_BOOL (lfo1.tempoSync) },
        { "lfo1_sync_note", "LFO1 Sync Note", Kind::Choice, 0, 20,
          &syncNoteChoices, TONE_INT (lfo1.tempoSyncNote) },
        { "lfo1_fade", "LFO1 Fade Time", Kind::Int, 0, 127, nullptr,
          TONE_INT (lfo1.fadeTime) },
        { "lfo1_key_trig", "LFO1 Key Trigger", Kind::Bool, 0, 1, nullptr,
          TONE_BOOL (lfo1.keyTrigger) },
        { "lfo1_dest1", "LFO1 Destination 1", Kind::Choice, 0, 4,
          &lfoDest1Choices, TONE_ENUM (lfo1.destination1, LfoDest1) },
        { "lfo1_depth1", "LFO1 Depth 1", Kind::Int, -63, 63, nullptr,
          TONE_INT (lfo1.depth1) },
        { "lfo1_dest2", "LFO1 Destination 2", Kind::Choice, 0, 3,
          &lfoDest2Choices, TONE_ENUM (lfo1.destination2, LfoDest2) },
        { "lfo1_depth2", "LFO1 Depth 2", Kind::Int, -63, 63, nullptr,
          TONE_INT (lfo1.depth2) },
        { "lfo2_shape", "LFO2 Shape", Kind::Choice, 0, 7, &lfoShapeChoices,
          TONE_ENUM (lfo2.shape, LfoShape) },
        { "lfo2_rate", "LFO2 Rate", Kind::Int, 0, 127, nullptr,
          TONE_INT (lfo2.rate) },
        { "lfo2_sync", "LFO2 Tempo Sync", Kind::Bool, 0, 1, nullptr,
          TONE_BOOL (lfo2.tempoSync) },
        { "lfo2_sync_note", "LFO2 Sync Note", Kind::Choice, 0, 20,
          &syncNoteChoices, TONE_INT (lfo2.tempoSyncNote) },
        { "lfo2_fade", "LFO2 Fade Time", Kind::Int, 0, 127, nullptr,
          TONE_INT (lfo2.fadeTime) },
        { "lfo2_key_trig", "LFO2 Key Trigger", Kind::Bool, 0, 1, nullptr,
          TONE_BOOL (lfo2.keyTrigger) },
        { "lfo2_dest1", "LFO2 Destination 1", Kind::Choice, 0, 4,
          &lfoDest1Choices, TONE_ENUM (lfo2.destination1, LfoDest1) },
        { "lfo2_depth1", "LFO2 Depth 1", Kind::Int, -63, 63, nullptr,
          TONE_INT (lfo2.depth1) },
        { "lfo2_dest2", "LFO2 Destination 2", Kind::Choice, 0, 3,
          &lfoDest2Choices, TONE_ENUM (lfo2.destination2, LfoDest2) },
        { "lfo2_depth2", "LFO2 Depth 2", Kind::Int, -63, 63, nullptr,
          TONE_INT (lfo2.depth2) },
        { "bend_range", "Pitch Bend Range", Kind::Int, 0, 24, nullptr,
          TONE_INT (bendRange) },
        { "octave_shift", "Octave Shift", Kind::Int, -3, 3, nullptr,
          TONE_INT (octaveShift) },
        { "portamento", "Portamento", Kind::Bool, 0, 1, nullptr,
          TONE_BOOL (portamento) },
        { "porta_time", "Portamento Time", Kind::Int, 0, 127, nullptr,
          TONE_INT (portamentoTime) },
        { "mono_mode", "Poly/Solo", Kind::Choice, 0, 3, &monoChoices,
          TONE_ENUM (mono, MonoMode) },
    };
    return bindings;
}

struct PatchBinding
{
    const char* id;
    const char* label;
    Kind kind;
    int low, high;
    const juce::StringArray* choices;
    float (*get) (const Patch&);
    void (*set) (Patch&, float);
    // Settled patch data the replica stores but never reads: the four bytes
    // the D Beam owns. They are saved, loaded and round-tripped through
    // SysEx so a dump from a real unit survives the trip, and they are
    // published as non-automatable so a host does not offer a player an
    // automation lane that cannot change what they hear.
    bool inert { false };
};

// The external-input path is a system setting, not patch data (OM pp. 49-51),
// so it gets its own binding table: these parameters live in the plug-in's
// state and are automatable, but a program change must not touch them.
struct ExternalBinding
{
    const char* id;
    const char* label;
    Kind kind;
    int low, high;
    const juce::StringArray* choices;
    float (*get) (const septum::ExternalInput&);
    void (*set) (septum::ExternalInput&, float);
};

const juce::StringArray audioFilterTypeChoices { "LPF", "HPF", "BPF", "NOTCH" };

#define EXT_INT(field) \
    [] (const septum::ExternalInput& e) { return (float) e.field; }, \
    [] (septum::ExternalInput& e, float v) { e.field = (int) roundedParameter (v); }
#define EXT_BOOL(field) \
    [] (const septum::ExternalInput& e) { return e.field ? 1.0f : 0.0f; }, \
    [] (septum::ExternalInput& e, float v) { e.field = v >= 0.5f; }
#define EXT_ENUM(field, type) \
    [] (const septum::ExternalInput& e) { return (float) (int) e.field; }, \
    [] (septum::ExternalInput& e, float v) { e.field = (type) (int) roundedParameter (v); }

const std::vector<ExternalBinding>& externalBindings()
{
    using septum::AudioFilterType;
    using septum::FilterSlope;
    static const std::vector<ExternalBinding> bindings {
        { "ext_input_vol", "External Input Volume", Kind::Int, 0, 127, nullptr,
          EXT_INT (inputVolume) },
        { "ext_center_cancel", "Center Cancel", Kind::Bool, 0, 1, nullptr,
          EXT_BOOL (centerCancel) },
        { "audio_filter_on", "Audio Filter Switch", Kind::Bool, 0, 1, nullptr,
          EXT_BOOL (filterOn) },
        { "audio_filter_type", "Audio Filter Type", Kind::Choice, 0, 4,
          &audioFilterTypeChoices, EXT_ENUM (type, AudioFilterType) },
        { "audio_filter_slope", "Audio Filter Slope", Kind::Choice, 0, 2,
          &slopeChoices, EXT_ENUM (slope, FilterSlope) },
        { "audio_filter_cutoff", "Audio Filter Cutoff", Kind::Int, 0, 127,
          nullptr, EXT_INT (cutoff) },
        { "audio_filter_reso", "Audio Filter Resonance", Kind::Int, 0, 127,
          nullptr, EXT_INT (resonance) },
    };
    return bindings;
}

// SYSTEM COMMON (settled, OM p. 68 and the address map's System Common
// block): settings that apply to the whole instrument and, like the
// external-input block, are not patch data — a program change must not touch
// them. MASTER TUNE is the only float the plug-in publishes: the address map
// stores it in 0.1-cent steps and the manual prints it as the frequency of
// A4, 415.30-466.20 Hz.
const juce::StringArray& systemParameterIds()
{
    static const juce::StringArray ids { "system_key_shift", "system_octave",
                                         "system_transpose" };
    return ids;
}

#define PATCH_INT(field) \
    [] (const Patch& p) { return (float) p.field; }, \
    [] (Patch& p, float v) { p.field = (int) roundedParameter (v); }
#define PATCH_BOOL(field) \
    [] (const Patch& p) { return p.field ? 1.0f : 0.0f; }, \
    [] (Patch& p, float v) { p.field = v >= 0.5f; }
#define PATCH_ENUM(field, type) \
    [] (const Patch& p) { return (float) (int) p.field; }, \
    [] (Patch& p, float v) { p.field = (type) (int) roundedParameter (v); }

const std::vector<PatchBinding>& patchBindings()
{
    using septum::KeyboardMode;
    using septum::KeyboardPart;
    using septum::ModulationAssign;

    static const std::vector<PatchBinding> bindings {
        { "patch_level", "Patch Level", Kind::Int, 0, 127, nullptr,
          PATCH_INT (patchLevel) },
        { "tone_balance", "Tone Balance", Kind::Int, -63, 63, nullptr,
          PATCH_INT (toneBalance) },
        { "patch_tempo", "Patch Tempo", Kind::Int, 5, 300, nullptr,
          PATCH_INT (tempo) },
        { "keyboard_mode", "Keyboard Mode", Kind::Choice, 0, 3,
          &keyboardModeChoices, PATCH_ENUM (keyboardMode, KeyboardMode) },
        { "keyboard_part", "Keyboard Part", Kind::Choice, 0, 2,
          &keyboardPartChoices, PATCH_ENUM (keyboardPart, KeyboardPart) },
        { "split_point", "Split Point", Kind::Int, 21, 108, nullptr,
          PATCH_INT (splitPoint) },
        { "delay_on", "Delay Switch", Kind::Bool, 0, 1, nullptr,
          PATCH_BOOL (delayOn) },
        { "reverb_on", "Reverb Switch", Kind::Bool, 0, 1, nullptr,
          PATCH_BOOL (reverbOn) },
        { "mod_assign", "Modulation Assign", Kind::Choice, 0, 8,
          &modAssignChoices, PATCH_ENUM (modulationAssign, ModulationAssign) },
        { "mod_dest", "Modulation Destination", Kind::Choice, 0, 3,
          &toneDestinationChoices,
          PATCH_ENUM (modulationDestination, septum::ToneDestination) },
        { "bend_dest", "Pitch Bend Destination", Kind::Choice, 0, 3,
          &toneDestinationChoices,
          PATCH_ENUM (pitchBendDestination, septum::ToneDestination) },
        { "expr_dest", "Expression Destination", Kind::Choice, 0, 3,
          &toneDestinationChoices,
          PATCH_ENUM (expressionDestination, septum::ToneDestination) },
        // The four D Beam bytes. Stored and inert — see PatchBinding::inert.
        { "dbeam_dest", "D Beam Destination (stored, no controller)",
          Kind::Choice, 0, 3, &toneDestinationChoices,
          PATCH_ENUM (dBeamDestination, septum::ToneDestination), true },
        { "dbeam_assign", "D Beam Assign (stored, no controller)", Kind::Choice,
          0, septum::dBeamAssignCount, &dBeamAssignChoices,
          PATCH_ENUM (dBeamAssign, septum::DBeamAssign), true },
        { "dbeam_polarity", "D Beam Polarity (stored, no controller)",
          Kind::Choice, 0, 2, &dBeamPolarityChoices,
          PATCH_ENUM (dBeamPolarity, septum::DBeamPolarity), true },
        { "active_expression", "Active Expression (stored, no controller)",
          Kind::Bool, 0, 1, nullptr, PATCH_BOOL (activeExpression), true },
        { "arp_on", "Arpeggio Switch", Kind::Bool, 0, 1, nullptr,
          PATCH_BOOL (arpeggio.on) },
        { "arp_hold", "Arpeggio Hold", Kind::Bool, 0, 1, nullptr,
          PATCH_BOOL (arpeggio.hold) },
        { "arp_style", "Arpeggio Style", Kind::Choice, 0,
          (int) septum::arpeggioStyles().size(), &arpStyleChoices(),
          PATCH_INT (arpeggio.styleIndex) },
        { "arp_end_step", "Arpeggio End Step", Kind::Int, 0, 32, nullptr,
          PATCH_INT (arpeggio.endStep) },
        { "arp_grid", "Arpeggio Grid", Kind::Choice, 0, 9, &arpGridChoices,
          PATCH_ENUM (arpeggio.grid, septum::ArpeggioGrid) },
        { "arp_duration", "Arpeggio Duration", Kind::Choice, 0, 10,
          &arpDurationChoices,
          PATCH_ENUM (arpeggio.duration, septum::ArpeggioDuration) },
        { "arp_motif", "Arpeggio Motif", Kind::Choice, 0, 12, &arpMotifChoices,
          PATCH_ENUM (arpeggio.motif, septum::ArpeggioMotif) },
        { "arp_octave", "Arpeggio Octave Range", Kind::Int, -3, 3, nullptr,
          PATCH_INT (arpeggio.octaveRange) },
        { "arp_accent", "Arpeggio Accent", Kind::Int, 0, 100, nullptr,
          PATCH_INT (arpeggio.accent) },
        { "arp_velocity", "Arpeggio Velocity", Kind::Int, 0, 127, nullptr,
          PATCH_INT (arpeggio.velocity) },
        { "arp_split", "Split Arpeggio", Kind::Choice, 0, 3, &arpSplitChoices,
          PATCH_ENUM (arpeggio.splitArpeggio, septum::SplitArpeggio) },
        { "delay_time", "Delay Time", Kind::Int, 0, 127, nullptr,
          PATCH_INT (delay.time) },
        { "delay_feedback", "Delay Feedback", Kind::Int, -98, 98, nullptr,
          PATCH_INT (delay.feedback) },
        { "delay_hf_damp", "Delay HF Damp", Kind::Choice, 0, 18,
          &delayHfDampChoices, PATCH_INT (delay.hfDamp) },
        { "delay_mod_rate", "Delay Mod Rate", Kind::Int, 0, 127, nullptr,
          PATCH_INT (delay.modulationRate) },
        { "delay_mod_depth", "Delay Mod Depth", Kind::Int, 0, 127, nullptr,
          PATCH_INT (delay.modulationDepth) },
        { "reverb_time", "Reverb Time", Kind::Int, 0, 127, nullptr,
          PATCH_INT (reverb.time) },
        { "reverb_pre_delay", "Reverb Pre Delay", Kind::Int, 0, 125, nullptr,
          PATCH_INT (reverb.preDelay) },
        { "reverb_size", "Reverb Size", Kind::Int, 0, 7, nullptr,
          PATCH_INT (reverb.size) },
        { "reverb_high_cut", "Reverb High Cut", Kind::Choice, 0, 21,
          &reverbHighCutChoices, PATCH_INT (reverb.highCut) },
        { "reverb_density", "Reverb Density", Kind::Int, 0, 127, nullptr,
          PATCH_INT (reverb.density) },
        { "reverb_diffusion", "Reverb Diffusion", Kind::Int, 0, 127, nullptr,
          PATCH_INT (reverb.diffusion) },
        { "reverb_lf_damp_freq", "Reverb LF Damp Freq", Kind::Choice, 0, 20,
          &reverbLfDampChoices, PATCH_INT (reverb.lfDampFrequency) },
        { "reverb_lf_damp_gain", "Reverb LF Damp Gain", Kind::Int, -36, 0,
          nullptr, PATCH_INT (reverb.lfDampGain) },
        { "reverb_hf_damp_freq", "Reverb HF Damp Freq", Kind::Choice, 0, 6,
          &reverbHfDampChoices, PATCH_INT (reverb.hfDampFrequency) },
        { "reverb_hf_damp_gain", "Reverb HF Damp Gain", Kind::Int, -36, 0,
          nullptr, PATCH_INT (reverb.hfDampGain) },
        { "master_level", "Master Level", Kind::Int, 0, 127, nullptr,
          [] (const Patch&) { return 127.0f; }, [] (Patch&, float) {} },
    };
    return bindings;
}

// The documented control-change map (Owner's Manual p.72). CC#83 stands in
// for the printed CC#88 collision on UPPER filter-env decay (see the research
// contract's OQ-02).
struct CcBinding
{
    int controller;
    bool upper;
    const char* suffix;
    bool signedValue;  // CC 0-127 arrives as value-64 for -63..+63 displays
};

constexpr CcBinding ccBindings[] {
    { 20, true, "osc1_pitch", true },   { 76, true, "osc1_detune", true },
    { 3, true, "osc1_pw", false },      { 24, true, "osc1_penv_depth", true },
    { 21, true, "osc2_pitch", true },   { 77, true, "osc2_detune", true },
    { 95, true, "osc2_pw", false },     { 25, true, "osc2_penv_depth", true },
    { 26, true, "penv_attack", false }, { 27, true, "penv_decay", false },
    { 8, true, "balance", true },       { 74, true, "cutoff", false },
    { 30, true, "key_follow", true },   { 71, true, "resonance", false },
    { 82, true, "fenv_attack", false }, { 83, true, "fenv_decay", false },
    { 28, true, "fenv_sustain", false },{ 29, true, "fenv_release", false },
    { 81, true, "fenv_depth", true },   { 14, true, "level", false },
    { 73, true, "aenv_attack", false }, { 75, true, "aenv_decay", false },
    { 31, true, "aenv_sustain", false },{ 72, true, "aenv_release", false },
    { 93, true, "delay_depth", false }, { 91, true, "reverb_depth", false },
    { 16, true, "lfo1_rate", false },   { 18, true, "lfo1_depth1", true },
    { 19, true, "lfo1_depth2", true },  { 17, true, "lfo2_rate", false },
    { 22, true, "lfo2_depth1", true },  { 23, true, "lfo2_depth2", true },
    { 78, false, "osc1_pitch", true },  { 79, false, "osc1_detune", true },
    { 80, false, "osc1_pw", false },    { 70, false, "osc1_penv_depth", true },
    { 85, false, "osc2_pitch", true },  { 86, false, "osc2_detune", true },
    { 87, false, "osc2_pw", false },    { 88, false, "osc2_penv_depth", true },
    { 89, false, "penv_attack", false },{ 90, false, "penv_decay", false },
    { 9, false, "balance", true },      { 102, false, "cutoff", false },
    { 103, false, "key_follow", true }, { 104, false, "resonance", false },
    { 105, false, "fenv_attack", false }, { 106, false, "fenv_decay", false },
    { 107, false, "fenv_sustain", false }, { 108, false, "fenv_release", false },
    { 109, false, "fenv_depth", true }, { 15, false, "level", false },
    { 110, false, "aenv_attack", false }, { 111, false, "aenv_decay", false },
    { 112, false, "aenv_sustain", false }, { 113, false, "aenv_release", false },
    { 94, false, "delay_depth", false }, { 92, false, "reverb_depth", false },
    { 114, false, "lfo1_rate", false }, { 115, false, "lfo1_depth1", true },
    { 116, false, "lfo1_depth2", true },{ 117, false, "lfo2_rate", false },
    { 118, false, "lfo2_depth1", true },{ 119, false, "lfo2_depth2", true },
};
} // namespace

// ---------------------------------------------------------------------------

SeptumAudioProcessor::SeptumAudioProcessor()
    // The modelled instrument has stereo INPUT jacks feeding the AUDIO FILTER
    // and the EXT-IN oscillator waveform, so the plug-in declares a stereo
    // input bus. It is off by default: a host that gives a synthesizer no
    // input still loads exactly as before, and the engine then behaves like
    // the hardware with nothing plugged in.
    : AudioProcessor (BusesProperties()
                          .withOutput ("Output", juce::AudioChannelSet::stereo(),
                                       true)
                          .withInput ("External In",
                                      juce::AudioChannelSet::stereo(), false)),
      parameters (*this, nullptr, "Septum", createParameterLayout())
{
    cacheParameterPointers();
    reconciliationState = std::make_shared<ReconciliationState> (*this);
    new ReconciliationTimer (reconciliationState);
}

SeptumAudioProcessor::~SeptumAudioProcessor()
{
    const juce::ScopedLock guard (reconciliationState->lock);
    reconciliationState->owner = nullptr;
}

void SeptumAudioProcessor::cacheParameterPointers()
{
    for (const bool upper : { true, false })
    {
        auto& values = upper ? upperValues : lowerValues;
        const juce::String prefix = upper ? "up_" : "lo_";
        for (const auto& binding : toneBindings())
        {
            auto* value = parameters.getRawParameterValue (prefix + binding.suffix);
            jassert (value != nullptr);
            values.push_back (value);
        }
    }
    for (const auto& binding : patchBindings())
    {
        auto* value = parameters.getRawParameterValue (binding.id);
        jassert (value != nullptr);
        patchValues.push_back (value);
    }
    partEnableValues[0] = parameters.getRawParameterValue ("upper_enabled");
    partEnableValues[1] = parameters.getRawParameterValue ("lower_enabled");
    masterValue = parameters.getRawParameterValue ("master_level");
    systemTuneValue = parameters.getRawParameterValue ("system_master_tune");
    midiChannelValue = parameters.getRawParameterValue ("system_midi_channel");
    receiveProgramValue = parameters.getRawParameterValue ("system_receive_program");
    receiveBankValue = parameters.getRawParameterValue ("system_receive_bank");
    remoteKeyboardValue = parameters.getRawParameterValue ("system_remote_keyboard");
    patchRemainValue = parameters.getRawParameterValue ("system_patch_remain");
    deviceIdValue = parameters.getRawParameterValue ("system_device_id");
    activeSensingValue = parameters.getRawParameterValue ("system_active_sensing");
    clockSourceValue = parameters.getRawParameterValue ("system_clock_source");
    systemTempoValue = parameters.getRawParameterValue ("system_tempo");
    for (const auto& id : systemParameterIds())
        systemValues.push_back (parameters.getRawParameterValue (id));
    // The three parameters Universal Realtime device control names, resolved
    // once so the audio thread never looks one up by string.
    {
        const char* const ids[deviceControlCount] { "master_level",
                                                    "system_master_tune",
                                                    "system_key_shift" };
        for (std::size_t i = 0; i < deviceControlCount; ++i)
        {
            deviceControlParameters[i] = parameters.getParameter (ids[i]);
            deviceControlValues[i] = parameters.getRawParameterValue (ids[i]);
            jassert (deviceControlParameters[i] != nullptr);
            jassert (deviceControlValues[i] != nullptr);
            if (deviceControlValues[i] != nullptr)
                deviceControlShadow[i].store (
                    deviceControlValues[i]->load (std::memory_order_relaxed),
                    std::memory_order_relaxed);
        }
    }
    for (const auto& binding : externalBindings())
    {
        auto* value = parameters.getRawParameterValue (binding.id);
        jassert (value != nullptr);
        externalValues.push_back (value);
    }
    for (const auto& binding : ccBindings)
    {
        const juce::String id =
            juce::String (binding.upper ? "up_" : "lo_") + binding.suffix;
        if (auto* parameter = parameters.getParameter (id))
        {
            const juce::String suffix (binding.suffix);
            std::atomic<float>* wide = nullptr;
            if (suffix == "osc1_pitch" || suffix == "osc2_pitch")
                wide = parameters.getRawParameterValue (
                    juce::String (binding.upper ? "up_" : "lo_")
                    + (suffix == "osc1_pitch" ? "osc1_wide" : "osc2_wide"));
            ccCache.push_back ({ binding.controller, parameter,
                                 parameters.getRawParameterValue (id),
                                 binding.signedValue,
                                 suffix == "key_follow", wide,
                                 wide == nullptr ? 0u : 0x10000000u
                                     + (binding.upper ? 0x100u : 0x200u)
                                     + (suffix == "osc1_pitch" ? 1u : 7u) });
        }
    }
    // Settled (OM p. 72): the audio filter answers on CC#2 and CC#4.
    const auto cacheShared = [this] (int controller, const char* id)
    {
        if (auto* parameter = parameters.getParameter (id))
            ccCache.push_back ({ controller, parameter,
                                 parameters.getRawParameterValue (id), false,
                                 false });
    };
    cacheShared (2, "audio_filter_cutoff");
    cacheShared (4, "audio_filter_reso");
    cacheShared (12, "delay_time");
    cacheShared (13, "reverb_time");
    // The dirty mask is a fixed pair of words, so the cache has to fit it.
    jassert (ccCache.size() <= 128);

    // One shadow slot per cached CC, seeded from the parameter so a pass that
    // runs before any CC has arrived publishes what is already there.
    ccShadow = std::make_unique<std::atomic<float>[]> (ccCache.size());
    for (std::size_t i = 0; i < ccCache.size(); ++i)
        ccShadow[i].store (ccCache[i].raw->load (std::memory_order_relaxed),
                           std::memory_order_relaxed);

    // The same for the three tables a received patch dump writes.
    const auto seed = [] (std::unique_ptr<std::atomic<float>[]>& shadow,
                          const std::vector<std::atomic<float>*>& values)
    {
        shadow = std::make_unique<std::atomic<float>[]> (values.size());
        for (std::size_t i = 0; i < values.size(); ++i)
            shadow[i].store (values[i]->load (std::memory_order_relaxed),
                             std::memory_order_relaxed);
    };
    seed (upperShadow, upperValues);
    seed (lowerShadow, lowerValues);
    seed (patchShadow, patchValues);
}

namespace
{
// How a value is printed, on the panel and in the host's own parameter list.
// The manual prints signed parameters with their sign and PAN as L64...63R,
// so the plug-in does too.
const std::vector<juce::String>& signedParameterSuffixes()
{
    static const std::vector<juce::String> suffixes {
        "osc1_pitch", "osc1_detune", "osc1_penv_depth", "osc2_pitch",
        "osc2_detune", "osc2_penv_depth", "balance", "key_follow",
        "cutoff_vel", "fenv_depth", "level_vel",
        "octave_shift", "tone_balance", "arp_octave", "delay_feedback",
        "reverb_lf_damp_gain", "reverb_hf_damp_gain",
        "system_key_shift", "system_octave", "system_transpose"
    };
    return suffixes;
}

[[nodiscard]] bool isSignedDisplay (const juce::String& id)
{
    for (const auto& suffix : signedParameterSuffixes())
        if (id == suffix || id.endsWith ("_" + suffix)
            || (id.startsWith ("up_") && id.substring (3) == suffix)
            || (id.startsWith ("lo_") && id.substring (3) == suffix))
            return true;
    return false;
}

[[nodiscard]] juce::AudioParameterIntAttributes intAttributes (const juce::String& id)
{
    if (id == "pan" || id == "up_pan" || id == "lo_pan")
        return juce::AudioParameterIntAttributes().withStringFromValueFunction (
            [] (int value, int)
            {
                // L64 ... 0 ... 63R, the display the manual prints.
                if (value < 0)
                    return "L" + juce::String (-value);
                if (value > 0)
                    return juce::String (value) + "R";
                return juce::String ("0");
            });
    if (id == "arp_end_step")
        return juce::AudioParameterIntAttributes().withStringFromValueFunction (
            [] (int value, int)
            {
                // Zero is not a step count, it is the absence of one.
                return value <= 0 ? juce::String ("STYLE") : juce::String (value);
            });
    // The manual prints these four as something other than the byte the
    // address map stores, so the panel and the host print that instead.
    if (id == "arp_velocity")
        return juce::AudioParameterIntAttributes().withStringFromValueFunction (
            [] (int value, int)
            {
                // "REAL, 1-127" (OM p. 66): zero is not a velocity, it is the
                // played one.
                return value <= 0 ? juce::String ("REAL") : juce::String (value);
            });
    if (id == "reverb_size")
        return juce::AudioParameterIntAttributes().withStringFromValueFunction (
            [] (int value, int)
            {
                return juce::String (value + 1);   // "SIZE 1-8" (OM p. 65)
            });
    if (id == "reverb_pre_delay")
        return juce::AudioParameterIntAttributes().withStringFromValueFunction (
            [] (int value, int)
            {
                // "0.0-100.0 (ms)" (OM p. 65).
                return juce::String (septum::mapping::reverbPreDelayMs (value), 1);
            });
    if (id == "split_point")
        return juce::AudioParameterIntAttributes().withStringFromValueFunction (
            [] (int value, int)
            {
                // "A0-C8" (OM p. 64) — a key, not a note number. Middle C is
                // C4 here, as it is on the panel's own keyboard.
                return juce::MidiMessage::getMidiNoteName (value, true, true, 4);
            });
    // Two parameters the address map stores more coarsely than one raw step
    // per displayed unit: the panel prints the position the instrument can
    // actually take, so the readout never disagrees with what is rendered.
    if (id == "delay_feedback")
        return juce::AudioParameterIntAttributes().withStringFromValueFunction (
            [] (int value, int)
            {
                const int snapped =
                    2 * juce::jlimit (-49, 49,
                                      (int) roundedParameter (value / 2.0));
                return snapped > 0 ? "+" + juce::String (snapped)
                                   : juce::String (snapped);
            });
    if (id == "key_follow" || id == "up_key_follow" || id == "lo_key_follow")
        return juce::AudioParameterIntAttributes().withStringFromValueFunction (
            [] (int value, int)
            {
                const int snapped =
                    10 * juce::jlimit (-20, 20,
                                       (int) roundedParameter (value / 10.0));
                return snapped > 0 ? "+" + juce::String (snapped)
                                   : juce::String (snapped);
            });
    if (isSignedDisplay (id))
        return juce::AudioParameterIntAttributes().withStringFromValueFunction (
            [] (int value, int)
            {
                return value > 0 ? "+" + juce::String (value)
                                 : juce::String (value);
            });
    return {};
}
} // namespace

juce::AudioProcessorValueTreeState::ParameterLayout
SeptumAudioProcessor::createParameterLayout()
{
    using namespace juce;
    AudioProcessorValueTreeState::ParameterLayout layout;

    const Patch defaults = septum::initPatch();

    const auto addTone = [&layout, &defaults] (bool upper)
    {
        const TonePatch& tone = upper ? defaults.upper : defaults.lower;
        const String prefix = upper ? "up_" : "lo_";
        const String partName = upper ? "Upper " : "Lower ";
        for (const auto& binding : toneBindings())
        {
            const String id = prefix + binding.suffix;
            const String name = partName + binding.label;
            const auto defaultValue = binding.get (tone);
            switch (binding.kind)
            {
                case Kind::Int:
                    layout.add (std::make_unique<AudioParameterInt> (
                        ParameterID { id, 1 }, name, binding.low, binding.high,
                        (int) roundedParameter (defaultValue), intAttributes (id)));
                    break;
                case Kind::Bool:
                    layout.add (std::make_unique<AudioParameterBool> (
                        ParameterID { id, 1 }, name, defaultValue >= 0.5f,
                        juce::AudioParameterBoolAttributes().withAutomatable (
                            ! binding.inert)));
                    break;
                case Kind::Choice:
                    layout.add (std::make_unique<AudioParameterChoice> (
                        ParameterID { id, 1 }, name, *binding.choices,
                        (int) roundedParameter (defaultValue)));
                    break;
            }
        }
    };
    addTone (true);
    addTone (false);

    // SYSTEM COMMON, outside the patch exactly as the external-input block is.
    layout.add (std::make_unique<juce::AudioParameterFloat> (
        juce::ParameterID { "system_master_tune", 1 }, "Master Tune",
        // 0.1-cent steps around A440, which is what the address map stores;
        // the manual prints the endpoints as the frequency of A4.
        juce::NormalisableRange<float> { 415.30f, 466.20f, 0.0f }, 440.0f,
        juce::AudioParameterFloatAttributes().withStringFromValueFunction (
            [] (float value, int) { return juce::String (value, 2) + " Hz"; })));
    layout.add (std::make_unique<juce::AudioParameterInt> (
        juce::ParameterID { "system_key_shift", 1 }, "Master Key Shift", -24, 24,
        0, intAttributes ("system_key_shift")));
    layout.add (std::make_unique<juce::AudioParameterInt> (
        juce::ParameterID { "system_octave", 1 }, "Keyboard Octave Shift", -3, 3,
        0, intAttributes ("system_octave")));
    layout.add (std::make_unique<juce::AudioParameterInt> (
        juce::ParameterID { "system_transpose", 1 }, "Transpose", -5, 6, 0,
        intAttributes ("system_transpose")));

    const septum::ExternalInput externalDefaults {};
    for (const auto& binding : externalBindings())
    {
        const auto defaultValue = binding.get (externalDefaults);
        switch (binding.kind)
        {
            case Kind::Int:
                layout.add (std::make_unique<juce::AudioParameterInt> (
                    juce::ParameterID { binding.id, 1 }, binding.label,
                    binding.low, binding.high, (int) roundedParameter (defaultValue),
                    intAttributes (binding.id)));
                break;
            case Kind::Bool:
                layout.add (std::make_unique<juce::AudioParameterBool> (
                    juce::ParameterID { binding.id, 1 }, binding.label,
                    defaultValue >= 0.5f));
                break;
            case Kind::Choice:
                layout.add (std::make_unique<juce::AudioParameterChoice> (
                    juce::ParameterID { binding.id, 1 }, binding.label,
                    *binding.choices, (int) roundedParameter (defaultValue)));
                break;
        }
    }

    for (const auto& binding : patchBindings())
    {
        const auto defaultValue =
            juce::String (binding.id) == "master_level"
                ? 100.0f
                : binding.get (defaults);
        const bool automatable = ! binding.inert;
        switch (binding.kind)
        {
            case Kind::Int:
                layout.add (std::make_unique<juce::AudioParameterInt> (
                    juce::ParameterID { binding.id, 1 }, binding.label,
                    binding.low, binding.high, (int) roundedParameter (defaultValue),
                    intAttributes (binding.id).withAutomatable (automatable)));
                break;
            case Kind::Bool:
                layout.add (std::make_unique<juce::AudioParameterBool> (
                    juce::ParameterID { binding.id, 1 }, binding.label,
                    defaultValue >= 0.5f,
                    juce::AudioParameterBoolAttributes().withAutomatable (
                        automatable)));
                break;
            case Kind::Choice:
                layout.add (std::make_unique<juce::AudioParameterChoice> (
                    juce::ParameterID { binding.id, 1 }, binding.label,
                    *binding.choices, (int) roundedParameter (defaultValue),
                    juce::AudioParameterChoiceAttributes().withAutomatable (
                        automatable)));
                break;
        }
    }

    // Append extensions for existing host parameter order, and use a newer
    // version hint so AUv2 keeps its older automation parameter indices.
    layout.add (std::make_unique<juce::AudioParameterBool> (
        juce::ParameterID { "upper_enabled", 2 }, "Upper Part Enabled", true));
    layout.add (std::make_unique<juce::AudioParameterBool> (
        juce::ParameterID { "lower_enabled", 2 }, "Lower Part Enabled", true));
    // OM pp. 58, 68–70: one MIDI part, receive switches and device ID are
    // system settings. Append to preserve all existing host parameter indices.
    layout.add (std::make_unique<juce::AudioParameterInt> (
        juce::ParameterID { "system_midi_channel", 3 }, "MIDI Receive Channel",
        0, 16, 1,
        juce::AudioParameterIntAttributes().withStringFromValueFunction (
            [] (int value, int) { return value == 0 ? juce::String ("ALL")
                                                   : juce::String (value); })));
    layout.add (std::make_unique<juce::AudioParameterBool> (
        juce::ParameterID { "system_receive_program", 3 },
        "Receive Program Change", true));
    layout.add (std::make_unique<juce::AudioParameterInt> (
        juce::ParameterID { "system_device_id", 3 }, "SysEx Device ID",
        17, 24, 17));
    layout.add (std::make_unique<juce::AudioParameterBool> (
        juce::ParameterID { "system_active_sensing", 3 },
        "Receive Active Sensing", true));
    // PATCH/SYSTEM/MIDI follow OM p. 68. USB MIDI reaches the same MIDI
    // event stream in a plug-in. HOST is an explicit DAW integration option.
    layout.add (std::make_unique<juce::AudioParameterChoice> (
        juce::ParameterID { "system_clock_source", 4 }, "Clock Source",
        juce::StringArray { "PATCH", "SYSTEM", "MIDI", "HOST" }, 0));
    layout.add (std::make_unique<juce::AudioParameterInt> (
        juce::ParameterID { "system_tempo", 4 }, "System Tempo", 5, 300, 120,
        juce::AudioParameterIntAttributes().withLabel ("BPM")));
    layout.add (std::make_unique<juce::AudioParameterBool> (
        juce::ParameterID { "system_receive_bank", 5 }, "Receive Bank Select", true));
    layout.add (std::make_unique<juce::AudioParameterChoice> (
        juce::ParameterID { "system_remote_keyboard", 6 }, "Remote Keyboard",
        juce::StringArray { "DIRECT", "REMOTE", "CHANNEL" }, 2));
    layout.add (std::make_unique<juce::AudioParameterBool> (
        juce::ParameterID { "system_patch_remain", 7 }, "Patch Remain", false));
    return layout;
}

void SeptumAudioProcessor::applySystemSettings() noexcept
{
    // Settled SYSTEM COMMON. Cached atomics only, so this costs the audio
    // thread four loads a block.
    engine.setMasterTuneHz (systemTuneValue->load (std::memory_order_relaxed));
    engine.setMasterKeyShift ((int) roundedParameter (
        systemValues[0]->load (std::memory_order_relaxed)));
    engine.setKeyboardOctaveShift ((int) roundedParameter (
        systemValues[1]->load (std::memory_order_relaxed)));
    engine.setTranspose ((int) roundedParameter (
        systemValues[2]->load (std::memory_order_relaxed)));
}

septum::ExternalInput SeptumAudioProcessor::snapshotExternalInput() const
{
    septum::ExternalInput settings {};
    const auto& bindings = externalBindings();
    for (std::size_t i = 0; i < bindings.size(); ++i)
        bindings[i].set (settings,
                         externalValues[i]->load (std::memory_order_relaxed));
    septum::clampToDocumentedRanges (settings);
    return settings;
}

// The imported grid is not a parameter, so the value tree does not carry it.
// It is stored as the sixteen Patch Arpeggio Pattern blocks the address map
// defines, base64'd — the same bytes a real unit would send, so the state file
// and the wire agree and there is no second format to keep right.
void SeptumAudioProcessor::writeImportedArpeggioToState (juce::ValueTree& state) const
{
    int selector = -1;
    septum::ArpeggioStyle style;
    // The flag is not even asked for. The selector this reads with was
    // scraped from the slot itself a moment ago, so a mismatch cannot mean
    // the user moved the selector — only that a dump landed between the two
    // reads. A save is a read of the patch; retiring on that threw away a
    // grid nobody moved away from, and then stripped it from the session.
    if (! importedArpeggio.valid.load (std::memory_order_acquire)
        || ! readImportedArpeggioStyle (-1, style, nullptr, &selector))
    {
        // The tree being written is a copy of the last state, so it may still
        // carry a grid from a session that was restored earlier. Leaving it
        // there saved a grid the plug-in had already discarded — a factory
        // program loaded after the restore, say — and restoring that session
        // brought it back to override the program's own style.
        state.removeProperty ("arpeggio_grid", nullptr);
        state.removeProperty ("arpeggio_grid_selector", nullptr);
        state.removeProperty ("arpeggio_grid_end_step", nullptr);
        return;
    }

    std::vector<std::uint8_t> bytes (
        septum::sysex::sizeArpeggioPattern * (std::size_t) septum::arpeggioMaxRows);
    for (int row = 0; row < septum::arpeggioMaxRows; ++row)
        septum::sysex::encodeArpeggioPattern (
            style, row,
            bytes.data() + (std::size_t) row * septum::sysex::sizeArpeggioPattern);

    juce::MemoryOutputStream encoded;
    juce::Base64::convertToBase64 (encoded, bytes.data(), bytes.size());
    state.setProperty ("arpeggio_grid", encoded.toString(), nullptr);
    state.setProperty ("arpeggio_grid_selector", selector, nullptr);
    state.setProperty ("arpeggio_grid_end_step", style.endStep, nullptr);
}

void SeptumAudioProcessor::readImportedArpeggioFromState (const juce::ValueTree& state)
{
    const auto encoded = state.getProperty ("arpeggio_grid").toString();
    if (encoded.isEmpty())
    {
        importedArpeggio.valid.store (false, std::memory_order_release);
        return;
    }

    // Whatever happens below, the grid this processor was holding belongs to
    // the session that has just been replaced. A restore whose grid property
    // is present but unreadable used to leave the old one valid, and if the
    // restored selector happened to match it, the stale grid played instead
    // of the restored patch's own style.
    juce::MemoryOutputStream decoded;
    const auto expected =
        septum::sysex::sizeArpeggioPattern * (std::size_t) septum::arpeggioMaxRows;
    if (! juce::Base64::convertFromBase64 (decoded, encoded)
        || decoded.getDataSize() != expected)
    {
        importedArpeggio.valid.store (false, std::memory_order_release);
        return;
    }

    const auto* bytes = static_cast<const std::uint8_t*> (decoded.getData());
    septum::ArpeggioStyle style;
    for (int row = 0; row < septum::arpeggioMaxRows; ++row)
        septum::sysex::decodeArpeggioPattern (
            bytes + (std::size_t) row * septum::sysex::sizeArpeggioPattern,
            septum::sysex::sizeArpeggioPattern, row, style);
    style.endStep = juce::jlimit (
        1, septum::arpeggioMaxSteps,
        (int) state.getProperty ("arpeggio_grid_end_step", style.endStep));

    publishImportedArpeggioStyle (
        style, (int) state.getProperty ("arpeggio_grid_selector", 0));
}

void SeptumAudioProcessor::publishImportedArpeggioStyle (
    const septum::ArpeggioStyle& style, int selector) noexcept
{
    for (std::size_t attempt = 0; attempt < ImportedArpeggioStyle::slotCount; ++attempt)
    {
        const auto mine = importedArpeggio.reserved.fetch_add (1, std::memory_order_relaxed);
        const auto index = mine % ImportedArpeggioStyle::slotCount;
        const auto published = importedArpeggio.published.load (std::memory_order_acquire);
        if (published != 0 && (published - 1u) % ImportedArpeggioStyle::slotCount == index)
            continue;
        auto& slot = importedArpeggio.slots[index];
        int free = 0;
        if (! slot.users.compare_exchange_strong (free, -1, std::memory_order_acquire))
            continue;
        slot.style = style;
        slot.selector = selector;
        importedArpeggio.valid.store (true, std::memory_order_release);
        importedArpeggio.published.store (mine + 1u, std::memory_order_release);
        slot.users.store (0, std::memory_order_release);
        return;
    }
    // Every slot is pinned by concurrent readers: preserve the last complete
    // grid instead of blocking the callback or racing a reader's copy.
}

void SeptumAudioProcessor::invalidateImportedArpeggioStyle() const noexcept
{
    importedArpeggio.valid.store (false, std::memory_order_release);
}

bool SeptumAudioProcessor::readImportedArpeggioStyle (
    int selector, septum::ArpeggioStyle& out, bool* selectorMoved,
    int* storedSelector, std::uint64_t* observedTicket) const noexcept
{
    if (! importedArpeggio.valid.load (std::memory_order_acquire))
        return false;

    for (int attempt = 0; attempt < 8; ++attempt)
    {
        const auto published =
            importedArpeggio.published.load (std::memory_order_acquire);
        if (published == 0u)
            return false;
        const auto& slot =
            importedArpeggio.slots[(published - 1u) % ImportedArpeggioStyle::slotCount];
        int users = slot.users.load (std::memory_order_relaxed);
        if (users < 0 || ! slot.users.compare_exchange_strong (
                users, users + 1, std::memory_order_acquire))
            continue;
        if (importedArpeggio.published.load (std::memory_order_acquire) != published)
        {
            slot.users.fetch_sub (1, std::memory_order_release);
            continue;
        }
        const int slotSelector = slot.selector;
        out = slot.style;
        slot.users.fetch_sub (1, std::memory_order_release);
        if (importedArpeggio.published.load (std::memory_order_acquire) != published)
            continue;
        if (storedSelector != nullptr)
            *storedSelector = slotSelector;
        if (observedTicket != nullptr)
            *observedTicket = published;

        // The grid belongs to the selector position it arrived under, and
        // moving the selector chooses a template — the manual says editing a
        // style needs the SH-201 Editor, so the panel only ever selects, and
        // a selection replaces what the patch held. Retiring the grid on that
        // first move is what makes returning to the same index load the
        // template rather than resurrect the import.
        if (selector >= 0 && slotSelector != selector)
        {
            // Reported, never acted on. `loadPatch` publishes the grid first
            // and then writes some ninety parameters one at a time, so for the
            // whole of that burst a snapshot carries the *previous* selector
            // while the slot already carries the new one — and retiring on
            // that mismatch destroyed the grid the load had just brought in,
            // permanently: the next state save then stripped it from the
            // session file too. Whether the burst overlapped this read is a
            // question only the caller can answer, and only afterwards.
            if (selectorMoved != nullptr)
                *selectorMoved = true;
            return false;
        }
        return true;
    }
    return false;   // publishes kept overtaking; the template stands in
}

septum::Patch SeptumAudioProcessor::snapshotPatch() const
{
    // Runs on the audio thread every block: only cached atomic loads, no
    // string building or lookups.
    const bool quietAtEntry = activePatchWriters.load (std::memory_order_acquire) == 0u;
    const auto generationAtEntry =
        patchGeneration.load (std::memory_order_acquire);
    Patch patch = septum::initPatch();

    const auto& bindings = toneBindings();
    for (std::size_t index = 0; index < bindings.size(); ++index)
    {
        bindings[index].set (patch.upper,
                             upperValues[index]->load (std::memory_order_relaxed));
        bindings[index].set (patch.lower,
                             lowerValues[index]->load (std::memory_order_relaxed));
    }
    const auto& shared = patchBindings();
    for (std::size_t index = 0; index < shared.size(); ++index)
        shared[index].set (patch,
                           patchValues[index]->load (std::memory_order_relaxed));

    // The style index is the panel's selector; the grid it names is what the
    // engine actually plays — unless a SysEx dump brought a grid of its own,
    // which no parameter can hold and which the hardware stores in the patch.
    bool selectorMoved = false;
    std::uint64_t importedTicket = 0;
    if (readImportedArpeggioStyle (patch.arpeggio.styleIndex, patch.arpeggio.style,
                                   &selectorMoved, nullptr, &importedTicket))
    {
        // END STEP still overrides, exactly as it does over a template.
        if (patch.arpeggio.endStep > 0)
            patch.arpeggio.style.endStep =
                std::min (patch.arpeggio.endStep, septum::arpeggioMaxSteps);
    }
    else
    {
        septum::applyArpeggioStyle (patch, patch.arpeggio.styleIndex);
    }

    // Whether everything read above — the selector among it — belongs to one
    // patch revision. Writers stay counted across their whole bursts, so
    // an active writer, or a revision that moved while this ran, means the
    // selector may be from a different revision than the slot it was compared
    // against. `applyCurrentPatch` throws such a snapshot away; the retire is
    // the one part of it that used to survive. Closing the window *below* the
    // read is the whole point: closed above it, a burst starting in between
    // was still free to publish a new grid under a new selector and have this
    // read retire it.
    const bool settled = quietAtEntry && patchSnapshotStable (generationAtEntry);
    if (selectorMoved && settled)
    {
        // A new import may publish after the generation check. Retire only
        // the exact slot revision this snapshot compared, never a newer grid.
        importedArpeggio.published.compare_exchange_strong (
            importedTicket, 0, std::memory_order_acq_rel, std::memory_order_acquire);
    }

    septum::clampToDocumentedRanges (patch);
    return patch;
}

void SeptumAudioProcessor::prepareToPlay (double sampleRate,
                                              int samplesPerBlock)
{
    prepared = false;
    deferredParameterRead = deferredParameterCount = 0;
    sampleRate = std::isfinite (sampleRate) ? std::clamp (sampleRate, 8000.0, 768000.0) : 44100.0;
    // Hosts may exceed their advertised maximum later. The render loop
    // chunks those calls into this fixed workspace without reallocating.
    samplesPerBlock = juce::jlimit (16, 65536, samplesPerBlock);
    midiTempoClock.prepare (sampleRate);
    hostTempoBpm = 0.0;
    appliedClockSource = static_cast<int> (roundedParameter (clockSourceValue->load()));
    liveSysExDecoder.reset();
    appliedLiveSysExRevision = liveSysExRevision.load (std::memory_order_acquire);
    activeSensingArmed = false;
    activeSensingSamplesRemaining = 0;
    // The manual says "exceeds 420 ms", hence the first sample strictly
    // beyond that interval, including at rates where 420 ms is integral.
    activeSensingTimeoutSamples = static_cast<std::uint64_t> (
        std::floor (sampleRate * 0.420)) + 1u;
    appliedMidiChannel = static_cast<int> (roundedParameter (midiChannelValue->load()));
    midiBankSelect.reset();
    appliedRemoteKeyboard = static_cast<int> (roundedParameter (remoteKeyboardValue->load()));
    appliedPatchSelectionRevision = patchSelectionRevision.load (std::memory_order_acquire);
    retainedReleaseSeconds.store (0.0, std::memory_order_relaxed);
    engine.prepare (sampleRate, samplesPerBlock);
    engine.setMasterLevel ((int) roundedParameter (masterValue->load()));
    applySystemSettings();
    engine.setPatch (snapshotPatch());
    engine.setExternalInput (snapshotExternalInput());
    for (std::size_t part = 0; part < partEnableValues.size(); ++part)
    {
        engine.setPartEnabled (part == 0,
            partEnableValues[part]->load (std::memory_order_relaxed) >= 0.5f);
        partActiveVoices[part].store (0, std::memory_order_relaxed);
        partHeldVoices[part].store (0, std::memory_order_relaxed);
    }
    activeVoices.store (0, std::memory_order_relaxed);
    engine.reset();
    applyTempoSource();
    monoScratch.assign ((std::size_t) juce::jmax (samplesPerBlock, 16), 0.0f);
    externalInputL.assign ((std::size_t) juce::jmax (samplesPerBlock, 16), 0.0f);
    externalInputR.assign ((std::size_t) juce::jmax (samplesPerBlock, 16), 0.0f);
    // All voices and monitored input carry the overdrive alignment delay and
    // shared output-circuit reconstruction delay. Report the complete path.
    setLatencySamples (engine.latencySamples());
    prepared = true;
}

void SeptumAudioProcessor::releaseResources()
{
    prepared = false;
    deferredParameterRead = deferredParameterCount = 0;
    engine.reset();
    activeSensingArmed = false;
    midiTempoClock.reset();
    uiRead.store (uiWrite.load (std::memory_order_acquire), std::memory_order_release);
    for (auto& release : forcedRelease)
        release.store (0, std::memory_order_relaxed);
    activeVoices.store (0, std::memory_order_relaxed);
    for (std::size_t part = 0; part < partActiveVoices.size(); ++part)
    {
        partActiveVoices[part].store (0, std::memory_order_relaxed);
        partHeldVoices[part].store (0, std::memory_order_relaxed);
    }
}

bool SeptumAudioProcessor::isBusesLayoutSupported (
    const BusesLayout& layouts) const
{
    if (layouts.getMainOutputChannelSet() != juce::AudioChannelSet::stereo())
        return false;
    const auto input = layouts.getMainInputChannelSet();
    return input.isDisabled() || input == juce::AudioChannelSet::mono()
           || input == juce::AudioChannelSet::stereo();
}

double SeptumAudioProcessor::getTailLengthSeconds() const
{
    // Honest per-patch tail: the longest amp release, plus the delay's
    // repeats down to -60 dB, plus the reverb's RT60 (the delay feeds the
    // reverb in series). The documented +/-98 % feedback extreme decays only
    // 2 % per repeat — minutes of audible tail — so the report is capped at
    // a bound offline renderers can live with.
    const Patch patch = snapshotPatch();
    using namespace septum::mapping;

    double tail = std::max ({decaySeconds (patch.upper.ampEnvRelease),
                            decaySeconds (patch.lower.ampEnvRelease),
                            retainedReleaseSeconds.load (std::memory_order_relaxed)});
    if (patch.delayOn)
    {
        const double feedback =
            std::clamp (std::abs (patch.delay.feedback) / 100.0, 0.0, 0.99);
        const double repeats =
            feedback <= 0.0 ? 1.0
                            : std::max (1.0, std::log (1.0e-3) / std::log (feedback));
        tail += delaySeconds (patch.delay.time) * repeats;
    }
    if (patch.reverbOn)
        tail += reverbSeconds (patch.reverb.time, patch.reverb.size);
    return std::clamp (tail, 0.1, 120.0);
}

void SeptumAudioProcessor::triggerFromUi (int note, int velocity) noexcept
{
    note = juce::jlimit (0, 127, note);
    velocity = juce::jlimit (1, 127, velocity);
    const auto write = uiWrite.load (std::memory_order_relaxed);
    const auto read = uiRead.load (std::memory_order_acquire);
    if (write - read >= uiQueueCapacity)
    {
        overflowUiVelocity[static_cast<std::size_t> (note)].store (velocity, std::memory_order_relaxed);
        forcedRelease[static_cast<std::size_t> (note >> 6)].fetch_or (
            1ull << (note & 63), std::memory_order_release);
        return;
    }
    forcedRelease[static_cast<std::size_t> (note >> 6)].fetch_and (
        ~(1ull << (note & 63)), std::memory_order_acq_rel);
    uiQueue[write % uiQueueCapacity] = { note, velocity };
    uiWrite.store (write + 1, std::memory_order_release);
}

void SeptumAudioProcessor::releaseFromUi (int note) noexcept
{
    note = juce::jlimit (0, 127, note);
    const auto write = uiWrite.load (std::memory_order_relaxed);
    const auto read = uiRead.load (std::memory_order_acquire);
    if (write - read >= uiQueueCapacity)
    {
        // A dropped note-off would leave the note stuck once processing
        // resumes; latch the release instead of losing it.
        overflowUiVelocity[static_cast<std::size_t> (note)].store (0, std::memory_order_relaxed);
        forcedRelease[(std::size_t) (note >> 6)].fetch_or (
            1ull << (note & 63), std::memory_order_release);
        return;
    }
    forcedRelease[static_cast<std::size_t> (note >> 6)].fetch_and (
        ~(1ull << (note & 63)), std::memory_order_acq_rel);
    uiQueue[write % uiQueueCapacity] = { note, 0 };
    uiWrite.store (write + 1, std::memory_order_release);
}

bool SeptumAudioProcessor::handleController (int controller, int value, int channel)
{
    switch (controller)
    {
        case 0:
        case 32:
            if (receiveBankValue->load (std::memory_order_relaxed) >= 0.5f)
                midiBankSelect.select (channel, controller, value);
            return false;
        case 1:  engine.setModulation (value / 127.0); return false;
        case 7:  engine.setPartLevel (value / 127.0); return false;
        case 10: engine.setPartPan ((value - 64) / 63.0); return false;
        case 11: engine.setExpression (value / 127.0); return false;
        case 64: engine.setHold (value >= 64); return false;
        case 66: engine.setSostenuto (value >= 64); return false;
        case 69:
            // Settled (OM p. 72): CC#69 is "Part Pitch (D Beam Pitch Mode)".
            // The replica does not implement the D Beam, so the message is
            // accepted and ignored — `false`, because nothing changed and
            // re-reading the patch mid-block would be wasted work.
            return false;
        case 84: engine.setPortamentoControl (value); return false;
        case 120: engine.allSoundOff(); return false;
        case 121:
            resetPerformanceControllers();
            return false;
        case 123:
        case 124:
        case 125:
            engine.allNotesOff();
            return false;
        case 126:
        case 127:
        {
            // OM p. 73 recognizes modes 3/4 and lists both mode messages
            // under All Sound Off. Mono is one note regardless of CC126's
            // channel-count byte. Follow MIDI's general mono-legato
            // recommendation; SH-201 CC126 articulation is unmeasured.
            engine.allSoundOff();
            ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Audio);
            if (! parameterWrite) return false;
            Patch livePatch = snapshotPatch();
            livePatch.upper.mono = livePatch.lower.mono =
                controller == 126 ? septum::MonoMode::SoloLegato : septum::MonoMode::Poly;
            writePatchToParameters (livePatch, true);
            patchReconciler.triggerAsyncUpdate();
            return true;
        }
        default: break;
    }

    ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Audio);
    if (! parameterWrite) return false;

    // Panel parameters per the documented CC map: received CCs edit the
    // corresponding patch parameter, exactly as the hardware does.
    //
    // This runs on the audio thread, so it writes the parameter's raw value
    // and nothing else — the idiom a MIDI program change already uses. The
    // three gesture calls it used to make instead all take the processor's
    // listener lock and can wake the message thread from inside the render
    // callback, which is the one thing a render callback may not do; and a
    // controller sweep makes 128 of them a second. The reconciler below
    // republishes the value with host and UI notification, coalesced.
    for (std::size_t index = 0; index < ccCache.size(); ++index)
    {
        const auto& cached = ccCache[index];
        if (cached.controller != controller)
            continue;
        float natural = cached.signedValue ? (float) (value - 64) : (float) value;
        if (cached.keyFollow)
            natural = juce::jlimit (-200.0f, 200.0f, (float) ((value - 64) * 10));
        if (cached.pitchWide != nullptr)
        {
            // A normal-range CC can round to the same physical semitone as
            // the preceding one. Retain its raw control position anyway: a
            // later WIDE DT1 must expand the latest byte, not an older byte
            // or a canonicalized inverse. Share the audio-thread decoder and
            // its patch-replacement revision handling with real SysEx.
            Patch livePatch = snapshotPatch();
            auto& tone = (cached.pitchAddress & 0xff00u) == 0x100u
                             ? livePatch.upper : livePatch.lower;
            auto& osc = (cached.pitchAddress & 0xffu) == 1u ? tone.osc1 : tone.osc2;
            std::array<std::uint8_t, 15> frame {
                0xf0, septum::sysex::rolandId, septum::sysex::defaultDeviceId,
                0, 0, 0x16, septum::sysex::cmdDt1,
                static_cast<std::uint8_t> (cached.pitchAddress >> 24),
                static_cast<std::uint8_t> ((cached.pitchAddress >> 16) & 0x7f),
                static_cast<std::uint8_t> ((cached.pitchAddress >> 8) & 0x7f),
                static_cast<std::uint8_t> (cached.pitchAddress & 0x7f),
                static_cast<std::uint8_t> (osc.pitchWide ? 1 : 0),
                static_cast<std::uint8_t> (value & 0x7f), 0, 0xf7
            };
            frame[13] = septum::sysex::calculateChecksum (frame.data() + 7, 6);
            if (decodeLivePatchMessage (frame.data(), frame.size(), livePatch))
                natural = static_cast<float> (osc.coarse);
        }
        const auto& range = cached.parameter->getNormalisableRange();
        const float snapped = range.snapToLegalValue (natural);
        // The engine snapshots the parameter's own storage, so the value goes
        // there to take effect on the next block, and into the shadow so the
        // message-thread pass below cannot publish an older one over it.
        cached.raw->store (snapped, std::memory_order_relaxed);
        ccShadow[index].store (snapped, std::memory_order_relaxed);
        ccDirty[index >> 6].fetch_or (1ull << (index & 63u),
                                      std::memory_order_release);
        ccReconciler.triggerAsyncUpdate();
        return true;
    }
    return false;
}

void SeptumAudioProcessor::reconcileControlChanges()
{
    ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Notification);
    if (! parameterWrite) return;
    for (std::size_t word = 0; word < ccDirty.size(); ++word)
    {
        auto bits = ccDirty[word].exchange (0u, std::memory_order_acquire);
        while (bits != 0u)
        {
            const auto index = word * 64u
                               + (std::size_t) std::countr_zero (bits);
            bits &= bits - 1u;
            if (index >= ccCache.size())
                continue;
            const auto& cached = ccCache[index];
            const auto& range = cached.parameter->getNormalisableRange();
            // Publish what the raw storage holds, not what the shadow holds.
            // Those differ whenever something moved the value after the CC
            // did — a knob, an automation lane — and the raw storage is what
            // the engine renders from, so it is what the host and the panel
            // have to be told about. Publishing the shadow regardless put the
            // CC's value back over an edit and snapped the slider under the
            // player's hand.
            //
            // The shadow is read first and only as a baseline. Read before the
            // raw value, a CC landing between the two loads leaves the newer
            // value in `natural` and the older one here, never the reverse.
            const float shadowAtEntry =
                ccShadow[index].load (std::memory_order_relaxed);
            const float natural = cached.raw->load (std::memory_order_relaxed);
            cached.parameter->beginChangeGesture();
            cached.parameter->setValueNotifyingHost (
                range.convertTo0to1 (range.snapToLegalValue (natural)));
            cached.parameter->endChangeGesture();
            // setValueNotifyingHost has just written the parameter's own
            // storage with the value read above, so a CC that arrived while it
            // ran was overwritten. Its dirty bit is already set for the next
            // pass — but the engine reads this storage every block, so the
            // newer value is put back now rather than a frame from now. A
            // shadow that has not moved means no CC landed, and whatever this
            // thread is publishing stays put.
            const float newest = ccShadow[index].load (std::memory_order_relaxed);
            if (newest != shadowAtEntry)
                cached.raw->store (newest, std::memory_order_relaxed);
        }
    }
}

// [settled] The MIDI Implementation lists three Universal Realtime device
// control messages among what the instrument receives, and names the SYSTEM
// COMMON parameter each one changes (v1.00 p. 2):
//
//   F0 7F 7F 04 01 ll mm F7   Master Volume       -> MASTER LEVEL
//   F0 7F 7F 04 03 ll mm F7   Master Fine Tuning  -> MASTER TUNE
//   F0 7F 7F 04 04 ll mm F7   Master Coarse Tuning-> MASTER KEY SHIFT
//
// All three parameters are published here, so the messages land on them.
bool SeptumAudioProcessor::handleDeviceControlSysEx (const std::uint8_t* data,
                                                     std::size_t size) noexcept
{
    // JUCE hands over the body without the F0 and the F7.
    if (data == nullptr || size < 6 || data[0] != 0x7F || data[1] != 0x7F
        || data[2] != 0x04)
        return false;

    ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Audio);
    if (! parameterWrite) return false;

    const int lsb = data[4] & 0x7F;
    const int msb = data[5] & 0x7F;

    const auto store = [this] (std::size_t index, float natural)
    {
        auto* parameter = deviceControlParameters[index];
        auto* raw = deviceControlValues[index];
        if (parameter == nullptr || raw == nullptr)
            return;
        const float snapped =
            parameter->getNormalisableRange().snapToLegalValue (natural);
        raw->store (snapped, std::memory_order_relaxed);
        deviceControlShadow[index].store (snapped, std::memory_order_relaxed);
        deviceControlDirty.fetch_or (1u << index, std::memory_order_release);
        systemReconciler.triggerAsyncUpdate();
    };

    switch (data[3])
    {
        case 0x01:
            // "The lower byte (llH) of Master Volume will be handled as 00H",
            // so the upper byte alone is the 0-127 level.
            store (0, static_cast<float> (msb));
            return true;
        case 0x03:
        {
            // 00 00H - 40 00H - 7F 7FH = -100 - 0 - +99.9 cents. MASTER TUNE
            // is published as the frequency of A4, which is how the manual
            // prints its endpoints.
            const double cents =
                (((msb << 7) | lsb) - 8192) * (100.0 / 8192.0);
            store (1, static_cast<float> (440.0 * std::exp2 (cents / 1200.0)));
            return true;
        }
        case 0x04:
            // "llH: ignored (processed as 00H)"; mmH 28H - 40H - 58H =
            // -24 - 0 - +24 semitones.
            store (2, static_cast<float> (msb - 64));
            return true;
        default:
            break;
    }
    return false;
}

void SeptumAudioProcessor::republishSystemParameters()
{
    ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Notification);
    if (! parameterWrite) return;
    auto bits = deviceControlDirty.exchange (0u, std::memory_order_acquire);
    for (std::size_t i = 0; i < deviceControlCount; ++i)
    {
        if ((bits & (1u << i)) == 0u)
            continue;
        auto* parameter = deviceControlParameters[i];
        auto* raw = deviceControlValues[i];
        if (parameter == nullptr || raw == nullptr)
            continue;
        const auto& range = parameter->getNormalisableRange();
        // Raw, not shadow, and the shadow only as a baseline — the same rule
        // the CC pass and the patch republish follow, and for the same reason:
        // the raw storage is what the engine renders from, so publishing the
        // shadow over it put a device-control message back on top of a later
        // edit. Baseline read before the raw value, so a message landing
        // between the two loads leaves the newer value in `natural`.
        const float shadowAtEntry =
            deviceControlShadow[i].load (std::memory_order_relaxed);
        const float natural = raw->load (std::memory_order_relaxed);
        parameter->beginChangeGesture();
        parameter->setValueNotifyingHost (range.convertTo0to1 (natural));
        parameter->endChangeGesture();
        // A second message for the same parameter that landed while
        // setValueNotifyingHost ran was overwritten by it, and the engine
        // reads that storage every block — so it goes back now, not a frame
        // from now. An unmoved shadow means nothing landed.
        const float newest = deviceControlShadow[i].load (std::memory_order_relaxed);
        if (newest != shadowAtEntry)
            raw->store (newest, std::memory_order_relaxed);
    }
}

void SeptumAudioProcessor::resetPerformanceControllers() noexcept
{
    engine.clearPortamentoControl();
    engine.setPitchBend (0.0);
    engine.setModulation (0.0);
    engine.setExpression (1.0);
    engine.setHold (false);
    engine.setSostenuto (false);
}

bool SeptumAudioProcessor::acceptsLiveSysEx (const std::uint8_t* data,
                                            std::size_t size) const noexcept
{
    if (data == nullptr || size < 2)
        return false;
    if (data[0] != septum::sysex::rolandId)
        return true; // Universal realtime controls specify broadcast separately.
    const auto device = static_cast<int> (roundedParameter (
        deviceIdValue->load (std::memory_order_relaxed))) - 1;
    // OM p. 70 displays 17–24; the wire carries 10H–17H. DT1 also
    // explicitly permits 7FH broadcast (MIDI Implementation p. 3).
    return data[1] == device || data[1] == 0x7f;
}

bool SeptumAudioProcessor::decodeLivePatchMessage (
    const std::uint8_t* data, std::size_t size, septum::Patch& patch) noexcept
{
    const auto revision = liveSysExRevision.load (std::memory_order_acquire);
    if (revision != appliedLiveSysExRevision)
    {
        liveSysExDecoder.reset();
        appliedLiveSysExRevision = revision;
    }
    return liveSysExDecoder.decode (data, size, patch);
}

void SeptumAudioProcessor::observeMidiActivity (
    const juce::MidiMessage& message) noexcept
{
    if (activeSensingValue->load (std::memory_order_relaxed) < 0.5f)
    {
        activeSensingArmed = false;
        return;
    }
    // MIDI Implementation p. 2: after FE, *all* subsequent MIDI traffic
    // refreshes the timer, including events addressed to other channels.
    if (message.isActiveSense())
        activeSensingArmed = true;
    if (activeSensingArmed)
        activeSensingSamplesRemaining = activeSensingTimeoutSamples;
}

bool SeptumAudioProcessor::handleMidiMessage (const juce::MidiMessage& message)
{
    const int channel = message.getChannel();
    const int controller = message.isController() ? message.getControllerNumber() : -1;
    const bool keyboardPerformance = message.isNoteOnOrOff() || message.isPitchWheel()
        || controller == 1 || controller == 7 || controller == 10 || controller == 11
        || controller == 64 || controller == 66 || controller == 84;
    // OM p. 69 makes a remote keyboard channel-independent. Panel edits,
    // program selection and mode commands remain on the receive channel.
    const bool remote = appliedRemoteKeyboard == 1 && keyboardPerformance;
    if (channel != 0 && appliedMidiChannel != 0 && channel != appliedMidiChannel && ! remote)
        return false;
    if (message.isNoteOn())
    {
        if (appliedRemoteKeyboard == 0)
            engine.noteOnDirect (message.getNoteNumber(), message.getVelocity());
        else
            engine.noteOn (message.getNoteNumber(), message.getVelocity());
    }
    else if (message.isNoteOff())
    {
        if (appliedRemoteKeyboard == 0) engine.noteOffDirect (message.getNoteNumber());
        else engine.noteOff (message.getNoteNumber());
    }
    else if (message.isPitchWheel())
        engine.setPitchBend ((message.getPitchWheelValue() - 8192) / 8192.0);
    else if (message.isController())
        return handleController (message.getControllerNumber(),
                                 message.getControllerValue(), channel);
    else if (message.isProgramChange())
    {
        ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Audio);
        if (! parameterWrite) return false;
        if (receiveProgramValue->load (std::memory_order_relaxed) < 0.5f)
            return false;
        const int program = midiBankSelect.program (channel, message.getProgramChangeNumber());
        if (program >= 0 && program < getNumPrograms())
        {
            // Land the program in the raw parameter values right here: notes
            // later in this same block must already play it, later edits must
            // compose on top of it, and none of that may depend on a message
            // loop that an offline host might never pump. The queued spray
            // only repeats these values with host/UI notification.
            writeProgramToParameters (program);
            applyProgramAsync (program);
            return true;
        }
    }
    else if (message.isSysEx())
    {
        ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Audio);
        if (! parameterWrite) return false;
        const auto* rawData = message.getSysExData();
        const auto rawSize = (std::size_t) message.getSysExDataSize();
        if (! acceptsLiveSysEx (rawData, rawSize))
            return false;
        if (handleDeviceControlSysEx (rawData, rawSize))
            return true;
        // A dump arrives on the audio thread. It writes the raw values here —
        // atomics only — and the message loop republishes them to the
        // parameter objects and the host, the same split a received CC uses
        // since Step 17. Calling loadPatch straight from here built a
        // juce::String per parameter and notified the host from inside the
        // render callback.
        Patch livePatch = snapshotPatch();
        if (decodeLivePatchMessage (rawData, rawSize, livePatch))
        {
            // The grid rides outside the parameters, so it goes in with them
            // rather than before: a dump is sixteen pattern packets and each
            // one starts from the snapshot the previous one left behind, and
            // publishing it inside the same guarded write window is what
            // keeps a concurrent state save from pairing this grid with the
            // previous packet's parameters.
            writePatchToParameters (livePatch, true);
            patchReconciler.triggerAsyncUpdate();
            return true;
        }
    }
    else if (message.isAllNotesOff())
        engine.allNotesOff();
    else if (message.isAllSoundOff())
        engine.allSoundOff();
    return false;
}

void SeptumAudioProcessor::resetPartEnablesToParameters() noexcept
{
    // The program writer owns the patch-generation window. Native programs
    // have no independent mute data and start with both parts enabled.
    for (auto* value : partEnableValues)
        value->store (1.0f, std::memory_order_relaxed);
}

void SeptumAudioProcessor::writeProgramToParameters (int index) noexcept
{
    if (index < 0 || index >= getNumPrograms())
        return;
    ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Audio);
    if (! parameterWrite) return;
    const Patch& patch =
        septum::factoryPatches()[(std::size_t) index].patch;
    liveSysExRevision.fetch_add (1, std::memory_order_acq_rel);

    // Guard the entire write burst, program index included, so a
    // concurrent state save — which seqlocks its raw-value copy against the
    // generation — can never serialize a half-written program or pair the
    // new index with the old values.
    PatchWriteScope patchWrite (*this);
    patchSelectionRevision.fetch_add (1, std::memory_order_release);
    currentProgram.store (index, std::memory_order_relaxed);
    presetIdentityRevision.fetch_add (1, std::memory_order_acq_rel);
    resetPartEnablesToParameters();

    const auto& bindings = toneBindings();
    for (std::size_t i = 0; i < bindings.size(); ++i)
    {
        upperValues[i]->store (bindings[i].get (patch.upper),
                               std::memory_order_relaxed);
        lowerValues[i]->store (bindings[i].get (patch.lower),
                               std::memory_order_relaxed);
    }
    const auto& shared = patchBindings();
    for (std::size_t i = 0; i < shared.size(); ++i)
        if (std::strcmp (shared[i].id, "master_level") != 0)
            patchValues[i]->store (shared[i].get (patch),
                                   std::memory_order_relaxed);

    // The program brings its own arpeggio style, named by its selector index,
    // so any grid a dump left behind stops standing in for a template.
    invalidateImportedArpeggioStyle();

    // A program change supersedes any dump republish still queued behind it,
    // and this runs on the audio thread, so the shadows are corrected here
    // rather than waiting for the message thread to notice.
    for (std::size_t i = 0; i < bindings.size(); ++i)
    {
        upperShadow[i].store (bindings[i].get (patch.upper), std::memory_order_relaxed);
        lowerShadow[i].store (bindings[i].get (patch.lower), std::memory_order_relaxed);
    }
    for (std::size_t i = 0; i < shared.size(); ++i)
        if (std::strcmp (shared[i].id, "master_level") != 0)
            patchShadow[i].store (shared[i].get (patch), std::memory_order_relaxed);
    patchDirty.store (false, std::memory_order_release);

    patchWrite.finish();
}

void SeptumAudioProcessor::reconcileProgram (int index)
{
    if (index < 0 || index >= getNumPrograms())
        return;
    ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Notification);
    if (! parameterWrite) return;
    const Patch& patch =
        septum::factoryPatches()[(std::size_t) index].patch;

    const auto apply = [this] (const juce::String& id, float natural)
    {
        auto* parameter = parameters.getParameter (id);
        auto* raw = parameters.getRawParameterValue (id);
        if (parameter == nullptr || raw == nullptr)
            return;
        const auto& range = parameters.getParameterRange (id);
        const float target = range.snapToLegalValue (natural);
        // The audio path already wrote this exact value when the program
        // change arrived. If it has moved since, the user edited it after
        // the program change and the edit wins — replaying the factory
        // value here would snap their edit back.
        if (raw->load() != target)
            return;
        parameter->setValueNotifyingHost (range.convertTo0to1 (target));
    };

    for (const bool upper : { true, false })
    {
        const TonePatch& tone = upper ? patch.upper : patch.lower;
        apply (upper ? "upper_enabled" : "lower_enabled", 1.0f);
        const juce::String prefix = upper ? "up_" : "lo_";
        for (const auto& binding : toneBindings())
            apply (prefix + binding.suffix, binding.get (tone));
    }
    for (const auto& binding : patchBindings())
        if (juce::String (binding.id) != "master_level")
            apply (binding.id, binding.get (patch));

    // No `syncPatchShadows()` here. This pass writes nothing new — it only
    // re-notifies the values the audio thread already stored, and skips any
    // the user has edited since. `writeProgramToParameters` already pointed
    // the shadows at the program and cleared the pending flag when the change
    // landed. Clearing it again here dropped the flag of a dump that arrived
    // *after* the program change, so the patch reconciler returned without
    // telling the host or the UI, and they sat on the program's values while
    // the engine rendered the dump's.
}

void SeptumAudioProcessor::applyProgramAsync (int program)
{
    // The newest program supersedes previous unpublished selections. The
    // timer owns notification; audio only makes an atomic mailbox write.
    pendingProgram.store (program, std::memory_order_release);
}

void SeptumAudioProcessor::applyTempoSource() noexcept
{
    switch (appliedClockSource)
    {
        case 1: engine.setTempoClock (systemTempoValue->load (std::memory_order_relaxed)); break;
        case 2: engine.setTempoClock (midiTempoClock.bpm(), midiTempoClock.running()); break;
        case 3: engine.setTempoClock (hostTempoBpm); break;
        default: engine.setTempoClock (0.0); break;
    }
}

void SeptumAudioProcessor::deferParameterMidi (const std::uint8_t* data, int size,
                                              std::uint64_t transaction) noexcept
{
    if (size <= 0 || size > static_cast<int> (DeferredParameterMidi {}.data.size()))
        return;
    if (deferredParameterTransaction != transaction)
    {
        deferredParameterRead = deferredParameterCount = 0;
        deferredParameterTransaction = transaction;
    }
    if (deferredParameterCount == deferredParameterCapacity)
    {
        // A lost DT1 packet breaks the continuity of raw multi-byte fields.
        // Remaining fragments must rebase from the current canonical patch.
        if (deferredParameterMidi[deferredParameterRead].data[0] == 0xf0)
            liveSysExDecoder.reset();
        deferredParameterRead = (deferredParameterRead + 1) % deferredParameterCapacity;
        --deferredParameterCount;
    }
    auto& event = deferredParameterMidi[
        (deferredParameterRead + deferredParameterCount) % deferredParameterCapacity];
    std::copy_n (data, size, event.data.begin());
    event.size = size;
    ++deferredParameterCount;
}

bool SeptumAudioProcessor::drainDeferredParameterMidi()
{
    if (deferredParameterCount == 0) return false;
    ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Audio);
    if (! parameterWrite) return false;
    if (deferredParameterTransaction != hostParameterTransaction.load())
    {
        deferredParameterRead = deferredParameterCount = 0;
        return false;
    }
    bool changed = false;
    while (deferredParameterCount > 0)
    {
        const auto& event = deferredParameterMidi[deferredParameterRead];
        deferredParameterRead = (deferredParameterRead + 1) % deferredParameterCapacity;
        --deferredParameterCount;
        if (event.data[0] == 0xf0)
        {
            const auto* body = event.data.data() + 1;
            const auto size = static_cast<std::size_t> (event.size - 2);
            if (! acceptsLiveSysEx (body, size)) continue;
            if (handleDeviceControlSysEx (body, size))
                changed = true;
            else
            {
                Patch patch = snapshotPatch();
                if (decodeLivePatchMessage (body, size, patch))
                {
                    writePatchToParameters (patch, true);
                    patchReconciler.triggerAsyncUpdate();
                    changed = true;
                }
            }
        }
        else if ((event.data[0] & 0xf0) == 0xb0
                 && (event.data[1] == 126 || event.data[1] == 127))
        {
            // The mode message's panic already occurred at its original
            // timestamp. Replay only its deferred parameter change, so a
            // later note is not killed a second time by draining the queue.
            Patch patch = snapshotPatch();
            patch.upper.mono = patch.lower.mono = event.data[1] == 126
                ? septum::MonoMode::SoloLegato : septum::MonoMode::Poly;
            writePatchToParameters (patch, true);
            patchReconciler.triggerAsyncUpdate();
            changed = true;
        }
        else
            changed = handleMidiMessage (juce::MidiMessage (
                event.data.data(), event.size, 0.0)) || changed;
    }
    return changed;
}

void SeptumAudioProcessor::processBlock (juce::AudioBuffer<float>& buffer,
                                             juce::MidiBuffer& midiMessages)
{
    juce::ScopedNoDenormals noDenormals;
    if (! prepared)
    {
        buffer.clear();
        midiMessages.clear();
        return;
    }

    const int clockSource = static_cast<int> (roundedParameter (
        clockSourceValue->load (std::memory_order_relaxed)));
    if (clockSource != appliedClockSource)
    {
        midiTempoClock.reset();
        appliedClockSource = clockSource;
    }
    hostTempoBpm = 0.0;
    if (appliedClockSource == 3)
        if (const auto* playHead = getPlayHead())
            if (const auto position = playHead->getPosition())
                if (const auto bpm = position->getBpm(); bpm && std::isfinite (*bpm) && *bpm > 0.0)
                    hostTempoBpm = *bpm;

    // Copy input immediately before rendering each bounded chunk. Output
    // only overwrites that chunk, leaving later input samples intact.
    const auto samples = buffer.getNumSamples();
    const int outputChannels = buffer.getNumChannels();
    const int inputChannels = std::min (getTotalNumInputChannels(), outputChannels);
    const bool haveExternalInput = inputChannels > 0 && samples > 0;

    const int midiChannel = static_cast<int> (roundedParameter (
        midiChannelValue->load (std::memory_order_relaxed)));
    if (midiChannel != appliedMidiChannel)
    {
        // Releases from the old channel will no longer reach us. Release its
        // keys and pedals before accepting another channel, preserving tails.
        engine.allNotesOff();
        resetPerformanceControllers();
        appliedMidiChannel = midiChannel;
    }
    if (activeSensingValue->load (std::memory_order_relaxed) < 0.5f)
        activeSensingArmed = false;

    const int remoteKeyboard = static_cast<int> (roundedParameter (remoteKeyboardValue->load()));
    if (remoteKeyboard != appliedRemoteKeyboard)
    {
        // A route change cannot leave releases addressed to the old input.
        engine.allNotesOff();
        resetPerformanceControllers();
        appliedRemoteKeyboard = remoteKeyboard;
    }

    drainDeferredParameterMidi();
    engine.setMasterLevel ((int) roundedParameter (
        masterValue->load (std::memory_order_relaxed)));
    applySystemSettings();

    // The engine's patch never depends on the message loop: MIDI program
    // changes write the raw values directly, and the snapshot is validated
    // against the message thread's write bursts (program sprays, state
    // restores) so a half-written mix is never rendered — the staged factory
    // patch or the previous block's patch covers the gap instead.
    const auto applyCurrentPatch = [this]
    {
        // The external-input block is not patch data, but CC#2 and CC#4 edit
        // it and arrive mid-block like any other mapped panel CC, so it is
        // refreshed on the same segment boundary rather than a block late —
        // and it is read *inside* the same seqlock the patch snapshot uses,
        // because a state restore writes both in one burst and a mixture of
        // old and new external settings is as torn as a mixed patch.
        const bool quietAtEntry = activePatchWriters.load (std::memory_order_acquire) == 0u;
        const auto generation = patchGeneration.load (std::memory_order_acquire);
        const auto selection = patchSelectionRevision.load (std::memory_order_acquire);
        const septum::ExternalInput external = snapshotExternalInput();
        const std::array<bool, 2> enabled {
            partEnableValues[0]->load (std::memory_order_relaxed) >= 0.5f,
            partEnableValues[1]->load (std::memory_order_relaxed) >= 0.5f
        };

        const auto stagedSelection = stagedProgram.load (std::memory_order_acquire);
        const int staged = static_cast<int> (stagedSelection & 127u) - 1;
        const bool stagedProgramPending =
            staged >= 0 && staged < (int) septum::factoryPatches().size()
            && (stagedSelection >> 7u) == selection;
        const septum::Patch snapshot =
            stagedProgramPending ? septum::Patch {} : snapshotPatch();

        // Otherwise a burst was in flight while the snapshots were read: keep
        // the previous values for this segment and pick up the completed ones
        // on the next.
        const bool stable = quietAtEntry && patchSnapshotStable (generation);
        if (stable)
        {
            engine.setExternalInput (external);
            engine.setPartEnabled (true, enabled[0]);
            engine.setPartEnabled (false, enabled[1]);
        }
        if (stagedProgramPending)
        {
            // The staged program is usable during the parameter spray, once
            // its selection revision is published. Do not reselect it on
            // every callback, which would turn current notes into old ones.
            if (selection != appliedPatchSelectionRevision)
            {
                engine.changePatch (septum::factoryPatches()[(std::size_t) staged].patch,
                    patchRemainValue->load (std::memory_order_relaxed) >= 0.5f);
                appliedPatchSelectionRevision = selection;
            }
        }
        else if (stable)
        {
            if (selection != appliedPatchSelectionRevision)
            {
                engine.changePatch (snapshot, patchRemainValue->load (std::memory_order_relaxed) >= 0.5f);
                appliedPatchSelectionRevision = selection;
            }
            else
                engine.setPatch (snapshot);
        }
    };
    applyCurrentPatch();
    applyTempoSource();

    // UI keyboard events.
    auto read = uiRead.load (std::memory_order_relaxed);
    const auto write = uiWrite.load (std::memory_order_acquire);
    while (read != write)
    {
        const auto& event = uiQueue[read % uiQueueCapacity];
        if (event.velocity > 0)
            engine.noteOn (event.note, event.velocity);
        else
            engine.noteOff (event.note);
        ++read;
    }
    uiRead.store (read, std::memory_order_release);

    // Under UI overload, the latest requested state for each note follows
    // the FIFO. Repeated states coalesce; notes are visited in pitch order.
    for (std::size_t word = 0; word < forcedRelease.size(); ++word)
    {
        auto bits = forcedRelease[word].exchange (0u, std::memory_order_acquire);
        while (bits != 0u)
        {
            const int note = (int) (word * 64) + std::countr_zero (bits);
            const int velocity = overflowUiVelocity[static_cast<std::size_t> (note)].load (std::memory_order_relaxed);
            if (velocity > 0)
                engine.noteOn (note, velocity);
            else
                engine.noteOff (note);
            bits &= bits - 1u;
        }
    }

    if (uiLeverDirty.exchange (false, std::memory_order_acquire))
    {
        engine.setPitchBend (uiBend.load (std::memory_order_relaxed));
        engine.setModulation (uiMod.load (std::memory_order_relaxed));
    }


    // Sample-accurate segmentation around MIDI events.
    int position = 0;
    const auto renderTo = [&] (int end)
    {
        while (position < end)
        {
            int count = std::min (end - position, static_cast<int> (monoScratch.size()));
            if (appliedClockSource == 2)
                count = midiTempoClock.samplesUntilTimeout (count);
            if (activeSensingArmed)
                count = static_cast<int> (std::min (
                    static_cast<std::uint64_t> (count), activeSensingSamplesRemaining));
            if (haveExternalInput)
            {
                std::copy_n (buffer.getReadPointer (0) + position, count, externalInputL.data());
                std::copy_n (buffer.getReadPointer (inputChannels > 1 ? 1 : 0) + position,
                             count, externalInputR.data());
            }
            // A host's zero-channel callback still advances MIDI, clocks and
            // releases. Render into scratch; never dereference channel zero.
            auto* left = outputChannels > 0 ? buffer.getWritePointer (0) + position : externalInputL.data();
            auto* right = outputChannels > 1 ? buffer.getWritePointer (1) + position : monoScratch.data();
            engine.process (left, right, count,
                            haveExternalInput ? externalInputL.data() : nullptr,
                            haveExternalInput ? externalInputR.data() : nullptr);
            if (outputChannels == 1)
                for (int i = 0; i < count; ++i)
                    left[i] = 0.5f * (left[i] + right[i]);
            position += count;
            if (appliedClockSource == 2)
            {
                midiTempoClock.advance (count);
                applyTempoSource();
            }
            if (activeSensingArmed)
            {
                activeSensingSamplesRemaining -= static_cast<std::uint64_t> (count);
                if (activeSensingSamplesRemaining == 0)
                {
                    engine.allSoundOff();
                    engine.allNotesOff();
                    resetPerformanceControllers();
                    activeSensingArmed = false;
                }
            }
        }
    };
    auto it = midiMessages.begin();
    while (it != midiMessages.end())
    {
        const auto metadata = *it;
        const int eventPosition =
            juce::jlimit (0, buffer.getNumSamples(), metadata.samplePosition);
        renderTo (eventPosition);

        if (! isValidLiveMidi (metadata))
        {
            ++it;
            continue;
        }
        const bool isSysEx = metadata.data[0] == 0xf0;
        // Only fixed-size short messages are materialized. A SysEx view
        // remains borrowed from the host's MidiBuffer throughout decoding.
        const auto message = isSysEx ? juce::MidiMessage (0xfe) : metadata.getMessage();
        if (! isSysEx)
            observeMidiActivity (message);
        else if (activeSensingArmed)
            activeSensingSamplesRemaining = activeSensingTimeoutSamples;
        if (appliedClockSource == 2 && message.isMidiClock())
        {
            midiTempoClock.pulse();
            applyTempoSource();
        }
        const auto applyDeferred = [&]
        {
            if (! drainDeferredParameterMidi()) return;
            engine.setMasterLevel (roundedParameter (masterValue->load (std::memory_order_relaxed)));
            applySystemSettings();
            applyCurrentPatch();
        };
        applyDeferred();
        std::optional<ParameterWriteAccess> parameterWrite;
        if (isParameterMidi (metadata.data))
        {
            // Parameter edits stay on the receive channel even with remote
            // keyboard enabled. Admit them before deferring or applying the
            // panic half of a mode message, at their original timestamp.
            const int channel = (metadata.data[0] & 0x0f) + 1;
            if (! isSysEx && appliedMidiChannel != 0 && channel != appliedMidiChannel)
            {
                ++it;
                continue;
            }
            parameterWrite.emplace (*this, ParameterWriteAccess::Mode::Audio);
            if (! *parameterWrite)
            {
                if (parameterWrite->shouldDefer())
                    deferParameterMidi (metadata.data, metadata.numBytes,
                                        parameterWrite->transactionAtEntry());
                // Mode changes include a panic, which retains its timestamp
                // even if changing the stored mode is deferred or rejected.
                if ((metadata.data[0] & 0xf0) == 0xb0
                    && (metadata.data[1] == 126 || metadata.data[1] == 127))
                    engine.allSoundOff();
                ++it;
                continue;
            }
            // The notification may have finished between the first drain
            // and acquiring this gate. Older edits must precede this one.
            applyDeferred();
        }
        if (isSysEx)
        {
            // Consecutive SysEx packets at this sample (such as multi-packet
            // patch dumps) share one atomic commit. A later timestamp must
            // return to the render loop first: batching it here would skip
            // the intervening audio and apply its changes too early.
            Patch livePatch = snapshotPatch();
            bool anyHandled = false;
            bool anyPatchDecoded = false;
            while (it != midiMessages.end())
            {
                const auto nextMeta = *it;
                if (! isValidLiveMidi (nextMeta) || nextMeta.data[0] != 0xf0
                    || juce::jlimit (0, samples, nextMeta.samplePosition)
                           != eventPosition)
                    break;
                const auto* rawData = nextMeta.data + 1;
                const auto rawSize = static_cast<std::size_t> (nextMeta.numBytes - 2);
                if (! acceptsLiveSysEx (rawData, rawSize))
                {
                    ++it;
                    continue;
                }
                if (handleDeviceControlSysEx (rawData, rawSize))
                {
                    anyHandled = true;
                }
                else if (decodeLivePatchMessage (rawData, rawSize, livePatch))
                {
                    anyHandled = true;
                    anyPatchDecoded = true;
                }
                ++it;
            }
            if (anyPatchDecoded)
            {
                writePatchToParameters (livePatch, true);
                patchReconciler.triggerAsyncUpdate();
            }
            if (anyHandled)
            {
                engine.setMasterLevel ((int) roundedParameter (
                    masterValue->load (std::memory_order_relaxed)));
                applySystemSettings();
                applyCurrentPatch();
            }
            continue;
        }

        if (handleMidiMessage (message))
        {
            // SYSTEM COMMON goes with it. The three Universal Realtime
            // device-control messages land on MASTER LEVEL, MASTER TUNE and
            // MASTER KEY SHIFT, and those were read once before this loop —
            // so one arriving mid-block did not take effect until the next
            // one, which in an offline render with a large buffer is an
            // arbitrarily long delay.
            engine.setMasterLevel ((int) roundedParameter (
                masterValue->load (std::memory_order_relaxed)));
            applySystemSettings();
            applyCurrentPatch();  // panel CC or program: next segment uses it
        }
        ++it;
    }
    renderTo (samples);

    for (int channel = 2; channel < outputChannels; ++channel)
        buffer.clear (channel, 0, samples);
    midiMessages.clear();

    activeVoices.store (engine.activeVoiceCount(), std::memory_order_relaxed);
    retainedReleaseSeconds.store (engine.retainedReleaseSeconds(), std::memory_order_relaxed);
    for (std::size_t part = 0; part < partActiveVoices.size(); ++part)
    {
        partActiveVoices[part].store (engine.activeVoiceCount (part == 0),
                                     std::memory_order_relaxed);
        partHeldVoices[part].store (engine.heldVoiceCount (part == 0),
                                   std::memory_order_relaxed);
    }
}

int SeptumAudioProcessor::getNumPrograms()
{
    return (int) septum::factoryPatches().size();
}

int SeptumAudioProcessor::getCurrentProgram()
{
    return currentProgram.load (std::memory_order_relaxed);
}

void SeptumAudioProcessor::setCurrentProgram (int index)
{
    if (index < 0 || index >= getNumPrograms())
        return;
    applyProgram (index);
}

void SeptumAudioProcessor::applyProgram (int index)
{
    if (index < 0 || index >= getNumPrograms())
        return;
    ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Host);
    if (! parameterWrite) return;
    const Patch& patch =
        septum::factoryPatches()[(std::size_t) index].patch;
    liveSysExRevision.fetch_add (1, std::memory_order_acq_rel);

    // The audio path renders this factory patch directly until every
    // parameter below has been written, so a block can never snapshot a
    // half-loaded program. The write scope guards the spray: a snapshot
    // that overlapped this spray in any way is discarded.
    PatchWriteScope patchWrite (*this);
    const auto selection = patchSelectionRevision.fetch_add (1, std::memory_order_release) + 1u;
    stagedProgram.store ((selection << 7u) | static_cast<std::uint64_t> (index + 1),
                          std::memory_order_release);
    currentProgram.store (index, std::memory_order_relaxed);
    presetIdentityRevision.fetch_add (1, std::memory_order_acq_rel);
    invalidateImportedArpeggioStyle();

    const auto apply = [this] (const juce::String& id, float natural)
    {
        if (auto* parameter = parameters.getParameter (id))
        {
            const auto& range = parameters.getParameterRange (id);
            parameter->setValueNotifyingHost (
                range.convertTo0to1 (range.snapToLegalValue (natural)));
        }
    };

    for (const bool upper : { true, false })
    {
        const TonePatch& tone = upper ? patch.upper : patch.lower;
        apply (upper ? "upper_enabled" : "lower_enabled", 1.0f);
        const juce::String prefix = upper ? "up_" : "lo_";
        for (const auto& binding : toneBindings())
            apply (prefix + binding.suffix, binding.get (tone));
    }
    for (const auto& binding : patchBindings())
        if (juce::String (binding.id) != "master_level")
            apply (binding.id, binding.get (patch));

    // Every parameter now matches the program; the audio path can go back to
    // snapshotting the APVTS.
    syncPatchShadows();
    // ParameterWriteAccess excludes conflicting MIDI edits from this whole
    // transaction, so the final values belong to one complete program.
    patchWrite.finish();
    stagedProgram.store (0, std::memory_order_release);
    liveSysExRevision.fetch_add (1, std::memory_order_release);
}

// The raw half: atomics only, no juce::String, no host notification. Safe on
// the audio thread, which is where a received SysEx patch dump arrives.
void SeptumAudioProcessor::writePatchToParameters (const septum::Patch& patch,
                                                   bool publishGrid) noexcept
{
    ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Audio);
    if (! parameterWrite) return;
    // This also receives individual streamed DT1 knob edits. They update
    // native patch data without changing the plug-in's independent mutes.
    PatchWriteScope patchWrite (*this);
    // Inside the guarded write with the parameters. Published outside it, a
    // state save could copy the old parameter values, then see and serialise
    // the new grid, and still pass its generation check — pairing one patch
    // revision's settings with another's grid.
    if (publishGrid)
        publishImportedArpeggioStyle (patch.arpeggio.style, patch.arpeggio.styleIndex);
    const auto& bindings = toneBindings();
    for (std::size_t i = 0; i < bindings.size(); ++i)
    {
        const float upperNatural = bindings[i].get (patch.upper);
        const float lowerNatural = bindings[i].get (patch.lower);
        // Into the parameter's own storage, which is what the engine
        // snapshots, and into the shadow, which is the republish's evidence
        // that this thread wrote at all.
        //
        // Raw first, shadow last — the order every audio-thread writer here
        // uses, `handleController` and the device-control store included. The
        // republish takes the shadow as a baseline before it reads the raw
        // value and re-seeds only when that baseline moves, so a shadow store
        // that lands is the signal the write is complete and the raw value is
        // safe to put back. Shadow first would raise that signal while the raw
        // value was still the old one, and the republish would then re-seed
        // with a value it had already published.
        upperValues[i]->store (upperNatural, std::memory_order_relaxed);
        lowerValues[i]->store (lowerNatural, std::memory_order_relaxed);
        upperShadow[i].store (upperNatural, std::memory_order_relaxed);
        lowerShadow[i].store (lowerNatural, std::memory_order_relaxed);
    }
    const auto& shared = patchBindings();
    for (std::size_t i = 0; i < shared.size(); ++i)
    {
        if (std::strcmp (shared[i].id, "master_level") == 0)
            continue;
        const float natural = shared[i].get (patch);
        patchValues[i]->store (natural, std::memory_order_relaxed);
        patchShadow[i].store (natural, std::memory_order_relaxed);   // shadow last
    }
    patchDirty.store (true, std::memory_order_release);
    patchWrite.finish();
}

// The message-thread half: republishes whatever the raw values now hold, with
// host and UI notification. Reached from the queued callback after a SysEx
// dump landed on the audio path, and directly from loadPatch.
void SeptumAudioProcessor::syncPatchShadows() noexcept
{
    if (upperShadow == nullptr)
        return;
    for (std::size_t i = 0; i < upperValues.size(); ++i)
    {
        upperShadow[i].store (upperValues[i]->load (std::memory_order_relaxed),
                              std::memory_order_relaxed);
        lowerShadow[i].store (lowerValues[i]->load (std::memory_order_relaxed),
                              std::memory_order_relaxed);
    }
    for (std::size_t i = 0; i < patchValues.size(); ++i)
        patchShadow[i].store (patchValues[i]->load (std::memory_order_relaxed),
                              std::memory_order_relaxed);
    patchDirty.store (false, std::memory_order_release);
}

void SeptumAudioProcessor::cancelPendingRepublishes() noexcept
{
    pendingProgram.store (-1, std::memory_order_release);
    syncPatchShadows();

    for (std::size_t i = 0; i < ccCache.size(); ++i)
        if (ccShadow != nullptr && ccCache[i].raw != nullptr)
            ccShadow[i].store (ccCache[i].raw->load (std::memory_order_relaxed),
                               std::memory_order_relaxed);
    for (auto& word : ccDirty)
        word.store (0u, std::memory_order_release);

    for (std::size_t i = 0; i < deviceControlCount; ++i)
        if (deviceControlValues[i] != nullptr)
            deviceControlShadow[i].store (
                deviceControlValues[i]->load (std::memory_order_relaxed),
                std::memory_order_relaxed);
    deviceControlDirty.store (0u, std::memory_order_release);
}

void SeptumAudioProcessor::republishPatchParameters()
{
    ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Notification);
    if (! parameterWrite) return;
    // Nothing to do unless the audio thread has actually written a dump. The
    // guard is what keeps a republish from putting the shadows back over a
    // program change or a preset load, both of which write the parameters
    // from this thread and never touch the shadows.
    if (! patchDirty.exchange (false, std::memory_order_acquire))
        return;

    const auto publish = [this] (const juce::String& id, std::atomic<float>* raw,
                                 std::atomic<float>& shadow)
    {
        if (raw == nullptr)
            return;
        auto* parameter = parameters.getParameter (id);
        if (parameter == nullptr)
            return;
        // Publish what the *raw* storage holds, not what the shadow holds.
        // Those differ whenever something moved the value after the dump did —
        // a knob, a host automation lane, a preset — and the raw storage is the
        // one the engine renders from, so it is the one the host and the panel
        // have to be told about. Publishing the shadow regardless put the
        // dump's value back over an edit and snapped the slider under the
        // player's hand.
        //
        // Skipping instead of publishing was the first attempt at that and it
        // was wrong in the other direction: the audio thread writes the shadow
        // and then the raw value, so a republish landing between those two
        // stores sees them differ and reads the audio thread's own half-done
        // write as a message-thread edit. It would skip, put the older value
        // back in the shadow, and consume `patchDirty` — and a binding in the
        // dump's last packet would then never be published at all. Publishing
        // the raw value is right in both cases and needs no guess about who
        // wrote it.
        // The shadow is read, never written, so the audio thread stays its
        // only writer on this path. Written here, a packet landing in the gap
        // was clobbered in both cells at once — the store put the old value
        // back in the shadow, `setValueNotifyingHost` put it back in the raw
        // storage, and the comparison below then saw nothing to recover.
        // Reading the baseline before the raw value keeps the newer of the
        // two in `natural` whichever way the interleaving falls.
        const float shadowAtEntry = shadow.load (std::memory_order_relaxed);
        const float natural = raw->load (std::memory_order_relaxed);
        parameter->setValueNotifyingHost (
            parameters.getParameterRange (id).convertTo0to1 (natural));
        // setValueNotifyingHost has just written the parameter's own storage
        // with the value read above. A packet that landed while it ran is
        // newer than that, and `patchDirty` is set again for the next pass —
        // but the engine reads this storage every block, so the newer value
        // goes back now rather than a frame from now. The audio thread stores
        // the raw value first and the shadow last, so a shadow that has moved
        // is a write that has fully landed; one that has not moved means the
        // value being published is nobody else's and stays put.
        const float newest = shadow.load (std::memory_order_relaxed);
        if (newest != shadowAtEntry)
            raw->store (newest, std::memory_order_relaxed);
    };
    const auto& bindings = toneBindings();
    for (std::size_t i = 0; i < bindings.size(); ++i)
    {
        publish ("up_" + juce::String (bindings[i].suffix), upperValues[i],
                 upperShadow[i]);
        publish ("lo_" + juce::String (bindings[i].suffix), lowerValues[i],
                 lowerShadow[i]);
    }
    const auto& shared = patchBindings();
    for (std::size_t i = 0; i < shared.size(); ++i)
        if (std::strcmp (shared[i].id, "master_level") != 0)
            publish (shared[i].id, patchValues[i], patchShadow[i]);
}

void SeptumAudioProcessor::loadPatch (const septum::Patch& patch)
{
    ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Host);
    if (! parameterWrite) return;
    loadPatchUnderWriteAccess (patch);
}

void SeptumAudioProcessor::loadPatchUnderWriteAccess (const septum::Patch& patch)
{
    liveSysExRevision.fetch_add (1, std::memory_order_acq_rel);
    PatchWriteScope patchWrite (*this);
    patchSelectionRevision.fetch_add (1, std::memory_order_release);
    for (const auto* id : { "upper_enabled", "lower_enabled" })
        parameters.getParameter (id)->setValueNotifyingHost (1.0f);

    // The arpeggio grid rides outside the parameter list, so writing the
    // parameters below is not enough to carry it. Both callers of this are
    // SysEx loads, and a `.syx` handed to the plug-in through the API has to
    // keep its grid for the same reason a dump arriving on the wire does.
    publishImportedArpeggioStyle (patch.arpeggio.style, patch.arpeggio.styleIndex);

    const auto& bindings = toneBindings();
    for (std::size_t i = 0; i < bindings.size(); ++i)
    {
        const float upVal = bindings[i].get (patch.upper);
        const float loVal = bindings[i].get (patch.lower);
        upperValues[i]->store (upVal, std::memory_order_relaxed);
        lowerValues[i]->store (loVal, std::memory_order_relaxed);

        const juce::String upId = "up_" + juce::String (bindings[i].suffix);
        const juce::String loId = "lo_" + juce::String (bindings[i].suffix);
        if (auto* param = parameters.getParameter (upId))
            param->setValueNotifyingHost (parameters.getParameterRange (upId).convertTo0to1 (upVal));
        if (auto* param = parameters.getParameter (loId))
            param->setValueNotifyingHost (parameters.getParameterRange (loId).convertTo0to1 (loVal));
    }
    const auto& shared = patchBindings();
    for (std::size_t i = 0; i < shared.size(); ++i)
    {
        if (std::strcmp (shared[i].id, "master_level") != 0)
        {
            const float pVal = shared[i].get (patch);
            patchValues[i]->store (pVal, std::memory_order_relaxed);
            if (auto* param = parameters.getParameter (shared[i].id))
                param->setValueNotifyingHost (parameters.getParameterRange (shared[i].id).convertTo0to1 (pVal));
        }
    }

    syncPatchShadows();
    patchWrite.finish();
    liveSysExRevision.fetch_add (1, std::memory_order_release);
}

void SeptumAudioProcessor::loadSysExData (const void* data, std::size_t sizeInBytes)
{
    if (data == nullptr || sizeInBytes == 0)
        return;
    std::vector<septum::NamedPatch> bank;
    if (septum::sysex::parseSyxBankFile (static_cast<const std::uint8_t*> (data),
                                         sizeInBytes, bank) && ! bank.empty())
    {
        loadPatch (bank.front().patch);
    }
    else
    {
        ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Host);
        if (! parameterWrite) return;
        septum::Patch single = snapshotPatch();
        if (septum::sysex::decodeSysExMessage (static_cast<const std::uint8_t*> (data),
                                               sizeInBytes, single))
        {
            loadPatchUnderWriteAccess (single);
        }
    }
}

std::vector<std::uint8_t> SeptumAudioProcessor::createSysExDataForCurrentPatch() const
{
    return septum::sysex::encodePatchToSyxBuffer (snapshotPatch(),
        septum::sysex::addrTemporaryPatch, static_cast<std::uint8_t> (
            roundedParameter (deviceIdValue->load (std::memory_order_relaxed)) - 1));
}

const juce::String SeptumAudioProcessor::getProgramName (int index)
{
    if (index < 0 || index >= getNumPrograms())
        return {};
    return septum::factoryPatches()[(std::size_t) index].name;
}

juce::String SeptumAudioProcessor::getCurrentPresetName() const
{
    const juce::ScopedLock lock (presetNameLock);
    return presetIdentityRevision.load (std::memory_order_acquire) == currentPresetNameRevision
               ? currentPresetName : juce::String {};
}

void SeptumAudioProcessor::setCurrentPresetName (const juce::String& name,
                                                std::uint64_t identityRevision)
{
    const juce::ScopedLock lock (presetNameLock);
    if (presetIdentityRevision.load (std::memory_order_acquire) != identityRevision)
        return;
    currentPresetName = name;
    currentPresetNameRevision = identityRevision;
}

juce::Result SeptumAudioProcessor::validatePresetState (const juce::ValueTree& state) const
{
    if (! state.isValid() || ! state.hasType (parameters.state.getType()))
        return juce::Result::fail ("This file is not a Septum preset.");

    double version = 0.0;
    if (! readPresetNumber (state["preset_format_version"], version)
        || version != nativePresetVersion)
        return juce::Result::fail ("This preset uses an unsupported file version.");

    double program = 0.0;
    if (! readPresetNumber (state["program"], program)
        || program != std::floor (program) || program < 0.0
        || program >= static_cast<double> (septum::factoryPatches().size()))
        return juce::Result::fail ("The preset contains an invalid program index.");

    if (state.getNumChildren() != getParameters().size())
        return juce::Result::fail ("The preset is incomplete or contains unsupported parameters.");

    juce::StringArray seen;
    for (const auto child : state)
    {
        const auto id = child["id"].toString();
        const auto* parameter = parameters.getParameter (id);
        if (! child.hasType ("PARAM") || child.getNumChildren() != 0
            || parameter == nullptr || seen.contains (id))
            return juce::Result::fail ("The preset contains an unknown or duplicated parameter: " + id);
        seen.add (id);

        double value = 0.0;
        const auto& range = parameter->getNormalisableRange();
        if (! readPresetNumber (child["value"], value)
            || value < range.start || value > range.end
            || std::abs (value - range.snapToLegalValue (static_cast<float> (value))) > 0.0001)
            return juce::Result::fail ("The preset contains an invalid value for " + parameter->getName (64) + ".");
    }

    if (state.hasProperty ("arpeggio_grid")
        || state.hasProperty ("arpeggio_grid_selector")
        || state.hasProperty ("arpeggio_grid_end_step"))
    {
        double selector = 0.0, endStep = 0.0;
        const auto& range = parameters.getParameterRange ("arp_style");
        if (! readPresetNumber (state["arpeggio_grid_selector"], selector)
            || selector != std::floor (selector) || selector < range.start || selector > range.end
            || ! readPresetNumber (state["arpeggio_grid_end_step"], endStep)
            || endStep != std::floor (endStep) || endStep < 1 || endStep > septum::arpeggioMaxSteps)
            return juce::Result::fail ("The preset contains invalid arpeggio pattern settings.");

        juce::MemoryOutputStream decoded;
        const auto expected = septum::sysex::sizeArpeggioPattern
                              * static_cast<std::size_t> (septum::arpeggioMaxRows);
        if (! juce::Base64::convertFromBase64 (decoded, state["arpeggio_grid"].toString())
            || decoded.getDataSize() != expected)
            return juce::Result::fail ("The preset's arpeggio pattern is damaged.");
        const auto* bytes = static_cast<const std::uint8_t*> (decoded.getData());
        for (std::size_t i = 0; i < expected; i += 2)
            if (bytes[i] > 0x0f || bytes[i + 1] > 0x0f
                || (bytes[i] * 16 + bytes[i + 1]) > 128)
                return juce::Result::fail ("The preset's arpeggio pattern contains invalid notes.");
    }
    return juce::Result::ok();
}

juce::Result SeptumAudioProcessor::savePresetToFile (const juce::File& file)
{
    if (file.getFileNameWithoutExtension().isEmpty() || file.isDirectory()
        || ! file.getParentDirectory().isDirectory())
        return juce::Result::fail ("Choose a preset filename in an existing folder.");

    const auto identityRevision = presetIdentityRevision.load (std::memory_order_acquire);
    juce::MemoryBlock data;
    getStateInformation (data);
    const auto xml = getXmlFromBinary (data.getData(), static_cast<int> (data.getSize()));
    if (xml == nullptr)
        return juce::Result::fail ("The current instrument state could not be saved.");

    auto state = juce::ValueTree::fromXml (*xml);
    const auto name = file.getFileNameWithoutExtension();
    state.setProperty ("preset_format_version", nativePresetVersion, nullptr);
    state.setProperty ("preset_name", name, nullptr);
    if (const auto result = validatePresetState (state); result.failed())
        return result;
    copyXmlToBinary (*state.createXml(), data);

    // Write beside the destination, close/flush, then replace it. An error
    // cannot truncate a previously saved preset or rename the active sound.
    juce::TemporaryFile temporary (file);
    {
        auto stream = temporary.getFile().createOutputStream();
        if (stream == nullptr || stream->failedToOpen())
            return juce::Result::fail ("Could not write to this folder. Choose another location.");
        if (! stream->write (data.getData(), data.getSize()))
            return juce::Result::fail ("The preset could not be written. Check available disk space.");
        stream->flush();
        if (stream->getStatus().failed())
            return juce::Result::fail ("The preset could not be saved: " + stream->getStatus().getErrorMessage());
    }
    if (! temporary.overwriteTargetFileWithTemporary())
        return juce::Result::fail ("Could not replace the preset file. Check its permissions or choose another name.");

    setCurrentPresetName (name, identityRevision);
    updateHostDisplay (ChangeDetails().withNonParameterStateChanged (true));
    return juce::Result::ok();
}

juce::Result SeptumAudioProcessor::loadPresetFromFile (const juce::File& file)
{
    if (! file.existsAsFile())
        return juce::Result::fail ("The selected preset file could not be found.");
    if (file.getSize() < 9 || file.getSize() > static_cast<juce::int64> (maximumPresetBytes))
        return juce::Result::fail ("The preset file is empty, damaged, or too large.");

    juce::MemoryBlock data;
    if (! file.loadFileAsData (data))
        return juce::Result::fail ("The preset file could not be read. Check its permissions.");
    // The host reader deliberately accepts old/truncated binary containers.
    // Files selected by the user must contain one complete native document.
    const auto* bytes = static_cast<const std::uint8_t*> (data.getData());
    if (data.getSize() < 9 || data.getSize() > maximumPresetBytes
        || static_cast<std::size_t> (juce::ByteOrder::littleEndianInt (bytes + 4)) != data.getSize() - 9
        || bytes[data.getSize() - 1] != 0
        || ! hasSafeStateXmlStructure (data.getData(), static_cast<int> (data.getSize())))
        return juce::Result::fail ("The preset file is damaged or is not in Septum format.");
    const auto xml = getXmlFromBinary (data.getData(), static_cast<int> (data.getSize()));
    if (xml == nullptr)
        return juce::Result::fail ("The selected file is not a readable Septum preset.");
    auto state = juce::ValueTree::fromXml (*xml);
    double storedVersion = 0.0;
    if (readPresetNumber (state["preset_format_version"], storedVersion)
        && (storedVersion == 1.0 || storedVersion == 2.0 || storedVersion == 3.0 || storedVersion == 4.0 || storedVersion == 5.0))
    {
        if (storedVersion == 1.0)
            addMissingMidiSettings (state);
        if (storedVersion <= 2.0)
            addMissingTempoSettings (state);
        if (storedVersion <= 3.0)
            addMissingBankSettings (state);
        if (storedVersion <= 4.0)
            addMissingRemoteSettings (state);
        addMissingRemainSettings (state);
        state.setProperty ("preset_format_version", nativePresetVersion, nullptr);
    }
    if (const auto result = validatePresetState (state); result.failed())
        return result;

    // Renaming a file also renames it in the instrument. Only reach the
    // existing host-state restore after all file content has been checked.
    state.setProperty ("preset_name", file.getFileNameWithoutExtension(), nullptr);
    copyXmlToBinary (*state.createXml(), data);
    setStateInformation (data.getData(), static_cast<int> (data.getSize()));
    updateHostDisplay (ChangeDetails().withProgramChanged (true).withNonParameterStateChanged (true));
    return juce::Result::ok();
}

void SeptumAudioProcessor::getStateInformation (
    juce::MemoryBlock& destinationData)
{
    if (auto state = parameters.copyState(); state.isValid())
    {
        // The value tree lags an audio-path program write until the message
        // thread reconciles it — which a headless host may never do.
        // Serializing the raw values instead makes saved state always match
        // what is audible. The tree copy is ours alone, so this is safe on any
        // thread; the copy seqlocks against the generation so it can never
        // interleave a program write's burst, pairing the program index with
        // values it does not describe.
        //
        // Read into a buffer and committed only once the generation has been
        // seen to hold still across the read. Writing straight into the tree
        // and retrying could not undo what a failed attempt had already put
        // there, and the last attempt used to write unconditionally as a "best
        // effort" — so a save racing a stream of dumps saved the spray in
        // flight, some bindings from before it and some from after, a patch
        // that never existed. Yielding between attempts buys a gap where the
        // writer leaves one; where it leaves none, the tree's own values stand.
        // They lag, but they are a patch somebody had.
        std::vector<float> values;
        std::vector<int> indices;
        for (int attempt = 0; attempt < 64; ++attempt)
        {
            const auto generation =
                patchGeneration.load (std::memory_order_acquire);
            if (activePatchWriters.load (std::memory_order_acquire) != 0u)
            {
                std::this_thread::yield();
                continue;
            }
            values.clear();
            indices.clear();
            for (int i = 0; i < state.getNumChildren(); ++i)
            {
                if (auto* raw = parameters.getRawParameterValue (
                        state.getChild (i).getProperty ("id").toString()))
                {
                    indices.push_back (i);
                    values.push_back (raw->load (std::memory_order_relaxed));
                }
            }
            const int program = currentProgram.load (std::memory_order_relaxed);
            const auto presetName = getCurrentPresetName();
            // Staged like the rest of it, into a tree of its own. A publish is
            // one store, so a read of the grid is always a whole grid — but
            // that only says it is not torn in itself. Written straight into
            // the session while the values waited for a verdict, an exhausted
            // save paired the tree's own settings, which lag, with a grid from
            // the attempt that had just been rejected: an old patch wearing a
            // newer patch's pattern. The values and the grid have to come from
            // the same reading or from neither.
            juce::ValueTree grid ("grid");
            writeImportedArpeggioToState (grid);
            if (! patchSnapshotStable (generation))
            {
                std::this_thread::yield();
                continue;
            }
            for (std::size_t v = 0; v < indices.size(); ++v)
                state.getChild (indices[v])
                    .setProperty ("value", values[v], nullptr);
            state.setProperty ("program", program, nullptr);
            if (presetName.isNotEmpty())
                state.setProperty ("preset_name", presetName, nullptr);
            else
                state.removeProperty ("preset_name", nullptr);
            // Absent means the read found no grid to save, which is the
            // instruction to drop one the restored tree may still carry.
            for (const auto* key : { "arpeggio_grid", "arpeggio_grid_selector",
                                     "arpeggio_grid_end_step" })
            {
                const juce::Identifier property (key);
                if (grid.hasProperty (property))
                    state.setProperty (property, grid[property], nullptr);
                else
                    state.removeProperty (property, nullptr);
            }
            break;
        }
        if (const auto xml = state.createXml())
            copyXmlToBinary (*xml, destinationData);
    }
}

void SeptumAudioProcessor::setStateInformation (const void* data,
                                                    int sizeInBytes)
{
    if (data == nullptr || sizeInBytes < 9
        || static_cast<std::size_t> (sizeInBytes) > maximumPresetBytes
        || ! hasSafeStateXmlStructure (data, sizeInBytes))
        return;
    if (const auto xml = getXmlFromBinary (data, sizeInBytes))
    {
        auto state = juce::ValueTree::fromXml (*xml);
        if (state.isValid() && state.hasType (parameters.state.getType()))
        {
            if (state.hasProperty ("preset_format_version"))
            {
                double version = 0.0;
                if (! readPresetNumber (state["preset_format_version"], version)
                    || version < 1 || version > nativePresetVersion
                    || version != std::floor (version))
                    return;
            }
            addMissingMidiSettings (state);
            addMissingTempoSettings (state);
            addMissingBankSettings (state);
            addMissingRemoteSettings (state);
            addMissingRemainSettings (state);
            // Older sessions omitted the extensions. Insert explicit ON
            // values so restoring over a currently muted instance is safe.
            for (const auto* id : { "upper_enabled", "lower_enabled" })
                if (! state.getChildWithProperty ("id", id).isValid())
                {
                    juce::ValueTree parameterState ("PARAM");
                    parameterState.setProperty ("id", id, nullptr);
                    parameterState.setProperty ("value", 1.0f, nullptr);
                    state.addChild (parameterState, -1, nullptr);
                }
            // Host state is an untrusted binary document too. Validate the
            // migrated tree before replacing any live parameter: a wrong
            // root, duplicate ID, nonfinite value or malformed pattern must
            // leave the previous sound intact.
            state.setProperty ("preset_format_version", nativePresetVersion, nullptr);
            if (! state.hasProperty ("program"))
                state.setProperty ("program", 0, nullptr);
            if (validatePresetState (state).failed())
                return;
            ParameterWriteAccess parameterWrite (*this, ParameterWriteAccess::Mode::Host);
            if (! parameterWrite) return;
            // A state restore is a multi-parameter write burst like a
            // program spray: keep its writer guard active so the audio
            // thread discards any snapshot that overlapped it.
            liveSysExRevision.fetch_add (1, std::memory_order_acq_rel);
            PatchWriteScope patchWrite (*this);
            patchSelectionRevision.fetch_add (1, std::memory_order_release);
            currentProgram.store (state.getProperty ("program", 0),
                                  std::memory_order_relaxed);
            const auto identityRevision = presetIdentityRevision.fetch_add (1, std::memory_order_acq_rel) + 1;
            setCurrentPresetName (state.getProperty ("preset_name").toString(), identityRevision);
            // The explicit host transaction wins over older queued edits and
            // conflicting MIDI parameter writes. Notes and pedal releases
            // remain immediate; the audio thread never waits for this load.
            cancelPendingRepublishes();
            parameters.replaceState (state);
            // JUCE bool parameters may retain a fractional normalized host
            // value while APVTS already holds the same canonical 0/1. In that
            // case replaceState skips the setter. Republish validated natural
            // values to synchronize the parameter objects as well as APVTS.
            for (int index = 0; index < state.getNumChildren(); ++index)
            {
                const auto child = state.getChild (index);
                if (auto* parameter = parameters.getParameter (child.getProperty ("id").toString()))
                    parameter->setValueNotifyingHost (parameter->convertTo0to1 (
                        static_cast<float> (child.getProperty ("value"))));
            }
            readImportedArpeggioFromState (state);
            patchWrite.finish();
            liveSysExRevision.fetch_add (1, std::memory_order_release);
        }
    }
}

juce::AudioProcessorEditor* SeptumAudioProcessor::createEditor()
{
    return new SeptumAudioProcessorEditor (*this);
}

// This creates new instances of the plugin.
juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new SeptumAudioProcessor();
}

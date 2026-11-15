// U9 parameter-extremes matrix over the plug-in processor, through the shared
// portfolio harness (Tests/ParameterMatrix.h is a byte-identical copy of the
// master; change it in reason-rack-extensions).
//
//   SeptumParameterMatrixTests [--jobs N] [--rotation] [--shard K/N]
//                              [--case LABEL] [--count] [--list]
//   SeptumParameterMatrixTests --reach [--jobs N] [--case PARAMETER]
//
// The shared command line (U9): --rotation runs each case at one rate and
// block size instead of all nine, --shard K/N runs the cases whose index
// modulo N is K (numbered from 0), --case runs only the case a FAIL line
// names (its label, e.g. "preset 4 Upper Amp Env R=1"), and --count and
// --list print the cases and parameters. --reach runs the U11 reach test
// (Septum.ParameterReach) instead, over every parameter including the
// editor-only ones, with the rules ReachFor below states.

#include "PluginProcessor.h"
#include "ParameterMatrix.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <initializer_list>
#include <map>
#include <cstdlib>
#include <string>
#include <utility>
#include <vector>

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
        // The reach test's numbering: the automatable parameters, then the
        // editor-only ones, each in the processor's order (JuceDevice's).
        for (const bool host : { true, false })
            for (auto* parameter : processor->getParameters())
                if (parameter->isAutomatable() == host)
                    if (auto* ranged = dynamic_cast<juce::RangedAudioParameter*> (parameter))
                        reachParameters.push_back ({ ranged->paramID.toStdString(), ranged });
        if (reachParameters.size() != static_cast<std::size_t> (processor->getParameters().size()))
        {
            std::fprintf (stderr, "a parameter is not a RangedAudioParameter\n");
            std::abort();
        }
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

    // U11. Everything not named here must audibly reach the chord held
    // through the change as well as the chords after it. The base patch is
    // INIT PATCH: SINGLE on the UPPER tone, OSC1 alone, the effects off and
    // every LFO depth at zero, so most parameters are heard on the first
    // factory preset that makes them audible, and those no preset sounds
    // are heard with the settings `with` names.
    protocodus::matrix::ReachRule ReachFor (std::size_t index, float value) const override
    {
        using protocodus::matrix::Reach;
        const std::string& id = reachParameters[index].first;
        const bool tone = id.rfind ("up_", 0) == 0 || id.rfind ("lo_", 0) == 0;
        const std::string part = tone ? id.substr (0, 3) : std::string();
        const std::string name = tone ? id.substr (3) : id;
        const bool lower = part == "lo_";
        const auto is = [&] (std::initializer_list<const char*> names)
        {
            return std::any_of (names.begin(), names.end(), [&] (const char* n) { return name == n; });
        };
        // `with` entries in the parameters' own units (a choice by its index).
        const auto set = [this] (Settings settings, const std::string& other, float natural)
        {
            const auto& [otherIndex, parameter] = find (other);
            settings.push_back ({ otherIndex, parameter->convertTo0to1 (natural) });
            return settings;
        };
        // The lower tone alone, as SINGLE with KEYBOARD PART LOWER plays it:
        // the base patch sounds only the upper one.
        const Settings alone = lower ? set ({}, "keyboard_part", 1.0f) : Settings {};
        const auto own = [&] (Settings settings, const char* suffix, float natural)
        {
            return set (std::move (settings), part + suffix, natural);
        };

        // -- Stored, never read ------------------------------------------
        // The four D Beam bytes and the two PITCH WIDE switches are settled
        // patch data the replica saves and round-trips through SysEx but
        // never reads (PatchBinding::inert, ToneBinding::inert), published
        // as editor-only so a host offers no lane for them.
        if (is ({ "dbeam_dest", "dbeam_assign", "dbeam_polarity", "active_expression" }))
            return rule (Reach::Exempt, "a D Beam byte, stored for SysEx but read by nothing that sounds: the replica has "
                         "no D Beam (Septum.PluginProcessor round-trips it)");
        if (is ({ "osc1_wide", "osc2_wide" }))
            return rule (Reach::Exempt, "PITCH WIDE is stored for SysEx but never read: PITCH already spans +/-36 "
                         "(Septum.PluginProcessor round-trips it)");

        // -- What the phrase does not send ----------------------------------
        // The external-input block filters and mixes the INPUT jacks'
        // signal, and the reach test plays with the input bus off, as the
        // plug-in loads.
        if (is ({ "ext_input_vol", "ext_center_cancel", "audio_filter_on", "audio_filter_type",
                  "audio_filter_slope", "audio_filter_cutoff", "audio_filter_reso" }))
            return rule (Reach::Exempt, "acts on the external input, which the phrase does not feed "
                         "(Septum.Engine and Septum.ControlSmoothing drive it)");
        if (is ({ "mod_assign", "mod_dest" }))
            return rule (Reach::Exempt, "what the modulation lever modulates, and on which tone; the phrase does not "
                         "move the lever (Septum.Engine moves it)");
        if (name == "expr_dest")
            return rule (Reach::Exempt, "which tones the expression pedal reaches; the phrase sends no expression "
                         "(Septum.Engine checks it)");
        if (name == "system_receive_program")
            return rule (Reach::Exempt, "whether a program change is obeyed; the phrase sends none "
                         "(Septum.MidiBankProcessor checks it)");
        if (name == "system_receive_bank")
            return rule (Reach::Exempt, "whether a bank select is obeyed; the phrase sends none "
                         "(Septum.MidiBankProcessor checks it)");
        if (name == "system_device_id")
            return rule (Reach::Exempt, "which SysEx device ID is answered; the phrase sends no SysEx "
                         "(Septum.PluginProcessor checks it)");
        if (name == "system_active_sensing")
            return rule (Reach::Exempt, "whether a lapse of active sensing silences the notes; the phrase sends no "
                         "active sensing (Septum.PluginProcessor checks it)");
        if (name == "system_patch_remain")
            return rule (Reach::Exempt, "whether sounding notes keep their patch across a program change; the phrase "
                         "changes no program (Septum.PatchRemain and Septum.PatchRemainProcessor check it)");
        // REMOTE takes keyboard notes on every channel, CHANNEL on the
        // receive channel alone, and the phrase plays on the receive
        // channel. DIRECT bypasses the arpeggiator, so it is heard with the
        // arpeggiator on.
        if (name == "system_remote_keyboard")
        {
            if (value > 0.25f && value < 0.75f)
                return rule (Reach::Exempt, "REMOTE also takes notes on other channels; the phrase plays on the receive "
                             "channel (Septum.RemoteKeyboardProcessor checks it)");
            return rule (Reach::Held, "", set ({}, "arp_on", 1.0f));
        }

        // -- Tempo and the arpeggiator ---------------------------------------
        // No factory preset runs the arpeggiator, so the tempo and every
        // arpeggio setting are heard with it playing the base patch.
        const Settings arpeggio = set ({}, "arp_on", 1.0f);
        if (is ({ "arp_hold", "arp_style", "arp_grid", "arp_duration", "arp_octave", "patch_tempo" }))
            return rule (Reach::Held, "", arpeggio);
        // END STEP is heard where the pattern ends: STRAIGHT 4 (the base
        // style) at 300 BPM ends every 0.2 s, and END STEP 32 rests on its
        // steps 5-32 instead of starting over.
        if (name == "arp_end_step")
            return rule (Reach::Held, "", set (arpeggio, "patch_tempo", 300.0f));
        // MOTIF walks a window of the style's rows over the keys held, one
        // step of it each pass of the pattern (mapping::arpeggioKeyIndexForRow),
        // so on STRAIGHT 4 every UP and UP&DOWN motif plays a chord of four
        // keys or fewer alike. SIXTEENTH PULSE has one row, and END STEP 1
        // makes each of its steps a pass. The RANDOM motifs draw each pass's
        // window from the arpeggiator's random stream, which advances only
        // while a RANDOM motif plays.
        if (name == "arp_motif")
            return rule (Reach::Held, "", set (set (arpeggio, "arp_style", 4.0f), "arp_end_step", 1.0f),
                         value > 0.75f && value < 0.95f
                             ? "each pass's RANDOM window comes from a stream T has drawn from since 0 s"
                             : "");
        // ACCENT and VELOCITY set the velocity of each note the arpeggiator
        // plays, heard where the level and the cutoff follow the velocity,
        // eight notes to the held chord at 300 BPM.
        if (is ({ "arp_accent", "arp_velocity" }))
        {
            Settings velocity = set (arpeggio, "patch_tempo", 300.0f);
            for (const auto& [setting, natural] : { std::pair { "up_level_vel", 63.0f },
                                                    std::pair { "up_cutoff_vel", 63.0f },
                                                    std::pair { "up_cutoff", 40.0f } })
                velocity = set (std::move (velocity), setting, natural);
            return rule (Reach::Held, "", std::move (velocity));
        }
        // SPLIT ARPEGGIO chooses the side of the split the arpeggiator
        // plays; a split at E4 puts the probes' G3 on the lower side and
        // their E4 and C5 on the upper.
        if (name == "arp_split")
            return rule (Reach::Held, "", set (set (arpeggio, "keyboard_mode", 2.0f), "split_point", 64.0f));
        if (name == "system_tempo")
            return rule (Reach::Held, "", set (arpeggio, "system_clock_source", 1.0f));
        if (name == "system_clock_source")
        {
            // With no host play head, as here, HOST falls back to the patch
            // tempo (SeptumAudioProcessor::processBlock).
            if (value > 0.9f)
                return rule (Reach::Exempt, "HOST follows the host's tempo, and with no play head it keeps the patch's "
                             "(Septum.TempoSyncProcessor checks it against one)");
            // SYSTEM plays at SYSTEM TEMPO (120) and MIDI waits for a clock,
            // so the patch's own tempo is set apart from 120.
            return rule (Reach::Held, "", set (arpeggio, "patch_tempo", 60.0f));
        }

        // -- Routing at the key ----------------------------------------------
        // Engine::noteOn routes each key to a tone when it is struck, and a
        // held key keeps sounding the tone it was struck on: Engine::noteOff
        // releases it from either tone, because these three are automatable
        // under held keys.
        if (is ({ "keyboard_mode", "keyboard_part", "split_point" }))
            return rule (Reach::NewNotes, "which tone the keys struck after it play; a held key keeps its tone");
        // POLY or SOLO is a voice count: Engine::startNoteForPart assigns
        // each new key, and the held chord keeps the voices it has.
        if (name == "mono_mode")
            return rule (Reach::NewNotes, "the voice count the keys struck after it are given");
        // The held chord is not bent; the probes are. Triggering a voice
        // starts its glide (Engine::triggerVoice); a held note has arrived.
        // Both retune the free-running oscillators, so on the first factory
        // preset with a lower tone (C-1, two detuned oscillators) the later
        // chords beat in the phase the old pitch left; the lower tone is
        // heard alone on the base patch's single oscillator instead, as the
        // upper one is.
        if (is ({ "bend_range", "bend_dest" }))
            return rule (Reach::NewNotes, "the next bend; the held chord is not bent", alone);
        if (name == "portamento")
            return rule (Reach::NewNotes, "a glide into each new note", alone);
        // No factory preset glides the lower tone.
        if (name == "porta_time" && lower)
            return rule (Reach::NewNotes, "a glide into each new note", own (alone, "portamento", 1.0f),
                         "each voice glides from wherever the glides before left it");

        // -- Envelope segments a held note has passed --------------------------
        // Envelope::configure retimes the segment a sounding voice is in;
        // the held chord, struck half a second before the change, is past
        // these.
        if (is ({ "aenv_attack", "fenv_attack" }))
            return rule (Reach::NewNotes, "an attack: the rise from a note's onset, which the held chord has finished");
        if (name == "aenv_decay")
            return rule (Reach::NewNotes, "a decay the held chord has finished");
        // The pitch envelope bends only a note's onset (PitchEnvelope: up
        // over A, down over D to rest); the held chord's is at rest. Each
        // depth is heard on its own oscillator with a DECAY of 64 (0.16 s to
        // rest), long enough to hear the sweep that the base patch's DECAY 0
        // ends as soon as it peaks. No factory preset bends the lower tone's
        // pitch, so its A and D are heard with OSC1 PITCH ENV DEPTH set, and
        // from DECAY 0 the held chord's envelope has ended.
        if (is ({ "osc1_penv_depth", "osc2_penv_depth" }))
            return rule (Reach::NewNotes, "the pitch envelope of a note's onset; the held chord's is at rest",
                         own (own (alone, "balance", name == "osc1_penv_depth" ? -63.0f : 63.0f), "penv_decay", 64.0f));
        if (name == "penv_attack")
            return rule (Reach::NewNotes, "an attack: the rise from a note's onset, which the held chord has finished",
                         lower ? own (alone, "osc1_penv_depth", 63.0f) : Settings {});
        if (name == "penv_decay" && lower)
            return rule (Reach::NewNotes, "a decay the held chord has finished", own (alone, "osc1_penv_depth", 63.0f));

        // -- The lower tone where no factory preset sounds it ------------------
        // SYNC restarts OSC1 at each OSC2 cycle and RING replaces OSC1 with
        // the product, both heard through the base patch's OSC1, and C-1's
        // OSC1 DETUNE beats its two oscillators as the bend does above.
        if (lower && is ({ "mix_type", "osc1_detune" }))
            return rule (Reach::Held, "", alone);
        if (lower && name == "osc2_pw") // PW-SQU, OSC2 alone
            return rule (Reach::Held, "", own (own (alone, "balance", 63.0f), "osc2_wave", 2.0f));
        if (lower && name == "drive")
            return rule (Reach::Held, "", own (alone, "overdrive", 1.0f));
        // A filter envelope opening a low cutoff, and an amp release long
        // enough to hear it close.
        if (lower && name == "fenv_release")
            return rule (Reach::Held, "", own (own (own (alone, "cutoff", 30.0f), "fenv_depth", 63.0f), "aenv_release", 80.0f));

        // -- LFOs ---------------------------------------------------------------
        // The factory LFOs either sit at depth zero or ride presets whose
        // delay, reverb and feedback oscillators carry the playing before the
        // change into every later chord, so each LFO setting is heard with
        // its LFO at full depth on the base patch: destination 1 sweeping a
        // half-open filter, destination 2 on the level of OSC2 alone.
        for (const char* lfo : { "lfo1_", "lfo2_" })
        {
            const std::string l = lfo;
            if (name.rfind (l, 0) != 0 || is ({ "lfo1_depth1", "lfo1_depth2", "lfo2_depth1", "lfo2_depth2" }))
                continue;
            const std::string setting = name.substr (l.size());
            Settings sweep = own (own (alone, (l + "depth1").c_str(), 63.0f), "cutoff", 64.0f);
            if (setting == "dest1") // PW1 needs a pulse to modulate
                return rule (Reach::Held, "", own (std::move (sweep), "osc1_wave", 2.0f));
            if (setting == "dest2") // PITCH2, PW2 or AMP, each heard on OSC2 alone
                return rule (Reach::Held, "",
                             own (own (own (alone, (l + "depth2").c_str(), 63.0f), "balance", 63.0f), "osc2_wave", 2.0f));
            if (setting == "sync_note")
                sweep = own (std::move (sweep), (l + "sync").c_str(), 1.0f);
            // FADE TIME fades the LFO in from a note's onset; KEY TRIGGER
            // restarts its cycle at each key struck, and a held note's runs on
            // in the phase it shares with the free-running LFO
            // (Engine::updateVoiceControls keeps the two aligned).
            if (setting == "fade")
                return rule (Reach::NewNotes, "the LFO's fade-in from a note's onset, which the held chord has finished",
                             std::move (sweep));
            if (setting == "key_trig")
                return rule (Reach::NewNotes, "where the LFO cycle of each key struck after it starts", std::move (sweep));
            return rule (Reach::Held, "", std::move (sweep));
        }

        // -- The reverb's damping -----------------------------------------------
        // The base patch's reverb is off; HF DAMP FREQ is heard only below
        // 0 dB of HF DAMP GAIN.
        if (name == "reverb_hf_damp_gain")
            return rule (Reach::Held, "", set (set ({}, "reverb_on", 1.0f), "up_reverb_depth", 127.0f));
        if (name == "reverb_hf_damp_freq")
            return rule (Reach::Held, "",
                         set (set (set ({}, "reverb_on", 1.0f), "up_reverb_depth", 127.0f), "reverb_hf_damp_gain", -36.0f));
        return rule (Reach::Held);
    }

private:
    struct Column { std::size_t index; juce::RangedAudioParameter* parameter; };

    using Settings = std::vector<std::pair<std::size_t, float>>;

    static protocodus::matrix::ReachRule rule (protocodus::matrix::Reach reach, std::string reason = {},
                                               Settings with = {}, std::string history = {})
    {
        protocodus::matrix::ReachRule made;
        made.reach = reach;
        made.reason = std::move (reason);
        made.with = std::move (with);
        made.history = std::move (history);
        return made;
    }

    // A parameter by ID, in the reach test's numbering.
    std::pair<std::size_t, juce::RangedAudioParameter*> find (const std::string& id) const
    {
        for (std::size_t i = 0; i < reachParameters.size(); ++i)
            if (reachParameters[i].first == id)
                return { i, reachParameters[i].second };
        std::fprintf (stderr, "no parameter %s\n", id.c_str());
        std::abort();
    }

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
    std::vector<std::pair<std::string, juce::RangedAudioParameter*>> reachParameters;
};
} // namespace

int main (int argc, char** argv)
{
    juce::ScopedJuceInitialiser_GUI juce;
    return protocodus::matrix::Main (argc, argv, [] { return std::make_unique<SeptumDevice>(); });
}

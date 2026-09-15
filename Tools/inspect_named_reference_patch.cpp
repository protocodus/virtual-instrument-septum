// Analysis-only decoder for inventory_static_filter_references.py.
// Input is the unchanged common/Upper/Lower/delay/reverb blocks concatenated.
#include "SeptumSysEx.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>

template <typename T> void field (const char* name, T value)
{
    std::cout << '\"' << name << "\":" << static_cast<int> (value) << ',';
}
#define FIELD(object, member) field (#member, object.member)

void oscillator (const septum::OscParams& o)
{
    std::cout << '{';
    FIELD(o, wave); FIELD(o, pitchWide); FIELD(o, coarse); FIELD(o, fine);
    FIELD(o, pulseWidth); FIELD(o, pitchEnvDepth);
    std::cout << "\"decoded_by_current_codec\":true}";
}

void lfo (const septum::LfoParams& l)
{
    std::cout << '{';
    FIELD(l, shape); FIELD(l, rate); FIELD(l, tempoSync); FIELD(l, tempoSyncNote);
    FIELD(l, fadeTime); FIELD(l, keyTrigger); FIELD(l, destination1);
    FIELD(l, depth1); FIELD(l, destination2); FIELD(l, depth2);
    std::cout << "\"decoded_by_current_codec\":true}";
}

void tone (const septum::TonePatch& t)
{
    std::cout << '{';
    FIELD(t, pitchEnvAttack); FIELD(t, pitchEnvDecay); FIELD(t, mixType);
    FIELD(t, balance); FIELD(t, lowFreq); FIELD(t, filterType); FIELD(t, filterSlope);
    FIELD(t, cutoff); FIELD(t, keyFollow); FIELD(t, cutoffVelocitySens);
    FIELD(t, resonance); FIELD(t, filterEnvAttack); FIELD(t, filterEnvDecay);
    FIELD(t, filterEnvSustain); FIELD(t, filterEnvRelease); FIELD(t, filterEnvDepth);
    FIELD(t, overdrive); FIELD(t, drive); FIELD(t, level); FIELD(t, levelVelocitySens);
    FIELD(t, pan); FIELD(t, ampEnvAttack); FIELD(t, ampEnvDecay);
    FIELD(t, ampEnvSustain); FIELD(t, ampEnvRelease); FIELD(t, delayDepth);
    FIELD(t, reverbDepth); FIELD(t, bendRange); FIELD(t, octaveShift);
    FIELD(t, portamento); FIELD(t, portamentoTime); FIELD(t, mono);
    std::cout << "\"osc1\":"; oscillator (t.osc1);
    std::cout << ",\"osc2\":"; oscillator (t.osc2);
    std::cout << ",\"lfo1\":"; lfo (t.lfo1);
    std::cout << ",\"lfo2\":"; lfo (t.lfo2);
    std::cout << '}';
}

int main (int argc, char** argv)
{
    if (argc != 2) return 2;
    std::ifstream input (argv[1], std::ios::binary);
    std::vector<std::uint8_t> bytes { std::istreambuf_iterator<char> (input), {} };
    if (bytes.size() != 33 + 64 + 64 + 5 + 10) return 3;
    septum::Patch p;
    septum::sysex::decodePatchCommon (bytes.data(), 33, p);
    septum::sysex::decodeTonePatch (bytes.data() + 33, 64, p.upper);
    septum::sysex::decodeTonePatch (bytes.data() + 97, 64, p.lower);
    septum::sysex::decodeDelayParams (bytes.data() + 161, 5, p.delay);
    septum::sysex::decodeReverbParams (bytes.data() + 166, 10, p.reverb);
    std::cout << '{';
    FIELD(p, keyboardMode); FIELD(p, keyboardPart); FIELD(p, splitPoint);
    FIELD(p, patchLevel); FIELD(p, toneBalance); FIELD(p, tempo);
    FIELD(p, delayOn); FIELD(p, reverbOn); FIELD(p, modulationAssign);
    FIELD(p, modulationDestination); FIELD(p, pitchBendDestination);
    field ("arpeggioOn", p.arpeggio.on);
    field ("delayTime", p.delay.time); field ("delayFeedback", p.delay.feedback);
    field ("delayModulationDepth", p.delay.modulationDepth);
    field ("reverbPreDelay", p.reverb.preDelay);
    std::cout << "\"upper\":"; tone (p.upper);
    std::cout << ",\"lower\":"; tone (p.lower);
    std::cout << "}\n";
}

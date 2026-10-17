// Renders one README demo per factory preset (README G3) from the committed
// phrases in Docs/audio/midi, through the same JUCE-free engine the plug-in
// runs. The contract and the fixed rate, block size and seed live in the
// shared PresetDemoRenderer.h.

#include "DSP/SeptumEngine.h"
#include "DSP/SeptumPresets.h"
#include "PresetDemoRenderer.h"

#include <stdexcept>
#include <string>

namespace
{
// The 32 PRESET A-1..D-8 programs; the User slots after them are INIT copies.
constexpr std::size_t presetCount = 32;
// One MASTER LEVEL for every preset, so the demos keep the bank's own level
// differences; nothing is normalised per preset. At the plug-in's full-scale
// default, Space Choir, Space Drone and PWM Strings drive the output stage's
// safety knee (mapping::outputLimitKnee) and peak above 0 dBFS, which a 24-bit
// demo file would clip. At 80 every preset stays under full scale, with
// Space Choir about 0.1 dB below it.
constexpr int masterLevel = 80;

class SeptumVoice final : public protocodus::demos::Voice
{
public:
    SeptumVoice (const septum::Patch& patch, double sampleRate, int maxBlockFrames)
        : engine (std::make_unique<septum::Engine>())
    {
        engine->prepare (sampleRate, maxBlockFrames);
        engine->setMasterLevel (masterLevel);
        engine->setPatch (patch);
        engine->reset();
    }

    // The plug-in's default REMOTE KEYBOARD setting (CHANNEL) plays MIDI
    // through the keyboard path, as the processor's noteOn does. Anything a
    // phrase sends beyond these is an error, not a silently dropped event.
    void Midi (const std::uint8_t* bytes, int size) override
    {
        const int kind = bytes[0] & 0xf0;
        const int data1 = size > 1 ? bytes[1] : 0, data2 = size > 2 ? bytes[2] : 0;
        if (kind == 0x80 || (kind == 0x90 && data2 == 0)) engine->noteOff (data1);
        else if (kind == 0x90) engine->noteOn (data1, data2);
        else if (kind == 0xe0) engine->setPitchBend (((data2 << 7) | data1) / 8192.0 - 1.0);
        else if (kind == 0xb0 && data1 == 1) engine->setModulation (data2 / 127.0);
        else if (kind == 0xb0 && data1 == 64) engine->setHold (data2 >= 64);
        else throw std::runtime_error ("unsupported MIDI message " + std::to_string (bytes[0])
                                       + " " + std::to_string (data1));
    }

    void Render (float* left, float* right, int frames) override
    {
        engine->process (left, right, frames);
    }

private:
    std::unique_ptr<septum::Engine> engine;
};
} // namespace

int main (int argc, char** argv)
{
    const auto& bank = septum::factoryPatches();
    if (bank.size() < presetCount)
        return 1;

    protocodus::demos::Instrument instrument;
    instrument.name = "Septum";
    // Program names are "A-1: SuperLead201"; the demo names the preset.
    for (std::size_t i = 0; i < presetCount; ++i)
    {
        const auto& name = bank[i].name;
        const auto colon = name.find (": ");
        instrument.presets.push_back (colon == std::string::npos ? name : name.substr (colon + 2));
    }
    instrument.open = [&bank] (std::size_t preset, double sampleRate, int maxBlockFrames, std::uint32_t)
    {
        // The engine seeds its own random sources in prepare().
        return std::make_unique<SeptumVoice> (bank[preset].patch, sampleRate, maxBlockFrames);
    };
    return protocodus::demos::Main (argc, argv, instrument);
}

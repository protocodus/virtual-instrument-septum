// U8 input fuzzing of the JUCE-free engine and SysEx boundary, through the
// shared portfolio harness (Tests/FuzzHarness.h is a byte-identical copy of
// the master; change it in reason-rack-extensions). Every input starts from
// fresh objects, so a saved crash replays alone; commands and rendered frames
// are bounded whatever the input length.
//
// Patches arrive the way a host or a librarian sends them: bytes through the
// block decoders and DT1 messages, which the engine must then play.
#include "DSP/SeptumEngine.h"
#include "DSP/SeptumPresets.h"
#include "DSP/SeptumSysEx.h"
#include "FuzzHarness.h"

#include <array>
#include <memory>
#include <vector>

extern "C" int LLVMFuzzerTestOneInput (const std::uint8_t* data, std::size_t size)
{
    using namespace protocodus::fuzz;
    namespace sx = septum::sysex;
    Input input { data, size };

    auto engine = std::make_unique<septum::Engine>();
    auto decoder = std::make_unique<sx::PatchDataDecoder>();
    const auto& bank = septum::factoryPatches();
    septum::Patch patch = bank[input.Pick (bank.size())].patch;
    engine->prepare (input.Rate(), static_cast<int> (input.Word() % 4096) - 8);
    engine->setPatch (patch);

    constexpr std::size_t maxFrames = 512;
    Sentinels<maxFrames> block;
    std::array<float, maxFrames> inputLeft {}, inputRight {};
    const auto render = [&] (std::size_t frames, bool externalInput)
    {
        block.Arm();
        if (externalInput)
            for (std::size_t i = 0; i < frames; ++i)
            {
                inputLeft[i] = input.Scalar();
                inputRight[i] = input.Scalar();
            }
        engine->process (block.Left(), block.Right(), static_cast<int> (frames),
                         externalInput ? inputLeft.data() : nullptr,
                         externalInput ? inputRight.data() : nullptr);
        block.Check (frames);
    };
    const auto bytes = [&] (std::size_t count)
    {
        std::vector<std::uint8_t> result (count);
        for (auto& b : result) b = input.Byte();
        return result;
    };

    for (int command = 0; command < 64 && ! input.Empty(); ++command)
    {
        switch (input.Pick (12))
        {
            case 0: engine->noteOn (static_cast<int> (input.Byte()) - 64, static_cast<int> (input.Byte()) - 64); break;
            case 1: engine->noteOff (static_cast<int> (input.Byte()) - 64); break;
            case 2: engine->noteOnDirect (input.Byte() & 0x7f, input.Byte()); break;
            case 3: engine->setPitchBend (input.Scalar()); break;
            case 4:
                switch (input.Pick (6))
                {
                    case 0: engine->setModulation (input.Scalar()); break;
                    case 1: engine->setExpression (input.Scalar()); break;
                    case 2: engine->setPartLevel (input.Scalar()); break;
                    case 3: engine->setPartPan (input.Scalar()); break;
                    case 4: engine->setHold (input.Byte() & 1); break;
                    default: engine->setSostenuto (input.Byte() & 1); break;
                }
                break;
            case 5:
            {
                // One patch block straight through its decoder, as a .syx file
                // or a dump would deliver it.
                const auto raw = bytes (input.Pick (sx::sizeArpeggioPattern + 2));
                switch (input.Pick (5))
                {
                    case 0: sx::decodePatchCommon (raw.data(), raw.size(), patch); break;
                    case 1: sx::decodeTonePatch (raw.data(), raw.size(), input.Byte() & 1 ? patch.upper : patch.lower); break;
                    case 2: sx::decodeDelayParams (raw.data(), raw.size(), patch.delay); break;
                    case 3: sx::decodeReverbParams (raw.data(), raw.size(), patch.reverb); break;
                    default: sx::decodeArpeggioCommon (raw.data(), raw.size(), patch.arpeggio); break;
                }
                engine->setPatch (patch);
                break;
            }
            case 6:
            {
                // A whole DT1 message, well-formed around fuzzed address and data
                // or entirely fuzzed.
                std::vector<std::uint8_t> message;
                if (input.Byte() & 1)
                {
                    const auto payload = bytes (input.Pick (160));
                    message = sx::makeDt1Message (input.Word(), payload.data(), payload.size(),
                                                  input.Byte() & 1 ? sx::defaultDeviceId : input.Byte());
                }
                else
                    message = bytes (input.Pick (256));
                if (decoder->decode (message.data(), message.size(), patch, input.Byte()))
                    engine->setPatch (patch);
                break;
            }
            case 7: engine->setMasterLevel (static_cast<int> (input.Word())); break;
            case 8: engine->setTempoClock (input.Scalar() * 400.0f, input.Byte() & 1); break;
            case 9:
            {
                septum::ExternalInput external;
                external.inputVolume = static_cast<int> (input.Byte()) - 64;
                external.centerCancel = input.Byte() & 1;
                external.filterOn = input.Byte() & 1;
                external.cutoff = static_cast<int> (input.Byte()) - 64;
                external.resonance = static_cast<int> (input.Byte()) - 64;
                engine->setExternalInput (external);
                break;
            }
            case 10:
                switch (input.Pick (4))
                {
                    case 0: engine->allNotesOff(); break;
                    case 1: engine->allSoundOff(); break;
                    case 2: engine->reset(); break;
                    default: engine->prepare (input.Rate(), static_cast<int> (input.Word() % 4096) - 8); break;
                }
                break;
            default:
                patch = bank[input.Pick (bank.size())].patch;
                decoder->reset();
                engine->setPatch (patch);
                break;
        }
        // Never more than the block the engine was prepared for is required
        // of it; the guard samples still catch any write past `frames`.
        render (1 + input.Word() % maxFrames, (input.Byte() & 7) == 0);
    }
    return 0;
}

#include "DSP/SeptumSysEx.h"
#include "DSP/MidiTempoClock.h"
#include "DSP/ReferenceRateEngine.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <memory>
#include <random>
#include <stdexcept>
#include <vector>

namespace
{
int failures = 0;
void expect (bool condition, const char* description)
{
    if (! condition) { ++failures; std::fprintf (stderr, "FAIL: %s\n", description); }
}

void protocolTests()
{
    using namespace septum::sysex;
    const auto packets = encodePatchToSysExPackets (septum::initPatch());
    Dt1Packet parsed;
    for (const auto& packet : packets)
    {
        expect (parseDt1Packet (packet.data(), packet.size(), defaultDeviceId, parsed)
                && parsed.isForThisInstrument(), "encoded frames parse");
        for (std::size_t index = 1; index + 1 < packet.size(); ++index)
        {
            auto corrupt = packet;
            corrupt[index] |= 0x80;
            parsed = { addrTemporaryPatch, packet.data(), 1 };
            expect (! parseDt1Packet (corrupt.data(), corrupt.size(), defaultDeviceId, parsed),
                    "status bits inside SysEx are rejected");
            expect (parsed.data == nullptr && parsed.dataLength == 0,
                    "failed parse clears previous successful payload");
        }
        for (std::size_t length = 0; length < packet.size(); ++length)
            expect (! parseDt1Packet (packet.data(), length, defaultDeviceId, parsed),
                    "truncated framed SysEx is rejected");
    }
    auto foreign = packets.front();
    foreign[2] = 0x7f;
    expect (parseDt1Packet (foreign.data(), foreign.size(), defaultDeviceId, parsed),
            "documented broadcast device ID is accepted");
    foreign[2] = 0x30;
    expect (! parseDt1Packet (foreign.data(), foreign.size(), defaultDeviceId, parsed),
            "device ID is compared without aliasing low bits");
    parsed = { addrTemporaryPatch + 1, packets.front().data(),
               std::numeric_limits<std::size_t>::max() };
    expect (! parsed.isForThisInstrument(), "packet length cannot wrap block range guard");
    parsed = { addrTemporaryPatch, nullptr, 1 };
    expect (! parsed.isForThisInstrument(), "null decoded payload is not applicable");

    auto interrupted = std::vector<std::uint8_t> { 0xf0, 0x41, 0x10, 0x00 };
    interrupted.insert (interrupted.end(), packets.front().begin(), packets.front().end());
    std::vector<septum::NamedPatch> bank;
    expect (parseSyxBankFile (interrupted.data(), interrupted.size(), bank) && bank.size() == 1,
            "bank scanner recovers a complete frame after a truncated frame");
    try { (void) makeDt1Message (addrTemporaryPatch, nullptr, 1);
          expect (false, "null payload should throw"); }
    catch (const std::invalid_argument&) {}
    const std::uint8_t byte = 0;
    try { (void) makeDt1Message (addrTemporaryPatch, &byte, std::numeric_limits<std::size_t>::max());
          expect (false, "oversized payload should throw"); }
    catch (const std::length_error&) {}

    // Exercise extreme structured values through the standalone encoder too:
    // callers do not have to instantiate an Engine to use the codec.
    septum::Patch extreme;
    extreme.toneBalance = std::numeric_limits<int>::max();
    extreme.upper.osc1.fine = std::numeric_limits<int>::max();
    extreme.lower.pan = std::numeric_limits<int>::min();
    const auto encoded = encodePatchToSyxBuffer (extreme);
    expect (! encoded.empty(), "extreme signed fields encode without overflow");

    // Reproducible mutation fuzzing: valid seeds exercise deep decoding, while
    // arbitrary packets, lengths and corrupted framing probe parser bounds.
    std::mt19937 random (0x53455054u);
    septum::Patch patch;
    PatchDataDecoder stream;
    for (int iteration = 0; iteration < 50000; ++iteration)
    {
        auto bytes = packets[random() % packets.size()];
        if (iteration % 4 == 0)
        {
            bytes.resize (random() % 256);
            for (auto& value : bytes) value = static_cast<std::uint8_t> (random());
        }
        else
        {
            for (unsigned changes = 1 + random() % 8; changes > 0; --changes)
                bytes[random() % bytes.size()] = static_cast<std::uint8_t> (random());
            if (iteration % 4 == 1)
            {
                // Keep framing, address and checksum valid to reach the block
                // decoders with every combination of seven-bit field values.
                bytes = packets[random() % packets.size()];
                for (std::size_t i = 11; i + 2 < bytes.size(); ++i)
                    bytes[i] = static_cast<std::uint8_t> (random() & 0x7f);
                bytes[bytes.size() - 2] = calculateChecksum (bytes.data() + 7, bytes.size() - 9);
            }
        }
        const auto before = encodePatchToSyxBuffer (patch);
        const bool accepted = stream.decode (bytes.data(), bytes.size(), patch);
        if (! accepted)
            expect (before == encodePatchToSyxBuffer (patch), "rejected stream frame leaves patch intact");
        if (iteration % 31 == 0)
        {
            std::vector<septum::NamedPatch> fuzzBank;
            (void) parseSyxBankFile (bytes.data(), bytes.size(), fuzzBank);
            stream.reset();
        }
    }
}

void numericBoundaryTests()
{
    constexpr double nan = std::numeric_limits<double>::quiet_NaN();
    constexpr double inf = std::numeric_limits<double>::infinity();
    for (double rate : { nan, inf, -inf, -1.0, 0.0, 1.0, 1.0e300, 44100.0 })
    {
        septum::MidiTempoClock clock;
        clock.prepare (rate);
        clock.pulse();
        expect (clock.samplesUntilTimeout (-1) == 0, "negative maximum timeout is empty");
        clock.advance (-1);
        clock.advance (1000);
        clock.pulse();
        expect (std::isfinite (clock.bpm()), "invalid sample rates cannot poison clock tempo");
    }
    septum::MidiTempoClock clock;
    clock.prepare (48000.0);
    clock.pulse(); clock.advance (1000); clock.pulse();
    clock.advance (std::numeric_limits<int>::min());
    expect (clock.running() && clock.bpm() == 120.0, "negative advance preserves acquired clock");

    septum::detail::ReferenceRateConverter converter;
    converter.push (1.0f, 1.0f);
    expect (converter.read (0.0) == std::array<float, 2> {}, "unprepared converter is silent");
    for (double rate : { nan, inf, -inf, 0.0, -1.0, 1.0e300 })
    {
        try { converter.prepare (rate, 44100.0); expect (false, "invalid source rate should throw"); }
        catch (const std::invalid_argument&) {}
        try { converter.prepare (44100.0, rate); expect (false, "invalid destination rate should throw"); }
        catch (const std::invalid_argument&) {}
    }
    converter.prepare (44100.0, 44100.0);
    converter.push (std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity());
    for (double position : { nan, inf, -inf, -1.0e300, 1.0e300, 0.0 })
    {
        const auto audio = converter.read (position);
        expect (std::isfinite (audio[0]) && std::isfinite (audio[1]), "converter handles invalid input/positions");
    }
    auto engine = std::make_unique<septum::ReferenceRateEngine>();
    std::array<float, 32> right;
    right.fill (1.0f);
    engine->process (nullptr, right.data(), static_cast<int> (right.size()));
    expect (std::all_of (right.begin(), right.end(), [] (float value) { return value == 0.0f; }),
            "unprepared reference engine clears connected channels");
    engine->prepare (44100.0, 32);
    engine->process (nullptr, nullptr, 32);
    engine->process (nullptr, right.data(), 32);
}
}

int main()
{
    protocolTests();
    numericBoundaryTests();
    std::printf ("Protocol robustness: 50000 seeded mutation cases; %d failures\n", failures);
    return failures == 0 ? 0 : 1;
}

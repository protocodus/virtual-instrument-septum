// Offline sample-stamped replay for Tools/render_midi.py. This uses the
// shipping Engine, retains its latency, and writes unnormalised float WAV.
#include "DSP/SeptumEngine.h"
#include "DSP/SeptumPresets.h"
#include "DSP/SeptumSysEx.h"

#include <algorithm>
#include <array>
#include <bit>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{
using Bytes = std::vector<std::uint8_t>;
constexpr int blockSize = 256;
constexpr std::uintmax_t maxInputBytes = 64u * 1024u * 1024u;

Bytes readBytes (const std::filesystem::path& path)
{
    std::ifstream input (path, std::ios::binary);
    if (! input) throw std::runtime_error ("Cannot read " + path.string());
    const auto size = std::filesystem::file_size (path);
    if (size > maxInputBytes) throw std::runtime_error ("Input exceeds 64 MiB");
    Bytes bytes (static_cast<std::size_t> (size));
    input.read (reinterpret_cast<char*> (bytes.data()), static_cast<std::streamsize> (size));
    if (input.gcount() != static_cast<std::streamsize> (size)
        || input.peek() != std::char_traits<char>::eof() || input.bad())
        throw std::runtime_error ("Input changed or could not be read completely");
    return bytes;
}

void writeBytes (const std::filesystem::path& path, const Bytes& bytes)
{
    std::ofstream output (path, std::ios::binary);
    output.write (reinterpret_cast<const char*> (bytes.data()),
                  static_cast<std::streamsize> (bytes.size()));
    if (! output) throw std::runtime_error ("Cannot write " + path.string());
}

std::string jsonString (const std::string& text)
{
    std::ostringstream result;
    result << '"';
    for (const unsigned char c : text)
        if (c == '"' || c == '\\') result << '\\' << c;
        else if (c < 32) result << "\\u" << std::hex << std::setfill ('0')
                               << std::setw (4) << static_cast<int> (c);
        else result << c;
    return result.str() + '"';
}

// A benchmark must not silently fill an incomplete dump with INIT values.
septum::Patch readCompletePatch (const std::filesystem::path& path)
{
    const auto bytes = readBytes (path);
    auto patch = septum::initPatch();
    std::array<std::vector<bool>, septum::sysex::patchBlockCount> coverage;
    std::array<Bytes, septum::sysex::patchBlockCount> images;
    std::uint32_t base = 0;
    std::size_t cursor = 0;
    while (cursor < bytes.size())
    {
        if (bytes[cursor] != 0xf0) throw std::runtime_error ("Unexpected data outside SysEx frame");
        const auto start = cursor++;
        while (cursor < bytes.size() && bytes[cursor] != 0xf7)
        {
            if (bytes[cursor] >= 0x80) throw std::runtime_error ("Non-data byte inside SysEx frame");
            ++cursor;
        }
        if (cursor == bytes.size()) throw std::runtime_error ("Truncated SysEx frame");
        ++cursor;
        septum::sysex::Dt1Packet packet;
        if (! septum::sysex::parseDt1Packet (bytes.data() + start, cursor - start, 0x7f, packet)
            || ! packet.isForThisInstrument())
            throw std::runtime_error ("Invalid checksum, unsupported SysEx or invalid patch address");
        if (base != 0 && base != packet.patchBase())
            throw std::runtime_error ("Supply one patch, not a bank of multiple patch addresses");
        base = packet.patchBase();
        const auto block = static_cast<std::size_t> ((packet.address >> 8) & 0x7fu);
        auto& covered = coverage.at (block);
        auto& image = images.at (block);
        covered.resize (packet.blockSize(), false);
        image.resize (packet.blockSize());
        for (std::size_t i = 0; i < packet.dataLength; ++i)
        {
            image[packet.offsetInBlock() + i] = packet.data[i];
            covered[packet.offsetInBlock() + i] = true;
        }
    }
    for (const auto& covered : coverage)
        if (covered.empty() || std::find (covered.begin(), covered.end(), false) != covered.end())
            throw std::runtime_error ("Incomplete patch dump: all 22 native patch blocks are required");
    // Decode complete byte images once. Applying individual fragments through
    // the structured patch would clamp partially received multi-nibble values
    // (for example tempo), losing bytes before later packets complete them.
    for (std::size_t block = 0; block < images.size(); ++block)
    {
        const auto& image = images[block];
        const auto packet = septum::sysex::makeDt1Message (
            base | (static_cast<std::uint32_t> (block) << 8), image.data(), image.size());
        if (! septum::sysex::decodeSysExMessage (packet.data(), packet.size(), patch))
            throw std::runtime_error ("Cannot decode complete patch block");
    }
    return patch;
}

std::string patchSummary (const septum::Patch& patch)
{
    std::ostringstream out;
    out << "{\"name\":" << jsonString (patch.name)
        << ",\"tempo\":" << patch.tempo
        << ",\"keyboard_mode\":" << jsonString (
            patch.keyboardMode == septum::KeyboardMode::Single ? "single"
            : patch.keyboardMode == septum::KeyboardMode::Dual ? "dual" : "split")
        << ",\"single_part\":" << jsonString (
            patch.keyboardPart == septum::KeyboardPart::Upper ? "upper" : "lower")
        << ",\"split_point\":" << patch.splitPoint
        << ",\"patch_level\":" << patch.patchLevel
        << ",\"tone_balance\":" << patch.toneBalance
        << ",\"arpeggio_on\":" << (patch.arpeggio.on ? "true" : "false")
        << ",\"delay_on\":" << (patch.delayOn ? "true" : "false")
        << ",\"reverb_on\":" << (patch.reverbOn ? "true" : "false");
    for (const bool upper : { true, false })
    {
        const auto& tone = upper ? patch.upper : patch.lower;
        out << (upper ? ",\"upper\":{" : ",\"lower\":{")
            << "\"mono_mode\":" << static_cast<int> (tone.mono)
            << ",\"octave_shift\":" << tone.octaveShift
            << ",\"level\":" << tone.level
            << ",\"level_velocity_sensitivity\":" << tone.levelVelocitySens
            << ",\"cutoff_velocity_sensitivity\":" << tone.cutoffVelocitySens
            << ",\"oscillator_balance\":" << tone.balance;
        for (const bool first : { true, false })
        {
            const auto& osc = first ? tone.osc1 : tone.osc2;
            out << (first ? ",\"osc1\":{" : ",\"osc2\":{")
                << "\"wave\":" << static_cast<int> (osc.wave)
                << ",\"pitch_wide\":" << (osc.pitchWide ? "true" : "false")
                << ",\"coarse_semitones\":" << osc.coarse
                << ",\"fine_cents\":" << osc.fine
                << ",\"pw_feedback\":" << osc.pulseWidth << '}';
        }
        out << '}';
    }
    out << '}';
    return out.str();
}

// Same documented panel CC bindings as PluginProcessor.cpp. Unknown CCs are
// errors here; the Python entry point can explicitly audit and omit them.
bool panelCc (septum::Patch& patch, int cc, int value)
{
#define CC(upNumber, loNumber, field, signedValue) \
    case upNumber: patch.upper.field = value - (signedValue ? 64 : 0); return true; \
    case loNumber: patch.lower.field = value - (signedValue ? 64 : 0); return true
    switch (cc)
    {
        case 20: patch.upper.osc1.coarse = septum::sysex::decodeCoarseTune (value - 64, patch.upper.osc1.pitchWide); return true;
        case 78: patch.lower.osc1.coarse = septum::sysex::decodeCoarseTune (value - 64, patch.lower.osc1.pitchWide); return true;
        CC (76, 79, osc1.fine, true);
        CC (3, 80, osc1.pulseWidth, false);
        CC (24, 70, osc1.pitchEnvDepth, true);
        case 21: patch.upper.osc2.coarse = septum::sysex::decodeCoarseTune (value - 64, patch.upper.osc2.pitchWide); return true;
        case 85: patch.lower.osc2.coarse = septum::sysex::decodeCoarseTune (value - 64, patch.lower.osc2.pitchWide); return true;
        CC (77, 86, osc2.fine, true);
        CC (95, 87, osc2.pulseWidth, false);
        CC (25, 88, osc2.pitchEnvDepth, true);
        CC (26, 89, pitchEnvAttack, false);
        CC (27, 90, pitchEnvDecay, false);
        CC (8, 9, balance, true);
        CC (74, 102, cutoff, false);
        CC (71, 104, resonance, false);
        CC (82, 105, filterEnvAttack, false);
        CC (83, 106, filterEnvDecay, false);
        CC (28, 107, filterEnvSustain, false);
        CC (29, 108, filterEnvRelease, false);
        CC (81, 109, filterEnvDepth, true);
        CC (14, 15, level, false);
        CC (73, 110, ampEnvAttack, false);
        CC (75, 111, ampEnvDecay, false);
        CC (31, 112, ampEnvSustain, false);
        CC (72, 113, ampEnvRelease, false);
        CC (93, 94, delayDepth, false);
        CC (91, 92, reverbDepth, false);
        CC (16, 114, lfo1.rate, false);
        CC (18, 115, lfo1.depth1, true);
        CC (19, 116, lfo1.depth2, true);
        CC (17, 117, lfo2.rate, false);
        CC (22, 118, lfo2.depth1, true);
        CC (23, 119, lfo2.depth2, true);
        case 30: patch.upper.keyFollow = (value - 64) * 10; return true;
        case 103: patch.lower.keyFollow = (value - 64) * 10; return true;
        case 12: patch.delay.time = value; return true;
        case 13: patch.reverb.time = value; return true;
        default: return false;
    }
#undef CC
}

// Preflight all events before creating audio output. Same-sample messages
// deliberately retain file order (including note-off/note-on retriggers).
void validateMidi (const Bytes& data)
{
    if (data.size() != 3 || data[0] < 0x80 || data[0] >= 0xf0
        || data[1] > 127 || data[2] > 127)
        throw std::runtime_error ("Replay event is not a three-byte channel message");
    const auto kind = data[0] & 0xf0;
    if (kind == 0x80 || kind == 0x90 || kind == 0xe0) return;
    if (kind != 0xb0) throw std::runtime_error ("Unsupported MIDI status in replay");
    switch (data[1])
    {
        case 1: case 2: case 4: case 7: case 10: case 11: case 64: case 66:
        case 84: case 120: case 121: case 123: case 124: case 125: case 126: case 127:
            return;
        default: break;
    }
    auto probe = septum::initPatch();
    if (! panelCc (probe, data[1], data[2]))
        throw std::runtime_error ("Unsupported CC " + std::to_string (data[1]));
}

void applyMidi (septum::Engine& engine, septum::Patch& patch,
                septum::ExternalInput& external, const Bytes& data)
{
    const auto kind = data[0] & 0xf0;
    const int key = data[1], value = data[2];
    if (kind == 0x80 || (kind == 0x90 && value == 0)) { engine.noteOff (key); return; }
    if (kind == 0x90) { engine.noteOn (key, value); return; }
    if (kind == 0xe0) { engine.setPitchBend (((value << 7) | key) / 8192.0 - 1.0); return; }
    if (kind != 0xb0) throw std::runtime_error ("Unsupported MIDI status in replay");
    switch (key)
    {
        case 1: engine.setModulation (value / 127.0); return;
        case 2: external.cutoff = value; engine.setExternalInput (external); return;
        case 4: external.resonance = value; engine.setExternalInput (external); return;
        case 7: engine.setPartLevel (value / 127.0); return;
        case 10: engine.setPartPan ((value - 64) / 63.0); return;
        case 11: engine.setExpression (value / 127.0); return;
        case 64: engine.setHold (value >= 64); return;
        case 66: engine.setSostenuto (value >= 64); return;
        case 84: engine.setPortamentoControl (value); return;
        case 120: engine.allSoundOff(); return;
        case 121:
            engine.clearPortamentoControl();
            engine.setPitchBend (0.0); engine.setModulation (0.0);
            engine.setExpression (1.0); engine.setHold (false); engine.setSostenuto (false);
            return;
        case 123: case 124: case 125: engine.allNotesOff(); return;
        case 126: case 127:
            engine.allSoundOff();
            patch.upper.mono = patch.lower.mono = key == 126
                ? septum::MonoMode::SoloLegato : septum::MonoMode::Poly;
            engine.setPatch (patch);
            return;
        default: break;
    }
    if (! panelCc (patch, key, value)) throw std::runtime_error ("Unsupported CC " + std::to_string (key));
    septum::clampToDocumentedRanges (patch);
    engine.setPatch (patch);
}

struct Event { std::uint64_t sample; std::string kind; Bytes data; double tempo = 0.0; };

std::uint64_t unsignedDecimal (const std::string& value)
{
    std::uint64_t number = 0;
    const auto result = std::from_chars (value.data(), value.data() + value.size(), number);
    if (value.empty() || result.ec != std::errc {} || result.ptr != value.data() + value.size())
        throw std::runtime_error ("Invalid nonnegative sample timestamp");
    return number;
}

bool readReplayLine (std::istream& input, std::string& line)
{
    // A legal record is under 100 bytes. Bound allocation independently of
    // the file-size check so a concurrently growing file cannot exhaust RAM.
    line.clear();
    char character = 0;
    while (input.get (character))
    {
        if (character == '\n') return true;
        if (line.size() >= 256) throw std::runtime_error ("Replay line exceeds 256 bytes");
        line.push_back (character);
    }
    if (input.bad()) throw std::runtime_error ("Replay read failed");
    return ! line.empty();
}

std::vector<Event> readEvents (const std::filesystem::path& path, std::uint64_t& end,
                              std::uint64_t maximumEnd)
{
    std::ifstream input (path);
    if (! input) throw std::runtime_error ("Cannot read replay events");
    if (std::filesystem::file_size (path) > maxInputBytes)
        throw std::runtime_error ("Input exceeds 64 MiB");
    std::string header, extra, endText;
    int version = 0;
    if (! readReplayLine (input, header)) throw std::runtime_error ("Missing replay header");
    std::istringstream first (header);
    if (! (first >> header >> version >> endText) || header != "SEPTUM_RENDER_EVENTS"
        || version != 1 || (first >> extra)) throw std::runtime_error ("Invalid replay header");
    end = unsignedDecimal (endText);
    if (end > maximumEnd) throw std::runtime_error ("Render exceeds one hour");
    std::vector<Event> events;
    std::string line;
    while (readReplayLine (input, line))
    {
        if (events.size() >= 1000000) throw std::runtime_error ("Too many replay events");
        Event event {};
        std::string sampleText, value;
        std::istringstream row (line);
        if (! (row >> sampleText >> event.kind >> value) || (row >> extra))
            throw std::runtime_error ("Invalid replay event");
        event.sample = unsignedDecimal (sampleText);
        if (event.sample > end || (! events.empty() && event.sample < events.back().sample))
            throw std::runtime_error ("Invalid or unsorted replay event");
        if (event.kind == "tempo")
        {
            std::size_t consumed = 0;
            event.tempo = std::stod (value, &consumed);
            if (consumed != value.size() || ! std::isfinite (event.tempo)
                || event.tempo < 5.0 || event.tempo > 300.0)
                throw std::runtime_error ("Clock tempo outside 5–300 BPM");
        }
        else if (event.kind == "midi")
        {
            if (value.size() != 6) throw std::runtime_error ("Invalid replay MIDI encoding");
            const auto hexDigit = [] (char digit) -> unsigned
            {
                if (digit >= '0' && digit <= '9') return static_cast<unsigned> (digit - '0');
                if (digit >= 'a' && digit <= 'f') return static_cast<unsigned> (digit - 'a' + 10);
                if (digit >= 'A' && digit <= 'F') return static_cast<unsigned> (digit - 'A' + 10);
                throw std::runtime_error ("Invalid MIDI hex digit");
            };
            for (std::size_t i = 0; i < value.size(); i += 2)
                event.data.push_back (static_cast<std::uint8_t> (
                    16u * hexDigit (value[i]) + hexDigit (value[i + 1])));
            validateMidi (event.data);
        }
        else throw std::runtime_error ("Unknown replay event kind");
        events.push_back (std::move (event));
    }
    return events;
}

struct IncompleteOutput
{
    std::filesystem::path path;
    bool remove = false;
    ~IncompleteOutput()
    {
        if (remove)
        {
            std::error_code ignored;
            std::filesystem::remove (path, ignored);
        }
    }
};

void little (std::ostream& output, std::uint32_t value, int count)
{
    for (int i = 0; i < count; ++i) output.put (static_cast<char> ((value >> (8 * i)) & 255u));
}

void wavHeader (std::ostream& output, std::uint32_t frames, int rate)
{
    const auto bytes = frames * 8u;
    output << "RIFF"; little (output, 48u + bytes, 4); output << "WAVEfmt ";
    little (output, 16, 4); little (output, 3, 2); little (output, 2, 2);
    little (output, static_cast<std::uint32_t> (rate), 4);
    little (output, static_cast<std::uint32_t> (rate) * 8u, 4);
    little (output, 8, 2); little (output, 32, 2);
    output << "fact"; little (output, 4, 4); little (output, frames, 4);
    output << "data"; little (output, bytes, 4);
}
} // namespace

int main (int argc, char** argv)
{
    try
    {
        if (argc == 3 && std::string (argv[1]) == "--inspect-patch")
        {
            std::cout << patchSummary (readCompletePatch (argv[2])) << '\n';
            return 0;
        }
        if (argc == 3 && std::string (argv[1]) == "--write-init-patch")
        {
            writeBytes (argv[2], septum::sysex::encodePatchToSyxBuffer (septum::initPatch()));
            return 0;
        }
        std::filesystem::path patchFile, eventFile, outputFile;
        int rate = 44100, master = 100;
        double tail = 2.0;
        bool keyboardMode = false;
        for (int i = 1; i < argc; ++i)
        {
            const std::string option = argv[i];
            if (option == "--keyboard-mode") { keyboardMode = true; continue; }
            if (++i >= argc) throw std::runtime_error ("Missing value for " + option);
            const std::string value = argv[i];
            if (option == "--syx") patchFile = value;
            else if (option == "--events") eventFile = value;
            else if (option == "--output") outputFile = value;
            else if (option == "--sample-rate" || option == "--master-level" || option == "--tail")
            {
                std::size_t consumed = 0;
                const double number = std::stod (value, &consumed);
                if (consumed != value.size() || ! std::isfinite (number))
                    throw std::runtime_error ("Invalid numeric option");
                if (option == "--tail") tail = number;
                else
                {
                    if (number != std::floor (number) || number < 0 || number > 192000)
                        throw std::runtime_error ("Invalid integer option");
                    (option == "--sample-rate" ? rate : master) = static_cast<int> (number);
                }
            }
            else throw std::runtime_error ("Unknown option: " + option);
        }
        if (patchFile.empty() || eventFile.empty() || outputFile.empty())
            throw std::runtime_error ("Use render_midi.py, or --syx PATCH --events EVENTS --output WAV");
        if (rate < 8000 || rate > 192000 || master < 0 || master > 127 || tail < 0 || tail > 120)
            throw std::runtime_error ("Rate 8000–192000, master 0–127 and tail 0–120 required");
        if (std::filesystem::exists (outputFile))
            throw std::runtime_error ("Output already exists; choose another filename");
        auto patch = readCompletePatch (patchFile);
        const auto initialPatchSummary = patchSummary (patch);
        if (patch.arpeggio.on && ! keyboardMode)
            throw std::runtime_error ("Arpeggio-on patch requires explicit --keyboard-mode replay");
        std::uint64_t end = 0;
        const auto events = readEvents (eventFile, end, static_cast<std::uint64_t> (rate) * 3600u);
        const auto frames = end + static_cast<std::uint64_t> (std::llround (tail * rate));
        if (end > static_cast<std::uint64_t> (rate) * 3600u || frames > (0xffffffffu - 48u) / 8u)
            throw std::runtime_error ("Render exceeds one hour or the RIFF size limit");
        auto engine = std::make_unique<septum::Engine>();
        engine->prepare (rate, blockSize);
        engine->setPatch (patch);
        engine->setMasterLevel (master);
        engine->reset();
        septum::ExternalInput external {};
        IncompleteOutput cleanup { outputFile };
        std::ofstream output (outputFile, std::ios::binary);
        if (! output) throw std::runtime_error ("Cannot create output WAV");
        cleanup.remove = true;
        wavHeader (output, static_cast<std::uint32_t> (frames), rate);
        std::array<float, blockSize> left {}, right {};
        std::array<char, blockSize * 8> encoded {};
        std::uint64_t position = 0;
        double peak = 0.0;
        const auto renderTo = [&] (std::uint64_t target)
        {
            while (position < target)
            {
                const int count = static_cast<int> (std::min<std::uint64_t> (blockSize, target - position));
                engine->process (left.data(), right.data(), count);
                std::size_t byteIndex = 0;
                for (int sample = 0; sample < count; ++sample)
                    for (const float value : { left[static_cast<std::size_t> (sample)],
                                              right[static_cast<std::size_t> (sample)] })
                    {
                        if (! std::isfinite (value)) throw std::runtime_error ("Non-finite render sample");
                        peak = std::max (peak, std::abs (static_cast<double> (value)));
                        const auto bits = std::bit_cast<std::uint32_t> (value);
                        for (int byte = 0; byte < 4; ++byte)
                            encoded[byteIndex++] = static_cast<char> ((bits >> (8 * byte)) & 255u);
                    }
                output.write (encoded.data(), static_cast<std::streamsize> (byteIndex));
                if (! output) throw std::runtime_error ("WAV write failed");
                position += static_cast<std::uint64_t> (count);
            }
        };
        for (const auto& event : events)
        {
            renderTo (event.sample);
            if (event.kind == "midi") applyMidi (*engine, patch, external, event.data);
            else engine->setTempoClock (event.tempo);
        }
        renderTo (frames);
        output.close();
        if (! output) throw std::runtime_error ("WAV write failed");
        cleanup.remove = false;
        std::cout << "{\"frames\":" << frames << ",\"sample_rate\":" << rate
                  << ",\"latency_samples\":" << engine->latencySamples()
                  << ",\"peak\":" << std::setprecision (12) << peak
                  << ",\"active_voices_at_end\":" << engine->activeVoiceCount()
                  << ",\"patch_name\":" << jsonString (patch.name)
                  << ",\"patch_arpeggio_on\":" << (patch.arpeggio.on ? "true" : "false")
                  << ",\"patch_tempo_at_end\":" << patch.tempo
                  << ",\"clock_tempo_at_end\":" << std::setprecision (17) << engine->tempoBpm()
                  << ",\"master_level\":" << master
                  << ",\"initial_patch\":" << initialPatchSummary
                  << ",\"patch_load_warning\":null}\n";
        return 0;
    }
    catch (const std::exception& error)
    {
        std::cerr << "RenderMidi: " << error.what() << '\n';
        return 1;
    }
}

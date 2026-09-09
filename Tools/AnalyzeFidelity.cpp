// Reproducible, unnormalised measurements of the public engine signal path.
// Synthetic fixtures establish implementation behavior, never hardware identity.
#include "DSP/SeptumEngine.h"
#include "DSP/ReferenceRateEngine.h"
#include "DSP/SeptumSysEx.h"

#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <complex>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{
namespace fs = std::filesystem;
constexpr double pi = septum::mapping::pi;
constexpr int blockSize = 256;
constexpr int masterLevel = 96;
constexpr double envelopeBinSeconds = 0.005;
constexpr double missing = std::numeric_limits<double>::quiet_NaN();
using Metrics = std::map<std::string, double>;

std::string quote (const std::string& text)
{
    std::ostringstream out;
    out << '"';
    for (const unsigned char c : text)
    {
        if (c == '"' || c == '\\') out << '\\' << c;
        else if (c < 32) out << "\\u" << std::hex << std::setw (4)
                             << std::setfill ('0') << static_cast<unsigned> (c);
        else out << c;
    }
    return out.str() + '"';
}

std::string number (double value)
{
    if (! std::isfinite (value)) return "null";
    std::ostringstream out;
    out << std::setprecision (12) << value;
    return out.str();
}

double db (double amplitude)
{
    return amplitude > 0.0 ? 20.0 * std::log10 (amplitude) : missing;
}

void writeText (const fs::path& file, const std::string& text)
{
    std::ofstream output (file, std::ios::binary);
    output << text;
    if (! output) throw std::runtime_error ("Cannot write " + file.string());
}

std::vector<std::uint8_t> readBytes (const fs::path& file)
{
    std::ifstream input (file, std::ios::binary);
    if (! input) throw std::runtime_error ("Cannot read " + file.string());
    return { std::istreambuf_iterator<char> (input), {} };
}

void writeBytes (const fs::path& file, const std::vector<std::uint8_t>& bytes)
{
    std::ofstream output (file, std::ios::binary);
    output.write (reinterpret_cast<const char*> (bytes.data()),
                  static_cast<std::streamsize> (bytes.size()));
    if (! output) throw std::runtime_error ("Cannot write " + file.string());
}

// File identity, not a security or authenticity guarantee.
std::string fingerprint (const std::vector<std::uint8_t>& bytes)
{
    std::uint64_t hash = 14695981039346656037ull;
    for (auto b : bytes) { hash ^= b; hash *= 1099511628211ull; }
    std::ostringstream out;
    out << std::hex << std::setw (16) << std::setfill ('0') << hash;
    return out.str();
}

void append (std::vector<std::uint8_t>& bytes, std::uint32_t value, int width,
             bool bigEndian = false)
{
    for (int i = 0; i < width; ++i)
    {
        const int shift = 8 * (bigEndian ? width - i - 1 : i);
        bytes.push_back (static_cast<std::uint8_t> ((value >> shift) & 255u));
    }
}

void tag (std::vector<std::uint8_t>& bytes, const std::string& value)
{
    bytes.insert (bytes.end(), value.begin(), value.end());
}

struct Audio
{
    std::vector<float> left, right;
    int latency { 0 };
    double exactLatency { 0.0 };
    double renderSeconds { 0.0 };
};

// IEEE-float stereo WAV preserves every finite output sample, including values
// above +/-1. No limiter, integer quantisation, silent repair or gain adjustment.
std::vector<std::uint8_t> wavBytes (const Audio& audio, int rate, double gain = 1.0)
{
    if (audio.left.size() != audio.right.size())
        throw std::runtime_error ("Mismatched channel lengths");
    const auto dataSize = static_cast<std::uint32_t> (audio.left.size() * 8u);
    std::vector<std::uint8_t> bytes;
    bytes.reserve (56u + dataSize);
    tag (bytes, "RIFF"); append (bytes, 48u + dataSize, 4); tag (bytes, "WAVEfmt ");
    append (bytes, 16, 4); append (bytes, 3, 2); append (bytes, 2, 2);
    append (bytes, static_cast<std::uint32_t> (rate), 4);
    append (bytes, static_cast<std::uint32_t> (rate) * 8u, 4);
    append (bytes, 8, 2); append (bytes, 32, 2);
    tag (bytes, "fact"); append (bytes, 4, 4);
    append (bytes, static_cast<std::uint32_t> (audio.left.size()), 4);
    tag (bytes, "data"); append (bytes, dataSize, 4);
    for (std::size_t i = 0; i < audio.left.size(); ++i)
        for (const float input : { audio.left[i], audio.right[i] })
        {
            const auto value = static_cast<float> (static_cast<double> (input) * gain);
            if (! std::isfinite (value))
                throw std::runtime_error ("Non-finite audio; measurement aborted");
            append (bytes, std::bit_cast<std::uint32_t> (value), 4);
        }
    return bytes;
}

// Reads only this tool's exact 56-byte-header float WAV format for listening
// copies. General external/hardware WAV ingestion needs a separate decoder.
Audio readOwnWav (const fs::path& file)
{
    const auto bytes = readBytes (file);
    if (bytes.size() < 56 || (bytes.size() - 56) % 8 != 0
        || std::string (bytes.begin() + 48, bytes.begin() + 52) != "data")
        throw std::runtime_error ("Not an AnalyzeFidelity raw WAV: " + file.string());
    Audio audio;
    for (std::size_t i = 56; i < bytes.size(); i += 8)
        for (std::size_t channel = 0; channel < 2; ++channel)
        {
            std::uint32_t word = 0;
            for (std::size_t b = 0; b < 4; ++b)
                word |= static_cast<std::uint32_t> (bytes[i + channel * 4 + b]) << (8 * b);
            (channel == 0 ? audio.left : audio.right).push_back (std::bit_cast<float> (word));
        }
    return audio;
}

struct Event
{
    int milliseconds;
    bool on;
    int note, velocity;
};

struct Fixture
{
    std::string id, category;
    septum::Patch patch;
    std::vector<Event> events;
    int durationMs { 2500 };
    double fundamentalHz { 440.0 };
};

septum::Patch dryPatch()
{
    septum::Patch patch;
    patch.name = "FIDELITY";
    patch.patchLevel = 100;
    patch.upper.level = 100;
    patch.upper.filterType = septum::FilterType::Bypass;
    patch.upper.ampEnvAttack = 0;
    patch.upper.ampEnvDecay = 0;
    patch.upper.ampEnvSustain = 127;
    patch.upper.ampEnvRelease = 0;
    return patch;
}

Fixture fixture (std::string id, std::string category, int note)
{
    return { std::move (id), std::move (category), dryPatch(),
             { { 100, true, note, 127 }, { 2100, false, note, 0 } }, 2500,
             440.0 * std::exp2 ((note - 69) / 12.0) };
}

std::vector<Fixture> fixtures (bool quick)
{
    std::vector<Fixture> result;
    for (int note : quick ? std::vector<int> { 93 } : std::vector<int> { 45, 69, 93 })
    {
        auto saw = fixture ("saw-n" + std::to_string (note), "oscillator", note);
        result.push_back (saw);
        for (int spread : quick ? std::vector<int> { 0 } : std::vector<int> { 0, 64, 127 })
        {
            auto super = fixture ("supersaw-n" + std::to_string (note) + "-spread"
                                      + std::to_string (spread), "oscillator", note);
            super.patch.upper.osc1.wave = septum::Waveform::SuperSaw;
            super.patch.upper.osc1.pulseWidth = spread;
            result.push_back (super);
        }
        auto feedback = fixture ("fbosc-n" + std::to_string (note) + "-feedback64",
                                 "oscillator", note);
        feedback.patch.upper.osc1.wave = septum::Waveform::FbOsc;
        feedback.patch.upper.osc1.pulseWidth = 64;
        result.push_back (feedback);
    }
    auto noise = fixture ("noise-bypass", "filter-reference", 69);
    noise.patch.upper.osc1.wave = septum::Waveform::Noise;
    noise.fundamentalHz = 0.0;
    result.push_back (noise);
    for (auto type : quick ? std::vector<septum::FilterType> { septum::FilterType::Lpf }
                           : std::vector<septum::FilterType> { septum::FilterType::Lpf,
                                 septum::FilterType::Hpf, septum::FilterType::Bpf })
        for (auto slope : { septum::FilterSlope::Db12, septum::FilterSlope::Db24 })
        {
            auto filtered = noise;
            filtered.category = "filter";
            filtered.id = "filter-type" + std::to_string (static_cast<int> (type))
                          + "-slope" + std::to_string (slope == septum::FilterSlope::Db12 ? 12 : 24)
                          + "-cutoff64-res64";
            filtered.patch.upper.filterType = type;
            filtered.patch.upper.filterSlope = slope;
            filtered.patch.upper.cutoff = 64;
            filtered.patch.upper.resonance = 64;
            result.push_back (filtered);
        }
    auto sine = fixture ("sine-n69", "envelope-reference", 69);
    sine.patch.upper.osc1.wave = septum::Waveform::Sine;
    result.push_back (sine);
    for (int value : quick ? std::vector<int> { 64 } : std::vector<int> { 0, 32, 64, 96, 127 })
    {
        auto envelope = sine;
        envelope.id = "amp-adr" + std::to_string (value) + "-sustain64";
        envelope.category = "envelope";
        envelope.patch.upper.ampEnvAttack = value;
        envelope.patch.upper.ampEnvDecay = value;
        envelope.patch.upper.ampEnvSustain = 64;
        envelope.patch.upper.ampEnvRelease = value;
        // Captures cover the documented fixture values at the current mapping;
        // exported times are the authority, not an implicit mapping on replay.
        const int holdMs = static_cast<int> (std::ceil (1000.0 *
            (septum::mapping::attackSeconds (value) + septum::mapping::decaySeconds (value)))) + 700;
        envelope.events[1].milliseconds = 100 + holdMs;
        envelope.durationMs = envelope.events[1].milliseconds
            + static_cast<int> (std::ceil (1000.0 * septum::mapping::decaySeconds (value))) + 500;
        result.push_back (envelope);
    }
    return result;
}

void midiVariable (std::vector<std::uint8_t>& bytes, std::uint32_t value)
{
    std::array<std::uint8_t, 4> encoded {};
    int count = 0;
    encoded[static_cast<std::size_t> (count++)] = static_cast<std::uint8_t> (value & 127u);
    while ((value >>= 7u) != 0)
        encoded[static_cast<std::size_t> (count++)] = static_cast<std::uint8_t> ((value & 127u) | 128u);
    while (count > 0) bytes.push_back (encoded[static_cast<std::size_t> (--count)]);
}

std::vector<std::uint8_t> midiBytes (const Fixture& item)
{
    // Type0, 1000 ticks/quarter, 1,000,000us/quarter => exactly 1ms/tick.
    std::vector<std::uint8_t> track { 0, 255, 81, 3, 15, 66, 64 };
    int previous = 0;
    for (const auto& event : item.events)
    {
        midiVariable (track, static_cast<std::uint32_t> (event.milliseconds - previous));
        track.push_back (event.on ? 0x90 : 0x80);
        track.push_back (static_cast<std::uint8_t> (event.note));
        track.push_back (static_cast<std::uint8_t> (event.velocity));
        previous = event.milliseconds;
    }
    midiVariable (track, static_cast<std::uint32_t> (item.durationMs - previous));
    track.insert (track.end(), { 255, 47, 0 });
    std::vector<std::uint8_t> file;
    tag (file, "MThd"); append (file, 6, 4, true); append (file, 0, 2, true);
    append (file, 1, 2, true); append (file, 1000, 2, true);
    tag (file, "MTrk"); append (file, static_cast<std::uint32_t> (track.size()), 4, true);
    file.insert (file.end(), track.begin(), track.end());
    return file;
}

template <typename EngineType>
Audio renderWithEngine (const Fixture& item, int rate, int requestedBlockSize)
{
    // reset() alone does not reset Engine's global RNG. A new instance is an
    // intentional part of every fixture's reproducibility contract.
    auto engine = std::make_unique<EngineType>();
    engine->prepare (rate, requestedBlockSize);
    engine->setMasterLevel (masterLevel);
    engine->setMasterTuneHz (440.0);
    engine->setPatch (item.patch);
    engine->reset();
    Audio audio;
    audio.latency = engine->latencySamples();
    if constexpr (requires { engine->exactLatencySamples(); })
        audio.exactLatency = engine->exactLatencySamples();
    else
        audio.exactLatency = audio.latency;
    const auto frames = static_cast<std::size_t> (std::llround (item.durationMs * (rate / 1000.0)));
    audio.left.resize (frames);
    audio.right.resize (frames);
    std::size_t position = 0;
    const auto renderStart = std::chrono::steady_clock::now();
    for (std::size_t eventIndex = 0; eventIndex <= item.events.size(); ++eventIndex)
    {
        const auto boundary = eventIndex == item.events.size() ? frames
            : static_cast<std::size_t> (std::llround (item.events[eventIndex].milliseconds * (rate / 1000.0)));
        while (position < boundary)
        {
            const auto count = static_cast<int> (std::min (boundary - position,
                static_cast<std::size_t> (requestedBlockSize)));
            engine->process (audio.left.data() + position, audio.right.data() + position, count);
            position += static_cast<std::size_t> (count);
        }
        if (eventIndex < item.events.size())
        {
            const auto& event = item.events[eventIndex];
            if (event.on) engine->noteOn (event.note, event.velocity);
            else engine->noteOff (event.note);
        }
    }
    audio.renderSeconds = std::chrono::duration<double> (
        std::chrono::steady_clock::now() - renderStart).count();
    return audio;
}

Audio render (const Fixture& item, int rate, int requestedBlockSize = blockSize,
              bool reference = false)
{
    return reference ? renderWithEngine<septum::ReferenceRateEngine> (item, rate, requestedBlockSize)
                     : renderWithEngine<septum::Engine> (item, rate, requestedBlockSize);
}

void fft (std::vector<std::complex<double>>& values)
{
    const auto n = values.size();
    for (std::size_t i = 1, j = 0; i < n; ++i)
    {
        auto bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) std::swap (values[i], values[j]);
    }
    for (std::size_t length = 2; length <= n; length *= 2)
    {
        const auto step = std::polar (1.0, -2.0 * pi / static_cast<double> (length));
        for (std::size_t start = 0; start < n; start += length)
        {
            std::complex<double> factor { 1.0, 0.0 };
            for (std::size_t i = 0; i < length / 2; ++i)
            {
                const auto even = values[start + i];
                const auto odd = values[start + i + length / 2] * factor;
                values[start + i] = even + odd;
                values[start + i + length / 2] = even - odd;
                factor *= step;
            }
        }
    }
}

double spectralAmplitude (const std::vector<double>& windowed, double windowSum,
                          double frequency, int rate)
{
    if (frequency <= 0.0 || frequency >= rate * 0.5) return missing;
    const auto step = std::polar (1.0, -2.0 * pi * frequency / rate);
    std::complex<double> phase { 1.0, 0.0 }, sum { 0.0, 0.0 };
    for (double value : windowed) { sum += phase * value; phase *= step; }
    return 2.0 * std::abs (sum) / windowSum;
}

struct Analysis
{
    Metrics metrics;
    std::string envelopeCsv, spectrumCsv;
};

Analysis analyse (const Audio& audio, const Fixture& item, int rate)
{
    Analysis result;
    auto& metrics = result.metrics;
    double squares = 0.0, peak = 0.0, mean = 0.0;
    for (std::size_t i = 0; i < audio.left.size(); ++i)
        for (const double value : { audio.left[i], audio.right[i] })
        {
            if (! std::isfinite (value)) throw std::runtime_error ("Non-finite engine output");
            squares += value * value; peak = std::max (peak, std::abs (value)); mean += value;
        }
    const double count = static_cast<double> (audio.left.size()) * 2.0;
    metrics["rms"] = std::sqrt (squares / count);
    metrics["peak"] = peak;
    metrics["dc_mean"] = mean / count;
    metrics["latency_samples"] = audio.latency;
    metrics["exact_latency_samples"] = audio.exactLatency;
    metrics["render_wall_seconds"] = audio.renderSeconds;
    metrics["real_time_factor"] = audio.renderSeconds / (audio.left.size() / static_cast<double> (rate));

    const double noteOn = item.events.front().milliseconds * 0.001;
    const double noteOff = item.events.back().milliseconds * 0.001;
    const auto binSize = static_cast<std::size_t> (std::lround (rate * envelopeBinSeconds));
    const double actualBinSeconds = static_cast<double> (binSize) / rate;
    metrics["envelope_bin_samples"] = static_cast<double> (binSize);
    metrics["envelope_bin_seconds"] = actualBinSeconds;
    std::vector<std::pair<double, double>> envelope;
    std::ostringstream envelopeCsv;
    envelopeCsv << "time_seconds,rms,dbfs\n";
    for (std::size_t start = 0; start < audio.left.size(); start += binSize)
    {
        const auto end = std::min (audio.left.size(), start + binSize);
        double energy = 0.0;
        for (std::size_t i = start; i < end; ++i)
            energy += (static_cast<double> (audio.left[i]) * audio.left[i]
                       + static_cast<double> (audio.right[i]) * audio.right[i]) * 0.5;
        const double rms = std::sqrt (energy / static_cast<double> (end - start));
        const double time = static_cast<double> (start + end) * 0.5 / rate;
        envelope.emplace_back (time, rms);
        envelopeCsv << number (time) << ',' << number (rms) << ',' << number (db (rms)) << '\n';
    }
    result.envelopeCsv = envelopeCsv.str();
    double heldPeak = 0.0, sustainEnergy = 0.0;
    int sustainCount = 0;
    for (auto [time, rms] : envelope)
    {
        if (time >= noteOn && time < noteOff) heldPeak = std::max (heldPeak, rms);
        if (time >= noteOff - 0.2 && time < noteOff)
        { sustainEnergy += rms * rms; ++sustainCount; }
    }
    const auto crossing = [&] (double fraction)
    {
        for (auto [time, rms] : envelope)
            if (time >= noteOn && time < noteOff && rms >= heldPeak * fraction)
                return time;
        return missing;
    };
    metrics["attack_10_90_ms"] = 1000.0 * (crossing (0.9) - crossing (0.1));
    metrics["sustain_rms"] = sustainCount > 0 ? std::sqrt (sustainEnergy / sustainCount) : missing;
    metrics["release_60db_ms"] = missing;
    int consecutive = 0;
    for (auto [time, rms] : envelope)
    {
        if (time < noteOff) continue;
        consecutive = rms <= metrics["sustain_rms"] * 0.001 ? consecutive + 1 : 0;
        if (consecutive == 6)
        {
            metrics["release_60db_ms"] = 1000.0 * (time - 5.0 * actualBinSeconds - noteOff);
            break;
        }
    }
    // Beating, noise, resonant filters and imported multi-oscillator patches
    // can cross these thresholds without any ADSR change. Only the isolated
    // sine fixtures support an amplitude-envelope timing interpretation.
    if (item.category != "envelope" && item.category != "envelope-reference")
    {
        metrics["attack_10_90_ms"] = missing;
        metrics["release_60db_ms"] = missing;
    }

    // Final held second, left channel, Hann window. Spectrum values are raw
    // peak sinusoidal amplitude, not an FFT-dependent arbitrary magnitude.
    const auto end = std::min (audio.left.size(), static_cast<std::size_t> (std::llround (noteOff * rate)));
    const auto start = static_cast<std::size_t> (std::llround (std::max (noteOn, noteOff - 1.0) * rate));
    const auto size = end - start;
    std::vector<double> windowed (size);
    double windowSum = 0.0;
    for (std::size_t i = 0; i < size; ++i)
    {
        const double window = 0.5 - 0.5 * std::cos (2.0 * pi * static_cast<double> (i)
                                                / static_cast<double> (size - 1));
        windowed[i] = audio.left[start + i] * window;
        windowSum += window;
    }
    const double fundamental = spectralAmplitude (windowed, windowSum, item.fundamentalHz, rate);
    metrics["nominal_note_frequency_hz"] = item.fundamentalHz;
    metrics["fundamental_dbfs"] = db (fundamental);
    for (const int frequency : { 15940, 19840 })
        metrics["probe_" + std::to_string (frequency) + "_dbc"] =
            db (spectralAmplitude (windowed, windowSum, frequency, rate) / fundamental);
    for (int harmonic = 2; harmonic <= 12; ++harmonic)
        metrics["harmonic_" + std::to_string (harmonic) + "_dbc"] =
            db (spectralAmplitude (windowed, windowSum, item.fundamentalHz * harmonic, rate) / fundamental);
    std::size_t fftSize = 1;
    while (fftSize < size) fftSize *= 2;
    std::vector<std::complex<double>> spectrum (fftSize);
    for (std::size_t i = 0; i < size; ++i) spectrum[i] = windowed[i];
    fft (spectrum);
    double weighted = 0.0, power = 0.0, highPower = 0.0;
    std::ostringstream spectrumCsv;
    spectrumCsv << "frequency_hz,peak_amplitude,dbfs\n";
    for (std::size_t bin = 1; bin < fftSize / 2; ++bin)
    {
        const double frequency = static_cast<double> (bin) * rate / static_cast<double> (fftSize);
        const double energy = std::norm (spectrum[bin]);
        const double amplitude = 2.0 * std::abs (spectrum[bin]) / windowSum;
        spectrumCsv << number (frequency) << ',' << number (amplitude) << ',' << number (db (amplitude)) << '\n';
        // A common20kHz band lets hosts with different Nyquist rates compare.
        if (frequency <= 20000.0)
        { weighted += frequency * energy; power += energy; if (frequency >= 12000.0) highPower += energy; }
    }
    metrics["centroid_20k_hz"] = power > 0.0 ? weighted / power : missing;
    metrics["power_12k_to_20k_fraction"] = power > 0.0 ? highPower / power : missing;
    metrics["spectrum_start_seconds"] = static_cast<double> (start) / rate;
    metrics["spectrum_duration_seconds"] = static_cast<double> (size) / rate;
    metrics["fft_size"] = static_cast<double> (fftSize);
    result.spectrumCsv = spectrumCsv.str();
    return result;
}

struct Row
{
    std::string id, patchHash, midiHash, basename;
    int rate;
    Metrics metrics;
};

std::map<std::string, Row> readSummary (const fs::path& file)
{
    std::ifstream input (file);
    if (! input) throw std::runtime_error ("Cannot read comparison " + file.string());
    std::map<std::string, Row> rows;
    std::string line;
    std::getline (input, line);
    if (line != "fixture\trate\tpatch_fnv1a64\tmidi_fnv1a64\tmetric\tvalue")
        throw std::runtime_error ("Unsupported summary schema: " + file.string());
    while (std::getline (input, line))
    {
        std::array<std::string, 6> columns;
        std::istringstream stream (line);
        for (auto& column : columns) std::getline (stream, column, '\t');
        auto& row = rows[columns[0] + "@" + columns[1]];
        row.id = columns[0]; row.rate = std::stoi (columns[1]);
        row.patchHash = columns[2]; row.midiHash = columns[3];
        row.metrics[columns[4]] = columns[5] == "null" ? missing : std::stod (columns[5]);
    }
    return rows;
}

// The renderer fixes these system gains, and an older/different binary could
// have chosen different constants. Refuse a level comparison in that case.
// This reads our own flat numeric manifest fields, rather than arbitrary JSON.
void verifyBaselineSettings (const fs::path& directory)
{
    const auto bytes = readBytes (directory / "manifest.json");
    const std::string text (bytes.begin(), bytes.end());
    const std::pair<const char*, double> required[] {
        { "raw_output_gain", 1.0 }, { "master_level_raw", masterLevel },
        { "master_tune_hz", 440.0 }, { "key_shift", 0.0 },
        { "octave_shift", 0.0 }, { "transpose", 0.0 },
        { "expression", 1.0 }, { "part_level", 1.0 }, { "part_pan", 0.0 },
        { "pitch_bend", 0.0 }, { "modulation", 0.0 }
    };
    for (const auto& [key, expected] : required)
    {
        const auto start = text.find (quote (key));
        const auto colon = start == std::string::npos ? start : text.find (':', start);
        if (colon == std::string::npos || std::stod (text.substr (colon + 1)) != expected)
            throw std::runtime_error (std::string ("Baseline gain/system setting mismatch: ") + key);
    }
    for (const auto& [key, expected] : std::array<std::pair<const char*, bool>, 4> {
             { { "hold", false }, { "sostenuto", false },
               { "upper_enabled", true }, { "lower_enabled", true } } })
    {
        const auto start = text.find (quote (key));
        const auto colon = start == std::string::npos ? start : text.find (':', start);
        const auto value = colon == std::string::npos ? colon : text.find_first_not_of (" \t\r\n", colon + 1);
        if (value == std::string::npos || text.compare (value, expected ? 4u : 5u,
                                                       expected ? "true" : "false") != 0)
            throw std::runtime_error (std::string ("Baseline performance setting mismatch: ") + key);
    }
}

void comparison (const std::vector<Row>& rows, const std::map<std::string, Row>& baseline,
                 const fs::path& file, bool acrossRates)
{
    std::ostringstream output;
    output << "fixture\trate\tbaseline_rate\tmetric\tbaseline\tcandidate\tdelta\n";
    for (const auto& row : rows)
    {
        const auto key = row.id + "@" + std::to_string (acrossRates ? 44100 : row.rate);
        const auto found = baseline.find (key);
        if (found == baseline.end()) throw std::runtime_error ("Missing baseline fixture " + key);
        const auto& reference = found->second;
        if (row.patchHash != reference.patchHash || row.midiHash != reference.midiHash)
            throw std::runtime_error ("Patch/MIDI mismatch for baseline fixture " + key);
        for (const auto& [name, value] : row.metrics)
        {
            const auto old = reference.metrics.find (name);
            if (old == reference.metrics.end()) continue;
            output << row.id << '\t' << row.rate << '\t' << reference.rate << '\t' << name << '\t'
                   << number (old->second) << '\t' << number (value) << '\t' << number (value - old->second) << '\n';
        }
    }
    writeText (file, output.str());
}

void selfTest()
{
    auto item = fixture ("self-test-sine", "envelope-reference", 69);
    item.patch.upper.osc1.wave = septum::Waveform::Sine;
    item.events.back().milliseconds = 600;
    item.durationMs = 900;
    const auto first = render (item, 44100);
    const auto second = render (item, 44100);
    if (first.left != second.left || first.right != second.right)
        throw std::runtime_error ("Fresh-engine renders are not deterministic");
    const auto bytes = wavBytes (first, 44100);
    if (bytes.size() != 56 + first.left.size() * 8 || bytes[20] != 3)
        throw std::runtime_error ("Float WAV header/length regression");
    Audio synthetic;
    synthetic.left.resize (44100); synthetic.right.resize (44100);
    for (std::size_t i = 0; i < synthetic.left.size(); ++i)
        synthetic.left[i] = synthetic.right[i] = static_cast<float> (0.25 * std::sin (2.0 * pi * 440.0 * i / 44100.0));
    item.events = { { 0, true, 69, 127 }, { 1000, false, 69, 0 } };
    const auto metrics = analyse (synthetic, item, 44100).metrics;
    if (std::abs (metrics.at ("fundamental_dbfs") - db (0.25)) > 0.01
        || std::abs (metrics.at ("rms") - 0.25 / std::sqrt (2.0)) > 1.0e-6
        || std::abs (metrics.at ("centroid_20k_hz") - 440.0) > 0.2)
        throw std::runtime_error ("Known-sine spectral/RMS calibration failed");
    item.events = { { 100, true, 69, 127 }, { 600, false, 69, 0 } };
    for (std::size_t i = 0; i < synthetic.left.size(); ++i)
    {
        const double time = static_cast<double> (i) / 44100.0;
        const double amplitude = time < 0.1 ? 0.0 : time < 0.3 ? (time - 0.1) / 0.2
            : time < 0.6 ? 1.0 : std::exp (std::log (0.001) * (time - 0.6) / 0.2);
        synthetic.left[i] = synthetic.right[i] = static_cast<float> (
            amplitude * 0.25 * std::sin (2.0 * pi * 1000.0 * time));
    }
    const auto envelope = analyse (synthetic, item, 44100).metrics;
    if (! std::isfinite (envelope.at ("attack_10_90_ms"))
        || ! std::isfinite (envelope.at ("release_60db_ms"))
        || std::abs (envelope.at ("attack_10_90_ms") - 160.0) > 10.0
        || std::abs (envelope.at ("release_60db_ms") - 200.0) > 10.0)
        throw std::runtime_error ("Known attack/release timing calibration failed");
    synthetic.left = { -1.25f, 1.5f }; synthetic.right = { 0.0f, -0.0f };
    const auto raw = wavBytes (synthetic, 44100);
    std::uint32_t word = 0;
    for (int b = 0; b < 4; ++b) word |= static_cast<std::uint32_t> (raw[56 + static_cast<std::size_t> (b)]) << (8 * b);
    if (std::bit_cast<float> (word) != -1.25f)
        throw std::runtime_error ("Raw float WAV samples were clipped or normalized");
    std::cout << "Fidelity self-test passed: deterministic engine, float WAV preservation, known-sine and envelope metrics.\n";
}

int run (int argc, char** argv)
{
    fs::path output, baseline, patchFile, references = "Docs/fidelity/reference-manifest.json";
    std::string sourceId, variant;
    bool quick = false, listening = false, reference = false, dryImport = false;
    int requestedBlockSize = blockSize, note = 69, velocity = 127;
    for (int i = 1; i < argc; ++i)
    {
        const std::string option = argv[i];
        if (option == "--self-test") { selfTest(); return 0; }
        if (option == "--quick") { quick = true; continue; }
        if (option == "--listening-copies") { listening = true; continue; }
        if (option == "--dry-import") { dryImport = true; continue; }
        if (option == "--help")
        {
            std::cout << "SeptumAnalyzeFidelity --output DIR --source-id LABEL [--variant LABEL] [--quick]\n"
                         "  [--baseline DIR] [--references FILE] [--listening-copies]\n"
                         "  [--renderer native|reference] [--block-size N]\n"
                         "  [--patch FILE.syx --note N --velocity N [--dry-import]]\n"
                         "  --self-test checks reproducibility, float WAV and measurement calibration.\n";
            return 0;
        }
        if (i + 1 >= argc) throw std::runtime_error ("Missing argument after " + option);
        const std::string value = argv[++i];
        if (option == "--output") output = value;
        else if (option == "--baseline") baseline = value;
        else if (option == "--references") references = value;
        else if (option == "--source-id") sourceId = value;
        else if (option == "--variant") variant = value;
        else if (option == "--block-size") requestedBlockSize = std::stoi (value);
        else if (option == "--note") note = std::stoi (value);
        else if (option == "--velocity") velocity = std::stoi (value);
        else if (option == "--patch") patchFile = value;
        else if (option == "--renderer")
        {
            if (value != "native" && value != "reference")
                throw std::runtime_error ("Renderer must be native or reference");
            reference = value == "reference";
        }
        else throw std::runtime_error ("Unknown option " + option);
    }
    if (requestedBlockSize < 1 || requestedBlockSize > 8192 || note < 0 || note > 127
        || velocity < 1 || velocity > 127)
        throw std::runtime_error ("Block size must be 1..8192, note 0..127, velocity 1..127");
    if (dryImport && patchFile.empty()) throw std::runtime_error ("--dry-import needs --patch");
    if (variant.empty()) variant = reference ? "reference-rate-engine" : "native-engine";
    if (output.empty() || sourceId.empty())
        throw std::runtime_error ("Require --output DIR and --source-id LABEL; see --help");
    output = fs::absolute (output);
    fs::create_directories (output);
    if (fs::exists (output / "summary.tsv"))
        throw std::runtime_error ("Choose a fresh output directory; refusing to replace an existing dataset");
    if (! baseline.empty()) verifyBaselineSettings (baseline);
    const auto referenceBytes = readBytes (references);
    writeBytes (output / "reference-manifest.json", referenceBytes);
    const auto binaryHash = fingerprint (readBytes (fs::absolute (argv[0])));
    auto cases = fixtures (quick);
    std::string importHash, importProvenanceHash;
    if (! patchFile.empty())
    {
        const auto bytes = readBytes (patchFile);
        importHash = fingerprint (bytes);
        auto provenance = patchFile;
        provenance.replace_extension (".provenance.json");
        if (fs::is_regular_file (provenance))
        {
            const auto provenanceBytes = readBytes (provenance);
            importProvenanceHash = fingerprint (provenanceBytes);
            writeBytes (output / "imported-source.provenance.json", provenanceBytes);
        }
        std::vector<septum::NamedPatch> patches;
        if (! septum::sysex::parseSyxBankFile (bytes.data(), bytes.size(), patches) || patches.size() != 1)
            throw std::runtime_error ("--patch requires a valid SysEx file containing exactly one patch");
        auto imported = fixture (dryImport ? "imported-modified-dry" : "imported-as-stored",
                                  "external-patch-characterization", note);
        imported.patch = patches.front().patch;
        imported.events[0].velocity = velocity;
        imported.events[1].milliseconds = 4100;
        imported.durationMs = 8100;
        if (dryImport)
        {
            imported.patch.delayOn = imported.patch.reverbOn = false;
            for (auto* tone : { &imported.patch.upper, &imported.patch.lower })
            { tone->overdrive = false; tone->delayDepth = tone->reverbDepth = 0; }
        }
        cases = { imported };
    }
    std::vector<Row> rows;
    std::ostringstream summary;
    summary << "fixture\trate\tpatch_fnv1a64\tmidi_fnv1a64\tmetric\tvalue\n";
    std::ostringstream manifest;
    manifest << "{\n\"schema_version\":1,\n\"source_id\":" << quote (sourceId)
             << ",\n\"variant\":" << quote (variant) << ",\n\"binary_fnv1a64\":" << quote (binaryHash)
             << ",\n\"renderer\":" << quote (reference ? "reference" : "native")
             << ",\n\"reference_manifest_fnv1a64\":" << quote (fingerprint (referenceBytes))
             << ",\n\"evidence\":\"synthetic_engine_characterization_not_hardware_calibration\","
             << "\n\"signal_path\":" << quote (patchFile.empty() || dryImport
                    ? "complete Engine output including modeled output stage; delay/reverb/overdrive disabled"
                    : "complete Engine output with imported patch effects/overdrive/routing as stored")
             << ",\n\"imported_source\":" << quote (patchFile.empty() ? "" : fs::absolute (patchFile).string())
             << ",\n\"imported_source_fnv1a64\":" << quote (importHash)
             << ",\n\"imported_provenance_fnv1a64\":" << quote (importProvenanceHash)
             << ",\n\"import_modified_for_dry_measurement\":" << (dryImport ? "true" : "false") << ','
             <<
                "\n\"raw_output_gain\":1,\n\"master_level_raw\":96,\n\"master_tune_hz\":440,"
                "\n\"performance\":{\"key_shift\":0,\"octave_shift\":0,\"transpose\":0,\"expression\":1,"
                "\"part_level\":1,\"part_pan\":0,\"pitch_bend\":0,\"modulation\":0,\"hold\":false,"
                "\"sostenuto\":false,\"upper_enabled\":true,\"lower_enabled\":true,\"external_input\":\"null\"},"
                "\n\"initial_random_state\":{\"method\":\"new selected engine per fixture/rate; prepare,setMasterLevel,setMasterTuneHz,setPatch,reset\","
                "\"engine_rng\":\"0x2545f491\",\"arpeggio_rng\":\"0x6d2b79f5\","
                "\"upper_lfo1\":\"0x9e3779b9\",\"upper_lfo2\":\"0x2545f491\","
                "\"lower_lfo1\":\"(0x9e3779b9+0x51ed270b)|1 modulo 2^32\","
                "\"lower_lfo2\":\"(0x2545f491+0x9e3779b9)|1 modulo 2^32\","
                "\"source\":\"Source/DSP/SeptumEngine.h Engine defaults; SeptumEngine.cpp reset\"},"
             << "\n\"block_size\":" << requestedBlockSize
             << ",\n\"envelope_bin_seconds\":0.005,\n\"renders\":[\n";
    bool firstRow = true;
    for (const auto& item : cases)
    {
        const auto patchBytes = septum::sysex::encodePatchToSyxBuffer (item.patch);
        const auto midi = midiBytes (item);
        const auto patchHash = fingerprint (patchBytes), midiHash = fingerprint (midi);
        writeBytes (output / (item.id + ".syx"), patchBytes);
        writeBytes (output / (item.id + ".mid"), midi);
        for (int rate : { 44100, 48000, 88200, 96000 })
        {
            const auto audio = render (item, rate, requestedBlockSize, reference);
            const auto analysis = analyse (audio, item, rate);
            const auto basename = item.id + "-" + std::to_string (rate);
            const auto raw = wavBytes (audio, rate);
            writeBytes (output / (basename + ".raw.wav"), raw);
            writeText (output / (basename + ".envelope.csv"), analysis.envelopeCsv);
            writeText (output / (basename + ".spectrum.csv"), analysis.spectrumCsv);
            rows.push_back ({ item.id, patchHash, midiHash, basename, rate, analysis.metrics });
            for (const auto& [name, value] : analysis.metrics)
                summary << item.id << '\t' << rate << '\t' << patchHash << '\t' << midiHash << '\t'
                        << name << '\t' << number (value) << '\n';
            if (! firstRow) manifest << ",\n";
            firstRow = false;
            manifest << "{\"fixture\":" << quote (item.id) << ",\"category\":" << quote (item.category)
                     << ",\"patch_name\":" << quote (item.patch.name)
                     << ",\"host_rate_hz\":" << rate << ",\"engine_rate_hz\":"
                     << (reference ? septum::ReferenceRateEngine::referenceRateHz : rate)
                     << ",\"raw_wav\":" << quote ((output / (basename + ".raw.wav")).string())
                     << ",\"wav_fnv1a64\":" << quote (fingerprint (raw))
                     << ",\"patch_sysex\":" << quote (item.id + ".syx")
                     << ",\"patch_fnv1a64\":" << quote (patchHash)
                     << ",\"midi_file\":" << quote (item.id + ".mid")
                     << ",\"midi_fnv1a64\":" << quote (midiHash)
                     << ",\"duration_ms\":" << item.durationMs << ",\"events\":[";
            for (std::size_t i = 0; i < item.events.size(); ++i)
            {
                const auto& event = item.events[i];
                if (i > 0) manifest << ',';
                manifest << "{\"time_ms\":" << event.milliseconds << ",\"sample_offset\":"
                         << std::llround (event.milliseconds * (rate / 1000.0)) << ",\"raw_midi\":["
                         << (event.on ? 144 : 128) << ',' << event.note << ',' << event.velocity << "]}";
            }
            manifest << "],\"metrics\":{";
            bool firstMetric = true;
            for (const auto& [name, value] : analysis.metrics)
            { if (! firstMetric) manifest << ','; firstMetric = false; manifest << quote (name) << ':' << number (value); }
            manifest << "}}";
            std::cout << basename << " rms=" << analysis.metrics.at ("rms") << '\n';
        }
    }
    manifest << "\n]}\n";
    writeText (output / "summary.tsv", summary.str());
    writeText (output / "manifest.json", manifest.str());
    const auto own = readSummary (output / "summary.tsv");
    comparison (rows, own, output / "rate-comparison.tsv", true);
    if (! baseline.empty()) comparison (rows, readSummary (baseline / "summary.tsv"), output / "baseline-comparison.tsv", false);
    if (listening)
    {
        std::ostringstream gains;
        gains << "raw_wav\tlistening_wav\trms_match_gain\tset_headroom_gain\ttotal_gain\n";
        std::map<std::string, double> groupPeak;
        for (const auto& row : rows)
        {
            if (row.metrics.at ("rms") <= 1.0e-12
                || own.at (row.id + "@44100").metrics.at ("rms") <= 1.0e-12)
                throw std::runtime_error ("Cannot level-match silent fixture " + row.id
                                          + "; raw measurements have been preserved");
            const double match = own.at (row.id + "@44100").metrics.at ("rms") / row.metrics.at ("rms");
            groupPeak[row.id] = std::max (groupPeak[row.id], row.metrics.at ("peak") * match);
        }
        for (const auto& row : rows)
        {
            const double match = own.at (row.id + "@44100").metrics.at ("rms") / row.metrics.at ("rms");
            const double headroom = std::min (1.0, 0.5 / groupPeak.at (row.id));
            writeBytes (output / (row.basename + ".listening.wav"),
                        wavBytes (readOwnWav (output / (row.basename + ".raw.wav")), row.rate, match * headroom));
            gains << row.basename << ".raw.wav\t" << row.basename << ".listening.wav\t"
                  << number (match) << '\t' << number (headroom) << '\t' << number (match * headroom) << '\n';
        }
        writeText (output / "listening-gains.tsv", gains.str());
    }
    std::cout << "Wrote " << rows.size() << " raw measurements to " << output << '\n';
    return 0;
}
} // namespace

int main (int argc, char** argv)
{
    try { return run (argc, argv); }
    catch (const std::exception& error)
    { std::cerr << "Fidelity analysis error: " << error.what() << '\n'; return 1; }
}

#include "DSP/AnalogOutput.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <complex>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>

namespace
{
constexpr double pi = 3.14159265358979323846;
int failures = 0;

void expect (bool condition, const char* message)
{
    if (! condition)
    {
        ++failures;
        std::cerr << "FAIL: " << message << '\n';
    }
}

// Independent circuit reference: solve the two node equations at the RC
// junctions, with IC25's frequency-dependent closed-loop gain. Component
// values are those on Roland Service Notes printed pp.36-37.
std::complex<double> nodalReference (double hz)
{
    const std::complex<double> s (0.0, 2.0 * pi * hz);
    const auto feedbackImpedance = 33000.0 / (1.0 + s * 33000.0 * 10.0e-12);
    const auto k = 1.0 + feedbackImpedance / 22000.0;
    const auto a11 = 1.0 / 4700.0 + 1.0 / 8200.0 + s * 270.0e-12;
    const auto a12 = -1.0 / 8200.0 - s * 270.0e-12 * k;
    const auto a21 = -1.0 / 8200.0;
    const auto a22 = 1.0 / 8200.0 + s * 820.0e-12;
    const auto v2 = -(1.0 / 4700.0) * a21 / (a11 * a22 - a12 * a21);
    const auto coupling = s * (22.0e-6 * 22000.0)
                          / (1.0 + s * (22.0e-6 * 22000.0));
    return coupling * v2 * k / 2.5;
}

std::complex<double> measure (double sampleRate, double hz)
{
    septum::AnalogOutput output;
    output.prepare (sampleRate);
    // A one-second capture contains whole cycles at every test frequency,
    // avoiding window/leakage estimates. Discard the initial 0.25 seconds.
    const int settle = static_cast<int> (std::lround (sampleRate * 0.25));
    const int count = static_cast<int> (std::lround (sampleRate));
    std::complex<double> response {};
    for (int n = 0; n < settle + count; ++n)
    {
        const double phase = 2.0 * pi * hz * n / sampleRate;
        const double y = output.processSample (std::cos (phase));
        if (n >= settle)
            response += y * std::complex<double> (std::cos (phase), -std::sin (phase));
    }
    response *= 2.0 / count;
    // Remove only the documented sample-rate-conversion transport delay.
    return response * std::polar (1.0, 2.0 * pi * hz
                                           * septum::AnalogOutput::latencySamples / sampleRate);
}

void testNodalTransfer()
{
    for (double hz : { 0.0, 0.329, 20.0, 1000.0, 10000.0, 20000.0, 100000.0 })
        expect (std::abs (septum::AnalogOutput::analogResponse (hz) - nodalReference (hz)) < 1.0e-12,
                "analytic transfer matches independently solved component network");

    const double corner = 1.0 / (2.0 * pi * 22.0e-6 * 22000.0);
    expect (std::abs (20.0 * std::log10 (std::abs (nodalReference (corner))) + 3.0102999566) < 1.0e-6,
            "output coupling is 0.329 Hz; ADC-only 3.4 Hz filter is absent");
    const auto legacy = [](double hz)
    {
        return 1.0 / std::sqrt ((1.0 + std::pow (hz / 23700.0, 2.0))
                               * (1.0 + std::pow (hz / 125400.0, 2.0)));
    };
    const double correction = 20.0 * std::log10 (std::abs (nodalReference (20000.0)) / legacy (20000.0));
    expect (correction < -0.3 && correction > -0.7,
            "active capacitor feedback produces a measurable correction to independent RC poles");
}

void testAudioBandResponse()
{
    for (double fs : { 44100.0, 48000.0, 96000.0, 192000.0 })
    {
        double worstDb = 0.0, worstDegrees = 0.0;
        for (double hz : { 20.0, 100.0, 1000.0, 5000.0, 10000.0, 15000.0, 20000.0 })
        {
            const auto error = measure (fs, hz) / nodalReference (hz);
            worstDb = std::max (worstDb, std::abs (20.0 * std::log10 (std::abs (error))));
            worstDegrees = std::max (worstDegrees, std::abs (std::arg (error) * 180.0 / pi));
        }
        std::cout << fs << " Hz: max magnitude error " << worstDb
                  << " dB; phase error " << worstDegrees << " degrees\n";
        expect (worstDb < 0.08, "sampled output follows the analog magnitude within 0.08 dB to 20 kHz");
        expect (worstDegrees < 0.8, "sampled output follows analog phase within 0.8 degrees after transport delay");
    }
}

void testTransportAndReset()
{
    septum::analog_output_detail::Oversampling8 converter;
    std::array<double, 512> impulse {};
    double sum = 0.0, moment = 0.0, symmetryError = 0.0;
    for (std::size_t n = 0; n < impulse.size(); ++n)
    {
        impulse[n] = converter.process (n == 0 ? 1.0 : 0.0, [](double x) { return x; });
        sum += impulse[n];
        moment += n * impulse[n];
    }
    constexpr int delay = septum::AnalogOutput::latencySamples;
    for (int n = 0; n <= 2 * delay; ++n)
        symmetryError = std::max (symmetryError, std::abs (impulse[n] - impulse[2 * delay - n]));
    expect (std::abs (sum - 1.0) < 1.0e-12, "resampling preserves nominal unity gain");
    expect (std::abs (moment / sum - delay) < 1.0e-10 && symmetryError < 1.0e-14,
            "resampling has exactly the reported 74-sample linear-phase transport delay");

    septum::AnalogOutput output;
    output.prepare (44100.0);
    std::array<double, 512> first {}, second {};
    for (std::size_t n = 0; n < first.size(); ++n)
        first[n] = output.processSample (n == 0 ? 1.0 : 0.0);
    output.reset();
    for (std::size_t n = 0; n < second.size(); ++n)
        second[n] = output.processSample (n == 0 ? 1.0 : 0.0);
    expect (first == second, "reset clears both circuit and sample-rate-conversion history");
    output.reset();
    for (int n = 0; n < 1024; ++n)
        expect (output.processSample (0.0) == 0.0, "reset leaves no output tail");

    for (double fs : { 8000.0, 22050.0, 384000.0, std::numeric_limits<double>::quiet_NaN() })
    {
        output.prepare (fs);
        bool finite = true;
        for (int n = 0; n < 4096; ++n)
            finite = finite && std::isfinite (output.processSample (n & 1 ? 1.0 : -1.0));
        expect (finite, "valid and defensive fallback rates remain finite");
    }
}

bool writeResponseCsv (const std::string& path)
{
    std::ofstream csv (path);
    if (! csv)
    {
        std::cerr << "Cannot write response CSV: " << path << '\n';
        return false;
    }
    csv << std::setprecision (12)
        << "sample_rate_hz,frequency_hz,analog_magnitude_db,measured_magnitude_db,"
           "legacy_analog_magnitude_db,analog_phase_deg,measured_phase_deg,"
           "magnitude_error_db,phase_error_deg\n";
    for (double fs : { 44100.0, 48000.0, 96000.0, 192000.0 })
    {
        for (int point = 0; point <= 80; ++point)
        {
            // Whole-Hz frequencies keep the one-second measurement coherent.
            const double hz = std::round (20.0 * std::pow (1000.0, point / 80.0));
            const auto analog = nodalReference (hz);
            const auto measured = measure (fs, hz);
            const auto error = measured / analog;
            const double legacy = 1.0 / std::sqrt (
                (1.0 + std::pow (hz / 23700.0, 2.0))
                * (1.0 + std::pow (hz / 125400.0, 2.0)));
            csv << fs << ',' << hz << ','
                << 20.0 * std::log10 (std::abs (analog)) << ','
                << 20.0 * std::log10 (std::abs (measured)) << ','
                << 20.0 * std::log10 (legacy) << ','
                << std::arg (analog) * 180.0 / pi << ','
                << std::arg (measured) * 180.0 / pi << ','
                << 20.0 * std::log10 (std::abs (error)) << ','
                << std::arg (error) * 180.0 / pi << '\n';
        }
    }
    std::cout << "Wrote measured circuit response to " << path << '\n';
    return static_cast<bool> (csv);
}
} // namespace

int main (int argc, char** argv)
{
    std::string csvPath;
    if (argc == 3 && std::string (argv[1]) == "--response-csv")
        csvPath = argv[2];
    else if (argc != 1)
    {
        std::cerr << "Usage: SeptumAnalogOutputTests [--response-csv PATH]\n";
        return 1;
    }
    testNodalTransfer();
    testAudioBandResponse();
    testTransportAndReset();
    if (failures == 0)
        std::cout << "Analog output circuit checks passed\n";
    if (failures == 0 && ! csvPath.empty() && ! writeResponseCsv (csvPath))
        return 1;
    return failures == 0 ? 0 : 1;
}

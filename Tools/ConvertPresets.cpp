// Offline SH-201 SysEx to Septum native preset conversion. Use the same
// message-thread import/save/load paths as the plug-in, including arp grids.

#include "PluginProcessor.h"
#include "DSP/SeptumSysEx.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <set>
#include <stdexcept>
#include <vector>

namespace
{
struct Conversion
{
    juce::File input;
    juce::File output;
    juce::MemoryBlock bytes;
    septum::Patch patch;
    std::array<std::vector<std::uint8_t>, 22> blocks;
};

[[noreturn]] void fail (const juce::String& message)
{
    throw std::runtime_error (message.toStdString());
}

juce::File resolve (const juce::String& path, const juce::File& base)
{
    if (path.isEmpty())
        fail ("Empty conversion path");
    return juce::File::isAbsolutePath (path) ? juce::File (path)
                                          : base.getChildFile (path);
}

void validateSource (Conversion& item)
{
    if (! item.input.existsAsFile() || item.input.getSize() <= 0
        || item.input.getSize() > 64 * 1024)
        fail ("Expected one complete SH-201 patch: " + item.input.getFullPathName());
    if (! item.input.loadFileAsData (item.bytes))
        fail ("Cannot read " + item.input.getFullPathName());

    const auto* bytes = static_cast<const std::uint8_t*> (item.bytes.getData());
    const auto size = item.bytes.getSize();
    std::size_t position = 0;
    std::uint32_t patchBase = 0;
    std::array<bool, 22> seen {};
    while (position < size)
    {
        if (bytes[position] != 0xf0)
            fail ("Unexpected bytes outside SysEx in " + item.input.getFullPathName());
        const auto* end = std::find (bytes + position, bytes + size, 0xf7);
        if (end == bytes + size)
            fail ("Truncated SysEx in " + item.input.getFullPathName());
        const auto length = static_cast<std::size_t> (end - (bytes + position)) + 1;
        septum::sysex::Dt1Packet packet;
        if (! septum::sysex::parseDt1Packet (bytes + position, length, 0x7f, packet)
            || ! packet.isForThisInstrument() || packet.offsetInBlock() != 0
            || packet.dataLength != packet.blockSize())
            fail ("Expected a valid complete SH-201 DT1 block in " + item.input.getFullPathName());
        if (position == 0)
            patchBase = packet.patchBase();
        if (packet.patchBase() != patchBase || seen[packet.block()])
            fail ("Expected one patch with no repeated blocks in " + item.input.getFullPathName());
        seen[packet.block()] = true;
        item.blocks[packet.block()].assign (packet.data, packet.data + packet.dataLength);
        position += length;
    }
    if (! std::all_of (seen.begin(), seen.end(), [] (bool value) { return value; }))
        fail ("Incomplete patch: all 22 blocks, including every arpeggio row, are required: "
              + item.input.getFullPathName());

    std::vector<septum::NamedPatch> bank;
    if (! septum::sysex::parseSyxBankFile (bytes, size, bank) || bank.size() != 1)
        fail ("Cannot decode one SH-201 patch from " + item.input.getFullPathName());
    item.patch = bank.front().patch;
}

void verifyPatch (septum::Patch actual, septum::Patch expected,
                  const juce::String& context)
{
    // The APVTS snapshot has INIT PATCH as its wire name. Native preset names
    // belong to preset_name and use the chosen filename. Compare sound data
    // separately so this documented display-name difference cannot hide a
    // tone, effect or arpeggio parameter loss.
    actual.name = expected.name;
    if (septum::sysex::encodePatchToSyxBuffer (actual)
        != septum::sysex::encodePatchToSyxBuffer (expected))
        fail ("Native patch parameter mismatch: " + context);
    const auto& a = actual.arpeggio.style;
    const auto& b = expected.arpeggio.style;
    if (a.endStep != b.endStep || a.originalNote != b.originalNote || a.cells != b.cells)
        fail ("Native arpeggio grid mismatch: " + context);
}

juce::var sourceDifferences (const Conversion& item)
{
    juce::Array<juce::var> differences;
    for (const auto& message : septum::sysex::encodePatchToSysExPackets (item.patch))
    {
        septum::sysex::Dt1Packet packet;
        if (! septum::sysex::parseDt1Packet (message.data(), message.size(), 0x7f, packet))
            fail ("Internal canonical SysEx encoding failed");
        const auto& original = item.blocks[packet.block()];
        for (std::size_t offset = 0; offset < packet.dataLength; ++offset)
            if (original[offset] != packet.data[offset])
            {
                auto difference = std::make_unique<juce::DynamicObject>();
                difference->setProperty ("block", static_cast<int> (packet.block()));
                difference->setProperty ("offset", static_cast<int> (offset));
                difference->setProperty ("source", static_cast<int> (original[offset]));
                difference->setProperty ("native", static_cast<int> (packet.data[offset]));
                differences.add (juce::var (difference.release()));
            }
    }
    return differences;
}

juce::var convert (Conversion& item, SeptumAudioProcessor& source,
                   SeptumAudioProcessor& restored, const juce::MemoryBlock& baseline)
{
    source.setStateInformation (baseline.getData(), static_cast<int> (baseline.getSize()));
    source.loadSysExData (item.bytes.getData(), item.bytes.getSize());
    verifyPatch (source.snapshotPatch(), item.patch, item.input.getFullPathName());
    if (const auto created = item.output.getParentDirectory().createDirectory(); created.failed())
        fail (created.getErrorMessage());
    // Recheck after preflight: saving must never replace an existing preset.
    if (item.output.exists())
        fail ("Refusing to replace " + item.output.getFullPathName());
    if (const auto saved = source.savePresetToFile (item.output); saved.failed())
        fail (saved.getErrorMessage());
    if (const auto loaded = restored.loadPresetFromFile (item.output); loaded.failed())
        fail (loaded.getErrorMessage());
    verifyPatch (restored.snapshotPatch(), item.patch, item.output.getFullPathName());
    if (source.createSysExDataForCurrentPatch() != restored.createSysExDataForCurrentPatch()
        || restored.getCurrentPresetName() != item.output.getFileNameWithoutExtension())
        fail ("Native preset reload differs from the saved state: " + item.output.getFullPathName());

    // Native presets also carry system/extension settings, so verify every
    // APVTS parameter rather than checking only fields with a SysEx address.
    for (const auto* parameter : source.getParameters())
        if (const auto* identified = dynamic_cast<const juce::AudioProcessorParameterWithID*> (parameter))
        {
            const auto& id = identified->paramID;
            const auto before = source.parameters.getRawParameterValue (id)->load();
            const auto after = restored.parameters.getRawParameterValue (id)->load();
            if (std::abs (before - after) > 0.00001f)
                fail ("Native parameter reload changed " + id + " in " + item.output.getFullPathName());
        }

    auto result = std::make_unique<juce::DynamicObject>();
    result->setProperty ("input", item.input.getFullPathName());
    result->setProperty ("output", item.output.getFullPathName());
    result->setProperty ("source_name", juce::String (item.patch.name));
    result->setProperty ("native_name", restored.getCurrentPresetName());
    result->setProperty ("native_bytes", item.output.getSize());
    result->setProperty ("source_parameter_differences", sourceDifferences (item));
    result->setProperty ("native_roundtrip_verified", true);
    result->setProperty ("arpeggio_grid_verified", true);
    return juce::var (result.release());
}
} // namespace

int main (int argc, char* argv[])
{
    try
    {
        juce::String input, output, manifest;
        for (int i = 1; i < argc; ++i)
        {
            const juce::String argument (argv[i]);
            if (argument == "--help")
            {
                std::cout << "SeptumConvertPresets --manifest conversions.json\n"
                             "SeptumConvertPresets --input patch.syx --output Name.septum\n"
                             "Manifest: [{\"input\":\"patch.syx\",\"output\":\"Name.septum\"}, ...]\n"
                             "Relative manifest paths resolve beside the manifest. Existing outputs are refused.\n";
                return 0;
            }
            if (i + 1 >= argc)
                fail ("Missing argument value: " + argument);
            if (argument == "--input" && input.isEmpty()) input = argv[++i];
            else if (argument == "--output" && output.isEmpty()) output = argv[++i];
            else if (argument == "--manifest" && manifest.isEmpty()) manifest = argv[++i];
            else fail ("Unknown or repeated argument: " + argument);
        }
        const auto cwd = juce::File::getCurrentWorkingDirectory();
        std::vector<Conversion> items;
        if (manifest.isNotEmpty())
        {
            if (input.isNotEmpty() || output.isNotEmpty())
                fail ("Use --manifest or --input/--output, not both");
            const auto file = resolve (manifest, cwd);
            if (! file.existsAsFile() || file.getSize() > 8 * 1024 * 1024)
                fail ("Missing or oversized conversion manifest");
            juce::var parsed;
            if (const auto status = juce::JSON::parse (file.loadFileAsString(), parsed); status.failed())
                fail (status.getErrorMessage());
            const auto* entries = parsed.getArray();
            if (entries == nullptr || entries->isEmpty() || entries->size() > 10000)
                fail ("Manifest must be a nonempty array of at most 10000 conversions");
            for (const auto& entry : *entries)
            {
                if (! entry.isObject() || ! entry["input"].isString() || ! entry["output"].isString())
                    fail ("Each conversion requires string input and output paths");
                items.push_back ({ resolve (entry["input"].toString(), file.getParentDirectory()),
                                   resolve (entry["output"].toString(), file.getParentDirectory()), {}, {}, {} });
            }
        }
        else
        {
            if (input.isEmpty() || output.isEmpty())
                fail ("Use --manifest conversions.json or --input patch.syx --output Name.septum");
            items.push_back ({ resolve (input, cwd), resolve (output, cwd), {}, {}, {} });
        }
        std::set<juce::String> destinations;
        for (auto& item : items)
        {
            if (item.output.exists() || item.output == item.input
                || ! destinations.insert (item.output.getFullPathName()).second)
                fail ("Output exists, duplicates another output, or equals input: " + item.output.getFullPathName());
            if (! item.output.hasFileExtension (".septum"))
                fail ("Native output must have .septum extension: " + item.output.getFullPathName());
            validateSource (item);
        }

        juce::ScopedJuceInitialiser_GUI initialiser;
        SeptumAudioProcessor source, restored;
        juce::MemoryBlock baseline;
        source.getStateInformation (baseline);
        juce::Array<juce::var> conversions;
        for (auto& item : items)
            conversions.add (convert (item, source, restored, baseline));
        auto result = std::make_unique<juce::DynamicObject>();
        result->setProperty ("converted", static_cast<int> (items.size()));
        result->setProperty ("comparison", "Source decoded through the current codec; every native sound parameter and arpeggio grid verified after reload. Display name uses output basename. Reported source byte differences are codec normalization, not changes to the source SysEx file.");
        result->setProperty ("conversions", conversions);
        std::cout << juce::JSON::toString (juce::var (result.release()), true).toStdString() << '\n';
        return 0;
    }
    catch (const std::exception& error)
    {
        std::cerr << "SeptumConvertPresets: " << error.what() << '\n';
        return 1;
    }
}

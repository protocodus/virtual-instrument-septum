cmake_minimum_required(VERSION 3.22)

if(POLICY CMP0135)
    cmake_policy(SET CMP0135 NEW)
endif()

option(SEPTUM_BUILD_UNIVERSAL "Build arm64 and x86_64 slices on macOS" ON)

# These must be established before project() so CMake's compiler checks use the
# same deployment target and architectures as the final plug-in.
if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Darwin")
    if(NOT DEFINED CMAKE_OSX_DEPLOYMENT_TARGET)
        set(CMAKE_OSX_DEPLOYMENT_TARGET "11.0" CACHE STRING
            "Minimum supported macOS version")
    endif()

    if(SEPTUM_BUILD_UNIVERSAL AND NOT DEFINED CMAKE_OSX_ARCHITECTURES)
        set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING
            "macOS architectures")
    endif()
endif()

# C is required in addition to C++: JUCE's macOS plug-in wrappers (AU and
# Standalone) compile C/Objective-C sources with non-Xcode generators too.
project(Septum VERSION 0.9.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(SEPTUM_BUILD_PLUGIN "Build the JUCE plug-in and standalone app" ON)
set(SEPTUM_JUCE_PATH "" CACHE PATH
    "Optional path to a local JUCE 8.0.14 checkout (avoids downloading JUCE)")

include(CTest)

set(SEPTUM_DSP_SOURCES
    Source/DSP/SeptumEngine.cpp
    Source/DSP/SeptumPresets.cpp
    Source/DSP/SeptumSysEx.cpp)
set(SEPTUM_DSP_HEADERS
    Source/DSP/AnalogInput.h
    Source/DSP/AnalogOutput.h
    Source/DSP/DelayInterpolation.h
    Source/DSP/ReverbDamping.h
    Source/DSP/MidiTempoClock.h
    Source/DSP/SeptumEngine.h
    Source/DSP/SeptumPatch.h
    Source/DSP/SeptumPresets.h
    Source/DSP/SeptumSysEx.h)

add_library(SeptumDSP STATIC
    ${SEPTUM_DSP_SOURCES}
    ${SEPTUM_DSP_HEADERS})

target_include_directories(SeptumDSP
    PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/Source")
target_compile_features(SeptumDSP PUBLIC cxx_std_20)
set_target_properties(SeptumDSP PROPERTIES POSITION_INDEPENDENT_CODE ON)

# A2 fidelity experiment. Kept separate from the shipping engine until MIDI,
# input latency and CPU tradeoffs are resolved with the comparison tools.
add_library(SeptumReferenceDSP STATIC Source/DSP/ReferenceRateEngine.cpp)
target_link_libraries(SeptumReferenceDSP PUBLIC SeptumDSP)
target_compile_features(SeptumReferenceDSP PUBLIC cxx_std_20)

if(MSVC)
    target_compile_options(SeptumDSP PRIVATE /W4 /permissive-)
else()
    target_compile_options(SeptumDSP PRIVATE -Wall -Wextra -Wpedantic)
endif()

if(SEPTUM_BUILD_PLUGIN)
    if(SEPTUM_JUCE_PATH)
        if(NOT EXISTS "${SEPTUM_JUCE_PATH}/CMakeLists.txt")
            message(FATAL_ERROR
                "SEPTUM_JUCE_PATH does not contain a JUCE CMakeLists.txt: ${SEPTUM_JUCE_PATH}")
        endif()
        add_subdirectory("${SEPTUM_JUCE_PATH}"
                         "${CMAKE_CURRENT_BINARY_DIR}/JUCE" EXCLUDE_FROM_ALL)
    else()
        include(FetchContent)
        FetchContent_Declare(
            JUCE
            # JUCE 8.0.14, pinned to its immutable release commit and archive
            # checksum so automated release builds cannot follow a moved tag.
            URL https://github.com/juce-framework/JUCE/archive/2cdfca8feb300fb424002ba2c2751569e5bacb64.tar.gz
            URL_HASH SHA256=814019716960a16f8f850a1593eeb56e2f21910aff2d673f7d3513b4ebaf251d)
        FetchContent_MakeAvailable(JUCE)
    endif()

    if(APPLE)
        set(SEPTUM_PLUGIN_FORMATS VST3 AU Standalone)
    else()
        set(SEPTUM_PLUGIN_FORMATS VST3 Standalone)
    endif()

    juce_add_plugin(Septum
        VERSION ${PROJECT_VERSION}
        COMPANY_NAME "Protocodus"
        COMPANY_WEBSITE "https://protocodus.cz"
        COMPANY_EMAIL "protocodus@proton.me"
        COMPANY_COPYRIGHT "Copyright (c) 2026 Protocodus"
        BUNDLE_ID "cz.protocodus.septum"
        PLUGIN_MANUFACTURER_CODE Sptm
        PLUGIN_CODE Spt1
        PRODUCT_NAME "Septum"
        DESCRIPTION "Septum ten-voice virtual-analog synthesizer"
        FORMATS ${SEPTUM_PLUGIN_FORMATS}
        VST3_CATEGORIES Instrument Synth
        AU_MAIN_TYPE kAudioUnitType_MusicDevice
        IS_SYNTH TRUE
        NEEDS_MIDI_INPUT TRUE
        NEEDS_MIDI_OUTPUT FALSE
        IS_MIDI_EFFECT FALSE
        EDITOR_WANTS_KEYBOARD_FOCUS TRUE
        AU_SANDBOX_SAFE TRUE
        COPY_PLUGIN_AFTER_BUILD FALSE)

    juce_generate_juce_header(Septum)

    target_sources(Septum PRIVATE
        Source/PluginProcessor.cpp
        Source/PluginProcessor.h
        Source/PluginEditor.cpp
        Source/PluginEditor.h)

    target_link_libraries(Septum
        PRIVATE
            SeptumDSP
            juce::juce_audio_utils
            juce::juce_dsp
        PUBLIC
            juce::juce_recommended_config_flags
            juce::juce_recommended_lto_flags
            juce::juce_recommended_warning_flags)

    target_compile_definitions(Septum
        PUBLIC
            JUCE_WEB_BROWSER=0
            JUCE_USE_CURL=0
            JUCE_VST3_CAN_REPLACE_VST2=0)
endif()

# The demonstration WAVs under Docs/audio are rendered by this tool
# from the same JUCE-free engine the plug-in uses, so they cannot drift away
# from what Septum actually produces. It is built by default, including on
# Linux CI, so it cannot rot unnoticed.
option(SEPTUM_BUILD_TOOLS "Build offline Septum tools" ON)

if(SEPTUM_BUILD_TOOLS)
    add_executable(SeptumRenderMidi Tools/RenderMidi.cpp)
    target_link_libraries(SeptumRenderMidi PRIVATE SeptumDSP)
    target_compile_features(SeptumRenderMidi PRIVATE cxx_std_20)

    add_executable(SeptumAnalyzeFidelity Tools/AnalyzeFidelity.cpp)
    target_link_libraries(SeptumAnalyzeFidelity PRIVATE SeptumReferenceDSP)
    target_compile_features(SeptumAnalyzeFidelity PRIVATE cxx_std_20)

    add_executable(SeptumRenderDemos Tools/RenderDemos.cpp)
    target_link_libraries(SeptumRenderDemos PRIVATE SeptumDSP)
    target_compile_features(SeptumRenderDemos PRIVATE cxx_std_20)

    if(MSVC)
        target_compile_options(SeptumRenderDemos PRIVATE /W4 /permissive-)
    else()
        target_compile_options(SeptumRenderDemos PRIVATE
            -Wall -Wextra -Wpedantic)
    endif()
endif()

if(BUILD_TESTING)
    add_executable(SeptumAmpEnvelopeLatencyTests Tests/AmpEnvelopeLatencyTests.cpp)
    target_link_libraries(SeptumAmpEnvelopeLatencyTests PRIVATE SeptumDSP)
    add_test(NAME Septum.AmpEnvelopeLatency COMMAND SeptumAmpEnvelopeLatencyTests)
    set_tests_properties(Septum.AmpEnvelopeLatency PROPERTIES TIMEOUT 120)

    add_executable(SeptumSplitPolyphonyTests Tests/SplitPolyphonyTests.cpp)
    target_link_libraries(SeptumSplitPolyphonyTests PRIVATE SeptumDSP)
    add_test(NAME Septum.SplitPolyphony COMMAND SeptumSplitPolyphonyTests)
    set_tests_properties(Septum.SplitPolyphony PROPERTIES TIMEOUT 120)

    add_executable(SeptumTempoClockTests Tests/TempoClockTests.cpp)
    target_link_libraries(SeptumTempoClockTests PRIVATE SeptumDSP)
    add_test(NAME Septum.TempoClock COMMAND SeptumTempoClockTests)
    set_tests_properties(Septum.TempoClock PROPERTIES TIMEOUT 120)

    add_executable(SeptumMidiPortamentoTests Tests/MidiPortamentoTests.cpp)
    target_link_libraries(SeptumMidiPortamentoTests PRIVATE SeptumDSP)
    add_test(NAME Septum.MidiPortamento COMMAND SeptumMidiPortamentoTests)
    set_tests_properties(Septum.MidiPortamento PROPERTIES TIMEOUT 120)

    add_executable(SeptumReverbDampingTests Tests/ReverbDampingTests.cpp)
    target_link_libraries(SeptumReverbDampingTests PRIVATE SeptumDSP)
    add_test(NAME Septum.ReverbDamping COMMAND SeptumReverbDampingTests)
    set_tests_properties(Septum.ReverbDamping PROPERTIES TIMEOUT 120)

    add_executable(SeptumFeedbackSyncTests Tests/FeedbackSyncTests.cpp)
    target_link_libraries(SeptumFeedbackSyncTests PRIVATE SeptumDSP)
    add_test(NAME Septum.FeedbackSync COMMAND SeptumFeedbackSyncTests)
    set_tests_properties(Septum.FeedbackSync PROPERTIES TIMEOUT 120)

    add_executable(SeptumPortamentoContinuityTests Tests/PortamentoContinuityTests.cpp)
    target_link_libraries(SeptumPortamentoContinuityTests PRIVATE SeptumDSP)
    add_test(NAME Septum.PortamentoContinuity COMMAND SeptumPortamentoContinuityTests)
    set_tests_properties(Septum.PortamentoContinuity PROPERTIES TIMEOUT 120)

    add_executable(SeptumHardwareVoiceFidelityTests Tests/HardwareVoiceFidelityTests.cpp)
    target_link_libraries(SeptumHardwareVoiceFidelityTests PRIVATE SeptumDSP)
    add_test(NAME Septum.HardwareVoiceFidelity COMMAND SeptumHardwareVoiceFidelityTests)
    set_tests_properties(Septum.HardwareVoiceFidelity PROPERTIES TIMEOUT 120)

    add_executable(SeptumHardwarePerformanceFidelityTests Tests/HardwarePerformanceFidelityTests.cpp)
    target_link_libraries(SeptumHardwarePerformanceFidelityTests PRIVATE SeptumDSP)
    add_test(NAME Septum.HardwarePerformanceFidelity COMMAND SeptumHardwarePerformanceFidelityTests)
    set_tests_properties(Septum.HardwarePerformanceFidelity PROPERTIES TIMEOUT 120)

    add_executable(SeptumControlSmoothingTests Tests/ControlSmoothingTests.cpp)
    target_link_libraries(SeptumControlSmoothingTests PRIVATE SeptumDSP)
    add_test(NAME Septum.ControlSmoothing COMMAND SeptumControlSmoothingTests)
    set_tests_properties(Septum.ControlSmoothing PROPERTIES TIMEOUT 120)

    add_executable(SeptumEffectsQualityTests Tests/EffectsQualityTests.cpp)
    target_link_libraries(SeptumEffectsQualityTests PRIVATE SeptumDSP)
    add_test(NAME Septum.EffectsQuality COMMAND SeptumEffectsQualityTests)
    set_tests_properties(Septum.EffectsQuality PROPERTIES TIMEOUT 120)

    add_executable(SeptumAnalogOutputTests Tests/AnalogOutputTests.cpp)
    target_link_libraries(SeptumAnalogOutputTests PRIVATE SeptumDSP)
    add_test(NAME Septum.AnalogOutput COMMAND SeptumAnalogOutputTests)
    set_tests_properties(Septum.AnalogOutput PROPERTIES TIMEOUT 240)

    find_package(Python3 COMPONENTS Interpreter QUIET)
    if(Python3_Interpreter_FOUND)
        if(SEPTUM_BUILD_TOOLS)
            add_test(NAME Septum.MidiRender
                     COMMAND "${Python3_EXECUTABLE}" -B
                             "${CMAKE_CURRENT_SOURCE_DIR}/Tests/MidiRenderTests.py"
                             --renderer "$<TARGET_FILE:SeptumRenderMidi>")
            set_tests_properties(Septum.MidiRender PROPERTIES TIMEOUT 120)
        endif()
        add_test(NAME Septum.ReferencePatchExtraction
                 COMMAND "${Python3_EXECUTABLE}" -B
                         "${CMAKE_CURRENT_SOURCE_DIR}/Tests/ReferencePatchExtractionTests.py")
    endif()

    add_executable(SeptumReferenceRateEngineTests Tests/ReferenceRateEngineTests.cpp)
    target_link_libraries(SeptumReferenceRateEngineTests PRIVATE SeptumReferenceDSP)
    add_test(NAME Septum.ReferenceRateEngine COMMAND SeptumReferenceRateEngineTests)
    set_tests_properties(Septum.ReferenceRateEngine PROPERTIES TIMEOUT 240)

    add_executable(SeptumEngineTests Tests/SeptumEngineTests.cpp)
    target_link_libraries(SeptumEngineTests PRIVATE SeptumDSP)
    target_compile_features(SeptumEngineTests PRIVATE cxx_std_20)

    if(MSVC)
        target_compile_options(SeptumEngineTests PRIVATE /W4 /permissive-)
    else()
        target_compile_options(SeptumEngineTests PRIVATE
            -Wall -Wextra -Wpedantic)
    endif()

    add_test(NAME Septum.Engine COMMAND SeptumEngineTests)
    # The suite renders every factory patch at two sample rates; allow slack
    # for slower CI workers.
    set_tests_properties(Septum.Engine PROPERTIES TIMEOUT 240)

    if(SEPTUM_BUILD_TOOLS)
        add_test(NAME Septum.FidelityTool COMMAND SeptumAnalyzeFidelity --self-test)
        set_tests_properties(Septum.FidelityTool PROPERTIES TIMEOUT 120)

        # Guards the renderer that produces the demonstration WAVs:
        # it renders a short take to a temporary directory and checks that the
        # audio is finite, audible and written as a readable WAV.
        add_test(NAME Septum.RenderDemos
                 COMMAND SeptumRenderDemos --smoke
                         "${CMAKE_CURRENT_BINARY_DIR}/demo-smoke")
        set_tests_properties(Septum.RenderDemos PROPERTIES TIMEOUT 60)
    endif()

    if(SEPTUM_BUILD_PLUGIN)
        add_executable(SeptumMidiBankProcessorTests Tests/MidiBankProcessorTests.cpp)
        target_link_libraries(SeptumMidiBankProcessorTests PRIVATE Septum)
        target_include_directories(SeptumMidiBankProcessorTests PRIVATE
            "${CMAKE_CURRENT_SOURCE_DIR}/Source"
            "$<TARGET_PROPERTY:Septum,JUCE_GENERATED_SOURCES_DIRECTORY>"
            "$<TARGET_PROPERTY:Septum,INCLUDE_DIRECTORIES>")
        add_test(NAME Septum.MidiBankProcessor COMMAND SeptumMidiBankProcessorTests)
        set_tests_properties(Septum.MidiBankProcessor PROPERTIES TIMEOUT 120)

        add_executable(SeptumMidiModeProcessorTests Tests/MidiModeProcessorTests.cpp)
        target_link_libraries(SeptumMidiModeProcessorTests PRIVATE Septum)
        target_include_directories(SeptumMidiModeProcessorTests PRIVATE
            "${CMAKE_CURRENT_SOURCE_DIR}/Source"
            "$<TARGET_PROPERTY:Septum,JUCE_GENERATED_SOURCES_DIRECTORY>"
            "$<TARGET_PROPERTY:Septum,INCLUDE_DIRECTORIES>")
        add_test(NAME Septum.MidiModeProcessor COMMAND SeptumMidiModeProcessorTests)
        set_tests_properties(Septum.MidiModeProcessor PROPERTIES TIMEOUT 120)

        add_executable(SeptumTempoSyncProcessorTests Tests/TempoSyncProcessorTests.cpp)
        target_link_libraries(SeptumTempoSyncProcessorTests PRIVATE Septum)
        target_include_directories(SeptumTempoSyncProcessorTests PRIVATE
            "${CMAKE_CURRENT_SOURCE_DIR}/Source"
            "$<TARGET_PROPERTY:Septum,JUCE_GENERATED_SOURCES_DIRECTORY>"
            "$<TARGET_PROPERTY:Septum,INCLUDE_DIRECTORIES>")
        add_test(NAME Septum.TempoSyncProcessor COMMAND SeptumTempoSyncProcessorTests)
        set_tests_properties(Septum.TempoSyncProcessor PROPERTIES TIMEOUT 120)

        add_executable(SeptumPluginProcessorTests Tests/PluginProcessorTests.cpp)
        target_link_libraries(SeptumPluginProcessorTests PRIVATE Septum)
        target_include_directories(SeptumPluginProcessorTests PRIVATE
            "${CMAKE_CURRENT_SOURCE_DIR}/Source"
            "$<TARGET_PROPERTY:Septum,JUCE_GENERATED_SOURCES_DIRECTORY>"
            "$<TARGET_PROPERTY:Septum,INCLUDE_DIRECTORIES>")
        target_compile_features(SeptumPluginProcessorTests PRIVATE cxx_std_20)

        if(MSVC)
            target_compile_options(SeptumPluginProcessorTests PRIVATE
                /W4 /permissive-)
        else()
            target_compile_options(SeptumPluginProcessorTests PRIVATE
                -Wall -Wextra -Wpedantic)
        endif()

        add_test(NAME Septum.PluginProcessor
                 COMMAND SeptumPluginProcessorTests)
        set_tests_properties(Septum.PluginProcessor PROPERTIES TIMEOUT 120)
    endif()
endif()

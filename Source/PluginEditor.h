#pragma once

#include <JuceHeader.h>

#include "PluginProcessor.h"

#include <array>
#include <limits>
#include <memory>
#include <vector>

// The active Upper/Lower tab joins the ivory page containing TONE PLAY,
// the voice chain and modulation. The shared controls stay visible outside
// that page. Charcoal panels hold arpeggio, external input, effects, performance
// and patch/controller settings. Program, shared routing and system tuning
// occupy the top header. Part accents never tint the shared controls.
//
// Controls use consistent geometry and always display their current values.
// One set of tone controls edits the selected Upper or Lower part; the scope
// of each section is derived from its parameter bindings.

class SeptumLookAndFeel final : public juce::LookAndFeel_V4
{
public:
    SeptumLookAndFeel();

    void drawRotarySlider (juce::Graphics&, int x, int y, int width, int height,
                           float sliderPos, float rotaryStartAngle,
                           float rotaryEndAngle, juce::Slider&) override;
    void drawLinearSlider (juce::Graphics&, int x, int y, int width, int height,
                           float sliderPos, float minSliderPos,
                           float maxSliderPos, juce::Slider::SliderStyle,
                           juce::Slider&) override;
    void drawButtonBackground (juce::Graphics&, juce::Button&,
                               const juce::Colour&, bool isHighlighted,
                               bool isDown) override;
    void drawComboBox (juce::Graphics&, int width, int height, bool isDown,
                       int buttonX, int buttonY, int buttonW, int buttonH,
                       juce::ComboBox&) override;
    juce::Font getComboBoxFont (juce::ComboBox&) override;
    juce::Font getLabelFont (juce::Label&) override;
    juce::Font getTextButtonFont (juce::TextButton&, int buttonHeight) override;
    void positionComboBoxText (juce::ComboBox&, juce::Label&) override;
    void drawButtonText (juce::Graphics&, juce::TextButton&,
                         bool isHighlighted, bool isDown) override;
};

// The bend/modulation lever left of the keys: the horizontal axis bends
// pitch and springs back to center on release; the vertical axis applies
// modulation and holds its position, mirroring the hardware lever's two
// motions.
class SeptumLever final : public juce::Component
{
public:
    explicit SeptumLever (SeptumAudioProcessor& processor);

    void paint (juce::Graphics&) override;
    void mouseDown (const juce::MouseEvent&) override;
    void mouseDrag (const juce::MouseEvent&) override;
    void mouseUp (const juce::MouseEvent&) override;
    void mouseDoubleClick (const juce::MouseEvent&) override;

    [[nodiscard]] float getModulation() const noexcept { return mod; }

private:
    static constexpr int captionHeight = 16;

    void applyFromEvent (const juce::MouseEvent&);
    [[nodiscard]] juce::Rectangle<float> leverBounds() const;
    void push() noexcept;

    SeptumAudioProcessor& processor;
    float bend { 0.0f };  // -1..+1, springs back
    float mod { 0.0f };   // 0..1, latches
    // Where the modulation axis was grabbed, so a drag moves it by the travel
    // rather than jumping it to the click.
    float grabY { 0.0f };
    float grabMod { 0.0f };
};

class SeptumAudioProcessorEditor final : public juce::AudioProcessorEditor,
                                             private juce::Timer,
                                             private juce::MidiKeyboardState::Listener
{
public:
    explicit SeptumAudioProcessorEditor (SeptumAudioProcessor&);
    ~SeptumAudioProcessorEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

    // The size to open at on a display with this much usable room. Public so
    // the suite can check the fit rule on screens no build machine has to
    // have.
    [[nodiscard]] static juce::Rectangle<int> panelSizeForWorkArea (
        juce::Rectangle<int> workArea);

    // The panel itself, always laid out at its design size and scaled to
    // whatever the window is. The suite walks it to prove every control the
    // panel builds is actually placed.
    [[nodiscard]] juce::Component& getPanel() noexcept { return canvas; }

    // Three invariants the panel is built on. They were `jassert`s, which
    // NDEBUG removes from every build this project produces — the plug-in,
    // both test binaries and CI's Release — so the thing the change log called
    // "a build-time failure" was present in no build and no test. They are
    // state the suite reads now, and a green suite is what enforces them.
    //
    // Every control's parameter id resolves; a control whose id stops
    // resolving would otherwise ship drawing, hovering and dragging while
    // editing nothing.
    [[nodiscard]] const juce::StringArray& getUnresolvedParameterIds() const noexcept
    {
        return unresolvedParameterIds;
    }
    // No section mixes per-tone and shared controls. A mixed one is classified
    // by its first per-tone control and wears the stronger background tint over
    // controls that are not per-tone, which is exactly the defect Step 28
    // removed.
    [[nodiscard]] const juce::StringArray& getMixedScopeSections() const noexcept
    {
        return mixedScopeSections;
    }
    // The section titles the layout addresses by index, in index order, so
    // inserting a section cannot silently shift every list below it.
    [[nodiscard]] juce::StringArray getSectionTitles() const;
    // Sections whose laid-out contents do not fit inside their own well. A
    // section is sized to its contents rather than its contents scaled to it,
    // so one that is handed less room than it asked for does not shrink — it
    // overflows, and its bottom row of value read-outs lands on the well's
    // border. Read by the suite after a layout.
    [[nodiscard]] juce::StringArray getSectionsOverflowingTheirWell() const;

    // What the key-zone band prints beside the split boundary, and where. The
    // paint uses this, and the suite reads it: the name has to stay inside the
    // band (SPLIT POINT reaches C8 while the drawn keyboard stops at C7) and
    // has to name the key the way the keyboard under it names it.
    struct SplitPointCaption
    {
        juce::String text;
        juce::Rectangle<int> bounds;
    };
    [[nodiscard]] SplitPointCaption getSplitPointCaption() const;

    // The key SPLIT POINT falls on, named the way the drawn keys are named.
    // The parameter's own text is fixed at middle C = C4 while the keyboard is
    // renamed by SYSTEM COMMON Octave Shift, so anything printing the split
    // point has to come through here or it prints a second name for one key.
    [[nodiscard]] juce::String getSplitPointKeyName() const;

    // The line beside the edit tabs says which parts receive new keys. Actual
    // activity comes separately from the engine. The suite requires the split
    // point in it to name the same key the caption over the keys does.
    [[nodiscard]] juce::String getToneAudibilitySummary() const;

    // What the frame timer compares to decide whether the panel's own drawing
    // of the tones and the keys has to be repainted. Public so the suite can
    // check that everything that drawing depends on is actually in it: the
    // keyboard component repaints itself, but the key-zone band and its
    // split-point caption are painted by the canvas behind it, so anything the
    // band reads and this key does not goes stale on screen.
    [[nodiscard]] juce::String getKeyboardRepaintKey() const;

private:
    // A hardware panel's controls do not reflow, so the alternative to
    // scaling this one is clipping it — and 784 points of panel do not fit
    // the 768-point screen a 1366x768 laptop has. Everything the panel draws
    // lives on this canvas, which is always exactly the design size; the
    // editor only chooses the transform that maps it onto the window.
    class PanelCanvas final : public juce::Component
    {
    public:
        explicit PanelCanvas (SeptumAudioProcessorEditor& o) : owner (o) {}
        void paint (juce::Graphics&) override;

    private:
        SeptumAudioProcessorEditor& owner;
    };

    enum class Style { Knob, VSlider, Combo, WideCombo, Toggle, Action };

    // Whether a section's controls edit one tone or the whole instrument.
    // Derived from the controls themselves rather than declared, so a section
    // cannot claim a scope its contents do not have. Every section on this
    // panel is one or the other: the parameter contract keeps the per-tone
    // values in the Patch Tone blocks and the shared ones in Patch Common,
    // and the panel now follows that line exactly.
    enum class Scope { Shared, PerTone };

    // Bands describe the signal-chain grouping; scope determines the surface.
    enum class Band { Voice, Modulation, InputEffects, Perform };

    struct Control
    {
        juce::String suffix;      // per-tone parameter suffix, or full ID
        bool perTone { true };
        bool inHeader { false };
        Style style { Style::Knob };
        juce::String unit;        // printed after the value, e.g. "st", "%"
        // Bipolar direction is included in the readable value below the knob,
        // e.g. OSC1 63 or Center, instead of miniature labels on the rim.
        juce::String leftEnd, rightEnd;
        [[nodiscard]] int cellWidth() const;
        std::unique_ptr<juce::Component> component;
        std::unique_ptr<juce::Label> label;
        std::unique_ptr<juce::Label> value;
        std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment>
            sliderAttachment;
        std::unique_ptr<juce::AudioProcessorValueTreeState::ComboBoxAttachment>
            comboAttachment;
        std::unique_ptr<juce::AudioProcessorValueTreeState::ButtonAttachment>
            buttonAttachment;
    };

    struct Section
    {
        juce::String title;
        Band band { Band::Voice };
        Scope scope { Scope::Shared };
        juce::Rectangle<int> bounds;
        std::vector<Control*> controls;
        // How many of the section's grid controls go on each row. Sections
        // are sized to fit their contents rather than their contents scaled
        // to fit them, which is what keeps every knob the same size.
        std::vector<int> rowCounts;
        // Columns are shared by every row. A wide selector can span narrow
        // columns; a pair of interval buttons can share the waveform column.
        struct GridPosition { int column; int span { 1 }; int rowSpan { 1 }; };
        std::vector<int> fixedColumns;
        std::vector<std::vector<GridPosition>> positions;
        bool manualLayout { false };

        [[nodiscard]] std::vector<int> columnWidths() const;
        [[nodiscard]] int naturalWidth() const;
    };

    Control* addControl (Section& section, const juce::String& suffix,
                         const juce::String& label, Style style,
                         bool perTone = true, const juce::String& unit = {});
    // Names the two directions used in a bipolar knob's value readout.
    static void nameEnds (Control* control, const char* left, const char* right);
    // `perToneOnly` re-attaches just the controls whose parameter changes with
    // the edit target; the shared ones keep the attachment they already have.
    void bindControls (bool perToneOnly = false);
    // What the keyboard mode and part say about the two tones right now.
    struct ToneAudibility
    {
        bool upperSounds { true };
        bool lowerSounds { false };
        juce::String summary;   // complete routing description for inspection
    };
    [[nodiscard]] ToneAudibility toneAudibility() const;
    void refreshToneTarget();
    void refreshPartActivity();
    [[nodiscard]] bool isEditedPartEnabled() const;
    void refreshToneControlAvailability();
    void paintPartTabs (juce::Graphics&);
    // The edit target rides in the state tree rather than in a parameter, and
    // setStateInformation replaces the whole tree, so an open editor has to be
    // told. Called from the frame timer and from a layout.
    void reconcileEditTarget();
    void setEditingUpper (bool upper);
    void paintKeyboardZones (juce::Graphics&);
    void layoutSection (Section& section, juce::Rectangle<int> bounds);
    void layoutBand (const std::vector<int>& indices, juce::Rectangle<int> bounds);
    void refreshValues();
    void refreshPresetDisplay();
    void choosePresetFile (bool saving);
    void finishPresetFileChoice (const juce::File&, bool saving);
    // Places every control inside the design-size rectangle. Called from
    // resized(), but independent of the window: the window only sets the
    // canvas transform.
    void layoutPanel();
    void paintPanel (juce::Graphics&);
    void setToneParameter (const char* suffix, float natural);
    [[nodiscard]] float getToneParameter (const char* suffix) const;
    // What `setToneParameter` would actually store for this value. The OSC 2
    // INTERVAL buttons and their lamps compare against a target, and the write
    // snaps it to the parameter's range, so an unsnapped target near the ends
    // of the pitch range makes the button a one-way trap with a dark lamp.
    [[nodiscard]] float snapToneParameter (const char* suffix, float natural) const;
    void applyKeyboardOctave();
    void stepKeyboardOctave (int delta);
    void timerCallback() override;

    void handleNoteOn (juce::MidiKeyboardState*, int channel, int note,
                       float velocity) override;
    void handleNoteOff (juce::MidiKeyboardState*, int channel, int note,
                        float velocity) override;

    SeptumAudioProcessor& processor;
    SeptumLookAndFeel lookAndFeel;
    PanelCanvas canvas { *this };

    std::vector<std::unique_ptr<Section>> sections;
    std::vector<std::unique_ptr<Control>> controls;
    Section* performSection { nullptr };
    Section* systemSection { nullptr };
    Section* stripSection { nullptr };
    Section* tonePlaySection { nullptr };
    Section* editToneSection { nullptr };
    Section* routingSection { nullptr };
    // Controls the current keyboard mode makes inert, dimmed while it does.
    Control* partControl { nullptr };
    Control* splitPointControl { nullptr };
    Control* splitArpControl { nullptr };
    juce::Rectangle<int> meterBounds;
    // The band above the keys that says which tone each key reaches.
    juce::Rectangle<int> keyZoneBounds;

    // Shared performance strip beside patch controls.
    juce::Slider masterSlider;
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment>
        masterAttachment;
    juce::Label masterLabel, masterValueLabel, octLabel, octValueLabel, voiceLabel;
    juce::TextButton octDownButton { "DOWN" }, octUpButton { "UP" };
    Control* tempoControl { nullptr };

    // Factory selector and native preset files in the header.
    juce::ComboBox programBox;
    juce::Label programLabel;
    juce::TextButton loadPresetButton { "LOAD" }, savePresetButton { "SAVE" };
    std::unique_ptr<juce::FileChooser> presetChooser;
    juce::ScopedMessageBox presetMessageBox;
    juce::File lastPresetFile;
    // The edit-target tabs, in the header above everything they govern.
    juce::TextButton upperButton { "UPPER" }, lowerButton { "LOWER" };
    juce::TextButton upperEnableButton { "ON" }, lowerEnableButton { "ON" };
    std::unique_ptr<juce::AudioProcessorValueTreeState::ButtonAttachment>
        upperEnableAttachment, lowerEnableAttachment;
    std::array<juce::Rectangle<int>, 2> partTabBounds;
    std::array<juce::Label, 2> partRouteLabels, partActivityLabels;
    std::array<float, 2> partMeterLevels { 0.0f, 0.0f };
    juce::Label titleLabel;

    // OSC 2 INTERVAL buttons (settled behavior: -OCT one octave below,
    // 5th seven semitones above; both together = unison).
    Control* intervalOctControl { nullptr };
    Control* intervalFifthControl { nullptr };

    // Hovering any control names the parameter it edits, in the same words
    // the host's own parameter list uses.
    juce::TooltipWindow tooltips { this, 650 };

    SeptumLever lever;

public:
    // The suite drives the lever through the same path the mouse does.
    [[nodiscard]] SeptumLever& getLever() noexcept { return lever; }

private:
    juce::MidiKeyboardState keyboardState;
    juce::MidiKeyboardComponent keyboard { keyboardState,
                                           juce::MidiKeyboardComponent::horizontalKeyboard };

    bool editingUpper { true };
    // The keyboard mode, part and split point the panel last drew, so the
    // frame timer only repaints when one of them has actually moved.
    juce::String lastKeyboardState;
    // And the octave shift the keys were last named for. JUCE's
    // setOctaveForMiddleC repaints unconditionally, so calling it every frame
    // invalidated the whole 1204x73 keyboard 24 times a second on an idle
    // panel — and through the scaled canvas that re-ran the panel paint over
    // that strip as well.
    int lastKeyboardOctave { std::numeric_limits<int>::min() };
    juce::StringArray unresolvedParameterIds;
    juce::StringArray mixedScopeSections;
    float meterLevel[2] { 0.0f, 0.0f };

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (SeptumAudioProcessorEditor)
};

#include "PluginEditor.h"

#include <array>

namespace
{
namespace colours
{
    const juce::Colour body { 0xff192327 };        // painted metal chassis
    const juce::Colour surround { 0xff101719 };
    const juce::Colour recess { 0xff253135 };
    const juce::Colour frame { 0xffe1e7e0 };       // light silkscreen on dark panels
    const juce::Colour silver { 0xffc5cec8 };
    const juce::Colour silverShade { 0xffa6b3ae };
    const juce::Colour ink { 0xff1c2a2d };         // silkscreen on silver panels
    const juce::Colour accent { 0xffed593d };
    const juce::Colour knobFace { 0xffbbc9c1 };
    const juce::Colour knobPointer { 0xff233b39 };
    const juce::Colour sliderTrack { 0xff10191c };
    const juce::Colour ledOn { 0xffff8050 };
    const juce::Colour shadow { 0x70000000 };
    // Stable part identities; selection, enable and signal activity have
    // separate indicators. Shared sections never wear either part's chip.
    const juce::Colour toneUpper { 0xfff17a5c };
    const juce::Colour toneLower { 0xff64c5dc };
}

// Fixed control geometry. Sections are sized to fit their contents; the
// contents are never scaled to fit a section, which is what keeps a knob the
// same size wherever it appears.
constexpr int knobCell = 63;
constexpr int comboCell = 108;
// One selector on the panel has entries as long as FILTER-CUTOFF-KEYFOLLOW,
// and a 104-point cell clips them.
constexpr int wideComboCell = 176;
constexpr int toggleCell = 66;
constexpr int actionCell = 60;
constexpr int sliderCell = 34;

constexpr int labelHeight = 17;
constexpr int valueHeight = 17;
constexpr int knobDiameter = 34;
constexpr int comboHeight = 26;
constexpr int toggleHeight = 26;

constexpr int sectionTitleHeight = 20;
// The chip a per-tone section wears on its title row, naming the tone it is
// editing.
constexpr int toneChipWidth = 52;
constexpr int sectionPadding = 7;
constexpr int gridRowHeight = 68;      // label + control + value
constexpr int sectionGap = 6;

constexpr int headerHeight = 170;
constexpr int clusterWidth = 128;
// Tall enough for a full-size control cell under the strip's own title,
// so the patch strip's knobs are the same knobs as everywhere else.
constexpr int stripHeight = sectionTitleHeight + gridRowHeight
                            + 2 * sectionPadding + 6;
// The bottom row is the instrument's performance surface: the per-tone play
// controls, the lever, and the keys under the band that says which tone each
// of them reaches.
constexpr int keyZoneHeight = 28;
constexpr int keyboardHeight = sectionTitleHeight + gridRowHeight
                               + 2 * sectionPadding;
// The meter reads in decibels down to here, which is the range a player
// actually mixes in.
constexpr float meterFloorDb = -48.0f;
constexpr int bandRows = 3;
constexpr int bandHeight = sectionTitleHeight + 2 * gridRowHeight + 2 * sectionPadding;
// A host window carries a frame and a title bar the panel does not get to
// use; these are enough of both that the fit rule does not put the panel
// under one.
constexpr int windowChromeWidth = 32;
constexpr int windowChromeHeight = 64;
// Wide enough for the REVERB section's whole documented parameter set: the
// effects band's four sections need 1474 points of content between them, and
// the panel scales to the window anyway.
constexpr int editorWidth = 1660;
constexpr int editorHeight = headerHeight + bandRows * bandHeight
                             + (bandRows - 1) * sectionGap + stripHeight
                             + keyboardHeight + 18;
// Bound host resizing while still fitting the complete panel on small displays.
constexpr int minimumWidth = editorWidth * 3 / 5;
constexpr int minimumHeight = editorHeight * 3 / 5;
} // namespace

// ---------------------------------------------------------------------------
// Look and feel
// ---------------------------------------------------------------------------

SeptumLookAndFeel::SeptumLookAndFeel()
{
    setColour (juce::Label::textColourId, colours::frame);
    setColour (juce::Slider::textBoxTextColourId, colours::frame);
    setColour (juce::Slider::textBoxOutlineColourId,
               juce::Colours::transparentBlack);
    setColour (juce::ComboBox::backgroundColourId, colours::body);
    setColour (juce::ComboBox::textColourId, colours::frame);
    setColour (juce::ComboBox::outlineColourId, colours::frame);
    setColour (juce::ComboBox::arrowColourId, colours::frame);
    setColour (juce::PopupMenu::backgroundColourId, colours::body);
    setColour (juce::PopupMenu::textColourId, colours::frame);
    setColour (juce::PopupMenu::highlightedBackgroundColourId, colours::accent);
    setColour (juce::PopupMenu::highlightedTextColourId, juce::Colours::white);
    setColour (juce::TextButton::buttonColourId, colours::body);
    setColour (juce::TextButton::textColourOffId, colours::frame);
    setColour (juce::TextButton::textColourOnId, juce::Colours::white);
    setColour (juce::TextButton::buttonOnColourId, colours::accent);
    setColour (juce::MidiKeyboardComponent::whiteNoteColourId,
               juce::Colour (0xfffaf8f4));
    setColour (juce::MidiKeyboardComponent::blackNoteColourId,
               juce::Colour (0xff26262a));
    setColour (juce::MidiKeyboardComponent::textLabelColourId, colours::ink);
    setColour (juce::MidiKeyboardComponent::keyDownOverlayColourId,
               colours::accent.withAlpha (0.6f));
    setColour (juce::MidiKeyboardComponent::mouseOverKeyOverlayColourId,
               colours::accent.withAlpha (0.25f));
}

void SeptumLookAndFeel::drawRotarySlider (juce::Graphics& g, int x, int y,
                                              int width, int height,
                                              float sliderPos,
                                              float rotaryStartAngle,
                                              float rotaryEndAngle,
                                              juce::Slider& slider)
{
    const bool bipolar = static_cast<bool> (slider.getProperties()["bipolar"]);
    const auto bounds =
        juce::Rectangle<int> (x, y, width, height).toFloat().reduced (3.0f);
    const auto radius = juce::jmin (bounds.getWidth(), bounds.getHeight()) * 0.5f;
    const auto centre = bounds.getCentre();
    const auto angle =
        rotaryStartAngle + sliderPos * (rotaryEndAngle - rotaryStartAngle);

    const auto ink = static_cast<bool> (slider.getProperties()["lightPanel"])
                         ? colours::ink : colours::frame;
    // Printed radial graduations surround a fluted, silver hardware cap.
    for (int tick = 0; tick <= 4; ++tick)
    {
        const float theta = rotaryStartAngle
                            + (rotaryEndAngle - rotaryStartAngle) * tick / 4.0f;
        const float inner = radius - (tick % 2 == 0 ? 3.0f : 2.0f);
        g.setColour (ink.withAlpha (tick % 2 == 0 ? 0.7f : 0.35f));
        g.drawLine (centre.x + std::sin (theta) * inner,
                    centre.y - std::cos (theta) * inner,
                    centre.x + std::sin (theta) * radius,
                    centre.y - std::cos (theta) * radius, 0.75f);
    }
    const float origin = bipolar ? (rotaryStartAngle + rotaryEndAngle) * 0.5f
                                 : rotaryStartAngle;
    if (std::abs (angle - origin) > 1.0e-3f)
    {
        juce::Path filled;
        filled.addCentredArc (centre.x, centre.y, radius - 4.7f, radius - 4.7f,
                              0.0f, juce::jmin (origin, angle),
                              juce::jmax (origin, angle), true);
        g.setColour (colours::accent.withAlpha (0.85f));
        g.strokePath (filled, juce::PathStrokeType (1.5f));
    }
    const float capRadius = radius * 0.69f;
    auto cap = juce::Rectangle<float> (centre.x - capRadius, centre.y - capRadius,
                                      capRadius * 2.0f, capRadius * 2.0f);
    g.setColour (colours::shadow);
    g.fillEllipse (cap.expanded (1.0f).translated (0.7f, 1.8f));
    g.setGradientFill (juce::ColourGradient (
        juce::Colour (0xffeef2e9), cap.getTopLeft(),
        juce::Colour (0xff708c87), cap.getBottomRight(), false));
    g.fillEllipse (cap);
    auto face = cap.reduced (capRadius * 0.24f);
    g.setGradientFill (juce::ColourGradient (
        juce::Colour (0xffcfded4), face.getTopLeft(),
        juce::Colour (0xff8fa8a0), face.getBottomRight(), false));
    g.fillEllipse (face);
    g.setColour (juce::Colours::white.withAlpha (0.45f));
    g.drawEllipse (face, 0.6f);
    juce::Path pointer;
    pointer.addRoundedRectangle (-1.2f, -capRadius + 1.0f, 2.4f,
                                 capRadius * 0.7f, 0.7f);
    g.setColour (colours::knobPointer);
    g.fillPath (pointer, juce::AffineTransform::rotation (angle)
                             .translated (centre.x, centre.y));
}

void SeptumLookAndFeel::drawLinearSlider (juce::Graphics& g, int x, int y,
                                              int width, int height,
                                              float sliderPos, float, float,
                                              juce::Slider::SliderStyle style,
                                              juce::Slider& slider)
{
    if (style != juce::Slider::LinearVertical)
    {
        LookAndFeel_V4::drawLinearSlider (g, x, y, width, height, sliderPos,
                                          0.0f, 0.0f, style, slider);
        return;
    }

    auto well = juce::Rectangle<float> ((float) x + 2.0f, (float) y,
                                        (float) width - 4.0f, (float) height);
    g.setColour (juce::Colour (0xff10181b));
    g.fillRoundedRectangle (well, 2.0f);
    g.setColour (juce::Colours::black.withAlpha (0.7f));
    g.drawRoundedRectangle (well, 2.0f, 1.0f);
    for (int step = 0; step <= 4; ++step)
    {
        const float lineY = (float) y + (float) height * step / 4.0f;
        g.setColour (colours::frame.withAlpha (step % 2 == 0 ? 0.4f : 0.2f));
        g.drawHorizontalLine ((int) lineY, well.getX() + 2.0f, well.getRight() - 2.0f);
    }
    g.setColour (juce::Colours::black);
    g.fillRect (well.getCentreX() - 1.5f, well.getY(), 3.0f, well.getHeight());
    juce::Rectangle<float> cap ((float) x + 4.0f, sliderPos - 7.0f,
                                (float) width - 8.0f, 14.0f);
    g.setColour (colours::shadow);
    g.fillRoundedRectangle (cap.translated (0.5f, 2.0f), 1.5f);
    g.setGradientFill (juce::ColourGradient (
        juce::Colour (0xff556367), cap.getTopLeft(),
        juce::Colour (0xff111a1d), cap.getBottomLeft(), false));
    g.fillRoundedRectangle (cap, 1.5f);
    g.setColour (juce::Colour (0xffdbe6dc));
    g.fillRect (cap.reduced (2.5f, 5.3f));
}

void SeptumLookAndFeel::drawButtonBackground (juce::Graphics& g,
                                                  juce::Button& button,
                                                  const juce::Colour&,
                                                  bool isHighlighted, bool isDown)
{
    auto bounds = button.getLocalBounds().toFloat().reduced (1.0f);
    const bool on = button.getToggleState();
    const auto tone = button.getProperties()["tone"].toString() == "lower"
                          ? colours::toneLower : colours::toneUpper;
    if (static_cast<bool> (button.getProperties()["tab"]))
    {
        // The large card behind this button carries selection. Its clickable
        // title remains separate from the independently focusable power button.
        if (isHighlighted || isDown || button.hasKeyboardFocus (true))
        {
            g.setColour (tone.withAlpha (0.10f));
            g.fillRoundedRectangle (bounds, 3.0f);
            g.setColour (tone);
            g.drawRoundedRectangle (bounds, 3.0f, 1.0f);
        }
        return;
    }
    g.setColour (juce::Colours::black.withAlpha (0.8f));
    g.fillRoundedRectangle (bounds.translated (0.0f, 1.0f), 2.5f);
    g.setGradientFill (juce::ColourGradient (
        isHighlighted ? juce::Colour (0xff4a5b60) : juce::Colour (0xff35464b),
        bounds.getTopLeft(), juce::Colour (0xff172327), bounds.getBottomLeft(), false));
    g.fillRoundedRectangle (bounds, 2.5f);
    g.setColour (button.hasKeyboardFocus (true) ? colours::frame
                                              : juce::Colour (0xff5b6b6e));
    g.drawRoundedRectangle (bounds, 2.5f, 0.8f);
    if (button.getWidth() < 48)
        return; // Compact octave actions need their full face for the label.
    const auto led = bounds.withSizeKeepingCentre (8.0f, 3.0f)
                        .withX (bounds.getX() + 5.0f);
    const auto ledColour = static_cast<bool> (button.getProperties()["power"])
                               ? tone : colours::ledOn;
    if (on)
    {
        g.setColour (ledColour.withAlpha (0.15f));
        g.fillRoundedRectangle (led.expanded (2.0f), 2.0f);
    }
    g.setColour (on ? ledColour : juce::Colour (0xff0b1315));
    g.fillRoundedRectangle (led, 1.0f);
}

void SeptumLookAndFeel::drawComboBox (juce::Graphics& g, int width,
                                          int height, bool, int, int, int, int,
                                          juce::ComboBox& box)
{
    auto bounds =
        juce::Rectangle<int> (0, 0, width, height).toFloat().reduced (0.5f);
    g.setColour (colours::body);
    g.fillRoundedRectangle (bounds, 3.0f);
    g.setColour (box.hasKeyboardFocus (true) ? colours::accent : colours::frame);
    g.drawRoundedRectangle (bounds, 3.0f, 1.0f);

    juce::Path arrow;
    const auto arrowZone = bounds.removeFromRight (16.0f).reduced (4.0f, 6.0f);
    arrow.addTriangle (arrowZone.getX(), arrowZone.getY(),
                       arrowZone.getRight(), arrowZone.getY(),
                       arrowZone.getCentreX(), arrowZone.getBottom());
    g.setColour (colours::frame);
    g.fillPath (arrow);
}

juce::Font SeptumLookAndFeel::getComboBoxFont (juce::ComboBox&)
{
    return juce::Font (juce::FontOptions (14.0f));
}

juce::Font SeptumLookAndFeel::getLabelFont (juce::Label& label)
{
    return label.getFont();
}

juce::Font SeptumLookAndFeel::getTextButtonFont (juce::TextButton&, int)
{
    return juce::Font (juce::FontOptions (14.0f, juce::Font::bold));
}

void SeptumLookAndFeel::positionComboBoxText (juce::ComboBox& box,
                                                  juce::Label& label)
{
    label.setBounds (6, 1, box.getWidth() - 27, box.getHeight() - 2);
    label.setBorderSize (juce::BorderSize<int> (0));
    label.setFont (juce::Font (juce::FontOptions (14.0f)));
}

void SeptumLookAndFeel::drawButtonText (juce::Graphics& g,
                                            juce::TextButton& button, bool, bool)
{
    const bool tab = static_cast<bool> (button.getProperties()["tab"]);
    const bool on = button.getToggleState();
    auto bounds = button.getLocalBounds();
    if (tab)
    {
        const auto tone = button.getProperties()["tone"].toString() == "lower"
                              ? colours::toneLower : colours::toneUpper;
        g.setFont (juce::Font (juce::FontOptions (19.0f, juce::Font::bold)));
        g.setColour (tone);
        g.drawText (button.getButtonText(), bounds.removeFromLeft (90),
                    juce::Justification::centredLeft);
        g.setFont (juce::Font (juce::FontOptions (13.0f, juce::Font::bold)));
        g.setColour (on ? colours::frame : colours::frame.withAlpha (0.62f));
        g.drawText (on ? "EDITING" : "EDIT", bounds,
                    juce::Justification::centredLeft);
        return;
    }
    g.setFont (juce::Font (juce::FontOptions (
        button.getWidth() < 48 ? 11.0f : 13.0f, juce::Font::bold)));
    g.setColour (on ? colours::frame : colours::frame.withAlpha (0.78f));
    g.drawText (button.getButtonText(),
                bounds.withTrimmedLeft (button.getWidth() < 48 ? 0 : 13).reduced (1),
                juce::Justification::centred);
}

// ---------------------------------------------------------------------------
// Bend/modulation lever
// ---------------------------------------------------------------------------

SeptumLever::SeptumLever (SeptumAudioProcessor& owner)
    : processor (owner)
{
    setMouseCursor (juce::MouseCursor::UpDownLeftRightResizeCursor);
}

void SeptumLever::push() noexcept
{
    processor.setLeverFromUi (bend, mod);
}

void SeptumLever::applyFromEvent (const juce::MouseEvent& event)
{
    const auto bounds = leverBounds();
    // Bend is absolute and spring-loaded, as the lever's horizontal axis is:
    // where you take it is where it is, and it comes back when you let go.
    bend = juce::jlimit (-1.0f, 1.0f,
                         (event.position.x - bounds.getCentreX())
                             / (bounds.getWidth() * 0.5f));
    // Modulation holds its position, so it moves by the drag rather than
    // jumping to the click: the hardware lever cannot be *put* at full
    // modulation by tapping the top of its travel, and a tap that latched
    // full vibrato is not something a player can see or easily undo.
    const float travel = (grabY - event.position.y) / bounds.getHeight();
    mod = juce::jlimit (0.0f, 1.0f, grabMod + travel);
    push();
    repaint();
}

juce::Rectangle<float> SeptumLever::leverBounds() const
{
    // The caption gets its own band at the foot; the frame and the stick are
    // drawn in what is left, so no text sits on top of a border.
    return getLocalBounds()
        .withTrimmedBottom (captionHeight)
        .toFloat()
        .reduced (2.0f);
}

void SeptumLever::mouseDown (const juce::MouseEvent& event)
{
    grabY = event.position.y;
    grabMod = mod;
    applyFromEvent (event);
}

void SeptumLever::mouseDrag (const juce::MouseEvent& event)
{
    applyFromEvent (event);
}

void SeptumLever::mouseUp (const juce::MouseEvent&)
{
    bend = 0.0f;  // the lever's bend axis is spring-loaded
    push();
    repaint();
}

void SeptumLever::mouseDoubleClick (const juce::MouseEvent&)
{
    // Somewhere to put the modulation back, since it holds.
    mod = 0.0f;
    bend = 0.0f;
    push();
    repaint();
}

void SeptumLever::paint (juce::Graphics& g)
{
    const auto bounds = leverBounds();
    g.setColour (colours::sliderTrack);
    g.fillRoundedRectangle (bounds, 5.0f);
    g.setColour (colours::frame);
    g.drawRoundedRectangle (bounds, 5.0f, 1.0f);

    // Modulation depth fills from the bottom.
    auto modZone = bounds.reduced (5.0f);
    g.setColour (colours::accent.withAlpha (0.25f));
    g.fillRoundedRectangle (modZone.removeFromBottom (modZone.getHeight() * mod),
                            3.0f);

    // The lever itself, offset by the bend.
    const float centreX = bounds.getCentreX()
                          + bend * (bounds.getWidth() * 0.5f - 8.0f);
    juce::Rectangle<float> stick (centreX - 5.0f, bounds.getY() + 8.0f, 10.0f,
                                  bounds.getHeight() - 16.0f);
    g.setColour (colours::shadow);
    g.fillRoundedRectangle (stick.translated (1.0f, 1.5f), 4.0f);
    g.setColour (colours::knobFace);
    g.fillRoundedRectangle (stick, 4.0f);
    g.setColour (colours::frame);
    g.fillRoundedRectangle (stick.reduced (3.0f, 14.0f), 2.0f);

    g.setColour (colours::frame.withAlpha (0.88f));
    g.setFont (juce::Font (juce::FontOptions (12.0f, juce::Font::bold)));
    g.drawText ("Bend/mod", getLocalBounds().removeFromBottom (captionHeight),
                juce::Justification::centred);
}

// ---------------------------------------------------------------------------
// Editor
// ---------------------------------------------------------------------------

SeptumAudioProcessorEditor::SeptumAudioProcessorEditor (
    SeptumAudioProcessor& owner)
    : AudioProcessorEditor (owner), processor (owner), lever (owner)
{
    setLookAndFeel (&lookAndFeel);
    // Everything the panel draws lives on the canvas; the editor holds only
    // the canvas and the transform that maps it onto the window.
    addAndMakeVisible (canvas);

    titleLabel.setText ("SEPTUM", juce::dontSendNotification);
    titleLabel.setFont (juce::Font (juce::FontOptions (34.0f, juce::Font::bold)));
    titleLabel.setColour (juce::Label::textColourId, colours::frame);
    canvas.addAndMakeVisible (titleLabel);

    subtitleLabel.setText (
        juce::String::fromUTF8 ("VIRTUAL ANALOG SYNTHESIZER"),
        juce::dontSendNotification);
    subtitleLabel.setFont (juce::Font (juce::FontOptions (14.0f)));
    subtitleLabel.setColour (juce::Label::textColourId,
                             colours::frame.withAlpha (0.7f));
    canvas.addAndMakeVisible (subtitleLabel);

    voiceLabel.setFont (juce::Font (juce::FontOptions (14.0f)));
    voiceLabel.setJustificationType (juce::Justification::centred);
    voiceLabel.setColour (juce::Label::textColourId,
                          colours::frame.withAlpha (0.88f));
    voiceLabel.setText ("0 / 10 VOICES", juce::dontSendNotification);
    canvas.addAndMakeVisible (voiceLabel);

    const auto section = [this] (const juce::String& title, Band band)
    {
        sections.push_back (std::make_unique<Section>());
        sections.back()->title = title;
        sections.back()->band = band;
        return sections.back().get();
    };

    // ---- left performance cluster (hardware's left panel block) ---------
    performSection = section ("PERFORM", Band::Perform);
    performSection->manualLayout = true;

    masterSlider.setSliderStyle (juce::Slider::RotaryHorizontalVerticalDrag);
    masterSlider.setTextBoxStyle (juce::Slider::NoTextBox, false, 0, 0);
    canvas.addAndMakeVisible (masterSlider);
    masterAttachment = std::make_unique<
        juce::AudioProcessorValueTreeState::SliderAttachment> (
        processor.parameters, "master_level", masterSlider);
    masterLabel.setText ("Master volume", juce::dontSendNotification);
    masterLabel.setFont (juce::Font (juce::FontOptions (14.0f)));
    masterLabel.setJustificationType (juce::Justification::centred);
    masterLabel.setColour (juce::Label::textColourId,
                           colours::frame.withAlpha (0.88f));
    canvas.addAndMakeVisible (masterLabel);
    masterValueLabel.setFont (
        juce::Font (juce::FontOptions (14.0f, juce::Font::bold)));
    masterValueLabel.setJustificationType (juce::Justification::centred);
    canvas.addAndMakeVisible (masterValueLabel);

    octLabel.setText ("Key octave", juce::dontSendNotification);
    octLabel.setFont (juce::Font (juce::FontOptions (14.0f)));
    octLabel.setColour (juce::Label::textColourId,
                        colours::frame.withAlpha (0.88f));
    octLabel.setJustificationType (juce::Justification::centred);
    canvas.addAndMakeVisible (octLabel);
    octValueLabel.setFont (juce::Font (juce::FontOptions (14.0f, juce::Font::bold)));
    octValueLabel.setJustificationType (juce::Justification::centred);
    canvas.addAndMakeVisible (octValueLabel);
    // Settled: SYSTEM COMMON Octave Shift is -3..+3 (address map 00 17), and
    // the OCT UP/DOWN buttons are what set it on the instrument. They write
    // the parameter, so a host can automate the same thing the buttons do.
    octDownButton.onClick = [this] { stepKeyboardOctave (-1); };
    octUpButton.onClick = [this] { stepKeyboardOctave (1); };
    canvas.addAndMakeVisible (octDownButton);
    canvas.addAndMakeVisible (octUpButton);

    // PORTAMENTO, GLIDE TIME and POLY/SOLO used to sit here, among controls
    // that belong to the whole instrument, while being Patch Tone bytes that
    // edit one tone. They moved to TONE PLAY on the keyboard row; what is
    // left in this cluster is global or patch-wide without exception.
    tempoControl = addControl (*performSection, "patch_tempo", "TEMPO",
                               Style::Knob, false, " BPM");

    // ---- band 1: the voice chain -----------------------------------------
    auto* osc1 = section ("OSC 1", Band::Voice);
    osc1->rowCounts = { 4, 2 };
    addControl (*osc1, "osc1_wave", "WAVE", Style::Combo);
    addControl (*osc1, "osc1_pitch", "PITCH", Style::Knob, true, " st");
    addControl (*osc1, "osc1_detune", "DETUNE", Style::Knob, true, " c");
    addControl (*osc1, "osc1_pw", "PW/FB", Style::Knob);
    addControl (*osc1, "osc1_wide", "WIDE", Style::Toggle);
    addControl (*osc1, "osc1_penv_depth", "P.ENV", Style::Knob);

    auto* osc2 = section ("OSC 2", Band::Voice);
    osc2->rowCounts = { 4, 4 };
    addControl (*osc2, "osc2_wave", "WAVE", Style::Combo);
    addControl (*osc2, "osc2_pitch", "PITCH", Style::Knob, true, " st");
    addControl (*osc2, "osc2_detune", "DETUNE", Style::Knob, true, " c");
    addControl (*osc2, "osc2_pw", "PW/FB", Style::Knob);
    intervalOctControl = addControl (*osc2, "", "INTERVAL", Style::Action);
    intervalFifthControl = addControl (*osc2, "", "", Style::Action);
    addControl (*osc2, "osc2_wide", "WIDE", Style::Toggle);
    addControl (*osc2, "osc2_penv_depth", "P.ENV", Style::Knob);

    // Settled (OM p. 30), and settled as *intervals*: "-OCT ... lowers the
    // OSC 2 pitch one octave below that of OSC 1", "the OSC 2 pitch will be
    // seven semitones (a perfect fifth) higher than OSC 1", and "if you press
    // the -OCT button and the 5th button simultaneously, the OSC 2 pitch will
    // be the same as the OSC 1 pitch". Both are measured against OSC 1, so a
    // patch whose OSC 1 is transposed used to get the wrong interval; and the
    // second press stands in for the hardware's simultaneous press, which is
    // why it lands on OSC 1's pitch rather than on zero.
    const auto interval = [this] (Control* control, const char* text,
                                  int semitones)
    {
        auto* button =
            dynamic_cast<juce::TextButton*> (control->component.get());
        if (button == nullptr)
            return;
        button->setButtonText (text);
        button->setClickingTogglesState (false);
        button->onClick = [this, semitones]
        {
            const float root = getToneParameter ("osc1_pitch");
            // Snapped, because the write below snaps: with OSC 1 at +30 the
            // fifth wants +37, lands on +36, and an unsnapped comparison then
            // read "not there yet" forever — the second press, documented as
            // the way back to unison, did nothing and the lamp stayed dark.
            const float wanted =
                snapToneParameter ("osc2_pitch", root + (float) semitones);
            setToneParameter ("osc2_pitch",
                              getToneParameter ("osc2_pitch") == wanted ? root
                                                                        : wanted);
        };
    };
    interval (intervalOctControl, "-OCT", -12);
    interval (intervalFifthControl, "5TH", 7);

    auto* mixMod = section ("MIX/MOD", Band::Voice);
    mixMod->rowCounts = { 2, 1 };
    addControl (*mixMod, "mix_type", "TYPE", Style::Combo);
    nameEnds (addControl (*mixMod, "balance", "BALANCE", Style::Knob),
              "OSC1", "OSC2");
    addControl (*mixMod, "low_freq", "LOW FREQ", Style::Combo);

    auto* filter = section ("FILTER", Band::Voice);
    filter->rowCounts = { 2, 4 };  // TYPE and SLOPE up top, the knobs below
    addControl (*filter, "filter_type", "TYPE", Style::Combo);
    addControl (*filter, "filter_slope", "SLOPE", Style::Combo);
    addControl (*filter, "cutoff", "CUTOFF", Style::Knob);
    addControl (*filter, "resonance", "RESO", Style::Knob);
    addControl (*filter, "key_follow", "KEY FOLLOW", Style::Knob);
    addControl (*filter, "cutoff_vel", "VELOCITY", Style::Knob);

    auto* amp = section ("AMP", Band::Voice);
    amp->rowCounts = { 3, 4 };
    addControl (*amp, "level", "LEVEL", Style::Knob);
    addControl (*amp, "level_vel", "VELOCITY", Style::Knob);
    nameEnds (addControl (*amp, "pan", "PAN", Style::Knob), "L", "R");
    addControl (*amp, "overdrive", "OVERDRIVE", Style::Toggle);
    addControl (*amp, "drive", "DRIVE", Style::Knob);
    // The two effect send depths are Patch *Tone* bytes — one per tone — so
    // they belong to the tone's amp stage, not to the shared effect that
    // receives them. Sitting in DELAY and REVERB they were the only per-tone
    // controls in two otherwise shared sections, and nothing said so.
    addControl (*amp, "delay_depth", "DLY SEND", Style::Knob);
    addControl (*amp, "reverb_depth", "REV SEND", Style::Knob);

    // ---- band 2: what modulates the chain --------------------------------
    auto* pitchEnv = section ("PITCH ENV", Band::Modulation);
    addControl (*pitchEnv, "penv_attack", "A", Style::VSlider);
    addControl (*pitchEnv, "penv_decay", "D", Style::VSlider);

    auto* filterEnv = section ("FILTER ENV", Band::Modulation);
    filterEnv->rowCounts = { 1 };
    addControl (*filterEnv, "fenv_attack", "A", Style::VSlider);
    addControl (*filterEnv, "fenv_decay", "D", Style::VSlider);
    addControl (*filterEnv, "fenv_sustain", "S", Style::VSlider);
    addControl (*filterEnv, "fenv_release", "R", Style::VSlider);
    addControl (*filterEnv, "fenv_depth", "DEPTH", Style::Knob);

    auto* ampEnv = section ("AMP ENV", Band::Modulation);
    addControl (*ampEnv, "aenv_attack", "A", Style::VSlider);
    addControl (*ampEnv, "aenv_decay", "D", Style::VSlider);
    addControl (*ampEnv, "aenv_sustain", "S", Style::VSlider);
    addControl (*ampEnv, "aenv_release", "R", Style::VSlider);

    for (int lfo = 1; lfo <= 2; ++lfo)
    {
        const juce::String prefix = "lfo" + juce::String (lfo) + "_";
        auto* lfoSection = section ("LFO " + juce::String (lfo), Band::Modulation);
        lfoSection->rowCounts = { 5, 5 };
        addControl (*lfoSection, prefix + "shape", "SHAPE", Style::Combo);
        addControl (*lfoSection, prefix + "rate", "RATE", Style::Knob);
        addControl (*lfoSection, prefix + "sync", "SYNC", Style::Toggle);
        addControl (*lfoSection, prefix + "sync_note", "NOTE", Style::Combo);
        addControl (*lfoSection, prefix + "fade", "FADE", Style::Knob);
        addControl (*lfoSection, prefix + "key_trig", "TRIG", Style::Toggle);
        addControl (*lfoSection, prefix + "dest1", "DEST 1", Style::Combo);
        addControl (*lfoSection, prefix + "depth1", "DEPTH 1", Style::Knob);
        addControl (*lfoSection, prefix + "dest2", "DEST 2", Style::Combo);
        addControl (*lfoSection, prefix + "depth2", "DEPTH 2", Style::Knob);
    }

    // ---- band 3: the two ends of the instrument --------------------------
    auto* arpSection = section ("ARPEGGIO", Band::InputEffects);
    // Row one is what the arpeggiator is and where it plays; row two is how
    // it reads the keys. The counts have to cover every control the section
    // holds — a row short and the last one is never given bounds.
    arpSection->rowCounts = { 5, 6 };
    addControl (*arpSection, "arp_on", "SWITCH", Style::Toggle, false);
    addControl (*arpSection, "arp_hold", "HOLD", Style::Toggle, false);
    addControl (*arpSection, "arp_style", "STYLE", Style::Combo, false);
    addControl (*arpSection, "arp_grid", "GRID", Style::Combo, false);
    splitArpControl =
        addControl (*arpSection, "arp_split", "SPLIT ARP", Style::Combo, false);
    addControl (*arpSection, "arp_motif", "MOTIF", Style::Combo, false);
    addControl (*arpSection, "arp_duration", "DURATION", Style::Combo, false);
    addControl (*arpSection, "arp_end_step", "END STEP", Style::Knob, false);
    addControl (*arpSection, "arp_octave", "OCT RANGE", Style::Knob, false);
    addControl (*arpSection, "arp_accent", "ACCENT", Style::Knob, false, " %");
    addControl (*arpSection, "arp_velocity", "VELOCITY", Style::Knob, false);

    auto* externalSection = section ("EXT IN", Band::InputEffects);
    externalSection->rowCounts = { 4, 3 };
    addControl (*externalSection, "ext_input_vol", "INPUT VOL", Style::Knob, false);
    addControl (*externalSection, "ext_center_cancel", "CENTER", Style::Toggle,
                false);
    addControl (*externalSection, "audio_filter_on", "FILTER", Style::Toggle,
                false);
    addControl (*externalSection, "audio_filter_type", "TYPE", Style::Combo, false);
    addControl (*externalSection, "audio_filter_slope", "SLOPE", Style::Combo,
                false);
    addControl (*externalSection, "audio_filter_cutoff", "CUTOFF", Style::Knob,
                false);
    addControl (*externalSection, "audio_filter_reso", "RESO", Style::Knob, false);

    auto* delay = section ("DELAY", Band::InputEffects);
    delay->rowCounts = { 3, 3 };
    addControl (*delay, "delay_on", "SWITCH", Style::Toggle, false);
    addControl (*delay, "delay_time", "TIME", Style::Knob, false);
    addControl (*delay, "delay_feedback", "FEEDBACK", Style::Knob, false, " %");
    addControl (*delay, "delay_hf_damp", "HF DAMP", Style::Combo, false);
    addControl (*delay, "delay_mod_rate", "MOD RATE", Style::Knob, false);
    addControl (*delay, "delay_mod_depth", "MOD DEPTH", Style::Knob, false);

    auto* reverb = section ("REVERB", Band::InputEffects);
    reverb->rowCounts = { 6, 5 };
    addControl (*reverb, "reverb_on", "SWITCH", Style::Toggle, false);
    addControl (*reverb, "reverb_time", "TIME", Style::Knob, false);
    addControl (*reverb, "reverb_size", "SIZE", Style::Knob, false);
    addControl (*reverb, "reverb_pre_delay", "PRE DELAY", Style::Knob, false,
                " ms");
    addControl (*reverb, "reverb_high_cut", "HIGH CUT", Style::Combo, false);
    addControl (*reverb, "reverb_density", "DENSITY", Style::Knob, false);
    addControl (*reverb, "reverb_diffusion", "DIFFUSION", Style::Knob, false);
    // The four remaining settled Patch Reverb bytes. PRE DELAY, HIGH CUT,
    // DENSITY and DIFFUSION above are equally editor-only on the instrument,
    // so leaving exactly these four off was an inconsistency rather than a
    // principle.
    addControl (*reverb, "reverb_lf_damp_freq", "LF DAMP", Style::Combo, false);
    addControl (*reverb, "reverb_lf_damp_gain", "LF GAIN", Style::Knob, false,
                " dB");
    addControl (*reverb, "reverb_hf_damp_freq", "HF DAMP", Style::Combo, false);
    addControl (*reverb, "reverb_hf_damp_gain", "HF GAIN", Style::Knob, false,
                " dB");

    // ---- the patch strip above the keys (the hardware's button row) ------
    stripSection = section ("PATCH", Band::Perform);
    stripSection->manualLayout = true;

    for (int index = 0; index < processor.getNumPrograms(); ++index)
        programBox.addItem (processor.getProgramName (index), index + 1);
    programBox.setSelectedId (processor.getCurrentProgram() + 1,
                              juce::dontSendNotification);
    programBox.onChange = [this]
    {
        const int index = programBox.getSelectedId() - 1;
        if (index >= 0 && index != processor.getCurrentProgram())
            processor.setCurrentProgram (index);
    };
    canvas.addAndMakeVisible (programBox);
    programLabel.setText ("Program", juce::dontSendNotification);
    programLabel.setFont (juce::Font (juce::FontOptions (14.0f)));
    programLabel.setJustificationType (juce::Justification::centredLeft);
    programLabel.setColour (juce::Label::textColourId,
                            colours::frame.withAlpha (0.88f));
    canvas.addAndMakeVisible (programLabel);

    // Every control on this strip belongs to the patch as a whole. BEND and
    // TONE OCT used to sit here and are Patch Tone bytes; they moved to
    // TONE PLAY with the rest of the per-tone play controls.
    addControl (*stripSection, "patch_level", "PATCH LEVEL", Style::Knob, false);
    nameEnds (addControl (*stripSection, "tone_balance", "TONE BAL", Style::Knob,
                          false),
              "LOWER", "UPPER");
    addControl (*stripSection, "mod_assign", "MOD ASSIGN", Style::Combo, false);
    // CONTROLLER DESTINATION: which tone each physical controller reaches.
    // These say UPPER/LOWER for a third reason again — not which tone is
    // edited, not which tone sounds, but which tone a lever or a pedal gets
    // to move — so each one names its controller and says TO TONE, which is
    // what tells them apart from PATCH LEVEL and TONE BAL beside them. There
    // is no group heading over them: the strip is one flat row of cells and
    // this comment used to claim one the panel never painted.
    addControl (*stripSection, "mod_dest", "MOD TO TONE", Style::Combo, false);
    addControl (*stripSection, "bend_dest", "BEND TO TONE", Style::Combo, false);
    addControl (*stripSection, "expr_dest", "EXPR TO TONE", Style::Combo, false);

    // ---- TONE PLAY, on the keyboard row beside the lever and the keys.
    // Five Patch *Tone* bytes about how the selected tone is played: they
    // were scattered between the global performance cluster and the patch
    // strip, where nothing said they belonged to one tone. Built after the
    // bands so the index lists below keep the construction order they name.
    tonePlaySection = section ("TONE PLAY", Band::Perform);
    tonePlaySection->rowCounts = { 5 };
    addControl (*tonePlaySection, "portamento", "PORTAMENTO", Style::Toggle);
    addControl (*tonePlaySection, "porta_time", "GLIDE TIME", Style::Knob);
    addControl (*tonePlaySection, "mono_mode", "POLY / SOLO", Style::Combo);
    addControl (*tonePlaySection, "bend_range", "BEND", Style::Knob, true, " st");
    addControl (*tonePlaySection, "octave_shift", "TONE OCT", Style::Knob);

    // ---- EDIT TONE, in the header. The panel edits one tone at a time and
    // every per-tone control silently changes meaning with this pair, so it
    // sits above the controls it governs rather than below them, it is
    // captioned, it draws as a pair of tabs rather than as two more of the
    // panel's lit toggles, and it says in words what the current keyboard
    // mode does with the tone it selects.
    editToneSection = section ("EDIT TONE", Band::Perform);
    editToneSection->manualLayout = true;

    const auto tab = [this] (juce::TextButton& button, bool upper)
    {
        button.setClickingTogglesState (false);
        button.getProperties().set ("tab", true);
        button.setComponentID (upper ? "edit_upper" : "edit_lower");
        button.setTitle (upper ? "Edit Upper part" : "Edit Lower part");
        button.setTooltip ("Select which part the synth controls edit. "
                           "This does not change the playing part or turn it on.");
        button.onClick = [this, upper] { setEditingUpper (upper); };
        canvas.addAndMakeVisible (button);
    };
    tab (upperButton, true);
    tab (lowerButton, false);
    const auto power = [this] (juce::TextButton& button, bool upper)
    {
        button.setClickingTogglesState (true);
        button.setComponentID (upper ? "upper_part_enabled" : "lower_part_enabled");
        button.setTitle (upper ? "Upper part enabled" : "Lower part enabled");
        button.setTooltip ("Mute this part without changing its sound settings. "
                           "Existing shared effect tails continue to decay.");
        button.getProperties().set ("power", true);
        button.getProperties().set ("tone", upper ? "upper" : "lower");
        auto* raw = &button;
        button.onStateChange = [this, raw]
        {
            raw->setButtonText (raw->getToggleState() ? "ON" : "OFF");
            refreshPartActivity();
        };
        canvas.addAndMakeVisible (button);
    };
    power (upperEnableButton, true);
    power (lowerEnableButton, false);
    upperEnableAttachment = std::make_unique<
        juce::AudioProcessorValueTreeState::ButtonAttachment> (
        processor.parameters, "upper_enabled", upperEnableButton);
    lowerEnableAttachment = std::make_unique<
        juce::AudioProcessorValueTreeState::ButtonAttachment> (
        processor.parameters, "lower_enabled", lowerEnableButton);
    for (std::size_t part = 0; part < 2; ++part)
    {
        for (auto* label : { &partRouteLabels[part], &partActivityLabels[part] })
        {
            label->setFont (juce::Font (juce::FontOptions (14.0f)));
            label->setInterceptsMouseClicks (false, false);
            label->setColour (juce::Label::textColourId, colours::frame);
            canvas.addAndMakeVisible (*label);
        }
        partActivityLabels[part].setJustificationType (juce::Justification::centredRight);
        partActivityLabels[part].setComponentID (part == 0 ? "upper_part_activity"
                                                         : "lower_part_activity");
        partRouteLabels[part].setComponentID (part == 0 ? "upper_part_route"
                                                       : "lower_part_route");
    }
    toneStatusLabel.setFont (juce::Font (juce::FontOptions (13.5f)));
    toneStatusLabel.setColour (juce::Label::textColourId, colours::frame.withAlpha (0.75f));
    toneStatusLabel.setJustificationType (juce::Justification::centredLeft);
    toneStatusLabel.setInterceptsMouseClicks (false, false);
    canvas.addAndMakeVisible (toneStatusLabel);

    // ---- SYSTEM COMMON, in the header: settings that apply to the whole
    // instrument rather than to the patch, and are not saved with one. Built
    // last so the band index lists below keep the construction order they
    // name.
    systemSection = section ("SYSTEM", Band::Perform);
    systemSection->rowCounts = { 3 };
    addControl (*systemSection, "system_master_tune", "TUNE", Style::Knob,
                false);
    addControl (*systemSection, "system_key_shift", "KEY SHIFT", Style::Knob,
                false, " st");
    addControl (*systemSection, "system_transpose", "TRANSPOSE", Style::Knob,
                false, " st");

    // Routing sits alongside the part tabs, with its own shared scope.
    // Appended so the signal-chain section indices remain stable.
    routingSection = section ("KEYBOARD ROUTING", Band::Perform);
    routingSection->manualLayout = true;
    addControl (*routingSection, "keyboard_mode", "KEYBOARD MODE", Style::Combo, false);
    partControl = addControl (*routingSection, "keyboard_part", "PLAY IN SINGLE",
                              Style::Combo, false);
    splitPointControl = addControl (*routingSection, "split_point", "SPLIT POINT",
                                    Style::Knob, false);

    // A section's scope is what its controls are, not what it declares. Every
    // section on this panel is wholly one or the other, because a mixed
    // section is exactly the defect Step 28 set out to remove: it would be
    // classified by its one per-tone control and wear the tone chip and wash
    // over controls that are not per-tone. Recorded rather than asserted —
    // `jassert` is compiled out of every build this project produces, so the
    // suite reads this list and expects it empty.
    mixedScopeSections.clear();
    for (auto& entry : sections)
    {
        int perTone = 0, shared = 0;
        for (const auto* control : entry->controls)
            (control->perTone ? perTone : shared) += 1;
        entry->scope = perTone > 0 ? Scope::PerTone : Scope::Shared;
        if (perTone > 0 && shared > 0)
            mixedScopeSections.add (entry->title);
    }

    // The target the player last chose, so reopening the editor does not
    // silently put them back on UPPER.
    editingUpper = (bool) processor.parameters.state.getProperty (
        "editingUpperTone", true);

    bindControls();
    refreshToneTarget();

    keyboardState.addListener (this);
    keyboard.setOctaveForMiddleC (4);
    applyKeyboardOctave();
    canvas.addAndMakeVisible (keyboard);
    canvas.addAndMakeVisible (lever);

    refreshValues();
    setOpaque (true);
    canvas.setOpaque (true);
    canvas.setInterceptsMouseClicks (false, true);

    // Any window; the panel inside it is always the design geometry, scaled.
    setResizable (true, false);
    // setResizeLimits installs the default constrainer, so it has to come
    // before the ratio is set on it.
    setResizeLimits (minimumWidth, minimumHeight, editorWidth * 2,
                     editorHeight * 2);
    if (auto* constrainer = getConstrainer())
        constrainer->setFixedAspectRatio ((double) editorWidth
                                          / (double) editorHeight);
    juce::Rectangle<int> workArea;
    if (auto* display =
            juce::Desktop::getInstance().getDisplays().getPrimaryDisplay())
        workArea = display->userArea;
    const auto opening = panelSizeForWorkArea (workArea);
    setSize (opening.getWidth(), opening.getHeight());
    startTimerHz (24);
}

SeptumAudioProcessorEditor::~SeptumAudioProcessorEditor()
{
    keyboardState.removeListener (this);
    setLookAndFeel (nullptr);
}

void SeptumAudioProcessorEditor::stepKeyboardOctave (int delta)
{
    auto* parameter = processor.parameters.getParameter ("system_octave");
    if (parameter == nullptr)
        return;
    const auto& range = processor.parameters.getParameterRange ("system_octave");
    const float wanted = range.snapToLegalValue (
        processor.parameters.getRawParameterValue ("system_octave")->load()
        + (float) delta);
    parameter->beginChangeGesture();
    parameter->setValueNotifyingHost (range.convertTo0to1 (wanted));
    parameter->endChangeGesture();
    applyKeyboardOctave();
}

void SeptumAudioProcessorEditor::applyKeyboardOctave()
{
    const auto* value =
        processor.parameters.getRawParameterValue ("system_octave");
    const int shift = value != nullptr ? (int) std::lround (value->load()) : 0;
    // Shift the printed octave names, not the note numbers. A key the player
    // clicks is sent to the engine unchanged (handleNoteOn -> triggerFromUi),
    // and the engine applies SYSTEM COMMON Octave Shift itself, so moving the
    // drawn range as well applied it twice: one press of OCT UP transposed
    // the on-screen keys by two octaves while their printed names claimed
    // one. The keys keep their notes; what moves is what they are called,
    // which is what the shift actually does to the pitch they sound.
    keyboard.setAvailableRange (36, 96);
    // JUCE's setOctaveForMiddleC repaints unconditionally, and the frame timer
    // calls this every tick, so an idle panel invalidated the whole keyboard
    // 24 times a second — and through the scaled canvas re-ran the panel paint
    // over that strip with it. setAvailableRange above is change-guarded
    // inside JUCE; this one has to be guarded here.
    if (shift != lastKeyboardOctave)
    {
        lastKeyboardOctave = shift;
        keyboard.setOctaveForMiddleC (4 + shift);
    }
    octValueLabel.setText (shift == 0 ? juce::String ("0")
                                      : (shift > 0 ? "+" : "")
                                            + juce::String (shift),
                           juce::dontSendNotification);
    octDownButton.setToggleState (shift < 0, juce::dontSendNotification);
    octUpButton.setToggleState (shift > 0, juce::dontSendNotification);
}

// Which parts receive new keys. Existing voices may still release after a
// routing change; actual audio activity is published separately by the engine.
SeptumAudioProcessorEditor::ToneAudibility
SeptumAudioProcessorEditor::toneAudibility() const
{
    const auto raw = [this] (const char* id)
    {
        const auto* value = processor.parameters.getRawParameterValue (id);
        return value != nullptr ? (int) std::lround (value->load()) : 0;
    };
    const int mode = raw ("keyboard_mode");   // 0 SINGLE, 1 DUAL, 2 SPLIT
    const bool partUpper = raw ("keyboard_part") == 0;

    ToneAudibility state;
    if (mode == 0)
    {
        state.upperSounds = partUpper;
        state.lowerSounds = ! partUpper;
        state.summary = juce::String ("SINGLE - ")
                        + (partUpper ? "UPPER" : "LOWER")
                        + " receives keys - 10 voices";
    }
    else if (mode == 1)
    {
        state.upperSounds = state.lowerSounds = true;
        state.summary = "DUAL - both parts receive all keys - 5 voices each";
    }
    else
    {
        state.upperSounds = state.lowerSounds = true;
        // Through the same namer the caption over the keys uses. The
        // parameter's own text is fixed at middle C = C4, so at OCT +1 this
        // line said "SPLIT at C4" about the key the keyboard and the caption
        // both print as C5 — the caption's own defect, one place along.
        state.summary = "SPLIT at " + getSplitPointKeyName()
                        + " - LOWER below, UPPER at and above";
    }
    return state;
}

void SeptumAudioProcessorEditor::reconcileEditTarget()
{
    // An editor left open across a session load kept showing UPPER while the
    // restored state said LOWER, and re-saving from there wrote back what
    // somebody else had been editing rather than what the player was.
    const bool stored =
        (bool) processor.parameters.state.getProperty ("editingUpperTone",
                                                       editingUpper);
    if (stored != editingUpper)
        setEditingUpper (stored);
}

void SeptumAudioProcessorEditor::setEditingUpper (bool upper)
{
    if (editingUpper == upper)
        return;
    editingUpper = upper;
    // The target survives closing and reopening the editor. It is not a
    // parameter — it changes nothing that sounds, so a host has no business
    // automating it — but losing it on every reopen made an already invisible
    // mode silently revert.
    processor.parameters.state.setProperty ("editingUpperTone", upper, nullptr);
    bindControls (true);
    refreshToneTarget();
    repaint();
    canvas.repaint();
}

// Everything that has to change when the target moves or the keyboard mode
// does: the tabs, the status line, and the controls the mode makes inert.
void SeptumAudioProcessorEditor::refreshToneTarget()
{
    upperButton.setToggleState (editingUpper, juce::dontSendNotification);
    lowerButton.setToggleState (! editingUpper, juce::dontSendNotification);
    upperButton.getProperties().set ("tone", "upper");
    lowerButton.getProperties().set ("tone", "lower");

    const auto state = toneAudibility();
    toneStatusLabel.setText (state.summary, juce::dontSendNotification);
    const auto* split = processor.parameters.getRawParameterValue ("keyboard_mode");
    const bool isSplit = split != nullptr && (int) std::lround (split->load()) == 2;
    for (std::size_t i = 0; i < 2; ++i)
    {
        const bool receives = i == 0 ? state.upperSounds : state.lowerSounds;
        const juce::String route = isSplit
            ? (i == 0 ? getSplitPointKeyName() + " and above"
                      : "Below " + getSplitPointKeyName())
            : receives ? "All keys" : "No keys in Single";
        partRouteLabels[i].setText (route, juce::dontSendNotification);
    }
    refreshPartActivity();

    // A control the engine ignores in this mode is dimmed rather than left
    // looking live: PART decides nothing outside SINGLE, and the split point
    // and SPLIT ARPEGGIO decide nothing outside SPLIT.
    const int mode = [this]
    {
        const auto* value = processor.parameters.getRawParameterValue ("keyboard_mode");
        return value != nullptr ? (int) std::lround (value->load()) : 0;
    }();
    const auto dim = [] (Control* control, bool live)
    {
        if (control == nullptr)
            return;
        const float alpha = live ? 1.0f : 0.65f;
        control->component->setAlpha (alpha);
        control->label->setAlpha (alpha);
        if (control->value != nullptr)
            control->value->setAlpha (alpha);
    };
    dim (partControl, mode == 0);
    dim (splitPointControl, mode == 2);
    dim (splitArpControl, mode == 2);
}

void SeptumAudioProcessorEditor::refreshPartActivity()
{
    const auto routing = toneAudibility();
    for (std::size_t i = 0; i < 2; ++i)
    {
        const bool upper = i == 0;
        const auto* enabled = processor.parameters.getRawParameterValue (
            upper ? "upper_enabled" : "lower_enabled");
        const bool on = enabled == nullptr || enabled->load() >= 0.5f;
        const int voices = processor.getPartActiveVoiceCount (upper);
        const int held = processor.getPartHeldVoiceCount (upper);
        const float signal = processor.getPartOutputLevel (upper);
        const float level = juce::jmax (signal, partMeterLevels[i] * 0.78f);
        if (std::abs (level - partMeterLevels[i]) > 0.00001f)
        {
            partMeterLevels[i] = level;
            canvas.repaint (partTabBounds[i]);
        }
        const bool routed = upper ? routing.upperSounds : routing.lowerSounds;
        juce::String text;
        if (! on)
            text = "OFF";
        else if (voices > 0 && signal > 0.00001f)
            text = juce::String (held > 0 ? "PLAYING" : "RELEASING")
                   + " / " + juce::String (voices)
                   + (voices == 1 ? " VOICE" : " VOICES");
        else if (voices > 0)
            text = juce::String (voices)
                   + (voices == 1 ? " VOICE / NO LEVEL" : " VOICES / NO LEVEL");
        else
            text = routed ? "READY" : "NO NEW KEYS";
        partActivityLabels[i].setText (text, juce::dontSendNotification);
    }
}

void SeptumAudioProcessorEditor::paintPartTabs (juce::Graphics& g)
{
    for (std::size_t i = 0; i < 2; ++i)
    {
        const auto area = partTabBounds[i].toFloat();
        if (area.isEmpty())
            continue;
        const auto tone = i == 0 ? colours::toneUpper : colours::toneLower;
        const bool edited = (i == 0) == editingUpper;
        g.setGradientFill (juce::ColourGradient (
            edited ? colours::recess.interpolatedWith (tone, 0.32f)
                   : juce::Colour (0xff222f33),
            area.getTopLeft(),
            edited ? colours::body.interpolatedWith (tone, 0.18f) : colours::body,
            area.getBottomLeft(), false));
        g.fillRoundedRectangle (area, 4.0f);
        g.setColour (edited ? tone.withAlpha (0.85f) : juce::Colour (0xff46565a));
        g.drawRoundedRectangle (area.reduced (0.5f), 4.0f, edited ? 1.5f : 1.0f);
        g.setColour (tone);
        g.fillRect (area.getX() + 1.0f, area.getY() + 6.0f, 3.0f,
                    area.getHeight() - 12.0f);
        auto meter = area.withTrimmedLeft (13.0f).withTrimmedRight (13.0f)
                         .removeFromBottom (9.0f).withHeight (3.0f);
        g.setColour (colours::sliderTrack);
        g.fillRect (meter);
        const float db = juce::Decibels::gainToDecibels (partMeterLevels[i], -60.0f);
        const float position = juce::jlimit (0.0f, 1.0f, (db + 60.0f) / 60.0f);
        g.setColour (tone);
        g.fillRect (meter.withWidth (meter.getWidth() * position));
    }
}

float SeptumAudioProcessorEditor::getToneParameter (const char* suffix) const
{
    const auto id = septum::parameters::toneId (editingUpper, suffix);
    if (const auto* value = processor.parameters.getRawParameterValue (id))
        return value->load();
    return 0.0f;
}

float SeptumAudioProcessorEditor::snapToneParameter (const char* suffix,
                                                     float natural) const
{
    const auto id = septum::parameters::toneId (editingUpper, suffix);
    if (processor.parameters.getParameter (id) != nullptr)
        return processor.parameters.getParameterRange (id).snapToLegalValue (natural);
    return natural;
}

void SeptumAudioProcessorEditor::setToneParameter (const char* suffix,
                                                       float natural)
{
    const auto id = septum::parameters::toneId (editingUpper, suffix);
    if (auto* parameter = processor.parameters.getParameter (id))
    {
        const auto& range = processor.parameters.getParameterRange (id);
        parameter->beginChangeGesture();
        parameter->setValueNotifyingHost (
            range.convertTo0to1 (range.snapToLegalValue (natural)));
        parameter->endChangeGesture();
    }
}

int SeptumAudioProcessorEditor::Section::naturalWidth() const
{
    const auto cellWidth = [] (Style style)
    {
        switch (style)
        {
            case Style::Knob:    return knobCell;
            case Style::Combo:   return comboCell;
            case Style::WideCombo: return wideComboCell;
            case Style::Toggle:  return toggleCell;
            case Style::Action:  return actionCell;
            case Style::VSlider: return sliderCell;
        }
        return knobCell;
    };

    int sliders = 0, gridWidth = 0;
    std::vector<const Control*> grid;
    for (const auto* control : controls)
    {
        if (control->style == Style::VSlider)
            sliders += sliderCell;
        else
            grid.push_back (control);
    }

    std::size_t index = 0;
    for (int count : rowCounts)
    {
        int width = 0;
        for (int i = 0; i < count && index < grid.size(); ++i, ++index)
            width += cellWidth (grid[index]->style);
        gridWidth = juce::jmax (gridWidth, width);
    }
    int remainder = 0;
    for (; index < grid.size(); ++index)
        remainder += cellWidth (grid[index]->style);
    gridWidth = juce::jmax (gridWidth, remainder);

    // The title must fit too, or a section can end up narrower than its name
    // — and on a per-tone section the title row also carries the tone chip.
    const int titleWidth =
        (int) juce::GlyphArrangement::getStringWidth (
            juce::Font (juce::FontOptions (15.0f, juce::Font::bold)), title)
        + 26 + (scope == Scope::PerTone ? toneChipWidth + 6 : 0);
    return juce::jmax (titleWidth, sliders + gridWidth) + 2 * sectionPadding;
}

SeptumAudioProcessorEditor::Control* SeptumAudioProcessorEditor::addControl (
    Section& section, const juce::String& suffix, const juce::String& labelText,
    Style style, bool perTone, const juce::String& unit)
{
    controls.push_back (std::make_unique<Control>());
    auto* control = controls.back().get();
    control->suffix = suffix;
    control->perTone = perTone;
    control->style = style;
    control->unit = unit;

    switch (style)
    {
        case Style::Knob:
        {
            // No drag-time popup: the value is on the panel all the time,
            // so a bubble would only cover the neighbours.
            control->component = std::make_unique<juce::Slider> (
                juce::Slider::RotaryHorizontalVerticalDrag,
                juce::Slider::NoTextBox);
            break;
        }
        case Style::VSlider:
        {
            control->component = std::make_unique<juce::Slider> (
                juce::Slider::LinearVertical, juce::Slider::NoTextBox);
            break;
        }
        case Style::Combo:
        case Style::WideCombo:
            control->component = std::make_unique<juce::ComboBox>();
            break;
        case Style::Toggle:
        {
            auto button = std::make_unique<juce::TextButton> ("OFF");
            button->setClickingTogglesState (true);
            // A switch says which way it is thrown. A button whose face reads
            // ON while the thing is off is the commonest misreading a
            // synthesizer panel invites, and eleven controls here are
            // toggles. Driven from the button's own state rather than the
            // frame timer, so it is right the moment a patch loads.
            auto* raw = button.get();
            raw->onStateChange = [raw]
            {
                raw->setButtonText (raw->getToggleState() ? "ON" : "OFF");
            };
            control->component = std::move (button);
            break;
        }
        case Style::Action:
            control->component = std::make_unique<juce::TextButton> (labelText);
            break;
    }

    juce::String caption = labelText.toLowerCase();
    if (caption.length() == 1)
        caption = caption.toUpperCase();
    else if (caption.length() > 1)
        caption = caption.substring (0, 1).toUpperCase() + caption.substring (1);
    if (labelText == "P.ENV") caption = "Env depth";
    if (labelText == "PW/FB") caption = "PW / FB";
    if (labelText == "KEY FOLLOW") caption = "Key track";
    if (labelText == "OVERDRIVE") caption = "Overdrive";
    if (labelText == "DLY SEND") caption = "Delay";
    if (labelText == "REV SEND") caption = "Reverb";
    if (labelText == "OCT RANGE") caption = "Octaves";
    if (labelText == "PORTAMENTO") caption = "Glide";
    if (labelText == "GLIDE TIME") caption = "Time";
    if (labelText == "TONE OCT") caption = "Octave";
    if (labelText == "MOD DEPTH") caption = "Mod depth";
    if (labelText == "KEYBOARD MODE") caption = "Keyboard mode";
    if (labelText == "PLAY IN SINGLE") caption = "Single part";
    if (caption.startsWithIgnoreCase ("hf ")) caption = "HF" + caption.substring (2);
    if (caption.startsWithIgnoreCase ("lf ")) caption = "LF" + caption.substring (2);
    control->label = std::make_unique<juce::Label>();
    control->label->setText (caption, juce::dontSendNotification);
    control->label->setFont (juce::Font (juce::FontOptions (14.0f)));
    control->label->setBorderSize (juce::BorderSize<int> (0));
    control->label->setJustificationType (juce::Justification::centred);
    control->label->setInterceptsMouseClicks (false, false);
    control->label->setColour (juce::Label::textColourId,
                               colours::frame.withAlpha (0.88f));
    canvas.addAndMakeVisible (*control->label);

    // Every continuous control reads out its value, so nothing on the panel
    // has to be dragged to be understood.
    if (style == Style::Knob || style == Style::VSlider)
    {
        control->value = std::make_unique<juce::Label>();
        control->value->setFont (
            juce::Font (juce::FontOptions (14.0f, juce::Font::bold)));
        control->value->setBorderSize (juce::BorderSize<int> (0));
        control->value->setJustificationType (juce::Justification::centred);
        control->value->setInterceptsMouseClicks (false, false);
        canvas.addAndMakeVisible (*control->value);
    }

    control->component->setComponentID (perTone ? "tone_" + suffix : suffix);
    control->component->getProperties().set ("lightPanel", section.band == Band::Voice);
    if (section.band == Band::Voice)
    {
        control->label->setColour (juce::Label::textColourId, colours::ink);
        if (control->value != nullptr)
            control->value->setColour (juce::Label::textColourId, colours::ink);
    }
    canvas.addAndMakeVisible (*control->component);
    section.controls.push_back (control);
    return control;
}

// Reads each control's own parameter text, so the panel prints what the host
// prints and neither can drift from the other.
void SeptumAudioProcessorEditor::refreshValues()
{
    for (auto& control : controls)
    {
        if (control->value == nullptr || control->suffix.isEmpty())
            continue;
        const juce::String id =
            control->perTone
                ? septum::parameters::toneId (editingUpper,
                                              control->suffix.toRawUTF8())
                : control->suffix;
        auto* parameter = processor.parameters.getParameter (id);
        if (parameter == nullptr)
            continue;
        juce::String text = parameter->getCurrentValueAsText() + control->unit;
        if (control->leftEnd.isNotEmpty())
        {
            const auto* raw = processor.parameters.getRawParameterValue (id);
            const int value = raw != nullptr ? (int) std::lround (raw->load()) : 0;
            text = value == 0 ? "Center"
                             : (value < 0 ? control->leftEnd : control->rightEnd)
                                   + " " + juce::String (std::abs (value));
        }
        control->value->setText (text, juce::dontSendNotification);
    }
    if (masterValueLabel.isVisible())
        if (auto* parameter = processor.parameters.getParameter ("master_level"))
            masterValueLabel.setText (parameter->getCurrentValueAsText(),
                                      juce::dontSendNotification);

    // The INTERVAL buttons carry indicator lamps on the instrument, and they
    // are the panel's only controls that write a parameter without reflecting
    // it: a patch loaded at OSC 2 = OSC 1 - 12 used to show two dark buttons.
    const float root = getToneParameter ("osc1_pitch");
    const float second = getToneParameter ("osc2_pitch");
    const auto lamp = [] (Control* control, bool on)
    {
        if (control == nullptr)
            return;
        if (auto* button = dynamic_cast<juce::Button*> (control->component.get()))
            button->setToggleState (on, juce::dontSendNotification);
    };
    // The same snapped targets the buttons write, so the lamp says where the
    // press actually lands rather than where it aimed.
    lamp (intervalOctControl,
          second == snapToneParameter ("osc2_pitch", root - 12.0f));
    lamp (intervalFifthControl,
          second == snapToneParameter ("osc2_pitch", root + 7.0f));

}

void SeptumAudioProcessorEditor::nameEnds (Control* control, const char* left,
                                           const char* right)
{
    if (control == nullptr)
        return;
    control->leftEnd = left;
    control->rightEnd = right;
}

void SeptumAudioProcessorEditor::bindControls (bool perToneOnly)
{
    for (auto& control : controls)
    {
        if (control->style == Style::Action || control->suffix.isEmpty())
            continue;
        // Only a per-tone control can change which parameter it edits, so a
        // target switch has no reason to tear down and rebuild the shared
        // ones — including re-populating combo boxes that are already right.
        if (perToneOnly && ! control->perTone)
            continue;

        const juce::String id =
            control->perTone
                ? septum::parameters::toneId (editingUpper,
                                                  control->suffix.toRawUTF8())
                : control->suffix;

        control->sliderAttachment.reset();
        control->comboAttachment.reset();
        control->buttonAttachment.reset();

        auto* parameter = processor.parameters.getParameter (id);
        if (parameter == nullptr)
        {
            // A control naming a parameter that does not exist still draws,
            // hovers and drags — it simply edits nothing — so this cannot stay
            // a `jassert`, which no build here compiles in. The suite expects
            // this list empty.
            unresolvedParameterIds.addIfNotAlreadyThere (id);
            continue;
        }
        unresolvedParameterIds.removeString (id);
        if (auto* tooltipClient =
                dynamic_cast<juce::SettableTooltipClient*> (control->component.get()))
            tooltipClient->setTooltip (parameter->getName (64));

        if (auto* slider = dynamic_cast<juce::Slider*> (control->component.get()))
        {
            // Read straight off the parameter's own range, so a control the
            // manual prints with a sign can never disagree with the way its
            // arc is lit.
            const auto& range = processor.parameters.getParameterRange (id);
            slider->getProperties().set (
                "bipolar", range.start < 0.0f && range.end > 0.0f);
            control->sliderAttachment = std::make_unique<
                juce::AudioProcessorValueTreeState::SliderAttachment> (
                processor.parameters, id, *slider);
        }
        else if (auto* combo =
                     dynamic_cast<juce::ComboBox*> (control->component.get()))
        {
            combo->clear (juce::dontSendNotification);
            if (auto* choice = dynamic_cast<juce::AudioParameterChoice*> (parameter))
            {
                int itemId = 1;
                for (const auto& name : choice->choices)
                    combo->addItem (name, itemId++);
            }
            control->comboAttachment = std::make_unique<
                juce::AudioProcessorValueTreeState::ComboBoxAttachment> (
                processor.parameters, id, *combo);
        }
        else if (auto* button =
                     dynamic_cast<juce::Button*> (control->component.get()))
        {
            control->buttonAttachment = std::make_unique<
                juce::AudioProcessorValueTreeState::ButtonAttachment> (
                processor.parameters, id, *button);
        }
    }
    refreshValues();
}

void SeptumAudioProcessorEditor::layoutSection (Section& section,
                                               juce::Rectangle<int> bounds)
{
    section.bounds = bounds;
    if (section.manualLayout)
        return;

    auto content = bounds.reduced (sectionPadding, sectionPadding);
    content.removeFromTop (sectionTitleHeight);

    std::vector<Control*> sliders, grid;
    for (auto* control : section.controls)
        (control->style == Style::VSlider ? sliders : grid).push_back (control);

    // Vertical sliders take a left column strip at full content height: label
    // on top, travel in the middle, value underneath. A section whose width
    // was set by its title rather than by its contents — PITCH ENV is two
    // 34 px cells under a nine-character name — centres the strip in what it
    // was given instead of hugging the left edge.
    if (! sliders.empty())
    {
        const int stripWidth = (int) sliders.size() * sliderCell;
        if (grid.empty())
            content = content.withSizeKeepingCentre (stripWidth,
                                                     content.getHeight());
        auto strip = content.removeFromLeft (stripWidth);
        for (std::size_t i = 0; i < sliders.size(); ++i)
        {
            auto cell = strip.removeFromLeft (sliderCell);
            sliders[i]->label->setBounds (cell.removeFromTop (labelHeight));
            sliders[i]->value->setBounds (cell.removeFromBottom (valueHeight));
            sliders[i]->component->setBounds (cell.reduced (2, 2));
        }
    }

    const auto cellWidth = [] (Style style)
    {
        switch (style)
        {
            case Style::Knob:    return knobCell;
            case Style::Combo:   return comboCell;
            case Style::WideCombo: return wideComboCell;
            case Style::Toggle:  return toggleCell;
            case Style::Action:  return actionCell;
            case Style::VSlider: return sliderCell;
        }
        return knobCell;
    };

    // Rows are declared per section, so a section is as wide as it needs to
    // be and no control is ever squeezed to make one fit.
    std::vector<int> rows = section.rowCounts;
    if (rows.empty())
        rows.push_back ((int) grid.size());

    // Rows are centred in whatever height the band gave the section, so a
    // section with fewer rows than the band's height allows — FILTER ENV's
    // single DEPTH row beside four full-height sliders — does not leave all
    // its spare room in one block underneath.
    int usedRows = 0;
    for (std::size_t r = 0, placed = 0; r < rows.size() && placed < grid.size();
         ++r)
    {
        placed += (std::size_t) juce::jmax (0, rows[r]);
        ++usedRows;
    }
    std::size_t index = 0;
    int rowTop = content.getY()
                 + juce::jmax (0, (content.getHeight()
                                   - usedRows * gridRowHeight) / 2);
    for (std::size_t r = 0; r < rows.size() && index < grid.size(); ++r)
    {
        const int count = juce::jmin (rows[r], (int) (grid.size() - index));
        int width = 0;
        for (int i = 0; i < count; ++i)
            width += cellWidth (grid[index + (std::size_t) i]->style);
        int x = content.getX() + (content.getWidth() - width) / 2;

        Control* previous = nullptr;
        for (int i = 0; i < count; ++i, ++index)
        {
            auto* control = grid[index];
            auto cell = juce::Rectangle<int> (x, rowTop,
                                              cellWidth (control->style),
                                              gridRowHeight);
            x += cell.getWidth();

            auto body = cell;
            auto captionRow = body.removeFromTop (labelHeight);
            // A control with no caption of its own shares the one to its
            // left — the INTERVAL pair is one caption over two buttons, and
            // an empty label under the second is the only orphaned text the
            // panel had.
            if (control->label->getText().isEmpty() && previous != nullptr)
            {
                previous->label->setBounds (
                    previous->label->getBounds().getUnion (captionRow));
                control->label->setVisible (false);
                control->label->setBounds ({});
            }
            else
            {
                control->label->setVisible (true);
                control->label->setBounds (captionRow);
            }
            // Every style gives up the same strip at the foot of its cell,
            // whether or not it prints a value there, so the controls in a
            // row share one vertical centre instead of the knobs sitting
            // 6 px above everything else.
            auto valueRow = body.removeFromBottom (valueHeight);
            switch (control->style)
            {
                case Style::Knob:
                    control->value->setBounds (valueRow);
                    control->component->setBounds (
                        body.withSizeKeepingCentre (knobDiameter, knobDiameter));
                    break;
                case Style::Combo:
                case Style::WideCombo:
                    control->component->setBounds (
                        body.withSizeKeepingCentre (cell.getWidth() - 8,
                                                    comboHeight));
                    break;
                case Style::Toggle:
                case Style::Action:
                    control->component->setBounds (
                        body.withSizeKeepingCentre (cell.getWidth() - 10,
                                                    toggleHeight));
                    break;
                case Style::VSlider:
                    break;   // laid out in the strip above
            }
            previous = control;
        }
        rowTop += gridRowHeight;
    }
}

// Adjacent modules share a common gutter. No decorative signal connectors.
void SeptumAudioProcessorEditor::layoutBand (const std::vector<int>& indices,
                                             juce::Rectangle<int> bounds)
{
    if (indices.empty()) return;
    int total = 0;
    for (int index : indices)
        total += sections[(std::size_t) index]->naturalWidth();
    const int slots = (int) indices.size() - 1;
    const int spare = juce::jmax (0, bounds.getWidth() - total - slots * sectionGap);
    const int extraWidth = spare / (int) indices.size();
    int x = bounds.getX();
    for (int index : indices)
    {
        auto& section = *sections[(std::size_t) index];
        const int width = section.naturalWidth() + extraWidth;
        layoutSection (section, { x, bounds.getY(), width, bounds.getHeight() });
        x += width + sectionGap;
    }
}

juce::Rectangle<int> SeptumAudioProcessorEditor::panelSizeForWorkArea (
    juce::Rectangle<int> workArea)
{
    // Full size wherever it fits. Where it does not - a 1366x768 or 1280x800
    // laptop, or a 1080p screen at 150 % - the whole panel shrinks rather
    // than losing its bottom edge. Never below the size the captions stay
    // readable at: on a screen smaller than that, a window the player can
    // move is a better failure than type nobody can read.
    double scale = 1.0;
    if (! workArea.isEmpty())
        scale = juce::jmin (1.0,
                            (double) (workArea.getWidth() - windowChromeWidth)
                                / editorWidth,
                            (double) (workArea.getHeight() - windowChromeHeight)
                                / editorHeight);
    scale = juce::jmax (scale, (double) minimumWidth / editorWidth);
    return { juce::roundToInt (editorWidth * scale),
             juce::roundToInt (editorHeight * scale) };
}

void SeptumAudioProcessorEditor::resized()
{
    // The panel keeps its proportions whatever the window's are, and is
    // centred in whatever is left over.
    const double scale = juce::jmin ((double) getWidth() / editorWidth,
                                     (double) getHeight() / editorHeight);
    const auto placed =
        juce::Rectangle<int> { juce::roundToInt (editorWidth * scale),
                               juce::roundToInt (editorHeight * scale) }
            .withCentre (getLocalBounds().getCentre());
    canvas.setTransform (
        juce::AffineTransform::scale ((float) scale)
            .translated ((float) placed.getX(), (float) placed.getY()));
    canvas.setBounds (0, 0, editorWidth, editorHeight);

    layoutPanel();
}

void SeptumAudioProcessorEditor::layoutPanel()
{
    auto bounds = juce::Rectangle<int> (0, 0, editorWidth, editorHeight);

    auto header = bounds.removeFromTop (headerHeight).reduced (16, 8);
    titleLabel.setBounds (header.getX() + 4, 25, 235, 46);
    subtitleLabel.setBounds (header.getX() + 6, 75, 234, 22);
    toneStatusLabel.setBounds (268, 71, 740, 17);
    programLabel.setBounds (268, 12, 270, 18);
    programBox.setBounds (268, 34, 270, 28);
    layoutSection (*systemSection, { 1442, 12, 202, 143 });
    routingSection->bounds = { 560, 8, 855, 79 };
    {
        int x = 578;
        for (auto* control : routingSection->controls)
        {
            const int width = control->style == Style::Combo ? 210 : 124;
            control->label->setBounds (x, 12, width, 18);
            if (control->style == Style::Combo)
                control->component->setBounds (x + 8, 34, width - 16, 28);
            else
            {
                control->component->setBounds (x + (width - 34) / 2, 30, 34, 34);
                control->value->setBounds (x, 66, width, 18);
            }
            x += width + 18;
        }
    }
    editToneSection->bounds = { 268, 91, 1150, 64 };
    {
        auto row = editToneSection->bounds;
        partTabBounds[0] = row.removeFromLeft (569);
        row.removeFromLeft (12);
        partTabBounds[1] = row;
        for (std::size_t i = 0; i < 2; ++i)
        {
            auto area = partTabBounds[i].reduced (13, 5);
            auto top = area.removeFromTop (28);
            (i == 0 ? upperEnableButton : lowerEnableButton).setBounds (
                top.removeFromRight (66).reduced (0, 1));
            (i == 0 ? upperButton : lowerButton).setBounds (top);
            auto text = area.removeFromTop (18);
            partRouteLabels[i].setBounds (text.removeFromLeft (220));
            partActivityLabels[i].setBounds (text);
        }
    }

    // Keyboard row: the per-tone play controls, then the lever at the left of
    // the keys as on the unit, then the keys under the band that says which
    // tone each of them reaches.
    // TONE PLAY gets the row at its full height. The row used to be reduced by
    // four vertically *before* the section was cut out of it, so the section
    // had 94 points for the 102 `keyboardHeight` declares — its centring term
    // went to zero and the GLIDE TIME, BEND and TONE OCT read-outs overflowed
    // onto the well's bottom border, the only section on the panel with no
    // bottom padding at all. The four points go to the lever and the keys,
    // which is what they were for.
    auto keyboardRow = bounds.removeFromBottom (keyboardHeight).reduced (10, 0);
    layoutSection (*tonePlaySection,
                   keyboardRow.removeFromLeft (tonePlaySection->naturalWidth()));
    keyboardRow.removeFromLeft (sectionGap);
    keyboardRow.reduce (0, 4);
    lever.setBounds (keyboardRow.removeFromLeft (66).reduced (0, 2));
    keyboardRow.removeFromLeft (6);
    keyZoneBounds = keyboardRow.removeFromTop (keyZoneHeight);
    keyboardRow.removeFromTop (2);
    // The visible range spans 36 white keys (five octaves).
    keyboard.setKeyWidth ((float) keyboardRow.getWidth() / 36.0f);
    keyboard.setBounds (keyboardRow.reduced (0, 2));

    // Shared patch/performance controls above the keys. Program and keyboard
    // routing selectors live in the header with the part tabs.
    auto strip = bounds.removeFromBottom (stripHeight).reduced (10, 2);
    stripSection->bounds = strip;
    auto stripContent = strip.reduced (sectionPadding, sectionPadding);
    stripContent.removeFromTop (sectionTitleHeight);
    {
        const int columns = (int) stripSection->controls.size();
        const int gap = 20;
        const int cellWidth = (stripContent.getWidth() - gap * (columns - 1)) / columns;
        int x = stripContent.getX();
        for (auto* control : stripSection->controls)
        {
            auto cell = juce::Rectangle<int> (x, stripContent.getY(), cellWidth,
                                              stripContent.getHeight());
            x += cellWidth + gap;
            control->label->setBounds (cell.removeFromTop (labelHeight));
            // Every column reserves the value row, including dropdowns.
            const auto value = cell.removeFromBottom (valueHeight);
            if (control->value != nullptr)
                control->value->setBounds (value);
            control->component->setBounds (cell.withSizeKeepingCentre (
                control->style == Style::Combo ? cellWidth - 16 : knobDiameter,
                control->style == Style::Combo ? comboHeight : knobDiameter));
        }
    }

    // Left performance cluster, spanning all three bands.
    auto panel = bounds.reduced (10, 4);
    auto cluster = panel.removeFromLeft (clusterWidth);
    performSection->bounds = cluster;
    auto clusterContent = cluster.reduced (sectionPadding, sectionPadding);
    clusterContent.removeFromTop (sectionTitleHeight);
    masterLabel.setBounds (clusterContent.removeFromTop (labelHeight));
    masterSlider.setBounds (
        clusterContent.removeFromTop (56).withSizeKeepingCentre (52, 52));
    masterValueLabel.setBounds (clusterContent.removeFromTop (valueHeight));
    clusterContent.removeFromTop (8);
    octLabel.setBounds (clusterContent.removeFromTop (labelHeight));
    {
        auto row = clusterContent.removeFromTop (24);
        octDownButton.setBounds (row.removeFromLeft (36));
        octValueLabel.setBounds (row.removeFromLeft (row.getWidth() - 36));
        octUpButton.setBounds (row);
    }
    clusterContent.removeFromTop (10);
    const auto placeClusterControl = [&clusterContent] (Control* control)
    {
        if (control == nullptr)
            return;
        control->label->setBounds (clusterContent.removeFromTop (labelHeight));
        if (control->style == Style::Knob)
        {
            control->component->setBounds (
                clusterContent.removeFromTop (knobDiameter)
                    .withSizeKeepingCentre (knobDiameter, knobDiameter));
            control->value->setBounds (clusterContent.removeFromTop (valueHeight));
        }
        else if (control->style == Style::Combo)
        {
            control->component->setBounds (
                clusterContent.removeFromTop (comboHeight).reduced (2, 0));
        }
        else
        {
            control->component->setBounds (
                clusterContent.removeFromTop (toggleHeight)
                    .withSizeKeepingCentre (clusterContent.getWidth() - 12,
                                            toggleHeight));
        }
        clusterContent.removeFromTop (8);
    };
    placeClusterControl (tempoControl);

    // The cluster's foot reports rather than edits: the output meter and the
    // voice count, where the hardware puts its own indicators.
    if (clusterContent.getHeight() > 60)
    {
        voiceLabel.setBounds (clusterContent.removeFromBottom (14));
        clusterContent.removeFromBottom (4);
        // The meter takes what the cluster has left rather than a fixed
        // 44 px: it is the one thing on the panel that reads better the
        // taller it is, and the space was otherwise dead.
        meterBounds = clusterContent.removeFromBottom (
            juce::jmin (150, clusterContent.getHeight() - 6));
    }
    else
    {
        meterBounds = {};
        voiceLabel.setBounds ({});
    }

    panel.removeFromLeft (sectionGap);

    // Three bands. Section indices follow the construction order in the
    // constructor: 0 PERFORM, then the voice chain, then the modulators, then
    // the arpeggiator, the external input and the effects, then PATCH.
    const int rowHeight = (panel.getHeight() - (bandRows - 1) * sectionGap)
                          / bandRows;
    auto voiceRow = panel.removeFromTop (rowHeight);
    panel.removeFromTop (sectionGap);
    auto modulationRow = panel.removeFromTop (rowHeight);
    panel.removeFromTop (sectionGap);
    auto effectsRow = panel;

    // Section indices follow the construction order in the constructor, and
    // inserting a section silently shifts every list below it. The titles at
    // the indices these three calls address are published through
    // getSectionTitles() and checked by the suite, because the `jassert` that
    // used to stand here is compiled out of every build this project makes.
    layoutBand ({ 1, 2, 3, 4, 5 }, voiceRow);
    layoutBand ({ 6, 7, 8, 9, 10 }, modulationRow);
    layoutBand ({ 11, 12, 13, 14 }, effectsRow);

    // Laying the panel out also re-reads what the parameters say about the
    // tones and the keyboard, so a panel rendered without the frame timer
    // running — the suite's snapshot — shows the same thing a live one does.
    reconcileEditTarget();
    refreshToneTarget();
    applyKeyboardOctave();
}

void SeptumAudioProcessorEditor::paint (juce::Graphics& g)
{
    // Whatever the window has that the panel's proportions do not use.
    const auto toneColour = editingUpper ? colours::toneUpper : colours::toneLower;
    g.fillAll (colours::surround.interpolatedWith (toneColour, 0.15f));
}

void SeptumAudioProcessorEditor::PanelCanvas::paint (juce::Graphics& g)
{
    owner.paintPanel (g);
}

void SeptumAudioProcessorEditor::paintPanel (juce::Graphics& g)
{
    const auto toneColour = editingUpper ? colours::toneUpper : colours::toneLower;
    // The whole surface identifies the edit target, including when that part
    // is muted or another part is sounding. Keep ink and control faces crisp
    // by tinting the chassis and panel fills rather than overlaying the UI.
    g.setGradientFill (juce::ColourGradient (
        juce::Colour (0xff2b3a3e).interpolatedWith (toneColour, 0.24f), 0.0f, 0.0f,
        colours::body.interpolatedWith (toneColour, 0.18f),
        0.0f, (float) editorHeight, false));
    g.fillAll();
    const juce::String toneName = editingUpper ? "UPPER" : "LOWER";
    for (const auto& section : sections)
    {
        if (section.get() == editToneSection || section.get() == routingSection)
            continue;
        auto area = section->bounds.reduced (1).toFloat();
        if (area.isEmpty())
            continue;
        const bool light = section->band == Band::Voice;
        const bool input = section->title == "EXT IN";
        const bool perTone = section->scope == Scope::PerTone;
        const float tint = light ? 0.32f : input ? 0.38f : perTone ? 0.22f : 0.16f;
        const auto panelTop = (light ? colours::silver : colours::recess)
                                  .interpolatedWith (toneColour, tint);
        const auto panelBottom = (light ? colours::silverShade
                                       : juce::Colour (0xff1c272b))
                                     .interpolatedWith (toneColour, tint);
        g.setGradientFill (juce::ColourGradient (
            panelTop, area.getTopLeft(), panelBottom, area.getBottomLeft(), false));
        g.fillRoundedRectangle (area, 4.0f);

        auto title = area.withHeight ((float) sectionTitleHeight)
                         .translated (0.0f, (float) sectionPadding - 1.0f)
                         .reduced ((float) sectionPadding, 0.0f);
        if (perTone)
        {
            auto chip = title.removeFromRight ((float) toneChipWidth)
                             .withSizeKeepingCentre ((float) toneChipWidth, 18.0f);
            g.setColour (toneColour);
            g.fillRoundedRectangle (chip, 2.0f);
            g.setColour (colours::ink);
            g.setFont (juce::Font (juce::FontOptions (12.5f, juce::Font::bold)));
            g.drawText (toneName, chip.toNearestInt(), juce::Justification::centred);
            title.removeFromRight (4.0f);
        }
        else if (section->band == Band::InputEffects)
        {
            g.setColour (colours::frame.withAlpha (0.75f));
            g.setFont (juce::Font (juce::FontOptions (12.0f, juce::Font::bold)));
            g.drawText ("SHARED", title.removeFromRight (58.0f).toNearestInt(),
                        juce::Justification::centredRight);
        }
        g.setColour (light ? colours::ink : colours::frame);
        g.setFont (juce::Font (juce::FontOptions (15.0f, juce::Font::bold)));
        g.drawText (section->title, title.toNearestInt(),
                    juce::Justification::centredLeft);
    }
    paintPartTabs (g);

    paintKeyboardZones (g);

    // Output meter, at the foot of the performance cluster where the voice
    // count sits: the one place on the panel that reports rather than edits.
    if (! meterBounds.isEmpty())
    {
        // Decibels, not amplitude. On a linear scale a healthy −20 dBFS fills
        // a tenth of the bar, so the meter sat near its floor for everything
        // that was not about to clip.
        const int barWidth = 12;
        const auto height = (float) meterBounds.getHeight();
        const auto positionOf = [] (float dB)
        {
            return juce::jlimit (0.0f, 1.0f,
                                 juce::jmap (dB, meterFloorDb, 0.0f, 0.0f, 1.0f));
        };
        for (int channel = 0; channel < 2; ++channel)
        {
            auto bar = juce::Rectangle<int> (
                meterBounds.getCentreX() - barWidth - 3 + channel * (barWidth + 6),
                meterBounds.getY(), barWidth, meterBounds.getHeight());
            g.setColour (colours::sliderTrack);
            g.fillRoundedRectangle (bar.toFloat(), 2.0f);

            const float level = juce::jlimit (0.0f, 1.2f, meterLevel[channel]);
            const float dB = juce::Decibels::gainToDecibels (level, meterFloorDb);
            g.setColour (level >= 1.0f ? colours::accent : colours::ledOn);
            g.fillRoundedRectangle (
                bar.toFloat().removeFromBottom (positionOf (dB) * height), 2.0f);

            // A −6 dB mark, so the scale can be read rather than guessed.
            g.setColour (colours::frame.withAlpha (0.45f));
            const float mark =
                (float) bar.getBottom() - positionOf (-6.0f) * height;
            g.drawHorizontalLine ((int) mark, (float) bar.getX(),
                                  (float) bar.getRight());
        }
    }
}

// The band above the keys: which tone each key reaches, drawn on the keys
// themselves rather than left to be inferred from two combo boxes at the
// other end of the strip. In SPLIT it is the only place on the panel that
// shows where the split point actually falls.
void SeptumAudioProcessorEditor::paintKeyboardZones (juce::Graphics& g)
{
    if (keyZoneBounds.isEmpty())
        return;

    const auto raw = [this] (const char* id)
    {
        const auto* value = processor.parameters.getRawParameterValue (id);
        return value != nullptr ? (int) std::lround (value->load()) : 0;
    };
    const int mode = raw ("keyboard_mode");
    const bool partUpper = raw ("keyboard_part") == 0;

    const auto zone = [&] (juce::Rectangle<int> area, bool upper,
                           const juce::String& text)
    {
        if (area.getWidth() <= 0)
            return;
        const auto colour = upper ? colours::toneUpper : colours::toneLower;
        const auto* parameter = processor.parameters.getRawParameterValue (
            upper ? "upper_enabled" : "lower_enabled");
        const bool enabled = parameter == nullptr || parameter->load() >= 0.5f;
        g.setColour (enabled ? colour : colour.withAlpha (0.22f));
        g.fillRoundedRectangle (area.toFloat().reduced (0.5f, 0.0f), 2.0f);
        g.setColour (enabled ? colours::ink : colours::frame);
        g.setFont (juce::Font (juce::FontOptions (12.5f, juce::Font::bold)));
        g.drawText (enabled ? text : text + " / OFF", area, juce::Justification::centred);
    };

    if (mode == 0)
    {
        zone (keyZoneBounds, partUpper, partUpper ? "UPPER" : "LOWER");
    }
    else if (mode == 1)
    {
        // Layered: both tones on every key, one stripe each.
        auto area = keyZoneBounds;
        zone (area.removeFromTop (area.getHeight() / 2), true, "UPPER");
        zone (area, false, "LOWER");
    }
    else
    {
        // The split point is a note number; the keyboard knows where that key
        // starts, so the boundary is drawn where the player will hear it.
        // getKeyStartPosition is already in the keyboard's own coordinates.
        const int splitNote = raw ("split_point");
        const int boundary =
            keyboard.getX()
            + juce::roundToInt (keyboard.getKeyStartPosition (splitNote));
        auto area = keyZoneBounds;
        const int cut = juce::jlimit (area.getX(), area.getRight(), boundary);
        auto lower = area.withRight (cut);
        auto upper = area.withLeft (cut);
        zone (lower, false, "LOWER");
        zone (upper, true, "UPPER");
        const auto caption = getSplitPointCaption();
        g.setColour (colours::frame);
        g.fillRect (cut - 1, keyZoneBounds.getY(), 2, keyZoneBounds.getHeight());
        g.setFont (juce::Font (juce::FontOptions (12.0f, juce::Font::bold)));
        g.drawText (caption.text, caption.bounds,
                    caption.bounds.getX() < cut ? juce::Justification::centredRight
                                                : juce::Justification::centredLeft);
    }
}

// Named the way the keys under it are named. The parameter's own text is fixed
// at middle C = C4, but the drawn keys are renamed by the octave shift, so at
// OCT +1 the band said "C4" over the key the keyboard itself prints as C5 —
// one drawn key with two names fifteen points apart. Everything that prints
// the split point comes through here, so there is one name to be right.
juce::String SeptumAudioProcessorEditor::getSplitPointKeyName() const
{
    const auto* value = processor.parameters.getRawParameterValue ("split_point");
    const int splitNote = value != nullptr ? (int) std::lround (value->load()) : 60;
    return juce::MidiMessage::getMidiNoteName (splitNote, true, true,
                                               keyboard.getOctaveForMiddleC());
}

juce::String SeptumAudioProcessorEditor::getToneAudibilitySummary() const
{
    return toneAudibility().summary;
}

SeptumAudioProcessorEditor::SplitPointCaption
SeptumAudioProcessorEditor::getSplitPointCaption() const
{
    SplitPointCaption caption;
    if (keyZoneBounds.isEmpty())
        return caption;
    const auto* value = processor.parameters.getRawParameterValue ("split_point");
    const int splitNote = value != nullptr ? (int) std::lround (value->load()) : 60;
    caption.text = getSplitPointKeyName();

    const int boundary = keyboard.getX()
                         + juce::roundToInt (
                             keyboard.getKeyStartPosition (splitNote));
    const int cut =
        juce::jlimit (keyZoneBounds.getX(), keyZoneBounds.getRight(), boundary);
    // SPLIT POINT reaches C8 while the drawn keyboard stops at C7, so for the
    // top twelve settings the boundary sits at the right edge of the band and a
    // name drawn to its right left the panel entirely. It flips to the left of
    // the line there, the way a tooltip does.
    constexpr int nameWidth = 34;
    const bool flip = cut + 3 + nameWidth > keyZoneBounds.getRight();
    caption.bounds = juce::Rectangle<int> (flip ? cut - 3 - nameWidth : cut + 3,
                                           keyZoneBounds.getY(), nameWidth,
                                           keyZoneBounds.getHeight());
    return caption;
}

juce::StringArray SeptumAudioProcessorEditor::getSectionsOverflowingTheirWell() const
{
    juce::StringArray overflowing;
    for (const auto& entry : sections)
    {
        if (entry->bounds.isEmpty())
            continue;
        for (const auto* control : entry->controls)
        {
            const auto fits = [&entry] (const juce::Component* part)
            {
                return part == nullptr || part->getBounds().isEmpty()
                       || entry->bounds.contains (part->getBounds());
            };
            if (! fits (control->component.get()) || ! fits (control->label.get())
                || ! fits (control->value.get()))
            {
                overflowing.addIfNotAlreadyThere (entry->title);
                break;
            }
        }
    }
    return overflowing;
}

juce::String SeptumAudioProcessorEditor::getKeyboardRepaintKey() const
{
    const auto reading = [this] (const char* id)
    {
        const auto* value = processor.parameters.getRawParameterValue (id);
        return value != nullptr ? (int) std::lround (value->load()) : 0;
    };
    // The octave is in here only since the split-point caption started being
    // named the way the keys under it are named. Moving OCT renames the drawn
    // keys through `applyKeyboardOctave`, which repaints the keyboard component
    // — but the band is painted by the canvas behind it, so without the octave
    // here it went on printing the old name over freshly renamed keys until
    // something unrelated repainted the panel.
    return juce::String (reading ("keyboard_mode")) + "/"
           + juce::String (reading ("keyboard_part")) + "/"
           + juce::String (reading ("split_point")) + "/"
           + juce::String (reading ("system_octave")) + "/"
           + juce::String (reading ("upper_enabled")) + "/"
           + juce::String (reading ("lower_enabled"));
}

juce::StringArray SeptumAudioProcessorEditor::getSectionTitles() const
{
    juce::StringArray titles;
    for (const auto& entry : sections)
        titles.add (entry->title);
    return titles;
}

void SeptumAudioProcessorEditor::timerCallback()
{
    refreshPartActivity();
    meterLevel[0] = processor.getOutputLevel (0);
    meterLevel[1] = processor.getOutputLevel (1);
    voiceLabel.setText (juce::String (processor.getActiveVoiceCount())
                            + " / 10 VOICES",
                        juce::dontSendNotification);
    applyKeyboardOctave();
    // KEYBOARD, PART and SPLIT POINT are automatable and a program change
    // moves all three, so what the panel says about the tones has to follow
    // the parameters rather than only the edit tabs. Repainted only when one
    // of them has actually moved.
    reconcileEditTarget();
    const juce::String keyState = getKeyboardRepaintKey();
    if (keyState != lastKeyboardState)
    {
        lastKeyboardState = keyState;
        refreshToneTarget();
        canvas.repaint();
    }
    programBox.setSelectedId (processor.getCurrentProgram() + 1,
                              juce::dontSendNotification);
    // juce::Label::setText only repaints when the text actually changes, so
    // this costs nothing on the frames where nothing moved.
    refreshValues();
    if (! meterBounds.isEmpty())
        canvas.repaint (meterBounds.expanded (2));
}

void SeptumAudioProcessorEditor::handleNoteOn (juce::MidiKeyboardState*, int,
                                                   int note, float velocity)
{
    processor.triggerFromUi (note,
                             juce::jlimit (1, 127, (int) (velocity * 127.0f)));
}

void SeptumAudioProcessorEditor::handleNoteOff (juce::MidiKeyboardState*,
                                                    int, int note, float)
{
    processor.releaseFromUi (note);
}

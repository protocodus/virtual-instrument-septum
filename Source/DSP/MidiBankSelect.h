#pragma once
#include <array>

namespace septum
{
// SH-201 MIDI Implementation p. 1: decimal MSB 87, LSB 0 (PRESET) / 20
// (USER), program bytes 0..31. Keep bank latches per channel for ALL mode.
class MidiBankSelect
{
public:
    void reset() noexcept { channels_ = {}; }
    void select (int channel, int controller, int value) noexcept
    {
        if (channel < 1 || channel > 16 || value < 0 || value > 127) return;
        auto& bank = channels_[static_cast<unsigned> (channel - 1)];
        if (controller == 0) bank.msb = value;
        else if (controller == 32) bank.lsb = value;
        else return;
        bank.selected = true;
    }
    [[nodiscard]] int program (int channel, int number) const noexcept
    {
        if (channel < 1 || channel > 16 || number < 0 || number > 127) return -1;
        const auto& bank = channels_[static_cast<unsigned> (channel - 1)];
        // Existing plug-in sessions used a flat 0..63 program list. Explicit
        // bank selection opts into the hardware map; bare PCs retain it.
        if (! bank.selected) return number < 64 ? number : -1;
        if (bank.msb != 87 || number > 31) return -1;
        if (bank.lsb == 0) return number;
        if (bank.lsb == 20) return number + 32;
        return -1;
    }
private:
    struct Bank { int msb = 87, lsb = 0; bool selected = false; };
    std::array<Bank, 16> channels_ {};
};
}

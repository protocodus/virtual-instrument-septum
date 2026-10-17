# MIDI bank selection

The [SH-201 MIDI Implementation](https://cdn.roland.com/assets/media/pdf/SH-201_MI.pdf), p. 1, maps decimal bank MSB 87 and LSB 0 to PRESET A-1–D-8, and LSB **20** to USER A-1–D-8. Program bytes are 0–31 (the printed program numbers are 1–32). The LSB is decimal 20, not hexadecimal 20/decimal 32. The [Owner’s Manual](https://static.roland.com/assets/media/pdf/SH-201_OM.pdf), p. 68, provides an independent Receive Bank Select switch.

The previous receiver ignored both bank controllers. It selected directly from the plug-in’s 64-entry program list, so a hardware USER-bank selection followed by program 1 recalled a PRESET sound. The receiver now latches bank bytes until Program Change, respects RX BANK independently of RX PROGRAM, and rejects unknown banks/programs. ALL-channel compatibility mode keeps independent latches for each MIDI channel. These latches are transient MIDI receiver state and reset when playback is prepared.

Bare Program Change messages retain the existing flat plug-in mapping until that channel receives an explicit bank selection. This preserves old host sessions while giving SH-201 sequences the documented mapping. The two groups contain Septum’s 32 authored presets and 32 initial user slots; the mapping does not supply Roland’s factory sound data. The offline fixed-patch renderer retains its explicit reject/ignore policy for bank/program changes.

The added RX BANK setting is appended to the host parameter list and saved in native format 4 and later; earlier preset formats migrate it to ON. Tests cover all 32 USER slots, invalid decimal/hex interpretations, receive switches, channel independence, bank/PC/note ordering, exact audio equivalence with the selected program, and state migration.

"""Synthetic librarian records: preserve payloads and reject malformed banks."""
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location(
    "extract_reference_patch",
    Path(__file__).resolve().parents[1] / "Tools" / "extract_reference_patch.py")
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)


def fixture():
    header = bytearray(160)
    header[:20] = b"SH2LibrarianFile0000"
    header[32:36] = struct.pack(">I", 1)
    blocks = [bytes((index + i) % 128 for i in range(length))
              for index, length in enumerate((33, 64, 64, 5, 10, 8) + (66,) * 16)]
    blocks[0] = b"TEST PATCH  " + blocks[0][12:]
    record = b"".join(struct.pack(">I", len(block)) + block for block in blocks)
    record += b"Original test fixture\0\0\0\0"
    return bytes(header) + struct.pack(">I", len(record)) + record, blocks


class ReferencePatchExtractionTests(unittest.TestCase):
    def test_round_trip_all_parameter_bytes_and_dt1_addresses(self):
        data, expected = fixture()
        patches = extract.parse_bank(data)
        self.assertEqual(patches[0][0], "TEST PATCH")
        self.assertEqual(patches[0][1], expected)
        packets = extract.encode_syx(patches[0][1]).split(b"\xf7")
        self.assertEqual(packets[-1], b"")
        self.assertEqual(len(packets), 23)
        for index, packet in enumerate(packets[:-1]):
            self.assertEqual(packet[:7], bytes.fromhex("f0 41 10 00 00 16 12"))
            self.assertEqual(packet[7:11], bytes((0x10, 0, index, 0)))
            self.assertEqual(packet[11:-1], expected[index])
            self.assertEqual(sum(packet[7:]) % 128, 0)

    def test_rejects_truncated_bank_or_missing_record(self):
        data, _ = fixture()
        for truncated in (data[:80], data[:163], data[:-1]):
            with self.assertRaises(ValueError):
                extract.parse_bank(truncated)
        data = bytearray(data)
        data[32:36] = struct.pack(">I", 2)
        with self.assertRaises(ValueError):
            extract.parse_bank(data)

    def test_rejects_wrong_block_size_and_non_midi_payload(self):
        data, _ = fixture()
        for offset, value in ((167, 32), (168, 128)):
            altered = bytearray(data)
            altered[offset] = value
            with self.assertRaises(ValueError):
                extract.parse_bank(altered)

    def test_rejects_unknown_container_revision_and_trailing_data(self):
        data, _ = fixture()
        for altered in (b"UNKNOWN" + data[7:], data + b"extra"):
            with self.assertRaises(ValueError):
                extract.parse_bank(altered)


if __name__ == "__main__":
    unittest.main()

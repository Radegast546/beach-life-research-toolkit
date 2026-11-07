"""Synthetic standalone workflow and distribution boundary regressions."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import research
import extract_installshield_v6


def game_fixture(root):
    script = root / 'Data/Script/Test.ble'
    script.parent.mkdir(parents=True)
    script.write_bytes(bytes(b ^ 255 for b in b'Example 123;'))
    sound = root / 'Data/Sound'
    sound.mkdir()
    payload = b'RIFF' + struct.pack('<I', 4) + b'WAVE'
    (sound / 'blsnd.spf').write_bytes(payload)
    (sound / 'blsnd.hdr').write_bytes(struct.pack('<II32s', 0, len(payload), b'example'))
    return script, sound


class ResearchTests(unittest.TestCase):
    def test_complete_synthetic_extraction_preserves_sources_and_hashes_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script, sound = game_fixture(root / 'game')
            before = {p: p.read_bytes() for p in (script, *sound.iterdir())}
            result = research.extract(root / 'game', root / 'output')
            self.assertTrue(result['inputs_unchanged'])
            self.assertEqual((root / 'output/scripts/Data/Script/Test.txt').read_text(), 'Example 123;')
            self.assertEqual((root / 'output/sounds/example.wav').read_bytes(), (sound / 'blsnd.spf').read_bytes())
            for path, data in before.items():
                self.assertEqual(path.read_bytes(), data)
            for relative, record in result['outputs'].items():
                self.assertEqual(hashlib.sha256((root / 'output' / relative).read_bytes()).hexdigest(), record['sha256'])
            self.assertEqual(json.loads((root / 'output/extraction.json').read_text()), result)

    def test_overlapping_existing_and_unknown_sprite_outputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game_fixture(root / 'game')
            for output in (root / 'game/output', root / 'game', root):
                with self.assertRaises(ValueError):
                    research.extract(root / 'game', output)
            self.assertFalse((root / 'game/output').exists())

    def test_bad_sound_names_and_truncated_spans_fail_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, sound = game_fixture(root / 'game')
            for name, length in ((b'../escape', 12), (b'C:escape', 12), (b'CON', 12), (b'ok', 99)):
                (sound / 'blsnd.hdr').write_bytes(struct.pack('<II32s', 0, length, name))
                with self.assertRaises(ValueError):
                    research.extract(root / 'game', root / 'output')
                self.assertFalse((root / 'output').exists())

    def test_truncated_biz_cannot_be_reported_as_successful(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'map.biz'
            path.write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'truncated'):
                list(research.biz_chunks(path))
            path.write_bytes(struct.pack('<I', 8192) + bytes(4092) + struct.pack('<I', 10) + bytes(4092))
            with self.assertRaisesRegex(ValueError, 'span'):
                list(research.biz_chunks(path))

    def test_literal_only_biz_chunk_retains_both_planes(self):
        raw = bytes(range(256)) * 256
        compressed = bytearray(5)
        for start in range(0, len(raw), 112):
            part = raw[start:start + 112]
            compressed.append(0xE0 + len(part) // 4 - 1)
            compressed.extend(part)
        compressed.append(0xFC)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'map.biz'
            path.write_bytes(struct.pack('<I', 8192) + bytes(4092) + struct.pack('<I', len(compressed)) + bytes(4092) + compressed)
            self.assertEqual(list(research.biz_chunks(path)), [(0, raw)])

    def test_cabinet_paths_are_portable_and_checked_before_writes(self):
        cabinet = object.__new__(extract_installshield_v6.InstallShieldCabinet)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for unsafe in ('../escape', 'C:\\escape', '\\escape', 'Data/../../escape', 'NUL', 'file:stream'):
                cabinet.files = [{'path': unsafe, 'name': 'example'}]
                with self.assertRaises(ValueError):
                    cabinet.extract(root / 'output')
                self.assertFalse((root / 'output').exists())
            cabinet.files = [{'path': 'Data\\Script\\example.txt', 'name': 'example.txt'}]
            with patch.object(cabinet, 'extract_one', return_value=b'example'):
                cabinet.extract(root / 'output')
            self.assertEqual((root / 'output/Data/Script/example.txt').read_bytes(), b'example')


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Focused regression tests for the water-animation BIN decoder."""

from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_wateranims


def make_wateranim_file(frame_payloads):
    offsets = []
    payload_parts = []
    payload_size = 0
    for frame_payload in frame_payloads:
        offsets.append(payload_size)
        payload_parts.append(frame_payload)
        payload_size += len(frame_payload)

    sizes = [len(frame_payload) for frame_payload in frame_payloads]
    header = extract_wateranims.HEADER_STRUCT.pack(
        payload_size, *offsets, *sizes
    )
    return header + b"".join(payload_parts)


def opaque_frame_payload():
    complete_runs, remainder = divmod(
        extract_wateranims.DECODED_PIXEL_COUNT, 127
    )
    return bytes((127,)) * complete_runs + bytes((remainder,))


class WaterAnimationDecoderTests(unittest.TestCase):
    def test_quadrant_blocks_are_rearranged_into_row_major_order(self):
        quadrant_size = extract_wateranims.QUADRANT_PIXEL_COUNT
        decoded = b"".join(
            bytes((value,)) * quadrant_size for value in (10, 20, 30, 40)
        )

        row_major = extract_wateranims.rearrange_quadrant_stream(decoded)
        width = extract_wateranims.FRAME_SIZE
        self.assertEqual(row_major[0 * width + 0], 10)
        self.assertEqual(row_major[127 * width + 127], 10)
        self.assertEqual(row_major[0 * width + 128], 20)
        self.assertEqual(row_major[127 * width + 255], 20)
        self.assertEqual(row_major[128 * width + 0], 30)
        self.assertEqual(row_major[255 * width + 127], 30)
        self.assertEqual(row_major[128 * width + 128], 40)
        self.assertEqual(row_major[255 * width + 255], 40)

        image = extract_wateranims.build_frame_image(decoded)
        self.assertEqual(image.getpixel((128, 128)), (255, 255, 255, 40))

    def test_valid_bin_decodes_15_frames_and_leaves_atlas_slot_16_empty(self):
        frame_payload = opaque_frame_payload()
        file_data = make_wateranim_file(
            [frame_payload] * extract_wateranims.FRAME_COUNT
        )

        frames = extract_wateranims.decode_wateranim_frames(file_data)
        self.assertEqual(len(frames), 15)
        self.assertEqual(frames[0].getpixel((0, 0)), (255, 255, 255, 255))

        spritesheet = extract_wateranims.build_spritesheet(frames)
        self.assertEqual(spritesheet.size, (1024, 1024))
        self.assertEqual(spritesheet.getpixel((512, 768)), (255, 255, 255, 255))
        self.assertEqual(spritesheet.getpixel((768, 768)), (255, 255, 255, 0))
        self.assertEqual(spritesheet.getpixel((1023, 1023)), (255, 255, 255, 0))

    def test_malformed_decoded_pixel_counts_fail_loudly(self):
        with self.assertRaisesRegex(ValueError, "decoded pixel count is 1"):
            extract_wateranims.decode_rle_frame(bytes((1,)))
        with self.assertRaisesRegex(ValueError, "decoded frame has 1 pixels"):
            extract_wateranims.rearrange_quadrant_stream(bytes((255,)))

    def test_header_payload_size_is_validated(self):
        frame_payload = opaque_frame_payload()
        file_data = bytearray(
            make_wateranim_file([frame_payload] * extract_wateranims.FRAME_COUNT)
        )
        declared_payload_size = len(file_data) - extract_wateranims.HEADER_SIZE
        struct.pack_into("<I", file_data, 0, declared_payload_size + 1)

        with self.assertRaisesRegex(ValueError, "header payload size"):
            extract_wateranims.parse_wateranim_header(bytes(file_data))

    def test_frame_sizes_must_cover_the_declared_payload(self):
        frame_payload = opaque_frame_payload()
        file_data = bytearray(
            make_wateranim_file([frame_payload] * extract_wateranims.FRAME_COUNT)
        )
        first_size_position = 4 + extract_wateranims.FRAME_COUNT * 4
        struct.pack_into("<I", file_data, first_size_position, len(frame_payload) - 1)

        with self.assertRaisesRegex(ValueError, "frame sizes total"):
            extract_wateranims.parse_wateranim_header(bytes(file_data))

    def test_configured_paths_are_resolved_when_arguments_are_omitted(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            original_game_dir = root / "original-game"
            source_path = (
                original_game_dir / "Data" / "WaterAnims" / "wateranim1.bin"
            )
            source_path.parent.mkdir(parents=True)
            source_path.write_bytes(b"configured source")
            output_dir = root / "runtime-assets" / "wateranims"
            paths = SimpleNamespace(
                original_game_dir=original_game_dir,
                wateranim_assets_dir=output_dir,
            )
            spritesheet = extract_wateranims.Image.new("RGBA", (1, 1))

            with patch.object(
                extract_wateranims, "get_project_paths", return_value=paths
            ), patch.object(
                extract_wateranims,
                "decode_wateranim_frames",
                return_value=[],
            ) as decode_frames, patch.object(
                extract_wateranims,
                "build_spritesheet",
                return_value=spritesheet,
            ):
                output_path = extract_wateranims.extract_wateranim(1)

            decode_frames.assert_called_once_with(b"configured source")
            self.assertEqual(
                output_path, output_dir / "wateranim1_spritesheet.png"
            )
            self.assertTrue(output_path.is_file())

    def test_frame_offsets_and_sizes_must_stay_inside_payload(self):
        frame_payload = opaque_frame_payload()
        file_data = bytearray(
            make_wateranim_file([frame_payload] * extract_wateranims.FRAME_COUNT)
        )
        payload_size = len(file_data) - extract_wateranims.HEADER_SIZE
        last_offset_position = 4 + (extract_wateranims.FRAME_COUNT - 1) * 4
        struct.pack_into("<I", file_data, last_offset_position, payload_size)

        with self.assertRaisesRegex(ValueError, "frame 14 span"):
            extract_wateranims.parse_wateranim_header(bytes(file_data))


if __name__ == "__main__":
    unittest.main()

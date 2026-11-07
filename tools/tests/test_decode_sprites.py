#!/usr/bin/env python3
"""Focused regression tests for the BLSprite animated frame-table parser."""

from collections import Counter
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest

import decode_sprites as decoder
from project_paths import get_project_paths

TOOLS_DIR = Path(__file__).resolve().parent


class ColorPixelTypeTests(unittest.TestCase):
    def test_hud_black_ink_is_not_discarded_as_unused_palette(self):
        palette = [(12, 13, 14)] * 256
        palette[255] = (0, 0, 0)
        sprite = SimpleNamespace(name="ui3_bar_blob_cash", num_frames=1, palette=palette)
        for uncompressed in (False, True):
            lut = decoder.make_rgba_lut(sprite, "UI3_bar_blob_cash", uncompressed)
            self.assertEqual(lut[0], decoder.TRANSPARENT_RGBA)
            self.assertEqual(lut[255], bytes((0, 0, 0, 255)))
        # Typed UI still uses native high-bit blend weights.
        sprite.num_frames = 3
        self.assertEqual(decoder.make_rgba_lut(sprite, "UI3_bar_blob_cash")[255],
                         bytes((*palette[63], 64)))

    def test_color_types_use_six_bit_palette_and_export_blend_weights(self):
        palette = [(7, 8, 9)] * 256
        palette[0] = (255, 255, 0)
        palette[1] = (0, 0, 0)
        palette[50] = (255, 0, 255)
        palette[64:] = [(0, 0, 0)] * 192
        sprite = SimpleNamespace(name="generic", num_frames=3, palette=palette)

        for parent_format in (3, 6):
            sprite.num_frames = parent_format
            for uncompressed in (False, True):
                with self.subTest(parent_format=parent_format, uncompressed=uncompressed):
                    lut = decoder.make_rgba_lut(sprite, "image", uncompressed)
                    self.assertEqual(lut[0], decoder.TRANSPARENT_RGBA)
                    self.assertEqual(lut[1], bytes((0, 0, 0, 255)))
                    self.assertEqual(lut[50], bytes((255, 0, 255, 255)))
                    self.assertEqual(lut[64], bytes((255, 255, 0, 191)))
                    self.assertEqual(lut[114], bytes((255, 0, 255, 191)))
                    self.assertEqual(lut[128], bytes((255, 255, 0, 128)))
                    self.assertEqual(lut[178], bytes((255, 0, 255, 128)))
                    self.assertEqual(lut[192], bytes((255, 255, 0, 64)))
                    self.assertEqual(lut[242], bytes((255, 0, 255, 64)))

    def test_full_palette_formats_keep_distinct_upper_bank_colors(self):
        palette = [(12, 13, 14)] * 256
        palette[64] = (0, 0, 0)
        palette[65] = (255, 0, 255)
        sprite = SimpleNamespace(name="generic", palette=palette)

        for parent_format in (1, 2, 5, 11):
            sprite.num_frames = parent_format
            for uncompressed in (False, True):
                with self.subTest(parent_format=parent_format, uncompressed=uncompressed):
                    lut = decoder.make_rgba_lut(sprite, "image", uncompressed)
                    self.assertEqual(lut[64], decoder.TRANSPARENT_RGBA)
                    self.assertEqual(lut[65], bytes((255, 0, 255, 255)))

    def test_special_layers_retain_existing_material_conversion(self):
        palette = [(12, 13, 14)] * 256
        palette[64] = (0, 0, 0)
        palette[65] = (255, 0, 255)
        sprite = SimpleNamespace(name="generic", num_frames=3, palette=palette)

        self.assertEqual(
            decoder.make_rgba_lut(sprite, "shadow")[65], bytes((255, 255, 255, 255))
        )
        self.assertEqual(
            decoder.make_rgba_lut(sprite, "pick")[65], bytes((255, 255, 255, 255))
        )
        self.assertEqual(
            decoder.make_rgba_lut(sprite, "depth")[65], bytes((65, 65, 65, 255))
        )
        self.assertEqual(
            decoder.make_rgba_lut(sprite, "lightmap")[64], decoder.TRANSPARENT_RGBA
        )
        self.assertEqual(
            decoder.make_rgba_lut(sprite, "lightmap")[65], bytes((255, 0, 255, 255))
        )
        for layer in ("shadow", "pick", "depth", "lightmap"):
            with self.subTest(layer=layer):
                lut = decoder.make_rgba_lut(sprite, layer, uncompressed=True)
                self.assertEqual(lut[64], decoder.TRANSPARENT_RGBA)
                self.assertEqual(lut[65], bytes((255, 0, 255, 255)))


class AnimatedFrameTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sprite_dir = get_project_paths().original_game_dir / "Data" / "Sprites"
        cls.hdr_path = sprite_dir / "BLSprite.hdr"
        cls.dat_path = sprite_dir / "BLSprite.dat"
        if not cls.hdr_path.exists() or not cls.dat_path.exists():
            raise unittest.SkipTest("Original BLSprite files are not available")

        _, _, cls.sprites = decoder.parse_hdr(cls.hdr_path)
        cls.dat_data = cls.dat_path.read_bytes()

    @classmethod
    def sub_image(cls, sprite_name, sub_name):
        sprite = next(sprite for sprite in cls.sprites if sprite.name == sprite_name)
        return next(sub for sub in sprite.sub_images if sub.name == sub_name)

    def assert_table_frame_count(self, sprite_name, sub_name, orientations):
        sub = self.sub_image(sprite_name, sub_name)
        table = decoder.find_animated_frame_table(self.dat_data, 24, sub)
        if table is None:
            self.fail(f"missing table for {sprite_name}/{sub_name}")
        _, _, _, offsets = table
        self.assertEqual(len(offsets), sub.field1 * orientations)
        self.assertEqual(offsets[0], 0)
        self.assertEqual(offsets, sorted(offsets))

    def test_building_table_has_four_facings(self):
        self.assert_table_frame_count("arcade_anim", "SingleAnim", 4)

    def test_staff_table_has_eight_facings(self):
        self.assert_table_frame_count("barman", "chat", 8)

    def test_long_guest_tables_are_not_truncated_at_250_entries(self):
        self.assert_table_frame_count("fat_bloke", "aerobic2", 8)
        self.assert_table_frame_count("fat_bloke", "fat_fidget1", 8)
        self.assert_table_frame_count("fat_bloke", "rescue", 8)

    def test_long_guest_clip_decodes_all_frames(self):
        sub = self.sub_image("fat_bloke", "aerobic2")
        frames = decoder.decode_animated_sprite(self.dat_data, 24, sub)
        if frames is None:
            self.fail("fat_bloke/aerobic2 did not decode")
        self.assertEqual(len(frames), sub.field1 * 8)

    def test_powergen_full_palette_image_and_lightmap_conversion_is_unchanged(self):
        sprite = next(sprite for sprite in self.sprites if sprite.name == "powergen")
        self.assertEqual(sprite.num_frames, 5)
        for layer in ("image", "lightmap"):
            self.assertTrue(any(sub.name == layer for sub in sprite.sub_images))
            for uncompressed in (False, True):
                with self.subTest(layer=layer, uncompressed=uncompressed):
                    lut = decoder.make_rgba_lut(sprite, layer, uncompressed)
                    expected = [
                        decoder.TRANSPARENT_RGBA
                        if index == 0 or (index >= 64 and rgb == (0, 0, 0))
                        else bytes((*rgb, 255))
                        for index, rgb in enumerate(sprite.palette)
                    ]
                    self.assertEqual(lut, expected)

    def test_tree17_preserves_all_color_types_without_opaque_black_patches(self):
        sprite = next(sprite for sprite in self.sprites if sprite.name == "flower")
        sub = next(sub for sub in sprite.sub_images if sub.name == "tree17")
        frames = decoder.decode_animated_sprite(self.dat_data, 24, sub)
        self.assertIsNotNone(frames)
        self.assertEqual((sub.data_offset, sub.data_size), (210678555, 27224))
        self.assertEqual((sub.width, sub.height, len(frames)), (86, 86, 8))
        types = Counter(index >> 6 for frame in frames for index in frame if index)
        self.assertEqual(types, {0: 11964, 1: 2434, 2: 5092, 3: 5100})

        lut = decoder.make_rgba_lut(sprite, sub.name)
        rgba = [lut[index] for frame in frames for index in frame]
        self.assertEqual(sum(pixel[3] != 0 for pixel in rgba), 24590)
        self.assertEqual(sum(pixel == bytes((0, 0, 0, 255)) for pixel in rgba), 0)
        self.assertEqual(
            Counter(pixel[3] for pixel in rgba if pixel[3]),
            {255: 11964, 191: 2434, 128: 5092, 64: 5100},
        )

    def test_flower06_preserves_authored_low_bank_black_detail(self):
        sprite = next(sprite for sprite in self.sprites if sprite.name == "flower06")
        sub = next(sub for sub in sprite.sub_images if sub.name == "flower06")
        frames = decoder.decode_animated_sprite(self.dat_data, 24, sub)
        self.assertIsNotNone(frames)
        self.assertEqual((sub.data_offset, sub.data_size), (210731357, 7390))
        self.assertEqual([frame.count(1) for frame in frames], [19, 14, 30, 21])

        lut = decoder.make_rgba_lut(sprite, sub.name)
        rgba = [lut[index] for frame in frames for index in frame]
        self.assertEqual(sum(pixel[3] != 0 for pixel in rgba), 6462)
        self.assertEqual(sum(pixel == bytes((0, 0, 0, 255)) for pixel in rgba), 84)
        self.assertEqual(
            Counter(pixel[3] for pixel in rgba if pixel[3]),
            {255: 5542, 191: 604, 128: 246, 64: 70},
        )

    def test_guest_clothing_ramp_preserves_index_50_and_selects_variants(self):
        sprite = deepcopy(
            next(sprite for sprite in self.sprites if sprite.name == "fat_bloke")
        )
        sub = next(sub for sub in sprite.sub_images if sub.name == "d_walk_normal")
        frames = decoder.decode_animated_sprite(self.dat_data, 24, sub)
        if frames is None:
            self.fail("fat_bloke/d_walk_normal did not decode")

        self.assertEqual(len(sprite.palettes), 66)
        self.assertEqual(sprite.palettes[0][50], (255, 0, 255))
        self.assertEqual(sprite.palettes[7][50], (220, 135, 1))
        self.assertEqual(frames[0].count(50), 32)

        decoder.select_sprite_palette(sprite, 0)
        palette_zero_lut = decoder.make_rgba_lut(sprite, sub.name)
        self.assertEqual(palette_zero_lut[50], bytes((255, 0, 255, 255)))
        self.assertEqual(
            sum(palette_zero_lut[index][3] == 255 for index in frames[0]), 384
        )
        self.assertEqual(sum(palette_zero_lut[index][3] != 0 for index in frames[0]), 568)

        decoder.select_sprite_palette(sprite, 7)
        palette_seven_lut = decoder.make_rgba_lut(sprite, sub.name)
        self.assertEqual(palette_seven_lut[50], bytes((220, 135, 1, 255)))
        self.assertEqual(
            sum(palette_seven_lut[index][3] == 255 for index in frames[0]), 384
        )
        self.assertEqual(sum(palette_seven_lut[index][3] != 0 for index in frames[0]), 568)

        with self.assertRaisesRegex(ValueError, "66 palette"):
            decoder.select_sprite_palette(sprite, 66)

    def test_boardwalk_palette_reconstructs_four_types_from_six_bit_colors(self):
        sprite = deepcopy(
            next(sprite for sprite in self.sprites if sprite.name == "pathtile_11b")
        )
        sub = next(sub for sub in sprite.sub_images if sub.name == "set1")
        frames = decoder.decode_animated_sprite(self.dat_data, 24, sub)
        if frames is None:
            self.fail("pathtile_11b/set1 did not decode")

        self.assertEqual(sprite.palette[171], (0, 0, 0))
        decoder.apply_pathtile_palette_fix(sprite, self.sprites)
        self.assertEqual(
            sprite.palette[171],
            (0, 0, 0),
            "the concrete fallback palette must not overwrite boardwalk keys",
        )

        lut = decoder.make_rgba_lut(sprite, sub.name)
        self.assertEqual(171 & 0x3F, 43)
        self.assertEqual(lut[171], bytes((*sprite.palette[43], 128)))
        self.assertEqual(
            sum(lut[index][3] != 0 for index in frames[17]),
            1024,
            "all four boardwalk pixel types should resolve through the 64-color bank",
        )

    def test_grass08_static_floor_uses_the_real_single_frame_table(self):
        sprite = next(sprite for sprite in self.sprites if sprite.name == "grass08")
        sub = self.sub_image("grass08", "grass08")
        table = decoder.find_animated_frame_table(self.dat_data, 24, sub)
        if table is None:
            self.fail("missing table for grass08/grass08")
        table_start, _, _, offsets = table
        self.assertEqual(table_start, 24 + sub.data_offset - 24)
        self.assertEqual(offsets, [0])

        frames = decoder.decode_animated_sprite(self.dat_data, 24, sub)
        if frames is None:
            self.fail("grass08/grass08 did not decode")
        self.assertEqual((sub.width, sub.height), (62, 32))
        self.assertEqual(len(frames), 1)
        self.assertEqual(sum(pixel != 0 for pixel in frames[0]), 1024)
        self.assertEqual(
            [
                sum(pixel != 0 for pixel in frames[0][row * 62 : (row + 1) * 62])
                for row in range(32)
            ],
            [
                2,
                6,
                10,
                14,
                18,
                22,
                26,
                30,
                34,
                38,
                42,
                46,
                50,
                54,
                58,
                62,
                62,
                58,
                54,
                50,
                46,
                42,
                38,
                34,
                30,
                26,
                22,
                18,
                14,
                10,
                6,
                2,
            ],
        )
        self.assertEqual(sprite.palettes[0][0], (255, 255, 0))


if __name__ == "__main__":
    unittest.main()

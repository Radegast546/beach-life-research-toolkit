#!/usr/bin/env python3
"""
Beach Life Sprite Extractor (BLSprite.hdr + BLSprite.dat)

File format (reverse-engineered):

BLSprite.hdr:
  Header:
    - 20 bytes: timestamp string (null-terminated, e.g. "2002:08:20 14:19:21")
    - u32: bpp (typically 4)
    - u32: num_sprites (e.g. 838)

  Per sprite:
    - u8: name_length (including null terminator)
    - name_length bytes: sprite name (null-terminated)
    - u32: format selector (legacy name num_frames)
    - format 5 only: four u8 facing depth scales (legacy packed name parent_id)
    - u32: palette count
    - RGB palettes: 64 entries for formats 3/6, otherwise 256
    - u32: num_sub_images
    - Sub-images:
        First sub-image:
          - u8: sub_name_length
          - sub_name_length bytes: sub name (null-terminated, e.g. "image", "depth", "lightmap", "pick", "shadow")
          - u16: field1 (typically 1)
          - u8: bpp
          - i16: width
          - i16: height
          - i16: origin_x
          - i16: origin_y
          - u32: data_offset (into BLSprite.dat, after the 24-byte .dat header)
          - u32: data_size
        Subsequent sub-images:
          - u16: separator (always 4)
          - (same fields as first sub-image)
    - u16: trailing separator (4)

BLSprite.dat:
  - 20 bytes: timestamp (same as .hdr)
  - u32: bpp
  - Raw sprite data follows, referenced by offsets from .hdr

Usage:
    python decode_sprites.py info <hdr_path>                              - List all sprites and sub-images
    python decode_sprites.py extract <hdr_path> <dat_path> <out> [sprite] - Extract sprites as PNG images
    python decode_sprites.py extract-list <hdr> <dat> <out> <targets>     - Extract named sprites from a file or comma list
    python decode_sprites.py palette <hdr_path> <sprite_name>             - Export a sprite's palette
    python decode_sprites.py search <hdr_path> <query>                    - Search sprites by name

Extraction options:
    --write-palettes       Also write palette.png beside extracted frames (off by default)
    --skip-existing        Skip a target sprite if its output folder already has PNGs
    --only-sub <name[,..]> Extract only named sub-images/layers
"""

import argparse
import json
import os
import re
import shutil
import struct
import sys
import time


class SpriteSubImage:
    def __init__(
        self,
        name,
        field1,
        bpp,
        width,
        height,
        origin_x,
        origin_y,
        data_offset,
        data_size,
    ):
        self.name = name
        self.field1 = field1
        self.bpp = bpp
        self.width = width
        self.height = height
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.data_offset = data_offset
        self.data_size = data_size

    def to_dict(self):
        return {
            "name": self.name,
            "field1": self.field1,
            "bpp": self.bpp,
            "width": self.width,
            "height": self.height,
            "origin_x": self.origin_x,
            "origin_y": self.origin_y,
            "data_offset": self.data_offset,
            "data_size": self.data_size,
        }


class SpriteEntry:
    def __init__(self, name, num_frames, parent_id, field3, palettes, sub_images):
        self.name = name
        self.num_frames = num_frames
        self.parent_id = parent_id
        self.field3 = field3
        self.palettes = palettes  # list of palettes (each a list of 256 RGB tuples)
        self.palette = (
            palettes[0] if palettes else []
        )  # first palette for backward compatibility
        self.sub_images = sub_images

    def to_dict(self):
        return {
            "name": self.name,
            "num_frames": self.num_frames,
            "parent_id": self.parent_id,
            "field3": self.field3,
            "num_palettes": len(self.palettes),
            "sub_images": [s.to_dict() for s in self.sub_images],
        }


def read_cstring(data, pos):
    """Read a length-prefixed null-terminated string."""
    name_len = data[pos]
    pos += 1
    name = data[pos : pos + name_len - 1].decode("ascii", errors="replace")
    pos += name_len  # includes the null terminator
    return name, pos


def parse_sub_image(data, pos):
    """Parse a single sub-image record (without leading separator)."""
    name, pos = read_cstring(data, pos)
    field1, bpp = struct.unpack_from("<HB", data, pos)
    pos += 3
    w, h, ox, oy = struct.unpack_from("<hhhh", data, pos)
    pos += 8
    data_offset, data_size = struct.unpack_from("<II", data, pos)
    pos += 8
    return SpriteSubImage(name, field1, bpp, w, h, ox, oy, data_offset, data_size), pos


def parse_hdr(hdr_path):
    """Parse the entire BLSprite.hdr file."""
    with open(hdr_path, "rb") as f:
        data = f.read()

    # Header
    timestamp = data[:20].split(b"\x00")[0].decode("ascii")
    bpp, num_sprites = struct.unpack_from("<II", data, 20)

    print(f"Timestamp: {timestamp}")
    print(f"BPP: {bpp}")
    print(f"Num sprites: {num_sprites}")
    print()

    pos = 28
    sprites = []

    for i in range(num_sprites):
        # Sprite name
        name, pos = read_cstring(data, pos)

        # Sprite fields
        num_frames = struct.unpack_from("<I", data, pos)[0]
        if num_frames == 5:
            # Four depth-scale bytes are retained in the legacy packed i32 field.
            num_frames, parent_id, num_palettes = struct.unpack_from("<IiI", data, pos)
            pos += 12
            field3 = num_palettes
        else:
            # 2 fields
            num_frames, num_palettes = struct.unpack_from("<II", data, pos)
            parent_id = -1
            field3 = 1
            pos += 8

        # Palettes
        palettes = []
        for p in range(num_palettes):
            palette = []
            for j in range(256):
                r, g, b = data[pos], data[pos + 1], data[pos + 2]
                palette.append((r, g, b))
                pos += 3
            palettes.append(palette)

        # Sub-images
        num_subs = struct.unpack_from("<I", data, pos)[0]
        pos += 4

        sub_images = []
        for s in range(num_subs):
            if s > 0:
                # Skip u16 separator
                pos += 2
            sub, pos = parse_sub_image(data, pos)
            sub_images.append(sub)

        # Trailing separator (u16) present after every sprite
        pos += 2

        sprites.append(
            SpriteEntry(name, num_frames, parent_id, field3, palettes, sub_images)
        )

    return timestamp, bpp, sprites


ANIMATION_TABLE_SEARCH_BACK = 100
ANIMATION_TABLE_MAX_ENTRIES = 0x10000
ANIMATION_TABLE_TRAILING_BYTES = 65536


def find_animated_frame_table(dat_data, dat_header_size, sub, expected_count=None):
    """Find a sequential playback table and its following frame-offset table.

    The header's ``data_offset`` commonly points 24 bytes into the record. The
    actual record starts with a sequential u16 playback table (0, 1, 2, ...),
    followed by u32 offsets relative to the compressed-frame region.
    """
    record_offset = dat_header_size + sub.data_offset
    payload_end = min(
        len(dat_data), record_offset + sub.data_size + ANIMATION_TABLE_TRAILING_BYTES
    )

    for back in range(ANIMATION_TABLE_SEARCH_BACK):
        table_start = record_offset - back
        if table_start < dat_header_size or table_start + 6 > payload_end:
            continue

        max_entries = min(
            ANIMATION_TABLE_MAX_ENTRIES, (payload_end - table_start) // 6
        )
        frame_count = 0
        while frame_count < max_entries:
            value = struct.unpack_from("<H", dat_data, table_start + frame_count * 2)[0]
            if value != frame_count:
                break
            frame_count += 1

        if frame_count == 0 or (expected_count is not None and frame_count != expected_count):
            continue

        offsets_start = table_start + frame_count * 2
        frame_data_start = offsets_start + frame_count * 4
        if frame_data_start > payload_end:
            continue

        offsets = [
            struct.unpack_from("<I", dat_data, offsets_start + index * 4)[0]
            for index in range(frame_count)
        ]
        if offsets[0] != 0:
            continue
        if any(current < previous for previous, current in zip(offsets, offsets[1:])):
            continue
        # data_size is compressed pixel bytes, excluding both offset tables.
        # The final chunk must not consume the following resource.
        bounded_end = min(len(dat_data), frame_data_start + sub.data_size)
        if frame_data_start + offsets[-1] >= bounded_end:
            continue

        return table_start, frame_data_start, bounded_end, offsets

    return None


def decode_animated_sprite(dat_data, dat_header_size, sub, is_1bit=False, expected_count=None):
    import struct

    target_len = sub.width * sub.height



    def try_direct(start_abs):
        pixel_pos = 0
        pos = start_abs
        pixels = bytearray(target_len)
        while pixel_pos < target_len and pos < len(dat_data):
            cmd = struct.unpack_from("<b", dat_data, pos)[0]
            pos += 1
            if cmd == 0:
                break
            elif cmd < 0:
                pixel_pos += min(-cmd, target_len - pixel_pos)
            else:
                for _ in range(min(cmd, target_len - pixel_pos)):
                    if is_1bit:
                        pixels[pixel_pos] = 1
                        pixel_pos += 1
                    elif pos < len(dat_data):
                        pixels[pixel_pos] = dat_data[pos]
                        pos += 1
                        pixel_pos += 1
        if pixel_pos == target_len:
            return [pixels]
        return None

    table = find_animated_frame_table(dat_data, dat_header_size, sub, expected_count)
    if table:
        _, frame_data_start, payload_end, offsets = table
        frames = []
        for frame_index, offset in enumerate(offsets):
            rle_start = frame_data_start + offset
            if frame_index + 1 < len(offsets):
                rle_end = frame_data_start + offsets[frame_index + 1]
            else:
                rle_end = payload_end

            pixel_pos = 0
            pos = rle_start
            pixels = bytearray(target_len)
            while pixel_pos < target_len and pos < rle_end:
                cmd = struct.unpack_from("<b", dat_data, pos)[0]
                pos += 1
                if cmd == 0:
                    break
                if cmd < 0:
                    pixel_pos += min(-cmd, target_len - pixel_pos)
                    continue

                run = min(cmd, target_len - pixel_pos)
                if is_1bit:
                    pixels[pixel_pos:pixel_pos + run] = b'\x01' * run
                else:
                    if pos + run > rle_end:
                        break
                    pixels[pixel_pos:pixel_pos + run] = dat_data[pos:pos + run]
                    pos += run
                pixel_pos += run

            if pixel_pos != target_len:
                frames = None
                break
            frames.append(pixels)

        if frames and len(frames) == len(offsets):
            return frames


    if expected_count is not None:
        return None  # A malformed declared table cannot fall back to guessed pixels.

    # Prioritize standard direct offset for static sprites (back=18 corresponds to data_offset + 6)
    start_direct = dat_header_size + sub.data_offset - 18
    if start_direct >= dat_header_size:
        frames = try_direct(start_direct)
        if frames:
            return frames

    for back in range(0, 500):
        start = dat_header_size + sub.data_offset - back
        if start < dat_header_size:
            continue
        frames = try_direct(start)
        if frames:
            if start >= 6:
                v_zeros = struct.unpack_from("<6s", dat_data, start - 6)[0]
                if v_zeros == b"\\x00\\x00\\x00\\x00\\x00\\x00":
                    return frames
            v = struct.unpack_from("<b", dat_data, start)[0]
            if v < 0:
                return frames
            if back == 0:
                return frames
            if back == 99:
                return frames

    for back in range(0, 500):
        start = dat_header_size + sub.data_offset - back
        if start < dat_header_size:
            continue
        frames = try_direct(start)
        if frames:
            return frames

    return None


def cmd_info(hdr_path):
    """Print sprite information."""
    timestamp, bpp, sprites = parse_hdr(hdr_path)

    total_subs = 0
    for sprite in sprites:
        print(
            f"  {sprite.name:40s}  frames={sprite.num_frames}  parent={sprite.parent_id}  subs={len(sprite.sub_images)}"
        )
        for sub in sprite.sub_images:
            print(
                f"    {sub.name:20s}  {sub.width:4d}x{sub.height:<4d}  origin=({sub.origin_x},{sub.origin_y})  "
                f"bpp={sub.bpp}  offset={sub.data_offset}  size={sub.data_size}"
            )
            total_subs += 1

    print(f"\nTotal: {len(sprites)} sprites, {total_subs} sub-images")


TRANSPARENT_RGBA = b"\x00\x00\x00\x00"
STRUCTURAL_SUB_IMAGES = {"image", "depth", "lightmap", "shadow", "pick"}
# HDR loader 0x00417391 dispatches parent formats 3/6 to the 64-color loader
# (0x00417449), which discards the upper 192 palette triples. The historical
# parser calls this parent format selector ``num_frames``; keep that API here.
TYPED_COLOR_PARENT_FORMATS = {3, 6}
SPECIAL_LAYER_SUB_IMAGES = {"depth", "lightmap", "shadow", "pick"}
# Color blitters 0x00401EA0 and 0x0041492D use the upper two pixel bits for
# source weights 1, 3/4, 1/2, 1/4. These are the nearest 8-bit PNG alpha values.
# Original RGB565 integer rounding and Bevy's linear blending can differ.
COLOR_PIXEL_TYPE_ALPHA = (255, 191, 128, 64)


def require_pillow():
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow is required for image extraction.")
        print("Install it with: pip install Pillow")
        sys.exit(1)
    return Image


def split_name_list(value):
    return [part.strip() for part in value.split(",") if part.strip()]


def load_target_names(target_spec):
    if not target_spec:
        return []

    if os.path.isfile(target_spec):
        names = []
        with open(target_spec, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if line:
                    names.extend(split_name_list(line))
        return names

    return split_name_list(target_spec)


def parse_only_subs(values):
    if not values:
        return None
    names = []
    for value in values:
        names.extend(split_name_list(value))
    return {name.lower() for name in names}


def select_sprite_palette(sprite, palette_index):
    if palette_index < 0 or palette_index >= len(sprite.palettes):
        raise ValueError(
            f"{sprite.name} has {len(sprite.palettes)} palette(s); "
            f"cannot select palette {palette_index}"
        )
    sprite.palette = sprite.palettes[palette_index]
    return sprite.palette


def palette_color(sprite, idx):
    if 0 <= idx < len(sprite.palette):
        return sprite.palette[idx]
    return (0, 0, 0)


def is_boardwalk_pathtile(sprite):
    name = sprite.name.lower()
    return name == "pathtile_b" or bool(re.fullmatch(r"pathtile_\d{2}b", name))


def decode_native_shadow_frames(archive, dat_header_size, sub, expected_count):
    """Normal-resolution format-5 shadow occupancy (native 00408120).

    Signed spans encode occupied/skipped pixels per row, without color literals
    or interpolated scanlines. PNG export is a diagnostic occupancy mask;
    runtime packed-color/depth blending is a separate compositor operation.
    """
    table = find_animated_frame_table(archive, dat_header_size, sub, expected_count)
    if table is None:
        raise ValueError('Missing count-qualified native shadow table')
    _, start, end, offsets = table
    frames = []
    for number, offset in enumerate(offsets):
        stop = start + offsets[number + 1] if number + 1 < len(offsets) else end
        position = start + offset
        frame = bytearray(sub.width * sub.height)
        for row in range(sub.height):
            column = 0
            while column < sub.width:
                if position >= stop:
                    raise ValueError(f'Truncated native shadow row {row}')
                command = struct.unpack_from('<b', archive, position)[0]
                position += 1
                length = abs(command)
                if not length or column + length > sub.width:
                    raise ValueError(f'Invalid native shadow span {command} at {column},{row}')
                if command > 0:
                    begin = row * sub.width + column
                    frame[begin:begin + length] = b'\x01' * length
                column += length
        frames.append(frame)
    return frames


def make_rgba_lut(sprite, sub_name, uncompressed=False):
    """Export typed color blending while retaining special-layer conversions."""
    table = []
    sub_name_lower = sub_name.lower()
    boardwalk = is_boardwalk_pathtile(sprite)
    # Ordinary indexed UI sprites retain all palette entries. In particular,
    # opaque black index 255 is ink in HUD status icons, not transparency.
    full_palette_ui = sprite.name.lower().startswith(("ui2_", "ui3_"))
    typed_color = (
        getattr(sprite, "num_frames", None) in TYPED_COLOR_PARENT_FORMATS
        and sub_name_lower not in SPECIAL_LAYER_SUB_IMAGES
    )

    for idx in range(256):
        if typed_color:
            if idx == 0:
                table.append(TRANSPARENT_RGBA)
            else:
                r, g, b = palette_color(sprite, idx & 0x3F)
                table.append(bytes((r, g, b, COLOR_PIXEL_TYPE_ALPHA[idx >> 6])))
            continue

        palette_idx = idx & 0x3F if boardwalk else idx
        if uncompressed:
            if idx == 0:
                table.append(TRANSPARENT_RGBA)
                continue
            r, g, b = palette_color(sprite, palette_idx)
            if not full_palette_ui and idx >= 64 and r == 0 and g == 0 and b == 0:
                table.append(TRANSPARENT_RGBA)
            else:
                table.append(bytes((r, g, b, 255)))
            continue

        if sub_name_lower == "shadow":
            # A native shadow is occupancy, not authored RGBA opacity. Exact
            # packed half-color/depth writes belong to the native compositor.
            table.append(bytes((255, 255, 255, 255)) if idx > 0 else TRANSPARENT_RGBA)
        elif sub_name_lower == "pick":
            table.append(bytes((255, 255, 255, 255)) if idx > 0 else TRANSPARENT_RGBA)
        elif sub_name_lower == "depth":
            table.append(bytes((idx, idx, idx, 255 if idx > 0 else 0)))
        else:
            r, g, b = palette_color(sprite, palette_idx)
            if idx == 0 or (
                not boardwalk and not full_palette_ui and idx >= 64 and r == 0 and g == 0 and b == 0
            ):
                table.append(TRANSPARENT_RGBA)
            else:
                table.append(bytes((r, g, b, 255)))

    return table


def image_from_indexed_pixels(indexed_pixels, width, height, rgba_lut, Image):
    target_len = width * height
    if len(indexed_pixels) != target_len or len(rgba_lut) != 256:
        raise ValueError('Incomplete indexed pixels or RGBA palette')
    # Preserve every LUT byte, including transparent RGB and partial alpha.
    indexed = Image.frombytes('P', (width, height), bytes(indexed_pixels))
    indexed.putpalette(b''.join(rgba_lut), rawmode='RGBA')
    return indexed.convert('RGBA')


def image_from_uncompressed_rows(
    raw_data, width, height, pitch, row_data_start, rgba_lut, Image
):
    rgba = bytearray()
    extend = rgba.extend

    for y in range(height):
        row_start = row_data_start + y * pitch
        row_end = min(row_start + width, len(raw_data))
        if row_start < len(raw_data):
            for idx in raw_data[row_start:row_end]:
                extend(rgba_lut[idx])
            missing = width - max(0, row_end - row_start)
        else:
            missing = width
        if missing > 0:
            extend(TRANSPARENT_RGBA * missing)

    return Image.frombytes("RGBA", (width, height), bytes(rgba))


def save_palette_image(sprite, sprite_dir, Image):
    palette = [palette_color(sprite, idx) for idx in range(256)]
    pal_img = Image.new("RGB", (256, 1))
    pal_img.putdata(palette)
    pal_img.save(os.path.join(sprite_dir, "palette.png"))


def find_best_uncompressed_pitch(raw_data, width, height):
    best_pitch = width
    min_diff = float("inf")
    rows_to_check = min(height - 4, 100)
    if rows_to_check <= 0 or len(raw_data) == 0:
        return best_pitch

    for pitch in range(width, width + 16):
        diff_sum = 0
        valid = True
        for y in range(rows_to_check):
            for x in range(width - 1):
                idx1 = y * pitch + x
                idx2 = (y + 1) * pitch + x
                if idx2 >= len(raw_data):
                    valid = False
                    break
                diff_sum += abs(raw_data[idx1] - raw_data[idx2])
            if not valid:
                break
        if valid and diff_sum < min_diff:
            min_diff = diff_sum
            best_pitch = pitch

    return best_pitch


def apply_pathtile_palette_fix(sprite, sprites):
    """Fill missing concrete path colors without destroying boardwalk transparency."""
    sprite_name = sprite.name.lower()
    if "pathtile" not in sprite_name or sprite_name.endswith("b"):
        return
    base_p01 = next((s for s in sprites if s.name == "pathtile_01"), None)
    if base_p01:
        zeros = sum(1 for c in sprite.palette if c == (0, 0, 0))
        if zeros > 150:
            sprite.palette = sprite.palette[:64] + base_p01.palette[64:]


def sprite_has_existing_pngs(sprite_dir):
    if not os.path.isdir(sprite_dir):
        return False
    for name in os.listdir(sprite_dir):
        if name.lower().endswith(".png"):
            return True
    return False


def write_extraction_manifest(output_dir, manifest):
    qa_dir = os.path.join(output_dir, "_qa")
    os.makedirs(qa_dir, exist_ok=True)
    path = os.path.join(qa_dir, "extraction_manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return path


def cmd_extract(hdr_path, dat_path, output_dir, target_sprite=None, target_names=None,
                write_palettes=False, skip_existing=False, only_subs=None,
                max_frames_per_sub=None, max_images_per_sprite=None, palette_index=0):
    """Extract source-validated frames; commit each complete parent from staging."""
    from pathlib import Path
    import hashlib
    import tempfile
    from sprite_pipeline import source_layout, rgba_frames
    start_time = time.perf_counter()
    root = Path(output_dir).resolve()
    for source in (Path(hdr_path).resolve(), Path(dat_path).resolve()):
        if source.is_relative_to(root):
            raise ValueError('Extraction output overlaps original source files')
    timestamp, bpp, sprites = parse_hdr(hdr_path)
    archive = Path(dat_path).read_bytes()
    selected = ([target_sprite] if target_sprite else [])
    selected += load_target_names(target_names) if isinstance(target_names, str) else list(target_names or [])
    targets = {name.lower() for name in selected}
    only = parse_only_subs(only_subs) if only_subs and not isinstance(only_subs, set) else only_subs
    source_ids = dict(hdr=hashlib.sha256(Path(hdr_path).read_bytes()).hexdigest(),
                      dat=hashlib.sha256(archive).hexdigest(),
                      decoder=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      contract=hashlib.sha256(Path(__file__).with_name('sprite_pipeline.py').read_bytes()).hexdigest(),
                      palette_index=palette_index)
    manifest = dict(hdr_path=str(hdr_path), dat_path=str(dat_path), output_dir=str(root),
                    timestamp=timestamp, bpp=bpp, source=source_ids, target_names=selected,
                    unknown_targets=sorted(targets - {s.name.lower() for s in sprites}),
                    only_sub_images=sorted(only) if only else None, write_palettes=write_palettes,
                    skip_existing=skip_existing, max_frames_per_sub=max_frames_per_sub,
                    max_images_per_sprite=max_images_per_sprite, processed_sprites=[],
                    skipped_sprites=[], skipped_sub_images=[], failed_sub_images=[], records=[], extracted_images=0)
    root.mkdir(parents=True, exist_ok=True)
    for sprite in sprites:
        if targets and sprite.name.lower() not in targets:
            continue
        if not re.fullmatch(r'[A-Za-z0-9_]+', sprite.name):
            raise ValueError(f'Unsafe parent name: {sprite.name!r}')
        select_sprite_palette(sprite, palette_index)
        apply_pathtile_palette_fix(sprite, sprites)
        destination = root / sprite.name
        stage = Path(tempfile.mkdtemp(prefix='.extract-stage-', dir=root))
        # Selected layers retain other products but invalidate their old proof.
        if only and destination.exists():
            shutil.copytree(destination, stage, dirs_exist_ok=True)
        records, file_hashes, images = [], {}, 0
        duplicates = {}
        failed = False
        for index, sub in enumerate(sprite.sub_images):
            occurrence = duplicates.get(sub.name.lower(), 0)
            duplicates[sub.name.lower()] = occurrence + 1
            if only and sub.name.lower() not in only:
                continue
            prefix = sub.name + (f'__record{index}' if occurrence else '')
            if not re.fullmatch(r'[A-Za-z0-9_]+', prefix):
                raise ValueError(f'Unsafe layer name: {sub.name!r}')
            try:
                layout = source_layout(sprite, sub)
                if ((max_frames_per_sub is not None and layout['frames'] > max_frames_per_sub) or
                    (max_images_per_sprite is not None and images + layout['frames'] > max_images_per_sprite)):
                    manifest['skipped_sub_images'].append(dict(sprite=sprite.name, sub_image=sub.name, reason='frame_limit'))
                    failed = True
                    continue
                for old in stage.glob(prefix + '_frame*.png'):
                    old.unlink()
                for frame_index, image in enumerate(rgba_frames(sprite, sub, archive)):
                    filename = f'{prefix}_frame{frame_index:03d}.png'
                    path = stage / filename
                    image.save(path)
                    file_hashes[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
                    images += 1
                records.append(dict(sprite=sprite.name, record=index, sub_image=sub.name, prefix=prefix,
                                    width=sub.width, height=sub.height, origin_x=sub.origin_x, origin_y=sub.origin_y,
                                    **layout, decoded_frames=layout['frames']))
            except (OSError, ValueError) as error:
                failed = True
                manifest['failed_sub_images'].append(dict(sprite=sprite.name, record=index,
                                                          sub_image=sub.name, error=str(error)))
        if only and set(only) - {sub.name.lower() for sub in sprite.sub_images}:
            failed = True
            manifest['failed_sub_images'].append(dict(sprite=sprite.name, error='Unknown selected subimage'))
        if failed:
            shutil.rmtree(stage)
            continue
        if write_palettes:
            save_palette_image(sprite, stage, require_pillow())
        (stage / '_sprite_source.json').write_text(json.dumps(dict(source=source_ids, records=records,
                                                                  files=file_hashes, complete=not bool(only)), indent=2), encoding='utf-8')
        # --skip-existing never accepts bare old PNGs. Verified identical files
        # can retain their folder; every file and the source identity must match.
        identical = False
        proof = destination / '_sprite_source.json'
        if skip_existing and proof.is_file():
            previous = json.loads(proof.read_text(encoding='utf-8'))
            identical = (previous.get('source') == source_ids and previous.get('files') == file_hashes and
                         {p.name for p in destination.glob('*_frame*.png')} == set(file_hashes) and
                         all((destination / name).is_file() and hashlib.sha256((destination / name).read_bytes()).hexdigest() == digest
                             for name, digest in file_hashes.items()))
        if identical:
            shutil.rmtree(stage)
        else:
            backup = root / (stage.name + '-previous')
            if destination.exists():
                destination.replace(backup)
            try:
                stage.replace(destination)
            except Exception:
                if backup.exists():
                    backup.replace(destination)
                raise
            if backup.exists():
                shutil.rmtree(backup)
        manifest['records'].extend(records)
        manifest['processed_sprites'].append(dict(name=sprite.name, images=images))
        manifest['extracted_images'] += images
        print(f'Extracted {sprite.name}: {images} source-validated images', flush=True)
    manifest['elapsed_seconds'] = round(time.perf_counter() - start_time, 3)
    path = write_extraction_manifest(str(root), manifest)
    print(f'Extraction manifest: {path}')
    if any(manifest[key] for key in ('unknown_targets', 'skipped_sub_images', 'failed_sub_images')):
        raise ValueError('Incomplete extraction; previous affected parents retained; inspect manifest')
    return manifest


def decode_rle_frames(
    data,
    width,
    height,
    is_animated,
    num_frames,
    data_size,
    is_1bit=False,
    fill_1bit=False,
    strict=False,
):
    """
    Decodes RLE frames.
    is_animated == True: animated sequence with internal offset table.
    Otherwise: sequential multi-frame RLE or single frame.
    """
    import struct

    target_len = width * height
    frame_chunks = []

    # is_animated indicates an animated sequence with internal frame offsets
    if is_animated:
        first_u16 = struct.unpack_from("<H", data, 0)[0]
        if first_u16 < 2000:
            # Has index table (playback table)
            offset_table_start = 0
            for i in range(0, min(2000, len(data)), 4):
                if struct.unpack_from("<I", data, i)[0] == 0:
                    offset_table_start = i
                    break

            # Find img0_start and num_unique
            # The offset table ends when the position reaches img0_start
            pos = offset_table_start
            offsets = []
            while True:
                off = struct.unpack_from("<I", data, pos)[0]
                offsets.append(off)
                pos += 4
                if len(offsets) > 1 and offsets[0] == 0:
                    # check if we reached the start of the data
                    if (
                        pos >= offset_table_start + offsets[1]
                    ):  # offsets[1] is typically the second offset, so offset_table_start + offsets[1] is well into the data. Wait, img0_start = pos.
                        break
                # Fallback to the old heuristic if it's tricky
                if pos - offset_table_start >= 4 * ((offset_table_start // 2) + 12):
                    break

            num_unique = (offset_table_start // 2) + 12
            pos = offset_table_start
            offsets = []
            for _ in range(num_unique):
                offsets.append(struct.unpack_from("<I", data, pos)[0])
                pos += 4
            img0_start = pos
            all_offsets = [img0_start + off for off in offsets]
        else:
            # No index table, starts directly with absolute offsets
            img0_start = struct.unpack_from("<I", data, 0)[0]
            num_unique = img0_start // 4
            pos = 0
            all_offsets = []
            for _ in range(num_unique):
                all_offsets.append(struct.unpack_from("<I", data, pos)[0])
                pos += 4

        all_offsets.append(data_size)

        for u_idx in range(num_unique):
            frame_off = all_offsets[u_idx]
            larger_offsets = [o for o in all_offsets if o > frame_off]
            frame_size = (
                min(larger_offsets) - frame_off
                if larger_offsets
                else data_size - frame_off
            )
            frame_chunks.append(data[frame_off : frame_off + frame_size])

    frames = []

    if is_animated:
        for f_idx, chunk in enumerate(frame_chunks):
            pixels = bytearray(target_len)
            pixel_pos = 0
            pos = 0

            while pixel_pos < target_len and pos < len(chunk):
                cmd = struct.unpack_from("<b", chunk, pos)[0]
                pos += 1

                if cmd == 0:
                    break
                elif cmd < 0:
                    run_len = -cmd
                    for _ in range(min(run_len, target_len - pixel_pos)):
                        pixels[pixel_pos] = 0
                        pixel_pos += 1
                elif cmd > 0:
                    lit_len = cmd
                    for _ in range(min(lit_len, target_len - pixel_pos)):
                        if is_1bit:
                            pixels[pixel_pos] = 1
                            pixel_pos += 1
                        else:
                            if pos < len(chunk):
                                pixels[pixel_pos] = chunk[pos]
                                pos += 1
                                pixel_pos += 1
            if strict and pixel_pos != target_len:
                raise ValueError(f'Incomplete sequential RLE frame {f_idx}: {pixel_pos}/{target_len} pixels')
            frames.append(pixels)
    else:
        # Sequential RLE without headers
        pos = 0
        for f_idx in range(num_frames):
            pixels = bytearray(target_len)
            pixel_pos = 0

            while pixel_pos < target_len and pos < len(data):
                cmd = struct.unpack_from("<b", data, pos)[0]
                pos += 1

                if cmd == 0:
                    break
                elif cmd < 0:
                    run_len = -cmd
                    pixel_pos += min(run_len, target_len - pixel_pos)
                elif cmd > 0:
                    lit_len = cmd
                    for _ in range(min(lit_len, target_len - pixel_pos)):
                        if is_1bit:
                            pixels[pixel_pos] = 1
                            pixel_pos += 1
                        else:
                            if pos < len(data):
                                pixels[pixel_pos] = data[pos]
                                pos += 1
                                pixel_pos += 1
            if strict and pixel_pos != target_len:
                raise ValueError(f'Incomplete sequential RLE frame {f_idx}: {pixel_pos}/{target_len} pixels')
            frames.append(pixels)

    if is_1bit and fill_1bit:
        fill_mask_frames(frames, width, height)
    return frames


def fill_mask_frames(frames, width, height):
    # Post-process 1-bit masks to fill scanlines using dual-edge interpolation
    # The game engine stores the left edge and right edge paths independently and skips rows
    # where the edge doesn't move horizontally to save space. We must track them independently!
    if frames:
        for f_idx in range(len(frames)):
            pixels = frames[f_idx]

            # Find the horizontal center of the shadow to separate left vs right edges
            global_min = width
            global_max = -1
            for p in range(len(pixels)):
                if pixels[p] > 0:
                    x = p % width
                    if x < global_min:
                        global_min = x
                    if x > global_max:
                        global_max = x

            if global_max == -1:
                continue  # Empty frame

            center_x = (global_min + global_max) // 2

            left_edges = [-1] * height
            right_edges = [-1] * height

            for y in range(height):
                row_start = y * width
                for x in range(width):
                    if pixels[row_start + x] > 0:
                        if x <= center_x:
                            if left_edges[y] == -1 or x < left_edges[y]:
                                left_edges[y] = x
                        if x >= center_x:
                            if right_edges[y] == -1 or x > right_edges[y]:
                                right_edges[y] = x

            def interpolate_edges(edges):
                first_valid = -1
                last_valid = -1
                for y in range(height):
                    if edges[y] != -1:
                        if first_valid == -1:
                            first_valid = y
                        last_valid = y
                if first_valid != -1:
                    for y in range(first_valid, last_valid + 1):
                        if edges[y] == -1:
                            prev_y = y - 1
                            while prev_y >= 0 and edges[prev_y] == -1:
                                prev_y -= 1
                            next_y = y + 1
                            while next_y < height and edges[next_y] == -1:
                                next_y += 1
                            if prev_y != -1 and next_y != height:
                                t = (y - prev_y) / (next_y - prev_y)
                                edges[y] = int(
                                    edges[prev_y] + t * (edges[next_y] - edges[prev_y])
                                )

            interpolate_edges(left_edges)
            interpolate_edges(right_edges)

            for y in range(height):
                if left_edges[y] != -1 and right_edges[y] != -1:
                    row_start = y * width
                    for x in range(left_edges[y], right_edges[y] + 1):
                        pixels[row_start + x] = 1

    final_frames = frames

    return final_frames


def cmd_extract_list(
    hdr_path,
    dat_path,
    output_dir,
    target_spec,
    write_palettes=False,
    skip_existing=False,
    only_subs=None,
    max_frames_per_sub=None,
    max_images_per_sprite=None,
    palette_index=0,
):
    """Extract multiple named sprites from a text file or comma-separated list."""
    target_names = load_target_names(target_spec)
    if not target_names:
        print(f"WARNING: no target sprites found in '{target_spec}'")
    return cmd_extract(
        hdr_path,
        dat_path,
        output_dir,
        target_names=target_names,
        write_palettes=write_palettes,
        skip_existing=skip_existing,
        only_subs=only_subs,
        max_frames_per_sub=max_frames_per_sub,
        max_images_per_sprite=max_images_per_sprite,
        palette_index=palette_index,
    )


def cmd_palette(hdr_path, sprite_name):
    """Export a sprite's palette as a PNG swatch."""
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow required. Install: pip install Pillow")
        sys.exit(1)

    _, _, sprites = parse_hdr(hdr_path)

    for sprite in sprites:
        if sprite.name.lower() == sprite_name.lower():
            img = Image.new("RGB", (256, 32))
            for x in range(256):
                r, g, b = sprite.palette[x]
                for y in range(32):
                    img.putpixel((x, y), (r, g, b))

            out_path = f"{sprite_name}_palette.png"
            img.save(out_path)
            print(f"Palette saved to {out_path}")
            print(
                f"Non-black entries: {sum(1 for r, g, b in sprite.palette if r + g + b > 0)}/256"
            )
            return

    print(f"Sprite '{sprite_name}' not found.")


def cmd_search(hdr_path, query):
    """Search sprites by name."""
    _, _, sprites = parse_hdr(hdr_path)
    query_lower = query.lower()

    results = [s for s in sprites if query_lower in s.name.lower()]
    print(f"Found {len(results)} sprites matching '{query}':\n")
    for s in results:
        sub_names = ", ".join(sub.name for sub in s.sub_images)
        print(f"  {s.name:40s}  frames={s.num_frames}  subs=[{sub_names}]")


def cmd_dump_json(hdr_path, output_path):
    """Dump all sprite metadata as JSON."""
    _, bpp, sprites = parse_hdr(hdr_path)

    data = {
        "bpp": bpp,
        "num_sprites": len(sprites),
        "sprites": [s.to_dict() for s in sprites],
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Metadata dumped to {output_path}")


def add_extract_options(parser):
    parser.add_argument(
        "--write-palettes",
        action="store_true",
        help="write palette.png beside extracted frames (disabled by default)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="skip a target sprite if its output folder already contains PNG files",
    )
    parser.add_argument(
        "--only-sub",
        action="append",
        default=[],
        metavar="NAME[,NAME]",
        help="extract only named sub-images/layers; may be repeated or comma-separated",
    )
    parser.add_argument(
        "--max-frames-per-sub",
        type=int,
        default=None,
        metavar="N",
        help="skip sub-images that decode to more than N frames; useful for broad QA runs while decoding is imperfect",
    )
    parser.add_argument(
        "--max-images-per-sprite",
        type=int,
        default=None,
        metavar="N",
        help="stop extracting a sprite after N written images; useful for smoke runs while decoding is imperfect",
    )
    parser.add_argument(
        "--palette-index",
        type=int,
        default=0,
        metavar="N",
        help="render selected sprites with embedded palette N (default: 0)",
    )


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Beach Life sprite extractor for BLSprite.hdr + BLSprite.dat"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    info = subparsers.add_parser("info", help="list all sprites and sub-images")
    info.add_argument("hdr_path")

    extract = subparsers.add_parser(
        "extract", help="extract all sprites or one named sprite"
    )
    extract.add_argument("hdr_path")
    extract.add_argument("dat_path")
    extract.add_argument("output_dir")
    extract.add_argument("target_sprite", nargs="?")
    add_extract_options(extract)

    extract_list = subparsers.add_parser(
        "extract-list", help="extract sprites named in a file or comma-separated list"
    )
    extract_list.add_argument("hdr_path")
    extract_list.add_argument("dat_path")
    extract_list.add_argument("output_dir")
    extract_list.add_argument(
        "targets", help="targets.txt path or comma-separated names"
    )
    add_extract_options(extract_list)

    palette = subparsers.add_parser("palette", help="export a sprite palette swatch")
    palette.add_argument("hdr_path")
    palette.add_argument("sprite_name")

    search = subparsers.add_parser("search", help="search sprites by name")
    search.add_argument("hdr_path")
    search.add_argument("query")

    dump_json = subparsers.add_parser("json", help="dump sprite metadata as JSON")
    dump_json.add_argument("hdr_path")
    dump_json.add_argument("output_path")

    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.command == "info":
        cmd_info(args.hdr_path)
    elif args.command == "extract":
        cmd_extract(
            args.hdr_path,
            args.dat_path,
            args.output_dir,
            args.target_sprite,
            write_palettes=args.write_palettes,
            skip_existing=args.skip_existing,
            only_subs=parse_only_subs(args.only_sub),
            max_frames_per_sub=args.max_frames_per_sub,
            max_images_per_sprite=args.max_images_per_sprite,
            palette_index=args.palette_index,
        )
    elif args.command == "extract-list":
        cmd_extract_list(
            args.hdr_path,
            args.dat_path,
            args.output_dir,
            args.targets,
            write_palettes=args.write_palettes,
            skip_existing=args.skip_existing,
            only_subs=parse_only_subs(args.only_sub),
            max_frames_per_sub=args.max_frames_per_sub,
            max_images_per_sprite=args.max_images_per_sprite,
            palette_index=args.palette_index,
        )
    elif args.command == "palette":
        cmd_palette(args.hdr_path, args.sprite_name)
    elif args.command == "search":
        cmd_search(args.hdr_path, args.query)
    elif args.command == "json":
        cmd_dump_json(args.hdr_path, args.output_path)
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()

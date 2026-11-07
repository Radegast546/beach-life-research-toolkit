"""Shared source contract for all sprite extraction and atlas builders.

The parent legacy ``num_frames`` is a format selector. Subimage field1/field2
declare the stored frame grid. Only formats 3/5/6 are labelled facing blocks;
UI sequences retain their raw fields without pretending UI states are views.
"""
import hashlib
import math
import itertools

from PIL import Image
import decode_sprites as decoder

MAX_ATLAS_SIZE = 8192


def source_layout(sprite, sub):
    if sprite.num_frames not in (1, 2, 3, 5, 6):
        raise ValueError(f'Unknown sprite format: {sprite.name}: {sprite.num_frames}')
    if min(sub.width, sub.height, sub.field1, sub.bpp) <= 0:
        raise ValueError(f'Invalid source geometry: {sprite.name}/{sub.name}')
    facing_blocks = sprite.num_frames in (3, 5, 6)
    total = sub.field1 * sub.bpp
    return dict(source_format=sprite.num_frames, source_field1=sub.field1,
                source_field2=sub.bpp, frames=total,
                frames_per_facing=sub.field1 if facing_blocks else total,
                facings=sub.bpp if facing_blocks else 1,
                layout_kind='facing_blocks' if facing_blocks else 'sequence')


def atlas_grid(width, height, total):
    if min(width, height, total) <= 0:
        raise ValueError('Atlas dimensions/count must be positive')
    columns = min(total, MAX_ATLAS_SIZE // width)
    if not columns or math.ceil(total / columns) * height > MAX_ATLAS_SIZE:
        raise ValueError(f'Atlas exceeds {MAX_ATLAS_SIZE}: {width}x{height} x {total}')
    return columns, math.ceil(total / columns)


def decode_source_frames(sprite, sub, archive):
    expected = source_layout(sprite, sub)['frames']
    start = 24 + sub.data_offset
    if start < 24 or start + sub.data_size > len(archive):
        raise ValueError(f'Payload outside archive: {sprite.name}/{sub.name}')
    # All 2,920 canonical records have frame tables, even 1x1 transparent
    # placeholders. Compressed size can coincidentally equal raw image size.
    mask = sub.name.lower() in ('shadow', 'pick')
    table = decoder.find_animated_frame_table(archive, 24, sub, expected)
    if table is None:
        raise ValueError(f'No count-qualified source table: {sprite.name}/{sub.name}')
    # 00408120 shadow drawing and 00413D90 pick testing consume the same
    # signed occupancy spans. Neither reconstructs/interpolates missing rows.
    native_mask = sprite.num_frames == 5 and sub.name.lower() in ('shadow', 'pick')
    frames = (decoder.decode_native_shadow_frames(archive, 24, sub, expected)
              if native_mask else decoder.decode_animated_sprite(archive, 24, sub, mask, expected_count=expected))
    if frames and mask and not native_mask:
        decoder.fill_mask_frames(frames, sub.width, sub.height)
    if frames is None or len(frames) != expected:
        raise ValueError(f'{sprite.name}/{sub.name}: source declares {expected} frames; '
                         f'decoder returned {len(frames) if frames is not None else None}')
    if any(len(frame) != sub.width * sub.height for frame in frames):
        raise ValueError(f'Incomplete pixel buffer: {sprite.name}/{sub.name}')
    return frames, False


def rgba_frames(sprite, sub, archive):
    frames, raw = decode_source_frames(sprite, sub, archive)
    lut = decoder.make_rgba_lut(sprite, sub.name, uncompressed=raw)
    for pixels in frames:
        yield decoder.image_from_indexed_pixels(pixels, sub.width, sub.height, lut, Image)


def pack_frames(frames, width, height, total):
    columns, rows = atlas_grid(width, height, total)
    sheet = Image.new('RGBA', (width * columns, height * rows))
    digest = hashlib.sha256()
    count = 0
    for index, image in enumerate(frames):
        if index >= total or image.size != (width, height):
            raise ValueError(f'Unexpected frame count/geometry at frame {index}')
        rgba = image.convert('RGBA')
        digest.update(rgba.tobytes())
        sheet.paste(rgba, ((index % columns) * width, (index // columns) * height))
        count += 1
    if count != total:
        raise ValueError(f'Source requires {total} frames; got {count}')
    return sheet, columns, rows, digest.hexdigest()


def pack_pages(frames, width, height, total):
    capacity = (MAX_ATLAS_SIZE // width) * (MAX_ATLAS_SIZE // height)
    if not capacity:
        raise ValueError(f'Frame exceeds atlas limit: {width}x{height}')
    iterator = iter(frames)
    start = 0
    while start < total:
        count = min(capacity, total - start)
        sheet, columns, rows, digest = pack_frames(itertools.islice(iterator, count), width, height, count)
        yield sheet, dict(start_frame=start, frames=count, columns=columns, rows=rows, rgba_sha256=digest)
        start += count
    if next(iterator, None) is not None:
        raise ValueError(f'More than the declared {total} frames')

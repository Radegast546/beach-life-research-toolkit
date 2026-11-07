#!/usr/bin/env python3
"""Decode the original water-animation masks into Bevy texture atlases."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from PIL import Image
from project_paths import get_project_paths

_DEFAULT_PATHS = get_project_paths()
REPO_ROOT = _DEFAULT_PATHS.repo_root
ORIGINAL_GAME_DIR = _DEFAULT_PATHS.original_game_dir
DEFAULT_OUTPUT_DIR = _DEFAULT_PATHS.wateranim_assets_dir

FRAME_COUNT = 15
FRAME_SIZE = 256
QUADRANT_SIZE = 128
QUADRANT_PIXEL_COUNT = QUADRANT_SIZE * QUADRANT_SIZE
DECODED_PIXEL_COUNT = FRAME_SIZE * FRAME_SIZE
ATLAS_GRID_SIZE = 4
HEADER_STRUCT = struct.Struct(f"<I{FRAME_COUNT}I{FRAME_COUNT}I")
HEADER_SIZE = HEADER_STRUCT.size


def parse_wateranim_header(file_data: bytes) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Validate a water BIN header and return payload-relative frame spans."""
    if len(file_data) < HEADER_SIZE:
        raise ValueError(
            f"water animation is {len(file_data)} bytes; expected at least "
            f"{HEADER_SIZE} bytes for the header"
        )

    header_values = HEADER_STRUCT.unpack_from(file_data)
    payload_size = header_values[0]
    offsets = header_values[1 : 1 + FRAME_COUNT]
    sizes = header_values[1 + FRAME_COUNT :]
    actual_payload_size = len(file_data) - HEADER_SIZE
    if payload_size != actual_payload_size:
        raise ValueError(
            f"header payload size is {payload_size} bytes; file contains "
            f"{actual_payload_size} payload bytes"
        )
    frame_size_total = sum(sizes)
    if frame_size_total != payload_size:
        raise ValueError(
            f"frame sizes total {frame_size_total} bytes; expected the full "
            f"{payload_size}-byte payload"
        )

    spans = []
    for frame_index, (offset, size) in enumerate(zip(offsets, sizes)):
        if size == 0:
            raise ValueError(f"frame {frame_index} has an empty compressed payload")
        if offset > payload_size or size > payload_size - offset:
            raise ValueError(
                f"frame {frame_index} span offset={offset}, size={size} exceeds "
                f"the {payload_size}-byte payload"
            )
        spans.append((offset, offset + size, frame_index))

    previous_end = 0
    previous_frame = None
    for offset, end, frame_index in sorted(spans):
        if previous_frame is not None and offset < previous_end:
            raise ValueError(
                f"frame {frame_index} payload overlaps frame {previous_frame}"
            )
        previous_end = end
        previous_frame = frame_index

    return offsets, sizes


def decode_rle_frame(frame_data: bytes) -> bytes:
    """Decode one signed-byte RLE frame into its 65,536-pixel quadrant stream."""
    decoded = bytearray()
    for command_index, encoded_command in enumerate(frame_data):
        command = encoded_command if encoded_command < 128 else encoded_command - 256
        if command == 0:
            continue

        run_length = abs(command)
        next_length = len(decoded) + run_length
        if next_length > DECODED_PIXEL_COUNT:
            raise ValueError(
                f"decoded pixel count exceeds {DECODED_PIXEL_COUNT} at "
                f"command {command_index}"
            )
        decoded.extend(bytes((255 if command > 0 else 0,)) * run_length)

    if len(decoded) != DECODED_PIXEL_COUNT:
        raise ValueError(
            f"decoded pixel count is {len(decoded)}; expected {DECODED_PIXEL_COUNT}"
        )
    return bytes(decoded)


def rearrange_quadrant_stream(decoded_pixels: bytes) -> bytes:
    """Convert contiguous TL/TR/BL/BR blocks to row-major 256x256 pixels."""
    if len(decoded_pixels) != DECODED_PIXEL_COUNT:
        raise ValueError(
            f"decoded frame has {len(decoded_pixels)} pixels; "
            f"expected {DECODED_PIXEL_COUNT}"
        )

    row_major = bytearray(DECODED_PIXEL_COUNT)
    quadrant_origins = (
        (0, 0),
        (QUADRANT_SIZE, 0),
        (0, QUADRANT_SIZE),
        (QUADRANT_SIZE, QUADRANT_SIZE),
    )
    for quadrant_index, (destination_x, destination_y) in enumerate(quadrant_origins):
        quadrant_start = quadrant_index * QUADRANT_PIXEL_COUNT
        for local_y in range(QUADRANT_SIZE):
            source_start = quadrant_start + local_y * QUADRANT_SIZE
            destination_start = (
                (destination_y + local_y) * FRAME_SIZE + destination_x
            )
            row_major[
                destination_start : destination_start + QUADRANT_SIZE
            ] = decoded_pixels[source_start : source_start + QUADRANT_SIZE]

    return bytes(row_major)


def build_frame_image(decoded_pixels: bytes) -> Image.Image:
    """Build a white RGBA frame whose alpha comes from a quadrant-order stream."""
    row_major_alpha = rearrange_quadrant_stream(decoded_pixels)
    alpha = Image.frombytes("L", (FRAME_SIZE, FRAME_SIZE), row_major_alpha)
    frame = Image.new("RGBA", (FRAME_SIZE, FRAME_SIZE), (255, 255, 255, 255))
    frame.putalpha(alpha)
    return frame


def decode_wateranim_frames(file_data: bytes) -> list[Image.Image]:
    """Validate and decode all 15 frames in one water-animation BIN."""
    offsets, sizes = parse_wateranim_header(file_data)
    payload = memoryview(file_data)[HEADER_SIZE:]
    frames = []
    for frame_index, (offset, size) in enumerate(zip(offsets, sizes)):
        try:
            decoded_pixels = decode_rle_frame(payload[offset : offset + size].tobytes())
        except ValueError as error:
            raise ValueError(f"frame {frame_index}: {error}") from error
        frames.append(build_frame_image(decoded_pixels))
    return frames


def build_spritesheet(frames: list[Image.Image]) -> Image.Image:
    """Arrange exactly 15 frames in a 4x4 atlas, leaving slot 16 transparent."""
    if len(frames) != FRAME_COUNT:
        raise ValueError(f"expected {FRAME_COUNT} frames; received {len(frames)}")

    atlas_size = FRAME_SIZE * ATLAS_GRID_SIZE
    spritesheet = Image.new("RGBA", (atlas_size, atlas_size), (255, 255, 255, 0))
    for frame_index, frame in enumerate(frames):
        if frame.size != (FRAME_SIZE, FRAME_SIZE):
            raise ValueError(
                f"frame {frame_index} dimensions are {frame.size}; expected "
                f"{FRAME_SIZE}x{FRAME_SIZE}"
            )
        grid_x = (frame_index % ATLAS_GRID_SIZE) * FRAME_SIZE
        grid_y = (frame_index // ATLAS_GRID_SIZE) * FRAME_SIZE
        spritesheet.paste(frame.convert("RGBA"), (grid_x, grid_y))
    return spritesheet


def extract_wateranim(
    file_idx: int,
    output_dir: Path | None = None,
    *,
    original_game_dir: Path | None = None,
) -> Path:
    """Decode one numbered original BIN and save its PNG texture atlas."""
    if file_idx not in range(1, 5):
        raise ValueError(f"unsupported water animation index: {file_idx}")

    paths = get_project_paths()
    source_root = Path(
        original_game_dir
        if original_game_dir is not None
        else paths.original_game_dir
    )
    source_path = source_root / "Data" / "WaterAnims" / f"wateranim{file_idx}.bin"
    spritesheet = build_spritesheet(decode_wateranim_frames(source_path.read_bytes()))

    output_directory = Path(
        output_dir if output_dir is not None else paths.wateranim_assets_dir
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / f"wateranim{file_idx}_spritesheet.png"
    spritesheet.save(output_path)
    print(f"Saved {output_path}")
    return output_path


def main(argv: list[str] | None = None) -> int:
    paths = get_project_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help=f"output directory (default: {paths.wateranim_assets_dir})",
    )
    parser.add_argument(
        "--original-game-dir",
        type=Path,
        default=None,
        help=f"original game install directory (default: {paths.original_game_dir})",
    )
    args = parser.parse_args(argv)
    output_dir = (
        args.output_dir
        if args.output_dir is not None
        else paths.wateranim_assets_dir
    )
    original_game_dir = (
        args.original_game_dir
        if args.original_game_dir is not None
        else paths.original_game_dir
    )

    for file_idx in range(1, 5):
        extract_wateranim(
            file_idx,
            output_dir,
            original_game_dir=original_game_dir,
        )
    print("All animations extracted successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

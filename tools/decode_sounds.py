#!/usr/bin/env python3
"""
Beach Life Sound Extractor (blsnd.hdr + blsnd.spf)

File format (reverse-engineered):

blsnd.hdr:
  Array of 40-byte records, no header:
    - u32: offset into .spf file (absolute byte offset)
    - u32: size in bytes
    - 32 bytes: WAV filename (null-padded ASCII)

blsnd.spf:
  Concatenated raw WAV file data. Each sound is a complete WAV file
  (RIFF header + PCM data), packed sequentially.

Usage:
    python decode_sounds.py list <hdr_path>                    - List all sounds
    python decode_sounds.py extract <hdr_path> <spf_path> <out_dir> - Extract all WAV files
    python decode_sounds.py extract_one <hdr> <spf> <name> [out]    - Extract a single sound
"""

import struct
import sys
import os


RECORD_SIZE = 40
NAME_SIZE = 32


def parse_hdr(hdr_path):
    """Parse the blsnd.hdr file and return list of (name, offset, size)."""
    with open(hdr_path, 'rb') as f:
        data = f.read()

    num_records = len(data) // RECORD_SIZE
    records = []

    for i in range(num_records):
        base = i * RECORD_SIZE
        offset, size = struct.unpack_from('<II', data, base)
        name_bytes = data[base + 8:base + 8 + NAME_SIZE]
        # Find null terminator
        null_pos = name_bytes.find(b'\x00')
        if null_pos >= 0:
            name = name_bytes[:null_pos].decode('ascii', errors='replace')
        else:
            name = name_bytes.decode('ascii', errors='replace')
        records.append((name, offset, size))

    return records


def cmd_list(hdr_path):
    """List all sounds with offset and size."""
    records = parse_hdr(hdr_path)
    print(f"{'#':>4s}  {'Name':32s}  {'Offset':>10s}  {'Size':>10s}  {'Duration ~':>10s}")
    print('-' * 75)

    total_size = 0
    for i, (name, offset, size) in enumerate(records):
        # Approximate duration assuming 22050 Hz, 16-bit mono
        duration_s = (size - 44) / (22050 * 2) if size > 44 else 0
        print(f"{i:4d}  {name:32s}  {offset:10d}  {size:10d}  {duration_s:8.2f}s")
        total_size += size

    print(f"\nTotal: {len(records)} sounds, {total_size / 1024 / 1024:.1f} MB")


def cmd_extract(hdr_path, spf_path, output_dir):
    """Extract all WAV files."""
    records = parse_hdr(hdr_path)
    os.makedirs(output_dir, exist_ok=True)

    with open(spf_path, 'rb') as spf:
        for i, (name, offset, size) in enumerate(records):
            if not name or size == 0:
                continue

            spf.seek(offset)
            wav_data = spf.read(size)

            # Ensure .wav extension
            if not name.lower().endswith('.wav'):
                name += '.wav'

            out_path = os.path.join(output_dir, name)
            with open(out_path, 'wb') as f:
                f.write(wav_data)

            print(f"  [{i:3d}] {name} ({size} bytes)")

    print(f"\nExtracted {len(records)} sounds to {output_dir}")


def cmd_extract_one(hdr_path, spf_path, target_name, output_path=None):
    """Extract a single sound by name."""
    records = parse_hdr(hdr_path)
    target_lower = target_name.lower()

    for name, offset, size in records:
        if target_lower in name.lower():
            with open(spf_path, 'rb') as spf:
                spf.seek(offset)
                wav_data = spf.read(size)

            if output_path is None:
                output_path = name if name.lower().endswith('.wav') else name + '.wav'

            with open(output_path, 'wb') as f:
                f.write(wav_data)

            print(f"Extracted: {name} -> {output_path} ({size} bytes)")
            return

    print(f"Sound '{target_name}' not found.")
    # Show suggestions
    matches = [n for n, _, _ in records if target_lower[:4] in n.lower()]
    if matches:
        print(f"Did you mean: {', '.join(matches[:5])}")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == 'list':
        cmd_list(sys.argv[2])
    elif cmd == 'extract':
        if len(sys.argv) < 5:
            print("Usage: decode_sounds.py extract <hdr> <spf> <output_dir>")
            sys.exit(1)
        cmd_extract(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == 'extract_one':
        if len(sys.argv) < 5:
            print("Usage: decode_sounds.py extract_one <hdr> <spf> <name> [output]")
            sys.exit(1)
        out = sys.argv[5] if len(sys.argv) > 5 else None
        cmd_extract_one(sys.argv[2], sys.argv[3], sys.argv[4], out)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

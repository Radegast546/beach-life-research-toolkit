#!/usr/bin/env python3
"""
Beach Life .ble File Decoder/Encoder

The .ble format used by Beach Life (2002) is simply every byte XOR'd with 0xFF.
Text files (text_uk.ble etc.) use the same XOR but contain UTF-16LE encoded text
with a 2-byte header.

Usage:
    python decode_ble.py decode <input.ble> [output.txt]     - Decode a single file
    python decode_ble.py encode <input.txt> [output.ble]     - Encode back to .ble
    python decode_ble.py batch <directory> [output_dir]      - Decode all .ble files
    python decode_ble.py list <directory>                    - List all .ble files with preview
"""

import sys
import os
import glob


def xor_bytes(data: bytes) -> bytes:
    """XOR every byte with 0xFF (bitwise NOT)."""
    return bytes(b ^ 0xFF for b in data)


def is_utf16le(data: bytes) -> bool:
    """Detect if decoded data is UTF-16LE (text localization files)."""
    if len(data) < 4:
        return False
    # text_uk.ble: after XOR, starts with bytes that decode as UTF-16LE
    # Check for BOM or null-byte pattern typical of UTF-16LE ASCII text
    # The decoded first 2 bytes are a header (0xFF, 0x00 after XOR = original 0x00, 0xFF)
    # If every other byte is 0x00 in the first ~100 bytes, it's UTF-16LE.
    sample = data[2:min(102, len(data))]
    if len(sample) < 4:
        return False
    null_count = sum(1 for i in range(1, len(sample), 2) if sample[i] == 0)
    return null_count > len(sample) // 4


def decode_file(input_path: str, output_path: str | None = None) -> str:
    """Decode a .ble file to readable text."""
    with open(input_path, 'rb') as f:
        data = f.read()

    decoded = xor_bytes(data)

    if is_utf16le(decoded):
        # Skip 2-byte header, decode as UTF-16LE
        text = decoded[2:].decode('utf-16-le', errors='replace')
        encoding_used = 'utf-16le'
    else:
        text = decoded.decode('cp1252', errors='replace')
        encoding_used = 'cp1252'

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"  Decoded: {input_path} -> {output_path} ({encoding_used}, {len(data)} bytes)")
    
    return text


def encode_file(
    input_path: str, output_path: str | None = None, force_utf16: bool = False
) -> None:
    """Encode a text file back to .ble format."""
    with open(input_path, 'r', encoding='utf-8') as f:
        text = f.read()

    if force_utf16 or 'text_' in os.path.basename(input_path).lower():
        # UTF-16LE with 2-byte header
        header = bytes([0xFF, 0x00])  # After XOR becomes 0x00, 0xFF
        raw = header + text.encode('utf-16-le')
    else:
        raw = text.encode('cp1252', errors='replace')

    encoded = xor_bytes(raw)

    if output_path is None:
        output_path = input_path.rsplit('.', 1)[0] + '.ble'

    with open(output_path, 'wb') as f:
        f.write(encoded)
    print(f"  Encoded: {input_path} -> {output_path} ({len(encoded)} bytes)")


def batch_decode(directory: str, output_dir: str | None = None) -> None:
    """Decode all .ble files in a directory tree."""
    if output_dir is None:
        output_dir = os.path.join(directory, '_decoded')

    ble_files = glob.glob(os.path.join(directory, '**', '*.ble'), recursive=True)
    print(f"Found {len(ble_files)} .ble files in {directory}\n")

    for ble_path in sorted(ble_files):
        rel_path = os.path.relpath(ble_path, directory)
        out_path = os.path.join(output_dir, rel_path.replace('.ble', '.txt'))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        try:
            decode_file(ble_path, out_path)
        except Exception as e:
            print(f"  ERROR: {ble_path}: {e}")


def list_files(directory: str) -> None:
    """List all .ble files with a content preview."""
    ble_files = glob.glob(os.path.join(directory, '**', '*.ble'), recursive=True)
    print(f"Found {len(ble_files)} .ble files:\n")

    for ble_path in sorted(ble_files):
        rel_path = os.path.relpath(ble_path, directory)
        size = os.path.getsize(ble_path)
        try:
            text = decode_file(ble_path)
            preview = text.strip()[:80].replace('\n', ' ').replace('\r', '')
        except Exception:
            preview = "<decode error>"
        print(f"  {rel_path:50s} {size:>8d} bytes  {preview}")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == 'decode':
        out = sys.argv[3] if len(sys.argv) > 3 else sys.argv[2].replace('.ble', '.txt')
        decode_file(sys.argv[2], out)

    elif cmd == 'encode':
        out = sys.argv[3] if len(sys.argv) > 3 else None
        encode_file(sys.argv[2], out)

    elif cmd == 'batch':
        out_dir = sys.argv[3] if len(sys.argv) > 3 else None
        batch_decode(sys.argv[2], out_dir)

    elif cmd == 'list':
        list_files(sys.argv[2])

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

#!/usr/bin/env python3
"""Explicit-path, read-only extraction entrypoint for the research toolkit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'tools'))
import decode_ble
import decode_sounds
import decode_sprites
import lzo_beachlife


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return {'size': path.stat().st_size, 'sha256': result.hexdigest()}


def inventory(root):
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('game directory must be a directory')
    files = {}
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        if not path.resolve().is_relative_to(root):
            raise ValueError('input contains a file link outside the game directory')
        key = path.relative_to(root).as_posix().lower()
        if key in files:
            raise ValueError(f'case-insensitive input collision: {key}')
        files[key] = path
    if not any(key.startswith('data/') for key in files):
        raise ValueError('game directory must contain Data with installed game files')
    return files


def unique(files, basename):
    matches = [p for k, p in files.items() if k.rsplit('/', 1)[-1] == basename.lower()]
    if len(matches) != 1:
        raise ValueError(f'expected one {basename}, found {len(matches)}')
    return matches[0]


def safe_name(name):
    win = PureWindowsPath(name)
    if not name or win.drive or win.root or len(win.parts) != 1 or name in ('.', '..'):
        raise ValueError(f'unsafe archive filename: {name!r}')
    if any(c in name for c in '/\\:<>"|?*') or name.endswith((' ', '.')):
        raise ValueError(f'unsafe archive filename: {name!r}')
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                                    *(f'COM{i}' for i in range(1, 10)),
                                    *(f'LPT{i}' for i in range(1, 10))}:
        raise ValueError(f'reserved archive filename: {name!r}')
    return name


def sound_records(header, bank):
    if header.stat().st_size % decode_sounds.RECORD_SIZE:
        raise ValueError('sound header has an incomplete record')
    records = decode_sounds.parse_hdr(str(header))
    names = set()
    for name, offset, size in records:
        if not name or not size:
            continue
        safe_name(name)
        name = name if name.lower().endswith('.wav') else name + '.wav'
        if name.lower() in names:
            raise ValueError(f'duplicate sound filename: {name}')
        names.add(name.lower())
        if offset + size > bank.stat().st_size:
            raise ValueError(f'sound outside bank: {name}')
        yield name, offset, size


def biz_chunks(path):
    data = path.read_bytes()
    if len(data) < 8192:
        raise ValueError('BIZ header is truncated')
    offsets = struct.unpack_from('<1024I', data)
    sizes = struct.unpack_from('<1024I', data, 4096)
    for index, (offset, size) in enumerate(zip(offsets, sizes)):
        if not size:
            continue
        if offset < 8192 or offset + size > len(data):
            raise ValueError(f'BIZ chunk {index}: invalid compressed span')
        decoded = lzo_beachlife.decompress_biz_chunk(data[offset:offset + size])
        if len(decoded) != 65536:
            raise ValueError(f'BIZ chunk {index}: expected 65536 bytes, got {len(decoded)}')
        yield index, decoded


def extract(game, output, *, sprites=(), maps=False, water=False):
    game = game.resolve(strict=True)
    output = output.resolve()
    toolkit = Path(__file__).resolve().parent
    if output.exists():
        raise ValueError('output directory must not exist')
    for source in (game, toolkit):
        if output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError('output must be separate from game and toolkit directories')
    files = inventory(game)
    ble = [p for k, p in files.items() if k.startswith('data/') and k.endswith('.ble')]
    if not ble:
        raise ValueError('no BLE files found under Data')
    header = unique(files, 'blsnd.hdr')
    bank = unique(files, 'blsnd.spf')
    sounds = list(sound_records(header, bank))
    selected = list(ble) + [header, bank]
    map_files = [p for k, p in files.items() if k.startswith('data/') and k.endswith('.biz')] if maps else []
    if maps and not map_files:
        raise ValueError('no BIZ files found')
    selected.extend(map_files)
    if sprites:
        sprite_header = unique(files, 'blsprite.hdr')
        sprite_bank = unique(files, 'blsprite.dat')
        selected.extend((sprite_header, sprite_bank))
        _, _, parents = decode_sprites.parse_hdr(str(sprite_header))
        available = {p.name.lower() for p in parents}
        for name in sprites:
            safe_name(name)
            if name.lower() not in available:
                raise ValueError(f'sprite not found: {name}')
    if water:
        selected.extend(unique(files, f'wateranim{i}.bin') for i in range(1, 5))
    before = {p.relative_to(game).as_posix(): digest(p) for p in selected}
    output.mkdir(parents=True)
    for source in ble:
        target = output / 'scripts' / source.relative_to(game).with_suffix('.txt')
        target.parent.mkdir(parents=True, exist_ok=True)
        decode_ble.decode_file(str(source), str(target))
    (output / 'sounds').mkdir()
    with bank.open('rb') as stream:
        for name, offset, size in sounds:
            stream.seek(offset)
            payload = stream.read(size)
            if len(payload) != size:
                raise ValueError(f'truncated sound: {name}')
            (output / 'sounds' / name).write_bytes(payload)
    for source in map_files:
        target = output / 'maps' / source.relative_to(game)
        target.mkdir(parents=True)
        for index, decoded in biz_chunks(source):
            (target / f'chunk_{index:04d}.bin').write_bytes(decoded)
    for name in sprites:
        decode_sprites.cmd_extract(str(sprite_header), str(sprite_bank), str(output / 'sprites'), name)
    if water:
        import extract_wateranims
        for index in range(1, 5):
            # Decode explicit discovered files rather than edition/case-sensitive defaults.
            source = unique(files, f'wateranim{index}.bin')
            frames = extract_wateranims.decode_wateranim_frames(source.read_bytes())
            target = output / 'water'
            target.mkdir(exist_ok=True)
            extract_wateranims.build_spritesheet(frames).save(target / f'wateranim{index}.png')
    after = {p.relative_to(game).as_posix(): digest(p) for p in selected}
    if before != after:
        raise ValueError('source hashes changed during extraction')
    products = {p.relative_to(output).as_posix(): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}
    report = {'schema': 1, 'inputs': before, 'inputs_unchanged': True,
              'options': {'sprites': list(sprites), 'maps': maps, 'water': water}, 'outputs': products}
    (output / 'extraction.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('inventory', 'extract'):
        child = sub.add_parser(name)
        child.add_argument('--game-dir', required=True, type=Path)
        if name == 'extract':
            child.add_argument('--output', required=True, type=Path)
            child.add_argument('--sprite', action='append', default=[])
            child.add_argument('--maps', action='store_true')
            child.add_argument('--water', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'inventory':
            files = inventory(args.game_dir)
            for key, path in files.items():
                if path.suffix.lower() in ('.ble', '.biz', '.hdr', '.spf', '.bin'):
                    print(f'{path.stat().st_size:12d} {key}')
        else:
            result = extract(args.game_dir, args.output, sprites=args.sprite, maps=args.maps, water=args.water)
            print(f"Extracted {len(result['outputs'])} files; source hashes unchanged.")
        return 0
    except (OSError, ValueError, struct.error) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
import argparse
import hashlib
import os
from pathlib import Path, PureWindowsPath
import struct
import zlib


FILE_OBFUSCATED = 2
FILE_COMPRESSED = 4
LINK_PREV = 1


def u16(buf, off):
    return struct.unpack_from("<H", buf, off)[0]


def u32(buf, off):
    return struct.unpack_from("<I", buf, off)[0]


def u64(buf, off):
    return struct.unpack_from("<Q", buf, off)[0]


def cstr(buf, off):
    end = buf.index(0, off)
    return buf[off:end].decode("latin-1")


def ror8(value, shift):
    return ((value >> shift) | ((value << (8 - shift)) & 0xFF)) & 0xFF


def deobfuscate(data, seed):
    out = bytearray(data)
    for i, value in enumerate(out):
        out[i] = (ror8(value ^ 0xD5, 2) - ((seed + i) % 0x47)) & 0xFF
    return bytes(out), seed + len(out)


class CabinetReader:
    def __init__(self, base, descriptor):
        self.base = base
        self.descriptor = descriptor
        self.seed = 0
        self.file = None

    def open(self):
        cab = self.base / f"data{self.descriptor['volume']}.cab"
        if not cab.exists():
            cab = self.base / f"DATA{self.descriptor['volume']}.CAB"
        self.file = cab.open("rb")
        self.file.seek(self.descriptor["data_offset"])

    def read(self, size):
        data = self.file.read(size)
        if len(data) != size:
            raise EOFError(f"short read for {self.descriptor['path']}")
        if self.descriptor["flags"] & FILE_OBFUSCATED:
            data, self.seed = deobfuscate(data, self.seed)
        return data

    def close(self):
        if self.file:
            self.file.close()


class InstallShieldCabinet:
    def __init__(self, hdr_path):
        self.hdr_path = Path(hdr_path)
        self.base = self.hdr_path.parent
        self.header = self.hdr_path.read_bytes()
        self.directories = []
        self.files = []
        self._parse()

    def _parse(self):
        buf = self.header
        if u32(buf, 0) != 0x28635349:
            raise ValueError("not an InstallShield cabinet header")

        version = u32(buf, 4)
        major = (version >> 12) & 0xF
        if major != 6:
            raise ValueError(f"expected InstallShield major version 6, got {major}")

        desc_off = u32(buf, 12)
        desc = desc_off
        file_table_offset = u32(buf, desc + 0x0C)
        directory_count = u32(buf, desc + 0x1C)
        file_count = u32(buf, desc + 0x28)
        file_table_offset2 = u32(buf, desc + 0x2C)
        table_base = desc + file_table_offset

        offsets = [u32(buf, table_base + i * 4) for i in range(directory_count + file_count)]
        self.directories = [cstr(buf, table_base + offsets[i]) for i in range(directory_count)]

        descriptor_base = table_base + file_table_offset2
        for index in range(file_count):
            off = descriptor_base + index * 0x57
            flags = u16(buf, off)
            expanded = u64(buf, off + 0x02)
            compressed = u64(buf, off + 0x0A)
            data_offset = u64(buf, off + 0x12)
            md5 = buf[off + 0x1A:off + 0x2A]
            name_offset = u32(buf, off + 0x3A)
            directory_index = u16(buf, off + 0x3E)
            link_previous = u32(buf, off + 0x4C)
            link_next = u32(buf, off + 0x50)
            link_flags = buf[off + 0x54]
            volume = u16(buf, off + 0x55)

            name = cstr(buf, table_base + name_offset) if name_offset else ""
            directory = self.directories[directory_index] if directory_index < len(self.directories) else ""
            rel_path = Path(directory) / name if directory else Path(name)
            self.files.append({
                "index": index,
                "name": name,
                "directory": directory,
                "path": str(rel_path),
                "flags": flags,
                "expanded": expanded,
                "compressed": compressed,
                "data_offset": data_offset,
                "md5": md5,
                "volume": volume,
                "link_previous": link_previous,
                "link_next": link_next,
                "link_flags": link_flags,
            })

    def extract_one(self, descriptor):
        if descriptor["link_flags"] & LINK_PREV:
            return self.extract_one(self.files[descriptor["link_previous"]])
        if not descriptor["data_offset"]:
            raise ValueError(f"{descriptor['path']}: external file is not stored in the cabinet")

        reader = CabinetReader(self.base, descriptor)
        reader.open()
        try:
            if descriptor["flags"] & FILE_COMPRESSED:
                left = descriptor["compressed"]
                chunks = []
                while left > 0:
                    chunk_size = u16(reader.read(2), 0)
                    if chunk_size == 0:
                        raise ValueError(f"zero compressed chunk in {descriptor['path']}")
                    chunk = reader.read(chunk_size)
                    left -= 2 + chunk_size
                    try:
                        chunks.append(zlib.decompress(chunk, -zlib.MAX_WBITS))
                    except zlib.error:
                        chunks.append(zlib.decompress(chunk + b"\0", -zlib.MAX_WBITS))
                data = b"".join(chunks)
            else:
                data = reader.read(descriptor["expanded"])
        finally:
            reader.close()

        if len(data) != descriptor["expanded"]:
            raise ValueError(f"{descriptor['path']}: expected {descriptor['expanded']} bytes, got {len(data)}")
        if descriptor["md5"] != hashlib.md5(data).digest():
            raise ValueError(f"{descriptor['path']}: md5 mismatch")
        return data

    def list_files(self):
        return self.files

    def extract(self, output, names=None):
        output = Path(output).resolve()
        wanted = {name.lower().replace("/", "\\") for name in names} if names else None
        extracted = []
        planned = []
        targets = set()
        for descriptor in self.files:
            normalized = descriptor["path"].lower().replace("/", "\\")
            if wanted and normalized not in wanted and descriptor["name"].lower() not in wanted:
                continue
            relative = PureWindowsPath(descriptor["path"])
            if relative.drive or relative.root or '..' in relative.parts or not relative.parts:
                raise ValueError(f"unsafe cabinet path: {descriptor['path']!r}")
            reserved = {'CON', 'PRN', 'AUX', 'NUL',
                        *(f'COM{i}' for i in range(1, 10)),
                        *(f'LPT{i}' for i in range(1, 10))}
            if any(any(c in part for c in ':<>"|?*') or
                   part.split('.')[0].upper() in reserved or
                   part.endswith((' ', '.')) for part in relative.parts):
                raise ValueError(f"unsafe cabinet path: {descriptor['path']!r}")
            target = output.joinpath(*relative.parts).resolve()
            if not target.is_relative_to(output) or target == output:
                raise ValueError(f"cabinet path escapes output: {descriptor['path']!r}")
            key = str(target).casefold()
            if key in targets:
                raise ValueError(f"duplicate cabinet path: {descriptor['path']!r}")
            targets.add(key)
            planned.append((descriptor, target))
        if wanted and not planned:
            raise ValueError('no cabinet files matched the requested names')
        for descriptor, target in planned:
            data = self.extract_one(descriptor)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            extracted.append(target)
        return extracted


def main():
    parser = argparse.ArgumentParser(description="Extract InstallShield 6 data1.hdr/data*.cab payloads.")
    parser.add_argument("hdr", help="Path to data1.hdr")
    parser.add_argument("--list", action="store_true", help="List files")
    parser.add_argument("--out", help="Extraction directory")
    parser.add_argument("--name", action="append", default=[], help="File name or relative path to extract")
    parser.add_argument("--data-only", action="store_true",
                        help="extract nonempty Data/ payloads, excluding installer components and external files")
    args = parser.parse_args()

    cab = InstallShieldCabinet(args.hdr)
    if args.list:
        for item in cab.list_files():
            print(f"{item['index']:04d} vol={item['volume']} flags=0x{item['flags']:04x} "
                  f"expanded={item['expanded']} compressed={item['compressed']} {item['path']}")
    if args.out:
        if args.data_only and args.name:
            parser.error('--data-only and --name are mutually exclusive')
        names = args.name or None
        if args.data_only:
            names = [item['path'] for item in cab.files
                     if PureWindowsPath(item['path']).parts and
                     PureWindowsPath(item['path']).parts[0].lower() == 'data'
                     and item['expanded'] and item['data_offset']]
            if not names:
                parser.error('no stored Data/ payloads found')
        for path in cab.extract(args.out, names):
            print(path)


if __name__ == "__main__":
    main()

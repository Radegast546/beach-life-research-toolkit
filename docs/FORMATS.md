# Recovered formats

These conclusions summarize the upstream extraction, sprite audit, terrain,
water and audio notes. No proprietary source records are bundled.

| Input | Structure and interpretation |
| --- | --- |
| `.ble` | Every byte XOR 0xFF. Most scripts decode as Windows-1252; localization uses UTF-16LE with a two-byte prefix. Text detection remains heuristic. |
| `BLSprite.hdr` | 20-byte timestamp, two u32 fields, then named parent/subimage records and palettes. Parent format controls layout/palette semantics. |
| `BLSprite.dat` | 24-byte archive header; source records reference payloads and count-qualified frame tables. Keep duplicate names as separate records. |
| `blsnd.hdr` | Headerless 40-byte records: u32 offset, u32 length, 32-byte NUL-padded sound name. |
| `blsnd.spf` | Concatenated RIFF/WAVE payloads; compression/encoding is inside each WAVE. |
| `.biz` | 1,024 little-endian u32 offsets followed by 1,024 u32 compressed lengths: 8,192-byte header, 32x32 spatial chunks. Custom LZO, not ordinary LZO1X or RLE16. |
| Decoded BIZ chunk | 65,536 bytes: 128x128 RGB565 u16 colors, then 128x128 u16 secondary words. Upper byte is screen depth; low-byte bit 0 excludes animated water. Other low bits remain incompletely interpreted. |
| `scenario*grid.dat` | Headerless 128x128 little-endian u32 flags; column-major index `x*128+y`, 65,536 bytes. Not a 128x512 byte grid. |
| Water BIN | u32 payload length, 15 u32 offsets and 15 u32 lengths, then RLE masks. Frames are 256x256, stored as four 128x128 quadrants. Export atlas is 4x4 with the last slot unused. |

Sprite formats 3/6 use 64-color palette banks with pixel-type blend weights;
other supported formats retain full palettes. Formats 3/5/6 expose facing blocks.
Source subimage fields declare total frames; names and compressed byte length
alone are insufficient to distinguish static images and animations. A source
table can encode even a one-frame image. See parser and synthetic tests for
field widths, frame bounds and native signed-run details.

Terrain screen depth is not vertical world height. Native height projection uses
a separate optional TGA descriptor. Preserve the entire secondary u16: native
packed terrain is `color | (secondary << 16)`, and low bits affect comparisons.

The custom LZO core is a research decoder that can return partial data on bad
input. The wrapper checks each declared compressed span and requires exactly
65,536 decoded bytes. This is not a general-purpose hardened archive library.

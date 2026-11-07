# Extraction recipes

Use separate output directories and keep originals unchanged. The `research.py`
wrapper requires explicit paths and rejects overlapping input/output roots;
legacy direct scripts may overwrite existing outputs and use workspace defaults.

## Original installation media

Mount your own disc image or copy its files to a private directory. ISO mounting
is outside this toolkit. The v6 extractor reads `data1.hdr` and adjacent
`dataN.cab` volumes without running the installer:

```console
python tools/extract_installshield_v6.py /media/disc/data1.hdr --list
python tools/extract_installshield_v6.py /media/disc/data1.hdr --data-only --out /private/new-install
```

`--data-only` selects the nonempty stored `Data/` files needed for research;
installer components and files stored outside the cabinets are excluded.
This is a focused InstallShield v6 implementation, not a general cabinet tool.
It checks expanded sizes and embedded MD5 values. Multi-volume split payloads,
external files and other installer versions may require additional recovery.
Locate the extracted directory containing `Data` and use it as `--game-dir`.

## Scripts and definitions

```console
python tools/decode_ble.py decode /game/Data/Script/BuildingList.ble /private/BuildingList.txt
python tools/extract_buildings.py --input /private/BuildingList.txt --output /private/buildings.ron
```

BLE text conversion is intended for reading; UTF-16 detection is heuristic and
replacement decoding can lose information. Preserve original bytes for research.
The encoder is not a promise of byte-exact text round trips.

## Sprites

```console
python tools/decode_sprites.py info /game/Data/Sprites/BLSprite.hdr
python tools/decode_sprites.py json /game/Data/Sprites/BLSprite.hdr /private/sprites.json
python tools/decode_sprites.py extract /game/Data/Sprites/BLSprite.hdr /game/Data/Sprites/BLSprite.dat /private/sprites grass08
```

Use `extract --help` for palette selection, layer filters and frame caps. A capped
export is deliberately incomplete. PNG alpha/blend representations and palette
repairs are diagnostic interpretations; the native renderer also needs packed
depth, blend rules and ordered composition. `num_frames` in legacy parser objects
is a format selector, not an animation length.

## Sound and water

```console
python tools/decode_sounds.py list /game/Data/Sounds/blsnd.hdr
python research.py extract --game-dir /game --output /private/new-extraction --water
```

Find the actual sound-bank location with `inventory`; installations can differ.
Extracted RIFF data can contain IMA ADPCM rather than PCM. Extraction does not
transcode it. The water option requires all four source BIN files.

## Output evidence

Successful wrapper runs write `extraction.json`: selected options, relative input
paths, source SHA-256/size, source preservation status, and hashes/sizes of output
files. Absolute machine paths are omitted. An error returns nonzero; a partial
output directory can remain for diagnosis and has no success manifest. Use a new
destination when retrying. Do not publish generated extraction directories.

# Prepared release checks

Preparation date: 2026-11-07. Published source:
[Radegast546/beach-life-research-toolkit](https://github.com/Radegast546/beach-life-research-toolkit).
MIT licensing selected by the project owner for original toolkit contributions.

## Clean-media extraction

Read-only copies of the owner's two ISO images were opened using a private
pycdlib installation (not a toolkit dependency). `data1.hdr`, `data1.cab` and
`data2.cab` were copied into separate disposable directories. The bundled v6
extractor unpacked every nonempty stored Data/ payload and verified its embedded
MD5. No installed-game cache supplied these inputs.

| Check | Beach Life | Spring Break |
| --- | --- | --- |
| ISO bytes | 686,936,064 | 662,630,400 |
| MD5-verified Data/ files | 187 | 188 |
| Decoded BLE text/script files | 55 | 55 |
| Extracted sounds | 302 | 302 |
| Selected grass08 sprite PNGs | 1 | 1 |
| Water atlases | 4 | 4 |
| Scenario 1 BIZ chunks, each 65,536 bytes | 1,024 | 1,024 |
| ISO and selected input hashes unchanged | yes | yes |

ISO SHA-256 identities:

- Beach Life: `60216d0fe111f40cb50714e9521b5f082643126a100cebb1679b02d8f15de84d`
- Spring Break: `ebeff00d01e8cf92841b990081a84a14c0895c5fa88a4401b216bef76683423b`

Concatenating Scenario 1's decoded chunks in source index order yields SHA-256
`8a834f7e46cf3e0e173c667d39dae2733f7bec05b0b2f01ba00abd03a5f95e69`
for both images. Full sprite-library export and every scenario's BIZ extraction
were not repeated for this release. No live game was launched.

## Source-only checks

The standalone exported bundle ran 21 tests successfully in a fresh venv with
Pillow 12.3.0 installed from requirements, under Windows with
Python 3.15.2; one optional original-archive-dependent test class was skipped.
Tests cover synthetic end-to-end script/sound extraction, source preservation,
output hashes, unsafe paths, malformed spans, a complete synthetic BIZ chunk,
water decoding, palette interpretation and building definitions. Windows/Linux
CI for Python 3.10 and 3.12 runs on both Windows and Linux; current results are
available in [GitHub Actions](https://github.com/Radegast546/beach-life-research-toolkit/actions).

The exported `--data-only` cabinet CLI and `research.py extract --sprite grass08
--water` CLI also passed against fresh Beach Life cabinet data, with 364 output
files and unchanged selected source hashes. The table above records both
editions' programmatic workflow checks using the exported modules.

The exporter uses an explicit file allowlist and creates a new source tree and
ZIP without upstream Git history. SOURCE_MANIFEST.json hashes every included
source/document/configuration file. No game binaries, assets, extraction outputs
or local workspace markers are included. This is an audit of the selected
distribution, not of the remake repository's historical Git objects.
`.gitattributes` preserves exact file bytes across Git checkouts so the source
manifest remains verifiable regardless of local line-ending preferences.

No full-game compatibility claim is made. Keep generated research output private.

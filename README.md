# Beach Life / Spring Break Research Toolkit

Reusable extraction tools and format findings for the 2002 game Beach Life,
also released as Spring Break. This is an early research release from an ongoing
Rust/Bevy reconstruction project. It contains no game assets and requires your
own installation or original installation media. It is an independent project.

## Quick start

Use Python 3.10 or newer. From this directory:

```console
python -m venv .venv
```

Activate `.venv` (`.venv\Scripts\Activate.ps1` in PowerShell,
`source .venv/bin/activate` on Linux/macOS), then:

```console
python -m pip install -r requirements.txt
python tools/run_tool_tests.py
python research.py inventory --game-dir /path/to/your/game
python research.py extract --game-dir /path/to/your/game --output /path/to/new/extraction
```

Replace the example paths with yours; quote paths containing spaces. `--game-dir`
is the directory containing `Data`, not `Data` itself. Input discovery is case
insensitive. The default extraction decodes BLE scripts/text and unpacks the
sound bank. Outputs are private research material, not covered by this repository's
license. The output directory must not exist and must be separate from the input
and toolkit source tree. Inputs are hashed before and after extraction.

Add any of these options to `extract`:

| Option | Output |
| --- | --- |
| `--sprite grass08` | All source-declared frames/layers for this sprite; repeat for more names |
| `--maps` | Raw 65,536-byte BIZ chunks, preserving both terrain planes |
| `--water` | Four water-animation PNG atlases |

Full sprite extraction can produce hundreds of thousands of files. Start with
one sprite. For direct commands and original-media extraction, see
[usage](docs/USAGE.md). Read [format findings](docs/FORMATS.md),
[research directions](docs/RESEARCH.md), and [validation](docs/VALIDATION.md)
before interpreting extracted images as native rendering or game behavior.

## What's included

- XOR-FF BLE text decoder/encoder, sprite HDR/DAT parser and frame exporter.
- Sound HDR/SPF extraction, custom BIZ LZO decoder and water BIN decoder.
- InstallShield v6 cabinet extractor and building-definition parser.
- Synthetic regression tests, a hash manifest for this source distribution,
  and CI that runs without proprietary inputs.

This release excludes the remake, generated catalogs, original executable code,
Ghidra databases, runtime hooks, compatibility binaries and private workspace
history. Native gameplay state-machine recovery remains ongoing upstream.

## Contributions

Report the edition, relevant input SHA-256, command, expected/actual result and
a minimal synthetic reproducer. Do not attach game files or extracted assets.
Document which facts came from bytes, native disassembly, controlled execution
or live observation. Keep unsupported interpretations explicit. See
[CONTRIBUTING.md](CONTRIBUTING.md).

Original toolkit code and documentation are MIT licensed; see [LICENSE](LICENSE).
Game data and third-party dependencies retain their own terms.

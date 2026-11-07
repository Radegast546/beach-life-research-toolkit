# Contributing

Run `python tools/run_tool_tests.py` before submitting changes. Ordinary tests
must work without original files. Construct small fixtures in test code rather
than copying source bytes, images, scripts or native instructions from the game.

Record evidence and unknowns alongside format changes. Executable addresses
need an edition and executable SHA-256; never assume another edition has the
same addresses. Do not submit game binaries, assets, decompilation dumps,
generated output, personal paths or local runtime configurations.

The initial release is exported from the remake workspace by an explicit file
allowlist. SOURCE_MANIFEST.json records each included file's SHA-256 and its
upstream relative path where applicable. It contains no upstream Git history.
Changes contributed here are under the MIT license.

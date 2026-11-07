# Validation scope

The release includes synthetic tests for water decoding, building definitions,
palette interpretation and the standalone wrapper's preservation/error guards.
Optional original-sprite tests skip when user-supplied archives are absent.
`python tools/run_tool_tests.py` needs no proprietary files for ordinary tests.

Upstream historical sprite validation covered 838 parents, 2,920 subimage records
and 584,564 declared frames. This establishes that corpus's inventory, not a
universal count for every edition and not native-renderer parity.

Reference sprite archive SHA-256:

- HDR: `377c8fda9b3287df20f91967141ea463330bc08ad3c08647762d7bb0fccbcaae`
- DAT: `461bf8257a1277466ac97e0f1d32d4fbe88c86e2c5b923c8ff6523664f6ee57b`

Fresh-media results for this prepared release are recorded in RELEASE_CHECKS.md.
Do not treat the upstream mixed working corpus as an untouched retail install.
Windows is the upstream development environment; the CI matrix proposes Windows
and Linux/Python 3.10 and 3.12 checks, which are not claimed to have run locally.

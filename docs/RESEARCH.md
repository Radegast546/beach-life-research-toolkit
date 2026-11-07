# Where to continue

Extraction removes the initial file-format barrier; it does not recover complete
gameplay or rendering. Useful next investigations include:

- Terrain low-byte bits beyond water exclusion, optional height rasters, native
  zoom sampling and ordered actor/scenery/shadow composition.
- Sprite state triggers, facing/temporal distinctions and special building
  drawing/audio callbacks. Do not infer animation timing from frame counts.
- Installer variants and edition-specific source identities.
- Native guest arrival, venue admission, transactions and full state dispatch;
  persistent worker/world scheduling and ownership transitions.

The upstream project has additional native-code findings and controlled execution
fixtures for power, guest needs and builder lifecycles. They are outside this
first extraction-focused distribution; their omission does not imply those
systems have not been investigated. Native harnesses need a separate dependency,
fixture-provenance and executable-version audit before distribution.

For each finding, record the precise question, input identity, offsets or native
address, method, observed result and remaining controlled dependencies. Build a
synthetic regression from the finding where possible. A PNG export, a native
function replay and a live gameplay observation support different conclusions.

Legacy executable reference: SHA-256
`983c098f69314c142ac8fd0d74fa34d098a49bd59f1aed88fb67a525c4b7f9e9`.
The upstream live visual reference later changed to Beach Life Remaster 1.0;
legacy addresses and findings must not silently be assigned to that executable
or to Spring Break. This toolkit does not hook or modify either executable.

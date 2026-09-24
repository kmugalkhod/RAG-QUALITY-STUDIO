# Reviewed structure-cleaning corpus baseline

Measured: 2026-09-24  
Profile: `structure-aware-v1` / engine `structure-clean-v1`  
Fixture: `backend/tests/fixtures/cleaning_corpus/manifest.json`

## Release result

The deterministic Phase 3 corpus passed the roadmap's reviewed boilerplate thresholds.

| Measure | Result | Release threshold |
| --- | ---: | ---: |
| Boilerplate removal precision | 100% (22/22 removed blocks were labelled noise) | at least 99% |
| Boilerplate removal recall | 100% (22/22 labelled noise blocks removed) | at least 90% |
| Reviewed useful/protected retention | 100% (16/16 blocks retained) | no reviewed body deletion |
| Deterministic rerun | 100% matching blocks and output hashes | 100% |

The PDF case contains five pages with repeated top-margin headers and bottom-margin
footers, five distinct body blocks and five protected footnotes. The three Website pages
contain repeated header, navigation, cookie-dialog and footer chrome plus unique main
headings and paragraphs. Expected removals and retentions are labelled independently of
the cleaner output. The default CI test constructs canonical blocks, runs the exact
saved profile and compares block identity membership; a useful or protected deletion
fails the test even if aggregate precision remains high.

Additional deterministic tests cover NFC and opt-in NFKC, unsupported controls,
paragraph reflow, positive and negative dehyphenation, short/long margin frequency,
empty and literal removal, protected table/list/code/quote/footnote behavior, bounded
selectors, semantic/main content, cross-page fingerprints, safe content bounds,
configuration order/hash stability and connector parity.

## Interpretation and limits

This is a small synthetic, legally safe release fixture, not a claim of universal
document or Website quality. It covers English repeated chrome, normalized PDF geometry
and inert server-parsed HTML; it does not measure JavaScript-rendered pages, visually
positioned HTML without semantic signals, arbitrary CSS, adversarial templates or every
language's hyphenation rules. NFKC remains opt-in because compatibility normalization
can change meaning. Conservative defaults intentionally prefer retaining uncertain text
over deleting useful content.

Any change to cleaner runtime, default profile, Website block extraction or positional
thresholds must rerun this reviewed test and add cases for newly supported patterns.
Changing expectations requires a human review of every added removed/retained label;
lower aggregate scores or unlabelled useful-text deletion block release.

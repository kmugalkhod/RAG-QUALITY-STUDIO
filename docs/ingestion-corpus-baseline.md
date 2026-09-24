# Phase 2 reviewed extraction corpus baseline

Measured on 2026-09-24 in the pinned backend container with PyMuPDF 1.28.2,
pypdf 6.18.0, Tesseract 5.5.0 and the Debian English trained-data package 4.1.0.
The source fixtures are small, deterministic, synthetic documents generated from the
reviewed expectations in
`backend/tests/fixtures/ingestion_corpus/manifest.json`; they contain no third-party
content or personal data.

| Measure | Result | Phase 2 gate |
| --- | ---: | ---: |
| Native normalized character preservation | 100.000% | at least 99.5% |
| OCR character error rate, median | 0.570% | at most 5% |
| OCR character error rate, p95 | 1.141% | at most 12% |
| Reviewed reading-order precedence pairs | 100.000% | at least 95% |
| Reviewed table cell/header association | 100.000% | at least 95% |
| Deterministic rerun | 100% | 100% |

The corpus covers a native PDF, an image-only scan, a mixed native/scan PDF, a
90-degree rotated scan, a two-column layout and a simple ruled table. The mixed file
reported one native and one OCR page with the exact page-level fallback path. The
rotated page reported a 90-degree clockwise correction. The measured run used automatic
deskew for scanned pages; the rotation fixture also exercises orientation detection.

Observed single-run extraction times in the local ARM64 Docker environment were 9 ms
for the native file, 237 ms for the ordinary scan, 578 ms for the rotated scan and
12 ms for the layout/table file. These are diagnostic samples, not throughput or
latency guarantees. Container scheduling and host load can change them.

Limits and caveats:

- The reviewed corpus is intentionally small and English-only. It validates the pinned
  release gate, not OCR accuracy for arbitrary languages, fonts or degraded scans.
- The supported table gate covers simple cells and headers. Merged or irregular tables
  are retained only when PyMuPDF supplies bounded rows; truncation or malformed output
  produces a quality finding instead of an accuracy claim.
- Page images, OCR output, layout blocks, table cells, time and page counts are bounded.
  Encrypted, malformed, timed-out and over-limit documents fail with safe codes.
- Parser dependency or language-pack changes require regenerating this report and an
  explicit review of structured differences before release.

Reproduce the release check from the repository root:

```sh
docker compose build backend
docker compose run --rm --no-deps backend pytest -q tests/test_layout_extraction.py
```

The default test suite skips the real-OCR corpus when Tesseract is not installed on a
developer host; the pinned backend container must run it and may not skip it.

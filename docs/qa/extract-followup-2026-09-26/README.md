# Extract and ingestion browser QA follow-up — 2026-09-26

The authoritative case ledger is [`../../extract-ingestion-qa-findings.csv`](../../extract-ingestion-qa-findings.csv). All new data was created in project `5a4a3af4-f2d3-43bc-ac4a-4b717c874054` (`Extract E2E QA 2026-09-26 1150`). The browser target was `http://127.0.0.1:5273`; backend, worker, dispatcher, PostgreSQL and Redis were reused. No developer data or Docker volumes were deleted, and the local artifact encryption key was unchanged.

## Recreate fixtures

`make_fixtures.py` creates `scanned-rotated.pdf`, `quality-warning.txt`, `quality-language-fr.txt` and `quality-language-mixed.txt`. The PDF contains raster-only pages: page 1 says the eastern trail has seven lanterns; page 2 is sideways and says the western trail has nine compasses. `browser-upload.txt` is the separate browser form fixture. Use a dedicated QA project for uploads and pipeline versions; do not overwrite existing documents.

## Browser paths and saved versions

| Case | Browser sequence and persisted check | Primary evidence |
| --- | --- | --- |
| EX-027 | Focus the native Mixed-language select; send ArrowUp, then Space, ArrowUp, Enter in both headless and headed agent-browser. The value stays Fail. A direct `agent-browser select` changes it, so keyboard support remains unproven. | `screenshots/ex-027-headed-native-select-unchanged.png` |
| EX-033 | Upload `browser-upload.txt` through Knowledge Base, prepare it, then inspect its one persisted chunk. | `screenshots/ex-033-upload-prepared.png` |
| EX-043 | In the ingestion editor, start a saved run and click Cancel run while queued/running; reopen run details and verify cancelled nodes/items and no index. | `screenshots/ex-043-browser-cancelled.png` |
| EX-049, EX-061 | Upload `scanned-rotated.pdf`, save OCR Always v7 and Automatic fallback v14, run each from the browser, and inspect Extracted page 2. Auto run `8976c8b5-3dfa-44bb-adb0-bf6e9d11556f` published OCR QA index v3. Page 2 records OCR, fallback, 90° rotation and 96.4/100 engine confidence. | `screenshots/ex-049-ocr-auto-page-2.png` |
| EX-050, EX-062 | Run saved warning, strict, French, mixed and optional/required versions; inspect run items and exact published passages. Optional warning is excluded, good source publishes; required failure cancels the sibling and keeps the old ready index. | `screenshots/ex-050-optional-excluded-published.png` |
| EX-063 | Save v15 with `en` allowlist, Disallowed language = Exclude and report, and English plus French files. The French file must be excluded even though it is required. Only English may appear in ready index v1. | `screenshots/ex-063-language-exclusion-membership.png` |
| EX-064, EX-065 | Run mixed English/Cyrillic file with Warn v16 and Allow v17. Persisted Extracted content reports `warn` plus a mixed-language finding, then `pass` without that finding. | `screenshots/ex-064-mixed-language-warn-published.png`, `screenshots/ex-065-mixed-language-allow-published.png` |
| EX-060 | Run page-bounded chunker v2 on the corrected two-page PDF (run `1e72a6ae-8186-46b4-a455-fc1e0f72d81f`), then Test retrieval for “How many maps cover the southern approach?” Rank 1 must cite page 2. | `screenshots/ex-060-page-2-retrieval.png` |

EX-063 initially reproduced a product defect: the browser run failed and cancelled the English sibling despite the saved exclusion action. The corrected rerun appears in the screenshots. EX-027 is still `BLOCKED` because agent-browser did not operate the native select keyboard popup in either mode; the screenshots capture the unchanged value, not proof of an application accessibility failure. A human keyboard pass or an independent browser driver is the next check.

## Verification

The dedicated `rag-quality-studio-qa-test` Compose project uses a disposable tmpfs PostgreSQL test database. Its database was recreated only between test runs because the test fixture refuses to reset populated data. The final integration command passed 61 tests:

```sh
docker compose -p rag-quality-studio-qa-test -f compose.test.yaml run --build --rm tests python -m pytest -q tests/test_existing_files_ingestion.py tests/test_structure_chunking.py tests/test_layout_extraction.py tests/test_content_derivations.py tests/test_security_controls.py tests/test_ingestion_contracts.py
```

Frontend lint, typecheck, 11 targeted Vitest tests, the full 121-test Vitest suite, and build passed. The live development database was upgraded to Alembic `0028`, and the backend, worker and dispatcher were recreated without touching volumes. The browser results above were then verified against persisted run, derivation and index inspectors.

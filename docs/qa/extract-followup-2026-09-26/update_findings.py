"""Apply the 2026-09-26 browser follow-up results to the original QA ledger."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FINDINGS = ROOT / "extract-ingestion-qa-findings.csv"
EVIDENCE = "docs/qa/extract-followup-2026-09-26/screenshots/"


def update(row: dict[str, str], *, actual: str, status: str, reproducibility: str, evidence: str, notes: str) -> None:
    row.update(
        {
            "actual result": actual,
            "status": status,
            "reproducibility": reproducibility,
            "evidence path": EVIDENCE + evidence,
            "notes": notes,
        }
    )


with FINDINGS.open(newline="") as handle:
    reader = csv.DictReader(handle)
    fields = reader.fieldnames
    assert fields is not None
    rows = [
        row
        for row in reader
        if row["ID"] not in {"EX-061", "EX-062", "EX-063", "EX-064", "EX-065"}
    ]

by_id = {row["ID"]: row for row in rows}

update(
    by_id["EX-007"],
    actual="Browser save of historical v4 with unavailable fra OCR pack returned 422; no new version was created. The same server validation also gates run submission.",
    status="PASS",
    reproducibility="1/1 after fix",
    evidence="ex-007-unavailable-ocr-rejected.png",
    notes="Root cause: ingestion graph validation accepted configured OCR languages without checking installed server packs. Fixed save/start validation. Historical v4 remains immutable and cannot run.",
)
update(
    by_id["EX-012"],
    actual="Browser save at 149 DPI returned 422 with a short Extract · OCR resolution message at the top and beside the field; saved version stayed v14.",
    status="PASS",
    reproducibility="1/1 after fix",
    evidence="ex-012-inline-dpi-validation.png",
    notes="Root cause: untagged schema-v2 union and unfiltered union errors. Discriminated node/chunk schemas and field-level 422 mapping now retain answer-pipeline compatibility.",
)
update(
    by_id["EX-027"],
    actual="Focused native select stayed on Fail after ArrowUp and Space+ArrowUp+Enter in headless and headed agent-browser sessions. Direct browser select changed it.",
    status="BLOCKED",
    reproducibility="2/2 agent-browser modes",
    evidence="ex-027-headed-native-select-unchanged.png",
    notes="Automation limitation remains plausible; browser-native select keyboard behavior is not proven defective. Requires a human keyboard pass or a browser tool that can operate the native popup. Headless screenshot: ex-027-native-select-keyboard.png.",
)
update(
    by_id["EX-033"],
    actual="agent-browser selected browser-upload.txt and submitted the browser form; POST /documents returned 201; browser preparation succeeded and persisted one chunk.",
    status="PASS",
    reproducibility="1/1 after retry",
    evidence="ex-033-upload-prepared.png",
    notes="Original click stall was transient browser automation/session behavior, not a confirmed product defect. Isolated encrypted QA upload; existing project files untouched.",
)
update(
    by_id["EX-040"],
    actual="Required-item failure ended with the failed item failed and the other item cancelled; no item remained processing and the previous ready index remained available.",
    status="PASS",
    reproducibility="1/1 after fix",
    evidence="ex-040-terminal-items.png",
    notes="Root cause: parent failure path did not terminalize sibling processing items. Worker now closes unfinished items before marking the run failed.",
)
update(
    by_id["EX-041"],
    actual="Browser content inspector for a failed schema-v2 item said processing failed and no canonical content is available.",
    status="PASS",
    reproducibility="1/1 after fix",
    evidence="ex-041-failed-content-reason.png",
    notes="Root cause: hardcoded legacy-only unavailable copy. Inspector now uses failed processing status and clears stale load errors after recovery.",
)
update(
    by_id["EX-043"],
    actual="Browser Run ingestion followed by Cancel run returned 202 then 200; run and all stages/items persisted as cancelled, with no new index.",
    status="PASS",
    reproducibility="1/1 after retry",
    evidence="ex-043-browser-cancelled.png",
    notes="Original attempt lacked a cancellable window. Browser control was retested on isolated QA run 78f353dc-62c0-406a-8974-90187fe4d044.",
)
update(
    by_id["EX-049"],
    actual="Raster-only two-page PDF uploaded and run from browser: OCR Always v7 and Auto v14 published ready indexes. Persisted page 2 shows OCR, 90° rotation, 96.4/100 confidence and the nine-compasses answer.",
    status="PASS",
    reproducibility="2/2 policies",
    evidence="ex-049-ocr-auto-page-2.png",
    notes="Original blocker was a missing scanned/rotated fixture. Added reproducible PDF generator. Product defect: page-level OCR provenance was not persisted; migration 0026 and inspector now expose it. Always screenshot: ex-049-ocr-rotated-page-clean.png. Auto run 8976c8b5-3dfa-44bb-adb0-bf6e9d11556f.",
)
update(
    by_id["EX-050"],
    actual="Browser-saved runs exercised warning publication, strict blocking, disallowed-language fail/exclude, mixed-language fail/warn/allow, optional exclusion and required failure. Excluded items stayed out of ready indexes; required failure published no new index.",
    status="PASS",
    reproducibility="9/9 variants",
    evidence="ex-050-optional-excluded-published.png",
    notes="Original blocker was missing isolated fixtures. Product defects: Existing Files lacked per-file optional flags, and processing lost the disallowed-language exclusion reason. Migrations 0027-0028, UI and worker now persist these decisions and publish exact successful membership. See EX-063 through EX-065 for additional language branches.",
)
update(
    by_id["EX-059"],
    actual="Browser Test retrieval on reprocessed PDF index returned the page-2 answer as rank 1 with page 2 in evidence.",
    status="PASS",
    reproducibility="1/1 after provenance fix",
    evidence="ex-060-page-2-retrieval.png",
    notes="Test retrieval returns passages, not a generated answer. Page provenance is separately assessed in EX-060.",
)
update(
    by_id["EX-060"],
    actual="Browser rerun of two-page PDF published index v2. Stored answer chunk and rank-1 retrieval evidence both cite PDF page 2.",
    status="PASS",
    reproducibility="1/1 after fix",
    evidence="ex-060-page-2-retrieval.png",
    notes="Root cause: section-token chunking grouped same-section blocks across a page boundary and dropped the page number. Page-bounded chunking v2 reprocessed the immutable source; run 1e72a6ae-8186-46b4-a455-fc1e0f72d81f.",
)

by_id["EX-005"]["notes"] = "Always and Auto executed on raster-only rotated PDF in EX-049; Off selection only was checked here."
by_id["EX-010"]["notes"] = "Both bounds persist; 200 DPI OCR executed on the scanned fixture in EX-049."
by_id["EX-016"]["notes"] = "Runtime warning and strict decisions now covered in EX-050."
by_id["EX-018"]["notes"] = "Optional exclusion runtime now covered in EX-050 and EX-062."
by_id["EX-021"]["notes"] = "Bounds verified; OCR confidence is now exposed from the scanned fixture in EX-049."
by_id["EX-024"]["notes"] = "Disallowed-language failure and exclusion executed in EX-050 and EX-063."
by_id["EX-025"]["notes"] = "Mixed-language Fail, Warn and Allow executed in EX-050, EX-064 and EX-065."
by_id["EX-032"]["notes"] = "Original sparse PDF remains a historical fixture. Browser upload was retested successfully with a separate TXT in EX-033."
by_id["EX-047"]["notes"] = "Backend validation only; browser upload itself was separately verified in EX-033."
by_id["EX-048"]["notes"] = "Backend validation only; browser upload itself was separately verified in EX-033."
by_id["EX-054"]["notes"] = "Corrected PDF used API upload plus browser preparation; a separate browser upload was verified in EX-033."


def extra(
    id: str,
    area: str,
    scenario: str,
    steps: str,
    expected: str,
    actual: str,
    evidence: str,
    notes: str,
    severity: str = "None",
) -> dict[str, str]:
    return {
        "ID": id,
        "area": area,
        "scenario": scenario,
        "steps": steps,
        "expected result": expected,
        "actual result": actual,
        "status": "PASS",
        "severity": severity,
        "reproducibility": "1/1",
        "evidence path": EVIDENCE + evidence,
        "notes": notes,
    }


rows.extend(
    [
        extra(
            "EX-061",
            "OCR runtime",
            "Automatic fallback on raster-only rotated PDF",
            "Save OCR Automatic fallback v14; run from browser; inspect persisted page 2.",
            "Low-native-text pages use OCR and retain per-page fallback/rotation evidence.",
            "Browser run succeeded and published index v3; page 2 records OCR, native text below 20 characters, 90° applied, confidence 96.4/100, and nine compasses.",
            "ex-049-ocr-auto-page-2.png",
            "Run 8976c8b5-3dfa-44bb-adb0-bf6e9d11556f. Full UI → API → worker → persisted inspector path.",
        ),
        extra(
            "EX-062",
            "Optional items",
            "Optional exclusion versus required failure",
            "Run saved v12 with warning source marked optional and good source required; rerun v13 with warning source required.",
            "Optional policy excludes only the bad source; required failure terminates siblings and preserves previous ready index.",
            "v12 published one-member ready index with bad item excluded; v13 failed, bad item failed and good item cancelled, without publishing over the ready index.",
            "ex-050-optional-published-membership.png",
            "Browser run and index inspectors. Required failure screenshot: ex-040-terminal-items.png.",
        ),
        extra(
            "EX-063",
            "Language policy",
            "Disallowed-language exclusion publishes eligible file",
            "Save v15 from v10 with French and English files, en allowlist, Exclude and report; run from browser and inspect the published index.",
            "French file is excluded and reported; English file alone is searchable in a ready index.",
            "Initial browser run failed both-file publication, exposing lost exclusion reason. After fix, French item was excluded, English item succeeded, and ready index v1 contained only the English passage.",
            "ex-063-language-exclusion-membership.png",
            "Root cause: processing persisted a generic failed status/message, so ingestion could not distinguish language exclusion from an ordinary quality failure. Migration 0028 adds a safe failure code, and the worker honors language_excluded. Run-details screenshot: ex-063-language-excluded-published.png.",
            severity="Medium",
        ),
        extra(
            "EX-064",
            "Language policy",
            "Mixed-language Warn publication",
            "Save v16 from v11 with Mixed-language Warn; run from browser and inspect persisted extracted content.",
            "Mixed document publishes with an explicit warning finding and quality decision warn.",
            "Browser run published ready index v1; persisted content showed quality decision warn and warning · mixed languages.",
            "ex-064-mixed-language-warn-published.png",
            "Real mixed English/Cyrillic QA fixture; no mock response or API-only result.",
        ),
        extra(
            "EX-065",
            "Language policy",
            "Mixed-language Allow publication",
            "Save v17 from v16 with Mixed-language Allow; run from browser and inspect persisted extracted content.",
            "Mixed document publishes with quality decision pass and no mixed-language warning finding.",
            "Browser run published ready index v1; persisted content showed quality decision pass, mixed detected, and no mixed-language warning.",
            "ex-065-mixed-language-allow-published.png",
            "Completes Fail, Warn and Allow runtime decisions with EX-050 and EX-064.",
        ),
    ]
)

assert len(rows) == len(by_id) + 5
with FINDINGS.open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

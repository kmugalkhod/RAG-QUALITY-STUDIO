"""Spec 0012 Slice 6: v1/v2 identity and v3 statistics on the saved real-source runs.

Free and read-only: it reads the stored extracted and cleaned derivations and the
stored chunks of each index's processing runs from DATABASE_URL, chunks and cleans
them again in memory, and calls no provider.

    python scripts/clean_chunk/v3_corpus.py --index files-A4s=<index id> --out v3.json

Per index:

- `identical`: each run's stored chunks (text, embedding text, role and parent)
  compared with chunking its stored cleaned document again with the saved version.
- `saved` and `v3`: passage statistics with the saved version and with v3 (the same
  sizes, `section-token-v3` or `parent-child-v3`).
- `cleaning`: for runs with structure-aware cleaning, whether cleaning the stored
  extracted document again with the saved settings reproduces the stored cleaned
  output hash, and, for website pages, the protected blocks v1 removed as repeated
  site chrome against those `structure-clean-v2` removes. Pages are grouped by host
  to measure repeated chrome, as a crawl groups them by source.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import Counter, defaultdict
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.ingestion_content import (
    chunk_cleaned_document,
    clean_document,
    cleaner_for_node,
)
from app.ingestion_content.cleaning import site_chrome_for
from app.schemas.ingestion import (
    CleanNodeV2,
    ParentChildChunkNodeV2,
    SectionTokenChunkNodeV2,
)
from app.services.derivations import (
    reusable_cleaned_document,
    reusable_extracted_document,
)

SHORT = 40
PROTECTED = {"table", "list_item", "code", "quote", "footnote"}
RUNS = text(
    """
    SELECT DISTINCT ic.run_id, pr.processing_config
    FROM index_chunks ic JOIN processing_runs pr ON pr.id = ic.run_id
    WHERE ic.index_id = :index_id
    """
)
CHUNKS = text(
    """
    SELECT ordinal, chunk_role, parent_ordinal, text,
           coalesce(embedding_text, text) AS embedding_text,
           provenance ->> 'canonical_location' AS location
    FROM chunks WHERE run_id = :run_id ORDER BY ordinal
    """
)
NODES = {
    "section_token": SectionTokenChunkNodeV2,
    "parent_child": ParentChildChunkNodeV2,
}
V3 = {"section_token": "section-token-v3", "parent_child": "parent-child-v3"}


def chunk_node(config: dict):
    return NODES[config["algorithm"]].model_validate(
        {**config, "id": "chunk", "type": "chunk"}
    )


def passages(document, result) -> list[dict]:
    """Embedded passages with size, embedding size and whether they start mid-word."""
    blocks = {block.ordinal: block for block in document.blocks}
    rows = []
    for chunk in result.chunks:
        span = result.spans[chunk.ordinal][0]
        block_text = blocks[span.block_ordinal].text
        start = span.block_start_char
        rows.append(
            {
                "role": chunk.chunk_role,
                "bytes": len(chunk.text.encode("utf-8")),
                "embedding_bytes": len((chunk.embedding_text or chunk.text).encode()),
                "mid_word": 0 < start < len(block_text)
                and block_text[start - 1].isalnum()
                and block_text[start].isalnum(),
                "page": chunk.page_number,
            }
        )
    return rows


def page_bytes(document) -> dict:
    sizes = Counter()
    for block in document.blocks:
        sizes[block.page_number] += len(block.text.encode("utf-8"))
    return sizes


def summary(rows: list[dict], small_pages: int) -> dict:
    embedded = [row for row in rows if row["role"] != "parent"]
    parents = [row for row in rows if row["role"] == "parent"]
    values = sorted(row["bytes"] for row in embedded)
    return {
        "passages": len(values),
        "median": statistics.median(values) if values else None,
        "min": values[0] if values else None,
        "max": values[-1] if values else None,
        "max_embedding_text": max(
            (r["embedding_bytes"] for r in embedded), default=None
        ),
        "under_40_bytes": sum(value < SHORT for value in values),
        # A page or document holding under 40 bytes cannot give a longer passage
        # without crossing the page boundary a citation needs.
        "under_40_on_pages_under_40": small_pages,
        "mid_word_starts": sum(row["mid_word"] for row in embedded),
        "parents": len(parents),
        "parent_mid_word_starts": sum(row["mid_word"] for row in parents),
        "parent_min": min((row["bytes"] for row in parents), default=None),
    }


def small_page_passages(document, rows) -> int:
    sizes = page_bytes(document)
    return sum(
        row["role"] != "parent" and row["bytes"] < SHORT and sizes[row["page"]] < SHORT
        for row in rows
    )


def index_report(session: Session, index_id: str) -> dict:
    runs = session.execute(RUNS, {"index_id": index_id}).all()
    identical = mismatched = skipped = 0
    saved_rows, v3_rows = [], []
    saved_small = v3_small = 0
    versions = Counter()
    clean_same = clean_differs = 0
    web_pages = defaultdict(list)
    clean_settings = None
    for run_id, config in runs:
        try:
            cleaned, _ = reusable_cleaned_document(session, run_id)
        except ValueError:
            skipped += 1
            continue
        node = chunk_node(config["chunk"])
        versions[node.config_version] += 1
        stored = session.execute(CHUNKS, {"run_id": run_id}).mappings().all()
        again = chunk_cleaned_document(cleaned, node)
        same = [
            (
                row["text"],
                row["embedding_text"],
                row["chunk_role"],
                row["parent_ordinal"],
            )
            for row in stored
        ] == [
            (c.text, c.embedding_text or c.text, c.chunk_role, c.parent_ordinal)
            for c in again.chunks
        ]
        identical += same
        mismatched += not same
        rows = passages(cleaned, again)
        saved_rows += rows
        saved_small += small_page_passages(cleaned, rows)
        v3_node = node.model_copy(update={"config_version": V3[node.algorithm]})
        v3 = chunk_cleaned_document(cleaned, v3_node)
        rows = passages(cleaned, v3)
        v3_rows += rows
        v3_small += small_page_passages(cleaned, rows)

        clean = config.get("clean") or {}
        if clean.get("profile") != "structure-aware-v1":
            continue
        clean_settings = CleanNodeV2.model_validate(
            {**clean, "id": "clean", "type": "clean"}
        )
        extracted = reusable_extracted_document(session, run_id)
        if extracted is None:
            continue
        document, extractor_version = extracted
        location = next((row["location"] for row in stored if row["location"]), None)
        if location:
            web_pages[urlsplit(location).netloc].append((location, document, cleaned))
            continue
        result = clean_document(
            document,
            clean_settings,
            cleaner_for_node(clean_settings),
            extractor_version=extractor_version,
            configuration_hash=cleaned.configuration_hash,
        )
        clean_same += result.output_hash == cleaned.output_hash
        clean_differs += result.output_hash != cleaned.output_hash

    report = {
        "runs": len(runs),
        "chunk_versions": dict(versions),
        "identical": identical,
        "mismatched": mismatched,
        "skipped": skipped,
        "saved": summary(saved_rows, saved_small),
        "v3": summary(v3_rows, v3_small),
        "cleaning": {"files_identical": clean_same, "files_differ": clean_differs},
    }
    if web_pages and clean_settings is not None:
        report["cleaning"]["website"] = website_report(web_pages, clean_settings)
    return report


def website_report(web_pages, v1_settings) -> dict:
    v2_settings = v1_settings.model_copy(
        update={"config_version": "structure-clean-v2"}
    )
    main_step = next(
        (
            s
            for s in v1_settings.steps
            if s.type == "website_main_content" and s.enabled
        ),
        None,
    )
    ratio = main_step.minimum_page_ratio if main_step else 0.6
    counts = Counter()
    for pages in web_pages.values():
        located = [(location, document) for location, document, _ in pages]
        chrome = {
            "v1": site_chrome_for(v1_settings, located, ratio),
            "v2": site_chrome_for(v2_settings, located, ratio),
        }
        for location, document, stored in pages:
            types = {block.id: block.type for block in document.blocks}
            for name, clean in (("v1", v1_settings), ("v2", v2_settings)):
                result = clean_document(
                    document,
                    clean,
                    cleaner_for_node(clean),
                    extractor_version=stored.extractor_version,
                    configuration_hash=stored.configuration_hash,
                    repeated_site_fingerprints=chrome[name],
                    document_location=location,
                )
                if name == "v1":
                    counts["pages"] += 1
                    counts["v1_same_as_stored"] += (
                        result.output_hash == stored.output_hash
                    )
                for audit in result.transforms:
                    for change in audit.changes:
                        if change.reason != "repeated_site_chrome":
                            continue
                        counts[f"{name}_repeated_chrome_removed"] += 1
                        if types.get(change.block_id) in PROTECTED:
                            counts[f"{name}_protected_removed"] += 1
                    kept = audit.metrics.get("repeated_blocks_kept")
                    if name == "v2" and kept:
                        counts["v2_repeated_kept"] += kept
    return dict(counts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", action="append", default=[], help="name=index id")
    parser.add_argument("--out")
    args = parser.parse_args()
    engine = create_engine(os.environ["DATABASE_URL"])
    report = {}
    with Session(engine) as session:
        for value in args.index:
            name, index_id = value.split("=", 1)
            report[name] = index_report(session, str(UUID(index_id)))
            print(name, json.dumps(report[name]), flush=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")


if __name__ == "__main__":
    main()

"""Spec 0012 baseline: preview files with the recommended settings and report the
per-stage timings each preview item records. Free: a preview embeds nothing.

    python scripts/clean_chunk/preview_timings.py <api base> <project id> <document id>...
"""

from __future__ import annotations

import json
import sys
import time

import httpx

TERMINAL = {"succeeded", "failed", "cancelled", "expired"}


def main():
    base, project_id, *document_ids = sys.argv[1:]
    client = httpx.Client(base_url=f"{base}/api/projects/{project_id}", timeout=120)
    capabilities = client.get("/ingestion-capabilities").json()
    embedding = client.get("/embedding-settings").json()["config"]
    policy = next(
        p["settings"]
        for p in capabilities["quality_policies"]
        if p["id"] == "default-v1"
    )
    chunk = next(
        p for p in capabilities["chunking_profiles"] if p["id"] == "section_token"
    )
    cleaning = capabilities["cleaning_profiles"][0]
    nodes = [
        {
            "id": "source",
            "type": "source",
            "config": {"kind": "existing_files", "document_ids": document_ids},
        },
        {
            "id": "extract",
            "type": "extract",
            "strategy": "auto",
            "ocr": {
                "mode": "auto",
                "languages": ["eng"],
                "rotate_pages": True,
                "deskew": True,
                "dpi": 200,
                "max_pages": 100,
                "timeout_seconds": 30,
            },
            "tables": "preserve",
            "quality_policy": {**policy, "warning_action": "publish"},
            "config_version": "layout-ocr-v5",
        },
        {
            "id": "clean",
            "type": "clean",
            "profile": cleaning["id"],
            "config_version": cleaning["config_version"],
            "steps": cleaning["steps"],
        },
        {
            "id": "chunk",
            "type": "chunk",
            "algorithm": "section_token",
            "unit": "tokens",
            **chunk["settings"],
        },
        {
            "id": "embed",
            "type": "embed",
            "provider": embedding["provider"],
            "model": embedding["model"],
            "dimensions": embedding["dimensions"],
            "config_version": embedding["revision"],
        },
        {
            "id": "publish",
            "type": "publish_index",
            "knowledge_set_name": "Baseline preview",
        },
    ]
    execution = {
        "schema_version": 2,
        "index_layout": "merged",
        "nodes": nodes,
        "edges": [
            {"source": left["id"], "target": right["id"]}
            for left, right in zip(nodes, nodes[1:])
        ],
    }
    started = time.monotonic()
    preview = client.post("/ingestion-previews", json={"execution": execution})
    preview.raise_for_status()
    preview_id = preview.json()["id"]
    while True:
        state = client.get(f"/source-previews/{preview_id}").json()
        if state["status"] in TERMINAL:
            break
        time.sleep(3)
    items = client.get(
        f"/source-previews/{preview_id}/items", params={"limit": 100}
    ).json()
    result = {
        "status": state["status"],
        "wall_seconds": round(time.monotonic() - started, 1),
        "known_compute_ms": state["known_compute_ms"],
        "items": [
            {
                "name": item["display_name"],
                "status": item["processing_status"],
                "stage_ms": item["stage_timings"],
                "chunks": item["metrics"].get("chunk_count"),
            }
            for item in items["items"]
        ],
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

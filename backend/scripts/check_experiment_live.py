"""Opt-in, bounded three-question check against the sample orchard source.

Uses the running API and its server credentials. Pass an existing sample project
and one or two immutable pipeline version IDs. Never use unrelated/private data.
"""

import argparse
import json
import time
from pathlib import Path
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8000")
parser.add_argument("--project", required=True)
parser.add_argument("--version", action="append", required=True)
parser.add_argument("--output", default="/tmp/rag-live-experiment.json")
args = parser.parse_args()
if not 1 <= len(args.version) <= 2:
    parser.error("Choose one or two saved pipeline versions.")
# Human-readable, reviewed against the sample source: orchard grows apples;
# harvest begins in September; founder is absent and has no reference answer.
data = b"question,reference_answer\nWhat fruit does the orchard grow?,The orchard grows apples.\nWhen does the harvest begin?,The harvest begins in September.\nWho founded the orchard?,\n"
with httpx.Client(base_url=args.base_url, timeout=30) as client:
    base = f"/api/projects/{args.project}"
    preview = client.post(
        base + "/datasets/preview", files={"file": ("reviewed-orchard.csv", data)}
    )
    preview.raise_for_status()
    assert not preview.json()["errors"]
    dataset = client.post(
        base + "/datasets",
        files={"file": ("reviewed-orchard.csv", data)},
        data={
            "name": "Reviewed orchard live check",
            "content_hash": preview.json()["content_hash"],
        },
    )
    dataset.raise_for_status()
    response = client.post(
        base + "/experiments",
        json={
            "name": "Milestone 5 live orchard comparison",
            "dataset_version_id": dataset.json()["id"],
            "pipeline_version_ids": args.version,
            "metrics": ["faithfulness", "response_relevancy", "context_recall"],
        },
    )
    response.raise_for_status()
    id = response.json()["id"]
    print(f"Experiment accepted: {id}", flush=True)
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        response = client.get(base + "/experiments/" + id)
        response.raise_for_status()
        result = response.json()
        if result["status"] not in ("queued", "running"):
            Path(args.output).write_text(json.dumps(result, indent=2))
            print(
                json.dumps(
                    {
                        "id": id,
                        "status": result["status"],
                        "progress": result["progress"],
                        "summary": result["summary"],
                    },
                    indent=2,
                ),
                flush=True,
            )
            break
        time.sleep(5)
    else:
        client.post(base + "/experiments/" + id + "/cancel").raise_for_status()
        raise SystemExit(
            "Live deadline reached; cancellation requested. Inspect persisted partial results."
        )

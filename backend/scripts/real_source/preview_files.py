"""Free check before paid rounds: preview the files track and look for each answer phrase."""

import json
import sys
from pathlib import Path

import run as harness

work = Path(sys.argv[1])
round_id = sys.argv[2] if len(sys.argv) > 2 else "R1"
runner = harness.Run(work, "http://127.0.0.1:8000")
started = runner.call(
    "POST",
    f"{runner.project}/ingestion-previews",
    json={"execution": runner.execution("files", round_id)},
)
done = runner.wait(f"{runner.project}/source-previews/{started['id']}", pause=3)
print("preview", done["status"], "known compute ms", done.get("known_compute_ms"))
items = runner.paged(f"{runner.project}/source-previews/{done['id']}/items")
chunks, blocks = {}, {}
for item in items:
    texts, extracted = [], []
    if item["processing_status"] == "succeeded":
        base = f"{runner.project}/source-previews/{done['id']}/items/{item['ordinal']}/representations"
        texts = [x["text"] for x in runner.paged(base, params={"stage": "chunks"})]
        extracted = [
            {"type": x["block_type"], "page": x["metadata"].get("page_number"),
             "path": x["metadata"].get("heading_path"), "text": x["text"][:200]}
            for x in runner.paged(base, params={"stage": "extracted"})
        ]
    chunks[item["display_name"]] = texts
    blocks[item["display_name"]] = extracted
    kinds = {}
    for block in extracted:
        kinds[block["type"]] = kinds.get(block["type"], 0) + 1
    print(item["display_name"], item["processing_status"], item["quality_decision"],
          item["error_code"], "chunks", len(texts), "blocks", kinds)
names = {sid: f["filename"] for sid, f in runner.sources["files"].items()}
for question in harness.load_questions():
    if question["source"].startswith("F") and question["phrases"]:
        phrases = [harness.normalize(p) for p in question["phrases"]]
        found = any(
            all(p in harness.normalize(t) for p in phrases)
            for t in chunks.get(names[question["source"]], [])
        )
        print(question["id"], "phrase in a chunk:", found)
(work / f"preview_files_{round_id}.json").write_text(
    json.dumps({"preview": done, "chunks": chunks, "blocks": blocks}) + "\n"
)

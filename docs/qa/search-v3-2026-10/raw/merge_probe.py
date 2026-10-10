"""Spec 0010 slice 0, B2: embed the merged Eurostat p. 21 chunk through the app and rank it.

The run of short chunks around the callout is appended to the chunk before it (same page),
written as one TXT document with the same "Section: ..." prefix, indexed with the files
settings, and searched with f4-q1. Its distance is compared with the unchanged chunks of
the A3 Eurostat index (top 50) to estimate its rank.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app/scripts/real_source")
from run import Run, load_questions  # noqa: E402

runner = Run(Path("/tmp/rs"), "http://127.0.0.1:8000")
records = json.load(open("/tmp/rs/records_new_A3.json"))
target = next(i for i, r in enumerate(records) if "381 d" in r["text"])
page = records[target]["page_number"]
start = target
while start > 0 and records[start]["token_count"] < 40 and records[start - 1]["page_number"] == page:
    start -= 1
end = target
while end + 1 < len(records) and records[end + 1]["token_count"] < 40 and records[end + 1]["page_number"] == page:
    end += 1
group = records[start : end + 1]
merged = (group[0].get("embedding_prefix") or "") + "\n\n".join(r["text"] for r in group)
group_ordinals = {r["ordinal"] for r in group}
print("merged ordinals", sorted(group_ordinals), "tokens", sum(r["token_count"] for r in group))

experiments = runner.state.setdefault("experiments_0010", {})
if not experiments.get("B2", {}).get("index_id"):
    uploaded = runner.call("POST", f"{runner.project}/documents",
                           files={"file": ("spec-0010-b2-merged-chunk.txt", merged.encode("utf-8"), "text/plain")})
    runner.state["capabilities"] = runner.call("GET", f"{runner.project}/ingestion-capabilities")
    execution = runner.execution("files", "A3")
    for node in execution["nodes"]:
        if node["type"] == "source":
            node["config"]["document_ids"] = [uploaded["id"]]
        if node["type"] == "publish_index":
            node["knowledge_set_name"] = "Spec 0010 slice 0 B2"
    saved = runner.call("POST", f"{runner.project}/pipelines", json={
        "kind": "ingestion", "name": "Spec 0010 slice 0 B2", "execution": execution,
        "layout": runner.layout(execution)})
    started = runner.call("POST", f"{runner.project}/pipelines/{saved['pipeline_id']}/versions/{saved['id']}/ingestion-runs", json={})
    done = runner.wait(f"{runner.project}/ingestion-runs/{started['id']}", deadline_s=1800)
    experiments["B2"] = {"document_id": uploaded["id"], "index_id": done["published_index_id"],
                         "status": done["status"], "chunks": done["chunk_count"],
                         "embedding_usage": done.get("embedding_usage")}
    runner.save()
print("B2 index", experiments["B2"])
question = next(q for q in load_questions() if q["id"] == "f4-q1")["question"]


def search(index_id, top_k):
    response = runner.call("POST", f"{runner.project}/retrieval", json={
        "index_id": index_id, "query": question, "retrieval": {"mode": "vector", "top_k": top_k}})
    return response.get("evidence") or response.get("items") or []


merged_items = search(experiments["B2"]["index_id"], 5)
merged_distance = min(i["cosine_distance"] for i in merged_items)
others = [i["cosine_distance"] for i in search(runner.state["runs"]["new:A3"]["index_id"], 50)
          if i["ordinal"] not in group_ordinals]
print(f"merged chunk distance {merged_distance:.4f}; today's top 5 {[round(d, 4) for d in others[:5]]}")
print("estimated rank of the merged chunk:", 1 + sum(1 for d in others if d < merged_distance))

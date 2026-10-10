"""Spec 0010 slice 0: experiment indexes for Census (F2) and Eurostat (F4) with v5 extraction."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/app/scripts/real_source")
from run import Run  # noqa: E402

VARIANTS = {
    "E1": {"id": "chunk", "type": "chunk", "algorithm": "section_token", "unit": "tokens",
           "tokenizer_version": "utf8-byte-v1", "target_tokens": 200, "maximum_tokens": 300,
           "overlap_tokens": 30, "add_heading_context": True, "config_version": "section-token-v1"},
    "E2": {"id": "chunk", "type": "chunk", "algorithm": "parent_child", "unit": "tokens",
           "tokenizer_version": "utf8-byte-v1", "child_target_tokens": 240,
           "child_maximum_tokens": 320, "child_overlap_tokens": 40, "parent_target_tokens": 900,
           "parent_maximum_tokens": 1200, "add_heading_context": True,
           "config_version": "parent-child-v1"},
    "E3": {"id": "chunk", "type": "chunk", "algorithm": "parent_child", "unit": "tokens",
           "tokenizer_version": "utf8-byte-v1", "child_target_tokens": 120,
           "child_maximum_tokens": 160, "child_overlap_tokens": 20, "parent_target_tokens": 900,
           "parent_maximum_tokens": 1200, "add_heading_context": True,
           "config_version": "parent-child-v1"},
}
runner = Runner = Run(Path("/tmp/rs"), "http://127.0.0.1:8000")
runner.state["capabilities"] = runner.call("GET", f"{runner.project}/ingestion-capabilities")
documents = [runner.state["documents"]["F2"]["id"], runner.state["documents_v4"]["F4"]["id"]]
experiments = runner.state.setdefault("experiments_0010", {})
for name, chunk in VARIANTS.items():
    if experiments.get(name, {}).get("index_id"):
        continue
    execution = runner.execution("files", "A3")
    for node in execution["nodes"]:
        if node["type"] == "source":
            node["config"]["document_ids"] = documents
        if node["type"] == "publish_index":
            node["knowledge_set_name"] = f"Spec 0010 slice 0 {name}"
    execution["nodes"] = [chunk if node["type"] == "chunk" else node for node in execution["nodes"]]
    saved = runner.call("POST", f"{runner.project}/pipelines", json={
        "kind": "ingestion", "name": f"Spec 0010 slice 0 {name}",
        "execution": execution, "layout": runner.layout(execution)})
    started = runner.call(
        "POST",
        f"{runner.project}/pipelines/{saved['pipeline_id']}/versions/{saved['id']}/ingestion-runs",
        json={})
    done = runner.wait(f"{runner.project}/ingestion-runs/{started['id']}", deadline_s=3600)
    experiments[name] = {"pipeline_id": saved["pipeline_id"], "version_id": saved["id"],
                         "run_id": done["id"], "status": done["status"],
                         "index_id": done["published_index_id"], "chunks": done["chunk_count"],
                         "embedding_usage": done.get("embedding_usage"), "error": done["error"]}
    runner.save()
    print(name, experiments[name], flush=True)
print(json.dumps(experiments, indent=1))

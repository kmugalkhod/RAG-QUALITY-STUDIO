"""Spec 0015 Slice 6: ask the disputed questions again on the saved answer pipelines.

Each answer the blind review counted as a win or loss is asked three more times on
the same pipeline, to tell a change's effect from the answer model's own variation
(temperature 0 is not fully deterministic). Paid: one answer (and one rerank) per
run. Run inside the backend container:

    python repeat_check.py /tmp/rs out.json --allow-paid
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from run import Run, load_questions, track_of

REPEATS = 3
# (question, pipeline key in state["answer_pipelines"]) for each disputed answer.
CHECKS = [
    ("f5-q2", "new:A6p"), ("f5-q2", "new:A7"), ("f5-q2", "new:A7+rerank"),
    ("f6-q1", "new:A5"), ("f6-q1", "new:A7s"), ("f6-q1", "new:A7s+rerank"),
    ("f2-q10", "files:A7s"), ("f2-q10", "files:A7s+rerank"),
]


def main(work: Path, out: Path) -> None:
    runner = Run(work, "http://127.0.0.1:8000")
    questions = {q["id"]: q for q in load_questions()}
    results = json.loads(out.read_text()) if out.exists() else {}
    for qid, key in CHECKS:
        assert track_of(questions[qid]["source"], runner.sources) == key.split(":")[0]
        pipeline = runner.state["answer_pipelines"][key]
        runs = results.setdefault(f"{qid}|{key}", [])
        while len(runs) < REPEATS:
            runner.check_cap(0.004)
            started = runner.call(
                "POST",
                f"{runner.project}/pipelines/{pipeline['pipeline_id']}/versions/"
                f"{pipeline['version_id']}/runs",
                json={"question": questions[qid]["question"]},
            )
            done = runner.wait_query(started["id"])
            snapshot = done["snapshot"]
            rerank = snapshot.get("rerank") or {}
            runs.append({
                "run_id": started["id"],
                "status": done["status"],
                "answer": done["answer"],
                "rerank_status": rerank.get("status"),
                "order": [s["retriever_rank"] for s in rerank.get("order", [])],
                "cost_usd": (snapshot.get("cost_usd") or 0) + (rerank.get("cost_usd") or 0),
            })
            out.write_text(json.dumps(results, indent=2) + "\n")
            print(qid, key, done["status"], (done["answer"] or "")[:90], flush=True)


if __name__ == "__main__":
    if "--allow-paid" not in sys.argv:
        raise SystemExit("Paid check: pass --allow-paid.")
    main(Path(sys.argv[1]), Path(sys.argv[2]))

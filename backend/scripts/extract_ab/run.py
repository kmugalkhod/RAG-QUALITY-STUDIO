"""Set up and run the Extract v1/v2 comparison through the public API (spec 0004).

Stages, run in order; each reads and updates `<work>/state.json` so a stage can be
repeated without duplicating uploads, pipelines, indexes or paid answers:

    python run.py setup      <work>                # project, corpus, both ingestion versions
    python run.py preview    <work>                # free: chunk previews for both versions
    python run.py index      <work> --allow-paid   # embeds and publishes both indexes
    python run.py ask        <work> --allow-paid   # asks every question through both arms
    python run.py fetch      <work>                # writes answers.jsonl for score.py

`--round N --arms v2` repeats `ask` and `fetch` for a later answer-side change
(spec 0005); round N keeps its own query runs and writes answers_roundN.jsonl.

Run inside the backend container against http://127.0.0.1:8000 (local auth mode).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import make_corpus  # noqa: E402
import score  # noqa: E402

PROJECT_NAME = "Extract A/B 2026-10"
ARMS = {"v1": "layout-ocr-v1", "v2": "layout-ocr-v2"}
COST_CAP_USD = 2.0
# Under "default-v1", v1 rejects the 40-row table PDF as malformed and the whole
# v1 run fails (recorded on 2026-10-07). "warn-v1" only changes publication
# gating, not extraction, so both arms use it to keep them comparable.
QUALITY_POLICY = "warn-v1"
ANSWER_MODEL = "google/gemini-2.5-flash"
TERMINAL = {"succeeded", "failed", "cancelled", "expired"}
MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class Run:
    def __init__(self, work: Path, base_url: str, round_number: int = 1, arms=None):
        self.round = round_number
        self.arms = arms or list(ARMS)
        self.runs_key = "query_runs" if round_number == 1 else f"query_runs_round{round_number}"
        self.work = work
        self.work.mkdir(parents=True, exist_ok=True)
        self.state_path = work / "state.json"
        self.state = (
            json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        )
        self.client = httpx.Client(base_url=base_url, timeout=120)

    def save(self) -> None:
        self.state_path.write_text(json.dumps(self.state, indent=2) + "\n")

    def call(self, method: str, path: str, **kwargs):
        response = self.client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise SystemExit(
                f"{method} {path} -> {response.status_code}: {response.text[:2000]}"
            )
        return response.json() if response.content else None

    @property
    def project(self) -> str:
        return f"/api/projects/{self.state['project_id']}"

    def wait(
        self, path: str, key: str = "status", deadline_s: int = 1800, pause: float = 3
    ):
        started = time.monotonic()
        while True:
            value = self.call("GET", path)
            if value[key] in TERMINAL:
                return value
            if time.monotonic() - started > deadline_s:
                raise SystemExit(f"Timed out waiting for {path}")
            time.sleep(pause)

    # setup -------------------------------------------------------------
    def setup(self) -> None:
        if "project_id" not in self.state:
            project = self.call(
                "POST",
                "/api/projects",
                json={
                    "name": PROJECT_NAME,
                    "description": "Spec 0004: Extract v1 vs v2 comparison on a fictional corpus.",
                },
            )
            self.state["project_id"] = project["id"]
            self.save()

        corpus_dir = self.work / "corpus"
        manifest = make_corpus.write_corpus(corpus_dir)
        hashes = {d["filename"]: d["sha256"] for d in manifest["documents"]}
        if self.state.get("corpus_hashes") not in (None, hashes):
            raise SystemExit("The regenerated corpus differs from the uploaded one.")
        self.state["corpus_hashes"] = hashes
        documents = self.state.setdefault("documents", {})
        for name in hashes:
            if name in documents:
                continue
            path = corpus_dir / name
            uploaded = self.call(
                "POST",
                f"{self.project}/documents",
                files={"file": (name, path.read_bytes(), MEDIA_TYPES[path.suffix])},
            )
            if uploaded["content_hash"] != hashes[name]:
                raise SystemExit(f"Upload hash mismatch for {name}.")
            documents[name] = uploaded["id"]
            self.save()

        embedding = self.call("GET", f"{self.project}/embedding-settings")["config"]
        capabilities = self.call("GET", f"{self.project}/ingestion-capabilities")
        self.state["embedding"] = embedding
        pipelines = self.state.setdefault("ingestion", {})
        for arm, version in ARMS.items():
            saved_policy = None
            if arm in pipelines:
                extract = next(
                    n
                    for n in pipelines[arm]["execution"]["nodes"]
                    if n["id"] == "extract"
                )
                saved_policy = extract["quality_policy"]
                saved_policy = (
                    saved_policy
                    if isinstance(saved_policy, str)
                    else saved_policy["id"]
                )
                if saved_policy == QUALITY_POLICY:
                    continue
            body = {
                "kind": "ingestion",
                "name": f"Extract A/B {arm}",
                "execution": ingestion_execution(
                    list(documents.values()), version, arm, embedding, capabilities
                ),
                "layout": {
                    "positions": {
                        node: {"x": 0, "y": index * 120}
                        for index, node in enumerate(
                            ["source", "extract", "clean", "chunk", "embed", "publish"]
                        )
                    }
                },
            }
            if arm in pipelines:
                # A new immutable version of the same pipeline; earlier runs stay
                # attached to the version they used.
                superseded = pipelines[arm]
                self.state.setdefault("superseded", []).append(
                    {
                        "arm": arm,
                        "version_id": superseded["version_id"],
                        "quality_policy": saved_policy,
                        "run": self.state.get("ingestion_runs", {}).pop(arm, None),
                    }
                )
                saved = self.call(
                    "POST",
                    f"{self.project}/pipelines/{superseded['pipeline_id']}/versions",
                    json=body,
                )
            else:
                saved = self.call("POST", f"{self.project}/pipelines", json=body)
            pipelines[arm] = {
                "pipeline_id": saved["pipeline_id"],
                "version_id": saved["id"],
                "execution": saved["execution"],
            }
            self.save()
        print(
            json.dumps(
                {"project_id": self.state["project_id"], "documents": documents},
                indent=2,
            )
        )

    # preview -----------------------------------------------------------
    def preview(self) -> None:
        chunks = {}
        for arm in ARMS:
            execution = self.state["ingestion"][arm]["execution"]
            started = self.call(
                "POST",
                f"{self.project}/ingestion-previews",
                json={"execution": execution},
            )
            done = self.wait(f"{self.project}/source-previews/{started['id']}")
            self.state.setdefault("previews", {})[arm] = {
                "id": done["id"],
                "status": done["status"],
            }
            self.save()
            items = self.paged(f"{self.project}/source-previews/{done['id']}/items")
            by_file = {}
            for item in items:
                texts = []
                if item["processing_status"] == "succeeded":
                    texts = [
                        r["text"]
                        for r in self.paged(
                            f"{self.project}/source-previews/{done['id']}/items/"
                            f"{item['ordinal']}/representations",
                            params={"stage": "chunks"},
                        )
                    ]
                by_file[item["display_name"]] = {
                    "status": item["status"],
                    "processing_status": item["processing_status"],
                    "quality_decision": item["quality_decision"],
                    "error_code": item["error_code"],
                    "chunks": texts,
                }
            chunks[arm] = by_file
        (self.work / "preview_chunks.json").write_text(
            json.dumps(chunks, indent=2) + "\n"
        )
        report = preview_report(score.load_questions(), chunks)
        (self.work / "preview_report.md").write_text(report)
        print(report)

    def paged(self, path: str, params: dict | None = None) -> list[dict]:
        items, offset = [], 0
        while True:
            page = self.call(
                "GET", path, params={**(params or {}), "limit": 100, "offset": offset}
            )
            items.extend(page["items"])
            offset += len(page["items"])
            if not page["items"] or offset >= page["total"]:
                return items

    # index (paid) --------------------------------------------------------
    def index(self) -> None:
        runs = self.state.setdefault("ingestion_runs", {})
        for arm in ARMS:
            pipeline = self.state["ingestion"][arm]
            if runs.get(arm, {}).get("status") == "succeeded":
                continue
            if arm not in runs or runs[arm]["status"] in {"failed", "cancelled"}:
                started = self.call(
                    "POST",
                    f"{self.project}/pipelines/{pipeline['pipeline_id']}/versions/"
                    f"{pipeline['version_id']}/ingestion-runs",
                    json={},
                )
                runs[arm] = {"id": started["id"], "status": started["status"]}
                self.save()
            done = self.wait(
                f"{self.project}/ingestion-runs/{runs[arm]['id']}", deadline_s=3600
            )
            runs[arm] = {
                "id": done["id"],
                "status": done["status"],
                "error": done["error"],
                "index_id": done["published_index_id"],
                "index_version": done["published_index_version"],
                "chunk_count": done["chunk_count"],
                "processed_count": done["processed_count"],
                "failed_count": done["failed_count"],
            }
            self.save()
            if done["status"] != "succeeded":
                raise SystemExit(
                    f"{arm} ingestion ended {done['status']}: {done['error']}"
                )
        print(json.dumps(runs, indent=2))

    # ask (paid) ----------------------------------------------------------
    def ask(self) -> None:
        options = self.call("GET", f"{self.project}/pipelines/options")
        if ANSWER_MODEL not in options["models"]:
            raise SystemExit(f"{ANSWER_MODEL} is not an available answer model.")
        answers = self.state.setdefault("answer", {})
        for arm in ARMS:
            if arm in answers:
                continue
            index_id = self.state["ingestion_runs"][arm]["index_id"]
            saved = self.call(
                "POST",
                f"{self.project}/pipelines",
                json=answer_pipeline(arm, index_id, options["template"]),
            )
            answers[arm] = {
                "pipeline_id": saved["pipeline_id"],
                "version_id": saved["id"],
            }
            self.save()

        runs = self.state.setdefault(self.runs_key, {})
        for question in score.load_questions():
            for arm in self.arms:
                key = f"{question['id']}:{arm}"
                if key in runs and runs[key]["status"] != "running":
                    continue
                spent = sum(
                    r.get("cost_usd") or 0
                    for name, rounds in self.state.items()
                    if name.startswith("query_runs")
                    for r in rounds.values()
                )
                if spent > COST_CAP_USD:
                    raise SystemExit(f"Cost cap reached: ${spent:.4f} recorded.")
                if key not in runs:
                    pipeline = answers[arm]
                    started = self.call(
                        "POST",
                        f"{self.project}/pipelines/{pipeline['pipeline_id']}/versions/"
                        f"{pipeline['version_id']}/runs",
                        json={"question": question["question"]},
                    )
                    runs[key] = {"id": started["id"], "status": started["status"]}
                    self.save()
                done = self.wait_query(runs[key]["id"])
                runs[key] = {
                    "id": done["id"],
                    "status": done["status"],
                    "cost_usd": done["snapshot"].get("cost_usd"),
                }
                self.save()
                print(f"{key} {done['status']}", flush=True)
        print(
            f"Recorded generation cost: ${sum(r.get('cost_usd') or 0 for r in runs.values()):.4f}"
        )

    def wait_query(self, run_id: str) -> dict:
        started = time.monotonic()
        while True:
            value = self.call("GET", f"{self.project}/query-runs/{run_id}")
            if value["status"] != "running":
                return value
            if time.monotonic() - started > 300:
                raise SystemExit(f"Timed out waiting for query run {run_id}")
            time.sleep(1.5)

    # fetch ---------------------------------------------------------------
    def fetch(self) -> None:
        lines = []
        for question in score.load_questions():
            for arm in self.arms:
                run_id = self.state[self.runs_key][f"{question['id']}:{arm}"]["id"]
                run = self.call("GET", f"{self.project}/query-runs/{run_id}")
                snapshot = run["snapshot"]
                retrieved = (snapshot.get("retrieval_result") or {}).get("items") or []
                lines.append(
                    {
                        "question_id": question["id"],
                        "arm": arm,
                        "query_run_id": run["id"],
                        "status": run["status"],
                        "answer": run["answer"],
                        "error": run["error"],
                        "evidence": [
                            {
                                "rank": item["rank"],
                                "filename": item["filename"],
                                "page_number": item.get("page_number"),
                                "section_path": item.get("section_path") or [],
                                "text": item["text"],
                            }
                            for item in retrieved
                        ],
                        "citations": snapshot.get("citations"),
                        "context_format": snapshot.get("context_format"),
                        "latency_ms": snapshot.get("total_ms"),
                        "tokens": (snapshot.get("usage") or {}).get("total_tokens"),
                        "cost_usd": snapshot.get("cost_usd"),
                    }
                )
        name = "answers.jsonl" if self.round == 1 else f"answers_round{self.round}.jsonl"
        (self.work / name).write_text(
            "".join(json.dumps(line) + "\n" for line in lines)
        )
        print(f"Wrote {len(lines)} answers.")


def ingestion_execution(document_ids, version, arm, embedding, capabilities) -> dict:
    """The editor's defaults for a new pipeline; only the Extract version differs."""

    cleaning = capabilities["cleaning_profiles"][0]
    chunking = next(
        (
            p
            for p in capabilities.get("chunking_profiles", [])
            if p["id"] == "section_token" and p.get("recommended")
        ),
        {"settings": {}},
    )["settings"]
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
                "mode": "auto" if capabilities["ocr"]["available"] else "off",
                "languages": ["eng"],
                "rotate_pages": True,
                "deskew": True,
                "dpi": 200,
                "max_pages": min(capabilities["ocr"]["max_pages"], 50),
                "timeout_seconds": 30,
            },
            "tables": "preserve",
            "quality_policy": QUALITY_POLICY,
            "config_version": version,
        },
        {
            "id": "clean",
            "type": "clean",
            "normalize_whitespace": True,
            "repeated_boilerplate": [],
            "minimum_text_chars": 1,
            "maximum_text_chars": 2_000_000,
            "exact_content_deduplication": True,
            "profile": cleaning["id"],
            "config_version": cleaning["config_version"],
            "steps": cleaning.get("steps", []),
        },
        {
            "id": "chunk",
            "type": "chunk",
            "algorithm": "section_token",
            "unit": "tokens",
            "tokenizer_version": "utf8-byte-v1",
            "target_tokens": chunking.get("target_tokens", 600),
            "maximum_tokens": chunking.get("maximum_tokens", 800),
            "overlap_tokens": chunking.get("overlap_tokens", 80),
            "add_heading_context": chunking.get("add_heading_context", True),
            "config_version": "section-token-v1",
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
            "knowledge_set_name": f"Extract A/B {arm}",
        },
    ]
    order = [node["id"] for node in nodes]
    return {
        "schema_version": 2,
        "nodes": nodes,
        "edges": [{"source": a, "target": b} for a, b in zip(order, order[1:])],
    }


def answer_pipeline(arm: str, index_id: str, template: str) -> dict:
    nodes = [
        {"id": "question", "type": "question"},
        {
            "id": "retriever",
            "type": "retriever",
            "index_id": index_id,
            "retrieval": {"mode": "vector", "top_k": 5},
        },
        {"id": "prompt", "type": "prompt", "template": template},
        {
            "id": "llm",
            "type": "llm",
            "model": ANSWER_MODEL,
            "max_tokens": 512,
            "temperature": 0,
        },
        {"id": "answer", "type": "answer"},
    ]
    order = [node["id"] for node in nodes]
    return {
        "kind": "answer",
        "name": f"Extract A/B answers {arm}",
        "execution": {
            "schema_version": 2,
            "nodes": nodes,
            "edges": [{"source": a, "target": b} for a, b in zip(order, order[1:])],
        },
        "layout": {
            "positions": {node: {"x": 0, "y": i * 120} for i, node in enumerate(order)}
        },
    }


def preview_report(questions: list[dict], chunks: dict) -> str:
    lines = [
        "# Preview check (no embedding cost)",
        "",
        "| File | v1 status | v1 chunks | v2 status | v2 chunks |",
        "|---|---|---|---|---|",
    ]
    for name in chunks["v2"]:
        cells = [name]
        for arm in ARMS:
            item = chunks[arm].get(name, {})
            cells += [
                f"{item.get('processing_status')} / {item.get('quality_decision')} / {item.get('error_code') or ''}",
                str(len(item.get("chunks", []))),
            ]
        lines.append("| " + " | ".join(cells) + " |")
    lines += [
        "",
        "| Question | Category | v1 evidence in one chunk | v2 evidence in one chunk |",
        "|---|---|---|---|",
    ]
    totals = {arm: 0 for arm in ARMS}
    answerable = [q for q in questions if q["evidence_terms"]]
    for question in answerable:
        cells = [question["id"], question["category"]]
        for arm in ARMS:
            texts = chunks[arm].get(question["document"], {}).get("chunks", [])
            terms = [score.normalize(t) for t in question["evidence_terms"]]
            found = any(
                all(t in score.normalize(text) for t in terms) for text in texts
            )
            totals[arm] += found
            cells.append("yes" if found else "**no**")
        lines.append("| " + " | ".join(cells) + " |")
    lines += [
        "",
        f"Totals: v1 {totals['v1']}/{len(answerable)}, v2 {totals['v2']}/{len(answerable)}.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["setup", "preview", "index", "ask", "fetch"])
    parser.add_argument("work", type=Path)
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--arms", nargs="+", choices=list(ARMS))
    arguments = parser.parse_args()
    if arguments.stage in {"index", "ask"} and not arguments.allow_paid:
        sys.exit(
            f"The {arguments.stage} stage calls a paid provider; pass --allow-paid."
        )
    runner = Run(arguments.work, arguments.base_url, arguments.round, arguments.arms)
    getattr(runner, arguments.stage)()

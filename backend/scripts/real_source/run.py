"""Real-source ingestion test through the public API (spec 0006).

Stages; each reads and updates `<work>/state.json`, so a stage can be repeated
without duplicating uploads, pipelines, crawls, indexes or paid answers:

    python run.py setup    <work> --files <dir>       # project and the three files
    python run.py round    <work> R1 --allow-paid     # pipelines, ingestion runs, indexes
    python run.py measure  <work>                     # structure from the published indexes
    python run.py retrieve <work> R1 --allow-paid     # retrieval checks (query embeddings)
    python run.py ask      <work> R1 --allow-paid     # 20 end-to-end answers
    python run.py fetch    <work> R1                  # answers_R1.jsonl for blind scoring

Rounds R1-R6 are defined in ROUNDS. A round that does not apply to a track reuses
that track's R1 index (or the round named in its "reuse"). Website sources are
fetched once, in R1; later website rounds build from the R1 source snapshot.

Spec 0008 adds round A2 and a third track, "new", for the `files_v4` sources
(`setup` uploads them too); questions marked with a later "round" are skipped in
earlier rounds. Spec 0010 adds rounds A4s and A4p (A3 with the v2 chunkers).
Spec 0012 adds round A5: A4s with `structure-clean-v2` and `section-token-v3`,
and the websites rebuilt from the R1 snapshot with the same two versions; and A5p:
A4p with `structure-clean-v2` and `parent-child-v3`.
Spec 0014 adds round A6: A5 with `layout-ocr-v6` and `section-token-v4` (the
websites rebuilt again, since v4 also chunks website tables by row); and A6p: A5p
with `layout-ocr-v6` and `parent-child-v4`.
Spec 0015 adds rounds A7s and A7: A6 and A6p with the v5 chunkers (whole tables
beside their row passages) and the Rerank node (vector top 30, keep 5) in the
answer pipelines. Their `retrieve` stage reranks with the node's own code
(`app.pipelines.rerank`) and also records the plain vector top 5. Rounds A7s-plain
and A7-plain only `ask`: the same indexes with vector top 5 and no Rerank node.

Run inside the backend container against http://127.0.0.1:8000 (local auth mode).
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import re
import statistics
import sys
import time
import unicodedata
from pathlib import Path


HERE = Path(__file__).parent
PROJECT_NAME = "Real-source test 2026-10"
COST_CAP_USD = 2.5
# Upper-bound embedding estimate: indexed UTF-8 bytes (the app's conservative token
# unit) at OpenRouter's list price for openai/text-embedding-3-small on 2026-10-09.
EMBEDDING_USD_PER_MILLION = 0.02
ANSWER_MODEL = "google/gemini-2.5-flash"
TERMINAL = {"succeeded", "failed", "cancelled", "expired"}
RECOMMENDED_CHUNK = {"target_tokens": 600, "maximum_tokens": 800, "overlap_tokens": 80}
# Spec 0015: the Rerank node as measured in Slice 0 (D2).
RERANK = {"model": "google/gemini-2.5-flash-lite", "top_n": 5, "candidates": 30}

# The free R1 preview showed the recommended "Stop and let me review" (default-v1)
# blocks the Census report (19 tables flagged malformed). R1 keeps the recommended
# setting for both tracks; R1w is the files baseline with "Publish the other files
# and show warnings" (warn-v1), and every later files round changes one setting
# from R1w.
WARN = {"files": "warn-v1"}
ROUNDS = {
    "R1": {"tracks": ["web", "files"], "label": "Recommended settings (v2)"},
    "R1w": {"tracks": ["files"], "label": "Recommended, publish others with warnings",
            "quality": WARN},
    "R2": {"tracks": ["files"], "label": "Extractor layout-ocr-v1",
           "extract": {"config_version": "layout-ocr-v1"}, "quality": WARN},
    "R3a": {"tracks": ["files"], "label": "OCR 300 DPI, 100 pages",
            "ocr": {"dpi": 300, "max_pages": 100}, "quality": WARN},
    "R3b": {"tracks": ["files"], "label": "OCR off", "ocr": {"mode": "off"},
            "quality": WARN},
    "R4": {"tracks": ["files"], "label": "Table evidence plain text",
           "extract": {"tables": "plain_text"}, "quality": WARN},
    "R5": {"tracks": ["web"], "label": "Publish the other pages and show warnings",
           "quality": {"web": "warn-v1"}},
    "R6": {"tracks": ["web", "files"], "label": "Chunks 300/400/40",
           "chunk": {"target_tokens": 300, "maximum_tokens": 400, "overlap_tokens": 40},
           "quality": WARN},
    # Spec 0007 slice 7: the recommended settings after the fixes. Extractor v3 and
    # the per-source defaults ("Stop" for files, "Publish the others" for websites),
    # on the same website snapshot, files and questions as R1.
    "A1": {"tracks": ["web", "files"], "label": "After fixes: recommended (v3)",
           "extract": {"config_version": "layout-ocr-v3"}, "quality": {"web": "warn-v1"}},
    # Spec 0008 slice 6: extractor v4 with the simplified defaults (Maximum OCR pages
    # 100). The spec 0006 files keep "Stop"; the new files use "Publish the other
    # files and show warnings", because the Eurostat report is known to fail "Stop"
    # (charts read as oversized tables). v4 does not change the website reader, so
    # websites reuse the A1 index and are not asked again.
    "A2": {"tracks": ["files", "new"], "label": "Extract v4: recommended",
           "extract": {"config_version": "layout-ocr-v4"}, "ocr": {"max_pages": 100},
           "quality": {"new": "warn-v1"}, "reuse": {"web": "A1"}},
    # Spec 0009 slice 4: extractor v5. The spec 0008 files now use "Stop" as well
    # (v5 reads Eurostat's charts as text). The spec 0009 files (`files_v5`, track
    # "d2") use "Publish the other files and show warnings" so each file's own
    # outcome is visible. Websites again reuse the A1 index.
    "A3": {"tracks": ["files", "new", "d2"], "label": "Extract v5: recommended",
           "extract": {"config_version": "layout-ocr-v5"}, "ocr": {"max_pages": 100},
           "quality": {"d2": "warn-v1"}, "reuse": {"web": "A1"}},
    # Spec 0010 slice 3: A3 with the v2 chunkers, which append a section's short
    # first chunk to the chunk before it on the same page. Each takes the chunking
    # profile's settings from the server's capabilities, as a new draft does.
    "A4s": {"tracks": ["files", "new", "d2"], "label": "Search v3: section-token-v2",
            "extract": {"config_version": "layout-ocr-v5"}, "ocr": {"max_pages": 100},
            "quality": {"d2": "warn-v1"}, "reuse": {"web": "A1"},
            "chunk_profile": "section_token"},
    "A4p": {"tracks": ["files", "new", "d2"], "label": "Search v3: parent-child-v2",
            "extract": {"config_version": "layout-ocr-v5"}, "ocr": {"max_pages": 100},
            "quality": {"d2": "warn-v1"}, "reuse": {"web": "A1"},
            "chunk_profile": "parent_child"},
    # Spec 0012 slice 7: A4s with the new cleaning and chunking versions only. The
    # websites are rebuilt from the R1 snapshot too, since structure-clean-v2 mostly
    # changes website chrome removal; their baseline is A1.
    "A5": {"tracks": ["web", "files", "new", "d2"],
           "label": "Clean v2 and chunk v3: section-token-v3",
           "extract": {"config_version": "layout-ocr-v5"}, "ocr": {"max_pages": 100},
           "quality": {"web": "warn-v1", "d2": "warn-v1"},
           "chunk_profile": "section_token",
           "clean_version": "structure-clean-v2", "chunk_version": "section-token-v3"},
    "A5p": {"tracks": ["files", "new", "d2"],
            "label": "Clean v2 and chunk v3: parent-child-v3",
            "extract": {"config_version": "layout-ocr-v5"}, "ocr": {"max_pages": 100},
            "quality": {"d2": "warn-v1"}, "reuse": {"web": "A1"},
            "chunk_profile": "parent_child",
            "clean_version": "structure-clean-v2", "chunk_version": "parent-child-v3"},
    # Spec 0014 slice 5: A5 and A5p with extractor v6 (table rows kept, columns
    # named) and the v4 chunkers (one passage per table row). Baselines A5, A5p.
    "A6": {"tracks": ["web", "files", "new", "d2"],
           "label": "Table rows: layout-ocr-v6 and section-token-v4",
           "extract": {"config_version": "layout-ocr-v6"}, "ocr": {"max_pages": 100},
           "quality": {"web": "warn-v1", "d2": "warn-v1"},
           "chunk_profile": "section_token",
           "clean_version": "structure-clean-v2", "chunk_version": "section-token-v4"},
    "A6p": {"tracks": ["files", "new", "d2"],
            "label": "Table rows: layout-ocr-v6 and parent-child-v4",
            "extract": {"config_version": "layout-ocr-v6"}, "ocr": {"max_pages": 100},
            "quality": {"d2": "warn-v1"}, "reuse": {"web": "A1"},
            "chunk_profile": "parent_child",
            "clean_version": "structure-clean-v2", "chunk_version": "parent-child-v4"},
    # Spec 0015 slice 6: A6 and A6p with the v5 chunkers (the whole table stays beside
    # its row passages, title rows name the columns) and the Rerank node. Baselines
    # A5 (the current defaults) and A6p (the best so far).
    "A7s": {"tracks": ["web", "files", "new", "d2"],
            "label": "Rerank and v5 tables: section-token-v5",
            "extract": {"config_version": "layout-ocr-v6"}, "ocr": {"max_pages": 100},
            "quality": {"web": "warn-v1", "d2": "warn-v1"},
            "chunk_profile": "section_token",
            "clean_version": "structure-clean-v2", "chunk_version": "section-token-v5",
            "rerank": RERANK},
    "A7": {"tracks": ["files", "new", "d2"],
           "label": "Rerank and v5 tables: parent-child-v5",
           "extract": {"config_version": "layout-ocr-v6"}, "ocr": {"max_pages": 100},
           "quality": {"d2": "warn-v1"}, "reuse": {"web": "A1"},
           "chunk_profile": "parent_child",
           "clean_version": "structure-clean-v2", "chunk_version": "parent-child-v5",
           "rerank": RERANK},
    # The A7s and A7 indexes answered without the Rerank node (vector top 5), so the
    # chunkers' effect on answers shows apart from the reranker's. They build nothing;
    # "ask" names the tracks they answer.
    "A7s-plain": {"tracks": [], "ask": ["web", "files", "new", "d2"],
                  "label": "A7s indexes without reranking",
                  "reuse": {"web": "A7s", "files": "A7s", "new": "A7s", "d2": "A7s"}},
    "A7-plain": {"tracks": [], "ask": ["files", "new", "d2"],
                 "label": "A7 indexes without reranking",
                 "reuse": {"web": "A1", "files": "A7", "new": "A7", "d2": "A7"}},
}
# The index a track falls back to when a round does not rebuild it.
BASELINE = {"web": "R1", "files": "R1w"}
MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
# Source group, state key and track for each set of files.
FILE_GROUPS = (
    ("files", "documents", "files"),
    ("files_v4", "documents_v4", "new"),
    ("files_v5", "documents_v5", "d2"),
)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("­", "")
    value = re.sub(r"[‐-―−]", "-", value)
    value = value.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", value).strip().casefold()


def load_questions() -> list[dict]:
    lines = (HERE / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def load_sources() -> dict:
    return json.loads((HERE / "sources.json").read_text(encoding="utf-8"))


def track_of(source_id: str, sources: dict) -> str:
    if source_id.startswith("W"):
        return "web"
    for group, _, track in FILE_GROUPS:
        if source_id in sources.get(group, {}):
            return track
    return "files"


def first_hit(evidence: list[dict], phrases: list[str]) -> int | None:
    """The rank of the first supplied text that holds every reference phrase."""

    for item in evidence:
        text = normalize(item.get("text") or "")
        if phrases and all(p in text for p in phrases):
            return item["rank"]
    return None


def reranker(stack: ExitStack, project_id: str, spec: dict):
    """The Rerank node's own call, with the project's key and approved models bound
    as a query run binds them. Needs the app, so it runs in the backend container."""

    sys.path.insert(0, str(HERE.parents[1]))
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.db.session import engine
    from app.pipelines import rerank
    from app.providers import generation
    from app.services import provider_credentials

    session = stack.enter_context(Session(engine))
    stack.enter_context(provider_credentials.bound_for_project(session, UUID(project_id)))
    provider = generation.provider_for()

    def call(question: str, items: list[dict]):
        return rerank.rerank(
            question, items, node_id="rerank", model=spec["model"],
            top_n=spec["top_n"], provider=provider,
        )

    return call


def in_round(question: dict, round_id: str) -> bool:
    """A question written for a later round is not part of earlier rounds."""

    introduced = question.get("round")
    order = list(ROUNDS)
    return not introduced or order.index(introduced) <= order.index(round_id)


class Run:
    def __init__(self, work: Path, base_url: str):
        self.work = work
        self.work.mkdir(parents=True, exist_ok=True)
        self.state_path = work / "state.json"
        self.state = (
            json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        )
        import httpx  # only the API stages need it; workbook.py imports this module

        self.client = httpx.Client(base_url=base_url, timeout=180)
        self.sources = load_sources()

    def save(self) -> None:
        self.state_path.write_text(json.dumps(self.state, indent=2) + "\n")

    def call(self, method: str, path: str, **kwargs):
        response = self.client.request(method, path, **kwargs)
        for _ in range(10):
            # The app's local embedding request budget resets every minute.
            if response.status_code != 503 or "budget" not in response.text:
                break
            time.sleep(65)
            response = self.client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise SystemExit(
                f"{method} {path} -> {response.status_code}: {response.text[:2000]}"
            )
        return response.json() if response.content else None

    @property
    def project(self) -> str:
        return f"/api/projects/{self.state['project_id']}"

    def wait(self, path: str, deadline_s: int = 3600, pause: float = 5):
        started = time.monotonic()
        while True:
            value = self.call("GET", path)
            if value["status"] in TERMINAL:
                return value
            if time.monotonic() - started > deadline_s:
                raise SystemExit(f"Timed out waiting for {path}")
            time.sleep(pause)

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

    # cost ----------------------------------------------------------------
    def spent(self) -> float:
        embedding = sum(
            r.get("embedding_estimate_usd") or 0 for r in self.state.get("runs", {}).values()
        )
        queries = sum(
            r.get("query_embedding_estimate_usd") or 0
            for r in self.state.get("retrieval_cost", {}).values()
        )
        # Spec 0015: rerank calls of the retrieval checks, provider-reported.
        queries += sum(
            (r.get("rerank") or {}).get("cost_usd") or 0
            for rounds in self.state.get("retrieval", {}).values()
            for r in rounds.values()
        )
        answers = sum(
            r.get("cost_usd") or 0
            for rounds in self.state.get("answers", {}).values()
            for r in rounds.values()
        )
        return embedding + queries + answers

    def check_cap(self, next_estimate: float = 0) -> None:
        spent = self.spent()
        if spent + next_estimate > COST_CAP_USD:
            raise SystemExit(
                f"Cost cap: ${spent:.4f} spent, next step ~${next_estimate:.4f}, "
                f"cap ${COST_CAP_USD:.2f}."
            )

    # setup ---------------------------------------------------------------
    def setup(self, files: Path) -> None:
        if "project_id" not in self.state:
            project = self.call(
                "POST",
                "/api/projects",
                json={
                    "name": PROJECT_NAME,
                    "description": "Spec 0006: real websites and files, settings verdict.",
                },
            )
            self.state["project_id"] = project["id"]
            self.save()
        for group, key, _ in FILE_GROUPS:
            documents = self.state.setdefault(key, {})
            for source_id, source in self.sources.get(group, {}).items():
                if source_id in documents:
                    continue
                path = files / source["filename"]
                data = path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                if digest != source["sha256"]:
                    raise SystemExit(f"{path.name}: SHA-256 {digest} differs from sources.json.")
                uploaded = self.call(
                    "POST",
                    f"{self.project}/documents",
                    files={"file": (source["filename"], data, MEDIA_TYPES[path.suffix])},
                )
                documents[source_id] = {"id": uploaded["id"], "filename": source["filename"]}
                self.save()
        documents = {
            source_id: document
            for _, key, _ in FILE_GROUPS
            for source_id, document in self.state.get(key, {}).items()
        }
        self.state["embedding"] = self.call("GET", f"{self.project}/embedding-settings")[
            "config"
        ]
        self.state["capabilities"] = self.call(
            "GET", f"{self.project}/ingestion-capabilities"
        )
        self.save()
        print(json.dumps({"project_id": self.state["project_id"], "documents": documents}, indent=2))

    # pipelines -----------------------------------------------------------
    def execution(self, track: str, round_id: str) -> dict:
        spec = ROUNDS[round_id]
        capabilities = self.state["capabilities"]
        embedding = self.state["embedding"]
        quality = spec.get("quality", {}).get(track, "default-v1")
        policy = next(
            p["settings"] for p in capabilities["quality_policies"] if p["id"] == quality
        )
        ocr = {
            "mode": "auto" if capabilities["ocr"]["available"] else "off",
            "languages": ["eng"],
            "rotate_pages": True,
            "deskew": True,
            "dpi": 200,
            "max_pages": min(capabilities["ocr"]["max_pages"], 50),
            "timeout_seconds": 30,
            **spec.get("ocr", {}),
        }
        extract = {
            "id": "extract",
            "type": "extract",
            "strategy": "auto",
            "ocr": ocr,
            "tables": "preserve",
            "quality_policy": json.loads(json.dumps(policy)),
            "config_version": "layout-ocr-v2",
            **spec.get("extract", {}),
        }
        cleaning = capabilities["cleaning_profiles"][0]
        chunk = {
            "id": "chunk",
            "type": "chunk",
            "algorithm": "section_token",
            "unit": "tokens",
            "tokenizer_version": "utf8-byte-v1",
            **RECOMMENDED_CHUNK,
            **spec.get("chunk", {}),
            "add_heading_context": True,
            "config_version": "section-token-v1",
        }
        if "chunk_profile" in spec:
            profile = next(
                p for p in capabilities["chunking_profiles"] if p["id"] == spec["chunk_profile"]
            )
            chunk = {
                "id": "chunk",
                "type": "chunk",
                "algorithm": spec["chunk_profile"],
                "unit": "tokens",
                **profile["settings"],
            }
        if "chunk_version" in spec:
            chunk["config_version"] = spec["chunk_version"]
        if track == "web":
            sources = [
                {"id": "source" if i == 0 else f"source-{i + 1}", "type": "source",
                 "config": config}
                for i, config in enumerate(self.sources["websites"].values())
            ]
        else:
            group = next(key for _, key, name in FILE_GROUPS if name == track)
            ids = [d["id"] for d in self.state[group].values()]
            sources = [{
                "id": "source",
                "type": "source",
                "config": {"kind": "existing_files", "document_ids": ids},
            }]
        nodes = [
            *sources,
            extract,
            {
                "id": "clean",
                "type": "clean",
                "normalize_whitespace": True,
                "repeated_boilerplate": [],
                "minimum_text_chars": 1,
                "maximum_text_chars": 2_000_000,
                "exact_content_deduplication": True,
                "profile": cleaning["id"],
                "config_version": spec.get("clean_version", cleaning["config_version"]),
                "steps": cleaning.get("steps", []),
            },
            chunk,
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
                "knowledge_set_name": f"Real-source {track} {round_id}",
            },
        ]
        chain = ["extract", "clean", "chunk", "embed", "publish"]
        edges = [{"source": s["id"], "target": "extract"} for s in sources]
        edges += [{"source": a, "target": b} for a, b in zip(chain, chain[1:])]
        return {
            "schema_version": 2,
            "index_layout": "merged",
            "nodes": nodes,
            "edges": edges,
        }

    def layout(self, execution: dict) -> dict:
        positions, source_column = {}, 0
        chain_y = 160
        for node in execution["nodes"]:
            if node["type"] == "source":
                positions[node["id"]] = {"x": source_column * 340, "y": 40}
                source_column += 1
            else:
                positions[node["id"]] = {"x": 0, "y": chain_y}
                chain_y += 116
        return {"positions": positions}

    # round (paid) --------------------------------------------------------
    def round(self, round_id: str) -> None:
        spec = ROUNDS[round_id]
        pipelines = self.state.setdefault("pipelines", {})
        runs = self.state.setdefault("runs", {})
        for track in spec["tracks"]:
            key = f"{track}:{round_id}"
            if runs.get(key, {}).get("status") == "succeeded":
                continue
            if runs.get(key, {}).get("status") in {"failed", "cancelled"}:
                print(f"{key} already ended {runs[key]['status']}; not repeated.")
                continue
            self.check_cap(0.15)
            if key not in pipelines:
                # Read the server's current defaults: a copy saved at setup ran A1
                # with the pre-spec-0007 cleaning steps (spec 0008, B3).
                self.state["capabilities"] = self.call(
                    "GET", f"{self.project}/ingestion-capabilities"
                )
                execution = self.execution(track, round_id)
                saved = self.call(
                    "POST",
                    f"{self.project}/pipelines",
                    json={
                        "kind": "ingestion",
                        "name": f"Real-source {track} {round_id}",
                        "execution": execution,
                        "layout": self.layout(execution),
                    },
                )
                pipelines[key] = {"pipeline_id": saved["pipeline_id"], "version_id": saved["id"]}
                self.save()
            if key not in runs:
                body = {}
                if track == "web" and round_id != "R1":
                    snapshot = runs["web:R1"].get("source_snapshot_id")
                    if not snapshot:
                        raise SystemExit("web R1 has no source snapshot to reuse.")
                    body = {"source_input": {"kind": "snapshot", "source_snapshot_id": snapshot}}
                pipeline = pipelines[key]
                started = self.call(
                    "POST",
                    f"{self.project}/pipelines/{pipeline['pipeline_id']}/versions/"
                    f"{pipeline['version_id']}/ingestion-runs",
                    json=body,
                )
                runs[key] = {"id": started["id"], "status": started["status"],
                             "started": time.time()}
                self.save()
            done = self.wait(f"{self.project}/ingestion-runs/{runs[key]['id']}", deadline_s=5400)
            items = self.paged(f"{self.project}/ingestion-runs/{done['id']}/items")
            record = {
                "id": done["id"],
                "status": done["status"],
                "error": done["error"],
                "index_id": done["published_index_id"],
                "source_snapshot_id": done.get("source_snapshot_id"),
                "chunk_count": done["chunk_count"],
                "processed_count": done["processed_count"],
                "failed_count": done["failed_count"],
                "discovered_count": done.get("discovered_count"),
                "started_at": done.get("started_at"),
                "finished_at": done.get("finished_at"),
                # Provider-reported by the app (spec 0007, X8); None when unknown.
                "embedding_usage": done.get("embedding_usage"),
                "items": [
                    {k: item.get(k) for k in (
                        "filename", "display_name", "source_url", "canonical_location",
                        "status", "outcome", "reason", "error", "is_optional",
                        "chunk_count")}
                    for item in items
                ],
            }
            if done["published_index_id"]:
                records = self.paged(
                    f"{self.project}/indexes/{done['published_index_id']}/records"
                )
                record["embedded_bytes"] = sum(
                    len(r["embedding_text"].encode("utf-8")) for r in records
                )
                record["embedding_estimate_usd"] = round(
                    record["embedded_bytes"] / 1e6 * EMBEDDING_USD_PER_MILLION, 6
                )
                (self.work / f"records_{track}_{round_id}.json").write_text(
                    json.dumps(records) + "\n"
                )
            runs[key] = record
            self.save()
            print(f"{key}: {done['status']} chunks={done['chunk_count']} "
                  f"index={done['published_index_id']} error={done['error']}")
        print(f"Estimated spend so far: ${self.spent():.4f}")

    def index_for(self, track: str, round_id: str) -> tuple[str | None, str]:
        """The index a round uses for a track, and the round that built it."""

        spec = ROUNDS[round_id]
        built = (
            round_id
            if track in spec["tracks"]
            else spec.get("reuse", {}).get(track, BASELINE.get(track))
        )
        run = self.state.get("runs", {}).get(f"{track}:{built}", {})
        return run.get("index_id"), built

    # measure (free) ------------------------------------------------------
    def measure(self) -> None:
        sources = self.sources
        origin_to_source = {
            config["allowed_origins"][0].rstrip("/"): source_id
            for source_id, config in sources["websites"].items()
        }
        filename_to_source = {
            f["filename"]: sid
            for group, _, _ in FILE_GROUPS
            for sid, f in sources.get(group, {}).items()
        }
        track_sources = {
            "web": sources["websites"],
            **{track: sources.get(group, {}) for group, _, track in FILE_GROUPS},
        }
        table_line = re.compile(r"^\|.*\|\s*$", re.MULTILINE)
        structure = []
        previous_path = self.work / "structure.json"
        previous = json.loads(previous_path.read_text()) if previous_path.exists() else []
        for key, run in self.state.get("runs", {}).items():
            track, round_id = key.split(":")
            path = self.work / f"records_{track}_{round_id}.json"
            kept = [r for r in previous if (r["track"], r["round"]) == (track, round_id)]
            if not path.exists() and kept:
                # Records of an earlier session are not kept; reuse its measured rows.
                structure.extend(kept)
                continue
            per_source: dict[str, list[dict]] = {}
            if path.exists():
                for record in json.loads(path.read_text()):
                    if track == "web":
                        url = record.get("source_url") or ""
                        origin = "/".join(url.split("/")[:3])
                        source_id = origin_to_source.get(origin, "W?")
                    else:
                        source_id = filename_to_source.get(record["filename"], "F?")
                    per_source.setdefault(source_id, []).append(record)
            for source_id in track_sources[track]:
                records = per_source.get(source_id, [])
                tokens = [r.get("token_count") or 0 for r in records]
                with_section = sum(1 for r in records if r.get("section_path"))
                tables = [r for r in records if len(table_line.findall(r["text"])) >= 2]
                header_tables = [
                    r for r in tables
                    if re.search(r"^\|.*\|\s*\n\|\s*-{3}", r["text"], re.MULTILINE)
                    or (r.get("embedding_prefix") or "")
                ]
                units = {
                    (r.get("source_url") if track == "web" else r.get("page_number"))
                    for r in records
                }
                items = [
                    i for i in run.get("items", [])
                    if (track != "web" and filename_to_source.get(i.get("filename")) == source_id)
                    or (track == "web" and origin_to_source.get(
                        "/".join(str(i.get("source_url") or i.get("canonical_location") or "").split("/")[:3])
                    ) == source_id)
                ]
                structure.append({
                    "round": round_id,
                    "track": track,
                    "source": source_id,
                    "run_status": run.get("status"),
                    "items": len(items),
                    "items_ready": sum(i.get("status") in {"ready", "succeeded"} for i in items),
                    "items_failed": sum(i.get("status") == "failed" for i in items),
                    "items_excluded": sum(i.get("status") == "excluded" for i in items),
                    "items_skipped": sum(i.get("status") == "skipped" for i in items),
                    "pages_or_urls_indexed": len({u for u in units if u is not None}),
                    "chunks": len(records),
                    "chunk_tokens_median": statistics.median(tokens) if tokens else None,
                    "chunk_tokens_max": max(tokens) if tokens else None,
                    "chunks_with_section_percent": round(100 * with_section / len(records), 1) if records else None,
                    "table_chunks": len(tables),
                    "table_chunks_with_header": len(header_tables),
                    "heading_only_chunks": sum(
                        1 for r in records if len(r["text"]) < 80 and "\n" not in r["text"].strip()
                    ),
                })
        (self.work / "structure.json").write_text(json.dumps(structure, indent=2) + "\n")
        for row in structure:
            print(json.dumps(row))

    # retrieve (paid: query embeddings) -----------------------------------
    def retrieve(self, round_id: str) -> None:
        questions = [q for q in load_questions() if in_round(q, round_id)]
        results = self.state.setdefault("retrieval", {}).setdefault(round_id, {})
        rerank_spec = ROUNDS[round_id].get("rerank")
        query_bytes = 0
        with ExitStack() as stack:
            rerank_call = (
                reranker(stack, self.state["project_id"], rerank_spec) if rerank_spec else None
            )
            for question in questions:
                if question["id"] in results:
                    continue
                if self.retrieve_one(question, round_id, results, rerank_spec, rerank_call):
                    query_bytes += len(question["question"].encode("utf-8"))
        cost = self.state.setdefault("retrieval_cost", {})
        previous = cost.get(round_id, {}).get("query_bytes", 0)
        cost[round_id] = {
            "query_bytes": previous + query_bytes,
            "query_embedding_estimate_usd": round(
                (previous + query_bytes) / 1e6 * EMBEDDING_USD_PER_MILLION, 6
            ),
        }
        self.save()
        answerable = [q for q in questions if q["phrases"]]
        hit1 = sum(results[q["id"]].get("hit_at_1", False) for q in answerable)
        hit5 = sum(results[q["id"]].get("hit_at_5", False) for q in answerable)
        print(f"{round_id}: hit@1 {hit1}/{len(answerable)}, hit@5 {hit5}/{len(answerable)}")
        if rerank_spec:
            plain = sum(
                results[q["id"]].get("vector_first_hit_rank") is not None for q in answerable
            )
            print(f"{round_id} without reranking: hit@5 {plain}/{len(answerable)}")
        print(f"Estimated spend so far: ${self.spent():.4f}")

    def retrieve_one(self, question, round_id, results, rerank_spec, rerank_call) -> bool:
        track = track_of(question["source"], self.sources)
        index_id, built = self.index_for(track, round_id)
        if not index_id:
            results[question["id"]] = {"index_round": built, "status": "no index"}
            return False
        self.check_cap(0.003 if rerank_spec else 0.001)
        response = self.call(
            "POST",
            f"{self.project}/retrieval",
            json={"index_id": index_id, "query": question["question"],
                  "retrieval": {"mode": "vector",
                                "top_k": rerank_spec["candidates"] if rerank_spec else 5}},
        )
        evidence = response.get("evidence") or response.get("items") or []
        phrases = [normalize(p) for p in question["phrases"]]
        extra = {}
        if rerank_spec:
            # The plain vector top 5 of the same index, and where the answer sits among
            # all the candidates the reranker could choose from.
            extra = {
                "vector_first_hit_rank": first_hit(evidence[:5], phrases),
                "candidate_hit_rank": first_hit(evidence, phrases),
            }
            evidence, record = rerank_call(question["question"], evidence)
            extra["rerank"] = {
                **{k: record[k] for k in (
                    "status", "message", "candidate_count", "candidates_read",
                    "returned_count", "actual_model", "cost_usd", "rerank_ms")},
                "order": [item["retriever_rank"] for item in record["order"]],
            }
        hit = first_hit(evidence, phrases)
        results[question["id"]] = {
            "index_round": built,
            "status": "ok",
            "first_hit_rank": hit,
            "hit_at_1": hit == 1,
            "hit_at_5": hit is not None,
            **extra,
            "top": [
                {
                    "rank": item["rank"],
                    **({"retriever_rank": item["retriever_rank"]}
                       if "retriever_rank" in item else {}),
                    "source": item.get("source_url") or item.get("filename"),
                    "page": item.get("page_number"),
                    "section": " > ".join(item.get("section_path") or []),
                    "distance": item.get("cosine_distance"),
                    "text": (item.get("text") or "")[:300],
                }
                for item in evidence
            ],
        }
        self.save()
        return True

    # ask (paid) ----------------------------------------------------------
    def ask(self, round_id: str) -> None:
        options = self.call("GET", f"{self.project}/pipelines/options")
        if ANSWER_MODEL not in options["models"]:
            raise SystemExit(f"{ANSWER_MODEL} is not an available answer model.")
        answer_pipelines = self.state.setdefault("answer_pipelines", {})
        answers = self.state.setdefault("answers", {}).setdefault(round_id, {})
        rerank_spec = ROUNDS.get(round_id, {}).get("rerank")
        if rerank_spec and rerank_spec["model"] not in options["models"]:
            raise SystemExit(f"{rerank_spec['model']} is not an approved model.")
        for question in load_questions():
            if not question["ask"] or not in_round(question, round_id):
                continue
            track = track_of(question["source"], self.sources)
            asked = ROUNDS[round_id].get("ask", ROUNDS[round_id]["tracks"])
            if round_id != "R1" and track not in asked:
                continue
            index_id, built = self.index_for(track, round_id)
            if not index_id:
                answers[question["id"]] = {"status": "no index", "index_round": built}
                continue
            key = f"{track}:{built}" + ("+rerank" if rerank_spec else "")
            if key not in answer_pipelines:
                saved = self.call(
                    "POST",
                    f"{self.project}/pipelines",
                    json=answer_pipeline(
                        f"Real-source answers {key}", index_id, options["template"], rerank_spec
                    ),
                )
                answer_pipelines[key] = {"pipeline_id": saved["pipeline_id"], "version_id": saved["id"]}
                self.save()
            existing = answers.get(question["id"])
            if existing and existing["status"] not in {"running", "queued"}:
                continue
            self.check_cap(0.012)
            if not existing:
                pipeline = answer_pipelines[key]
                started = self.call(
                    "POST",
                    f"{self.project}/pipelines/{pipeline['pipeline_id']}/versions/"
                    f"{pipeline['version_id']}/runs",
                    json={"question": question["question"]},
                )
                answers[question["id"]] = {"id": started["id"], "status": started["status"],
                                           "index_round": built}
                self.save()
            done = self.wait_query(answers[question["id"]]["id"])
            answer_cost = done["snapshot"].get("cost_usd")
            # The run's cost is the answer call's; a Rerank node reports its own.
            rerank = done["snapshot"].get("rerank") or {}
            answers[question["id"]].update(
                status=done["status"],
                cost_usd=None if answer_cost is None
                else answer_cost + (rerank.get("cost_usd") or 0),
                **({"rerank_status": rerank.get("status"),
                    "rerank_cost_usd": rerank.get("cost_usd")} if rerank else {}),
            )
            self.save()
            print(f"{round_id} {question['id']} {done['status']}", flush=True)
        print(f"Estimated spend so far: ${self.spent():.4f}")

    def wait_query(self, run_id: str) -> dict:
        started = time.monotonic()
        while True:
            value = self.call("GET", f"{self.project}/query-runs/{run_id}")
            if value["status"] not in {"running", "queued"}:
                return value
            if time.monotonic() - started > 300:
                raise SystemExit(f"Timed out waiting for query run {run_id}")
            time.sleep(1.5)

    def fetch(self, round_id: str) -> None:
        lines = []
        questions = {q["id"]: q for q in load_questions()}
        for question_id, answer in self.state.get("answers", {}).get(round_id, {}).items():
            if "id" not in answer:
                lines.append({"question_id": question_id, "round": round_id, **answer})
                continue
            run = self.call("GET", f"{self.project}/query-runs/{answer['id']}")
            snapshot = run["snapshot"]
            retrieved = (snapshot.get("retrieval_result") or {}).get("items") or []
            rerank = snapshot.get("rerank")
            if rerank:
                # The prompt got the reranked passages, in the reranked order.
                by_rank = {item["rank"]: item for item in retrieved}
                retrieved = [
                    {**by_rank[step["retriever_rank"]], "rank": step["rerank_rank"],
                     "retriever_rank": step["retriever_rank"]}
                    for step in rerank["order"]
                ]
            lines.append({
                "question_id": question_id,
                "round": round_id,
                "index_round": answer.get("index_round"),
                "question": questions[question_id]["question"],
                "status": run["status"],
                "answer": run["answer"],
                "error": run["error"],
                "citations": snapshot.get("citations"),
                "evidence": [
                    {
                        "rank": item["rank"],
                        **({"retriever_rank": item["retriever_rank"]}
                           if "retriever_rank" in item else {}),
                        "source": item.get("source_url") or item.get("filename"),
                        "section": " > ".join(item.get("section_path") or []),
                        "text": item["text"],
                    }
                    for item in retrieved
                ],
                "latency_ms": snapshot.get("total_ms"),
                "cost_usd": answer.get("cost_usd", snapshot.get("cost_usd")),
                **({"rerank": {k: rerank.get(k) for k in (
                    "status", "message", "model", "cost_usd", "rerank_ms")}}
                   if rerank else {}),
            })
        (self.work / f"answers_{round_id}.jsonl").write_text(
            "".join(json.dumps(line) + "\n" for line in lines)
        )
        print(f"Wrote {len(lines)} answers for {round_id}.")


def answer_pipeline(name: str, index_id: str, template: str, rerank: dict | None = None) -> dict:
    nodes = [
        {"id": "question", "type": "question"},
        {"id": "retriever", "type": "retriever", "index_id": index_id,
         "retrieval": {"mode": "vector", "top_k": rerank["candidates"] if rerank else 5}},
        # Spec 0015: the optional Rerank node (answer graph schema 3).
        *([{"id": "rerank", "type": "rerank", "model": rerank["model"],
            "top_n": rerank["top_n"]}] if rerank else []),
        {"id": "prompt", "type": "prompt", "template": template},
        {"id": "llm", "type": "llm", "model": ANSWER_MODEL, "max_tokens": 512,
         "temperature": 0},
        {"id": "answer", "type": "answer"},
    ]
    order = [node["id"] for node in nodes]
    return {
        "kind": "answer",
        "name": name,
        "execution": {
            "schema_version": 3 if rerank else 2,
            "nodes": nodes,
            "edges": [{"source": a, "target": b} for a, b in zip(order, order[1:])],
        },
        "layout": {"positions": {n: {"x": 0, "y": i * 120} for i, n in enumerate(order)}},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["setup", "round", "measure", "retrieve", "ask", "fetch"])
    parser.add_argument("work", type=Path)
    parser.add_argument("round_id", nargs="?", choices=list(ROUNDS))
    parser.add_argument("--files", type=Path)
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    arguments = parser.parse_args()
    if arguments.stage in {"round", "retrieve", "ask"} and not arguments.allow_paid:
        sys.exit(f"The {arguments.stage} stage calls a paid provider; pass --allow-paid.")
    if arguments.stage in {"round", "retrieve", "ask", "fetch"} and not arguments.round_id:
        sys.exit("Name the round, for example R1.")
    runner = Run(arguments.work, arguments.base_url)
    if arguments.stage == "setup":
        if not arguments.files:
            sys.exit("Pass --files <folder with the downloaded files>.")
        runner.setup(arguments.files)
    elif arguments.stage == "measure":
        runner.measure()
    else:
        getattr(runner, arguments.stage)(arguments.round_id)

"""Spec 0014 Slice 0: table rows kept and findable, measured before building on.

For the Census report (F2) and the GAO testimony (G3), the document is processed
again with `layout-ocr-v6` and v4 chunking through the worker's own extract, clean
and chunk path, with the round's saved settings otherwise unchanged. Its passages
replace the document's passages in the round's index; every other passage keeps
its stored embedding. Every answerable question of the two tracks (F1-F3 and
G1-G8) is then ranked over the old and the new passage set:

- vector: cosine similarity with the question's embedding (same model);
- bm25: the spec 0013 Slice 0 BM25 over each passage's searched text;
- hybrid: reciprocal-rank fusion of both top-50 lists (weight 0.5, constant 60).

A question is found when one supplied text (the parent for a child) among the top
5 holds all its reference phrases, the real-source harness's rule. Paid work:
embeddings of the new passages and of the questions (well under $0.05).

    python scripts/table_rows/slice0.py <state.json> <out.json> --allow-paid
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "real_source"))
from run import load_questions, load_sources, normalize, track_of  # noqa: E402

from app.models.document import Document  # noqa: E402
from app.providers.embeddings import EmbeddingConfig  # noqa: E402
from app.providers.openrouter import OpenRouterEmbeddings  # noqa: E402
from app.services import artifact_storage, provider_credentials  # noqa: E402
from app.workers.processing import _v2_chunks  # noqa: E402

K1, B, CONSTANT, WEIGHT, DEPTH, TOP = 1.2, 0.75, 60, 0.5, 50, 5
# Upper bound: UTF-8 bytes at the list price of text-embedding-3-small.
USD_PER_BYTE = 0.02 / 1_000_000
TARGETS = {"F2": ("files", "documents"), "G3": ("d2", "documents_v5")}
ROUNDS = {
    "A5": {"section_token": "section-token-v4"},
    "A5p": {"parent_child": "parent-child-v4"},
}

MEMBERS = text(
    """
    SELECT c.run_id::text AS run_id, c.ordinal, pr.document_id::text AS document_id,
           coalesce(c.embedding_text, c.text) AS searched,
           coalesce(p.text, c.text) AS supplied, ic.embedding::text AS vector
    FROM index_chunks ic
    JOIN chunks c ON c.run_id = ic.run_id AND c.ordinal = ic.ordinal
    JOIN processing_runs pr ON pr.id = c.run_id
    LEFT JOIN chunks p ON p.run_id = c.run_id AND p.ordinal = c.parent_ordinal
    WHERE ic.index_id = :index_id
    """
)
CONFIG = text(
    """
    SELECT DISTINCT pr.processing_config FROM index_chunks ic
    JOIN processing_runs pr ON pr.id = ic.run_id
    WHERE ic.index_id = :index_id AND pr.document_id = :document_id
    """
)
LEXEMES = text(
    "SELECT lexeme, coalesce(array_length(positions, 1), 1) AS tf "
    "FROM unnest(to_tsvector('simple', :value))"
)


def unit(vector):
    value = numpy.asarray(vector, dtype=numpy.float64)
    return value / (numpy.linalg.norm(value) or 1.0)


def matrix(passages):
    keys = sorted(passages)
    return keys, numpy.vstack([passages[key]["unit"] for key in keys])


def cosine_ranking(query, keys_and_matrix):
    keys, vectors = keys_and_matrix
    scores = vectors @ query
    order = sorted(range(len(keys)), key=lambda i: (-scores[i], keys[i]))
    return [keys[i] for i in order[:DEPTH]]


def bm25_ranking(terms, passages):
    count = len(passages)
    average = sum(item["length"] for item in passages.values()) / max(count, 1)
    postings = defaultdict(dict)
    for key, item in passages.items():
        for term, tf in item["tf"].items():
            postings[term][key] = tf
    scores = Counter()
    for term in set(terms):
        found = postings.get(term)
        if not found:
            continue
        idf = math.log(1 + (count - len(found) + 0.5) / (len(found) + 0.5))
        for key, tf in found.items():
            norm = K1 * (1 - B + B * passages[key]["length"] / average)
            scores[key] += idf * tf * (K1 + 1) / (tf + norm)
    ranked = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
    return [key for key, _ in ranked[:DEPTH]]


def fuse(vector, keyword):
    scores = Counter()
    for weight, keys in ((WEIGHT, vector), (1 - WEIGHT, keyword)):
        for rank, key in enumerate(keys, 1):
            scores[key] += weight / (CONSTANT + rank)
    return [key for key, _ in sorted(scores.items(), key=lambda p: (-p[1], p[0]))]


def first_hit(keys, passages, phrases):
    for rank, key in enumerate(keys[:TOP], 1):
        value = normalize(passages[key]["supplied"])
        if all(phrase in value for phrase in phrases):
            return rank
    return None


def lexemes(connection, value):
    rows = connection.execute(LEXEMES, {"value": value}).all()
    return {row[0]: row[1] for row in rows}


def embed(adapter, values):
    vectors = []
    for start in range(0, len(values), 64):
        vectors.extend(adapter.embed(values[start : start + 64]))
    return vectors


def main():
    if "--allow-paid" not in sys.argv:
        raise SystemExit("Embeds new passages and questions (paid); pass --allow-paid.")
    state = json.loads(Path(sys.argv[1]).read_text())
    engine = create_engine(os.environ["DATABASE_URL"])
    # The project's provider key, as the workers bind it.
    with (
        Session(engine) as session,
        provider_credentials.bound_for_project(session, state["project_id"]),
    ):
        measure(state, Path(sys.argv[2]), engine)


def measure(state, out_path, engine):
    sources = load_sources()
    embedding = state["embedding"]
    adapter = OpenRouterEmbeddings(EmbeddingConfig(**embedding))
    questions = [q for q in load_questions() if q["phrases"]]
    tracks = {track for track, _ in TARGETS.values()}
    questions = [q for q in questions if track_of(q["source"], sources) in tracks]
    paid_bytes = 0
    query_vectors = {}
    pending = [q for q in questions if q["id"] not in query_vectors]
    for question, vector in zip(
        pending, embed(adapter, [q["question"] for q in pending]), strict=True
    ):
        query_vectors[question["id"]] = unit(vector)
        paid_bytes += len(question["question"].encode("utf-8"))
    report = {"rounds": {}, "new_passages": {}}
    with engine.connect() as connection, Session(engine) as session:
        query_terms = {
            q["id"]: list(lexemes(connection, q["question"])) for q in questions
        }
        for round_id, chunk_versions in ROUNDS.items():
            rows = report["rounds"].setdefault(round_id, {})
            for track in sorted(tracks):
                run = state["runs"].get(f"{track}:{round_id}")
                index_id = run["index_id"]
                old = {}
                for row in connection.execute(
                    MEMBERS, {"index_id": index_id}
                ).mappings():
                    vector = json.loads(row["vector"])
                    terms = lexemes(connection, row["searched"])
                    old[(row["run_id"], row["ordinal"])] = {
                        "document_id": row["document_id"],
                        "supplied": row["supplied"],
                        "unit": unit(vector),
                        "tf": terms,
                        "length": sum(terms.values()),
                    }
                new = {
                    key: item
                    for key, item in old.items()
                    if item["document_id"]
                    not in {
                        state[group][source]["id"]
                        for source, (target_track, group) in TARGETS.items()
                        if target_track == track
                    }
                }
                for source, (target_track, group) in TARGETS.items():
                    if target_track != track:
                        continue
                    document_id = state[group][source]["id"]
                    configs = (
                        connection.execute(
                            CONFIG, {"index_id": index_id, "document_id": document_id}
                        )
                        .scalars()
                        .all()
                    )
                    if len(configs) != 1:
                        raise SystemExit(f"{source}: expected one saved configuration")
                    config = json.loads(json.dumps(configs[0]))
                    config["extract"]["config_version"] = "layout-ocr-v6"
                    algorithm = config["chunk"]["algorithm"]
                    config["chunk"]["config_version"] = chunk_versions[algorithm]
                    document = session.get(Document, document_id)
                    job = SimpleNamespace(
                        id=uuid4(),
                        processing_config=config,
                        processing_config_hash=hashlib.sha256(
                            json.dumps(config, sort_keys=True).encode()
                        ).hexdigest(),
                    )
                    with artifact_storage.temporary_plaintext(
                        artifact_storage.read(document)
                    ) as path:
                        chunks = _v2_chunks(
                            job,
                            path,
                            document.media_type,
                            document.filename,
                            lambda _stage: None,
                        )[0]
                    by_ordinal = {chunk["ordinal"]: chunk for chunk in chunks}
                    embedded = [c for c in chunks if c["chunk_role"] != "parent"]
                    searched = [c.get("embedding_text") or c["text"] for c in embedded]
                    paid_bytes += sum(len(value.encode("utf-8")) for value in searched)
                    vectors = embed(adapter, searched)
                    for chunk, value, vector in zip(
                        embedded, searched, vectors, strict=True
                    ):
                        parent = by_ordinal.get(chunk["parent_ordinal"])
                        terms = lexemes(connection, value)
                        new[(f"new-{source}", chunk["ordinal"])] = {
                            "document_id": document_id,
                            "supplied": (parent or chunk)["text"],
                            "unit": unit(vector),
                            "tf": terms,
                            "length": sum(terms.values()),
                        }
                    report["new_passages"][f"{round_id}:{source}"] = {
                        "passages": len(embedded),
                        "row_passages": sum(
                            1
                            for c in embedded
                            if c["provenance"].get("table_passage") == "row-v1"
                        ),
                        "old_passages": sum(
                            1
                            for item in old.values()
                            if item["document_id"] == document_id
                        ),
                    }
                matrices = {"old": matrix(old), "new": matrix(new)}
                for question in questions:
                    if track_of(question["source"], sources) != track:
                        continue
                    phrases = [normalize(p) for p in question["phrases"]]
                    entry = {"source": question["source"]}
                    for name, passages in (("old", old), ("new", new)):
                        vector = cosine_ranking(
                            query_vectors[question["id"]], matrices[name]
                        )
                        keyword = bm25_ranking(query_terms[question["id"]], passages)
                        entry[name] = {
                            "vector": first_hit(vector, passages, phrases),
                            "bm25": first_hit(keyword, passages, phrases),
                            "hybrid": first_hit(
                                fuse(vector, keyword), passages, phrases
                            ),
                        }
                    rows[question["id"]] = entry
                print(f"{round_id} {track}: done", flush=True)
    summary = {}
    for round_id, rows in report["rounds"].items():
        entry = {"questions": len(rows)}
        for name in ("old", "new"):
            for method in ("vector", "bm25", "hybrid"):
                entry[f"{name}_{method}_hit5"] = sum(
                    r[name][method] is not None for r in rows.values()
                )
        for method in ("vector", "hybrid"):
            entry[f"{method}_lost"] = sorted(
                q
                for q, r in rows.items()
                if r["old"]["vector"] is not None and r["new"][method] is None
            )
            entry[f"{method}_gained"] = sorted(
                q
                for q, r in rows.items()
                if r["old"]["vector"] is None and r["new"][method] is not None
            )
        entry["targets"] = {
            q: rows[q] for q in ("f2-q9", "f2-q10", "g3-q2") if q in rows
        }
        summary[round_id] = entry
    report["summary"] = summary
    report["paid_bytes"] = paid_bytes
    report["embedding_estimate_usd"] = round(paid_bytes * USD_PER_BYTE, 6)
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {"summary": summary, "usd": report["embedding_estimate_usd"]}, indent=2
        )
    )


if __name__ == "__main__":
    main()

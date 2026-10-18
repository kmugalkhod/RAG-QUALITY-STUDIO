"""Spec 0013 Slice 0: BM25 keyword and hybrid search measured before building.

Read-only except for query embeddings (vector search through the app's own
retrieval API, well under $0.01). For each answerable real-source question and
each round's index (A5: section-token-v3, A5p: parent-child-v3):

- vector: the app's vector search, top 50;
- bm25: BM25 (k1 1.2, b 0.75) over the index's member passages, using
  PostgreSQL's `to_tsvector('simple', ...)` on the section path and passage text,
  with the index's own term statistics and any question word allowed to match;
- hybrid: reciprocal-rank fusion of both top-50 lists with weight 0.5 and
  constant 60, as the app's hybrid mode does.

A question is found when one supplied text (the parent for a child) among the
top 5 holds all its reference phrases, the real-source harness's rule.

    python scripts/keyword_search/slice0.py <state.json> <out.json> [base_url]
"""

from __future__ import annotations

import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "real_source"))
from run import load_questions, load_sources, normalize, track_of  # noqa: E402

K1, B, CONSTANT, WEIGHT, DEPTH, TOP = 1.2, 0.75, 60, 0.5, 50, 5
ROUNDS = ("A5", "A5p")

PASSAGES = text(
    """
    SELECT c.run_id::text AS run_id, c.ordinal, c.parent_ordinal,
           coalesce(c.embedding_text, c.text) AS searched,
           coalesce(p.text, c.text) AS supplied
    FROM index_chunks ic
    JOIN chunks c ON c.run_id = ic.run_id AND c.ordinal = ic.ordinal
    LEFT JOIN chunks p ON p.run_id = c.run_id AND p.ordinal = c.parent_ordinal
    WHERE ic.index_id = :index_id
    """
)
TERMS = text(
    """
    SELECT ic.run_id::text AS run_id, ic.ordinal, t.lexeme,
           coalesce(array_length(t.positions, 1), 1) AS tf
    FROM index_chunks ic
    JOIN chunks c ON c.run_id = ic.run_id AND c.ordinal = ic.ordinal,
         LATERAL unnest(to_tsvector('simple', coalesce(c.embedding_text, c.text))) t
    WHERE ic.index_id = :index_id
    """
)
QUERY_TERMS = text("SELECT lexeme FROM unnest(to_tsvector('simple', :query))")


class Bm25:
    def __init__(self, connection, index_id):
        self.supplied = {}
        for row in connection.execute(PASSAGES, {"index_id": index_id}).mappings():
            self.supplied[(row["run_id"], row["ordinal"])] = row["supplied"]
        self.tf = defaultdict(dict)
        lengths = Counter()
        for row in connection.execute(TERMS, {"index_id": index_id}).mappings():
            key = (row["run_id"], row["ordinal"])
            self.tf[row["lexeme"]][key] = row["tf"]
            lengths[key] += row["tf"]
        self.lengths = {key: lengths.get(key, 0) for key in self.supplied}
        self.count = len(self.supplied)
        self.average = sum(self.lengths.values()) / max(self.count, 1)

    def search(self, terms, depth=DEPTH):
        scores = Counter()
        for term in set(terms):
            postings = self.tf.get(term)
            if not postings:
                continue
            df = len(postings)
            idf = math.log(1 + (self.count - df + 0.5) / (df + 0.5))
            for key, tf in postings.items():
                norm = K1 * (1 - B + B * self.lengths[key] / self.average)
                scores[key] += idf * tf * (K1 + 1) / (tf + norm)
        ranked = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
        return [key for key, _ in ranked[:depth]]


def first_hit(keys, supplied, phrases):
    for rank, key in enumerate(keys[:TOP], 1):
        value = normalize(supplied.get(key, ""))
        if all(phrase in value for phrase in phrases):
            return rank
    return None


def fuse(vector, keyword):
    scores = Counter()
    for weight, keys in ((WEIGHT, vector), (1 - WEIGHT, keyword)):
        for rank, key in enumerate(keys, 1):
            scores[key] += weight / (CONSTANT + rank)
    return [key for key, _ in sorted(scores.items(), key=lambda p: (-p[1], p[0]))]


def main():
    state = json.loads(Path(sys.argv[1]).read_text())
    out_path = Path(sys.argv[2])
    base_url = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8000"
    client = httpx.Client(base_url=base_url, timeout=120)
    project = f"/api/projects/{state['project_id']}"
    sources = load_sources()
    questions = [q for q in load_questions() if q["phrases"]]
    engine = create_engine(os.environ["DATABASE_URL"])
    results, query_bytes = {}, 0
    with engine.connect() as connection:
        for round_id in ROUNDS:
            cache = {}
            for question in questions:
                track = track_of(question["source"], sources)
                run = state["runs"].get(f"{track}:{round_id}") or state["runs"].get(
                    f"{track}:A5"
                )
                if not run or not run.get("index_id"):
                    continue
                index_id = run["index_id"]
                if index_id not in cache:
                    cache[index_id] = Bm25(connection, index_id)
                bm25 = cache[index_id]
                response = client.post(
                    f"{project}/retrieval",
                    json={
                        "index_id": index_id,
                        "query": question["question"],
                        "retrieval": {"mode": "vector", "top_k": DEPTH},
                    },
                )
                response.raise_for_status()
                body = response.json()
                evidence = body.get("evidence") or body.get("items") or []
                query_bytes += len(question["question"].encode("utf-8"))
                vector = [(str(item["run_id"]), item["ordinal"]) for item in evidence]
                for item in evidence:
                    bm25.supplied.setdefault(
                        (str(item["run_id"]), item["ordinal"]), item["text"]
                    )
                terms = [
                    row[0]
                    for row in connection.execute(
                        QUERY_TERMS, {"query": question["question"]}
                    )
                ]
                keyword = bm25.search(terms)
                hybrid = fuse(vector, keyword)
                phrases = [normalize(p) for p in question["phrases"]]
                results.setdefault(round_id, {})[question["id"]] = {
                    "track": track,
                    "terms": terms,
                    "vector": first_hit(vector, bm25.supplied, phrases),
                    "bm25": first_hit(keyword, bm25.supplied, phrases),
                    "hybrid": first_hit(hybrid, bm25.supplied, phrases),
                }
            print(f"{round_id}: {len(results.get(round_id, {}))} questions", flush=True)
    summary = {}
    for round_id, rows in results.items():
        entry = {}
        for scope, keep in (("files", "fg"), ("websites", "w"), ("all", "fgw")):
            chosen = {q: r for q, r in rows.items() if q[0] in keep}
            entry[scope] = {
                "questions": len(chosen),
                **{
                    f"{method}_hit5": sum(
                        r[method] is not None for r in chosen.values()
                    )
                    for method in ("vector", "bm25", "hybrid")
                },
                **{
                    f"{method}_hit1": sum(r[method] == 1 for r in chosen.values())
                    for method in ("vector", "bm25", "hybrid")
                },
            }
        entry["hybrid_loses"] = sorted(
            q
            for q, r in rows.items()
            if r["vector"] is not None and r["hybrid"] is None
        )
        entry["hybrid_gains"] = sorted(
            q
            for q, r in rows.items()
            if r["vector"] is None and r["hybrid"] is not None
        )
        entry["targets"] = {
            q: rows[q] for q in ("f2-q9", "f2-q10", "g3-q2", "f5-q3") if q in rows
        }
        summary[round_id] = entry
    report = {
        "summary": summary,
        "query_bytes": query_bytes,
        "query_embedding_estimate_usd": round(query_bytes / 1e6 * 0.02, 6),
        "per_question": results,
    }
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

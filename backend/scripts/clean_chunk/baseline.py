"""Spec 0012 baseline: chunk statistics of saved indexes and stage timings of runs.

Free and read-only: it reads stored chunks, block spans and run stage states from
the database in DATABASE_URL and calls no provider.

    python scripts/clean_chunk/baseline.py \
        --index files-A4s=<index id> --run W1a=<run id> --out baseline.json

Per index it reports, for the embedded passages (leaf and child chunks) and for
parents separately: count, median, minimum, p95 and maximum size in UTF-8 bytes,
passages under 40 bytes, embedding texts over the provider's 8,191-byte limit, and
passages that start in the middle of a word (the first span starts inside a block
between two letters or digits).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import Counter

from sqlalchemy import create_engine, text

EMBED_LIMIT = 8191
SHORT = 40

CHUNKS = text(
    """
    SELECT c.run_id, c.ordinal, c.chunk_role, c.text,
           coalesce(c.embedding_text, c.text) AS embedding_text,
           pr.processing_config -> 'chunk' ->> 'config_version' AS chunk_version,
           pr.processing_config -> 'versions' ->> 'cleaner' AS cleaner
    FROM index_chunks ic
    JOIN chunks c ON c.run_id = ic.run_id AND c.ordinal = ic.ordinal
    JOIN processing_runs pr ON pr.id = c.run_id
    WHERE ic.index_id = :index_id
    UNION ALL
    -- Parents are not index members; they are read through their children.
    SELECT p.run_id, p.ordinal, p.chunk_role, p.text, p.text, NULL, NULL
    FROM chunks p
    WHERE p.chunk_role = 'parent' AND p.run_id IN (
        SELECT run_id FROM index_chunks WHERE index_id = :index_id
    )
    """
)

# A passage starts mid-word when its first span starts inside a block, with a
# letter or digit on both sides of the cut.
MID_WORD = text(
    """
    SELECT count(*)
    FROM index_chunks ic
    JOIN chunk_block_spans s
      ON s.run_id = ic.run_id AND s.chunk_ordinal = ic.ordinal
     AND s.span_ordinal = 0 AND s.chunk_start_char = 0
    JOIN content_blocks b
      ON b.derivation_id = s.derivation_id AND b.ordinal = s.block_ordinal
    WHERE ic.index_id = :index_id
      AND s.block_start_char > 0
      AND substr(b.text, s.block_start_char, 1) ~ '^[[:alnum:]]$'
      AND substr(b.text, s.block_start_char + 1, 1) ~ '^[[:alnum:]]$'
    """
)

STAGES = text(
    """
    SELECT n.ordinal, n.node_type, n.status,
           extract(epoch FROM n.finished_at - n.started_at) AS seconds
    FROM ingestion_run_nodes n
    WHERE n.run_id = :run_id
    ORDER BY n.ordinal
    """
)

RUN = text(
    """
    SELECT r.status, r.discovered_count, r.chunk_count,
           extract(epoch FROM r.started_at - r.created_at) AS queue_seconds,
           extract(epoch FROM r.finished_at - r.started_at) AS run_seconds,
           i.embedding_tokens, i.embedding_cost_usd
    FROM ingestion_runs r
    LEFT JOIN index_versions i ON i.ingestion_run_id = r.id
    WHERE r.id = :run_id
    """
)


def sizes(values: list[int]) -> dict:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "median": statistics.median(ordered),
        "min": ordered[0],
        "p95": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))],
        "max": ordered[-1],
    }


def index_stats(connection, index_id: str) -> dict:
    rows = connection.execute(CHUNKS, {"index_id": index_id}).mappings().all()
    embedded = [row for row in rows if row["chunk_role"] != "parent"]
    parents = [row for row in rows if row["chunk_role"] == "parent"]
    passage = [len(row["text"].encode("utf-8")) for row in embedded]
    embedding = [len(row["embedding_text"].encode("utf-8")) for row in embedded]
    return {
        "chunk_versions": dict(Counter(row["chunk_version"] for row in embedded)),
        "cleaners": dict(Counter(row["cleaner"] for row in embedded)),
        "passages": sizes(passage),
        "embedding_texts": sizes(embedding),
        "under_40_bytes": sum(value < SHORT for value in passage),
        "over_embed_limit": sum(value > EMBED_LIMIT for value in embedding),
        "mid_word_starts": connection.execute(
            MID_WORD, {"index_id": index_id}
        ).scalar_one(),
        "parents": sizes([len(row["text"].encode("utf-8")) for row in parents]),
    }


def run_stats(connection, run_id: str) -> dict:
    run = connection.execute(RUN, {"run_id": run_id}).mappings().one()
    return {
        **{
            key: (float(value) if key.endswith(("seconds", "usd")) and value else value)
            for key, value in run.items()
        },
        "stages": [
            {
                "stage": row["node_type"],
                "status": row["status"],
                "seconds": None
                if row["seconds"] is None
                else round(float(row["seconds"]), 2),
            }
            for row in connection.execute(STAGES, {"run_id": run_id}).mappings()
        ],
    }


def pairs(values: list[str]) -> dict[str, str]:
    return dict(value.split("=", 1) for value in values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", action="append", default=[], help="name=index id")
    parser.add_argument("--run", action="append", default=[], help="name=run id")
    parser.add_argument("--out")
    args = parser.parse_args()
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        result = {
            "indexes": {
                name: index_stats(connection, value)
                for name, value in pairs(args.index).items()
            },
            "runs": {
                name: run_stats(connection, value)
                for name, value in pairs(args.run).items()
            },
        }
    output = json.dumps(result, indent=2, default=str)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(output + "\n")
    print(output)


if __name__ == "__main__":
    main()

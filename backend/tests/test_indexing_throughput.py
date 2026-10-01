"""Opt-in indexing throughput benchmark: RUN_BENCHMARKS=1 python -m pytest -s ...

Drives the real dispatcher and embedding worker against PostgreSQL with a
deterministic provider double, so it measures queueing and database cost, not
provider latency. Wall time adds the production dispatcher interval per pass.
"""

import inspect
import os
import time
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.models.index import IndexVersion
from app.workers.dispatcher import dispatch_indexes_once
from app.workers.indexing import process_index
from app.workers.processing import process
from test_documents import start, upload
from test_indexes import create, index_api  # noqa: F401
from test_documents import documents_api  # noqa: F401
from test_indexes import embedding_config  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_BENCHMARKS"), reason="Set RUN_BENCHMARKS=1 to run"
)

DISPATCH_INTERVAL_SECONDS = 5
CHUNK_CHARACTERS = 100


def corpus(label, chunks):
    lines = (f"{label} passage {i:06d} " for i in range(chunks))
    return "".join(line.ljust(CHUNK_CHARACTERS, "x") for line in lines).encode()


def drive(engine, index_id):
    """Run dispatcher passes until the index finishes; follow worker hand-offs."""
    chains = "send" in inspect.signature(process_index).parameters
    passes = batches = 0
    started = time.perf_counter()
    while True:
        with Session(engine) as session:
            status = session.get(IndexVersion, index_id).status
        if status not in ("queued", "running"):
            break
        passes += 1
        assert passes < 100_000
        sent = []
        dispatch_indexes_once(engine, send=sent.append)
        pending = [value for value in sent if value == index_id]
        while pending:
            pending.pop(0)
            batches += 1
            if chains:
                process_index(
                    index_id,
                    engine,
                    send=lambda value, **_: pending.append(value),
                )
            else:
                process_index(index_id, engine)
    return status, passes, batches, time.perf_counter() - started


def report(label, chunks, status, passes, batches, seconds):
    wall = seconds + passes * DISPATCH_INTERVAL_SECONDS
    print(
        f"\n[{label}] status={status} chunks={chunks} batches={batches} "
        f"dispatcher_passes={passes} worker_db_seconds={seconds:.2f} "
        f"ms_per_batch={1000 * seconds / max(batches, 1):.1f} "
        f"estimated_wall_seconds={wall:.0f} "
        f"chunks_per_minute={60 * chunks / wall:.0f}"
    )


def test_indexing_throughput(index_api):  # noqa: F811
    client, engine, p, _, provider = index_api
    chunks = int(os.environ.get("BENCHMARK_CHUNKS", "2000"))
    for label in ("first", "second"):
        document = upload(client, p, corpus(label, chunks), f"{label}.txt")
        run = start(client, p, document["id"], size=CHUNK_CHARACTERS, overlap=0)
        process(UUID(run["id"]), engine)
        index = create(client, p)
        indexed = index["chunk_count"]
        result = drive(engine, UUID(index["id"]))
        assert result[0] == "succeeded"
        # The second index also scans the first index's vectors for reuse.
        report(f"{label} index", indexed, *result)
    assert provider.calls

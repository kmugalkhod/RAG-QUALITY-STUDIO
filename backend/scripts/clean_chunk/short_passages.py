"""Spec 0012 Slice 6: why each v3 passage under 40 bytes is left short.

Free and read-only, like v3_corpus.py:

    python scripts/clean_chunk/short_passages.py <index id> [<index id> ...]

Each embedded passage under 40 bytes is put in the first reason that applies: its
page holds under 40 bytes; the next passage on its page opens with a table, list or
code block, which is never split; the passage before it on its page ends with one;
both neighbours on its page are too full to take it; or other.
"""

import os
import sys
from collections import Counter

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, "/app/scripts/clean_chunk")
from v3_corpus import (  # noqa: E402
    RUNS,
    V3,
    chunk_cleaned_document,
    chunk_node,
    page_bytes,
    reusable_cleaned_document,
)

PROTECTED = {"table", "list_item", "code"}
engine = create_engine(os.environ["DATABASE_URL"])
reasons = Counter()
with Session(engine) as session:
    for index_id in sys.argv[1:]:
        for run_id, config in session.execute(RUNS, {"index_id": index_id}).all():
            cleaned, _ = reusable_cleaned_document(session, run_id)
            node = chunk_node(config["chunk"])
            node = node.model_copy(update={"config_version": V3[node.algorithm]})
            result = chunk_cleaned_document(cleaned, node)
            sizes = page_bytes(cleaned)
            leaves = [c for c in result.chunks if c.chunk_role != "parent"]
            limit = node.size
            for position, chunk in enumerate(leaves):
                if len(chunk.text.encode()) >= 40:
                    continue
                before = leaves[position - 1] if position else None
                after = leaves[position + 1] if position + 1 < len(leaves) else None

                def block(c, index):
                    span = result.spans[c.ordinal][index]
                    return cleaned.blocks[span.block_ordinal]

                same_before = (
                    before is not None and before.page_number == chunk.page_number
                )
                same_after = (
                    after is not None and after.page_number == chunk.page_number
                )
                if sizes[chunk.page_number] < 40:
                    reason = "page holds under 40 bytes"
                elif same_after and block(after, 0).type in PROTECTED:
                    reason = "before a table, list or code block"
                elif same_before and block(before, -1).type in PROTECTED:
                    reason = "after a table, list or code block"
                elif (
                    not same_before
                    or before.token_count + 2 + chunk.token_count > limit
                ) and (
                    not same_after or after.token_count + 2 + chunk.token_count > limit
                ):
                    reason = "neighbours on the page are full"
                else:
                    reason = "other"
                reasons[reason] += 1
                print(
                    reason,
                    "|",
                    repr(chunk.text[:60]),
                    chunk.chunk_role,
                    chunk.page_number,
                )
print(dict(reasons))

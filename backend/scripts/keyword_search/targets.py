"""Spec 0013 Slice 0: where BM25 ranks the passages that answer the target questions.

Free and read-only. For each target question, every passage of the A5 index whose
supplied text holds all reference phrases is listed with its BM25 rank, and the
question's terms with their passage counts, to show why it is or is not found.

    python scripts/keyword_search/targets.py <state.json>
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parent))
from slice0 import QUERY_TERMS, Bm25  # noqa: E402
from run import load_questions, load_sources, normalize, track_of  # noqa: E402

TARGETS = ("f2-q9", "f2-q10", "g3-q2")


def main():
    state = json.loads(Path(sys.argv[1]).read_text())
    sources = load_sources()
    questions = {q["id"]: q for q in load_questions()}
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as connection:
        for qid in TARGETS:
            question = questions[qid]
            track = track_of(question["source"], sources)
            index_id = state["runs"][f"{track}:A5"]["index_id"]
            bm25 = Bm25(connection, index_id)
            terms = [
                r[0]
                for r in connection.execute(
                    QUERY_TERMS, {"query": question["question"]}
                )
            ]
            ranking = bm25.search(terms, depth=len(bm25.supplied))
            phrases = [normalize(p) for p in question["phrases"]]
            gold = [
                key
                for key, value in bm25.supplied.items()
                if all(p in normalize(value) for p in phrases)
            ]
            print(f"{qid}: {question['question']}")
            print("  phrases", question["phrases"], "passages holding them:", len(gold))
            for key in gold:
                rank = ranking.index(key) + 1 if key in ranking else None
                held = sorted(t for t in set(terms) if key in bm25.tf.get(t, {}))
                print("   gold rank", rank, "of", bm25.count, "holds", held)
                print("   text:", bm25.supplied[key][:300].replace("\n", " | "))
            print(
                "  term passage counts:",
                {t: len(bm25.tf.get(t, {})) for t in sorted(set(terms))},
            )
            phrase_terms = [
                r[0]
                for p in question["phrases"]
                for r in connection.execute(QUERY_TERMS, {"query": p})
            ]
            print("  phrase terms:", phrase_terms)


if __name__ == "__main__":
    main()

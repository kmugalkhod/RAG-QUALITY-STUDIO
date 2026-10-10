"""Spec 0010 slice 0: simulate retrieval-v3 hybrid search on existing indexes.

    python hybrid_sim.py OUT.json TRACK=INDEX_ID [TRACK=INDEX_ID ...] [--only F2,F4]

Vector: the app's own vector search (top 50) through the API. Keyword: content words of
the question joined by OR over section path + text (chunks.embedding_text), top 50, in
SQL. Hybrid v3: reciprocal-rank fusion, weight 0.5 each, constant 60, as the app's
hybrid mode does. A question counts as found when one supplied text in the top 5 holds
all its reference phrases (the harness rule).
"""
import json
import re
import sys

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import engine

sys.path.insert(0, "/app/scripts/real_source")
from run import load_questions, load_sources, normalize, track_of  # noqa: E402

STOP = set("""a about according an and are as at be by did do does for from had has have how in
is it its of on or than that the their there these this to under up was were what when where
which who whom whose why will with would you your le la les de des du un une et en pour par
au aux est sont dans que qui quel quelle quels quelles combien ont été l d""".split())
KEYWORD = text("""
SELECT c.run_id, c.ordinal, coalesce(p.text, c.text) AS supplied,
       ts_rank_cd(to_tsvector('simple', coalesce(c.embedding_text, c.text)),
                  to_tsquery('simple', :q)) AS score
FROM index_chunks ic
JOIN chunks c ON c.run_id = ic.run_id AND c.ordinal = ic.ordinal
LEFT JOIN chunks p ON p.run_id = c.run_id AND p.ordinal = c.parent_ordinal
WHERE ic.index_id = :index AND ic.embedding IS NOT NULL
  AND to_tsvector('simple', coalesce(c.embedding_text, c.text)) @@ to_tsquery('simple', :q)
ORDER BY score DESC, c.run_id, c.ordinal LIMIT 50
""")


def terms(question: str) -> str:
    keep = set()
    for word in re.findall(r"[^\W_][\w.,'-]*[^\W_]|[^\W_]", question.lower()):
        word = word.strip(".,'")
        if word in STOP or len(word) < 2:
            continue
        if re.search(r"\d", word):
            keep.update(part for part in re.split(r"[^\w]+", word) if part)
        else:
            keep.update(part for part in re.split(r"[^\w]+", word) if len(part) > 1 and part not in STOP)
    return " | ".join(sorted(keep)) or "zzzz"


DF = text("""
SELECT count(*) FROM index_chunks ic JOIN chunks c ON c.run_id = ic.run_id AND c.ordinal = ic.ordinal
WHERE ic.index_id = :index AND ic.embedding IS NOT NULL
  AND to_tsvector('simple', coalesce(c.embedding_text, c.text)) @@ to_tsquery('simple', :t)
""")
TOTAL = text("SELECT count(*) FROM index_chunks WHERE index_id = :index AND embedding IS NOT NULL")


def rare_terms(session, question, index):
    total = session.execute(TOTAL, {"index": index}).scalar() or 1
    keep = []
    for term in terms(question).split(" | "):
        if term == "zzzz":
            continue
        try:
            df = session.execute(DF, {"index": index, "t": term}).scalar()
        except Exception:
            session.rollback()
            continue
        if 0 < df <= max(3, 0.05 * total):
            keep.append(term)
    return " | ".join(keep) or "zzzz"


def found(texts, phrases):
    return next(
        (rank for rank, value in enumerate(texts[:5], 1)
         if all(p in normalize(value) for p in phrases)),
        None,
    )


out, mapping, only = sys.argv[1], {}, None
for arg in sys.argv[2:]:
    if arg.startswith("--only="):
        only = set(arg.split("=", 1)[1].split(","))
    else:
        track, index = arg.split("=")
        mapping[track] = index
state = json.load(open("/tmp/rs/state.json"))
project = f"/api/projects/{state['project_id']}"
client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=120)
sources = load_sources()
results = {}
with Session(engine) as session:
    for q in load_questions():
        track = track_of(q["source"], sources)
        if track not in mapping or not q["phrases"] or (only and q["source"] not in only):
            continue
        phrases = [normalize(p) for p in q["phrases"]]
        response = client.post(
            f"{project}/retrieval",
            json={"index_id": mapping[track], "query": q["question"],
                  "retrieval": {"mode": "vector", "top_k": 50}},
        )
        response.raise_for_status()
        vector = response.json().get("evidence") or response.json().get("items") or []
        keyword = session.execute(KEYWORD, {"q": terms(q["question"]), "index": mapping[track]}).all()
        rare = session.execute(KEYWORD, {"q": rare_terms(session, q["question"], mapping[track]), "index": mapping[track]}).all()
        fused_rare, texts = {}, {}
        for rank, item in enumerate(vector, 1):
            key = (str(item["run_id"]), item["ordinal"])
            fused_rare[key] = fused_rare.get(key, 0) + 0.5 / (60 + rank)
            texts[key] = item["text"]
        for rank, row in enumerate(rare, 1):
            key = (str(row.run_id), row.ordinal)
            fused_rare[key] = fused_rare.get(key, 0) + 0.5 / (60 + rank)
            texts.setdefault(key, row.supplied)
        fused = {}
        for rank, item in enumerate(vector, 1):
            key = (str(item["run_id"]), item["ordinal"])
            fused[key] = fused.get(key, 0) + 0.5 / (60 + rank)
            texts[key] = item["text"]
        for rank, row in enumerate(keyword, 1):
            key = (str(row.run_id), row.ordinal)
            fused[key] = fused.get(key, 0) + 0.5 / (60 + rank)
            texts.setdefault(key, row.supplied)
        hybrid = [texts[key] for key, _ in sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))]
        results[q["id"]] = {
            "vector": found([item["text"] for item in vector], phrases),
            "keyword": found([row.supplied for row in keyword], phrases),
            "hybrid_v3": found(hybrid, phrases),
            "keyword_rare": found([row.supplied for row in rare], phrases),
            "hybrid_rare": found([texts[key] for key, _ in sorted(fused_rare.items(), key=lambda kv: (-kv[1], kv[0]))], phrases),
        }
json.dump(results, open(out, "w"), indent=1)
for mode in ("vector", "keyword", "hybrid_v3", "keyword_rare", "hybrid_rare"):
    print(f"{mode:9} hit@1 {sum(r[mode] == 1 for r in results.values())}/{len(results)}  "
          f"hit@5 {sum(bool(r[mode]) for r in results.values())}/{len(results)}")
for qid in ("f2-q9", "f2-q10", "f4-q1", "f4-q4", "f5-q2", "f6-q1", "g3-q2", "g8-q1", "g8-q2"):
    if qid in results:
        print(qid, results[qid])
for mode in ("hybrid_v3", "hybrid_rare"):
    gained = [q for q, r in results.items() if r[mode] and not r["vector"]]
    lost = [q for q, r in results.items() if r["vector"] and not r[mode]]
    print(mode, "gained:", gained, "lost:", lost)

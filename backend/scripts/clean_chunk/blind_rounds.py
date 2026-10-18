"""Spec 0012 Slice 7: blind paired scoring of two real-source rounds.

    python blind_rounds.py blind <dir> A4s:A5:fg A1:A5:w   # blind_review.md, blind_key.json
    python blind_rounds.py final <dir>                # reads labels.csv and the key, writes result.json

`<dir>` holds `answers_<round>.jsonl` from `scripts/real_source/run.py fetch`. Each
pair "baseline:candidate:prefixes" compares the questions both rounds asked whose
ID starts with one of the prefix letters (f and g files, w websites). For every
question the two answers are shown as X and Y, assigned at random from a fixed seed;
the key is written to its own file and is not read until `labels.csv` is complete.
`labels.csv` has the columns pair, question_id, slot, label, reason, with the labels
of the spec 0004 rubric: correct, partial, wrong, correct-abstain, wrong-abstain,
fabricated. "Correct" means correct or correct-abstain; a loss is a question the
baseline answered correctly and the candidate did not.
"""

from __future__ import annotations

import csv
import json
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "real_source"
# Each spec scores with its own seed (BLIND_SEED), so X and Y never repeat an
# earlier review's order.
SEED = os.environ.get("BLIND_SEED", "clean-chunk-0012")
LABELS = {
    "correct",
    "partial",
    "wrong",
    "correct-abstain",
    "wrong-abstain",
    "fabricated",
}
CORRECT = {"correct", "correct-abstain"}


def answers(directory: Path, round_id: str) -> dict[str, dict]:
    path = directory / f"answers_{round_id}.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    return {row["question_id"]: row for row in rows}


def blind(directory: Path, pairs: list[str]) -> None:
    questions = {
        q["id"]: q
        for q in (
            json.loads(line)
            for line in (HERE / "questions.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
    }
    rng = random.Random(SEED)
    key, lines = {}, ["# Blind review", ""]
    for pair in pairs:
        baseline, candidate, prefixes = pair.split(":")
        left, right = answers(directory, baseline), answers(directory, candidate)
        shared = [qid for qid in right if qid in left and qid[0] in prefixes]
        lines += [f"## Pair {pair}", ""]
        for qid in sorted(shared):
            order = [baseline, candidate]
            rng.shuffle(order)
            key[f"{pair}|{qid}"] = {"X": order[0], "Y": order[1]}
            rows = {
                "X": (left if order[0] == baseline else right)[qid],
                "Y": (left if order[1] == baseline else right)[qid],
            }
            question = questions[qid]
            lines += [
                f"### {qid}",
                f"Question: {question['question']}",
                f"Reference: {question.get('answer') or 'Not answerable from the sources.'}",
                "",
            ]
            for slot in ("X", "Y"):
                row = rows[slot]
                text = (
                    row.get("answer")
                    if row.get("status") == "succeeded"
                    else (f"[run {row.get('status')}: {row.get('error')}]")
                )
                lines += [f"**{slot}:** {(text or '').strip()}", ""]
    (directory / "blind_review.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    (directory / "blind_key.json").write_text(json.dumps(key, indent=2) + "\n")
    print(f"{len(key)} questions written to blind_review.md")


def final(directory: Path) -> None:
    key = json.loads((directory / "blind_key.json").read_text())
    with (directory / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    labels = {}
    for row in rows:
        if row["label"] not in LABELS:
            raise SystemExit(
                f"Unknown label {row['label']!r} for {row['question_id']}."
            )
        labels[(row["pair"], row["question_id"], row["slot"])] = row
    result = {}
    for item, slots in key.items():
        pair, qid = item.split("|")
        baseline, candidate, _ = pair.split(":")
        by_round = {}
        for slot, round_id in slots.items():
            if (pair, qid, slot) not in labels:
                raise SystemExit(f"{pair} {qid} {slot} has no label.")
            by_round[round_id] = labels[(pair, qid, slot)]
        before = by_round[baseline]["label"] in CORRECT
        after = by_round[candidate]["label"] in CORRECT
        entry = result.setdefault(
            pair,
            {
                "questions": 0,
                baseline: 0,
                candidate: 0,
                "wins": [],
                "losses": [],
                "per_question": {},
            },
        )
        entry["questions"] += 1
        entry[baseline] += before
        entry[candidate] += after
        if after and not before:
            entry["wins"].append(qid)
        if before and not after:
            entry["losses"].append(qid)
        entry["per_question"][qid] = {
            round_id: {"label": value["label"], "reason": value["reason"]}
            for round_id, value in by_round.items()
        }
    (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    for pair, entry in result.items():
        baseline, candidate, _ = pair.split(":")
        print(
            f"{pair}: {baseline} {entry[baseline]}/{entry['questions']}, "
            f"{candidate} {entry[candidate]}/{entry['questions']}, "
            f"wins {entry['wins']}, losses {entry['losses']}"
        )


if __name__ == "__main__":
    command, directory = sys.argv[1], Path(sys.argv[2])
    if command == "blind":
        blind(directory, sys.argv[3:])
    elif command == "final":
        final(directory)
    else:
        raise SystemExit(__doc__)

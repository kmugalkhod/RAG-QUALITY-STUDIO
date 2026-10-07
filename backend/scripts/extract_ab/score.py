"""Score the Extract v1/v2 comparison (spec 0004).

    python score.py blind <run directory>   # writes blind_review.csv, manual_scores.csv, blind_key.json
    python score.py final <run directory>   # writes report.md and per_question.csv

The run directory holds `answers.jsonl` from `run.py fetch`. `questions.jsonl` is
read from this script's directory. Correctness labels are given from
`blind_review.csv`, which shows only the question, the reference answer and the
two answers as X and Y. The evidence differs visibly between versions, so the
`supported` column is judged in a second, non-blind pass.
"""

from __future__ import annotations

import csv
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ARMS = ("v1", "v2")
SEED = "extract-ab-0004"
LABELS = {
    "correct",
    "partial",
    "wrong",
    "correct-abstain",
    "wrong-abstain",
    "fabricated",
}
CORRECT = {"correct", "correct-abstain"}
AFFECTED = {"C1", "C2", "C3", "C4", "C5", "C6"}
TOP_K = 5


class ScoringError(Exception):
    pass


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text("utf-8").splitlines()
        if line.strip()
    ]


def load_questions(path: Path = HERE / "questions.jsonl") -> list[dict]:
    questions = load_jsonl(path)
    ids = [q["id"] for q in questions]
    texts = [normalize(q["question"]) for q in questions]
    if len(set(ids)) != len(ids) or len(set(texts)) != len(texts):
        raise ScoringError("Question IDs and question texts must be unique.")
    return questions


def answers_by_key(
    answers: list[dict], questions: list[dict]
) -> dict[tuple[str, str], dict]:
    result = {}
    for answer in answers:
        key = (answer["question_id"], answer["arm"])
        if key in result:
            raise ScoringError(f"Duplicate answer for {key}.")
        result[key] = answer
    missing = [
        (q["id"], arm)
        for q in questions
        for arm in ARMS
        if (q["id"], arm) not in result
    ]
    if missing:
        raise ScoringError(f"Missing answers, never dropped silently: {missing}")
    return result


def evidence_rank(
    question: dict, answer: dict, *, with_section: bool = False
) -> int | None:
    """Rank of the first top-k chunk holding every evidence term, or None.

    By default only the chunk text counts, because that is all the answer model
    receives. `with_section` also counts the chunk's section path, which is
    embedded for search but not sent to the model.
    """

    terms = [normalize(term) for term in question["evidence_terms"]]
    if not terms or answer["status"] == "failed":
        return None
    for item in sorted(answer.get("evidence") or [], key=lambda e: e["rank"]):
        if item["rank"] > TOP_K:
            break
        section = " ".join(item.get("section_path") or []) if with_section else ""
        text = normalize(f"{section} {item.get('text') or ''}")
        if all(term in text for term in terms):
            return item["rank"]
    return None


def fact_present(question: dict, answer: dict) -> bool | None:
    if not question["answer_terms"]:
        return None
    if answer["status"] != "succeeded":
        return False
    text = normalize(answer.get("answer") or "")
    return all(
        any(normalize(option) in text for option in options)
        for options in question["answer_terms"]
    )


def blind_assignment(question_ids: list[str]) -> dict[str, dict[str, str]]:
    generator = random.Random(SEED)
    key = {}
    for question_id in sorted(question_ids):
        first, second = ("v1", "v2") if generator.random() < 0.5 else ("v2", "v1")
        key[question_id] = {"X": first, "Y": second}
    return key


def write_blind(directory: Path, questions: list[dict]) -> None:
    answers = answers_by_key(load_jsonl(directory / "answers.jsonl"), questions)
    key = blind_assignment([q["id"] for q in questions])
    with (directory / "blind_review.csv").open(
        "w", newline="", encoding="utf-8"
    ) as output:
        writer = csv.writer(output)
        writer.writerow(
            ["id", "question", "reference_answer", "slot", "status", "answer"]
        )
        for question in questions:
            for slot in ("X", "Y"):
                answer = answers[(question["id"], key[question["id"]][slot])]
                writer.writerow(
                    [
                        question["id"],
                        question["question"],
                        question["reference_answer"] or "(unanswerable)",
                        slot,
                        answer["status"],
                        answer.get("answer") or "",
                    ]
                )
    with (directory / "manual_scores.csv").open(
        "w", newline="", encoding="utf-8"
    ) as output:
        writer = csv.writer(output)
        writer.writerow(
            ["id", "slot", "label", "reason", "supported", "supported_reason"]
        )
        for question in questions:
            for slot in ("X", "Y"):
                writer.writerow([question["id"], slot, "", "", "", ""])
    (directory / "blind_key.json").write_text(json.dumps(key, indent=2) + "\n")


def load_manual(directory: Path, questions: list[dict]) -> dict[tuple[str, str], dict]:
    key = json.loads((directory / "blind_key.json").read_text())
    with (directory / "manual_scores.csv").open(encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    result = {}
    for row in rows:
        if row["label"] not in LABELS:
            raise ScoringError(
                f"{row['id']} {row['slot']}: unknown label {row['label']!r}."
            )
        if not row["reason"].strip():
            raise ScoringError(
                f"{row['id']} {row['slot']}: every label needs a reason."
            )
        if row["supported"] not in {"yes", "no", "n/a"}:
            raise ScoringError(
                f"{row['id']} {row['slot']}: supported must be yes, no or n/a."
            )
        result[(row["id"], key[row["id"]][row["slot"]])] = row
    missing = [
        (q["id"], arm)
        for q in questions
        for arm in ARMS
        if (q["id"], arm) not in result
    ]
    if missing:
        raise ScoringError(f"Missing manual scores: {missing}")
    return result


def pair(first: bool, second: bool) -> str:
    if second and not first:
        return "win"
    if first and not second:
        return "loss"
    return "tie"


def decide(nets: dict[str, int]) -> str:
    hit, correct = nets["affected_evidence"], nets["affected_correct"]
    control, unanswerable = nets["control_correct"], nets["unanswerable_correct"]
    if hit <= -3 or correct <= -3 or control <= -2:
        return "v2 hurts"
    if hit >= 5 and correct >= 3 and control >= -1 and unanswerable >= -1:
        return "v2 helps"
    if -2 <= hit <= 2 and -2 <= correct <= 2:
        return "no real difference"
    return "inconclusive"


def score(
    questions: list[dict], answers: list[dict], manual: dict
) -> tuple[list[dict], dict]:
    by_key = answers_by_key(answers, questions)
    rows = []
    for question in questions:
        row = {"id": question["id"], "category": question["category"]}
        for arm in ARMS:
            answer = by_key[(question["id"], arm)]
            label = manual[(question["id"], arm)]["label"]
            rank = evidence_rank(question, answer)
            row[f"{arm}_status"] = answer["status"]
            row[f"{arm}_evidence_rank"] = rank
            row[f"{arm}_evidence_rank_with_section"] = evidence_rank(
                question, answer, with_section=True
            )
            row[f"{arm}_fact_present"] = fact_present(question, answer)
            # A failed run is wrong whatever label it was given.
            row[f"{arm}_label"] = "wrong" if answer["status"] == "failed" else label
            row[f"{arm}_correct"] = row[f"{arm}_label"] in CORRECT
            row[f"{arm}_supported"] = manual[(question["id"], arm)]["supported"]
        if question["evidence_terms"]:
            row["evidence_pair"] = pair(
                row["v1_evidence_rank"] is not None, row["v2_evidence_rank"] is not None
            )
        else:
            row["evidence_pair"] = "n/a"
        row["correct_pair"] = pair(row["v1_correct"], row["v2_correct"])
        rows.append(row)

    def net(selected, column):
        values = [r[column] for r in selected]
        return values.count("win") - values.count("loss")

    affected = [r for r in rows if r["category"] in AFFECTED]
    nets = {
        "affected_evidence": net(affected, "evidence_pair"),
        "affected_correct": net(affected, "correct_pair"),
        "control_correct": net(
            [r for r in rows if r["category"] == "K"], "correct_pair"
        ),
        "control_evidence": net(
            [r for r in rows if r["category"] == "K"], "evidence_pair"
        ),
        "unanswerable_correct": net(
            [r for r in rows if r["category"] == "U"], "correct_pair"
        ),
    }
    return rows, {"nets": nets, "outcome": decide(nets)}


def _known(values):
    known = [v for v in values if v is not None]
    return {
        "known_sum": round(sum(known), 6),
        "known_count": len(known),
        "total": len(values),
    }


def write_final(directory: Path, questions: list[dict]) -> dict:
    answers = load_jsonl(directory / "answers.jsonl")
    manual = load_manual(directory, questions)
    rows, summary = score(questions, answers, manual)
    with (directory / "per_question.csv").open(
        "w", newline="", encoding="utf-8"
    ) as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    categories = sorted({r["category"] for r in rows})
    lines = [
        "# Extract v1 vs v2 results (spec 0004)",
        "",
        f"**Outcome under the pre-registered rule: {summary['outcome']}.**",
        "",
        "| Net (wins − losses) | Value |",
        "|---|---|",
        *[f"| {name} | {value:+d} |" for name, value in summary["nets"].items()],
        "",
        "| Category | Questions | v1 evidence hit@5 | v2 evidence hit@5 "
        "| v1 hit@5 with section | v2 hit@5 with section | v1 MRR | v2 MRR "
        "| v1 correct | v2 correct | v1 supported | v2 supported | correct W/L/T |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for category in [*categories, "all"]:
        selected = (
            rows
            if category == "all"
            else [r for r in rows if r["category"] == category]
        )
        scored = [r for r in selected if r["evidence_pair"] != "n/a"]
        cells = [category, str(len(selected))]
        for arm in ARMS:
            hits = sum(r[f"{arm}_evidence_rank"] is not None for r in scored)
            cells.append(f"{hits}/{len(scored)}" if scored else "n/a")
        for arm in ARMS:
            hits = sum(
                r[f"{arm}_evidence_rank_with_section"] is not None for r in scored
            )
            cells.append(f"{hits}/{len(scored)}" if scored else "n/a")
        for arm in ARMS:
            mrr = sum(
                1 / r[f"{arm}_evidence_rank"]
                for r in scored
                if r[f"{arm}_evidence_rank"]
            )
            cells.append(f"{mrr / len(scored):.2f}" if scored else "n/a")
        for arm in ARMS:
            cells.append(
                f"{sum(r[f'{arm}_correct'] for r in selected)}/{len(selected)}"
            )
        for arm in ARMS:
            cells.append(
                f"{sum(r[f'{arm}_supported'] == 'yes' for r in selected)}/{len(selected)}"
            )
        pairs = [r["correct_pair"] for r in selected]
        cells.append(f"{pairs.count('win')}/{pairs.count('loss')}/{pairs.count('tie')}")
        lines.append("| " + " | ".join(cells) + " |")

    lines += [
        "",
        "| Arm | Mean latency (ms) | Tokens | Generation cost (USD) | Failed runs |",
        "|---|---|---|---|---|",
    ]
    for arm in ARMS:
        selected = [a for a in answers if a["arm"] == arm]
        latency = [
            a.get("latency_ms") for a in selected if a.get("latency_ms") is not None
        ]
        tokens = _known([a.get("tokens") for a in selected])
        cost = _known([a.get("cost_usd") for a in selected])
        lines.append(
            f"| {arm} | {sum(latency) / len(latency):.0f} ({len(latency)} runs) | "
            f"{tokens['known_sum']:.0f} ({tokens['known_count']}/{tokens['total']} known) | "
            f"{cost['known_sum']:.4f} ({cost['known_count']}/{cost['total']} known) | "
            f"{sum(a['status'] == 'failed' for a in selected)} |"
            if latency
            else f"| {arm} | unknown | unknown | unknown | {len(selected)} |"
        )
    lines += [
        "",
        "Evidence hit@5 counts only chunk text, which is all the answer model receives; "
        'the "with section" columns also count the section path, which is embedded '
        "for search but not sent to the model. "
        "Correct means `correct` or `correct-abstain`. Correctness labels were given blind; "
        "`supported` was judged afterwards with the evidence visible, so it is not blind. "
        "Failed runs count as wrong. Unknown costs are not counted as zero.",
    ]
    (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in {"blind", "final"}:
        sys.exit("usage: score.py blind|final <run directory>")
    run_directory = Path(sys.argv[2])
    loaded = load_questions()
    if sys.argv[1] == "blind":
        write_blind(run_directory, loaded)
    else:
        print(json.dumps(write_final(run_directory, loaded), indent=2))

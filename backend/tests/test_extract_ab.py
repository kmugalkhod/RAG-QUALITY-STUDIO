"""Corpus and scoring checks for the Extract v1/v2 comparison (spec 0004)."""

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts" / "extract_ab"


def _load(name):
    spec = importlib.util.spec_from_file_location(
        f"extract_ab_{name}", SCRIPTS / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


corpus = _load("make_corpus")
score = _load("score")
QUESTIONS = score.load_questions()


def _answer(question_id, arm, status="succeeded", answer="", evidence=()):
    return {
        "question_id": question_id,
        "arm": arm,
        "status": status,
        "answer": answer,
        "evidence": [{"rank": rank, "text": text} for rank, text in evidence],
    }


def test_corpus_is_deterministic(tmp_path):
    first = corpus.write_corpus(tmp_path / "a")
    second = corpus.write_corpus(tmp_path / "b")
    assert first == second
    assert len(first["documents"]) == 9


def test_expected_terms_occur_in_their_documents():
    texts = {name: score.normalize(text) for name, text in corpus.source_text().items()}
    for question in QUESTIONS:
        if question["category"] == "U":
            assert not question["evidence_terms"] and not question["reference_answer"]
            continue
        text = texts[question["document"]]
        for term in question["evidence_terms"]:
            assert score.normalize(term) in text, (question["id"], term)
        for options in question["answer_terms"]:
            assert any(score.normalize(option) in text for option in options), question[
                "id"
            ]


def test_question_set_shape():
    categories = [q["category"] for q in QUESTIONS]
    assert len(QUESTIONS) == 40
    assert sum(c in score.AFFECTED for c in categories) == 28
    assert categories.count("K") == 6 and categories.count("U") == 6


def test_evidence_needs_every_term_in_one_top_k_chunk():
    question = {
        "evidence_terms": ["Roof inspection", "Hourly rate", "40.55"],
        "answer_terms": [],
    }
    header_lost = _answer(
        "q", "v1", evidence=[(1, "SR-108 Roof inspection West 40.55 5")]
    )
    with_header = _answer(
        "q",
        "v2",
        evidence=[
            (1, "other"),
            (2, "| Hourly  rate (EUR) |\n| Roof inspection | 40.55 |"),
        ],
    )
    beyond_top_k = _answer(
        "q", "v2", evidence=[(6, "Roof inspection Hourly rate 40.55")]
    )
    failed = _answer(
        "q", "v2", status="failed", evidence=[(1, "Roof inspection Hourly rate 40.55")]
    )
    assert score.evidence_rank(question, header_lost) is None
    assert score.evidence_rank(question, with_header) == 2
    assert score.evidence_rank(question, beyond_top_k) is None
    assert score.evidence_rank(question, failed) is None


def test_fact_present_accepts_alternatives_and_rejects_abstention():
    question = {"answer_terms": [["160500", "160,500"]]}
    assert score.fact_present(
        question, _answer("q", "v1", answer="It is EUR 160,500 [S1].")
    )
    assert not score.fact_present(
        question,
        _answer(
            "q",
            "v1",
            status="insufficient_evidence",
            answer="INSUFFICIENT_EVIDENCE 160500",
        ),
    )
    assert score.fact_present({"answer_terms": []}, _answer("q", "v1")) is None


def test_missing_or_duplicate_answers_are_errors():
    questions = QUESTIONS[:1]
    with pytest.raises(score.ScoringError, match="Missing answers"):
        score.answers_by_key([_answer(questions[0]["id"], "v1")], questions)
    with pytest.raises(score.ScoringError, match="Duplicate"):
        score.answers_by_key([_answer(questions[0]["id"], "v1")] * 2, questions)


def test_blind_assignment_is_fixed_and_mixed():
    ids = [q["id"] for q in QUESTIONS]
    key = score.blind_assignment(ids)
    assert key == score.blind_assignment(list(reversed(ids)))
    assert {pair["X"] for pair in key.values()} == {"v1", "v2"}
    assert all({pair["X"], pair["Y"]} == {"v1", "v2"} for pair in key.values())


def test_blind_review_hides_arms_and_manual_scores_round_trip(tmp_path):
    answers = [
        _answer(q["id"], arm, answer=f"{arm} says")
        for q in QUESTIONS
        for arm in score.ARMS
    ]
    (tmp_path / "answers.jsonl").write_text(
        "".join(json.dumps(a) + "\n" for a in answers)
    )
    score.write_blind(tmp_path, QUESTIONS)
    review = (tmp_path / "blind_review.csv").read_text()
    assert "v1" not in review.replace("v1 says", "").replace("v2 says", "")

    with (tmp_path / "manual_scores.csv").open() as source:
        rows = list(csv.DictReader(source))
    with pytest.raises(score.ScoringError, match="unknown label"):
        score.load_manual(tmp_path, QUESTIONS)
    for row in rows:
        row.update(label="wrong", reason="r", supported="n/a")
    rows[0]["reason"] = ""
    _write_manual(tmp_path, rows)
    with pytest.raises(score.ScoringError, match="needs a reason"):
        score.load_manual(tmp_path, QUESTIONS)
    rows[0]["reason"] = "r"
    _write_manual(tmp_path, rows)
    summary = score.write_final(tmp_path, QUESTIONS)
    assert summary["outcome"] == "no real difference"
    assert (tmp_path / "report.md").exists()


def _write_manual(directory, rows):
    with (directory / "manual_scores.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_failed_runs_count_as_wrong_and_pairs_are_counted():
    question = {
        "id": "q1",
        "category": "C2",
        "evidence_terms": ["x"],
        "answer_terms": [["x"]],
    }
    answers = [
        _answer("q1", "v1", status="failed"),
        _answer("q1", "v2", answer="x", evidence=[(1, "x")]),
    ]
    manual = {
        ("q1", "v1"): {"label": "correct", "supported": "no"},
        ("q1", "v2"): {"label": "correct", "supported": "yes"},
    }
    rows, summary = score.score([question], answers, manual)
    assert rows[0]["v1_label"] == "wrong"
    assert rows[0]["correct_pair"] == "win" and rows[0]["evidence_pair"] == "win"
    assert summary["nets"]["affected_correct"] == 1


@pytest.mark.parametrize(
    ("nets", "outcome"),
    [
        ((5, 3, -1, -1), "v2 helps"),
        ((5, 3, -2, 0), "v2 hurts"),
        ((-3, 0, 0, 0), "v2 hurts"),
        ((2, -2, 0, 0), "no real difference"),
        ((4, 3, 0, 0), "inconclusive"),
        ((6, 1, 0, 0), "inconclusive"),
    ],
)
def test_decision_rule(nets, outcome):
    names = (
        "affected_evidence",
        "affected_correct",
        "control_correct",
        "unanswerable_correct",
    )
    assert score.decide(dict(zip(names, nets))) == outcome


def test_section_path_counts_only_when_asked():
    question = {
        "evidence_terms": ["Contractors", "14 calendar days"],
        "answer_terms": [],
    }
    answer = _answer(
        "q", "v2", evidence=[(1, "The notice period is 14 calendar days.")]
    )
    answer["evidence"][0]["section_path"] = ["Staff Handbook", "Part B: Contractors"]
    assert score.evidence_rank(question, answer) is None
    assert score.evidence_rank(question, answer, with_section=True) == 1

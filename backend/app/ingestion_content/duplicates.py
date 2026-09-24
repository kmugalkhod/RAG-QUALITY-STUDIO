"""Reproducible project/run-scoped duplicate classification."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class DuplicateCandidate:
    identity: str
    source_kind: str
    raw_hash: str
    cleaned_hash: str
    text: str
    stable_order: int = 0


@dataclass(frozen=True)
class DuplicateDecision:
    outcome: str
    retained_identity: str
    excluded_identity: str | None
    method: str
    similarity: float
    reason: str

    def as_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "retained_identity": self.retained_identity,
            "excluded_identity": self.excluded_identity,
            "method": self.method,
            "similarity": self.similarity,
            "reason": self.reason,
        }


def normalized_fingerprint(text: str) -> str:
    normalized = " ".join(_TOKEN.findall(text.casefold()))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def simhash64(text: str) -> int:
    weights = [0] * 64
    for token in _TOKEN.findall(text.casefold())[:100_000]:
        digest = int.from_bytes(
            hashlib.sha256(token.encode("utf-8")).digest()[:8], "big"
        )
        for bit in range(64):
            weights[bit] += 1 if digest & (1 << bit) else -1
    return sum(1 << bit for bit, value in enumerate(weights) if value >= 0)


def simhash_similarity(left: int, right: int) -> float:
    return round(1 - ((left ^ right).bit_count() / 64), 6)


def _priority(candidate: DuplicateCandidate, policy) -> tuple:
    connector = {value: index for index, value in enumerate(policy.connector_priority)}
    pinned = set(policy.pinned_canonical_locations)
    return (
        0 if candidate.identity in pinned else 1,
        connector.get(candidate.source_kind, len(connector)),
        candidate.stable_order,
        candidate.identity,
    )


def classify_duplicates(
    candidates: list[DuplicateCandidate], policy
) -> dict[str, DuplicateDecision]:
    """Return a decision for every candidate without deleting any source revision."""

    ordered = sorted(candidates, key=lambda value: _priority(value, policy))
    retained: list[DuplicateCandidate] = []
    decisions: dict[str, DuplicateDecision] = {}
    simhashes: dict[str, int] = {}
    for candidate in ordered:
        match = None
        method = "unique"
        similarity = 0.0
        for prior in retained:
            if policy.exact_raw and candidate.raw_hash == prior.raw_hash:
                match, method, similarity = prior, "exact_raw_sha256", 1.0
                break
            if policy.exact_cleaned and candidate.cleaned_hash == prior.cleaned_hash:
                match, method, similarity = prior, "exact_cleaned_sha256", 1.0
                break
            if policy.normalized_sections and normalized_fingerprint(
                candidate.text
            ) == normalized_fingerprint(prior.text):
                match, method, similarity = prior, "normalized_sections_sha256", 1.0
                break
            if policy.near_duplicate:
                left = simhashes.setdefault(
                    candidate.identity, simhash64(candidate.text)
                )
                right = simhashes.setdefault(prior.identity, simhash64(prior.text))
                score = simhash_similarity(left, right)
                if score >= policy.near_duplicate_threshold and score > similarity:
                    match, method, similarity = (
                        prior,
                        policy.near_duplicate_method,
                        score,
                    )
        if match is None:
            retained.append(candidate)
            decisions[candidate.identity] = DuplicateDecision(
                outcome="retained",
                retained_identity=candidate.identity,
                excluded_identity=None,
                method=method,
                similarity=1.0,
                reason="No duplicate matched the saved policy.",
            )
        else:
            decisions[candidate.identity] = DuplicateDecision(
                outcome="excluded",
                retained_identity=match.identity,
                excluded_identity=candidate.identity,
                method=method,
                similarity=similarity,
                reason="Excluded in favor of the deterministic canonical source.",
            )
    return decisions

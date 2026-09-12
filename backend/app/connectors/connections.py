"""Provider-independent credential check boundary."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ConnectionCheck:
    outcome: str
    code: str


class ConnectionTester(Protocol):
    def check(self, credentials: dict) -> ConnectionCheck: ...


class UnavailableTester:
    def check(self, credentials: dict) -> ConnectionCheck:
        return ConnectionCheck("unavailable", "adapter_unavailable")


def tester_for(kind: str) -> ConnectionTester:
    # Real provider checks are registered by each complete connector phase.
    return UnavailableTester()

"""Shared immutable artifact storage and deterministic identity helpers."""

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from app.core.config import settings


def store(content: bytes) -> tuple[str, Path]:
    root = settings.storage_path
    root.mkdir(parents=True, exist_ok=True)
    name = uuid4().hex
    temporary = root / f"{name}.part"
    final = root / name
    with temporary.open("xb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, final)
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return name, final


def identity_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def config_hash(value: dict) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

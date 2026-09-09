"""Opt-in, bounded external check: never enabled by default CI."""

import os
import pytest
from app.providers.embeddings import configured, provider_for


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_EMBEDDINGS") != "1",
    reason="Live OpenRouter check requires RUN_LIVE_EMBEDDINGS=1 and server credentials.",
)
def test_live_openrouter_vectors():
    config = configured()
    vectors = provider_for(config).embed(
        ["The orchard grows apples.", "What does the orchard grow?"]
    )
    assert len(vectors) == 2
    assert all(len(v) == config.dimensions for v in vectors)

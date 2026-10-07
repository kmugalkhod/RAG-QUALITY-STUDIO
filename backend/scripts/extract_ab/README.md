# Extract v1/v2 comparison (spec 0004)

Scripts for `docs/specs/0004-extract-v1-v2-answer-quality.md`. They run inside the backend container against the local API (`AUTH_MODE=local`). The image does not mount the source, so copy the folder in first. From the repository root in Git Bash, set `MSYS_NO_PATHCONV=1` so container paths are not rewritten.

```sh
docker compose exec -T backend mkdir -p /app/scripts/extract_ab
docker compose cp backend/scripts/extract_ab/. backend:/app/scripts/extract_ab/
docker compose exec -T backend python scripts/extract_ab/run.py setup   /tmp/extract-ab
docker compose exec -T backend python scripts/extract_ab/run.py preview /tmp/extract-ab              # free
docker compose exec -T backend python scripts/extract_ab/run.py index   /tmp/extract-ab --allow-paid # embeddings
docker compose exec -T backend python scripts/extract_ab/run.py ask     /tmp/extract-ab --allow-paid # answers, $2 cap
docker compose exec -T backend python scripts/extract_ab/run.py fetch   /tmp/extract-ab
docker compose exec -T backend sh -c 'cd scripts/extract_ab && python score.py blind /tmp/extract-ab'
# Fill manual_scores.csv: labels from blind_review.csv only, then the supported pass.
docker compose exec -T backend sh -c 'cd scripts/extract_ab && python score.py final /tmp/extract-ab'
docker compose cp backend:/tmp/extract-ab/. <results folder>
```

- `setup` creates the project "Extract A/B 2026-10" once and records every ID in `state.json`. Re-running any stage reuses those IDs instead of repeating uploads, pipelines, indexes or paid answers.
- `make_corpus.py` writes the same bytes every time; the manifest records SHA-256 hashes, and `setup` refuses to continue if they change.
- Tests: `docker compose exec backend python -m pytest tests/test_extract_ab.py` (after copying `tests/test_extract_ab.py` into the container).

The 2026-10-07 results are in `docs/qa/extract-ab-2026-10-07/`.

# Development

Local setup and baseline verification commands are documented in [README](../README.md).

## Evaluation experiments

Set server-only `EVALUATOR_MODEL` (independent of `CHAT_MODEL`) and `OPENROUTER_API_KEY`, then recreate backend, worker and dispatcher. Response relevancy reuses the configured OpenRouter embedding model. `EVALUATOR_MAX_TOKENS` defaults to 4096; `DATASET_MAX_ROWS` defaults to 200 and `DATASET_MAX_BYTES` to 2097152. Model calls have no automatic paid retries. Keep the dispatcher running for progress and stale recovery.

In a project, open Experiments, download the example CSV, replace it with reviewed questions for that project's sources, preview, and import. Reference answers are optional; context recall is unavailable for rows without them. Choose one or two saved pipeline versions, select metrics, and run. Open a question in the comparison table to see answers, exact supplied evidence and available structured judge explanations. Export CSV or inspect the immutable snapshot. LLM scores require human review.

The opt-in `backend/scripts/check_experiment_live.py --project <sample-orchard-project> --version <saved-version> [--version <second-version>]` submits exactly three reviewed orchard questions through the running API. Only run against the matching orchard sample source; it creates persistent dataset and experiment records and makes paid calls. It cancels scheduling after a 15-minute deadline. Default automated tests use deterministic provider/evaluator doubles and do not use credentials.

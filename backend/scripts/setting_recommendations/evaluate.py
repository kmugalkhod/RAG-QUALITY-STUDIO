"""Field-agreement run of recommended Website settings on the labelled sites (spec 0011, Slice 3).

Free: HTTP only, no model or embedding calls, no database. For every row of
docs/qa/setting-recommendations-2026-10/labels.csv it runs the real probe
(`probe_website`, the product's SSRF-safe client, robots.txt and its own bounds:
at most 18 requests, 1 request per second per origin, Crawl-delay honoured) and
then `recommend()`, exactly as the worker does. It scores the result against
the label and today's baseline (baseline.csv) and writes results.csv beside them.

Run inside a throwaway backend container with this directory mounted:

    python scripts/setting_recommendations/evaluate.py [--only W1a,S1] [--save-signals DIR]

`--save-signals DIR` also writes each row's probe signals to DIR/<site_id>.json.
`--replay DIR` reads those files instead of probing, so a rule change can be
re-scored offline on the same evidence (no network).

Scoring follows "How Slice 3 will score" in that folder's README.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.connectors.base import ConnectorFailure  # noqa: E402
from app.connectors.safe_http import failure  # noqa: E402
from app.connectors.website_probe import ProbeSignals, probe_website  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.schemas.setting_recommendations import SettingRecommendationRequest  # noqa: E402
from app.services.setting_recommendations import inputs_for  # noqa: E402
from app.services.website_recommendation import (  # noqa: E402
    MAX_RUN_PAGES,
    RecommendationFailed,
    recommend,
)

QA = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "qa"
    / "setting-recommendations-2026-10"
)
CEILING = 200
# A pause between rows, so consecutive rows on one host (docs.python.org) stay polite.
ROW_PAUSE_SECONDS = 3

COLUMNS = [
    "site_id",
    "status",
    "error",
    "warnings",
    "requests",
    "mode",
    "sitemap_url",
    "allowed_origins",
    "include_prefixes",
    "exclude_prefixes",
    "max_pages",
    "max_depth",
    "requests_per_second",
    "reason_codes",
    "check_fields",
    "safe_origins",
    "safe_include",
    "safe_exclusions",
    "safe_speed",
    "safe_pages",
    "safe_none_row",
    "scope_safe",
    "mode_ok",
    "pages_ok",
    "depth_ok",
    "origins_match",
    "include_match",
    "exclusions_ok",
    "expected_exclusions_found",
    "speed_match",
    "warnings_ok",
    "touches_after",
    "touches_before",
    "notes",
]


def items(value: str) -> list[str]:
    """A `;` list from the CSV; `(none)` and `n/a` are empty."""
    value = value.strip()
    if value in ("", "(none)", "n/a") or value.startswith("n/a"):
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def origin(value: str) -> str:
    return value.rstrip("/")


def selection_for(entered: str) -> dict:
    urls = entered.split()
    if len(urls) > 1:
        return {"mode": "url_list", "urls": urls}
    url = urls[0]
    if re.search(r"\.xml(\.gz)?$", url.split("?")[0]):
        return {"mode": "sitemap", "sitemap_url": url}
    return {"mode": "crawl", "start_url": url}


def page_range(value: str) -> tuple[int, int] | None:
    match = re.match(r"^(\d+)-(\d+)$", value.strip())
    return (int(match.group(1)), int(match.group(2))) if match else None


def depth_range(value: str) -> tuple[int, int] | None:
    match = re.search(r"(\d+)-(\d+)", value)
    return (int(match.group(1)), int(match.group(2))) if match else None


def path_of(url: str) -> str:
    from urllib.parse import unquote, urlsplit

    return unquote(urlsplit(url).path or "/")


def must_stay(label: dict) -> list[str]:
    value = label["must_stay_included"]
    if value.startswith("all"):
        return [path_of(url) for url in label["entered_url"].split()]
    return [
        token.rstrip(")").strip()
        for token in re.findall(r"/[^\s;()]*", value)
        if token.startswith("/")
    ]


def no_wider(prefixes: list[str], bound: list[str]) -> bool:
    """Every prefix starts with a bound prefix; an empty bound allows anything."""
    if not bound:
        return True
    if not prefixes:
        return False
    return all(any(prefix.startswith(item) for item in bound) for prefix in prefixes)


def probe_row(site_id: str, selection: dict, replay: Path | None, save: Path | None):
    if replay is not None:
        data = json.loads((replay / f"{site_id}.json").read_text(encoding="utf-8"))
        if "failure" in data:
            raise failure(data["failure"]["code"], data["failure"]["message"])
        return ProbeSignals.from_json(data)
    try:
        signals = probe_website(selection, user_agent=settings.website_user_agent)
    except ConnectorFailure as exc:
        if save is not None:
            record = {"failure": {"code": exc.issue.code, "message": exc.issue.message}}
            (save / f"{site_id}.json").write_text(json.dumps(record), encoding="utf-8")
        raise
    if save is not None:
        (save / f"{site_id}.json").write_text(
            json.dumps(signals.as_json(), indent=1), encoding="utf-8"
        )
    return signals


def run_row(label: dict, replay: Path | None = None, save: Path | None = None) -> dict:
    selection = selection_for(label["entered_url"])
    request = SettingRecommendationRequest(
        target="website",
        source_node_id="source",
        selection=selection,
        other_sources_max_pages=0,
    )
    inputs, _ = inputs_for(request)
    inputs["page_ceiling"] = CEILING
    result: dict = {"site_id": label["site_id"], "input_mode": selection["mode"]}
    signals = None
    try:
        signals = probe_row(label["site_id"], inputs["selection"], replay, save)
        recommendation = recommend(signals, inputs, settings)
    except ConnectorFailure as exc:
        result.update(
            status="failed", error=exc.issue.message, warnings=[exc.issue.code]
        )
    except RecommendationFailed as exc:
        result.update(status="failed", error=str(exc), warnings=list(exc.warnings))
    else:
        config = recommendation.recommended
        result.update(
            status="succeeded",
            error="",
            warnings=[item["code"] for item in recommendation.warnings],
            config=config,
            fields=recommendation.fields,
        )
    result["requests"] = len(signals.requests) if signals is not None else ""
    return result


def score(label: dict, baseline: dict, result: dict) -> dict:
    row = {column: "" for column in COLUMNS}
    row.update(
        site_id=label["site_id"],
        status=result["status"],
        error=result["error"],
        warnings=";".join(result["warnings"]) or "(none)",
        requests=result["requests"],
        touches_before=baseline["touches_valid_safe"],
    )
    expected_modes = label["expected_mode"].split("|")
    expected_warnings = items(label["expected_warnings"])
    runnable = expected_modes[0] != "none"
    notes: list[str] = []

    if result["status"] != "succeeded":
        if runnable:
            row.update(scope_safe="yes", touches_after=baseline["touches_valid_safe"])
            notes.append("No recommendation; the form keeps today's values.")
        else:
            reported = all(code in result["warnings"] for code in expected_warnings)
            row.update(
                safe_none_row="yes" if reported else "no",
                scope_safe="yes" if reported else "no",
                warnings_ok="yes" if reported else "no",
            )
            notes.append(
                "Not runnable, and the analysis ended failed (no draft offered)."
            )
        row["notes"] = " ".join(notes)
        return row

    config = result["config"]
    fields = {item["path"]: item for item in result["fields"]}
    selection = config["selection"]
    mode = selection["mode"]
    origins = [origin(item) for item in config["allowed_origins"]]
    include = config.get("include_path_prefixes") or []
    exclude = config.get("exclude_path_prefixes") or []
    row.update(
        mode=mode,
        sitemap_url=selection.get("sitemap_url", ""),
        allowed_origins=";".join(origins),
        include_prefixes=";".join(include) or "(none)",
        exclude_prefixes=";".join(exclude) or "(none)",
        max_pages=config["max_pages"],
        max_depth=config["max_depth"],
        requests_per_second=config["requests_per_second"],
        reason_codes=";".join(
            f"{path}={item['rationale_code']}" for path, item in fields.items()
        ),
        check_fields=";".join(path for path, item in fields.items() if item["check"])
        or "(none)",
    )

    if not runnable:
        # A `none` row: the expected warning must be reported, and the result
        # must not be a crawl or sitemap draft presented as ready to run.
        reported = all(code in result["warnings"] for code in expected_warnings)
        ready_scope = mode in ("crawl", "sitemap") and not reported
        ok = (
            reported
            and not ready_scope
            and (mode in expected_modes or mode == "single_url")
        )
        row.update(
            safe_none_row="yes" if ok else "no",
            scope_safe="yes" if ok else "no",
            warnings_ok="yes" if reported else "no",
            mode_ok="yes" if mode in expected_modes else "no",
        )
        row["notes"] = "Not runnable; recommendation succeeded with the warnings shown."
        return row

    expected_origins = [origin(item) for item in items(label["expected_origins"])]
    label_include = items(label["expected_include_prefixes"])
    baseline_include = items(baseline["baseline_include_prefixes"])
    stay = must_stay(label)
    start_path = path_of(selection.get("start_url") or label["entered_url"].split()[0])
    pages = page_range(label["page_range"])
    depth = depth_range(label["max_depth"])
    max_speed = float(label["max_speed"])
    rps = float(config["requests_per_second"])

    safe_origins = set(origins) <= set(expected_origins)
    include_vs_label = no_wider(include, label_include)
    include_vs_baseline = no_wider(include, baseline_include)
    safe_include = include_vs_label and include_vs_baseline
    known_mismatch = (
        label["site_id"] == "S3" and include_vs_baseline and not include_vs_label
    )
    excluded_paths = [
        path
        for path in stay + [start_path]
        if any(path.startswith(item) for item in exclude)
    ]
    safe_exclusions = not excluded_paths
    safe_speed = rps <= max_speed + 1e-9 and rps <= 2
    safe_pages = config["max_pages"] <= CEILING and config["max_pages"] <= MAX_RUN_PAGES
    counted_include = safe_include or known_mismatch
    scope_safe = all(
        (safe_origins, counted_include, safe_exclusions, safe_speed, safe_pages)
    )
    acceptable = items(label["acceptable_exclusions"])
    exclusions_ok = all(item in acceptable for item in exclude)
    found = [item for item in acceptable if item in exclude]

    row.update(
        safe_origins="yes" if safe_origins else "no",
        safe_include=(
            "known label mismatch"
            if known_mismatch
            else ("yes" if safe_include else "no")
        ),
        safe_exclusions="yes"
        if safe_exclusions
        else f"no ({';'.join(excluded_paths)})",
        safe_speed="yes" if safe_speed else "no",
        safe_pages="yes" if safe_pages else "no",
        scope_safe="yes" if scope_safe else "no",
        mode_ok="yes" if mode in expected_modes else "no",
        pages_ok=(
            "yes" if pages and pages[0] <= config["max_pages"] <= pages[1] else "no"
        ),
        depth_ok=(
            "n/a"
            if mode != "crawl" or depth is None
            else ("yes" if depth[0] <= config["max_depth"] <= depth[1] else "no")
        ),
        origins_match="yes" if set(origins) == set(expected_origins) else "no",
        include_match="yes" if set(include) == set(label_include) else "no",
        exclusions_ok="yes" if exclusions_ok else "no",
        expected_exclusions_found=f"{len(found)} of {len(acceptable)}"
        if acceptable
        else "n/a",
        speed_match="yes" if abs(rps - max_speed) < 1e-9 else "no",
        warnings_ok=(
            "yes"
            if all(code in result["warnings"] for code in expected_warnings)
            else "no"
        ),
    )
    # Fields a user must still change for a valid, safe draft: the address,
    # plus each unsafe field. A start page outside the origins cannot be fetched.
    touches = 1
    if not safe_origins or not set(expected_origins) <= set(origins):
        touches += 1
    if not safe_include:
        touches += 1
    if not safe_speed:
        touches += 1
    row["touches_after"] = touches
    if known_mismatch:
        notes.append(
            "Include is no wider than today's derivation but wider than the /lang label, "
            "which the folder rule cannot express (known label mismatch)."
        )
    row["notes"] = " ".join(notes)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default="", help="Comma-separated site IDs")
    parser.add_argument("--out", default=str(QA / "results.csv"))
    parser.add_argument("--save-signals", type=Path, help="Write probe signals here")
    parser.add_argument("--replay", type=Path, help="Read saved signals; no network")
    args = parser.parse_args()
    if args.save_signals:
        args.save_signals.mkdir(parents=True, exist_ok=True)
    with (QA / "labels.csv").open(encoding="utf-8") as handle:
        labels = list(csv.DictReader(handle))
    with (QA / "baseline.csv").open(encoding="utf-8") as handle:
        baselines = {row["site_id"]: row for row in csv.DictReader(handle)}
    only = {item for item in args.only.split(",") if item}
    rows = []
    for label in labels:
        if only and label["site_id"] not in only:
            continue
        if rows and args.replay is None:
            time.sleep(ROW_PAUSE_SECONDS)
        started = time.monotonic()
        result = run_row(label, args.replay, args.save_signals)
        row = score(label, baselines[label["site_id"]], result)
        rows.append(row)
        print(
            f"{row['site_id']}: {row['status']} mode={row['mode'] or '-'} "
            f"include={row['include_prefixes'] or '-'} pages={row['max_pages'] or '-'} "
            f"rps={row['requests_per_second'] or '-'} safe={row['scope_safe']} "
            f"warnings={row['warnings']} ({time.monotonic() - started:.0f} s)",
            flush=True,
        )
        if row["error"]:
            print(f"  error: {row['error']}", flush=True)
    with Path(args.out).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    summarize(rows, labels)


def summarize(rows: list[dict], labels: list[dict]) -> None:
    by_id = {label["site_id"]: label for label in labels}
    runnable = [
        row
        for row in rows
        if not by_id[row["site_id"]]["expected_mode"].startswith("none")
    ]
    reachable = [row for row in runnable if row["status"] == "succeeded"]
    unsafe = [row["site_id"] for row in rows if row["scope_safe"] != "yes"]

    def share(subset: list[dict], key: str) -> str:
        hits = sum(1 for row in subset if row[key] == "yes")
        return f"{hits}/{len(subset)}"

    single = sum(1 for row in runnable if str(row["touches_after"]) == "1")
    before = sum(1 for row in runnable if str(row["touches_before"]) == "1")
    print(f"scope-safety failures: {len(unsafe)} {unsafe}")
    print(f"mode correct (reachable runnable): {share(reachable, 'mode_ok')}")
    print(f"pages in range (reachable runnable): {share(reachable, 'pages_ok')}")
    print(f"one touch: before {before}/{len(runnable)}, after {single}/{len(runnable)}")


if __name__ == "__main__":
    main()

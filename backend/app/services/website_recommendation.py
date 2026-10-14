"""Code rules that turn Website probe signals into recommended settings.

Pure module (spec 0011): no database, no network. `recommend()` builds a
candidate `WebsiteConfig`, runs the same validators that saves and runs use,
and explains every value with a reason built from a fixed template.

`website-rules-v1`, Slice 1: allowed origins, include path prefixes and crawl
speed are computed; the remaining fields keep product defaults.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

from pydantic import ValidationError

from app.connectors.safe_http import url_origin
from app.connectors.website import WebsiteScopeTooLarge, resolve_website_fetch_policy
from app.connectors.website_probe import ProbeSignals, same_site
from app.schemas.ingestion import WebsiteConfig

PROBE_VERSION = "website-probe-v1"
RULES_VERSION = "website-rules-v1"

MAX_RUN_PAGES = 2500
DEFAULT_MAX_PAGES = 50
DEFAULT_MAX_DEPTH = 3
DEFAULT_RPS = 2.0
MIN_RPS = 0.1
SLOW_RESPONSE_MS = 2000
LINK_SHARE = 0.5

# One sentence per reason code; values are measured numbers or the user's own
# input, never page text.
RATIONALE = {
    "origins_start": "Pages are fetched only from {origin}, the address you entered.",
    "origins_redirect": (
        "{entered} redirects to {final} on the same site, so both are allowed."
    ),
    "include_redirect_folder": (
        "{entered_path} redirects to the folder {prefix}, so only pages under "
        "{prefix} are crawled."
    ),
    "include_links_folder": (
        "{below} of the start page's {total} links on this site are under {prefix}, "
        "so only that section is crawled."
    ),
    "include_folder": "Only pages under {prefix}, the folder of the address, are crawled.",
    "include_none": "The address is the top of the site, so every path is allowed.",
    "rps_default": (
        "robots.txt sets no crawl delay and the site answered promptly, so the "
        "default {rps:g} requests per second is used."
    ),
    "rps_crawl_delay": (
        "robots.txt asks for {delay:g} seconds between requests, so the speed is "
        "{rps:g} requests per second."
    ),
    "rps_slow_site": (
        "The site answered slowly or asked for fewer requests during the check, so "
        "the speed is {rps:g} requests per second."
    ),
    "pages_budget": (
        "The other Website sources already use {other:,} of the {limit:,}-page "
        "pipeline limit, so this source may fetch {pages:,} pages."
    ),
    "default_no_evidence": "The default; this check does not measure it yet.",
}

WARNINGS = {
    "redirect_other_site": (
        "The address redirects to a different site. Only the address you entered "
        "is allowed; enter the other site's address to crawl it instead."
    ),
}

LABELS = {
    "selection": "Discovery",
    "allowed_origins": "Allowed sites",
    "include_path_prefixes": "Pages under",
    "exclude_path_prefixes": "Excluded",
    "max_pages": "Maximum pages",
    "max_depth": "Crawl depth",
    "requests_per_second": "Crawl speed",
}

# The risk of overriding each value, shown when a user edit differs.
RISK = {
    "selection": "medium",
    "allowed_origins": "high",
    "include_path_prefixes": "high",
    "exclude_path_prefixes": "medium",
    "max_pages": "high",
    "max_depth": "medium",
    "requests_per_second": "high",
}

MANAGED_PATHS = tuple(LABELS)


class RecommendationFailed(ValueError):
    """No candidate passed validation; the safe message is shown to the user."""


@dataclass
class Recommendation:
    recommended: dict
    fields: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)


@dataclass
class _Value:
    value: object
    basis: str
    code: str
    context: dict = field(default_factory=dict)
    check: bool = False


def _folder(path: str) -> list[str]:
    """Today's derived include prefix: `/docs/x` → `/docs/`; none for `/`."""
    directory = path[: path.rfind("/") + 1]
    return [directory] if directory and directory != "/" else []


def _path(url: str) -> str:
    return unquote(urlsplit(url).path or "/")


def _origins(signals: ProbeSignals) -> tuple[_Value, str]:
    entered = signals.entered_origin
    final_url = signals.start_page.get("final_url") or signals.entered_url
    final = url_origin(final_url)
    if final != entered and same_site(entered, final):
        return (
            _Value(
                [entered, final],
                "computed",
                "origins_redirect",
                {"entered": entered, "final": final},
            ),
            final_url,
        )
    return _Value([entered], "computed", "origins_start", {"origin": entered}), (
        final_url if final == entered else signals.entered_url
    )


def _include(signals: ProbeSignals, final_url: str) -> _Value:
    entered_path = _path(signals.entered_url)
    path = _path(final_url)
    start = signals.start_page
    if path in ("", "/"):
        value, code, context = [], "include_none", {}
    elif path.endswith("/"):
        value = [path]
        code = "include_redirect_folder" if path != entered_path else "include_folder"
        context = {"entered_path": entered_path, "prefix": path}
    elif (
        start.get("links_same_origin", 0) > 0
        and start.get("links_below_path", 0) >= LINK_SHARE * start["links_same_origin"]
    ):
        prefix = path + "/"
        value, code = [prefix], "include_links_folder"
        context = {
            "below": start["links_below_path"],
            "total": start["links_same_origin"],
            "prefix": prefix,
        }
    else:
        value = _folder(path)
        code = "include_folder" if value else "include_none"
        context = {"prefix": value[0]} if value else {}
    # Never wider than today's derivation from the entered or the final URL.
    bases = [(_folder(entered_path) or [""])[0], (_folder(path) or [""])[0]]
    narrowest = value[0] if value else ""
    if not any(narrowest.startswith(base) for base in bases):
        fallback = _folder(entered_path)
        return _Value(fallback, "default", "default_no_evidence")
    return _Value(value, "computed", code, context)


def _rps_ceiling(crawl_delay: float | None) -> float:
    rate = DEFAULT_RPS if not crawl_delay else min(DEFAULT_RPS, 1 / crawl_delay)
    # Rounded down, so the value never asks for more than robots.txt allows.
    return max(MIN_RPS, math.floor(rate * 100) / 100)


def _speed(signals: ProbeSignals) -> _Value:
    delay = signals.robots.get("crawl_delay")
    rate = _rps_ceiling(delay)
    median = signals.start_page.get("median_response_ms")
    slow = bool(signals.start_page.get("throttled")) or (
        median is not None and median > SLOW_RESPONSE_MS
    )
    if slow and rate > 1:
        return _Value(1.0, "computed", "rps_slow_site", {"rps": 1.0})
    if delay:
        return _Value(
            rate, "computed", "rps_crawl_delay", {"delay": delay, "rps": rate}
        )
    return _Value(rate, "computed", "rps_default", {"rps": rate})


def _candidate(selection: dict, values: dict[str, _Value]) -> dict:
    return {
        "kind": "website",
        "selection": selection,
        **{path: values[path].value for path in MANAGED_PATHS if path != "selection"},
    }


def _defaults(selection: dict, other_pages: int, ceiling: int) -> dict[str, _Value]:
    room = MAX_RUN_PAGES - other_pages
    pages = min(DEFAULT_MAX_PAGES, ceiling)
    values = {
        "selection": _Value(selection, "default", "default_no_evidence"),
        "allowed_origins": _Value(
            [url_origin(selection["start_url"])], "default", "default_no_evidence"
        ),
        "include_path_prefixes": _Value(
            _folder(_path(selection["start_url"])), "default", "default_no_evidence"
        ),
        "exclude_path_prefixes": _Value([], "default", "default_no_evidence"),
        "max_pages": _Value(pages, "default", "default_no_evidence"),
        "max_depth": _Value(DEFAULT_MAX_DEPTH, "default", "default_no_evidence"),
        "requests_per_second": _Value(DEFAULT_RPS, "default", "default_no_evidence"),
    }
    if pages > room:
        values["max_pages"] = _Value(
            max(1, room),
            "computed",
            "pages_budget",
            {"other": other_pages, "limit": MAX_RUN_PAGES, "pages": max(1, room)},
        )
    return values


def _valid(candidate: dict, other_pages: int, settings) -> bool:
    try:
        WebsiteConfig.model_validate(candidate)
        resolve_website_fetch_policy(candidate, settings)
    except (ValidationError, WebsiteScopeTooLarge):
        return False
    return candidate["max_pages"] + other_pages <= MAX_RUN_PAGES


def _display(path: str, value):
    if path == "allowed_origins":
        return [url_origin(str(item)) for item in value]
    return value


def recommend(signals: ProbeSignals, inputs: dict, settings) -> Recommendation:
    """Recommended `WebsiteConfig` for `inputs`, explained field by field."""
    selection = inputs["selection"]
    other_pages = int(inputs.get("other_sources_max_pages", 0))
    ceiling = int(
        inputs.get("page_ceiling", settings.setting_recommendations_page_ceiling)
    )
    defaults = _defaults(selection, other_pages, ceiling)
    values = dict(defaults)
    origins, final_url = _origins(signals)
    values["allowed_origins"] = origins
    values["include_path_prefixes"] = _include(signals, final_url)
    values["requests_per_second"] = _speed(signals)

    # Guards: each failing field falls back to its default on its own.
    permitted = {signals.entered_origin}
    if same_site(signals.entered_origin, url_origin(final_url)):
        permitted.add(url_origin(final_url))
    if not set(values["allowed_origins"].value) <= permitted:
        values["allowed_origins"] = defaults["allowed_origins"]
    if values["requests_per_second"].value > _rps_ceiling(
        signals.robots.get("crawl_delay")
    ):
        values["requests_per_second"] = defaults["requests_per_second"]
    if values["max_pages"].value > ceiling:
        values["max_pages"] = _Value(ceiling, "default", "default_no_evidence")

    candidate = _candidate(selection, values)
    if not _valid(candidate, other_pages, settings):
        values = dict(defaults)
        candidate = _candidate(selection, values)
        if not _valid(candidate, other_pages, settings):
            raise RecommendationFailed(
                "No recommended settings passed validation for this address. "
                "Keep the current settings or change the address."
            )
    recommended = WebsiteConfig.model_validate(candidate).model_dump(mode="json")
    fields = []
    for path in MANAGED_PATHS:
        item = values[path]
        fields.append(
            {
                "path": path,
                "label": LABELS[path],
                "value": _display(path, recommended[path]),
                "basis": item.basis,
                "risk": RISK[path],
                "rationale_code": item.code,
                "rationale": RATIONALE[item.code].format(**item.context),
                "check": item.check,
            }
        )
    warnings = [
        {"code": code, "message": WARNINGS[code]}
        for code in signals.warnings
        if code in WARNINGS
    ]
    return Recommendation(recommended=recommended, fields=fields, warnings=warnings)

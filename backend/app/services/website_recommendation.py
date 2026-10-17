"""Code rules that turn Website probe signals into recommended settings.

Pure module (spec 0011): no database, no network. `recommend()` builds a
candidate `WebsiteConfig`, runs the same validators that saves and runs use,
and explains every value with a reason built from a fixed template.

`website-rules-v1`: discovery mode, allowed origins, include and exclude path
prefixes, maximum pages, crawl depth and crawl speed, for crawl, sitemap,
URL-list and single-page input. A field that fails a guard or validation
falls back to its default on its own, and validation runs again.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

from pydantic import ValidationError

from app.connectors.safe_http import url_origin
from app.connectors.website import (
    MAX_NESTED_SITEMAPS,
    WebsiteScopeTooLarge,
    resolve_website_fetch_policy,
)
from app.connectors.website_probe import (
    UTILITY_SEGMENTS,
    ProbeSignals,
    folder_prefix,
    include_scope,
    same_site,
    section_prefix,
)
from app.schemas.ingestion import WebsiteConfig

PROBE_VERSION = "website-probe-v1"
RULES_VERSION = "website-rules-v1"

MAX_RUN_PAGES = 2500
DEFAULT_MAX_PAGES = 50
DEFAULT_MAX_DEPTH = 3
DEFAULT_RPS = 2.0
MIN_RPS = 0.1
SLOW_RESPONSE_MS = 2000
# Sitemap mode needs this many in-scope URLs and this share (percent) of the
# in-scope pages found by links.
SITEMAP_MIN_URLS = 5
SITEMAP_MIN_COVERAGE_PERCENT = 80
OPEN_FRONTIER_MIN_PAGES = 50
# Room above the pages an open frontier showed. The labelled sites (2026-10)
# fit 1.25; the earlier 2 x N overshot every open docs site.
OPEN_FRONTIER_HEADROOM_PERCENT = 125
LANGUAGE_CODE = re.compile(r"^[a-z]{2}(-[a-z]{2,4})?$", re.IGNORECASE)

# One sentence per reason code; values are measured numbers or the user's own
# input, never page text.
RATIONALE = {
    "mode_sitemap": (
        "The site's sitemap lists {listed:,} pages in scope, and the sample found "
        "{matched:,} of the {linked:,} linked pages in it, so the sitemap is read."
    ),
    "mode_crawl_no_sitemap": (
        "The site has no sitemap the check could read, so links are followed "
        "from the address."
    ),
    "mode_crawl_sitemap_partial": (
        "The site's sitemap lists {listed:,} pages in scope and holds {matched:,} "
        "of the {linked:,} linked pages, too few to rely on, so links are followed "
        "from the address."
    ),
    "mode_sitemap_input": "You entered a sitemap, so the pages it lists are read.",
    "mode_url_list": "You entered a list of URLs, so exactly those pages are read.",
    "mode_single_url": "You entered one page, so only that page is read.",
    "origins_start": "Pages are fetched only from {origin}, the address you entered.",
    "origins_redirect": (
        "{entered} redirects to {final} on the same site, so both are allowed."
    ),
    "origins_url_list": "Pages are fetched only from the sites of the listed URLs.",
    "include_redirect_folder": (
        "{entered_path} redirects to the folder {prefix}, so only pages under "
        "{prefix} are crawled."
    ),
    "include_links_folder": (
        "{below} of the start page's {total} links on this site are under {prefix}, "
        "so only that section is crawled."
    ),
    "include_folder": "Only pages under {prefix}, the folder of the address, are crawled.",
    "include_none": (
        "The address is at the top level of the site, so pages anywhere on the "
        "site are allowed."
    ),
    "filters_not_used": "Path filters apply only to crawls and sitemaps.",
    "exclude_utility_pattern": (
        "{utility} hold search, feed or other utility pages, so they are skipped."
    ),
    "exclude_language": (
        "{languages} are other-language versions of the start page, so they are "
        "skipped."
    ),
    "exclude_none": "The check found no utility or other-language sections to skip.",
    "pages_sitemap": (
        "The sitemap lists {count:,} pages in scope, so up to {pages:,} are fetched."
    ),
    "pages_crawl_closed": (
        "The start page and the sampled pages link to {count:,} pages in scope and "
        "no others, so up to {pages:,} are fetched."
    ),
    "pages_crawl_open": (
        "The sampled pages keep linking to new pages, so the site has more than the "
        "{count:,} found; up to {pages:,} are fetched."
    ),
    "pages_crawl_open_sitemap": (
        "The sampled pages keep linking to new pages and the sitemap lists "
        "{count:,} pages in scope, so up to {pages:,} are fetched."
    ),
    "pages_budget": (
        "The other Website sources already use {other:,} of the {limit:,}-page "
        "pipeline limit, so this source may fetch {pages:,} pages."
    ),
    "pages_deadline": (
        "At {rps:g} requests per second the server's {seconds:,.0f}-second crawl "
        "limit allows {pages:,} pages."
    ),
    "pages_url_list": "The list has {pages:,} URLs, so all of them are fetched.",
    "pages_not_used": "Only the page you entered is fetched; this limit is not used.",
    "depth_toc": (
        "The sampled pages link to no pages in scope beyond the start page's "
        "{l1:,} links, so one link hop reaches them all."
    ),
    "depth_two": (
        "The sampled pages link to {l2:,} new pages, no more than the start page's "
        "{l1:,}, so two link hops are followed."
    ),
    "depth_default": (
        "The sampled pages link to {l2:,} new pages, more than the start page's "
        "{l1:,}, so the default {depth} link hops are followed."
    ),
    "depth_not_used": "Crawl depth applies only when links are followed.",
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
    "default_no_evidence": (
        "The default, because the site check found no evidence for another value."
    ),
}

# Sentences appended to a reason when they apply.
NOTES = {
    "ceiling": " That is capped at the {ceiling:,}-page recommendation ceiling.",
    "lower_bound": " Some nested sitemaps were not read, so there may be more.",
    "rps_floor": (
        " 0.1 is the slowest setting; the crawler still waits {delay:g} seconds "
        "between requests."
    ),
    "language": (
        " {languages} are other-language versions of the start page, so they are "
        "skipped too."
    ),
}

WARNINGS = {
    "redirect_other_site": (
        "The address redirects to a different site. Only the address you entered "
        "is allowed; enter the other site's address to crawl it instead."
    ),
    "client_rendered": (
        "The start page shows almost no text without JavaScript. Pages that need "
        "JavaScript cannot be read; use server-rendered pages or a sitemap of them."
    ),
    "robots_blocks_start": (
        "robots.txt disallows the start URL, so it cannot be crawled. Choose an "
        "address the site allows."
    ),
    "robots_blocks_urls": (
        "robots.txt disallows some of the listed URLs; they will be skipped."
    ),
    "non_html_start": (
        "The address is not an HTML page. Upload the file as a document, or use an "
        "S3 source for files."
    ),
    "all_links_off_origin": (
        "Every link on the start page leads to another site, so a crawl would stop "
        "at the start page."
    ),
    "start_not_found": "The start page was not found. Check the address.",
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

    def __init__(self, message: str, warnings: list[str] | None = None):
        super().__init__(message)
        self.warnings = warnings or []


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
    notes: list[str] = field(default_factory=list)

    def rationale(self) -> str:
        return RATIONALE[self.code].format(**self.context) + "".join(
            NOTES[note].format(**self.context) for note in self.notes
        )


def _path(url: str) -> str:
    return unquote(urlsplit(url).path or "/")


def _ceil10(value: int) -> int:
    return -(-value // 10) * 10


def _selection_urls(selection: dict) -> list[str]:
    mode = selection["mode"]
    if mode == "url_list":
        return [str(url) for url in selection["urls"]]
    key = {"crawl": "start_url", "sitemap": "sitemap_url", "single_url": "url"}[mode]
    return [str(selection[key])]


def warning_items(codes: list[str]) -> list[dict]:
    """Warning codes as `{code, message}`; unknown codes are not shown."""
    return [
        {"code": code, "message": WARNINGS[code]}
        for code in dict.fromkeys(codes)
        if code in WARNINGS
    ]


def _robots_facts(signals: ProbeSignals) -> list[dict]:
    return [item for item in [signals.robots, *signals.extra_robots] if item]


def _crawl_delay(signals: ProbeSignals) -> float | None:
    delays = [
        item["crawl_delay"]
        for item in _robots_facts(signals)
        if item.get("crawl_delay")
    ]
    return max(delays) if delays else None


def _rps_ceiling(crawl_delay: float | None) -> float:
    rate = DEFAULT_RPS if not crawl_delay else min(DEFAULT_RPS, 1 / crawl_delay)
    # Rounded down, so the value never asks for more than robots.txt allows;
    # 0.1 is the slowest valid setting, and the crawler honours longer delays.
    return max(MIN_RPS, math.floor(rate * 100) / 100)


def _effective_rps(rps: float, crawl_delay: float | None) -> float:
    """The rate the connector really achieves: robots.txt can only slow it."""
    return min(rps, 1 / crawl_delay) if crawl_delay else rps


# Field rules ----------------------------------------------------------------


def _origins(signals: ProbeSignals, selection: dict) -> tuple[_Value, str]:
    if selection["mode"] == "url_list":
        origins = list(
            dict.fromkeys(url_origin(url) for url in _selection_urls(selection))
        )
        return _Value(origins, "computed", "origins_url_list"), signals.entered_url
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
    start = signals.start_page
    value, code, context = include_scope(
        signals.entered_url,
        final_url,
        start.get("links_same_origin", 0),
        start.get("links_below_path", 0),
    )
    if code == "default_no_evidence":
        return _Value(value, "default", code)
    # A page (not a folder) whose parent is the root widens to the whole site,
    # exactly as today's derivation does; ask the user to check it.
    check = not value and _path(final_url) not in ("", "/")
    return _Value(value, "computed", code, context, check=check)


def _mode(signals: ProbeSignals, selection: dict) -> _Value:
    sitemap = signals.sitemap
    listed = sitemap.get("in_scope", 0)
    linked = signals.links.get("linked_total", 0)
    matched = sitemap.get("linked_in_sitemap", 0)
    context = {"listed": listed, "linked": linked, "matched": matched}
    if not sitemap.get("found"):
        return _Value(selection, "computed", "mode_crawl_no_sitemap")
    covered = linked > 0 and matched * 100 >= SITEMAP_MIN_COVERAGE_PERCENT * linked
    if sitemap.get("url") and listed >= SITEMAP_MIN_URLS and covered:
        return _Value(
            {"mode": "sitemap", "sitemap_url": sitemap["url"]},
            "computed",
            "mode_sitemap",
            context,
        )
    return _Value(selection, "computed", "mode_crawl_sitemap_partial", context)


def _exclusions(
    signals: ProbeSignals, include: list[str], start_paths: list[str]
) -> tuple[_Value, list[dict]]:
    """Utility and other-language sections; returns the value and the
    excluded sections (for the page count)."""
    lang = (signals.start_page.get("html_lang") or "").lower()
    alternates = set()
    for item in signals.start_page.get("hreflang") or []:
        if item.get("lang", "").lower() == "x-default" or not item.get("url"):
            continue
        segment = _path(item["url"]).strip("/").split("/", 1)[0]
        if segment:
            alternates.add(segment.lower())
    utility, languages, excluded = [], [], []
    for section in signals.sections:
        segment = section["segment"]
        if section["count"] < 2 or segment == signals.start_section:
            continue
        prefix = section_prefix(segment, include, section.get("exact", False))
        if any(path.startswith(prefix) for path in start_paths):
            continue
        if segment in UTILITY_SEGMENTS or (
            segment == "page" and section.get("numbered")
        ):
            utility.append(prefix)
        elif (
            not include
            and LANGUAGE_CODE.match(segment)
            and segment.lower() in alternates
            and segment.lower() != lang
        ):
            languages.append(prefix)
        else:
            continue
        excluded.append(section)
    value = (utility + languages)[:50]
    excluded = excluded[: len(value)]
    if not value:
        return _Value([], "computed", "exclude_none"), []
    context = {"utility": ", ".join(utility), "languages": ", ".join(languages)}
    if utility:
        notes = ["language"] if languages else []
        return (
            _Value(value, "computed", "exclude_utility_pattern", context, notes=notes),
            excluded,
        )
    return _Value(value, "computed", "exclude_language", context), excluded


def _pages(
    signals: ProbeSignals,
    selection: dict,
    excluded: list[dict],
    origins: list[str],
    rps: float,
    ceiling: int,
    room: int,
    settings,
) -> _Value:
    mode = selection["mode"]
    if mode == "url_list":
        count = len(selection["urls"])
        return _Value(count, "computed", "pages_url_list", {"pages": count})
    if mode == "single_url":
        return _Value(
            max(1, min(DEFAULT_MAX_PAGES, ceiling, room)), "default", "pages_not_used"
        )
    notes, check = [], False
    if mode == "sitemap":
        count = signals.sitemap.get("in_scope", 0) - sum(
            item.get("sitemap", 0) for item in excluded
        )
        base = _ceil10(-(-count * 11 // 10))
        code = "pages_sitemap"
        if signals.sitemap.get("lower_bound"):
            notes.append("lower_bound")
            check = True
    else:
        count = (
            1
            + signals.links.get("linked_total", 0)
            - sum(item.get("links", 0) for item in excluded)
        )
        if signals.links.get("frontier") == "closed":
            base, code = _ceil10(-(-count * 11 // 10)), "pages_crawl_closed"
        else:
            code, check = "pages_crawl_open", True
            # A partial sitemap can still count more in-scope pages than the
            # probe could reach by links (a blog's dated posts).
            listed = signals.sitemap.get("in_scope", 0) - sum(
                item.get("sitemap", 0) for item in excluded
            )
            if signals.sitemap.get("found") and listed > count:
                count, code = listed, "pages_crawl_open_sitemap"
                if signals.sitemap.get("lower_bound"):
                    notes.append("lower_bound")
            room_above = -(-count * OPEN_FRONTIER_HEADROOM_PERCENT // 100)
            base = _ceil10(max(OPEN_FRONTIER_MIN_PAGES, room_above))
    count = max(count, 0)
    pages = max(1, min(ceiling, room, base))
    context = {"count": count, "pages": pages, "ceiling": ceiling}
    if room < min(ceiling, base):
        other = MAX_RUN_PAGES - room
        code, notes = "pages_budget", []
        context.update(other=other, limit=MAX_RUN_PAGES)
    elif ceiling < base:
        notes.insert(0, "ceiling")
    # Fit the server's crawl deadline at the rate the crawl really runs.
    effective = _effective_rps(rps, _crawl_delay(signals))
    overhead = len(origins) + (1 + MAX_NESTED_SITEMAPS if mode == "sitemap" else 0)
    seconds = settings.website_deadline_max_seconds
    fits = math.floor(seconds * effective) - overhead
    if pages > fits:
        pages = max(1, fits)
        code, notes = "pages_deadline", []
        context.update(pages=pages, rps=round(effective, 3), seconds=seconds)
    context["pages"] = pages
    return _Value(pages, "computed", code, context, check=check, notes=notes)


def _depth(signals: ProbeSignals, mode: str) -> _Value:
    if mode != "crawl":
        return _Value(DEFAULT_MAX_DEPTH, "default", "depth_not_used")
    links = signals.links
    l1, l2 = links.get("l1", 0), links.get("l2", 0)
    context = {"l1": l1, "l2": l2, "depth": DEFAULT_MAX_DEPTH}
    if l1 and not links.get("sampled"):
        # No linked page could be read, so L2 was not measured.
        return _Value(DEFAULT_MAX_DEPTH, "default", "default_no_evidence", check=True)
    if l2 == 0:
        return _Value(1, "computed", "depth_toc", context)
    if l2 <= l1:
        return _Value(2, "computed", "depth_two", context)
    return _Value(DEFAULT_MAX_DEPTH, "computed", "depth_default", context)


def _speed(signals: ProbeSignals) -> _Value:
    delay = _crawl_delay(signals)
    rate = _rps_ceiling(delay)
    timing = signals.timing or signals.start_page
    median = timing.get("median_response_ms")
    slow = bool(timing.get("throttled")) or (
        median is not None and median > SLOW_RESPONSE_MS
    )
    if slow and rate > 1:
        return _Value(1.0, "computed", "rps_slow_site", {"rps": 1.0})
    if delay:
        notes = ["rps_floor"] if 1 / delay < MIN_RPS else []
        return _Value(
            rate,
            "computed",
            "rps_crawl_delay",
            {"delay": delay, "rps": rate},
            notes=notes,
        )
    return _Value(rate, "computed", "rps_default", {"rps": rate})


# Assembly and validation ----------------------------------------------------


def _candidate(values: dict[str, _Value]) -> dict:
    return {
        "kind": "website",
        **{path: values[path].value for path in MANAGED_PATHS},
    }


def _defaults(selection: dict, other_pages: int, ceiling: int) -> dict[str, _Value]:
    room = MAX_RUN_PAGES - other_pages
    urls = _selection_urls(selection)
    mode = selection["mode"]
    if mode == "url_list":
        pages = len(urls)
    else:
        pages = min(DEFAULT_MAX_PAGES, ceiling)
    values = {
        "selection": _Value(selection, "default", "default_no_evidence"),
        "allowed_origins": _Value(
            list(dict.fromkeys(url_origin(url) for url in urls)),
            "default",
            "default_no_evidence",
        ),
        # Today's derivation: the address's folder in crawl and sitemap modes.
        "include_path_prefixes": _Value(
            folder_prefix(_path(urls[0])) if mode in ("crawl", "sitemap") else [],
            "default",
            "default_no_evidence",
        ),
        "exclude_path_prefixes": _Value([], "default", "default_no_evidence"),
        "max_pages": _Value(pages, "default", "default_no_evidence"),
        "max_depth": _Value(DEFAULT_MAX_DEPTH, "default", "default_no_evidence"),
    }
    if mode != "url_list" and pages > room:
        values["max_pages"] = _Value(
            max(1, room),
            "computed",
            "pages_budget",
            {"other": other_pages, "limit": MAX_RUN_PAGES, "pages": max(1, room)},
        )
    return values


def _failing(candidate: dict, other_pages: int, settings) -> tuple[list[str], str]:
    """Managed paths that make the candidate invalid, with a safe reason."""
    try:
        WebsiteConfig.model_validate(candidate)
    except ValidationError as exc:
        paths = [
            path
            for path in MANAGED_PATHS
            if any(error["loc"][:1] == (path,) for error in exc.errors())
        ]
        return paths or list(MANAGED_PATHS), ""
    try:
        resolve_website_fetch_policy(candidate, settings)
    except WebsiteScopeTooLarge as exc:
        return ["max_pages", "requests_per_second"], str(exc)
    if candidate["max_pages"] + other_pages > MAX_RUN_PAGES:
        return ["max_pages"], (
            f"The other Website sources leave room for {MAX_RUN_PAGES - other_pages:,} "
            f"pages, fewer than this source needs ({candidate['max_pages']:,})."
        )
    return [], ""


# Fields tried first when an error names no field: the least important first.
FALLBACK_ORDER = (
    "exclude_path_prefixes",
    "max_depth",
    "max_pages",
    "include_path_prefixes",
    "selection",
    "requests_per_second",
    "allowed_origins",
)


def _invalid_paths(
    values: dict[str, _Value], defaults: dict[str, _Value], other_pages: int, settings
) -> tuple[list[str], str]:
    """The fields to fall back. An error for the whole config (a model-level
    validator) is traced to the one computed field whose default fixes it."""
    failing, reason = _failing(_candidate(values), other_pages, settings)
    if failing != list(MANAGED_PATHS):
        return failing, reason
    for path in FALLBACK_ORDER:
        if values[path] is defaults[path]:
            continue
        trial = {**values, path: defaults[path]}
        if not _failing(_candidate(trial), other_pages, settings)[0]:
            return [path], reason
    return failing, reason


def _guard(
    values: dict[str, _Value],
    defaults: dict[str, _Value],
    *,
    permitted: set[str],
    start_paths: list[str],
    delay: float | None,
    page_limit: int,
) -> None:
    """Safety guards; a failing field falls back to its default on its own."""
    if not {url_origin(str(item)) for item in values["allowed_origins"].value} <= (
        permitted
    ):
        values["allowed_origins"] = defaults["allowed_origins"]
    if any(
        path.startswith(prefix)
        for prefix in values["exclude_path_prefixes"].value
        for path in start_paths
    ):
        values["exclude_path_prefixes"] = defaults["exclude_path_prefixes"]
    if values["requests_per_second"].value > _rps_ceiling(delay):
        values["requests_per_second"] = defaults["requests_per_second"]
    if values["max_pages"].value > page_limit:
        values["max_pages"] = defaults["max_pages"]


def recommend(signals: ProbeSignals, inputs: dict, settings) -> Recommendation:
    """Recommended `WebsiteConfig` for `inputs`, explained field by field."""
    selection = inputs["selection"]
    mode = selection["mode"]
    other_pages = int(inputs.get("other_sources_max_pages", 0))
    ceiling = int(
        inputs.get("page_ceiling", settings.setting_recommendations_page_ceiling)
    )
    room = MAX_RUN_PAGES - other_pages
    if room < 1:
        raise RecommendationFailed(
            f"The other Website sources already use the whole {MAX_RUN_PAGES:,}-page "
            "pipeline limit. Lower their maximum pages first."
        )
    defaults = _defaults(selection, other_pages, ceiling)
    # Falling back never asks for more than robots.txt allows.
    defaults["requests_per_second"] = _Value(
        _rps_ceiling(_crawl_delay(signals)), "default", "default_no_evidence"
    )
    values = dict(defaults)
    origins, final_url = _origins(signals, selection)
    values["allowed_origins"] = origins
    values["requests_per_second"] = _speed(signals)
    start_paths = (
        list(dict.fromkeys([_path(signals.entered_url), _path(final_url)]))
        if mode == "crawl"
        else []
    )

    if mode == "crawl":
        values["include_path_prefixes"] = _include(signals, final_url)
        values["selection"] = _mode(signals, selection)
    elif mode == "sitemap":
        values["selection"] = _Value(selection, "computed", "mode_sitemap_input")
        values["include_path_prefixes"] = _Value([], "computed", "include_none")
    else:
        code = "mode_url_list" if mode == "url_list" else "mode_single_url"
        values["selection"] = _Value(selection, "computed", code)
        values["include_path_prefixes"] = _Value([], "computed", "filters_not_used")
        values["exclude_path_prefixes"] = _Value([], "computed", "filters_not_used")
    chosen = values["selection"].value["mode"]

    excluded: list[dict] = []
    if chosen in ("crawl", "sitemap"):
        values["exclude_path_prefixes"], excluded = _exclusions(
            signals, values["include_path_prefixes"].value, start_paths
        )
    values["max_pages"] = _pages(
        signals,
        values["selection"].value,
        excluded,
        values["allowed_origins"].value,
        values["requests_per_second"].value,
        ceiling,
        room,
        settings,
    )
    values["max_depth"] = _depth(signals, chosen)

    permitted = set(origins.value) if mode == "url_list" else {signals.entered_origin}
    if mode != "url_list" and same_site(signals.entered_origin, url_origin(final_url)):
        permitted.add(url_origin(final_url))
    page_limit = len(selection["urls"]) if mode == "url_list" else ceiling
    _guard(
        values,
        defaults,
        permitted=permitted,
        start_paths=start_paths,
        delay=_crawl_delay(signals),
        page_limit=max(page_limit, 1),
    )

    warnings = list(signals.warnings)
    linked = signals.links.get("linked_total", 0)
    if (
        mode == "crawl"
        and "client_rendered" in warnings
        and chosen == "crawl"
        and not linked
    ):
        # Nothing to crawl: the page needs JavaScript and links nowhere.
        raise RecommendationFailed(
            "The start page needs JavaScript and links to no other pages, so a "
            "Website source has nothing to read here.",
            warnings,
        )

    # Validation chain: fall back failing fields, then validate again.
    reason = ""
    for _ in range(len(MANAGED_PATHS) + 1):
        failing, reason = _invalid_paths(values, defaults, other_pages, settings)
        if not failing:
            break
        replaced = [path for path in failing if values[path] is not defaults[path]]
        if not replaced:
            raise RecommendationFailed(
                reason
                or "No recommended settings passed validation for this address. "
                "Keep the current settings or change the address.",
                warnings,
            )
        for path in replaced:
            values[path] = defaults[path]
    else:  # pragma: no cover - every pass replaces at least one field
        raise RecommendationFailed(
            reason or "No recommended settings passed validation."
        )

    candidate = _candidate(values)
    recommended = WebsiteConfig.model_validate(candidate).model_dump(mode="json")
    fields = []
    for path in MANAGED_PATHS:
        item = values[path]
        value = recommended[path]
        if path == "allowed_origins":
            value = [url_origin(str(origin)) for origin in value]
        fields.append(
            {
                "path": path,
                "label": LABELS[path],
                "value": value,
                "basis": item.basis,
                "risk": RISK[path],
                "rationale_code": item.code,
                "rationale": item.rationale(),
                "check": item.check,
            }
        )
    return Recommendation(
        recommended=recommended, fields=fields, warnings=warning_items(warnings)
    )

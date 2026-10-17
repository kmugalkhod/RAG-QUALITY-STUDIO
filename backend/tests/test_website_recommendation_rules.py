"""Recommended Website settings, spec 0011 Slice 2: probe steps and rules.

The rule table runs `recommend()` on recorded `ProbeSignals` fixtures
(`fixtures/website_probe/*.json`, recorded from the controlled sites in
`website_probe_sites.py`), changed only where a case sets a boundary value.
"""

import gzip
import json
from copy import deepcopy

import pytest

from app.connectors.base import ConnectorFailure
from app.connectors.website import resolve_website_fetch_policy
from app.connectors.website_probe import (
    MAX_REQUESTS,
    MAX_SIGNALS_BYTES,
    ProbeSignals,
)
from app.core.config import settings
from app.schemas.ingestion import WebsiteConfig
from app.services import website_recommendation
from app.services.website_recommendation import (
    RecommendationFailed,
    _Value,
    recommend,
)
from website_probe_sites import (
    GZIP,
    HTML,
    MISSING,
    SITES,
    XML,
    FakeClock,
    page,
    probe_site,
    recorded,
    robots,
    run,
    selection_of,
    sitemapindex,
    urlset,
)


def signals_of(name: str, **overrides) -> ProbeSignals:
    """A recorded fixture with dotted-path overrides, e.g. `sitemap__in_scope`."""
    value = deepcopy(recorded(name))
    for key, item in overrides.items():
        target = value
        *parents, last = key.split("__")
        for parent in parents:
            target = target[parent]
        target[last] = item
    return ProbeSignals.from_json(value)


def inputs_for(name: str, other: int = 0, ceiling: int = 200) -> dict:
    return {
        "selection": selection_of(name),
        "other_sources_max_pages": other,
        "page_ceiling": ceiling,
    }


def fields(result) -> dict:
    return {item["path"]: item for item in result.fields}


@pytest.mark.parametrize("name", sorted(SITES))
def test_fixtures_are_recordings_of_the_controlled_sites(name):
    assert probe_site(name).as_json() == recorded(name)


@pytest.mark.parametrize("name", sorted(SITES))
def test_every_fixture_gives_a_config_the_validators_accept(name):
    result = recommend(signals_of(name), inputs_for(name), settings)
    config = WebsiteConfig.model_validate(result.recommended)
    resolve_website_fetch_policy(config, settings)
    assert result.recommended["max_pages"] <= max(
        200, len(result.recommended["selection"].get("urls", []))
    )
    stored = json.dumps(recorded(name))
    # Measurements only: no page text reaches the signals (D7).
    assert "Plain server-rendered documentation text" not in stored
    assert "<main>" not in stored


RULES = [
    # Discovery mode: a sitemap needs >= 5 in-scope URLs and >= 80% coverage.
    pytest.param(
        "docs_sitemap", {"sitemap__in_scope": 5}, {},
        {"selection": ({"mode": "sitemap", "sitemap_url": "https://docs.example/sitemap_index.xml"}, "mode_sitemap")},
        id="mode-sitemap-5-urls",
    ),
    pytest.param(
        "docs_sitemap", {"sitemap__in_scope": 4}, {},
        {"selection": ({"mode": "crawl", "start_url": "https://docs.example/guide/"}, "mode_crawl_sitemap_partial")},
        id="mode-crawl-4-urls",
    ),
    pytest.param(
        "docs_sitemap", {"links__linked_total": 100, "sitemap__linked_in_sitemap": 80}, {},
        {"selection": ({"mode": "sitemap", "sitemap_url": "https://docs.example/sitemap_index.xml"}, "mode_sitemap")},
        id="mode-sitemap-80-percent",
    ),
    pytest.param(
        "docs_sitemap", {"links__linked_total": 100, "sitemap__linked_in_sitemap": 79}, {},
        {"selection": ({"mode": "crawl", "start_url": "https://docs.example/guide/"}, "mode_crawl_sitemap_partial")},
        id="mode-crawl-79-percent",
    ),
    pytest.param(
        "docs_crawl", {}, {},
        {"selection": ({"mode": "crawl", "start_url": "https://docs.example/manual"}, "mode_crawl_no_sitemap")},
        id="mode-crawl-no-sitemap",
    ),
    pytest.param(
        "sitemap_input", {}, {},
        {"selection": ({"mode": "sitemap", "sitemap_url": "https://maps.example/sitemap.xml"}, "mode_sitemap_input")},
        id="mode-sitemap-input-kept",
    ),
    pytest.param(
        "url_list", {}, {}, {"selection": (selection_of("url_list"), "mode_url_list")},
        id="mode-url-list-kept",
    ),
    # Crawl depth: L2 = 0 gives 1, L2 <= L1 gives 2, otherwise 3 (L1 = 6 here).
    pytest.param("docs_crawl", {"links__l2": 0}, {}, {"max_depth": (1, "depth_toc")}, id="depth-l2-0"),
    pytest.param("docs_crawl", {"links__l2": 6}, {}, {"max_depth": (2, "depth_two")}, id="depth-l2-equals-l1"),
    pytest.param("docs_crawl", {"links__l2": 7}, {}, {"max_depth": (3, "depth_default")}, id="depth-l2-above-l1"),
    pytest.param(
        "docs_crawl", {"links__sampled": 0}, {}, {"max_depth": (3, "default_no_evidence")},
        id="depth-no-sample",
    ),
    pytest.param("docs_sitemap", {}, {}, {"max_depth": (3, "depth_not_used")}, id="depth-not-used-in-sitemap"),
    # Crawl speed: min(2, 1/Crawl-delay), floored at 0.1.
    pytest.param(
        "crawl_delay", {"robots__crawl_delay": 10}, {}, {"requests_per_second": (0.1, "rps_crawl_delay")},
        id="speed-crawl-delay-10",
    ),
    pytest.param(
        "crawl_delay", {"robots__crawl_delay": 11}, {}, {"requests_per_second": (0.1, "rps_crawl_delay")},
        id="speed-crawl-delay-11-floor",
    ),
    pytest.param(
        "crawl_delay", {"robots__crawl_delay": 3}, {}, {"requests_per_second": (0.33, "rps_crawl_delay")},
        id="speed-rounds-down",
    ),
    pytest.param(
        "crawl_delay", {"robots__crawl_delay": None}, {}, {"requests_per_second": (2, "rps_default")},
        id="speed-default",
    ),
    pytest.param(
        "docs_crawl", {"timing__median_response_ms": 2000}, {}, {"requests_per_second": (2, "rps_default")},
        id="speed-2000-ms",
    ),
    pytest.param(
        "docs_crawl", {"timing__median_response_ms": 2001}, {}, {"requests_per_second": (1, "rps_slow_site")},
        id="speed-2001-ms",
    ),
    pytest.param(
        "docs_crawl", {"timing__throttled": 1}, {}, {"requests_per_second": (1, "rps_slow_site")},
        id="speed-throttled",
    ),
    pytest.param(
        "url_list", {}, {}, {"requests_per_second": (0.25, "rps_crawl_delay")},
        id="speed-url-list-slowest-origin",
    ),
    # Maximum pages.
    pytest.param("docs_crawl", {}, {}, {"max_pages": (50, "pages_crawl_open")}, id="pages-open-frontier"),
    pytest.param(
        # OpenBSD FAQ (label S2): 41 pages seen (one section excluded), more linked;
        # 1.25 x 41 rounds to 60.
        "docs_crawl", {"links__linked_total": 42}, {}, {"max_pages": (60, "pages_crawl_open")},
        id="pages-open-frontier-headroom",
    ),
    pytest.param(
        "docs_crawl", {"links__linked_total": 170}, {}, {"max_pages": (200, "pages_crawl_open")},
        id="pages-open-frontier-ceiling",
    ),
    pytest.param(
        # Hacks (label S5): a partial sitemap lists far more posts than links reach.
        "docs_crawl", {"sitemap__found": True, "sitemap__in_scope": 80}, {},
        {"max_pages": (100, "pages_crawl_open_sitemap")},
        id="pages-open-frontier-sitemap-count",
    ),
    pytest.param(
        "docs_crawl", {"sitemap__found": True, "sitemap__in_scope": 3, "links__linked_total": 60}, {},
        {"max_pages": (80, "pages_crawl_open")},
        id="pages-open-frontier-sitemap-smaller",
    ),
    pytest.param(
        "docs_crawl", {"links__frontier": "closed"}, {}, {"max_pages": (10, "pages_crawl_closed")},
        id="pages-closed-frontier",
    ),
    pytest.param("docs_sitemap", {}, {}, {"max_pages": (10, "pages_sitemap")}, id="pages-sitemap"),
    pytest.param(
        "docs_sitemap", {}, {"other": 2490}, {"max_pages": (10, "pages_sitemap")},
        id="pages-budget-exactly-fits",
    ),
    pytest.param(
        "docs_sitemap", {}, {"other": 2491}, {"max_pages": (9, "pages_budget")},
        id="pages-budget-one-short",
    ),
    pytest.param(
        "docs_crawl", {"links__frontier": "closed", "links__linked_total": 300}, {},
        {"max_pages": (200, "pages_crawl_closed")},
        id="pages-ceiling",
    ),
    pytest.param(
        "crawl_delay",
        {"robots__crawl_delay": 11, "links__frontier": "open", "links__linked_total": 400},
        {"ceiling": 1000},
        {"max_pages": (326, "pages_deadline")},
        id="pages-deadline-fit",
    ),
    pytest.param("url_list", {}, {}, {"max_pages": (4, "pages_url_list")}, id="pages-url-list"),
    pytest.param("single_url", {}, {}, {"max_pages": (50, "pages_not_used")}, id="pages-single-url"),
    # Exclusions.
    pytest.param(
        "docs_crawl", {}, {}, {"exclude_path_prefixes": (["/manual/print/"], "exclude_utility_pattern")},
        id="exclude-utility",
    ),
    pytest.param(
        "docs_crawl", {"start_section": "print"}, {}, {"exclude_path_prefixes": ([], "exclude_none")},
        id="exclude-never-the-start-section",
    ),
    pytest.param(
        "multilingual", {}, {},
        {"exclude_path_prefixes": (["/es", "/fr", "/pt-BR", "/zh-CN"], "exclude_language")},
        id="exclude-languages-mixed-case",
    ),
    pytest.param(
        "multilingual", {"start_page__html_lang": "es"}, {},
        {"exclude_path_prefixes": (["/fr", "/pt-BR", "/zh-CN"], "exclude_language")},
        id="exclude-not-the-page-language",
    ),
    pytest.param(
        "sitemap_input", {}, {}, {"exclude_path_prefixes": (["/search/"], "exclude_utility_pattern")},
        id="exclude-utility-in-sitemap",
    ),
    pytest.param(
        "url_list", {}, {}, {"exclude_path_prefixes": ([], "filters_not_used")},
        id="exclude-not-used-in-url-list",
    ),
    # Origins and include prefixes.
    pytest.param(
        "multilingual", {}, {},
        {"allowed_origins": (["https://www.lang.example", "https://lang.example"], "origins_redirect")},
        id="origins-same-site-redirect",
    ),
    pytest.param(
        "url_list", {}, {}, {"allowed_origins": (["https://a.example", "https://b.example"], "origins_url_list")},
        id="origins-url-list",
    ),
    pytest.param(
        "docs_crawl", {}, {}, {"include_path_prefixes": (["/manual/"], "include_redirect_folder")},
        id="include-redirect-folder",
    ),
    pytest.param(
        "sitemap_input", {}, {}, {"include_path_prefixes": ([], "include_none")},
        id="include-none-for-sitemap-input",
    ),
]  # fmt: skip


@pytest.mark.parametrize(("name", "overrides", "options", "expected"), RULES)
def test_rule_table(name, overrides, options, expected):
    result = recommend(
        signals_of(name, **overrides), inputs_for(name, **options), settings
    )
    by_path = fields(result)
    for path, (value, code) in expected.items():
        assert by_path[path]["value"] == value, path
        assert by_path[path]["rationale_code"] == code, path
        assert result.recommended[path] == (
            value if path != "allowed_origins" else result.recommended[path]
        )
    WebsiteConfig.model_validate(result.recommended)
    resolve_website_fetch_policy(result.recommended, settings)


def test_reasons_carry_the_measured_numbers_and_flags():
    speed = fields(
        recommend(
            signals_of("crawl_delay", robots__crawl_delay=10),
            inputs_for("crawl_delay"),
            settings,
        )
    )["requests_per_second"]
    assert "10 seconds" in speed["rationale"] and "slowest" not in speed["rationale"]
    speed = fields(
        recommend(
            signals_of("crawl_delay", robots__crawl_delay=11),
            inputs_for("crawl_delay"),
            settings,
        )
    )["requests_per_second"]
    assert "waits 11 seconds" in speed["rationale"]

    open_pages = fields(
        recommend(signals_of("docs_crawl"), inputs_for("docs_crawl"), settings)
    )["max_pages"]
    assert open_pages["check"] is True
    capped = fields(
        recommend(
            signals_of("docs_crawl", links__frontier="closed", links__linked_total=300),
            inputs_for("docs_crawl"),
            settings,
        )
    )["max_pages"]
    assert (
        capped["check"] is False
        and "200-page recommendation ceiling" in capped["rationale"]
    )
    lower = fields(
        recommend(
            signals_of("docs_sitemap", sitemap__lower_bound=True),
            inputs_for("docs_sitemap"),
            settings,
        )
    )["max_pages"]
    assert (
        lower["check"] is True and "nested sitemaps were not read" in lower["rationale"]
    )
    sitemap = fields(
        recommend(signals_of("docs_sitemap"), inputs_for("docs_sitemap"), settings)
    )
    assert "9 pages in scope" in sitemap["selection"]["rationale"]
    assert "5 of the 5 linked pages" in sitemap["selection"]["rationale"]


def test_deadline_fit_uses_the_rate_the_crawl_really_runs():
    result = recommend(
        signals_of(
            "crawl_delay",
            robots__crawl_delay=11,
            links__frontier="open",
            links__linked_total=400,
        ),
        inputs_for("crawl_delay", ceiling=1000),
        settings,
    )
    pages = result.recommended["max_pages"]
    # 326 pages and robots.txt at one request per 11 s fit the 3,600 s limit.
    assert (pages + 1) * 11 <= settings.website_deadline_max_seconds
    assert (pages + 2) * 11 > settings.website_deadline_max_seconds


def test_page_numbered_sections_and_single_urls_are_judged_by_count():
    numbered = {
        "segment": "page",
        "count": 3,
        "links": 3,
        "sitemap": 0,
        "exact": False,
        "numbered": True,
        "samples": [],
    }
    base = recorded("docs_crawl")
    for section, expected in (
        (numbered, ["/manual/print/", "/manual/page/"]),
        ({**numbered, "numbered": False}, ["/manual/print/"]),
        ({**numbered, "segment": "search", "count": 1}, ["/manual/print/"]),
    ):
        result = recommend(
            signals_of("docs_crawl", sections=[*base["sections"], section]),
            inputs_for("docs_crawl"),
            settings,
        )
        assert result.recommended["exclude_path_prefixes"] == expected
    # Excluded sections are not counted: 1 + 8 linked - 2 print pages.
    closed = fields(
        recommend(
            signals_of("docs_crawl", links__frontier="closed"),
            inputs_for("docs_crawl"),
            settings,
        )
    )["max_pages"]
    assert "7 pages in scope" in closed["rationale"]


def test_a_page_at_the_top_level_widens_no_further_than_today_and_asks_for_a_check():
    # SQLite's /lang.html (label S3): the folder rule cannot express /lang, so
    # the scope is the whole site, exactly today's derivation, flagged.
    signals = ProbeSignals(
        probe_mode="crawl",
        entered_url="https://www.sqlite.example/lang.html",
        entered_origin="https://www.sqlite.example",
        robots={"crawl_delay": None},
        start_page={
            "final_url": "https://www.sqlite.example/lang.html",
            "links_same_origin": 40,
            "links_below_path": 0,
        },
        links={
            "l1": 40,
            "l2": 0,
            "linked_total": 40,
            "sampled": 9,
            "frontier": "closed",
        },
    )
    result = recommend(
        signals,
        {
            "selection": {
                "mode": "crawl",
                "start_url": "https://www.sqlite.example/lang.html",
            },
            "other_sources_max_pages": 0,
            "page_ceiling": 200,
        },
        settings,
    )
    include = fields(result)["include_path_prefixes"]
    assert include["value"] == [] and include["rationale_code"] == "include_none"
    assert include["check"] is True
    assert result.recommended["exclude_path_prefixes"] == []


def test_a_failing_field_falls_back_on_its_own(monkeypatch):
    monkeypatch.setattr(
        website_recommendation,
        "_depth",
        lambda signals, mode: _Value(
            11, "computed", "depth_default", {"l1": 1, "l2": 2, "depth": 11}
        ),
    )
    by_path = fields(
        recommend(signals_of("docs_crawl"), inputs_for("docs_crawl"), settings)
    )
    assert by_path["max_depth"]["value"] == 3
    assert by_path["max_depth"]["rationale_code"] == "default_no_evidence"
    assert (
        by_path["include_path_prefixes"]["rationale_code"] == "include_redirect_folder"
    )
    assert by_path["max_pages"]["rationale_code"] == "pages_crawl_open"

    # An error the validator reports for the whole config is traced to the
    # one field whose default fixes it.
    monkeypatch.setattr(
        website_recommendation,
        "_exclusions",
        lambda signals, include, start: (
            _Value(
                ["no-slash"],
                "computed",
                "exclude_utility_pattern",
                {"utility": "x", "languages": ""},
            ),
            [],
        ),
    )
    by_path = fields(
        recommend(signals_of("docs_crawl"), inputs_for("docs_crawl"), settings)
    )
    assert by_path["exclude_path_prefixes"]["value"] == []
    assert by_path["exclude_path_prefixes"]["rationale_code"] == "default_no_evidence"
    assert (
        by_path["include_path_prefixes"]["rationale_code"] == "include_redirect_folder"
    )


def test_no_room_in_the_pipeline_budget_fails_with_a_reason():
    with pytest.raises(RecommendationFailed) as caught:
        recommend(
            signals_of("docs_crawl"), inputs_for("docs_crawl", other=2500), settings
        )
    assert "2,500-page" in str(caught.value)
    url_list = recommend(
        signals_of("url_list"), inputs_for("url_list", other=2496), settings
    )
    assert url_list.recommended["max_pages"] == 4
    with pytest.raises(RecommendationFailed):
        recommend(signals_of("url_list"), inputs_for("url_list", other=2497), settings)


def test_warnings():
    single = recommend(signals_of("single_url"), inputs_for("single_url"), settings)
    assert [item["code"] for item in single.warnings] == ["client_rendered"]
    assert single.recommended["selection"]["mode"] == "single_url"
    listed = recommend(signals_of("url_list"), inputs_for("url_list"), settings)
    assert [item["code"] for item in listed.warnings] == ["robots_blocks_urls"]
    # A JavaScript shell that links nowhere has nothing to crawl.
    shell = signals_of(
        "crawl_delay",
        warnings=["client_rendered"],
        links__l1=0,
        links__linked_total=0,
    )
    with pytest.raises(RecommendationFailed) as caught:
        recommend(shell, inputs_for("crawl_delay"), settings)
    assert caught.value.warnings == ["client_rendered"]


# Probe steps against controlled sites ---------------------------------------


def crawl_site(responses, start="https://site.example/docs/"):
    base = {
        "https://site.example/robots.txt": robots("User-agent: *\nAllow: /\n"),
        start: page("/docs/a", name="start"),
        "https://site.example/docs/a": page(name="a"),
    }
    base.update(responses)
    return run({"mode": "crawl", "start_url": start}, base)


def test_sitemap_with_a_document_type_is_refused():
    signals, _ = crawl_site(
        {
            "https://site.example/sitemap.xml": (
                200,
                XML,
                b"<?xml version='1.0'?><!DOCTYPE urlset [<!ENTITY x 'y'>]><urlset/>",
            ),
            "https://site.example/sitemap_index.xml": MISSING,
        }
    )
    assert signals.sitemap["found"] is False
    assert {"url": "https://site.example/sitemap.xml", "code": "unsafe_sitemap"} in (
        signals.sitemap["errors"]
    )
    with pytest.raises(ConnectorFailure) as caught:
        run(
            {"mode": "sitemap", "sitemap_url": "https://site.example/sitemap.xml"},
            {
                "https://site.example/robots.txt": MISSING,
                "https://site.example/sitemap.xml": (
                    200,
                    XML,
                    b"<!DOCTYPE urlset><urlset/>",
                ),
            },
        )
    assert caught.value.issue.code == "sitemap_unreadable"


def test_gzip_sitemaps_are_decompressed_within_the_byte_bound():
    bomb = gzip.compress(b"<urlset>" + b" " * (6 * 1024 * 1024) + b"</urlset>")
    assert len(bomb) < 64 * 1024
    signals, _ = crawl_site(
        {
            "https://site.example/robots.txt": robots(
                "User-agent: *\nAllow: /\nSitemap: https://site.example/big.xml.gz\n"
            ),
            "https://site.example/big.xml.gz": (200, GZIP, bomb),
            "https://site.example/sitemap.xml": MISSING,
            "https://site.example/sitemap_index.xml": MISSING,
        }
    )
    assert {"url": "https://site.example/big.xml.gz", "code": "sitemap_too_large"} in (
        signals.sitemap["errors"]
    )
    assert signals.sitemap["found"] is False


def test_nested_sitemaps_are_followed_one_level_and_at_most_three():
    origin = "https://site.example"
    nested = [f"{origin}/part-{n}.xml" for n in range(5)]
    responses = {
        f"{origin}/sitemap.xml": (
            200,
            XML,
            sitemapindex(f"{origin}/inner-index.xml", *nested),
        ),
        f"{origin}/inner-index.xml": (200, XML, sitemapindex(f"{origin}/deep.xml")),
    }
    for n, url in enumerate(nested):
        responses[url] = (200, XML, urlset(f"{origin}/docs/p{n}"))
    signals, transport = crawl_site(responses)
    sitemap = signals.sitemap
    assert f"{origin}/deep.xml" not in transport.calls
    assert {"url": f"{origin}/inner-index.xml", "code": "nested_index"} in sitemap[
        "errors"
    ]
    assert sitemap["nested_read"] == 3 and sitemap["nested_listed"] == 6
    assert sitemap["lower_bound"] is True
    assert sitemap["in_scope"] == 3
    assert f"{origin}/part-3.xml" not in transport.calls


def test_the_probe_never_makes_more_than_18_requests():
    origin = "https://site.example"
    hops = [f"{origin}/start{n}" for n in range(5)]
    responses = {
        f"{origin}/robots.txt": robots(
            f"User-agent: *\nAllow: /\nSitemap: {origin}/a.xml\nSitemap: {origin}/b.xml\n"
        ),
        f"{origin}/a.xml": (
            200,
            XML,
            sitemapindex(*[f"{origin}/n{n}.xml" for n in range(10)]),
        ),
    }
    for current, target in zip(hops, hops[1:] + [f"{origin}/docs/"]):
        responses[current] = (301, {**HTML, "location": target}, b"")
    links = [f"/docs/p{n}" for n in range(40)]
    responses[f"{origin}/docs/"] = page(*links, name="docs")
    for n in range(10):
        responses[f"{origin}/n{n}.xml"] = (200, XML, urlset(f"{origin}/docs/p{n}"))
    for n in range(40):
        # Every sampled page redirects once, so samples cost two requests.
        responses[f"{origin}/docs/p{n}"] = (
            301,
            {**HTML, "location": f"/docs/q{n}"},
            b"",
        )
        responses[f"{origin}/docs/q{n}"] = page(name=f"q{n}")
    signals, transport = run({"mode": "crawl", "start_url": hops[0]}, responses)
    assert len(transport.calls) == MAX_REQUESTS
    assert len(signals.requests) <= MAX_REQUESTS
    assert signals.links["l1"] == 40
    assert len(signals.sample_pages) <= 9


def test_crawl_delay_paces_every_request_and_bounds_the_samples():
    origin = "https://slow.example"
    clock = FakeClock()
    responses = {
        f"{origin}/robots.txt": robots("Crawl-delay: 10\nUser-agent: *\nAllow: /\n"),
        f"{origin}/docs/": page(*[f"/docs/p{n}" for n in range(20)], name="docs"),
        f"{origin}/sitemap.xml": MISSING,
        f"{origin}/sitemap_index.xml": MISSING,
    }
    for n in range(20):
        responses[f"{origin}/docs/p{n}"] = page(name=f"p{n}")
    start = clock()
    signals, transport = run(
        {"mode": "crawl", "start_url": f"{origin}/docs/"}, responses, clock
    )
    assert all(
        later - earlier >= 10 - 1e-6
        for earlier, later in zip(transport.times, transport.times[1:])
    )
    assert transport.times[-1] - start < 90
    # robots.txt, the start page and two sitemap reads leave time for 5 pages.
    assert 1 <= len(signals.sample_pages) <= 5


def test_signals_stay_within_64_kib():
    long = "https://site.example/" + "x" * 480
    signals = ProbeSignals(
        probe_mode="crawl",
        entered_url=long,
        entered_origin="https://site.example",
        requests=[
            {
                "purpose": "sample_pages",
                "url": long,
                "status": 200,
                "outcome": "response",
                "elapsed_ms": 1,
            }
        ]
        * MAX_REQUESTS,
        start_page={"hreflang": [{"lang": "x" * 35, "url": "/" + "y" * 199}] * 40},
        sections=[
            {
                "segment": f"s{n}" + "z" * 190,
                "count": 2,
                "links": 1,
                "sitemap": 1,
                "exact": False,
                "numbered": False,
                "samples": ["/" + "p" * 199] * 3,
            }
            for n in range(300)
        ],
        sample_pages=[
            {"url": long, "section": "s", "outcome": "included", "new_links": 1}
        ]
        * 9,
        links={"l1": 40, "l2": 3, "linked_total": 43, "frontier": "open"},
        sitemap={"found": True, "in_scope": 1234},
    )
    stored = signals.as_json()
    assert len(json.dumps(stored, separators=(",", ":")).encode()) <= MAX_SIGNALS_BYTES
    # Counts the rules read are never dropped.
    assert stored["links"] == signals.links and stored["sitemap"] == signals.sitemap


@pytest.mark.parametrize(
    ("response", "code"),
    [
        ((200, {"content-type": "application/pdf"}, b"%PDF-1.7"), "non_html_start"),
        ((404, HTML, b"missing"), "start_not_found"),
    ],
)
def test_start_pages_that_cannot_be_crawled_fail_with_their_warning(response, code):
    with pytest.raises(ConnectorFailure) as caught:
        crawl_site({"https://site.example/docs/": response})
    assert caught.value.issue.code == code
    assert code in website_recommendation.WARNINGS


def test_robots_rules_after_a_blank_line_block_the_start_url():
    # docs.python.org (labels S7 and S8): /3.9/ is disallowed after a blank line.
    rules = "User-agent: *\nDisallow: /dev\n\n# EOL\nDisallow: /3.9/\n"
    with pytest.raises(ConnectorFailure) as caught:
        run(
            {"mode": "crawl", "start_url": "https://site.example/3.9/tutorial/"},
            {"https://site.example/robots.txt": robots(rules)},
        )
    assert caught.value.issue.code == "robots_blocks_start"


def test_links_that_all_leave_the_site_are_reported():
    signals, _ = crawl_site(
        {
            "https://site.example/docs/": page("https://elsewhere.example/a", name="x"),
            "https://site.example/sitemap.xml": MISSING,
            "https://site.example/sitemap_index.xml": MISSING,
        }
    )
    assert "all_links_off_origin" in signals.warnings


def test_links_to_the_start_pages_canonical_address_are_not_new_pages():
    # docs.python.org (labels W1a, W1b): /3/tutorial/ declares rel=canonical
    # .../index.html and every chapter links back to index.html.
    start = "https://site.example/tutorial/"
    canonical = "<link rel='canonical' href='https://site.example/tutorial/index.html'>"
    signals, _ = crawl_site(
        {
            start: page("a.html", "b.html", head=canonical, name="start"),
            f"{start}a.html": page("index.html", "b.html", name="a"),
            f"{start}b.html": page("index.html", "a.html", name="b"),
            "https://site.example/sitemap.xml": MISSING,
            "https://site.example/sitemap_index.xml": MISSING,
        },
        start=start,
    )
    assert signals.start_page["canonical_url"] == f"{start}index.html"
    assert signals.links["l2"] == 0
    assert signals.links["frontier"] == "closed"

"""robots.txt reading shared by Website previews, runs and the probe (spec 0011).

`RobotRules` reads robots.txt at least as strictly as `urllib.robotparser`:
rules after a blank line inside a group (docs.python.org, label S8) and a
Crawl-delay placed before the first User-agent line (Hacks, label S5) apply.
"""

import time
from urllib.robotparser import RobotFileParser

import pytest

from app.connectors.base import ConnectorFailure
from app.connectors.safe_http import HttpResponse, SafeHttpClient
from app.connectors.website import (
    RobotRules,
    WebsiteConnector,
    parse_robots,
    resolve_website_fetch_policy,
)
from app.core.config import settings

UA = settings.website_user_agent
HTML = {"content-type": "text/html"}
PUBLIC_IP = "93.184.216.34"
PYTHON_DOCS = (
    "User-agent: *\nDisallow: /dev\n\n# End-of-life versions\nDisallow: /3.9/\n"
)


def python_parser(text: str) -> RobotFileParser:
    parser = RobotFileParser("https://docs.example/robots.txt")
    parser.parse(text.splitlines())
    return parser


def rules(text: str) -> RobotRules:
    return RobotRules("https://docs.example/robots.txt", text)


def test_rules_after_a_blank_line_inside_a_group_apply():
    # The gap: Python's parser ends the group at the blank line.
    assert python_parser(PYTHON_DOCS).can_fetch(
        UA, "https://docs.example/3.9/tutorial/"
    )
    read = rules(PYTHON_DOCS)
    assert not read.can_fetch(UA, "https://docs.example/3.9/tutorial/")
    assert not read.can_fetch(UA, "https://docs.example/dev/tutorial/")
    assert read.can_fetch(UA, "https://docs.example/3/tutorial/")


def test_a_crawl_delay_before_the_first_user_agent_applies():
    text = "Crawl-delay: 10\n\nUser-agent: *\nDisallow: /wp-admin/\n"
    assert python_parser(text).crawl_delay(UA) is None
    assert rules(text).crawl_delay(UA) == 10


def test_the_longest_delay_wins_and_a_group_never_shortens_it():
    assert rules("Crawl-delay: 5\nUser-agent: *\nCrawl-delay: 2\n").crawl_delay(UA) == 5
    assert rules("Crawl-delay: 5\nUser-agent: *\nCrawl-delay: 7\n").crawl_delay(UA) == 7
    # A later delay after a blank line cannot lower the group's own delay.
    assert (
        rules("User-agent: *\nCrawl-delay: 8\n\nCrawl-delay: 1\n").crawl_delay(UA) == 8
    )
    assert rules("User-agent: *\nDisallow: /x\n").crawl_delay(UA) is None


def test_both_readings_must_allow_a_url():
    # Grouped without blank lines, our agent would join the permissive group;
    # Python's parser drops it and applies `*`. The stricter answer wins.
    text = (
        "User-agent: RAGQualityStudio\n"
        "\n"
        "User-agent: Friendly\n"
        "Allow: /\n"
        "\n"
        "User-agent: *\n"
        "Disallow: /\n"
    )
    assert not python_parser(text).can_fetch(UA, "https://docs.example/a")
    assert not rules(text).can_fetch(UA, "https://docs.example/a")


def test_ordinary_files_read_as_before():
    text = (
        "User-agent: RAGQualityStudio\nDisallow: /private\n\n"
        "User-agent: *\nDisallow:\n"
        "Sitemap: https://docs.example/sitemap.xml\n"
    )
    read, python = rules(text), python_parser(text)
    for path in ("/", "/private/x", "/public"):
        url = f"https://docs.example{path}"
        assert read.can_fetch(UA, url) == python.can_fetch(UA, url)
    assert read.site_maps() == ["https://docs.example/sitemap.xml"]


def test_parse_robots_statuses():
    def response(status, body=b""):
        return HttpResponse(
            "https://docs.example/robots.txt", status, {}, body, 0, len(body)
        )

    assert parse_robots(response(404)) is None
    assert parse_robots(response(200, PYTHON_DOCS.encode())).can_fetch(
        UA, "https://docs.example/3/"
    )
    for status in (401, 403, 500):
        with pytest.raises(ConnectorFailure) as caught:
            parse_robots(response(status))
        assert caught.value.issue.code == "robots_unavailable"


class FakeClock:
    def __init__(self):
        self.now = time.monotonic()
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Transport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def request(self, url, address, timeout, headers, max_bytes):
        self.calls.append(url)
        return self.responses[url]


def crawl(robots: str, urls: list[str], pages: dict):
    clock = FakeClock()
    transport = Transport(
        {
            "https://docs.example/robots.txt": (
                200,
                {"content-type": "text/plain"},
                robots.encode(),
            ),
            **pages,
        }
    )
    connector = WebsiteConnector(
        client=SafeHttpClient(
            resolver=lambda host, port, type: [(2, type, 6, "", (PUBLIC_IP, port))],
            transport=transport,
        ),
        clock=clock,
        sleeper=clock.sleep,
        jitter=lambda: 0.0,
    )
    value = {
        "kind": "website",
        "selection": {"mode": "url_list", "urls": urls},
        "allowed_origins": ["https://docs.example"],
        "max_pages": len(urls),
        "requests_per_second": 2,
    }
    policy = resolve_website_fetch_policy(value, settings).model_copy(
        update={"fetch_concurrency": 1}
    )
    return connector.discover_all(value, policy), transport, clock


def body(text: str) -> bytes:
    return f"<main><p>{text} {'Readable text. ' * 20}</p></main>".encode()


def test_runs_skip_pages_disallowed_after_a_blank_line():
    urls = ["https://docs.example/3/a", "https://docs.example/3.9/a"]
    outcomes, transport, _ = crawl(
        PYTHON_DOCS, urls, {url: (200, HTML, body(url)) for url in urls}
    )
    by_url = {item.external_id: item for item in outcomes}
    assert by_url[urls[0]].status == "included"
    assert by_url[urls[1]].status == "excluded"
    assert "robots.txt" in by_url[urls[1]].reason
    assert urls[1] not in transport.calls


def test_runs_honour_a_crawl_delay_before_the_first_user_agent():
    urls = ["https://docs.example/a", "https://docs.example/b"]
    _, _, clock = crawl(
        "Crawl-delay: 3\n\nUser-agent: *\nAllow: /\n",
        urls,
        {url: (200, HTML, body(url)) for url in urls},
    )
    # Without the preamble delay the crawl would wait 0.5 s (2 per second).
    assert clock.sleeps.count(3) == 2

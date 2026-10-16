"""Controlled sites for the Website probe (spec 0011, Slice 2).

Each site is a transport double: a dict of URL → (status, headers, body). The
recorded `ProbeSignals` fixtures in `fixtures/website_probe/` are the probe's
output for these sites; `test_website_recommendation_rules.py` checks that
they still match. To re-record after an intended probe change:

    python -c "import sys; sys.path.insert(0, 'tests'); \\
        import website_probe_sites as s; s.record_all()"
"""

import gzip
import json
import time
from pathlib import Path

from app.connectors.base import ConnectorFailure, ConnectorIssue
from app.connectors.safe_http import SafeHttpClient
from app.connectors.website import WebsiteConnector
from app.connectors.website_probe import probe_website

PUBLIC_IP = "93.184.216.34"
UA = "RecommendationTest/1.0"
FIXTURES = Path(__file__).parent / "fixtures" / "website_probe"

HTML = {"content-type": "text/html"}
XML = {"content-type": "application/xml"}
TEXT = {"content-type": "text/plain"}
GZIP = {"content-type": "application/gzip"}
MISSING = (404, {}, b"")
# Static pages carry enough text not to look like JavaScript shells.
FILLER = "<p>" + "Plain server-rendered documentation text. " * 8 + "</p>"


def public_resolver(host, port, type):
    return [(2, type, 6, "", (PUBLIC_IP, port))]


class FakeClock:
    """Monotonic time that only moves when the code sleeps. It starts at the
    real clock, because SafeHttpClient checks deadlines with time.monotonic()."""

    def __init__(self):
        self.value = time.monotonic()
        self.sleeps = []

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


class Transport:
    def __init__(self, responses, clock=None):
        self.responses = responses
        self.clock = clock
        self.calls = []
        self.times = []

    def request(self, url, address, timeout, headers, max_bytes):
        self.calls.append(url)
        if self.clock is not None:
            self.times.append(self.clock())
        response = self.responses.get(url)
        if response is None:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="missing", message="No controlled response.", retryable=False
                )
            )
        return response


def page(
    *links: str, lang: str | None = None, head: str = "", body: str = FILLER, name=""
):
    """An HTML page; `name` keeps pages with the same links from being
    merged as duplicate content."""
    body = f"<h1>{name}</h1>{body}" if name else body
    anchors = "".join(f"<a href='{link}'>{link}</a>" for link in links)
    html_lang = f" lang='{lang}'" if lang else ""
    return (
        200,
        HTML,
        f"<html{html_lang}><head>{head}</head><body><main>{body}{anchors}</main>"
        f"</body></html>".encode(),
    )


def urlset(*urls: str) -> bytes:
    entries = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        f"{entries}</urlset>"
    ).encode()


def sitemapindex(*urls: str) -> bytes:
    entries = "".join(f"<sitemap><loc>{url}</loc></sitemap>" for url in urls)
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        f"{entries}</sitemapindex>"
    ).encode()


def robots(text: str):
    return (200, TEXT, text.encode())


def docs_sitemap():
    """Docs folder with a sitemap index (one nested file gzipped) that covers
    every linked page, plus two feed URLs listed only in the sitemap."""
    origin = "https://docs.example"
    guide = [f"{origin}/guide/{name}" for name in "abcde"]
    responses = {
        f"{origin}/robots.txt": robots(
            f"User-agent: *\nAllow: /\nSitemap: {origin}/sitemap_index.xml\n"
        ),
        f"{origin}/guide/": page(*guide, "/", "https://elsewhere.example/x", lang="en"),
        f"{origin}/sitemap_index.xml": (
            200,
            XML,
            sitemapindex(
                f"{origin}/sitemap-guide.xml", f"{origin}/sitemap-more.xml.gz"
            ),
        ),
        f"{origin}/sitemap-guide.xml": (
            200,
            XML,
            urlset(
                f"{origin}/guide/", *guide[:3], f"{origin}/blog/1", f"{origin}/blog/2"
            ),
        ),
        f"{origin}/sitemap-more.xml.gz": (
            200,
            GZIP,
            gzip.compress(
                urlset(
                    *guide[3:],
                    f"{origin}/guide/f",
                    f"{origin}/guide/feed/",
                    f"{origin}/guide/feed/atom",
                )
            ),
        ),
    }
    for url in guide:
        responses[url] = page(f"{origin}/guide/", *guide, name=url)
    return {"mode": "crawl", "start_url": f"{origin}/guide/"}, responses


def docs_crawl():
    """A folder entered without its slash, no sitemap, a print section and
    sampled pages that link one level deeper."""
    origin = "https://docs.example"
    links = [f"/manual/{name}" for name in ("a", "b", "c", "d", "print/a", "print/b")]
    responses = {
        f"{origin}/robots.txt": robots("User-agent: *\nDisallow: /private\n"),
        f"{origin}/manual": (301, {**HTML, "location": "/manual/"}, b""),
        f"{origin}/manual/": page(*links, "/private/x", lang="en"),
        f"{origin}/sitemap.xml": MISSING,
        f"{origin}/sitemap_index.xml": MISSING,
        f"{origin}/manual/a": page("/manual/a/one", "/manual/", name="a"),
        f"{origin}/manual/b": page("/manual/b/two", "/manual/", name="b"),
        f"{origin}/manual/c": page("/manual/", name="c"),
        f"{origin}/manual/d": page("/manual/", name="d"),
        f"{origin}/manual/print/a": page("/manual/", name="print a"),
        f"{origin}/manual/print/b": page("/manual/", name="print b"),
    }
    return {"mode": "crawl", "start_url": f"{origin}/manual"}, responses


LANGUAGES = ("es", "fr", "pt-BR", "zh-CN")


def multilingual():
    """www redirects to the bare domain; hreflang alternates with mixed-case
    codes; each language section is linked twice."""
    www, bare = "https://www.lang.example", "https://lang.example"
    alternates = (
        "".join(
            f"<link rel='alternate' hreflang='{code}' href='{www}/{code}'>"
            for code in (*LANGUAGES, "en-US")
        )
        + f"<link rel='alternate' hreflang='x-default' href='{www}/'>"
    )
    links = [path for code in LANGUAGES for path in (f"/{code}", f"/{code}/learn")]
    links += ["/en-US", "/learn", "/learn/basics", "/tools"]
    responses = {
        f"{www}/robots.txt": MISSING,
        f"{www}/": (301, {**HTML, "location": f"{bare}/"}, b""),
        f"{bare}/robots.txt": MISSING,
        f"{bare}/": page(*links, lang="en-US", head=alternates),
        f"{bare}/sitemap.xml": MISSING,
        f"{bare}/sitemap_index.xml": MISSING,
    }
    for path in links:
        responses[f"{bare}{path}"] = page("/", name=path)
    return {"mode": "crawl", "start_url": f"{www}/"}, responses


def crawl_delay():
    """Crawl-delay before the first User-agent line (Hacks, S5)."""
    origin = "https://slow.example"
    responses = {
        f"{origin}/robots.txt": robots("Crawl-delay: 10\n\nUser-agent: *\nAllow: /\n"),
        f"{origin}/docs/": page("/docs/a", "/docs/b"),
        f"{origin}/sitemap.xml": MISSING,
        f"{origin}/sitemap_index.xml": MISSING,
        f"{origin}/docs/a": page("/docs/", name="a"),
        f"{origin}/docs/b": page("/docs/", name="b"),
    }
    return {"mode": "crawl", "start_url": f"{origin}/docs/"}, responses


def sitemap_input():
    """A sitemap entered directly, with a search section and one URL on
    another site."""
    origin = "https://maps.example"
    urls = [f"{origin}/docs/{n}" for n in range(1, 25)]
    urls += [f"{origin}/search/a", f"{origin}/search/b", "https://other.example/x"]
    responses = {
        f"{origin}/robots.txt": robots("User-agent: *\nCrawl-delay: 2\n"),
        f"{origin}/sitemap.xml": (200, XML, urlset(*urls)),
    }
    return {"mode": "sitemap", "sitemap_url": f"{origin}/sitemap.xml"}, responses


def url_list():
    """Two origins; one disallows a listed URL, the other sets a delay."""
    a, b = "https://a.example", "https://b.example"
    responses = {
        f"{a}/robots.txt": robots("User-agent: *\nDisallow: /private\n"),
        f"{b}/robots.txt": robots("User-agent: *\nCrawl-delay: 4\n"),
        f"{a}/1": page(name="one"),
        f"{b}/x": page(name="x"),
    }
    selection = {
        "mode": "url_list",
        "urls": [f"{a}/1", f"{a}/2", f"{a}/private/3", f"{b}/x"],
    }
    return selection, responses


def single_url():
    """One page that is a JavaScript shell."""
    origin = "https://app.example"
    responses = {
        f"{origin}/robots.txt": MISSING,
        f"{origin}/": (
            200,
            HTML,
            b"<html><body><div id='root'></div><script src='/app.js'></script>"
            b"</body></html>",
        ),
    }
    return {"mode": "single_url", "url": f"{origin}/"}, responses


SITES = {
    "docs_sitemap": docs_sitemap,
    "docs_crawl": docs_crawl,
    "multilingual": multilingual,
    "crawl_delay": crawl_delay,
    "sitemap_input": sitemap_input,
    "url_list": url_list,
    "single_url": single_url,
}


def run(selection, responses, clock=None):
    """Probe `selection` against `responses`; returns (signals, transport)."""
    clock = clock or FakeClock()
    transport = Transport(responses, clock)
    client = SafeHttpClient(resolver=public_resolver, transport=transport)
    signals = probe_website(
        selection,
        connector_factory=lambda: WebsiteConnector(
            client=client, clock=clock, sleeper=clock.sleep, jitter=lambda: 0.0
        ),
        user_agent=UA,
        clock=clock,
        sleeper=clock.sleep,
    )
    return signals, transport


def probe_site(name: str):
    selection, responses = SITES[name]()
    return run(selection, responses)[0]


def selection_of(name: str) -> dict:
    return SITES[name]()[0]


def recorded(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def record_all() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name in SITES:
        value = probe_site(name).as_json()
        (FIXTURES / f"{name}.json").write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

"""Pinned-address HTTP transport for the public-website SSRF boundary."""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass
from posixpath import normpath
from typing import Callable, Protocol
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

from app.connectors.base import ConnectorFailure, ConnectorIssue


REDIRECT_STATUSES = {301, 302, 303, 307, 308}
BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}


def failure(code: str, message: str, *, retryable: bool = False):
    return ConnectorFailure(
        ConnectorIssue(code=code, message=message, retryable=retryable)
    )


def canonical_url(value: str, *, base: str | None = None) -> str:
    try:
        parts = urlsplit(urljoin(base, value) if base else value)
        port = parts.port
    except ValueError as exc:
        raise failure("invalid_url", "The website URL is invalid.") from exc
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise failure("unsafe_scheme", "Website URLs must use HTTP or HTTPS.")
    if parts.username is not None or parts.password is not None:
        raise failure("url_credentials", "Website URLs cannot contain credentials.")
    if not parts.hostname:
        raise failure("invalid_url", "The website URL must contain a hostname.")
    try:
        hostname = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise failure("invalid_hostname", "The website hostname is invalid.") from exc
    if not hostname or len(hostname) > 253:
        raise failure("invalid_hostname", "The website hostname is invalid.")
    default_port = 80 if scheme == "http" else 443
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None and port != default_port:
        netloc += f":{port}"
    decoded = unquote(parts.path or "/")
    normalized = normpath(decoded)
    if decoded.endswith("/") and not normalized.endswith("/"):
        normalized += "/"
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    path = quote(normalized, safe="/%:@!$&'()*+,;=-._~")
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def url_origin(value: str) -> str:
    parts = urlsplit(canonical_url(value))
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def resolve_public(
    hostname: str, port: int, resolver=socket.getaddrinfo
) -> tuple[str, ...]:
    if hostname.lower().rstrip(".") in BLOCKED_HOSTS or hostname.lower().endswith(
        ".localhost"
    ):
        raise failure("blocked_destination", "The website destination is not public.")
    try:
        literal = ipaddress.ip_address(hostname)
        addresses = [literal]
    except ValueError:
        try:
            answers = resolver(hostname, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise failure(
                "dns_failure",
                "The website hostname could not be resolved.",
                retryable=True,
            ) from exc
        addresses = []
        for answer in answers:
            try:
                addresses.append(ipaddress.ip_address(answer[4][0]))
            except (ValueError, IndexError) as exc:
                raise failure("dns_failure", "The DNS response was invalid.") from exc
    if not addresses:
        raise failure(
            "dns_failure", "The website hostname returned no addresses.", retryable=True
        )
    if any(
        not address.is_global
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
        for address in addresses
    ):
        raise failure("blocked_destination", "The website destination is not public.")
    return tuple(dict.fromkeys(str(address) for address in addresses))


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status: int
    headers: dict[str, str]
    content: bytes
    redirect_count: int
    transferred_bytes: int


class HttpTransport(Protocol):
    def request(
        self,
        url: str,
        address: str,
        timeout: float,
        headers: dict[str, str],
        max_bytes: int,
    ) -> tuple[int, dict[str, str], bytes]: ...


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, address: str, port: int, timeout: float):
        super().__init__(host, port=port, timeout=timeout)
        self._address = address

    def connect(self):
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, port: int, timeout: float):
        super().__init__(
            host, port=port, timeout=timeout, context=ssl.create_default_context()
        )
        self._address = address

    def connect(self):
        raw = socket.create_connection((self._address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


class StdlibTransport:
    def request(self, url, address, timeout, headers, max_bytes):
        parts = urlsplit(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        connection_class = (
            _PinnedHTTPSConnection if parts.scheme == "https" else _PinnedHTTPConnection
        )
        connection = connection_class(parts.hostname, address, port, timeout)
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
        try:
            connection.request("GET", target, headers=headers)
            response = connection.getresponse()
            content_length = response.getheader("Content-Length")
            if content_length is not None:
                try:
                    if int(content_length) > max_bytes:
                        raise failure(
                            "response_too_large",
                            "The website response exceeded its byte limit.",
                        )
                except ValueError as exc:
                    raise failure(
                        "invalid_response",
                        "The website returned an invalid content length.",
                    ) from exc
            content = bytearray()
            while True:
                chunk = response.read(min(65536, max_bytes + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise failure(
                        "response_too_large",
                        "The website response exceeded its byte limit.",
                    )
            return (
                response.status,
                {key.lower(): value for key, value in response.getheaders()},
                bytes(content),
            )
        except (TimeoutError, socket.timeout) as exc:
            raise failure(
                "request_timeout", "The website request timed out.", retryable=True
            ) from exc
        except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
            raise failure(
                "request_failed", "The website request failed.", retryable=True
            ) from exc
        finally:
            connection.close()


class SafeHttpClient:
    def __init__(
        self, *, resolver=socket.getaddrinfo, transport: HttpTransport | None = None
    ):
        self.resolver = resolver
        self.transport = transport or StdlibTransport()

    def get(
        self,
        url: str,
        *,
        user_agent: str,
        request_timeout: float,
        deadline: float,
        redirect_limit: int,
        max_response_bytes: int,
        max_total_bytes: int,
        allowed: Callable[[str], bool],
    ) -> HttpResponse:
        current = canonical_url(url)
        total = 0
        redirects = 0
        while True:
            if time.monotonic() >= deadline:
                raise failure(
                    "deadline_exceeded",
                    "The website preview exceeded its deadline.",
                    retryable=True,
                )
            if not allowed(current):
                raise failure(
                    "outside_scope", "The URL is outside the configured website scope."
                )
            parts = urlsplit(current)
            port = parts.port or (443 if parts.scheme == "https" else 80)
            addresses = resolve_public(parts.hostname, port, self.resolver)
            remaining = min(max_response_bytes, max_total_bytes - total)
            if remaining <= 0:
                raise failure(
                    "total_bytes_exceeded",
                    "The website preview exceeded its total byte limit.",
                )
            headers = {
                "Accept": "text/html, application/xml;q=0.9, text/xml;q=0.9, text/plain;q=0.8",
                "Accept-Encoding": "identity",
                "User-Agent": user_agent,
                "Host": parts.netloc,
                "Connection": "close",
            }
            status, response_headers, content = self.transport.request(
                current,
                addresses[0],
                min(request_timeout, max(0.001, deadline - time.monotonic())),
                headers,
                remaining,
            )
            encoding = response_headers.get("content-encoding", "identity").lower()
            if encoding not in ("", "identity"):
                raise failure(
                    "unsupported_encoding",
                    "Compressed website responses are not accepted in preview.",
                )
            total += len(content)
            if status not in REDIRECT_STATUSES:
                return HttpResponse(
                    current, status, response_headers, content, redirects, total
                )
            location = response_headers.get("location")
            if not location or len(location) > 4000:
                raise failure(
                    "invalid_redirect", "The website returned an invalid redirect."
                )
            if redirects >= redirect_limit:
                raise failure(
                    "redirect_limit", "The website exceeded its redirect limit."
                )
            current = canonical_url(location, base=current)
            redirects += 1

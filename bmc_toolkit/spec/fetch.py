"""Downloading a document version into the Library.

The chain is direct download, then the Internet Archive's Wayback Machine,
then an instruction for the user. Which steps run depends on the document's
fetch method in the catalog. Every network call goes through an ``HttpClient``
so tests can substitute a fake; the default client prefers ``curl_cffi``
(browser TLS fingerprint, needed by some publishers) and falls back to
``urllib`` when it is not installed.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from bmc_toolkit.spec.catalog import Document, Version
from bmc_toolkit.spec.library import Library

WAYBACK_AVAILABLE = "https://archive.org/wayback/available?url="
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
TIMEOUT_S = 120
MAGIC = {"pdf": (b"%PDF",), "zip": (b"PK\x03\x04",)}


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def header(self, name: str) -> str:
        return self.headers.get(name.lower(), "")


HttpClient = Callable[[str], Response]
"""Fetch a URL following redirects; raises OSError on transport failure."""


def _urllib_client(url: str) -> Response:
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            body = resp.read()
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return Response(resp.status, headers, body)
    except urllib.error.HTTPError as exc:
        return Response(exc.code, {k.lower(): v for k, v in exc.headers.items()}, b"")


def _curl_cffi_client(url: str) -> Response:
    from curl_cffi import requests  # lazy: optional at runtime

    resp = requests.get(url, impersonate="chrome", timeout=TIMEOUT_S)
    headers = {k.lower(): v for k, v in resp.headers.items()}
    return Response(resp.status_code, headers, resp.content)


def default_client() -> HttpClient:
    try:
        import curl_cffi  # noqa: F401
    except ImportError:
        return _urllib_client
    return _curl_cffi_client


class RejectedBody(Exception):
    """The response was not the file we asked for."""


def check_body(resp: Response, expected_type: str) -> bytes:
    """Return the body if it is a complete file of the expected type."""
    if resp.status != 200:
        raise RejectedBody(f"HTTP {resp.status}")
    body = resp.body
    if not any(body.startswith(m) for m in MAGIC[expected_type]):
        ctype = resp.header("content-type") or "unknown content type"
        raise RejectedBody(f"not a {expected_type} ({ctype}, {len(body)} bytes)")
    declared = resp.header("content-length")
    # A body shorter than Content-Length is a cut-off download. Longer is
    # fine: with Content-Encoding the header counts compressed bytes and the
    # client hands back the decompressed body.
    if declared.isdigit() and not resp.header("content-encoding"):
        if len(body) < int(declared):
            raise RejectedBody(f"truncated: {len(body)} of {declared} bytes")
    return body


def wayback_snapshot(url: str, client: HttpClient) -> str | None:
    """The Wayback Machine URL serving the archived original bytes, if any."""
    resp = client(WAYBACK_AVAILABLE + urllib.parse.quote(url, safe=":/?=&"))
    if resp.status != 200:
        return None
    try:
        info = json.loads(resp.body.decode("utf-8"))
        closest = info["archived_snapshots"]["closest"]
        if not closest.get("available"):
            return None
        snapshot = closest["url"]
        timestamp = closest["timestamp"]
    except (ValueError, KeyError, TypeError):
        return None
    # ".../web/<timestamp>/<url>" -> ".../web/<timestamp>id_/<url>" serves raw bytes
    marker = f"/web/{timestamp}/"
    if marker not in snapshot:
        return None
    return snapshot.replace(marker, f"/web/{timestamp}id_/", 1)


@dataclass(frozen=True)
class Outcome:
    status: str  # fetched | skipped | failed
    document: str
    version: str
    method: str = ""
    message: str = ""
    attempts: tuple[str, ...] = ()


def manual_instruction(library: Library, doc: Document, ver: Version) -> str:
    target = library.version_dir(doc.family, doc.id, ver.version)
    lines = []
    if ver.url and doc.access != "confidential":
        lines.append(f"Open in a browser: {ver.url}")
    else:
        lines.append(f"Obtain '{doc.title}' version {ver.version} from {doc.family}.")
    lines.append(f"Save it as: {target / ('original.' + ver.type)}")
    lines.append("Then run: bmcspec scan")
    return "\n".join(lines)


def fetch_version(
    library: Library,
    doc: Document,
    ver: Version,
    *,
    force: bool = False,
    client: HttpClient | None = None,
) -> Outcome:
    """Bring one document version into the Library."""
    existing = library.find(doc.id, ver.version)
    if existing is not None and not force:
        return Outcome("skipped", doc.id, ver.version, "library", "already in Library")

    steps: list[str] = []
    if doc.fetch == "direct":
        steps = ["direct", "wayback"]
    elif doc.fetch == "wayback":
        steps = ["wayback"]
    if not ver.url:
        steps = []

    attempts: list[str] = []
    if steps and client is None:
        client = default_client()
    for step in steps:
        try:
            if step == "direct":
                body = check_body(client(ver.url), ver.type)
                source_url = ver.url
            else:
                snapshot = wayback_snapshot(ver.url, client)
                if snapshot is None:
                    raise RejectedBody("no Wayback snapshot")
                body = check_body(client(snapshot), ver.type)
                source_url = snapshot
        except (RejectedBody, OSError) as exc:
            attempts.append(f"{step}: {exc}")
            continue
        library.store(
            doc.family,
            doc.id,
            ver.version,
            body,
            ver.type,
            url=None if doc.access == "confidential" else source_url,
            method=step,
        )
        return Outcome("fetched", doc.id, ver.version, step, "", tuple(attempts))

    message = manual_instruction(library, doc, ver)
    return Outcome("failed", doc.id, ver.version, "manual", message, tuple(attempts))

"""Publisher listings: what versions a publisher says exist right now.

Three sources, named by a document's ``listing`` key in the Source Catalog:

- ``dmtf:<DSP id>``: the published-documents page lists the current version
  of every DSP (one request for all of them); the per-DSP page lists every
  version with its publication date.
- ``nvme:<slug>``: the nvmexpress.org specifications API (JSON) gives the
  current file of each specification; earlier versions appear only as
  attachment ids, so the history is the current version alone.
- ``ocp:<wiki page>|<description prefix>``: the OCP wiki's specification
  tables (Description, Version or Revision, Submit Date, Link). Links are
  mostly Google Drive viewers, so a human confirms the download URL.

Standard library only. Every page comes through the ``HttpClient`` of
``fetch``; pages are cached per ``Listings`` instance so a check over the
whole catalog fetches each listing once.
"""

import datetime
import json
import re
import urllib.parse
from dataclasses import dataclass
from html.parser import HTMLParser

from bmc_toolkit.spec.fetch import HttpClient

DMTF_PUBLISHED = "https://www.dmtf.org/standards/published_documents"
DMTF_DSP = "https://www.dmtf.org/dsp/{key}"
NVME_API = "https://nvmexpress.org/wp-json/vtm/v1/specifications"
OCP_WIKI = "https://www.opencompute.org/w/index.php?title={page}"

PUBLISHER_NAMES = {"dmtf": "DMTF", "nvme": "NVM Express", "ocp": "the OCP wiki"}

_MONTHS = {
    m: i
    for i, m in enumerate(
        "jan feb mar apr may jun jul aug sep oct nov dec".split(), start=1
    )
}
_DMTF_VERSION_IN_URL = re.compile(r"DSP\d+_(?P<version>[^/]+?)(?:_\d)?\.(?:pdf|zip)$")
_NVME_DATE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})")
_NVME_VERSION = (
    re.compile(r"Revision[-_](?P<v>\d+[._]\d+[a-z]?)"),
    re.compile(r"[-_](?P<v>\d+[._]\d+[a-z]?)[-_](?:\d{4}\.|Ratified|gold)"),
)
_OCP_DOTTED = re.compile(r"\d+(?:\.\d+)+")
_OCP_BARE = re.compile(r"(?<![A-Za-z])\d+")
_OCP_RC = re.compile(r"RC\d+", re.IGNORECASE)
_OCP_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}|[A-Z][a-z]+ \d{1,2}, \d{4}")


class ListingError(Exception):
    """The listing could not be fetched or does not say what was asked."""


@dataclass(frozen=True)
class Seen:
    """One version as the publisher lists it."""

    version: str
    url: str = ""  # "" when the listing gives no direct file
    published: str = ""  # ISO date, "" when the listing gives none
    note: str = ""  # a status or the wiki description


def parse_listing(listing: str) -> tuple[str, str]:
    source, _, key = listing.partition(":")
    if not source or not key:
        raise ListingError(f"'{listing}' is not '<source>:<key>'")
    return source, key.strip()


def version_key(source: str, version: str) -> str:
    """What makes two version strings the same version: verbatim for DMTF
    and NVMe; for OCP the leading number and the RC token, so the wiki's
    ``1.2 RC3`` matches the catalog's ``R1 v1.2 RC3``."""
    if source != "ocp":
        return version.strip()
    dotted = _OCP_DOTTED.search(version)  # "1.2" of "R1 v1.2 RC3", not the 1 of R1
    bare = _OCP_BARE.search(version)
    number = dotted.group(0) if dotted else (bare.group(0) if bare else "")
    rc = _OCP_RC.search(version)
    return f"{number} {rc.group(0).upper() if rc else ''}".strip()


# ------------------------------------------------------------- parsing


class _Tables(HTMLParser):
    """Every <table> as rows of (text, href) cells."""

    def __init__(self):
        super().__init__()
        self.tables: list[list[list[tuple[str, str]]]] = []
        self._row = None
        self._cell = None
        self._href = ""

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            self._href = ""
        elif tag == "a" and self._cell is not None and not self._href:
            self._href = dict(attrs).get("href") or ""
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append((" ".join("".join(self._cell).split()), self._href))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def html_tables(html: str) -> list[list[list[tuple[str, str]]]]:
    parser = _Tables()
    parser.feed(html)
    return parser.tables


def _records(html: str, *required: str) -> list[dict[str, tuple[str, str]]]:
    """Rows of every table whose header has all ``required`` column names
    (case-insensitive prefix match), keyed by the lower-cased header."""
    out = []
    for table in html_tables(html):
        if not table:
            continue
        header = []
        for cell in table[0]:  # a repeated name keeps its first column
            name = cell[0].lower().rstrip(". ")
            header.append(name if name not in header else f"{name}#{len(header)}")
        if not all(any(h.startswith(r) for h in header) for r in required):
            continue
        for row in table[1:]:
            if len(row) != len(header):
                continue
            out.append(dict(zip(header, row, strict=True)))
    return out


def _column(record: dict, *names: str) -> tuple[str, str]:
    for name in names:
        for key, value in record.items():
            if key.startswith(name):
                return value
    return "", ""


def dmtf_date(text: str) -> str:
    """``25 Mar 2024`` to ``2024-03-25``; "" when not a date."""
    parts = text.split()
    if len(parts) != 3 or not parts[0].isdigit() or not parts[2].isdigit():
        return ""
    month = _MONTHS.get(parts[1][:3].lower())
    if not month:
        return ""
    try:
        return datetime.date(int(parts[2]), month, int(parts[0])).isoformat()
    except ValueError:
        return ""


def dmtf_version_of_url(url: str) -> str:
    """The version string in a DMTF file name (``DSP0236_1.3.3.pdf``); a
    ``_0`` or ``_1`` re-upload suffix is not part of it. "" for the few
    irregular names (``DSP0134V2.4Final.pdf``)."""
    m = _DMTF_VERSION_IN_URL.search(url)
    return m.group("version") if m else ""


def parse_dmtf_published(html: str) -> dict[str, Seen]:
    """DSP id -> the current version, from the published-documents page."""
    out = {}
    for rec in _records(html, "dsp", "version", "title"):
        dsp = _column(rec, "dsp")[0].upper()
        version = _column(rec, "version")[0]
        title, href = _column(rec, "title")
        if not dsp.startswith("DSP") or not version:
            continue
        out[dsp] = Seen(version, urllib.parse.urljoin(DMTF_PUBLISHED, href))
    return out


def parse_dmtf_versions(html: str) -> list[Seen]:
    """Every version of one DSP with its date, from the per-DSP page."""
    out = []
    for rec in _records(html, "version", "title", "publication date"):
        version = _column(rec, "version")[0]
        _, href = _column(rec, "title")
        if not version or not href:
            continue
        comments = _column(rec, "comments")[0]
        out.append(
            Seen(
                version,
                urllib.parse.urljoin(DMTF_PUBLISHED, href),
                dmtf_date(_column(rec, "publication date")[0]),
                "" if comments.lower() == "standard" else comments,
            )
        )
    return out


def nvme_version_of_url(url: str) -> str:
    """The version in an nvmexpress.org file name: ``Revision-2.4``,
    ``2.0e-2024.07.29``, ``1_3d-2019``, ``1_0_gold``; "" when none."""
    name = url.rsplit("/", 1)[-1]
    for pattern in _NVME_VERSION:
        m = pattern.search(name)
        if m:
            return m.group("v").replace("_", ".")
    return ""


def parse_nvme(body: bytes | str) -> dict[str, Seen]:
    """Specification slug -> its current file, from the API's JSON."""
    try:
        data = json.loads(body)
        posts = data["posts"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ListingError(
            f"nvmexpress.org API: not the expected JSON ({exc})"
        ) from exc
    out = {}
    for post in posts:
        if not isinstance(post, dict):
            continue
        slug = str(post.get("slug") or "")
        file = post.get("file")
        if not slug or not isinstance(file, dict):
            continue
        url = str(file.get("url") or "")
        if not url:
            continue
        m = _NVME_DATE.search(url.rsplit("/", 1)[-1])
        published = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""
        out[slug] = Seen(nvme_version_of_url(url), url, published)
    return out


def ocp_date(text: str) -> str:
    """The first date in a wiki cell (``4/24/26``, ``3/21/2024``,
    ``October 16, 2025``) as ISO; "" when none."""
    m = _OCP_DATE.search(text)
    if not m:
        return ""
    token = m.group(0)
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%B %d, %Y"):
        try:
            return datetime.datetime.strptime(token, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def parse_ocp(html: str, prefix: str) -> list[Seen]:
    """Specification rows whose description starts with ``prefix``."""
    wanted = prefix.casefold()
    out = []
    for rec in _records(html, "type", "description", "submit date"):
        description, href = _column(rec, "description")
        if not description.casefold().startswith(wanted):
            continue
        version = _column(rec, "version", "revision")[0]
        if not href:
            href = _column(rec, "link")[1]
        if not version:
            continue
        out.append(
            Seen(version, href, ocp_date(_column(rec, "submit date")[0]), description)
        )
    return out


# ------------------------------------------------------------ fetching


class Listings:
    """Publisher listings fetched on demand and cached for the instance."""

    def __init__(self, client: HttpClient):
        self.client = client
        self._pages: dict[str, bytes] = {}

    def _get(self, url: str) -> bytes:
        if url not in self._pages:
            try:
                resp = self.client(url)
            except OSError as exc:
                raise ListingError(f"{url}: {exc}") from exc
            if resp.status != 200:
                raise ListingError(f"{url}: HTTP {resp.status}")
            self._pages[url] = resp.body
        return self._pages[url]

    def _text(self, url: str) -> str:
        return self._get(url).decode("utf-8", errors="replace")

    def current(self, listing: str) -> list[Seen]:
        """What the publisher lists now for the key: one version for DMTF
        and NVMe, the matching wiki rows for OCP (newest first as listed).
        ListingError when the key is not on the page."""
        source, key = parse_listing(listing)
        if source == "dmtf":
            table = parse_dmtf_published(self._text(DMTF_PUBLISHED))
            if key.upper() not in table:
                raise ListingError(f"{key} is not on {DMTF_PUBLISHED}")
            return [table[key.upper()]]
        if source == "nvme":
            table = parse_nvme(self._get(NVME_API))
            if key not in table:
                raise ListingError(f"no specification '{key}' in {NVME_API}")
            return [table[key]]
        if source == "ocp":
            page, _, prefix = key.partition("|")
            if not page or not prefix:
                raise ListingError(f"ocp key '{key}' is not '<page>|<prefix>'")
            rows = parse_ocp(self._text(OCP_WIKI.format(page=page)), prefix)
            if not rows:
                raise ListingError(f"no row starting with '{prefix}' on wiki {page}")
            return rows
        raise ListingError(f"unknown listing source '{source}'")

    def history(self, listing: str) -> list[Seen]:
        """Every version the publisher lists with dates where it gives
        them: the DMTF per-DSP page; for NVMe and OCP the same as
        ``current``."""
        source, key = parse_listing(listing)
        if source != "dmtf":
            return self.current(listing)
        rows = parse_dmtf_versions(self._text(DMTF_DSP.format(key=key.upper())))
        if not rows:
            raise ListingError(f"no versions on {DMTF_DSP.format(key=key.upper())}")
        return rows


__all__ = [
    "DMTF_DSP",
    "DMTF_PUBLISHED",
    "NVME_API",
    "OCP_WIKI",
    "PUBLISHER_NAMES",
    "ListingError",
    "Listings",
    "Seen",
    "dmtf_date",
    "dmtf_version_of_url",
    "html_tables",
    "nvme_version_of_url",
    "ocp_date",
    "parse_dmtf_published",
    "parse_dmtf_versions",
    "parse_listing",
    "parse_nvme",
    "parse_ocp",
    "version_key",
]

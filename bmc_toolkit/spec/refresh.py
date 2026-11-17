"""Bringing the Source Catalog up to date from the publishers' listings.

A maintainer's tool. For every document with a listing it reports the
versions the publisher lists that the catalog lacks and, with ``--write``,
inserts each as a ``[[documents.versions]]`` block into the document's
block in the catalog file, at its place in publication order (see
``append_versions``). The file is edited as text so the maintainer
comments survive; the result is re-parsed before it is kept. A version
block whose ``version`` or ``published`` line the text scan cannot read
(``UnreadableBlock``) makes the document be skipped rather than edited at
the wrong place.
OCP versions are only reported: their links are viewers, not files.
A document's newest Markdown version, pinned to a commit in a
raw.githubusercontent.com URL, is compared with the newest commit touching
its file (``check_pin``, one GitHub API request); a newer one is reported
as ``changed`` with the URL to re-pin to, and never written.
A DSP id on DMTF's published-documents page that the catalog neither
lists nor names in ``[listings.dmtf] not_taken`` is reported
(``unlisted``) and never written.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

from bmc_toolkit.spec.catalog import (
    Catalog,
    CatalogError,
    Document,
    Version,
    load_catalog,
    version_numbers,
)
from bmc_toolkit.spec.fetch import HttpClient
from bmc_toolkit.spec.listing import ListingError, Listings, Seen, version_key

_BLOCK_START = re.compile(r"^\[\[(documents|repos)\]\]\s*$")
# A plain table such as [listings.dmtf] or [families.x]: never part of a
# document's block, wherever the file puts it.
_TABLE_START = re.compile(r"^\[[A-Za-z0-9_.-]+\]\s*(?:#.*)?$")
_SECTION_COMMENT = re.compile(r"^# -{10,}")


class RefreshError(Exception):
    """The catalog text could not be edited; the message says why."""


@dataclass(frozen=True)
class Proposal:
    """One thing the publisher's listing says about a document."""

    kind: str  # add | confirm | changed | unreachable | obsoleted
    document: str
    seen: Seen | None = None
    problem: str = ""
    why: str = ""  # for confirm: what keeps it from being written

    @property
    def writable(self) -> bool:
        """An ``add``: a published version whose URL is a file the fetch
        chain can download."""
        return self.kind == "add"


def _file_type(url: str) -> str:
    lower = url.lower().split("?", 1)[0]
    for ext in ("pdf", "zip"):
        if lower.endswith("." + ext):
            return ext
    return ""


def _file_id(url: str) -> str:
    """A URL without its scheme: a listing's http:// link names the same
    file as the catalog's https:// one (DSP8011 2017.1)."""
    return re.sub(r"^https?://", "", url, flags=re.IGNORECASE)


def _is_wip(seen: Seen) -> bool:
    """A Work-in-Progress row: the catalog lists WIP releases only by hand,
    with ``wip = true``, so refresh never writes one."""
    return "work in progress" in seen.note.lower() or "_wip" in seen.url.lower()


def _why_confirm(source: str, seen: Seen) -> str:
    if source == "ocp":
        return "URL to confirm by hand"
    if _is_wip(seen):
        return "work in progress, not written; add it by hand with wip = true"
    return "not a pdf or zip URL, not written"


def proposals(doc: Document, listings: Listings) -> list[Proposal]:
    """What the listing adds to the catalog entry of one document; for an
    RFC, an ``obsoleted`` proposal per obsoleting RFC its ``obsoleted_by``
    lacks (never written)."""
    try:
        seen = listings.history(doc.listing)
    except ListingError as exc:
        return [Proposal("unreachable", doc.id, problem=str(exc))]
    source = doc.listing_source
    if source == "rfc":
        known = set(doc.obsoleted_by)
        return [
            Proposal("obsoleted", doc.id, s) for s in seen if s.version not in known
        ]
    by_key = {version_key(source, v.version): v for v in doc.versions}
    # A publisher may list one version more than once (DMTF keeps a file and
    # its re-upload, DSP0266 1.20.2): the catalog URL has not moved while
    # any of those rows still names it.
    listed: dict[str, set[str]] = {}
    for s in seen:
        listed.setdefault(version_key(source, s.version), set()).add(_file_id(s.url))
    out = []
    for s in seen:
        key = version_key(source, s.version)
        known = by_key.get(key)
        if known is None:
            if source != "ocp" and _file_type(s.url) and not _is_wip(s):
                out.append(Proposal("add", doc.id, s))
            else:
                out.append(Proposal("confirm", doc.id, s, why=_why_confirm(source, s)))
        elif (
            source != "ocp"
            and known.url
            and s.url
            and _file_id(known.url) not in listed[key]
        ):
            out.append(Proposal("changed", doc.id, s))
    return out


@dataclass(frozen=True)
class Unlisted:
    """A DSP id on DMTF's published-documents page that the catalog
    neither lists nor names in ``[listings.dmtf] not_taken``."""

    dsp: str
    seen: Seen
    title: str


def unlisted(catalog: Catalog, listings: Listings) -> list[Unlisted]:
    """The page's ids the catalog has not decided on, in id order; an id a
    document lists is never one, whatever ``not_taken`` covers.
    ListingError when the page cannot be read."""
    listed = catalog.dmtf_listed()
    return [
        Unlisted(dsp, seen, title)
        for dsp, (seen, title) in sorted(listings.dmtf_published().items())
        if dsp not in listed and not catalog.dmtf_not_taken_covers(dsp)
    ]


# ------------------------------------------------- pinned Markdown files

PIN_SOURCE = "github"
_RAW_PIN = re.compile(
    r"^https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([0-9a-f]{40})/(.+)$"
)
COMMITS_API = (
    "https://api.github.com/repos/{owner}/{repo}/commits?path={path}&per_page=1"
)
RAW_URL = "https://raw.githubusercontent.com/{owner}/{repo}/{sha}/{path}"


@dataclass(frozen=True)
class PinReport:
    """What the repository says about the commit a Markdown version pins."""

    kind: str  # changed | confirm | unreachable
    document: str
    version: str
    text: str

    def line(self) -> str:
        return f"{self.kind} {self.document} {self.version}: {self.text}"


def markdown_version(doc: Document) -> Version | None:
    """The document's newest Markdown version, ordered as
    ``Document.latest`` orders versions (publication date, then the numbers
    in the version string, then catalog order), or None."""
    pinned = [v for v in doc.versions if v.type == "md"]
    if not pinned:
        return None
    return sorted(pinned, key=lambda v: (v.published, version_numbers(v.version)))[-1]


def _newest_commit(body: bytes) -> tuple[str, str] | None:
    """(sha, YYYY-MM-DD) of the first commit in a commits API reply, None
    for an empty list; ValueError when the reply is not such a list."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("the reply is not JSON") from exc
    if not isinstance(data, list):
        raise ValueError("the reply is not a list of commits")
    if not data:
        return None
    first = data[0]
    try:
        sha = first["sha"]
        date = first["commit"]["committer"]["date"]
    except (KeyError, TypeError) as exc:
        raise ValueError("the first commit has no sha or committer date") from exc
    if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)):
        raise ValueError("the first commit's sha is not a commit id")
    if not (isinstance(date, str) and re.match(r"\d{4}-\d{2}-\d{2}", date)):
        raise ValueError("the first commit's date is not a date")
    return sha, date[:10]


def check_pin(doc: Document, client: HttpClient) -> PinReport | None:
    """Compare the commit the document's newest Markdown version pins with
    the newest commit touching its file on the default branch. None when
    there is nothing to report (no Markdown version, or the pin is the
    newest commit). Never edits the catalog: a newer commit may be a new
    revision, whose version string the maintainer decides."""
    ver = markdown_version(doc)
    if ver is None:
        return None

    def report(kind: str, text: str) -> PinReport:
        return PinReport(kind, doc.id, ver.version, text)

    m = _RAW_PIN.match(ver.url)
    if not m:
        return report(
            "confirm",
            f"{ver.url} (cannot check: not a pinned raw.githubusercontent.com URL)",
        )
    owner, repo, pinned, path = m.groups()
    # The catalog URL may carry escapes (a space is %20): the API takes the
    # file's name, so decode before encoding it once; the messages name the
    # file, and the re-pin URL keeps the catalog's spelling.
    name = unquote(path)
    api = COMMITS_API.format(owner=owner, repo=repo, path=quote(name, safe="/"))
    try:
        resp = client(api)
    except OSError as exc:
        return report("unreachable", f"{api}: {exc}")
    if resp.status in (403, 429):
        return report(
            "unreachable",
            f"{api}: HTTP {resp.status} (the GitHub API rate limit: "
            f"60 requests an hour without a token; try again later)",
        )
    if resp.status != 200:
        return report("unreachable", f"{api}: HTTP {resp.status}")
    try:
        newest = _newest_commit(resp.body)
    except ValueError as exc:
        return report("unreachable", f"{api}: {exc}")
    if newest is None:
        return report(
            "unreachable",
            f"{name} has no commit on the default branch of {owner}/{repo}",
        )
    sha, date = newest
    if sha == pinned:
        return None
    url = RAW_URL.format(owner=owner, repo=repo, sha=sha, path=path)
    return report(
        "changed",
        f"{name} has commit {sha[:7]} ({date}), the catalog pins {pinned[:7]}; "
        f"{url} (not written; re-pin by hand)",
    )


def _toml_string(value: str) -> str:
    """A TOML basic string: JSON's escaping of ``"`` and ``\\`` is TOML's."""
    return json.dumps(value, ensure_ascii=False)


def version_block(seen: Seen) -> str:
    lines = [
        "[[documents.versions]]",
        f"version = {_toml_string(seen.version)}",
        f"url = {_toml_string(seen.url)}",
        f'type = "{_file_type(seen.url)}"',
        f"published = {_toml_string(seen.published)}",
    ]
    if seen.note:
        lines.append(f"notes = {_toml_string(seen.note)}")
    return "\n".join(lines) + "\n"


def _document_span(lines: list[str], doc_id: str) -> tuple[int, int]:
    """(start, end) line indexes of the document's block: from its
    ``[[documents]]`` line to the line before the next block or plain
    ``[table]``, the next section comment, or the end of the file. Comment
    lines (blank lines between them included) that run up to the next block
    or the end of the file introduce what follows, so the span ends above
    them; a section comment ends the span where it stands."""
    id_re = re.compile(rf'^id\s*=\s*"{re.escape(doc_id)}"\s*$', re.IGNORECASE)
    start = None
    for i, line in enumerate(lines):
        if _BLOCK_START.match(line):  # a repos block never holds a document
            start = i if line.startswith("[[documents]]") else None
        elif id_re.match(line) and start is not None:
            end = len(lines)
            for j in range(i + 1, len(lines)):
                if _SECTION_COMMENT.match(lines[j]):
                    return start, j
                if _BLOCK_START.match(lines[j]) or _TABLE_START.match(lines[j]):
                    end = j
                    break
            comments = end
            for j in range(end - 1, i, -1):
                if lines[j].lstrip().startswith("#"):
                    comments = j
                elif lines[j].strip():
                    break
            return start, comments
    raise RefreshError(f"no [[documents]] block with id {doc_id} in the catalog")


_VERSION_BLOCK = re.compile(r"^\[\[documents\.versions\]\]\s*$")
_KEY_LINE = re.compile(
    r"""^(version|published)\s*=\s*(?:"(?P<basic>[^"\\]*)"|'(?P<literal>[^']*)')\s*(?:#.*)?$"""
)
_KEY_START = re.compile(r"^(version|published)\s*=")


class UnreadableBlock(ValueError):
    """A version block carries a version or published line the text scan
    cannot read (an escape sequence, a multi-line string): the document is
    left alone rather than edited at the wrong place."""


def _version_blocks(
    lines: list[str], start: int, end: int
) -> list[tuple[int, str, str]]:
    """(line index, published, version) of every ``[[documents.versions]]``
    block between start and end, in file order."""
    blocks = []
    for i in range(start, end):
        if not _VERSION_BLOCK.match(lines[i]):
            continue
        published = version = ""
        for j in range(i + 1, end):
            if _VERSION_BLOCK.match(lines[j]):
                break
            m = _KEY_LINE.match(lines[j])
            if m is None:
                if _KEY_START.match(lines[j]):
                    raise UnreadableBlock(f"line {j + 1}: {lines[j].strip()}")
                continue
            value = (
                m.group("basic") if m.group("basic") is not None else m.group("literal")
            )
            if m.group(1) == "version":
                version = value
            else:
                published = value
        blocks.append((i, published, version))
    return blocks


def append_versions(path: Path, doc_id: str, seen: list[Seen]) -> None:
    """Add version blocks to the document's block at their place in the
    order the catalog keeps (publication date, same-day versions ascending
    by their numbers): before the first existing block that sorts after the
    new one, at the end when none does. The file is re-parsed afterwards
    and restored on a parse failure. Raises UnreadableBlock, before any
    edit, when an existing block cannot be placed."""
    if not seen:
        return
    with open(path, encoding="utf-8", newline="") as fh:  # read_text(newline=) is 3.13+
        original = fh.read()
    lines = original.split("\n")
    start, end = _document_span(lines, doc_id)
    while end > 0 and lines[end - 1].strip() == "":
        end -= 1
    existing = _version_blocks(lines, start, end)
    ordered = sorted(seen, key=lambda s: (s.published, version_numbers(s.version)))
    # Later insertions must not shift earlier ones: collect per position,
    # then rebuild from the end of the block backwards.
    at: dict[int, list[str]] = {}
    for s in ordered:
        key = (s.published, version_numbers(s.version))
        position = end
        for index, published, version in existing:
            if (published, version_numbers(version)) > key:
                position = index
                break
        at.setdefault(position, []).append(version_block(s))
    for position in sorted(at, reverse=True):
        # Blocks end in a newline; joined, that newline is the blank line
        # between them, and the trailing one is dropped here.
        blocks = "\n".join(at[position]).rstrip("\n").split("\n")
        if position == end:
            # A blank line, then the blocks, then whatever followed the block.
            lines[end:end] = ["", *blocks]
        else:
            # The blocks, then a blank line, before the block that follows.
            lines[position:position] = [*blocks, ""]
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8", newline="")
    try:
        load_catalog(path)
    except CatalogError as exc:
        path.write_text(original, encoding="utf-8", newline="")
        raise RefreshError(
            f"the edited catalog does not parse ({exc}); restored"
        ) from exc


__all__ = [
    "PIN_SOURCE",
    "PinReport",
    "Proposal",
    "RefreshError",
    "UnreadableBlock",
    "append_versions",
    "check_pin",
    "markdown_version",
    "proposals",
    "version_block",
]

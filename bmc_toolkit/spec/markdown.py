"""Markdown documents (a catalog version of type ``md``): check a body,
build the Outline from its headings, search it and hand out lines with
Citation lines.

A Markdown document has no pages. It is read by the line numbers of the
file as stored (``original.md``), which are the line numbers the publisher's
own repository shows at the pinned commit, so a reader can open the same
lines. Lines are split on ``\\n`` only (a ``\\r`` before it is dropped, a BOM
at the start is dropped); a final newline does not add a line.

The Outline holds the ATX headings (``#`` to ``######`` followed by a space
or a tab, at most three spaces of indent) outside fenced code blocks
(``````` or ``~~~``); level is the number of ``#`` minus one. Setext
headings and HTML headings are not read.

Files written next to the original::

    outline.json   [{"level": n, "title": "...", "line": n}, ...]
    extract.json   {"extractor_version": MARKDOWN_VERSION, "kind": "markdown",
                    "lines": n, "outline_entries": n, "seconds": s,
                    "outline_source": "headings"}

The ``cite:`` line keeps the seven fields of a PDF's::

    cite: <family> | <document> <version> | <sections> | Markdown
          | lines <a>-<b> | <origin> | <library path>

Standard library only.
"""

import json
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from bmc_toolkit.spec.library import atomic_write_json
from bmc_toolkit.spec.search import USER_PROVIDED, query_matches, query_words

MARKDOWN_VERSION = 1
KIND = "markdown"
META_NAME = "extract.json"  # shared with the PDF extractor; "kind" tells them apart
OUTLINE_NAME = "outline.json"
OUTLINE_SOURCE = "headings"
MAX_LINES = 200  # lines ``page`` prints per call
PAGE_FIELD = "Markdown"

_BOM = b"\xef\xbb\xbf"
_HTML_START = re.compile(rb"^\s*<(?:!doctype\s+html|html)[\s>]", re.IGNORECASE)
_HEADING = re.compile(r"^ {0,3}(?P<marks>#{1,6})(?:[ \t]+(?P<title>.*?))?[ \t]*$")
_CLOSING = re.compile(r"(?:^|[ \t]+)#+[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")


class MarkdownError(Exception):
    """A Markdown version cannot be read; the message says why."""


# ------------------------------------------------------------ the check


def looks_like_markdown(data: bytes) -> bool:
    """True for UTF-8 text (a BOM allowed) that is not an HTML page: what a
    publisher's raw Markdown URL returns, and not its error or login page."""
    if data.startswith(_BOM):
        data = data[len(_BOM) :]
    if not data.strip():
        return False
    if _HTML_START.match(data + b" "):
        return False
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


# ------------------------------------------------------------- reading


def split_lines(text: str) -> list[str]:
    """The file's lines as a repository viewer numbers them."""
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # the final newline
    return [ln[:-1] if ln.endswith("\r") else ln for ln in lines]


def read_lines(path: Path) -> list[str]:
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError as exc:
        raise MarkdownError(f"{path}: {exc}") from exc
    return split_lines(text)


def outline(lines: list[str]) -> list[dict]:
    """The ATX headings outside fenced code blocks, in order."""
    out: list[dict] = []
    fence: str | None = None  # the opening fence while inside a block
    for number, text in enumerate(lines, start=1):
        m = _FENCE.match(text)
        if fence is not None:
            if m and m.group("fence")[0] == fence[0]:
                if len(m.group("fence")) >= len(fence) and not m.group("info").strip():
                    fence = None
            continue
        if m and not (m.group("fence")[0] == "`" and "`" in m.group("info")):
            fence = m.group("fence")
            continue
        h = _HEADING.match(text)
        if not h:
            continue
        title = _CLOSING.sub("", h.group("title") or "").strip()
        if not title:
            continue
        out.append({"level": len(h.group("marks")) - 1, "title": title, "line": number})
    return out


# ------------------------------------------------------------- extract


@dataclass
class MarkdownResult:
    lines: int
    entries: int
    seconds: float

    def to_meta(self) -> dict:
        return {
            "extractor_version": MARKDOWN_VERSION,
            "kind": KIND,
            "lines": self.lines,
            "outline_entries": self.entries,
            "seconds": round(self.seconds, 2),
            "outline_source": OUTLINE_SOURCE,
        }


def extract(original: Path, vdir: Path) -> MarkdownResult:
    """Write the Outline and extract.json of a Markdown original."""
    started = time.monotonic()
    lines = read_lines(original)
    entries = outline(lines)
    result = MarkdownResult(len(lines), len(entries), time.monotonic() - started)
    atomic_write_json(vdir / OUTLINE_NAME, entries, ensure_ascii=False)
    atomic_write_json(vdir / META_NAME, result.to_meta())
    return result


def read_meta(vdir: Path) -> dict | None:
    """extract.json when it describes a Markdown extract, else None."""
    path = vdir / META_NAME
    if not path.is_file():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) and meta.get("kind") == KIND else None


def is_current(vdir: Path) -> bool:
    meta = read_meta(vdir)
    return (
        bool(meta)
        and meta.get("extractor_version") == MARKDOWN_VERSION
        and (vdir / OUTLINE_NAME).is_file()
    )


# -------------------------------------------------------------- version


@dataclass(frozen=True)
class Heading:
    level: int
    title: str
    line: int
    label: str  # the title, or its heading path when the title repeats


@dataclass(frozen=True)
class MarkdownHit:
    line: int
    text: str
    section: Heading | None


def _labelled(entries: list[dict]) -> list[Heading]:
    """Headings with labels: the title, or, when two or more headings share
    it, the titles of the enclosing headings and its own joined by ``>``."""
    counts: dict[str, int] = {}
    for e in entries:
        counts[e["title"]] = counts.get(e["title"], 0) + 1
    out: list[Heading] = []
    stack: list[dict] = []
    for e in entries:
        while stack and stack[-1]["level"] >= e["level"]:
            stack.pop()
        path = [s["title"] for s in stack] + [e["title"]]
        stack.append(e)
        label = e["title"] if counts[e["title"]] == 1 else " > ".join(path)
        out.append(Heading(e["level"], e["title"], e["line"], label))
    return out


labelled = _labelled  # the text reader labels its headings the same way


@dataclass
class MarkdownVersion:
    """One held, extracted Markdown version."""

    family: str
    document: str
    version: str
    path: Path
    origin: str
    lines: list[str]
    headings: list[Heading] = field(default_factory=list)
    # Line numbers that are never a hit or a printed line (a text version's
    # page furniture); a Markdown version hides none.
    hidden: frozenset[int] = frozenset()

    page_field: ClassVar[str] = PAGE_FIELD

    @classmethod
    def load(
        cls,
        *,
        family: str,
        document: str,
        version: str,
        path: Path,
        original: Path,
        origin: str = USER_PROVIDED,
    ) -> "MarkdownVersion":
        try:
            entries = json.loads((path / OUTLINE_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise MarkdownError(f"{path / OUTLINE_NAME}: {exc}") from exc
        return cls(
            family=family,
            document=document,
            version=version,
            path=path,
            origin=origin,
            lines=read_lines(original),
            headings=_labelled(entries),
        )

    @property
    def label(self) -> str:
        return f"{self.document} {self.version}"

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def owner(self, line: int) -> Heading | None:
        """The heading a line belongs to: the last one at or above it."""
        found = None
        for h in self.headings:
            if h.line > line:
                break
            found = h
        return found

    def end_of(self, heading: Heading) -> int:
        """The line before the next heading of the same or a higher level,
        else the last line."""
        after = False
        for h in self.headings:
            if h is heading:
                after = True
            elif after and h.level <= heading.level:
                return h.line - 1
        return self.line_count

    def match_sections(self, query: str) -> list[tuple[int, Heading, int]]:
        """(level, heading, end line) for the headings matching the query,
        as for a PDF (a section number against the title, words against the
        title). A repeated title, whose label is its heading path, also
        matches when every word is in the path and at least one is in its
        own title: ``fuses goals`` picks ``Fuses > Goals``, while ``fuses``
        alone does not list every repeated title under ``Fuses``."""
        out = []
        words = query_words(query)
        for h in self.headings:
            if query_matches(query, h.title):
                matched = True
            elif h.label != h.title and query_matches(query, h.title, h.label):
                # A word holds no whitespace, so the raw title serves.
                matched = any(w in h.title.lower() for w in words)
            else:
                matched = False
            if matched:
                out.append((h.level, h, self.end_of(h)))
        return out

    def find(
        self, pattern: str, *, regex: bool = False, case: bool = False
    ) -> Iterator[MarkdownHit]:
        flags = 0 if case else re.IGNORECASE
        rx = re.compile(pattern if regex else re.escape(pattern), flags)
        for number, text in enumerate(self.lines, start=1):
            if number not in self.hidden and rx.search(text):
                yield MarkdownHit(number, text, self.owner(number))

    def spanned(self, first: int, last: int) -> list[Heading]:
        """The heading owning ``first``, then every heading on ``first+1``
        to ``last``."""
        owner = self.owner(first)
        out = [owner] if owner else []
        out.extend(h for h in self.headings if first < h.line <= last)
        return out

    def cite(self, first: int, last: int, *, section: str | None = None) -> str:
        if section is None:
            section = "; ".join(h.label for h in self.spanned(first, last)) or "-"
        return " | ".join(
            [
                f"cite: {self.family}",
                self.label,
                section,
                self.page_field,
                f"lines {first}-{last}",
                self.origin,
                str(self.path),
            ]
        )

    def format_lines(self, first: int, last: int) -> list[str]:
        """Lines ``first`` to ``last`` behind their numbers, as ``code``
        prints a file."""
        width = len(str(last))
        return [
            f"{str(n).rjust(width)}  {self.lines[n - 1]}".rstrip()
            for n in range(first, last + 1)
            if n not in self.hidden
        ]


def load_version(holding, origin: str) -> MarkdownVersion:
    """Load a held Markdown version whose extract is current."""
    return MarkdownVersion.load(
        family=holding.family,
        document=holding.document,
        version=holding.version,
        path=holding.path,
        original=holding.original,
        origin=origin,
    )


__all__ = [
    "KIND",
    "MARKDOWN_VERSION",
    "MAX_LINES",
    "Heading",
    "MarkdownError",
    "MarkdownHit",
    "MarkdownVersion",
    "extract",
    "is_current",
    "load_version",
    "looks_like_markdown",
    "outline",
    "read_lines",
    "read_meta",
    "split_lines",
]

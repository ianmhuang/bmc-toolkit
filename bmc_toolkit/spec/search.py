"""Read what ``extract`` wrote for a held version: search it, look sections
up, hand out pages, and print Citation lines.

Standard library only. Everything here works on the files next to the
original (``extract.txt``, ``outline.json``, ``linemap.json``,
``figures.json``, ``meta.json``); nothing opens the PDF.

The ``cite:`` line is the one thing an answer may copy a Citation from. Its
fields are fixed and separated by `` | ``::

    cite: <family> | <document> <version> | <section> | PDF page <n>
          | lines <a>-<b> | <origin> | <library path>

``section`` is the Outline entry that owns the page's first line (``-`` when
the Outline is empty, ``~`` in front when the entry's page is approximate);
``lines`` are the first and last printed line numbers on the page, ``-``
without a Line Map, ``rendered page`` for an image; ``origin`` is the
recorded download URL or ``user-provided`` for a Drop-in.
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from bmc_toolkit.spec.extract import (
    EXTRACT_NAME,
    FIGURES_NAME,
    LINEMAP_NAME,
    OUTLINE_NAME,
    PAGE_MARKER,
)

USER_PROVIDED = "user-provided"
_MARKER = re.compile(r"^=== page (\d+) ===$")
_SECTION_NUMBER = re.compile(r"^(?P<num>(?:\d+|[A-Z])(?:\.\d+)*)\.?\s+\S")
_NUMBER_QUERY = re.compile(r"^(?:\d+|[A-Z])(?:\.\d+)*\.?$")


class SearchError(Exception):
    """A file the search needs is missing or unreadable."""


@dataclass(frozen=True)
class Section:
    title: str
    page: int
    approximate: bool = False

    @property
    def number(self) -> str:
        m = _SECTION_NUMBER.match(self.title)
        return m.group("num") if m else ""

    @property
    def label(self) -> str:
        return ("~" if self.approximate else "") + self.title


@dataclass(frozen=True)
class Hit:
    page: int
    index: int  # 0-based line within the page block
    text: str
    number: int | None  # printed line number, when the Line Map has one
    section: Section | None
    figure: bool


@dataclass
class Version:
    """One held, extracted version, loaded from its directory."""

    family: str
    document: str
    version: str
    path: Path
    origin: str
    pages: list[list[str]]  # pages[0] is physical page 1
    outline: list[dict]
    linemap: dict = field(default_factory=dict)  # "N" -> {"first","last","lines"}
    figures: dict = field(default_factory=dict)  # "N" -> {"regions","lines"}
    original: Path | None = None  # the PDF the Extract came from

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def label(self) -> str:
        return f"{self.document} {self.version}"

    def lines(self, page: int) -> list[str]:
        return self.pages[page - 1]

    def line_number(self, page: int, index: int) -> int | None:
        entry = self.linemap.get(str(page))
        if not entry:
            return None
        return entry.get("lines", {}).get(str(index))

    def line_range(self, page: int) -> tuple[int, int] | None:
        entry = self.linemap.get(str(page))
        if not entry:
            return None
        return entry["first"], entry["last"]

    def in_figure(self, page: int, index: int) -> bool:
        entry = self.figures.get(str(page))
        return bool(entry) and index in entry.get("lines", ())

    # ---------------------------------------------------------- sections

    def sections(self) -> list[Section]:
        return [
            Section(e["title"], e["page"], bool(e.get("approximate")))
            for e in self.outline
        ]

    def owning_section(self, page: int, index: int) -> Section | None:
        """The Outline entry a line belongs to.

        The last entry that starts on an earlier page, unless an entry
        starting on the same page has its heading at or above the line.
        """
        entries = self.sections()
        if not entries:
            return None
        before = None
        same: list[tuple[int, Section]] = []
        for e in entries:
            if e.page < page:
                before = e
            elif e.page == page:
                same.append((self._heading_index(e, page), e))
        owner = before
        for heading, e in same:
            if heading <= index:
                owner = e
        return owner

    def _heading_index(self, entry: Section, page: int) -> int:
        """Line index of the entry's heading on the page.

        A line that is the title or starts with it, else one that contains
        it, else one starting with the section number; -1 (the top of the
        page) when none is on the page. Body text that quotes a short title
        ("see Overview below") therefore does not steal the heading.
        """
        wanted = _norm(entry.title)
        if not wanted:
            return -1
        normed = [_norm(ln) for ln in self.lines(page)]
        for i, ln in enumerate(normed):  # the heading itself
            if ln == wanted or ln.startswith(wanted + " "):
                return i
        for i, ln in enumerate(normed):  # a heading with a trailing note
            if wanted in ln:
                return i
        number = entry.number
        if number:  # the bookmark's wording differs: settle for the number
            for i, ln in enumerate(normed):
                if ln.startswith(number.lower() + " "):
                    return i
        return -1

    def match_sections(self, query: str) -> list[tuple[int, Section, int]]:
        """(level, entry, end page) for the entries matching the query; the
        end page is where the next entry of the same or a higher level
        begins, or the last page.

        A query that looks like a section number (``20.1``, ``A.2``) matches
        entries whose number is it or starts with it on a dot boundary;
        anything else matches entries whose title contains every word of the
        query, case-insensitively.
        """
        q = query.strip().rstrip(".")
        numeric = bool(_NUMBER_QUERY.match(q))
        words = [w for w in _norm(q).split() if w]
        out = []
        entries = self.outline
        for i, e in enumerate(entries):
            sec = Section(e["title"], e["page"], bool(e.get("approximate")))
            if numeric:
                num = sec.number
                matched = bool(num) and (num == q or num.startswith(q + "."))
            else:
                title = _norm(sec.title)
                matched = bool(words) and all(w in title for w in words)
            if not matched:
                continue
            end = self.page_count
            for later in entries[i + 1 :]:
                if later["level"] <= e["level"]:
                    end = later["page"]
                    break
            out.append((e["level"], sec, end))
        return out

    # ------------------------------------------------------------ search

    def find(
        self, pattern: str, *, regex: bool = False, case: bool = False
    ) -> Iterator[Hit]:
        flags = 0 if case else re.IGNORECASE
        rx = re.compile(pattern if regex else re.escape(pattern), flags)
        for page_no, lines in enumerate(self.pages, start=1):
            for index, text in enumerate(lines):
                if rx.search(text):
                    yield Hit(
                        page=page_no,
                        index=index,
                        text=text,
                        number=self.line_number(page_no, index),
                        section=self.owning_section(page_no, index),
                        figure=self.in_figure(page_no, index),
                    )

    # ---------------------------------------------------------- citation

    def cite(self, page: int, lines: str | None = None) -> str:
        section = self.owning_section(page, 0)
        if lines is None:
            rng = self.line_range(page)
            lines = f"{rng[0]}-{rng[1]}" if rng else "-"
        return " | ".join(
            [
                f"cite: {self.family}",
                self.label,
                section.label if section else "-",
                f"PDF page {page}",
                f"lines {lines}",
                self.origin,
                str(self.path),
            ]
        )


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def split_pages(text: str) -> list[list[str]]:
    """The Extract's page blocks, in order; a missing or out-of-order marker
    is a SearchError."""
    pages: list[list[str]] = []
    current: list[str] | None = None
    for raw in text.split("\n"):
        m = _MARKER.match(raw)
        if m:
            if int(m.group(1)) != len(pages) + 1:
                raise SearchError(f"page markers out of order at {raw!r}")
            current = []
            pages.append(current)
        elif current is not None:
            current.append(raw)
    if not pages:
        raise SearchError("no page markers in the Extract")
    if pages[-1] and pages[-1][-1] == "":
        pages[-1].pop()  # the file's final newline
    return pages


def _read_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SearchError(f"{path}: {exc}") from exc


def load_version(holding) -> Version:
    """Load a held version's Extract and companions.

    ``holding`` is a ``library.Holding`` whose extraction is current; the
    caller checks that and turns a missing file into an exit-2 message.
    """
    vdir = holding.path
    try:
        text = (vdir / EXTRACT_NAME).read_text(encoding="utf-8")
    except OSError as exc:
        raise SearchError(f"{vdir / EXTRACT_NAME}: {exc}") from exc
    meta = holding.meta
    origin = meta.get("url") or USER_PROVIDED
    if meta.get("dropin"):
        origin = USER_PROVIDED
    return Version(
        family=holding.family,
        document=holding.document,
        version=holding.version,
        path=vdir,
        origin=origin,
        pages=split_pages(text),
        original=holding.original,
        outline=_read_json(vdir / OUTLINE_NAME, []),
        linemap=_read_json(vdir / LINEMAP_NAME, {}).get("pages", {}),
        figures=_read_json(vdir / FIGURES_NAME, {}).get("pages", {}),
    )


def page_prefix_width(version: Version, page: int) -> int:
    rng = version.line_range(page)
    return max(4, len(str(rng[1]))) if rng else 0


def format_page(version: Version, page: int) -> list[str]:
    """The page's lines, each behind its printed line number (or blanks)
    and with a ``[figure]`` mark on lines inside a figure region."""
    width = page_prefix_width(version, page)
    out = []
    for index, text in enumerate(version.lines(page)):
        number = version.line_number(page, index)
        prefix = ""
        if width:
            prefix = (str(number) if number is not None else "").rjust(width) + "  "
        mark = "  [figure]" if version.in_figure(page, index) else ""
        line = prefix + text + mark
        out.append(line.rstrip() if not text.strip() else line)
    return out


__all__ = [
    "Hit",
    "PAGE_MARKER",
    "SearchError",
    "Section",
    "Version",
    "format_page",
    "load_version",
    "split_pages",
]

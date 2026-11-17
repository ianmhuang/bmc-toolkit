"""Text documents (a catalog version of type ``txt``): the IETF plain-text
layout of an RFC, read like a Markdown version by the line numbers of the
file as stored (``original.txt``) and cited by section and lines, never by
page (ADR 0010).

Lines are counted as for Markdown (``markdown.split_lines``); a form-feed
line is a line. An RFC printed in pages carries page furniture between two
pages: the footer ending in ``[Page N]``, the form-feed line, the running
header starting ``RFC <number> `` and the blank lines padding them (between
the last text line and the footer, between the header and the next text
line). A form feed may share its line with the header; in a file that has
a page break, a footer ending the file with no form feed after it is
furniture too. Furniture keeps its line numbers but is never a heading, a
``find`` hit or a printed line.

The Outline holds the lines that start in column 0 and are not furniture:

- numbered headings, ``4.1.2.  Title``, ``1.1 Title``, ``1.1. Title``,
  ``Appendix A.  Title``, ``A.1.  Title`` (one or two spaces after the
  number; the number holds a dot or follows ``Appendix``); level is the
  number of parts minus one; anywhere in the file;
- unnumbered headings, a column-0 line with a blank or furniture line (or
  the file's edge) on both sides and an indented line as the next text
  (or none), after the file's first block (the author and stream block):
  ``Abstract``, ``Status of This Memo``, level 0. The indented next line
  keeps column-0 code, such as a MIB module, out of the Outline.

A numbered heading followed directly by an indented non-blank line is
wrapped: the title joins both lines. A heading's title is its number without
the trailing dot, a space and the text with runs of spaces collapsed
(``4.1.2 Client Hello``, ``Appendix A State Machine``); ``section DOC A``
finds that appendix as ``section DOC 4`` finds section 4.

Files written next to the original are those of a Markdown version, with
``"kind": "text"`` and this module's extractor version in ``extract.json``.
The ``cite:`` line has ``Text`` in the page position.

Standard library only.
"""

import dataclasses
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from bmc_toolkit.spec import markdown as md_mod
from bmc_toolkit.spec.library import atomic_write_json
from bmc_toolkit.spec.markdown import Heading, MarkdownVersion

TEXT_VERSION = 1
KIND = "text"
META_NAME = md_mod.META_NAME
OUTLINE_NAME = md_mod.OUTLINE_NAME
OUTLINE_SOURCE = md_mod.OUTLINE_SOURCE
MAX_LINES = md_mod.MAX_LINES
PAGE_FIELD = "Text"

_FOOTER = re.compile(r"\[Page \d+\]\s*$")
_HEADER = re.compile(r"^RFC \d+ ")
_NUMBERED = re.compile(
    r"^(?P<appendix>Appendix )?"
    r"(?P<number>(?:\d+|[A-Z])(?:\.\d+)*)(?P<dot>\.?)"
    r" {1,2}(?P<title>\S.*?)\s*$"
)
_SPACES = re.compile(r"\s+")


# The body check is the Markdown one (``library.body_matches_type``), and
# lines are read as Markdown reads them.
read_lines = md_mod.read_lines


def _blank(text: str) -> bool:
    return not text.strip()


def _break(text: str) -> str | None:
    """``"alone"`` for a page-break line (form feeds and blanks only),
    ``"header"`` for a form feed sharing its line with the running header,
    else None."""
    if "\f" in text and not text.replace("\f", "").strip():
        return "alone"
    if text.startswith("\f") and _HEADER.match(text.lstrip("\f")):
        return "header"
    return None


def furniture(lines: list[str]) -> frozenset[int]:
    """The line numbers (1-based) of the page furniture."""
    hidden: set[int] = set()
    count = len(lines)

    def hide_blanks(index: int, step: int) -> None:
        while 0 <= index < count and _blank(lines[index]) and index + 1 not in hidden:
            hidden.add(index + 1)
            index += step

    for index, text in enumerate(lines):
        kind = _break(text)
        if kind is None:
            continue
        hidden.add(index + 1)
        before = index - 1
        if before >= 0 and _FOOTER.search(lines[before]):
            hidden.add(before + 1)
            before -= 1
        hide_blanks(before, -1)
        after = index + 1
        if kind == "alone" and after < count and _HEADER.match(lines[after]):
            hidden.add(after + 1)
            after += 1
        hide_blanks(after, 1)
    if hidden:
        # The last page's footer, when no form feed follows it.
        last = count - 1
        while last >= 0 and _blank(lines[last]):
            last -= 1
        if last >= 0 and last + 1 not in hidden and _FOOTER.search(lines[last]):
            hidden.add(last + 1)
            hide_blanks(last - 1, -1)
            hide_blanks(last + 1, 1)
    return frozenset(hidden)


def _first_block_end(lines: list[str]) -> int:
    """The 0-based index of the first line after the file's first block of
    non-blank lines (the author and stream block)."""
    index = 0
    while index < len(lines) and _blank(lines[index]):
        index += 1
    while index < len(lines) and not _blank(lines[index]):
        index += 1
    return index


def _numbered(text: str) -> tuple[int, str] | None:
    """(level, title) of a numbered heading line, else None."""
    m = _NUMBERED.match(text)
    if not m:
        return None
    number, appendix = m.group("number"), bool(m.group("appendix"))
    if not appendix and "." not in number and not m.group("dot"):
        return None  # "1 Introduction" or a capital letter starting a sentence
    parts = number.split(".")
    title = _SPACES.sub(" ", m.group("title"))
    prefix = f"Appendix {number}" if appendix else number
    return len(parts) - 1, f"{prefix} {title}"


def outline(lines: list[str], hidden: frozenset[int] | None = None) -> list[dict]:
    """The headings of an IETF text, in order."""
    if hidden is None:
        hidden = furniture(lines)
    count = len(lines)

    def gap(index: int) -> bool:
        """Blank, furniture or outside the file."""
        return (
            index < 0 or index >= count or index + 1 in hidden or _blank(lines[index])
        )

    def indented_next(index: int) -> bool:
        """The next line that is not a gap is indented, or there is none:
        body text follows a heading, while a column-0 line of a MIB module
        or other code is followed by more column-0 code."""
        index += 1
        while index < count and gap(index):
            index += 1
        return index >= count or lines[index][:1] in (" ", "\t")

    out: list[dict] = []
    start = _first_block_end(lines)  # unnumbered headings come after it
    for index in range(count):
        text = lines[index]
        if index + 1 in hidden or _blank(text) or text[0] in " \t\f":
            continue
        found = _numbered(text)
        if found is not None:
            level, title = found
            nxt = index + 1
            if (
                nxt < count
                and nxt + 1 not in hidden
                and lines[nxt][:1] in (" ", "\t")
                and not _blank(lines[nxt])
            ):
                title = f"{title} {_SPACES.sub(' ', lines[nxt].strip())}"
            out.append({"level": level, "title": title, "line": index + 1})
        elif (
            index >= start
            and gap(index - 1)
            and gap(index + 1)
            and indented_next(index)
        ):
            title = _SPACES.sub(" ", text.strip())
            out.append({"level": 0, "title": title, "line": index + 1})
    return out


# ------------------------------------------------------------- extract


@dataclass
class TextResult:
    lines: int
    entries: int
    seconds: float

    def to_meta(self) -> dict:
        return {
            "extractor_version": TEXT_VERSION,
            "kind": KIND,
            "lines": self.lines,
            "outline_entries": self.entries,
            "seconds": round(self.seconds, 2),
            "outline_source": OUTLINE_SOURCE,
        }


def extract(original: Path, vdir: Path) -> TextResult:
    """Write the Outline and extract.json of a text original."""
    started = time.monotonic()
    lines = read_lines(original)
    entries = outline(lines)
    result = TextResult(len(lines), len(entries), time.monotonic() - started)
    atomic_write_json(vdir / OUTLINE_NAME, entries, ensure_ascii=False)
    atomic_write_json(vdir / META_NAME, result.to_meta())
    return result


def read_meta(vdir: Path) -> dict | None:
    """extract.json when it describes a text extract, else None."""
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
        and meta.get("extractor_version") == TEXT_VERSION
        and (vdir / OUTLINE_NAME).is_file()
    )


# -------------------------------------------------------------- version


@dataclass
class TextVersion(MarkdownVersion):
    """One held, extracted text version: a Markdown version whose page
    furniture is hidden and whose Citation says ``Text``."""

    page_field: ClassVar[str] = PAGE_FIELD

    @classmethod
    def load(cls, **kwargs) -> "TextVersion":
        """As ``MarkdownVersion.load``, with the furniture hidden."""
        version = super().load(**kwargs)
        return dataclasses.replace(version, hidden=furniture(version.lines))

    def match_sections(self, query: str) -> list[tuple[int, Heading, int]]:
        """As for Markdown, and a bare appendix letter (``A`` or ``A.``)
        also matches the ``Appendix A`` heading itself, as ``4`` matches
        ``4 Title``."""
        out = super().match_sections(query)
        m = re.fullmatch(r"\s*([A-Z])\.?\s*", query)
        if m:
            prefix = f"Appendix {m.group(1)} "
            found = {id(h) for _, h, _ in out}
            extra = [
                (h.level, h, self.end_of(h))
                for h in self.headings
                if h.title.startswith(prefix) and id(h) not in found
            ]
            out = sorted(out + extra, key=lambda match: match[1].line)
        return out


def load_version(holding, origin: str) -> TextVersion:
    """Load a held text version whose extract is current."""
    return TextVersion.load(
        family=holding.family,
        document=holding.document,
        version=holding.version,
        path=holding.path,
        original=holding.original,
        origin=origin,
    )


__all__ = [
    "KIND",
    "MAX_LINES",
    "TEXT_VERSION",
    "TextVersion",
    "extract",
    "furniture",
    "is_current",
    "load_version",
    "outline",
    "read_lines",
    "read_meta",
]

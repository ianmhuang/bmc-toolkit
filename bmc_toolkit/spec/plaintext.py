"""Text documents (a catalog version of type ``txt``): the IETF plain-text
layout of an RFC, read like a Markdown version by the line numbers of the
file as stored (``original.txt``) and cited by section and lines, never by
page (ADR 0010).

Lines are counted as for Markdown (``markdown.split_lines``); a form-feed
line is a line. An RFC printed in pages carries page furniture between two
pages: the footer ending in ``[Page N]``, the form-feed line, the running
header starting ``RFC <number> `` and the blank lines padding them (between
the last text line and the footer, between the header and the next text
line). Furniture keeps its line numbers but is never a heading, a ``find``
hit or a printed line.

The Outline holds the lines that start in column 0 and are not furniture:

- numbered headings, ``4.1.2.  Title``, ``1.1 Title``, ``1.1. Title``,
  ``Appendix A.  Title``, ``A.1.  Title`` (one or two spaces after the
  number; the number holds a dot or follows ``Appendix``); level is the
  number of parts minus one;
- unnumbered headings, a column-0 line with a blank or furniture line (or
  the file's edge) on both sides and an indented line as the next text
  (or none), after the file's first block (the author and stream block):
  ``Abstract``, ``Status of This Memo``, level 0. The indented next line
  keeps column-0 code, such as a MIB module, out of the Outline.

A numbered heading followed directly by an indented non-blank line is
wrapped: the title joins both lines. A heading's title is its number without
the trailing dot, a space and the text with runs of spaces collapsed
(``4.1.2 Client Hello``, ``Appendix A State Machine``).

Files written next to the original are those of a Markdown version, with
``"kind": "text"`` and this module's extractor version in ``extract.json``.
The ``cite:`` line has ``Text`` in the page position.

Standard library only.
"""

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from bmc_toolkit.spec import markdown as md_mod
from bmc_toolkit.spec.library import atomic_write_json
from bmc_toolkit.spec.markdown import MarkdownError, MarkdownVersion, split_lines
from bmc_toolkit.spec.search import USER_PROVIDED

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


class TextError(MarkdownError):
    """A text version cannot be read; the message says why."""


# ------------------------------------------------------------ the check


def looks_like_text(data: bytes) -> bool:
    """UTF-8 text (a BOM allowed) that is not an HTML page, as for Markdown."""
    return md_mod.looks_like_markdown(data)


# ------------------------------------------------------------- reading


def read_lines(path: Path) -> list[str]:
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError as exc:
        raise TextError(f"{path}: {exc}") from exc
    return split_lines(text)


def _blank(text: str) -> bool:
    return not text.strip()


def _is_break(text: str) -> bool:
    return "\f" in text and not text.replace("\f", "").strip()


def furniture(lines: list[str]) -> frozenset[int]:
    """The line numbers (1-based) of the page furniture."""
    hidden: set[int] = set()
    count = len(lines)
    for index, text in enumerate(lines):
        if not _is_break(text):
            continue
        hidden.add(index + 1)
        before = index - 1
        if before >= 0 and _FOOTER.search(lines[before]):
            hidden.add(before + 1)
            before -= 1
        while before >= 0 and _blank(lines[before]) and before + 1 not in hidden:
            hidden.add(before + 1)
            before -= 1
        after = index + 1
        if after < count and _HEADER.match(lines[after]):
            hidden.add(after + 1)
            after += 1
        while after < count and _blank(lines[after]):
            hidden.add(after + 1)
            after += 1
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
    start = _first_block_end(lines)
    for index in range(start, count):
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
        elif gap(index - 1) and gap(index + 1) and indented_next(index):
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
    def load(
        cls,
        *,
        family: str,
        document: str,
        version: str,
        path: Path,
        original: Path,
        origin: str = USER_PROVIDED,
    ) -> "TextVersion":
        try:
            entries = json.loads((path / OUTLINE_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TextError(f"{path / OUTLINE_NAME}: {exc}") from exc
        lines = read_lines(original)
        return cls(
            family=family,
            document=document,
            version=version,
            path=path,
            origin=origin,
            lines=lines,
            headings=md_mod.labelled(entries),
            hidden=furniture(lines),
        )


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
    "TextError",
    "TextVersion",
    "extract",
    "furniture",
    "is_current",
    "load_version",
    "looks_like_text",
    "outline",
    "read_lines",
    "read_meta",
]

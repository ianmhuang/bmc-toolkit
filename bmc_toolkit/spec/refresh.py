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
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from bmc_toolkit.spec.catalog import (
    CatalogError,
    Document,
    load_catalog,
    version_numbers,
)
from bmc_toolkit.spec.listing import ListingError, Listings, Seen, version_key

_BLOCK_START = re.compile(r"^\[\[(documents|repos)\]\]\s*$")
_SECTION_COMMENT = re.compile(r"^# -{10,}")


class RefreshError(Exception):
    """The catalog text could not be edited; the message says why."""


@dataclass(frozen=True)
class Proposal:
    """One thing the publisher's listing says about a document."""

    kind: str  # add | confirm | changed | unreachable
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
    """What the listing adds to the catalog entry of one document."""
    try:
        seen = listings.history(doc.listing)
    except ListingError as exc:
        return [Proposal("unreachable", doc.id, problem=str(exc))]
    source = doc.listing_source
    by_key = {version_key(source, v.version): v for v in doc.versions}
    out = []
    for s in seen:
        known = by_key.get(version_key(source, s.version))
        if known is None:
            if source != "ocp" and _file_type(s.url) and not _is_wip(s):
                out.append(Proposal("add", doc.id, s))
            else:
                out.append(Proposal("confirm", doc.id, s, why=_why_confirm(source, s)))
        elif source != "ocp" and known.url and s.url and known.url != s.url:
            out.append(Proposal("changed", doc.id, s))
    return out


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
    ``[[documents]]`` line to the line before the next block, the next
    section comment, or the end of the file."""
    id_re = re.compile(rf'^id\s*=\s*"{re.escape(doc_id)}"\s*$', re.IGNORECASE)
    start = None
    for i, line in enumerate(lines):
        if _BLOCK_START.match(line):  # a repos block never holds a document
            start = i if line.startswith("[[documents]]") else None
        elif id_re.match(line) and start is not None:
            for j in range(i + 1, len(lines)):
                if _BLOCK_START.match(lines[j]) or _SECTION_COMMENT.match(lines[j]):
                    return start, j
            return start, len(lines)
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
    "Proposal",
    "RefreshError",
    "UnreadableBlock",
    "append_versions",
    "proposals",
    "version_block",
]

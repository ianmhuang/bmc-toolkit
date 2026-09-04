"""Bringing the Source Catalog up to date from the publishers' listings.

A maintainer's tool. For every document with a listing it reports the
versions the publisher lists that the catalog lacks and, with ``--write``,
appends each as a ``[[documents.versions]]`` block at the end of the
document's block in the catalog file. The file is edited as text so the
maintainer comments survive; the result is re-parsed before it is kept.
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


def append_versions(path: Path, doc_id: str, seen: list[Seen]) -> None:
    """Add version blocks at the end of the document's block, newest last
    (same-day versions ascending by their numbers, the order the catalog
    keeps), and re-parse the file; on a parse failure the file is restored."""
    if not seen:
        return
    with open(path, encoding="utf-8", newline="") as fh:  # read_text(newline=) is 3.13+
        original = fh.read()
    lines = original.split("\n")
    _, end = _document_span(lines, doc_id)
    while end > 0 and lines[end - 1].strip() == "":
        end -= 1
    ordered = sorted(seen, key=lambda s: (s.published, version_numbers(s.version)))
    blocks = [version_block(s) for s in ordered]
    insert = "\n" + "\n".join(blocks)  # a blank line, then the blocks
    rest = "\n".join(lines[end:])  # starts with the blank line(s) that were there
    text = "\n".join(lines[:end]) + "\n" + insert + rest
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
    "append_versions",
    "proposals",
    "version_block",
]

"""The Support Level table: what a user is told about every document.

Generated from the Source Catalog, never written by hand: family, document,
Access Tier (with the latest version's tier when it differs), latest
version, how it is fetched, whether it is Verified, and its Known Limits.
Verified comes from the Golden Questions file: a Markdown table whose
header has a ``Document`` column naming ``<catalog id> <version>`` per
question; the cell lists the question ids per version they were checked
on, ``G1, G3 (1.3.3); G2 (1.3.2)``. Standard library only.
"""

import re
from pathlib import Path

from bmc_toolkit.spec.catalog import Catalog, Document

COLUMNS = (
    "Family",
    "Document",
    "Access",
    "Latest",
    "Fetch",
    "Verified",
    "Known limit",
)

BY_FAMILY_COLUMNS = ("Document", "Access", "Latest", "Verified", "Known limit")

_QUESTION_RE = re.compile(r"^G\d+$")
_RULE_RE = re.compile(r"^\|?\s*:?-{3,}")


def _cells(line: str) -> list[str]:
    """The cells of a Markdown table row, stripped; ``\\|`` stays escaped."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    parts = re.split(r"(?<!\\)\|", body)
    return [p.strip() for p in parts]


Verified = dict[str, list[tuple[str, str]]]


def read_golden(path: Path, catalog: Catalog) -> tuple[Verified, list[str]]:
    """(verified, problems): per catalog document id (lower-cased) named in
    a ``Document`` column, the (question id, version) pairs in file order,
    the version being the cell text after the id ("" when there is none);
    and the cells that name a document the catalog does not know."""
    text = path.read_text(encoding="utf-8")
    verified: Verified = {}
    problems: list[str] = []
    column: int | None = None
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            column = None
            continue
        cells = _cells(line)
        if _RULE_RE.match(line.strip()):
            continue
        lowered = [c.lower() for c in cells]
        if "document" in lowered and not _QUESTION_RE.match(cells[0]):
            column = lowered.index("document")
            continue
        if column is None or column >= len(cells):
            continue
        if not _QUESTION_RE.match(cells[0]):
            continue
        for entry in cells[column].split(";"):
            entry = entry.strip()
            if not entry or entry == "-":
                continue
            doc_id, *rest = entry.split(None, 1)  # any whitespace, once
            version = rest[0] if rest else ""
            doc = catalog.get(doc_id)
            if doc is None:
                problems.append(f"{cells[0]}: unknown document '{doc_id}'")
                continue
            pairs = verified.setdefault(doc.id.lower(), [])
            if cells[0] not in (q for q, _ in pairs):
                pairs.append((cells[0], version.strip()))
    return verified, problems


def verified_label(pairs: list[tuple[str, str]]) -> str:
    """The Verified cell: question ids grouped by the version they were
    checked on, in order of first appearance; ``-`` when there are none."""
    groups: dict[str, list[str]] = {}
    for qid, version in pairs:
        groups.setdefault(version, []).append(qid)
    parts = []
    for version, ids in groups.items():
        text = ", ".join(ids)
        parts.append(f"{text} ({version})" if version else text)
    return "; ".join(parts) if parts else "-"


def _escape(cell: str) -> str:
    return cell.replace("|", "\\|") if cell else "-"


def access_label(doc: Document) -> str:
    """The document's tier, and the latest version's when it differs."""
    latest = doc.latest()
    if latest is not None and latest.access != doc.access:
        return f"{doc.access} (latest {latest.access})"
    return doc.access


def fetch_label(doc: Document) -> str:
    return "manual (Drop-in)" if doc.fetch == "manual" else doc.fetch


def _document_cells(doc: Document, verified: Verified) -> list[str]:
    """The document's cells without the Family column (COLUMNS[1:])."""
    latest = doc.latest()
    return [
        f"`{doc.id}` {doc.title}",
        access_label(doc),
        latest.version if latest else "-",
        fetch_label(doc),
        verified_label(verified.get(doc.id.lower(), [])),
        doc.limits or "-",
    ]


def support_rows(catalog: Catalog, verified: Verified) -> list[list[str]]:
    """One row per document, in catalog order."""
    return [
        [catalog.families[doc.family].title, *_document_cells(doc, verified)]
        for doc in catalog.documents
    ]


def _table_lines(columns: tuple[str, ...], rows: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "---|" * len(columns),
    ]
    for row in rows:
        lines.append("| " + " | ".join(_escape(c) for c in row) + " |")
    return lines


def support_table(catalog: Catalog, verified: Verified) -> list[str]:
    """The Markdown lines of the Support Level table, one flat table."""
    return _table_lines(COLUMNS, support_rows(catalog, verified))


def _family_cells(doc: Document, verified: Verified) -> list[str]:
    """The document's cells of the per-family table (BY_FAMILY_COLUMNS):
    no Fetch, and Verified reduced to ``PASS`` or ``-``."""
    document, access, latest, _fetch, label, limit = _document_cells(doc, verified)
    return [document, access, latest, "-" if label == "-" else "PASS", limit]


def support_by_family(catalog: Catalog, verified: Verified) -> list[str]:
    """The reader's form of the table, split per family: a ``##`` heading
    with the family title, then its documents with BY_FAMILY_COLUMNS.
    Families come in catalog order, documents in catalog order within their
    family, so a document whose catalog block sits apart from its family
    still lands under the family's heading. Documents marked ``unlisted``
    are left out, and so is a family with nothing left to list."""
    grouped: dict[str, list[list[str]]] = {}
    for doc in catalog.documents:
        if doc.unlisted:
            continue
        grouped.setdefault(doc.family, []).append(_family_cells(doc, verified))
    lines: list[str] = []
    for family in catalog.families.values():
        rows = grouped.get(family.id)
        if not rows:
            continue
        if lines:
            lines.append("")
        lines.append(f"## {family.title}")
        lines.append("")
        lines.extend(_table_lines(BY_FAMILY_COLUMNS, rows))
    return lines


__all__ = [
    "BY_FAMILY_COLUMNS",
    "COLUMNS",
    "Verified",
    "access_label",
    "fetch_label",
    "read_golden",
    "support_by_family",
    "support_rows",
    "support_table",
    "verified_label",
]

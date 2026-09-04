"""The Support Level table: what a user is told about every document.

Generated from the Source Catalog, never written by hand: family, document,
Access Tier (with the latest version's tier when it differs), latest
version, how it is fetched, whether it is Verified, and its Known Limits.
Verified comes from the Golden Questions file: a Markdown table whose
header has a ``Document`` column naming ``<catalog id> <version>`` per
question. Standard library only.
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


def read_golden(path: Path, catalog: Catalog) -> tuple[dict[str, list[str]], list[str]]:
    """(verified, problems): the question ids per catalog document id
    (lower-cased) named in a ``Document`` column, and the cells that name
    a document the catalog does not know."""
    text = path.read_text(encoding="utf-8")
    verified: dict[str, list[str]] = {}
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
            doc_id = entry.split()[0]
            doc = catalog.get(doc_id)
            if doc is None:
                problems.append(f"{cells[0]}: unknown document '{doc_id}'")
                continue
            ids = verified.setdefault(doc.id.lower(), [])
            if cells[0] not in ids:
                ids.append(cells[0])
    return verified, problems


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


def support_rows(catalog: Catalog, verified: dict[str, list[str]]) -> list[list[str]]:
    rows = []
    for doc in catalog.documents:
        latest = doc.latest()
        questions = verified.get(doc.id.lower(), [])
        rows.append(
            [
                catalog.families[doc.family].title,
                f"`{doc.id}` {doc.title}",
                access_label(doc),
                latest.version if latest else "-",
                fetch_label(doc),
                ", ".join(questions) if questions else "-",
                doc.limits or "-",
            ]
        )
    return rows


def support_table(catalog: Catalog, verified: dict[str, list[str]]) -> list[str]:
    """The Markdown lines of the Support Level table."""
    lines = [
        "| " + " | ".join(COLUMNS) + " |",
        "|" + "---|" * len(COLUMNS),
    ]
    for row in support_rows(catalog, verified):
        lines.append("| " + " | ".join(_escape(c) for c in row) + " |")
    return lines


__all__ = [
    "COLUMNS",
    "access_label",
    "fetch_label",
    "read_golden",
    "support_rows",
    "support_table",
]

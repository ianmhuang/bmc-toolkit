"""Freshness Check: is the Source Catalog behind the publisher?

``check`` compares what a publisher lists now (``listing``) with the
catalog, reports a newer Version and records the outcome in
``freshness.json`` at the Library root. Nothing is downloaded and no
version is switched: the catalog stays the authority for "latest" until a
maintainer updates it. Commands that serve a document print a note when
its last check is older than ``freshness_days`` (``[library]`` in
``config.toml``, default 30); the note is printed once (``reminded_at``)
and not again until the next check, and it never touches the network.

``freshness.json``::

    {"documents": {"DSP0236": {"checked_at": ISO 8601 UTC,
                               "catalog_latest": "1.3.3",
                               "newer": [{"version": ..., "url": ...,
                                          "published": ..., "note": ...}],
                               "problem": "",
                               "reminded_at": ISO 8601 UTC (once noted)}},
     "release": {"checked_at": ..., "configured": "2.18.0",
                 "newest": "3.0.0", "problem": ""}}

The OpenBMC part: the newest ``X.Y.Z`` tag of the catalog's ``openbmc``
repository (``git ls-remote``) against the release ``config.toml`` pins.
"""

import json
import re
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.catalog import Catalog, Document
from bmc_toolkit.spec.library import now_iso
from bmc_toolkit.spec.listing import (
    PUBLISHER_NAMES,
    ListingError,
    Listings,
    Seen,
    version_key,
)

FRESHNESS_NAME = "freshness.json"
DEFAULT_MAX_AGE_DAYS = 30
_RELEASE_TAG = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class FreshnessError(Exception):
    """config.toml or freshness.json cannot be used; the message says why."""


def max_age_days(root: Path) -> int:
    """``[library] freshness_days`` of config.toml, or the default."""
    path = root / code_mod.CONFIG_NAME
    if not path.is_file():
        return DEFAULT_MAX_AGE_DAYS
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise FreshnessError(f"{path}: {exc}") from exc
    section = data.get("library", {})
    if not isinstance(section, dict):
        raise FreshnessError(f"{path}: [library] must be a table")
    days = section.get("freshness_days", DEFAULT_MAX_AGE_DAYS)
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise FreshnessError(
            f"{path}: library.freshness_days must be a positive integer"
        )
    return days


@dataclass
class Check:
    """The outcome of checking one document against its publisher."""

    document: str
    catalog_latest: str
    checked_at: str
    newer: list[Seen] = field(default_factory=list)
    problem: str = ""  # "" when the listing was read

    @property
    def status(self) -> str:
        if self.problem:
            return "unreachable"
        return "newer" if self.newer else "current"

    def to_dict(self) -> dict:
        return {
            "checked_at": self.checked_at,
            "catalog_latest": self.catalog_latest,
            "newer": [
                {
                    "version": s.version,
                    "url": s.url,
                    "published": s.published,
                    "note": s.note,
                }
                for s in self.newer
            ],
            "problem": self.problem,
        }


def compare(doc: Document, seen: list[Seen], checked_at: str | None = None) -> Check:
    """Which of the listed versions the catalog lacks."""
    known = {version_key(doc.listing_source, v.version) for v in doc.versions}
    latest = doc.latest()
    newer = [s for s in seen if version_key(doc.listing_source, s.version) not in known]
    return Check(
        doc.id, latest.version if latest else "-", checked_at or now_iso(), newer
    )


def check_document(doc: Document, listings: Listings) -> Check:
    """Fetch the document's listing and compare; a failure becomes the
    Check's ``problem`` rather than an exception."""
    now = now_iso()
    try:
        seen = listings.current(doc.listing)
    except ListingError as exc:
        latest = doc.latest()
        return Check(doc.id, latest.version if latest else "-", now, problem=str(exc))
    return compare(doc, seen, now)


def publisher_name(doc: Document) -> str:
    return PUBLISHER_NAMES.get(doc.listing_source, "its publisher")


# ---------------------------------------------------------- releases


def newest_release_tag(url: str) -> str | None:
    """The highest ``X.Y.Z`` tag the repository has (``-dev`` and other
    suffixes are not releases); None when it has none."""
    proc = code_mod.run_git(["ls-remote", "--tags", "--refs", url])
    best: tuple[tuple[int, int, int], str] | None = None
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2 or not parts[1].startswith("refs/tags/"):
            continue
        tag = parts[1].removeprefix("refs/tags/")
        m = _RELEASE_TAG.match(tag)
        if not m:
            continue
        key = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if best is None or key > best[0]:
            best = (key, tag)
    return best[1] if best else None


def release_is_newer(configured: str, newest: str) -> bool | None:
    """True when ``newest`` is a higher X.Y.Z than the configured release;
    None when the configured release is not a version number (a branch)."""
    a = _RELEASE_TAG.match(configured.strip())
    b = _RELEASE_TAG.match(newest.strip())
    if not a or not b:
        return None
    return tuple(map(int, b.groups())) > tuple(map(int, a.groups()))


# ---------------------------------------------------------------- state


class Freshness:
    """The record of past checks at the Library root."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / FRESHNESS_NAME
        self._data: dict | None = None

    @property
    def data(self) -> dict:
        if self._data is None:
            self._data = {"documents": {}, "release": {}}
            if self.path.is_file():
                try:
                    loaded = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    loaded = None
                if isinstance(loaded, dict):
                    docs = loaded.get("documents")
                    if isinstance(docs, dict):
                        self._data["documents"] = docs
                    rel = loaded.get("release")
                    if isinstance(rel, dict):
                        self._data["release"] = rel
        return self._data

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8", newline="") as fh:
            json.dump(self.data, fh, indent=4, sort_keys=True)
            fh.write("\n")

    def record(self, check: Check) -> None:
        # a fresh record: any earlier reminder is spent
        self.data["documents"][check.document.upper()] = check.to_dict()

    def reminded(self, doc_id: str) -> bool:
        """True when the note was printed since the last check."""
        entry = self.data["documents"].get(doc_id.upper())
        return isinstance(entry, dict) and bool(entry.get("reminded_at"))

    def mark_reminded(self, doc_ids, now: str | None = None) -> None:
        stamp = now or now_iso()
        for doc_id in doc_ids:
            entry = self.data["documents"].setdefault(doc_id.upper(), {})
            if isinstance(entry, dict):
                entry["reminded_at"] = stamp

    def record_release(self, configured: str, newest: str | None, problem: str) -> None:
        self.data["release"] = {
            "checked_at": now_iso(),
            "configured": configured,
            "newest": newest or "",
            "problem": problem,
        }

    def checked_at(self, doc_id: str) -> datetime | None:
        entry = self.data["documents"].get(doc_id.upper())
        if not isinstance(entry, dict):
            return None
        try:
            return datetime.fromisoformat(str(entry.get("checked_at", "")))
        except ValueError:
            return None

    def age_days(self, doc_id: str, now: datetime | None = None) -> int | None:
        """Days since the document was last checked; None when never."""
        when = self.checked_at(doc_id)
        if when is None:
            return None
        now = now or datetime.now(UTC)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return max(0, (now - when).days)

    def stale(self, doc_id: str, max_age: int, now: datetime | None = None) -> bool:
        age = self.age_days(doc_id, now)
        return age is None or age >= max_age

    def stale_documents(
        self, catalog: Catalog, doc_ids, max_age: int, now: datetime | None = None
    ) -> list[Document]:
        """The catalog documents among ``doc_ids`` that have a listing and
        no recent check, in catalog order."""
        wanted = {d.upper() for d in doc_ids}
        return [
            doc
            for doc in catalog.documents
            if doc.id.upper() in wanted
            and doc.listing
            and self.stale(doc.id, max_age, now)
        ]

    def due_documents(
        self, catalog: Catalog, doc_ids, max_age: int, now: datetime | None = None
    ) -> list[Document]:
        """The stale documents whose note has not been printed yet."""
        return [
            doc
            for doc in self.stale_documents(catalog, doc_ids, max_age, now)
            if not self.reminded(doc.id)
        ]

    def note_for(self, doc: Document, max_age: int, now: datetime | None = None) -> str:
        """The one-line reminder for a stale document, "" when fresh."""
        if not doc.listing or not self.stale(doc.id, max_age, now):
            return ""
        age = self.age_days(doc.id, now)
        if age is None:
            what = f"has never been checked against {publisher_name(doc)}"
        else:
            what = f"has not been checked against {publisher_name(doc)} for {age} days"
        return f"note: {doc.id} {what}; run: bmcspec check {doc.id}"


__all__ = [
    "DEFAULT_MAX_AGE_DAYS",
    "FRESHNESS_NAME",
    "Check",
    "Freshness",
    "FreshnessError",
    "check_document",
    "compare",
    "max_age_days",
    "newest_release_tag",
    "publisher_name",
    "release_is_newer",
]

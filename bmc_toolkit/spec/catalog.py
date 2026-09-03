"""The Source Catalog: which documents exist, their versions, where to get them.

The catalog is a TOML file (``catalog.toml`` next to this module) read with
the standard library. This module validates it into plain dataclasses and
answers "which version is latest" and "do we know this version".

Schema (``schema_version = 1``)::

    [families.<id>]            one table per family
    title = "..."
    publisher = "..."

    [[documents]]              one entry per document
    id = "DSP0236"             unique, matched case-insensitively
    family = "mctp"            must name a family above
    title = "..."
    access = "open"            open | gated | member | confidential
    fetch = "direct"           direct | wayback | manual
    notes = "..."              optional, free text
    searched_with = ["ID"]     optional: documents searched together with
                               this one (errata, spec updates); their hits
                               are reported first

    [[documents.versions]]     newest last or in any order; dates decide
    version = "1.3.3"          the publisher's own string, verbatim
    url = "https://..."        may be "" when fetch = "manual"
    type = "pdf"               pdf | zip
    published = "2024-03-25"   ISO date
    wip = false                optional, default false
    notes = "..."              optional

    [[repos]]                  one entry per code repository (Code Trees)
    id = "bmcweb"              unique, matched case-insensitively; also the
                               directory name under the Library's code/
    url = "https://github.com/openbmc/bmcweb.git"
                               https://; file:// for a local mirror (and tests)
    topics = ["redfish"]       what the repository is about, for `repos --topic`
    sparse = ["meta-phosphor"] optional: only these directories are checked
                               out, or with globs ("/meta-*/**/*.bb") only the
                               matching files
"""

import datetime
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ACCESS_TIERS = ("open", "gated", "member", "confidential")
FETCH_METHODS = ("direct", "wayback", "manual")
FILE_TYPES = ("pdf", "zip")
SCHEMA_VERSION = 1
DEFAULT_CATALOG = Path(__file__).with_name("catalog.toml")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CatalogError(Exception):
    """The catalog file is malformed; the message names the offending key."""


@dataclass(frozen=True)
class Family:
    id: str
    title: str
    publisher: str


@dataclass(frozen=True)
class Version:
    version: str
    url: str
    type: str
    published: str
    wip: bool = False
    notes: str = ""


@dataclass(frozen=True)
class Document:
    id: str
    family: str
    title: str
    access: str
    fetch: str
    versions: tuple[Version, ...]
    notes: str = ""
    searched_with: tuple[str, ...] = ()

    def latest(self, include_wip: bool = False) -> Version | None:
        """Newest version by publication date; WIP only when asked.

        Ties on the date keep catalog order, later entry wins.
        """
        candidates = [v for v in self.versions if include_wip or not v.wip]
        if not candidates:
            return None
        best = candidates[0]
        for v in candidates[1:]:
            if v.published >= best.published:
                best = v
        return best

    def find_version(self, version: str) -> Version | None:
        for v in self.versions:
            if v.version == version:
                return v
        return None


@dataclass(frozen=True)
class Repo:
    id: str
    url: str
    topics: tuple[str, ...]
    sparse: tuple[str, ...] = ()


@dataclass
class Catalog:
    families: dict[str, Family]
    documents: list[Document]
    repos: list[Repo] = field(default_factory=list)
    _index: dict[str, Document] = field(default_factory=dict, repr=False)
    _repo_index: dict[str, Repo] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._index = {d.id.lower(): d for d in self.documents}
        self._repo_index = {r.id.lower(): r for r in self.repos}

    def get(self, doc_id: str) -> Document | None:
        return self._index.get(doc_id.strip().lower())

    def by_family(self, family_id: str) -> list[Document]:
        return [d for d in self.documents if d.family == family_id]

    def get_repo(self, repo_id: str) -> Repo | None:
        return self._repo_index.get(repo_id.strip().lower())

    def by_topic(self, topic: str) -> list[Repo]:
        wanted = topic.strip().lower()
        return [r for r in self.repos if wanted in (t.lower() for t in r.topics)]


def _expect(table: dict, key: str, kind, where: str, default=None, required=True):
    if key not in table:
        if required:
            raise CatalogError(f"{where}: missing key '{key}'")
        return default
    value = table[key]
    if not isinstance(value, kind):
        raise CatalogError(
            f"{where}.{key}: expected {kind.__name__}, got {type(value).__name__}"
        )
    return value


def _parse_version(raw: dict, where: str) -> Version:
    if not isinstance(raw, dict):
        raise CatalogError(f"{where}: expected a table")
    version = _expect(raw, "version", str, where).strip()
    if not version:
        raise CatalogError(f"{where}.version: must not be empty")
    url = _expect(raw, "url", str, where).strip()
    ftype = _expect(raw, "type", str, where)
    if ftype not in FILE_TYPES:
        raise CatalogError(f"{where}.type: '{ftype}' not one of {FILE_TYPES}")
    published = _expect(raw, "published", str, where)
    try:
        if not _DATE_RE.match(published):
            raise ValueError
        datetime.date.fromisoformat(published)
    except ValueError:
        raise CatalogError(
            f"{where}.published: '{published}' is not a valid YYYY-MM-DD date"
        ) from None
    wip = _expect(raw, "wip", bool, where, default=False, required=False)
    notes = _expect(raw, "notes", str, where, default="", required=False)
    return Version(version, url, ftype, published, wip, notes)


def _parse_document(raw: dict, families: dict[str, Family], where: str) -> Document:
    if not isinstance(raw, dict):
        raise CatalogError(f"{where}: expected a table")
    doc_id = _expect(raw, "id", str, where).strip()
    if not doc_id or "/" in doc_id or "\\" in doc_id:
        raise CatalogError(f"{where}.id: '{doc_id}' is empty or contains a slash")
    family = _expect(raw, "family", str, where)
    if family not in families:
        raise CatalogError(f"{where}.family: unknown family '{family}'")
    title = _expect(raw, "title", str, where)
    access = _expect(raw, "access", str, where)
    if access not in ACCESS_TIERS:
        raise CatalogError(f"{where}.access: '{access}' not one of {ACCESS_TIERS}")
    fetch = _expect(raw, "fetch", str, where)
    if fetch not in FETCH_METHODS:
        raise CatalogError(f"{where}.fetch: '{fetch}' not one of {FETCH_METHODS}")
    notes = _expect(raw, "notes", str, where, default="", required=False)
    raw_versions = _expect(raw, "versions", list, where)
    if not raw_versions:
        raise CatalogError(f"{where}.versions: must list at least one version")
    versions = []
    seen: set[str] = set()
    for i, rv in enumerate(raw_versions):
        v = _parse_version(rv, f"{where}.versions[{i}]")
        if v.version in seen:
            raise CatalogError(
                f"{where}.versions[{i}]: duplicate version '{v.version}'"
            )
        if fetch != "manual" and not v.url:
            raise CatalogError(
                f"{where}.versions[{i}].url: required when fetch is '{fetch}'"
            )
        seen.add(v.version)
        versions.append(v)
    raw_with = _expect(raw, "searched_with", list, where, default=[], required=False)
    for k, item in enumerate(raw_with):
        if not isinstance(item, str) or not item.strip():
            raise CatalogError(f"{where}.searched_with[{k}]: expected a document id")
        if item.strip().lower() == doc_id.lower():
            raise CatalogError(
                f"{where}.searched_with[{k}]: a document cannot list itself"
            )
    return Document(
        doc_id,
        family,
        title,
        access,
        fetch,
        tuple(versions),
        notes,
        tuple(s.strip() for s in raw_with),
    )


def _parse_repo(raw: dict, where: str) -> Repo:
    if not isinstance(raw, dict):
        raise CatalogError(f"{where}: expected a table")
    repo_id = _expect(raw, "id", str, where).strip()
    if not repo_id or "/" in repo_id or "\\" in repo_id or repo_id.startswith("."):
        raise CatalogError(f"{where}.id: '{repo_id}' is not a directory name")
    url = _expect(raw, "url", str, where).strip()
    if not (url.startswith("https://") or url.startswith("file://")):
        raise CatalogError(
            f"{where}.url: '{url}' must start with https:// (or file://)"
        )
    topics = _expect(raw, "topics", list, where)
    if not topics or not all(isinstance(t, str) and t.strip() for t in topics):
        raise CatalogError(f"{where}.topics: must list at least one non-empty topic")
    sparse = _expect(raw, "sparse", list, where, default=[], required=False)
    if not all(isinstance(s, str) and s.strip() for s in sparse):
        raise CatalogError(f"{where}.sparse: expected non-empty path strings")
    return Repo(
        repo_id,
        url,
        tuple(t.strip() for t in topics),
        tuple(s.strip() for s in sparse),
    )


def parse_catalog(data: dict) -> Catalog:
    """Validate a decoded TOML document into a Catalog."""
    if not isinstance(data, dict):
        raise CatalogError("catalog: top level must be a table")
    schema = _expect(data, "schema_version", int, "catalog")
    if schema != SCHEMA_VERSION:
        raise CatalogError(
            f"catalog.schema_version: {schema} unsupported, expected {SCHEMA_VERSION}"
        )
    raw_families = _expect(data, "families", dict, "catalog")
    if not raw_families:
        raise CatalogError("catalog.families: must define at least one family")
    families: dict[str, Family] = {}
    for fid, raw in raw_families.items():
        where = f"families.{fid}"
        if not isinstance(raw, dict):
            raise CatalogError(f"{where}: expected a table")
        families[fid] = Family(
            fid,
            _expect(raw, "title", str, where),
            _expect(raw, "publisher", str, where),
        )
    raw_docs = _expect(data, "documents", list, "catalog")
    documents: list[Document] = []
    ids: set[str] = set()
    for i, raw in enumerate(raw_docs):
        doc = _parse_document(raw, families, f"documents[{i}]")
        key = doc.id.lower()
        if key in ids:
            raise CatalogError(f"documents[{i}].id: duplicate id '{doc.id}'")
        ids.add(key)
        documents.append(doc)
    for i, doc in enumerate(documents):
        for k, other in enumerate(doc.searched_with):
            if other.lower() not in ids:
                raise CatalogError(
                    f"documents[{i}].searched_with[{k}]: unknown document '{other}'"
                )
    raw_repos = _expect(data, "repos", list, "catalog", default=[], required=False)
    repos: list[Repo] = []
    repo_ids: set[str] = set()
    for i, raw in enumerate(raw_repos):
        repo = _parse_repo(raw, f"repos[{i}]")
        if repo.id.lower() in repo_ids:
            raise CatalogError(f"repos[{i}].id: duplicate id '{repo.id}'")
        repo_ids.add(repo.id.lower())
        repos.append(repo)
    return Catalog(families, documents, repos)


def load_catalog(path: Path | None = None) -> Catalog:
    """Read and validate the catalog file (the shipped one by default)."""
    path = DEFAULT_CATALOG if path is None else path
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError as exc:
        raise CatalogError(f"catalog file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise CatalogError(f"{path}: not valid TOML: {exc}") from exc
    return parse_catalog(data)

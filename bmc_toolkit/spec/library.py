"""The Library: the on-disk store of document versions.

Layout::

    <root>/
        specs/<family>/<document>/<version-dir>/
            original.<ext>      the file as published (or as dropped in)
            meta.json           provenance, see write_meta()
        code/                   code trees, later milestone

``<version-dir>`` is the version string made path-safe; ``meta.json`` keeps
the verbatim string.

``meta.json`` keys: ``family``, ``document``, ``version`` (verbatim),
``file`` (name of the original), ``url`` (source URL or null), ``fetch_method``
(``direct`` | ``wayback`` | ``dropin``), ``sha256``, ``size``, ``fetched_at``
(ISO 8601, UTC), ``dropin`` (bool), and for files registered by ``scan``
``catalog_known`` (bool: whether the document id is in the Source Catalog).

Everything derived from the original (the Extract and its companions,
``tables.json``, rendered pages, a bundle's ``schemas/`` or ``registries/``)
goes away when the original is replaced.

Single files are written through :func:`atomic_write_bytes` and friends: to
``<name>.<pid>-<token>.part`` next to the target, then renamed into place,
so a reader never sees a half-written file and two Sessions writing the same
file do not collide. Multi-file operations hold the directory's lock
(``lock.py``).
"""

import hashlib
import json
import os
import re
import secrets
import shutil
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ENV_LIBRARY = "BMC_SPEC_LIBRARY"
DEFAULT_LIBRARY_DIRNAME = ".bmc-specs"
META_NAME = "meta.json"
ORIGINAL_STEM = "original"
DERIVED_NAMES = (
    "extract.txt",
    "extract.json",
    "outline.json",
    "linemap.json",
    "figures.json",
    "tables.json",
)
RENDERS_DIRNAME = "renders"  # page images rendered from the original
SCHEMAS_DIRNAME = "schemas"  # JSON Schema files unpacked from a bundle
REGISTRIES_DIRNAME = "registries"  # message registry files unpacked from a bundle
MAGIC = {"pdf": (b"%PDF",), "zip": (b"PK\x03\x04",)}

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def resolve_library(env: Mapping[str, str] | None = None) -> Path:
    """Return the Library root: ``$BMC_SPEC_LIBRARY`` or ``~/.bmc-specs``.

    Expanded and absolute, not created.
    """
    env = os.environ if env is None else env
    override = env.get(ENV_LIBRARY, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / DEFAULT_LIBRARY_DIRNAME).resolve()


def safe_name(version: str) -> str:
    """Turn a version string into a directory name; '2.0 rev 1.1' -> '2.0_rev_1.1'."""
    name = _UNSAFE.sub("_", version.strip()).strip("_.")
    return name or "unnamed"


class LibraryError(Exception):
    """The Library refuses an operation; the message says why."""


def file_matches_type(path: Path, ext: str) -> bool:
    """True when the file starts with the magic bytes of ``ext`` (pdf, zip)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return False
    return any(head.startswith(m) for m in MAGIC.get(ext, ()))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


PART_SUFFIX = ".part"
REPLACE_RETRIES = 40  # Windows: renames onto one target can collide
REPLACE_PAUSE = 0.05  # seconds between retries


def temp_path(target: Path) -> Path:
    """A temporary name beside ``target`` that no other process will pick."""
    token = f"{os.getpid()}-{secrets.token_hex(4)}"
    return target.with_name(f"{target.name}.{token}{PART_SUFFIX}")


def atomic_write_bytes(target: Path, data: bytes) -> None:
    """Write ``data`` to a temp file beside ``target`` and rename it into place."""
    tmp = temp_path(target)
    try:
        tmp.write_bytes(data)
        _replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _replace(tmp: Path, target: Path) -> None:
    """``os.replace`` that rides out Windows refusing the rename while another
    process is renaming onto, or has just opened, the same target."""
    for attempt in range(REPLACE_RETRIES):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if attempt == REPLACE_RETRIES - 1:
                raise
            time.sleep(REPLACE_PAUSE)


def atomic_copy(source: Path, target: Path) -> None:
    """Copy ``source`` to a temp file beside ``target`` and rename it into place."""
    tmp = temp_path(target)
    try:
        shutil.copyfile(source, tmp)
        _replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_text(target: Path, text: str) -> None:
    """UTF-8, LF; see :func:`atomic_write_bytes`."""
    atomic_write_bytes(target, text.encode("utf-8"))


def atomic_write_json(
    target: Path,
    data,
    *,
    indent: int = 4,
    sort_keys: bool = False,
    ensure_ascii: bool = True,
) -> None:
    text = json.dumps(
        data, indent=indent, sort_keys=sort_keys, ensure_ascii=ensure_ascii
    )
    atomic_write_text(target, text + "\n")


@dataclass(frozen=True)
class Holding:
    """One document version present in the Library."""

    family: str
    document: str
    version: str
    path: Path
    meta: dict

    @property
    def dropin(self) -> bool:
        return bool(self.meta.get("dropin"))

    @property
    def original(self) -> Path:
        return self.path / self.meta.get("file", "original")

    @property
    def extract_meta(self) -> dict | None:
        """Contents of extract.json when the version has been extracted
        (a PDF's Extract, or a bundle's schemas or registries directory)."""
        path = self.path / "extract.json"
        if not path.is_file():
            return None
        if (
            not (self.path / "extract.txt").is_file()
            and not (self.path / SCHEMAS_DIRNAME).is_dir()
            and not (self.path / REGISTRIES_DIRNAME).is_dir()
        ):
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None


class Library:
    def __init__(self, root: Path):
        self.root = Path(root)

    @property
    def specs(self) -> Path:
        return self.root / "specs"

    def ensure(self) -> bool:
        """Create the root and ``specs/`` if needed; True when newly created."""
        created = not self.root.exists()
        self.specs.mkdir(parents=True, exist_ok=True)
        return created

    def version_dir(self, family: str, document: str, version: str) -> Path:
        return self.specs / family / document / safe_name(version)

    def find(self, document: str, version: str) -> Holding | None:
        """The holding for a document version, matching ids case-insensitively."""
        for h in self.holdings():
            if h.document.lower() == document.lower() and h.version == version:
                return h
        return None

    def holdings(self) -> Iterator[Holding]:
        """Every version directory that carries a meta.json, sorted by path."""
        if not self.specs.is_dir():
            return
        for meta_path in sorted(self.specs.glob("*/*/*/" + META_NAME)):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            vdir = meta_path.parent
            yield Holding(
                family=meta.get("family", vdir.parents[1].name),
                document=meta.get("document", vdir.parent.name),
                version=meta.get("version", vdir.name),
                path=vdir,
                meta=meta,
            )

    def _guard_collision(self, vdir: Path, version: str) -> None:
        """Refuse to write over a directory that holds a different version string.

        ``safe_name`` is not injective ('1.0 a' and '1.0_a' share a directory).
        """
        meta_path = vdir / META_NAME
        if not meta_path.exists():
            return
        try:
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        held = existing.get("version")
        if held is not None and held != version:
            raise LibraryError(
                f"{vdir} already holds version '{held}', which maps to the same "
                f"directory as '{version}'"
            )

    @staticmethod
    def _clear_previous(vdir: Path, keep: str) -> None:
        """Drop the meta, other originals and every derived file before a
        new original. The meta goes first and comes back last (``store`` and
        ``add_dropin`` write it after the original), so a Session killed in
        between leaves an original without ``meta.json``: not a holding, so
        the next ``fetch`` redoes it and ``scan`` can still register it,
        rather than the old meta describing the new file."""
        if not vdir.is_dir():
            return
        meta = vdir / META_NAME
        if meta.exists():
            meta.unlink()
        for p in vdir.glob(ORIGINAL_STEM + ".*"):
            if p.name != keep and not p.name.endswith(PART_SUFFIX):
                p.unlink()
        for name in DERIVED_NAMES:
            p = vdir / name
            if p.exists():
                p.unlink()
        for dirname in (RENDERS_DIRNAME, SCHEMAS_DIRNAME, REGISTRIES_DIRNAME):
            tree = vdir / dirname
            if tree.is_dir():
                shutil.rmtree(tree)

    def write_meta(self, vdir: Path, meta: dict) -> Path:
        vdir.mkdir(parents=True, exist_ok=True)
        path = vdir / META_NAME
        atomic_write_json(path, meta, indent=4, sort_keys=True)
        return path

    def store(
        self,
        family: str,
        document: str,
        version: str,
        data: bytes,
        ext: str,
        *,
        url: str | None,
        method: str,
        dropin: bool = False,
    ) -> Path:
        """Write bytes as the original of a version and record its meta."""
        vdir = self.version_dir(family, document, version)
        self._guard_collision(vdir, version)
        vdir.mkdir(parents=True, exist_ok=True)
        filename = f"{ORIGINAL_STEM}.{ext}"
        self._clear_previous(vdir, filename)
        target = vdir / filename
        atomic_write_bytes(target, data)
        self.write_meta(
            vdir,
            {
                "family": family,
                "document": document,
                "version": version,
                "file": filename,
                "url": url,
                "fetch_method": method,
                "sha256": sha256_of(target),
                "size": target.stat().st_size,
                "fetched_at": now_iso(),
                "dropin": dropin,
            },
        )
        return vdir

    def add_dropin(
        self, source: Path, family: str, document: str, version: str, ext: str
    ) -> Path:
        """Copy a user-supplied file into the Library as a Drop-in."""
        vdir = self.version_dir(family, document, version)
        self._guard_collision(vdir, version)
        vdir.mkdir(parents=True, exist_ok=True)
        filename = f"{ORIGINAL_STEM}.{ext}"
        self._clear_previous(vdir, filename)
        target = vdir / filename
        atomic_copy(source, target)
        self.write_meta(
            vdir,
            {
                "family": family,
                "document": document,
                "version": version,
                "file": filename,
                "url": None,
                "fetch_method": "dropin",
                "sha256": sha256_of(target),
                "size": target.stat().st_size,
                "fetched_at": now_iso(),
                "dropin": True,
            },
        )
        return vdir

    def unregistered(self) -> Iterator[tuple[Path, Path]]:
        """(version_dir, original file) pairs that have no meta.json yet."""
        if not self.specs.is_dir():
            return
        for vdir in sorted(p for p in self.specs.glob("*/*/*") if p.is_dir()):
            if (vdir / META_NAME).exists():
                continue
            originals = sorted(vdir.glob(ORIGINAL_STEM + ".*"))
            originals = [p for p in originals if not p.name.endswith(PART_SUFFIX)]
            if originals:
                yield vdir, originals[0]


def latest_held(doc, held: list[Holding]) -> Holding | None:
    """The newest held version of a document: the catalog's latest if held,
    else the held version the catalog dates newest, else the most recently
    fetched. ``doc`` is the catalog Document, or None for one it lacks."""
    if not held:
        return None
    if doc is not None:
        latest = doc.latest()
        if latest is not None:
            for h in held:
                if h.version == latest.version:
                    return h
        dated = {v.version: v.published for v in doc.versions}
        known = [h for h in held if h.version in dated]
        if known:
            return max(known, key=lambda h: dated[h.version])
    return max(held, key=lambda h: h.meta.get("fetched_at", ""))


def released(doc, held: list[Holding]) -> list[Holding]:
    """The held versions the catalog does not mark WIP (versions it does not
    list, and every version of a document it lacks, count as released)."""
    if doc is None:
        return list(held)
    kept = []
    for h in held:
        ver = doc.find_version(h.version)
        if ver is None or not ver.wip:
            kept.append(h)
    return kept


def answering_holding(doc, held: list[Holding]) -> Holding | None:
    """The held version a reading command answers from without ``--version``
    when it cannot download: the newest released one, or the newest WIP one
    when nothing released is held."""
    return latest_held(doc, released(doc, held)) or latest_held(doc, held)

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
"""

import hashlib
import json
import os
import re
import shutil
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ENV_LIBRARY = "BMC_SPEC_LIBRARY"
DEFAULT_LIBRARY_DIRNAME = ".bmc-specs"
META_NAME = "meta.json"
ORIGINAL_STEM = "original"
DERIVED_NAMES = ("extract.txt", "extract.json", "outline.json", "linemap.json")
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
        """Contents of extract.json when the version has been extracted."""
        path = self.path / "extract.json"
        if not path.is_file() or not (self.path / "extract.txt").is_file():
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
        """Drop other originals and every derived file before a new original."""
        if not vdir.is_dir():
            return
        for p in vdir.glob(ORIGINAL_STEM + ".*"):
            if p.name != keep and not p.name.endswith(".part"):
                p.unlink()
        for name in DERIVED_NAMES:
            p = vdir / name
            if p.exists():
                p.unlink()

    def write_meta(self, vdir: Path, meta: dict) -> Path:
        vdir.mkdir(parents=True, exist_ok=True)
        path = vdir / META_NAME
        with open(path, "w", encoding="utf-8", newline="") as fh:
            json.dump(meta, fh, indent=4, sort_keys=True)
            fh.write("\n")
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
        tmp = vdir / (filename + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, target)
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
        shutil.copyfile(source, target)
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
            originals = [p for p in originals if not p.name.endswith(".part")]
            if originals:
                yield vdir, originals[0]

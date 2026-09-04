"""Redfish message registries (DSP8011 ZIP): unpack the newest file of
each registry, then read messages from them.

The archive ships every version of every registry (Base alone has 91
files), flat or under one folder, named ``<Prefix>.<M>.<m>.<p>.json``.
``unpack`` keeps the newest per prefix under ``registries/``; the privilege
registries (``Redfish_<v>_PrivilegeRegistry.json``), the HTML and the PDF
stay in the ZIP. A message is cited by file and JSON pointer, and its
``Message`` text is printed verbatim, since that is what a client matches.

Files written next to the original::

    registries/<Prefix>.<M>.<m>.<p>.json
    extract.json   {"extractor_version": REGISTRY_VERSION,
                    "kind": "registries", "files": n, "registries": n,
                    "seconds": s, "outline_source": "registries"}

Standard library only.
"""

import json
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from bmc_toolkit.spec.library import REGISTRIES_DIRNAME, SCHEMAS_DIRNAME

REGISTRY_VERSION = 1
META_NAME = "extract.json"  # shared with the other extractors; "kind" tells them apart
KIND = "registries"

_REGISTRY_FILE = re.compile(
    r"^(?P<prefix>[A-Za-z][A-Za-z0-9]*)\.(?P<maj>\d+)\.(?P<min>\d+)\.(?P<pat>\d+)\.json$"
)


class RegistryError(Exception):
    """The archive cannot be unpacked, or a registry file cannot be read."""


class NoRegistries(RegistryError):
    """The archive holds no message registry file."""


@dataclass
class RegistryResult:
    files: int
    registries: int
    seconds: float
    refused: int = 0  # members whose path would have escaped registries/
    duplicates: int = 0  # members whose base name another kept member has

    def to_meta(self) -> dict:
        return {
            "extractor_version": REGISTRY_VERSION,
            "kind": KIND,
            "files": self.files,
            "registries": self.registries,
            "refused": self.refused,
            "duplicates": self.duplicates,
            "seconds": round(self.seconds, 2),
            "outline_source": KIND,
        }


# --------------------------------------------------------------- unpack


def version_key(name: str) -> tuple[int, int, int] | None:
    """(major, minor, patch) of a registry file name, else None."""
    m = _REGISTRY_FILE.match(name)
    if not m:
        return None
    return int(m.group("maj")), int(m.group("min")), int(m.group("pat"))


def prefix_of(name: str) -> str | None:
    m = _REGISTRY_FILE.match(name)
    return m.group("prefix") if m else None


def version_label(name: str) -> str | None:
    """'1.23.0' for 'Base.1.23.0.json'."""
    key = version_key(name)
    return ".".join(str(n) for n in key) if key else None


def _is_safe(member: str) -> bool:
    path = PurePosixPath(member)
    return not path.is_absolute() and ".." not in path.parts and "\\" not in member


def select_members(members: list[str]) -> tuple[list[str], int, int]:
    """(archive members to keep, members refused for their path, members
    dropped because an earlier one has the same base name): the newest
    ``<Prefix>.<M>.<m>.<p>.json`` per prefix, wherever it lies in the
    archive. Raises NoRegistries when there is none."""
    refused = 0
    repeats: dict[str, int] = {}
    newest: dict[str, tuple[tuple[int, int, int], str]] = {}
    for member in members:
        base = PurePosixPath(member).name
        key = version_key(base)
        if key is None:
            continue
        if not _is_safe(member):
            refused += 1
            continue
        if base in repeats:
            repeats[base] += 1
            continue
        repeats[base] = 0
        prefix = prefix_of(base)
        if prefix not in newest or key > newest[prefix][0]:
            newest[prefix] = (key, member)
    if not newest:
        raise NoRegistries("no message registry files in the archive")
    kept = sorted(m for _, m in newest.values())
    duplicates = sum(repeats[PurePosixPath(m).name] for m in kept)
    return kept, refused, duplicates


def unpack(zip_path: Path, vdir: Path) -> RegistryResult:
    """Write the newest registry files into ``vdir/registries`` and the
    meta file; an existing ``registries/`` directory is replaced."""
    started = time.perf_counter()
    try:
        archive = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise RegistryError(f"cannot open {zip_path}: {exc}") from exc
    with archive:
        kept, refused, duplicates = select_members(archive.namelist())
        meta_path = vdir / META_NAME
        if meta_path.exists():
            meta_path.unlink()  # nothing is_current() believes until the end
        target = vdir / REGISTRIES_DIRNAME
        for stale in (target, vdir / SCHEMAS_DIRNAME):  # one kind per version
            if stale.is_dir():
                shutil.rmtree(stale)
        target.mkdir(parents=True)
        for member in kept:
            base = PurePosixPath(member).name
            try:
                data = archive.read(member)
            except (zipfile.BadZipFile, KeyError, RuntimeError) as exc:
                raise RegistryError(f"cannot read {member}: {exc}") from exc
            (target / base).write_bytes(data)
    result = RegistryResult(
        files=len(kept),
        registries=len(kept),
        seconds=time.perf_counter() - started,
        refused=refused,
        duplicates=duplicates,
    )
    with open(vdir / META_NAME, "w", encoding="utf-8", newline="") as fh:
        json.dump(result.to_meta(), fh, indent=1)
        fh.write("\n")
    return result


def read_meta(vdir: Path) -> dict | None:
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
        and meta.get("extractor_version") == REGISTRY_VERSION
        and (vdir / REGISTRIES_DIRNAME).is_dir()
    )


def remove_registries(vdir: Path) -> None:
    target = vdir / REGISTRIES_DIRNAME
    if target.is_dir():
        shutil.rmtree(target)


# -------------------------------------------------------------- reading


@dataclass(frozen=True)
class Registry:
    prefix: str
    version: str  # '1.23.0'
    file: str
    count: int  # messages

    @property
    def label(self) -> str:
        return f"{self.prefix} {self.version}"

    @property
    def id_prefix(self) -> str:
        """The MessageId prefix a service sends: registry, major, minor."""
        parts = self.version.split(".")
        return ".".join([self.prefix, *parts[:2]])


@dataclass(frozen=True)
class Message:
    registry: Registry
    key: str  # 'PropertyMissing', as spelled in the file
    node: dict

    @property
    def id(self) -> str:
        return f"{self.registry.id_prefix}.{self.key}"

    @property
    def pointer(self) -> str:
        return f"#/Messages/{self.key}"


class Registries:
    """The unpacked registry files of one bundle version."""

    def __init__(self, vdir: Path):
        self.dir = vdir / REGISTRIES_DIRNAME
        self._cache: dict[str, dict] = {}

    def files(self) -> list[str]:
        if not self.dir.is_dir():
            raise RegistryError(f"{self.dir} is missing")
        return sorted(p.name for p in self.dir.glob("*.json") if version_key(p.name))

    def load(self, file: str) -> dict:
        data = self._cache.get(file)
        if data is None:
            path = self.dir / file
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except OSError as exc:
                raise RegistryError(f"{path}: {exc}") from exc
            except ValueError as exc:
                raise RegistryError(f"{path}: not valid JSON ({exc})") from exc
            if not isinstance(data, dict) or not isinstance(data.get("Messages"), dict):
                raise RegistryError(f"{path}: not a message registry (no Messages)")
            self._cache[file] = data
        return data

    def registries(self) -> list[Registry]:
        out = []
        for file in self.files():
            data = self.load(file)
            out.append(
                Registry(
                    prefix=str(data.get("RegistryPrefix") or prefix_of(file)),
                    version=str(data.get("RegistryVersion") or version_label(file)),
                    file=file,
                    count=len(data["Messages"]),
                )
            )
        return sorted(out, key=lambda r: r.prefix.lower())

    def registry(self, query: str) -> Registry | None:
        wanted = query.lower()
        for r in self.registries():
            if r.prefix.lower() == wanted:
                return r
        return None

    def similar(self, query: str) -> list[str]:
        wanted = query.lower()
        return [r.prefix for r in self.registries() if wanted in r.prefix.lower()]

    def messages(self, reg: Registry) -> list[Message]:
        nodes = self.load(reg.file)["Messages"]
        return [Message(reg, k, n) for k, n in nodes.items() if isinstance(n, dict)]

    def message(self, reg: Registry, key: str) -> Message | None:
        """The message whose key matches ``key`` case-insensitively; a full
        MessageId (``Base.1.23.PropertyMissing``) is accepted as well."""
        wanted = key.rsplit(".", 1)[-1].lower()
        for m in self.messages(reg):
            if m.key.lower() == wanted:
                return m
        return None

    def similar_messages(self, reg: Registry, key: str) -> list[str]:
        wanted = key.rsplit(".", 1)[-1].lower()
        return [m.key for m in self.messages(reg) if wanted in m.key.lower()]


# ----------------------------------------------------------- formatting


def _text(value) -> str:
    return " ".join(str(value).split())


def severity_of(node: dict) -> str:
    return str(node.get("MessageSeverity") or node.get("Severity") or "-")


def message_line(m: Message) -> str:
    """One line of a registry listing: key, severity, the message text."""
    return f"{m.key} | {severity_of(m.node)} | {_text(m.node.get('Message', ''))}"


def detail_lines(m: Message) -> list[str]:
    """The ``message:`` line and everything the registry says about it."""
    node = m.node
    args = node.get("NumberOfArgs")
    try:
        n = int(args)
    except (TypeError, ValueError):
        n = len(node.get("ParamTypes", []) or [])
    out = [f"message: {m.id} | {severity_of(node)} | {n} arg{'' if n == 1 else 's'}"]
    if node.get("Message") is not None:
        out.append(f"text: {node['Message']}")
    for key, label in (
        ("Description", "description"),
        ("LongDescription", "longDescription"),
        ("Resolution", "resolution"),
    ):
        if node.get(key):
            out.append(f"{label}: {_text(node[key])}")
    types = node.get("ParamTypes") or []
    descriptions = node.get("ArgDescriptions") or []
    if types or descriptions:
        out.append("args:")
        for i in range(max(len(types), len(descriptions))):
            kind = types[i] if i < len(types) else "-"
            what = _text(descriptions[i]) if i < len(descriptions) else ""
            out.append(f"  %{i + 1} | {kind}" + (f" | {what}" if what else ""))
    if node.get("VersionAdded"):
        out.append(f"added v{node['VersionAdded']}")
    if node.get("Deprecated"):
        since = node.get("VersionDeprecated")
        note = f" (since v{since})" if since else ""
        out.append(f"deprecated{note}: {_text(node['Deprecated'])}")
    return out


__all__ = [
    "KIND",
    "META_NAME",
    "REGISTRIES_DIRNAME",
    "REGISTRY_VERSION",
    "Message",
    "NoRegistries",
    "Registries",
    "Registry",
    "RegistryError",
    "RegistryResult",
    "detail_lines",
    "is_current",
    "message_line",
    "prefix_of",
    "read_meta",
    "remove_registries",
    "select_members",
    "severity_of",
    "unpack",
    "version_key",
    "version_label",
]

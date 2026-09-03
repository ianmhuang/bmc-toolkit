"""Redfish schema bundles (DSP8010 ZIP): unpack the JSON Schema files an
answer needs, then read resources, properties and enum values from them.

The archive ships every version every resource ever had (Chassis alone has
263 files); ``unpack`` keeps, flat under ``schemas/``, every unversioned
``<Name>.json`` (the index: common definitions such as ``Resource.json``'s
``PowerState``, and the list of versions) and the newest
``<Name>.vX_Y_Z.json`` per resource. Nothing else leaves the ZIP.

Files written next to the original::

    schemas/<Name>.json, schemas/<Name>.vX_Y_Z.json
    extract.json   {"extractor_version": BUNDLE_VERSION, "kind": "schemas",
                    "files": n, "resources": n, "seconds": s,
                    "outline_source": "schemas"}

Standard library only.
"""

import json
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

BUNDLE_VERSION = 1
SCHEMAS_DIRNAME = "schemas"
SCHEMA_FOLDER = "json-schema"
META_NAME = "extract.json"  # shared with the PDF extractor; "kind" tells them apart

_VERSIONED = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9_-]*)\.v(?P<maj>\d+)_(?P<min>\d+)_(?P<pat>\d+)\.json$"
)
_UNVERSIONED = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9_-]*)\.json$")
_REF = re.compile(r"^(?P<file>[^#]*?)(?:#(?P<pointer>.*))?$")
_ODATA_FILES = ("odata-v4.json", "odata.4.0.0.json")


class BundleError(Exception):
    """The archive cannot be unpacked; the message says why."""


class NoSchemas(BundleError):
    """The archive has no json-schema folder (not a schema bundle)."""


class SchemaError(Exception):
    """A schema file is missing or unreadable."""


@dataclass
class BundleResult:
    files: int
    resources: int
    seconds: float
    refused: int = 0  # members whose path would have escaped schemas/

    def to_meta(self) -> dict:
        return {
            "extractor_version": BUNDLE_VERSION,
            "kind": "schemas",
            "files": self.files,
            "resources": self.resources,
            "refused": self.refused,
            "seconds": round(self.seconds, 2),
            "outline_source": "schemas",
        }


# --------------------------------------------------------------- unpack


def version_key(name: str) -> tuple[int, int, int] | None:
    """(major, minor, patch) of a versioned schema file name, else None."""
    m = _VERSIONED.match(name)
    if not m:
        return None
    return int(m.group("maj")), int(m.group("min")), int(m.group("pat"))


def version_label(name: str) -> str | None:
    """'v1.28.0' for 'Chassis.v1_28_0.json', None for an unversioned file."""
    key = version_key(name)
    return "v" + ".".join(str(n) for n in key) if key else None


def resource_name(name: str) -> str | None:
    m = _VERSIONED.match(name) or _UNVERSIONED.match(name)
    return m.group("name") if m else None


def _is_safe(member: str) -> bool:
    path = PurePosixPath(member)
    return not path.is_absolute() and ".." not in path.parts and "\\" not in member


def select_members(members: list[str]) -> tuple[list[str], int]:
    """(archive members to keep, members refused for their path).

    Kept: every unversioned ``<Name>.json`` under a ``json-schema`` folder
    and the newest ``<Name>.vX_Y_Z.json`` per name. Raises NoSchemas when
    no member lies under such a folder.
    """
    refused = 0
    unversioned: list[str] = []
    newest: dict[str, tuple[tuple[int, int, int], str]] = {}
    seen_folder = False
    for member in members:
        parts = PurePosixPath(member).parts
        if SCHEMA_FOLDER not in parts[:-1]:
            continue
        seen_folder = True
        if not _is_safe(member):
            refused += 1
            continue
        base = parts[-1]
        key = version_key(base)
        if key is not None:
            name = resource_name(base)
            if name not in newest or key > newest[name][0]:
                newest[name] = (key, member)
        elif _UNVERSIONED.match(base):
            unversioned.append(member)
    if not seen_folder:
        raise NoSchemas(f"no {SCHEMA_FOLDER}/ folder in the archive")
    kept = sorted(unversioned) + sorted(m for _, m in newest.values())
    return kept, refused


def unpack(zip_path: Path, vdir: Path) -> BundleResult:
    """Write the selected schema files into ``vdir/schemas`` and the meta
    file; an existing ``schemas/`` directory is replaced."""
    started = time.perf_counter()
    try:
        archive = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BundleError(f"cannot open {zip_path}: {exc}") from exc
    with archive:
        kept, refused = select_members(archive.namelist())
        meta_path = vdir / META_NAME
        if meta_path.exists():
            meta_path.unlink()  # nothing is_current() believes until the end
        target = vdir / SCHEMAS_DIRNAME
        if target.is_dir():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        names = set()
        for member in kept:
            base = PurePosixPath(member).name
            try:
                data = archive.read(member)
            except (zipfile.BadZipFile, KeyError, RuntimeError) as exc:
                raise BundleError(f"cannot read {member}: {exc}") from exc
            (target / base).write_bytes(data)
            names.add(resource_name(base))
    result = BundleResult(
        files=len(kept),
        resources=len(names),
        seconds=time.perf_counter() - started,
        refused=refused,
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
    return meta if isinstance(meta, dict) and meta.get("kind") == "schemas" else None


def is_current(vdir: Path) -> bool:
    meta = read_meta(vdir)
    return (
        bool(meta)
        and meta.get("extractor_version") == BUNDLE_VERSION
        and (vdir / SCHEMAS_DIRNAME).is_dir()
    )


def remove_schemas(vdir: Path) -> None:
    target = vdir / SCHEMAS_DIRNAME
    if target.is_dir():
        shutil.rmtree(target)


# -------------------------------------------------------------- reading


@dataclass(frozen=True)
class Resource:
    name: str
    file: str  # newest versioned file, or the index file
    version: str | None  # 'v1.28.0', None for an index-only name

    @property
    def label(self) -> str:
        return f"{self.name} {self.version}" if self.version else self.name


@dataclass(frozen=True)
class Located:
    """A schema node and where it lives."""

    file: str
    pointer: str  # JSON pointer within the file, '#/definitions/...'
    node: dict


class Schemas:
    """The unpacked schema files of one bundle version."""

    def __init__(self, vdir: Path):
        self.dir = vdir / SCHEMAS_DIRNAME
        self._cache: dict[str, dict] = {}

    def files(self) -> list[str]:
        if not self.dir.is_dir():
            raise SchemaError(f"{self.dir} is missing")
        return sorted(p.name for p in self.dir.glob("*.json"))

    def has(self, file: str) -> bool:
        return (self.dir / file).is_file()

    def load(self, file: str) -> dict:
        data = self._cache.get(file)
        if data is None:
            path = self.dir / file
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except OSError as exc:
                raise SchemaError(f"{path}: {exc}") from exc
            except ValueError as exc:
                raise SchemaError(f"{path}: not valid JSON ({exc})") from exc
            if not isinstance(data, dict):
                raise SchemaError(f"{path}: not a JSON object")
            self._cache[file] = data
        return data

    def resources(self) -> list[Resource]:
        """Every name, with its newest versioned file when there is one."""
        newest: dict[str, tuple[tuple[int, int, int], str]] = {}
        index: dict[str, str] = {}
        for file in self.files():
            name = resource_name(file)
            if name is None:
                continue
            key = version_key(file)
            if key is not None:
                if name not in newest or key > newest[name][0]:
                    newest[name] = (key, file)
            else:
                index[name] = file
        out = []
        for name in sorted(set(newest) | set(index), key=str.lower):
            if name in newest:
                file = newest[name][1]
                out.append(Resource(name, file, version_label(file)))
            else:
                out.append(Resource(name, index[name], None))
        return out

    def resource(self, query: str) -> Resource | None:
        wanted = query.lower()
        for r in self.resources():
            if r.name.lower() == wanted:
                return r
        return None

    def similar(self, query: str) -> list[str]:
        wanted = query.lower()
        return [r.name for r in self.resources() if wanted in r.name.lower()]

    # ---------------------------------------------------------- nodes

    def definition(self, file: str, name: str) -> Located | None:
        """The definition named ``name`` (case-insensitively) in ``file``."""
        defs = self.load(file).get("definitions", {})
        if not isinstance(defs, dict):
            return None
        for key, node in defs.items():
            if key.lower() == name.lower() and isinstance(node, dict):
                return Located(file, f"#/definitions/{key}", node)
        return None

    def main_definition(self, res: Resource) -> Located | None:
        """The resource's own definition: the newest versioned node when
        the file has one, else the index entry."""
        return self.definition(res.file, res.name)

    def property(self, where: Located, name: str) -> Located | None:
        props = where.node.get("properties", {})
        if not isinstance(props, dict):
            return None
        for key, node in props.items():
            if key.lower() == name.lower() and isinstance(node, dict):
                return Located(where.file, f"{where.pointer}/properties/{key}", node)
        return None

    def resolve(self, ref: str, current: str) -> Located | None:
        """Follow a ``$ref`` to a node in an unpacked file; None when the
        target file is not in ``schemas/`` or the pointer does not exist."""
        m = _REF.match(ref)
        if not m:
            return None
        file = PurePosixPath(m.group("file")).name if m.group("file") else current
        pointer = m.group("pointer") or ""
        if not self.has(file):
            return None
        node = self.load(file)
        for part in [p for p in pointer.split("/") if p]:
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        if not isinstance(node, dict):
            return None
        return Located(file, "#" + pointer, node)

    # ---------------------------------------------------------- types

    def type_of(self, node: dict, file: str) -> str:
        """The type of a property, resolved through anyOf/null and $ref."""
        options = _non_null(node.get("anyOf"))
        if options is not None:
            if not options:
                return "null"
            if len(options) == 1:
                return self.type_of(options[0], file)
            return " or ".join(self.type_of(o, file) for o in options)
        ref = node.get("$ref")
        if isinstance(ref, str):
            return self._type_of_ref(ref, file)
        if "enum" in node:
            return "enum"
        kind = node.get("type")
        if isinstance(kind, list):
            kinds = [k for k in kind if k != "null"]
            kind = kinds[0] if len(kinds) == 1 else " or ".join(kinds)
        if kind == "array":
            items = node.get("items")
            inner = self.type_of(items, file) if isinstance(items, dict) else "-"
            return f"array of {inner}"
        if kind == "object" and "properties" in node:
            return "object"
        return kind if isinstance(kind, str) else "-"

    def _type_of_ref(self, ref: str, file: str) -> str:
        m = _REF.match(ref)
        target_file = (
            PurePosixPath(m.group("file")).name if m and m.group("file") else file
        )
        pointer = (m.group("pointer") or "") if m else ""
        def_name = pointer.rsplit("/", 1)[-1] if pointer else target_file
        if target_file in _ODATA_FILES:
            return f"odata {def_name}"
        target = self.resolve(ref, file)
        if target is None:
            return ref
        node = target.node
        if "enum" in node:
            return f"enum {def_name}"
        if "properties" in node or node.get("type") == "object" or "anyOf" in node:
            return f"object {def_name}"
        inner = self.type_of(node, target.file)
        return inner if inner != "-" else def_name

    def enum_of(self, node: dict, file: str, pointer: str = "") -> Located | None:
        """The enum node a property's type resolves to, if any, with the
        file and pointer it was found at (``pointer`` names ``node`` itself
        for an inline enum)."""
        options = _non_null(node.get("anyOf"))
        if options is not None:
            for option in options:
                found = self.enum_of(option, file, pointer)
                if found:
                    return found
            return None
        ref = node.get("$ref")
        if isinstance(ref, str):
            target = self.resolve(ref, file)
            if target is None:
                return None
            return self.enum_of(target.node, target.file, target.pointer)
        if "enum" in node:
            return Located(file, pointer, node)
        return None


def _non_null(options) -> list[dict] | None:
    if not isinstance(options, list):
        return None
    return [o for o in options if isinstance(o, dict) and o != {"type": "null"}]


# ----------------------------------------------------------- formatting


def label_of(file: str) -> str:
    """'Chassis v1.28.0' for a versioned file, 'Resource' for an index."""
    name = resource_name(file) or file
    version = version_label(file)
    return f"{name} {version}" if version else name


def dotted(version: str | None) -> str:
    """'v1_2_0' -> 'v1.2.0'; anything else unchanged."""
    if isinstance(version, str) and re.match(r"^v\d+_\d+_\d+$", version):
        return version.replace("_", ".")
    return version or "-"


def property_line(schemas: Schemas, name: str, node: dict, file: str) -> str:
    access = "readonly" if node.get("readonly") else "writable"
    added = node.get("versionAdded")
    added = f"added {dotted(added)}" if added else "-"
    description = " ".join(str(node.get("description", "")).split())
    kind = schemas.type_of(node, file)
    return f"{name} | {kind} | {access} | {added} | {description}".rstrip()


def property_lines(schemas: Schemas, where: Located) -> list[str]:
    props = where.node.get("properties", {})
    if not isinstance(props, dict):
        return []
    return [
        property_line(schemas, name, node, where.file)
        for name, node in props.items()
        if isinstance(node, dict)
    ]


def detail_lines(node: dict) -> list[str]:
    """description, longDescription and the other notes a node carries."""
    out = []
    for key in ("description", "longDescription"):
        if node.get(key):
            out.append(f"{key}: {' '.join(str(node[key]).split())}")
    if node.get("deprecated"):
        since = node.get("versionDeprecated")
        note = f" (since {dotted(since)})" if since else ""
        out.append(f"deprecated{note}: {' '.join(str(node['deprecated']).split())}")
    for key in ("units", "pattern", "minimum", "maximum", "format"):
        if key in node:
            out.append(f"{key}: {node[key]}")
    return out


def enum_lines(node: dict) -> list[str]:
    values = node.get("enum", [])
    descriptions = node.get("enumDescriptions", {})
    added = node.get("enumVersionAdded", {})
    deprecated = node.get("enumDeprecated", {})
    out = ["values:"]
    for value in values:
        line = f"  {value}"
        text = descriptions.get(value) if isinstance(descriptions, dict) else None
        if text:
            line += f": {' '.join(str(text).split())}"
        notes = []
        if isinstance(added, dict) and value in added:
            notes.append(f"added {dotted(added[value])}")
        if isinstance(deprecated, dict) and value in deprecated:
            notes.append(f"deprecated: {' '.join(str(deprecated[value]).split())}")
        if notes:
            line += f" ({'; '.join(notes)})"
        out.append(line)
    return out


def parameter_lines(schemas: Schemas, where: Located) -> list[str]:
    """An action's parameters in the property line format."""
    params = where.node.get("parameters")
    if not isinstance(params, dict) or not params:
        return []
    out = ["parameters:"]
    for name, node in params.items():
        if not isinstance(node, dict):
            continue
        required = "required" if node.get("requiredParameter") else "optional"
        description = " ".join(str(node.get("description", "")).split())
        kind = schemas.type_of(node, where.file)
        out.append(f"  {name} | {kind} | {required} | {description}")
    return out


__all__ = [
    "BUNDLE_VERSION",
    "META_NAME",
    "SCHEMAS_DIRNAME",
    "BundleError",
    "BundleResult",
    "Located",
    "NoSchemas",
    "Resource",
    "SchemaError",
    "Schemas",
    "detail_lines",
    "dotted",
    "enum_lines",
    "is_current",
    "label_of",
    "parameter_lines",
    "property_line",
    "property_lines",
    "read_meta",
    "remove_schemas",
    "resource_name",
    "select_members",
    "unpack",
    "version_key",
    "version_label",
]

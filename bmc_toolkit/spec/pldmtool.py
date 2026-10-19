"""pldmtool's subcommand for a PLDM Command, read from the held openbmc/pldm
Code Tree (ADR 0007).

``invocation pldm --subcommand NAME`` asks: does pldmtool register a
subcommand called NAME, under which type, with which options? The answer
is read from ``pldmtool/`` of the tree at the commit the Library holds:
the ``add_subcommand`` registration, the class the registration hands the
subcommand to, and the ``add_option`` / ``add_flag`` calls of that class's
constructor. What is printed is those source lines with a code cite and a
template line built from the option spellings, every value a placeholder.
No value is filled in and no table of subcommands ships: the source at the
held commit is the only source, and the parse is best effort (the lines
are always printed; the template is dropped when they cannot be read).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from . import code as code_mod

SUBDIR = "pldmtool"
MAX_CONSTRUCTOR_LINES = 60
MAX_MAP_LINES = 30

# `auto var = parent->add_subcommand("Name", ...)`; the `auto var =` part is
# optional (a registration whose handle is not kept)
_REGISTRATION = re.compile(
    r"(?:auto\s+(?P<var>\w+)\s*=\s*)?(?P<parent>\w+)\s*(?:->|\.)\s*"
    r'add_subcommand\(\s*"(?P<name>[^"]+)"'
)
_OPTION_CALL = re.compile(
    r'add_(?P<kind>option|flag)\(\s*(?P<literals>(?:"[^"]*"\s*)+)'
)
_LITERAL = re.compile(r'"([^"]*)"')
_TRANSFORM = re.compile(r"CheckedTransformer\(\s*(\w+)")


@dataclass
class Option:
    spellings: list[str]  # as the literal spells them: ["-i", "--sensor_id"]
    required: bool
    flag: bool
    transform_map: str | None = None

    @property
    def short(self) -> str | None:
        return next((s for s in self.spellings if not s.startswith("--")), None)

    @property
    def long(self) -> str | None:
        return next((s for s in self.spellings if s.startswith("--")), None)

    def item(self) -> str:
        """The option in the template: `-i <sensor_id>`, `[-s <state_set_id>]`
        for one not required, `[-a]` for a flag."""
        name = self.short or self.long or ""
        if self.flag:
            return f"[{name}]"
        placeholder = (self.long or name).lstrip("-")
        text = f"{name} <{placeholder}>"
        return text if self.required else f"[{text}]"


@dataclass
class Match:
    path: str  # pldmtool/pldm_platform_cmd.cpp
    name: str  # as registered
    type_: str  # base, platform, fru, bios, fw_update, oem-ibm
    registration: int  # 1-based first line of the add_subcommand call
    registration_end: int = 0  # the line the name sits on (same or later)
    class_name: str | None = None
    first: int = 0  # constructor lines, 1-based; 0 when none was found
    last: int = 0  # the whole constructor; describe prints up to the cap
    explicit: bool = False  # an `explicit Class(` constructor, not a `using`
    options: list[Option] = field(default_factory=list)
    map_lines: dict[str, tuple[int, int]] = field(default_factory=dict)

    def template(self) -> str:
        items = [f"pldmtool {self.type_} {self.name} -m <eid>"]
        items.extend(opt.item() for opt in self.options)
        return " ".join(items)


def cpp_files(tree: code_mod.Tree) -> list[str]:
    """The ``pldmtool/**/*.cpp`` files of the tree, as tree-relative paths."""
    base = tree.path / SUBDIR
    if not base.is_dir():
        return []
    out = []
    for path in sorted(base.rglob("*.cpp")):
        rel = path.relative_to(tree.path)
        out.append(str(PurePosixPath(*rel.parts)))
    return out


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _registrations(text: str) -> list[dict]:
    regs = []
    for m in _REGISTRATION.finditer(text):
        regs.append(
            {
                "var": m.group("var"),
                "parent": m.group("parent"),
                "name": m.group("name"),
                "line": _line_of(text, m.start()),
                "end": _line_of(text, m.start("name")),
            }
        )
    return regs


def _type_of(reg: dict, regs: list[dict], path: str) -> str:
    """The type a registration sits under: the string its parent variable
    was registered with (`auto base = app.add_subcommand("base", ...)`), or
    the oem directory name for a file under ``pldmtool/oem/``."""
    parents = {r["var"]: r["name"] for r in regs if r["var"]}
    found = parents.get(reg["parent"])
    if found is not None:
        return found
    parts = PurePosixPath(path).parts
    if len(parts) > 2 and parts[1] == "oem":
        return f"oem-{parts[2]}"
    return reg["parent"]


def _class_for(text: str, var: str | None, name: str) -> str | None:
    if var:
        made = re.search(
            r"std::make_unique<(\w+)>\((?:[^()]|\([^()]*\))*?\b"
            + re.escape(var)
            + r"\s*\)",
            text,
            re.S,
        )
        if made:
            return made.group(1)
    for m in re.finditer(r"\bclass\s+(\w+)\s*:", text):
        if m.group(1).lower() == name.lower():
            return m.group(1)
    return None


def _constructor_span(text: str, class_name: str) -> tuple[int, int, bool] | None:
    """(first, last, explicit) 1-based lines of the class's constructor:
    from `explicit Class(` to the brace that closes its body, or the one
    `using CommandInterface::CommandInterface;` line (explicit False);
    None when neither."""
    decl = re.search(r"\bclass\s+" + re.escape(class_name) + r"\s*:", text)
    start = decl.start() if decl else 0
    ctor = re.compile(r"\bexplicit\s+" + re.escape(class_name) + r"\s*\(").search(
        text, start
    )
    if ctor:
        first = _line_of(text, ctor.start())
        brace = text.find("{", ctor.end())
        if brace < 0:
            return first, first, True
        depth, i = 0, brace
        while i < len(text):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        last = _line_of(text, i if i < len(text) else len(text) - 1)
        return first, last, True
    using = re.compile(r"using\s+CommandInterface::CommandInterface\s*;").search(
        text, start
    )
    if using:
        line = _line_of(text, using.start())
        return line, line, False
    return None


def _options(segment: str) -> list[Option]:
    opts = []
    for m in _OPTION_CALL.finditer(segment):
        end = segment.find(";", m.end())
        call = segment[m.start() : end if end >= 0 else len(segment)]
        joined = "".join(_LITERAL.findall(m.group("literals")))
        spellings = [s.strip() for s in joined.split(",") if s.strip()]
        if not spellings:
            continue
        transform = _TRANSFORM.search(call)
        opts.append(
            Option(
                spellings,
                required="->required()" in call.replace(" ", ""),
                flag=m.group("kind") == "flag",
                transform_map=transform.group(1) if transform else None,
            )
        )
    return opts


def _map_span(lines: list[str], map_name: str) -> tuple[int, int] | None:
    head = re.compile(r"\bstd::map<.*\b" + re.escape(map_name) + r"\s*\{")
    for i, line in enumerate(lines):
        if head.search(line):
            for j in range(i, min(len(lines), i + MAX_MAP_LINES)):
                if lines[j].strip() == "};":
                    return i + 1, j + 1
            return i + 1, min(len(lines), i + MAX_MAP_LINES)
    return None


def find(tree: code_mod.Tree, name: str) -> Match | None:
    """The subcommand registered as ``name`` (case-insensitive) in the
    tree's ``pldmtool/`` sources, with its class, constructor lines and
    options; None when no registration carries the name."""
    for rel in cpp_files(tree):
        path, lines = code_mod.read_lines(tree, rel)
        if lines and lines[-1] == "":
            lines.pop()
        text = "\n".join(lines)
        regs = _registrations(text)
        reg = next((r for r in regs if r["name"].lower() == name.lower()), None)
        if reg is None:
            continue
        match = Match(
            path, reg["name"], _type_of(reg, regs, path), reg["line"], reg["end"]
        )
        match.class_name = _class_for(text, reg["var"], reg["name"])
        if match.class_name is None:
            return match
        span = _constructor_span(text, match.class_name)
        if span is None:
            return match
        match.first, match.last, match.explicit = span
        segment = "\n".join(lines[match.first - 1 : match.last])
        match.options = _options(segment)
        for opt in match.options:
            if opt.transform_map and opt.transform_map not in match.map_lines:
                found = _map_span(lines, opt.transform_map)
                if found:
                    match.map_lines[opt.transform_map] = found
        return match
    return None


def _numbered(lines: list[str], first: int, last: int) -> list[str]:
    width = len(str(last))
    return [
        f"{str(n).rjust(width)}  {lines[n - 1]}".rstrip()
        for n in range(first, last + 1)
    ]


def describe(tree: code_mod.Tree, name: str, origin: str) -> list[str]:
    """The lines ``invocation`` prints for ``--subcommand name``."""
    match = find(tree, name)
    if match is None:
        return [f"subcommand: none in {SUBDIR}/"]
    path, lines = code_mod.read_lines(tree, match.path)
    if lines and lines[-1] == "":
        lines.pop()
    first, end = match.registration, match.registration_end
    where = f"{path}:{first}" if end == first else f"{path}:{first}-{end}"
    registration = " ".join(ln.strip() for ln in lines[first - 1 : end])
    out = [f"{tree.label} {where} | {registration}"]
    if match.first:
        shown = min(match.last, match.first + MAX_CONSTRUCTOR_LINES - 1)
        out.append(code_mod.cite(tree, path, match.first, shown, origin))
        out.extend(_numbered(lines, match.first, shown))
        if shown < match.last:
            more = match.last - shown
            out.append(f"({more} more lines of the constructor, to line {match.last})")
    for first, last in match.map_lines.values():
        out.append(code_mod.cite(tree, path, first, last, origin))
        out.extend(_numbered(lines, first, last))
    out.append(f"subcommand: {match.template()}")
    if match.explicit and not match.options:
        # a constructor that adds its options somewhere this parse does not
        # follow; a `using` constructor has none by design
        out.append("subcommand: options not read; see the lines above")
    out.append(note(tree, match))
    return out


def note(tree: code_mod.Tree, match: Match) -> str:
    """The line after the template naming the tree the spellings came from
    and how to check them on the target, whose pldmtool may be another
    version (ADR 0007)."""
    return (
        f"note: spellings of {tree.label} "
        f"({tree.provenance.label(tree.fetched_at)}); the target's pldmtool "
        f"may differ: check with pldmtool {match.type_} {match.name} --help"
    )

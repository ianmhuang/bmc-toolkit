"""The ``invocation`` command: a request's bytes arranged from its fields.

The Session reads a Command's request layout from the Document and hands
each field over as ``NAME:SIZE=VALUE``; this module lays the values out
over their sizes and prints the result in the syntax of the sending tools.
It knows no Document and no Command: what is wrong in the fields is wrong
in the line. A field it cannot lay out is refused rather than guessed, so a
printed line always holds exactly the bytes the fields add up to.

Nothing here touches the Catalog or the network, and nothing reads a
Document. The one Library read is ``--subcommand NAME`` for ``pldm``: the
held openbmc/pldm Code Tree is opened for the spelling of pldmtool's
subcommand and its options (:mod:`pldmtool`); the values in the line it
prints are placeholders, as every value here is the Session's.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

EXIT_OK = 0
EXIT_ACTION = 2

PROTOCOLS = ("ipmi", "mctp-control", "pldm", "spdm")
FORM = "NAME:SIZE=VALUE"
MAX_SIZE = 0xFFFF  # the most a 16-bit length field can state
FIELD_RE = re.compile(
    r"(?P<name>.*?):(?P<size>[0-9]+)(?::(?P<order>be|le))?=(?P<value>.*)", re.S
)
# \d on purpose: the lazy NAME match stops at the first ASCII :N=, so a
# NAME never holds one; what \d finds there is a SIZE written in digits
# outside [0-9], which FIELD_RE did not take as one
OTHER_SIZE_RE = re.compile(r":\d+(?::(?:be|le))?=")
HEX_RE = re.compile(r"0[xX][0-9a-fA-F]+")
DECIMAL_RE = re.compile(r"0+|[1-9][0-9]*")
PIECE = 600  # digits int() converts under any sys.set_int_max_str_digits()
SHIFT = 10**PIECE
WRITE_HEX = "write hex with 0x (0x0a), decimal without a leading zero"
NO_SIZE = f"SIZE, the field's bytes, is missing or not a number; a field is {FORM}"
SHOWN = 80  # characters of the caller's text a refusal echoes


class FieldError(ValueError):
    """A field that cannot be laid out; the message is the reason."""


@dataclass
class Field:
    name: str
    size: int
    tokens: list[int | str]  # one per byte, in layout order: a value or a placeholder


def _shown(text: str, quoted: bool = False) -> str:
    """The caller's text as a refusal echoes it: whole up to SHOWN
    characters, else cut there and followed by its length, so a field of
    any length gives a short line. SHOWN counts the caller's characters:
    a quoted head goes through repr, which spells a control character or
    a backslash as an escape, so it can show more than SHOWN; the line
    stays bounded all the same."""
    if len(text) <= SHOWN:
        return repr(text) if quoted else text
    head = repr(text[:SHOWN]) if quoted else text[:SHOWN]
    return f"{head}... ({len(text)} characters)"


def _is_number(text: str) -> bool:
    return bool(HEX_RE.fullmatch(text) or DECIMAL_RE.fullmatch(text))


def _decimal(text: str) -> int:
    # in pieces: int() refuses a decimal longer than the interpreter's limit
    first = len(text) % PIECE
    number = int(text[:first] or "0")
    for start in range(first, len(text), PIECE):
        number = number * SHIFT + int(text[start : start + PIECE])
    return number


def _number(text: str) -> int:
    if HEX_RE.fullmatch(text):
        return int(text, 16)
    if DECIMAL_RE.fullmatch(text):
        return _decimal(text)
    if text.startswith("-") and _is_number(text[1:]):
        raise FieldError(f"{_shown(text)} is negative")
    raise FieldError(f"{_shown(text, True)} is not a number: {WRITE_HEX}")


def _byte_list(value: str, size: int) -> list[int | str]:
    parts = [part.strip() for part in value.split(",")]
    out: list[int | str] = []
    for part in parts:
        # a bare 10 in a list of bytes may be meant as 0x10: never guessed
        if not HEX_RE.fullmatch(part) and part.strip("0"):
            raise FieldError(
                f"byte {_shown(part, True)} of the list: write every byte with 0x"
            )
        number = _number(part)
        if number > 0xFF:
            raise FieldError(f"{_shown(part)} of the list is more than one byte")
        out.append(number)
    if len(out) != size:
        raise FieldError(f"the list holds {len(out)} bytes, SIZE is {size}")
    return out


def parse_field(text: str) -> Field:
    """``NAME:SIZE=VALUE`` or ``NAME:SIZE:be=VALUE`` as a :class:`Field`."""
    found = FIELD_RE.fullmatch(text)
    if not found:
        if "=" not in text:
            raise FieldError(f"no =VALUE; a field is {FORM}")
        raise FieldError(NO_SIZE)
    # NAME may hold : and =, so a SIZE in digits of another script would be
    # read as part of a NAME that ends at a later :N=
    if OTHER_SIZE_RE.search(found["name"]):
        raise FieldError(NO_SIZE)
    name, value = found["name"].strip(), found["value"].strip()
    # digits are counted before int() reads them: it raises on very long ones
    digits = found["size"].lstrip("0")
    too_long = len(digits) > len(str(MAX_SIZE))
    size = MAX_SIZE + 1 if too_long else int(digits or "0")
    if not name:
        raise FieldError(f"no NAME; a field is {FORM}")
    if size < 1:
        raise FieldError("SIZE is 0; it is the number of bytes of the field")
    if size > MAX_SIZE:
        raise FieldError(f"SIZE is above {MAX_SIZE}, the most bytes a field takes")
    if not value:
        raise FieldError(f"no VALUE; a field is {FORM}")
    if value.startswith("<") or value.endswith(">"):
        inner = value[1:-1].strip()
        if not (value.startswith("<") and value.endswith(">") and inner):
            raise FieldError("a placeholder is written <text>")
        if "<" in inner or ">" in inner:
            raise FieldError(
                "a field takes one placeholder; give each placeholder its own field"
            )
        if size == 1:
            return Field(name, size, [f"<{inner}>"])
        return Field(name, size, [f"<{inner} {i}>" for i in range(size)])
    if "," in value:
        return Field(name, size, _byte_list(value, size))
    if any(ch.isspace() for ch in value):
        raise FieldError(
            "a list of bytes is separated by commas (0x00,0x10); "
            "one number has no space"
        )
    # a decimal of d digits is at least 2**(3*(d-1)): one far too long for
    # SIZE is refused by its length, before the number is built
    value_digits = len(value.lstrip("0")) if DECIMAL_RE.fullmatch(value) else 0
    misfit = f"{_shown(value)} does not fit {size} byte{'s' if size > 1 else ''}"
    if 3 * (value_digits - 1) >= 8 * size:
        raise FieldError(misfit)
    number = _number(value)
    if number.bit_length() > 8 * size:
        raise FieldError(misfit)
    order = "big" if found["order"] == "be" else "little"
    return Field(name, size, list(number.to_bytes(size, order)))


def _plain(token: int | str) -> str:
    return token if isinstance(token, str) else f"{token:02x}"


def _prefixed(token: int | str) -> str:
    # a placeholder stands for two hex digits: ipmitool and pldmtool read a
    # bare 30 as decimal and refuse 08 as octal, so it takes the 0x too
    return f"0x{token}" if isinstance(token, str) else f"0x{token:02x}"


def tool_lines(protocol: str, fields: list[Field]) -> list[str]:
    """The Invocation line(s) of ``protocol`` for the bytes of ``fields``."""
    tokens = [token for field in fields for token in field.tokens]
    plain = " ".join(_plain(t) for t in tokens)
    prefixed = " ".join(_prefixed(t) for t in tokens)
    if protocol == "ipmi":
        return [f"ipmitool raw {prefixed}"]
    kind = "control" if protocol == "mctp-control" else protocol
    lines = [f"mctp-client eid <eid> type {kind} data {plain}"]
    if protocol == "pldm":
        lines.append(f"pldmtool raw -m <eid> -d {prefixed}")
    return lines


def render(protocol: str, texts: list[str]) -> list[str]:
    """What the command prints for the fields ``texts``; raises
    :class:`FieldError` naming the first one that cannot be laid out."""
    if protocol not in PROTOCOLS:
        raise FieldError(
            f"unknown protocol {_shown(protocol, True)}; "
            f"it is one of {', '.join(PROTOCOLS)}"
        )
    if not texts:
        raise FieldError(f"no field given; a field is {FORM}")
    fields = []
    for text in texts:
        try:
            fields.append(parse_field(text))
        except FieldError as exc:
            raise FieldError(f"field {_shown(text, True)}: {exc}") from None
    if protocol == "ipmi":
        if len(fields) < 2:
            raise FieldError("ipmi: the first two fields are NetFn and Cmd")
        for field, text in zip(fields[:2], texts[:2], strict=True):
            if field.size != 1:
                raise FieldError(
                    f"field {_shown(text, True)}: NetFn and Cmd are one byte each"
                )
    show = _prefixed if protocol == "ipmi" else _plain
    out = [f"bytes: {sum(field.size for field in fields)}"]
    out.extend(tool_lines(protocol, fields))
    out.append("offset | size | field | bytes")
    offset = 0
    for field in fields:
        shown = " ".join(show(t) for t in field.tokens)
        out.append(f"{offset} | {field.size} | {field.name} | {shown}")
        offset += field.size
    return out


NOT_HELD = "subcommand: pldm Code Tree not held; clone pldm"


def cmd_invocation(args, tree_for: Callable[..., tuple] | None = None) -> int:
    """``tree_for(args)`` gives (Tree, origin URL) of the held openbmc/pldm
    Code Tree for ``--subcommand``, or raises ``code.CodeError``; the CLI
    supplies it, a bare call has none and prints the not-held line."""
    try:
        lines = render(args.protocol, args.fields)
    except FieldError as exc:
        print(f"invocation: {exc}")
        return EXIT_ACTION
    name = getattr(args, "subcommand", None)
    if name is not None and args.protocol != "pldm":
        print(f"invocation: --subcommand is for pldm, not {args.protocol}")
        return EXIT_ACTION
    print("\n".join(lines))
    if name is None:
        return EXIT_OK
    from . import pldmtool
    from .code import CodeError

    try:
        if tree_for is None:
            raise CodeError("no Library")
        tree, origin = tree_for(args)
        print("\n".join(pldmtool.describe(tree, name, origin)))
    except CodeError as exc:
        message = str(exc)
        if (
            "not held" in message
            or "not in the Library" in message
            or "no Library" in message
        ):
            print(not_held_line(message))
        else:
            print(f"subcommand: {exc}")
    return EXIT_OK


def not_held_line(message: str) -> str:
    """The not-held line with the clone the tree selector asked for: its
    message ends in ``run: bmcspec clone pldm [--release X]`` when a
    config Release is not held, and a plain ``clone pldm`` would not
    satisfy that selection."""
    _, found, hint = message.partition("run: bmcspec ")
    if found and hint.strip():
        return f"subcommand: pldm Code Tree not held; {hint.strip()}"
    return NOT_HELD


def reorder_argv(argv: list[str]) -> list[str]:
    """``--subcommand NAME`` moved to just after ``invocation``. argparse
    before CPython 3.12.7 / 3.13 (3.11 never got the fix, gh-59317) reads
    ``invocation pldm --subcommand NAME FIELD...`` with an empty FIELD list
    and refuses the fields as unrecognized; the option before the
    positionals parses the same everywhere."""
    if "invocation" not in argv:
        return argv
    at = argv.index("invocation")
    head, rest = argv[: at + 1], argv[at + 1 :]
    option, tail, i = [], [], 0
    while i < len(rest):
        tok = rest[i]
        if tok == "--subcommand" and i + 1 < len(rest):
            option = [tok, rest[i + 1]]
            i += 2
            continue
        if tok.startswith("--subcommand="):
            option = [tok]
            i += 1
            continue
        tail.append(tok)
        i += 1
    return head + option + tail


COMMANDS: dict[str, Callable[..., int]] = {"invocation": cmd_invocation}


def add_parsers(sub) -> None:
    p = sub.add_parser(
        "invocation", help="a request's bytes from its fields, in each tool's syntax"
    )
    p.add_argument("protocol", help=" | ".join(PROTOCOLS))
    p.add_argument(
        "--subcommand",
        metavar="NAME",
        help="pldm only: pldmtool's subcommand for the Command, read from the "
        "held openbmc/pldm Code Tree (its source lines, a code cite and a "
        "template with placeholders)",
    )
    p.add_argument(
        "fields",
        nargs="*",
        metavar="FIELD",
        help=f"{FORM}, in the order of the request (NAME:SIZE:be=VALUE: "
        "most significant byte first)",
    )

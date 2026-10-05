"""The ``invocation`` command: a request's bytes arranged from its fields.

The Session reads a Command's request layout from the Document and hands
each field over as ``NAME:SIZE=VALUE``; this module lays the values out
over their sizes and prints the result in the syntax of the sending tools.
It knows no Document and no Command: what is wrong in the fields is wrong
in the line. A field it cannot lay out is refused rather than guessed, so a
printed line always holds exactly the bytes the fields add up to.

Nothing here touches the Library, the Catalog or the network.
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
    r"(?P<name>.*?):(?P<size>\d+)(?::(?P<order>be|le))?=(?P<value>.*)", re.S
)
HEX_RE = re.compile(r"0[xX][0-9a-fA-F]+")
DECIMAL_RE = re.compile(r"0+|[1-9]\d*")
WRITE_HEX = "write hex with 0x (0x0a), decimal without a leading zero"


class FieldError(ValueError):
    """A field that cannot be laid out; the message is the reason."""


@dataclass
class Field:
    name: str
    size: int
    tokens: list[int | str]  # one per byte, in layout order: a value or a placeholder


def _number(text: str) -> int:
    if HEX_RE.fullmatch(text):
        return int(text, 16)
    if DECIMAL_RE.fullmatch(text):
        try:
            return int(text)
        except ValueError:  # more digits than int() converts
            raise FieldError(
                f"a decimal of {len(text)} digits is too long to read: "
                "write the value in hex with 0x"
            ) from None
    if text.startswith("-"):
        raise FieldError(f"{text} is negative")
    raise FieldError(f"{text!r} is not a number: {WRITE_HEX}")


def _byte_list(value: str, size: int) -> list[int | str]:
    parts = [part.strip() for part in value.split(",")]
    out: list[int | str] = []
    for part in parts:
        # a bare 10 in a list of bytes may be meant as 0x10: never guessed
        if not HEX_RE.fullmatch(part) and part.strip("0"):
            raise FieldError(f"byte {part!r} of the list: write every byte with 0x")
        number = _number(part)
        if number > 0xFF:
            raise FieldError(f"{part} of the list is more than one byte")
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
        raise FieldError(
            f"SIZE, the field's bytes, is missing or not a number; a field is {FORM}"
        )
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
    number = _number(value)
    if number.bit_length() > 8 * size:
        raise FieldError(f"{value} does not fit {size} byte{'s' if size > 1 else ''}")
    order = "big" if found["order"] == "be" else "little"
    return Field(name, size, list(number.to_bytes(size, order)))


def _plain(token: int | str) -> str:
    return token if isinstance(token, str) else f"{token:02x}"


def _prefixed(token: int | str) -> str:
    return token if isinstance(token, str) else f"0x{token:02x}"


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
            f"unknown protocol {protocol!r}; it is one of {', '.join(PROTOCOLS)}"
        )
    if not texts:
        raise FieldError(f"no field given; a field is {FORM}")
    fields = []
    for text in texts:
        try:
            fields.append(parse_field(text))
        except FieldError as exc:
            raise FieldError(f"field {text!r}: {exc}") from None
    if protocol == "ipmi":
        if len(fields) < 2:
            raise FieldError("ipmi: the first two fields are NetFn and Cmd")
        for field, text in zip(fields[:2], texts[:2], strict=True):
            if field.size != 1:
                raise FieldError(f"field {text!r}: NetFn and Cmd are one byte each")
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


def cmd_invocation(args) -> int:
    try:
        lines = render(args.protocol, args.fields)
    except FieldError as exc:
        print(f"invocation: {exc}")
        return EXIT_ACTION
    print("\n".join(lines))
    return EXIT_OK


COMMANDS: dict[str, Callable[..., int]] = {"invocation": cmd_invocation}


def add_parsers(sub) -> None:
    p = sub.add_parser(
        "invocation", help="a request's bytes from its fields, in each tool's syntax"
    )
    p.add_argument("protocol", help=" | ".join(PROTOCOLS))
    p.add_argument(
        "fields",
        nargs="*",
        metavar="FIELD",
        help=f"{FORM}, in the order of the request (NAME:SIZE:be=VALUE: "
        "most significant byte first)",
    )

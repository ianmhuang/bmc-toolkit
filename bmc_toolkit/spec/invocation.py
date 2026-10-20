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

``nc-si`` is the one protocol whose header is built here: the Session
gives the Control Packet Type, package, channel and IID as options and
the payload as fields, and the DSP0222 header, Payload Length, padding
and checksum are fixed-format arithmetic over those bytes (ADR 0008 of
the design workspace).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

EXIT_OK = 0
EXIT_ACTION = 2

PROTOCOLS = ("ipmi", "mctp-control", "nc-si", "pldm", "spdm")
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


def _parse_all(texts: list[str]) -> list[Field]:
    fields = []
    for text in texts:
        try:
            fields.append(parse_field(text))
        except FieldError as exc:
            raise FieldError(f"field {_shown(text, True)}: {exc}") from None
    return fields


def render(
    protocol: str, texts: list[str], header: NcsiHeader | None = None
) -> list[str]:
    """What the command prints for the fields ``texts``; raises
    :class:`FieldError` naming the first one that cannot be laid out.
    ``header`` is the NC-SI header's options, for ``nc-si`` only."""
    if protocol not in PROTOCOLS:
        raise FieldError(
            f"unknown protocol {_shown(protocol, True)}; "
            f"it is one of {', '.join(PROTOCOLS)}"
        )
    if protocol == "nc-si":
        if header is None:
            raise FieldError("nc-si takes --type, --package and --channel")
        return render_ncsi(header, texts)
    if not texts:
        raise FieldError(f"no field given; a field is {FORM}")
    fields = _parse_all(texts)
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


# ---------------------------------------------------------------- nc-si
# DSP0222 1.2.1 Table 10 (header), 8.2.2.2 (padding), 8.2.2.3 (checksum);
# the ncsi-cmd syntax is phosphor-networkd 1c55a45 src/ncsi_cmd.cpp

NCSI_OPTIONS = ("type", "package", "channel", "iid")
NCSI_MAX_PAYLOAD = 0xFFF  # Payload Length is 12 bits
NETLINK = "ncsi-cmd -i <ifindex in hex>"
OVER_MCTP = "ncsi-cmd -m <eid in decimal>"
NOTE_NUMBERS = (
    "note: ncsi-cmd reads -i, -p, -c, TYPE and every payload byte as hex "
    "without 0x, so an ifindex written in decimal (10 for 0x0a) reaches "
    "another interface; -m takes [NET,]EID in decimal"
)
NOTE_IID = (
    "note: the IID (packet byte 3) is 0x01..0xff and differs from the "
    "previous command's, or the controller takes the packet as a retry "
    "(DSP0222 6.2.2.2); ncsi-cmd picks its own"
)
NOTE_CHANNEL = (
    "note: Channel ID is the package in bits 7..5 and the channel in bits "
    "4..0 (channel 0x1f: the whole package)"
)
NOTE_CHECKSUM = (
    "note: checksum 00 00 00 00: the packet holds placeholders, and zero "
    "means no checksum (DSP0222 8.2.2.3); give every value to have it computed"
)


@dataclass
class NcsiHeader:
    type: int
    package: int | str
    channel: int | str
    iid: int | str


def _ncsi_option(flag: str, text: str, low: int, high: int, what: str) -> int | str:
    """One header option: a number in low..high, or a ``<placeholder>``."""
    if text.startswith("<") or text.endswith(">"):
        inner = text[1:-1].strip()
        if not (text.startswith("<") and text.endswith(">") and inner):
            raise FieldError(f"{flag}: a placeholder is written <text>")
        if "<" in inner or ">" in inner:
            raise FieldError(f"{flag}: a placeholder holds no < or >")
        return f"<{inner}>"
    try:
        number = _number(text)
    except FieldError as exc:
        raise FieldError(f"{flag}: {exc}") from None
    if not low <= number <= high:
        raise FieldError(f"{flag} {_shown(text)}: {what}")
    return number


def ncsi_header(args) -> NcsiHeader | None:
    """The NC-SI header options of ``args``: None for another protocol,
    which must not carry them."""
    given = [name for name in NCSI_OPTIONS if getattr(args, name, None) is not None]
    if args.protocol != "nc-si":
        if given and args.protocol in PROTOCOLS:
            raise FieldError(f"--{given[0]} is for nc-si, not {args.protocol}")
        return None
    for name, what in (
        ("type", "the Control Packet Type"),
        ("package", "the package"),
        ("channel", "the channel, or package"),
    ):
        if name not in given:
            raise FieldError(f"nc-si: --{name}, {what}, is missing")
    kind = _ncsi_option(
        "--type",
        args.type,
        0,
        0x7F,
        "the Control Packet Type is 0x00..0x7f (bit 7 marks a response)",
    )
    if isinstance(kind, str):
        raise FieldError(
            "--type: the Control Packet Type is a number, not a placeholder"
        )
    package = _ncsi_option(
        "--package", args.package, 0, 7, "a package is 0..7 (Channel ID bits 7..5)"
    )
    channel = (
        0x1F
        if args.channel == "package"
        else _ncsi_option(
            "--channel",
            args.channel,
            0,
            0x1F,
            "a channel is 0x00..0x1f, or package (0x1f) for the whole package",
        )
    )
    iid = (
        "<iid>"
        if args.iid is None
        else _ncsi_option("--iid", args.iid, 1, 0xFF, "the IID is 0x01..0xff")
    )
    return NcsiHeader(kind, package, channel, iid)


def _hex_option(value: int | str) -> str:
    # a package or channel is said in decimal ("channel 10"), and ncsi-cmd
    # reads -p and -c as hex: the placeholder says so, as <ifindex in hex>
    if not isinstance(value, str):
        return f"{value:02x}"
    return value if value[:-1].endswith(" in hex") else f"{value[:-1]} in hex>"


def ncsi_checksum(data: bytes) -> int:
    """DSP0222 8.2.2.3: the two's complement of the 32-bit sum of the
    header and payload read as 16-bit big-endian words; an odd last byte
    pairs with the zero padding byte after it."""
    data += bytes(len(data) % 2)
    total = sum(int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2))
    return -total & 0xFFFFFFFF


def render_ncsi(header: NcsiHeader, texts: list[str]) -> list[str]:
    """What ``invocation nc-si`` prints: the ncsi-cmd lines, which carry
    the payload alone, and the whole packet from MC ID for mctp-client."""
    fields = _parse_all(texts)
    size = sum(field.size for field in fields)
    if size > NCSI_MAX_PAYLOAD:
        raise FieldError(
            f"the payload is {size} bytes; Payload Length holds at most "
            f"{NCSI_MAX_PAYLOAD} (0xfff)"
        )
    known = isinstance(header.package, int) and isinstance(header.channel, int)
    channel_id = header.package << 5 | header.channel if known else "<channel id>"
    parts: list[tuple[str, list[int | str]]] = [
        ("MC ID", [0x00]),
        ("Header Revision", [0x01]),
        ("Reserved", [0x00]),
        ("IID", [header.iid]),
        ("Control Packet Type", [header.type]),
        ("Channel ID", [channel_id]),
        ("Flags and Payload Length", list(size.to_bytes(2, "big"))),
        ("Reserved", [0x00] * 8),
    ]
    parts.extend((field.name, field.tokens) for field in fields)
    summed = [token for _, tokens in parts for token in tokens]
    placeholders = any(isinstance(token, str) for token in summed)
    if size % 4:
        parts.append(("Padding", [0x00] * (4 - size % 4)))
    checksum = 0 if placeholders else ncsi_checksum(bytes(summed))
    parts.append(("Checksum", list(checksum.to_bytes(4, "big"))))
    payload = [token for field in fields for token in field.tokens]
    options = " ".join(
        ["-p", _hex_option(header.package), "-c", _hex_option(header.channel), "raw"]
        + [_plain(token) for token in (header.type, *payload)]
    )
    packet = [token for _, tokens in parts for token in tokens]
    out = [
        f"payload bytes: {size}",
        f"packet bytes: {len(packet)}",
        f"{NETLINK} {options}",
        f"{OVER_MCTP} {options}",
        f"mctp-client eid <eid> type nc-si data {' '.join(map(_plain, packet))}",
        NOTE_NUMBERS,
        NOTE_IID,
    ]
    if not known:
        out.append(NOTE_CHANNEL)
    if placeholders:
        out.append(NOTE_CHECKSUM)
    out.append("offset | size | field | bytes")
    offset = 0
    for name, tokens in parts:
        out.append(
            f"{offset} | {len(tokens)} | {name} | {' '.join(map(_plain, tokens))}"
        )
        offset += len(tokens)
    return out


NOT_HELD = "subcommand: pldm Code Tree not held; clone pldm"


def cmd_invocation(args, tree_for: Callable[..., tuple] | None = None) -> int:
    """``tree_for(args)`` gives (Tree, origin URL) of the held openbmc/pldm
    Code Tree for ``--subcommand``, or raises ``code.CodeError``; the CLI
    supplies it, a bare call has none and prints the not-held line."""
    try:
        lines = render(args.protocol, args.fields, ncsi_header(args))
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


MOVED_OPTIONS = ("--subcommand", *(f"--{name}" for name in NCSI_OPTIONS))


def reorder_argv(argv: list[str]) -> list[str]:
    """``--subcommand NAME`` and the nc-si options moved to just after
    ``invocation``. argparse before CPython 3.12.7 / 3.13 (3.11 never got
    the fix, gh-59317) reads ``invocation pldm --subcommand NAME FIELD...``
    with an empty FIELD list and refuses the fields as unrecognized; the
    options before the positionals parse the same everywhere."""
    if "invocation" not in argv:
        return argv
    at = argv.index("invocation")
    head, rest = argv[: at + 1], argv[at + 1 :]
    options, tail, i = [], [], 0
    while i < len(rest):
        tok = rest[i]
        if tok in MOVED_OPTIONS and i + 1 < len(rest):
            options += [tok, rest[i + 1]]
            i += 2
            continue
        if tok.startswith(tuple(f"{name}=" for name in MOVED_OPTIONS)):
            options.append(tok)
            i += 1
            continue
        tail.append(tok)
        i += 1
    return head + options + tail


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
        "--type",
        metavar="T",
        help="nc-si only: the Control Packet Type (0x00..0x7f)",
    )
    p.add_argument("--package", metavar="P", help="nc-si only: the package (0..7)")
    p.add_argument(
        "--channel",
        metavar="C",
        help="nc-si only: the channel (0x00..0x1f), or package for the whole package",
    )
    p.add_argument(
        "--iid",
        metavar="I",
        help="nc-si only: the Instance ID (0x01..0xff); <iid> when not given",
    )
    p.add_argument(
        "fields",
        nargs="*",
        metavar="FIELD",
        help=f"{FORM}, in the order of the request (NAME:SIZE:be=VALUE: "
        "most significant byte first)",
    )

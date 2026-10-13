"""Reviewer acceptance tests for the ``invocation`` command (AC-1 to AC-5).

Black box: every test calls the CLI entry point with ``invocation PROTOCOL
FIELD ...`` and reads what it prints. The expected bytes are written out by
hand or computed here with ``int.to_bytes``, never taken from the module
under test. Hex digits are compared without regard to case, and a field row
is read as ``offset | size | name | bytes`` (the form docs/COMMANDS.md
gives), with ``0x`` in the bytes cell allowed.

On develop the subcommand does not exist: argparse leaves through
SystemExit before anything is printed, so every test fails there.
"""

import random
import re

import pytest

from bmc_toolkit.spec.cli import main

TOOLS = ("ipmitool", "mctp-client", "pldmtool")
PROTOCOLS = ("ipmi", "mctp-control", "pldm", "spdm")
IPMITOOL = "ipmitool raw "
PLDMTOOL = "pldmtool raw -m <eid> -d "
# a placeholder is one token even with spaces inside
TOKEN = re.compile(r"<[^>]*>|\S+")


def mctp(kind: str) -> str:
    return f"mctp-client eid <eid> type {kind} data "


def invoke(capsys, *argv):
    """(exit code, stdout lines, everything printed)."""
    code = main(["invocation", *argv])
    got = capsys.readouterr()
    return code, got.out.splitlines(), got.out + got.err


def sent(lines: list[str]) -> list[str]:
    """The Invocation lines: the lines that start with a sending tool."""
    return [ln for ln in lines if ln.split(" ")[0] in TOOLS]


def data(line: str, prefix: str) -> list[str]:
    """The byte tokens of an Invocation line, after the tool's own words."""
    assert line.startswith(prefix), line
    return TOKEN.findall(line[len(prefix) :])


def bare(tokens: list[str]) -> list[str]:
    """Tokens as two lower-case hex digits; a placeholder stays as it is."""
    out = []
    for token in tokens:
        if token.startswith("<"):
            out.append(token)
            continue
        low = token.lower()
        out.append(low[2:] if low.startswith("0x") else low)
    return out


def rows(lines: list[str]) -> list[list[str]]:
    """The field rows after the last Invocation line, cut at ``|``. A heading
    row has no offset number and is not a field."""
    last = max(i for i, ln in enumerate(lines) if ln.split(" ")[0] in TOOLS)
    found = []
    for line in lines[last + 1 :]:
        cells = [cell.strip() for cell in line.split("|")]
        if cells[0].isdigit():
            found.append(cells)
    return found


# 20 bytes with a run of seven and a run of three 00: the shape of request
# the change exists for
LONG = [
    "SPDMVersion:1=0x12",
    "RequestResponseCode:1=0xe1",
    "Param1:1=0",
    "Param2:1=0",
    "Reserved:1=0",
    "CTExponent:1=0x0c",
    "Reserved2:2=0",
    "Flags:4=0",
    "DataTransferSize:4=0x1200",
    "MaxSPDMmsgSize:4=0x1200",
]
LONG_DATA = "12 e1 00 00 00 0c 00 00 00 00 00 00 00 12 00 00 00 12 00 00"


# ------------------------------------------------------------------ AC-1


def test_ipmi_is_one_ipmitool_raw_line_with_0x_on_every_byte(capsys):
    code, lines, _ = invoke(
        capsys,
        "ipmi",
        "NetFn:1=0x0a",
        "Cmd:1=0x43",
        "Reservation ID:2=0x1234",
        "Record ID:2=0xffff",
        "Offset into record:1=0",
        "Bytes to read:1=0xff",
    )
    assert code == 0, lines
    assert [ln.lower() for ln in sent(lines)] == [
        "ipmitool raw 0x0a 0x43 0x34 0x12 0xff 0xff 0x00 0xff"
    ]


def test_mctp_control_is_one_mctp_client_line_of_type_control(capsys):
    code, lines, _ = invoke(
        capsys,
        "mctp-control",
        "Rq D Instance ID:1=0x80",
        "Command Code:1=0x04",
        "Message Type Number:1=0xff",
    )
    assert code == 0, lines
    assert [ln.lower() for ln in sent(lines)] == [
        "mctp-client eid <eid> type control data 80 04 ff"
    ]


def test_spdm_is_one_mctp_client_line_of_type_spdm_with_every_zero(capsys):
    code, lines, _ = invoke(capsys, "spdm", *LONG)
    assert code == 0, lines
    assert len(LONG_DATA.split()) == 20
    assert [ln.lower() for ln in sent(lines)] == [
        "mctp-client eid <eid> type spdm data " + LONG_DATA
    ]


@pytest.mark.parametrize("size", [1, 11, 12, 31, 32, 33])
def test_a_run_of_zero_bytes_is_as_long_as_the_field(capsys, size):
    code, lines, _ = invoke(
        capsys, "spdm", "Code:1=0x84", f"Reserved:{size}=0", "Tail:1=0x01"
    )
    assert code == 0, lines
    (line,) = sent(lines)
    assert bare(data(line, mctp("spdm"))) == ["84"] + ["00"] * size + ["01"]
    assert lines[0] == f"bytes: {size + 2}"


def test_pldm_prints_mctp_client_and_pldmtool_with_the_same_bytes(capsys):
    code, lines, _ = invoke(
        capsys,
        "pldm",
        "Header:1=0x80",
        "PLDM Type:1=0x02",
        "Command Code:1=0x11",
        "sensorID:2=0x00a5",
        "rearmEventState:1=0",
    )
    assert code == 0, lines
    assert sorted(ln.lower() for ln in sent(lines)) == [
        "mctp-client eid <eid> type pldm data 80 02 11 a5 00 00",
        "pldmtool raw -m <eid> -d 0x80 0x02 0x11 0xa5 0x00 0x00",
    ]


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_no_citation_line_is_printed(capsys, protocol):
    code, lines, _ = invoke(capsys, protocol, "First:1=0x06", "Second:1=0x01")
    assert code == 0, lines
    assert sent(lines)
    assert not [ln for ln in lines if ln.lstrip().startswith("cite:")]


def _random_request(rng: random.Random, protocol: str):
    """Fields in every way AC-2 allows, and the bytes they must become."""
    texts, expected = [], []
    if protocol == "ipmi":
        for name in ("NetFn", "Cmd"):
            value = rng.randrange(256)
            texts.append(f"{name}:1=0x{value:02x}")
            expected.append(value)
    for index in range(rng.randint(1, 12)):
        size = rng.randint(1, 8)
        # zero often, so that long runs of 00 come up
        value = 0 if rng.random() < 0.4 else rng.randrange(256**size)
        name = f"Field {index}"
        kind = rng.choice(("le", "plain", "be", "list"))
        written = str(value) if rng.random() < 0.5 else hex(value)
        if kind == "list" and size > 1:
            layout = [rng.randrange(256) for _ in range(size)]
            written = ",".join(f"0x{b:02x}" for b in layout)
            texts.append(f"{name}:{size}={written}")
        elif kind == "be":
            layout = list(value.to_bytes(size, "big"))
            texts.append(f"{name}:{size}:be={written}")
        else:
            layout = list(value.to_bytes(size, "little"))
            texts.append(f"{name}:{size}={written}")
        expected.extend(layout)
    return texts, [f"{b:02x}" for b in expected]


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_every_line_holds_the_bytes_of_the_fields_in_the_order_given(capsys, protocol):
    rng = random.Random(27)
    for _ in range(25):
        texts, expected = _random_request(rng, protocol)
        code, lines, _ = invoke(capsys, protocol, *texts)
        assert code == 0, (texts, lines)
        assert lines[0] == f"bytes: {len(expected)}", texts
        got = sent(lines)
        if protocol == "ipmi":
            assert len(got) == 1, got
            tokens = data(got[0], IPMITOOL)
            assert all(t.lower().startswith("0x") for t in tokens), got
            assert bare(tokens) == expected, texts
            continue
        kind = "control" if protocol == "mctp-control" else protocol
        client = [ln for ln in got if ln.startswith("mctp-client ")]
        assert len(client) == 1, got
        tokens = data(client[0], mctp(kind))
        assert all(len(t) == 2 for t in tokens), client
        assert bare(tokens) == expected, texts
        tool = [ln for ln in got if ln.startswith("pldmtool ")]
        assert len(got) == len(client) + len(tool)
        if protocol == "pldm":
            assert len(tool) == 1, got
            tokens = data(tool[0], PLDMTOOL)
            assert all(t.lower().startswith("0x") for t in tokens), tool
            assert bare(tokens) == expected, texts
        else:
            assert not tool, got


# ------------------------------------------------------------------ AC-2


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("DataTransferSize:4=0x1200", "00 12 00 00"),  # hex, least significant first
        ("DataTransferSize:4=4608", "00 12 00 00"),  # the same number in decimal
        ("Count:1=23", "17"),  # a bare number is decimal
        ("Port:2=623", "6f 02"),
        ("Port:2:be=623", "02 6f"),  # most significant byte first
        ("Length:3=0x012345", "45 23 01"),
        ("Length:3:be=0x012345", "01 23 45"),
        ("Small:4=1", "01 00 00 00"),
        ("Small:4:be=1", "00 00 00 01"),
        ("Mask:2=0xffff", "ff ff"),  # the largest value that fits
        ("Mask:2=65535", "ff ff"),
        ("Nonce:8=0", "00 00 00 00 00 00 00 00"),
        ("IP Address:4=0xc0,0xa8,0x01,0x0a", "c0 a8 01 0a"),  # a list, as written
        ("MAC address:6=0x00,0x1b,0x21,0x3c,0x4d,0x5e", "00 1b 21 3c 4d 5e"),
        ("Request Data byte 1:1=0x7f", "7f"),  # a name with spaces
    ],
)
def test_a_value_is_laid_out_over_the_size_of_its_field(capsys, field, expected):
    code, lines, _ = invoke(capsys, "spdm", field)
    assert code == 0, lines
    (line,) = sent(lines)
    assert bare(data(line, mctp("spdm"))) == expected.split()
    assert lines[0] == f"bytes: {len(expected.split())}"


def test_a_name_with_spaces_is_kept_whole_in_its_row(capsys):
    code, lines, _ = invoke(
        capsys,
        "ipmi",
        "NetFn:1=0x0c",
        "Cmd:1=0x01",
        "Channel number:1=1",
        "IP Address:4=0xc0,0xa8,0x01,0x0a",
    )
    assert code == 0, lines
    assert [ln.lower() for ln in sent(lines)] == [
        "ipmitool raw 0x0c 0x01 0x01 0xc0 0xa8 0x01 0x0a"
    ]
    assert [row[2] for row in rows(lines)] == [
        "NetFn",
        "Cmd",
        "Channel number",
        "IP Address",
    ]


# ------------------------------------------------------------------ AC-3


def test_a_one_byte_placeholder_is_printed_as_written_for_ipmitool(capsys):
    code, lines, _ = invoke(
        capsys, "ipmi", "NetFn:1=0x04", "Cmd:1=0x27", "Sensor Number:1=<sensor number>"
    )
    assert code == 0, lines
    # no 0x in front of it: it is not a number
    assert sent(lines) == ["ipmitool raw 0x04 0x27 <sensor number>"]
    assert lines[0] == "bytes: 3"


def test_a_one_byte_placeholder_is_printed_as_written_for_mctp_client(capsys):
    code, lines, _ = invoke(
        capsys,
        "spdm",
        "SPDMVersion:1=<negotiated version>",
        "RequestResponseCode:1=0x84",
        "Param1:1=0",
        "Param2:1=0",
    )
    assert code == 0, lines
    assert sent(lines) == [
        "mctp-client eid <eid> type spdm data <negotiated version> 84 00 00"
    ]
    assert lines[0] == "bytes: 4"


def test_a_placeholder_of_n_bytes_is_n_numbered_tokens_in_both_pldm_lines(capsys):
    code, lines, _ = invoke(
        capsys,
        "pldm",
        "Header:1=0x80",
        "PLDM Type:1=0x02",
        "Command Code:1=0x11",
        "sensorID:2=<sensor id>",
        "rearmEventState:1=0",
    )
    assert code == 0, lines
    assert sorted(sent(lines)) == [
        "mctp-client eid <eid> type pldm data 80 02 11 <sensor id 0> <sensor id 1> 00",
        "pldmtool raw -m <eid> -d 0x80 0x02 0x11 <sensor id 0> <sensor id 1> 0x00",
    ]
    assert lines[0] == "bytes: 6"


@pytest.mark.parametrize("order", ["", ":be"])
def test_a_long_placeholder_keeps_one_token_per_byte(capsys, order):
    code, lines, _ = invoke(
        capsys,
        "ipmi",
        "NetFn:1=0x06",
        "Cmd:1=0x01",
        f"Address:4{order}=<address>",
        "Last:1=0x77",
    )
    assert code == 0, lines
    (line,) = sent(lines)
    tokens = data(line, IPMITOOL)
    assert tokens == [
        "0x06",
        "0x01",
        "<address 0>",
        "<address 1>",
        "<address 2>",
        "<address 3>",
        "0x77",
    ]
    assert lines[0] == f"bytes: {len(tokens)}"


# ------------------------------------------------------------------ AC-4


def test_the_total_is_first_then_the_line_then_a_row_per_field(capsys):
    code, lines, _ = invoke(capsys, "spdm", *LONG)
    assert code == 0, lines
    assert lines[0] == "bytes: 20"
    assert [i for i, ln in enumerate(lines) if ln.split(" ")[0] in TOOLS] == [1]
    found = rows(lines)
    assert [row[:3] for row in found] == [
        ["0", "1", "SPDMVersion"],
        ["1", "1", "RequestResponseCode"],
        ["2", "1", "Param1"],
        ["3", "1", "Param2"],
        ["4", "1", "Reserved"],
        ["5", "1", "CTExponent"],
        ["6", "2", "Reserved2"],
        ["8", "4", "Flags"],
        ["12", "4", "DataTransferSize"],
        ["16", "4", "MaxSPDMmsgSize"],
    ]
    assert all(len(row) == 4 for row in found), found
    assert [bare(TOKEN.findall(row[3])) for row in found] == [
        ["12"],
        ["e1"],
        ["00"],
        ["00"],
        ["00"],
        ["0c"],
        ["00", "00"],
        ["00", "00", "00", "00"],
        ["00", "12", "00", "00"],
        ["00", "12", "00", "00"],
    ]


def test_the_rows_put_together_are_the_bytes_of_the_line(capsys):
    code, lines, _ = invoke(
        capsys,
        "mctp-control",
        "Header:1=0x80",
        "Command Code:1=0x01",
        "Operation:1=<operation>",
        "Endpoint ID:1=9",
        "Vendor:3:be=0x0a0b0c",
        "Blob:2=0xde,0xad",
        "Handle:4=<handle>",
    )
    assert code == 0, lines
    (line,) = sent(lines)
    found = rows(lines)
    assert [row[0] for row in found] == ["0", "1", "2", "3", "4", "7", "9"]
    assert [row[1] for row in found] == ["1", "1", "1", "1", "3", "2", "4"]
    joined = [token for row in found for token in bare(TOKEN.findall(row[3]))]
    assert joined == bare(data(line, mctp("control")))
    assert joined == [
        "80",
        "01",
        "<operation>",
        "09",
        "0a",
        "0b",
        "0c",
        "de",
        "ad",
        "<handle 0>",
        "<handle 1>",
        "<handle 2>",
        "<handle 3>",
    ]
    assert lines[0] == "bytes: 13"


def test_ipmi_counts_netfn_and_cmd_as_two_of_the_bytes(capsys):
    code, lines, _ = invoke(capsys, "ipmi", "NetFn:1=0x06", "Cmd:1=0x01")
    assert code == 0, lines
    assert lines[0] == "bytes: 2"
    assert [ln.lower() for ln in sent(lines)] == ["ipmitool raw 0x06 0x01"]
    found = rows(lines)
    assert [row[:3] for row in found] == [["0", "1", "NetFn"], ["1", "1", "Cmd"]]
    assert [bare(TOKEN.findall(row[3])) for row in found] == [["06"], ["01"]]

    code, lines, _ = invoke(
        capsys, "ipmi", "NetFn:1=0x00", "Cmd:1=0x02", "Chassis Control:1=0x02"
    )
    assert code == 0, lines
    assert lines[0] == "bytes: 3"
    assert [row[:3] for row in rows(lines)] == [
        ["0", "1", "NetFn"],
        ["1", "1", "Cmd"],
        ["2", "1", "Chassis Control"],
    ]


def test_pldm_rows_come_after_both_lines(capsys):
    code, lines, _ = invoke(
        capsys, "pldm", "Header:1=0x80", "PLDM Type:1=0", "Command Code:1=0x02"
    )
    assert code == 0, lines
    assert lines[0] == "bytes: 3"
    assert [i for i, ln in enumerate(lines) if ln.split(" ")[0] in TOOLS] == [1, 2]
    assert [row[:3] for row in rows(lines)] == [
        ["0", "1", "Header"],
        ["1", "1", "PLDM Type"],
        ["2", "1", "Command Code"],
    ]


# ------------------------------------------------------------------ AC-5

REFUSED = [
    # (arguments, what the message must name)
    (["spdm", "Flags:1=256"], "Flags"),  # one more than fits
    (["spdm", "Flags:2=0x10000"], "Flags"),
    (["spdm", "Flags:4=0x100000000"], "Flags"),
    (["spdm", "Flags:4:be=4294967296"], "Flags"),
    (["spdm", "Flags:1=-1"], "Flags"),  # negative
    (["spdm", "Flags:0=1"], "Flags"),  # SIZE not a positive integer
    (["spdm", "Flags:-2=1"], "Flags"),
    (["spdm", "Flags:two=1"], "Flags"),
    (["spdm", "Flags:1.5=1"], "Flags"),
    (["spdm", "Address:4=0xc0,0xa8,0x01"], "Address"),  # a byte short
    (["spdm", "Address:2=0xc0,0xa8,0x01"], "Address"),  # a byte long
    (["spdm", "Address:2=0xc0,0x100"], "Address"),  # above 0xff
    (["spdm", "Flags=1"], "Flags"),  # no :SIZE
    (["spdm", "Flags:1"], "Flags"),  # no =VALUE
    (["spdm"], None),  # no field at all
    (["pldm"], None),
    (["redfish", "Flags:1=1"], "redfish"),  # unknown protocol
    (["ipmi"], None),
    (["ipmi", "NetFn:1=0x06"], None),  # fewer than two fields
    (["ipmi", "NetFn:2=0x06", "Cmd:1=0x01"], "NetFn"),
    (["ipmi", "NetFn:1=0x06", "Cmd:2=0x01"], "Cmd"),
    (["ipmi", "NetFn:1=0x06", "Cmd:2=<cmd>"], "Cmd"),
]


@pytest.mark.parametrize(("argv", "named"), REFUSED)
def test_what_cannot_be_laid_out_is_refused_with_exit_2(capsys, argv, named):
    code, lines, text = invoke(capsys, *argv)
    assert code == 2, text
    assert text.strip(), "a refusal says why"
    if named is not None:
        assert named in text, text
    assert not sent(lines), lines


@pytest.mark.parametrize("protocol", ["spdm", "pldm", "mctp-control", "ipmi"])
def test_one_bad_field_among_good_ones_prints_no_line_and_is_named(capsys, protocol):
    good = ["First:1=0x06", "Second:1=0x01", "Third:2=0x1234"]
    code, lines, text = invoke(
        capsys, protocol, *good, "Culprit:1=0x1ff", "Fifth:1=<fifth>"
    )
    assert code == 2, text
    assert "Culprit" in text
    assert not sent(lines), lines

    # the same fields without the bad one are laid out
    code, lines, _ = invoke(capsys, protocol, *good, "Fifth:1=<fifth>")
    assert code == 0, lines
    assert lines[0] == "bytes: 5"

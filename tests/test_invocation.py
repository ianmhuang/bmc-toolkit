"""The ``invocation`` command: the bytes of a request arranged from the
fields the caller gives, printed in each sending tool's syntax."""

from pathlib import Path

import pytest

from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
COMMANDS_DOC = ROOT / "docs" / "COMMANDS.md"

# SPDM GET_CAPABILITIES of DSP0274 1.4.1: 20 bytes, eleven 00 in a row
CAPABILITIES = [
    "SPDMVersion:1=<negotiated version>",
    "RequestResponseCode:1=0xe1",
    "Param1:1=0",
    "Param2:1=0",
    "Reserved:1=0",
    "CTExponent:1=0",
    "ExtFlags:2=0",
    "Flags:4=0",
    "DataTransferSize:4=0x1000",
    "MaxSPDMmsgSize:4=0x1000",
]
CAPABILITIES_DATA = (
    "<negotiated version> e1 00 00 00 00 00 00 00 00 00 00 00 10 00 00 00 10 00 00"
)
TOOLS = ("ipmitool ", "mctp-client ", "pldmtool ")


@pytest.fixture(autouse=True)
def no_library(monkeypatch, tmp_path):
    """The command must not need a Library: point at one that is not there."""
    missing = tmp_path / "no-such-library"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(missing))
    yield missing
    assert not missing.exists()


def run(capsys, *argv):
    code = main(["invocation", *argv])
    return code, capsys.readouterr().out.splitlines()


def tool_lines(lines):
    return [ln for ln in lines if ln.startswith(TOOLS)]


# ------------------------------------------------------------------ AC-1


def test_ipmi_prints_ipmitool_raw_with_every_byte_prefixed(capsys):
    code, lines = run(
        capsys,
        "ipmi",
        "NetFn:1=0x0a",
        "Cmd:1=0x23",
        "Reservation ID:2=0",
        "Record ID:2=0x0102",
        "Offset:1=0",
        "Bytes to read:1=5",
    )
    assert code == 0, lines
    assert tool_lines(lines) == ["ipmitool raw 0x0a 0x23 0x00 0x00 0x02 0x01 0x00 0x05"]


def test_mctp_control_prints_mctp_client_with_type_control(capsys):
    code, lines = run(
        capsys, "mctp-control", "Header:1=0x80", "Command:1=0x04", "Type:1=1"
    )
    assert code == 0, lines
    assert tool_lines(lines) == ["mctp-client eid <eid> type control data 80 04 01"]


def test_spdm_prints_the_twenty_bytes_of_get_capabilities(capsys):
    code, lines = run(capsys, "spdm", *CAPABILITIES)
    assert code == 0, lines
    assert tool_lines(lines) == [
        "mctp-client eid <eid> type spdm data " + CAPABILITIES_DATA
    ]


def test_pldm_prints_both_tools_with_the_same_bytes(capsys):
    code, lines = run(
        capsys,
        "pldm",
        "Header:1=0x80",
        "PLDM Type:1=0x02",
        "Command:1=0x11",
        "sensorID:2=0x1234",
        "rearmEventState:1=0",
    )
    assert code == 0, lines
    assert tool_lines(lines) == [
        "mctp-client eid <eid> type pldm data 80 02 11 34 12 00",
        "pldmtool raw -m <eid> -d 0x80 0x02 0x11 0x34 0x12 0x00",
    ]


def test_no_citation_is_printed(capsys):
    code, lines = run(capsys, "spdm", *CAPABILITIES)
    assert code == 0
    assert not [ln for ln in lines if ln.startswith("cite:")]


# ------------------------------------------------------------------ AC-2


@pytest.mark.parametrize(
    ("field", "data"),
    [
        ("Size:4=0x1000", "00 10 00 00"),  # least significant byte first
        ("Size:4=4096", "00 10 00 00"),  # decimal
        ("Size:4:be=0x1000", "00 00 10 00"),  # most significant byte first
        ("Size:4:le=0x1000", "00 10 00 00"),  # the default, spelled out
        ("Size:2=0xABCD", "cd ab"),  # upper-case digits, lower-case output
        ("Size:3=0", "00 00 00"),
        ("Size:1=00", "00"),  # zero is zero in any base
        ("Address:4=0xc0,0xa8,0x01,0x0a", "c0 a8 01 0a"),  # a byte list, as written
        ("Address:4:be=0xc0,0xa8,0x01,0x0a", "c0 a8 01 0a"),  # still as written
        ("Pad:3=0,0,0", "00 00 00"),
        ("Byte 2:3 of the record:2=0x0102", "02 01"),  # a name with spaces and a colon
    ],
)
def test_a_field_is_laid_out_over_its_size(capsys, field, data):
    code, lines = run(capsys, "spdm", field)
    assert code == 0, lines
    assert tool_lines(lines) == ["mctp-client eid <eid> type spdm data " + data]


# ------------------------------------------------------------------ AC-3


def test_a_placeholder_reaches_the_line_unchanged(capsys):
    code, lines = run(
        capsys, "ipmi", "NetFn:1=0x04", "Cmd:1=0x2d", "Sensor:1=<sensor number>"
    )
    assert code == 0, lines
    assert tool_lines(lines) == ["ipmitool raw 0x04 0x2d <sensor number>"]


def test_a_placeholder_of_several_bytes_prints_one_token_per_byte(capsys):
    code, lines = run(
        capsys,
        "pldm",
        "Header:1=0x80",
        "Type:1=2",
        "Cmd:1=0x11",
        "sensorID:2=<sensor id>",
    )
    assert code == 0, lines
    assert tool_lines(lines) == [
        "mctp-client eid <eid> type pldm data 80 02 11 <sensor id 0> <sensor id 1>",
        "pldmtool raw -m <eid> -d 0x80 0x02 0x11 <sensor id 0> <sensor id 1>",
    ]
    assert lines[0] == "bytes: 5"


# ------------------------------------------------------------------ AC-4


def test_the_total_comes_first_and_every_field_has_its_row(capsys):
    code, lines = run(capsys, "spdm", *CAPABILITIES)
    assert code == 0, lines
    assert lines[0] == "bytes: 20"
    assert lines[1].startswith("mctp-client ")
    assert lines[2:] == [
        "offset | size | field | bytes",
        "0 | 1 | SPDMVersion | <negotiated version>",
        "1 | 1 | RequestResponseCode | e1",
        "2 | 1 | Param1 | 00",
        "3 | 1 | Param2 | 00",
        "4 | 1 | Reserved | 00",
        "5 | 1 | CTExponent | 00",
        "6 | 2 | ExtFlags | 00 00",
        "8 | 4 | Flags | 00 00 00 00",
        "12 | 4 | DataTransferSize | 00 10 00 00",
        "16 | 4 | MaxSPDMmsgSize | 00 10 00 00",
    ]


def test_ipmi_counts_netfn_and_cmd_among_the_bytes(capsys):
    code, lines = run(capsys, "ipmi", "NetFn:1=0x00", "Cmd:1=0x02", "Control:1=0x02")
    assert code == 0, lines
    assert lines == [
        "bytes: 3",
        "ipmitool raw 0x00 0x02 0x02",
        "offset | size | field | bytes",
        "0 | 1 | NetFn | 0x00",
        "1 | 1 | Cmd | 0x02",
        "2 | 1 | Control | 0x02",
    ]


def test_pldm_rows_follow_the_two_tool_lines(capsys):
    code, lines = run(capsys, "pldm", "Header:1=0x80", "Type:1=0", "Cmd:1=0x02")
    assert code == 0, lines
    assert lines[0] == "bytes: 3"
    assert [ln.split(" ")[0] for ln in lines[1:3]] == ["mctp-client", "pldmtool"]
    assert lines[3:] == [
        "offset | size | field | bytes",
        "0 | 1 | Header | 80",
        "1 | 1 | Type | 00",
        "2 | 1 | Cmd | 02",
    ]


# ------------------------------------------------------------------ AC-5


@pytest.mark.parametrize(
    ("argv", "names", "reason"),
    [
        (["spdm", "Flags:4=0x1ffffffff"], "Flags:4=0x1ffffffff", "does not fit"),
        (["spdm", "Code:1=256"], "Code:1=256", "does not fit"),
        (["spdm", "Code:1=-1"], "Code:1=-1", "negative"),
        (["spdm", "Code:0=1"], "Code:0=1", "SIZE"),
        (["spdm", "Code:x=1"], "Code:x=1", "SIZE"),
        (["spdm", "Code=1"], "Code=1", "SIZE"),
        (["spdm", "Code:1"], "Code:1", "VALUE"),
        (["spdm", "Code:1="], "Code:1=", "VALUE"),
        (["spdm", ":1=1"], ":1=1", "NAME"),
        (["spdm", "Code:1=e1"], "Code:1=e1", "0x"),
        (["spdm", "Code:1=08"], "Code:1=08", "0x"),  # octal, decimal or hex?
        (["spdm", "Code:1=<>"], "Code:1=<>", "placeholder"),
        (["spdm", "Address:4=0xc0,0xa8,0x01"], "Address:4=0xc0,0xa8,0x01", "3 bytes"),
        (["spdm", "Address:2=0xc0,0x1a8"], "Address:2=0xc0,0x1a8", "0x1a8"),
        (["spdm", "Address:2=00,10"], "Address:2=00,10", "0x"),  # 10 or 0x10?
        (["spdm", "Address:2=0xc0 0xa8"], "Address:2=0xc0 0xa8", "comma"),
        (["ipmi", "NetFn:1=0x06"], "ipmi", "NetFn and Cmd"),
        (["ipmi", "NetFn:2=0x06", "Cmd:1=1"], "NetFn:2=0x06", "one byte"),
        (["ipmi", "NetFn:1=0x06", "Cmd:2=1"], "Cmd:2=1", "one byte"),
        (["spdm"], "NAME:SIZE=VALUE", "no field"),
        (["redfish", "Code:1=1"], "redfish", "mctp-control"),
    ],
)
def test_a_field_that_cannot_be_laid_out_is_refused(capsys, argv, names, reason):
    code, lines = run(capsys, *argv)
    assert code == 2, lines
    text = "\n".join(lines)
    assert names in text
    assert reason in text
    assert not tool_lines(lines)
    assert not [ln for ln in lines if ln.startswith("bytes:")]


def test_one_bad_field_among_good_ones_prints_no_line(capsys):
    code, lines = run(
        capsys, "spdm", *CAPABILITIES[:7], "Flags:4=oops", *CAPABILITIES[8:]
    )
    assert code == 2
    assert "Flags:4=oops" in "\n".join(lines)
    assert not tool_lines(lines)


# ------------------------------------------------------------------ AC-6


def test_the_module_imports_the_standard_library_only():
    import sys

    from bmc_toolkit.spec import invocation

    source = Path(invocation.__file__).read_text("utf-8")
    imported = set()
    for line in source.splitlines():
        words = line.split()
        if line.startswith("import ") or line.startswith("from "):
            imported.add(words[1].split(".")[0])
    assert imported, "no import found"
    assert imported <= set(sys.stdlib_module_names), imported


def test_a_wait_of_zero_and_no_library_change_nothing(capsys, no_library):
    code = main(["--wait", "0", "invocation", "spdm", *CAPABILITIES])
    assert code == 0
    assert "bytes: 20" in capsys.readouterr().out
    assert not no_library.exists()


# ------------------------------------------------------------------ AC-7


def test_skill_table_and_commands_doc_describe_the_command():
    skill = SKILL.read_text("utf-8")
    rows = [ln for ln in skill.splitlines() if ln.startswith("| `invocation ")]
    assert len(rows) == 1, rows
    for word in (
        "ipmi",
        "mctp-control",
        "pldm",
        "spdm",
        "NAME:SIZE=VALUE",
        ":be",
        "bytes: N",
    ):
        assert word in rows[0], word
    doc = " ".join(COMMANDS_DOC.read_text("utf-8").split())
    assert "`invocation PROTOCOL" in doc
    for word in ("NAME:SIZE=VALUE", "NAME:SIZE:be=VALUE", "exit 2", "no Library"):
        assert word in doc, word

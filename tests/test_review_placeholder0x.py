"""Reviewer acceptance tests: a placeholder carries the ``0x`` of its line
(T40, AC-1 to AC-5 and AC-7).

Black box: every test calls the CLI entry point with ``invocation PROTOCOL
FIELD ...`` and reads what it prints. In the lines whose bytes all carry
``0x`` (``ipmitool raw``, ``pldmtool raw``, the ``ipmi`` rows) a placeholder
byte is printed ``0x<text>``; in the ``mctp-client`` line and the other rows
it stays ``<text>``. Refusals, totals and the two protocols without a ``0x``
line are unchanged. The Command workflow block no longer tells the answer
to drop a ``0x``.

On develop the ``0x`` lines print a placeholder bare, so AC-1 to AC-3 fail
there; AC-4, AC-5 are the guards the criteria ask for and pass on both.
"""

import re
from pathlib import Path

import pytest

from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
MAX_LINES = 58  # unchanged by T40 (AC-7); 40 until T41; 42 until T43; 44 until T46; 46 until T52; 52 until T53

TOOLS = ("ipmitool", "mctp-client", "pldmtool")
HEADER = {
    "ipmi": ["NetFn:1=0x0a", "Cmd:1=0x23"],
    "mctp-control": ["Header:1=0x80", "Command Code:1=0x02"],
    "pldm": ["Header:1=0x80", "PLDM Type:1=0x02", "Command Code:1=0x11"],
    "spdm": ["SPDMVersion:1=0x12", "RequestResponseCode:1=0x84"],
}
# a placeholder is one token even with spaces inside; its 0x belongs to it
TOKEN = re.compile(r"(?:0x)?<[^>]*>|\S+")


@pytest.fixture(autouse=True)
def no_library(monkeypatch, tmp_path):
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path / "no-such-library"))


def invoke(capsys, *argv):
    """(exit code, stdout lines, everything printed)."""
    code = main(["invocation", *argv])
    got = capsys.readouterr()
    return code, got.out.splitlines(), got.out + got.err


def sent(lines):
    return [ln for ln in lines if ln.split(" ")[0] in TOOLS]


def rows(lines):
    """The offset rows as (offset, size, field, bytes) after the header row."""
    at = lines.index("offset | size | field | bytes")
    return [tuple(ln.split(" | ")) for ln in lines[at + 1 :]]


def data_tokens(line: str, after: str) -> list[str]:
    _, _, rest = line.partition(after)
    return TOKEN.findall(rest)


def refusal(capsys, *argv) -> str:
    code, lines, text = invoke(capsys, *argv)
    assert code == 2, text[:300]
    assert "Traceback" not in text
    assert not sent(lines), lines[:3]
    assert not [ln for ln in lines if ln.startswith("bytes:")], lines[:3]
    said = [ln for ln in text.splitlines() if ln.strip()]
    assert len(said) == 1, said[:3]
    return said[0]


# ------------------------------------------------------------------ AC-1


def test_ipmi_prints_a_one_byte_placeholder_with_0x_in_line_and_row(capsys):
    # IPMI Get Sensor Reading, the sensor number not known (I2e)
    code, lines, _ = invoke(
        capsys, "ipmi", "NetFn:1=0x04", "Cmd:1=0x2d", "Sensor:1=<sensor number>"
    )
    assert code == 0, lines
    assert lines == [
        "bytes: 3",
        "ipmitool raw 0x04 0x2d 0x<sensor number>",
        "offset | size | field | bytes",
        "0 | 1 | NetFn | 0x04",
        "1 | 1 | Cmd | 0x2d",
        "2 | 1 | Sensor | 0x<sensor number>",
    ]


def test_every_token_of_the_ipmitool_line_carries_0x(capsys):
    code, lines, _ = invoke(
        capsys, "ipmi", "NetFn:1=0x04", "Cmd:1=0x2d", "Sensor:1=<sensor number>"
    )
    assert code == 0, lines
    (line,) = sent(lines)
    tokens = data_tokens(line, "ipmitool raw ")
    assert tokens == ["0x04", "0x2d", "0x<sensor number>"]
    assert all(t.startswith("0x") for t in tokens), tokens


# ------------------------------------------------------------------ AC-2


@pytest.mark.parametrize("order", ["", ":be", ":le"])
def test_ipmi_prints_one_0x_token_per_placeholder_byte_in_order(capsys, order):
    # IPMI Get SDR, the reservation id not known (I5): a 2-byte placeholder
    code, lines, _ = invoke(
        capsys,
        "ipmi",
        "NetFn:1=0x0a",
        "Cmd:1=0x23",
        f"Reservation ID:2{order}=<reservation id>",
        "Record ID:2=0x0102",
        "Offset:1=0",
        "Bytes to read:1=5",
    )
    assert code == 0, lines
    assert lines[0] == "bytes: 8"
    assert sent(lines) == [
        "ipmitool raw 0x0a 0x23 0x<reservation id 0> 0x<reservation id 1> "
        "0x02 0x01 0x00 0x05"
    ]
    assert rows(lines) == [
        ("0", "1", "NetFn", "0x0a"),
        ("1", "1", "Cmd", "0x23"),
        ("2", "2", "Reservation ID", "0x<reservation id 0> 0x<reservation id 1>"),
        ("4", "2", "Record ID", "0x02 0x01"),
        ("6", "1", "Offset", "0x00"),
        ("7", "1", "Bytes to read", "0x05"),
    ]


def test_a_long_ipmi_placeholder_is_n_0x_tokens(capsys):
    code, lines, _ = invoke(
        capsys, "ipmi", *HEADER["ipmi"], "Address:4=<address>", "Tail:1=0x77"
    )
    assert code == 0, lines
    assert lines[0] == "bytes: 7"
    (line,) = sent(lines)
    assert data_tokens(line, "ipmitool raw ") == [
        "0x0a",
        "0x23",
        "0x<address 0>",
        "0x<address 1>",
        "0x<address 2>",
        "0x<address 3>",
        "0x77",
    ]
    assert rows(lines)[2] == (
        "2",
        "4",
        "Address",
        "0x<address 0> 0x<address 1> 0x<address 2> 0x<address 3>",
    )


# ------------------------------------------------------------------ AC-3


def test_pldm_prints_0x_in_the_pldmtool_line_only(capsys):
    # PLDM GetSensorReading, the sensor id not given (P5): a 2-byte
    # placeholder, and a one-byte one after it
    code, lines, _ = invoke(
        capsys,
        "pldm",
        *HEADER["pldm"],
        "sensorID:2=<sensor id>",
        "rearmEventState:1=<rearm>",
    )
    assert code == 0, lines
    assert lines[0] == "bytes: 6"
    assert sorted(sent(lines)) == [
        "mctp-client eid <eid> type pldm data 80 02 11 "
        "<sensor id 0> <sensor id 1> <rearm>",
        "pldmtool raw -m <eid> -d 0x80 0x02 0x11 "
        "0x<sensor id 0> 0x<sensor id 1> 0x<rearm>",
    ]
    assert rows(lines) == [
        ("0", "1", "Header", "80"),
        ("1", "1", "PLDM Type", "02"),
        ("2", "1", "Command Code", "11"),
        ("3", "2", "sensorID", "<sensor id 0> <sensor id 1>"),
        ("5", "1", "rearmEventState", "<rearm>"),
    ]


def test_the_two_pldm_lines_hold_the_same_bytes_under_their_own_prefix(capsys):
    code, lines, _ = invoke(
        capsys, "pldm", *HEADER["pldm"], "sensorID:2:be=<sensor id>", "Rearm:1=0"
    )
    assert code == 0, lines
    client, tool = sorted(sent(lines))
    plain = data_tokens(client, " data ")
    prefixed = data_tokens(tool, " -d ")
    assert plain == ["80", "02", "11", "<sensor id 0>", "<sensor id 1>", "00"]
    assert prefixed == [f"0x{t}" for t in plain]
    # the mctp-client line carries no 0x anywhere in its data
    assert not any(t.startswith("0x") for t in plain), plain


# ------------------------------------------------------------------ AC-4


def test_spdm_placeholders_stay_bare_including_version_and_nonce(capsys):
    code, lines, _ = invoke(
        capsys,
        "spdm",
        "SPDMVersion:1=<negotiated version>",
        "RequestResponseCode:1=0x83",
        "Param1:1=0",
        "Param2:1=0xff",
        "Nonce:32=<nonce>",
    )
    assert code == 0, lines
    nonce = " ".join(f"<nonce {i}>" for i in range(32))
    assert lines == [
        "bytes: 36",
        f"mctp-client eid <eid> type spdm data <negotiated version> 83 00 ff {nonce}",
        "offset | size | field | bytes",
        "0 | 1 | SPDMVersion | <negotiated version>",
        "1 | 1 | RequestResponseCode | 83",
        "2 | 1 | Param1 | 00",
        "3 | 1 | Param2 | ff",
        f"4 | 32 | Nonce | {nonce}",
    ]
    assert "0x" not in "\n".join(lines)


def test_mctp_control_placeholders_stay_bare(capsys):
    code, lines, _ = invoke(
        capsys,
        "mctp-control",
        "Header:1=0x80",
        "Command Code:1=0x01",
        "Operation:1=0",
        "EID:1=<eid to assign>",
    )
    assert code == 0, lines
    assert lines == [
        "bytes: 4",
        "mctp-client eid <eid> type control data 80 01 00 <eid to assign>",
        "offset | size | field | bytes",
        "0 | 1 | Header | 80",
        "1 | 1 | Command Code | 01",
        "2 | 1 | Operation | 00",
        "3 | 1 | EID | <eid to assign>",
    ]
    assert "0x" not in "\n".join(lines)


# ------------------------------------------------------------------ AC-5

REFUSED = [
    ("<>", "a placeholder is written <text>"),
    ("< >", "a placeholder is written <text>"),
    ("<x", "a placeholder is written <text>"),
    ("x>", "a placeholder is written <text>"),
    # a 0x written around the placeholder is a VALUE, not a placeholder
    ("0x<sensor number>", "a placeholder is written <text>"),
    ("<sensor number>0", "a placeholder is written <text>"),
    ("<lsb>,<msb>", "a field takes one placeholder"),
    ("<lsb> <msb>", "a field takes one placeholder"),
    ("<a><b>", "a field takes one placeholder"),
]


@pytest.mark.parametrize("protocol", sorted(HEADER))
@pytest.mark.parametrize("value,reason", REFUSED)
def test_placeholder_refusals_are_unchanged(capsys, protocol, value, reason):
    field = f"Sensor:2={value}"
    line = refusal(capsys, protocol, *HEADER[protocol], field)
    assert line.startswith("invocation: "), line
    assert repr(field) in line, line
    assert reason in line, line


@pytest.mark.parametrize("protocol", sorted(HEADER))
def test_a_placeholder_still_counts_its_size_in_the_total(capsys, protocol):
    head = HEADER[protocol]
    code, lines, _ = invoke(
        capsys, protocol, *head, "One:1=<one>", "Four:4=<four>", "Last:1=0x11"
    )
    assert code == 0, lines
    assert lines[0] == f"bytes: {len(head) + 6}"
    # and every line to send holds exactly that many byte tokens
    after = {"ipmitool": " raw ", "mctp-client": " data ", "pldmtool": " -d "}
    for line in sent(lines):
        tokens = data_tokens(line, after[line.split(" ")[0]])
        assert len(tokens) == len(head) + 6, (line, tokens)


def test_a_number_written_with_0x_is_not_doubled(capsys):
    # the 0x of a value byte is printed once, as before
    code, lines, _ = invoke(capsys, "ipmi", "NetFn:1=0x04", "Cmd:1=0x2d", "S:1=0x30")
    assert code == 0, lines
    assert sent(lines) == ["ipmitool raw 0x04 0x2d 0x30"]
    assert "0x0x" not in "\n".join(lines)


# ------------------------------------------------------------------ AC-7


def block_lines():
    lines = SKILL.read_text("utf-8").splitlines()
    assert lines.count(START) == 1 and lines.count(END) == 1
    first, last = lines.index(START), lines.index(END)
    assert first < last
    return lines[first + 1 : last]


def test_the_block_no_longer_tells_the_answer_to_drop_a_0x():
    low = " ".join(" ".join(block_lines()).split()).lower()
    assert not re.search(
        r"placeholder[^.()]*\bno `0x`|\bno `0x`[^.()]*placeholder", low
    ), low
    assert "takes no `0x`" not in low


def test_the_helper_step_still_says_to_copy_the_printed_lines():
    low = " ".join(" ".join(block_lines()).split()).lower()
    step = low[low.index("4. run `invocation") :]
    assert re.search(r"copy the line\(s\)", step), step
    assert "total it prints" in step


def test_the_block_stays_within_its_cap():
    assert len(block_lines()) <= MAX_LINES

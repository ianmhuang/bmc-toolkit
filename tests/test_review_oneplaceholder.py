"""Reviewer acceptance tests: a field takes one placeholder (AC-1, AC-2, AC-6).

Black box: every test calls the CLI entry point with ``invocation PROTOCOL
FIELD ...`` and reads what it prints. The expected output is written out by
hand in the form docs/COMMANDS.md gives: ``bytes: N``, the line(s) to send,
``offset | size | field | bytes`` and one row per field.

On develop a VALUE that starts with ``<`` and ends with ``>`` is one
placeholder whatever lies between, so every refusal asked for here is exit 0
there. The tests that pin what stays accepted (AC-2, AC-6) ask for the
refusal next to it as well: each draws the line between one placeholder and
two, and fails on develop for the half that is new.
"""

import pytest

from bmc_toolkit.spec.cli import main

TOOLS = ("ipmitool", "mctp-client", "pldmtool")
PROTOCOLS = ("ipmi", "mctp-control", "pldm", "spdm")
# what a request of the protocol starts with: the field under test is then
# the only thing wrong with the call
HEADER = {
    "ipmi": ["NetFn:1=0x0a", "Cmd:1=0x43"],
    "mctp-control": ["Header:1=0x80", "Command Code:1=0x02"],
    "pldm": ["Header:1=0x80", "PLDM Type:1=0x02", "Command Code:1=0x11"],
    "spdm": ["SPDMVersion:1=0x12", "RequestResponseCode:1=0x84"],
}
INNER = ["sensor number", "record id, LSB first", "eid 0x08-0xfe"]


@pytest.fixture(autouse=True)
def no_library(monkeypatch, tmp_path):
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path / "no-such-library"))


def invoke(capsys, *argv):
    """(exit code, stdout lines, everything printed)."""
    code = main(["invocation", *argv])
    got = capsys.readouterr()
    return code, got.out.splitlines(), got.out + got.err


def refusal(capsys, *argv) -> str:
    """The one line a refused call prints; nothing to send comes with it."""
    code, lines, text = invoke(capsys, *argv)
    assert code == 2, text[:300]
    assert "Traceback" not in text
    assert not [ln for ln in lines if ln.split(" ")[0] in TOOLS], lines[:3]
    assert not [ln for ln in lines if ln.startswith("bytes:")], lines[:3]
    said = [ln for ln in text.splitlines() if ln.strip()]
    assert len(said) == 1, said[:3]
    return said[0]


# ------------------------------------------------------------------ AC-1

TWO = [
    # the four the criterion names
    "Reservation ID:2=<lsb>,<msb>",
    "X:1=<a> <b>",
    "X:1=<a><b>",
    "X:1=<<a>>",
    # the same fault with an order, more bytes, or one bracket too many
    "Reservation ID:2:be=<lsb>,<msb>",
    "Record ID:2=<record id lsb>, <record id msb>",
    "Handle:4=<a>,<b>,<c>,<d>",
    "Handle:4=<a<b>",
    "Handle:4=<a>b>",
]


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("field", TWO)
def test_a_value_with_more_than_one_placeholder_is_refused(capsys, protocol, field):
    line = refusal(capsys, protocol, *HEADER[protocol], field, "Last:1=0x01")
    assert field.split(":")[0] in line
    assert "one placeholder" in line


@pytest.mark.parametrize("protocol", ["mctp-control", "pldm", "spdm"])
def test_it_is_refused_as_the_only_field_too(capsys, protocol):
    line = refusal(capsys, protocol, "Reservation ID:2=<lsb>,<msb>")
    assert "Reservation ID" in line
    assert "one placeholder" in line


def test_each_placeholder_in_a_field_of_its_own_is_laid_out(capsys):
    head = HEADER["ipmi"]
    line = refusal(capsys, "ipmi", *head, "Reservation ID:2=<lsb>,<msb>")
    assert "Reservation ID" in line
    assert "one placeholder" in line

    code, lines, _ = invoke(
        capsys,
        "ipmi",
        *head,
        "Reservation ID LSB:1=<lsb>",
        "Reservation ID MSB:1=<msb>",
    )
    assert code == 0, lines
    assert lines == [
        "bytes: 4",
        "ipmitool raw 0x0a 0x43 <lsb> <msb>",
        "offset | size | field | bytes",
        "0 | 1 | NetFn | 0x0a",
        "1 | 1 | Cmd | 0x43",
        "2 | 1 | Reservation ID LSB | <lsb>",
        "3 | 1 | Reservation ID MSB | <msb>",
    ]


# ------------------------------------------------------------ AC-2, AC-6


@pytest.mark.parametrize("inner", INNER)
def test_one_placeholder_prints_as_before_and_two_of_it_are_refused(capsys, inner):
    one = f"<{inner}>"
    three = f"<{inner} 0> <{inner} 1> <{inner} 2>"
    code, lines, _ = invoke(capsys, "spdm", f"One:1={one}", f"Three:3={one}")
    assert code == 0, lines
    assert lines == [
        "bytes: 4",
        f"mctp-client eid <eid> type spdm data {one} {three}",
        "offset | size | field | bytes",
        f"0 | 1 | One | {one}",
        f"1 | 3 | Three | {three}",
    ]

    # the same text twice in one field is two placeholders
    line = refusal(capsys, "spdm", f"One:1={one}", f"Three:3={one},{one}")
    assert "Three" in line
    assert "one placeholder" in line


@pytest.mark.parametrize("inner", INNER)
def test_ipmitool_takes_one_placeholder_as_before(capsys, inner):
    one = f"<{inner}>"
    two = f"<{inner} 0> <{inner} 1>"
    head = HEADER["ipmi"]
    code, lines, _ = invoke(capsys, "ipmi", *head, f"Two:2={one}", f"One:1={one}")
    assert code == 0, lines
    assert lines == [
        "bytes: 5",
        f"ipmitool raw 0x0a 0x43 {two} {one}",
        "offset | size | field | bytes",
        "0 | 1 | NetFn | 0x0a",
        "1 | 1 | Cmd | 0x43",
        f"2 | 2 | Two | {two}",
        f"4 | 1 | One | {one}",
    ]

    line = refusal(capsys, "ipmi", *head, f"Two:2={one} {one}", f"One:1={one}")
    assert "Two" in line
    assert "one placeholder" in line


@pytest.mark.parametrize("inner", INNER)
def test_both_pldm_lines_take_one_placeholder_as_before(capsys, inner):
    one = f"<{inner}>"
    two = f"<{inner} 0> <{inner} 1>"
    head = HEADER["pldm"]
    code, lines, _ = invoke(capsys, "pldm", *head, f"sensorID:2:be={one}")
    assert code == 0, lines
    assert lines == [
        "bytes: 5",
        f"mctp-client eid <eid> type pldm data 80 02 11 {two}",
        f"pldmtool raw -m <eid> -d 0x80 0x02 0x11 {two}",
        "offset | size | field | bytes",
        "0 | 1 | Header | 80",
        "1 | 1 | PLDM Type | 02",
        "2 | 1 | Command Code | 11",
        f"3 | 2 | sensorID | {two}",
    ]

    line = refusal(capsys, "pldm", *head, f"sensorID:2:be={one}{one}")
    assert "sensorID" in line
    assert "one placeholder" in line

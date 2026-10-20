"""Reviewer acceptance tests: the forms docs/COMMANDS.md and ``_shown``'s
docstring now name are handled as they say (AC-3, AC-4).

Black box: every test calls the CLI entry point with ``invocation PROTOCOL
FIELD ...`` and reads what it prints. The change is wording only, so what
is pinned here is the behaviour the new wording describes: a placeholder
not opened (``x>``) is refused as a malformed placeholder, a bracket inside
one (``<>>``, ``<a>b>``) as more than one placeholder, hex written ``0X``
is laid out like ``0x``, and a refusal that echoes a quoted field of
control characters or backslashes prints more than 80 characters of head
yet stays one bounded line.

No test here fails on develop: the behaviour is unchanged by design and a
test must not pin the strings of a document. They guard that the docs and
the docstring claim nothing the code does not do.
"""

import pytest

from bmc_toolkit.spec.cli import main

TOOLS = ("ipmitool", "mctp-client", "pldmtool")
PROTOCOLS = ("ipmi", "mctp-control", "pldm", "spdm")
HEADER = {
    "ipmi": ["NetFn:1=0x0a", "Cmd:1=0x43"],
    "mctp-control": ["Header:1=0x80", "Command Code:1=0x02"],
    "pldm": ["Header:1=0x80", "PLDM Type:1=0x02", "Command Code:1=0x11"],
    "spdm": ["SPDMVersion:1=0x12", "RequestResponseCode:1=0x84"],
}
SHOWN = 80
# repr spells one character as at most \\UXXXXXXXX: ten characters
LONGEST_HEAD = 2 + 10 * SHOWN


@pytest.fixture(autouse=True)
def no_library(monkeypatch, tmp_path):
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path / "no-such-library"))


def invoke(capsys, *argv):
    """(exit code, stdout lines, everything printed)."""
    code = main(["invocation", *argv])
    got = capsys.readouterr()
    return code, got.out.splitlines(), got.out + got.err


def rows(lines):
    at = lines.index("offset | size | field | bytes")
    return [tuple(ln.split(" | ")) for ln in lines[at + 1 :]]


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


# ------------------------------------------------------------------ AC-4
# the docs list `x>` beside `<>` and `<x`: one placeholder written wrong


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("value", ["x>", "sensor number>", ">"])
def test_a_placeholder_not_opened_is_refused_as_written_wrong(capsys, protocol, value):
    field = f"Sensor:1={value}"
    line = refusal(capsys, protocol, *HEADER[protocol], field)
    assert line.startswith("invocation: field "), line
    assert repr(field) in line, line
    assert line.endswith("a placeholder is written <text>"), line
    assert "one placeholder" not in line, line


# the docs list `<>>` and `<a>b>` beside `<lsb>,<msb>`: more than one


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("value", ["<>>", "<a>b>", "<<>", "<a<b>", "<<a>>"])
def test_a_bracket_inside_a_placeholder_is_refused_as_more_than_one(
    capsys, protocol, value
):
    field = f"Sensor:2={value}"
    line = refusal(capsys, protocol, *HEADER[protocol], field)
    assert repr(field) in line, line
    assert "a field takes one placeholder" in line, line
    assert "give each placeholder its own field" in line, line
    assert "is written <text>" not in line, line


@pytest.mark.parametrize("protocol", ["mctp-control", "pldm", "spdm"])
@pytest.mark.parametrize(
    "value,reason", [("x>", "is written <text>"), ("<>>", "one placeholder")]
)
def test_the_two_forms_are_refused_as_the_only_field_too(
    capsys, protocol, value, reason
):
    line = refusal(capsys, protocol, f"Sensor:1={value}")
    assert "Sensor" in line and reason in line, line


# the docs say hex takes `0x` or `0X`


def test_0X_is_laid_out_like_0x_in_every_line(capsys):
    code, lines, _ = invoke(
        capsys, "pldm", *HEADER["pldm"], "sensorID:2=0X1f", "rearm:1=0XFF"
    )
    assert code == 0, lines
    assert lines == [
        "bytes: 6",
        "mctp-client eid <eid> type pldm data 80 02 11 1f 00 ff",
        "pldmtool raw -m <eid> -d 0x80 0x02 0x11 0x1f 0x00 0xff",
        "offset | size | field | bytes",
        "0 | 1 | Header | 80",
        "1 | 1 | PLDM Type | 02",
        "2 | 1 | Command Code | 11",
        "3 | 2 | sensorID | 1f 00",
        "5 | 1 | rearm | ff",
    ]
    assert "0X" not in "\n".join(lines)


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("order", ["", ":le", ":be"])
def test_0X_and_0x_give_the_same_bytes(capsys, protocol, order):
    head = HEADER[protocol]
    upper = invoke(capsys, protocol, *head, f"Record ID:2{order}=0X0a1B")
    lower = invoke(capsys, protocol, *head, f"Record ID:2{order}=0x0a1b")
    assert upper[0] == 0 and lower[0] == 0, (upper[1], lower[1])
    assert upper[1] == lower[1]
    want = ("0x0a", "0x1b") if protocol == "ipmi" else ("0a", "1b")
    first, second = (want[1], want[0]) if order != ":be" else want
    row = (str(len(head)), "2", "Record ID", f"{first} {second}")
    assert rows(upper[1])[len(head)] == row


def test_0X_is_taken_in_a_list_of_bytes_too(capsys):
    code, lines, _ = invoke(
        capsys, "ipmi", *HEADER["ipmi"], "Address:4=0XC0,0xa8,0X01,0x0a"
    )
    assert code == 0, lines
    assert lines[1] == "ipmitool raw 0x0a 0x43 0xc0 0xa8 0x01 0x0a"


@pytest.mark.parametrize("value", ["0X", "0X1g", "0XX1f", "00X1f", "0X 1f"])
def test_what_is_not_0X_hex_stays_refused(capsys, value):
    line = refusal(capsys, "spdm", *HEADER["spdm"], f"Sensor:1={value}")
    assert "Sensor" in line, line
    assert "is not a number" in line or "separated by commas" in line, line


# ------------------------------------------------------------------ AC-3
# a quoted head goes through repr: a control character or a backslash is
# spelt as an escape, so the head may show more than 80 characters of
# text, while the line stays bounded and names the length


@pytest.mark.parametrize("filler", ["\n", "\t", "\\", "\x00"])
def test_a_quoted_head_of_escapes_shows_more_than_80_yet_stays_bounded(capsys, filler):
    # a VALUE of nothing but control characters is stripped to none; of
    # backslashes it is not a number: either way the field is echoed quoted
    field = "Sensor:1=" + filler * 100
    line = refusal(capsys, "spdm", *HEADER["spdm"], field)
    head, cut, tail = line.partition("... (109 characters): ")
    assert cut, line
    assert head == "invocation: field " + repr(field[:SHOWN]), line
    assert len(repr(field[:SHOWN])) > SHOWN
    assert len(head) <= len("invocation: field ") + LONGEST_HEAD
    assert tail.startswith("no VALUE") or "is not a number" in tail, tail
    # the escape is printed, never the character itself
    assert line.isprintable(), line


def test_a_quoted_head_of_plain_text_shows_exactly_80(capsys):
    field = "Sensor:1=" + "x" * 100
    line = refusal(capsys, "spdm", *HEADER["spdm"], field)
    want = "invocation: field " + repr(field[:SHOWN]) + "... (109 characters): "
    assert line.startswith(want), line
    assert len(repr(field[:SHOWN])) == SHOWN + 2


def test_a_field_of_80_characters_is_echoed_whole(capsys):
    field = "Sensor:1=" + "\n" * (SHOWN - len("Sensor:1="))
    assert len(field) == SHOWN
    line = refusal(capsys, "spdm", *HEADER["spdm"], field)
    assert line.startswith("invocation: field " + repr(field) + ": "), line
    assert "characters)" not in line, line

"""Acceptance tests for the fix "invocation clips a long field in its
refusal line instead of printing it twice in full".

Black-box against ``bmc_toolkit.spec.invocation.render`` and the CLI
``main``: a refusal echoes the caller's text whole when it is at most 80
characters, else its first 80 characters followed by ``... (N characters)``;
short fields keep develop's text byte for byte; accepted fields, exit codes
and the number reading do not change.
"""

import sys

import pytest

from bmc_toolkit.spec.cli import main
from bmc_toolkit.spec.invocation import FieldError, render

SHOWN = 80
NINES_80 = "9" * SHOWN


@pytest.fixture(autouse=True)
def no_library(monkeypatch, tmp_path):
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path / "no-such-library"))


def refusal(protocol, *fields):
    with pytest.raises(FieldError) as caught:
        render(protocol, list(fields))
    return str(caught.value)


def cut(text, quoted=False):
    """The AC-1 form of a text over 80 characters."""
    head = repr(text[:SHOWN]) if quoted else text[:SHOWN]
    return f"{head}... ({len(text)} characters)"


# ----------------------------------------------------------------- AC-1
# every echo site, whole at 80 and cut at 81 or more


def test_a_field_of_exactly_80_characters_is_echoed_whole():
    field = "X:1=" + "9" * (SHOWN - 4)
    assert len(field) == SHOWN
    text = refusal("spdm", field)
    assert text == f"field {field!r}: {field[4:]} does not fit 1 byte"


def test_a_field_of_81_characters_is_cut_with_its_length_and_keeps_its_quotes():
    field = "X:1=" + "9" * (SHOWN - 3)
    assert len(field) == SHOWN + 1
    text = refusal("spdm", field)
    assert text == f"field {cut(field, True)}: {field[4:]} does not fit 1 byte"
    # the quotes stay around the 80 characters, the length follows them
    assert text.startswith(f"field '{field[:SHOWN]}'... (81 characters): ")


def test_a_value_of_80_characters_is_whole_while_the_field_around_it_is_cut():
    # the field is 84 characters and cut; its VALUE is 80 and shown whole
    field = "X:1=" + NINES_80
    text = refusal("spdm", field)
    assert text == f"field {cut(field, True)}: {NINES_80} does not fit 1 byte"


def test_a_value_of_81_characters_is_cut_in_does_not_fit():
    value = "9" * (SHOWN + 1)
    text = refusal("spdm", "X:1=" + value)
    assert text.endswith(f": {cut(value)} does not fit 1 byte")
    assert "(81 characters) does not fit 1 byte" in text


def test_a_long_hex_value_is_cut_in_does_not_fit_for_several_bytes():
    value = "0x" + "f" * 1000
    text = refusal("spdm", "X:4=" + value)
    assert text.endswith(f": {cut(value)} does not fit 4 bytes")


def test_a_long_negative_value_is_cut_in_is_negative():
    value = "-" + "9" * 1000
    text = refusal("spdm", "X:1=" + value)
    assert text.endswith(f": {cut(value)} is negative")


def test_a_long_non_number_is_cut_in_is_not_a_number_with_quotes():
    value = "q" * 1000
    text = refusal("spdm", "X:1=" + value)
    assert text.endswith(
        f": {cut(value, True)} is not a number: "
        "write hex with 0x (0x0a), decimal without a leading zero"
    )


def test_a_long_list_byte_without_0x_is_cut_with_quotes():
    part = "z" * 1000
    text = refusal("spdm", "X:2=0x01," + part)
    assert text.endswith(
        f": byte {cut(part, True)} of the list: write every byte with 0x"
    )


def test_a_long_list_byte_over_one_byte_is_cut_unquoted():
    part = "0x" + "f" * 1000
    text = refusal("spdm", "X:2=0x01," + part)
    assert text.endswith(f": {cut(part)} of the list is more than one byte")


def test_a_long_protocol_is_cut_with_quotes():
    protocol = "p" * 1000
    text = refusal(protocol, "X:1=0")
    assert text == (
        f"unknown protocol {cut(protocol, True)}; "
        # nc-si since T52, nvme-mi since T53
        "it is one of ipmi, mctp-control, nc-si, nvme-mi, pldm, spdm"
    )


def test_a_long_ipmi_netfn_field_is_cut_in_the_one_byte_refusal():
    field = "NetFn:2=" + "<" + "x" * 1000 + ">"
    text = refusal("ipmi", field, "Cmd:1=0x01")
    assert text == f"field {cut(field, True)}: NetFn and Cmd are one byte each"


def test_a_long_field_refused_by_its_size_is_cut_once():
    field = "Flags:" + "9" * 5000 + "=0"
    text = refusal("spdm", field)
    assert text == (
        f"field {cut(field, True)}: SIZE is above 65535, the most bytes a field takes"
    )


# ----------------------------------------------------------------- AC-2
# the six baseline inputs, each at most 300 characters with its reason and NAME

BASELINES = [
    pytest.param(
        "X:1=" + "9" * 1_000_000, "does not fit 1 byte", "X:1=", id="million-nines"
    ),
    pytest.param(
        "Flags:65536=" + ",".join(["0x00"] * 65536), "65535", "Flags:", id="list-65536"
    ),
    pytest.param("Flags:" + "9" * 5000 + "=0", "65535", "Flags:", id="size-5000"),
    pytest.param("X:1=" + "q" * 10000, "is not a number", "X:1=", id="non-number"),
    pytest.param("X:1=-" + "9" * 10000, "is negative", "X:1=", id="negative"),
    pytest.param(
        "X:2=0x01," + "z" * 10000, "write every byte with 0x", "X:2=", id="bad-byte"
    ),
]


@pytest.mark.parametrize(("field", "reason", "name"), BASELINES)
def test_a_baseline_long_field_gives_a_refusal_of_at_most_300_characters(
    field, reason, name
):
    text = refusal("spdm", field)
    assert len(text) <= 300, len(text)
    assert reason in text
    assert text.startswith(f"field '{name}")
    assert f"({len(field)} characters)" in text


def test_the_million_nines_refusal_ends_with_its_reason():
    text = refusal("spdm", "X:1=" + "9" * 1_000_000)
    assert text.endswith("does not fit 1 byte")
    assert text.startswith("field 'X:1=" + "9" * 76 + "'... (1000004 characters): ")


# ----------------------------------------------------------------- AC-3
# fields of at most 80 characters keep develop's text byte for byte

DEVELOP_TEXT = [
    ("spdm", ["Code:1=-0x10"], "field 'Code:1=-0x10': -0x10 is negative"),
    (
        "spdm",
        ["Code:1=08"],
        "field 'Code:1=08': '08' is not a number: write hex with 0x (0x0a), "
        "decimal without a leading zero",
    ),
    ("spdm", ["Code:1=300"], "field 'Code:1=300': 300 does not fit 1 byte"),
    (
        "spdm",
        ["Code:2=0x10000"],
        "field 'Code:2=0x10000': 0x10000 does not fit 2 bytes",
    ),
    (
        "spdm",
        ["L:2=0x01,10"],
        "field 'L:2=0x01,10': byte '10' of the list: write every byte with 0x",
    ),
    (
        "spdm",
        ["L:2=0x01,0x100"],
        "field 'L:2=0x01,0x100': 0x100 of the list is more than one byte",
    ),
    (
        "nvme",
        ["X:1=0"],
        # T52 added nc-si to the protocols this line names, T53 nvme-mi
        "unknown protocol 'nvme'; it is one of ipmi, mctp-control, nc-si, "
        "nvme-mi, pldm, spdm",
    ),
    (
        "ipmi",
        ["NetFn:2=0x06", "Cmd:1=0x01"],
        "field 'NetFn:2=0x06': NetFn and Cmd are one byte each",
    ),
    # a field holding a quote keeps repr's double quotes, as on develop
    (
        "spdm",
        ["X:1=it's"],
        "field \"X:1=it's\": \"it's\" is not a number: write hex with 0x (0x0a), "
        "decimal without a leading zero",
    ),
]


@pytest.mark.parametrize(("protocol", "fields", "message"), DEVELOP_TEXT)
def test_a_short_field_keeps_develops_refusal_text(protocol, fields, message):
    assert refusal(protocol, *fields) == message


def test_no_short_refusal_carries_a_character_count():
    for protocol, fields, _ in DEVELOP_TEXT:
        assert "characters)" not in refusal(protocol, *fields)


# ----------------------------------------------------------------- AC-4
# accepted fields, exit codes and the number reading are unchanged


def test_an_accepted_long_field_prints_the_same_lines(capsys):
    # a 1000-digit zero value and a 65535-byte field are laid out, not cut
    code = main(["invocation", "spdm", "X:1=" + "0" * 1000, "Y:2=0x1234"])
    out = capsys.readouterr().out.splitlines()
    assert code == 0
    assert out[0] == "bytes: 3"
    assert out[1] == "mctp-client eid <eid> type spdm data 00 34 12"
    assert out[3] == "0 | 1 | X | 00"
    assert out[4] == "1 | 2 | Y | 34 12"
    assert not [ln for ln in out if "characters)" in ln]


def test_a_long_field_is_refused_on_the_command_line_with_exit_2(capsys):
    code = main(["invocation", "spdm", "Code:1=0x84", "X:1=" + "9" * 5000])
    lines = capsys.readouterr().out.splitlines()
    assert code == 2
    assert len(lines) == 1
    assert len(lines[0]) <= 300
    assert lines[0].startswith("invocation: field 'X:1=" + "9" * 76 + "'... (5004")
    assert lines[0].endswith("does not fit 1 byte")


def test_the_clipping_does_not_read_the_number():
    # a value too long for int() under a tight digit limit is still clipped,
    # not converted: a FieldError with the cut value, never a ValueError
    limit = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(640)
    try:
        value = "9" * 5000
        text = refusal("spdm", "X:1=" + value)
    finally:
        sys.set_int_max_str_digits(limit)
    assert text.endswith(f": {cut(value)} does not fit 1 byte")
    assert "(5000 characters)" in text


def test_a_refusal_of_a_short_field_keeps_exit_2_and_one_line(capsys):
    code = main(["invocation", "spdm", "Code:1=300"])
    lines = capsys.readouterr().out.splitlines()
    assert code == 2
    assert lines == ["invocation: field 'Code:1=300': 300 does not fit 1 byte"]

"""The ``invocation`` command: the bytes of a request arranged from the
fields the caller gives, printed in each sending tool's syntax."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
COMMANDS_DOC = ROOT / "docs" / "COMMANDS.md"
LAUNCHER = ROOT / "skills" / "bmc-spec" / "scripts" / "bmcspec.py"

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


def test_a_placeholder_takes_the_0x_of_the_ipmitool_line(capsys):
    code, lines = run(
        capsys, "ipmi", "NetFn:1=0x04", "Cmd:1=0x2d", "Sensor:1=<sensor number>"
    )
    assert code == 0, lines
    assert tool_lines(lines) == ["ipmitool raw 0x04 0x2d 0x<sensor number>"]


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
        "pldmtool raw -m <eid> -d 0x80 0x02 0x11 0x<sensor id 0> 0x<sensor id 1>",
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


# ------------------------------------------- refusals added after PR #67

HEADER = {
    "ipmi": ["NetFn:1=0x0a", "Cmd:1=0x23"],
    "mctp-control": ["Header:1=0x80"],
    "pldm": ["Header:1=0x80"],
    "spdm": ["Version:1=0x12"],
}


def refused(capsys, *argv):
    code, lines = run(capsys, *argv)
    assert code == 2, lines[:3]
    assert not tool_lines(lines)
    assert not [ln for ln in lines if ln.startswith("bytes:")]
    return "\n".join(lines)


@pytest.mark.parametrize("protocol", sorted(HEADER))
@pytest.mark.parametrize(
    "field",
    [
        "Reservation ID:2=<lsb>,<msb>",
        "X:1=<a> <b>",
        "X:1=<a><b>",
        "X:1=<<a>>",
    ],
)
def test_two_placeholders_in_one_field_are_refused(capsys, protocol, field):
    text = refused(capsys, protocol, *HEADER[protocol], field)
    assert field in text
    assert "one placeholder" in text


@pytest.mark.parametrize(
    "inner", ["sensor number", "record id, LSB first", "eid 0x08-0xfe"]
)
def test_one_placeholder_may_hold_commas_and_spaces(capsys, inner):
    code, lines = run(capsys, "spdm", f"One:1=<{inner}>", f"Three:3=<{inner}>")
    assert code == 0, lines
    assert tool_lines(lines) == [
        "mctp-client eid <eid> type spdm data "
        f"<{inner}> <{inner} 0> <{inner} 1> <{inner} 2>"
    ]


@pytest.mark.parametrize(
    "field",
    [
        "Flags:65536=0",
        "Flags:99999999999=0",
        "Flags:65536=<x>",
        "Flags:65536=0x00,0x01",
        # more digits than int() converts
        pytest.param("Flags:" + "9" * 5000 + "=0", id="size-of-5000-digits"),
    ],
)
def test_a_size_above_the_limit_is_refused(capsys, field):
    text = refused(capsys, "spdm", field)
    # a field over 80 characters is echoed cut, followed by its length
    if len(field) > 80:
        assert field[:80] in text and f"({len(field)} characters)" in text
    else:
        assert field in text
    assert "65535" in text


@pytest.mark.parametrize(
    ("field", "first"), [("Data:65535=0", "00"), ("Data:65535=1", "01")]
)
def test_the_largest_size_is_laid_out(capsys, field, first):
    code, lines = run(capsys, "spdm", field)
    assert code == 0, lines[:1]
    assert lines[0] == "bytes: 65535"
    data = tool_lines(lines)[0].split(" data ")[1].split(" ")
    assert len(data) == 65535
    assert data[0] == first
    assert set(data[1:]) == {"00"}


def test_the_largest_size_takes_a_placeholder(capsys):
    code, lines = run(capsys, "spdm", "Chain:65535=<chain>")
    assert code == 0, lines[:1]
    data = tool_lines(lines)[0].split(" data ")[1]
    assert data.startswith("<chain 0> <chain 1> ")
    assert data.endswith(" <chain 65534>")


@pytest.mark.parametrize(
    ("field", "data"),
    [
        ("X:1=255", "ff"),
        ("X:2=0xffff", "ff ff"),
        ("X:2=65535", "ff ff"),
        ("X:3:be=0xffffff", "ff ff ff"),
    ],
)
def test_the_largest_number_of_a_size_still_fits(capsys, field, data):
    code, lines = run(capsys, "spdm", field)
    assert code == 0, lines
    assert tool_lines(lines) == ["mctp-client eid <eid> type spdm data " + data]


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("X:1=256", "does not fit 1 byte"),
        ("X:2=0x10000", "does not fit 2 bytes"),
        ("X:2=65536", "does not fit 2 bytes"),
        pytest.param(
            "X:65535=0x1" + "00" * 65535,
            "does not fit 65535 bytes",
            id="one-more-than-65535-bytes",
        ),
    ],
)
def test_one_more_than_fits_is_refused_with_the_same_reason(capsys, field, reason):
    text = refused(capsys, "spdm", field)
    assert reason in text


def test_commands_doc_lists_the_refusals():
    doc = " ".join(COMMANDS_DOC.read_text("utf-8").split())
    start = doc.index("Refused with exit 2")
    listed = doc[start : doc.index("The command knows no Document", start)]
    for word in (
        "without NAME",
        "without VALUE",
        "spaces instead of commas",
        "`<>`",
        "`<x`",
        "more than one placeholder",
        "above 65535",
    ):
        assert word in listed, word


# ------------------- how a number is read (follow-ups of PR #67 and PR #68)

THREE = "\u0663"  # ARABIC-INDIC DIGIT THREE: int() reads it as 3
ZERO = "\u0660"  # ARABIC-INDIC DIGIT ZERO
NINES = 10**4301 - 1  # one digit more than int() converts by default
NINES_SIZE = (NINES.bit_length() + 7) // 8  # the bytes it just fits


def decimal(number):
    """``str(number)``, whatever its length; the limit is put back after."""
    limit = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    try:
        return str(number)
    finally:
        sys.set_int_max_str_digits(limit)


def data_of(lines):
    return tool_lines(lines)[0].split(" data ")[1]


def spaced(raw):
    return " ".join(f"{byte:02x}" for byte in raw)


@pytest.mark.parametrize(
    "size",
    [THREE, "1" + THREE, ZERO * 6 + THREE, "0" + ZERO * 5 + THREE, "\uff13"],
    ids=["one", "after-ascii", "seven", "seven-after-ascii-zero", "fullwidth"],
)
def test_a_size_in_digits_of_another_script_is_refused(capsys, size):
    field = f"Code:{size}=0x010203"
    text = refused(capsys, "spdm", field)
    assert field in text
    assert "SIZE, the field's bytes, is missing or not a number" in text
    assert "65535" not in text


@pytest.mark.parametrize(
    "field",
    [
        f"X:{THREE}=A:1=5",
        f"X:1{THREE}=A:1=5",
        f"X:{THREE}:be=A:2=5",
        f"X:{THREE}=<a>:1=5",
        f"X:{ZERO * 6}{THREE}=0x01,0x02:2=0x0102",
    ],
    ids=["one", "after-ascii", "with-order", "placeholder", "seven"],
)
def test_a_size_of_another_script_is_not_skipped_for_a_later_one(capsys, field):
    # NAME may hold : and =, so the text after such a SIZE could be read as
    # the rest of a NAME that ends at a later :N=
    text = refused(capsys, "spdm", field)
    assert field in text
    assert "SIZE, the field's bytes, is missing or not a number" in text


@pytest.mark.parametrize(
    ("field", "row"),
    [
        ("Flags (b0=1):1=0", "0 | 1 | Flags (b0=1) | 00"),
        ("Byte 1: flags:1=0", "0 | 1 | Byte 1: flags | 00"),
        ("A:1:2=5", "0 | 2 | A:1 | 05 00"),
        ("X:1=<see 5: 1=on>", "0 | 1 | X | <see 5: 1=on>"),
    ],
)
def test_a_name_with_a_colon_or_an_equals_sign_is_read_as_before(capsys, field, row):
    code, lines = run(capsys, "spdm", field)
    assert code == 0, lines
    assert lines[-1] == row


def test_a_size_in_ascii_digits_keeps_its_leading_zeros(capsys):
    code, lines = run(capsys, "spdm", "Code:003=0x010203")
    assert code == 0, lines
    assert data_of(lines) == "03 02 01"


@pytest.mark.parametrize(
    "value", ["1" + THREE, THREE, ZERO, "1" + ZERO + "0"], ids=lambda v: ascii(v)
)
def test_a_decimal_in_digits_of_another_script_is_refused(capsys, value):
    text = refused(capsys, "spdm", f"Code:2={value}")
    assert "is not a number" in text


@pytest.mark.parametrize("value", ["-abc", "-", "--5", "-08", "-0x", "-e1"])
def test_a_dash_before_what_is_no_number_is_not_called_negative(capsys, value):
    text = refused(capsys, "spdm", f"Code:1={value}")
    assert f"{value!r} is not a number: write hex with 0x" in text
    assert "negative" not in text


@pytest.mark.parametrize("value", ["-1", "-0x10", "-0", "-65536"])
def test_a_dash_before_a_number_is_negative(capsys, value):
    text = refused(capsys, "spdm", f"Code:1={value}")
    assert f"{value} is negative" in text
    assert "not a number" not in text


@pytest.mark.parametrize(
    ("order", "raw"),
    [
        ("", NINES.to_bytes(NINES_SIZE, "little")),
        (":le", NINES.to_bytes(NINES_SIZE, "little")),
        (":be", NINES.to_bytes(NINES_SIZE, "big")),
    ],
    ids=["default", "le", "be"],
)
def test_a_decimal_longer_than_int_converts_is_laid_out(capsys, order, raw):
    code, lines = run(capsys, "spdm", f"X:{NINES_SIZE}{order}={'9' * 4301}")
    assert code == 0, lines[:1]
    assert lines[0] == f"bytes: {NINES_SIZE}"
    assert data_of(lines) == spaced(raw)


def test_a_decimal_of_any_length_is_read_digit_for_digit():
    from bmc_toolkit.spec.invocation import render

    lengths = set()
    # powers of 7: every length around 600, 1200 and 4300 digits
    for power in (*range(700, 725), *range(1415, 1425), *range(5082, 5095)):
        number = 7**power
        written = decimal(number)
        lengths.add(len(written))
        size = (number.bit_length() + 7) // 8
        lines = render("spdm", [f"X:{size}:be={written}"])
        assert data_of(lines) == spaced(number.to_bytes(size, "big")), len(written)
    assert lengths >= {599, 600, 601, 1200, 1201, 4300, 4301}


def test_a_long_decimal_in_a_larger_field_is_padded_with_zeros(capsys):
    code, lines = run(capsys, "spdm", "X:65535=" + "9" * 4301)
    assert code == 0, lines[:1]
    assert lines[0] == "bytes: 65535"
    assert data_of(lines) == spaced(NINES.to_bytes(65535, "little"))


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        pytest.param("X:4=" + "9" * 5000, "does not fit 4 bytes", id="5000-nines"),
        pytest.param(
            f"X:{NINES_SIZE - 1}=" + "9" * 4301,
            f"does not fit {NINES_SIZE - 1} bytes",
            id="one-byte-short",
        ),
    ],
)
def test_a_long_decimal_that_does_not_fit_is_refused_as_any_number(
    capsys, field, reason
):
    text = refused(capsys, "spdm", field)
    assert text.endswith(reason)
    assert "too long" not in text


@pytest.mark.parametrize(
    ("value", "data"),
    [
        pytest.param("0" * 5000, "00", id="alone"),
        pytest.param("0," + "0" * 5000, "00 00", id="in-a-list"),
    ],
)
def test_zeros_of_any_number_are_zero(capsys, value, data):
    code, lines = run(capsys, "spdm", f"X:{value.count(',') + 1}={value}")
    assert code == 0, lines[:1]
    assert data_of(lines) == data


@pytest.mark.parametrize("size", [1, 2, 3, 4, 8, 16, 64, 1000, 65535])
def test_the_largest_number_of_a_size_fits_when_written_in_decimal(capsys, size):
    # the refusal by the count of digits must not reach a number that fits
    largest = 256**size - 1
    code, lines = run(capsys, "spdm", f"X:{size}={decimal(largest)}")
    assert code == 0, lines[:1]
    assert set(data_of(lines).split(" ")) == {"ff"}
    text = refused(capsys, "spdm", f"X:{size}={decimal(largest + 1)}")
    assert text.endswith(f"does not fit {size} byte{'s' if size > 1 else ''}")


def test_a_decimal_far_too_long_for_its_size_is_refused_as_not_fitting():
    # no command line carries a field this long: handed over in process
    from bmc_toolkit.spec.invocation import FieldError, render

    with pytest.raises(FieldError) as caught:
        render("spdm", ["X:1=" + "9" * 1_000_000])
    assert str(caught.value).endswith("does not fit 1 byte")


@pytest.mark.parametrize(
    ("field", "code", "tail"),
    [
        pytest.param("X:65535=" + "9" * 4301, 0, " 00 00", id="fits"),
        pytest.param("X:4=" + "9" * 5000, 2, "does not fit 4 bytes", id="too-big"),
        pytest.param("X:1=" + "0" * 5000, 0, "0 | 1 | X | 00", id="zeros"),
        pytest.param("X:2=0," + "0" * 5000, 0, "0 | 2 | X | 00 00", id="zero-list"),
    ],
)
def test_the_interpreters_limit_on_decimals_changes_nothing(field, code, tail):
    seen = []
    for limit in ("0", "640", None):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        env.pop("CLAUDE_PLUGIN_DATA", None)
        env.pop("PYTHONINTMAXSTRDIGITS", None)
        if limit is not None:
            env["PYTHONINTMAXSTRDIGITS"] = limit
        done = subprocess.run(
            [sys.executable, str(LAUNCHER), "invocation", "spdm", field],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=60,
        )
        assert done.returncode == code, (limit, done.stderr[-300:])
        assert done.stderr == "", limit
        assert done.stdout.rstrip("\n").endswith(tail), limit
        seen.append(done.stdout)
    assert seen[0] == seen[1] == seen[2]


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
    # T46: the one Library read is `--subcommand`; the claim was "no Library"
    for word in (
        "NAME:SIZE=VALUE",
        "NAME:SIZE:be=VALUE",
        "exit 2",
        "reads no Document",
        "`--subcommand`",
    ):
        assert word in doc, word


# ------------------------------------------------- T40: a placeholder's 0x
# ipmitool raw and pldmtool raw read every number with base 0: a placeholder
# printed bare and replaced by two hex digits (30) sends decimal 30, and 08
# is refused as octal. Where every byte carries 0x the placeholder does too.

NONCE = "Nonce:32=<nonce>"


def test_t40_ac1_ipmi_prints_a_one_byte_placeholder_with_0x(capsys):
    code, lines = run(
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


@pytest.mark.parametrize("order", ["", ":be", ":le"])
def test_t40_ac2_ipmi_prints_one_0x_token_per_placeholder_byte(capsys, order):
    code, lines = run(
        capsys,
        "ipmi",
        "NetFn:1=0x0a",
        "Cmd:1=0x23",
        f"Reservation ID:2{order}=<reservation id>",
        "Record ID:2=0x0102",
        "Offset:1=<offset>",
        "Count:3=<count>",
    )
    assert code == 0, lines
    assert lines == [
        "bytes: 10",
        "ipmitool raw 0x0a 0x23 0x<reservation id 0> 0x<reservation id 1> "
        "0x02 0x01 0x<offset> 0x<count 0> 0x<count 1> 0x<count 2>",
        "offset | size | field | bytes",
        "0 | 1 | NetFn | 0x0a",
        "1 | 1 | Cmd | 0x23",
        "2 | 2 | Reservation ID | 0x<reservation id 0> 0x<reservation id 1>",
        "4 | 2 | Record ID | 0x02 0x01",
        "6 | 1 | Offset | 0x<offset>",
        "7 | 3 | Count | 0x<count 0> 0x<count 1> 0x<count 2>",
    ]


def test_t40_ac3_pldm_prints_0x_in_pldmtool_only(capsys):
    code, lines = run(
        capsys,
        "pldm",
        "Header:1=0x80",
        "PLDM Type:1=0x02",
        "Command Code:1=0x11",
        "sensorID:2=<sensor id>",
        "rearmEventState:1=<rearm>",
    )
    assert code == 0, lines
    assert lines == [
        "bytes: 6",
        "mctp-client eid <eid> type pldm data 80 02 11 "
        "<sensor id 0> <sensor id 1> <rearm>",
        "pldmtool raw -m <eid> -d 0x80 0x02 0x11 "
        "0x<sensor id 0> 0x<sensor id 1> 0x<rearm>",
        "offset | size | field | bytes",
        "0 | 1 | Header | 80",
        "1 | 1 | PLDM Type | 02",
        "2 | 1 | Command Code | 11",
        "3 | 2 | sensorID | <sensor id 0> <sensor id 1>",
        "5 | 1 | rearmEventState | <rearm>",
    ]


def test_t40_ac4_spdm_placeholders_stay_bare(capsys):
    code, lines = run(
        capsys,
        "spdm",
        "SPDMVersion:1=<negotiated version>",
        "RequestResponseCode:1=0x83",
        "Param1:1=0",
        "Param2:1=0xff",
        NONCE,
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


def test_t40_ac4_mctp_control_placeholders_stay_bare(capsys):
    code, lines = run(
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


@pytest.mark.parametrize("protocol", sorted(HEADER))
@pytest.mark.parametrize("value", ["0x<sensor number>", "<sensor number>0"])
def test_t40_ac5_a_0x_around_a_placeholder_is_still_refused(capsys, protocol, value):
    field = f"Sensor:1={value}"
    text = refused(capsys, protocol, *HEADER[protocol], field)
    assert field in text
    assert "a placeholder is written <text>" in text


@pytest.mark.parametrize("protocol", sorted(HEADER))
def test_t40_ac5_the_total_counts_a_placeholder_by_its_size(capsys, protocol):
    head = HEADER[protocol]
    code, lines = run(capsys, protocol, *head, "A:1=<a>", "B:4=<b>")
    assert code == 0, lines
    assert lines[0] == f"bytes: {len(head) + 5}"


def test_t40_ac6_docs_say_how_a_placeholder_is_printed():
    skill = SKILL.read_text("utf-8")
    (row,) = [ln for ln in skill.splitlines() if ln.startswith("| `invocation ")]
    assert "`0x<placeholder>`" in row
    assert "two hex digits" in row
    doc = " ".join(COMMANDS_DOC.read_text("utf-8").split())
    assert "printed as it is" not in doc
    for words in (
        "two hex digits",
        "`0x<text>`",
        "`ipmitool raw`, `pldmtool raw` and the `ipmi` rows",
        "the `mctp-client` line",
    ):
        assert words in doc, words


# ------------------------------------------------- a long field in a refusal
# The refusal echoes the field, and most reasons echo its value again: a
# field of a million digits made a line of two million characters. Text
# over SHOWN characters is cut to SHOWN and followed by its length.

SHOWN = 80

SHORT_REFUSALS = [
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
        ["L:2=0x01,10"],
        "field 'L:2=0x01,10': byte '10' of the list: write every byte with 0x",
    ),
    (
        "spdm",
        ["L:2=0x01,0x100"],
        "field 'L:2=0x01,0x100': 0x100 of the list is more than one byte",
    ),
    (
        "spdm",
        ["L:3=0x01,0x02"],
        "field 'L:3=0x01,0x02': the list holds 2 bytes, SIZE is 3",
    ),
    (
        "spdm",
        ["Flags:65536=0"],
        "field 'Flags:65536=0': SIZE is above 65535, the most bytes a field takes",
    ),
    (
        "nvme",
        ["X:1=0"],
        "unknown protocol 'nvme'; it is one of ipmi, mctp-control, pldm, spdm",
    ),
    (
        "ipmi",
        ["NetFn:2=0x06", "Cmd:1=0x01"],
        "field 'NetFn:2=0x06': NetFn and Cmd are one byte each",
    ),
]


@pytest.mark.parametrize(
    ("protocol", "fields", "message"), SHORT_REFUSALS, ids=lambda v: str(v)[:20]
)
def test_a_short_field_is_refused_with_the_same_text(protocol, fields, message):
    from bmc_toolkit.spec.invocation import FieldError, render

    with pytest.raises(FieldError) as caught:
        render(protocol, fields)
    assert str(caught.value) == message


def test_a_field_of_80_characters_is_shown_whole_and_81_is_cut():
    from bmc_toolkit.spec.invocation import FieldError, render

    for length, cut in ((SHOWN, False), (SHOWN + 1, True)):
        field = "X:1=" + "9" * (length - 4)
        with pytest.raises(FieldError) as caught:
            render("spdm", [field])
        text = str(caught.value)
        assert (f"({length} characters)" in text) is cut
        if not cut:
            assert text == f"field {field!r}: {field[4:]} does not fit 1 byte"


def test_a_long_field_is_cut_with_its_length():
    from bmc_toolkit.spec.invocation import FieldError, render

    field = "X:1=" + "9" * 1000
    with pytest.raises(FieldError) as caught:
        render("spdm", [field])
    assert str(caught.value) == (
        f"field {field[:SHOWN]!r}... (1004 characters): "
        f"{'9' * SHOWN}... (1000 characters) does not fit 1 byte"
    )


LONG_REFUSALS = [
    pytest.param("spdm", "X:1=" + "9" * 1_000_000, "does not fit 1 byte", id="1M"),
    pytest.param(
        "spdm",
        "Flags:65536=" + ",".join(["0x00"] * 65536),
        "65535",
        id="list-65536",
    ),
    pytest.param("spdm", "Flags:" + "9" * 5000 + "=0", "65535", id="size-5000"),
    pytest.param("spdm", "X:1=" + "q" * 10000, "is not a number", id="not-a-number"),
    pytest.param("spdm", "X:1=-" + "9" * 10000, "is negative", id="negative"),
    pytest.param(
        "spdm", "X:2=0x01," + "z" * 10000, "write every byte with 0x", id="list-byte"
    ),
    pytest.param(
        "spdm",
        "X:2=0x01,0x" + "f" * 10000,
        "of the list is more than one byte",
        id="list-hex",
    ),
    pytest.param("p" * 10000, "X:1=0", "unknown protocol", id="protocol"),
]


@pytest.mark.parametrize(("protocol", "field", "reason"), LONG_REFUSALS)
def test_a_long_field_gives_a_short_refusal(protocol, field, reason):
    from bmc_toolkit.spec.invocation import FieldError, render

    with pytest.raises(FieldError) as caught:
        render(protocol, [field])
    text = str(caught.value)
    assert len(text) <= 300, len(text)
    assert reason in text
    # the field, or the protocol refused before any field is read
    assert (field if protocol == "spdm" else protocol)[:5] in text
    assert "characters)" in text


def test_a_long_field_is_refused_on_the_command_line_in_one_short_line(capsys):
    field = "X:1=" + "9" * 5000
    code, lines = run(capsys, "spdm", "Code:1=0x84", field)
    assert code == 2
    assert len(lines) == 1 and len(lines[0]) <= 300
    assert lines[0].startswith("invocation: field 'X:1=999")
    assert lines[0].endswith("does not fit 1 byte")


def test_commands_doc_says_a_long_field_is_shown_cut():
    text = " ".join(COMMANDS_DOC.read_text(encoding="utf-8").split())
    assert "longer than 80 characters" in text


# ------------------------- what the docs say a placeholder and hex may be
# A placeholder without its `<`, and a bracket inside one, were refused
# without the docs naming them; `0X` was taken without the docs saying so.


def _refusal_docs() -> str:
    doc = " ".join(COMMANDS_DOC.read_text("utf-8").split())
    start = doc.index("`invocation PROTOCOL")
    return doc[start : doc.index("The command knows no Document", start)]


def test_docs_name_the_placeholder_forms_and_0X():
    text = _refusal_docs()
    for word in ("`x>`", "`<>>`", "`<a>b>`", "`0X`"):
        assert word in text, word


def test_the_forms_the_docs_name_are_handled_as_they_say(capsys):
    text = refused(capsys, "spdm", "X:1=x>")
    assert text.endswith("a placeholder is written <text>")
    for value in ("<>>", "<a>b>"):
        text = refused(capsys, "spdm", f"X:1={value}")
        assert "a field takes one placeholder" in text, value
    code, lines = run(capsys, "spdm", "X:1=0X1f")
    assert code == 0 and lines[-1] == "0 | 1 | X | 1f"

"""Reviewer acceptance tests: how ``invocation`` reads a SIZE and a VALUE
(AC-1 to AC-7).

Black box: the tests call the CLI entry point with ``invocation PROTOCOL
FIELD ...`` and read what it prints. Two exceptions, both asked for by the
criteria: AC-5 runs the launcher in an interpreter of its own, once per
setting of ``PYTHONINTMAXSTRDIGITS``, and AC-6 hands a field of a million
digits to ``render`` in process, since no command line carries it.

Expected bytes are computed here with ``int.to_bytes``. A long decimal is
written by ``written``, which divides by ``10**500`` and so never asks the
interpreter for a conversion its limit could refuse.

On develop a SIZE or a VALUE in digits of another script is laid out, a
``-`` in front of anything is called negative, and a decimal of more than
4300 digits is refused as too long to read. The tests that pin what must
stay as it was (AC-7, and the negative numbers of AC-3) depend on the
``changed`` fixture, which fails on develop.

Round 2: a SIZE of another script in front of a later ``:N=`` (AC-1). NAME
may hold ``:`` and ``=``, so such a field must not be read as one with a
longer NAME; names and values that hold ``:`` or ``=`` stay as they were.
"""

import os
import random
import re
import subprocess
import sys
from pathlib import Path

import pytest

from bmc_toolkit.spec import invocation
from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "skills" / "bmc-spec" / "scripts" / "bmcspec.py"
TOOLS = ("ipmitool", "mctp-client", "pldmtool")
MCTP = "mctp-client eid <eid> type spdm data "
# a placeholder is one token even with a space inside
TOKEN = re.compile(r"<[^>]*>|\S+")
HEADER = {
    "ipmi": ["NetFn:1=0x0a", "Cmd:1=0x43"],
    "mctp-control": ["Header:1=0x80"],
    "pldm": ["Header:1=0x80"],
    "spdm": ["SPDMVersion:1=0x12"],
}
NO_SIZE = "SIZE, the field's bytes, is missing or not a number"
CHUNK_DIGITS = 500
CHUNK = 10**CHUNK_DIGITS

# the digit zero of scripts whose digits int() and \d read as numbers
ARABIC_INDIC = 0x0660
DEVANAGARI = 0x0966
THAI = 0x0E50
FULLWIDTH = 0xFF10
MATH_BOLD = 0x1D7CE
SCRIPTS = {
    "arabic-indic": ARABIC_INDIC,
    "devanagari": DEVANAGARI,
    "thai": THAI,
    "fullwidth": FULLWIDTH,
    "math-bold": MATH_BOLD,
}


def other(digits: str, zero: int = ARABIC_INDIC) -> str:
    """``digits`` written in the script whose zero is ``zero``."""
    return "".join(chr(zero + int(ch)) for ch in digits)


def written(number: int) -> str:
    """The decimal digits of ``number``, whatever the interpreter's limit."""
    pieces = []
    while number >= CHUNK:
        number, low = divmod(number, CHUNK)
        pieces.append(f"{low:0{CHUNK_DIGITS}d}")
    pieces.append(str(number))
    return "".join(reversed(pieces))


def hexed(raw: bytes) -> list[str]:
    return [f"{byte:02x}" for byte in raw]


@pytest.fixture(autouse=True)
def no_library(monkeypatch, tmp_path):
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path / "no-such-library"))


@pytest.fixture
def limit():
    """Sets the interpreter's limit on decimal strings; put back afterwards."""
    before = sys.get_int_max_str_digits()
    yield sys.set_int_max_str_digits
    sys.set_int_max_str_digits(before)


@pytest.fixture
def changed():
    """What stays as it was is pinned only next to what changed: on develop
    a SIZE in Arabic-Indic digits is laid out, so the tests using this
    fixture fail there."""
    with pytest.raises(invocation.FieldError):
        invocation.render("spdm", [f"Code:{other('3')}=0x010203"])


def invoke(capsys, *argv):
    """(exit code, stdout lines, everything printed)."""
    code = main(["invocation", *argv])
    got = capsys.readouterr()
    return code, got.out.splitlines(), got.out + got.err


def one_refusal(code: int, text: str) -> str:
    """The one line of a refused call: exit 2, no traceback, nothing to send."""
    assert code == 2, text[:300]
    assert "Traceback" not in text
    said = [ln for ln in text.splitlines() if ln.strip()]
    assert not [ln for ln in said if ln.split(" ")[0] in TOOLS], said[0][:300]
    assert not [ln for ln in said if ln.startswith("bytes:")], said[0][:300]
    assert len(said) == 1, [ln[:120] for ln in said[:3]]
    return said[0]


def refusal(capsys, *argv) -> str:
    code, _, text = invoke(capsys, *argv)
    return one_refusal(code, text)


def spdm_data(capsys, *fields) -> list[str]:
    """The byte tokens of the one line an accepted spdm call prints."""
    code, lines, text = invoke(capsys, "spdm", *fields)
    assert code == 0, text[:300]
    sent = [ln for ln in lines if ln.split(" ")[0] in TOOLS]
    assert len(sent) == 1, [ln[:120] for ln in sent]
    assert sent[0].startswith(MCTP), sent[0][:120]
    tokens = TOKEN.findall(sent[0][len(MCTP) :])
    assert lines[0] == f"bytes: {len(tokens)}"
    return tokens


# ------------------------------------------------------------------ AC-1

SIZES = [
    pytest.param(other("3"), id="three"),
    pytest.param("1" + other("3"), id="after-an-ascii-digit"),
    pytest.param(other("3") + "1", id="before-an-ascii-digit"),
    pytest.param(other("0000003"), id="seven-digits"),
    pytest.param("0" + other("000003"), id="seven-digits-after-an-ascii-zero"),
    pytest.param(other("3", DEVANAGARI), id="devanagari"),
    pytest.param(other("3", THAI), id="thai"),
    pytest.param(other("3", FULLWIDTH), id="fullwidth"),
    pytest.param(other("3", MATH_BOLD), id="math-bold"),
    pytest.param(other("1", ARABIC_INDIC) + other("2", FULLWIDTH), id="two-scripts"),
]


@pytest.mark.parametrize("size", SIZES)
def test_a_size_in_digits_of_another_script_is_refused_as_no_number(capsys, size):
    line = refusal(capsys, "spdm", f"Code:{size}=0x010203")
    assert "Code" in line
    assert NO_SIZE in line
    # the limit is not the reason: the SIZE was never read as a number
    assert "65535" not in line
    # word for word what a SIZE of x gets
    of_x = refusal(capsys, "spdm", "Code:x=0x010203")
    assert line.replace(f"Code:{size}=", "Code:x=") == of_x


@pytest.mark.parametrize("order", ["be", "le"])
def test_a_size_of_another_script_is_refused_with_a_byte_order_too(capsys, order):
    line = refusal(capsys, "spdm", f"Code:{other('3')}:{order}=0x010203")
    assert "Code" in line
    assert NO_SIZE in line


@pytest.mark.parametrize("protocol", sorted(HEADER))
def test_a_size_of_another_script_is_refused_for_every_protocol(capsys, protocol):
    field = f"Flags:{other('2')}=0x1234"
    line = refusal(capsys, protocol, *HEADER[protocol], field, "Last:1=0x01")
    assert "Flags" in line
    assert NO_SIZE in line


def test_ipmi_netfn_with_a_size_of_another_script_is_refused(capsys):
    line = refusal(capsys, "ipmi", f"NetFn:{other('1')}=0x06", "Cmd:1=0x01")
    assert "NetFn" in line
    assert NO_SIZE in line


def test_a_size_of_another_script_is_refused_whatever_the_value(capsys):
    for value in ("0", "<x>", "0x00,0x01,0x02", "66051"):
        line = refusal(capsys, "spdm", f"Code:{other('3')}={value}")
        assert NO_SIZE in line, value


# A SIZE of another script in front of a later :N=. NAME may hold : and =,
# so once that SIZE is no SIZE the text up to the later :N= could be read as
# a NAME and the field laid out. On develop these are refused with another
# reason (the text after the first = is no number, or the SIZE is too large).
THREE = other("3")
LATER_SIZE = [
    pytest.param(f"Code:{THREE}=A:1=5", id="one-digit"),
    pytest.param(f"Code:1{THREE}=A:1=5", id="after-an-ascii-digit"),
    pytest.param(f"Code:{THREE}1=A:1=5", id="before-an-ascii-digit"),
    pytest.param(f"Code:{other('0000003')}=0x01,0x02:2=0x0102", id="seven-digits"),
    pytest.param(f"Code:{THREE}:be=A:2=5", id="most-significant-first"),
    pytest.param(f"Code:{THREE}:le=A:2=5", id="least-significant-first"),
    pytest.param(f"Code:{THREE}=A:2:be=5", id="later-one-with-an-order"),
    pytest.param(f"Code:{THREE}=<a>:1=5", id="placeholder-between"),
    pytest.param(f"Code:{THREE}=A:1=<a>", id="placeholder-as-value"),
    pytest.param(f"Code:{THREE}=A:2=0x01,0x02", id="list-as-value"),
    pytest.param(f"Code:{THREE}=B:{other('2')}=A:1=5", id="two-of-them"),
    pytest.param(f"a:b=Code:{THREE}=A:1=5", id="after-a-colon-in-the-name"),
    pytest.param(f"Code:{THREE}=A:1=5:1=5", id="two-later-ones"),
]


@pytest.mark.parametrize("field", LATER_SIZE)
def test_a_later_size_does_not_hide_one_of_another_script(capsys, field):
    line = refusal(capsys, "spdm", field)
    assert "Code" in line
    assert NO_SIZE in line
    assert "65535" not in line


@pytest.mark.parametrize("zero", list(SCRIPTS.values()), ids=list(SCRIPTS))
def test_a_later_size_hides_a_size_of_no_script(capsys, zero):
    three = other("3", zero)
    for field in (f"Code:{three}=A:1=5", f"Code:{three}:be=A:2=5"):
        line = refusal(capsys, "spdm", field)
        assert NO_SIZE in line, field


@pytest.mark.parametrize("protocol", sorted(HEADER))
def test_a_later_size_hides_none_for_any_protocol(capsys, protocol):
    field = f"Flags:{other('2')}=A:1=5"
    line = refusal(capsys, protocol, *HEADER[protocol], field, "Last:1=0x01")
    assert "Flags" in line
    assert NO_SIZE in line


# ------------------------------------------------------------------ AC-2

VALUES = [
    pytest.param("Code:2=1" + other("3"), id="13"),
    pytest.param("Code:1=1" + other("0"), id="10-in-one-byte"),
    pytest.param("Code:2:be=1" + other("3"), id="13-most-significant-first"),
    pytest.param("Code:4=12" + other("34"), id="1234"),
    pytest.param("Code:4=1" + other("2") + "3", id="between-ascii-digits"),
    pytest.param("Code:2=1" + other("3", DEVANAGARI), id="devanagari"),
    pytest.param("Code:2=1" + other("3", THAI), id="thai"),
    pytest.param("Code:2=1" + other("3", FULLWIDTH), id="fullwidth"),
    pytest.param("Code:2=1" + other("3", MATH_BOLD), id="math-bold"),
]


@pytest.mark.parametrize("field", VALUES)
def test_a_decimal_with_a_digit_of_another_script_is_no_number(capsys, field):
    line = refusal(capsys, "spdm", field)
    assert "Code" in line
    assert "is not a number" in line


@pytest.mark.parametrize("zero", list(SCRIPTS.values()), ids=list(SCRIPTS))
def test_no_digit_of_a_decimal_may_be_of_another_script(capsys, zero):
    digits = "12345"
    for at, digit in enumerate(digits):
        value = digits[:at] + other(digit, zero) + digits[at + 1 :]
        line = refusal(capsys, "spdm", f"Code:4={value}")
        assert "is not a number" in line, at
    # all five of them
    line = refusal(capsys, "spdm", f"Code:4={other(digits, zero)}")
    assert "is not a number" in line
    # and the same digits in ASCII are the number 12345
    assert spdm_data(capsys, f"Code:4={digits}") == ["39", "30", "00", "00"]


# ------------------------------------------------------------------ AC-3

NO_NUMBERS = [
    "-abc",
    "-",
    "--5",
    "-08",
    "-0x",
    "-x10",
    "-0xg1",
    "-1a",
    "-1.5",
    "-+1",
    "-1-",
    "-1e3",
    "-0b1",
    "-1_000",
    "-" + other("1"),
    "-1" + other("3"),
]


@pytest.mark.parametrize("value", NO_NUMBERS, ids=ascii)
def test_a_dash_before_what_is_no_number_is_refused_as_no_number(capsys, value):
    line = refusal(capsys, "spdm", f"Code:1={value}")
    assert "Code" in line
    assert "is not a number" in line
    # the hint on how to write hex and decimal
    hint = line.split("is not a number", 1)[1]
    assert "0x" in hint
    assert "decimal" in hint
    assert "negative" not in line


NEGATIVE = [
    "-1",
    "-0x10",
    "-255",
    "-0XfF",
    "-65536",
    "-0x" + "f" * 40,
    "-" + "9" * 5000,
    "-0",  # out of scope of the change: it stays negative
]


@pytest.mark.parametrize("value", NEGATIVE, ids=lambda v: v[:12])
def test_a_dash_before_a_number_is_still_negative(capsys, changed, value):
    line = refusal(capsys, "spdm", f"Code:1={value}")
    assert "Code" in line
    assert "is negative" in line
    assert "not a number" not in line


# ------------------------------------------------------------------ AC-4

NINES = 10**4301 - 1  # one digit more than int() converts by default


def test_4301_nines_in_65535_bytes_are_laid_out(capsys):
    tokens = spdm_data(capsys, "X:65535=" + "9" * 4301)
    assert tokens == hexed(NINES.to_bytes(65535, "little"))
    assert set(tokens[1787:]) == {"00"}


@pytest.mark.parametrize(
    ("suffix", "order"), [("", "little"), (":le", "little"), (":be", "big")]
)
def test_4301_nines_are_laid_out_in_the_bytes_they_just_fit(capsys, suffix, order):
    size = (NINES.bit_length() + 7) // 8
    tokens = spdm_data(capsys, f"X:{size}{suffix}=" + "9" * 4301)
    assert tokens == hexed(NINES.to_bytes(size, order))
    line = refusal(capsys, "spdm", f"X:{size - 1}{suffix}=" + "9" * 4301)
    assert f"does not fit {size - 1} bytes" in line
    assert "too long" not in line


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("X:4=" + "9" * 5000, "does not fit 4 bytes"),
        ("X:1=" + "9" * 5000, "does not fit 1 byte"),
        ("X:4:be=" + "9" * 5000, "does not fit 4 bytes"),
        ("X:4=1" + "0" * 4999, "does not fit 4 bytes"),
        ("X:2075=" + "9" * 5000, "does not fit 2075 bytes"),
    ],
    ids=["nines", "one-byte", "most-significant-first", "power-of-ten", "close"],
)
def test_a_long_decimal_that_does_not_fit_gets_the_reason_of_any_number(
    capsys, field, reason
):
    line = refusal(capsys, "spdm", field)
    assert "X" in line
    assert line.endswith(reason)
    assert "too long" not in line


def test_5000_nines_fit_the_bytes_they_need_and_not_one_less(capsys):
    number = 10**5000 - 1
    size = (number.bit_length() + 7) // 8
    assert spdm_data(capsys, f"X:{size}:be=" + "9" * 5000) == hexed(
        number.to_bytes(size, "big")
    )
    line = refusal(capsys, "spdm", f"X:{size - 1}:be=" + "9" * 5000)
    assert f"does not fit {size - 1} bytes" in line


@pytest.mark.parametrize(
    ("field", "data"),
    [
        ("X:1=" + "0" * 5000, ["00"]),
        ("X:3=" + "0" * 5000, ["00", "00", "00"]),
        ("X:2:be=" + "0" * 5000, ["00", "00"]),
        ("X:2=0," + "0" * 5000, ["00", "00"]),
        ("X:2=" + "0" * 5000 + ",0x10", ["00", "10"]),
        ("X:3=0x01," + "0" * 4301 + ",0xff", ["01", "00", "ff"]),
    ],
    ids=["alone", "three-bytes", "be", "last-of-a-list", "first-of-a-list", "4301"],
)
def test_zeros_of_any_number_are_the_number_zero(capsys, field, data):
    assert spdm_data(capsys, field) == data


def test_long_decimals_are_read_digit_for_digit(capsys):
    rng = random.Random(29)
    lengths = [599, 600, 601, 1199, 1200, 1201, 1800, 4299, 4300, 4301, 4302]
    lengths += [4800, 6000, 12345]
    for length in lengths:
        numbers = [
            rng.randrange(10 ** (length - 1), 10**length),
            # hundreds of zeros in the middle
            7 * 10 ** (length - 1) + rng.randrange(1000),
            10 ** (length - 1),
            10**length - 1,
        ]
        for number in numbers:
            text = written(number)
            assert len(text) == length
            size = (number.bit_length() + 7) // 8
            got = spdm_data(capsys, f"X:{size}={text}")
            assert got == hexed(number.to_bytes(size, "little")), length
            got = spdm_data(capsys, f"X:{size}:be={text}")
            assert got == hexed(number.to_bytes(size, "big")), length
            got = spdm_data(capsys, f"X:{size + 5}:be={text}")
            assert got == ["00"] * 5 + hexed(number.to_bytes(size, "big")), length


def test_the_largest_number_of_a_large_size_fits_and_one_more_does_not(capsys):
    rng = random.Random(68)
    # from 1786 bytes on the largest number has more than 4300 digits
    for size in [1786, *sorted(rng.sample(range(1787, 65535), 4)), 65535]:
        top = 256**size - 1
        text = written(top)
        assert len(text) > 4300
        assert spdm_data(capsys, f"X:{size}={text}") == ["ff"] * size, size
        line = refusal(capsys, "spdm", f"X:{size}={written(top + 1)}")
        assert line.endswith(f"does not fit {size} bytes"), size
        assert "too long" not in line
        # the smallest number of as many digits fits, of one digit more not
        low = 10 ** (len(text) - 1)
        got = spdm_data(capsys, f"X:{size}:be=1" + "0" * (len(text) - 1))
        assert got == hexed(low.to_bytes(size, "big")), size
        line = refusal(capsys, "spdm", f"X:{size}=1" + "0" * len(text))
        assert line.endswith(f"does not fit {size} bytes"), size


# ------------------------------------------------------------------ AC-5

LIMITS = ("0", "640", None)
UNDER_ANY_LIMIT = [
    pytest.param("X:65535=" + "9" * 4301, 0, "bytes: 65535", id="fits"),
    pytest.param("X:4=" + "9" * 5000, 2, "does not fit 4 bytes", id="too-big"),
    pytest.param("X:1=" + "0" * 5000, 0, "0 | 1 | X | 00", id="zeros"),
    pytest.param("X:2=0," + "0" * 5000, 0, "0 | 2 | X | 00 00", id="zeros-in-a-list"),
]


@pytest.mark.parametrize(("field", "code", "said"), UNDER_ANY_LIMIT)
def test_the_answer_is_the_same_under_every_limit_of_the_interpreter(
    tmp_path, field, code, said
):
    home = tmp_path / "home"
    home.mkdir()
    answers = []
    for value in LIMITS:
        env = dict(os.environ)
        env.pop("CLAUDE_PLUGIN_DATA", None)
        env.pop("PYTHONINTMAXSTRDIGITS", None)
        env.update(
            BMC_SPEC_LIBRARY=str(tmp_path / "no-such-library"),
            HOME=str(home),
            USERPROFILE=str(home),
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONIOENCODING="utf-8",
        )
        if value is not None:
            env["PYTHONINTMAXSTRDIGITS"] = value
        result = subprocess.run(
            [sys.executable, str(LAUNCHER), "invocation", "spdm", field],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=home,
            timeout=120,
        )
        assert "Traceback" not in result.stderr, value
        assert result.returncode == code, (value, result.stdout[:300])
        lines = result.stdout.splitlines()
        assert [ln for ln in lines if ln == said or ln.endswith(said)], value
        assert "too long" not in result.stdout, value
        if code == 2:
            one_refusal(result.returncode, result.stdout + result.stderr)
        answers.append((result.returncode, result.stdout))
    assert answers[0] == answers[1] == answers[2]


def test_the_limit_set_in_process_changes_nothing_either(capsys, limit):
    fields = [
        "X:65535=" + "9" * 4301,
        "X:1787:be=" + "9" * 4301,
        "X:4=" + "9" * 5000,
        "X:1=" + "0" * 5000,
        "X:2=0," + "0" * 5000,
        "X:1=-" + "9" * 5000,
    ]
    for field in fields:
        answers = []
        for digits in (4300, 0, 640, 100000):
            limit(digits)
            code, lines, _ = invoke(capsys, "spdm", field)
            answers.append((code, lines))
        assert all(answer == answers[0] for answer in answers), field[:20]
        assert "too long" not in "\n".join(answers[0][1])
    limit(640)
    tokens = spdm_data(capsys, "X:65535=" + "9" * 4301)
    assert tokens == hexed(NINES.to_bytes(65535, "little"))


# ------------------------------------------------------------------ AC-6


@pytest.mark.parametrize(
    ("size", "reason"),
    [
        (1, "does not fit 1 byte"),
        (2, "does not fit 2 bytes"),
        (65535, "does not fit 65535 bytes"),
    ],
)
def test_a_million_nines_do_not_fit(size, reason):
    # no command line carries a field this long: handed over in process
    with pytest.raises(invocation.FieldError) as caught:
        invocation.render("spdm", [f"X:{size}=" + "9" * 1_000_000])
    said = str(caught.value)
    assert said.endswith(reason)
    assert "too long" not in said[-200:]


def test_a_million_nines_do_not_fit_under_any_limit(limit):
    for digits in (4300, 640, 0):
        limit(digits)
        with pytest.raises(invocation.FieldError) as caught:
            invocation.render("spdm", ["X:1=" + "9" * 1_000_000])
        assert str(caught.value).endswith("does not fit 1 byte"), digits


def test_a_million_nines_are_refused_by_the_command_with_one_line(capsys):
    line = refusal(capsys, "spdm", "Code:1=0x84", "X:1=" + "9" * 1_000_000)
    assert line.endswith("does not fit 1 byte")
    assert "too long" not in line[-200:]


def test_a_million_zeros_are_the_number_zero():
    lines = invocation.render("spdm", ["X:1=" + "0" * 1_000_000])
    assert lines[0] == "bytes: 1"
    assert lines[1] == MCTP + "00"


# ------------------------------------------------------------------ AC-7

SAME_AS_BEFORE = [
    ("Code:003=0x010203", ["03", "02", "01"]),
    ("Flags:0000002=0x1234", ["34", "12"]),
    ("X:1=255", ["ff"]),
    ("X:1=0", ["00"]),
    ("X:1=000", ["00"]),
    ("X:2=65535", ["ff", "ff"]),
    ("X:2:be=0x0100", ["01", "00"]),
    ("X:2:le=0x0100", ["00", "01"]),
    ("X:4=4294967295", ["ff", "ff", "ff", "ff"]),
    ("X:4:be=305419896", ["12", "34", "56", "78"]),
    ("X:8=0XFFFFFFFFFFFFFFFF", ["ff"] * 8),
    ("X:3=0x00,0,0x10", ["00", "00", "10"]),
    ("X:2=<handle>", ["<handle 0>", "<handle 1>"]),
    ("a:b=c:2=0x1234", ["34", "12"]),
]


@pytest.mark.parametrize(("field", "data"), SAME_AS_BEFORE)
def test_a_field_accepted_before_prints_the_same_bytes(capsys, changed, field, data):
    assert spdm_data(capsys, field) == data


# NAME may hold : and =, and a VALUE may hold what looks like a SIZE: the
# refusal of a SIZE of another script must not reach these
KEPT_NAMES = [
    ("Flags (b0=1):1=0", "0 | 1 | Flags (b0=1) | 00"),
    ("Byte 1: flags:1=0", "0 | 1 | Byte 1: flags | 00"),
    ("A:1:2=5", "0 | 2 | A:1 | 05 00"),
    ("X:y=A:1=5", "0 | 1 | X:y=A | 05"),
    ("a:b=c:2:be=0x1234", "0 | 2 | a:b=c | 12 34"),
    ("X:1=<see 5: 1=on>", "0 | 1 | X | <see 5: 1=on>"),
    (f"X:1=<see 5:{THREE}=on>", f"0 | 1 | X | <see 5:{THREE}=on>"),
    (f"Reg {THREE}:1=5", f"0 | 1 | Reg {THREE} | 05"),
]


@pytest.mark.parametrize(("field", "row"), KEPT_NAMES, ids=ascii)
def test_a_colon_or_an_equals_sign_in_a_name_is_kept(capsys, changed, field, row):
    code, lines, text = invoke(capsys, "spdm", field)
    assert code == 0, text[:300]
    size = row.split(" | ")[1]
    assert lines[0] == f"bytes: {size}"
    assert lines[-1] == row


def test_a_whole_answer_is_printed_as_before(capsys, changed):
    code, lines, _ = invoke(
        capsys,
        "pldm",
        "Header:1=0x80",
        "PLDM Type:1=0x02",
        "Command:1=0x11",
        "sensorID:2=4660",
        "rearmEventState:1=0",
    )
    assert code == 0
    assert lines == [
        "bytes: 6",
        "mctp-client eid <eid> type pldm data 80 02 11 34 12 00",
        "pldmtool raw -m <eid> -d 0x80 0x02 0x11 0x34 0x12 0x00",
        "offset | size | field | bytes",
        "0 | 1 | Header | 80",
        "1 | 1 | PLDM Type | 02",
        "2 | 1 | Command | 11",
        "3 | 2 | sensorID | 34 12",
        "5 | 1 | rearmEventState | 00",
    ]


def test_a_decimal_of_4300_digits_is_laid_out_as_before(capsys, changed):
    number = 10**4300 - 1
    size = (number.bit_length() + 7) // 8
    tokens = spdm_data(capsys, f"X:{size}=" + "9" * 4300)
    assert tokens == hexed(number.to_bytes(size, "little"))


# the refusals of develop this change does not touch, and their reason
KEPT = [
    (["spdm", "Flags:1=-1"], "Flags", "is negative"),
    (["spdm", "Flags:1=256"], "Flags", "does not fit 1 byte"),
    (["spdm", "Flags:2=65536"], "Flags", "does not fit 2 bytes"),
    (["spdm", "Flags:1=e1"], "Flags", "is not a number"),
    (["spdm", "Flags:1=08"], "Flags", "is not a number"),
    (["spdm", "Flags:1=0x"], "Flags", "is not a number"),
    (["spdm", "Flags:x=1"], "Flags", NO_SIZE),
    (["spdm", "Flags:=1"], "Flags", NO_SIZE),
    (["spdm", "Flags:-1=1"], "Flags", NO_SIZE),
    (["spdm", "Flags:0=1"], "Flags", "SIZE is 0"),
    (["spdm", "Flags:000=1"], "Flags", "SIZE is 0"),
    (["spdm", "Flags:65536=0"], "Flags", "SIZE is above 65535"),
    (["spdm", "Flags:" + "9" * 5000 + "=0"], "Flags", "SIZE is above 65535"),
    (["spdm", "Address:2=00,10"], "Address", "write every byte with 0x"),
    (["spdm", "Address:2=0x00,-1"], "Address", "write every byte with 0x"),
    (["spdm", "Address:2=0xc0,0x1a8"], "Address", "is more than one byte"),
    (["spdm", "Address:2=0xc0 0xa8"], "Address", "separated by commas"),
]


@pytest.mark.parametrize(("argv", "named", "reason"), KEPT, ids=lambda v: str(v)[:24])
def test_the_other_refusals_keep_their_reason(capsys, changed, argv, named, reason):
    line = refusal(capsys, *argv)
    assert named in line
    assert reason in line

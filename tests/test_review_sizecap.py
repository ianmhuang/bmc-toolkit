"""Reviewer acceptance tests: the cap on SIZE and the fit check (AC-3, AC-4,
AC-6).

Black box but for one check: the tests call the CLI entry point with
``invocation PROTOCOL FIELD ...`` and read what it prints, and the expected
bytes are written out by hand or computed here with ``int.to_bytes``. AC-4
asks how the fit is decided (without building ``256**SIZE``), which no
output shows once SIZE is capped, so the ``no_power`` fixture reads the
bytecode of the module for a power operation.

On develop a SIZE of 65536 or more is laid out (exit 0), a SIZE too long for
``int()`` ends in a ValueError, and ``Flags:99999999999=0`` computes
``256**99999999999``: that one runs in an interpreter of its own with a
timeout, so develop fails it after a minute instead of taking the machine
down. The tests of AC-4 that pin what must stay as it is depend on
``no_power``, which fails on develop.
"""

import dis
import os
import random
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

from bmc_toolkit.spec import invocation
from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "skills" / "bmc-spec" / "scripts" / "bmcspec.py"
TOOLS = ("ipmitool", "mctp-client", "pldmtool")
PROTOCOLS = ("ipmi", "mctp-control", "pldm", "spdm")
MCTP = "mctp-client eid <eid> type spdm data "
# a placeholder is one token even with a space inside
TOKEN = re.compile(r"<[^>]*>|\S+")
LIMIT = 65535
HEADER = {
    "ipmi": ["NetFn:1=0x0a", "Cmd:1=0x43"],
    "mctp-control": ["Header:1=0x80"],
    "pldm": ["Header:1=0x80"],
    "spdm": ["SPDMVersion:1=0x12"],
}


@pytest.fixture(autouse=True)
def no_library(monkeypatch, tmp_path):
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path / "no-such-library"))


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


# ------------------------------------------------------------------ AC-3

ABOVE = [
    pytest.param("Flags:65536=0", id="number"),
    pytest.param("Flags:65536=0x01", id="hex"),
    pytest.param("Flags:65536:be=1", id="most-significant-first"),
    pytest.param("Flags:65536=<x>", id="placeholder"),
    pytest.param(
        "Flags:65536=" + ",".join(["0x00"] * 65536), id="a-list-of-65536-bytes"
    ),
    pytest.param("Flags:65536=0x00,0x01", id="list-of-two-bytes"),
    pytest.param("Flags:100000=0", id="100000"),
    pytest.param("Flags:0065536=0", id="leading-zeros"),
    # more digits than int() converts: no traceback either
    pytest.param("Flags:" + "9" * 5000 + "=0", id="size-of-5000-digits"),
]


@pytest.mark.parametrize("field", ABOVE)
def test_a_size_above_65535_is_refused_whatever_the_value(capsys, field):
    line = refusal(capsys, "spdm", "Code:1=0x84", field, "Last:1=0x01")
    assert "Flags" in line
    # no field above holds 65535: the number is the limit the line states
    assert str(LIMIT) in line


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_the_limit_holds_for_every_protocol(capsys, protocol):
    line = refusal(capsys, protocol, *HEADER[protocol], "Flags:65536=0")
    assert "Flags" in line
    assert str(LIMIT) in line


def test_an_absurd_size_is_exit_2_at_once_and_no_traceback(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ)
    env.pop("CLAUDE_PLUGIN_DATA", None)
    env.update(
        BMC_SPEC_LIBRARY=str(tmp_path / "no-such-library"),
        HOME=str(home),
        USERPROFILE=str(home),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONIOENCODING="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(LAUNCHER), "invocation", "spdm", "Flags:99999999999=0"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=home,
        timeout=60,
    )
    line = one_refusal(result.returncode, result.stdout + result.stderr)
    assert "Flags" in line
    assert str(LIMIT) in line


def test_a_number_of_65535_bytes_is_laid_out_and_one_byte_more_is_refused(capsys):
    assert spdm_data(capsys, "Flags:65535=0") == ["00"] * LIMIT
    line = refusal(capsys, "spdm", "Flags:65536=0")
    assert "Flags" in line
    assert str(LIMIT) in line


def test_a_placeholder_of_65535_bytes_is_laid_out_and_one_more_is_refused(capsys):
    tokens = spdm_data(capsys, "Chain:65535=<chain>")
    assert tokens == [f"<chain {i}>" for i in range(LIMIT)]
    line = refusal(capsys, "spdm", "Chain:65536=<chain>")
    assert "Chain" in line
    assert str(LIMIT) in line


def test_a_list_of_65535_bytes_is_laid_out_and_one_more_is_refused(capsys):
    layout = [(7 * i + 3) % 256 for i in range(LIMIT)]
    written = ",".join(f"0x{b:02x}" for b in layout)
    assert spdm_data(capsys, f"Blob:65535={written}") == [f"{b:02x}" for b in layout]
    line = refusal(capsys, "spdm", f"Blob:65536={written},0x00")
    assert "Blob" in line
    assert str(LIMIT) in line


def test_zeros_in_front_of_a_size_within_the_limit_do_not_count(capsys):
    # accepted before the change and within the limit: laid out as before
    assert spdm_data(capsys, "Flags:0000002=0x1234") == ["34", "12"]
    line = refusal(capsys, "spdm", "Flags:0065536=0x1234")
    assert "Flags" in line
    assert str(LIMIT) in line


# ------------------------------------------------------------------ AC-4


def _code_objects(code):
    yield code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from _code_objects(const)


def _raises_to_a_power(code) -> bool:
    if "pow" in code.co_names:
        return True
    for ins in dis.get_instructions(code):
        if ins.opname == "BINARY_POWER":
            return True
        if ins.opname == "BINARY_OP" and (ins.argrepr or "").startswith("**"):
            return True
    return False


@pytest.fixture
def no_power():
    """AC-4: no function of the module raises to a power, so whether a number
    fits is not decided by building ``256**SIZE``."""
    found = sorted(
        name
        for name, value in vars(invocation).items()
        if isinstance(value, types.FunctionType)
        and value.__module__ == invocation.__name__
        and any(_raises_to_a_power(code) for code in _code_objects(value.__code__))
    )
    assert not found, f"a power is computed in: {', '.join(found)}"


def test_whether_a_number_fits_is_decided_without_a_power(no_power):
    assert callable(invocation.parse_field)


FITS = [
    ("X:1=255", "ff"),
    ("X:1=0xff", "ff"),
    ("X:2=0xffff", "ff ff"),
    ("X:2=65535", "ff ff"),
    ("X:2:be=0x0100", "01 00"),
    ("X:3:be=0xffffff", "ff ff ff"),
    ("X:4=4294967295", "ff ff ff ff"),
    ("X:8=0xffffffffffffffff", "ff ff ff ff ff ff ff ff"),
    ("X:8:be=1", "00 00 00 00 00 00 00 01"),
]


@pytest.mark.parametrize(("field", "data"), FITS)
def test_the_largest_number_of_a_size_still_fits(capsys, no_power, field, data):
    assert spdm_data(capsys, field) == data.split()


DOES_NOT_FIT = [
    ("X:1=256", "does not fit 1 byte"),
    ("X:1=0x100", "does not fit 1 byte"),
    ("X:2=0x10000", "does not fit 2 bytes"),
    ("X:2=65536", "does not fit 2 bytes"),
    ("X:2:be=0x10000", "does not fit 2 bytes"),
    ("X:4=4294967296", "does not fit 4 bytes"),
    ("X:8=0x10000000000000000", "does not fit 8 bytes"),
]


@pytest.mark.parametrize(("field", "reason"), DOES_NOT_FIT)
def test_one_more_than_fits_is_refused_with_the_reason_it_had(
    capsys, no_power, field, reason
):
    line = refusal(capsys, "spdm", field)
    assert "X" in line
    assert reason in line


def test_the_fit_is_decided_the_same_at_every_size(capsys, no_power):
    rng = random.Random(67)
    sizes = [*range(1, 10), *rng.sample(range(10, 400), 12)]
    for size in sizes:
        top = 256**size - 1
        word = "byte" if size == 1 else "bytes"
        for written in (hex(top), str(top)):
            assert spdm_data(capsys, f"X:{size}={written}") == ["ff"] * size, size
        for written in (hex(top + 1), str(top + 1)):
            line = refusal(capsys, "spdm", f"X:{size}={written}")
            assert f"does not fit {size} {word}" in line, size
        value = rng.randrange(top + 1)
        for order in ("little", "big"):
            suffix = ":be" if order == "big" else ""
            expected = [f"{b:02x}" for b in value.to_bytes(size, order)]
            got = spdm_data(capsys, f"X:{size}{suffix}={hex(value)}")
            assert got == expected, (size, order)


def test_the_fit_is_decided_the_same_at_the_largest_size(capsys, no_power):
    assert spdm_data(capsys, "X:65535=1") == ["01"] + ["00"] * (LIMIT - 1)
    assert spdm_data(capsys, "X:65535:be=1") == ["00"] * (LIMIT - 1) + ["01"]
    assert spdm_data(capsys, "X:65535=0x" + "ff" * LIMIT) == ["ff"] * LIMIT
    line = refusal(capsys, "spdm", "X:65535=0x1" + "00" * LIMIT)
    assert "does not fit 65535 bytes" in line


# what develop refuses, and the reason it gives: AC-4 keeps both
KEPT = [
    (["spdm", "Flags:1=-1"], "Flags", "is negative"),
    (["spdm", "Flags:0=1"], "Flags", "SIZE is 0"),
    (["spdm", "Flags:two=1"], "Flags", "SIZE, the field's bytes, is missing"),
    (["spdm", "Flags=1"], "Flags", "SIZE, the field's bytes, is missing"),
    (["spdm", "Flags:1"], "Flags", "no =VALUE"),
    (["spdm", "Flags:1="], "Flags", "no VALUE"),
    (["spdm", ":1=1"], ":1=1", "no NAME"),
    (["spdm", "Flags:1=e1"], "Flags", "is not a number"),
    (["spdm", "Flags:1=08"], "Flags", "is not a number"),
    (["spdm", "Flags:1=<>"], "Flags", "a placeholder is written <text>"),
    (["spdm", "Flags:1=<x"], "Flags", "a placeholder is written <text>"),
    (["spdm", "Address:4=0xc0,0xa8,0x01"], "Address", "the list holds 3 bytes"),
    (["spdm", "Address:2=0xc0,0x1a8"], "Address", "is more than one byte"),
    (["spdm", "Address:2=00,10"], "Address", "write every byte with 0x"),
    (["spdm", "Address:2=0xc0 0xa8"], "Address", "separated by commas"),
    (["spdm"], "NAME:SIZE=VALUE", "no field given"),
    (["redfish", "Flags:1=1"], "redfish", "unknown protocol"),
    (["ipmi", "NetFn:1=0x06"], "ipmi", "the first two fields are NetFn and Cmd"),
    (["ipmi", "NetFn:2=0x06", "Cmd:1=1"], "NetFn", "one byte each"),
    (["ipmi", "NetFn:1=0x06", "Cmd:2=1"], "Cmd", "one byte each"),
]


@pytest.mark.parametrize(("argv", "named", "reason"), KEPT)
def test_the_earlier_refusals_keep_exit_2_and_their_reason(
    capsys, no_power, argv, named, reason
):
    line = refusal(capsys, *argv)
    assert named in line
    assert reason in line

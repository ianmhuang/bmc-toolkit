"""Reviewer acceptance tests for ``invocation nc-si`` (T52, AC-1 to AC-5).

Black box: every test calls the CLI entry point and reads what it prints.
The expected packets are written out by hand (sums worked on paper in the
comments) or built here from the DSP0222 Table 10 layout with a checksum
of this file's own, never taken from the module under test.

On develop the ``nc-si`` protocol and its options do not exist: argparse
leaves through SystemExit, or the protocol is refused, so every test
fails there.
"""

import random
import re
from pathlib import Path

import pytest

from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]

NETLINK = "ncsi-cmd -i <ifindex in hex> "
OVER_MCTP = "ncsi-cmd -m <eid in decimal> "
CLIENT = "mctp-client eid <eid> type nc-si data "
TABLE_HEAD = "offset | size | field | bytes"
# a placeholder is one token even with spaces inside
TOKEN = re.compile(r"<[^>]*>|\S+")


@pytest.fixture(autouse=True)
def _no_library(monkeypatch, tmp_path):
    """The command reads no Library: point at one that is not there."""
    missing = tmp_path / "no-such-library"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(missing))
    yield
    assert not missing.exists()


def invoke(capsys, *argv):
    """(exit code, stdout lines)."""
    code = main(["invocation", *argv])
    return code, capsys.readouterr().out.splitlines()


def only(lines, prefix):
    found = [ln for ln in lines if ln.startswith(prefix)]
    assert len(found) == 1, (prefix, lines)
    return found[0]


def packet(lines):
    return TOKEN.findall(only(lines, CLIENT)[len(CLIENT) :])


def notes(lines):
    return [ln for ln in lines if ln.startswith("note:")]


def table(lines):
    """Rows after the table heading as (offset, size, name, byte tokens)."""
    at = lines.index(TABLE_HEAD)
    out = []
    for line in lines[at + 1 :]:
        offset, size, name, cells = line.split(" | ")
        out.append((int(offset), int(size), name, TOKEN.findall(cells)))
    return out


def word_sum_checksum(data: bytes) -> int:
    """AC-2 as stated: the two's complement of the 32-bit sum of the bytes
    read as 16-bit big-endian words, an odd tail paired with a zero."""
    if len(data) % 2:
        data = data + b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        total = (total + data[i] * 256 + data[i + 1]) % 2**32
    return (2**32 - total) % 2**32


def linux_checksum(data: bytes) -> int:
    """net/ncsi/ncsi-cmd.c ncsi_calculate_checksum, line by line: the
    loop reads data[i + 1] past an odd length, which is the zero padding
    byte that follows the payload."""
    data = data + b"\x00"
    checksum = 0
    i = 0
    while i < len(data) - 1:
        checksum = (checksum + ((data[i] << 8) | data[i + 1])) & 0xFFFFFFFF
        i += 2
    return (~checksum + 1) & 0xFFFFFFFF


def hexes(data: bytes) -> list[str]:
    return [f"{b:02x}" for b in data]


# ------------------------------------------------------------------ AC-1


# Get Link Status (0x0a) to package 0 channel 1, IID 0x2a, no payload.
# Words from MC ID: 0x0001 + 0x002a + 0x0a01 = 0x0a2c; 2^32 - 0x0a2c =
# 0xfffff5d4
GET_LINK_STATUS = [
    "nc-si", "--type", "0x0a", "--package", "0", "--channel", "1", "--iid", "0x2a",
]  # fmt: skip
GET_LINK_STATUS_PACKET = (
    "00 01 00 2a 0a 01 00 00 00 00 00 00 00 00 00 00 ff ff f5 d4"
)


def test_a_command_without_payload_prints_the_lines_in_the_order_of_ac1(capsys):
    code, lines = invoke(capsys, *GET_LINK_STATUS)
    assert code == 0, lines
    assert lines[0] == "payload bytes: 0"
    assert lines[1] == "packet bytes: 20"
    assert lines[2] == NETLINK + "-p 00 -c 01 raw 0a"
    assert lines[3] == OVER_MCTP + "-p 00 -c 01 raw 0a"
    assert lines[4] == CLIENT + GET_LINK_STATUS_PACKET
    head = lines.index(TABLE_HEAD)
    assert head > 5, lines
    assert all(ln.startswith("note:") for ln in lines[5:head]), lines[5:head]
    # the table: every packet byte, header rows from MC ID, checksum last
    rows = table(lines)
    assert [tok for *_, toks in rows for tok in toks] == GET_LINK_STATUS_PACKET.split()
    offset = 0
    for at, size, _, toks in rows:
        assert at == offset and len(toks) == size, rows
        offset += size
    assert offset == 20
    assert rows[-1][0] == 16 and rows[-1][1] == 4
    assert "checksum" in rows[-1][2].lower(), rows[-1]
    assert [r[:2] for r in rows[:6]] == [(0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1)]
    assert "iid" in rows[3][2].lower(), rows[3]
    assert rows[6][:2] == (6, 2)
    assert rows[7][:2] == (8, 8)
    assert not any("padding" in r[2].lower() for r in rows)


# Set MAC Address (0x0e) to package 1 channel 2 (Channel ID 0x22), IID 3,
# payload 00 11 22 33 44 55 01 01 (8 bytes, no padding). Words: 0x0001 +
# 0x0003 + 0x0e22 + 0x0008 + 0x0011 + 0x2233 + 0x4455 + 0x0101 = 0x75c8;
# 2^32 - 0x75c8 = 0xffff8a38
SET_MAC = [
    "nc-si", "--type", "0x0e", "--package", "1", "--channel", "2", "--iid", "3",
    "MAC Address:6=0x00,0x11,0x22,0x33,0x44,0x55", "MAC Number:1=1", "AT and E:1=0x01",
]  # fmt: skip
SET_MAC_PACKET = (
    "00 01 00 03 0e 22 00 08 00 00 00 00 00 00 00 00 "
    "00 11 22 33 44 55 01 01 ff ff 8a 38"
)


def test_the_payload_follows_the_header_at_offset_16(capsys):
    code, lines = invoke(capsys, *SET_MAC)
    assert code == 0, lines
    assert lines[:2] == ["payload bytes: 8", "packet bytes: 28"]
    assert lines[2] == NETLINK + "-p 01 -c 02 raw 0e 00 11 22 33 44 55 01 01"
    assert lines[3] == OVER_MCTP + "-p 01 -c 02 raw 0e 00 11 22 33 44 55 01 01"
    assert lines[4] == CLIENT + SET_MAC_PACKET
    rows = table(lines)
    named = {name: (at, size) for at, size, name, _ in rows}
    assert named["MAC Address"] == (16, 6)
    assert named["MAC Number"] == (22, 1)
    assert named["AT and E"] == (23, 1)
    assert rows[-1][:2] == (24, 4)
    assert [tok for *_, toks in rows for tok in toks] == SET_MAC_PACKET.split()
    assert not any("padding" in r[2].lower() for r in rows)


def test_the_two_ncsi_cmd_lines_carry_the_same_options_and_payload(capsys):
    code, lines = invoke(capsys, *SET_MAC)
    assert code == 0, lines
    assert lines[2][len(NETLINK) :] == lines[3][len(OVER_MCTP) :]
    # every number is two hex digits without 0x
    tail = lines[2][len(NETLINK) :].split()
    assert tail[:5] == ["-p", "01", "-c", "02", "raw"]
    assert all(re.fullmatch(r"[0-9a-f]{2}", t) for t in tail[5:]), tail


# ------------------------------------------------------------------ AC-2


# type 0x7f to package 7 channel 0x1e (Channel ID 0xfe), IID 0xff, payload
# 01 02 03 04 05 padded with three 00. Words: 0x0001 + 0x00ff + 0x7ffe +
# 0x0005 + 0x0102 + 0x0304 + 0x0500 = 0x8a09; 2^32 - 0x8a09 = 0xffff75f7
ODD = [
    "nc-si", "--type", "0x7f", "--package", "7", "--channel", "0x1e",
    "--iid", "0xff", "Data:5=0x01,0x02,0x03,0x04,0x05",
]  # fmt: skip
ODD_PACKET = (
    "00 01 00 ff 7f fe 00 05 00 00 00 00 00 00 00 00 "
    "01 02 03 04 05 00 00 00 ff ff 75 f7"
)


def test_an_odd_payload_is_padded_to_four_and_summed_as_worked_by_hand(capsys):
    code, lines = invoke(capsys, *ODD)
    assert code == 0, lines
    assert lines[:2] == ["payload bytes: 5", "packet bytes: 28"]
    assert lines[4] == CLIENT + ODD_PACKET
    rows = table(lines)
    padding = [r for r in rows if "padding" in r[2].lower()]
    assert padding == [(21, 3, padding[0][2], ["00", "00", "00"])], rows
    assert rows[-1] == (24, 4, rows[-1][2], ["ff", "ff", "75", "f7"])
    # the ncsi-cmd lines carry the payload alone: no padding, no checksum
    assert lines[2] == NETLINK + "-p 07 -c 1e raw 7f 01 02 03 04 05"


def test_the_sum_is_32_bits_wide(capsys):
    # Get Capabilities (0x16) to package 0 channel 0, IID 1, with forty
    # 0xff bytes: twenty words of 0xffff (0x13ffec) on top of the header
    # words 0x0001 + 0x0001 + 0x1600 + 0x0028 (0x162a), a sum far above 16
    # bits: 0x141616; 2^32 - 0x141616 = 0xffebe9ea
    field = "Data:40=" + ",".join(["0xff"] * 40)
    code, lines = invoke(
        capsys, "nc-si", "--type", "0x16", "--package", "0", "--channel", "0",
        "--iid", "1", field,
    )  # fmt: skip
    assert code == 0, lines
    got = bytes(int(t, 16) for t in packet(lines))
    body = got[:56]
    assert sum(body[i] * 256 + body[i + 1] for i in range(0, 56, 2)) == 0x141616
    assert got[56:] == word_sum_checksum(body).to_bytes(4, "big")
    assert got[56:] == b"\xff\xeb\xe9\xea"
    assert lines[1] == "packet bytes: 60"


def test_the_packet_is_table_10_and_the_checksum_is_linux_s(capsys):
    rng = random.Random(2022)
    for _ in range(30):
        kind, package = rng.randrange(0x80), rng.randrange(8)
        channel, iid = rng.randrange(0x20), rng.randint(1, 0xFF)
        size = rng.randrange(38)
        payload = bytes(rng.randrange(256) for _ in range(size))
        fields = []
        if size == 1:
            fields = [f"Data:1=0x{payload[0]:02x}"]
        elif size:
            listed = ",".join(f"0x{b:02x}" for b in payload)
            fields = [f"Data:{size}={listed}"]
        argv = [
            "nc-si", "--type", f"0x{kind:02x}", "--package", str(package),
            "--channel", f"0x{channel:02x}", "--iid", str(iid), *fields,
        ]  # fmt: skip
        code, lines = invoke(capsys, *argv)
        assert code == 0, (argv, lines)
        header = bytes([0x00, 0x01, 0x00, iid, kind, package << 5 | channel])
        header += size.to_bytes(2, "big") + bytes(8)
        body = header + payload
        want = body + bytes((-size) % 4) + linux_checksum(body).to_bytes(4, "big")
        assert packet(lines) == hexes(want), argv
        assert lines[0] == f"payload bytes: {size}"
        assert lines[1] == f"packet bytes: {len(want)}"
        assert lines[2] == NETLINK + " ".join(
            ["-p", f"{package:02x}", "-c", f"{channel:02x}", "raw", f"{kind:02x}"]
            + hexes(payload)
        )
        assert linux_checksum(body) == word_sum_checksum(body)


def test_payload_length_is_twelve_bits_big_endian(capsys):
    code, lines = invoke(
        capsys, "nc-si", "--type", "0x0b", "--package", "0", "--channel", "0",
        "--iid", "1", "Data:4095=0",
    )  # fmt: skip
    assert code == 0, lines
    got = packet(lines)
    assert got[6:8] == ["0f", "ff"]
    assert lines[0] == "payload bytes: 4095"
    assert lines[1] == f"packet bytes: {16 + 4095 + 1 + 4}"
    assert len(got) == 16 + 4095 + 1 + 4


# ------------------------------------------------------------------ AC-3


@pytest.mark.parametrize("channel", ["package", "0x1f", "31"])
def test_the_whole_package_is_channel_1f_in_both_places(capsys, channel):
    code, lines = invoke(
        capsys, "nc-si", "--type", "0x01", "--package", "5", "--channel", channel,
        "--iid", "1", "Reserved:3=0", "Features Control:1=0",
    )  # fmt: skip
    assert code == 0, lines
    assert lines[2] == NETLINK + "-p 05 -c 1f raw 01 00 00 00 00"
    assert lines[3] == OVER_MCTP + "-p 05 -c 1f raw 01 00 00 00 00"
    assert packet(lines)[5] == f"{5 << 5 | 0x1F:02x}"


@pytest.mark.parametrize(
    ("package", "channel", "options"),
    [
        ("<pkg>", "2", "-p <pkg> -c 02"),
        ("3", "<chan>", "-p 03 -c <chan>"),
        ("<pkg>", "<chan>", "-p <pkg> -c <chan>"),
    ],
)
def test_a_package_or_channel_placeholder_is_one_packet_byte_and_no_checksum(
    capsys, package, channel, options
):
    code, lines = invoke(
        capsys, "nc-si", "--type", "0x15", "--package", package, "--channel",
        channel, "--iid", "1",
    )  # fmt: skip
    assert code == 0, lines
    assert lines[2] == NETLINK + options + " raw 15"
    assert lines[3] == OVER_MCTP + options + " raw 15"
    got = packet(lines)
    assert len(got) == 20, got
    assert got[5].startswith("<") and got[5].endswith(">"), got
    assert [t for t in got if t.startswith("<")] == [got[5]], got
    assert got[16:] == ["00", "00", "00", "00"]
    assert lines[1] == "packet bytes: 20"
    said = " ".join(notes(lines))
    assert "8.2.2.3" in said and "00 00 00 00" in said, said
    # the table carries the same placeholder byte, at offset 5
    rows = table(lines)
    assert rows[5][:2] == (5, 1) and rows[5][3] == [got[5]], rows


def test_a_payload_placeholder_shows_in_the_lines_and_zeroes_the_checksum(capsys):
    code, lines = invoke(
        capsys, "nc-si", "--type", "0x01", "--package", "0", "--channel",
        "package", "--iid", "4", "Reserved:3=0", "Features Control:1=<features>",
    )  # fmt: skip
    assert code == 0, lines
    assert lines[2] == NETLINK + "-p 00 -c 1f raw 01 00 00 00 <features>"
    assert lines[3] == OVER_MCTP + "-p 00 -c 1f raw 01 00 00 00 <features>"
    got = packet(lines)
    assert len(got) == 24, got
    assert got[16:20] == ["00", "00", "00", "<features>"]
    assert got[20:] == ["00", "00", "00", "00"]
    assert "8.2.2.3" in " ".join(notes(lines))


def test_without_iid_the_packet_iid_is_a_placeholder_and_the_checksum_zero(capsys):
    code, lines = invoke(
        capsys, "nc-si", "--type", "0x0a", "--package", "0", "--channel", "1"
    )
    assert code == 0, lines
    got = packet(lines)
    assert len(got) == 20, got
    assert got[3] == "<iid>"
    assert got[:3] == ["00", "01", "00"] and got[4:6] == ["0a", "01"]
    assert got[16:] == ["00", "00", "00", "00"]
    assert "8.2.2.3" in " ".join(notes(lines))
    # the ncsi-cmd lines carry no IID: the tool picks one
    assert lines[2] == NETLINK + "-p 00 -c 01 raw 0a"
    assert "<iid>" not in lines[2] and "<iid>" not in lines[3]


def test_with_every_byte_known_the_checksum_is_the_sum_and_no_note_says_zero(
    capsys,
):
    code, lines = invoke(capsys, *GET_LINK_STATUS)
    assert code == 0, lines
    assert packet(lines)[16:] == ["ff", "ff", "f5", "d4"]
    assert not any("00 00 00 00" in n for n in notes(lines)), notes(lines)
    assert not any("8.2.2.3" in n for n in notes(lines)), notes(lines)


# ------------------------------------------------------------------ AC-4


def _argv(**given):
    base = {"type": "0x15", "package": "0", "channel": "0", "iid": "1"}
    base.update(given)
    out = ["nc-si"]
    for name, value in base.items():
        if value is not None:
            out += [f"--{name}", value]
    return out


@pytest.mark.parametrize(
    ("argv", "said"),
    [
        (_argv(type=None), "--type"),
        (_argv(type="zz"), "--type"),
        (_argv(type="<type>"), "--type"),
        (_argv(type="0x80"), "--type"),
        (_argv(type="128"), "--type"),
        (_argv(type="0xff"), "--type"),
        (_argv(package="8"), "--package"),
        (_argv(package="0x8"), "--package"),
        (_argv(package=None), "--package"),
        (_argv(channel="0x20"), "--channel"),
        (_argv(channel="32"), "--channel"),
        (_argv(channel="Package"), "--channel"),
        (_argv(channel=None), "--channel"),
        (_argv(iid="0"), "--iid"),
        (_argv(iid="0x0"), "--iid"),
        (_argv(iid="0x100"), "--iid"),
        (_argv(iid="256"), "--iid"),
        (_argv(package=None, channel=None), "--"),
    ],
)
def test_a_wrong_header_option_is_refused_with_one_line(capsys, argv, said):
    code, lines = invoke(capsys, *argv)
    assert code == 2, lines
    assert len(lines) == 1, lines
    assert lines[0].startswith("invocation: "), lines
    assert said in lines[0], lines


@pytest.mark.parametrize(
    "fields",
    [
        ["Data:4096=0"],
        ["A:4095=0", "B:1=0"],
        ["A:2048=0", "B:2048=0", "C:1=0"],
    ],
)
def test_a_payload_above_0xfff_bytes_is_refused_with_one_line(capsys, fields):
    code, lines = invoke(capsys, *_argv(), *fields)
    assert code == 2, lines
    assert len(lines) == 1, lines
    assert lines[0].startswith("invocation: "), lines
    assert "4095" in lines[0] or "0xfff" in lines[0].lower(), lines


def test_a_bad_payload_field_is_refused_with_one_line(capsys):
    code, lines = invoke(capsys, *_argv(), "Reserved:3=0", "Bad:1=0x100")
    assert code == 2, lines
    assert len(lines) == 1, lines
    assert lines[0].startswith("invocation: ") and "Bad:1=0x100" in lines[0], lines


@pytest.mark.parametrize("option", ["--type", "--package", "--channel", "--iid"])
@pytest.mark.parametrize(
    ("protocol", "fields"),
    [
        ("ipmi", ["NetFn:1=0x06", "Cmd:1=0x01"]),
        ("mctp-control", ["Hdr:1=0x80", "Cmd:1=0x02"]),
        ("pldm", ["Hdr:1=0x80", "Type:1=0", "Cmd:1=0x02"]),
        ("spdm", ["Version:1=0x10", "Code:1=0x84"]),
    ],
)
def test_a_header_option_with_another_protocol_is_refused(
    capsys, option, protocol, fields
):
    code, lines = invoke(capsys, protocol, option, "1", *fields)
    assert code == 2, lines
    assert len(lines) == 1, lines
    assert lines[0].startswith("invocation: "), lines
    assert option in lines[0] and "nc-si" in lines[0], lines


def test_nc_si_option_numbers_are_read_as_field_values_are(capsys):
    hex_form = invoke(
        capsys, "nc-si", "--type", "0x15", "--package", "0x1", "--channel",
        "0x1f", "--iid", "0xff",
    )  # fmt: skip
    decimal = invoke(
        capsys, "nc-si", "--type", "21", "--package", "1", "--channel", "31",
        "--iid", "255",
    )  # fmt: skip
    assert hex_form[0] == decimal[0] == 0, (hex_form, decimal)
    assert hex_form[1] == decimal[1]
    assert hex_form[1][2] == NETLINK + "-p 01 -c 1f raw 15"
    assert packet(hex_form[1])[3:6] == ["ff", "15", "3f"]


# ------------------------------------------------------------------ AC-5


def test_the_notes_say_how_ncsi_cmd_reads_numbers_and_the_iid_rule(capsys):
    code, lines = invoke(capsys, *SET_MAC)
    assert code == 0, lines
    found = notes(lines)
    assert found, lines
    # the notes sit between the mctp-client line and the table
    first = lines.index(found[0])
    assert first == 5 and lines.index(TABLE_HEAD) == 5 + len(found), lines
    said = " ".join(found)
    for word in ("-i", "-p", "-c", "TYPE", "hex", "decimal", "-m", "EID"):
        assert word in said, (word, said)
    assert "ifindex" in said and "interface" in said, said
    assert "0x01..0xff" in said and "retry" in said and "6.2.2.2" in said, said

"""``invocation nc-si``: the ``ncsi-cmd`` lines and the whole NC-SI packet
for ``mctp-client``, header, padding and checksum laid out by the helper
(T52, ADR 0008 of the design workspace)."""

import hashlib
import random
import re
from pathlib import Path

import pytest

from bmc_toolkit.spec import invocation
from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
COMMANDS_DOC = ROOT / "docs" / "COMMANDS.md"
README = ROOT / "README.md"

START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
MAX_LINES = 52  # AC-6: 46 until T52
# sha256 of SKILL.md's front matter on develop 1d2f2d7 (AC-6: unchanged)
FRONT_MATTER_SHA = "46edbffa30899ddf84be501e93d260d25163b63bf7f6fcf49c1ec13efeced22a"

NETLINK = "ncsi-cmd -i <ifindex in hex> "
OVER_MCTP = "ncsi-cmd -m <eid in decimal> "
CLIENT = "mctp-client eid <eid> type nc-si data "


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


def one(lines, prefix):
    found = [ln for ln in lines if ln.startswith(prefix)]
    assert len(found) == 1, (prefix, lines)
    return found[0]


def tokens(text):
    # a placeholder may hold spaces (`<channel id>`): one token all the same
    return re.findall(r"<[^>]*>|\S+", text)


def packet(lines):
    return tokens(one(lines, CLIENT)[len(CLIENT) :])


def notes(lines):
    return " ".join(ln for ln in lines if ln.startswith("note: "))


def rows(lines):
    at = lines.index("offset | size | field | bytes")
    return [ln.split(" | ") for ln in lines[at + 1 :]]


def linux_checksum(data: bytes) -> int:
    """net/ncsi/ncsi-cmd.c ncsi_calculate_checksum (Linux v7.3), line by
    line: data[i + 1] past an odd length is the zero padding byte."""
    data = data + b"\0"
    checksum = 0
    for i in range(0, len(data) - 1, 2):
        checksum = (checksum + ((data[i] << 8) | data[i + 1])) & 0xFFFFFFFF
    checksum = (~checksum + 1) & 0xFFFFFFFF
    return checksum


# ------------------------------------------------------------------ AC-1


# Get Version ID (Control Packet Type 0x15), no payload: header words
# 0x0001 (MC ID 00, revision 01) + 0x0001 (reserved 00, IID 01) + 0x1500
# (type 15, channel 00) = 0x1502, two's complement 0xffffeafe
GET_VERSION_ID = [
    "payload bytes: 0",
    "packet bytes: 20",
    NETLINK + "-p 00 -c 00 raw 15",
    OVER_MCTP + "-p 00 -c 00 raw 15",
    CLIENT + "00 01 00 01 15 00 00 00 00 00 00 00 00 00 00 00 ff ff ea fe",
]
GET_VERSION_ID_TABLE = [
    "offset | size | field | bytes",
    "0 | 1 | MC ID | 00",
    "1 | 1 | Header Revision | 01",
    "2 | 1 | Reserved | 00",
    "3 | 1 | IID | 01",
    "4 | 1 | Control Packet Type | 15",
    "5 | 1 | Channel ID | 00",
    "6 | 2 | Flags and Payload Length | 00 00",
    "8 | 8 | Reserved | 00 00 00 00 00 00 00 00",
    "16 | 4 | Checksum | ff ff ea fe",
]


def test_a_command_without_payload_prints_every_line_in_order(capsys):
    code, lines = run(
        capsys, "nc-si", "--type", "0x15", "--package", "0", "--channel", "0",
        "--iid", "1",
    )  # fmt: skip
    assert code == 0, lines
    assert lines[:5] == GET_VERSION_ID
    at = lines.index("offset | size | field | bytes")
    assert all(ln.startswith("note: ") for ln in lines[5:at]), lines
    assert lines[5:at], "no note line"
    assert lines[at:] == GET_VERSION_ID_TABLE


def test_the_options_after_the_fields_give_the_same_lines(capsys):
    # argparse before 3.12.7 (CI's 3.11) leaves FIELD empty when an option
    # sits between the positionals; the options are moved first
    before = run(
        capsys, "nc-si", "--type", "0x04", "--package", "1", "--channel", "2",
        "--iid", "7", "Reserved:3=0", "ALD:1=1",
    )  # fmt: skip
    after = run(
        capsys, "nc-si", "Reserved:3=0", "ALD:1=1", "--type", "0x04",
        "--package", "1", "--channel", "2", "--iid=7",
    )  # fmt: skip
    assert before[0] == after[0] == 0, (before, after)
    assert before[1] == after[1]
    assert one(before[1], NETLINK) == NETLINK + "-p 01 -c 02 raw 04 00 00 00 01"
    assert one(before[1], OVER_MCTP) == OVER_MCTP + "-p 01 -c 02 raw 04 00 00 00 01"


def test_reorder_moves_every_option_of_the_command_first():
    fields = ["A:1=1", "B:2=2"]
    got = invocation.reorder_argv(
        ["invocation", "nc-si", *fields, "--type", "1", "--package=0",
         "--channel", "package", "--iid", "3"]
    )  # fmt: skip
    assert got == [
        "invocation", "--type", "1", "--package=0", "--channel", "package",
        "--iid", "3", "nc-si", *fields,
    ]  # fmt: skip
    # another command is left alone
    other = ["find", "x", "--type", "1"]
    assert invocation.reorder_argv(other) == other


def test_the_payload_fields_follow_the_header_in_the_table(capsys):
    # Select Package (0x01), DSP0222 1.2.1 Table 26: Reserved, then the
    # Features Control byte (Table 27, bit 0 disables hardware arbitration)
    code, lines = run(
        capsys, "nc-si", "--type", "0x01", "--package", "3", "--channel",
        "package", "--iid", "0x10", "Reserved:3=0", "Features Control:1=1",
    )  # fmt: skip
    assert code == 0, lines
    assert lines[0] == "payload bytes: 4"
    assert lines[1] == "packet bytes: 24"
    table = rows(lines)
    assert [r[2] for r in table] == [
        "MC ID", "Header Revision", "Reserved", "IID", "Control Packet Type",
        "Channel ID", "Flags and Payload Length", "Reserved", "Reserved",
        "Features Control", "Checksum",
    ]  # fmt: skip
    assert [int(r[0]) for r in table] == [0, 1, 2, 3, 4, 5, 6, 8, 16, 19, 20]
    # every byte of the packet is in the table, in order
    assert tokens(" ".join(r[3] for r in table)) == packet(lines)


# ------------------------------------------------------------------ AC-2


def test_an_odd_payload_is_padded_and_the_sum_is_the_worked_one(capsys):
    # type 01, package 2 channel 3 (Channel ID 0x43), IID 5, 3 bytes 12 34 56
    # then one 00 of padding. Words: 0x0001 + 0x0005 + 0x0143 + 0x0003
    # (length) + 0x1234 + 0x5600 = 0x6980; two's complement 0xffff9680
    code, lines = run(
        capsys, "nc-si", "--type", "1", "--package", "2", "--channel", "3",
        "--iid", "5", "Value:3:be=0x123456",
    )  # fmt: skip
    assert code == 0, lines
    assert lines[:2] == ["payload bytes: 3", "packet bytes: 24"]
    assert (
        packet(lines)
        == (
            "00 01 00 05 01 43 00 03 00 00 00 00 00 00 00 00 12 34 56 00 ff ff 96 80"
        ).split()
    )
    table = rows(lines)
    assert table[-2] == ["19", "1", "Padding", "00"]
    assert table[-1] == ["20", "4", "Checksum", "ff ff 96 80"]


def test_payload_length_takes_twelve_bits_big_endian(capsys):
    code, lines = run(
        capsys, "nc-si", "--type", "0x0b", "--package", "0", "--channel", "1",
        "--iid", "2", "Data:300=0",
    )  # fmt: skip
    assert code == 0, lines
    got = packet(lines)
    assert got[6:8] == ["01", "2c"]
    assert lines[1] == f"packet bytes: {16 + 300 + 4}"
    assert not [r for r in rows(lines) if r[2] == "Padding"]


def test_the_checksum_matches_linux_for_random_packets(capsys):
    rng = random.Random(52)
    for _ in range(40):
        size = rng.randint(0, 40)
        fields = []
        if size:
            value = ",".join(f"0x{rng.randrange(256):02x}" for _ in range(size))
            fields = [f"Data:{size}={value}" if size > 1 else f"Data:1={value}"]
        argv = [
            "nc-si", "--type", hex(rng.randrange(0x80)),
            "--package", str(rng.randrange(8)),
            "--channel", hex(rng.randrange(0x20)),
            "--iid", str(rng.randint(1, 255)), *fields,
        ]  # fmt: skip
        code, lines = run(capsys, *argv)
        assert code == 0, (argv, lines)
        got = bytes(int(b, 16) for b in packet(lines))
        body = got[: 16 + size]
        assert len(got) == 16 + size + (-size) % 4 + 4, argv
        assert got[16 + size : -4] == bytes((-size) % 4), argv
        assert int.from_bytes(got[-4:], "big") == linux_checksum(body), argv
        # the header as DSP0222 Table 10 lays it out
        assert got[:3] == b"\x00\x01\x00", argv
        assert got[4] == int(argv[2], 16)
        assert got[5] == int(argv[4]) << 5 | int(argv[6], 16)
        assert got[6:8] == size.to_bytes(2, "big")
        assert got[8:16] == bytes(8)


# ------------------------------------------------------------------ AC-3


def test_the_whole_package_is_channel_1f(capsys):
    for channel in ("package", "0x1f", "31"):
        code, lines = run(
            capsys, "nc-si", "--type", "0x17", "--package", "1", "--channel",
            channel, "--iid", "1",
        )  # fmt: skip
        assert code == 0, (channel, lines)
        assert one(lines, NETLINK) == NETLINK + "-p 01 -c 1f raw 17"
        assert packet(lines)[5] == "3f"


def test_a_missing_iid_is_a_placeholder_and_zeroes_the_checksum(capsys):
    code, lines = run(
        capsys, "nc-si", "--type", "0x15", "--package", "0", "--channel", "0"
    )
    assert code == 0, lines
    got = packet(lines)
    assert got[3] == "<iid>"
    assert got[-4:] == ["00", "00", "00", "00"]
    text = notes(lines)
    assert "8.2.2.3" in text and "placeholder" in text, text
    # the ncsi-cmd lines carry no IID
    assert one(lines, NETLINK) == NETLINK + "-p 00 -c 00 raw 15"


@pytest.mark.parametrize(
    ("option", "value", "netlink"),
    [
        ("--package", "<package>", "-p <package> -c 01"),
        ("--channel", "<channel>", "-p 00 -c <channel>"),
    ],
)
def test_a_package_or_channel_placeholder_is_one_packet_byte(
    capsys, option, value, netlink
):
    argv = {"--package": "0", "--channel": "1"}
    argv[option] = value
    code, lines = run(
        capsys, "nc-si", "--type", "0x15", "--iid", "1",
        "--package", argv["--package"], "--channel", argv["--channel"],
    )  # fmt: skip
    assert code == 0, lines
    assert one(lines, NETLINK) == NETLINK + netlink + " raw 15"
    got = packet(lines)
    assert len(got) == 20, got
    assert got[5].startswith("<") and got[5].endswith(">"), got
    assert sum(t.startswith("<") for t in got) == 1, got
    assert got[-4:] == ["00", "00", "00", "00"]
    assert "8.2.2.3" in notes(lines)


def test_a_payload_placeholder_shows_in_both_lines(capsys):
    code, lines = run(
        capsys, "nc-si", "--type", "0x04", "--package", "0", "--channel", "0",
        "--iid", "9", "Reserved:3=0", "ALD:1=<ald>",
    )  # fmt: skip
    assert code == 0, lines
    assert one(lines, OVER_MCTP).endswith("raw 04 00 00 00 <ald>")
    got = packet(lines)
    assert got[16:20] == ["00", "00", "00", "<ald>"]
    assert got[-4:] == ["00", "00", "00", "00"]
    assert "8.2.2.3" in notes(lines)


def test_with_every_byte_known_there_is_no_checksum_note(capsys):
    code, lines = run(
        capsys, "nc-si", "--type", "0x15", "--package", "0", "--channel", "0",
        "--iid", "1",
    )  # fmt: skip
    assert code == 0, lines
    assert "8.2.2.3" not in notes(lines)


# ------------------------------------------------------------------ AC-4


BASE = ["--type", "0x15", "--package", "0", "--channel", "0", "--iid", "1"]


def _with(**changes):
    out = list(BASE)
    for key, value in changes.items():
        flag = f"--{key}"
        at = out.index(flag)
        if value is None:
            del out[at : at + 2]
        else:
            out[at + 1] = value
    return out


@pytest.mark.parametrize(
    ("argv", "word"),
    [
        (_with(type=None), "--type"),
        (_with(type="x15"), "--type"),
        (_with(type="<type>"), "--type"),
        (_with(type="0x80"), "--type"),
        (_with(type="0xff"), "--type"),
        (_with(type="-1"), "--type"),
        (_with(package="8"), "--package"),
        (_with(package="0x08"), "--package"),
        (_with(package=None), "--package"),
        (_with(channel="0x20"), "--channel"),
        (_with(channel="packages"), "--channel"),
        (_with(channel=None), "--channel"),
        (_with(iid="0"), "--iid"),
        (_with(iid="0x100"), "--iid"),
        (_with(iid="256"), "--iid"),
        (_with(iid="<a>b>"), "--iid"),
        ([*BASE, "Data:4096=0"], "4095"),
        ([*BASE, "A:4000=0", "B:96=0"], "4095"),
        ([*BASE, "Bad:1=0x100"], "Bad:1=0x100"),
        ([*BASE, "--subcommand", "GetTID"], "--subcommand"),
    ],
)
def test_a_wrong_option_is_refused_with_one_line(capsys, argv, word):
    code, lines = run(capsys, "nc-si", *argv)
    assert code == 2, lines
    assert len(lines) == 1, lines
    assert lines[0].startswith("invocation: "), lines
    assert word in lines[0], lines


@pytest.mark.parametrize("option", ["--type", "--package", "--channel", "--iid"])
@pytest.mark.parametrize(
    ("protocol", "fields"),
    [
        ("ipmi", ["NetFn:1=6", "Cmd:1=1"]),
        ("mctp-control", ["Header:1=0x80", "Cmd:1=2"]),
        ("pldm", ["Header:1=0x80", "Type:1=0", "Cmd:1=2"]),
        ("spdm", ["Version:1=0x10", "Code:1=0x84"]),
    ],
)
def test_the_nc_si_options_are_refused_with_another_protocol(
    capsys, option, protocol, fields
):
    code, lines = run(capsys, protocol, *fields, option, "1")
    assert code == 2, lines
    assert lines == [f"invocation: {option} is for nc-si, not {protocol}"]


def test_the_four_protocols_print_what_they_did(capsys):
    # develop's output for one request per protocol, byte for byte
    cases = {
        ("ipmi", "NetFn:1=6", "Cmd:1=1"): [
            "bytes: 2",
            "ipmitool raw 0x06 0x01",
            "offset | size | field | bytes",
            "0 | 1 | NetFn | 0x06",
            "1 | 1 | Cmd | 0x01",
        ],
        ("spdm", "Version:1=0x10", "Code:1=0x84"): [
            "bytes: 2",
            "mctp-client eid <eid> type spdm data 10 84",
            "offset | size | field | bytes",
            "0 | 1 | Version | 10",
            "1 | 1 | Code | 84",
        ],
    }
    for argv, want in cases.items():
        code, lines = run(capsys, *argv)
        assert code == 0, lines
        assert lines == want


def test_the_unknown_protocol_line_names_nc_si():
    with pytest.raises(invocation.FieldError) as raised:
        invocation.render("nvme", ["X:1=0"])
    assert str(raised.value) == (
        "unknown protocol 'nvme'; it is one of ipmi, mctp-control, nc-si, pldm, spdm"
    )


def test_render_of_nc_si_without_its_header_is_refused():
    with pytest.raises(invocation.FieldError) as raised:
        invocation.render("nc-si", [])
    assert "--type" in str(raised.value)


# ------------------------------------------------------------------ AC-5


def test_the_notes_say_how_ncsi_cmd_reads_numbers_and_the_iid_rule(capsys):
    code, lines = run(capsys, "nc-si", *BASE)
    assert code == 0, lines
    text = notes(lines)
    for word in ("-i", "-p", "-c", "TYPE", "hex", "decimal", "-m", "EID"):
        assert word in text, word
    assert "another interface" in text
    assert "0x01..0xff" in text and "retry" in text and "6.2.2.2" in text


# ------------------------------------------------------------------ AC-6


def _block():
    text = SKILL.read_text("utf-8")
    start = text.index(START) + len(START)
    return text[start : text.index(END)].strip("\n").splitlines()


def _flat(lines):
    return " ".join(" ".join(lines).split())


def test_the_block_stays_within_its_raised_cap():
    assert len(_block()) <= MAX_LINES, len(_block())


def test_the_block_gives_nc_si_an_invocation():
    text = _flat(_block())
    for word in (
        "ncsi-cmd",
        "phosphor-networkd 1c55a45",
        "type nc-si",
        # one `invocation` span in the block (test_review_cmdblock): the
        # nc-si call names its options in a span of its own
        "`nc-si --type <t> --package <p> --channel <c>`",
        "Response N bytes:",
        "Reason Code",
    ):
        assert word in text, word
    # NC-SI fields are big-endian
    assert re.search(r"NC-SI[^.]*big-endian|big-endian[^.]*NC-SI", text), text
    assert "Other Families (NVMe-MI): no Invocation, no bytes to send;" in text
    assert "Other Families (NC-SI, NVMe-MI)" not in text
    assert "OEM 0x50: none" in text


def test_the_front_matter_is_develops():
    text = SKILL.read_text("utf-8")
    front = text.split("---")[1]
    assert hashlib.sha256(front.encode()).hexdigest() == FRONT_MATTER_SHA


def test_the_skill_table_row_names_nc_si():
    skill = SKILL.read_text("utf-8")
    row = one(skill.splitlines(), "| `invocation ")
    # no tool name outside the block (test_review_cmdblock's removal check)
    for word in ("nc-si", "--type", "--package", "--channel", "netlink", "MCTP"):
        assert word in row, word


# ------------------------------------------------------------------ AC-7


def test_commands_doc_describes_nc_si():
    doc = " ".join(COMMANDS_DOC.read_text("utf-8").split())
    for word in (
        "`invocation nc-si --type",
        "--package",
        "--channel",
        "--iid",
        "payload bytes: N",
        "packet bytes: M",
        "ncsi-cmd -i",
        "ncsi-cmd -m",
        "type nc-si",
        "`<iid>`",
        "00 00 00 00",
        "0x7f",
        "0xfff",
        "is for nc-si",
    ):
        assert word in doc, word


def test_readme_names_ncsi_cmd_and_keeps_nvme_mi_out():
    text = README.read_text("utf-8")
    assert len(text.splitlines()) <= 200
    start = text.index("## How a question is answered")
    section = " ".join(text[start : text.index("\n## ", start + 1)].split())
    assert "NC-SI" in section and "`ncsi-cmd`" in section
    assert "NVMe-MI" in section
    assert "(NC-SI, NVMe-MI)" not in section

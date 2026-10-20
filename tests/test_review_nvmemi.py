"""Reviewer acceptance tests for T53: ``invocation nvme-mi`` prints the whole
NVMe-MI message with its MIC, and for an NVMe Admin Command the
``nvme admin-passthru`` line.

Black-box through the CLI entry point. The MIC is checked against a
table-driven CRC-32C written here, not the helper's bitwise one, and that
table is itself checked against the public RFC 3720 B.4 vectors. AC-7's and
AC-8's sentences are documentation and are not pinned; what is pinned there
is the block's growth within its cap, the front matter, the absence of a
``type nvme`` line and the README's line cap. AC-9 is a measurement outside
the repository.
"""

import hashlib
import random
import re
from pathlib import Path

import pytest

from bmc_toolkit.spec import invocation
from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
README = ROOT / "README.md"

START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
DEVELOP_LINES = 52  # the cap before T53
MAX_LINES = 58  # 46 until T52 (NC-SI Invocation); 52 until T53
# sha256 of SKILL.md's front matter on develop (AC-7: unchanged); the same
# value test_invocation_ncsi.py pins on develop
FRONT_MATTER_SHA = "46edbffa30899ddf84be501e93d260d25163b63bf7f6fcf49c1ec13efeced22a"

MESSAGE = "message: "
PASSTHRU = "nvme admin-passthru mctp:<net>,<eid>:"
TABLE_HEADER = "offset | size | field | bytes"


# ------------------------------------------------------------ CRC-32C here


def _crc_table() -> list[int]:
    table = []
    for n in range(256):
        c = n
        for _ in range(8):
            c = (c >> 1) ^ 0x82F63B78 if c & 1 else c >> 1
        table.append(c)
    return table


CRC_TABLE = _crc_table()


def crc32c(data: bytes) -> int:
    """Table-driven CRC-32C: reflected polynomial 0x82F63B78, initial value
    and final XOR 0xFFFFFFFF."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc = CRC_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


def mic_of(body: bytes) -> list[str]:
    return [f"{b:02x}" for b in crc32c(body).to_bytes(4, "little")]


# --------------------------------------------------------------- helpers


@pytest.fixture(autouse=True)
def no_library(monkeypatch, tmp_path):
    """The command reads no Library: point at one that is not there."""
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
    # a placeholder may hold spaces (`<nmd0 0>`): one token all the same
    return re.findall(r"<[^>]*>|\S+", text)


def message(lines):
    return tokens(one(lines, MESSAGE)[len(MESSAGE) :])


def notes(lines):
    return [ln for ln in lines if ln.startswith("note: ")]


def rows(lines):
    at = lines.index(TABLE_HEADER)
    return [ln.split(" | ") for ln in lines[at + 1 :]]


def passthru(lines):
    return one(lines, PASSTHRU)


def options(line):
    """The ``--name=value`` options of a passthru line as a list of pairs."""
    # the controller may be `<ctrl id>`, a placeholder with a space in it
    items = tokens(line[len(PASSTHRU) :])
    ctrl, pairs = items[0], []
    for item in items[1:]:
        assert item.startswith("--") and "=" in item, item
        name, _, value = item[2:].partition("=")
        pairs.append((name, value))
    return ctrl, pairs


def hexval(value):
    assert re.fullmatch(r"0x[0-9a-fA-F]+", value), value
    return int(value, 16)


def mi_fields(opcode="0x01", nmd0=0, nmd1=0, extra=()):
    return [
        f"Opcode:1={opcode}",
        "Reserved:3=0",
        f"NMD0:4={nmd0}",
        f"NMD1:4={nmd1}",
        *extra,
    ]


def admin_fields(**given):
    """An Admin request with every field zero but those given by name:
    opcode, cflgs, ctlid, nsid, cdw2..cdw5, dofst, dlen, cdw10..cdw15."""
    get = given.get
    return [
        f"Opcode:1={get('opcode', '0x06')}",
        f"CFLGS:1={get('cflgs', 0)}",
        f"CTLID:2={get('ctlid', 0)}",
        f"NSID:4={get('nsid', 0)}",
        f"CDW2:4={get('cdw2', 0)}",
        f"CDW3:4={get('cdw3', 0)}",
        f"CDW4:4={get('cdw4', 0)}",
        f"CDW5:4={get('cdw5', 0)}",
        f"DOFST:4={get('dofst', 0)}",
        f"DLEN:4={get('dlen', 0)}",
        "Reserved:8=0",
        *(f"CDW{n}:4={get(f'cdw{n}', 0)}" for n in range(10, 16)),
    ]


# NVMe-MI 2.2 Appendix C Example 3 as AC-2 names it: NVM Subsystem Health
# Status Poll with CCF set; the MIC AC-2 gives is aa ef 81 b4
HEALTH_POLL = mi_fields(opcode="0x01", nmd1="0x80000000")
# Appendix C Example 1 as AC-2 names it: Identify; the MIC is 4a c3 2c fa
IDENTIFY = admin_fields(
    opcode="0x06", cflgs=3, ctlid=1, dofst=4, dlen=0x14, cdw10=1
)


# ------------------------------------------------------------------ AC-1


def test_an_mi_request_prints_the_lines_in_order_and_no_tool_line(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *HEALTH_POLL)
    assert code == 0, lines
    assert lines[0] == "request bytes: 12"
    assert lines[1] == "message bytes: 20"
    assert lines[2].startswith(MESSAGE), lines
    at = lines.index(TABLE_HEADER)
    assert at > 3 and all(ln.startswith("note: ") for ln in lines[3:at]), lines
    assert len(lines) > at + 1
    # two hex digits per byte, space separated
    got = message(lines)
    assert len(got) == 20
    assert all(re.fullmatch(r"[0-9a-f]{2}", t) for t in got), got
    # no tool line for an NVMe-MI command, and never mctp-client
    assert not any(ln.startswith(("nvme ", "mctp-client")) for ln in lines), lines


def test_an_admin_request_prints_the_passthru_line_then_the_message(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *IDENTIFY)
    assert code == 0, lines
    assert lines[0] == "request bytes: 64"
    assert lines[1] == "message bytes: 72"
    assert lines[2].startswith(PASSTHRU), lines
    assert lines[3].startswith(MESSAGE), lines
    at = lines.index(TABLE_HEADER)
    assert at > 4 and all(ln.startswith("note: ") for ln in lines[4:at]), lines
    assert len(message(lines)) == 72
    assert not any("mctp-client" in ln for ln in lines), lines


def test_the_table_counts_from_byte_0_and_holds_the_message_byte_for_byte(capsys):
    fields = [*HEALTH_POLL, "Data:3=0x0a,0x0b,0x0c"]
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *fields)
    assert code == 0, lines
    table = rows(lines)
    # four header byte groups, five request fields, the MIC
    assert len(table) == 4 + 5 + 1, table
    offsets = [int(row[0]) for row in table]
    sizes = [int(row[1]) for row in table]
    assert offsets[0] == 0
    for i in range(1, len(table)):
        assert offsets[i] == offsets[i - 1] + sizes[i - 1], table
    assert sizes[:4] == [1, 1, 1, 1]
    assert [row[2] for row in table[4:9]] == [
        "Opcode",
        "Reserved",
        "NMD0",
        "NMD1",
        "Data",
    ]
    assert sizes[4:9] == [1, 3, 4, 4, 3]
    assert table[4][0] == "4"  # the opcode at byte 4
    assert table[-1][2] == "MIC" and sizes[-1] == 4
    assert [t for row in table for t in tokens(row[3])] == message(lines)
    assert one(lines, "message bytes:") == "message bytes: 23"


def test_the_options_after_the_fields_give_the_same_output(capsys):
    _, before = run(capsys, "nvme-mi", "--nmimt", "admin", "--csi", "1", *IDENTIFY)
    _, after = run(capsys, "nvme-mi", *IDENTIFY, "--nmimt=admin", "--csi", "1")
    _, mixed = run(
        capsys, "nvme-mi", *IDENTIFY[:5], "--csi=1", *IDENTIFY[5:], "--nmimt", "admin"
    )
    assert before == after == mixed


# ------------------------------------------------------------------ AC-2


@pytest.mark.parametrize(
    ("nmimt", "csi", "byte1"),
    [
        ("mi", None, "08"),
        ("mi", "0", "08"),
        ("mi", "1", "09"),
        ("admin", None, "10"),
        ("admin", "0", "10"),
        ("admin", "1", "11"),
    ],
)
def test_the_header_is_84_then_ror_0_nmimt_csi_then_two_zero_bytes(
    capsys, nmimt, csi, byte1
):
    fields = HEALTH_POLL if nmimt == "mi" else IDENTIFY
    argv = ["nvme-mi", "--nmimt", nmimt, *(["--csi", csi] if csi else []), *fields]
    code, lines = run(capsys, *argv)
    assert code == 0, lines
    got = message(lines)
    assert got[:4] == ["84", byte1, "00", "00"]
    table = rows(lines)
    assert [row[3] for row in table[:4]] == ["84", byte1, "00", "00"]
    body = bytes(int(t, 16) for t in got[:-4])
    assert got[-4:] == mic_of(body)


def test_the_fields_follow_the_header_from_byte_4_little_endian(capsys):
    fields = mi_fields(opcode="0x05", nmd0="0x11223344", nmd1="0xaabbccdd")
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *fields)
    assert code == 0, lines
    got = message(lines)
    assert got[4:16] == "05 00 00 00 44 33 22 11 dd cc bb aa".split()
    # :be keeps the existing meaning
    fields = mi_fields(opcode="0x05", nmd0="0x11223344", extra=[])
    fields[2] = "NMD0:4:be=0x11223344"
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *fields)
    assert code == 0, lines
    assert message(lines)[8:12] == ["11", "22", "33", "44"]


def test_the_two_appendix_c_examples_have_the_mic_ac_2_names(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *HEALTH_POLL)
    assert code == 0, lines
    got = message(lines)
    assert got[:4] == ["84", "08", "00", "00"]
    assert got[4:16] == "01 00 00 00 00 00 00 00 00 00 00 80".split()
    assert got[16:] == ["aa", "ef", "81", "b4"]
    assert got[-4:] == mic_of(bytes(int(t, 16) for t in got[:-4]))

    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *IDENTIFY)
    assert code == 0, lines
    got = message(lines)
    assert got[:8] == "84 10 00 00 06 03 01 00".split()
    assert got[-4:] == ["4a", "c3", "2c", "fa"]
    assert got[-4:] == mic_of(bytes(int(t, 16) for t in got[:-4]))
    assert rows(lines)[-1][3] == "4a c3 2c fa"


def test_the_crc_is_crc32c_by_its_check_value_and_rfc_3720_vectors():
    # the table used here, then the helper's own function (AC-2 names it)
    for crc in (crc32c, invocation.nvme_mi_crc):
        assert crc(b"123456789") == 0xE3069283
        # RFC 3720 B.4 test vectors, written there least significant byte first
        assert crc(bytes(32)) == 0x8A9136AA
        assert crc(b"\xff" * 32) == 0x62A8AB43
        assert crc(bytes(range(32))) == 0x46DD794E
        assert crc(bytes(range(31, -1, -1))) == 0x113FDB5C
    rng = random.Random(2026)
    for _ in range(200):
        data = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 300)))
        assert invocation.nvme_mi_crc(data) == crc32c(data)


def test_the_mic_covers_every_byte_from_byte_0_for_random_requests(capsys):
    rng = random.Random(53)
    for _ in range(30):
        size = rng.randrange(12, 120)
        data = [rng.randrange(256) for _ in range(size)]
        fields = [
            f"Opcode:1=0x{data[0]:02x}",
            f"Rest:{size - 1}={','.join(f'0x{b:02x}' for b in data[1:])}",
        ]
        csi = rng.choice(["0", "1"])
        code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", "--csi", csi, *fields)
        assert code == 0, lines
        got = message(lines)
        body = bytes([0x84, 0x08 | int(csi), 0, 0, *data])
        assert got[:-4] == [f"{b:02x}" for b in body]
        assert got[-4:] == mic_of(body)
        assert one(lines, "message bytes:") == f"message bytes: {size + 8}"
    # and for Admin requests with random dwords (direction bits 00, 01 or 10)
    for _ in range(20):
        opcode = rng.randrange(256) & ~0x03 | rng.choice([0, 1, 2])
        given = {
            "opcode": f"0x{opcode:02x}",
            "cflgs": rng.randrange(256),
            "ctlid": rng.randrange(0x10000),
            "nsid": rng.randrange(1 << 32),
            "cdw2": rng.randrange(1 << 32),
            "cdw3": rng.randrange(1 << 32),
            "dlen": rng.randrange(4097),
            **{f"cdw{n}": rng.randrange(1 << 32) for n in range(10, 16)},
        }
        fields = admin_fields(**given)
        code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
        assert code == 0, lines
        got = message(lines)
        body = bytes(int(t, 16) for t in got[:-4])
        assert len(body) == 68
        assert got[-4:] == mic_of(body)


# ------------------------------------------------------------------ AC-3


def test_a_placeholder_gives_four_mic_placeholders_and_a_note(capsys):
    fields = mi_fields(opcode="0x02", nmd0="<nmd0>")
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *fields)
    assert code == 0, lines
    got = message(lines)
    assert got[8:12] == ["<nmd0 0>", "<nmd0 1>", "<nmd0 2>", "<nmd0 3>"]
    assert got[-4:] == ["<mic>"] * 4
    assert rows(lines)[-1][2] == "MIC"
    assert tokens(rows(lines)[-1][3]) == ["<mic>"] * 4
    text = " ".join(notes(lines))
    assert "<mic>" in text or "MIC" in text, text
    assert re.search(r"placeholder|every value", text), text


def test_a_placeholder_opcode_keeps_the_mic_unknown_in_an_admin_request(capsys):
    fields = admin_fields(opcode="<opcode>")
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
    assert code == 0, lines
    got = message(lines)
    assert got[4] == "<opcode>"
    assert got[-4:] == ["<mic>"] * 4
    assert passthru(lines)  # the tool line is still printed


def test_with_every_byte_known_the_mic_is_computed_and_there_is_no_note(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *admin_fields())
    assert code == 0, lines
    got = message(lines)
    assert "<mic>" not in got
    assert got[-4:] == mic_of(bytes(int(t, 16) for t in got[:-4]))
    text = " ".join(notes(lines))
    assert "<mic>" not in text and "placeholder" not in text, text


# ------------------------------------------------------------------ AC-4


def test_the_passthru_line_names_every_non_zero_dword_in_order_in_hex(capsys):
    fields = admin_fields(
        opcode="0x0a",
        ctlid="0x0102",
        nsid="0xfffffffe",
        cdw2="0x22",
        cdw3="0x33",
        dlen=4096,
        cdw10="0x10101010",
        cdw11=11,
        cdw12=12,
        cdw13=13,
        cdw14=14,
        cdw15="0xffffffff",
    )
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
    assert code == 0, lines
    ctrl, pairs = options(passthru(lines))
    assert ctrl == "258"  # CTLID 0x0102 in decimal
    assert [name for name, _ in pairs] == [
        "opcode",
        "namespace-id",
        "cdw2",
        "cdw3",
        "cdw10",
        "cdw11",
        "cdw12",
        "cdw13",
        "cdw14",
        "cdw15",
        "data-len",
    ]
    values = dict(pairs)
    assert values["opcode"] == "0x0a"
    assert hexval(values["namespace-id"]) == 0xFFFFFFFE
    assert hexval(values["cdw2"]) == 0x22
    assert hexval(values["cdw3"]) == 0x33
    assert hexval(values["cdw10"]) == 0x10101010
    assert [hexval(values[f"cdw{n}"]) for n in range(11, 15)] == [11, 12, 13, 14]
    assert hexval(values["cdw15"]) == 0xFFFFFFFF
    assert hexval(values["data-len"]) == 4096


def test_zero_dwords_and_a_zero_dlen_are_left_out(capsys):
    fields = admin_fields(opcode="0x0c")
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
    assert code == 0, lines
    assert passthru(lines) == f"{PASSTHRU}0 --opcode=0x0c"
    code, lines = run(
        capsys, "nvme-mi", "--nmimt", "admin", *admin_fields(opcode="0x02", cdw10=2)
    )
    assert code == 0, lines
    ctrl, pairs = options(passthru(lines))
    assert ctrl == "0"
    assert [name for name, _ in pairs] == ["opcode", "cdw10"]
    assert hexval(dict(pairs)["cdw10"]) == 2


def test_the_dwords_are_read_by_offset_however_the_fields_are_cut(capsys):
    # CDW10 in three fields, CDW2 and CDW3 in one 8-byte field, NSID in bytes
    fields = admin_fields(opcode="0x02", dlen=512)
    at = fields.index("CDW10:4=0")
    fields[at : at + 1] = ["LID:1=0x02", "LSP and RAE:1=0", "NUMDL:2=0x7f"]
    at = fields.index("CDW2:4=0")
    fields[at : at + 2] = ["CDW2 and CDW3:8=0x0000000300000002"]
    at = fields.index("NSID:4=0")
    fields[at] = "NSID:4=0x01,0x00,0x00,0x00"
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
    assert code == 0, lines
    assert lines[0] == "request bytes: 64"
    _, pairs = options(passthru(lines))
    values = dict(pairs)
    assert hexval(values["cdw10"]) == 0x007F0002
    assert hexval(values["cdw2"]) == 2
    assert hexval(values["cdw3"]) == 3
    assert hexval(values["namespace-id"]) == 1
    assert hexval(values["data-len"]) == 512


def test_a_placeholder_dword_prints_as_its_named_placeholder(capsys):
    fields = admin_fields(
        ctlid="<controller>", nsid="<ns>", cdw12="<x>", dlen="<len>"
    )
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
    assert code == 0, lines
    ctrl, pairs = options(passthru(lines))
    assert ctrl == "<ctrl id>"
    values = dict(pairs)
    assert values["namespace-id"] == "<nsid>"
    assert values["cdw12"] == "<cdw12>"
    assert values["data-len"] == "<dlen>"
    assert "cdw11" not in values and "cdw2" not in values
    # one placeholder byte inside a dword: the whole dword is a placeholder
    fields = admin_fields()
    at = fields.index("CDW10:4=0")
    fields[at : at + 1] = ["LID:1=0x02", "LSP and RAE:1=<lsp>", "NUMDL:2=0x7f"]
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
    assert code == 0, lines
    assert dict(options(passthru(lines))[1])["cdw10"] == "<cdw10>"
    fields = admin_fields(opcode="<op>")
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
    assert code == 0, lines
    assert dict(options(passthru(lines))[1])["opcode"] == "<op>"


def test_request_data_past_dword_15_is_in_the_message_not_the_line(capsys):
    fields = [*admin_fields(opcode="0x09", dlen=4), "Data:4=0x01020304"]
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
    assert code == 0, lines
    assert lines[0] == "request bytes: 68"
    assert one(lines, "message bytes:") == "message bytes: 76"
    got = message(lines)
    assert got[68:72] == ["04", "03", "02", "01"]
    assert got[-4:] == mic_of(bytes(int(t, 16) for t in got[:-4]))
    assert "0x01020304" not in passthru(lines) and "Data" not in passthru(lines)
    assert hexval(dict(options(passthru(lines))[1])["data-len"]) == 4


def test_mi_prints_no_tool_line_and_neither_prints_mctp_client(capsys):
    for nmimt, fields in (("mi", HEALTH_POLL), ("admin", IDENTIFY)):
        code, lines = run(capsys, "nvme-mi", "--nmimt", nmimt, *fields)
        assert code == 0, lines
        assert not any(ln.startswith("mctp-client") for ln in lines), lines
        assert not any("type nvme" in ln for ln in lines), lines
        tool = [ln for ln in lines if ln.startswith("nvme ")]
        assert len(tool) == (1 if nmimt == "admin" else 0), lines


# ------------------------------------------------------------------ AC-5


def test_the_mi_notes_say_no_openbmc_command_sends_it(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *HEALTH_POLL)
    assert code == 0, lines
    text = " ".join(notes(lines))
    for word in ("OpenBMC", "mctp-client", "IC bit", "MIC", "nvme-cli", "Admin"):
        assert word in text, (word, text)
    assert re.search(r"capture", text) and "libnvme" in text, text
    assert "no command" in text or "No command" in text, text


def test_the_admin_notes_name_nvme_cli_2_16_and_how_it_reads_its_line(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *admin_fields())
    assert code == 0, lines
    text = " ".join(notes(lines))
    for word in ("2.16", "probe", "decimal", "bits 1..0", "stdin", "-i "):
        assert word in text, (word, text)
    assert "-r" in text and "-w" in text, text
    # nothing held in DOFST or Dwords 4-5: no note on where nvme-cli differs
    assert "DOFST" not in text, text


@pytest.mark.parametrize(
    "given",
    [{"dofst": 4}, {"cdw4": 1}, {"cdw5": "0x80000000"}, {"dofst": "<off>"}],
)
def test_the_admin_notes_say_where_nvme_cli_differs_when_the_fields_hold_them(
    capsys, given
):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *admin_fields(**given))
    assert code == 0, lines
    text = " ".join(notes(lines))
    assert "DOFST" in text, text
    assert re.search(r"Dwords? 4", text), text


def test_a_message_above_64_bytes_gets_the_packets_note(capsys):
    _, small = run(capsys, "nvme-mi", "--nmimt", "mi", *HEALTH_POLL)
    assert not any("packet" in ln for ln in notes(small)), small
    exact = mi_fields(extra=["Data:44=0"])
    _, at64 = run(capsys, "nvme-mi", "--nmimt", "mi", *exact)
    assert one(at64, "message bytes:") == "message bytes: 64"
    assert not any("packet" in ln for ln in notes(at64)), at64
    over = mi_fields(extra=["Data:45=0"])
    _, at65 = run(capsys, "nvme-mi", "--nmimt", "mi", *over)
    assert one(at65, "message bytes:") == "message bytes: 65"
    text = " ".join(notes(at65))
    assert "packet" in text and "64" in text, text
    # every Admin message is above 64 bytes
    _, admin = run(capsys, "nvme-mi", "--nmimt", "admin", *admin_fields())
    assert any("packet" in ln for ln in notes(admin)), admin


# ------------------------------------------------------------------ AC-6


@pytest.mark.parametrize(
    ("argv", "word"),
    [
        (HEALTH_POLL, "PCIe"),
        (HEALTH_POLL, "Control Primitives"),
        (["--nmimt", "pcie", *HEALTH_POLL], "PCIe"),
        (["--nmimt", "control", *HEALTH_POLL], "Control Primitives"),
        (["--nmimt", "MI", *HEALTH_POLL], "--nmimt"),
        (["--nmimt", "1", *HEALTH_POLL], "--nmimt"),
        (["--nmimt", "mi", "--csi", "2", *HEALTH_POLL], "--csi"),
        (["--nmimt", "mi", "--csi", "-1", *HEALTH_POLL], "--csi"),
        (["--nmimt", "mi", "--csi", "<slot>", *HEALTH_POLL], "--csi"),
        (["--nmimt", "admin", "--csi", "x", *IDENTIFY], "--csi"),
        (["--nmimt", "mi", *HEALTH_POLL[:3]], "12"),
        (["--nmimt", "mi", "Opcode:1=1", "Rest:10=0"], "12"),
        (["--nmimt", "mi"], "12"),
        (["--nmimt", "admin", *HEALTH_POLL], "64"),
        (["--nmimt", "admin", *IDENTIFY[:-1]], "64"),
        (["--nmimt", "admin"], "64"),
        (["--nmimt", "mi", *HEALTH_POLL, "Data:4205=0"], "4224"),
        (["--nmimt", "admin", *admin_fields(), "Data:4153=0"], "4224"),
        (["--nmimt", "admin", *admin_fields(dlen=4097)], "4096"),
        (["--nmimt", "admin", *admin_fields(dlen="0xffffffff")], "4096"),
        (["--nmimt", "admin", *admin_fields(opcode="0x03")], "bidirectional"),
        (["--nmimt", "admin", *admin_fields(opcode="0x7f")], "bidirectional"),
        (["--nmimt", "admin", *admin_fields(opcode="0xc3")], "bidirectional"),
        (["--nmimt", "mi", *HEALTH_POLL, "Bad:1=0x100"], "Bad:1=0x100"),
        (["--nmimt", "mi", *HEALTH_POLL, "Bad:1=<a><b>"], "placeholder"),
        (["--nmimt", "mi", "--type", "0x15", *HEALTH_POLL], "--type"),
        (["--nmimt", "mi", "--package", "0", *HEALTH_POLL], "--package"),
        (["--nmimt", "mi", "--channel", "0", *HEALTH_POLL], "--channel"),
        (["--nmimt", "admin", "--iid", "1", *IDENTIFY], "--iid"),
        (["--nmimt", "mi", "--subcommand", "X", *HEALTH_POLL], "--subcommand"),
    ],
)
def test_a_wrong_request_is_refused_with_one_invocation_line(capsys, argv, word):
    code, lines = run(capsys, "nvme-mi", *argv)
    assert code == 2, lines
    assert len(lines) == 1, lines
    assert lines[0].startswith("invocation: "), lines
    assert word in lines[0], (word, lines)
    assert MESSAGE not in lines[0] and PASSTHRU not in lines[0]


def test_the_nc_si_options_are_named_as_nc_si_s_when_given_to_nvme_mi(capsys):
    argv = ["nvme-mi", "--nmimt", "mi", "--type", "0x15", *HEALTH_POLL]
    code, lines = run(capsys, *argv)
    assert code == 2, lines
    assert lines == ["invocation: --type is for nc-si, not nvme-mi"]


def test_the_largest_message_and_dlen_are_taken(capsys):
    argv = ["nvme-mi", "--nmimt", "mi", *HEALTH_POLL, "Data:4204=0"]
    code, lines = run(capsys, *argv)
    assert code == 0, lines
    assert one(lines, "message bytes:") == "message bytes: 4224"
    assert len(message(lines)) == 4224
    fields = admin_fields(dlen=4096)
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
    assert code == 0, lines
    assert hexval(dict(options(passthru(lines))[1])["data-len"]) == 4096


def test_an_mi_opcode_with_bits_11_is_taken_and_the_admin_direction_bits_are_read(
    capsys,
):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *mi_fields(opcode="0x03"))
    assert code == 0, lines
    for opcode in ("0x00", "0x01", "0x02", "0x7c", "0xfd", "0xfe"):
        code, lines = run(
            capsys, "nvme-mi", "--nmimt", "admin", *admin_fields(opcode=opcode)
        )
        assert code == 0, (opcode, lines)


@pytest.mark.parametrize("option", ["--nmimt", "--csi"])
@pytest.mark.parametrize(
    ("protocol", "fields"),
    [
        ("ipmi", ["NetFn:1=6", "Cmd:1=1"]),
        ("mctp-control", ["Header:1=0x80", "Cmd:1=2"]),
        ("pldm", ["Header:1=0x80", "Type:1=0", "Cmd:1=2"]),
        ("spdm", ["Version:1=0x10", "Code:1=0x84"]),
        ("nc-si", ["--type", "0x15", "--package", "0", "--channel", "0"]),
    ],
)
def test_the_nvme_mi_options_are_refused_with_another_protocol(
    capsys, option, protocol, fields
):
    value = "mi" if option == "--nmimt" else "0"
    code, lines = run(capsys, protocol, *fields, option, value)
    assert code == 2, lines
    assert len(lines) == 1, lines
    assert lines[0].startswith("invocation: "), lines
    assert option in lines[0] and "nvme-mi" in lines[0], lines
    assert protocol in lines[0], lines


def test_the_five_protocols_print_develops_lines_and_the_unknown_line_grew(capsys):
    cases = {
        ("ipmi", "NetFn:1=6", "Cmd:1=1"): [
            "bytes: 2",
            "ipmitool raw 0x06 0x01",
            TABLE_HEADER,
            "0 | 1 | NetFn | 0x06",
            "1 | 1 | Cmd | 0x01",
        ],
        ("mctp-control", "Header:1=0x80", "Cmd:1=2"): [
            "bytes: 2",
            "mctp-client eid <eid> type control data 80 02",
            TABLE_HEADER,
            "0 | 1 | Header | 80",
            "1 | 1 | Cmd | 02",
        ],
        ("pldm", "Header:1=0x80", "Type:1=0", "Cmd:1=2"): [
            "bytes: 3",
            "mctp-client eid <eid> type pldm data 80 00 02",
            "pldmtool raw -m <eid> -d 0x80 0x00 0x02",
            TABLE_HEADER,
            "0 | 1 | Header | 80",
            "1 | 1 | Type | 00",
            "2 | 1 | Cmd | 02",
        ],
        ("spdm", "Version:1=0x10", "Code:1=0x84"): [
            "bytes: 2",
            "mctp-client eid <eid> type spdm data 10 84",
            TABLE_HEADER,
            "0 | 1 | Version | 10",
            "1 | 1 | Code | 84",
        ],
    }
    for argv, want in cases.items():
        code, lines = run(capsys, *argv)
        assert code == 0, lines
        assert lines == want, argv
    ncsi = ["--type", "0x15", "--package", "0", "--channel", "0", "--iid", "1"]
    code, lines = run(capsys, "nc-si", *ncsi)
    assert code == 0, lines
    assert lines[0] == "payload bytes: 0"
    assert lines[1] == "packet bytes: 20"
    assert one(lines, "mctp-client") == (
        "mctp-client eid <eid> type nc-si data "
        "00 01 00 01 15 00 00 00 00 00 00 00 00 00 00 00 ff ff ea fe"
    )
    # the unknown-protocol line now names nvme-mi
    code, lines = run(capsys, "nvme", "X:1=0")
    assert code == 2, lines
    assert lines == [
        "invocation: unknown protocol 'nvme'; it is one of ipmi, mctp-control, "
        "nc-si, nvme-mi, pldm, spdm"
    ]


# ------------------------------------------------------------ AC-7, AC-8


def _block() -> list[str]:
    lines = SKILL.read_text("utf-8").splitlines()
    assert lines.count(START) == 1 and lines.count(END) == 1
    first, last = lines.index(START), lines.index(END)
    assert first < last
    return lines[first + 1 : last]


def test_the_block_grew_for_nvme_mi_within_58_lines_without_a_type_nvme_line():
    body = _block()
    assert DEVELOP_LINES < len(body) <= MAX_LINES, len(body)
    text = SKILL.read_text("utf-8")
    assert "type nvme" not in text
    # no mctp-client line in the block mentions NVMe (it cannot send one right)
    for line in body:
        if "mctp-client" in line:
            assert "nvme" not in line.lower(), line
    # the front matter is develop's
    front = text.split("---")[1]
    assert hashlib.sha256(front.encode()).hexdigest() == FRONT_MATTER_SHA
    # the README stays within its cap
    assert len(README.read_text("utf-8").splitlines()) <= 200

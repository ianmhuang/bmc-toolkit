"""``invocation nvme-mi``: the whole NVMe-MI message with its MIC, laid out
by the helper, and for an NVMe Admin Command the ``nvme admin-passthru``
line nvme-cli sends it with (T53, ADR 0009 of the design workspace)."""

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
MAX_LINES = 58  # AC-7: 52 until T53
# sha256 of SKILL.md's front matter on develop c2ae57b (AC-7: unchanged)
FRONT_MATTER_SHA = "46edbffa30899ddf84be501e93d260d25163b63bf7f6fcf49c1ec13efeced22a"

MESSAGE = "message: "
PASSTHRU = "nvme admin-passthru mctp:<net>,<eid>:"


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
    # a placeholder may hold spaces (`<nmd0 0>`): one token all the same
    return re.findall(r"<[^>]*>|\S+", text)


def message(lines):
    return tokens(one(lines, MESSAGE)[len(MESSAGE) :])


def notes(lines):
    return " ".join(ln for ln in lines if ln.startswith("note: "))


def rows(lines):
    at = lines.index("offset | size | field | bytes")
    return [ln.split(" | ") for ln in lines[at + 1 :]]


def crc32c(data: bytes) -> int:
    """CRC-32C written out bit by bit from NVMe-MI 2.2 Figure 21: reflected
    polynomial 0x82F63B78, initial value and final XOR 0xFFFFFFFF."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x82F63B78 if crc & 1 else crc >> 1
    return crc ^ 0xFFFFFFFF


# NVMe-MI 2.2 Appendix C Example 3 (p.207): NVM Subsystem Health Status
# Poll with CCF set, MIC aa ef 81 b4
HEALTH_POLL = [
    "Opcode:1=0x01",
    "Reserved:3=0",
    "NMD0:4=0",
    "NMD1:4=0x80000000",
]
HEALTH_POLL_BYTES = (
    "84 08 00 00 01 00 00 00 00 00 00 00 00 00 00 80 aa ef 81 b4".split()
)

# NVMe-MI 2.2 Appendix C Example 1 (pp.205-206): Identify, CNS 01h, 20
# bytes from offset 4, MIC 4a c3 2c fa
IDENTIFY = [
    "Opcode:1=0x06",
    "CFLGS:1=0x03",
    "CTLID:2=1",
    "SQE Dwords 1-5:20=0",
    "DOFST:4=4",
    "DLEN:4=0x14",
    "Reserved:8=0",
    "SQE Dword 10:4=1",
    "SQE Dwords 11-15:20=0",
]
IDENTIFY_BYTES = (
    ["84", "10", "00", "00", "06", "03", "01", "00"]
    + ["00"] * 20
    + ["04", "00", "00", "00", "14", "00", "00", "00"]
    + ["00"] * 8
    + ["01", "00", "00", "00"]
    + ["00"] * 20
    + ["4a", "c3", "2c", "fa"]
)


def admin(**dwords):
    """An Admin request with every field zero but those given, by name:
    opcode, ctlid, nsid, cdw2, cdw3, cdw4, cdw5, dofst, dlen, cdw10..cdw15
    (a number or a placeholder text)."""
    get = dwords.get
    return [
        f"Opcode:1={get('opcode', '0x06')}",
        "CFLGS:1=0",
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


# ------------------------------------------------------------------ AC-1


def test_an_mi_command_prints_every_line_in_order(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *HEALTH_POLL)
    assert code == 0, lines
    assert lines[0] == "request bytes: 12"
    assert lines[1] == "message bytes: 20"
    assert lines[2] == MESSAGE + " ".join(HEALTH_POLL_BYTES)
    at = lines.index("offset | size | field | bytes")
    assert all(ln.startswith("note: ") for ln in lines[3:at]), lines
    assert at > 3, lines
    # no tool line for the NVMe-MI command set, and never mctp-client
    assert not any(ln.startswith(("nvme ", "mctp-client")) for ln in lines), lines


def test_an_admin_command_prints_the_passthru_line_before_the_message(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *IDENTIFY)
    assert code == 0, lines
    assert lines[0] == "request bytes: 64"
    assert lines[1] == "message bytes: 72"
    assert lines[2].startswith(PASSTHRU), lines
    assert lines[3] == MESSAGE + " ".join(IDENTIFY_BYTES)
    at = lines.index("offset | size | field | bytes")
    assert all(ln.startswith("note: ") for ln in lines[4:at]), lines
    assert not any("mctp-client" in ln for ln in lines), lines


def test_the_table_counts_from_byte_0_and_ends_with_the_mic(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *HEALTH_POLL)
    assert code == 0, lines
    table = rows(lines)
    assert [row[:2] for row in table] == [
        ["0", "1"],
        ["1", "1"],
        ["2", "1"],
        ["3", "1"],
        ["4", "1"],
        ["5", "3"],
        ["8", "4"],
        ["12", "4"],
        ["16", "4"],
    ]
    assert [row[2] for row in table[4:8]] == ["Opcode", "Reserved", "NMD0", "NMD1"]
    assert table[0][3] == "84" and table[1][3] == "08"
    assert table[-1][2] == "MIC" and table[-1][3] == "aa ef 81 b4"
    # the table holds the message, byte for byte
    assert [t for row in table for t in tokens(row[3])] == message(lines)


def test_the_options_after_the_fields_give_the_same_lines(capsys):
    _, before = run(capsys, "nvme-mi", "--nmimt", "admin", "--csi", "1", *IDENTIFY)
    _, after = run(capsys, "nvme-mi", *IDENTIFY, "--nmimt=admin", "--csi", "1")
    assert before == after


def test_reorder_moves_the_nvme_mi_options_first():
    argv = ["invocation", "nvme-mi", "A:1=0", "--nmimt", "mi", "B:1=0", "--csi=1"]
    assert invocation.reorder_argv(argv) == [
        "invocation",
        "--nmimt",
        "mi",
        "--csi=1",
        "nvme-mi",
        "A:1=0",
        "B:1=0",
    ]


# ------------------------------------------------------------------ AC-2


def test_the_mi_message_is_appendix_c_example_3(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *HEALTH_POLL)
    assert code == 0, lines
    assert message(lines) == HEALTH_POLL_BYTES


def test_the_admin_message_is_appendix_c_example_1(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *IDENTIFY)
    assert code == 0, lines
    assert message(lines) == IDENTIFY_BYTES


@pytest.mark.parametrize(
    ("nmimt", "csi", "byte1"),
    [("mi", None, "08"), ("mi", "1", "09"), ("admin", "0", "10"), ("admin", "1", "11")],
)
def test_byte_1_is_ror_0_nmimt_and_csi(capsys, nmimt, csi, byte1):
    fields = HEALTH_POLL if nmimt == "mi" else IDENTIFY
    argv = ["nvme-mi", "--nmimt", nmimt, *(["--csi", csi] if csi else []), *fields]
    code, lines = run(capsys, *argv)
    assert code == 0, lines
    got = message(lines)
    assert got[:4] == ["84", byte1, "00", "00"]
    body = bytes(int(t, 16) for t in got[:-4])
    assert got[-4:] == [f"{b:02x}" for b in crc32c(body).to_bytes(4, "little")]


def test_crc32c_has_the_check_value_and_appendix_b_rows():
    assert invocation.nvme_mi_crc(b"123456789") == 0xE3069283
    # NVMe-MI 2.2 Appendix B (pp.203-204)
    assert invocation.nvme_mi_crc(bytes(32)) == 0x8A9136AA
    assert invocation.nvme_mi_crc(b"\xff" * 32) == 0x62A8AB43
    assert invocation.nvme_mi_crc(bytes(range(30))) == 0x1E0592D7


def test_the_mic_matches_a_bitwise_crc_for_random_messages(capsys):
    rng = random.Random(53)
    for _ in range(40):
        size = rng.randrange(12, 90)
        data = bytes(rng.randrange(256) for _ in range(size))
        rest = ",".join(f"0x{b:02x}" for b in data[1:])
        fields = ["Opcode:1=0x04", f"Rest:{size - 1}={rest}"]
        code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *fields)
        assert code == 0, lines
        got = message(lines)
        body = bytes([0x84, 0x08, 0, 0, 0x04, *data[1:]])
        assert got[:-4] == [f"{b:02x}" for b in body]
        assert got[-4:] == [f"{b:02x}" for b in crc32c(body).to_bytes(4, "little")]


def test_fields_are_little_endian_unless_marked_be(capsys):
    code, lines = run(
        capsys,
        "nvme-mi",
        "--nmimt",
        "mi",
        "Opcode:1=0",
        "R:3=0",
        "NMD0:4=0x03000000",
        "NMD1:4:be=0x01020304",
    )
    assert code == 0, lines
    assert message(lines)[4:16] == "00 00 00 00 00 00 00 03 01 02 03 04".split()


# ------------------------------------------------------------------ AC-3


def test_a_placeholder_makes_the_mic_four_mic_bytes_with_a_note(capsys):
    fields = ["Opcode:1=0x02", "Reserved:3=0", "NMD0:4=<nmd0>", "NMD1:4=0"]
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *fields)
    assert code == 0, lines
    got = message(lines)
    assert got[8:12] == ["<nmd0 0>", "<nmd0 1>", "<nmd0 2>", "<nmd0 3>"]
    assert got[-4:] == ["<mic>"] * 4
    assert rows(lines)[-1][3] == "<mic> <mic> <mic> <mic>"
    text = notes(lines)
    assert "MIC" in text and "placeholder" in text, text


def test_with_every_value_known_there_is_no_mic_note(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *HEALTH_POLL)
    assert code == 0, lines
    assert "<mic>" not in notes(lines)
    assert "placeholder" not in notes(lines)


# ------------------------------------------------------------------ AC-4


def passthru(lines):
    return one(lines, PASSTHRU)


def test_the_passthru_line_of_appendix_c_example_1(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *IDENTIFY)
    assert code == 0, lines
    assert passthru(lines) == (
        "nvme admin-passthru mctp:<net>,<eid>:1 --opcode=0x06 --cdw10=0x1 "
        "--data-len=0x14"
    )


def test_the_passthru_line_takes_each_non_zero_dword_in_order(capsys):
    fields = admin(
        opcode="0x02",
        ctlid=12,
        nsid="0xffffffff",
        cdw2=2,
        cdw3=3,
        dlen=512,
        cdw10="0x007f0002",
        cdw11=11,
        cdw12=12,
        cdw13=13,
        cdw14=14,
        cdw15=15,
    )
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
    assert code == 0, lines
    assert passthru(lines) == (
        "nvme admin-passthru mctp:<net>,<eid>:12 --opcode=0x02 "
        "--namespace-id=0xffffffff --cdw2=0x2 --cdw3=0x3 --cdw10=0x7f0002 "
        "--cdw11=0xb --cdw12=0xc --cdw13=0xd --cdw14=0xe --cdw15=0xf "
        "--data-len=0x200"
    )


def test_a_zero_request_gives_the_opcode_alone(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *admin(opcode="0x0c"))
    assert code == 0, lines
    assert passthru(lines) == "nvme admin-passthru mctp:<net>,<eid>:0 --opcode=0x0c"


def test_dwords_split_into_fields_are_read_by_offset(capsys):
    # Get Log Page: CDW10 as NUMDL (bits 31:16), RAE, LSP, LID; little-endian
    fields = admin(opcode="0x02", dlen=512)
    at = fields.index("CDW10:4=0")
    fields[at : at + 1] = ["LID:1=0x02", "LSP and RAE:1=0", "NUMDL:2=0x7f"]
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
    assert code == 0, lines
    assert "--cdw10=0x7f0002" in passthru(lines).split()


def test_a_placeholder_dword_prints_as_a_named_placeholder(capsys):
    fields = admin(ctlid="<controller>", nsid="<nsid>", cdw11="<x>", dlen="<len>")
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
    assert code == 0, lines
    line = passthru(lines)
    assert line.startswith("nvme admin-passthru mctp:<net>,<eid>:<ctrl id> "), line
    for option in ("--namespace-id=<nsid>", "--cdw11=<cdw11>", "--data-len=<dlen>"):
        assert option in line.split(), (option, line)


def test_a_placeholder_opcode_prints_as_one(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *admin(opcode="<opcode>"))
    assert code == 0, lines
    assert "--opcode=<opcode>" in passthru(lines).split()


def test_request_data_after_dword_15_is_in_the_message_only(capsys):
    fields = [*admin(opcode="0x09", dlen=4), "Data:4=0x01020304"]
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
    assert code == 0, lines
    assert lines[0] == "request bytes: 68"
    assert message(lines)[68:72] == ["04", "03", "02", "01"]
    assert "Data" not in passthru(lines) and "0x01020304" not in passthru(lines)


# ------------------------------------------------------------------ AC-5


def test_the_mi_note_says_no_bmc_command_sends_it(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *HEALTH_POLL)
    assert code == 0, lines
    text = notes(lines)
    for word in (
        "no command",
        "OpenBMC",
        "mctp-client",
        "IC bit",
        "MIC",
        "nvme-cli",
        "Admin",
        "capture",
        "libnvme",
    ):
        assert word in text, word
    assert "nvme-cli 2.16" not in text


def test_the_admin_notes_name_nvme_cli_and_how_it_reads(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *admin())
    assert code == 0, lines
    text = notes(lines)
    for word in (
        "nvme-cli 2.16",
        "probe",
        "decimal",
        "bits 1..0",
        "stdin",
        "-i <file>",
    ):
        assert word in text, word
    assert "DOFST" not in text  # the fields hold no DOFST or Dword 4-5
    assert "packets" in text  # 4 + 64 + 4 bytes: above the 64-byte baseline


def test_the_admin_notes_say_where_nvme_cli_differs(capsys):
    for fields in (admin(dofst=4), admin(cdw4=1), admin(cdw5="<x>")):
        code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *fields)
        assert code == 0, lines
        text = notes(lines)
        assert "DOFST 0" in text and "Dwords 4-5" in text, (fields, text)


def test_a_message_above_64_bytes_says_mctp_splits_it(capsys):
    _, small = run(capsys, "nvme-mi", "--nmimt", "mi", *HEALTH_POLL)
    assert "packets" not in notes(small)
    big = ["Opcode:1=0", "Reserved:3=0", "NMD0:4=0", "NMD1:4=0", "Data:49=0"]
    _, at65 = run(capsys, "nvme-mi", "--nmimt", "mi", *big)
    assert one(at65, "message bytes:") == "message bytes: 69"
    assert "packets" in notes(at65) and "64" in notes(at65)
    exact = [*big[:-1], "Data:44=0"]
    _, at64 = run(capsys, "nvme-mi", "--nmimt", "mi", *exact)
    assert one(at64, "message bytes:") == "message bytes: 64"
    assert "packets" not in notes(at64)


# ------------------------------------------------------------------ AC-6


@pytest.mark.parametrize(
    ("argv", "word"),
    [
        (["--nmimt", "pcie", *HEALTH_POLL], "PCIe"),
        (["--nmimt", "control", *HEALTH_POLL], "Control Primitives"),
        (["--nmimt", "1", *HEALTH_POLL], "--nmimt"),
        (HEALTH_POLL, "--nmimt"),
        (["--nmimt", "mi", "--csi", "2", *HEALTH_POLL], "--csi"),
        (["--nmimt", "mi", "--csi", "<slot>", *HEALTH_POLL], "--csi"),
        (["--nmimt", "mi", *HEALTH_POLL[:3]], "12"),
        (["--nmimt", "mi"], "12"),
        (["--nmimt", "admin", *HEALTH_POLL], "64"),
        (["--nmimt", "admin", *IDENTIFY[:-1]], "64"),
        (["--nmimt", "mi", *HEALTH_POLL, "Data:4205=0"], "4224"),
        (["--nmimt", "admin", *admin(dlen=4097)], "4096"),
        (["--nmimt", "admin", *admin(opcode="0x03")], "bidirectional"),
        (["--nmimt", "admin", *admin(opcode="0x7f")], "bidirectional"),
        (["--nmimt", "mi", *HEALTH_POLL, "Bad:1=0x100"], "Bad:1=0x100"),
        (["--nmimt", "mi", "--type", "0x15", *HEALTH_POLL], "--type is for nc-si"),
        (["--nmimt", "mi", "--iid", "1", *HEALTH_POLL], "--iid is for nc-si"),
        (["--nmimt", "mi", "--subcommand", "X", *HEALTH_POLL], "--subcommand"),
    ],
)
def test_a_wrong_request_is_refused_with_one_line(capsys, argv, word):
    code, lines = run(capsys, "nvme-mi", *argv)
    assert code == 2, lines
    assert len(lines) == 1, lines
    assert lines[0].startswith("invocation: "), lines
    assert word in lines[0], lines


def test_the_largest_message_and_dlen_are_taken(capsys):
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *HEALTH_POLL, "Data:4204=0")
    assert code == 0, lines
    assert one(lines, "message bytes:") == "message bytes: 4224"
    code, lines = run(capsys, "nvme-mi", "--nmimt", "admin", *admin(dlen=4096))
    assert code == 0, lines
    assert "--data-len=0x1000" in passthru(lines).split()


def test_the_mi_message_takes_any_opcode(capsys):
    # the bidirectional check is nvme-cli's, so the NVMe-MI command set has none
    fields = ["Opcode:1=0x03", "Reserved:3=0", "NMD0:4=0", "NMD1:4=0"]
    code, lines = run(capsys, "nvme-mi", "--nmimt", "mi", *fields)
    assert code == 0, lines


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
    assert lines == [f"invocation: {option} is for nvme-mi, not {protocol}"]


def test_the_five_protocols_print_what_they_did(capsys):
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
    code, lines = run(
        capsys,
        "nc-si",
        "--type",
        "0x15",
        "--package",
        "0",
        "--channel",
        "0",
        "--iid",
        "1",
    )
    assert code == 0, lines
    assert one(lines, "mctp-client").endswith("ff ff ea fe")


def test_the_unknown_protocol_line_names_nvme_mi():
    with pytest.raises(invocation.FieldError) as raised:
        invocation.render("nvme", ["X:1=0"])
    assert str(raised.value) == (
        "unknown protocol 'nvme'; it is one of ipmi, mctp-control, nc-si, "
        "nvme-mi, pldm, spdm"
    )


def test_render_of_nvme_mi_without_its_options_is_refused():
    with pytest.raises(invocation.FieldError) as raised:
        invocation.render("nvme-mi", HEALTH_POLL)
    assert "--nmimt" in str(raised.value)


# ------------------------------------------------------------------ AC-7


def _block():
    text = SKILL.read_text("utf-8")
    start = text.index(START) + len(START)
    return text[start : text.index(END)].strip("\n").splitlines()


def _flat(lines):
    return " ".join(" ".join(lines).split())


def test_the_block_stays_within_its_raised_cap():
    assert len(_block()) <= MAX_LINES, len(_block())


def test_the_block_gives_nvme_mi_an_invocation():
    text = _flat(_block())
    for word in (
        "nvme-cli 2.16",
        "`nvme-mi --nmimt <mi|admin>`",
        "`message:`",
        "`nvme admin-passthru`",
        "MIC",
        "Status",
    ):
        assert word in text, word
    bullet = text[text.index("- NVMe-MI:") : text.index("3. Headers")]
    assert "little-endian" in bullet, bullet
    assert "say so" in bullet, bullet  # no BMC command sends an NVMe-MI command
    # what is left of the other-Families sentence: PCIe and Control Primitives
    assert "Other Families (NVMe-MI)" not in text
    assert re.search(
        r"PCIe Commands and Control Primitives[^.]*no Invocation, no bytes to send;",
        text,
    ), text
    # the one message type mctp-client cannot send right stays out
    assert "type nvme" not in text


def test_the_front_matter_is_develops():
    text = SKILL.read_text("utf-8")
    front = text.split("---")[1]
    assert hashlib.sha256(front.encode()).hexdigest() == FRONT_MATTER_SHA


def test_the_skill_table_row_names_nvme_mi():
    skill = SKILL.read_text("utf-8")
    row = one(skill.splitlines(), "| `invocation ")
    for word in ("nvme-mi", "--nmimt", "MIC", "Admin"):
        assert word in row, word


# ------------------------------------------------------------------ AC-8


def test_commands_doc_describes_nvme_mi():
    doc = " ".join(COMMANDS_DOC.read_text("utf-8").split())
    for word in (
        "`invocation nvme-mi --nmimt",
        "--csi",
        "request bytes: N",
        "message bytes: M",
        "`message:`",
        "nvme admin-passthru mctp:<net>,<eid>:",
        "CRC-32C",
        "`<mic>`",
        "4224",
        "4096",
        "bidirectional",
        "is for nvme-mi",
    ):
        assert word in doc, word


def test_readme_names_nvme_cli_and_keeps_within_its_cap():
    text = README.read_text("utf-8")
    assert len(text.splitlines()) <= 200
    start = text.index("## How a question is answered")
    section = " ".join(text[start : text.index("\n## ", start + 1)].split())
    assert "NVMe-MI" in section and "`nvme admin-passthru`" in section
    assert "other Families (NVMe-MI) get none" not in section

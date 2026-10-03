"""The Command workflow block of SKILL.md: removable in one cut, kept short,
and holding only the rules for writing an Invocation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
README = ROOT / "README.md"

START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
MAX_LINES = 32


def block_lines():
    lines = SKILL.read_text("utf-8").splitlines()
    assert lines.count(START) == 1
    assert lines.count(END) == 1
    first, last = lines.index(START), lines.index(END)
    assert first < last
    return lines[first + 1 : last]


def block_text():
    """The block as one line, so a phrase is found across a line break."""
    return " ".join(" ".join(block_lines()).split())


def test_block_sits_between_its_markers_and_holds_the_workflow():
    body = "\n".join(block_lines())
    assert "## Command workflow" in body
    for term in ("**Command**", "**Raw Request**", "**Invocation**"):
        assert term in block_text(), term


def test_block_stays_within_its_line_budget():
    assert len(block_lines()) <= MAX_LINES


def test_block_gives_the_syntax_of_each_tool():
    text = block_text()
    for rule in (
        "`ipmitool raw 0x<netfn> 0x<cmd> 0x<byte> ...`",
        "`mctp-client eid <eid> type <control|pldm|spdm> data <bytes>`",
        "`pldmtool raw -m <eid> -d 0x<byte> ...`",
        "no connection options",
        "`<name>` placeholder",
    ):
        assert rule in text, rule


def test_block_gives_the_header_rules():
    text = block_text()
    assert "starts with `80` (Rq=1, D=0, instance id 0)" in text
    # the SPDM version byte: fixed for GET_VERSION, a placeholder otherwise,
    # and never taken from the Version of the Document that was read
    assert "GET_VERSION" in text
    assert "`<negotiated version>`" in text
    assert "Version of the Document" in text


def test_block_makes_the_answer_count_the_bytes():
    text = block_text()
    assert "count" in text
    assert "sum of its field sizes" in text
    assert "total" in text


def test_block_names_the_tool_versions_it_was_checked_against():
    text = block_text()
    for version in ("ipmitool be11d948", "mctp v2.5", "pldm b0e6c54e"):
        assert version in text, version
    assert "another tool version may differ" in text


def test_block_holds_no_rule_for_a_pasted_response():
    text = block_text()
    for gone in (
        "Decode",
        "decode",
        "pastes",
        "Unable to send RAW command",
        "Rx:",
        "completion code",
        "rewrites the instance id",
        "Raw Response",
    ):
        assert gone not in text, gone


def test_description_names_the_tools_the_workflow_writes_for():
    head = SKILL.read_text("utf-8").split("\n---\n", 1)[0]
    description = next(
        line for line in head.splitlines() if line.startswith("description:")
    )
    for tool in ("ipmitool raw", "mctp-client", "pldmtool raw"):
        assert tool in description


def test_readme_says_what_can_be_asked_and_that_nothing_ran_on_hardware():
    text = README.read_text("utf-8")
    start = text.index("## How a question is answered")
    section = " ".join(text[start : text.index("\n## ", start + 1)].split())
    for tool in ("`ipmitool raw`", "`mctp-client`", "`pldmtool raw`"):
        assert tool in section, tool
    for family in ("IPMI", "MCTP control", "PLDM", "SPDM"):
        assert family in section, family
    assert "placeholder" in section
    assert "run against hardware or QEMU" in section

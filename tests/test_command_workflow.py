"""The Command workflow block of SKILL.md: removable in one cut, kept short,
and holding only the rules for writing an Invocation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
README = ROOT / "README.md"

START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
# 32 until the OEM sentence and step 4's own-call and `0x` clause (T33);
# 34 until what `ipmitool raw` prints and the other Families (T34)
MAX_LINES = 37


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


def test_block_has_the_helper_lay_out_the_bytes():
    # the step that had the Session count the bytes itself is gone: the
    # helper arranges them and counts them
    text = block_text()
    form = "`invocation <ipmi|mctp-control|pldm|spdm> '<field>:<size>=<value>' ...`"
    assert form in text
    assert "every field in order, the header and codes too" in text
    assert "Never write bytes by hand" in text
    assert "copy the line(s) and total it prints" in text
    assert "sum of its field sizes" not in text


def test_only_the_helper_writes_bytes():
    # step 1 once said "Lay out every byte" while step 4 said never to
    text = block_text()
    assert "Lay out every byte" not in text
    assert "Work out every field for step 4" in text


def test_a_placeholder_takes_no_0x():
    # the helper prints `<sensor number>`; a run once wrote `0x<sensor number>`
    assert "(a placeholder takes no `0x`)" in block_text()


def test_invocation_runs_as_a_bash_call_of_its_own():
    # a compound command is refused by the Bash permission rule and retried
    assert "as a Bash call of its own (no `;`, `&&`, `|`)" in block_text()


def test_an_oem_command_without_a_document_gets_no_invocation():
    text = block_text()
    assert "An OEM Command no Library Document defines: no Invocation; say why." in text


def test_block_says_what_ipmitool_raw_prints():
    # answers called the completion code the first byte the user sees;
    # ipmitool strips it on success and prints only an error otherwise
    text = block_text()
    sentence = (
        "ipmitool raw prints the data after the completion code (the "
        "response table's byte 2 first); a non-zero code prints an error "
        "ending `rsp=0x<code>`, no data."
    )
    assert sentence in text
    for word in ("decode", "paste"):
        assert word not in sentence


def test_other_families_get_no_invocation_and_no_bytes():
    # NC-SI and NVMe-MI runs gave hand-laid packets and self-computed CRCs
    text = block_text()
    assert (
        "Other Families (NC-SI, NVMe-MI): no Invocation, no bytes to send; "
        "cite the layout, say why." in text
    )
    # the OEM rule keeps its sentence
    assert "An OEM Command no Library Document defines: no Invocation; say why." in text


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
        # "completion code" left this list in T34: the IPMI bullet says what
        # ipmitool raw prints for the encode answer, which is not decoding
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


def test_frontmatter_values_are_valid_yaml_scalars():
    """A plain (unquoted) YAML scalar may hold neither `: ` nor ` #`; the
    description's "means: the bytes" needs the value quoted."""
    for skill in sorted((ROOT / "skills").glob("*/SKILL.md")):
        head = skill.read_text("utf-8").split("\n---\n", 1)[0]
        for line in head.splitlines()[1:]:
            key, _, value = line.partition(": ")
            if value.startswith('"'):
                assert value.endswith('"'), (skill.parent.name, key)
                assert '"' not in value[1:-1] and "\\" not in value, key
            else:
                assert ": " not in value and " #" not in value, (
                    skill.parent.name,
                    key,
                )


def test_readme_says_what_can_be_asked_and_that_nothing_ran_on_hardware():
    text = README.read_text("utf-8")
    start = text.index("## How a question is answered")
    section = " ".join(text[start : text.index("\n## ", start + 1)].split())
    for tool in ("`ipmitool raw`", "`mctp-client`", "`pldmtool raw`"):
        assert tool in section, tool
    for family in ("IPMI", "MCTP control", "PLDM", "SPDM"):
        assert family in section, family
    assert "placeholder" in section
    assert "other Families (NC-SI, NVMe-MI) get none" in section
    assert "check them against the cited layout" in section
    assert "run against hardware or QEMU" in section

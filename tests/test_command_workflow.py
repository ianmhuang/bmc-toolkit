"""The Command workflow block of SKILL.md: removable in one cut, kept short,
and holding only the rules for writing an Invocation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
README = ROOT / "README.md"

START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
# 32 until the OEM sentence and step 4's own-call and `0x` clause (T33);
# 34 until what `ipmitool raw` prints and the other Families (T34);
# 37 until no bytes from memory (T36);
# 38 until the SPDM layout follows its Document Version (T39);
# 40 until the PLDM header's Type byte (T41);
# 42 until every Invocation line comes from `invocation` (T43);
# 44 until the pldmtool subcommand from `invocation --subcommand` (T46)
MAX_LINES = 52  # 46 until T52 (NC-SI Invocation)


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


def test_pldm_answers_copy_the_subcommand_line_the_helper_prints():
    # T46: pldmtool has a subcommand for many PLDM Commands; T45 had the
    # Session look it up itself and it skipped the lookup in 11 of 42 runs,
    # so `invocation --subcommand` now reads the held openbmc/pldm tree and
    # prints the line, and the answer copies it as it copies the raw lines
    text = block_text()
    bullet = text[text.index("- MCTP control, PLDM, SPDM:") :]
    bullet = bullet[: bullet.index("3. ")]
    raw_form = "`pldmtool raw -m <eid> -d 0x<byte> ...`"
    # the `note:` line names the tree the spellings came from and the
    # `--help` check: the target's pldmtool may be another version
    rule = (
        "PLDM: add `--subcommand <Name>` to the helper call of step 4; copy its "
        "`subcommand:` and `note:` lines, values filled, with cite; `none`: raw only."
    )
    assert raw_form in bullet and rule in bullet
    assert bullet.index(raw_form) < bullet.index(rule)
    # the lookup is the helper's, not a grep the Session runs
    assert "grep pldm" not in text


def test_block_gives_the_header_rules():
    text = block_text()
    assert "starts with `80` (Rq=1, D=0, instance id 0)" in text
    # the SPDM version byte: fixed for GET_VERSION, a placeholder otherwise,
    # and never taken from the Version of the Document that was read
    assert "GET_VERSION" in text
    assert "`<negotiated version>`" in text
    assert "Version of the Document" in text


def test_block_says_which_type_a_pldm_header_carries():
    # T41: asked for GetPLDMVersion of type 2, answers wrote the 2 into the
    # header's Type byte as well as into the request's PLDMType field
    text = block_text()
    after = text[text.index("instance id 0); say so.") :][:260]
    assert "PLDM byte 1 is the Type whose Document defines the Command" in after
    assert "DSP0240's base Commands: `00`" in after
    assert "not a Type asked about, which is a request field" in after


def test_spdm_layout_follows_its_document_version():
    # an older negotiated version lays some requests out differently
    # (GET_CAPABILITIES 12 bytes in 1.1, the GET_MEASUREMENTS Context from 1.3)
    text = block_text()
    version = (
        "in every other request `<negotiated version>` unless the user names "
        "one, never the Version of the Document the layout came from."
    )
    rule = (
        "The layout is that Document Version's: say so, and that an older "
        "negotiated version can differ. If the user names one: use that Version "
        "(`--version`)."
    )
    assert version + " " + rule in text
    # the reading command brings a named version to Ready; no `fetch` first
    assert "`fetch`" not in text
    # it stays in step 3, before the `invocation` step
    assert text.index(rule) < text.index("4. Run `invocation")


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


def test_every_invocation_line_comes_from_the_helper():
    # T43: the line asked for was copied from `invocation`, then a filled-in
    # example (`ipmitool raw 0x04 0x2d 0x30`) or a follow-up Command the
    # user did not ask for was written by hand, marked as inference
    text = block_text()
    after = text[text.index("Never write bytes by hand") :]
    rule = (
        "That holds for every Invocation line the answer writes, an example "
        "with a value filled in or a Command not asked for: no call, no line; "
        "name the Command instead."
    )
    assert rule in after
    # it closes step 4, before the block ends
    assert "5." not in after[after.index(rule) :]


def test_only_the_helper_writes_bytes():
    # step 1 once said "Lay out every byte" while step 4 said never to
    text = block_text()
    assert "Lay out every byte" not in text
    assert "Work out every field for step 4" in text


def test_the_printed_placeholder_is_copied_as_it_is():
    # T33 told the answer to drop the 0x the helper did not print; runs
    # added it anyway. Since T40 the helper prints `0x<sensor number>` in
    # the ipmitool and pldmtool lines, and the answer copies the line.
    text = block_text()
    assert "placeholder takes no `0x`" not in text
    assert "copy the line(s) and total it prints." in text


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
        "line with `rsp=0x<code>`, no data."
    )
    assert sentence in text
    # the IPMI bullet as the file holds it, up to the next bullet or step
    lines = block_lines()
    first = next(i for i, ln in enumerate(lines) if ln.startswith("   - IPMI:"))
    last = next(
        i
        for i in range(first + 1, len(lines))
        if lines[i].startswith("   - ") or lines[i][:1].isdigit()
    )
    bullet = " ".join(" ".join(lines[first:last]).split()).lower()
    assert "prints the data after the completion code" in bullet
    for word in ("decode", "paste"):
        assert word not in bullet, word


def test_other_families_get_no_invocation_and_no_bytes():
    # NC-SI and NVMe-MI runs gave hand-laid packets and self-computed CRCs
    text = block_text()
    assert (
        "Other Families (NVMe-MI): no Invocation, no bytes to send; "
        "cite the layout, say why." in text
    )
    # the OEM rule keeps its sentence
    assert "An OEM Command no Library Document defines: no Invocation; say why." in text


def test_neither_answer_writes_bytes_from_memory():
    # O2 runs refused the Invocation but still wrote the Dell bytes they
    # remembered, hedged as community-known or as a `repos --search` string
    text = block_text()
    family = (
        "Other Families (NVMe-MI): no Invocation, no bytes to send; "
        "cite the layout, say why."
    )
    rule = "Neither answer writes bytes from memory, even hedged or as a search term."
    assert family + " " + rule in text


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
    # NC-SI got an Invocation in T52
    assert "other Families (NVMe-MI) get none" in section
    assert "check them against the cited layout" in section
    assert "run against hardware or QEMU" in section

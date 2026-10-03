"""Reviewer acceptance tests for the Command workflow block of SKILL.md
(AC-1 to AC-9 and the skills/ half of AC-11).

The block is the feature: rules a Session follows when asked for a named
Command. These tests read SKILL.md the way a Session gets it and check the
shape of the rules the acceptance criteria name: the markers and the line
cap, the three tool forms token by token, the header and SPDM version
rules, the byte count, the absence of rules for a pasted response, and
that nothing outside the markers depends on the block.

Every test locates the block through its markers (or reads the tool names
from the description), so each one fails on develop, where neither exists.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"

START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
MAX_LINES = 32

HEX_BYTE = re.compile(r"0x(<[a-z ]+>|[0-9a-fA-F]{1,2})")


def _parts() -> tuple[list[str], list[str], list[str]]:
    """(lines before the start marker, block body, lines after the end marker)."""
    lines = SKILL.read_text("utf-8").splitlines()
    assert lines.count(START) == 1, "start marker: one whole line, exactly once"
    assert lines.count(END) == 1, "end marker: one whole line, exactly once"
    first, last = lines.index(START), lines.index(END)
    assert first < last
    return lines[:first], lines[first + 1 : last], lines[last + 1 :]


def _block() -> str:
    """The block on one line, so a rule is found across a line break."""
    return " ".join(" ".join(_parts()[1]).split())


def _spans() -> list[str]:
    """Every `code span` of the block."""
    return re.findall(r"`([^`]+)`", _block())


def _forms(tool: str) -> list[list[str]]:
    """The code spans that start with the tool's name, split into tokens."""
    forms = [span.split() for span in _spans() if span.split()[0] == tool]
    assert forms, f"the block gives no `{tool} ...` form"
    return forms


def _description() -> str:
    text = SKILL.read_text("utf-8")
    assert text.startswith("---\n")
    head = text[4:].split("\n---\n", 1)[0]
    found = [ln for ln in head.splitlines() if ln.startswith("description:")]
    assert len(found) == 1, found
    return found[0]


# ------------------------------------------------------------------ AC-1


def test_one_block_between_the_markers_within_the_line_cap():
    _, body, _ = _parts()
    assert any(ln.strip() for ln in body), "empty block"
    assert len(body) <= MAX_LINES, len(body)
    headings = [ln for ln in body if ln.startswith("#")]
    assert len(headings) == 1, headings
    assert headings[0].startswith("## ") and "Command" in headings[0]


def test_block_defines_the_terms_it_uses():
    text = _block()
    for term in ("**Command**", "**Raw Request**", "**Invocation**"):
        assert term in text, term


# ------------------------------------------------------------------ AC-2


def test_block_says_what_an_answer_holds():
    text = _block()
    low = text.lower()
    assert re.search(r"every (request )?byte", low), "what every byte is"
    assert "document version" in low, "the Version the definition came from"
    assert "cite:" in _spans(), "Citations come from the cite: lines"
    assert re.search(r"sentence on the response|response carries", low)
    # the Invocation line itself is not where a Citation goes
    assert re.search(r"invocations? carr(y|ies) no citation", low)
    # a name two Families share: the family rule, and the other one is named
    assert "famil" in low and "other" in low


# ------------------------------------------------------------------ AC-3


def test_ipmitool_form_has_raw_first_and_every_number_prefixed():
    for tokens in _forms("ipmitool"):
        assert tokens[1] == "raw", f"something stands before raw: {tokens}"
        numbers = [t.strip("[]") for t in tokens[2:] if t.strip("[]") != "..."]
        assert len(numbers) >= 2, tokens
        assert "netfn" in numbers[0].lower() and "cmd" in numbers[1].lower()
        for number in numbers:
            assert not number.startswith("-"), f"an option in the form: {tokens}"
            assert HEX_BYTE.fullmatch(number), f"not 0x-prefixed: {number}"


def test_block_rules_out_connection_options_and_names_the_placeholder():
    low = _block().lower()
    for option in ("interface", "host", "password", "bridging"):
        assert option in low, option
    assert "<name>" in _spans()
    assert "placeholder" in low


# ------------------------------------------------------------------ AC-4


def test_mctp_client_form_is_eid_type_data_with_data_last():
    for tokens in _forms("mctp-client"):
        keywords = [tokens.index(k) for k in ("eid", "type", "data")]
        assert keywords == sorted(keywords), tokens
        assert tokens[-2] == "data", f"data is not the last keyword: {tokens}"
        types = tokens[tokens.index("type") + 1].strip("<>").split("|")
        assert {"control", "pldm", "spdm"} <= set(types), types
        assert not any(t.startswith("0x") for t in tokens), tokens
    low = _block().lower()
    assert "two hex digits" in low
    assert "space separated" in low
    # the message type is the type argument, not a data byte
    assert re.search(r"never a byte in `?data`?", low)


def test_pldmtool_form_takes_the_eid_and_prefixed_bytes():
    for tokens in _forms("pldmtool"):
        assert tokens[1] == "raw", tokens
        assert tokens[tokens.index("-m") + 1] == "<eid>", tokens
        first_byte = tokens[tokens.index("-d") + 1]
        assert HEX_BYTE.fullmatch(first_byte), first_byte
    assert "header included" in _block().lower()


def test_request_header_default_is_80_and_the_answer_says_so():
    text = _block()
    assert "80" in _spans()
    assert re.search(r"Rq\s*=\s*1", text)
    assert re.search(r"\bD\s*=\s*0", text)
    assert re.search(r"instance id 0\b", text, re.I)
    assert "say so" in text.lower()


# ------------------------------------------------------------------ AC-5


def test_spdm_version_byte_is_a_placeholder_except_for_get_version():
    text = _block()
    assert "GET_VERSION" in text
    assert "<negotiated version>" in _spans()
    assert text.index("GET_VERSION") < text.index("<negotiated version>")
    after = text[text.index("<negotiated version>") :][:200]
    assert "unless the user names" in after
    # the Version of the Document that was read is not the byte's value
    assert re.search(r"\b(never|not)\b[^.]*\bDocument\b", after), after


# ------------------------------------------------------------------ AC-6


def test_block_counts_the_bytes_against_the_layout_and_states_the_total():
    low = _block().lower()
    assert re.search(r"\bcount\b[^.]*\blayout\b", low)
    assert "field sizes" in low
    assert re.search(r"state the total", low)
    # the count comes before the answer is given
    assert "before answering" in low


# ------------------------------------------------------------------ AC-7


def test_block_has_no_rule_for_a_pasted_response():
    low = _block().lower()
    for gone in (
        "decode",
        "pasted",
        "pastes",
        "raw response",
        "unable to send raw command",
        "rx:",
        "mctp-client output",
        "`mctp-client` output",
        "rewrites the instance id",
        "completion code",
    ):
        assert gone not in low, gone
    # the numbered steps are about the request only
    steps = [ln for ln in _parts()[1] if re.match(r"\d+\. ", ln)]
    assert steps and not any("response" in ln.lower().split(":")[0] for ln in steps)


# ------------------------------------------------------------------ AC-8


def test_block_names_the_tool_versions_and_says_others_may_differ():
    text = _block()
    assert re.search(r"ipmitool be11d948\b", text)
    assert re.search(r"CodeConstruct/mctp v2\.5\b", text)
    assert re.search(r"openbmc/pldm b0e6c54e\b", text)
    assert "another tool version may differ" in text


# ------------------------------------------------------------------ AC-9


def test_description_names_the_three_tools():
    description = _description()
    for tool in ("ipmitool raw", "mctp-client", "pldmtool raw"):
        assert tool in description, tool


# ----------------------------------------------------------- AC-1, AC-11


def test_nothing_outside_the_block_depends_on_it():
    """Removal check, the skills/ half: with the block and the description
    sentence gone, SKILL.md must not be left naming the tools or the terms."""
    before, _, after = _parts()
    body_start = before.index("---", 1) + 1  # past the frontmatter
    outside = "\n".join(before[body_start:] + after)
    for word in (
        "ipmitool",
        "pldmtool",
        "mctp-client",
        "Invocation",
        "Raw Request",
        "Command workflow",
        "command-workflow",
    ):
        assert word not in outside, word
    # the block is cut out between blank lines, so removal leaves no gap
    assert before[-1] == "" and after[0] == ""

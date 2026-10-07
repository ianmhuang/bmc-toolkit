"""Reviewer acceptance tests for the T33 rewording of the Command workflow
block of SKILL.md (AC-1 to AC-5).

The block is the feature: the rules a Session follows when asked for a named
Command. These tests read it the way a Session gets it and check the shape
of each rule the acceptance criteria name, not the author's exact words:
step 1 works out fields and leaves byte writing to the helper, a placeholder
carries no `0x`, `invocation` runs as a Bash call of its own, an OEM Command
without a Document gets no Invocation, and the block stays within its cap.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"

START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
MAX_LINES = 34


def _body() -> list[str]:
    lines = SKILL.read_text("utf-8").splitlines()
    assert lines.count(START) == 1 and lines.count(END) == 1
    first, last = lines.index(START), lines.index(END)
    assert first < last
    return lines[first + 1 : last]


def _flat(lines: list[str]) -> str:
    """Lines joined into one, so a phrase is found across a line break."""
    return " ".join(" ".join(lines).split())


def _steps() -> dict[int, str]:
    """The numbered steps, each flattened with its continuation lines."""
    steps: dict[int, str] = {}
    current = None
    for line in _body():
        match = re.match(r"(\d+)\. ", line)
        if match:
            current = int(match.group(1))
            steps[current] = line
        elif current is not None and line.startswith("   "):
            steps[current] += " " + line
    assert steps, "no numbered steps in the block"
    return {n: _flat([text]) for n, text in steps.items()}


def _spans(text: str) -> list[str]:
    return re.findall(r"`([^`]+)`", text)


def _invocation_step() -> str:
    """The step that gives the `invocation ...` form."""
    found = [
        text
        for text in _steps().values()
        if any(span.split()[0] == "invocation" for span in _spans(text))
    ]
    assert len(found) == 1, found
    return found[0]


# ------------------------------------------------------------------ AC-1


def test_step_1_works_out_fields_and_leaves_the_bytes_to_the_helper():
    steps = _steps()
    first = steps[1]
    low = first.lower()
    # the Session no longer lays bytes out itself
    assert not re.search(r"lay out", low), first
    assert not re.search(r"write[s]? (every |the |each )?bytes?", low), first
    # it works out each field, with its endianness and placeholder rule,
    # for the helper call
    assert re.search(r"work out every field|work out each field", low), first
    assert "little-endian" in low, first
    assert "`<name>`" in first and "placeholder" in low, first
    assert re.search(r"for step 4|for `?invocation`?", low), first


def test_only_the_helper_step_speaks_of_writing_bytes():
    writers = [
        n
        for n, text in _steps().items()
        if re.search(r"\b(lay out|write|writing)\b[^.]*\bbytes?\b", text.lower())
    ]
    helper = _invocation_step()
    assert writers == [n for n, t in _steps().items() if t == helper], writers
    assert re.search(r"never write bytes by hand", helper.lower()), helper


# ------------------------------------------------------------------ AC-2


def test_a_placeholder_carries_no_0x_prefix():
    low = _flat(_body()).lower()
    assert re.search(
        r"placeholder[^.()]*\bno `0x`|\bno `0x`[^.()]*placeholder", low
    ), low
    # the rule sits with the helper step, where the bytes are copied from
    assert re.search(r"placeholder[^.]*no `0x`", _invocation_step().lower())


def test_block_does_not_ask_for_per_byte_placeholders_one_by_one():
    low = _flat(_body()).lower()
    for phrase in ("one by one", "byte by byte", "each byte of", "each placeholder"):
        assert phrase not in low, phrase


# ------------------------------------------------------------------ AC-3


def test_invocation_runs_as_a_bash_call_of_its_own():
    step = _invocation_step()
    low = step.lower()
    assert re.search(
        r"(bash )?(call|command) of its own|on its own|alone|by itself", low
    ), step
    spans = _spans(step)
    for joiner in (";", "&&", "|"):
        assert joiner in spans, f"{joiner!r} is not named as a joiner: {spans}"
    assert re.search(r"\bno\b[^.]*`;`", low), step


# ------------------------------------------------------------------ AC-4


def test_an_oem_command_without_a_document_gets_no_invocation_and_a_reason():
    low = _flat(_body()).lower()
    sentence = re.search(r"[^.]*\boem command\b[^.]*\.", low)
    assert sentence, "the block has no OEM Command rule"
    text = sentence.group(0)
    assert "document" in text, text
    assert re.search(r"\bno invocation\b", text), text
    assert re.search(r"\bwhy\b", text), text
    # the rule is about a Command no Document in the Library defines
    assert re.search(r"\b(no|without)\b[^.]*\bdocument\b", text), text


# ------------------------------------------------------------------ AC-5


def test_block_stays_within_its_raised_cap_and_keeps_the_prior_rules():
    body = _body()
    assert len(body) <= MAX_LINES, len(body)
    text = _flat(body)
    # the rules the earlier pins named are still there
    for kept in (
        "`<name>` placeholder",
        "no connection options",
        "every field in order, the header and codes too",
        "Never write bytes by hand",
        "copy the line(s) and total it prints",
        "another tool version may differ",
    ):
        assert kept in text, kept

"""Reviewer acceptance tests for the T34 change to the Command workflow block
of SKILL.md (AC-1 to AC-4).

The block is the feature: the rules a Session follows when asked for a named
Command. These tests read it the way a Session gets it and check the shape
of the two new rules, not the author's exact words: the IPMI bullet says what
`ipmitool raw` prints (data after the completion code, an error line with the
code and no data otherwise) without turning into a decode rule, a Command of
a Family outside the four gets no Invocation and keeps the OEM rule intact,
and the block stays within its raised cap with the decode guards still in
place.

Every test requires one of the new sentences, so each one fails on develop,
where neither exists.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"

START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
MAX_LINES = 37  # AC-3: 34 until T34


def _body() -> list[str]:
    lines = SKILL.read_text("utf-8").splitlines()
    assert lines.count(START) == 1 and lines.count(END) == 1
    first, last = lines.index(START), lines.index(END)
    assert first < last
    return lines[first + 1 : last]


def _flat(lines: list[str]) -> str:
    """Lines joined into one, so a phrase is found across a line break."""
    return " ".join(" ".join(lines).split())


def _spans(text: str) -> list[str]:
    return re.findall(r"`([^`]+)`", text)


def _intro() -> str:
    """The paragraph(s) before the first numbered step, flattened."""
    body = _body()
    first_step = next(i for i, ln in enumerate(body) if re.match(r"\d+\. ", ln))
    return _flat(body[:first_step])


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


def _ipmi_bullet() -> str:
    """The `- IPMI:` bullet of the Invocations step with its continuation
    lines, up to the next bullet, step or blank line."""
    body = _body()
    starts = [i for i, ln in enumerate(body) if re.match(r"\s*- IPMI:", ln)]
    assert len(starts) == 1, starts
    bullet = [body[starts[0]]]
    for line in body[starts[0] + 1 :]:
        if not line.strip() or re.match(r"\s*- ", line) or re.match(r"\d+\. ", line):
            break
        bullet.append(line)
    return _flat(bullet)


def _sentence_with(text: str, word: str) -> str:
    """The sentence of `text` (lower-cased) that holds `word`."""
    low = text.lower()
    found = re.search(r"[^.]*\b" + re.escape(word) + r"\b[^.]*\.", low)
    assert found, f"no sentence holds {word!r}: {low}"
    return found.group(0)


# ------------------------------------------------------------------ AC-1


def test_ipmi_bullet_says_what_ipmitool_raw_prints_on_success():
    bullet = _ipmi_bullet()
    low = bullet.lower()
    # the sentence is about what the tool prints, in the IPMI bullet itself
    assert re.search(r"ipmitool raw[^.;]*\bprints?\b", low), bullet
    printed = _sentence_with(bullet, "prints")
    # the completion code is named, and the data is what follows it
    assert "completion code" in printed, printed
    assert re.search(r"\bdata\b[^.;]*\bafter\b[^.;]*completion code", printed), printed
    # the first printed byte is the response table's byte 2
    assert re.search(r"response table[^.;]*byte 2", printed), printed


def test_ipmi_bullet_says_a_non_zero_code_prints_an_error_and_no_data():
    bullet = _ipmi_bullet()
    low = bullet.lower()
    assert re.search(r"non-?zero\b[^.]*\bcode\b", low), bullet
    assert re.search(r"\berror\b", low), bullet
    # the code appears in the error line as rsp=0x<code>
    spans = _spans(bullet)
    assert any(re.fullmatch(r"rsp=0x<[a-z ]+>", span) for span in spans), spans
    assert re.search(r"\bno data\b", low), bullet


def test_ipmi_output_sentence_is_not_a_decode_rule():
    bullet = _ipmi_bullet()
    low = bullet.lower()
    assert "prints" in low, bullet  # the sentence is there (fails on develop)
    for word in ("decode", "decoding", "paste", "pasted", "pastes", "rx:"):
        assert word not in low, word
    # the numbered steps are still about the request only
    steps = _steps()
    assert not any("response" in text.split(":")[0].lower() for text in steps.values())


# ------------------------------------------------------------------ AC-2


def test_other_families_get_no_invocation_and_the_layout_with_a_reason():
    intro = _intro()
    sentence = _sentence_with(intro, "nc-si")
    assert "nvme-mi" in sentence, sentence
    assert re.search(r"\bno invocation\b", sentence), sentence
    assert "layout" in sentence, sentence
    assert re.search(r"\bcite\b|\bcitation", sentence), sentence
    assert re.search(r"\bwhy\b", sentence), sentence
    # the rule is not an Invocation form for these Families
    for span in _spans(intro):
        assert not span.startswith(("ipmitool", "mctp-client", "pldmtool")), span


def test_other_families_rule_sits_with_the_oem_rule_which_keeps_its_meaning():
    intro = _intro()
    low = intro.lower()
    oem = re.search(r"[^.]*\boem command\b[^.]*\.", low)
    other = re.search(r"[^.]*\bnc-si\b[^.]*\.", low)
    assert oem and other, low
    # one sentence, or the two sentences next to each other
    if oem.span() != other.span():
        between = low[oem.end() : other.start()] or low[other.end() : oem.start()]
        assert between.strip() == "", (oem.group(0), other.group(0))
    # the OEM rule: a Command no Document defines, no Invocation, say why
    text = oem.group(0)
    assert re.search(r"\b(no|without)\b[^.]*\bdocument\b", text), text
    assert re.search(r"\bno invocation\b", text), text
    assert re.search(r"\bwhy\b", text), text


# ------------------------------------------------------------------ AC-3, AC-4


def test_block_stays_within_its_raised_cap_and_keeps_the_decode_guards():
    body = _body()
    assert len(body) <= MAX_LINES, len(body)
    low = _flat(body).lower()
    # both new rules are in (so this fails on develop)
    assert "nc-si" in low and "nvme-mi" in low, low
    assert re.search(r"ipmitool raw[^.;]*\bprints?\b", low), low
    # every decode guard but "completion code" still holds
    for gone in (
        "decode",
        "pasted",
        "pastes",
        "raw response",
        "unable to send raw command",
        "rx:",
        "mctp-client output",
        "rewrites the instance id",
    ):
        assert gone not in low, gone
    # the earlier rules are still there
    for kept in (
        "`<name>` placeholder",
        "no connection options",
        "Never write bytes by hand",
        "copy the line(s) and total it prints",
        "another tool version may differ",
    ):
        assert kept in _flat(body), kept

"""Reviewer acceptance tests for T36: the Command workflow block says that an
answer for an OEM Command no Document defines, or for a Command of a Family
outside the four, writes no bytes from memory (AC-1 to AC-3).

The block is the feature, so the tests read SKILL.md the way a Session gets
it and check the shape of the rule, not one wording: a sentence of the intro
(before step 1) that names memory and says no bytes, placed right after the
other-Families sentence, that also rules out the two forms the O2 runs used
(a hedged byte sequence, a search term). AC-2 is the raised cap with the
rule inside it; AC-3 is the author's own test, which must exist and pass.

Every test needs the memory sentence in the intro, which develop's block
does not hold, so each one fails on develop.
"""

import importlib.util
import inspect
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
AUTHOR_TESTS = ROOT / "tests" / "test_command_workflow.py"

START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
MAX_LINES = 46  # AC-2: 37 until T36; 38 until T39; 40 until T41; 42 until T43; 44 until T46

HEX_BYTE = re.compile(r"\b0x[0-9a-fA-F]{1,2}\b")


def _body() -> list[str]:
    lines = SKILL.read_text("utf-8").splitlines()
    assert lines.count(START) == 1, "start marker: one whole line, exactly once"
    assert lines.count(END) == 1, "end marker: one whole line, exactly once"
    first, last = lines.index(START), lines.index(END)
    assert first < last
    return lines[first + 1 : last]


def _flat(lines: list[str]) -> str:
    return " ".join(" ".join(lines).split())


def _intro() -> str:
    """The paragraph(s) before the first numbered step, flattened."""
    body = _body()
    first_step = next(i for i, ln in enumerate(body) if re.match(r"\d+\. ", ln))
    return _flat(body[:first_step])


def _sentences(text: str) -> list[str]:
    """The sentences of `text`, lower-cased, each with its full stop."""
    return [s.strip() for s in re.findall(r"[^.]*\.", text.lower())]


def _memory_sentence() -> str:
    found = [s for s in _sentences(_intro()) if re.search(r"\bmemory\b", s)]
    assert found, "the intro has no sentence about memory"
    assert len(found) == 1, found
    return found[0]


# ------------------------------------------------------------------ AC-1


def test_intro_rules_out_bytes_from_memory():
    sentence = _memory_sentence()
    assert re.search(r"\bbytes?\b", sentence), sentence
    # a negation: neither/no/never/not ... bytes ... from memory
    assert re.search(r"\b(neither|no|never|not)\b", sentence), sentence
    assert re.search(r"\bfrom memory\b", sentence), sentence
    # the rule is a rule, not a byte sequence of its own
    assert not HEX_BYTE.search(sentence), sentence


def test_memory_rule_covers_hedged_bytes_and_search_terms():
    # the O2 slips: bytes hedged as community-known, or printed as a
    # `repos --search` string; both forms are named by the rule
    sentence = _memory_sentence()
    assert re.search(r"\bhedg(ed|ing)?\b", sentence), sentence
    assert re.search(r"\bsearch\b", sentence), sentence


def test_memory_rule_follows_the_other_families_sentence():
    sentences = _sentences(_intro())
    family = [i for i, s in enumerate(sentences) if "nc-si" in s and "nvme-mi" in s]
    assert len(family) == 1, sentences
    memory = [i for i, s in enumerate(sentences) if re.search(r"\bmemory\b", s)]
    assert memory == [family[0] + 1], (sentences[family[0]], sentences[memory[0]])
    # the rule speaks for both answers, the OEM one and the Families one,
    # which stand right before it, still saying no Invocation and why
    oem = sentences[family[0] - 1]
    assert re.search(r"\boem command\b", oem), oem
    for sentence in (oem, sentences[family[0]]):
        assert re.search(r"\bno invocation\b", sentence), sentence
        assert re.search(r"\bwhy\b", sentence), sentence
    assert re.search(r"\bno bytes to send\b", sentences[family[0]])


def test_memory_rule_is_in_the_intro_not_a_step():
    body = _body()
    first_step = next(i for i, ln in enumerate(body) if re.match(r"\d+\. ", ln))
    steps = _flat(body[first_step:]).lower()
    assert "from memory" in _intro().lower()
    assert "from memory" not in steps, "the rule belongs to the intro"


# ------------------------------------------------------------------ AC-2


def test_block_stays_within_the_raised_cap_with_the_rule_inside():
    body = _body()
    assert len(body) <= MAX_LINES, len(body)
    assert re.search(r"\bmemory\b", _intro().lower()), "rule not in the block"
    # the earlier rules the cap was raised for are still there
    text = _flat(body)
    for kept in (
        "Never write bytes by hand",
        "copy the line(s) and total it prints",
        "another tool version may differ",
        "no connection options",
    ):
        assert kept in text, kept


# ------------------------------------------------------------------ AC-3


def _author_module():
    spec = importlib.util.spec_from_file_location("author_cmd_workflow", AUTHOR_TESTS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_author_test_checks_the_memory_rule_and_passes():
    module = _author_module()
    tests = [
        fn
        for name, fn in vars(module).items()
        if name.startswith("test_") and callable(fn)
    ]
    about = [fn for fn in tests if "memory" in inspect.getsource(fn).lower()]
    assert about, "no test in test_command_workflow.py names memory"
    for fn in about:
        source = inspect.getsource(fn).lower()
        assert "search" in source, fn.__name__
        assert "bytes" in source, fn.__name__
        assert "nc-si" in source or "famil" in source, fn.__name__
        fn()  # passes on this branch

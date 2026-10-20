"""Reviewer acceptance tests for T39: step 3 of the Command workflow block says
an SPDM layout is that of the Document Version read, that an older negotiated
version can differ, and that a version the user names is the Version used
(AC-1 to AC-3, AC-10).

The block is the feature, so the tests read SKILL.md the way a Session gets
it and check the shape of the rule, not one wording: sentences of step 3 that
come after the SPDMVersion sentence (kept word for word), name the Document
Version as the layout's, name an older negotiated version as one that can
differ, and send a user-named version to that Version. AC-2 is the raised
cap in the five test files with the rule inside it; AC-3 is the author's own
test, which must exist, pass here, and fail once the rule is cut out. AC-10
(round 1, F1): the named-version clause goes through the reading command's
`--version`, as the Ready rule and step 2 of the answering workflow say, and
the block holds no `fetch`.

Every test needs the rule after the SPDMVersion sentence, which develop's
step 3 does not hold, so each one fails on develop.
"""

import importlib.util
import inspect
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
TESTS = ROOT / "tests"
AUTHOR_TESTS = TESTS / "test_command_workflow.py"
CAPPED = (
    "test_command_workflow.py",
    "test_review_cmdblock.py",
    "test_review_cmdresponse.py",
    "test_review_cmdwording.py",
    "test_review_cmdmemory.py",
)

START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
# AC-2: 38 until T39; 40 until T41; 42 until T43; 44 until T46; 46 until T52
MAX_LINES = 52

# the SPDMVersion sentence as develop holds it (AC-1: stays word for word)
SPDM_VERSION_SENTENCE = (
    "SPDM byte 0 is SPDMVersion: what the Document fixes for GET_VERSION; in "
    "every other request `<negotiated version>` unless the user names one, "
    "never the Version of the Document the layout came from."
)


def _body(path: Path = SKILL) -> list[str]:
    lines = path.read_text("utf-8").splitlines()
    assert lines.count(START) == 1, "start marker: one whole line, exactly once"
    assert lines.count(END) == 1, "end marker: one whole line, exactly once"
    first, last = lines.index(START), lines.index(END)
    assert first < last
    return lines[first + 1 : last]


def _flat(lines: list[str]) -> str:
    return " ".join(" ".join(lines).split())


def _step_lines(number: int, body: list[str] | None = None) -> list[str]:
    """The lines of step `number`, from its own line to the line before the
    next step or the end of the block."""
    body = _body() if body is None else body
    first = next(i for i, ln in enumerate(body) if ln.startswith(f"{number}. "))
    last = next(
        (i for i in range(first + 1, len(body)) if re.match(r"\d+\. ", body[i])),
        len(body),
    )
    return body[first:last]


def _sentences(text: str) -> list[str]:
    """The sentences of `text`, each with its full stop; a `.` inside a
    backtick span or a version number is not a sentence end."""
    out, current = [], ""
    in_code = False
    for i, ch in enumerate(text):
        current += ch
        if ch == "`":
            in_code = not in_code
        elif ch == "." and not in_code:
            after = text[i + 1 : i + 2]
            if after == "" or after == " ":
                out.append(current.strip())
                current = ""
    if current.strip():
        out.append(current.strip())
    return out


def _after_version_sentence() -> list[str]:
    """The sentences of step 3 that follow the SPDMVersion sentence."""
    sentences = _sentences(_flat(_step_lines(3)))
    assert SPDM_VERSION_SENTENCE in sentences, sentences
    return sentences[sentences.index(SPDM_VERSION_SENTENCE) + 1 :]


# ------------------------------------------------------------------ AC-1


def test_spdm_version_sentence_stays_word_for_word_in_step_3():
    text = _flat(_step_lines(3))
    assert SPDM_VERSION_SENTENCE in text, text
    # and only there: the rule did not move it or copy it
    assert _flat(_body()).count(SPDM_VERSION_SENTENCE) == 1


def test_step_3_says_the_layout_is_the_document_versions_and_to_say_so():
    rule = " ".join(_after_version_sentence())
    assert rule, "nothing follows the SPDMVersion sentence in step 3"
    low = rule.lower()
    assert re.search(r"\blayout\b", low), rule
    assert re.search(r"\bdocument version\b", low), rule
    # the answer names it: "say so" or an equivalent telling
    assert re.search(r"\b(say so|say which|name it|names it|say it)\b", low), rule


def test_step_3_says_an_older_negotiated_version_can_differ():
    rule = " ".join(_after_version_sentence())
    low = rule.lower()
    assert re.search(r"\bolder\b", low), rule
    assert re.search(r"\bnegotiated version\b", low), rule
    assert re.search(r"\b(differ|differs|different|differently)\b", low), rule


def test_step_3_sends_a_user_named_version_to_that_document_version():
    rule = " ".join(_after_version_sentence())
    low = rule.lower()
    assert re.search(r"\buser names\b", low), rule
    # brought to Ready by the reading command's `--version` (AC-10)
    assert "`--version`" in rule, rule
    assert re.search(r"\buse\b", low), rule
    assert re.search(r"\bthat (document )?version\b", low), rule


# ------------------------------------------------------------------ AC-10


def test_named_version_clause_agrees_with_the_ready_rule():
    # round 1 F1: the clause said `fetch` while the Ready rule says never to
    # run `fetch` before a reading command and step 2 passes the named
    # version with `--version`; the block now says the same as those two
    body = _body()
    rule = " ".join(_after_version_sentence())
    assert "`--version`" in rule, rule
    assert not re.search(r"\bfetch", rule.lower()), rule
    assert not re.search(r"\bfetch", _flat(body).lower()), "no `fetch` in the block"
    # the rest of SKILL.md still carries the rule the clause now follows
    text = " ".join(SKILL.read_text("utf-8").split())
    assert "You never run `fetch` or `extract` before a reading command." in text
    assert "passed verbatim with `--version`" in text


def test_named_version_clause_is_a_sentence_of_its_own_after_the_differ_rule():
    # the two new rules read as two sentences: the layout one, then the
    # named-version one, so a Session can follow either without the other
    after = _after_version_sentence()
    assert len(after) >= 2, after
    layout, named = after[0].lower(), " ".join(after[1:]).lower()
    assert re.search(r"\bolder\b", layout) and re.search(r"\bdiffer", layout), layout
    assert "user names" in named and "--version" in named, named


def test_the_version_rule_sits_in_step_3_and_nowhere_else():
    body = _body()
    step3 = _flat(_step_lines(3, body)).lower()
    rest = _flat([ln for ln in body if ln not in _step_lines(3, body)]).lower()
    assert re.search(r"\bolder\b", step3)
    assert not re.search(r"\bolder\b", rest), "the rule belongs to step 3"
    # the SPDMVersion sentence and the rule stand before the `invocation` step
    text = _flat(body)
    assert text.index("older") < text.index("4. Run `invocation")


def test_rule_writes_no_bytes_and_no_version_number():
    # the rule names no Document Version of its own (1.4.1) and no byte:
    # the Version comes from what was read, the bytes from the helper
    rule = " ".join(_after_version_sentence())
    assert not re.search(r"\b\d+\.\d+(\.\d+)?\b", rule), rule
    assert not re.search(r"\b0x[0-9a-fA-F]{1,2}\b", rule), rule
    assert not re.search(r"\b[0-9a-f]{2}( [0-9a-f]{2})+\b", rule), rule


# ------------------------------------------------------------------ AC-2


def test_block_stays_within_the_raised_cap_with_the_rule_inside():
    body = _body()
    assert len(body) <= MAX_LINES, len(body)
    assert re.search(r"\bolder\b", _flat(_step_lines(3, body)).lower())
    # the earlier rules the cap was raised for are still there
    text = _flat(body)
    for kept in (
        "Never write bytes by hand",
        "copy the line(s) and total it prints",
        "another tool version may differ",
        "no connection options",
        "even hedged or as a search term",
        "Other Families (NVMe-MI)",  # NC-SI left in T52
    ):
        assert kept in text, kept


@pytest.mark.parametrize("name", CAPPED)
def test_each_capped_test_file_declares_the_raised_cap(name):
    source = (TESTS / name).read_text("utf-8")
    found = re.findall(r"^MAX_LINES\s*=\s*(\d+)", source, re.M)
    assert found == [str(MAX_LINES)], (name, found)


# ------------------------------------------------------------------ AC-3


def _author_module():
    spec = importlib.util.spec_from_file_location("author_cmd_workflow", AUTHOR_TESTS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _author_tests_about_the_rule(module):
    tests = [
        fn
        for name, fn in vars(module).items()
        if name.startswith("test_") and callable(fn)
    ]
    about = [
        fn
        for fn in tests
        if re.search(r"\bolder\b", inspect.getsource(fn).lower())
        and "names" in inspect.getsource(fn).lower()
    ]
    assert about, "no test in test_command_workflow.py names an older version"
    return about


def test_author_test_checks_the_version_rule_and_passes():
    module = _author_module()
    for fn in _author_tests_about_the_rule(module):
        source = inspect.getsource(fn).lower()
        assert "negotiated version" in source, fn.__name__
        assert "invocation" in source, fn.__name__  # placed before step 4
        fn()  # passes on this branch


def test_author_test_fails_without_the_rule(tmp_path):
    # develop's step 3 ends with the SPDMVersion sentence: cut what follows
    # it and the author's test must fail
    lines = SKILL.read_text("utf-8").splitlines()
    first, last = lines.index(START), lines.index(END)
    body = lines[first + 1 : last]
    step3 = _step_lines(3, body)
    keep = next(i for i, ln in enumerate(step3) if ln.rstrip().endswith("came from."))
    cut = step3[keep + 1 :]
    assert cut, "nothing follows the SPDMVersion sentence to cut"
    start = first + 1 + body.index(step3[0])
    trimmed = lines[: start + keep + 1] + lines[start + len(step3) :]
    assert len(trimmed) == len(lines) - len(cut)
    stub = tmp_path / "SKILL.md"
    stub.write_text("\n".join(trimmed) + "\n", "utf-8", newline="")

    module = _author_module()
    about = _author_tests_about_the_rule(module)
    module.SKILL = stub
    for fn in about:
        with pytest.raises(AssertionError):
            fn()

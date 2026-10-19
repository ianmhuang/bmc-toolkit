"""Reviewer acceptance tests for T41: step 3 of the Command workflow block says
which Type a PLDM request header carries (AC-1 to AC-3).

The block is the feature, so the tests read SKILL.md the way a Session gets
it and check the shape of the rule, not one wording: a sentence of step 3,
right after the `80` sentence (kept word for word), that names PLDM byte 1,
ties it to the Type whose Document defines the Command, gives `00` for the
DSP0240 base Commands, and sends a Type the request names into a request
field. AC-2 is the raised cap, declared as the same number in every test file
that pins it and annotated with T41; the SPDM sentences that follow the new
one are unchanged word for word. AC-3 is the author's own test, which must
exist, pass here, and fail once the new sentence is cut out of a stub.

Every test needs the PLDM Type sentence, which develop's step 3 does not
hold, so each one fails on develop.
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

START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
# develop's block was 40 lines; T41 AC-2 let it grow by two; 42 until T43; 44 until T46
MAX_LINES = 46

# every test file that pins the cap (AC-2)
CAPPED = (
    "test_command_workflow.py",
    "test_review_cmdblock.py",
    "test_review_cmdmemory.py",
    "test_review_cmdresponse.py",
    "test_review_cmdwording.py",
    "test_review_spdmlayout.py",
    "test_review_placeholder0x.py",
)

# the `80` sentence as develop holds it (AC-1: stays)
HEADER_80_SENTENCE = (
    "Headers: an MCTP control or PLDM request starts with `80` (Rq=1, D=0, "
    "instance id 0); say so."
)
# the SPDM sentences that follow, as develop holds them (AC-2: unchanged)
SPDM_VERSION_SENTENCE = (
    "SPDM byte 0 is SPDMVersion: what the Document fixes for GET_VERSION; in "
    "every other request `<negotiated version>` unless the user names one, "
    "never the Version of the Document the layout came from."
)
SPDM_LAYOUT_SENTENCES = (
    "The layout is that Document Version's: say so, and that an older "
    "negotiated version can differ. If the user names one: use that Version "
    "(`--version`)."
)


def _lines(path: Path = SKILL) -> list[str]:
    return path.read_text("utf-8").splitlines()


def _body(path: Path = SKILL) -> list[str]:
    lines = _lines(path)
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


def _step3_sentences(body: list[str] | None = None) -> list[str]:
    text = _flat(_step_lines(3, body))
    assert text.startswith("3. ")
    return _sentences(text[len("3. ") :])


def _is_pldm_type_sentence(sentence: str) -> bool:
    low = sentence.lower()
    return bool(
        re.search(r"\bpldm\b", low)
        and re.search(r"\bbyte 1\b", low)
        and re.search(r"\btype\b", low)
    )


def _pldm_type_sentence(body: list[str] | None = None) -> str:
    found = [s for s in _step3_sentences(body) if _is_pldm_type_sentence(s)]
    assert len(found) == 1, found
    return found[0]


# ------------------------------------------------------------------ AC-1


def test_step_3_keeps_the_80_sentence_word_for_word():
    sentences = _step3_sentences()
    assert sentences[0] == HEADER_80_SENTENCE, sentences[0]
    assert _flat(_body()).count(HEADER_80_SENTENCE) == 1
    # with the new rule beside it (fails on develop)
    assert _pldm_type_sentence()


def test_step_3_has_one_sentence_on_pldm_byte_1_right_after_the_80_sentence():
    sentences = _step3_sentences()
    assert sentences[0] == HEADER_80_SENTENCE
    assert len(sentences) >= 2, sentences
    assert _is_pldm_type_sentence(sentences[1]), sentences[1]
    # one such sentence in the whole block, and it belongs to step 3
    body = _body()
    rest = [ln for ln in body if ln not in _step_lines(3, body)]
    rest_sentences = _sentences(_flat(rest))
    assert not any(_is_pldm_type_sentence(s) for s in rest_sentences), rest


def test_byte_1_is_the_type_of_the_document_that_defines_the_command():
    rule = _pldm_type_sentence()
    low = rule.lower()
    assert re.search(r"\bdocument\b", low), rule
    assert re.search(r"\bdefines?\b", low), rule
    assert re.search(r"\bcommand\b", low), rule


def test_dsp0240_base_commands_are_type_00():
    rule = _pldm_type_sentence()
    assert "DSP0240" in rule, rule
    assert re.search(r"\bbase commands?\b", rule.lower()), rule
    # the byte is written the way the block writes `80`: a two-digit code span
    spans = re.findall(r"`([^`]+)`", rule)
    assert "00" in spans, spans
    # and it is the only byte the sentence writes: no bytes from memory
    assert [s for s in spans if re.fullmatch(r"[0-9a-fA-F]{2}", s)] == ["00"]
    assert not re.search(r"\b0x[0-9a-fA-F]{1,2}\b", rule), rule
    assert not re.search(r"\b[0-9a-f]{2}( [0-9a-f]{2})+\b", rule), rule


def test_a_type_the_request_names_goes_into_a_request_field_not_the_header():
    rule = _pldm_type_sentence()
    low = rule.lower()
    # a Type the user asks about (names, asks for) ...
    assert re.search(r"\b(asked|asks|named|names|request names|user names)\b", low), rule
    # ... is a request field, not the header's byte
    assert re.search(r"\b(request|payload)('s)? field\b|\bfield of the request\b", low), (
        rule
    )
    assert re.search(r"\bnot\b|\bnever\b", low), rule


def test_the_rule_stands_before_the_spdm_sentences_and_the_invocation_step():
    text = _flat(_body())
    rule = _pldm_type_sentence()
    assert text.index(rule) < text.index(SPDM_VERSION_SENTENCE)
    assert text.index(rule) < text.index("4. Run `invocation")


# ------------------------------------------------------------------ AC-2


def test_block_grew_by_at_most_two_lines_and_stays_within_the_cap():
    body = _body()
    assert len(body) <= MAX_LINES, len(body)
    # the rule is inside the capped block
    assert _pldm_type_sentence(body)


def test_spdm_sentences_after_the_rule_are_unchanged_word_for_word():
    sentences = _step3_sentences()
    rule = _pldm_type_sentence()
    after = " ".join(sentences[sentences.index(rule) + 1 :])
    assert after == SPDM_VERSION_SENTENCE + " " + SPDM_LAYOUT_SENTENCES, after


def test_the_earlier_rules_the_cap_was_raised_for_are_still_there():
    text = _flat(_body())
    assert _pldm_type_sentence() in text
    for kept in (
        "Never write bytes by hand",
        "copy the line(s) and total it prints",
        "another tool version may differ",
        "no connection options",
        "even hedged or as a search term",
        "Other Families (NC-SI, NVMe-MI)",
        "An OEM Command no Library Document defines: no Invocation; say why.",
        "header included",
    ):
        assert kept in text, kept


@pytest.mark.parametrize("name", CAPPED)
def test_each_capped_test_file_declares_the_raised_cap_with_the_t41_reason(name):
    source = (TESTS / name).read_text("utf-8").splitlines()
    pins = [i for i, ln in enumerate(source) if re.match(r"MAX_LINES\s*=", ln)]
    assert len(pins) == 1, (name, pins)
    line = source[pins[0]]
    found = re.match(r"MAX_LINES\s*=\s*(\d+)", line).group(1)
    assert found == str(MAX_LINES), (name, found)
    # the reason sits on the pin line or in the comment block above it
    window = " ".join(source[max(0, pins[0] - 4) : pins[0] + 1])
    assert "T41" in window, (name, window)


def test_no_capped_file_pins_a_stale_cap():
    for name in CAPPED:
        source = (TESTS / name).read_text("utf-8")
        found = re.findall(r"^MAX_LINES\s*=\s*(\d+)", source, re.M)
        assert found == [str(MAX_LINES)], (name, found)


# ------------------------------------------------------------------ AC-3


def _author_module():
    spec = importlib.util.spec_from_file_location("author_cmd_workflow_t41", AUTHOR_TESTS)
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
    about = []
    for fn in tests:
        source = inspect.getsource(fn).lower()
        if "pldm" in source and "type" in source and "header" in source:
            about.append(fn)
    assert about, "no test in test_command_workflow.py is about the PLDM header Type"
    return about


def test_author_test_checks_the_rule_next_to_the_80_sentence_and_passes():
    module = _author_module()
    for fn in _author_tests_about_the_rule(module):
        source = inspect.getsource(fn).lower()
        # anchored on the `80` sentence, as AC-3 asks
        assert "say so" in source or "`80`" in source, fn.__name__
        assert "byte 1" in source, fn.__name__
        fn()  # passes on this branch


def test_author_test_fails_without_the_rule(tmp_path):
    # cut the PLDM Type sentence out of step 3 and the author's test must fail;
    # the rest of the block is kept, so the `80` and SPDM sentences stay
    lines = _lines()
    first, last = lines.index(START), lines.index(END)
    body = lines[first + 1 : last]
    step3 = _step_lines(3, body)
    sentences = _step3_sentences(body)
    rule = _pldm_type_sentence(body)
    trimmed_step3 = "3. " + " ".join(s for s in sentences if s != rule)
    assert rule not in trimmed_step3
    start = first + 1 + body.index(step3[0])
    stub_lines = lines[:start] + [trimmed_step3] + lines[start + len(step3) :]
    stub = tmp_path / "SKILL.md"
    stub.write_text("\n".join(stub_lines) + "\n", "utf-8", newline="")
    # the stub still holds the sentences the rule sits between
    stub_body = _body(stub)
    stub_text = _flat(stub_body)
    assert HEADER_80_SENTENCE in stub_text
    assert SPDM_VERSION_SENTENCE in stub_text

    module = _author_module()
    about = _author_tests_about_the_rule(module)
    module.SKILL = stub
    for fn in about:
        with pytest.raises(AssertionError):
            fn()


def test_author_test_does_not_weaken_the_header_or_spdm_tests():
    # the existing header and SPDM assertions still read the block and pass
    module = _author_module()
    module.test_block_gives_the_header_rules()
    module.test_spdm_layout_follows_its_document_version()
    module.test_block_stays_within_its_line_budget()
    # and the new one sits beside them (fails on develop: no such test there)
    assert _author_tests_about_the_rule(module)

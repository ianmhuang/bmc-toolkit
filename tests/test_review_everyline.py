"""Review tests for T43: every Invocation line the answer writes comes from
`invocation`.

AC-1 is the wording of a document and is not pinned here. AC-2: the Command
workflow block grew by at most two lines past develop's 42, the growth is
the tail of step 4 only, and every file that pins the cap raised it to the
same number naming T43. AC-3: the author's test exists, passes on this
branch, and fails on a SKILL.md whose step 4 ends where develop's did.
"""

import importlib.util
import inspect
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
AUTHOR_TESTS = TESTS / "test_command_workflow.py"

START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
# develop's block was 42 lines when T43 landed; its AC-2 let it grow by at
# most two. T46 then added two lines to step 2's PLDM bullet (`invocation
# --subcommand`), so the block cut where T43's step 4 ended is 42 + 2 lines.
DEVELOP_LINES = 42
LATER_GROWTH = 8  # T46: 2, outside step 4; T52: 6 (step 2, step 4's call)
MAX_LINES = 52  # 44 until T46; 46 until T52

# where develop's step 4, and its block, ended
DEVELOP_TAIL = "copy the line(s) and total it prints."

# every test file AC-2 lists as pinning the cap
CAPPED = (
    "test_command_workflow.py",
    "test_review_cmdblock.py",
    "test_review_cmdmemory.py",
    "test_review_cmdresponse.py",
    "test_review_cmdwording.py",
    "test_review_placeholder0x.py",
    "test_review_pldmtype.py",
    "test_review_spdmlayout.py",
)

# the author tests develop holds; none may go missing (AC-3: not weakened)
DEVELOP_AUTHOR_TESTS = (
    "test_block_sits_between_its_markers_and_holds_the_workflow",
    "test_block_stays_within_its_line_budget",
    "test_block_gives_the_syntax_of_each_tool",
    "test_block_gives_the_header_rules",
    "test_block_says_which_type_a_pldm_header_carries",
    "test_spdm_layout_follows_its_document_version",
    "test_block_has_the_helper_lay_out_the_bytes",
    "test_only_the_helper_writes_bytes",
    "test_the_printed_placeholder_is_copied_as_it_is",
    "test_invocation_runs_as_a_bash_call_of_its_own",
    "test_an_oem_command_without_a_document_gets_no_invocation",
    "test_block_says_what_ipmitool_raw_prints",
    "test_other_families_get_no_invocation_and_no_bytes",
    "test_neither_answer_writes_bytes_from_memory",
    "test_block_names_the_tool_versions_it_was_checked_against",
    "test_block_holds_no_rule_for_a_pasted_response",
    "test_description_names_the_tools_the_workflow_writes_for",
    "test_frontmatter_values_are_valid_yaml_scalars",
    "test_readme_says_what_can_be_asked_and_that_nothing_ran_on_hardware",
)


def _lines(path=SKILL):
    return path.read_text("utf-8").splitlines()


def _body(path=SKILL):
    lines = _lines(path)
    assert lines.count(START) == 1 and lines.count(END) == 1
    first, last = lines.index(START), lines.index(END)
    assert first < last
    return lines[first + 1 : last]


def _flat(lines):
    return " ".join(" ".join(lines).split())


def _step4(body):
    """The lines of step 4, from its number to the end of the block."""
    first = next(i for i, ln in enumerate(body) if ln.startswith("4. "))
    later = [i for i in range(first + 1, len(body)) if re.match(r"\d+\. ", body[i])]
    assert not later, "step 4 is the last step of the block"
    return body[first:]


def _develop_shape(lines):
    """The file with step 4 cut where develop's ended: everything after the
    tail sentence, up to the end marker, dropped."""
    first, last = lines.index(START), lines.index(END)
    body = lines[first + 1 : last]
    step4 = _step4(body)
    joined = " ".join(step4)
    assert DEVELOP_TAIL in joined, joined
    kept = []
    for ln in step4:
        if DEVELOP_TAIL in ln:
            kept.append(ln[: ln.index(DEVELOP_TAIL) + len(DEVELOP_TAIL)])
            break
        kept.append(ln)
    start = first + 1 + body.index(step4[0])
    return lines[:start] + kept + lines[last:]


# ------------------------------------------------------------------ AC-2


def test_block_stays_within_the_raised_cap():
    body = _body()
    assert DEVELOP_LINES < len(body) <= MAX_LINES, len(body)


def test_the_growth_is_the_tail_of_step_4_only(tmp_path):
    # cutting step 4 where develop's ended gives back a block of develop's
    # size: no line was added anywhere else
    stub = tmp_path / "SKILL.md"
    stub.write_text("\n".join(_develop_shape(_lines())) + "\n", "utf-8", newline="")
    trimmed = _body(stub)
    assert len(trimmed) == DEVELOP_LINES + LATER_GROWTH, len(trimmed)
    # and the lines before the tail are the file's own, word for word
    assert _body()[: len(trimmed) - 1] == trimmed[:-1]
    assert _body()[len(trimmed) - 1].startswith(trimmed[-1])


def test_step_4_says_more_after_the_tail_develop_ended_on():
    # the rule AC-1 adds sits after "copy the line(s) and total it prints."
    # and closes the block; its words are the author's to pin
    step4 = _flat(_step4(_body()))
    after = step4[step4.index(DEVELOP_TAIL) + len(DEVELOP_TAIL) :].strip()
    assert after, "step 4 ends where develop's did"
    assert after.endswith("."), after
    assert "Never write bytes by hand" in step4


@pytest.mark.parametrize("name", CAPPED)
def test_each_capped_file_pins_the_raised_cap_with_the_t43_reason(name):
    source = (TESTS / name).read_text("utf-8").splitlines()
    pins = [i for i, ln in enumerate(source) if re.match(r"MAX_LINES\s*=", ln)]
    assert len(pins) == 1, (name, pins)
    found = re.match(r"MAX_LINES\s*=\s*(\d+)", source[pins[0]]).group(1)
    assert found == str(MAX_LINES), (name, found)
    # the reason sits on the pin line or in the comment block above it
    window = " ".join(source[max(0, pins[0] - 6) : pins[0] + 1])
    assert "T43" in window, (name, window)


def test_no_other_test_file_pins_a_stale_cap():
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        found = re.findall(r"^MAX_LINES\s*=\s*(\d+)", path.read_text("utf-8"), re.M)
        assert found in ([], [str(MAX_LINES)]), (path.name, found)


# ------------------------------------------------------------------ AC-3


def _author_module():
    spec = importlib.util.spec_from_file_location("author_cmd_workflow_t43", AUTHOR_TESTS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _author_tests_about_the_rule(module):
    about = []
    for name, fn in vars(module).items():
        if not (name.startswith("test_") and callable(fn)):
            continue
        source = inspect.getsource(fn).lower()
        if "never write bytes by hand" in source and "every invocation line" in source:
            about.append(fn)
    assert about, "no test in test_command_workflow.py is about every Invocation line"
    return about


def test_author_keeps_every_test_develop_held():
    module = _author_module()
    names = {n for n, fn in vars(module).items() if n.startswith("test_") and callable(fn)}
    missing = [n for n in DEVELOP_AUTHOR_TESTS if n not in names]
    assert not missing, missing


def test_author_test_pins_the_rule_after_never_write_bytes_by_hand_and_passes():
    module = _author_module()
    for fn in _author_tests_about_the_rule(module):
        source = inspect.getsource(fn)
        # anchored after the sentence AC-1 keeps
        assert "Never write bytes by hand" in source, fn.__name__
        fn()  # passes on this branch


def test_author_test_fails_on_develops_step_4(tmp_path, monkeypatch):
    # step 4 cut where develop's ended: the author's test must fail there
    stub = tmp_path / "SKILL.md"
    stub.write_text("\n".join(_develop_shape(_lines())) + "\n", "utf-8", newline="")
    assert DEVELOP_TAIL in _flat(_body(stub))
    module = _author_module()
    monkeypatch.setattr(module, "SKILL", stub)
    for fn in _author_tests_about_the_rule(module):
        with pytest.raises(AssertionError):
            fn()
    # while the tests develop already held still pass on develop's shape:
    # the new test, not a loosened old one, is what tells the branches apart
    for name in DEVELOP_AUTHOR_TESTS:
        getattr(module, name)()

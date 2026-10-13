"""The Citation wording of SKILL.md and docs/COMMANDS.md: an answer's
Citation keeps the fields the tool printed, written the way it prints them."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
COMMANDS = ROOT / "docs" / "COMMANDS.md"


def flat(text):
    """Text as one line, so a phrase is found across a line break."""
    return " ".join(text.split())


def rules():
    text = SKILL.read_text("utf-8")
    start = text.index("\n## Citation rules\n")
    return flat(text[start : text.index("\n## ", start + 1)])


def definition():
    text = SKILL.read_text("utf-8")
    start = text.index("- **Citation**:")
    return flat(text[start : text.index("\n## ", start)])


def test_a_table_citation_is_described_with_the_lines_field_the_tool_prints():
    # `table` prints `lines table K` (tests/test_table_cli.py); the docs said
    # `table K`, and answers copied the docs
    for path in (SKILL, COMMANDS):
        text = flat(path.read_text("utf-8"))
        assert "`lines table K`" in text, path.name
        assert not re.search(r"(?<!lines )table K\b", text), path.name
    assert "`lines table K`" in definition()
    assert "`lines table K`" in rules()
    row = next(
        line
        for line in SKILL.read_text("utf-8").splitlines()
        if line.startswith("| `table DOC")
    )
    assert "`lines table K`" in row


def test_the_definition_gives_every_lines_form_with_its_prefix():
    text = definition()
    for form in ("`lines A-B`", "`lines -`", "`lines rendered page`"):
        assert form in text, form


def test_rules_say_which_fields_an_answer_keeps():
    text = rules()
    for phrase in (
        "separated by ` | `",
        "not as prose",
        "family, document and version, section, page and lines",
        "`lines table 1` stays `lines table 1`, not `table 1`",
        "Origin and Library path may be left out",
        "`user-provided` origin stays",
        "only when it reads `lines -`",
    ):
        assert phrase in text, phrase


def test_rules_say_how_a_section_field_may_be_cut_down():
    text = rules()
    for phrase in (
        "Copy the field whole, or keep the entries your claim sits in",
        "each whole and in the printed order",
        "Never shorten a title with `...`",
        "change its number",
        "a heading read in the page text",
    ):
        assert phrase in text, phrase


def test_the_as_printed_rule_points_at_what_may_be_cut():
    text = rules()
    for phrase in (
        "Two rules below say what may be cut",
        "a line range narrowed to the lines used",
        "a section field cut down to the entries the claim sits in",
    ):
        assert phrase in text, phrase
    # the pointer comes before the two rules it names
    pointer = text.index("Two rules below say what may be cut")
    assert pointer < text.index("give the range you actually used")
    assert pointer < text.index("Copy the field whole, or keep the entries")


def test_a_user_provided_citation_keeps_its_library_path():
    text = rules()
    for phrase in (
        "a `user-provided` origin stays and its Library path with it",
        "keep it, and the Library path after it",
        "Confidential documents are cited by path, never by a URL",
    ):
        assert phrase in text, phrase


def test_a_rendered_page_is_cited_with_the_line_render_printed():
    text = rules()
    for phrase in (
        "An answer read from a rendered PNG cites the `cite:` line `render` printed",
        "`lines rendered page` stays as it is",
    ):
        assert phrase in text, phrase
    # the printed field says it; no other words are asked for
    assert "read from a rendered page" not in text


def test_one_line_is_written_as_a_single_number():
    text = rules()
    for phrase in (
        "a claim on one line is `lines N`",
        "on several `lines A-B`",
        "Line numbers appear only when the `page` output printed them",
    ):
        assert phrase in text, phrase


def test_rules_give_a_find_hit_no_citation():
    text = rules()
    for phrase in (
        "A page seen only in `find` output has no Citation",
        "say it came from a `find` hit",
        "write no `cite:` line for it",
    ):
        assert phrase in text, phrase


def test_rules_keep_what_they_said_before():
    text = rules()
    for phrase in (
        "copied from a `cite:` line the tool printed in this session",
        "do not cite a page you did not read",
        "give the range you actually used, not the page's whole range",
        "open the page and check the heading before citing it",
        "A schema answer cites the `cite:` line(s) `schema` printed",
        "A code claim cites the `cite:` line `code` printed",
        "A value read from a Logical Table is cited with the `cite:` line",
        "A registry answer cites the `cite:` line `registry` printed",
        "Confidential documents are cited by path, never by a URL",
        "A statement without a Citation is labelled inference",
        "cite the Update first, then the base document",
    ):
        assert phrase in text, phrase

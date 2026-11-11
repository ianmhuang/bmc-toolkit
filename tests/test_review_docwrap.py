"""Reviewer acceptance test for the small-leftovers change (T75), AC-1.

AC-1 states a layout rule for the ``bmc_toolkit.spec.extract`` module
docstring: in each paragraph no line but the last is short enough that the
next line's first word would fit within that paragraph's widest line.

The rule is checked on the docstring as the source file carries it (read
with ``ast``, so the test does not depend on importing the module or on
``-OO``). No wording is pinned: the test measures line lengths only. The
indented block after ``Files written next to the original::`` is a literal
block laid out by hand, not wrapped prose, and is left out.

The other half of AC-1 (the words are the same as on develop) needs the
base branch's text and was checked by reading the diff.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "bmc_toolkit" / "spec" / "extract.py"


def _module_docstring() -> str:
    tree = ast.parse(EXTRACT.read_bytes().decode("utf-8"))
    doc = ast.get_docstring(tree, clean=True)
    assert doc, "bmc_toolkit/spec/extract.py has no module docstring"
    return doc


def _prose_paragraphs(doc: str) -> list[list[str]]:
    """Blank-line separated blocks whose lines all start at column 0."""
    paragraphs = []
    block: list[str] = []
    for line in [*doc.splitlines(), ""]:
        if line.strip():
            block.append(line.rstrip())
            continue
        if block and not any(ln[0].isspace() for ln in block):
            paragraphs.append(block)
        block = []
    return paragraphs


def _short_lines(paragraph: list[str]) -> list[str]:
    """Lines the next line's first word would still fit on."""
    widest = max(len(line) for line in paragraph)
    short = []
    for line, following in zip(paragraph, paragraph[1:], strict=False):
        first_word = following.split()[0]
        if len(line) + 1 + len(first_word) <= widest:
            short.append(line)
    return short


def test_ac1_the_docstring_has_wrapped_prose_to_measure():
    doc = _module_docstring()
    paragraphs = _prose_paragraphs(doc)
    wrapped = [p for p in paragraphs if len(p) > 1]
    # the description paragraph and the pypdfium2 requirement, at least
    assert len(wrapped) >= 2, paragraphs
    # the literal block of file names is in the docstring and is not prose
    indented = [ln for ln in doc.splitlines() if ln[:1].isspace() and ln.strip()]
    assert indented, "the literal block is gone; revisit what counts as prose"
    measured = {ln for p in paragraphs for ln in p}
    assert measured.isdisjoint(indented)


def test_ac1_no_line_is_short_enough_to_take_the_next_lines_first_word():
    problems = []
    for paragraph in _prose_paragraphs(_module_docstring()):
        for line in _short_lines(paragraph):
            widest = max(len(ln) for ln in paragraph)
            problems.append(f"{len(line)} of {widest} columns: {line!r}")
    assert problems == [], "lines wrapped short:\n" + "\n".join(problems)


def test_the_rule_itself_tells_a_short_line_from_an_even_one():
    """The helper is the AC's rule: synthetic text, no project wording."""
    even = ["aaaa bbbb cccc dddd", "eeee ffff gggg hhh", "iiii"]
    assert _short_lines(even) == []
    # "eeee" (4) fits after "aaaa bbbb" (9 + 1 + 4 <= 19)
    uneven = ["aaaa bbbb", "eeee ffff gggg hhhh", "iiii jjjj kkkk llll", "mm"]
    assert _short_lines(uneven) == ["aaaa bbbb"]
    # the last line may be as short as it likes
    assert _short_lines(["aaaa bbbb cccc", "d"]) == []
    # a single line has nothing to be compared with
    assert _short_lines(["aaaa"]) == []

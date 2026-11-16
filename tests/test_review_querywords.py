"""Reviewer acceptance tests for the query words the section matchers share
(AC-7): ``search.query_words``, and ``section`` on a PDF title and on a
Markdown document answering as before for queries written with odd
spacing, case and a trailing dot.

``query_words`` and ``query_matches`` are called directly (they are the
interface AC-7 names); the Markdown side goes through the CLI with a small
hand-written document.
"""

import pytest

from bmc_toolkit.spec.cli import main
from bmc_toolkit.spec.search import query_matches, query_words
from tests.conftest import MINI_CATALOG, ok

MD_URL = "https://example.test/raw/0123abc/doc/words.md"
MD_CATALOG = (
    MINI_CATALOG
    + f"""
[families.security]
title = "Security"
publisher = "various"

[[documents]]
id = "QW"
family = "security"
title = "A Markdown document written for the query words"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0"
url = "{MD_URL}"
type = "md"
published = "2026-10-01"
"""
)

# The title "Design   goals" (three spaces) is carried by two headings, so
# each is labelled by its heading path; "Ladder" is unique.
MD_LINES = [
    "# Fuses",  # 1
    "## Design   goals",  # 2
    "Fuse goals.",  # 3
    "# Keys",  # 4
    "## Design   goals",  # 5
    "Key goals.",  # 6
    "## Ladder",  # 7
    "The key ladder.",  # 8
]
MD_BYTES = ("\n".join(MD_LINES) + "\n").encode("utf-8")

FUSES_GOALS = "1 | Fuses > Design   goals | lines 2-3"
KEYS_GOALS = "1 | Keys > Design   goals | lines 5-6"


def run(capsys, catalog, *argv):
    code = main(["--catalog", str(catalog), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def held(tmp_path, library, scripted, capsys):
    """QW 1.0 fetched and extracted; the catalog file."""
    catalog = tmp_path / "words_catalog.toml"
    catalog.write_text(MD_CATALOG, encoding="utf-8", newline="")
    scripted.responses[MD_URL] = ok(MD_BYTES, "text/plain; charset=utf-8")
    code, out = run(capsys, catalog, "fetch", "QW")
    assert code == 0, out
    return catalog


# ------------------------------------------------------------ query_words


@pytest.mark.parametrize(
    "query, words",
    [
        ("fuse zeroing", ["fuse", "zeroing"]),
        # stripped, and runs of whitespace of any kind separate words
        ("  fuse   zeroing  ", ["fuse", "zeroing"]),
        ("fuse\tzeroing\n", ["fuse", "zeroing"]),
        # lower-cased
        ("Fuse ZEROING", ["fuse", "zeroing"]),
        # a trailing dot is dropped, before or after the stripping
        ("fuse zeroing.", ["fuse", "zeroing"]),
        ("fuse zeroing. ", ["fuse", "zeroing"]),
        ("4.2.", ["4.2"]),
        # a dot inside the query stays
        ("e.g. keys", ["e.g.", "keys"]),
        ("Boot flow > Scope", ["boot", "flow", ">", "scope"]),
        # nothing to compare
        ("", []),
        ("   ", []),
        (".", []),
    ],
)
def test_query_words_are_the_normalised_words_of_the_query(query, words):
    found = query_words(query)
    assert found == words
    assert isinstance(found, list)


# ----------------------------------------------------- the PDF's matching

WORD_CASES = [
    ("reset vector", "4.1 Reset vector", None, True),
    ("vector reset", "4.1 Reset vector", None, True),
    ("  VECTOR   reset. ", "4.1 Reset vector", None, True),
    ("reset", "4.1  Reset\tvector", None, True),
    ("reset boot", "4.1 Reset vector", None, False),
    ("", "4.1 Reset vector", None, False),
    ("   ", "4.1 Reset vector", None, False),
    # ``text`` replaces the title as what the words are looked for in
    ("scope notes", "Notes", "Overview > Scope > Notes", True),
    ("scope notes", "Notes", None, False),
]


@pytest.mark.parametrize("query, title, text, expected", WORD_CASES)
def test_query_matches_is_every_query_word_in_the_title(query, title, text, expected):
    assert query_matches(query, title, text) is expected
    # and it is the words query_words gives that are compared
    haystack = " ".join((title if text is None else text).split()).lower()
    words = query_words(query)
    assert (bool(words) and all(w in haystack for w in words)) is expected


@pytest.mark.parametrize(
    "query, title, expected",
    [
        ("4.2", "4.2 Measured boot", True),
        ("4.2.", "4.2 Measured boot", True),
        ("4", "4.2 Measured boot", True),
        ("4.2", "4.20 Other", False),
        ("4.2", "14.2 Other", False),
        ("A.2", "A.2 Annex", True),
        ("5", "Measured boot", False),
    ],
)
def test_a_section_number_query_is_matched_as_before(query, title, expected):
    assert query_matches(query, title) is expected


# ------------------------------------------------ the Markdown's matching


@pytest.mark.parametrize(
    "query, lines",
    [
        # every word in the heading path, one of them in the title itself
        ("keys design goals", [KEYS_GOALS]),
        ("  KEYS   Design\tgoals. ", [KEYS_GOALS]),
        ("fuses goals.", [FUSES_GOALS]),
        ("Keys > Design goals", [KEYS_GOALS]),
        # the words of the title alone list every heading that carries it
        ("design goals", [FUSES_GOALS, KEYS_GOALS]),
        ("GOALS  design.", [FUSES_GOALS, KEYS_GOALS]),
        # a word of an enclosing heading alone does not list what is under it
        ("keys", ["0 | Keys | lines 4-8"]),
        ("Fuses.", ["0 | Fuses | lines 1-3"]),
        # a unique title has no heading path to match
        ("ladder", ["1 | Ladder | lines 7-8"]),
        ("keys ladder", ["no matching section"]),
        ("   ", ["no matching section"]),
    ],
)
def test_markdown_sections_answer_the_same_words(held, capsys, query, lines):
    code, out = run(capsys, held, "section", "QW", query)
    assert (code, out.splitlines()) == (0, lines)


def test_page_section_reads_the_heading_the_words_select(held, capsys):
    code, out = run(capsys, held, "page", "QW", "--section", " keys  GOALS. ")
    assert code == 0, out
    lines = out.splitlines()
    fields = lines[0].split(" | ")
    assert fields[1:5] == ["QW 1.0", "Keys > Design   goals", "Markdown", "lines 5-6"]
    assert lines[1:] == ["5  ## Design   goals", "6  Key goals."]

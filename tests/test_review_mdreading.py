"""Reviewer acceptance tests for reading a Markdown version: ``section``,
``find``, ``page --lines``, ``page --section``, the section labels, the
``cite:`` line and the line numbering (AC-6 to AC-11, AC-14), and ``find``
across a Markdown ``searched_with`` companion (round 1, F5).

Black-box through the CLI. The document is the synthetic one of
``test_review_mdlibrary``; its comments give the line numbers used here.
"""

import pytest

from tests.conftest import ok
from tests.test_review_mdlibrary import (
    BOM,
    MD_BYTES,
    MD_CATALOG,
    MD_URL,
    PLAIN,
    add_bytes,
    run,
    said,
    version_dir,
)


@pytest.fixture
def md_catalog(tmp_path):
    path = tmp_path / "md_catalog.toml"
    path.write_text(MD_CATALOG, encoding="utf-8", newline="")
    return path


@pytest.fixture
def held(md_catalog, library, scripted, capsys):
    """RVW 1.0 fetched from its URL and extracted; the version directory."""
    scripted.responses[MD_URL] = ok(MD_BYTES, PLAIN)
    code, out = run(capsys, md_catalog, "fetch", "RVW")
    assert code == 0, out
    return version_dir(library)


def hits(out):
    """(line number, section label) of every ``find`` hit line."""
    found = []
    for ln in out.splitlines():
        if ln.startswith("RVW l."):
            where, label, _ = ln.split(" | ", 2)
            found.append((int(where.removeprefix("RVW l.")), label))
    return found


def cite_fields(out):
    first = out.splitlines()[0]
    assert first.startswith("cite: "), out
    return first.split(" | ")


def long_document(body_lines):
    """``# Long``, then ``body_lines`` lines, then ``# Next`` and one line."""
    body = "".join(f"body {i}\n" for i in range(body_lines))
    return ("# Long\n" + body + "# Next\nthe end\n").encode()


# ------------------------------------------------------------------- AC-6


@pytest.mark.parametrize(
    "query, lines",
    [
        ("glossary", ["0 | Glossary | lines 22-23"]),
        ("reset vector", ["2 | 4.1 Reset vector | lines 16-17"]),
        ("vector reset", ["2 | 4.1 Reset vector | lines 16-17"]),
        ("RESET", ["2 | 4.1 Reset vector | lines 16-17"]),
        ("4.2", ["1 | 4.2 Measured boot | lines 18-21"]),
        ("4.2.", ["1 | 4.2 Measured boot | lines 18-21"]),
        (
            "4",
            [
                "2 | 4.1 Reset vector | lines 16-17",
                "1 | 4.2 Measured boot | lines 18-21",
            ],
        ),
    ],
)
def test_section_prints_level_title_and_line_range(
    held, md_catalog, capsys, query, lines
):
    code, out = run(capsys, md_catalog, "section", "RVW", query)
    assert (code, out.splitlines()) == (0, lines)


def test_a_top_level_section_ends_before_the_next_top_level_heading(
    held, md_catalog, capsys
):
    # Only the first line is pinned here; which other headings answer the
    # query is test_words_are_matched_against_the_title_as_for_a_pdf's.
    code, out = run(capsys, md_catalog, "section", "RVW", "overview")
    assert code == 0
    assert out.splitlines()[0] == "0 | Overview | lines 3-12"


def test_two_headings_with_one_title_each_get_their_own_range(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "section", "RVW", "scope")
    assert code == 0
    rows = [ln.split(" | ") for ln in out.splitlines()]
    # the headings titled "Scope", whether printed bare or as a heading path
    scopes = [r for r in rows if r[1].split(" > ")[-1] == "Scope"]
    assert [(r[0], r[-1]) for r in scopes] == [
        ("1", "lines 6-12"),
        ("1", "lines 14-17"),
    ]


def test_words_are_matched_against_the_title_as_for_a_pdf(held, md_catalog, capsys):
    """AC-6: word matching is as for PDFs, where an entry matches when its
    title holds every word of the query. A heading titled ``Notes`` does not
    answer ``scope`` or ``measured`` because a heading above it does."""
    code, out = run(capsys, md_catalog, "section", "RVW", "scope")
    assert code == 0
    assert [ln.split(" | ")[-1] for ln in out.splitlines()] == [
        "lines 6-12",
        "lines 14-17",
    ]
    code, out = run(capsys, md_catalog, "section", "RVW", "measured")
    assert (code, out.splitlines()) == (0, ["1 | 4.2 Measured boot | lines 18-21"])
    code, out = run(capsys, md_catalog, "section", "RVW", "overview")
    assert (code, out.splitlines()) == (0, ["0 | Overview | lines 3-12"])


@pytest.mark.parametrize(
    "query, lines",
    [
        # every word in the heading path, one of them in the title itself
        ("boot flow scope", ["1 | Boot flow > Scope | lines 14-17"]),
        ("overview scope", ["1 | Overview > Scope | lines 6-12"]),
        ("scope notes", ["2 | Overview > Scope > Notes | lines 8-12"]),
        ("Boot flow > Scope", ["1 | Boot flow > Scope | lines 14-17"]),
        (
            "measured notes",
            ["2 | Boot flow > 4.2 Measured boot > Notes | lines 20-21"],
        ),
        # the words of the title alone list every heading that carries it
        (
            "notes",
            [
                "2 | Overview > Scope > Notes | lines 8-12",
                "2 | Boot flow > 4.2 Measured boot > Notes | lines 20-21",
            ],
        ),
        # a word of an enclosing heading alone does not list what is under it
        ("boot flow", ["0 | Boot flow | lines 13-21"]),
    ],
)
def test_a_repeated_title_is_also_matched_by_its_heading_path(
    held, md_catalog, capsys, query, lines
):
    """AC-6 as amended in round 1: a title two or more headings share is
    printed as its label and also matches when every word of the query is in
    its heading path and at least one is in its own title."""
    code, out = run(capsys, md_catalog, "section", "RVW", query)
    assert (code, out.splitlines()) == (0, lines)


def test_a_path_word_does_not_reach_a_unique_title_under_it(held, md_catalog, capsys):
    """Only a repeated title has a heading path: ``4.1 Reset vector`` is
    unique, so words of the heading above it do not select it."""
    code, out = run(capsys, md_catalog, "section", "RVW", "boot flow reset")
    assert (code, out.strip()) == (0, "no matching section")
    # "Notes" under "4.2 Measured boot" has both words in its path and
    # neither in its own title: only the heading that carries them answers
    code, out = run(capsys, md_catalog, "section", "RVW", "boot measured")
    assert (code, out.splitlines()) == (0, ["1 | 4.2 Measured boot | lines 18-21"])


@pytest.mark.parametrize("query", ["no such heading", "4.3", "9", "fence"])
def test_no_match_is_said_with_exit_0(held, md_catalog, capsys, query):
    code, out = run(capsys, md_catalog, "section", "RVW", query)
    assert (code, out.strip()) == (0, "no matching section")


# ------------------------------------------------------------------- AC-7


def test_find_prints_the_file_line_the_section_and_the_text(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "find", "RVW", "vector is fixed")
    assert code == 0
    assert out.splitlines() == ["RVW l.17 | 4.1 Reset vector | The vector is fixed."]


def test_find_context_prints_neighbours_and_ends_each_block(held, md_catalog, capsys):
    code, out = run(
        capsys, md_catalog, "find", "RVW", "Measurements extend", "--context", "1"
    )
    assert code == 0
    assert out.splitlines() == [
        "RVW l.19 | 4.2 Measured boot | Measurements extend the register.",
        "    line 18: ## 4.2 Measured boot",
        "    line 20: ### Notes",
        "--",
    ]


def test_find_context_stops_at_the_ends_of_the_file(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "find", "RVW", "read-only", "--context", "2")
    assert code == 0
    assert out.splitlines() == [
        "RVW l.23 | Glossary | ROM: read-only memory.",
        "    line 21: Ordering matters here.",
        "    line 22: # Glossary",
        "--",
    ]
    code, out = run(capsys, md_catalog, "find", "RVW", "preamble", "--context", "2")
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "RVW l.1 | - | Preamble line before any heading."
    assert lines[-2:] == ["    line 3: # Overview", "--"]
    assert len(lines) == 4  # the hit, lines 2 and 3, the separator
    assert lines[1].startswith("    line 2:")


def test_find_max_and_the_overflow_line(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "find", "RVW", "scope", "--max", "1")
    assert code == 0
    lines = out.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("RVW l.6 | ")
    assert lines[1].startswith("3 more hits")
    code, out = run(capsys, md_catalog, "find", "RVW", "scope", "--max", "0")
    assert code == 0
    assert [n for n, _ in hits(out)] == [6, 7, 14, 15]
    assert len(out.splitlines()) == 4


def test_find_is_a_case_insensitive_literal_unless_told(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "find", "RVW", "rom")
    assert [n for n, _ in hits(out)] == [4, 23]  # "from ROM", "ROM:"
    code, out = run(capsys, md_catalog, "find", "RVW", "ROM", "--case")
    assert [n for n, _ in hits(out)] == [4, 23]
    code, out = run(capsys, md_catalog, "find", "RVW", "rom", "--case")
    assert [n for n, _ in hits(out)] == [4]  # only "from"
    code, out = run(capsys, md_catalog, "find", "RVW", "^#{3} ", "--regex")
    assert (code, [n for n, _ in hits(out)]) == (0, [8, 16, 20])
    code, out = run(capsys, md_catalog, "find", "RVW", "^#{3} ")
    assert (code, out.strip()) == (0, "no hits")
    code, out = run(capsys, md_catalog, "find", "RVW", "nowhere in the file")
    assert (code, out.strip()) == (0, "no hits")


NOTES_URL = "https://example.test/raw/0123abc/doc/review-notes.md"
NOTES_BYTES = b"# Errata\nRead-only fuses are listed here.\n"
NOTES_HIT = "RVWNOTES l.2 | Errata | Read-only fuses are listed here."


@pytest.fixture
def companion_catalog(tmp_path, scripted):
    """MD_CATALOG with RVW searched together with RVWNOTES, a second
    Markdown document; both URLs answer."""
    title = 'title = "A Markdown specification written for the review"'
    assert title in MD_CATALOG
    path = tmp_path / "companion_catalog.toml"
    path.write_text(
        MD_CATALOG.replace(title, title + '\nsearched_with = ["RVWNOTES"]')
        + f"""
[[documents]]
id = "RVWNOTES"
family = "security"
title = "Errata of the Markdown specification written for the review"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1"
url = "{NOTES_URL}"
type = "md"
published = "2026-10-02"
""",
        encoding="utf-8",
        newline="",
    )
    scripted.responses[MD_URL] = ok(MD_BYTES, PLAIN)
    scripted.responses[NOTES_URL] = ok(NOTES_BYTES, PLAIN)
    return path


def test_a_markdown_document_searched_with_another_is_searched_too(
    companion_catalog, library, capsys
):
    """Round 1, F5: ``find`` reads Markdown, so a ``searched_with`` companion
    of type md is brought to Ready and searched like a PDF companion: what
    that prints is a ``note:``, its hits come first, ``--only`` skips it."""
    catalog = companion_catalog
    code, out = run(capsys, catalog, "find", "RVW", "read-only")
    assert code == 0, out
    lines = out.splitlines()
    assert said(out, "note: fetched RVWNOTES 1 via direct"), out
    assert said(out, "note: extracted RVWNOTES 1: 2 lines"), out
    assert lines[-2:] == [NOTES_HIT, "RVW l.23 | Glossary | ROM: read-only memory."]
    companion = library.specs / "security" / "RVWNOTES" / "1" / "original.md"
    assert companion.read_bytes() == NOTES_BYTES
    # both are Ready now: the answer alone, the companion's hit with context
    code, out = run(
        capsys, catalog, "find", "RVW", "fuses are listed", "--context", "1"
    )
    assert (code, out.splitlines()) == (0, [NOTES_HIT, "    line 1: # Errata", "--"])
    code, out = run(capsys, catalog, "find", "RVW", "read-only", "--only")
    assert (code, out.splitlines()) == (
        0,
        ["RVW l.23 | Glossary | ROM: read-only memory."],
    )


def test_only_keeps_find_from_fetching_a_markdown_companion(
    companion_catalog, library, scripted, capsys
):
    code, out = run(capsys, companion_catalog, "find", "RVW", "read-only", "--only")
    assert code == 0, out
    assert out.splitlines()[-1] == "RVW l.23 | Glossary | ROM: read-only memory."
    assert NOTES_URL not in scripted.calls
    assert not (library.specs / "security" / "RVWNOTES").exists()


# ------------------------------------------------------------------- AC-8


def test_a_unique_title_is_its_own_label(held, md_catalog, capsys):
    _, out = run(capsys, md_catalog, "find", "RVW", "boots from")
    assert hits(out) == [(4, "Overview")]
    _, out = run(capsys, md_catalog, "find", "RVW", "glossary")
    assert hits(out) == [(22, "Glossary")]


def test_a_line_before_the_first_heading_has_no_section(held, md_catalog, capsys):
    _, out = run(capsys, md_catalog, "find", "RVW", "preamble")
    assert hits(out) == [(1, "-")]


def test_a_repeated_title_is_labelled_by_its_heading_path(held, md_catalog, capsys):
    _, out = run(capsys, md_catalog, "find", "RVW", "scope")
    assert hits(out) == [
        (6, "Overview > Scope"),
        (7, "Overview > Scope"),
        (14, "Boot flow > Scope"),
        (15, "Boot flow > Scope"),
    ]
    # two levels of enclosing headings, and an enclosing title that is
    # itself unique
    _, out = run(capsys, md_catalog, "find", "RVW", "notes")
    assert hits(out) == [
        (8, "Overview > Scope > Notes"),
        (20, "Boot flow > 4.2 Measured boot > Notes"),
    ]
    _, out = run(capsys, md_catalog, "find", "RVW", "ordering matters")
    assert hits(out) == [(21, "Boot flow > 4.2 Measured boot > Notes")]


def test_a_line_in_a_fenced_block_belongs_to_the_heading_above_the_block(
    held, md_catalog, capsys
):
    _, out = run(capsys, md_catalog, "find", "RVW", "tilde fence")
    assert hits(out) == [(10, "Overview > Scope > Notes")]


# ------------------------------------------------------- AC-9 and AC-11


def test_page_lines_prints_the_cite_line_then_the_numbered_lines(
    held, md_catalog, capsys
):
    code, out = run(capsys, md_catalog, "page", "RVW", "--lines", "16-19")
    assert code == 0, out
    assert out.splitlines() == [
        "cite: security | RVW 1.0 | 4.1 Reset vector; 4.2 Measured boot | Markdown | "
        f"lines 16-19 | {MD_URL} | {held}",
        "16  ### 4.1 Reset vector",
        "17  The vector is fixed.",
        "18  ## 4.2 Measured boot",
        "19  Measurements extend the register.",
    ]


def test_line_numbers_are_right_aligned_to_the_last_one(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "page", "RVW", "--lines", "8-10")
    assert code == 0, out
    assert out.splitlines()[1:] == [
        " 8  ### Notes",
        " 9  ~~~",
        "10  # inside a tilde fence",
    ]


def test_an_end_past_the_file_is_clamped(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "page", "RVW", "--lines", "22-99")
    assert code == 0, out
    assert cite_fields(out)[4] == "lines 22-23"
    assert out.splitlines()[1:] == ["22  # Glossary", "23  ROM: read-only memory."]


@pytest.mark.parametrize(
    "value, message",
    [
        ("7", "--lines takes A-B (line numbers, 1-based)"),
        ("a-b", "--lines takes A-B (line numbers, 1-based)"),
        ("3-", "--lines takes A-B (line numbers, 1-based)"),
        ("1-2-3", "--lines takes A-B (line numbers, 1-based)"),
        ("0-3", "RVW 1.0 has 23 lines; --lines 0-3 is outside it"),
        ("24-30", "RVW 1.0 has 23 lines; --lines 24-30 is outside it"),
        ("400-500", "RVW 1.0 has 23 lines; --lines 400-500 is outside it"),
    ],
)
def test_page_lines_refusals(held, md_catalog, capsys, value, message):
    code, out = run(capsys, md_catalog, "page", "RVW", "--lines", value)
    assert (code, out.strip()) == (2, message)


def test_a_reversed_range_is_refused_and_prints_nothing_of_the_file(
    held, md_catalog, capsys
):
    """AC-9 names no message for B before A; it is a refusal with exit 2,
    and not the message that says the range is outside the file (both
    numbers are inside it)."""
    code, out = run(capsys, md_catalog, "page", "RVW", "--lines", "9-3")
    assert code == 2, out
    text = out.strip()
    assert len(text.splitlines()) == 1 and not text.startswith("cite:")
    assert "outside" not in text
    assert "--lines" in text


def test_more_than_200_lines_per_call_is_refused(
    md_catalog, library, tmp_path, capsys
):
    code, out, _ = add_bytes(capsys, md_catalog, tmp_path, long_document(250))
    assert code == 0, out
    run(capsys, md_catalog, "extract", "RVW")
    code, out = run(capsys, md_catalog, "page", "RVW", "--lines", "1-201")
    assert (code, out.strip()) == (
        2,
        "lines 1-201 are 201 lines; the limit is 200 per call",
    )
    code, out = run(capsys, md_catalog, "page", "RVW", "--lines", "2-201")
    assert code == 0, out
    lines = out.splitlines()
    assert len(lines) == 201  # the cite line and 200 lines
    assert lines[1] == "  2  body 0"
    assert lines[-1] == "201  body 199"


@pytest.mark.parametrize(
    "first, last, sections",
    [
        (1, 2, "-"),
        (1, 4, "Overview"),
        (7, 7, "Overview > Scope"),
        (12, 14, "Overview > Scope > Notes; Boot flow; Boot flow > Scope"),
        (19, 22, "4.2 Measured boot; Boot flow > 4.2 Measured boot > Notes; Glossary"),
    ],
)
def test_cite_lists_the_owner_of_the_first_line_then_the_headings_in_range(
    held, md_catalog, capsys, first, last, sections
):
    code, out = run(capsys, md_catalog, "page", "RVW", "--lines", f"{first}-{last}")
    assert code == 0, out
    assert cite_fields(out) == [
        "cite: security",
        "RVW 1.0",
        sections,
        "Markdown",
        f"lines {first}-{last}",
        MD_URL,
        str(held),
    ]


def test_a_drop_in_is_cited_as_user_provided(md_catalog, library, tmp_path, capsys):
    code, out, _ = add_bytes(capsys, md_catalog, tmp_path, MD_BYTES)
    assert code == 0, out
    run(capsys, md_catalog, "extract", "RVW")
    code, out = run(capsys, md_catalog, "page", "RVW", "--lines", "3-4")
    assert code == 0, out
    assert cite_fields(out) == [
        "cite: security",
        "RVW 1.0",
        "Overview",
        "Markdown",
        "lines 3-4",
        "user-provided",
        str(version_dir(library)),
    ]


# ------------------------------------------------------ AC-10 and AC-11


def test_page_section_prints_the_section_with_its_own_label_only(
    held, md_catalog, capsys
):
    code, out = run(capsys, md_catalog, "page", "RVW", "--section", "4.2")
    assert code == 0, out
    # lines 18-21 hold the heading of "Notes" too; --section names one section
    assert out.splitlines() == [
        f"cite: security | RVW 1.0 | 4.2 Measured boot | Markdown | lines 18-21 | "
        f"{MD_URL} | {held}",
        "18  ## 4.2 Measured boot",
        "19  Measurements extend the register.",
        "20  ### Notes",
        "21  Ordering matters here.",
    ]


def test_page_section_reads_the_first_match(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "page", "RVW", "--section", "4")
    assert code == 0, out
    assert cite_fields(out)[2:5] == ["4.1 Reset vector", "Markdown", "lines 16-17"]
    assert out.splitlines()[1:] == [
        "16  ### 4.1 Reset vector",
        "17  The vector is fixed.",
    ]
    # the first of two headings that share a title, cited by its label
    code, out = run(capsys, md_catalog, "page", "RVW", "--section", "scope")
    assert code == 0, out
    assert cite_fields(out)[2:5] == ["Overview > Scope", "Markdown", "lines 6-12"]
    assert out.splitlines()[1] == " 6  ## Scope"
    assert len(out.splitlines()) == 8


def test_page_section_without_a_match_is_exit_2(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "page", "RVW", "--section", "no such heading")
    assert (code, out.strip()) == (2, "no matching section")


def test_a_section_over_200_lines_is_refused_with_its_range(
    md_catalog, library, tmp_path, capsys
):
    code, out, _ = add_bytes(capsys, md_catalog, tmp_path, long_document(250))
    assert code == 0, out
    run(capsys, md_catalog, "extract", "RVW")
    code, out = run(capsys, md_catalog, "page", "RVW", "--section", "long")
    assert code == 2
    text = out.strip()
    assert len(text.splitlines()) == 1 and not text.startswith("cite:")
    assert "1-251" in text  # the heading on line 1 and 250 body lines
    assert "--lines" in text and "narrower" in text
    # a section of exactly 200 lines is printed
    code, out, _ = add_bytes(
        capsys, md_catalog, tmp_path, long_document(199), "--force"
    )
    assert code == 0, out
    run(capsys, md_catalog, "extract", "RVW")
    code, out = run(capsys, md_catalog, "page", "RVW", "--section", "long")
    assert code == 0, out
    assert cite_fields(out)[4] == "lines 1-200"
    assert len(out.splitlines()) == 201


# ------------------------------------------------------------------ AC-14

READS = [
    ["section", "RVW", "4"],
    ["find", "RVW", "scope"],
    ["find", "RVW", "preamble", "--context", "1"],
    ["page", "RVW", "--lines", "1-23"],
    ["page", "RVW", "--section", "glossary"],
]


def read_all(capsys, md_catalog, tmp_path, data, *extra):
    code, out, _ = add_bytes(capsys, md_catalog, tmp_path, data, *extra)
    assert code == 0, out
    code, out = run(capsys, md_catalog, "extract", "RVW")
    assert code == 0, out
    assert out.strip().startswith("extracted RVW 1.0: 23 lines")
    return [run(capsys, md_catalog, *argv) for argv in READS]


def test_crlf_and_a_bom_change_neither_the_numbers_nor_the_text(
    md_catalog, library, tmp_path, capsys
):
    lf = read_all(capsys, md_catalog, tmp_path, MD_BYTES)
    crlf = MD_BYTES.replace(b"\n", b"\r\n")
    assert read_all(capsys, md_catalog, tmp_path, crlf, "--force") == lf
    with_bom = BOM + crlf
    assert read_all(capsys, md_catalog, tmp_path, with_bom, "--force") == lf
    assert all(code == 0 for code, _ in lf)
    for _, out in lf:
        assert "\r" not in out and chr(0xFEFF) not in out


def test_a_bom_is_not_printed(md_catalog, library, tmp_path, capsys):
    code, out, _ = add_bytes(capsys, md_catalog, tmp_path, BOM + MD_BYTES)
    assert code == 0, out
    run(capsys, md_catalog, "extract", "RVW")
    code, out = run(capsys, md_catalog, "page", "RVW", "--lines", "1-1")
    assert code == 0, out
    assert out.splitlines()[1] == "1  Preamble line before any heading."
    code, out = run(capsys, md_catalog, "find", "RVW", "preamble")
    assert out.splitlines() == ["RVW l.1 | - | Preamble line before any heading."]


def test_page_and_find_print_lines_without_their_trailing_whitespace(
    held, md_catalog, capsys
):
    # line 17 of the file ends with two spaces (a Markdown hard break)
    assert (held / "original.md").read_bytes().splitlines()[16].endswith(b".  ")
    code, out = run(capsys, md_catalog, "page", "RVW", "--lines", "17-17")
    assert code == 0, out
    assert out.splitlines()[1] == "17  The vector is fixed."
    code, out = run(capsys, md_catalog, "find", "RVW", "vector is fixed")
    assert out.splitlines() == ["RVW l.17 | 4.1 Reset vector | The vector is fixed."]
    # an empty line is its number alone
    code, out = run(capsys, md_catalog, "page", "RVW", "--lines", "11-13")
    assert out.splitlines()[1:] == ["11  ~~~", "12", "13  # Boot flow"]


def test_context_lines_are_printed_without_their_trailing_whitespace(
    held, md_catalog, capsys
):
    """AC-14 says printed lines are the file's text with trailing whitespace
    stripped; a ``--context`` neighbour is a printed line of the file."""
    code, out = run(
        capsys, md_catalog, "find", "RVW", "4.2 Measured boot", "--context", "1"
    )
    assert code == 0, out
    assert out.splitlines() == [
        "RVW l.18 | 4.2 Measured boot | ## 4.2 Measured boot",
        "    line 17: The vector is fixed.",
        "    line 19: Measurements extend the register.",
        "--",
    ]

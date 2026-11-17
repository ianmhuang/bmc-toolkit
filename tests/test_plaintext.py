"""The text reader on its own (type txt, the IETF plain-text layout): the
body check, line numbering, page furniture, the Outline and its labels,
and the Citation line. The fixture is synthetic, laid out as an RFC."""

import json

import pytest

from bmc_toolkit.spec import plaintext as txt_mod
from bmc_toolkit.spec.library import body_matches_type
from bmc_toolkit.spec.markdown import split_lines

URL = "https://example.test/rfc9999.txt"
FOOTER = "Writer                   Standards Track                    [Page {n}]"
HEADER = "RFC 9999                  Example Protocol                 March 2026"

# A paginated RFC in miniature. Page 1 carries the author block, the title,
# Abstract and the contents; page 2 the numbered sections (old one-space
# style among them), ASCII art and a wrapped heading; page 3 a MIB-like
# block of column-0 code, the appendix and the authors' addresses.
RFC_TEXT = "\n".join(
    [
        "Internet Engineering Task Force (IETF)                     A. Writer",
        "Request for Comments: 9999                                  Example",
        "Category: Standards Track                                 March 2026",
        "",
        "",
        "                          Example Protocol",
        "",
        "Abstract",
        "",
        "   This document defines the example protocol.",
        "",
        "Table of Contents",
        "",
        "   1.  Introduction . . . . . . . . . . . . . . . . . . . . . .  2",
        "   2.  Old Style  . . . . . . . . . . . . . . . . . . . . . . .  2",
        "",
        "",
        FOOTER.format(n=1),
        "\f",
        HEADER,
        "",
        "",
        "1.  Introduction",
        "",
        "   The introduction says what the example is.  It goes on to",
        "",
        "",
        FOOTER.format(n=2),
        "\f",
        HEADER,
        "",
        "",
        "   continue on the next page with the Example word.",
        "",
        "1.1.  Terms",
        "",
        "   A term is defined here.",
        "",
        "2. Old Style",
        "",
        "2.1 One space",
        "",
        "   Old RFCs put one space after the number.",
        "",
        "+--------+",
        "| Box    |",
        "+--------+",
        "",
        "3.  A heading long enough that it wraps",
        "    onto a second line",
        "",
        "   Wrapped heading body with the Example word.",
        "",
        "EXAMPLE-MIB DEFINITIONS ::= BEGIN",
        "",
        "exampleObject OBJECT IDENTIFIER ::= { example 1 }",
        "",
        "END",
        "",
        "Appendix A.  Collected Rules",
        "",
        "   Rules go here.",
        "",
        "A.1.  First Rule",
        "",
        "   The first rule.",
        "",
        "Author's Address",
        "",
        "   A. Writer",
        "",
        "",
        FOOTER.format(n=3),
        "\f",
        "",
    ]
)


def lines():
    return split_lines(RFC_TEXT)


def number_of(text: str) -> int:
    """The 1-based line number of the first line equal to ``text``."""
    return lines().index(text) + 1


# --------------------------------------------------------------- check


@pytest.mark.parametrize(
    "data, expected",
    [
        (RFC_TEXT.encode(), True),
        (b"\xef\xbb\xbf" + RFC_TEXT.encode(), True),
        (b"<!DOCTYPE html><html><body>x</body></html>", False),
        (b"text with a \x00 byte", False),
        (b"\xff\xfe not utf-8", False),
        (b"   \n\n", False),
        (b"", False),
    ],
)
def test_the_body_check_is_the_markdown_one(data, expected):
    assert txt_mod.looks_like_text(data) is expected
    assert body_matches_type(data, "txt") is expected


# ----------------------------------------------------------- furniture


def test_page_furniture_is_footer_form_feed_header_and_their_padding():
    hidden = txt_mod.furniture(lines())
    first_break = number_of("\f")
    # page 1: the two blank lines above the footer, footer, form feed,
    # header and the two blank lines below it
    assert set(range(first_break - 3, first_break + 4)) <= hidden
    assert first_break - 4 not in hidden  # the last contents line
    assert number_of("1.  Introduction") not in hidden
    # the text on both sides of the second break keeps its lines
    assert (
        number_of("   The introduction says what the example is.  It goes on to")
        not in hidden
    )
    assert (
        number_of("   continue on the next page with the Example word.") not in hidden
    )


def test_a_form_feed_at_the_end_with_no_header_is_furniture():
    ls = lines()
    hidden = txt_mod.furniture(ls)
    last_break = len(ls) - ls[::-1].index("\f")
    assert last_break in hidden
    assert last_break - 1 in hidden  # its footer
    assert number_of("   A. Writer") not in hidden


def test_a_file_without_form_feeds_has_no_furniture():
    text = RFC_TEXT.replace("\f", "")
    assert txt_mod.furniture(split_lines(text)) == frozenset()


def test_a_form_feed_line_counts_as_a_line():
    ls = lines()
    assert ls.count("\f") == 3
    assert len(ls) == len(RFC_TEXT.rstrip("\n").split("\n"))


# ------------------------------------------------------------- outline


def test_the_outline_holds_the_rfc_headings_in_order():
    entries = txt_mod.outline(lines())
    assert [(e["level"], e["title"]) for e in entries] == [
        (0, "Abstract"),
        (0, "Table of Contents"),
        (0, "1 Introduction"),
        (1, "1.1 Terms"),
        (0, "2 Old Style"),
        (1, "2.1 One space"),
        (0, "3 A heading long enough that it wraps onto a second line"),
        (0, "Appendix A Collected Rules"),
        (1, "A.1 First Rule"),
        (0, "Author's Address"),
    ]
    assert entries[2]["line"] == number_of("1.  Introduction")
    assert entries[6]["line"] == number_of("3.  A heading long enough that it wraps")


def test_the_author_block_footer_and_header_are_never_headings():
    titles = [e["title"] for e in txt_mod.outline(lines())]
    assert not any("Writer" in t or t.startswith("RFC 9999") for t in titles)
    assert not any(t.startswith("Internet Engineering") for t in titles)


def test_ascii_art_and_column_0_code_are_not_headings():
    titles = [e["title"] for e in txt_mod.outline(lines())]
    assert not any(
        t.startswith(("+", "|", "EXAMPLE-MIB", "exampleObject", "END")) for t in titles
    )


@pytest.mark.parametrize(
    "line, expected",
    [
        ("4.1.2.  Client Hello", (2, "4.1.2 Client Hello")),
        ("4.1.2  Client Hello", (2, "4.1.2 Client Hello")),
        ("1.1 Changes to RFC 1541", (1, "1.1 Changes to RFC 1541")),
        ("1.1. Threats", (1, "1.1 Threats")),
        ("7.  Security   Considerations", (0, "7 Security Considerations")),
        ("Appendix B.  Protocol Data", (0, "Appendix B Protocol Data")),
        ("B.3.1.  Key Exchange", (2, "B.3.1 Key Exchange")),
        # not numbered: read as an unnumbered heading (blank lines around,
        # indented text next), whose title is the line as it stands
        ("1 Introduction", (0, "1 Introduction")),
        ("I wonder why.", (0, "I wonder why.")),
        ("1.   Three spaces", (0, "1. Three spaces")),
    ],
)
def test_numbered_heading_forms(line, expected):
    text = "Author block\n\n" + line + "\n\n   body\n"
    entries = txt_mod.outline(split_lines(text))
    assert [(e["level"], e["title"]) for e in entries] == [expected]


def test_a_text_without_rfc_layout_has_an_empty_outline():
    text = "just some notes\nwith no headings at all\n  and an indented line\n"
    assert txt_mod.outline(split_lines(text)) == []


# ------------------------------------------------------- extract / load


def test_extract_writes_outline_and_meta(tmp_path):
    original = tmp_path / "original.txt"
    original.write_text(RFC_TEXT, encoding="utf-8", newline="")
    result = txt_mod.extract(original, tmp_path)
    assert result.entries == 10
    meta = json.loads((tmp_path / "extract.json").read_text("utf-8"))
    assert meta["kind"] == "text"
    assert meta["extractor_version"] == txt_mod.TEXT_VERSION
    assert meta["lines"] == len(lines())
    assert txt_mod.is_current(tmp_path)
    meta["extractor_version"] = 0
    (tmp_path / "extract.json").write_text(json.dumps(meta), "utf-8")
    assert not txt_mod.is_current(tmp_path)
    meta["kind"] = "markdown"
    meta["extractor_version"] = txt_mod.TEXT_VERSION
    (tmp_path / "extract.json").write_text(json.dumps(meta), "utf-8")
    assert not txt_mod.is_current(tmp_path)


@pytest.fixture
def version(tmp_path):
    original = tmp_path / "original.txt"
    original.write_text(RFC_TEXT, encoding="utf-8", newline="")
    txt_mod.extract(original, tmp_path)
    return txt_mod.TextVersion.load(
        family="ietf",
        document="RFC9999",
        version="March 2026",
        path=tmp_path,
        original=original,
        origin=URL,
    )


def test_find_skips_furniture_and_keeps_file_line_numbers(version):
    hits = list(version.find("example"))
    numbers = [h.line for h in hits]
    assert number_of("   continue on the next page with the Example word.") in numbers
    assert not any(n in version.hidden for n in numbers)
    assert not any(h.text.startswith("RFC 9999") for h in hits)
    assert list(version.find("Page 2")) == []


def test_printed_lines_leave_out_furniture(version):
    first = number_of("   The introduction says what the example is.  It goes on to")
    last = number_of("   continue on the next page with the Example word.")
    printed = version.format_lines(first, last)
    assert len(printed) == 2
    assert printed[0].endswith("It goes on to")
    assert printed[1].startswith(str(last))


def test_the_cite_names_text_and_the_file_lines(version, tmp_path):
    first = number_of("1.1.  Terms")
    last = number_of("2.1 One space")
    assert version.cite(first, last) == (
        "cite: ietf | RFC9999 March 2026 | 1.1 Terms; 2 Old Style; 2.1 One space"
        f" | Text | lines {first}-{last} | {URL} | {tmp_path}"
    )


def test_section_queries_match_number_and_words(version):
    by_number = version.match_sections("1.1")
    assert [(lvl, h.label) for lvl, h, _ in by_number] == [(1, "1.1 Terms")]
    _, heading, end = version.match_sections("old style")[0]
    assert heading.label == "2 Old Style"
    assert end == number_of("3.  A heading long enough that it wraps") - 1
    _, heading, end = version.match_sections("1")[0]
    assert end == number_of("2. Old Style") - 1

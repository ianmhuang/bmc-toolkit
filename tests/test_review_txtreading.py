"""Reviewer acceptance tests for reading a text version (catalog type
``txt``): line numbering, page furniture, the Outline and its labels,
``section``, ``find``, ``page --lines``, ``page --section``, the ``cite:``
line, a ``searched_with`` companion and a text without RFC layout (AC-4 to
AC-8, AC-10), then the round-2 criteria: a numbered heading in the first
block (AC-15), a footer ending the file and a form feed on the header line
(AC-16), and an appendix found by its letter (AC-17).

Black-box through the CLI, plus ``outline.json`` (the Library layout the
docs describe). The document is synthetic, laid out as a paginated RFC; the
comments give the line numbers the tests name.
"""

import json

import pytest

from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG, ok

VERSION = "2026-06"
LABEL = f"RFC7777 {VERSION}"
TXT_URL = "https://example.test/rfc/rfc7777.txt"
OTHER_URL = "https://example.test/rfc/rfc7778.txt"
PLAIN = "text/plain; charset=utf-8"
BOM = b"\xef\xbb\xbf"

FOOTER = "Reviewer                 Informational                 [Page {n}]"
HEADER = "RFC 7777           The Review Transfer Protocol          June 2026"
AUTHOR = "Example Group                                    A. Reviewer"
WRAPPED = "2.2 A Message Whose Title Is Long Enough To Be Wrapped Onto A Second Line"

# The position in the list is the line number minus one; keep the order.
RFC_LINES = [
    "Example Task Force                              A. Reviewer",  # 1
    "Request for Comments: 7777                          Example",  # 2
    "Category: Informational                           June 2026",  # 3
    "",  # 4
    "",  # 5
    "                The Review Transfer Protocol",  # 6
    "",  # 7
    "Abstract",  # 8
    "",  # 9
    "   This memo describes a protocol made up for the review.",  # 10
    "",  # 11
    "Table of Contents",  # 12
    "",  # 13
    "   1.  Overview . . . . . . . . . . . . . . . . . . . .   2",  # 14
    "   2.  Messages . . . . . . . . . . . . . . . . . . . .   2",  # 15
    "",  # 16: furniture from here ...
    "",  # 17
    FOOTER.format(n=1),  # 18
    "\f",  # 19
    HEADER,  # 20
    "",  # 21
    "",  # 22: ... to here
    "1.  Overview",  # 23
    "",  # 24
    "   The transfer starts with a greeting that is split",  # 25
    "",  # 26: furniture from here ...
    FOOTER.format(n=2),  # 27
    "\f",  # 28
    HEADER,  # 29
    "",  # 30: ... to here
    "   across a page break and ends with a farewell.",  # 31
    "",  # 32
    "1.1.  Terms",  # 33
    "",  # 34
    "   Greeting: the first message.",  # 35
    "",  # 36
    "2. Messages",  # 37: one space after the dot
    "",  # 38
    "2.1 Hello Message",  # 39: no dot, one space
    "",  # 40
    "   The hello message carries a version.",  # 41
    "",  # 42
    "+---------+---------+",  # 43: ASCII art in column 0
    "| Version | Flags   |",  # 44
    "+---------+---------+",  # 45
    "",  # 46
    "2.1.1.  Version   Field",  # 47: a run of spaces in the title
    "",  # 48
    "   One octet.",  # 49
    "",  # 50
    "2.2.  A Message Whose Title Is Long Enough To Be",  # 51: wrapped
    "      Wrapped Onto A Second Line",  # 52
    "",  # 53
    "   The wrapped heading has this body.",  # 54
    "",  # 55
    "Appendix A.  State Machine",  # 56
    "",  # 57
    "   States are listed here.",  # 58
    "",  # 59
    "A.1.  Idle State",  # 60
    "",  # 61
    "   Nothing happens.",  # 62
    "",  # 63
    "Acknowledgements",  # 64
    "",  # 65
    "   Thanks to the reviewer.",  # 66
    "",  # 67: furniture from here to the end
    "",  # 68
    FOOTER.format(n=3),  # 69
    "\f",  # 70: a form feed with no header after it
]
assert len(RFC_LINES) == 70
RFC_TEXT = "\n".join(RFC_LINES) + "\n"
FURNITURE = {*range(16, 23), *range(26, 31), *range(67, 71)}

OUTLINE = [
    (0, "Abstract", 8),
    (0, "Table of Contents", 12),
    (0, "1 Overview", 23),
    (1, "1.1 Terms", 33),
    (0, "2 Messages", 37),
    (1, "2.1 Hello Message", 39),
    (2, "2.1.1 Version Field", 47),
    (1, WRAPPED, 51),
    (0, "Appendix A State Machine", 56),
    (1, "A.1 Idle State", 60),
    (0, "Acknowledgements", 64),
]


def entry(doc_id, url, title, extra=""):
    return f"""
[[documents]]
id = "{doc_id}"
family = "ietf"
title = "{title}"
access = "open"
fetch = "direct"
{extra}
[[documents.versions]]
version = "{VERSION}"
url = "{url}"
type = "txt"
published = "2026-06-01"
"""


FAMILY = """
[families.ietf]
title = "IETF RFCs"
publisher = "IETF"
"""
TXT_CATALOG = (
    MINI_CATALOG + FAMILY + entry("RFC7777", TXT_URL, "The Review Transfer Protocol")
)
PAIR_CATALOG = (
    MINI_CATALOG
    + FAMILY
    + entry(
        "RFC7777",
        TXT_URL,
        "The Review Transfer Protocol",
        'searched_with = ["RFC7778"]\n',
    )
    + entry("RFC7778", OTHER_URL, "Review Transfer Protocol Extensions")
)


@pytest.fixture
def txt_catalog(tmp_path):
    path = tmp_path / "txt_catalog.toml"
    path.write_text(TXT_CATALOG, encoding="utf-8", newline="")
    return path


@pytest.fixture
def pair_catalog(tmp_path):
    path = tmp_path / "pair_catalog.toml"
    path.write_text(PAIR_CATALOG, encoding="utf-8", newline="")
    return path


def run(capsys, catalog, *argv):
    code = main(["--catalog", str(catalog), *argv])
    return code, capsys.readouterr().out


def said(out, prefix):
    return any(ln.startswith(prefix) for ln in out.splitlines())


def hold(capsys, catalog, library, scripted, body):
    """Fetch RFC7777 with this body (bytes or text); (version dir, output)."""
    data = body.encode() if isinstance(body, str) else body
    scripted.responses[TXT_URL] = ok(data, PLAIN)
    code, out = run(capsys, catalog, "fetch", "RFC7777")
    assert code == 0, out
    holding = library.find("RFC7777", VERSION)
    assert holding is not None
    return holding.path, out


@pytest.fixture
def held(txt_catalog, library, scripted, capsys):
    """The synthetic RFC fetched and extracted; its version directory."""
    vdir, _ = hold(capsys, txt_catalog, library, scripted, RFC_TEXT)
    return vdir


def outline_of(vdir):
    entries = json.loads((vdir / "outline.json").read_text(encoding="utf-8"))
    return [(e["level"], e["title"], e["line"]) for e in entries]


def row(n, width=2):
    """Line ``n`` of the synthetic RFC as ``page`` prints it."""
    return f"{str(n).rjust(width)}  {RFC_LINES[n - 1]}".rstrip()


def cite(vdir, sections, first, last, origin=TXT_URL):
    return (
        f"cite: ietf | {LABEL} | {sections} | Text | lines {first}-{last} | "
        f"{origin} | {vdir}"
    )


def printed_numbers(lines):
    return [int(ln.split()[0]) for ln in lines]


# ------------------------------------------------------------------- AC-4


@pytest.mark.parametrize(
    "body",
    [
        RFC_TEXT.encode(),
        RFC_TEXT.rstrip("\n").encode(),
        BOM + RFC_TEXT.replace("\n", "\r\n").encode(),
    ],
    ids=["lf", "no-final-newline", "bom-crlf"],
)
def test_lines_are_counted_as_markdown_counts_them(
    txt_catalog, library, scripted, capsys, body
):
    vdir, out = hold(capsys, txt_catalog, library, scripted, body)
    # 70 lines: the three form-feed lines count, the final newline does not
    assert said(out, f"extracted {LABEL}: 70 lines")
    assert outline_of(vdir) == OUTLINE
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "1-1")
    assert code == 0, out
    assert out.splitlines()[1] == f"1  {RFC_LINES[0]}"
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "71-71")
    assert code == 2, out
    assert not said(out, "cite:")


# ------------------------------------------------------------------- AC-5


def test_furniture_is_never_a_find_hit(held, txt_catalog, capsys):
    # every footer holds "Informational" and "[Page", every header "RFC 7777"
    code, out = run(capsys, txt_catalog, "find", "RFC7777", "Informational")
    assert code == 0, out
    assert out.splitlines() == [f"RFC7777 l.3 | - | {RFC_LINES[2]}"]
    for pattern in ("[Page", "RFC 7777"):
        code, out = run(capsys, txt_catalog, "find", "RFC7777", pattern)
        assert (code, out.strip()) == (0, "no hits"), pattern


def test_a_hit_after_a_page_break_keeps_its_file_line(held, txt_catalog, capsys):
    code, out = run(
        capsys, txt_catalog, "find", "RFC7777", "farewell", "--context", "3"
    )
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == f"RFC7777 l.31 | 1 Overview | {RFC_LINES[30].strip()}"
    context = [
        int(ln.split(":")[0].split()[-1]) for ln in lines if ln.startswith("    line ")
    ]
    assert context, out
    assert not FURNITURE & set(context)
    assert 33 in context
    assert "    line 33: 1.1.  Terms" in lines


def test_page_lines_leaves_the_page_break_out_and_keeps_the_numbers(
    held, txt_catalog, capsys
):
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "25-33")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "1 Overview; 1.1 Terms", 25, 33),
        row(25),
        row(31),
        row(32),
        row(33),
    ]


def test_page_lines_across_the_first_break_and_at_the_end_of_the_file(
    held, txt_catalog, capsys
):
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "14-23")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "Table of Contents; 1 Overview", 14, 23),
        row(14),
        row(15),
        row(23),
    ]
    # the last footer and the form feed after it, with no header behind
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "64-70")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "Acknowledgements", 64, 70),
        row(64),
        row(65),
        row(66),
    ]


def test_page_section_leaves_the_page_break_out(held, txt_catalog, capsys):
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--section", "1")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == cite(held, "1 Overview", 23, 36)
    assert printed_numbers(lines[1:]) == [23, 24, 25, 31, 32, 33, 34, 35, 36]
    assert lines[1] == row(23)


def test_a_file_without_a_form_feed_has_no_furniture(
    txt_catalog, library, scripted, capsys
):
    footer = FOOTER.format(n=1)
    body = "\n".join(
        [
            AUTHOR,  # 1
            "",  # 2
            "1.  Scope",  # 3
            "",  # 4
            "   Text of the scope.",  # 5
            "",  # 6
            "",  # 7
            footer,  # 8
            HEADER,  # 9
            "",  # 10
            "   More text.",  # 11
            "",
        ]
    )
    hold(capsys, txt_catalog, library, scripted, body)
    code, out = run(capsys, txt_catalog, "find", "RFC7777", "[Page 1]")
    assert code == 0, out
    assert len(out.splitlines()) == 1
    assert out.startswith("RFC7777 l.8 | ")
    code, out = run(capsys, txt_catalog, "find", "RFC7777", "RFC 7777")
    assert code == 0, out
    assert out.startswith("RFC7777 l.9 | ")
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "5-11")
    assert code == 0, out
    assert printed_numbers(out.splitlines()[1:]) == [5, 6, 7, 8, 9, 10, 11]


# ------------------------------------------------------------ AC-6, AC-7


def test_the_outline_holds_the_headings_and_nothing_else(held):
    # not in it: the author block, the centred title, the indented contents
    # lines, the footers and headers, the ASCII art, the wrapped second line
    assert outline_of(held) == OUTLINE


@pytest.mark.parametrize(
    "line, expected",
    [
        ("7.  Security Considerations", (0, "7 Security Considerations")),
        ("4.1.2.  Client Hello", (2, "4.1.2 Client Hello")),
        ("1.1 Changes", (1, "1.1 Changes")),
        ("1.1  Changes", (1, "1.1 Changes")),
        ("1.1. Threats", (1, "1.1 Threats")),
        ("Appendix B.  Protocol Data", (0, "Appendix B Protocol Data")),
        ("B.3.  Key Exchange", (1, "B.3 Key Exchange")),
        ("Status of This Memo", (0, "Status of This Memo")),
    ],
)
def test_heading_forms(txt_catalog, library, scripted, capsys, line, expected):
    body = f"{AUTHOR}\n\n{line}\n\n   Body text.\n"
    vdir, _ = hold(capsys, txt_catalog, library, scripted, body)
    assert outline_of(vdir) == [(*expected, 3)]


def test_column_0_code_is_not_a_heading(txt_catalog, library, scripted, capsys):
    body = "\n".join(
        [
            AUTHOR,  # 1
            "",  # 2
            "1.  Module",  # 3
            "",  # 4
            "EXAMPLE-MIB DEFINITIONS ::= BEGIN",  # 5: column-0 text is next
            "",  # 6
            "exampleObject OBJECT IDENTIFIER",  # 7: no blank line after it
            "    ::= { example 1 }",  # 8
            "",  # 9
            "END",  # 10: column-0 text is next
            "",  # 11
            "2.  Security",  # 12
            "",  # 13
            "   Text.",  # 14
            "",
        ]
    )
    vdir, _ = hold(capsys, txt_catalog, library, scripted, body)
    assert outline_of(vdir) == [(0, "1 Module", 3), (0, "2 Security", 12)]


def test_an_unnumbered_heading_may_end_the_file(txt_catalog, library, scripted, capsys):
    body = f"{AUTHOR}\n\n1.  Scope\n\n   Text.\n\nAcknowledgements\n"
    vdir, _ = hold(capsys, txt_catalog, library, scripted, body)
    assert outline_of(vdir) == [(0, "1 Scope", 3), (0, "Acknowledgements", 7)]


def test_the_first_block_is_not_an_unnumbered_heading(
    txt_catalog, library, scripted, capsys
):
    body = "Example Group\n\n   An indented line.\n\nAbstract\n\n   Body.\n"
    vdir, _ = hold(capsys, txt_catalog, library, scripted, body)
    assert outline_of(vdir) == [(0, "Abstract", 5)]


@pytest.mark.parametrize(
    "query, expected",
    [
        ("2.1.1", ["2 | 2.1.1 Version Field | lines 47-50"]),
        ("version field", ["2 | 2.1.1 Version Field | lines 47-50"]),
        ("hello message", ["1 | 2.1 Hello Message | lines 39-50"]),
        ("1", ["0 | 1 Overview | lines 23-36", "1 | 1.1 Terms | lines 33-36"]),
        (
            "2",
            [
                "0 | 2 Messages | lines 37-55",
                "1 | 2.1 Hello Message | lines 39-50",
                "2 | 2.1.1 Version Field | lines 47-50",
                f"1 | {WRAPPED} | lines 51-55",
            ],
        ),
        ("state machine", ["0 | Appendix A State Machine | lines 56-63"]),
        ("A.1", ["1 | A.1 Idle State | lines 60-63"]),
        # AC-17: the letter lists the appendix heading, then its subsections
        (
            "A",
            [
                "0 | Appendix A State Machine | lines 56-63",
                "1 | A.1 Idle State | lines 60-63",
            ],
        ),
        (
            "A.",
            [
                "0 | Appendix A State Machine | lines 56-63",
                "1 | A.1 Idle State | lines 60-63",
            ],
        ),
        ("B", ["no matching section"]),
        ("abstract", ["0 | Abstract | lines 8-11"]),
        # furniture, the author block, the title and ASCII art match nothing
        ("reviewer", ["no matching section"]),
        ("review transfer", ["no matching section"]),
        ("flags", ["no matching section"]),
    ],
)
def test_section_finds_headings_by_number_and_words(
    held, txt_catalog, capsys, query, expected
):
    code, out = run(capsys, txt_catalog, "section", "RFC7777", query)
    assert code == 0, out
    assert out.splitlines() == expected


def test_a_repeated_title_is_labelled_by_its_path(
    txt_catalog, library, scripted, capsys
):
    body = "\n".join(
        [
            AUTHOR,  # 1
            "",  # 2
            "1.  Alpha",  # 3
            "",  # 4
            "1.1.  Notes",  # 5
            "",  # 6
            "   First notes.",  # 7
            "",  # 8
            "2.  Beta",  # 9
            "",  # 10
            "1.1.  Notes",  # 11
            "",  # 12
            "   Second notes.",  # 13
            "",
        ]
    )
    hold(capsys, txt_catalog, library, scripted, body)
    code, out = run(capsys, txt_catalog, "section", "RFC7777", "1.1")
    assert code == 0, out
    assert out.splitlines() == [
        "1 | 1 Alpha > 1.1 Notes | lines 5-8",
        "1 | 2 Beta > 1.1 Notes | lines 11-13",
    ]


# ------------------------------------------------------------------- AC-8


def test_page_section_prints_the_section_under_its_cite(held, txt_catalog, capsys):
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--section", "2.1.1")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "2.1.1 Version Field", 47, 50),
        row(47),
        row(48),
        row(49),
        row(50),
    ]
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--section", "absent")
    assert (code, out.strip()) == (2, "no matching section")


def test_find_prints_the_line_the_section_and_the_text(held, txt_catalog, capsys):
    code, out = run(capsys, txt_catalog, "find", "RFC7777", "one octet")
    assert code == 0, out
    assert out.splitlines() == ["RFC7777 l.49 | 2.1.1 Version Field | One octet."]
    code, out = run(capsys, txt_catalog, "find", "RFC7777", "one octet", "--case")
    assert (code, out.strip()) == (0, "no hits")


def test_page_prints_at_most_200_lines(txt_catalog, library, scripted, capsys):
    body = f"{AUTHOR}\n\n1.  Long\n\n" + "".join(
        f"   body line {i}\n" for i in range(250)
    )
    hold(capsys, txt_catalog, library, scripted, body)  # 254 lines
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "1-201")
    assert code == 2, out
    assert "200" in out and not said(out, "cite:")
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--section", "long")
    assert code == 2, out
    assert len(out.strip().splitlines()) == 1 and not said(out, "cite:")
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "1-200")
    assert code == 0, out
    assert len(out.splitlines()) == 201
    # B past the end is cut to the last line, as for md
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "250-999")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ")[2:5] == ["1 Long", "Text", "lines 250-254"]
    assert printed_numbers(lines[1:]) == [250, 251, 252, 253, 254]


COMPANION = f"{AUTHOR}\n\n1.  Extension\n\n   The idle timer is extended.\n"


def hits(out):
    wanted = ("RFC7777 l.", "RFC7778 l.")
    return [ln for ln in out.splitlines() if ln.startswith(wanted)]


def test_a_text_companion_is_searched_with_the_document(
    pair_catalog, library, scripted, capsys
):
    hold(capsys, pair_catalog, library, scripted, RFC_TEXT)
    scripted.responses[OTHER_URL] = ok(COMPANION.encode(), PLAIN)
    code, out = run(capsys, pair_catalog, "find", "RFC7777", "idle")
    assert code == 0, out
    assert hits(out) == [
        "RFC7778 l.5 | 1 Extension | The idle timer is extended.",
        "RFC7777 l.60 | A.1 Idle State | A.1.  Idle State",
    ]


def test_only_leaves_the_text_companion_out(pair_catalog, library, scripted, capsys):
    hold(capsys, pair_catalog, library, scripted, RFC_TEXT)
    scripted.responses[OTHER_URL] = ok(COMPANION.encode(), PLAIN)
    code, out = run(capsys, pair_catalog, "find", "RFC7777", "idle", "--only")
    assert code == 0, out
    assert out.splitlines() == ["RFC7777 l.60 | A.1 Idle State | A.1.  Idle State"]
    assert OTHER_URL not in scripted.calls


# ------------------------------------------------------------------ AC-10


def test_a_text_without_rfc_layout_is_read_by_its_lines(
    txt_catalog, library, scripted, capsys
):
    body = (
        "notes line one\n"
        "notes line two\n"
        "\n"
        "another paragraph\n"
        "of plain text\n"
        "  an indented remark\n"
    )
    vdir, out = hold(capsys, txt_catalog, library, scripted, body)
    assert said(out, f"extracted {LABEL}: 6 lines")
    assert outline_of(vdir) == []
    code, out = run(capsys, txt_catalog, "section", "RFC7777", "notes")
    assert (code, out.strip()) == (0, "no matching section")
    code, out = run(capsys, txt_catalog, "find", "RFC7777", "remark")
    assert (code, out.strip()) == (0, "RFC7777 l.6 | - | an indented remark")
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "4-6")
    assert code == 0, out
    assert out.splitlines() == [
        f"cite: ietf | {LABEL} | - | Text | lines 4-6 | {TXT_URL} | {vdir}",
        "4  another paragraph",
        "5  of plain text",
        "6    an indented remark",
    ]


# ------------------------------------------------------------------ AC-15


@pytest.mark.parametrize(
    "body, expected",
    [
        (
            "1.  Introduction\n\n   Body.\n\n2.  Next\n\n   More.\n",
            [(0, "1 Introduction", 1), (0, "2 Next", 5)],
        ),
        (
            "Review notes\n1.1 Scope\nColumn-0 text of the scope.\n\n"
            "2.  Rules\n\n   Rule text.\n",
            [(1, "1.1 Scope", 2), (0, "2 Rules", 5)],
        ),
        (
            "\n\n1.  Introduction\n\n   Body.\n",
            [(0, "1 Introduction", 3)],
        ),
    ],
    ids=["first-line", "inside-the-block", "after-blank-lines"],
)
def test_a_numbered_heading_in_the_first_block_is_in_the_outline(
    txt_catalog, library, scripted, capsys, body, expected
):
    # the other column-0 lines of the first block are not numbered, so they
    # stay out: only unnumbered headings wait for the block to end
    vdir, _ = hold(capsys, txt_catalog, library, scripted, body)
    assert outline_of(vdir) == expected


def test_a_heading_on_the_first_line_owns_its_section(
    txt_catalog, library, scripted, capsys
):
    body = "\n".join(
        [
            "1.  Introduction",  # 1
            "",  # 2
            "   Body of it.",  # 3
            "",  # 4
            "1.1.  Terms",  # 5
            "",  # 6
            "   A term.",  # 7
            "",  # 8
            "2.  Next",  # 9
            "",  # 10
            "   More.",  # 11
            "",
        ]
    )
    vdir, _ = hold(capsys, txt_catalog, library, scripted, body)
    code, out = run(capsys, txt_catalog, "section", "RFC7777", "1")
    assert code == 0, out
    assert out.splitlines() == [
        "0 | 1 Introduction | lines 1-8",
        "1 | 1.1 Terms | lines 5-8",
    ]
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "3-3")
    assert code == 0, out
    assert out.splitlines() == [
        cite(vdir, "1 Introduction", 3, 3),
        "3     Body of it.",
    ]


# ------------------------------------------------------------------ AC-16


@pytest.mark.parametrize(
    "tail", [[], ["", ""]], ids=["footer-last-line", "blank-lines-after"]
)
def test_a_footer_ending_a_paginated_file_without_a_form_feed_is_furniture(
    txt_catalog, library, scripted, capsys, tail
):
    # the synthetic RFC without its final form-feed line: the last page's
    # footer (line 69) is the last non-blank line
    body = "\n".join(RFC_LINES[:69] + tail) + "\n"
    vdir, out = hold(capsys, txt_catalog, library, scripted, body)
    assert said(out, f"extracted {LABEL}: {69 + len(tail)} lines")
    assert outline_of(vdir) == OUTLINE  # the footer is not a heading
    code, out = run(capsys, txt_catalog, "find", "RFC7777", "Informational")
    assert code == 0, out
    assert out.splitlines() == [f"RFC7777 l.3 | - | {RFC_LINES[2]}"]
    code, out = run(capsys, txt_catalog, "find", "RFC7777", "[Page")
    assert (code, out.strip()) == (0, "no hits")
    # the footer and the two blank lines padding it are not printed
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "64-69")
    assert code == 0, out
    assert out.splitlines() == [
        cite(vdir, "Acknowledgements", 64, 69),
        row(64),
        row(65),
        row(66),
    ]


def test_a_form_feed_on_the_header_line_is_a_page_break(
    txt_catalog, library, scripted, capsys
):
    body = "\n".join(
        [
            AUTHOR,  # 1
            "",  # 2
            "1.  Scope",  # 3
            "",  # 4
            "   Text that runs to the end of the first page and",  # 5
            "",  # 6: furniture from here ...
            FOOTER.format(n=1),  # 7
            "\f" + HEADER,  # 8
            "",  # 9: ... to here
            "   goes on after the page break.",  # 10
            "",  # 11
            "2.  Rules",  # 12
            "",  # 13
            "   Rule text.",  # 14
            "",
        ]
    )
    vdir, out = hold(capsys, txt_catalog, library, scripted, body)
    assert said(out, f"extracted {LABEL}: 14 lines")
    assert outline_of(vdir) == [(0, "1 Scope", 3), (0, "2 Rules", 12)]
    for pattern in ("[Page", "RFC 7777"):
        code, out = run(capsys, txt_catalog, "find", "RFC7777", pattern)
        assert (code, out.strip()) == (0, "no hits"), pattern
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "5-12")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == cite(vdir, "1 Scope; 2 Rules", 5, 12)
    assert printed_numbers(lines[1:]) == [5, 10, 11, 12]


def test_a_trailing_footer_in_a_file_without_a_form_feed_stays_text(
    txt_catalog, library, scripted, capsys
):
    body = "\n".join(
        [
            AUTHOR,  # 1
            "",  # 2
            "1.  Scope",  # 3
            "",  # 4
            "   Text of the scope.",  # 5
            "",  # 6
            FOOTER.format(n=1),  # 7
            "",
        ]
    )
    hold(capsys, txt_catalog, library, scripted, body)
    code, out = run(capsys, txt_catalog, "find", "RFC7777", "[Page 1]")
    assert code == 0, out
    assert len(out.splitlines()) == 1
    assert out.startswith("RFC7777 l.7 | ")
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "5-7")
    assert code == 0, out
    assert printed_numbers(out.splitlines()[1:]) == [5, 6, 7]


# ------------------------------------------------------------------ AC-17


def test_page_section_by_appendix_letter_prints_the_whole_appendix(
    held, txt_catalog, capsys
):
    # the first match of the letter is the appendix heading, not A.1
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--section", "A")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "Appendix A State Machine", 56, 63),
        *(row(n) for n in range(56, 64)),
    ]

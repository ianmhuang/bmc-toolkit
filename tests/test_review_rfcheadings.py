"""Reviewer acceptance tests for T81.2 (feature/ietf-rfcs), the heading
rules of a text version: a line starting with a lowercase letter or ending
in a colon is no unnumbered heading, so it no longer cuts its section short
(AC-4); the older appendix headings are level-0 headings found by their
letter, and ``A. Title`` stays one (AC-5); an extract written by the
previous extractor is stale and is redone (AC-6); ``markdown.labelled`` is
gone (AC-7).

Black-box through the CLI, plus ``outline.json`` and ``extract.json`` (the
Library layout the docs describe). The documents are synthetic, laid out as
the RFCs the criteria name are (a MIB in column 0 broken by a page, a table
legend, an ``APPENDIX A - Title`` heading); no RFC text is used. The
version string is a month, as the catalog's RFC versions are.
"""

import json

import pytest

from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG, ok

VERSION = "June 2026"
LABEL = f"RFC7777 {VERSION}"
TXT_URL = "https://example.test/rfc/rfc7777.txt"
PLAIN = "text/plain; charset=utf-8"

FOOTER = "Reviewer                 Informational                 [Page 1]"
HEADER = "RFC 7777          The Review Management Protocol         June 2026"

CATALOG = (
    MINI_CATALOG
    + f"""
[families.ietf]
title = "IETF RFCs"
publisher = "IETF"

[[documents]]
id = "RFC7777"
family = "ietf"
title = "The Review Management Protocol"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "{VERSION}"
url = "{TXT_URL}"
type = "txt"
published = "2026-06-01"
"""
)

FRONT = [
    "Example Task Force                              A. Reviewer",
    "Request for Comments: 7777                          Example",
    "Category: Informational                           June 2026",
    "",
    "               The Review Management Protocol",
    "",
    "Abstract",
    "",
    "   This memo describes a protocol made up for the review.",
    "",
]
SEC4 = "4.  Elements"
SEC5 = "5.  Definitions"
SEC6 = "6.  Security Considerations"
MIB_FOOT = "reviewStatsWrongDigests OBJECT-TYPE"
OLD_APPENDIX = "APPENDIX A - Installation"
A1 = "A.1.  Installation Parameters"
A2 = "A.2.  Password to Key"
LETTER_APPENDIX = "A. Host Configuration Parameters"


def mib_rfc(appendix=OLD_APPENDIX):
    """Laid out as RFC 3414 is: a MIB module in column 0 whose object line
    is the last text of page 1, then an appendix with A.n subsections."""
    return [
        *FRONT,
        SEC4,
        "",
        "   Elements come before the definitions.",
        "",
        SEC5,
        "",
        "REVIEW-MIB DEFINITIONS ::= BEGIN",
        "",
        "reviewStatsUnknownNames OBJECT-TYPE",
        "    SYNTAX       Counter32",
        "    ::= { reviewStats 1 }",
        "",
        MIB_FOOT,  # alone at the foot of the page
        "",  # furniture from here ...
        FOOTER,
        "\f",
        HEADER,
        "",  # ... to here
        "    SYNTAX       Counter32",
        "    ::= { reviewStats 2 }",
        "",
        "END",
        "",
        SEC6,
        "",
        "   Nothing to add.",
        "",
        appendix,
        "",
        A1,
        "",
        "   Parameters are listed here.",
        "",
        A2,
        "",
        "   Passwords are hashed.",
    ]


def legend_rfc():
    """Laid out as RFC 2131 ends: ``A. Title``, a table and its legend."""
    return [
        *FRONT,
        SEC4,
        "",
        "   Elements come before the appendix.",
        "",
        LETTER_APPENDIX,
        "",
        "   Parameter           Host      Router",
        "",
        "Key:",
        "",
        "   MAY = optional",
    ]


def stray_rfc(line):
    """Section 5 with ``line`` standing alone between two paragraphs."""
    return [
        *FRONT,
        SEC5,
        "",
        "   Body of the definitions.",
        "",
        line,
        "",
        "   More of the same section.",
        "",
        SEC6,
        "",
        "   Nothing to add.",
    ]


def number(lines, text):
    """The 1-based line number of the one line equal to ``text``."""
    assert lines.count(text) == 1, text
    return lines.index(text) + 1


@pytest.fixture
def txt_catalog(tmp_path):
    path = tmp_path / "txt_catalog.toml"
    path.write_text(CATALOG, encoding="utf-8", newline="")
    return path


def run(capsys, catalog, *argv):
    code = main(["--catalog", str(catalog), *argv])
    return code, capsys.readouterr().out


def said(out, prefix):
    return any(ln.startswith(prefix) for ln in out.splitlines())


def hold(capsys, catalog, library, scripted, lines):
    """Fetch RFC7777 with these lines as its body; the version directory."""
    body = ("\n".join(lines) + "\n").encode()
    scripted.responses[TXT_URL] = ok(body, PLAIN)
    code, out = run(capsys, catalog, "fetch", "RFC7777")
    assert code == 0, out
    holding = library.find("RFC7777", VERSION)
    assert holding is not None
    assert holding.original.name == "original.txt"
    return holding.path


def outline_of(vdir):
    entries = json.loads((vdir / "outline.json").read_text(encoding="utf-8"))
    return [(e["level"], e["title"], e["line"]) for e in entries]


def titles_of(vdir):
    return [title for _, title, _ in outline_of(vdir)]


def section(capsys, catalog, query):
    code, out = run(capsys, catalog, "section", "RFC7777", query)
    assert code == 0, out
    return out.splitlines()


def section_line(level, title, first, last):
    return f"{level} | {title} | lines {first}-{last}"


def status_row(capsys, catalog):
    code, out = run(capsys, catalog, "status")
    assert code == 0, out
    rows = [ln.split("\t") for ln in out.splitlines() if "\tRFC7777\t" in ln]
    assert len(rows) == 1, out
    return rows[0]


# ------------------------------------------------------------------- AC-4


def test_ac4_a_mib_line_alone_at_a_page_foot_does_not_cut_its_section(
    txt_catalog, library, scripted, capsys
):
    lines = mib_rfc()
    vdir = hold(capsys, txt_catalog, library, scripted, lines)
    assert MIB_FOOT not in titles_of(vdir)
    first, last = number(lines, SEC5), number(lines, SEC6) - 1
    assert number(lines, MIB_FOOT) < last  # the section runs past the page break
    assert section(capsys, txt_catalog, "5") == [
        section_line(0, "5 Definitions", first, last)
    ]
    # what follows the page break still belongs to section 5
    code, out = run(capsys, txt_catalog, "find", "RFC7777", "reviewStats 2")
    assert code == 0, out
    hit = number(lines, "    ::= { reviewStats 2 }")
    assert out.splitlines()[0].startswith(f"RFC7777 l.{hit} | 5 Definitions | ")


def test_ac4_a_legend_ending_in_a_colon_does_not_cut_the_appendix(
    txt_catalog, library, scripted, capsys
):
    lines = legend_rfc()
    vdir = hold(capsys, txt_catalog, library, scripted, lines)
    assert titles_of(vdir) == [
        "Abstract",
        "4 Elements",
        "A Host Configuration Parameters",
    ]
    # AC-5: `A. Title` is a level-0 numbered heading that `section DOC A`
    # finds; AC-4: it runs to the end of the file, past the legend
    first = number(lines, LETTER_APPENDIX)
    assert section(capsys, txt_catalog, "A") == [
        section_line(0, "A Host Configuration Parameters", first, len(lines))
    ]


@pytest.mark.parametrize(
    "line",
    [
        "reviewStatsWrongDigests OBJECT-TYPE",
        "where the fields are as follows",
        "Key:",
        "Legend for the table above:",
        "Key:   ",
    ],
    ids=["lowercase", "lowercase-words", "colon", "colon-words", "colon-spaces"],
)
def test_ac4_a_lowercase_start_or_a_trailing_colon_is_no_heading(
    txt_catalog, library, scripted, capsys, line
):
    lines = stray_rfc(line)
    vdir = hold(capsys, txt_catalog, library, scripted, lines)
    assert titles_of(vdir) == ["Abstract", "5 Definitions", "6 Security Considerations"]
    first, last = number(lines, SEC5), number(lines, SEC6) - 1
    assert section(capsys, txt_catalog, "5") == [
        section_line(0, "5 Definitions", first, last)
    ]


KEPT = [
    "Abstract",
    "Status of This Memo",
    "Copyright Notice",
    "Table of Contents",
    "1 Introduction",  # no dot: unnumbered, as T81.1 reads it
    "1.   Three spaces",
    "IANA Considerations",
    "Trademark Notice",
    "Acknowledgements",
    "Authors' Addresses",
    "Full Copyright Statement",
]


def test_ac4_the_usual_unnumbered_headings_are_all_kept(
    txt_catalog, library, scripted, capsys
):
    lines = FRONT[:4]
    for heading in KEPT:
        lines = [*lines, heading, "", "   Text under the heading.", ""]
    vdir = hold(capsys, txt_catalog, library, scripted, lines)
    expected = [
        (0, " ".join(heading.split()), number(lines, heading)) for heading in KEPT
    ]
    assert outline_of(vdir) == expected


def test_ac4_a_capitalised_line_between_paragraphs_is_still_a_heading(
    txt_catalog, library, scripted, capsys
):
    """The rule is the lowercase start and the colon, nothing wider."""
    lines = stray_rfc("Notation")
    vdir = hold(capsys, txt_catalog, library, scripted, lines)
    assert titles_of(vdir) == [
        "Abstract",
        "5 Definitions",
        "Notation",
        "6 Security Considerations",
    ]


# ------------------------------------------------------------------- AC-5


@pytest.mark.parametrize(
    "appendix",
    [
        "APPENDIX A - Installation",
        "Appendix A - Installation",
        "Appendix A: Installation",
        "Appendix A.  Installation",
    ],
    ids=["upper-dash", "dash", "colon", "dot"],
)
def test_ac5_an_older_appendix_heading_is_level_0_and_found_by_its_letter(
    txt_catalog, library, scripted, capsys, appendix
):
    lines = mib_rfc(appendix)
    vdir = hold(capsys, txt_catalog, library, scripted, lines)
    at, a1, a2 = number(lines, appendix), number(lines, A1), number(lines, A2)
    assert outline_of(vdir)[-3:] == [
        (0, "Appendix A Installation", at),
        (1, "A.1 Installation Parameters", a1),
        (1, "A.2 Password to Key", a2),
    ]
    assert section(capsys, txt_catalog, "A") == [
        section_line(0, "Appendix A Installation", at, len(lines)),
        section_line(1, "A.1 Installation Parameters", a1, a2 - 1),
        section_line(1, "A.2 Password to Key", a2, len(lines)),
    ]
    # section 6 ends where the appendix starts
    assert section(capsys, txt_catalog, "6") == [
        section_line(0, "6 Security Considerations", number(lines, SEC6), at - 1)
    ]


def test_ac5_the_older_appendix_heading_is_cited_by_its_label(
    txt_catalog, library, scripted, capsys
):
    lines = mib_rfc()
    hold(capsys, txt_catalog, library, scripted, lines)
    first, last = number(lines, OLD_APPENDIX), number(lines, A1)
    code, out = run(
        capsys, txt_catalog, "page", "RFC7777", "--lines", f"{first}-{last}"
    )
    assert code == 0, out
    fields = out.splitlines()[0].split(" | ")
    assert fields[:5] == [
        "cite: ietf",
        LABEL,
        "Appendix A Installation; A.1 Installation Parameters",
        "Text",
        f"lines {first}-{last}",
    ]


# ------------------------------------------------------------------- AC-6


def test_ac6_an_extract_of_the_previous_extractor_is_stale_and_redone(
    txt_catalog, library, scripted, capsys
):
    lines = mib_rfc()
    vdir = hold(capsys, txt_catalog, library, scripted, lines)
    meta_path = vdir / "extract.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["kind"] == "text"
    assert meta["extractor_version"] >= 2
    assert status_row(capsys, txt_catalog)[5] == "extracted"
    # what the extractor before this change left behind: version 1 and an
    # Outline with the page-foot MIB line as a heading
    old = [
        (0, "5 Definitions", number(lines, SEC5)),
        (0, MIB_FOOT, number(lines, MIB_FOOT)),
    ]
    meta["extractor_version"] = 1
    meta_path.write_text(json.dumps(meta), encoding="utf-8", newline="")
    (vdir / "outline.json").write_text(
        json.dumps([{"level": lv, "title": t, "line": ln} for lv, t, ln in old]),
        encoding="utf-8",
        newline="",
    )
    assert status_row(capsys, txt_catalog)[5] == "stale"
    # a reading command extracts it again by itself
    code, out = run(capsys, txt_catalog, "section", "RFC7777", "5")
    assert code == 0, out
    assert said(out, f"extracted {LABEL}:")
    first, last = number(lines, SEC5), number(lines, SEC6) - 1
    assert section_line(0, "5 Definitions", first, last) in out.splitlines()
    assert MIB_FOOT not in titles_of(vdir)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["extractor_version"] >= 2
    assert status_row(capsys, txt_catalog)[5] == "extracted"


# ------------------------------------------------------------------- AC-7


def test_ac7_the_markdown_module_no_longer_exports_labelled():
    from bmc_toolkit.spec import markdown

    assert not hasattr(markdown, "labelled")
    assert "labelled" not in markdown.__all__

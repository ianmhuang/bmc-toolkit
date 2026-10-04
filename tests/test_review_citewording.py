"""Reviewer acceptance tests for the Citation rules of SKILL.md (AC-1 to
AC-4).

The forms are not written down here. They are read from the ``cite:``
lines ``page`` and ``render`` print for a synthetic PDF, held once as a
download and once as a Drop-in, and the Citation rules have to agree with
those lines. On develop the rendered-page rule asks for quoted words the
printed line does not hold, the line-number rule gives no written form,
the as-printed rule names no rule that lets a field be cut, and neither
rule that keeps a ``user-provided`` origin keeps the Library path.
"""

import re
from pathlib import Path

import pytest

from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"

URL = "https://example.test/DSP0236_1.3.3.pdf"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def flat(text):
    """Text on one line, so a form is found across a line break."""
    return " ".join(text.split())


def bullets():
    """The rules of `## Citation rules`, each on one line."""
    text = SKILL.read_text("utf-8")
    start = text.index("\n## Citation rules\n")
    body = text[start : text.index("\n## ", start + 1)]
    return [flat(part) for part in re.split(r"\n- ", body)[1:]]


def rule(*words):
    """The one rule that holds every one of ``words``."""
    found = [b for b in bullets() if all(word in b for word in words)]
    assert len(found) == 1, (words, found)
    return found[0]


def sentences(text):
    return re.split(r"(?<=\.) ", text)


def numbered_doc(tmp_path):
    """Three pages with printed line numbers 100-117 and bookmarks."""
    page1 = pdfgen.numbered_page(
        100,
        [
            "Running header text",
            "1 Introduction",
            "This document describes the widget bus.",
            "2 Scope",
            "The scope covers frobnication only.",
            "Frobnicate command summary",
        ],
    )
    page2 = pdfgen.numbered_page(
        106,
        [
            "Scope continues here",
            "3 Commands",
            "3.1 Frobnicate",
            "Frobnicate sets the FROB bit.",
            "Reserved fields are zero.",
            "3.2 Reset",
        ],
    )
    page3 = pdfgen.numbered_page(
        112,
        [
            "Reset clears the FROB bit.",
            "Reserved fields are zero.",
            "3.10 Extra",
            "row a",
            "row b",
            "row c",
        ],
    )
    return pdfgen.write_pdf(
        tmp_path / "numbered.pdf",
        [page1, page2, page3],
        bookmarks=[
            (0, "1 Introduction", 0),
            (0, "2 Scope", 0),
            (0, "3 Commands", 1),
            (1, "3.1 Frobnicate", 1),
            (1, "3.2 Reset", 1),
            (1, "3.10 Extra", 2),
        ],
    ).read_bytes()


def cite_fields(out):
    """The fields of the one `cite:` line in a command's output."""
    cites = [ln for ln in out.splitlines() if ln.startswith("cite: ")]
    assert len(cites) == 1, out
    fields = cites[0].split(" | ")
    assert len(fields) == 7, fields
    return fields


@pytest.fixture
def downloaded(catalog_file, library, scripted, tmp_path, capsys):
    """DSP0236 1.3.3 held from its catalog URL and extracted."""
    scripted.responses[URL] = ok(numbered_doc(tmp_path))
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


@pytest.fixture
def dropped_in(catalog_file, library, tmp_path, capsys):
    """The same document held as a Drop-in and extracted."""
    mine = tmp_path / "mine.pdf"
    mine.write_bytes(numbered_doc(tmp_path))
    code, out = run(
        capsys,
        "add",
        str(mine),
        "--document",
        "DSP0236",
        "--version",
        "1.3.3",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


# ---------------------------------------------------------------- AC-1


def test_the_as_printed_rule_points_at_the_rules_that_let_a_field_be_cut(
    downloaded, catalog_file, capsys
):
    """AC-1: the rule that keeps the fields as printed says where the two
    exceptions are, a narrowed line range and a cut-down section field,
    and stands before the two rules it points at."""
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    fields = cite_fields(out)
    # the two fields a later rule lets an answer cut: a section field with
    # more than one entry, and a line range
    assert "; " in fields[2], fields
    assert re.fullmatch(r"lines \d+-\d+", fields[4]), fields

    rules = bullets()
    keep = rule("as printed")
    assert re.search(r"\brules?\b", keep), keep
    assert "range" in keep, keep
    assert "section field" in keep, keep

    line_rule = rule("Line numbers")
    section_rule = rule("section field lists")
    assert rules.index(keep) < rules.index(line_rule)
    assert rules.index(keep) < rules.index(section_rule)
    # the two rules still allow what they allowed
    assert "range" in line_rule and "used" in line_rule
    assert "entries" in section_rule and "whole" in section_rule


# ---------------------------------------------------------------- AC-2


def test_every_rule_that_keeps_a_user_provided_origin_keeps_the_library_path(
    dropped_in, catalog_file, capsys
):
    """AC-2: a Citation whose origin reads `user-provided` keeps the origin
    and the Library path; the sentence on Confidential documents stays."""
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    fields = cite_fields(out)
    origin = fields[5]
    assert origin == "user-provided"
    assert fields[6] == str(dropped_in)

    naming = [b for b in bullets() if origin in b]
    assert naming, "no rule names the origin a Drop-in prints"
    for text in naming:
        # the sentence that keeps the origin goes on to keep the path
        after = sentences(text.split(origin, 1)[1])[0]
        assert "Library path" in after, text

    confidential = [
        s for s in sentences(rule("Confidential")) if "Confidential" in s
    ]
    assert len(confidential) == 1, confidential
    assert "by path" in confidential[0] and "URL" in confidential[0]


# ---------------------------------------------------------------- AC-3


def test_the_rendered_page_rule_asks_for_nothing_render_does_not_print(
    downloaded, catalog_file, capsys
):
    """AC-3: a rendered page is cited with the line `render` printed; the
    rule names the lines field of that line and no words outside it."""
    code, out = run(
        capsys, "render", "DSP0236", "--page", "2", catalog_file=catalog_file
    )
    assert code == 0, out
    fields = cite_fields(out)
    printed = " | ".join(fields)

    text = rule("PNG")
    assert "`cite:`" in text and "`render`" in text, text
    # the lines field is named the way `render` prints it
    assert f"`{fields[4]}`" in text, text
    # words the rule puts in quotes are words of the printed line
    for quoted in re.findall(r'"([^"]+)"', text):
        assert quoted in printed, quoted


# ---------------------------------------------------------------- AC-4


def test_the_line_number_rule_gives_a_form_for_one_line_and_for_several(
    downloaded, catalog_file, capsys
):
    """AC-4: one line is written `lines N`, several as the range form the
    tool prints; the rule still ties line numbers to the `page` output and
    still asks for the range used."""
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    printed = cite_fields(out)[4]
    assert re.fullmatch(r"lines \d+-\d+", printed), printed

    text = rule("Line numbers")
    forms = re.findall(r"`(lines [^`]+)`", text)
    shapes = [re.sub(r"[A-Z]", "X", form) for form in forms]
    # several lines: the printed shape, its numbers as placeholders
    assert shapes.count(re.sub(r"\d+", "X", printed)) == 1, forms
    # one line: a single number behind `lines`
    assert shapes.count("lines X") == 1, forms

    assert "`page`" in text and "printed" in text, text
    assert "whole range" in text, text

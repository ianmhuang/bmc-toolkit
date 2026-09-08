"""Reviewer acceptance tests for AC-5: the Notes citation parsers accept a
section field holding several "; "-joined titles, in the cite: form and in
the prose form, and a Note's section titles are the parts. The parsers are
named by the AC, so the notes module is exercised directly; the serving
side is checked once through the CLI."""

import json

import pytest

from bmc_toolkit.spec import notes as N
from bmc_toolkit.spec.cli import main
from tests.conftest import ok
from tests.test_search_cli import URL, mctp_pdf

pytest.importorskip("pypdfium2")

SPAN = (
    "6 Symbols and abbreviated terms; 7 SPDM message exchanges; "
    "7.1 Request and response messages; 7.2 Generic SPDM message format"
)
assert len(SPAN) > 80  # longer than the prose form used to allow

CITE_LINE = (
    f"cite: spdm | DSP0274 1.4.1 | {SPAN} | PDF page 27 | lines 1-9 | "
    "https://example.test/DSP0274_1.4.1.pdf | /lib"
)
PROSE_LINE = f"DSP0274 1.4.1, §{SPAN}, PDF pp.27-28, lines 1-9."
STORED = f"DSP0274 1.4.1 | {SPAN} | PDF page 27"
TIME = "2026-09-08T01:02:03+00:00"


def test_cite_form_with_a_spanning_section_field_is_stored_whole():
    assert N.find_cites("Answer.\n" + CITE_LINE + "\n") == [STORED]


def test_prose_form_with_a_long_spanning_section_field_is_a_citation():
    assert N.find_cites("As " + PROSE_LINE) == [
        f"DSP0274 1.4.1 | {SPAN} | PDF pages 27-28"
    ]
    # the prose form still stops at the first comma after the section
    text = "DSP0274 1.4.1, §7 SPDM message exchanges, PDF p.27, lines 1-3."
    assert N.find_cites(text) == ["DSP0274 1.4.1 | 7 SPDM message exchanges | PDF page 27"]


def test_a_note_from_such_an_answer_has_one_section_title_per_part():
    made = N.make_note("q", "", "One request, one response.\n" + CITE_LINE, TIME)
    assert made is not None
    assert made.cites == (STORED,)
    assert made.sections() == [
        "6 Symbols and abbreviated terms",
        "7 SPDM message exchanges",
        "7.1 Request and response messages",
        "7.2 Generic SPDM message format",
    ]
    assert made.pages() == "DSP0274 1.4.1 p.27"
    # the prose form yields a Note too (it did not before the field grew)
    prose = N.make_note("q", "", "Short.\n" + PROSE_LINE, TIME)
    assert prose is not None
    assert prose.sections()[-1] == "7.2 Generic SPDM message format"


def test_a_single_title_section_field_is_one_part():
    made = N.make_note(
        "q",
        "",
        "cite: mctp | DSP0236 1.3.3 | 8.1 Overview | PDF page 1 | lines 1-2 | u | p",
        TIME,
    )
    assert made is not None and made.sections() == ["8.1 Overview"]


def test_every_part_is_a_matching_term_on_its_own():
    made = N.make_note("問題", "", "答。\n" + CITE_LINE, TIME)
    assert made is not None
    assert N.matches("abbreviated terms", made)
    assert N.matches("generic format", made)
    assert N.matches("request response", made)


# ------------------------------------------------- serving through the CLI


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(mctp_pdf(tmp_path))
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def test_find_serves_a_note_whose_cite_spans_sections(
    held, library, capsys, catalog_file
):
    library.root.mkdir(parents=True, exist_ok=True)
    (library.root / "config.toml").write_text("[library]\nnotes = true\n", encoding="utf-8")
    span = "8 MCTP base protocol; 8.1 Overview; 8.2 MCTP packet fields"
    cite = (
        f"cite: mctp | DSP0236 1.3.3 | {span} | PDF page 1 | lines 100-105 | "
        f"{URL} | /lib"
    )
    note = {
        "id": "eeee0001",
        "question": "封包欄位有哪些？",
        "context": "",
        "answer": "The fields follow.\n\n" + cite,
        "partial": False,
        "cites": [f"DSP0236 1.3.3 | {span} | PDF page 1"],
        "documents": [["DSP0236", "1.3.3"]],
        "time": TIME,
    }
    (library.root / "notes.jsonl").write_text(
        json.dumps(note, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    # "packet" is only in the third part of the section field
    code, out = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "notes DSP0236 1.3.3: 1"
    assert lines[1] == "eeee0001 2026-09-08 | 封包欄位有哪些？ | DSP0236 1.3.3 p.1"
    assert "note: answer from a Note of 2026-09-08 (eeee0001)" in out
    assert cite in lines

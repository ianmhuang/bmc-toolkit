"""Reviewer acceptance tests for the commands that do not read a Markdown
version, ``--lines`` on a PDF, and Notes beside Markdown (AC-12, AC-13).

Black-box through the CLI, except the two Notes functions the Stop hook
records through (``find_cites``, ``make_note``): AC-13 is about what they
skip. The document is the synthetic one of ``test_review_mdlibrary``.
"""

import pytest

from bmc_toolkit.spec import notes as notes_mod
from tests.conftest import PDF_BYTES, ok
from tests.test_review_mdlibrary import (
    MD_BYTES,
    MD_CATALOG,
    MD_URL,
    PLAIN,
    run,
    said,
    version_dir,
)

PDF_URL = "https://example.test/DSP0236_1.3.3.pdf"
POINTER = (
    "RVW 1.0 is a Markdown document with no pages; read it with: "
    "bmcspec page RVW --section QUERY, or: bmcspec page RVW --lines A-B"
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
    scripted.calls.clear()
    return version_dir(library)


# ------------------------------------------------------------------ AC-12

PAGE_COMMANDS = [
    ["page", "RVW", "3"],
    ["page", "RVW", "3", "--to", "4"],
    ["render", "RVW", "--page", "3"],
    ["table", "RVW", "--page", "3"],
]


def check_pointer(argv, code, out):
    assert code == 2, out
    text = out.strip()
    assert len(text.splitlines()) == 1, out
    if argv[0] == "table":
        assert text.startswith(POINTER)
        rest = text[len(POINTER) :]
        assert "tables" in rest and "text" in rest and "page" in rest
    else:
        assert text == POINTER


@pytest.mark.parametrize("argv", PAGE_COMMANDS, ids=lambda a: " ".join(a))
def test_commands_that_need_pages_point_to_page_before_any_download(
    md_catalog, library, scripted, capsys, argv
):
    scripted.responses[MD_URL] = ok(MD_BYTES, PLAIN)  # reachable, and not asked
    code, out = run(capsys, md_catalog, *argv)
    check_pointer(argv, code, out)
    assert scripted.calls == []
    assert not (version_dir(library) / "original.md").exists()


@pytest.mark.parametrize("argv", PAGE_COMMANDS, ids=lambda a: " ".join(a))
def test_commands_that_need_pages_point_to_page_on_a_held_version(
    md_catalog, library, scripted, capsys, argv
):
    scripted.responses[MD_URL] = ok(MD_BYTES, PLAIN)
    code, out = run(capsys, md_catalog, "fetch", "RVW", "--no-extract")
    assert code == 0, out
    scripted.calls.clear()
    code, out = run(capsys, md_catalog, *argv)
    check_pointer(argv, code, out)
    assert scripted.calls == []


def check_lines_on_a_pdf(code, out):
    assert code == 2, out
    text = out.strip()
    assert len(text.splitlines()) == 1, out
    assert "--lines" in text and "Markdown" in text
    assert "DSP0236 1.3.3" in text
    assert "page number" in text and "--section" in text


def test_lines_on_a_pdf_version_is_refused_before_any_download(
    md_catalog, library, scripted, capsys
):
    scripted.responses[PDF_URL] = ok(PDF_BYTES)  # reachable, and not asked
    code, out = run(capsys, md_catalog, "page", "DSP0236", "--lines", "1-5")
    check_lines_on_a_pdf(code, out)
    assert scripted.calls == []
    assert not (library.specs / "mctp" / "DSP0236").exists()


def test_lines_on_a_held_pdf_version_is_refused_without_extracting(
    md_catalog, library, scripted, capsys
):
    scripted.responses[PDF_URL] = ok(PDF_BYTES)
    code, out = run(capsys, md_catalog, "fetch", "DSP0236", "--no-extract")
    assert code == 0, out
    scripted.calls.clear()
    code, out = run(capsys, md_catalog, "page", "DSP0236", "--lines", "1-5")
    check_lines_on_a_pdf(code, out)
    assert scripted.calls == []
    assert not (library.specs / "mctp" / "DSP0236" / "1.3.3" / "extract.json").exists()


@pytest.mark.parametrize("command", ["schema", "registry"])
def test_schema_and_registry_call_a_held_md_version_a_markdown_document(
    held, md_catalog, scripted, capsys, command
):
    code, out = run(capsys, md_catalog, command, "RVW")
    assert code == 2, out
    text = out.strip()
    assert text.startswith("RVW 1.0 is a Markdown document")
    assert "PDF document" not in text
    assert "bmcspec find RVW PATTERN" in text
    assert scripted.calls == []


@pytest.mark.parametrize("command", ["schema", "registry"])
def test_schema_and_registry_say_markdown_before_any_download(
    md_catalog, library, scripted, capsys, command
):
    scripted.responses[MD_URL] = ok(MD_BYTES, PLAIN)  # reachable, and not asked
    code, out = run(capsys, md_catalog, command, "RVW")
    assert code == 2, out
    text = out.strip()
    assert text.startswith("RVW 1.0 is a Markdown document")
    assert "PDF document" not in text
    assert scripted.calls == []
    assert not (version_dir(library) / "original.md").exists()


# ------------------------------------------------------------------ AC-13


def md_cite(capsys, md_catalog):
    code, out = run(capsys, md_catalog, "page", "RVW", "--lines", "16-17")
    assert code == 0, out
    cite = out.splitlines()[0]
    assert cite.startswith("cite: security | RVW 1.0 | ") and " | Markdown | " in cite
    return cite


def test_a_markdown_cite_is_not_recorded(held, md_catalog, capsys):
    cite = md_cite(capsys, md_catalog)
    answer = f"The reset vector is fixed.\n\n{cite}\n"
    assert notes_mod.find_cites(answer) == []
    assert notes_mod.make_note("where is the reset vector?", "", answer, "t") is None
    # quoted inline, without the prefix, it is still not one
    inline = cite.removeprefix("cite: ")
    assert notes_mod.find_cites(f"See {inline} for the vector.") == []


def test_a_pdf_cite_beside_a_markdown_cite_is_the_only_one_recorded(
    held, md_catalog, capsys
):
    cite = md_cite(capsys, md_catalog)
    pdf_cite = (
        "cite: mctp | DSP0236 1.3.3 | 8 Overview | PDF page 24 | lines 310-340 | "
        "https://example.test/DSP0236_1.3.3.pdf | /library/specs/mctp/DSP0236/1.3.3"
    )
    answer = f"Both say so.\n\n{cite}\n{pdf_cite}\n"
    found = notes_mod.find_cites(answer)
    assert len(found) == 1, found
    assert found[0].startswith("DSP0236 1.3.3 | ") and "RVW" not in found[0]
    note = notes_mod.make_note("which documents say so?", "", answer, "t")
    assert note is not None
    assert [d for d, _ in note.documents] == ["DSP0236"]


def notes_on(library):
    (library.root / "config.toml").write_text(
        "[library]\nnotes = true\n", encoding="utf-8", newline=""
    )


READS = [
    (["find", "RVW", "scope"], 4),
    (["find", "RVW", "preamble", "--context", "1"], 3),
    (["find", "RVW", "nowhere in the file"], 1),
    (["section", "RVW", "4"], 2),
    (["section", "RVW", "no such heading"], 1),
]


def test_find_and_section_print_their_normal_output_with_notes_on(
    held, md_catalog, library, capsys
):
    plain = [run(capsys, md_catalog, *argv) for argv, _ in READS]
    for (_, count), (code, out) in zip(READS, plain, strict=True):
        assert code == 0 and len(out.splitlines()) == count, out
    notes_on(library)
    assert [run(capsys, md_catalog, *argv) for argv, _ in READS] == plain


def test_find_and_section_keep_their_output_when_a_note_cites_the_document(
    held, md_catalog, library, capsys
):
    plain = [run(capsys, md_catalog, *argv) for argv, _ in READS]
    notes_on(library)
    # A Note keyed to the same document and version (as an earlier PDF
    # answer would leave it): the serving path now runs on a Markdown version.
    pdf_cite = (
        f"cite: security | RVW 1.0 | Boot flow | PDF page 2 | lines - | {MD_URL} | "
        f"{held}"
    )
    note = notes_mod.make_note(
        "what is the scope?", "", f"It boots.\n\n{pdf_cite}\n", "2026-11-01T00:00:00Z"
    )
    assert note is not None
    (library.root / notes_mod.NOTES_NAME).write_text(
        note.to_json() + "\n", encoding="utf-8", newline=""
    )
    for (argv, _), (_, before) in zip(READS, plain, strict=True):
        code, out = run(capsys, md_catalog, *argv)
        assert code == 0, out
        assert not said(out, "note: notes:"), out  # the Notes did not fail
        assert said(out, "notes RVW 1.0: 1"), out
        # every line of the normal output is still there, in order
        kept = [ln for ln in out.splitlines() if ln in before.splitlines()]
        assert kept == before.splitlines(), out

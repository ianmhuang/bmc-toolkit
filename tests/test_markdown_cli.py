"""Markdown versions (type md) through the CLI: catalog, fetch, add, scan,
extract, status, section, find, page, the commands that refuse them, and
Notes. No PDF is extracted here, so these run without pypdfium2."""

import json

import pytest

from bmc_toolkit.spec import notes as notes_mod
from bmc_toolkit.spec.cli import main
from bmc_toolkit.spec.library import Library
from tests.conftest import HTML_BYTES, MINI_CATALOG, PDF_BYTES, ok
from tests.test_markdown import MD_TEXT

MD_URL = "https://example.test/raw/abc123/doc/RoT.md"
PDF_URL = "https://example.test/rot-2.0.pdf"
PLAIN = "text/plain; charset=utf-8"

MD_CATALOG = (
    MINI_CATALOG
    + """
[families.security]
title = "Security"
publisher = "various"

[[documents]]
id = "ROT"
family = "security"
title = "A root of trust specification"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "2.1"
url = "https://example.test/raw/abc123/doc/RoT.md"
type = "md"
published = "2026-09-17"

[[documents]]
id = "ROTMIX"
family = "security"
title = "Released as PDF, next revision drafted in Markdown"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "2.0"
url = "https://example.test/rot-2.0.pdf"
type = "pdf"
published = "2025-07-31"

[[documents.versions]]
version = "2.1"
url = "https://example.test/raw/abc123/doc/RoT.md"
type = "md"
published = "2026-09-17"
wip = true
"""
)

POINTER = (
    "ROT 2.1 is a Markdown document with no pages; read it with: "
    "bmcspec page ROT --section QUERY, or: bmcspec page ROT --lines A-B"
)


@pytest.fixture
def md_catalog(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(MD_CATALOG, encoding="utf-8", newline="")
    return path


def run(capsys, catalog, *argv):
    code = main(["--catalog", str(catalog), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def held(md_catalog, library, scripted, capsys):
    """ROT 2.1 fetched (and extracted by fetch)."""
    scripted.responses[MD_URL] = ok(MD_TEXT.encode(), PLAIN)
    code, out = run(capsys, md_catalog, "fetch", "ROT")
    assert code == 0, out
    return library.specs / "security" / "ROT" / "2.1"


# ------------------------------------------------------------- catalog


def test_catalog_lists_the_md_type(md_catalog, capsys):
    code, out = run(capsys, md_catalog, "catalog", "ROT")
    assert code == 0
    assert "\t2.1\t2026-09-17\tmd\t" in out


def test_an_unknown_type_names_md_among_the_types(tmp_path, capsys):
    path = tmp_path / "catalog.toml"
    path.write_text(MD_CATALOG.replace('type = "md"', 'type = "txt"', 1), "utf-8")
    code, out = run(capsys, path, "catalog")
    assert code == 1
    assert "'txt' not one of ('pdf', 'zip', 'md')" in out


# --------------------------------------------------------------- fetch


def test_fetch_stores_original_md_and_extracts(md_catalog, library, scripted, capsys):
    scripted.responses[MD_URL] = ok(MD_TEXT.encode(), PLAIN)
    code, out = run(capsys, md_catalog, "fetch", "ROT")
    assert code == 0, out
    vdir = library.specs / "security" / "ROT" / "2.1"
    assert (vdir / "original.md").read_bytes() == MD_TEXT.encode()
    assert "fetched ROT 2.1 via direct" in out
    assert "extracted ROT 2.1: 24 lines, outline headings (6 entries)" in out
    meta = json.loads((vdir / "meta.json").read_text("utf-8"))
    assert meta["file"] == "original.md"


def test_fetch_of_an_html_page_falls_through_and_names_original_md(
    md_catalog, library, scripted, capsys
):
    scripted.responses[MD_URL] = ok(HTML_BYTES, "text/html")
    code, out = run(capsys, md_catalog, "fetch", "ROT")
    assert code == 2
    assert f"direct: not a md (text/html, {len(HTML_BYTES)} bytes)" in out
    assert "failed ROT 2.1" in out
    assert "original.md" in out
    assert "Traceback" not in out
    assert not (library.specs / "security" / "ROT" / "2.1" / "original.md").exists()


def test_fetch_refuses_a_binary_body(md_catalog, scripted, capsys):
    """A binary body is not Markdown either."""
    scripted.responses[MD_URL] = ok(b"\x89PNG\r\n\x1a\n", "image/png")
    code, out = run(capsys, md_catalog, "fetch", "ROT")
    assert code == 2
    assert "not a md (image/png, 8 bytes)" in out


# ---------------------------------------------------------- add / scan


def test_add_a_markdown_file(md_catalog, library, tmp_path, capsys):
    source = tmp_path / "RoT.md"
    source.write_text(MD_TEXT, "utf-8")
    code, out = run(
        capsys, md_catalog, "add", str(source), "--document", "ROT", "--version", "2.1"
    )
    assert code == 0, out
    vdir = library.specs / "security" / "ROT" / "2.1"
    assert out.splitlines()[-1] == f"added ROT 2.1 as Drop-in at {vdir}"
    assert (vdir / "original.md").is_file()


def test_add_refuses_an_html_page_saved_as_md(md_catalog, tmp_path, capsys):
    source = tmp_path / "saved.md"
    source.write_bytes(HTML_BYTES)
    code, out = run(
        capsys, md_catalog, "add", str(source), "--document", "ROT", "--version", "2.1"
    )
    assert code == 2
    assert out.strip() == f"{source} is not a md (wrong leading bytes); not added"


def test_add_names_md_among_the_accepted_types(md_catalog, tmp_path, capsys):
    source = tmp_path / "notes.txt"
    source.write_text("x", "utf-8")
    code, out = run(
        capsys, md_catalog, "add", str(source), "--document", "ROT", "--version", "2.1"
    )
    assert code == 2
    assert out.strip() == "unsupported file type '.txt': expected .pdf, .zip or .md"


def test_scan_registers_original_md_and_skips_a_bad_one(md_catalog, library, capsys):
    good = library.specs / "security" / "ROT" / "2.1"
    good.mkdir(parents=True)
    (good / "original.md").write_text(MD_TEXT, "utf-8")
    bad = library.specs / "security" / "ROT" / "2.2"
    bad.mkdir(parents=True)
    (bad / "original.md").write_bytes(HTML_BYTES)
    code, out = run(capsys, md_catalog, "scan")
    assert code == 0
    assert "registered ROT 2.1 as Drop-in" in out
    assert f"skipped {bad}: 'original.md' is not a md (wrong leading bytes)" in out
    assert out.strip().endswith("scan: registered 1, skipped 1")


# ------------------------------------------------------ extract / status


def status_row(capsys, catalog, document):
    _, out = run(capsys, catalog, "status")
    rows = [ln.split("\t") for ln in out.splitlines() if f"\t{document}\t" in ln]
    assert len(rows) == 1, out
    return rows[0]


def test_status_shows_extracted_headings_then_stale(held, md_catalog, capsys):
    row = status_row(capsys, md_catalog, "ROT")
    assert row[5:] == ["extracted", "headings"]
    meta_path = held / "extract.json"
    meta = json.loads(meta_path.read_text("utf-8"))
    meta["extractor_version"] = 0
    meta_path.write_text(json.dumps(meta), "utf-8")
    row = status_row(capsys, md_catalog, "ROT")
    assert row[5] == "stale"
    # a reading command extracts it again
    code, out = run(capsys, md_catalog, "section", "ROT", "fuses")
    assert code == 0
    assert out.startswith("extracted ROT 2.1: 24 lines")


def test_extract_again_is_skipped_and_force_redoes_it(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "extract", "ROT")
    assert (code, out.strip()) == (0, "skipped ROT 2.1: already extracted")
    code, out = run(capsys, md_catalog, "extract", "ROT", "--force")
    assert code == 0
    assert out.strip() == "extracted ROT 2.1: 24 lines, outline headings (6 entries)"


def test_extract_all_takes_markdown_along(held, md_catalog, capsys):
    (held / "extract.json").unlink()
    code, out = run(capsys, md_catalog, "extract", "--all")
    assert code == 0
    assert "extracted ROT 2.1: 24 lines" in out
    assert "summary: extracted 1, skipped 0, failed 0" in out


def test_a_reading_command_fetches_and_extracts_first(
    md_catalog, library, scripted, capsys
):
    scripted.responses[MD_URL] = ok(MD_TEXT.encode(), PLAIN)
    code, out = run(capsys, md_catalog, "find", "ROT", "zeroize")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[-1] == "ROT l.17 | 5.2 Zeroization | Zeroize the fuse."
    assert any(ln.startswith("fetched ROT 2.1") for ln in lines)
    assert any(ln.startswith("extracted ROT 2.1") for ln in lines)


# ------------------------------------------------------------- section


def test_section_prints_line_ranges(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "section", "ROT", "goals")
    assert code == 0
    assert out.splitlines() == [
        "1 | Introduction > Goals | lines 6-12",
        "1 | Fuses > Goals | lines 14-17",
    ]
    code, out = run(capsys, md_catalog, "section", "ROT", "5.2")
    assert out.splitlines() == ["2 | 5.2 Zeroization | lines 16-17"]
    code, out = run(capsys, md_catalog, "section", "ROT", "absent words")
    assert (code, out.strip()) == (0, "no matching section")


# ---------------------------------------------------------------- find


def test_find_prints_file_lines_and_context(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "find", "ROT", "goal", "--context", "1")
    assert code == 0
    assert out.splitlines() == [
        "ROT l.6 | Introduction > Goals | ## Goals",
        "    line 5: ",
        "    line 7: Goal one: the fuse.",
        "--",
        "ROT l.7 | Introduction > Goals | Goal one: the fuse.",
        "    line 6: ## Goals",
        "    line 8: ",
        "--",
        "ROT l.14 | Fuses > Goals | ## Goals",
        "    line 13: # Fuses",
        "    line 15: Fuse goal text.",
        "--",
        "ROT l.15 | Fuses > Goals | Fuse goal text.",
        "    line 14: ## Goals",
        "    line 16: ### 5.2 Zeroization ###",
        "--",
    ]


def test_find_limits_and_misses(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "find", "ROT", "fuse", "--max", "2")
    assert code == 0
    assert out.splitlines()[-1] == (
        "3 more hits not shown; narrow the pattern or raise --max"
    )
    code, out = run(capsys, md_catalog, "find", "ROT", "Fuse", "--case")
    assert [ln.split(" | ")[0] for ln in out.splitlines()] == ["ROT l.13", "ROT l.15"]
    code, out = run(capsys, md_catalog, "find", "ROT", "nowhere")
    assert (code, out.strip()) == (0, "no hits")
    code, out = run(capsys, md_catalog, "find", "ROT", "(", "--regex")
    assert code == 2 and out.startswith("bad regular expression")


def test_a_hit_before_the_first_heading_has_no_section(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "find", "ROT", "title page")
    assert out.strip() == "ROT l.1 | - | <p>Title page</p>"


# ---------------------------------------------------------------- page


def test_page_lines_prints_cite_and_numbered_lines(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "page", "ROT", "--lines", "14-17")
    assert code == 0
    assert out.splitlines() == [
        "cite: security | ROT 2.1 | Fuses > Goals; 5.2 Zeroization | Markdown | "
        f"lines 14-17 | {MD_URL} | {held}",
        "14  ## Goals",
        "15  Fuse goal text.",
        "16  ### 5.2 Zeroization ###",
        "17  Zeroize the fuse.",
    ]


def test_page_lines_clamps_the_end(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "page", "ROT", "--lines", "23-99")
    assert code == 0
    lines = out.splitlines()
    assert " | lines 23-24 | " in lines[0]
    assert lines[1:] == ["23  | fuse | 1 |", "24  ![diagram](./images/x.png)"]


@pytest.mark.parametrize(
    "value, message",
    [
        ("12", "--lines takes A-B (line numbers, 1-based)"),
        ("a-b", "--lines takes A-B (line numbers, 1-based)"),
        ("0-3", "ROT 2.1 has 24 lines; --lines 0-3 is outside it"),
        ("25-30", "ROT 2.1 has 24 lines; --lines 25-30 is outside it"),
        ("9-3", "ROT 2.1 has 24 lines; --lines 9-3 is outside it"),
    ],
)
def test_page_lines_refusals(held, md_catalog, capsys, value, message):
    code, out = run(capsys, md_catalog, "page", "ROT", "--lines", value)
    assert (code, out.strip()) == (2, message)


def long_md(n_body):
    return "# Long\n" + "".join(f"body {i}\n" for i in range(n_body)) + "# Next\n"


def test_more_than_200_lines_is_refused(md_catalog, library, scripted, capsys):
    scripted.responses[MD_URL] = ok(long_md(250).encode(), PLAIN)
    run(capsys, md_catalog, "fetch", "ROT")
    code, out = run(capsys, md_catalog, "page", "ROT", "--lines", "1-201")
    assert (code, out.strip()) == (
        2,
        "lines 1-201 are 201 lines; the limit is 200 per call",
    )
    code, out = run(capsys, md_catalog, "page", "ROT", "--lines", "1-200")
    assert code == 0 and len(out.splitlines()) == 201
    code, out = run(capsys, md_catalog, "page", "ROT", "--section", "long")
    assert code == 2
    assert out.strip() == (
        "section Long is lines 1-251 (251 lines); the limit is 200 per call: "
        "read it in parts with --lines, or give a narrower section"
    )


def test_page_section_prints_the_first_match(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "page", "ROT", "--section", "fuses goals")
    assert code == 0
    assert out.splitlines() == [
        f"cite: security | ROT 2.1 | Fuses > Goals | Markdown | lines 14-17 | "
        f"{MD_URL} | {held}",
        "14  ## Goals",
        "15  Fuse goal text.",
        "16  ### 5.2 Zeroization ###",
        "17  Zeroize the fuse.",
    ]
    code, out = run(capsys, md_catalog, "page", "ROT", "--section", "absent")
    assert (code, out.strip()) == (2, "no matching section")


def test_lines_goes_alone(held, md_catalog, capsys):
    code, out = run(capsys, md_catalog, "page", "ROT", "3", "--lines", "1-2")
    assert (code, out.strip()) == (
        2,
        "--lines goes alone, not with a page number or --section",
    )
    code, out = run(capsys, md_catalog, "page", "ROT", "--lines", "1-2", "--to", "4")
    assert (code, out.strip()) == (2, "--to goes with a page number, not with --lines")


# ------------------------------------------------- commands that refuse md


@pytest.mark.parametrize(
    "argv, message",
    [
        (["page", "ROT", "3"], POINTER),
        (["render", "ROT", "--page", "3"], POINTER),
        (
            ["table", "ROT", "--page", "3"],
            POINTER + "; its tables are printed as text by page",
        ),
    ],
)
@pytest.mark.parametrize("is_held", [True, False], ids=["held", "not-held"])
def test_page_numbers_are_refused_on_markdown(
    md_catalog, library, scripted, capsys, argv, message, is_held
):
    if is_held:
        scripted.responses[MD_URL] = ok(MD_TEXT.encode(), PLAIN)
        run(capsys, md_catalog, "fetch", "ROT")
    scripted.calls.clear()
    code, out = run(capsys, md_catalog, *argv)
    assert (code, out.strip()) == (2, message)
    assert scripted.calls == []  # nothing downloaded first


def test_lines_on_a_pdf_is_refused_before_any_download(md_catalog, scripted, capsys):
    code, out = run(capsys, md_catalog, "page", "DSP0236", "--lines", "1-5")
    assert (code, out.strip()) == (
        2,
        "--lines reads a Markdown document; DSP0236 1.3.3 is a PDF: give a page "
        "number or --section",
    )
    assert scripted.calls == []


def test_lines_on_a_held_pdf_is_refused(md_catalog, library, scripted, capsys):
    scripted.responses["https://example.test/DSP0236_1.3.3.pdf"] = ok(PDF_BYTES)
    run(capsys, md_catalog, "fetch", "DSP0236", "--no-extract")
    code, out = run(capsys, md_catalog, "page", "DSP0236", "--lines", "1-5")
    assert (code, out.strip()) == (
        2,
        "--lines reads a Markdown document; DSP0236 1.3.3 is a PDF: give a page "
        "number or --section",
    )


@pytest.mark.parametrize(
    "command, bundle", [("schema", "schema"), ("registry", "registries")]
)
def test_schema_and_registry_say_markdown(held, md_catalog, capsys, command, bundle):
    code, out = run(capsys, md_catalog, command, "ROT")
    assert (code, out.strip()) == (
        2,
        f"ROT 2.1 is a Markdown document, not a {bundle} bundle; read it with: "
        "bmcspec find ROT PATTERN, or: bmcspec page ROT --section QUERY",
    )


@pytest.mark.parametrize("command", ["schema", "registry"])
def test_schema_and_registry_say_markdown_before_a_download(
    md_catalog, scripted, capsys, command
):
    code, out = run(capsys, md_catalog, command, "ROT")
    assert (code, out.strip()) == (
        2,
        "ROT 2.1 is a Markdown document, not a bundle; read it with: "
        "bmcspec find ROT PATTERN, or: bmcspec page ROT --section QUERY",
    )
    assert scripted.calls == []


def test_a_markdown_draft_beside_a_released_pdf(md_catalog, library, scripted, capsys):
    """The Caliptra shape: the PDF is Latest, the md draft is read by
    --version; page N still reads the PDF's catalog version."""
    scripted.responses[MD_URL] = ok(MD_TEXT.encode(), PLAIN)
    code, out = run(
        capsys, md_catalog, "page", "ROTMIX", "--version", "2.1", "--lines", "3-4"
    )
    assert code == 0, out
    assert "| ROTMIX 2.1 | Introduction | Markdown | lines 3-4 |" in out
    scripted.calls.clear()
    code, out = run(capsys, md_catalog, "page", "ROTMIX", "--lines", "3-4")
    assert code == 2
    assert out.strip().startswith("--lines reads a Markdown document; ROTMIX 2.0")
    assert scripted.calls == []


# --------------------------------------------------------------- Notes


def test_notes_skip_markdown_cites(held):
    cite = (
        f"cite: security | ROT 2.1 | Fuses > Goals | Markdown | lines 14-17 | "
        f"{MD_URL} | {held}"
    )
    assert notes_mod.find_cites(f"An answer.\n\n{cite}\n") == []
    assert notes_mod.make_note("q", "", f"An answer.\n\n{cite}\n", "t") is None


def test_find_and_section_with_notes_on(held, md_catalog, library, capsys):
    (library.root / "config.toml").write_text("[library]\nnotes = true\n", "utf-8")
    pdf_cite = (
        f"cite: security | ROT 2.1 | Fuses | PDF page 3 | lines - | {MD_URL} | {held}"
    )
    note = notes_mod.make_note("fuse goals?", "", f"Goals.\n\n{pdf_cite}\n", "t")
    (library.root / notes_mod.NOTES_NAME).write_text(note.to_json() + "\n", "utf-8")
    code, out = run(capsys, md_catalog, "find", "ROT", "zeroize")
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "notes ROT 2.1: 1"  # placed before the first hit
    assert lines[-1] == "ROT l.17 | 5.2 Zeroization | Zeroize the fuse."
    code, out = run(capsys, md_catalog, "section", "ROT", "5.2")
    assert code == 0
    assert out.splitlines()[0] == "notes ROT 2.1: 1"
    assert out.splitlines()[-1] == "2 | 5.2 Zeroization | lines 16-17"


def test_library_holding_is_extracted_once_extracted(held):
    holding = Library(held.parents[2].parent).find("ROT", "2.1")
    assert holding is not None
    assert holding.extract_meta["kind"] == "markdown"

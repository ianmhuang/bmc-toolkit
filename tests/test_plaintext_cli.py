"""Text versions (type txt) through the CLI: catalog, fetch, add, scan,
extract, status, section, find, page, the commands that refuse them, a
searched_with companion, Notes and refresh. No PDF is extracted here."""

import json

import pytest

from bmc_toolkit.spec import notes as notes_mod
from bmc_toolkit.spec.cli import main
from bmc_toolkit.spec.library import Library
from bmc_toolkit.spec.markdown import split_lines
from tests.conftest import HTML_BYTES, MINI_CATALOG, ok
from tests.test_plaintext import RFC_TEXT

TXT_URL = "https://example.test/rfc/rfc9999.txt"
PLAIN = "text/plain; charset=utf-8"

TXT_CATALOG = (
    MINI_CATALOG
    + f"""
[families.ietf]
title = "IETF RFCs"
publisher = "IETF"

[[documents]]
id = "RFC9999"
family = "ietf"
title = "Example Protocol"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "March 2026"
url = "{TXT_URL}"
type = "txt"
published = "2026-03-01"
"""
)

POINTER = (
    "RFC9999 March 2026 is a text document, read by its lines and not by "
    "pages; read it with: bmcspec page RFC9999 --section QUERY, or: bmcspec "
    "page RFC9999 --lines A-B"
)
LINES = split_lines(RFC_TEXT)
AUTHOR = "Author's Address"
ENTRIES = 10


def n(text: str) -> int:
    return LINES.index(text) + 1


@pytest.fixture
def txt_catalog(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(TXT_CATALOG, encoding="utf-8", newline="")
    return path


def run(capsys, catalog, *argv):
    code = main(["--catalog", str(catalog), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def held(txt_catalog, library, scripted, capsys):
    """RFC9999 fetched (and extracted by fetch)."""
    scripted.responses[TXT_URL] = ok(RFC_TEXT.encode(), PLAIN)
    code, out = run(capsys, txt_catalog, "fetch", "RFC9999")
    assert code == 0, out
    return library.specs / "ietf" / "RFC9999" / "March_2026"


# ------------------------------------------------------------- catalog


def test_catalog_lists_the_txt_type(txt_catalog, capsys):
    code, out = run(capsys, txt_catalog, "catalog", "RFC9999")
    assert code == 0, out
    assert "\tMarch 2026\t2026-03-01\ttxt\t" in out


def test_an_unknown_type_names_txt_among_the_types(tmp_path, capsys):
    path = tmp_path / "catalog.toml"
    path.write_text(TXT_CATALOG.replace('type = "txt"', 'type = "rtf"'), "utf-8")
    code, out = run(capsys, path, "catalog")
    assert code == 1
    assert "'rtf' not one of ('pdf', 'zip', 'md', 'txt')" in out


# --------------------------------------------------------------- fetch


def test_fetch_stores_original_txt_and_extracts(txt_catalog, library, scripted, capsys):
    scripted.responses[TXT_URL] = ok(RFC_TEXT.encode(), PLAIN)
    code, out = run(capsys, txt_catalog, "fetch", "RFC9999")
    assert code == 0, out
    vdir = library.specs / "ietf" / "RFC9999" / "March_2026"
    assert (vdir / "original.txt").read_bytes() == RFC_TEXT.encode()
    assert (
        f"extracted RFC9999 March 2026: {len(LINES)} lines, outline headings "
        f"({ENTRIES} entries)"
    ) in out
    meta = json.loads((vdir / "meta.json").read_text("utf-8"))
    assert meta["file"] == "original.txt"


@pytest.mark.parametrize(
    "body, ctype",
    [(HTML_BYTES, "text/html"), (b"\x89PNG\r\n\x1a\n", "image/png")],
    ids=["html", "binary"],
)
def test_fetch_refuses_a_body_that_is_not_text(
    txt_catalog, library, scripted, capsys, body, ctype
):
    scripted.responses[TXT_URL] = ok(body, ctype)
    code, out = run(capsys, txt_catalog, "fetch", "RFC9999")
    assert code == 2
    assert f"direct: not a txt ({ctype}, {len(body)} bytes)" in out
    assert "original.txt" in out
    vdir = library.specs / "ietf" / "RFC9999" / "March_2026"
    assert not (vdir / "original.txt").exists()


# ---------------------------------------------------------- add / scan


def test_add_a_text_file(txt_catalog, library, tmp_path, capsys):
    source = tmp_path / "rfc9999.txt"
    source.write_text(RFC_TEXT, encoding="utf-8", newline="")
    code, out = run(
        capsys,
        txt_catalog,
        "add",
        str(source),
        "--document",
        "RFC9999",
        "--version",
        "March 2026",
    )
    assert code == 0, out
    vdir = library.specs / "ietf" / "RFC9999" / "March_2026"
    assert out.splitlines()[-1] == f"added RFC9999 March 2026 as Drop-in at {vdir}"
    assert (vdir / "original.txt").is_file()


def test_add_refuses_an_html_page_saved_as_txt(txt_catalog, tmp_path, capsys):
    source = tmp_path / "saved.txt"
    source.write_bytes(HTML_BYTES)
    code, out = run(
        capsys,
        txt_catalog,
        "add",
        str(source),
        "--document",
        "RFC9999",
        "--version",
        "March 2026",
    )
    assert (code, out.strip()) == (
        2,
        f"{source} is not a txt (wrong leading bytes); not added",
    )


def test_add_names_txt_among_the_accepted_types(txt_catalog, tmp_path, capsys):
    source = tmp_path / "notes.rtf"
    source.write_text("x", "utf-8")
    code, out = run(
        capsys,
        txt_catalog,
        "add",
        str(source),
        "--document",
        "RFC9999",
        "--version",
        "March 2026",
    )
    assert (code, out.strip()) == (
        2,
        "unsupported file type '.rtf': expected .pdf, .zip, .md or .txt",
    )


def test_scan_registers_original_txt_and_skips_a_bad_one(txt_catalog, library, capsys):
    good = library.specs / "ietf" / "RFC9999" / "March_2026"
    good.mkdir(parents=True)
    (good / "original.txt").write_text(RFC_TEXT, encoding="utf-8", newline="")
    bad = library.specs / "ietf" / "RFC9999" / "April_2026"
    bad.mkdir(parents=True)
    (bad / "original.txt").write_bytes(HTML_BYTES)
    code, out = run(capsys, txt_catalog, "scan")
    assert code == 0
    assert "registered RFC9999 March_2026 as Drop-in" in out or (
        "registered RFC9999 March 2026 as Drop-in" in out
    )
    assert f"skipped {bad}: 'original.txt' is not a txt (wrong leading bytes)" in out
    assert out.strip().endswith("scan: registered 1, skipped 1")


# ------------------------------------------------------ extract / status


def status_row(capsys, catalog, document):
    _, out = run(capsys, catalog, "status")
    rows = [ln.split("\t") for ln in out.splitlines() if f"\t{document}\t" in ln]
    assert len(rows) == 1, out
    return rows[0]


def test_status_shows_extracted_headings_then_stale(held, txt_catalog, capsys):
    row = status_row(capsys, txt_catalog, "RFC9999")
    assert row[5:] == ["extracted", "headings"]
    meta_path = held / "extract.json"
    meta = json.loads(meta_path.read_text("utf-8"))
    assert meta["kind"] == "text"
    meta["extractor_version"] = 0
    meta_path.write_text(json.dumps(meta), "utf-8")
    assert status_row(capsys, txt_catalog, "RFC9999")[5] == "stale"
    code, out = run(capsys, txt_catalog, "section", "RFC9999", "terms")
    assert code == 0
    assert out.startswith(f"extracted RFC9999 March 2026: {len(LINES)} lines")


def test_a_markdown_extract_beside_a_text_original_is_not_current(
    held, txt_catalog, capsys
):
    meta_path = held / "extract.json"
    meta = json.loads(meta_path.read_text("utf-8"))
    meta["kind"] = "markdown"
    meta_path.write_text(json.dumps(meta), "utf-8")
    code, out = run(capsys, txt_catalog, "section", "RFC9999", "terms")
    assert code == 0
    assert out.startswith("extracted RFC9999 March 2026")


def test_extract_again_is_skipped_and_force_redoes_it(held, txt_catalog, capsys):
    code, out = run(capsys, txt_catalog, "extract", "RFC9999")
    assert (code, out.strip()) == (0, "skipped RFC9999 March 2026: already extracted")
    code, out = run(capsys, txt_catalog, "extract", "RFC9999", "--force")
    assert (code, out.strip()) == (
        0,
        f"extracted RFC9999 March 2026: {len(LINES)} lines, outline headings "
        f"({ENTRIES} entries)",
    )


def test_the_holding_counts_as_extracted(held):
    holding = Library(held.parents[2].parent).find("RFC9999", "March 2026")
    assert holding is not None
    assert holding.extract_meta["kind"] == "text"


# ------------------------------------------------------------- section


def test_section_prints_line_ranges(held, txt_catalog, capsys):
    code, out = run(capsys, txt_catalog, "section", "RFC9999", "1.1")
    assert code == 0
    assert out.splitlines() == [
        f"1 | 1.1 Terms | lines {n('1.1.  Terms')}-{n('2. Old Style') - 1}"
    ]
    code, out = run(capsys, txt_catalog, "section", "RFC9999", "collected rules")
    assert out.splitlines() == [
        f"0 | Appendix A Collected Rules | lines {n('Appendix A.  Collected Rules')}"
        f"-{n(AUTHOR) - 1}"
    ]
    code, out = run(capsys, txt_catalog, "section", "RFC9999", "absent words")
    assert (code, out.strip()) == (0, "no matching section")


# ---------------------------------------------------------------- find


def test_find_skips_furniture_and_its_context(held, txt_catalog, capsys):
    target = "   continue on the next page with the Example word."
    code, out = run(
        capsys, txt_catalog, "find", "RFC9999", "next page", "--context", "2"
    )
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == (f"RFC9999 l.{n(target)} | 1 Introduction | {target.strip()}")
    context = [ln for ln in lines[1:] if ln.startswith("    line ")]
    # furniture lines above the hit are left out; the lines below are text
    assert all("Page" not in ln and "RFC 9999" not in ln for ln in context)
    assert f"    line {n(target) + 2}: 1.1.  Terms" in context


def test_furniture_is_never_a_hit(held, txt_catalog, capsys):
    code, out = run(capsys, txt_catalog, "find", "RFC9999", "[Page")
    assert (code, out.strip()) == (0, "no hits")
    code, out = run(capsys, txt_catalog, "find", "RFC9999", "RFC 9999")
    assert (code, out.strip()) == (0, "no hits")


# ---------------------------------------------------------------- page


def test_page_lines_prints_cite_and_lines_without_furniture(held, txt_catalog, capsys):
    first = n("   The introduction says what the example is.  It goes on to")
    last = n("1.1.  Terms")
    code, out = run(
        capsys, txt_catalog, "page", "RFC9999", "--lines", f"{first}-{last}"
    )
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == (
        f"cite: ietf | RFC9999 March 2026 | 1 Introduction; 1.1 Terms | Text | "
        f"lines {first}-{last} | {TXT_URL} | {held}"
    )
    assert lines[1:] == [
        f"{first}  {LINES[first - 1]}",
        f"{n('   continue on the next page with the Example word.')}  "
        "   continue on the next page with the Example word.",
        f"{last - 1}",
        f"{last}  1.1.  Terms",
    ]


def test_page_section_prints_the_section(held, txt_catalog, capsys):
    code, out = run(capsys, txt_catalog, "page", "RFC9999", "--section", "2.1")
    assert code == 0, out
    first = n("2.1 One space")
    last = n("3.  A heading long enough that it wraps") - 1
    lines = out.splitlines()
    assert lines[0] == (
        f"cite: ietf | RFC9999 March 2026 | 2.1 One space | Text | "
        f"lines {first}-{last} | {TXT_URL} | {held}"
    )
    assert lines[1] == f"{first}  2.1 One space"


def test_more_than_200_lines_is_refused(txt_catalog, library, scripted, capsys):
    body = "Writer\n\n1.  Long\n\n" + "".join(f"   body {i}\n" for i in range(250))
    scripted.responses[TXT_URL] = ok(body.encode(), PLAIN)
    run(capsys, txt_catalog, "fetch", "RFC9999")
    code, out = run(capsys, txt_catalog, "page", "RFC9999", "--lines", "1-201")
    assert (code, out.strip()) == (
        2,
        "lines 1-201 are 201 lines; the limit is 200 per call",
    )
    code, out = run(capsys, txt_catalog, "page", "RFC9999", "--section", "long")
    assert code == 2
    assert out.strip().startswith("section 1 Long is lines 3-254 (252 lines)")


def test_a_text_without_rfc_layout_reads_by_lines(
    txt_catalog, library, scripted, capsys
):
    body = "plain notes\nmore notes\n  an indented note\n"
    scripted.responses[TXT_URL] = ok(body.encode(), PLAIN)
    code, out = run(capsys, txt_catalog, "fetch", "RFC9999")
    assert code == 0, out
    assert "outline headings (0 entries)" in out
    code, out = run(capsys, txt_catalog, "section", "RFC9999", "notes")
    assert (code, out.strip()) == (0, "no matching section")
    code, out = run(capsys, txt_catalog, "find", "RFC9999", "more")
    assert (code, out.strip()) == (0, "RFC9999 l.2 | - | more notes")
    code, out = run(capsys, txt_catalog, "page", "RFC9999", "--lines", "2-3")
    assert code == 0
    assert out.splitlines()[0].startswith("cite: ietf | RFC9999 March 2026 | - | Text")


# --------------------------------------------- commands that refuse txt


@pytest.mark.parametrize(
    "argv, message",
    [
        (["page", "RFC9999", "3"], POINTER),
        (["render", "RFC9999", "--page", "3"], POINTER),
        (
            ["table", "RFC9999", "--page", "3"],
            POINTER + "; its tables are printed as text by page",
        ),
    ],
)
@pytest.mark.parametrize("is_held", [True, False], ids=["held", "not-held"])
def test_page_numbers_are_refused_on_text(
    txt_catalog, library, scripted, capsys, argv, message, is_held
):
    if is_held:
        scripted.responses[TXT_URL] = ok(RFC_TEXT.encode(), PLAIN)
        run(capsys, txt_catalog, "fetch", "RFC9999")
    scripted.calls.clear()
    code, out = run(capsys, txt_catalog, *argv)
    assert (code, out.strip()) == (2, message)
    assert scripted.calls == []


@pytest.mark.parametrize(
    "command, bundle", [("schema", "schema"), ("registry", "registries")]
)
def test_schema_and_registry_say_text(held, txt_catalog, capsys, command, bundle):
    code, out = run(capsys, txt_catalog, command, "RFC9999")
    assert (code, out.strip()) == (
        2,
        f"RFC9999 March 2026 is a text document, not a {bundle} bundle; read it "
        "with: bmcspec find RFC9999 PATTERN, or: bmcspec page RFC9999 --section QUERY",
    )


@pytest.mark.parametrize("command", ["schema", "registry"])
def test_schema_and_registry_say_text_before_a_download(
    txt_catalog, library, scripted, capsys, command
):
    code, out = run(capsys, txt_catalog, command, "RFC9999")
    assert (code, out.strip()) == (
        2,
        "RFC9999 March 2026 is a text document, not a bundle; read it with: "
        "bmcspec find RFC9999 PATTERN, or: bmcspec page RFC9999 --section QUERY",
    )
    assert scripted.calls == []


def test_lines_on_a_pdf_is_still_refused(txt_catalog, scripted, capsys):
    code, out = run(capsys, txt_catalog, "page", "DSP0236", "--lines", "1-5")
    assert (code, out.strip()) == (
        2,
        "--lines reads a Markdown document; DSP0236 1.3.3 is a PDF: give a page "
        "number or --section",
    )
    assert scripted.calls == []


# ---------------------------------------------------- companion / Notes


def test_a_text_companion_is_searched_with_the_document(
    tmp_path, library, scripted, capsys
):
    other = "https://example.test/rfc/rfc9998.txt"
    path = tmp_path / "catalog.toml"
    path.write_text(
        TXT_CATALOG.replace(
            'title = "Example Protocol"',
            'title = "Example Protocol"\nsearched_with = ["RFC9998"]',
        )
        + f"""
[[documents]]
id = "RFC9998"
family = "ietf"
title = "Example Protocol Extensions"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "February 2026"
url = "{other}"
type = "txt"
published = "2026-02-01"
""",
        encoding="utf-8",
    )
    scripted.responses[TXT_URL] = ok(RFC_TEXT.encode(), PLAIN)
    scripted.responses[other] = ok(
        b"Writer\n\n1.  Extension\n\n   The rule note.\n", PLAIN
    )
    code, out = run(capsys, path, "find", "RFC9999", "rule note")
    assert code == 0, out
    assert out.splitlines()[-1] == "RFC9998 l.5 | 1 Extension | The rule note."
    assert "bundle" not in out


def test_notes_skip_text_cites(held):
    cite = (
        f"cite: ietf | RFC9999 March 2026 | 1.1 Terms | Text | lines 35-37 | "
        f"{TXT_URL} | {held}"
    )
    assert notes_mod.find_cites(f"An answer.\n\n{cite}\n") == []
    assert notes_mod.make_note("q", "", f"An answer.\n\n{cite}\n", "t") is None


# ------------------------------------------------------------- refresh


def test_refresh_passes_over_a_text_version(txt_catalog, scripted, capsys):
    before = txt_catalog.read_bytes()
    code, out = run(capsys, txt_catalog, "refresh", "--write")
    assert code in (0, 1), out
    assert "RFC9999" not in out
    assert "Traceback" not in out
    assert txt_catalog.read_bytes() == before

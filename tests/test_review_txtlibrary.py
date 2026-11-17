"""Reviewer acceptance tests for the text document type (catalog type
``txt``) on its way into the Library and at the commands that do not read
it: catalog, fetch, add, scan, extract, status, the page-number refusals,
Notes and refresh (AC-1 to AC-3, AC-9, AC-11, AC-12).

Black-box through ``bmc_toolkit.spec.cli.main`` with the scripted client of
conftest, except the two Notes functions the Stop hook records through. The
documents are synthetic; no PDF is extracted here.
"""

import json

import pytest

from bmc_toolkit.spec import notes as notes_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG, ok

VERSION = "2026-06"
LABEL = f"RFC7777 {VERSION}"
TXT_URL = "https://example.test/rfc/rfc7777.txt"
MD_URL = "https://example.test/raw/0123abc/doc/mdx.md"
PLAIN = "text/plain; charset=utf-8"
BOM = b"\xef\xbb\xbf"

TXT_CATALOG = (
    MINI_CATALOG
    + f"""
[families.ietf]
title = "IETF RFCs"
publisher = "IETF"

[[documents]]
id = "RFC7777"
family = "ietf"
title = "The Review Transfer Protocol"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "{VERSION}"
url = "{TXT_URL}"
type = "txt"
published = "2026-06-01"
"""
)

# The same catalog with a Markdown document beside the text one.
MIXED_CATALOG = (
    TXT_CATALOG
    + f"""
[[documents]]
id = "MDX"
family = "ietf"
title = "A Markdown document beside the text one"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0"
url = "{MD_URL}"
type = "md"
published = "2026-05-01"
"""
)

# Five lines: an author block, one numbered heading on line 3, its body.
SMALL = (
    "Example Group                                    A. Reviewer\n"
    "\n"
    "1.  Scope\n"
    "\n"
    "   The scope of the example.\n"
).encode()
HTML_PAGE = b"<!DOCTYPE html><html><body>Sign in to continue</body></html>"

# Not text as an md body must be: an HTML page, a NUL byte, bytes that are
# not UTF-8, a blank body.
BAD_BODIES = [
    pytest.param(HTML_PAGE, "text/html", id="html"),
    pytest.param(b"Text with a \x00 byte in it\n", PLAIN, id="nul"),
    pytest.param(b"caf\xe9 is not UTF-8\n", PLAIN, id="not-utf8"),
    pytest.param(b" \n\n\t\n", PLAIN, id="blank"),
]


@pytest.fixture
def txt_catalog(tmp_path):
    path = tmp_path / "txt_catalog.toml"
    path.write_text(TXT_CATALOG, encoding="utf-8", newline="")
    return path


@pytest.fixture
def mixed_catalog(tmp_path):
    path = tmp_path / "mixed_catalog.toml"
    path.write_text(MIXED_CATALOG, encoding="utf-8", newline="")
    return path


def run(capsys, catalog, *argv):
    code = main(["--catalog", str(catalog), *argv])
    return code, capsys.readouterr().out


def said(out, prefix):
    """Whether a printed line starts with ``prefix``."""
    return any(ln.startswith(prefix) for ln in out.splitlines())


def originals(library):
    """Every original.* file under the Library."""
    if not library.root.is_dir():
        return []
    return sorted(p.name for p in library.root.rglob("original.*"))


def fetch_small(capsys, catalog, scripted, *extra):
    scripted.responses[TXT_URL] = ok(SMALL, PLAIN)
    code, out = run(capsys, catalog, "fetch", "RFC7777", *extra)
    assert code == 0, out
    scripted.calls.clear()
    return out


@pytest.fixture
def held(txt_catalog, library, scripted, capsys):
    """RFC7777 fetched and extracted; its holding."""
    fetch_small(capsys, txt_catalog, scripted)
    holding = library.find("RFC7777", VERSION)
    assert holding is not None
    return holding


def extract_meta(holding):
    return json.loads((holding.path / "extract.json").read_text(encoding="utf-8"))


def write_extract_meta(holding, meta):
    (holding.path / "extract.json").write_text(
        json.dumps(meta), encoding="utf-8", newline=""
    )


def status_row(capsys, catalog):
    code, out = run(capsys, catalog, "status")
    assert code == 0, out
    rows = [ln.split("\t") for ln in out.splitlines() if "\tRFC7777\t" in ln]
    assert len(rows) == 1, out
    return rows[0]


# ------------------------------------------------------------------- AC-1


def test_catalog_takes_the_txt_type_and_prints_it(txt_catalog, capsys):
    code, out = run(capsys, txt_catalog, "catalog", "RFC7777")
    assert code == 0, out
    rows = [
        ln.split("\t") for ln in out.splitlines() if ln.startswith(f"\t{VERSION}\t")
    ]
    assert len(rows) == 1, out
    assert rows[0][1:4] == [VERSION, "2026-06-01", "txt"]


def test_an_unknown_type_is_still_refused_and_txt_is_listed(tmp_path, capsys):
    path = tmp_path / "bad_catalog.toml"
    bad = TXT_CATALOG.replace('type = "txt"', 'type = "rtf"')
    path.write_text(bad, encoding="utf-8", newline="")
    code, out = run(capsys, path, "catalog")
    assert code == 1, out
    assert "'rtf' not one of (" in out
    assert "'txt'" in out


# ------------------------------------------------------------------- AC-2


@pytest.mark.parametrize("body", [SMALL, BOM + SMALL], ids=["plain", "bom"])
def test_fetch_stores_original_txt_and_extracts_it(
    txt_catalog, library, scripted, capsys, body
):
    scripted.responses[TXT_URL] = ok(body, PLAIN)
    code, out = run(capsys, txt_catalog, "fetch", "RFC7777")
    assert code == 0, out
    holding = library.find("RFC7777", VERSION)
    assert holding is not None
    assert holding.original.name == "original.txt"
    assert holding.original.read_bytes() == body
    assert originals(library) == ["original.txt"]
    assert said(out, f"extracted {LABEL}: 5 lines")


@pytest.mark.parametrize("body, ctype", BAD_BODIES)
def test_fetch_refuses_a_body_that_is_not_text(
    txt_catalog, library, scripted, capsys, body, ctype
):
    scripted.responses[TXT_URL] = ok(body, ctype)
    code, out = run(capsys, txt_catalog, "fetch", "RFC7777")
    assert code == 2, out
    assert "not a txt" in out
    assert library.find("RFC7777", VERSION) is None
    assert originals(library) == []


def add(capsys, catalog, source):
    return run(
        capsys,
        catalog,
        "add",
        str(source),
        "--document",
        "RFC7777",
        "--version",
        VERSION,
    )


def test_add_takes_a_txt_file_and_reads_it_as_user_provided(
    txt_catalog, library, tmp_path, capsys
):
    source = tmp_path / "rfc7777.txt"
    source.write_bytes(SMALL)
    code, out = add(capsys, txt_catalog, source)
    assert code == 0, out
    assert out.splitlines()[-1].startswith(f"added {LABEL} as Drop-in at ")
    holding = library.find("RFC7777", VERSION)
    assert holding is not None and holding.original.name == "original.txt"
    code, out = run(capsys, txt_catalog, "page", "RFC7777", "--lines", "3-5")
    assert code == 0, out
    cites = [ln for ln in out.splitlines() if ln.startswith("cite: ")]
    assert len(cites) == 1, out
    fields = cites[0].split(" | ")
    assert fields[:6] == [
        "cite: ietf",
        LABEL,
        "1 Scope",
        "Text",
        "lines 3-5",
        "user-provided",
    ]


@pytest.mark.parametrize(
    "data",
    [HTML_PAGE, b"Text with a \x00 byte in it\n", b"   \n"],
    ids=["html", "nul", "blank"],
)
def test_add_refuses_a_txt_file_that_is_not_text(
    txt_catalog, library, tmp_path, capsys, data
):
    source = tmp_path / "saved.txt"
    source.write_bytes(data)
    code, out = add(capsys, txt_catalog, source)
    assert code == 2, out
    assert "is not a txt" in out
    assert library.find("RFC7777", VERSION) is None


def test_add_lists_txt_among_the_types_it_takes(txt_catalog, tmp_path, capsys):
    source = tmp_path / "notes.rtf"
    source.write_bytes(SMALL)
    code, out = add(capsys, txt_catalog, source)
    assert code == 2, out
    assert "'.rtf'" in out
    assert ".pdf, .zip, .md or .txt" in out


def test_scan_registers_original_txt_and_skips_one_that_is_not_text(
    txt_catalog, library, capsys
):
    good = library.specs / "ietf" / "RFC7777" / VERSION
    good.mkdir(parents=True)
    (good / "original.txt").write_bytes(SMALL)
    bad = library.specs / "ietf" / "RFC7777" / "2026-07"
    bad.mkdir(parents=True)
    (bad / "original.txt").write_bytes(HTML_PAGE)
    code, out = run(capsys, txt_catalog, "scan")
    assert code == 0, out
    assert said(out, f"registered {LABEL} as Drop-in")
    assert "'original.txt' is not a txt" in out
    assert out.strip().splitlines()[-1] == "scan: registered 1, skipped 1"
    code, out = run(capsys, txt_catalog, "section", "RFC7777", "scope")
    assert code == 0, out
    assert said(out, "0 | 1 Scope | lines 3-5")


# ------------------------------------------------------------------- AC-3


def test_extract_writes_the_outline_and_a_text_extract_json(held):
    outline = json.loads((held.path / "outline.json").read_text(encoding="utf-8"))
    entries = [(e["level"], e["title"], e["line"]) for e in outline]
    assert entries == [(0, "1 Scope", 3)]
    meta = extract_meta(held)
    assert meta["kind"] == "text"
    assert isinstance(meta["extractor_version"], int)
    # nothing a PDF's Extract writes: the original is what is read
    assert not (held.path / "extract.txt").exists()


def test_status_says_extracted_then_stale_for_an_older_extractor(
    held, txt_catalog, capsys
):
    row = status_row(capsys, txt_catalog)
    assert (row[0], row[2], row[5]) == ("ietf", VERSION, "extracted")
    meta = extract_meta(held)
    meta["extractor_version"] -= 1
    write_extract_meta(held, meta)
    assert status_row(capsys, txt_catalog)[5] == "stale"
    # a reading command brings it back to Ready by itself, as for md
    code, out = run(capsys, txt_catalog, "section", "RFC7777", "scope")
    assert code == 0, out
    assert said(out, f"extracted {LABEL}:")
    assert said(out, "0 | 1 Scope | lines 3-5")
    assert status_row(capsys, txt_catalog)[5] == "extracted"


@pytest.mark.parametrize("kind", ["markdown", None], ids=["markdown", "no-kind"])
def test_an_extract_json_of_another_kind_is_not_current(
    held, txt_catalog, capsys, kind
):
    meta = extract_meta(held)
    if kind is None:
        del meta["kind"]
    else:
        meta["kind"] = kind
    write_extract_meta(held, meta)
    code, out = run(capsys, txt_catalog, "extract", "RFC7777")
    assert code == 0, out
    assert said(out, f"extracted {LABEL}:")
    assert extract_meta(held)["kind"] == "text"


def test_extract_skips_a_current_version_and_force_redoes_it(
    held, txt_catalog, capsys
):
    code, out = run(capsys, txt_catalog, "extract", "RFC7777")
    assert code == 0, out
    assert said(out, f"skipped {LABEL}")
    code, out = run(capsys, txt_catalog, "extract", "RFC7777", "--force")
    assert code == 0, out
    assert said(out, f"extracted {LABEL}: 5 lines")


# ------------------------------------------------------------------- AC-9

PAGE_COMMANDS = [
    ["page", "RFC7777", "3"],
    ["page", "RFC7777", "3", "--to", "4"],
    ["render", "RFC7777", "--page", "3"],
    ["table", "RFC7777", "--page", "3"],
]


def check_pointer(code, out):
    assert code == 2, out
    text = out.strip()
    assert len(text.splitlines()) == 1, out
    assert text.startswith(f"{LABEL} is a text document")
    assert "Markdown" not in text
    assert "bmcspec page RFC7777 --section QUERY" in text
    assert "bmcspec page RFC7777 --lines A-B" in text


@pytest.mark.parametrize("argv", PAGE_COMMANDS, ids=lambda a: " ".join(a))
def test_commands_that_need_pages_refuse_txt_before_any_download(
    txt_catalog, library, scripted, capsys, argv
):
    scripted.responses[TXT_URL] = ok(SMALL, PLAIN)  # reachable, and not asked
    code, out = run(capsys, txt_catalog, *argv)
    check_pointer(code, out)
    assert scripted.calls == []
    assert originals(library) == []


@pytest.mark.parametrize("argv", PAGE_COMMANDS, ids=lambda a: " ".join(a))
def test_commands_that_need_pages_refuse_a_held_txt_version(
    txt_catalog, library, scripted, capsys, argv
):
    fetch_small(capsys, txt_catalog, scripted, "--no-extract")
    code, out = run(capsys, txt_catalog, *argv)
    check_pointer(code, out)
    assert scripted.calls == []


def check_bundle_pointer(code, out):
    assert code == 2, out
    text = out.strip()
    assert len(text.splitlines()) == 1, out
    assert text.startswith(f"{LABEL} is a text document")
    assert "Markdown" not in text and "PDF" not in text
    assert "bmcspec find RFC7777 PATTERN" in text
    assert "bmcspec page RFC7777 --section QUERY" in text


@pytest.mark.parametrize("command", ["schema", "registry"])
def test_schema_and_registry_point_a_txt_version_to_page_before_any_download(
    txt_catalog, library, scripted, capsys, command
):
    scripted.responses[TXT_URL] = ok(SMALL, PLAIN)  # reachable, and not asked
    code, out = run(capsys, txt_catalog, command, "RFC7777")
    check_bundle_pointer(code, out)
    assert scripted.calls == []
    assert originals(library) == []


@pytest.mark.parametrize("command", ["schema", "registry"])
def test_schema_and_registry_point_a_held_txt_version_to_page(
    held, txt_catalog, scripted, capsys, command
):
    code, out = run(capsys, txt_catalog, command, "RFC7777")
    check_bundle_pointer(code, out)
    assert scripted.calls == []


def test_lines_on_a_pdf_is_still_refused(txt_catalog, library, scripted, capsys):
    code, out = run(capsys, txt_catalog, "page", "DSP0236", "--lines", "1-5")
    assert code == 2, out
    text = out.strip()
    assert len(text.splitlines()) == 1, out
    assert "--lines" in text and "DSP0236 1.3.3" in text
    assert scripted.calls == []
    assert originals(library) == []


# ------------------------------------------------------------------ AC-11


def text_cite(capsys, catalog):
    code, out = run(capsys, catalog, "page", "RFC7777", "--lines", "3-5")
    assert code == 0, out
    cite = out.splitlines()[0]
    assert cite.startswith(f"cite: ietf | {LABEL} | ") and " | Text | " in cite
    return cite


def test_a_text_cite_is_not_recorded_in_the_notes(held, txt_catalog, capsys):
    cite = text_cite(capsys, txt_catalog)
    answer = f"The scope is the example.\n\n{cite}\n"
    assert notes_mod.find_cites(answer) == []
    assert notes_mod.make_note("what is the scope?", "", answer, "t") is None
    inline = cite.removeprefix("cite: ")
    assert notes_mod.find_cites(f"See {inline} for the scope.") == []


def test_a_pdf_cite_beside_a_text_cite_is_the_only_one_recorded(
    held, txt_catalog, capsys
):
    cite = text_cite(capsys, txt_catalog)
    pdf_cite = (
        "cite: mctp | DSP0236 1.3.3 | 8 Overview | PDF page 24 | lines 310-340 | "
        "https://example.test/DSP0236_1.3.3.pdf | /library/specs/mctp/DSP0236/1.3.3"
    )
    found = notes_mod.find_cites(f"Both say so.\n\n{cite}\n{pdf_cite}\n")
    assert len(found) == 1, found
    assert found[0].startswith("DSP0236 1.3.3 | ") and "RFC7777" not in found[0]


def test_refresh_passes_over_a_txt_version_and_keeps_the_pin_rule_for_md(
    mixed_catalog, scripted, capsys
):
    before = mixed_catalog.read_bytes()
    code, out = run(
        capsys,
        mixed_catalog,
        "refresh",
        "--write",
        "--skip-source",
        "dmtf",
        "--skip-source",
        "nvme",
        "--skip-source",
        "ocp",
    )
    assert code == 0, out
    # the Markdown version's URL pins no commit and is reported; the text
    # version's URL pins none either and is not looked at
    assert said(out, "confirm MDX 1.0")
    assert "RFC7777" not in out
    assert out.strip().splitlines()[-1].startswith("summary: ")
    assert scripted.calls == []
    assert mixed_catalog.read_bytes() == before


# ------------------------------------------------------------------ AC-12

# A Markdown file holding what would be page furniture in a text version: a
# footer line, a form-feed line and a running header.
MD_LINES = [
    "# Title",  # 1
    "",  # 2
    "Writer                 Informational                 [Page 1]",  # 3
    "\f",  # 4
    "RFC 7777 is named at the start of this line",  # 5
    "",  # 6
    "Closing words.",  # 7
]
MD_BYTES = ("\n".join(MD_LINES) + "\n").encode()


def test_a_markdown_version_hides_no_line_and_is_still_cited_as_markdown(
    mixed_catalog, library, scripted, capsys
):
    scripted.responses[MD_URL] = ok(MD_BYTES, PLAIN)
    code, out = run(capsys, mixed_catalog, "fetch", "MDX")
    assert code == 0, out
    assert originals(library) == ["original.md"]
    code, out = run(capsys, mixed_catalog, "find", "MDX", "[Page 1]")
    assert code == 0, out
    assert out.splitlines() == [f"MDX l.3 | Title | {MD_LINES[2]}"]
    code, out = run(capsys, mixed_catalog, "find", "MDX", "RFC 7777")
    assert code == 0, out
    assert out.splitlines() == [f"MDX l.5 | Title | {MD_LINES[4]}"]
    code, out = run(capsys, mixed_catalog, "page", "MDX", "--lines", "1-3")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ")[1:5] == ["MDX 1.0", "Title", "Markdown", "lines 1-3"]
    assert lines[1:] == ["1  # Title", "2", f"3  {MD_LINES[2]}"]

"""Reviewer acceptance tests for the Markdown document type (catalog type
``md``) on its way into the Library: catalog, fetch, add, scan, extract and
status (AC-1 to AC-5).

Black-box through ``bmc_toolkit.spec.cli.main`` with the scripted client of
conftest. No PDF is extracted here, so no third-party package is needed.
"""

import json

import pytest

from bmc_toolkit.spec import fetch as fetch_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG, ZIP_BYTES, ok, wayback_hit

MD_URL = "https://example.test/raw/0123abc/doc/review.md"
BUNDLE_URL = "https://example.test/bundle_2026.1.zip"
PLAIN = "text/plain; charset=utf-8"
BOM = b"\xef\xbb\xbf"

MD_CATALOG = (
    MINI_CATALOG
    + """
[families.security]
title = "Security"
publisher = "various"

[[documents]]
id = "RVW"
family = "security"
title = "A Markdown specification written for the review"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0"
url = "https://example.test/raw/0123abc/doc/review.md"
type = "md"
published = "2026-10-01"
"""
)

# The synthetic document. The position in the list is the line number minus
# one; the tests below name lines by number, so keep the order.
MD_LINES = [
    "Preamble line before any heading.",  # 1
    "",  # 2
    "# Overview",  # 3
    "The device boots from ROM.",  # 4
    "",  # 5
    "## Scope",  # 6
    "Scope of the overview.",  # 7
    "### Notes",  # 8
    "~~~",  # 9
    "# inside a tilde fence",  # 10
    "~~~",  # 11
    "",  # 12
    "# Boot flow",  # 13
    "## Scope",  # 14
    "Scope of the boot flow.",  # 15
    "### 4.1 Reset vector",  # 16
    "The vector is fixed.  ",  # 17: a hard break, two trailing spaces
    "## 4.2 Measured boot",  # 18
    "Measurements extend the register.",  # 19
    "### Notes",  # 20
    "Ordering matters here.",  # 21
    "# Glossary",  # 22
    "ROM: read-only memory.",  # 23
]
MD_TEXT = "\n".join(MD_LINES) + "\n"
MD_BYTES = MD_TEXT.encode("utf-8")
EXTRACTED = "extracted RVW 1.0: 23 lines, outline headings (9 entries)"

# What is and is not an ATX heading (AC-4): 9 lines, 3 headings.
HEADING_CASES = (
    "# One\n"  # 1: level 0
    "```sh\n"  # 2
    "# comment in a fence\n"  # 3: inside a fenced code block
    "```\n"  # 4
    "   ## Two\n"  # 5: three spaces of indent, level 1
    "    # four spaces\n"  # 6: four spaces, not a heading
    "#NoSpace\n"  # 7: no space after the marks
    "####### seven\n"  # 8: seven marks
    "###### Six\n"  # 9: level 5
)


@pytest.fixture
def md_catalog(tmp_path):
    path = tmp_path / "md_catalog.toml"
    path.write_text(MD_CATALOG, encoding="utf-8", newline="")
    return path


def run(capsys, catalog, *argv):
    code = main(["--catalog", str(catalog), *argv])
    return code, capsys.readouterr().out


def said(out, prefix):
    """Whether a printed line starts with ``prefix`` (the Library path in a
    cite: line may hold any word, so whole-output substring tests are out)."""
    return any(ln.startswith(prefix) for ln in out.splitlines())


def version_dir(library, version="1.0"):
    return library.specs / "security" / "RVW" / version


def add_bytes(capsys, catalog, tmp_path, data, *extra):
    """``add`` a file with these bytes as RVW 1.0; (code, output, source)."""
    source = tmp_path / "given.md"
    source.write_bytes(data)
    code, out = run(
        capsys,
        catalog,
        "add",
        str(source),
        "--document",
        "RVW",
        "--version",
        "1.0",
        *extra,
    )
    return code, out, source


# ------------------------------------------------------------------- AC-1


def test_catalog_prints_md_in_the_type_column(md_catalog, capsys):
    code, out = run(capsys, md_catalog, "catalog", "RVW")
    assert code == 0, out
    rows = [ln.split("\t") for ln in out.splitlines() if ln.startswith("\t1.0\t")]
    assert len(rows) == 1, out
    assert rows[0][3] == "md"


def test_another_unknown_type_is_still_refused_and_md_is_listed(tmp_path, capsys):
    path = tmp_path / "bad_catalog.toml"
    bad = MD_CATALOG.replace('type = "md"', 'type = "txt"')
    path.write_text(bad, encoding="utf-8", newline="")
    code, out = run(capsys, path, "catalog")
    assert code == 1, out
    assert "'txt' not one of (" in out
    assert "'md'" in out


# ------------------------------------------------------------------- AC-2


def test_fetch_stores_the_body_as_original_md(md_catalog, library, scripted, capsys):
    scripted.responses[MD_URL] = ok(MD_BYTES, PLAIN)
    code, out = run(capsys, md_catalog, "fetch", "RVW")
    assert code == 0, out
    assert "fetched RVW 1.0 via direct" in out.splitlines()
    vdir = version_dir(library)
    assert (vdir / "original.md").read_bytes() == MD_BYTES
    assert not (vdir / "original.pdf").exists()
    meta = json.loads((vdir / "meta.json").read_text("utf-8"))
    assert meta["file"] == "original.md"
    assert meta["url"] == MD_URL


@pytest.mark.parametrize(
    "body",
    [
        BOM + MD_BYTES,
        MD_BYTES.replace(b"\n", b"\r\n"),
        b'<p align="center">a logo line</p>\n\n# Title\n',
        "# Café — résumé\n".encode(),
        b"no heading at all, only text\n",
    ],
    ids=["bom", "crlf", "inline-html-first", "non-ascii", "no-heading"],
)
def test_utf8_text_is_accepted_and_stored_as_it_came(
    md_catalog, library, scripted, capsys, body
):
    scripted.responses[MD_URL] = ok(body, PLAIN)
    code, out = run(capsys, md_catalog, "fetch", "RVW", "--no-extract")
    assert code == 0, out
    assert "fetched RVW 1.0 via direct" in out.splitlines()
    assert (version_dir(library) / "original.md").read_bytes() == body


@pytest.mark.parametrize(
    "body, ctype",
    [
        (b"<!DOCTYPE html>\n<html><body>Not found</body></html>", "text/html"),
        (b"\n \t<!doctype HTML>\n<p>Sign in</p>", "text/html; charset=utf-8"),
        (b"<HtMl lang='en'><body>Access denied</body></html>", "text/html"),
        (BOM + b"  <html>\n<body>Blocked</body></html>", "text/html"),
        (b"# A title\n\xff\xfe\xfa not UTF-8\n", PLAIN),
    ],
    ids=["doctype", "doctype-after-space", "html-mixed-case", "bom-html", "not-utf8"],
)
def test_a_body_that_is_not_markdown_fails_the_step_and_the_chain_goes_on(
    md_catalog, library, scripted, capsys, body, ctype
):
    scripted.responses[MD_URL] = ok(body, ctype)
    code, out = run(capsys, md_catalog, "fetch", "RVW")
    assert code == 2, out
    assert f"direct: not a md ({ctype}, {len(body)} bytes)" in out
    # the chain went on: wayback was asked, then the manual instructions
    assert any(url.startswith(fetch_mod.WAYBACK_AVAILABLE) for url in scripted.calls)
    assert "wayback: " in out
    assert str(version_dir(library) / "original.md") in out
    assert "bmcspec scan" in out
    assert "Traceback" not in out and "KeyError" not in out
    assert not (version_dir(library) / "original.md").exists()


def test_the_wayback_snapshot_is_taken_when_the_publisher_serves_html(
    md_catalog, library, scripted, capsys
):
    stamp = "20261001000000"
    scripted.responses[MD_URL] = ok(b"<html><body>Moved</body></html>", "text/html")
    scripted.responses[fetch_mod.WAYBACK_AVAILABLE + MD_URL] = wayback_hit(
        MD_URL, stamp
    )
    snapshot = f"http://web.archive.org/web/{stamp}id_/{MD_URL}"
    scripted.responses[snapshot] = ok(MD_BYTES, PLAIN)
    code, out = run(capsys, md_catalog, "fetch", "RVW")
    assert code == 0, out
    assert "fetched RVW 1.0 via wayback" in out.splitlines()
    assert (version_dir(library) / "original.md").read_bytes() == MD_BYTES


# ------------------------------------------------------------------- AC-3


def test_add_accepts_a_markdown_file(md_catalog, library, tmp_path, capsys):
    code, out, source = add_bytes(capsys, md_catalog, tmp_path, MD_BYTES)
    assert code == 0, out
    vdir = version_dir(library)
    assert out.splitlines()[-1] == f"added RVW 1.0 as Drop-in at {vdir}"
    assert (vdir / "original.md").read_bytes() == MD_BYTES
    assert source.is_file()


@pytest.mark.parametrize(
    "data",
    [
        b"<!DOCTYPE html><html><body>saved page</body></html>",
        b" \n<HTML><body>saved page</body></HTML>",
        b"# fine start\n" + b"\xff" * 16,
    ],
    ids=["doctype", "html", "not-utf8"],
)
def test_add_refuses_a_md_file_that_is_not_markdown(
    md_catalog, library, tmp_path, capsys, data
):
    code, out, source = add_bytes(capsys, md_catalog, tmp_path, data)
    assert code == 2
    assert out.strip() == f"{source} is not a md (wrong leading bytes); not added"
    assert not version_dir(library).exists()


def test_add_names_md_among_the_types_it_takes(md_catalog, tmp_path, capsys):
    source = tmp_path / "spec.txt"
    source.write_bytes(b"# Title\n")
    code, out = run(
        capsys, md_catalog, "add", str(source), "--document", "RVW", "--version", "1.0"
    )
    assert code == 2
    assert out.strip() == "unsupported file type '.txt': expected .pdf, .zip or .md"


def test_scan_registers_original_md_and_skips_one_that_is_not_markdown(
    md_catalog, library, capsys
):
    good = version_dir(library)
    good.mkdir(parents=True)
    (good / "original.md").write_bytes(MD_BYTES)
    bad = version_dir(library, "0.9")
    bad.mkdir(parents=True)
    (bad / "original.md").write_bytes(b"<html><body>Access Denied</body></html>")
    code, out = run(capsys, md_catalog, "scan")
    assert code == 0, out
    lines = out.splitlines()
    assert "registered RVW 1.0 as Drop-in" in lines
    skipped = [ln for ln in lines if ln.startswith(f"skipped {bad}")]
    assert len(skipped) == 1, out
    assert "'original.md' is not a md (wrong leading bytes)" in skipped[0]
    assert lines[-1] == "scan: registered 1, skipped 1"
    assert (good / "meta.json").is_file()
    assert not (bad / "meta.json").exists()
    # the registered Drop-in is readable
    code, out = run(capsys, md_catalog, "section", "RVW", "glossary")
    assert code == 0, out
    assert out.splitlines()[-1] == "0 | Glossary | lines 22-23"


# ------------------------------------------------------------------- AC-4


def test_extract_prints_the_line_and_heading_counts(
    md_catalog, library, scripted, capsys
):
    scripted.responses[MD_URL] = ok(MD_BYTES, PLAIN)
    code, out = run(capsys, md_catalog, "fetch", "RVW", "--no-extract")
    assert code == 0, out
    assert not said(out, "extracted ")
    code, out = run(capsys, md_catalog, "extract", "RVW")
    assert (code, out.strip()) == (0, EXTRACTED)


def test_only_atx_headings_outside_fences_enter_the_outline(
    md_catalog, library, tmp_path, capsys
):
    code, out, _ = add_bytes(capsys, md_catalog, tmp_path, HEADING_CASES.encode())
    assert code == 0, out
    code, out = run(capsys, md_catalog, "extract", "RVW")
    assert code == 0, out
    assert out.strip() == "extracted RVW 1.0: 9 lines, outline headings (3 entries)"
    # level is the number of marks minus one
    for query, line in [
        ("one", "0 | One | lines 1-9"),
        ("two", "1 | Two | lines 5-9"),
        ("six", "5 | Six | lines 9-9"),
    ]:
        code, out = run(capsys, md_catalog, "section", "RVW", query)
        assert (code, out.splitlines()) == (0, [line])
    for query in ("comment", "four", "nospace", "seven"):
        code, out = run(capsys, md_catalog, "section", "RVW", query)
        assert (code, out.strip()) == (0, "no matching section"), query


def test_a_file_without_headings_extracts_with_no_entries(
    md_catalog, library, tmp_path, capsys
):
    code, out, _ = add_bytes(capsys, md_catalog, tmp_path, b"just text\nmore text\n")
    assert code == 0, out
    code, out = run(capsys, md_catalog, "extract", "RVW")
    assert (code, out.strip()) == (
        0,
        "extracted RVW 1.0: 2 lines, outline headings (0 entries)",
    )
    code, out = run(capsys, md_catalog, "find", "RVW", "more")
    assert (code, out.strip()) == (0, "RVW l.2 | - | more text")


def test_extract_all_takes_a_markdown_version_beside_a_bundle(
    md_catalog, library, scripted, capsys
):
    scripted.responses[MD_URL] = ok(MD_BYTES, PLAIN)
    scripted.responses[BUNDLE_URL] = ok(ZIP_BYTES, "application/zip")
    code, out = run(capsys, md_catalog, "fetch", "RVW", "--no-extract")
    assert code == 0, out
    code, out = run(capsys, md_catalog, "fetch", "BUNDLE", "--no-extract")
    assert code == 0, out
    code, out = run(capsys, md_catalog, "extract", "--all")
    assert code == 0, out
    lines = out.splitlines()
    assert EXTRACTED in lines
    assert lines[-1] == "summary: extracted 1, skipped 1, failed 0"


# ------------------------------------------------------------------- AC-5


def status_row(capsys, catalog):
    code, out = run(capsys, catalog, "status")
    assert code == 0, out
    rows = [ln.split("\t") for ln in out.splitlines() if "\tRVW\t" in ln]
    assert len(rows) == 1, out
    return rows[0]


def test_status_goes_from_dash_to_extracted_to_stale_and_back(
    md_catalog, library, scripted, capsys
):
    scripted.responses[MD_URL] = ok(MD_BYTES, PLAIN)
    run(capsys, md_catalog, "fetch", "RVW", "--no-extract")
    row = status_row(capsys, md_catalog)
    assert row[:3] == ["security", "RVW", "1.0"]
    assert row[5:] == ["-", "-"]

    run(capsys, md_catalog, "extract", "RVW")
    assert status_row(capsys, md_catalog)[5:] == ["extracted", "headings"]

    # an extract written by an older Markdown extractor
    meta_path = version_dir(library) / "extract.json"
    meta = json.loads(meta_path.read_text("utf-8"))
    assert isinstance(meta["extractor_version"], int)
    meta["extractor_version"] -= 1
    meta_path.write_text(json.dumps(meta), encoding="utf-8", newline="")
    assert status_row(capsys, md_catalog)[5] == "stale"

    # a reading command brings it back to Ready by itself
    code, out = run(capsys, md_catalog, "section", "RVW", "glossary")
    assert code == 0, out
    assert out.splitlines() == [EXTRACTED, "0 | Glossary | lines 22-23"]
    assert status_row(capsys, md_catalog)[5:] == ["extracted", "headings"]


@pytest.mark.parametrize(
    "argv, answer",
    [
        (["section", "RVW", "glossary"], "0 | Glossary | lines 22-23"),
        (["find", "RVW", "read-only"], "RVW l.23 | Glossary | ROM: read-only memory."),
        (["page", "RVW", "--lines", "23-23"], "23  ROM: read-only memory."),
    ],
    ids=["section", "find", "page"],
)
def test_a_reading_command_fetches_and_extracts_first(
    md_catalog, library, scripted, capsys, argv, answer
):
    scripted.responses[MD_URL] = ok(MD_BYTES, PLAIN)
    code, out = run(capsys, md_catalog, *argv)
    assert code == 0, out
    lines = out.splitlines()
    assert "fetched RVW 1.0 via direct" in lines
    assert EXTRACTED in lines
    assert lines.index("fetched RVW 1.0 via direct") < lines.index(EXTRACTED)
    assert lines[-1] == answer
    assert (version_dir(library) / "original.md").read_bytes() == MD_BYTES
    # the second call finds it Ready: nothing fetched, nothing extracted
    scripted.calls.clear()
    code, out = run(capsys, md_catalog, *argv)
    assert code == 0, out
    assert scripted.calls == []
    assert not said(out, "fetched ") and not said(out, "extracted ")

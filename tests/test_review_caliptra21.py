"""Reviewer acceptance tests for Caliptra 2.1 as a Work-in-Progress Markdown
version of CALIPTRA: the catalog entry (AC-1), 2.0 staying the Latest
(AC-2), every Markdown URL pinned to a commit (AC-3), and the reading path
of AC-4 as far as it goes without the network.

Black-box: the shipped catalog through ``load_catalog`` and
``bmc_toolkit.spec.cli.main``, with conftest's scripted client in place of
the network. The Markdown body served for 2.1 is a few hand-written lines,
not the publisher's text; what AC-4 says about the real file (1779 lines,
``lines 1300-1313``, the blob id) needs the network and is not checked.
"""

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import PDF_BYTES, ok

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "e81808ad1983e7582fd587c9ddae4b40331682c4"
RAW_URL = (
    f"https://raw.githubusercontent.com/chipsalliance/Caliptra/{COMMIT}/doc/Caliptra.md"
)
PLAIN = "text/plain; charset=utf-8"

# The synthetic body served at RAW_URL. The position in the list is the
# line number minus one.
MD_LINES = [
    "# Synthetic root of trust",  # 1
    "",  # 2
    "## Fuses",  # 3
    "Fuses are programmed once.",  # 4
    "### Fuse zeroing",  # 5
    "Zeroing clears a programmed fuse.",  # 6
    "It cannot be undone.",  # 7
    "## Keys",  # 8
    "Keys are derived at boot.",  # 9
]
MD_BYTES = ("\n".join(MD_LINES) + "\n").encode("utf-8")

_SHA = re.compile(r"[0-9a-f]{40}")


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


@pytest.fixture
def pdf_url(shipped):
    """The URL the catalog gives CALIPTRA 2.0, the published PDF."""
    return shipped.get("CALIPTRA").find_version("2.0").url


def run(capsys, *argv, catalog_file=None):
    """main() on the shipped catalog, or on ``catalog_file``."""
    head = ["--catalog", str(catalog_file)] if catalog_file else []
    code = main([*head, *argv])
    return code, capsys.readouterr().out


def real_pdf(tmp_path):
    """A one-page PDF that extracts, with one bookmark ``1 Intro``."""
    page = pdfgen.plain_page(["1 Intro", "alpha", "beta"])
    path = pdfgen.write_pdf(tmp_path / "published.pdf", [page], [(0, "1 Intro", 0)])
    return path.read_bytes()


def _q(text):
    return json.dumps(text, ensure_ascii=False)


def caliptra_only(tmp_path, shipped, name="caliptra.toml"):
    """A catalog file holding CALIPTRA and its family as the shipped catalog
    parses them, so ``fetch --all`` has one document to go through."""
    doc = shipped.get("CALIPTRA")
    family = shipped.families[doc.family]
    out = [
        "schema_version = 1",
        "",
        f"[families.{doc.family}]",
        f"title = {_q(family.title)}",
        f"publisher = {_q(family.publisher)}",
        "",
        "[[documents]]",
        f"id = {_q(doc.id)}",
        f"family = {_q(doc.family)}",
        f"title = {_q(doc.title)}",
        f"access = {_q(doc.access)}",
        f"fetch = {_q(doc.fetch)}",
    ]
    for v in doc.versions:
        out += [
            "",
            "[[documents.versions]]",
            f"version = {_q(v.version)}",
            f"url = {_q(v.url)}",
            f"type = {_q(v.type)}",
            f"published = {_q(v.published)}",
            f"wip = {'true' if v.wip else 'false'}",
            f"access = {_q(v.access)}",
            f"notes = {_q(v.notes)}",
        ]
    path = tmp_path / name
    path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="")
    copy = load_catalog(path).get("CALIPTRA")
    assert copy.versions == doc.versions  # the file says what the catalog says
    return path


def unpinned(catalog):
    """(document, version, URL) of every Markdown version whose URL has no
    path segment that is a 40-hex-digit commit id."""
    return [
        (d.id, v.version, v.url)
        for d in catalog.documents
        for v in d.versions
        if v.type == "md"
        and not any(_SHA.fullmatch(part) for part in urlsplit(v.url).path.split("/"))
    ]


# ------------------------------------------------------------------- AC-1


def test_ac1_caliptra_gains_2_1_after_2_0(shipped):
    doc = shipped.get("CALIPTRA")
    assert [v.version for v in doc.versions] == ["2.0", "2.1"]
    old, new = doc.versions
    # 2.0 is the published PDF it was
    assert (old.type, old.wip, old.open, old.published) == (
        "pdf",
        False,
        True,
        "2025-07-31",
    )
    assert new.type == "md"
    assert new.url == RAW_URL
    assert new.published == "2026-09-17"
    assert new.wip is True
    assert new.open
    # the version note names the repository and the short commit
    assert "chipsalliance/Caliptra" in new.notes
    assert COMMIT[:7] in new.notes
    # the document's notes tell the two versions apart and how to read 2.1
    assert "2.0" in doc.notes and "2.1" in doc.notes
    assert "--version 2.1" in doc.notes


def test_ac1_catalog_lists_2_1_first_with_md_and_wip(pdf_url, capsys):
    code, out = run(capsys, "catalog", "CALIPTRA")
    assert code == 0, out
    lines = out.splitlines()
    assert "latest: 2.0" in lines
    assert any(ln.startswith("notes: ") and "--version 2.1" in ln for ln in lines)
    rows = [ln.split("\t") for ln in lines[lines.index("versions:") + 1 :]]
    assert rows == [
        ["", "2.1", "2026-09-17", "md", "wip", RAW_URL, "open"],
        ["", "2.0", "2025-07-31", "pdf", "published", pdf_url, "open"],
    ]


# ------------------------------------------------------------------- AC-2


def test_ac2_the_latest_stays_2_0(shipped, capsys):
    doc = shipped.get("CALIPTRA")
    assert doc.latest(include_wip=True).version == "2.1"
    assert doc.latest().version == "2.0"
    assert doc.newest_open().version == "2.0"
    # the one-line listing: latest 2.0, both versions known
    code, out = run(capsys, "catalog", "--family", doc.family)
    assert code == 0, out
    (row,) = [
        ln.split("\t") for ln in out.splitlines() if ln.split("\t")[1] == "CALIPTRA"
    ]
    assert row[4] == "2.0"
    assert row[6] == "2.0;2.1"


def test_ac2_fetch_without_version_takes_2_0_and_wip_takes_2_1(
    library, scripted, pdf_url, capsys
):
    scripted.responses[pdf_url] = ok(PDF_BYTES)
    scripted.responses[RAW_URL] = ok(MD_BYTES, PLAIN)
    code, out = run(capsys, "fetch", "CALIPTRA", "--no-extract")
    assert code == 0, out
    assert "fetched CALIPTRA 2.0 via direct" in out.splitlines()
    assert scripted.calls == [pdf_url]
    code, out = run(capsys, "fetch", "CALIPTRA", "--wip", "--no-extract")
    assert code == 0, out
    assert "fetched CALIPTRA 2.1 via direct" in out.splitlines()
    assert scripted.calls == [pdf_url, RAW_URL]
    held = library.specs / "ocp-security" / "CALIPTRA"
    assert (held / "2.0" / "original.pdf").read_bytes() == PDF_BYTES
    assert (held / "2.1" / "original.md").read_bytes() == MD_BYTES


def test_ac2_fetch_all_takes_2_0_and_2_1_only_with_wip(
    tmp_path, shipped, library, scripted, pdf_url, capsys
):
    catalog_file = caliptra_only(tmp_path, shipped)
    scripted.responses[pdf_url] = ok(PDF_BYTES)
    scripted.responses[RAW_URL] = ok(MD_BYTES, PLAIN)
    code, out = run(capsys, "fetch", "--all", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert "fetched CALIPTRA 2.0 via direct" in lines
    assert not any("CALIPTRA 2.1" in ln for ln in lines)
    assert lines[-1] == "summary: fetched 1, skipped 0, failed 0"
    assert scripted.calls == [pdf_url]
    assert not (library.specs / "ocp-security" / "CALIPTRA" / "2.1").exists()
    code, out = run(capsys, "fetch", "--all", "--wip", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert "fetched CALIPTRA 2.1 via direct" in lines
    assert lines[-1] == "summary: fetched 1, skipped 0, failed 0"
    assert scripted.calls == [pdf_url, RAW_URL]


def test_ac2_a_question_without_version_reads_the_pdf_though_2_1_is_held(
    tmp_path, library, scripted, pdf_url, capsys
):
    """2.1 is held and Ready; a reading command that does not ask for it
    still downloads 2.0 and answers with pages, not with lines."""
    scripted.responses[RAW_URL] = ok(MD_BYTES, PLAIN)
    code, out = run(capsys, "fetch", "CALIPTRA", "--version", "2.1")
    assert code == 0, out
    assert "fetched CALIPTRA 2.1 via direct" in out.splitlines()
    scripted.responses[pdf_url] = ok(real_pdf(tmp_path))
    code, out = run(capsys, "section", "CALIPTRA", "intro")
    assert code == 0, out
    lines = out.splitlines()
    assert "fetched CALIPTRA 2.0 via direct" in lines
    assert " | pages " in lines[-1] and "1 Intro" in lines[-1]
    assert not any(" | lines " in ln for ln in lines)
    assert scripted.calls == [RAW_URL, pdf_url]
    # both are held now: the same question is answered from 2.0, offline
    code, again = run(capsys, "section", "CALIPTRA", "intro")
    assert (code, again.splitlines()) == (0, [lines[-1]])
    assert scripted.calls == [RAW_URL, pdf_url]


def test_ac2_the_support_table_row_still_names_2_0(shipped, capsys):
    assert shipped.get("CALIPTRA").find_version("2.1") is not None
    golden = ROOT / "docs" / "golden-questions.md"
    code, out = run(
        capsys, "catalog", "--table", "--by-family", "--golden", str(golden)
    )
    assert code == 0, out
    (row,) = [ln for ln in out.splitlines() if ln.startswith("| `CALIPTRA` ")]
    assert row.split(" | ")[1:3] == ["open", "2.0"]
    # docs/SUPPORT.md holds the row the command prints
    support = (ROOT / "docs" / "SUPPORT.md").read_text(encoding="utf-8")
    assert row in support.splitlines()


# ------------------------------------------------------------------- AC-3


def test_ac3_every_markdown_version_is_pinned_to_a_commit(tmp_path, shipped):
    markdown = [
        (d.id, v.version)
        for d in shipped.documents
        for v in d.versions
        if v.type == "md"
    ]
    assert ("CALIPTRA", "2.1") in markdown
    assert unpinned(shipped) == []
    # the same check on a catalog whose Markdown URL names a branch, a tag,
    # a short commit id or 39 hex digits: each one is reported
    pinned = caliptra_only(tmp_path, shipped).read_text(encoding="utf-8")
    assert COMMIT in pinned
    for ref in ("main", "v2.1", COMMIT[:7], COMMIT[:39]):
        path = tmp_path / "moved.toml"
        path.write_text(pinned.replace(COMMIT, ref), encoding="utf-8", newline="")
        assert unpinned(load_catalog(path)) == [
            ("CALIPTRA", "2.1", RAW_URL.replace(COMMIT, ref))
        ], ref


# ------------------------------------------- AC-4, as far as it is offline


def test_version_2_1_is_fetched_from_the_pinned_url_and_cited_by_line(
    library, scripted, capsys
):
    scripted.responses[RAW_URL] = ok(MD_BYTES, PLAIN)
    code, out = run(capsys, "section", "CALIPTRA", "fuse zeroing", "--version", "2.1")
    assert code == 0, out
    lines = out.splitlines()
    assert "fetched CALIPTRA 2.1 via direct" in lines
    assert "extracted CALIPTRA 2.1: 9 lines, outline headings (4 entries)" in lines
    assert lines[-1] == "2 | Fuse zeroing | lines 5-7"
    # only the pinned URL was asked for: the 2.0 PDF is not touched
    assert scripted.calls == [RAW_URL]
    vdir = library.specs / "ocp-security" / "CALIPTRA" / "2.1"
    assert (vdir / "original.md").read_bytes() == MD_BYTES
    assert not (library.specs / "ocp-security" / "CALIPTRA" / "2.0").exists()

    code, out = run(
        capsys, "page", "CALIPTRA", "--section", "fuse zeroing", "--version", "2.1"
    )
    assert code == 0, out
    assert out.splitlines() == [
        "cite: ocp-security | CALIPTRA 2.1 | Fuse zeroing | Markdown | lines 5-7 | "
        f"{RAW_URL} | {vdir}",
        "5  ### Fuse zeroing",
        "6  Zeroing clears a programmed fuse.",
        "7  It cannot be undone.",
    ]
    assert scripted.calls == [RAW_URL]


def test_a_failed_download_of_2_1_is_exit_2_and_stores_nothing(
    library, scripted, capsys
):
    """The error path: the pinned URL does not answer (the scripted client
    raises OSError for it and for the Archive), so no original is held and
    the 2.0 PDF does not stand in for the version asked for."""
    code, out = run(capsys, "section", "CALIPTRA", "fuse zeroing", "--version", "2.1")
    assert code == 2, out
    lines = out.splitlines()
    assert "failed CALIPTRA 2.1" in lines
    assert f"Open in a browser: {RAW_URL}" in lines
    assert scripted.calls[0] == RAW_URL
    held = library.specs / "ocp-security" / "CALIPTRA"
    assert not (held / "2.1" / "original.md").exists()
    assert not (held / "2.0").exists()

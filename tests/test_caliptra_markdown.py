"""Caliptra 2.1 as a Markdown version of CALIPTRA (T5.2): the catalog entry,
2.0 staying the latest, every Markdown URL pinned to a commit, and the
query words the section matchers share."""

import re
from pathlib import Path

import pytest

from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from bmc_toolkit.spec.markdown import MarkdownVersion
from bmc_toolkit.spec.search import query_words
from tests.conftest import PDF_BYTES, ok

ROOT = Path(__file__).resolve().parent.parent
CATALOG_TOML = ROOT / "bmc_toolkit" / "spec" / "catalog.toml"
COMMIT = "e81808ad1983e7582fd587c9ddae4b40331682c4"
RAW = (
    f"https://raw.githubusercontent.com/chipsalliance/Caliptra/{COMMIT}/doc/Caliptra.md"
)
PDF_URL = "https://www.opencompute.org/documents/caliptra-2-0-pdf"
_COMMIT_SEGMENT = re.compile(r"/[0-9a-f]{40}/")


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def run(capsys, *argv, catalog_file=None):
    args = ["--catalog", str(catalog_file)] if catalog_file else []
    code = main([*args, *argv])
    return code, capsys.readouterr().out


# ------------------------------------------------------------------ AC-1


def test_caliptra_2_1_is_a_wip_markdown_version_pinned_to_a_commit(shipped):
    doc = shipped.get("CALIPTRA")
    assert [v.version for v in doc.versions] == ["2.0", "2.1"]
    ver = doc.find_version("2.1")
    assert ver.type == "md" and ver.wip and ver.open
    assert ver.url == RAW
    assert ver.published == "2026-09-17"
    assert "chipsalliance/Caliptra" in ver.notes and "e81808a" in ver.notes
    assert "--version 2.1" in doc.notes and "2.0" in doc.notes


def test_catalog_lists_2_1_first_as_md_and_wip(capsys):
    code, out = run(capsys, "catalog", "CALIPTRA")
    assert code == 0
    rows = out.split("versions:\n", 1)[1].splitlines()
    assert rows[0].split("\t")[1:5] == ["2.1", "2026-09-17", "md", "wip"]
    assert rows[1].split("\t")[1:5] == ["2.0", "2025-07-31", "pdf", "published"]


# ------------------------------------------------------------------ AC-2


def test_2_0_stays_the_latest(shipped):
    doc = shipped.get("CALIPTRA")
    assert doc.latest().version == "2.0"
    assert doc.newest_open().version == "2.0"
    assert doc.latest(include_wip=True).version == "2.1"


def _caliptra_only(tmp_path):
    """A catalog file holding the shipped CALIPTRA block and its family."""
    text = CATALOG_TOML.read_text("utf-8")
    start = text.index('[[documents]]\nid = "CALIPTRA"')
    end = text.index("[[documents]]", start + 1)
    path = tmp_path / "catalog.toml"
    path.write_text(
        "schema_version = 1\n\n"
        '[families.ocp-security]\ntitle = "OCP Security"\n'
        'publisher = "Open Compute Project"\n\n' + text[start:end],
        encoding="utf-8",
        newline="",
    )
    return path


def test_fetch_all_takes_2_0_and_2_1_only_with_wip(tmp_path, library, scripted, capsys):
    catalog_file = _caliptra_only(tmp_path)
    scripted.responses[PDF_URL] = ok(PDF_BYTES)
    scripted.responses[RAW] = ok(b"# Caliptra\n\nText.\n", "text/plain")
    code, out = run(capsys, "fetch", "--all", catalog_file=catalog_file)
    assert code == 0, out
    assert "fetched CALIPTRA 2.0 via direct" in out
    assert "CALIPTRA 2.1" not in out
    assert scripted.calls == [PDF_URL]
    code, out = run(capsys, "fetch", "--all", "--wip", catalog_file=catalog_file)
    assert code == 0, out
    assert "fetched CALIPTRA 2.1 via direct" in out
    assert scripted.calls == [PDF_URL, RAW]


def test_support_row_is_unchanged():
    lines = (ROOT / "docs" / "SUPPORT.md").read_text("utf-8").splitlines()
    (row,) = [ln for ln in lines if ln.startswith("| `CALIPTRA` ")]
    assert row.split(" | ")[1:] == ["open", "2.0", "PASS", "- |"]


# ------------------------------------------------------------------ AC-3


def test_every_markdown_version_pins_a_commit(shipped):
    md = [
        (d.id, v.version, v.url)
        for d in shipped.documents
        for v in d.versions
        if v.type == "md"
    ]
    assert md, "the catalog holds no Markdown version"
    for doc_id, version, url in md:
        assert _COMMIT_SEGMENT.search(url), (doc_id, version, url)


@pytest.mark.parametrize(
    "url",
    [
        "https://raw.githubusercontent.com/chipsalliance/Caliptra/main/doc/Caliptra.md",
        "https://raw.githubusercontent.com/chipsalliance/Caliptra/v2.1/doc/Caliptra.md",
        "https://raw.githubusercontent.com/o/r/e81808a/doc/Caliptra.md",
    ],
    ids=["branch", "tag", "short-sha"],
)
def test_an_unpinned_url_is_caught(url):
    assert not _COMMIT_SEGMENT.search(url)


# ------------------------------------------------------------------ AC-7


@pytest.mark.parametrize(
    "query, words",
    [
        ("  Fuses   Goals. ", ["fuses", "goals"]),
        ("FUSE\tzeroing", ["fuse", "zeroing"]),
        ("5.2.", ["5.2"]),
        ("e.g. foo", ["e.g.", "foo"]),
        ("   ", []),
    ],
)
def test_query_words(query, words):
    assert query_words(query) == words


def test_markdown_matching_uses_the_shared_query_words(tmp_path, monkeypatch):
    from bmc_toolkit.spec import markdown

    original = tmp_path / "original.md"
    original.write_bytes(b"# Fuses\n## Goals\n# Keys\n## Goals\n")
    markdown.extract(original, tmp_path)
    version = MarkdownVersion.load(
        family="f", document="D", version="1", path=tmp_path, original=original
    )
    seen = []

    def spy(query):
        seen.append(query)
        return query_words(query)

    monkeypatch.setattr(markdown, "query_words", spy)
    found = [h.label for _, h, _ in version.match_sections("keys goals")]
    assert found == ["Keys > Goals"]
    assert seen == ["keys goals"]

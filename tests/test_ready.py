"""The reading commands bring the document to Ready themselves (fewer
round trips change, AC-1 to AC-8): download the catalog's Latest or the
version asked for, extract it, answer, then run a due Freshness Check and
report it as a note; `[library] offline` turns the network off; `fetch`
leaves a version Ready; SKILL.md tells the Session to locate first."""

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bmc_toolkit.spec import cli
from bmc_toolkit.spec import fetch as fetch_mod
from bmc_toolkit.spec import freshness as F
from bmc_toolkit.spec import listing as L
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import MINI_CATALOG, PDF_BYTES, ok, wayback_hit
from tests.test_bundle import bundle_bytes
from tests.test_listing import DMTF_PUBLISHED_HTML
from tests.test_lock import fake_lock

pytest.importorskip("pypdfium2")

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"
URL = "https://example.test/DSP0236_1.3.3.pdf"
OLD_URL = "https://example.test/DSP0236_1.3.2.pdf"
BUNDLE_URL = "https://example.test/bundle_2026.1.zip"
# The real after-output check, captured before conftest's autouse fixture
# replaces it for the tests that do not want the network.
CHECK_WHEN_DUE = cli._check_when_due

READING = {
    "find": ["find", "DSP0236", "alpha"],
    "section": ["section", "DSP0236", "Intro"],
    "page": ["page", "DSP0236", "1"],
    "render": ["render", "DSP0236", "--page", "1"],
}

NO_VERSIONS_CATALOG = (
    MINI_CATALOG
    + """
[[documents]]
id = "NDA"
family = "vendor"
title = "A datasheet under NDA"
access = "confidential"
fetch = "manual"
"""
)

OLDER_CATALOG = MINI_CATALOG.replace(
    """[[documents.versions]]
version = "1.3.3"
url = "https://example.test/DSP0236_1.3.3.pdf"
type = "pdf"
published = "2024-03-25"

""",
    "",
)
assert '"1.3.3"' not in OLDER_CATALOG


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def pdf_bytes(tmp_path, name="a.pdf", lines=("1 Intro", "alpha", "beta")):
    page = pdfgen.plain_page(list(lines))
    marks = [(0, lines[0], 0)]
    return pdfgen.write_pdf(tmp_path / name, [page], bookmarks=marks).read_bytes()


def html(text):
    return ok(text.encode("utf-8"), "text/html")


@pytest.fixture
def checking(monkeypatch):
    """The after-output Freshness Check, on."""
    monkeypatch.setattr(cli, "_check_when_due", CHECK_WHEN_DUE)


@pytest.fixture
def ready(catalog_file, library, scripted, tmp_path, capsys):
    """DSP0236 1.3.3 Ready; the client's call log cleared."""
    scripted.responses[URL] = ok(pdf_bytes(tmp_path))
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    scripted.calls.clear()
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def freshness(library) -> dict:
    return json.loads((library.root / F.FRESHNESS_NAME).read_text("utf-8"))


# ----------------------------------------------------------------- AC-1


@pytest.mark.parametrize("command", sorted(READING))
def test_reading_a_missing_document_downloads_extracts_and_answers(
    command, catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[URL] = ok(pdf_bytes(tmp_path))
    code, out = run(capsys, *READING[command], catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == f"Library created at {library.root}"
    assert lines[1] == "fetched DSP0236 1.3.3 via direct"
    assert lines[2].startswith("extracted DSP0236 1.3.3: 1 pages in ")
    assert len(lines) > 3, out  # then the answer
    assert scripted.calls == [URL]
    # Ready now: the same call prints the answer alone, byte for byte twice
    # (render says "existing" from the second run on)
    code, again = run(capsys, *READING[command], catalog_file=catalog_file)
    assert code == 0
    if command != "render":
        assert again == "\n".join(lines[3:]) + "\n"
    assert run(capsys, *READING[command], catalog_file=catalog_file) == (0, again)
    assert scripted.calls == [URL]


def test_table_shares_the_ready_path(catalog_file, library, scripted, tmp_path, capsys):
    pytest.importorskip("pdfplumber")
    scripted.responses[URL] = ok(pdf_bytes(tmp_path))
    code, out = run(
        capsys, "table", "DSP0236", "--page", "1", catalog_file=catalog_file
    )
    assert code == 2, out  # the page has no table; the document is Ready
    lines = out.splitlines()
    assert lines[1] == "fetched DSP0236 1.3.3 via direct"
    assert lines[2].startswith("extracted DSP0236 1.3.3")
    assert lines[3].startswith("no table on page 1 of DSP0236 1.3.3")


def test_latest_is_fetched_even_when_an_older_version_is_held(
    catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[OLD_URL] = ok(pdf_bytes(tmp_path, "old.pdf", ["old text"]))
    scripted.responses[URL] = ok(pdf_bytes(tmp_path))
    run(capsys, "fetch", "DSP0236", "--version", "1.3.2", catalog_file=catalog_file)
    scripted.calls.clear()
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "fetched DSP0236 1.3.3 via direct"
    assert lines[2].startswith("cite: mctp | DSP0236 1.3.3 | ")
    assert "alpha" in out and "old text" not in out
    assert scripted.calls == [URL]


def test_a_held_version_that_is_not_ready_is_extracted_not_downloaded(
    catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[URL] = ok(pdf_bytes(tmp_path))
    run(capsys, "fetch", "DSP0236", "--no-extract", catalog_file=catalog_file)
    scripted.calls.clear()
    code, out = run(capsys, "section", "DSP0236", "Intro", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("extracted DSP0236 1.3.3: 1 pages")
    assert "fetched" not in out
    assert lines[1].startswith("0 | 1 Intro | pages 1-1")
    assert scripted.calls == []


def test_a_stale_extract_is_redone_before_answering(
    ready, catalog_file, scripted, capsys
):
    meta = ready / "extract.json"
    data = json.loads(meta.read_text("utf-8"))
    data["extractor_version"] = 0
    meta.write_text(json.dumps(data), "utf-8")
    code, out = run(capsys, "find", "DSP0236", "alpha", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0].startswith("extracted DSP0236 1.3.3")
    assert scripted.calls == []


def test_companions_are_brought_to_ready_as_notes(library, scripted, tmp_path, capsys):
    from tests.test_search_cli import COMPANION_CATALOG, IPMI_URL, UPDATE_URL

    cat = tmp_path / "companion.toml"
    cat.write_text(COMPANION_CATALOG, encoding="utf-8", newline="")
    scripted.responses[IPMI_URL] = ok(pdf_bytes(tmp_path, "i.pdf", ["Get Device ID"]))
    scripted.responses[UPDATE_URL] = ok(
        pdf_bytes(tmp_path, "u.pdf", ["Get Device ID errata"])
    )
    code, out = run(capsys, "find", "IPMI", "get device id", catalog_file=cat)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[1] == "fetched IPMI 2.0 rev 1.1 via direct"
    assert lines[2].startswith("extracted IPMI 2.0 rev 1.1")
    assert lines[3] == "note: fetched IPMI-UPDATE Errata 7 via direct"
    assert lines[4].startswith("note: extracted IPMI-UPDATE Errata 7")
    assert lines[5].startswith("IPMI-UPDATE p.1 | ") and "errata" in lines[5]
    assert lines[6].startswith("IPMI p.1 | ") and "Get Device ID" in lines[6]
    assert scripted.calls == [IPMI_URL, UPDATE_URL]
    # a companion that cannot be downloaded is a note, never a failure
    del scripted.responses[UPDATE_URL]
    for p in (library.specs / "ipmi" / "IPMI-UPDATE").rglob("*"):
        if p.is_file():
            p.unlink()
    code, out = run(capsys, "find", "IPMI", "get device id", catalog_file=cat)
    assert code == 0, out
    lines = out.splitlines()
    assert "note: failed IPMI-UPDATE Errata 7" in lines
    assert f"note: Open in a browser: {UPDATE_URL}" in lines
    assert lines[-1].startswith("IPMI p.1 | ") and "Get Device ID" in lines[-1]


# ----------------------------------------------------------------- AC-2


def test_version_flag_fetches_that_version_and_refuses_an_unknown_one(
    ready, catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[OLD_URL] = ok(pdf_bytes(tmp_path, "old.pdf", ["old text"]))
    code, out = run(
        capsys, "page", "DSP0236", "1", "--version", "1.3.2", catalog_file=catalog_file
    )
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "fetched DSP0236 1.3.2 via direct"
    assert lines[2].startswith("cite: mctp | DSP0236 1.3.2 | ")
    assert "old text" in out
    assert scripted.calls == [OLD_URL]
    # exact match only, no prefix search; the known versions are listed
    code, out = run(
        capsys, "page", "DSP0236", "1", "--version", "1.3", catalog_file=catalog_file
    )
    assert code == 2
    assert out.splitlines()[0] == (
        "DSP0236 1.3 is not in the Library; held: 1.3.2, 1.3.3. "
        "Known: 1.3.2, 1.3.3, 1.4.0."
    )
    assert "run: bmcspec scan" in out
    assert scripted.calls == [OLD_URL]
    # a Drop-in of a version the catalog does not list is read as held
    src = tmp_path / "dropin.pdf"
    src.write_bytes(pdf_bytes(tmp_path, "d.pdf", ["dropped in"]))
    argv = ["add", str(src), "--document", "DSP0236", "--version", "7.7"]
    assert run(capsys, *argv, catalog_file=catalog_file)[0] == 0
    code, out = run(
        capsys, "page", "DSP0236", "1", "--version", "7.7", catalog_file=catalog_file
    )
    assert code == 0 and "dropped in" in out
    assert "user-provided" in out.splitlines()[1]
    assert scripted.calls == [OLD_URL]


# ----------------------------------------------------------------- AC-3


def test_gated_manual_and_busy_versions_are_not_downloaded(
    catalog_file, library, scripted, tmp_path, capsys
):
    code, out = run(capsys, "find", "SECRET", "x", catalog_file=catalog_file)
    assert code == 2
    lines = out.splitlines()
    assert lines[0] == "SECRET 0.9 is confidential: the tool does not download it."
    assert lines[1].startswith("Obtain 'A confidential datasheet' version 0.9")
    assert lines[-1] == "no open version is listed"
    cat = tmp_path / "nda.toml"
    cat.write_text(NO_VERSIONS_CATALOG, encoding="utf-8", newline="")
    code, out = run(capsys, "section", "NDA", "x", catalog_file=cat)
    assert code == 2
    assert out.strip() == (
        "NDA is confidential and lists no versions: the tool does not download "
        "it. Register the file you obtained with: bmcspec add FILE --document "
        "NDA --version V"
    )
    scripted.responses[URL] = ok(pdf_bytes(tmp_path))
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    fake_lock(vdir, command="fetch DSP0236 1.3.3")
    code, out = run(
        capsys, "--wait", "0", "page", "DSP0236", "1", catalog_file=catalog_file
    )
    assert code == 3, out
    assert out.strip().startswith(f"busy: {vdir / '.lock'} is held by pid 4242 ")
    assert scripted.calls == []
    assert not (vdir / "original.pdf").exists()


# ----------------------------------------------------------------- AC-4


def test_a_failed_download_falls_back_to_the_held_version_with_a_note(
    catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[OLD_URL] = ok(pdf_bytes(tmp_path, "old.pdf", ["old text"]))
    run(capsys, "fetch", "DSP0236", "--version", "1.3.2", catalog_file=catalog_file)
    scripted.calls.clear()
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("note: could not fetch DSP0236 1.3.3: direct: ")
    assert lines[0].endswith("; answering from held 1.3.2")
    assert lines[1].startswith("cite: mctp | DSP0236 1.3.2 | ")
    assert "old text" in out
    assert URL in scripted.calls  # the download was tried before the fallback


def test_a_failed_download_with_nothing_held_is_exit_2_with_the_save_path(
    catalog_file, library, scripted, capsys
):
    code, out = run(capsys, "find", "DSP0236", "x", catalog_file=catalog_file)
    assert code == 2, out
    lines = out.splitlines()
    assert "failed DSP0236 1.3.3" in lines
    assert f"Open in a browser: {URL}" in lines
    save = library.specs / "mctp" / "DSP0236" / "1.3.3" / "original.pdf"
    assert f"Save it as: {save}" in lines
    assert lines[-1] == "Then run: bmcspec scan"
    # a version asked for is not replaced by another held one
    code, out = run(
        capsys, "find", "DSP0236", "x", "--version", "1.3.2", catalog_file=catalog_file
    )
    assert code == 2 and "failed DSP0236 1.3.2" in out.splitlines()


# ----------------------------------------------------------------- AC-5


def test_a_due_freshness_check_runs_after_the_answer(
    ready, catalog_file, library, scripted, checking, capsys
):
    scripted.responses[L.DMTF_PUBLISHED] = html(DMTF_PUBLISHED_HTML)
    code, out = run(capsys, "find", "DSP0236", "alpha", catalog_file=catalog_file)
    assert code == 0, out
    assert "note" not in out  # current: nothing to say
    assert "run: bmcspec check" not in out
    assert scripted.calls == [L.DMTF_PUBLISHED]
    assert freshness(library)["documents"]["DSP0236"]["catalog_latest"] == "1.3.3"
    # stamped: not again within freshness_days
    code, out = run(capsys, "find", "DSP0236", "alpha", catalog_file=catalog_file)
    assert code == 0 and scripted.calls == [L.DMTF_PUBLISHED]
    state = F.Freshness(library.root)
    old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    state.data["documents"]["DSP0236"]["checked_at"] = old
    state.save()
    code, out = run(capsys, "find", "DSP0236", "alpha", catalog_file=catalog_file)
    assert code == 0 and scripted.calls == [L.DMTF_PUBLISHED] * 2
    # a failing command runs no check
    scripted.calls.clear()
    state.data["documents"]["DSP0236"]["checked_at"] = old
    state.save()
    code, out = run(capsys, "page", "DSP0236", "99", catalog_file=catalog_file)
    assert code == 2 and scripted.calls == []


def test_a_newer_publisher_version_is_a_note_never_a_download(
    library, scripted, tmp_path, checking, capsys
):
    cat = tmp_path / "older.toml"
    cat.write_text(OLDER_CATALOG, encoding="utf-8", newline="")
    scripted.responses[OLD_URL] = ok(pdf_bytes(tmp_path, "old.pdf", ["old text"]))
    scripted.responses[L.DMTF_PUBLISHED] = html(DMTF_PUBLISHED_HTML)
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=cat)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[1] == "fetched DSP0236 1.3.2 via direct"
    assert lines[-1] == (
        "note: newer DSP0236: catalog latest 1.3.2, DMTF lists 1.3.3 "
        "https://www.dmtf.org/sites/default/files/standards/documents/"
        "DSP0236_1.3.3.pdf"
    )
    assert "old text" in out
    assert scripted.calls == [OLD_URL, L.DMTF_PUBLISHED]
    assert freshness(library)["documents"]["DSP0236"]["newer"][0]["version"] == "1.3.3"
    assert not (library.specs / "mctp" / "DSP0236" / "1.3.3").exists()
    # the catalog file is untouched
    assert cat.read_text("utf-8") == OLDER_CATALOG


def test_an_unreachable_publisher_is_a_note_and_the_exit_code_stays_0(
    ready, catalog_file, library, scripted, checking, capsys
):
    code, out = run(capsys, "section", "DSP0236", "Intro", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("0 | 1 Intro | pages")
    assert lines[-1].startswith(
        f"note: unreachable DSP0236: {L.DMTF_PUBLISHED}: no route to "
    )
    assert scripted.calls == [L.DMTF_PUBLISHED]
    assert freshness(library)["documents"]["DSP0236"]["problem"]
    code, out = run(capsys, "section", "DSP0236", "Intro", catalog_file=catalog_file)
    assert code == 0 and "note" not in out
    assert scripted.calls == [L.DMTF_PUBLISHED]  # stamped like check


def test_documents_without_a_listing_are_never_checked(
    catalog_file, library, scripted, tmp_path, checking, capsys
):
    ipmi = "https://example.test/ipmi-v2-rev1-1.pdf"  # fetch = "wayback"
    scripted.responses[fetch_mod.WAYBACK_AVAILABLE + ipmi] = wayback_hit(ipmi)
    scripted.responses[f"http://web.archive.org/web/20250101000000id_/{ipmi}"] = ok(
        pdf_bytes(tmp_path, "i.pdf", ["ipmi text"])
    )
    code, out = run(capsys, "find", "IPMI", "ipmi", catalog_file=catalog_file)
    assert code == 0, out
    assert "note" not in out
    assert not (library.root / F.FRESHNESS_NAME).exists()


# ----------------------------------------------------------------- AC-6


def offline(library, value="true"):
    library.root.mkdir(parents=True, exist_ok=True)
    (library.root / "config.toml").write_text(
        f"[library]\noffline = {value}\n", encoding="utf-8"
    )


def test_offline_reading_commands_stay_off_the_network(
    catalog_file, library, scripted, tmp_path, capsys
):
    offline(library)
    scripted.responses[URL] = ok(pdf_bytes(tmp_path))
    code, out = run(capsys, "find", "DSP0236", "x", catalog_file=catalog_file)
    assert code == 2
    assert out.strip() == (
        "DSP0236 1.3.3 is not in the Library (config.toml: offline); "
        "run: bmcspec fetch DSP0236"
    )
    code, out = run(
        capsys, "find", "DSP0236", "x", "--version", "1.3.2", catalog_file=catalog_file
    )
    assert code == 2
    assert out.strip().endswith("run: bmcspec fetch DSP0236 --version 1.3.2")
    assert scripted.calls == []
    # fetch is the user asking for the network: it ignores the key
    code, out = run(
        capsys, "fetch", "DSP0236", "--no-extract", catalog_file=catalog_file
    )
    assert code == 0 and scripted.calls == [URL]
    # a held version that is not Ready is still extracted (local work)
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0].startswith("extracted DSP0236 1.3.3")


def test_offline_answers_from_the_held_version_with_a_note_and_skips_the_check(
    ready, catalog_file, library, scripted, tmp_path, checking, capsys
):
    offline(library)
    cat = tmp_path / "newer.toml"  # the catalog moved on to 1.4.0 (not held)
    cat.write_text(MINI_CATALOG.replace("wip = true", "wip = false"), "utf-8")
    scripted.responses[L.DMTF_PUBLISHED] = html(DMTF_PUBLISHED_HTML)
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=cat)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == (
        "note: DSP0236 1.4.0 is not in the Library and the Library is offline; "
        "answering from held 1.3.3"
    )
    assert lines[1].startswith("cite: mctp | DSP0236 1.3.3 | ")
    assert "newer" not in out and "unreachable" not in out
    assert scripted.calls == []
    # check itself still goes online
    code, out = run(capsys, "check", "DSP0236", catalog_file=catalog_file)
    assert code == 0 and scripted.calls == [L.DMTF_PUBLISHED]


def test_a_bad_offline_value_is_exit_2(catalog_file, library, capsys):
    offline(library, '"yes"')
    code, out = run(capsys, "find", "DSP0236", "x", catalog_file=catalog_file)
    assert code == 2
    assert out.strip().endswith("library.offline must be true or false")


# ----------------------------------------------------------------- AC-7


def test_fetch_leaves_the_version_ready(
    catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[URL] = ok(pdf_bytes(tmp_path))
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[1] == "fetched DSP0236 1.3.3 via direct"
    assert lines[2].startswith("extracted DSP0236 1.3.3: 1 pages in ")
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    assert (vdir / "extract.txt").is_file()
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert out.splitlines() == [
        "skipped DSP0236 1.3.3: already in Library",
        "skipped DSP0236 1.3.3: already extracted",
    ]
    scripted.responses[OLD_URL] = ok(pdf_bytes(tmp_path, "old.pdf"))
    code, out = run(
        capsys,
        "fetch",
        "DSP0236",
        "--version",
        "1.3.2",
        "--no-extract",
        catalog_file=catalog_file,
    )
    assert code == 0 and out.strip() == "fetched DSP0236 1.3.2 via direct"
    assert not (library.specs / "mctp" / "DSP0236" / "1.3.2" / "extract.txt").exists()
    # a bundle is unpacked the same way
    scripted.responses[BUNDLE_URL] = ok(bundle_bytes(), "application/zip")
    code, out = run(capsys, "fetch", "BUNDLE", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[1].startswith("extracted BUNDLE 2026.1: 6 schema files")


def test_fetch_reports_a_failed_extraction_and_keeps_the_download(
    catalog_file, library, scripted, capsys
):
    scripted.responses[URL] = ok(PDF_BYTES)  # not a PDF pypdfium2 can open
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[1] == "fetched DSP0236 1.3.3 via direct"
    assert lines[2].startswith("failed DSP0236 1.3.3: ")
    vdir = library.specs / "mctp" / "DSP0236" / "1.3.3"
    assert (vdir / "original.pdf").read_bytes() == PDF_BYTES
    assert not (vdir / "extract.txt").exists()


def test_fetch_all_is_unchanged(catalog_file, library, scripted, tmp_path, capsys):
    scripted.responses[URL] = ok(pdf_bytes(tmp_path))
    code, out = run(capsys, "fetch", "--all", catalog_file=catalog_file)
    assert "extracted" not in out
    assert out.splitlines()[-1].startswith("summary: fetched 1, ")
    assert not (library.specs / "mctp" / "DSP0236" / "1.3.3" / "extract.txt").exists()


# ----------------------------------------------------------------- AC-8


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start + len(heading) :]
    end = rest.find("\n## ")
    return rest[: end if end >= 0 else None]


def test_skill_locates_first_and_relays_newer_notes():
    text = SKILL.read_text("utf-8")
    assert "**Ready**" in _section(text, "## Vocabulary")
    workflow = _section(text, "## Answering workflow")
    for gone in ("`fetch DOC`", "`extract DOC`", "run `check DOC` once"):
        assert gone not in workflow, gone
    assert "Ready" in workflow
    assert "`fetched`" in workflow and "`extracted`" in workflow
    assert "note: newer" in workflow
    assert "note: unreachable" in workflow
    assert "never during a question" in workflow
    # no fetch, extract or check step before the locate step
    locate = workflow.index("Locate")
    before = workflow[:locate]
    assert not re.search(r"`(fetch|extract|check)`", before), before
    for name in ("section DOC", "find DOC", "page DOC", "table DOC"):
        row = next(ln for ln in text.splitlines() if ln.startswith(f"| `{name}"))
        assert "Ready" in row or "downloads" in row, row
    fetch_row = next(ln for ln in text.splitlines() if ln.startswith("| `fetch DOC"))
    assert "--no-extract" in fetch_row and "Ready" in fetch_row
    assert "offline" in text


def test_docs_describe_ready_and_offline():
    commands = (ROOT / "docs" / "COMMANDS.md").read_text("utf-8")
    readme = (ROOT / "README.md").read_text("utf-8")
    for text in (commands, readme):
        assert "Ready" in text
    assert "offline = " in commands
    assert "--no-extract" in commands
    assert "note: newer" in commands
    assert "Claude->>CLI: fetch" not in readme  # the diagram starts by locating

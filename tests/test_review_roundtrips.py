"""Acceptance tests for the fewer round trips change, AC-1 to AC-4 and AC-7:
a reading command brings the catalog's Latest, or the version named, to
Ready by itself (download, extraction) and answers in the same call; a
failed download of Latest falls back to a held version with a note; gated,
manual, unknown and busy versions are refused without a download; ``fetch
DOC`` leaves the version Ready unless ``--no-extract``.

Black-box through ``main``; the network is the scripted client of conftest.
"""

import json
import threading
import time

import pytest

from bmc_toolkit.spec import extract as extract_mod
from bmc_toolkit.spec import lock as lock_mod
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import MINI_CATALOG, PDF_BYTES, ZIP_BYTES, ok
from tests.test_lock import fake_lock
from tests.test_search_cli import COMPANION_CATALOG, IPMI_URL, UPDATE_URL

pytest.importorskip("pypdfium2")

URL_133 = "https://example.test/DSP0236_1.3.3.pdf"
URL_132 = "https://example.test/DSP0236_1.3.2.pdf"
URL_140 = "https://example.test/DSP0236_1.4.0.pdf"
BUNDLE_URL = "https://example.test/bundle_2026.1.zip"
ERRATA_6_URL = "https://example.test/ipmi-update-6.pdf"
ERRATA_7_URL = UPDATE_URL

# IPMI's companion with two versions: Errata 6 (older) and Errata 7 (Latest).
TWO_ERRATA_CATALOG = COMPANION_CATALOG.replace(
    '[[documents.versions]]\nversion = "Errata 7"',
    "[[documents.versions]]\n"
    'version = "Errata 6"\n'
    f'url = "{ERRATA_6_URL}"\n'
    'type = "pdf"\n'
    'published = "2014-04-01"\n'
    "\n"
    "[[documents.versions]]\n"
    'version = "Errata 7"',
)
assert '"Errata 6"' in TWO_ERRATA_CATALOG

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


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def lines_of(out):
    """Output lines without the one-time Library announcement."""
    return [ln for ln in out.splitlines() if not ln.startswith("Library created at ")]


def pdf(tmp_path, name, *lines):
    """A one-page PDF whose first line is a level-0 bookmark."""
    page = pdfgen.plain_page(list(lines))
    marks = [(0, lines[0], 0)]
    return pdfgen.write_pdf(tmp_path / name, [page], bookmarks=marks).read_bytes()


def vdir(library, version="1.3.3"):
    return library.specs / "mctp" / "DSP0236" / version


def cite_version(out):
    """The document and version named by the first cite: line."""
    line = next(ln for ln in out.splitlines() if ln.startswith("cite: "))
    return line.split(" | ")[1]


def make_stale(directory):
    meta = directory / "extract.json"
    data = json.loads(meta.read_text("utf-8"))
    data["extractor_version"] = extract_mod.EXTRACTOR_VERSION - 1
    meta.write_text(json.dumps(data), "utf-8")


def hold_from_thread(directory, seconds):
    """Another Session holds the version lock for a moment."""
    ready = threading.Event()

    def holder():
        with lock_mod.Lock(directory, "other session", wait=0):
            ready.set()
            time.sleep(seconds)

    thread = threading.Thread(target=holder, daemon=True)
    thread.start()
    assert ready.wait(5)
    return thread


# ----------------------------------------------------------------- AC-1


@pytest.mark.parametrize(
    "argv",
    [
        ["section", "DSP0236", "Intro"],
        ["find", "DSP0236", "alpha"],
        ["page", "DSP0236", "1"],
    ],
    ids=["section", "find", "page"],
)
def test_ac1_first_touch_downloads_extracts_and_answers_in_one_call(
    argv, catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[URL_133] = ok(pdf(tmp_path, "a.pdf", "1 Intro", "alpha"))
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0, out
    lines = lines_of(out)
    assert lines[0] == "fetched DSP0236 1.3.3 via direct"
    assert lines[1].startswith("extracted DSP0236 1.3.3: 1 pages")
    answer = lines[2:]
    assert answer, out
    assert scripted.calls == [URL_133]
    assert (vdir(library) / "extract.txt").is_file()
    # Ready now: the same call prints the answer alone and touches nothing
    code, again = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0, again
    assert again.splitlines() == answer
    assert scripted.calls == [URL_133]


def test_ac1_latest_is_the_catalog_latest_not_the_newest_held(
    catalog_file, library, scripted, tmp_path, capsys
):
    # the WIP 1.4.0 is held (newest by date); Latest excludes WIP: 1.3.3
    scripted.responses[URL_140] = ok(pdf(tmp_path, "w.pdf", "1 Intro", "wip text"))
    scripted.responses[URL_133] = ok(pdf(tmp_path, "a.pdf", "1 Intro", "released text"))
    code, out = run(capsys, "fetch", "DSP0236", "--wip", catalog_file=catalog_file)
    assert code == 0, out
    scripted.calls.clear()
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    assert lines_of(out)[0] == "fetched DSP0236 1.3.3 via direct"
    assert cite_version(out) == "DSP0236 1.3.3"
    assert "released text" in out and "wip text" not in out
    assert scripted.calls == [URL_133]


def test_ac1_a_held_version_is_extracted_not_downloaded(
    catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[URL_133] = ok(pdf(tmp_path, "a.pdf", "1 Intro", "alpha"))
    run(capsys, "fetch", "DSP0236", "--no-extract", catalog_file=catalog_file)
    scripted.calls.clear()
    code, out = run(capsys, "find", "DSP0236", "alpha", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("extracted DSP0236 1.3.3: 1 pages")
    assert lines[1].startswith("DSP0236 p.1 ") and "alpha" in lines[1]
    assert len(lines) == 2
    assert scripted.calls == []
    # an Extract from an older extractor is not Ready: redone, not refused
    make_stale(vdir(library))
    code, out = run(capsys, "find", "DSP0236", "alpha", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0].startswith("extracted DSP0236 1.3.3")
    assert scripted.calls == []


# ----------------------------------------------------------------- AC-2


def test_ac2_a_named_version_is_brought_to_ready_and_read(
    catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[URL_133] = ok(pdf(tmp_path, "a.pdf", "1 Intro", "new text"))
    scripted.responses[URL_132] = ok(pdf(tmp_path, "b.pdf", "1 Intro", "old text"))
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)  # Latest is Ready
    scripted.calls.clear()
    argv = ["page", "DSP0236", "1", "--version", "1.3.2"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "fetched DSP0236 1.3.2 via direct"
    assert lines[1].startswith("extracted DSP0236 1.3.2")
    assert cite_version(out) == "DSP0236 1.3.2"
    assert "old text" in out and "new text" not in out
    assert scripted.calls == [URL_132]
    # held now: the answer alone, no network
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0 and out.startswith("cite: ")
    assert scripted.calls == [URL_132]


def test_ac2_an_unknown_version_is_exit_2_listing_the_known_ones(
    catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[URL_133] = ok(pdf(tmp_path, "a.pdf", "1 Intro", "alpha"))
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    scripted.calls.clear()
    for bad in ("1.3", "1.3.3.1", "9.9"):  # exact match: no prefix either way
        code, out = run(
            capsys, "find", "DSP0236", "alpha", "--version", bad, catalog_file=catalog_file
        )
        assert code == 2, (bad, out)
        assert f"DSP0236 {bad} is not in the Library" in out
        for known in ("1.3.2", "1.3.3", "1.4.0"):
            assert known in out, (bad, out)
        assert "fetched" not in out and "DSP0236 p." not in out
    assert scripted.calls == []


# ----------------------------------------------------------------- AC-3


def test_ac3_gated_and_manual_versions_are_refused_as_fetch_refuses_them(
    catalog_file, library, scripted, tmp_path, capsys
):
    for argv in (
        ["find", "SECRET", "x"],
        ["page", "SECRET", "1"],
        ["section", "SECRET", "x", "--version", "0.9"],
    ):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 2, (argv, out)
        lines = out.splitlines()
        assert lines[0] == "SECRET 0.9 is confidential: the tool does not download it."
        assert lines[-1] == "no open version is listed"
    code, fetch_out = run(capsys, "fetch", "SECRET", catalog_file=catalog_file)
    assert code == 2 and fetch_out == out
    assert scripted.calls == []
    assert not (library.specs / "vendor").exists()
    # a manual document that lists no versions: the add instruction
    cat = tmp_path / "nda.toml"
    cat.write_text(NO_VERSIONS_CATALOG, encoding="utf-8", newline="")
    code, out = run(capsys, "page", "NDA", "1", catalog_file=cat)
    assert code == 2, out
    assert "bmcspec add FILE --document NDA --version V" in out
    code, fetch_out = run(capsys, "fetch", "NDA", catalog_file=cat)
    assert code == 2 and fetch_out == out
    assert scripted.calls == []


def test_ac3_a_live_lock_is_busy_and_wait_applies(
    catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[URL_133] = ok(pdf(tmp_path, "a.pdf", "1 Intro", "alpha"))
    directory = vdir(library)
    fake_lock(directory, command="fetch DSP0236 1.3.3")
    code, out = run(
        capsys, "--wait", "0", "find", "DSP0236", "alpha", catalog_file=catalog_file
    )
    assert code == 3, out
    assert out.strip().startswith(f"busy: {directory / '.lock'} is held by pid 4242 ")
    assert scripted.calls == []
    assert not (directory / "original.pdf").exists()
    (directory / ".lock").unlink()
    # --wait: a lock released within the wait is waited out, then the
    # command downloads, extracts and answers as if nobody had been there
    thread = hold_from_thread(directory, 0.6)
    started = time.monotonic()
    code, out = run(
        capsys, "--wait", "10", "find", "DSP0236", "alpha", catalog_file=catalog_file
    )
    thread.join()
    assert code == 0, out
    assert time.monotonic() - started < 8
    lines = lines_of(out)
    assert lines[0] == "fetched DSP0236 1.3.3 via direct"
    assert lines[1].startswith("extracted DSP0236 1.3.3")
    assert lines[2].startswith("DSP0236 p.1 ")
    assert scripted.calls == [URL_133]


# ----------------------------------------------------------------- AC-4


def test_ac4_a_failed_download_of_latest_answers_from_the_held_version(
    catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[URL_132] = ok(pdf(tmp_path, "b.pdf", "1 Intro", "old text"))
    argv = ["fetch", "DSP0236", "--version", "1.3.2", "--no-extract"]
    assert run(capsys, *argv, catalog_file=catalog_file)[0] == 0
    scripted.calls.clear()
    # 1.3.3 has no route (direct and the Archive fail); 1.3.2 is held but
    # not Ready: it is made Ready and answers, the Citation names it
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("note: could not fetch DSP0236 1.3.3: ")
    assert lines[0].endswith("; answering from held 1.3.2")
    assert lines[1].startswith("extracted DSP0236 1.3.2")
    assert cite_version(out) == "DSP0236 1.3.2"
    assert "old text" in out
    assert scripted.calls[0] == URL_133  # the download was tried first
    assert not (vdir(library) / "original.pdf").exists()
    # a version the user named is never replaced by another held one
    code, out = run(
        capsys, "page", "DSP0236", "1", "--version", "1.3.3", catalog_file=catalog_file
    )
    assert code == 2, out
    assert "failed DSP0236 1.3.3" in out.splitlines()
    assert "answering from" not in out and "cite:" not in out


def test_ac4_nothing_held_is_exit_2_with_the_url_and_the_save_path(
    catalog_file, library, scripted, capsys
):
    code, out = run(capsys, "section", "DSP0236", "Intro", catalog_file=catalog_file)
    assert code == 2, out
    lines = out.splitlines()
    assert "failed DSP0236 1.3.3" in lines
    assert f"Open in a browser: {URL_133}" in lines
    assert f"Save it as: {vdir(library) / 'original.pdf'}" in lines
    assert lines[-1] == "Then run: bmcspec scan"
    assert "note:" not in out
    # the same lines fetch prints
    code, fetch_out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 2, fetch_out
    for line in lines:
        if line.startswith("Library created at "):
            continue
        assert line in fetch_out.splitlines(), line


# ----------------------------------------------------------------- AC-7


def test_ac7_fetch_leaves_the_version_ready(
    catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[URL_133] = ok(pdf(tmp_path, "a.pdf", "1 Intro", "alpha"))
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    lines = lines_of(out)
    assert lines[0] == "fetched DSP0236 1.3.3 via direct"
    assert lines[1].startswith("extracted DSP0236 1.3.3: 1 pages")
    assert (vdir(library) / "extract.txt").is_file()
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0 and out.startswith("skipped DSP0236 1.3.3: already extracted")
    # Ready already: two skipped lines
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    assert [ln for ln in out.splitlines() if not ln.startswith("note:")] == [
        "skipped DSP0236 1.3.3: already in Library",
        "skipped DSP0236 1.3.3: already extracted",
    ]
    # held but not Ready: skipped, then extracted
    make_stale(vdir(library))
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "skipped DSP0236 1.3.3: already in Library"
    assert lines[1].startswith("extracted DSP0236 1.3.3")
    assert scripted.calls == [URL_133]


def test_ac7_no_extract_and_fetch_all_stop_after_the_download(
    catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[URL_132] = ok(pdf(tmp_path, "b.pdf", "1 Intro", "old"))
    argv = ["fetch", "DSP0236", "--version", "1.3.2", "--no-extract"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0, out
    lines = [ln for ln in lines_of(out) if not ln.startswith("note:")]
    assert lines == ["fetched DSP0236 1.3.2 via direct"]
    assert not (vdir(library, "1.3.2") / "extract.txt").exists()
    scripted.responses[URL_133] = ok(pdf(tmp_path, "a.pdf", "1 Intro", "alpha"))
    code, out = run(capsys, "fetch", "--all", catalog_file=catalog_file)
    assert "fetched DSP0236 1.3.3 via direct" in out.splitlines()
    assert "extracted" not in out
    assert out.splitlines()[-1].startswith("summary: fetched 1, ")
    assert not (vdir(library) / "extract.txt").exists()


def test_ac7_a_failed_extraction_after_a_good_download_keeps_the_download(
    catalog_file, library, scripted, capsys
):
    # AC-7 as amended in review round 1: the download landed, so the exit
    # code is 0; the failure is followed by the extract command to run.
    scripted.responses[URL_133] = ok(PDF_BYTES)  # a PDF no extractor can open
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    lines = lines_of(out)
    assert lines[0] == "fetched DSP0236 1.3.3 via direct"
    assert lines[1].startswith("failed DSP0236 1.3.3: ")
    assert lines[2] == "run: bmcspec extract DSP0236"
    assert len(lines) == 3, out
    assert (vdir(library) / "original.pdf").read_bytes() == PDF_BYTES
    assert not (vdir(library) / "extract.txt").exists()
    # a reading command meeting the same file reports the failure with a
    # non-zero exit and no answer
    code, out = run(capsys, "find", "DSP0236", "x", catalog_file=catalog_file)
    assert code == 1 and out.startswith("failed DSP0236 1.3.3: "), out
    assert "DSP0236 p." not in out


def test_ac7_a_missing_dependency_after_a_good_download_is_exit_0_with_the_hint(
    catalog_file, library, scripted, tmp_path, capsys, monkeypatch
):
    def no_package(path):
        raise ImportError("No module named 'pypdfium2'")

    monkeypatch.setattr(extract_mod, "extract_pdf", no_package)
    scripted.responses[URL_132] = ok(pdf(tmp_path, "b.pdf", "1 Intro", "old"))
    argv = ["fetch", "DSP0236", "--version", "1.3.2"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0, out
    lines = lines_of(out)
    assert lines[0] == "fetched DSP0236 1.3.2 via direct"
    assert lines[1].startswith("failed DSP0236 1.3.2: No module named 'pypdfium2'")
    assert "pip install -r requirements.txt" in lines[1]
    # the hint carries the version the user named
    assert lines[2] == "run: bmcspec extract DSP0236 --version 1.3.2"
    assert (vdir(library, "1.3.2") / "original.pdf").is_file()
    assert not (vdir(library, "1.3.2") / "extract.txt").exists()
    # the same dependency gap inside a reading command is exit 2, as extract
    code, out = run(
        capsys, "page", "DSP0236", "1", "--version", "1.3.2", catalog_file=catalog_file
    )
    assert code == 2, out
    assert out.startswith("failed DSP0236 1.3.2: No module named")


# ---------------------------------------------- review round 1 fixes


def test_r1_the_fallback_prefers_a_released_held_version_over_a_wip_one(
    catalog_file, library, scripted, tmp_path, capsys
):
    """F4 (AC-4): Latest 1.3.3 has no route; 1.4.0 (WIP, dated newest) and
    1.3.2 (released) are held: the released one answers."""
    scripted.responses[URL_132] = ok(pdf(tmp_path, "b.pdf", "1 Intro", "released"))
    scripted.responses[URL_140] = ok(pdf(tmp_path, "w.pdf", "1 Intro", "wip"))
    for version in ("1.3.2", "1.4.0"):
        argv = ["fetch", "DSP0236", "--version", version]
        assert run(capsys, *argv, catalog_file=catalog_file)[0] == 0
    scripted.calls.clear()
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("note: could not fetch DSP0236 1.3.3: ")
    assert lines[0].endswith("; answering from held 1.3.2")
    assert cite_version(out) == "DSP0236 1.3.2"
    assert "released" in out and "wip" not in out
    assert scripted.calls == [URL_133]
    # with nothing released held, the WIP version is what there is
    for path in vdir(library, "1.3.2").rglob("*"):
        if path.is_file():
            path.unlink()
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0].endswith("; answering from held 1.4.0")
    assert cite_version(out) == "DSP0236 1.4.0"


def test_r1_a_command_of_the_other_kind_is_refused_before_any_download(
    catalog_file, library, scripted, tmp_path, capsys
):
    """F7: the catalog names the file type, so a text command on a bundle
    and schema/registry on a PDF point to the right command without
    downloading anything."""
    scripted.responses[URL_133] = ok(pdf(tmp_path, "a.pdf", "1 Intro", "alpha"))
    scripted.responses[BUNDLE_URL] = ok(ZIP_BYTES, "application/zip")
    for argv in (
        ["find", "BUNDLE", "x"],
        ["section", "BUNDLE", "x"],
        ["page", "BUNDLE", "1"],
        ["render", "BUNDLE", "--page", "1"],
    ):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 2, (argv, out)
        last = out.splitlines()[-1]
        assert last.startswith("BUNDLE 2026.1 is a zip bundle")
        assert "bmcspec schema BUNDLE" in last and "bmcspec registry BUNDLE" in last
        assert "fetched" not in out
    for command in ("schema", "registry"):
        code, out = run(capsys, command, "DSP0236", catalog_file=catalog_file)
        assert code == 2, (command, out)
        last = out.splitlines()[-1]
        assert last.startswith("DSP0236 1.3.3 is a PDF document, not a bundle")
        assert "bmcspec find DSP0236" in last and "bmcspec page DSP0236" in last
        assert "fetched" not in out
    assert scripted.calls == []
    assert not (library.specs / "mctp" / "BUNDLE").exists()
    assert not vdir(library).exists()
    # the refusal names the version asked for as well
    code, out = run(
        capsys, "schema", "DSP0236", "--version", "1.3.2", catalog_file=catalog_file
    )
    assert code == 2 and "DSP0236 1.3.2 is a PDF document" in out, out
    assert scripted.calls == []


def test_r1_a_bundle_with_nothing_to_unpack_says_why_the_command_failed(
    catalog_file, library, scripted, capsys
):
    """F5: a skipped unpack that leaves nothing to read is closed by a line
    that matches the exit code, for a reading command and for fetch."""
    scripted.responses[BUNDLE_URL] = ok(ZIP_BYTES, "application/zip")
    code, out = run(capsys, "registry", "BUNDLE", catalog_file=catalog_file)
    assert code == 1, out
    lines = lines_of(out)
    assert lines[0] == "fetched BUNDLE 2026.1 via direct"
    assert lines[1].startswith("skipped BUNDLE 2026.1: ")
    assert lines[2] == "cannot read BUNDLE 2026.1: nothing to extract"
    assert len(lines) == 3, out
    # held now: fetch says skipped, then the same closing line, exit 0
    code, out = run(capsys, "fetch", "BUNDLE", catalog_file=catalog_file)
    assert code == 0, out
    lines = [ln for ln in out.splitlines() if not ln.startswith("note:")]
    assert lines[0] == "skipped BUNDLE 2026.1: already in Library"
    assert lines[1].startswith("skipped BUNDLE 2026.1: ")
    assert "cannot read BUNDLE 2026.1: nothing to extract" in lines


def test_r1_a_companion_note_carries_one_prefix(library, scripted, tmp_path, capsys):
    """F3: a companion line that is already a note (the held-version
    fallback after a failed download) is not prefixed a second time."""
    cat = tmp_path / "companions.toml"
    cat.write_text(TWO_ERRATA_CATALOG, encoding="utf-8", newline="")
    scripted.responses[IPMI_URL] = ok(
        pdf(tmp_path, "i.pdf", "1 Intro", "Get Device ID")
    )
    scripted.responses[ERRATA_6_URL] = ok(
        pdf(tmp_path, "e6.pdf", "1 Intro", "Get Device ID errata six")
    )
    argv = ["fetch", "IPMI-UPDATE", "--version", "Errata 6"]
    assert run(capsys, *argv, catalog_file=cat)[0] == 0
    # Errata 7 (Latest) has no route: the companion answers from Errata 6
    code, out = run(capsys, "find", "IPMI", "get device id", catalog_file=cat)
    assert code == 0, out
    lines = lines_of(out)
    assert lines[0] == "fetched IPMI 2.0 rev 1.1 via direct"
    assert lines[1].startswith("extracted IPMI 2.0 rev 1.1")
    notes = [ln for ln in lines if ln.startswith("note:")]
    assert len(notes) == 1, out
    assert notes[0].startswith("note: could not fetch IPMI-UPDATE Errata 7: ")
    assert notes[0].endswith("; answering from held Errata 6")
    assert "note: note:" not in out
    hits = [ln for ln in lines if " p.1 " in ln]
    assert hits[0].startswith("IPMI-UPDATE p.1 ") and "errata six" in hits[0]
    assert hits[1].startswith("IPMI p.1 ")
    assert ERRATA_7_URL in scripted.calls

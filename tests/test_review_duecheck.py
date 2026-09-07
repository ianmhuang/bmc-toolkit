"""Acceptance tests for the fewer round trips change, AC-5 and AC-6: after
its output a reading command runs the Freshness Check of the document when
the last one is older than ``freshness_days``, records it, and reports the
outcome as a ``note:`` that never downloads, never edits the catalog and
never changes the exit code; ``[library] offline = true`` keeps every
reading command off the network while ``fetch`` and ``check`` still go.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from bmc_toolkit.spec import cli
from bmc_toolkit.spec import freshness as F
from bmc_toolkit.spec import listing as L
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import MINI_CATALOG, ok
from tests.test_bundle import bundle_bytes
from tests.test_listing import DMTF_PUBLISHED_HTML

pytest.importorskip("pypdfium2")

# The after-output check as shipped, taken at import time: conftest's autouse
# fixture replaces it with a no-op for every test, and the tests here that
# want it put it back.
REAL_CHECK = cli._check_when_due

URL_133 = "https://example.test/DSP0236_1.3.3.pdf"
URL_132 = "https://example.test/DSP0236_1.3.2.pdf"
BUNDLE_URL = "https://example.test/bundle_2026.1.zip"

LATEST_BLOCK = """[[documents.versions]]
version = "1.3.3"
url = "https://example.test/DSP0236_1.3.3.pdf"
type = "pdf"
published = "2024-03-25"

"""
OLDER_CATALOG = MINI_CATALOG.replace(LATEST_BLOCK, "")
assert '"1.3.3"' not in OLDER_CATALOG
LISTED_BUNDLE_CATALOG = MINI_CATALOG.replace(
    'id = "BUNDLE"', 'id = "BUNDLE"\nlisting = "dmtf:DSP8010"'
)


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def lines_of(out):
    return [ln for ln in out.splitlines() if not ln.startswith("Library created at ")]


def pdf(tmp_path, name, *lines):
    page = pdfgen.plain_page(list(lines))
    marks = [(0, lines[0], 0)]
    return pdfgen.write_pdf(tmp_path / name, [page], bookmarks=marks).read_bytes()


def html(text):
    return ok(text.encode("utf-8"), "text/html")


def config(library, text):
    library.root.mkdir(parents=True, exist_ok=True)
    (library.root / "config.toml").write_text(text, encoding="utf-8", newline="")


def stamp(library, days_ago, document="DSP0236", latest="1.3.3"):
    """A check of the document recorded ``days_ago`` days ago."""
    state = F.Freshness(library.root)
    when = datetime.now(UTC) - timedelta(days=days_ago)
    state.data["documents"][document] = {
        "checked_at": when.isoformat(),
        "catalog_latest": latest,
        "newer": [],
        "problem": "",
    }
    state.save()


def freshness(library):
    return json.loads((library.root / F.FRESHNESS_NAME).read_text("utf-8"))


def checked(library, document="DSP0236"):
    """True when a check of the document is recorded (fetch's reminder
    stamps only ``reminded_at``, which is not a check)."""
    path = library.root / F.FRESHNESS_NAME
    if not path.is_file():
        return False
    return "checked_at" in freshness(library)["documents"].get(document, {})


@pytest.fixture
def checking(monkeypatch):
    """The after-output Freshness Check, on."""
    monkeypatch.setattr(cli, "_check_when_due", REAL_CHECK)


@pytest.fixture
def ready(catalog_file, library, scripted, tmp_path, capsys):
    """DSP0236 1.3.3 Ready, never checked; the client's call log cleared."""
    scripted.responses[URL_133] = ok(pdf(tmp_path, "a.pdf", "1 Intro", "alpha"))
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    scripted.calls.clear()
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


# ----------------------------------------------------------------- AC-5


def test_ac5_the_due_check_runs_after_the_answer_and_is_stamped(
    ready, catalog_file, library, scripted, checking, capsys
):
    scripted.responses[L.DMTF_PUBLISHED] = html(DMTF_PUBLISHED_HTML)
    config(library, "[library]\nfreshness_days = 5\n")
    stamp(library, 6)  # older than freshness_days: due
    argv = ["section", "DSP0236", "Intro"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    # current: the answer alone, no note and no "run: bmcspec check" reminder
    assert len(lines) == 1 and lines[0].startswith("0 | 1 Intro | pages 1-1"), out
    assert scripted.calls == [L.DMTF_PUBLISHED]
    entry = freshness(library)["documents"]["DSP0236"]
    assert entry["catalog_latest"] == "1.3.3" and entry["problem"] == ""
    checked = datetime.fromisoformat(entry["checked_at"])
    assert datetime.now(UTC) - checked < timedelta(minutes=5)
    # stamped: the next question within the age does not check again
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0 and scripted.calls == [L.DMTF_PUBLISHED]
    stamp(library, 4)  # younger than freshness_days
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0 and scripted.calls == [L.DMTF_PUBLISHED]
    stamp(library, 5)  # at the age: due again
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0 and scripted.calls == [L.DMTF_PUBLISHED] * 2
    assert "note" not in out


def test_ac5_a_newer_publisher_version_is_a_note_after_the_answer_never_fetched(
    library, scripted, tmp_path, checking, capsys
):
    cat = tmp_path / "older.toml"  # the catalog stops at 1.3.2; DMTF lists 1.3.3
    cat.write_text(OLDER_CATALOG, encoding="utf-8", newline="")
    scripted.responses[URL_132] = ok(pdf(tmp_path, "b.pdf", "1 Intro", "old text"))
    scripted.responses[L.DMTF_PUBLISHED] = html(DMTF_PUBLISHED_HTML)
    code, out = run(capsys, "find", "DSP0236", "old", catalog_file=cat)
    assert code == 0, out
    lines = lines_of(out)
    assert lines[0] == "fetched DSP0236 1.3.2 via direct"
    assert lines[1].startswith("extracted DSP0236 1.3.2")
    assert lines[2].startswith("DSP0236 p.1 ") and "old text" in lines[2]
    assert lines[3].startswith(
        "note: newer DSP0236: catalog latest 1.3.2, DMTF lists 1.3.3"
    )
    assert "DSP0236_1.3.3.pdf" in lines[3]
    assert len(lines) == 4, out
    assert scripted.calls == [URL_132, L.DMTF_PUBLISHED]
    # reported, never acted on: no download, the catalog file untouched
    assert not (library.specs / "mctp" / "DSP0236" / "1.3.3").exists()
    assert cat.read_text("utf-8") == OLDER_CATALOG
    assert freshness(library)["documents"]["DSP0236"]["newer"][0]["version"] == "1.3.3"
    # recorded like check: the next question does not check again
    code, out = run(capsys, "find", "DSP0236", "old", catalog_file=cat)
    assert code == 0 and scripted.calls == [URL_132, L.DMTF_PUBLISHED]
    assert not (library.specs / "mctp" / "DSP0236" / "1.3.3").exists()


def test_ac5_a_failing_check_is_a_note_and_never_the_exit_code(
    ready, catalog_file, library, scripted, checking, capsys
):
    # no route to the listing page
    argv = ["page", "DSP0236", "1"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("cite: mctp | DSP0236 1.3.3 | ")
    assert lines[-1].startswith("note: unreachable DSP0236: ")
    assert scripted.calls == [L.DMTF_PUBLISHED]
    assert freshness(library)["documents"]["DSP0236"]["problem"]
    # stamped like check: not again within the age, and no note
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0 and "note:" not in out
    assert scripted.calls == [L.DMTF_PUBLISHED]
    # an unexpected failure inside the check is a note too, exit still 0
    stamp(library, 31)
    scripted.responses[L.DMTF_PUBLISHED] = RuntimeError("boom")
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0].startswith("cite: mctp | DSP0236 1.3.3 | ")
    assert out.splitlines()[-1].startswith("note: unreachable DSP0236: ")
    # a command that fails runs no check at all
    stamp(library, 31)
    scripted.calls.clear()
    code, out = run(capsys, "page", "DSP0236", "7", catalog_file=catalog_file)
    assert code == 2 and scripted.calls == [] and "note:" not in out


def test_ac5_schema_runs_the_due_check_of_its_document_too(
    library, scripted, tmp_path, checking, capsys
):
    cat = tmp_path / "bundle.toml"
    cat.write_text(LISTED_BUNDLE_CATALOG, encoding="utf-8", newline="")
    scripted.responses[BUNDLE_URL] = ok(bundle_bytes(), "application/zip")
    scripted.responses[L.DMTF_PUBLISHED] = html(DMTF_PUBLISHED_HTML)
    code, out = run(capsys, "schema", "BUNDLE", catalog_file=cat)
    assert code == 0, out
    lines = lines_of(out)
    assert lines[0] == "fetched BUNDLE 2026.1 via direct"
    assert lines[1].startswith("extracted BUNDLE 2026.1: ")
    assert any("\t" in ln for ln in lines[2:]), out  # the resource listing
    assert "note" not in out  # DSP8010 2026.1 is what DMTF lists: current
    assert scripted.calls == [BUNDLE_URL, L.DMTF_PUBLISHED]
    assert freshness(library)["documents"]["BUNDLE"]["catalog_latest"] == "2026.1"


def test_ac5_a_document_without_a_listing_is_never_checked(
    ready, catalog_file, library, scripted, tmp_path, checking, capsys
):
    # IPMI (Intel) has no publisher listing; a Drop-in of it is read and
    # nothing is asked of anyone
    src = tmp_path / "ipmi.pdf"
    src.write_bytes(pdf(tmp_path, "i.pdf", "1 Intro", "ipmi text"))
    argv = ["add", str(src), "--document", "IPMI", "--version", "2.0 rev 1.1"]
    assert run(capsys, *argv, catalog_file=catalog_file)[0] == 0
    scripted.calls.clear()
    code, out = run(capsys, "find", "IPMI", "ipmi", catalog_file=catalog_file)
    assert code == 0, out
    assert "note" not in out
    assert scripted.calls == []
    path = library.root / F.FRESHNESS_NAME
    assert not path.is_file() or "IPMI" not in freshness(library)["documents"]


# ----------------------------------------------------------------- AC-6


def test_ac6_offline_keeps_the_reading_commands_off_the_network(
    catalog_file, library, scripted, tmp_path, checking, capsys
):
    config(library, "[library]\noffline = true\n")
    scripted.responses[URL_133] = ok(pdf(tmp_path, "a.pdf", "1 Intro", "alpha"))
    scripted.responses[L.DMTF_PUBLISHED] = html(DMTF_PUBLISHED_HTML)
    for argv in (
        ["find", "DSP0236", "alpha"],
        ["section", "DSP0236", "Intro"],
        ["page", "DSP0236", "1"],
    ):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 2, (argv, out)
        assert "run: bmcspec fetch DSP0236" in out
        assert "fetched" not in out and "failed" not in out
    code, out = run(
        capsys, "page", "DSP0236", "1", "--version", "1.3.2", catalog_file=catalog_file
    )
    assert code == 2, out
    assert "run: bmcspec fetch DSP0236 --version 1.3.2" in out
    assert scripted.calls == []
    # fetch is the user asking for the network: it ignores the key
    code, out = run(
        capsys, "fetch", "DSP0236", "--no-extract", catalog_file=catalog_file
    )
    assert code == 0, out
    assert scripted.calls == [URL_133]
    # a held version that is not Ready is still extracted (local work), and
    # the due check is skipped: no listing call, no note, nothing recorded
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("extracted DSP0236 1.3.3")
    assert lines[1].startswith("cite: mctp | DSP0236 1.3.3 | ")
    assert "note:" not in out
    assert scripted.calls == [URL_133]
    entry = freshness(library)["documents"].get("DSP0236", {})
    assert "checked_at" not in entry
    # check itself still goes to the publisher
    code, out = run(capsys, "check", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    assert scripted.calls == [URL_133, L.DMTF_PUBLISHED]


def test_ac6_offline_false_and_a_bad_value(
    catalog_file, library, scripted, tmp_path, capsys
):
    config(library, "[library]\noffline = false\n")
    scripted.responses[URL_133] = ok(pdf(tmp_path, "a.pdf", "1 Intro", "alpha"))
    code, out = run(capsys, "find", "DSP0236", "alpha", catalog_file=catalog_file)
    assert code == 0, out
    assert lines_of(out)[0] == "fetched DSP0236 1.3.3 via direct"
    assert scripted.calls == [URL_133]
    config(library, '[library]\noffline = "yes"\n')
    code, out = run(capsys, "section", "DSP0236", "Intro", catalog_file=catalog_file)
    assert code == 2, out
    assert "offline" in out and "Traceback" not in out


def test_ac6_offline_answers_from_an_older_held_version_with_a_note(
    catalog_file, library, scripted, tmp_path, checking, capsys
):
    # AC-6 as amended in review round 1: offline, Latest (1.3.3) not held,
    # 1.3.2 held and Ready: a note and the answer from 1.3.2, no network,
    # no due check, exit 0.
    scripted.responses[URL_132] = ok(pdf(tmp_path, "b.pdf", "1 Intro", "old text"))
    argv = ["fetch", "DSP0236", "--version", "1.3.2"]
    assert run(capsys, *argv, catalog_file=catalog_file)[0] == 0
    scripted.calls.clear()
    config(library, "[library]\noffline = true\n")
    scripted.responses[URL_133] = ok(pdf(tmp_path, "a.pdf", "1 Intro", "alpha"))
    scripted.responses[L.DMTF_PUBLISHED] = html(DMTF_PUBLISHED_HTML)
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == (
        "note: DSP0236 1.3.3 is not in the Library and the Library is offline; "
        "answering from held 1.3.2"
    )
    assert lines[1].startswith("cite: mctp | DSP0236 1.3.2 | ")
    assert "old text" in out and "alpha" not in out
    assert "newer" not in out and "unreachable" not in out
    assert scripted.calls == []
    assert not (library.specs / "mctp" / "DSP0236" / "1.3.3").exists()
    assert not checked(library)
    # a version the user named is not replaced: exit 2 with the fetch command
    code, out = run(
        capsys, "page", "DSP0236", "1", "--version", "1.3.3", catalog_file=catalog_file
    )
    assert code == 2, out
    assert "run: bmcspec fetch DSP0236 --version 1.3.3" in out
    assert "answering from" not in out and scripted.calls == []


# ---------------------------------------------- review round 1 fixes


def test_r1_a_failed_stamp_is_a_note_and_the_outcome_is_still_printed(
    ready, catalog_file, library, scripted, tmp_path, checking, capsys, monkeypatch
):
    """F8 (AC-5): freshness.json cannot be written after a successful
    check: the outcome is printed all the same, the write failure is a
    note of its own, the exit code stays 0, and the next question checks
    again because nothing was stamped."""
    scripted.responses[L.DMTF_PUBLISHED] = html(DMTF_PUBLISHED_HTML)

    def refuse(self):
        raise OSError("disk full")

    monkeypatch.setattr(F.Freshness, "save", refuse)
    # current: the write failure is the only note
    argv = ["find", "DSP0236", "alpha"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("DSP0236 p.1 ") and "alpha" in lines[0]
    assert lines[1] == "note: could not record the check of DSP0236: disk full"
    assert len(lines) == 2, out
    assert "unreachable" not in out
    assert not checked(library)
    assert scripted.calls == [L.DMTF_PUBLISHED]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0 and scripted.calls == [L.DMTF_PUBLISHED] * 2
    # newer: the write failure and then the newer note, in that order
    cat = tmp_path / "older.toml"
    cat.write_text(OLDER_CATALOG, encoding="utf-8", newline="")
    scripted.responses[URL_132] = ok(pdf(tmp_path, "b.pdf", "1 Intro", "old text"))
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=cat)
    assert code == 0, out
    lines = lines_of(out)
    assert lines[0] == "fetched DSP0236 1.3.2 via direct"
    assert lines[-2] == "note: could not record the check of DSP0236: disk full"
    assert lines[-1].startswith(
        "note: newer DSP0236: catalog latest 1.3.2, DMTF lists 1.3.3"
    )
    assert not checked(library)
    # validation round 2: the `ready` fixture put 1.3.3 in the Library, so
    # the check made no download is what can be asserted
    assert URL_133 not in scripted.calls

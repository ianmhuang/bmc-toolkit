"""Reviewer acceptance tests for the Notes follow-ups closed before 1.0.0:
the prose Citation with a section marked by the sign may hold commas
(AC-4), a reminder that fails after serving keeps the served Note (AC-5),
``notes record`` writes under the Library root's lock (AC-6), and the
managing commands judge a Note current against the version ``find``
answers from (AC-7). Black-box through the CLI; no network."""

import os
import time

import pytest

from bmc_toolkit.spec import lock as lock_mod
from bmc_toolkit.spec import notes as N
from tests.conftest import ok
from tests.test_lock import fake_lock
from tests.test_notes import ANSWER, HELPER, note, on, transcript, write_notes
from tests.test_search_cli import URL, mctp_pdf, run

pytest.importorskip("pypdfium2")

OLD_URL = "https://example.test/DSP0236_1.3.2.pdf"
WIP_URL = "https://example.test/DSP0236_1.4.0.pdf"
HOLDER = "pid 4242 on host elsewhere (notes record, since 2026-09-05T00:00:00+00:00)"


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    """DSP0236 1.3.3 fetched and extracted."""
    scripted.responses[URL] = ok(mctp_pdf(tmp_path))
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def fetch_too(scripted, tmp_path, capsys, catalog_file, url, version):
    scripted.responses[url] = ok(mctp_pdf(tmp_path))
    code, out = run(
        capsys, "fetch", "DSP0236", "--version", version, catalog_file=catalog_file
    )
    assert code == 0, out


def cited(document, version):
    return f"cite: mctp | {document} {version} | 8.1 Overview | PDF page 1 | l | u | p"


# ---------------------------------------------------------------- AC-4


def test_a_marked_prose_section_may_hold_commas_and_several_titles():
    # a title with a comma
    text = "As DSP0274 1.4.1, §6 Symbols, terms and abbreviations, PDF p.27 says."
    expected = "DSP0274 1.4.1 | 6 Symbols, terms and abbreviations | PDF page 27"
    assert N.find_cites(text) == [expected]
    # several titles copied from a cite: line, commas in two of them, and
    # the line numbers after the pages
    text = (
        "DSP0274 1.4.1, §6 Symbols, terms; 7 SPDM, exchanges; 7.1 Requests, "
        "responses, PDF pp.27-28, lines 1-9."
    )
    expected = (
        "DSP0274 1.4.1 | 6 Symbols, terms; 7 SPDM, exchanges; 7.1 Requests, "
        "responses | PDF pages 27-28"
    )
    assert N.find_cites(text) == [expected]
    # the fullwidth comma the Session writes in Chinese prose
    text = "See DSP0275 1.0.2，§4.5.1 Fields, flags，PDF page 9."
    assert N.find_cites(text) == ["DSP0275 1.0.2 | 4.5.1 Fields, flags | PDF page 9"]
    # two marked Citations in one sentence stay two
    text = "DSP0274 1.4.1, §3 Scope, PDF p.18; DSP0236 1.3.3, §8 Overview, PDF p.5."
    assert N.find_cites(text) == [
        "DSP0274 1.4.1 | 3 Scope | PDF page 18",
        "DSP0236 1.3.3 | 8 Overview | PDF page 5",
    ]


def test_an_unmarked_prose_section_still_ends_at_the_first_comma():
    # a mention of another document before the Citation is not swallowed
    text = "Per DSP0274 1.4.1, see also DSP0236 1.3.0, §8 Overview, PDF p.5"
    assert N.find_cites(text) == ["DSP0236 1.3.0 | 8 Overview | PDF page 5"]
    # the plain unmarked form as before
    text = "DSP0274 1.4.1, 3 Scope, PDF p.18, line 82."
    assert N.find_cites(text) == ["DSP0274 1.4.1 | 3 Scope | PDF page 18"]
    # unmarked, a comma inside the section still ends it: no Citation
    assert N.find_cites("DSP0274 1.4.1, 6 Symbols, terms, PDF p.27") == []


def test_record_keys_a_note_to_a_marked_section_with_a_comma(library, tmp_path):
    on(library)
    answer = (
        "The tag fields are listed in DSP0236 1.3.3, §8.2 Msg tag, TO and "
        "Tag owner, PDF p.1."
    )
    path = transcript(tmp_path, [("which tag fields?", [HELPER], answer)])
    assert N.record(library.root, path).startswith("noted ")
    notes = N.load(library.root / N.NOTES_NAME)
    assert notes[0].documents == (("DSP0236", "1.3.3"),)
    assert notes[0].cites == (
        "DSP0236 1.3.3 | 8.2 Msg tag, TO and Tag owner | PDF page 1",
    )
    # a mention of another document before an unmarked-then-marked Citation
    # keys the Note to the cited document only
    answer = "Per DSP0274 1.4.1, see also DSP0236 1.3.0, §8 Overview, PDF p.5."
    path = transcript(tmp_path, [("which overview?", [HELPER], answer)], "u.jsonl")
    assert N.record(library.root, path).startswith("noted ")
    notes = N.load(library.root / N.NOTES_NAME)
    assert notes[1].documents == (("DSP0236", "1.3.0"),)


# ---------------------------------------------------------------- AC-5


def test_a_reminder_that_fails_after_serving_keeps_the_served_note(
    held, library, capsys, catalog_file, monkeypatch
):
    on(library)
    made = note("Give me the overview of the base protocol")
    write_notes(library, made)

    def broken(root):
        raise OSError("disk went away")

    monkeypatch.setattr(N, "reminder", broken)
    code, out = run(capsys, "section", "DSP0236", "overview", catalog_file=catalog_file)
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "notes DSP0236 1.3.3: 1"
    assert lines[1].startswith(f"{made.id} 2026-09-08 | Give me the overview")
    assert lines[2] == (
        f"note: answer from a Note of 2026-09-08 ({made.id}); ask to re-read to verify"
    )
    assert f"end of note {made.id}" in lines
    assert "1 | 8.1 Overview | pages 1-1" in lines  # the answer proper follows
    assert lines[-1] == "note: notes: disk went away"
    assert out.count("note: notes:") == 1
    # find, the same way
    code, out = run(capsys, "find", "DSP0236", "overview", catalog_file=catalog_file)
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "notes DSP0236 1.3.3: 1"
    assert f"end of note {made.id}" in lines
    assert lines[-1] == "note: notes: disk went away"


# ---------------------------------------------------------------- AC-6


def test_record_holds_the_root_lock_while_it_writes_and_releases_it(
    library, tmp_path, monkeypatch
):
    on(library)
    path = transcript(tmp_path, [("packet", [HELPER], ANSWER)])
    seen = {}
    real = N.upsert

    def spy(notes_path, made):
        seen["holder"] = lock_mod.read_holder(library.root / lock_mod.LOCK_NAME)
        return real(notes_path, made)

    monkeypatch.setattr(N, "upsert", spy)
    assert N.record(library.root, path).startswith("noted ")
    holder = seen["holder"]
    assert holder is not None
    assert holder.pid == os.getpid() and holder.command == "notes record"
    assert not (library.root / lock_mod.LOCK_NAME).exists()
    assert len(N.load(library.root / N.NOTES_NAME)) == 1


def test_record_yields_to_a_live_root_lock_and_leaves_the_file_alone(
    held, library, capsys, catalog_file, tmp_path, monkeypatch
):
    on(library)
    write_notes(library, note("packet"))
    before = (library.root / N.NOTES_NAME).read_bytes()
    path = transcript(tmp_path, [("another question", [HELPER], ANSWER)])
    lock_path = fake_lock(library.root, command="notes record")
    monkeypatch.setattr(N, "RECORD_WAIT", 0.3)
    started = time.monotonic()
    code, out = run(
        capsys, "notes", "record", "--transcript", str(path), catalog_file=catalog_file
    )
    assert code == 0
    assert out == f"note: notes: busy: {lock_path} is held by {HOLDER}; not noted\n"
    assert time.monotonic() - started >= 0.2  # it waited for the holder
    assert (library.root / N.NOTES_NAME).read_bytes() == before
    assert lock_path.exists()  # the other Session's lock is left to it
    # status lists the lock like any other
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0
    assert f"lock: {lock_path} held by {HOLDER}, live" in out.splitlines()


def test_a_stale_root_lock_is_listed_by_prune_and_taken_over_by_record(
    library, tmp_path, capsys, catalog_file
):
    on(library)
    stale = fake_lock(
        library.root, command="notes record", age=lock_mod.STALE_SECONDS + 60
    )
    code, out = run(capsys, "prune", catalog_file=catalog_file)
    assert code == 0, out
    assert f"would remove {stale} (stale lock, {HOLDER})" in out.splitlines()
    path = transcript(tmp_path, [("packet", [HELPER], ANSWER)])
    code, out = run(
        capsys, "notes", "record", "--transcript", str(path), catalog_file=catalog_file
    )
    assert code == 0 and out.startswith("noted ")
    assert not stale.exists()
    assert len(N.load(library.root / N.NOTES_NAME)) == 1


# ---------------------------------------------------------------- AC-7


def test_managing_commands_judge_against_the_version_find_answers_from(
    held, library, scripted, tmp_path, capsys, catalog_file
):
    # 1.3.2 and 1.3.3 (the catalog's Latest) both held: a Note citing 1.3.2
    # is superseded in list, recall and prune, as it is in find
    on(library)
    fetch_too(scripted, tmp_path, capsys, catalog_file, OLD_URL, "1.3.2")
    current = note("packet", time="2026-09-08T02:00:00+00:00")
    older = note(
        "older packet",
        answer=cited("DSP0236", "1.3.2"),
        time="2026-09-08T01:00:00+00:00",
    )
    write_notes(library, current, older)
    code, out = run(capsys, "notes", "list", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines() == [
        f"{current.id} 2026-09-08 | packet | DSP0236 1.3.3 p.1",
        f"{older.id} 2026-09-08 superseded | older packet | DSP0236 1.3.2 p.1",
    ]
    code, out = run(capsys, "recall", older.id, catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[:2] == [
        f"{older.id} 2026-09-08 superseded | older packet | DSP0236 1.3.2 p.1",
        "note: this Note cites DSP0236 1.3.2, the Library answers from 1.3.3; "
        "read the pages again",
    ]
    assert "answer from a Note" not in out
    code, out = run(capsys, "recall", current.id, catalog_file=catalog_file)
    assert code == 0 and "answer from a Note" in out
    code, out = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    assert code == 0
    assert f"{older.id} 2026-09-08 superseded | older packet" in out
    assert f"{current.id} 2026-09-08 | packet" in out
    code, out = run(capsys, "notes", "prune", catalog_file=catalog_file)
    assert code == 0
    assert out == (
        f"pruned {older.id} 2026-09-08 superseded | older packet | "
        "DSP0236 1.3.2 p.1\n"
    )
    assert [n.id for n in N.load(library.root / N.NOTES_NAME)] == [current.id]


def test_a_held_wip_version_is_not_the_one_answered_from(
    held, library, scripted, tmp_path, capsys, catalog_file
):
    # 1.4.0 is WIP in the catalog: find answers from 1.3.3 while it is held,
    # so a Note citing 1.4.0 is superseded and one citing 1.3.3 is current
    on(library)
    fetch_too(scripted, tmp_path, capsys, catalog_file, WIP_URL, "1.4.0")
    current = note("packet", time="2026-09-08T02:00:00+00:00")
    wip = note(
        "wip packet",
        answer=cited("DSP0236", "1.4.0"),
        time="2026-09-08T01:00:00+00:00",
    )
    write_notes(library, current, wip)
    code, out = run(capsys, "notes", "list", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines() == [
        f"{current.id} 2026-09-08 | packet | DSP0236 1.3.3 p.1",
        f"{wip.id} 2026-09-08 superseded | wip packet | DSP0236 1.4.0 p.1",
    ]
    code, out = run(capsys, "recall", wip.id, catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[1] == (
        "note: this Note cites DSP0236 1.4.0, the Library answers from 1.3.3; "
        "read the pages again"
    )
    code, out = run(capsys, "notes", "prune", catalog_file=catalog_file)
    assert code == 0 and out.startswith(f"pruned {wip.id} ")
    assert [n.id for n in N.load(library.root / N.NOTES_NAME)] == [current.id]


def test_recall_names_the_answering_version_or_that_none_is_held(
    held, library, scripted, tmp_path, capsys, catalog_file
):
    on(library)
    fetch_too(scripted, tmp_path, capsys, catalog_file, OLD_URL, "1.3.2")
    two = note(
        "two documents",
        answer=cited("DSP0236", "1.2.0") + "\n" + cited("DSP0999", "1.0"),
    )
    write_notes(library, two)
    code, out = run(capsys, "recall", two.id, catalog_file=catalog_file)
    assert code == 0
    # with two versions held the one find answers from is named, not both
    assert out.splitlines()[1] == (
        "note: this Note cites DSP0236 1.2.0, the Library answers from 1.3.3; "
        "DSP0999 1.0, which the Library no longer holds; read the pages again"
    )
    assert "1.3.2" not in out.splitlines()[1]

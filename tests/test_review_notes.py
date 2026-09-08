"""Acceptance tests for the Notes feature, serving side: the Note file is
written by hand and read through the public CLI (find, section, recall,
notes list / forget / prune, status). The notes module is never imported
here; every check goes through ``cli.main``."""

import json
import re

import pytest

from bmc_toolkit.spec import cli as cli_mod
from bmc_toolkit.spec.cli import main
from bmc_toolkit.spec.library import LibraryError
from tests.conftest import ok
from tests.test_search_cli import URL, mctp_pdf

pytest.importorskip("pypdfium2")

OLD_URL = "https://example.test/DSP0236_1.3.2.pdf"
CITE = (
    "cite: mctp | DSP0236 1.3.3 | 8.1 Overview | PDF page 1 | lines 1-2 | "
    "https://example.test/DSP0236_1.3.3.pdf | /lib"
)
REMINDER = re.compile(
    r"^note: notes\.jsonl holds 1 Notes \(\d+ KB\), over notes_limit; run notes prune$"
)


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    """DSP0236 1.3.3 fetched and extracted."""
    scripted.responses[URL] = ok(mctp_pdf(tmp_path))
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "extract", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def config(library, text):
    library.root.mkdir(parents=True, exist_ok=True)
    (library.root / "config.toml").write_text(text, encoding="utf-8")


def on(library, extra=""):
    config(library, f"[library]\nnotes = true\n{extra}")


def a_note(
    id,
    question,
    *,
    cites=("DSP0236 1.3.3 | 8.1 Overview | PDF page 1",),
    answer="The packet fields are as follows.\n\n" + CITE,
    time="2026-09-08T01:02:03+00:00",
    partial=False,
    context="",
):
    """One Note in the documented on-disk form; ``documents`` is derived
    from the cites so the two never disagree."""
    documents = []
    for cite in cites:
        doc, ver = cite.split(" | ")[0].split(" ", 1)
        if [doc, ver] not in documents:
            documents.append([doc, ver])
    return {
        "id": id,
        "question": question,
        "context": context,
        "answer": answer,
        "partial": partial,
        "cites": list(cites),
        "documents": sorted(documents),
        "time": time,
    }


def write_notes(library, *notes, extra_lines=()):
    library.root.mkdir(parents=True, exist_ok=True)
    path = library.root / "notes.jsonl"
    lines = [json.dumps(n, ensure_ascii=False) for n in notes] + list(extra_lines)
    path.write_text("".join(ln + "\n" for ln in lines), encoding="utf-8")
    return path


def find(capsys, catalog_file, *extra):
    return run(capsys, "find", "DSP0236", "packet", *extra, catalog_file=catalog_file)


# ---------------------------------------------------------------- AC-4


def test_find_lists_the_notes_and_prints_the_latest_matching_one_whole(
    held, library, capsys, catalog_file
):
    on(library)
    older = a_note(
        "aaaa0001", "What is in the MCTP packet?", time="2026-09-01T00:00:00+00:00"
    )
    newer = a_note(
        "aaaa0002",
        "Which fields does an MCTP packet header carry?",
        time="2026-09-02T10:00:00+00:00",
    )
    write_notes(library, older, newer)
    code, out = find(capsys, catalog_file)
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "notes DSP0236 1.3.3: 2"
    # latest first, the documented title line form
    assert lines[1] == (
        "aaaa0002 2026-09-02 | Which fields does an MCTP packet header carry? "
        "| DSP0236 1.3.3 p.1"
    )
    assert (
        lines[2]
        == "aaaa0001 2026-09-01 | What is in the MCTP packet? | DSP0236 1.3.3 p.1"
    )
    # both match the pattern; only the latest is printed whole, right after
    # the title lines, in the documented frame
    assert lines[3] == (
        "note: answer from a Note of 2026-09-02 (aaaa0002); ask to re-read to verify"
    )
    assert lines[4] == "The packet fields are as follows."
    assert lines[5] == ""
    assert lines[6] == CITE
    assert lines[7] == "end of note aaaa0002"
    assert lines[8].startswith("DSP0236 p.")  # then the hits, untouched
    assert out.count("end of note") == 1
    assert "aaaa0001); ask to re-read" not in out


def test_the_query_must_be_covered_by_the_question_or_the_cited_section_titles(
    held, library, capsys, catalog_file
):
    on(library)
    # "packet" is neither in the question nor in the cited section title
    write_notes(library, a_note("bbbb0001", "What does the tag owner bit mean?"))
    code, out = find(capsys, catalog_file)
    assert code == 0
    assert out.splitlines()[0] == "notes DSP0236 1.3.3: 1"
    assert out.splitlines()[1].startswith("bbbb0001 2026-09-08 | ")
    assert "answer from a Note" not in out and "end of note" not in out
    # a question without ASCII words still matches through the section title
    write_notes(
        library,
        a_note(
            "bbbb0002",
            "封包欄位有哪些？",
            cites=("DSP0236 1.3.3 | 8.2 MCTP packet fields | PDF page 1",),
        ),
    )
    code, out = find(capsys, catalog_file)
    assert code == 0
    assert "note: answer from a Note of 2026-09-08 (bbbb0002)" in out
    # every token of the query must occur: one missing word is no match
    code, out = run(
        capsys, "find", "DSP0236", "packet checksum", catalog_file=catalog_file
    )
    assert code == 0 and "answer from a Note" not in out
    # matching is case-insensitive
    code, out = run(capsys, "find", "DSP0236", "PACKET", catalog_file=catalog_file)
    assert code == 0 and "answer from a Note of 2026-09-08 (bbbb0002)" in out


def test_section_serves_the_same_way(held, library, capsys, catalog_file):
    on(library)
    write_notes(
        library, a_note("cccc0001", "Give me the overview of the base protocol")
    )
    code, out = run(capsys, "section", "DSP0236", "overview", catalog_file=catalog_file)
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "notes DSP0236 1.3.3: 1"
    assert lines[1].startswith("cccc0001 2026-09-08 | Give me the overview")
    assert lines[2] == (
        "note: answer from a Note of 2026-09-08 (cccc0001); ask to re-read to verify"
    )
    assert "end of note cccc0001" in lines
    assert any(
        "8.1 Overview" in ln for ln in lines[lines.index("end of note cccc0001") :]
    )


def test_at_most_ten_title_lines_latest_first(held, library, capsys, catalog_file):
    on(library)
    notes = [
        a_note(
            f"dddd00{i:02d}",
            f"question number {i} about nothing",
            time=f"2026-08-{i:02d}T00:00:00+00:00",
        )
        for i in range(1, 13)
    ]
    write_notes(library, *notes)
    code, out = find(capsys, catalog_file)
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "notes DSP0236 1.3.3: 12"
    titles = [ln for ln in lines if ln.startswith("dddd00")]
    assert len(titles) == 10
    assert [t.split(" ", 1)[0] for t in titles] == [
        f"dddd00{i:02d}" for i in range(12, 2, -1)
    ]
    assert "answer from a Note" not in out


def test_a_partial_note_is_listed_but_never_printed_whole(
    held, library, capsys, catalog_file
):
    on(library)
    write_notes(
        library,
        a_note(
            "eeee0001", "packet fields", answer="First paragraph only.", partial=True
        ),
    )
    code, out = find(capsys, catalog_file)
    assert code == 0
    assert out.splitlines()[0] == "notes DSP0236 1.3.3: 1"
    assert out.splitlines()[1].startswith("eeee0001 2026-09-08 | packet fields | ")
    assert "answer from a Note" not in out and "First paragraph only." not in out


def test_without_a_note_citing_the_document_the_output_is_unchanged(
    held, library, capsys, catalog_file
):
    code, plain = find(capsys, catalog_file)
    assert code == 0
    on(library)
    write_notes(
        library,
        a_note("ffff0001", "packet", cites=("DSP9999 1.0 | s | PDF page 1",)),
    )
    code, out = find(capsys, catalog_file)
    assert (code, out) == (0, plain)
    code, out = run(capsys, "section", "DSP0236", "8.1", catalog_file=catalog_file)
    assert code == 0 and "notes DSP0236" not in out
    # and as soon as one cites it, the same call lists it
    write_notes(library, a_note("ffff0002", "tag owner"))
    code, out = find(capsys, catalog_file)
    assert code == 0 and out.splitlines()[0] == "notes DSP0236 1.3.3: 1"
    assert out.endswith(plain)


def test_a_broken_line_in_the_file_is_skipped_and_never_stops_a_command(
    held, library, capsys, catalog_file
):
    on(library)
    write_notes(
        library,
        a_note("abcd0001", "packet"),
        extra_lines=['{"id": "cut off', "", "not json at all"],
    )
    code, out = find(capsys, catalog_file)
    assert code == 0
    assert out.splitlines()[0] == "notes DSP0236 1.3.3: 1"
    assert "answer from a Note of 2026-09-08 (abcd0001)" in out
    code, out = run(capsys, "notes", "list", catalog_file=catalog_file)
    assert code == 0 and len(out.splitlines()) == 1


def test_the_notes_block_sits_between_the_download_preamble_and_the_hits(
    library, scripted, tmp_path, capsys, catalog_file
):
    """Round 1 F6: a reading command that downloads on the fly prints
    fetched / extracted lines first; the Notes come after all of them and
    right before the first hit."""
    on(library)
    write_notes(library, a_note("f6f60001", "packet"))
    scripted.responses[URL] = ok(mctp_pdf(tmp_path))
    code, out = find(capsys, catalog_file)  # nothing held: find fetches first
    assert code == 0, out
    lines = out.splitlines()
    start = lines.index("notes DSP0236 1.3.3: 1")
    preamble = lines[:start]
    assert any(ln.startswith("fetched DSP0236 1.3.3") for ln in preamble), out
    assert any(ln.startswith("extracted DSP0236 1.3.3") for ln in preamble), out
    assert not any(ln.startswith("DSP0236 p.") for ln in preamble)
    end = lines.index("end of note f6f60001")
    assert lines[start + 1].startswith("f6f60001 2026-09-08 | packet | ")
    assert not any(ln.startswith("DSP0236 p.") for ln in lines[start:end])
    assert lines[end + 1].startswith("DSP0236 p.")
    # the same call again, now with the document held, prints no preamble
    code, again = find(capsys, catalog_file)
    assert code == 0 and again.splitlines()[0] == "notes DSP0236 1.3.3: 1"
    assert again == "\n".join(lines[start:]) + "\n"


# ---------------------------------------------------------------- AC-5


def test_a_note_citing_another_version_of_the_document_is_superseded(
    held, library, capsys, catalog_file
):
    on(library)
    write_notes(
        library,
        a_note(
            "1111aaaa",
            "packet",
            cites=("DSP0236 1.3.2 | 8.1 Overview | PDF pages 1-2",),
            answer="old answer\ncite: mctp | DSP0236 1.3.2 | 8.1 Overview | PDF pages 1-2 | l | u | p",
        ),
    )
    code, out = find(capsys, catalog_file)
    assert code == 0
    assert out.splitlines()[0] == "notes DSP0236 1.3.3: 1"
    # superseded after the date, the pages still named so the Session can
    # read them in the new version; never printed whole
    assert (
        out.splitlines()[1]
        == "1111aaaa 2026-09-08 superseded | packet | DSP0236 1.3.2 pp.1-2"
    )
    assert "answer from a Note" not in out and "old answer" not in out


def test_a_note_whose_other_document_is_not_held_is_superseded(
    held, library, capsys, catalog_file
):
    on(library)
    write_notes(
        library,
        a_note(
            "2222aaaa",
            "packet",
            cites=(
                "DSP0236 1.3.3 | 8.1 Overview | PDF page 1",
                "DSP0274 1.4.1 | 3 Scope | PDF page 18",
            ),
        ),
    )
    code, out = find(capsys, catalog_file)
    assert code == 0
    assert out.splitlines()[1] == (
        "2222aaaa 2026-09-08 superseded | packet | DSP0236 1.3.3 p.1; DSP0274 1.4.1 p.18"
    )
    assert "answer from a Note" not in out


# ---------------------------------------------------------------- AC-6


def test_recall_prints_a_note_whole_and_a_superseded_one_as_a_pointer(
    held, library, capsys, catalog_file
):
    on(library)
    current = a_note("3333aaaa", "packet")
    old = a_note(
        "3333bbbb",
        "old packet",
        cites=("DSP0236 1.3.2 | 8.1 Overview | PDF page 1",),
        answer="old answer",
    )
    write_notes(library, current, old)
    code, out = run(capsys, "recall", "3333aaaa", catalog_file=catalog_file)
    assert code == 0
    lines = out.splitlines()
    assert (
        "note: answer from a Note of 2026-09-08 (3333aaaa); ask to re-read to verify"
        in lines
    )
    assert lines[-1] == "end of note 3333aaaa"
    assert "The packet fields are as follows." in lines
    code, out = run(capsys, "recall", "3333bbbb", catalog_file=catalog_file)
    assert code == 0
    lines = out.splitlines()
    # round 1 F5: the pointer names the version the Library answers from
    assert lines[1] == (
        "note: this Note cites DSP0236 1.3.2, the Library answers from 1.3.3; "
        "read the pages again"
    )
    assert "ask to re-read to verify" not in out
    assert "old answer" in lines and lines[-1] == "end of note 3333bbbb"
    code, out = run(capsys, "recall", "00000000", catalog_file=catalog_file)
    assert code == 2 and "00000000" in out


def test_recall_names_every_held_version_or_says_none_is_held(
    held, library, scripted, tmp_path, capsys, catalog_file
):
    """AC-6: `the Library answers from W` with the version held or not
    (several held: the one `find` answers from), `which the Library no
    longer holds` with none; one part per missing version."""
    on(library)
    gone = a_note(
        "3333cccc",
        "gone",
        cites=("DSP0999 1.0 | 1 A | PDF page 1",),
        answer="an answer about a document the Library never held",
    )
    both = a_note(
        "3333dddd",
        "two missing",
        cites=(
            "DSP0236 1.2.0 | 8.1 Overview | PDF page 1",
            "DSP0999 1.0 | 1 A | PDF page 1",
        ),
        answer="an answer citing two versions",
    )
    write_notes(library, gone, both)
    code, out = run(capsys, "recall", "3333cccc", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[1] == (
        "note: this Note cites DSP0999 1.0, which the Library no longer holds; "
        "read the pages again"
    )
    assert out.splitlines()[-1] == "end of note 3333cccc"
    code, out = run(capsys, "recall", "3333dddd", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[1] == (
        "note: this Note cites DSP0236 1.2.0, the Library answers from 1.3.3; "
        "DSP0999 1.0, which the Library no longer holds; read the pages again"
    )
    # a second version of DSP0236 held: the one find answers from is named
    # (the follow-up of round 2 made the managing commands judge as find does)
    scripted.responses[OLD_URL] = ok(mctp_pdf(tmp_path))
    code, out = run(
        capsys, "fetch", "DSP0236", "--version", "1.3.2", catalog_file=catalog_file
    )
    assert code == 0, out
    code, out = run(capsys, "recall", "3333dddd", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[1] == (
        "note: this Note cites DSP0236 1.2.0, the Library answers from 1.3.3; "
        "DSP0999 1.0, which the Library no longer holds; read the pages again"
    )


# ---------------------------------------------------------------- AC-7


def test_notes_list_filters_by_document_and_is_latest_first(
    held, library, capsys, catalog_file
):
    on(library)
    write_notes(
        library,
        a_note("4444aaaa", "first", time="2026-09-01T00:00:00+00:00"),
        a_note(
            "4444bbbb",
            "second",
            cites=("DSP0274 1.4.1 | 3 Scope | PDF page 18",),
            time="2026-09-03T00:00:00+00:00",
        ),
        a_note("4444cccc", "third", time="2026-09-02T00:00:00+00:00"),
    )
    code, out = run(capsys, "notes", "list", catalog_file=catalog_file)
    assert code == 0
    assert [ln.split(" ")[0] for ln in out.splitlines()] == [
        "4444bbbb",
        "4444cccc",
        "4444aaaa",
    ]
    assert (
        out.splitlines()[0]
        == "4444bbbb 2026-09-03 superseded | second | DSP0274 1.4.1 p.18"
    )
    code, out = run(capsys, "notes", "list", "DSP0236", catalog_file=catalog_file)
    assert code == 0
    assert [ln.split(" ")[0] for ln in out.splitlines()] == ["4444cccc", "4444aaaa"]
    code, out = run(capsys, "notes", "list", "DSP9999", catalog_file=catalog_file)
    assert code == 0 and "4444" not in out


def test_notes_forget_and_prune(held, library, capsys, catalog_file):
    on(library)
    current = a_note("5555aaaa", "packet", time="2026-09-02T00:00:00+00:00")
    old = a_note(
        "5555bbbb",
        "old packet",
        cites=("DSP0236 1.3.2 | 8.1 Overview | PDF page 1",),
        time="2026-09-01T00:00:00+00:00",
    )
    ancient = a_note("5555cccc", "ancient", time="1990-01-01T00:00:00+00:00")
    path = write_notes(library, current, old, ancient)

    def ids():
        return [json.loads(ln)["id"] for ln in path.read_text("utf-8").splitlines()]

    code, out = run(capsys, "notes", "prune", catalog_file=catalog_file)
    assert code == 0 and "5555bbbb" in out and "5555aaaa" not in out
    assert ids() == ["5555aaaa", "5555cccc"]
    code, out = run(capsys, "notes", "prune", catalog_file=catalog_file)
    assert (code, out) == (0, "nothing to prune\n")
    code, out = run(
        capsys, "notes", "prune", "--days", "3650", catalog_file=catalog_file
    )
    assert code == 0 and "5555cccc" in out and "5555aaaa" not in out
    assert ids() == ["5555aaaa"]
    code, out = run(capsys, "notes", "forget", "5555aaaa", catalog_file=catalog_file)
    assert code == 0 and "5555aaaa" in out
    assert ids() == []
    code, out = run(capsys, "notes", "forget", "5555aaaa", catalog_file=catalog_file)
    assert code == 2 and "5555aaaa" in out
    write_notes(library, current, ancient)
    code, out = run(capsys, "notes", "prune", "--all", catalog_file=catalog_file)
    assert code == 0 and "5555aaaa" in out and "5555cccc" in out
    assert ids() == []


def test_status_counts_the_notes(held, library, capsys, catalog_file):
    on(library)
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0 and "notes:" not in out  # no file yet
    write_notes(library, a_note("6666aaaa", "packet"), a_note("6666bbbb", "tag"))
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0
    assert re.search(r"^notes: 2 \(\d+ KB\)$", out, re.MULTILINE)


def test_status_of_an_empty_library_prints_the_reminder_first_and_the_count(
    library, capsys, catalog_file
):
    """Round 1 F3: with no document held, `status` still leads with the
    size reminder (AC-8, before `library:`) and ends with the count (AC-7)."""
    on(library, 'notes_limit = "1KB"\n')
    write_notes(library, a_note("6666cccc", "packet", answer="y" * 3000 + "\n" + CITE))
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert REMINDER.match(lines[0]), lines[0]
    assert lines[1].startswith("library: ") and lines[2] == "(empty)"
    assert re.fullmatch(r"notes: 1 \(\d+ KB\)", lines[-1]), lines[-1]
    # under the limit: no reminder, `library:` first, the count still there
    on(library, 'notes_limit = "1MB"\n')
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0
    lines = out.splitlines()
    assert lines[0].startswith("library: ") and lines[1] == "(empty)"
    assert re.fullmatch(r"notes: 1 \(\d+ KB\)", lines[-1]), lines[-1]


# ---------------------------------------------------------------- AC-8


def test_the_size_reminder_leads_find_section_and_status(
    held, library, capsys, catalog_file
):
    on(library, 'notes_limit = "1KB"\n')
    write_notes(library, a_note("7777aaaa", "tag", answer="y" * 3000 + "\n" + CITE))
    for argv in (["find", "DSP0236", "packet"], ["section", "DSP0236", "8.1"]):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 0
        assert re.match(
            r"^note: notes\.jsonl holds 1 Notes \(\d+ KB\), over notes_limit; "
            r"run notes prune$",
            out.splitlines()[0],
        )
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0 and REMINDER.match(out.splitlines()[0]), out
    assert out.splitlines()[1].startswith("library: ")
    assert (library.root / "notes.jsonl").stat().st_size > 3000  # nothing removed
    on(library, 'notes_limit = "0"\n')
    code, out = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    assert code == 0 and "over notes_limit" not in out
    on(library, 'notes_limit = "1MB"\n')
    code, out = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    assert code == 0 and "over notes_limit" not in out


def test_a_bad_notes_limit_is_one_note_line_and_exit_zero(
    held, library, capsys, catalog_file
):
    on(library, 'notes_limit = "five"\n')
    write_notes(library, a_note("8888aaaa", "packet"))
    code, out = find(capsys, catalog_file)
    assert code == 0
    last = out.splitlines()[-1]
    assert last.startswith("note: notes: ") and "notes_limit" in last
    assert out.splitlines()[0].startswith("DSP0236 p.")  # the answer is intact


def test_notes_limit_takes_only_an_integer_with_kb_or_mb_or_zero(
    held, library, capsys, catalog_file
):
    """Round 1 F8: the documented forms are accepted, case-insensitively;
    a bare number (string or integer), a fraction, a boolean and an unknown
    unit are refused with one note line, the answer intact."""
    write_notes(library, a_note("8888bbbb", "tag", answer="y" * 3000 + "\n" + CITE))
    for value in ('"2KB"', '"2kb"', '"1 KB"'):
        on(library, f"notes_limit = {value}\n")
        code, out = find(capsys, catalog_file)
        assert code == 0 and REMINDER.match(out.splitlines()[0]), (value, out)
    for value in ('"1MB"', '"5mb"', '"0"'):
        on(library, f"notes_limit = {value}\n")
        code, out = find(capsys, catalog_file)
        assert code == 0 and out.splitlines()[0] == "notes DSP0236 1.3.3: 1", value
        assert "note: notes" not in out, value
    for value in ("true", "100", '"100"', '"0.5MB"', '"1GB"', '"five"', '""'):
        on(library, f"notes_limit = {value}\n")
        code, out = find(capsys, catalog_file)
        assert code == 0, value
        lines = out.splitlines()
        assert lines[0].startswith("DSP0236 p."), (value, out)
        assert lines[-1].startswith("note: notes: ") and "notes_limit" in lines[-1], (
            value,
            out,
        )
        assert sum(ln.startswith("note: notes: ") for ln in lines) == 1, value


# ---------------------------------------------------------------- AC-9


def test_off_by_default_nothing_is_served_and_the_commands_say_so(
    held, library, capsys, catalog_file
):
    write_notes(library, a_note("9999aaaa", "packet"))
    code, plain = find(capsys, catalog_file)
    assert code == 0
    assert "notes DSP0236" not in plain and "Note" not in plain
    assert plain.splitlines()[0].startswith("DSP0236 p.")
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0 and "notes:" not in out
    config(library, "[library]\nnotes = false\n")
    code, out = find(capsys, catalog_file)
    assert (code, out) == (0, plain)
    expected = (
        f"notes are off: set [library] notes = true in {library.root / 'config.toml'}\n"
    )
    for argv in (["recall", "9999aaaa"], ["notes", "list"], ["notes", "prune"]):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert (code, out) == (2, expected), argv
    # the file is left as it is
    assert (
        json.loads((library.root / "notes.jsonl").read_text("utf-8"))["id"]
        == "9999aaaa"
    )


def test_a_switch_that_is_not_a_boolean_is_refused_like_offline(
    held, library, capsys, catalog_file
):
    config(library, '[library]\nnotes = "yes"\n')
    write_notes(library, a_note("9999bbbb", "packet"))
    code, out = find(capsys, catalog_file)
    assert code == 0
    assert out.splitlines()[-1] == (
        f"note: notes: {library.root / 'config.toml'}: library.notes must be true or false"
    )
    assert "answer from a Note" not in out


def test_recall_and_notes_refuse_a_bad_switch_or_an_unparsable_config(
    held, library, capsys, catalog_file
):
    """Round 1 F2: the managing commands print the refusal in the
    library.offline form and exit 2 instead of a traceback; the file is
    left alone; `status` turns the same failure into one note line."""
    path = write_notes(library, a_note("f2f20001", "packet"))
    before = path.read_text("utf-8")
    config(library, "[library]\nnotes = 1\n")
    message = f"{library.root / 'config.toml'}: library.notes must be true or false\n"
    for argv in (
        ["recall", "f2f20001"],
        ["notes", "list"],
        ["notes", "list", "DSP0236"],
        ["notes", "forget", "f2f20001"],
        ["notes", "prune"],
        ["notes", "prune", "--all"],
    ):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert (code, out) == (2, message), argv
    config(library, "[library\nnotes = true\n")  # does not parse
    for argv in (["recall", "f2f20001"], ["notes", "list"], ["notes", "prune"]):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 2, (argv, out)
        assert len(out.splitlines()) == 1 and "Traceback" not in out, (argv, out)
        assert out.startswith(str(library.root / "config.toml")), (argv, out)
    assert path.read_text("utf-8") == before
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[0].startswith("note: notes: "), out
    assert out.splitlines()[0].startswith(
        f"note: notes: {library.root / 'config.toml'}"
    )
    # `notes record`, the hook's command, never exits non-zero on it
    code, out = run(
        capsys, "notes", "record", "--transcript", "x", catalog_file=catalog_file
    )
    assert code == 0 and len(out.splitlines()) == 1 and out.startswith("note: notes: ")


# --------------------------------------------------------------- AC-13


def test_the_answer_is_printed_before_an_error_and_a_module_failure_is_one_line(
    held, library, capsys, catalog_file, monkeypatch
):
    on(library)
    write_notes(library, a_note("aaaa9999", "packet"))
    # a non-zero exit serves nothing
    code, out = run(
        capsys, "find", "DSP0236", "[", "--regex", catalog_file=catalog_file
    )
    assert code == 2 and "notes DSP0236" not in out and "bad regular expression" in out
    # a failure inside the module is one note line, the exit code untouched
    monkeypatch.setattr(cli_mod.notes_mod, "serve", lambda *a: 1 / 0)
    code, out = find(capsys, catalog_file)
    assert code == 0
    assert out.splitlines()[0].startswith("DSP0236 p.")
    assert out.splitlines()[-1] == "note: notes: division by zero"

    # what the command printed before raising comes before the error message
    def boom(args):
        print("half done")
        raise LibraryError("gone")

    monkeypatch.setitem(cli_mod.COMMANDS, "find", boom)
    code, out = find(capsys, catalog_file)
    assert (code, out) == (2, "half done\nlibrary: gone\n")

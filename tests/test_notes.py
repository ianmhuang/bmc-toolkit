"""Notes: the Stop hook records an answer; find and section serve it while
its versions hold; recall, list, forget, prune; the switch; the module
stays an add-on."""

import json
import re
from pathlib import Path

import pytest

from bmc_toolkit.spec import cli as cli_mod
from bmc_toolkit.spec import notes as N
from bmc_toolkit.spec.library import LibraryError
from tests.conftest import ok
from tests.test_search_cli import URL, mctp_pdf, run

pytest.importorskip("pypdfium2")

ROOT = Path(__file__).resolve().parents[1]
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")
CITE = (
    "cite: mctp | DSP0236 1.3.3 | 8.1 Overview | PDF page 1 | lines 1-2 | "
    "https://example.test/DSP0236_1.3.3.pdf | /lib"
)
ANSWER = f"The packet fields are as follows.\n\n{CITE}\n"


@pytest.fixture
def held(catalog_file, library, scripted, tmp_path, capsys):
    """DSP0236 1.3.3 fetched and extracted, as in test_search_cli."""
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


def note(question, answer=ANSWER, time="2026-09-08T01:02:03+00:00", context=""):
    made = N.make_note(question, context, answer, time)
    assert made is not None
    return made


def write_notes(library, *notes):
    path = library.root / N.NOTES_NAME
    path.write_text("".join(n.to_json() + "\n" for n in notes), encoding="utf-8")
    return path


def event(kind, content, **extra):
    return json.dumps({"type": kind, "message": {"content": content}, **extra})


def transcript(tmp_path, turns, name="t.jsonl"):
    """A transcript in the shape Claude Code writes: per turn the prompt,
    tool calls with their results, and the final text."""
    lines = []
    for prompt, commands, answer in turns:
        lines.append(event("user", prompt, promptId="p"))
        for command in commands:
            lines.append(
                event(
                    "assistant",
                    [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": command},
                        }
                    ],
                )
            )
            lines.append(event("user", [{"type": "tool_result", "content": "..."}]))
        lines.append(event("assistant", [{"type": "text", "text": answer}]))
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


HELPER = 'python "/plugin/skills/bmc-spec/scripts/bmcspec.py" find DSP0236 packet'


# ------------------------------------------------------------- parsing


def test_find_cites_takes_every_form_the_session_writes():
    text = "\n".join(
        [
            "Line form.",
            "cite: mctp | DSP0236 1.3.3 | 8.1 Overview | PDF page 1 | lines 1-2 | u",
            "Inline (cite: spdm | DSP0274 1.4.1 | 3 Scope | PDF page 18 | lines 82).",
            "Prefix dropped: mctp | DSP0236 1.3.3 | 8.2 Fields | PDF pages 43-45 | u",
            "Prose: DSP0274 1.4.1, §7 SPDM message exchanges, PDF p.27, line 99.",
            "Prose: DSP0275 1.0.2，4.5.1，PDF page 9，line 22。",
            "No version: DSP0275 4.6, PDF page 9.",
            "cite: code | bmcweb ae6cec2 (master) | x.hpp | lines 1-3 | p",
            "Again: cite: mctp | DSP0236 1.3.3 | 8.1 Overview | PDF page 1 | lines 3",
            "Spanning: cite: spdm | DSP0274 1.4.1 | 6 Symbols and abbreviated terms; "
            "7 SPDM message exchanges | PDF page 27 | lines 1-3 | u | p",
            "Prose spanning: DSP0274 1.4.1, §6 Symbols and abbreviated terms; "
            "7 SPDM message exchanges; 7.1 Request and response messages; "
            "7.2 Generic SPDM message format, PDF pp.27-28, lines 1-9.",
        ]
    )
    assert N.find_cites(text) == [
        "DSP0236 1.3.3 | 8.1 Overview | PDF page 1",
        "DSP0274 1.4.1 | 3 Scope | PDF page 18",
        "DSP0236 1.3.3 | 8.2 Fields | PDF pages 43-45",
        "DSP0274 1.4.1 | 7 SPDM message exchanges | PDF page 27",
        "DSP0275 1.0.2 | 4.5.1 | PDF page 9",
        "DSP0274 1.4.1 | 6 Symbols and abbreviated terms; 7 SPDM message exchanges"
        " | PDF page 27",
        "DSP0274 1.4.1 | 6 Symbols and abbreviated terms; 7 SPDM message exchanges;"
        " 7.1 Request and response messages; 7.2 Generic SPDM message format"
        " | PDF pages 27-28",
    ]


def test_note_sections_are_the_parts_of_a_spanning_section_field():
    made = note(
        "How does a request map to a response?",
        answer=(
            "One request, one response.\n"
            "cite: spdm | DSP0274 1.4.1 | 6 Symbols and abbreviated terms; "
            "7 SPDM message exchanges | PDF page 27 | lines 1-3 | u | p\n"
        ),
    )
    assert made.sections() == [
        "6 Symbols and abbreviated terms",
        "7 SPDM message exchanges",
    ]
    assert made.pages() == "DSP0274 1.4.1 p.27"
    assert N.matches("SPDM exchanges", made)
    assert N.matches("abbreviated", made)


def test_make_note_keys_documents_and_pages_and_stores_long_answers_partial():
    answer = "\n".join(
        [
            "First paragraph (DSP0274 1.4.1, §3 Scope, PDF p.18).",
            "",
            "x" * N.MAX_ANSWER,
            "cite: mctp | DSP0236 1.3.3 | 8.1 Overview | PDF page 1 | lines 1 | u | p",
        ]
    )
    made = note("What is SPDM for?", answer, context="  earlier prompt  ")
    assert made.documents == (("DSP0236", "1.3.3"), ("DSP0274", "1.4.1"))
    assert made.pages() == "DSP0274 1.4.1 p.18; DSP0236 1.3.3 p.1"
    assert made.partial and made.answer == answer.split("\n\n")[0]
    assert made.context == "earlier prompt"
    assert len(made.id) == 8 and made.id == N.note_id(
        "What is  SPDM for? ", made.documents
    )
    assert N.make_note("q", "", "no citation here", "t") is None


def test_note_round_trips_and_a_bad_line_is_skipped(tmp_path):
    made = note("q")
    again = N.Note.from_json(made.to_json())
    assert again == made
    path = tmp_path / N.NOTES_NAME
    path.write_text(made.to_json() + "\n{not json\n", encoding="utf-8")
    assert N.load(path) == [made]
    assert N.load(tmp_path / "missing.jsonl") == []


def test_upsert_replaces_the_same_id_and_appends_a_new_one(tmp_path):
    path = tmp_path / N.NOTES_NAME
    first = note("q", time="2026-09-01T00:00:00+00:00")
    assert N.upsert(path, first) is False
    later = note("q", time="2026-09-02T00:00:00+00:00")
    assert N.upsert(path, later) is True
    other = note("another question")
    assert N.upsert(path, other) is False
    assert [n.time for n in N.load(path)] == [later.time, other.time]


# -------------------------------------------------------------- config


def test_enabled_defaults_to_false_and_refuses_a_non_boolean(library):
    assert N.enabled(library.root) is False
    config(library, "[library]\nnotes = true\n")
    assert N.enabled(library.root) is True
    config(library, '[library]\nnotes = "yes"\n')
    with pytest.raises(N.NotesError, match="library.notes must be true or false"):
        N.enabled(library.root)


def test_limit_bytes_takes_kb_mb_and_zero_and_refuses_the_rest(library):
    assert N.limit_bytes(library.root) == 5 * 1024 * 1024
    for value, expected in [('"512KB"', 512 * 1024), ('"2mb"', 2 * 1024 * 1024)]:
        config(library, f"[library]\nnotes_limit = {value}\n")
        assert N.limit_bytes(library.root) == expected
    for value in ('"0"', "0"):
        config(library, f"[library]\nnotes_limit = {value}\n")
        assert N.limit_bytes(library.root) == 0
    # only the documented forms: no bare byte count, no fraction, no bool
    for value in ("true", '"100"', "100", '"0.5MB"', '"five"', '"1GB"'):
        config(library, f"[library]\nnotes_limit = {value}\n")
        with pytest.raises(N.NotesError, match="notes_limit must be a size"):
            N.limit_bytes(library.root)


# ----------------------------------------------------------- recording


def test_record_stores_the_last_turn_with_its_context(library, tmp_path):
    on(library)
    path = transcript(
        tmp_path,
        [
            ("earlier question", [HELPER], "earlier answer, no citation"),
            ("What are the packet fields?", [HELPER, "ls"], ANSWER),
        ],
    )
    line = N.record(library.root, path)
    notes = N.load(library.root / N.NOTES_NAME)
    assert len(notes) == 1
    assert line == f"noted {notes[0].id}: What are the packet fields?"
    assert notes[0].question == "What are the packet fields?"
    assert notes[0].context == "earlier question"
    assert notes[0].answer == ANSWER.strip()
    assert notes[0].cites == ("DSP0236 1.3.3 | 8.1 Overview | PDF page 1",)
    assert ISO.match(notes[0].time)


def test_record_stores_nothing_without_a_helper_call_or_a_citation(library, tmp_path):
    on(library)
    no_helper = transcript(tmp_path, [("q", ["ls"], ANSWER)], "a.jsonl")
    assert N.record(library.root, no_helper).startswith("nothing to note: the turn ran")
    no_cite = transcript(tmp_path, [("q", [HELPER], "plain answer")], "b.jsonl")
    assert N.record(library.root, no_cite) == (
        "nothing to note: the answer carries no Citation"
    )
    assert not (library.root / N.NOTES_NAME).exists()


def test_record_command_reads_the_hook_json_and_never_fails(
    library, tmp_path, capsys, catalog_file, monkeypatch
):
    on(library)
    cjk = "PLDM 的 SetNumericSensorEnable 命令有哪些 completion code？"
    answer = "封包欄位如下。\n\n" + CITE + "\n"
    path = transcript(tmp_path, [(cjk, [HELPER], answer)])
    hook = json.dumps(
        {"transcript_path": str(path), "last_assistant_message": answer},
        ensure_ascii=False,  # as Node writes it
    )
    # A piped stdin on Windows is cp950 with surrogateescape: the hook's
    # UTF-8 JSON must be read as bytes or CJK becomes lone surrogates.
    io = __import__("io")
    stdin = io.TextIOWrapper(
        io.BytesIO(hook.encode("utf-8")), encoding="cp950", errors="surrogateescape"
    )
    monkeypatch.setattr("sys.stdin", stdin)
    code, out = run(capsys, "notes", "record", catalog_file=catalog_file)
    assert code == 0 and out.startswith("noted ")
    notes = N.load(library.root / N.NOTES_NAME)
    assert notes[0].question == cjk and notes[0].answer == answer.strip()
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("not json"))
    code, out = run(capsys, "notes", "record", catalog_file=catalog_file)
    assert code == 0 and "no transcript_path" in out
    code, out = run(
        capsys,
        "notes",
        "record",
        "--transcript",
        str(tmp_path / "gone.jsonl"),
        catalog_file=catalog_file,
    )
    assert code == 0 and out.startswith("note: notes: ")


def test_record_command_exits_before_the_transcript_when_off(
    library, tmp_path, capsys, catalog_file
):
    code, out = run(
        capsys,
        "notes",
        "record",
        "--transcript",
        str(tmp_path / "never-read.jsonl"),
        catalog_file=catalog_file,
    )
    assert (code, out) == (0, "notes are off\n")


# ------------------------------------------------------------- serving


def test_find_lists_the_notes_and_prints_a_matching_one_whole(
    held, library, capsys, catalog_file
):
    on(library)
    older = note("What is in the MCTP packet?", time="2026-09-01T00:00:00+00:00")
    newer = note(
        "Which fields does an MCTP packet header carry?",
        time="2026-09-02T00:00:00+00:00",
    )
    write_notes(library, older, newer)
    code, out = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "notes DSP0236 1.3.3: 2"
    assert lines[1] == (
        f"{newer.id} 2026-09-02 | Which fields does an MCTP packet header carry? "
        "| DSP0236 1.3.3 p.1"
    )
    assert lines[2].startswith(f"{older.id} 2026-09-01 | ")
    assert lines[3] == (
        f"note: answer from a Note of 2026-09-02 ({newer.id}); ask to re-read to verify"
    )
    assert lines[4] == "The packet fields are as follows."
    assert lines[6] == CITE
    assert lines[7] == f"end of note {newer.id}"
    assert lines[8].startswith("DSP0236 p.")  # the hits follow
    assert "end of note" not in "\n".join(lines[8:])


def test_section_prints_titles_but_not_a_note_the_query_does_not_match(
    held, library, capsys, catalog_file
):
    on(library)
    made = note("What is in the MCTP packet?")
    write_notes(library, made)
    code, out = run(capsys, "section", "DSP0236", "8.1", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[0] == "notes DSP0236 1.3.3: 1"
    assert out.splitlines()[1].startswith(f"{made.id} 2026-09-08 | ")
    assert "answer from a Note" not in out
    assert "8.1 Overview" in out


def test_a_note_citing_another_version_is_superseded_and_never_whole(
    held, library, capsys, catalog_file
):
    on(library)
    old = note(
        "packet",
        answer="cite: mctp | DSP0236 1.2.0 | 8.1 Overview | PDF page 1 | l | u | p",
    )
    write_notes(library, old)
    code, out = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[1] == (
        f"{old.id} 2026-09-08 superseded | packet | DSP0236 1.2.0 p.1"
    )
    assert "answer from a Note" not in out


def test_a_note_citing_a_document_not_held_is_superseded(
    held, library, capsys, catalog_file
):
    on(library)
    two = note(
        "packet",
        answer=ANSWER
        + "cite: spdm | DSP0274 1.4.1 | 3 Scope | PDF page 18 | l | u | p\n",
    )
    write_notes(library, two)
    code, out = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    assert code == 0 and " superseded | packet | " in out.splitlines()[1]


def test_a_partial_note_is_listed_but_never_whole(held, library, capsys, catalog_file):
    on(library)
    made = note("packet", answer="p1\n\n" + "x" * (N.MAX_ANSWER + 1) + "\n" + CITE)
    assert made.partial
    write_notes(library, made)
    code, out = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    assert code == 0 and out.splitlines()[0] == "notes DSP0236 1.3.3: 1"
    assert "answer from a Note" not in out


def test_without_a_note_for_the_document_the_output_is_unchanged(
    held, library, capsys, catalog_file
):
    code, plain = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    on(library)
    write_notes(library, note("q", answer="cite: x | DSP9999 1.0 | s | PDF page 1 | l"))
    code, out = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    assert (code, out) == (0, plain)


def test_notes_off_leaves_every_output_byte_for_byte(
    held, library, capsys, catalog_file
):
    write_notes(library, note("packet"))
    code, plain = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    assert code == 0 and "notes DSP0236" not in plain and "Note" not in plain
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0 and "notes:" not in out
    for argv in (["recall", "abcd1234"], ["notes", "list"]):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 2
        assert out == (
            "notes are off: set [library] notes = true in "
            f"{library.root / 'config.toml'}\n"
        )


def test_a_bad_switch_is_one_note_line_and_a_zero_exit(
    held, library, capsys, catalog_file
):
    config(library, "[library]\nnotes = 1\n")
    code, out = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[-1] == (
        f"note: notes: {library.root / 'config.toml'}: library.notes must be true "
        "or false"
    )


def test_the_size_reminder_leads_find_and_status(held, library, capsys, catalog_file):
    on(library, 'notes_limit = "1KB"\n')
    write_notes(library, note("q", answer="y" * 2000 + "\n" + CITE))
    code, out = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[0] == (
        "note: notes.jsonl holds 1 Notes (2 KB), over notes_limit; run notes prune"
    )
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[0] == (
        "note: notes.jsonl holds 1 Notes (2 KB), over notes_limit; run notes prune"
    )
    assert out.splitlines()[1].startswith("library: ") and "notes: 1 (2 KB)" in out
    on(library, 'notes_limit = "0"\n')
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert "over notes_limit" not in out and "notes: 1 (2 KB)" in out


def test_status_reports_notes_of_an_empty_library_too(library, capsys, catalog_file):
    on(library, 'notes_limit = "1KB"\n')
    write_notes(library, note("q", answer="y" * 2000 + "\n" + CITE))
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0
    lines = out.splitlines()
    assert lines[0].startswith("note: notes.jsonl holds 1 Notes")
    assert lines[1].startswith("library: ") and lines[2] == "(empty)"
    assert lines[-1] == "notes: 1 (2 KB)"


def test_recall_and_notes_refuse_a_bad_config_like_offline_does(
    held, library, capsys, catalog_file
):
    config(library, '[library]\nnotes = "yes"\n')
    for argv in (["recall", "abcd1234"], ["notes", "list"], ["notes", "prune"]):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert (code, out) == (
            2,
            f"{library.root / 'config.toml'}: library.notes must be true or false\n",
        )
    config(library, "[library\nnotes = true\n")  # does not parse
    code, out = run(capsys, "notes", "list", catalog_file=catalog_file)
    assert code == 2 and out.startswith(str(library.root / "config.toml"))
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0 and out.splitlines()[0].startswith("note: notes: ")


def test_record_takes_a_prompt_starting_with_a_bracket_and_skips_injected_ones(
    library, tmp_path
):
    on(library)
    pasted = "<Error code=0x05> what does this mean in DSP0236?"
    lines = [
        event("user", "first question", promptId="p1"),
        event("assistant", [{"type": "text", "text": "first answer, no helper"}]),
        event("user", pasted, promptId="p2"),
        event("user", "<command-name>/compact</command-name>", isMeta=True),
        event("user", "<local-command-stdout>done</local-command-stdout>"),
        event("assistant", [{"type": "tool_use", "input": {"command": HELPER}}]),
        event("user", [{"type": "tool_result", "content": "..."}]),
        event("assistant", [{"type": "text", "text": ANSWER}]),
    ]
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    turn = N.read_turn(path)
    assert turn.question == pasted and turn.context == "first question"
    assert turn.helper_calls == 1 and turn.answer == ANSWER
    assert N.record(library.root, path).startswith("noted ")
    assert N.load(library.root / N.NOTES_NAME)[0].question == pasted


# ------------------------------------------------------- recall, notes


def test_recall_prints_a_note_whole_and_a_superseded_one_as_a_pointer(
    held, library, capsys, catalog_file
):
    on(library)
    current = note("packet")
    old = note(
        "old packet",
        answer="cite: mctp | DSP0236 1.2.0 | 8.1 Overview | PDF page 1 | l | u | p",
    )
    write_notes(library, current, old)
    code, out = run(capsys, "recall", current.id, catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[1] == (
        f"note: answer from a Note of 2026-09-08 ({current.id}); ask to re-read "
        "to verify"
    )
    assert out.splitlines()[-1] == f"end of note {current.id}"
    code, out = run(capsys, "recall", old.id, catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[1] == (
        "note: this Note cites DSP0236 1.2.0, the Library answers from 1.3.3; "
        "read the pages again"
    )
    gone = note("gone", answer="cite: x | DSP0999 1.0 | 1 A | PDF page 1 | l | u | p")
    write_notes(library, current, old, gone)
    code, out = run(capsys, "recall", gone.id, catalog_file=catalog_file)
    assert out.splitlines()[1] == (
        "note: this Note cites DSP0999 1.0, which the Library no longer holds; "
        "read the pages again"
    )
    code, out = run(capsys, "recall", "00000000", catalog_file=catalog_file)
    assert (code, out) == (2, "no Note 00000000; notes list shows the ids\n")


def test_notes_list_forget_and_prune(held, library, capsys, catalog_file):
    on(library)
    current = note("packet", time="2026-09-02T00:00:00+00:00")
    old = note(
        "old packet",
        answer="cite: mctp | DSP0236 1.2.0 | 8.1 Overview | PDF page 1 | l | u | p",
        time="2026-09-01T00:00:00+00:00",
    )
    ancient = note("ancient", time="2020-01-01T00:00:00+00:00")
    write_notes(library, current, old, ancient)
    code, out = run(capsys, "notes", "list", catalog_file=catalog_file)
    assert code == 0
    assert [ln.split(" | ")[1] for ln in out.splitlines()] == [
        "packet",
        "old packet",
        "ancient",
    ]
    assert " superseded | old packet | " in out
    code, out = run(capsys, "notes", "list", "DSP9999", catalog_file=catalog_file)
    assert (code, out) == (0, "no Notes\n")
    code, out = run(capsys, "notes", "prune", catalog_file=catalog_file)
    assert code == 0 and out.startswith(f"pruned {old.id} ")
    code, out = run(capsys, "notes", "prune", catalog_file=catalog_file)
    assert (code, out) == (0, "nothing to prune\n")
    code, out = run(capsys, "notes", "prune", "--days", "30", catalog_file=catalog_file)
    assert code == 0 and out.startswith(f"pruned {ancient.id} ")
    code, out = run(capsys, "notes", "forget", current.id, catalog_file=catalog_file)
    assert (code, out) == (0, f"forgot {current.id}\n")
    code, out = run(capsys, "notes", "forget", current.id, catalog_file=catalog_file)
    assert (code, out) == (2, f"no Note {current.id}\n")
    assert N.load(library.root / N.NOTES_NAME) == []
    write_notes(library, current, ancient)
    code, out = run(capsys, "notes", "prune", "--all", catalog_file=catalog_file)
    assert code == 0 and out.count("pruned ") == 2


# ------------------------------------------------------------- add-on


def test_buffered_output_is_printed_before_an_error(
    held, library, capsys, catalog_file, monkeypatch
):
    on(library)

    def boom(args):
        print("half done")
        raise LibraryError("gone")

    monkeypatch.setitem(cli_mod.COMMANDS, "find", boom)
    code, out = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    assert (code, out) == (2, "half done\nlibrary: gone\n")


def test_a_failure_inside_the_module_is_one_note_line(
    held, library, capsys, catalog_file, monkeypatch
):
    on(library)
    write_notes(library, note("packet"))
    monkeypatch.setattr(N, "serve", lambda *a: 1 / 0)
    code, out = run(capsys, "find", "DSP0236", "packet", catalog_file=catalog_file)
    assert code == 0 and out.splitlines()[-1] == "note: notes: division by zero"
    assert out.splitlines()[0].startswith("DSP0236 p.")


def test_other_commands_print_straight(library, capsys, catalog_file):
    on(library)
    code, out = run(capsys, "library", catalog_file=catalog_file)
    assert code == 0 and out == f"{library.root}\n"


def test_notes_is_imported_only_by_cli_in_the_package():
    """The add-on stays one module behind ``cli.main``: no other package
    module imports it. Test files may (this one and the review tests)."""
    importers = set()
    for path in ROOT.glob("bmc_toolkit/**/*.py"):
        text = path.read_text("utf-8")
        if re.search(r"from bmc_toolkit\.spec import notes\b", text) or re.search(
            r"bmc_toolkit\.spec\.notes\b", text
        ):
            importers.add(path.relative_to(ROOT).as_posix())
    assert importers == {"bmc_toolkit/spec/cli.py"}


def test_hooks_json_registers_the_stop_hook():
    data = json.loads((ROOT / "hooks" / "hooks.json").read_text("utf-8"))
    commands = [h["command"] for group in data["hooks"]["Stop"] for h in group["hooks"]]
    assert len(commands) == 1
    assert 'bmcspec.py" notes record' in commands[0]
    assert "${CLAUDE_PLUGIN_ROOT}" in commands[0]

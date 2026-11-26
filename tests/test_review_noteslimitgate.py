"""Reviewer acceptance tests for T91 AC-1 and AC-2: ``recall`` and the
managing ``notes`` actions refuse a ``notes_limit`` that is not a size with
exit 2, ``notes record`` goes on storing, and a valid size or the switch
turned off behave as before. Everything goes through ``cli.main`` on a
Library that holds no document; the notes module is never imported."""

import json

import pytest

from bmc_toolkit.spec.cli import main

CITE = (
    "cite: mctp | DSP0236 1.3.3 | 8.1 Overview | PDF page 1 | lines 1-2 | "
    "https://example.test/DSP0236_1.3.3.pdf | /lib"
)
ANSWER = "The packet fields are as follows.\n\n" + CITE
NOTE_ID = "aaaa0001"
HELPER = 'python "/plugin/skills/bmc-spec/scripts/bmcspec.py" find DSP0236 packet'
PREFIX = "note: notes: "

MANAGING = (
    ["recall", NOTE_ID],
    ["notes", "list"],
    ["notes", "list", "DSP0236"],
    ["notes", "forget", NOTE_ID],
    ["notes", "prune"],
    ["notes", "prune", "--days", "1"],
    ["notes", "prune", "--all"],
)
# the forms the documentation refuses: a word, a bare number (string or
# integer), a boolean, a fraction, an unknown unit, nothing
NOT_A_SIZE = ('"five"', '"100"', "100", "true", '"0.5MB"', '"1GB"', '""')
# the documented sizes, and no key at all (the default)
A_SIZE = ('"0"', "0", '"512KB"', '"5MB"', '"2kb"', None)


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def config(library, *, notes="true", limit=None):
    library.root.mkdir(parents=True, exist_ok=True)
    text = f"[library]\nnotes = {notes}\n"
    if limit is not None:
        text += f"notes_limit = {limit}\n"
    (library.root / "config.toml").write_text(text, encoding="utf-8")


def a_note(id=NOTE_ID, question="What is in the MCTP packet?"):
    """One Note in the documented on-disk form."""
    return {
        "id": id,
        "question": question,
        "context": "",
        "answer": ANSWER,
        "partial": False,
        "cites": ["DSP0236 1.3.3 | 8.1 Overview | PDF page 1"],
        "documents": [["DSP0236", "1.3.3"]],
        "time": "2026-09-08T01:02:03+00:00",
    }


def write_notes(library, *notes):
    library.root.mkdir(parents=True, exist_ok=True)
    path = library.root / "notes.jsonl"
    path.write_text(
        "".join(json.dumps(n, ensure_ascii=False) + "\n" for n in notes),
        encoding="utf-8",
    )
    return path


def stored_ids(path):
    return [json.loads(ln)["id"] for ln in path.read_text("utf-8").splitlines() if ln]


def the_message(capsys, catalog_file):
    """The notes_limit message as ``status`` prints it, without the
    ``note: notes: `` lead a serving command puts before it."""
    code, out = run(capsys, "status", catalog_file=catalog_file)
    first = out.splitlines()[0]
    assert code == 0 and first.startswith(PREFIX), out
    assert "notes_limit" in first, first
    return first[len(PREFIX) :]


def event(kind, content):
    return json.dumps({"type": kind, "message": {"content": content}})


def transcript(path, question):
    """One turn in the shape Claude Code writes: the prompt, a helper call
    with its result, the final text carrying a Citation."""
    call = [{"type": "tool_use", "name": "Bash", "input": {"command": HELPER}}]
    lines = [
        event("user", question),
        event("assistant", call),
        event("user", [{"type": "tool_result", "content": "..."}]),
        event("assistant", [{"type": "text", "text": ANSWER}]),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- AC-1


@pytest.mark.parametrize("value", NOT_A_SIZE)
def test_recall_and_notes_print_the_notes_limit_message_and_exit_2(
    library, capsys, catalog_file, value
):
    path = write_notes(library, a_note())
    before = path.read_bytes()
    config(library, limit=value)
    message = the_message(capsys, catalog_file)
    for argv in MANAGING:
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        # the message alone: no title line, no Note text, nothing pruned
        assert (code, out) == (2, message + "\n"), (value, argv)
        assert path.read_bytes() == before, (value, argv)
    assert not list(library.root.glob("*.part"))

    # AC-2: with the switch off the same bad value changes nothing; the
    # commands answer as they do when notes_limit is not set at all
    config(library, notes="false")
    plain = [run(capsys, *argv, catalog_file=catalog_file) for argv in MANAGING]
    config(library, notes="false", limit=value)
    for argv, expected in zip(MANAGING, plain, strict=True):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert (code, out) == expected, (value, argv)
        assert code == 2 and out != message + "\n", (value, argv)
    assert path.read_bytes() == before


def test_notes_record_still_stores_under_a_notes_limit_that_is_not_a_size(
    library, tmp_path, capsys, catalog_file
):
    path = write_notes(library, a_note())
    config(library, limit='"five"')
    message = the_message(capsys, catalog_file)
    code, out = run(capsys, "notes", "list", catalog_file=catalog_file)
    assert (code, out) == (2, message + "\n")

    turn = transcript(tmp_path / "t.jsonl", "Which fields does the packet carry?")
    code, out = run(
        capsys, "notes", "record", "--transcript", str(turn), catalog_file=catalog_file
    )
    assert code == 0 and out.startswith("noted "), out
    ids = stored_ids(path)
    assert len(ids) == 2 and ids[0] == NOTE_ID
    assert out.startswith(f"noted {ids[1]}: ")

    # the managing commands stay refused until the value is a size
    code, out = run(capsys, "notes", "list", catalog_file=catalog_file)
    assert (code, out) == (2, message + "\n")
    config(library, limit='"5MB"')
    code, out = run(capsys, "notes", "list", catalog_file=catalog_file)
    assert code == 0
    assert sorted(ln.split(" ", 1)[0] for ln in out.splitlines()) == sorted(ids)


# ---------------------------------------------------------------- AC-2


@pytest.mark.parametrize("value", A_SIZE)
def test_recall_and_notes_work_as_before_when_the_limit_is_a_size(
    library, capsys, catalog_file, value
):
    path = write_notes(library, a_note())
    # refused while it is not a size ...
    config(library, limit='"five"')
    message = the_message(capsys, catalog_file)
    code, out = run(capsys, "recall", NOTE_ID, catalog_file=catalog_file)
    assert (code, out) == (2, message + "\n")
    # ... and served once it is one (or is left to the default)
    config(library, limit=value)
    code, out = run(capsys, "recall", NOTE_ID, catalog_file=catalog_file)
    lines = out.splitlines()
    assert code == 0, out
    assert lines[0].startswith(f"{NOTE_ID} ") and "What is in the MCTP packet?" in out
    assert "The packet fields are as follows." in lines
    assert lines[-1] == f"end of note {NOTE_ID}"
    assert message not in out

    for argv in (["notes", "list"], ["notes", "list", "DSP0236"]):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 0 and len(out.splitlines()) == 1, (value, argv, out)
        assert out.startswith(f"{NOTE_ID} "), (value, argv, out)
    code, out = run(capsys, "notes", "list", "DSP0240", catalog_file=catalog_file)
    assert (code, out) == (0, "no Notes\n")

    code, out = run(capsys, "notes", "forget", NOTE_ID, catalog_file=catalog_file)
    assert code == 0 and NOTE_ID in out
    assert stored_ids(path) == []
    code, out = run(capsys, "notes", "forget", NOTE_ID, catalog_file=catalog_file)
    assert code == 2 and NOTE_ID in out and message not in out

    write_notes(library, a_note(), a_note("aaaa0002", "What is a message tag?"))
    code, out = run(capsys, "notes", "prune", "--all", catalog_file=catalog_file)
    assert code == 0 and NOTE_ID in out and "aaaa0002" in out
    assert stored_ids(path) == []
    code, out = run(capsys, "notes", "prune", catalog_file=catalog_file)
    assert (code, out) == (0, "nothing to prune\n")

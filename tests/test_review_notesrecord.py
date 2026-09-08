"""Acceptance tests for the Notes feature, recording side: ``notes record``
on a transcript and on the Stop hook JSON, the Note it writes, the hook
registration and the module's single importer. Everything goes through
``cli.main``; the notes module is never imported here."""

import io
import json
import re
from pathlib import Path

import pytest

from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")
HELPER = 'python "/plugin/skills/bmc-spec/scripts/bmcspec.py" find DSP0236 packet'
CITE = (
    "cite: mctp | DSP0236 1.3.3 | 8.1 Overview | PDF page 1 | lines 1-2 | "
    "https://example.test/DSP0236_1.3.3.pdf | /lib"
)
ANSWER = f"The packet fields are as follows.\n\n{CITE}\n"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def on(library, extra=""):
    library.root.mkdir(parents=True, exist_ok=True)
    (library.root / "config.toml").write_text(
        f"[library]\nnotes = true\n{extra}", encoding="utf-8"
    )


def event(kind, content, **extra):
    return json.dumps({"type": kind, "message": {"content": content}, **extra})


def transcript(tmp_path, turns, name="t.jsonl"):
    """A transcript in the shape Claude Code writes: per turn the prompt,
    the tool calls with their results, the final text."""
    lines = []
    for prompt, commands, answer in turns:
        lines.append(event("user", prompt))
        for command in commands:
            lines.append(
                event(
                    "assistant",
                    [{"type": "tool_use", "name": "Bash", "input": {"command": command}}],
                )
            )
            lines.append(event("user", [{"type": "tool_result", "content": "..."}]))
        lines.append(event("assistant", [{"type": "text", "text": answer}]))
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def stored(library):
    path = library.root / "notes.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text("utf-8").splitlines() if ln]


def record(capsys, catalog_file, path):
    return run(capsys, "notes", "record", "--transcript", str(path), catalog_file=catalog_file)


# ---------------------------------------------------------- AC-1, AC-2


def test_record_stores_one_note_of_the_last_turn(library, tmp_path, capsys, catalog_file):
    on(library)
    earlier = "e" * 300
    path = transcript(
        tmp_path,
        [
            ("first question", [HELPER], "first answer, no citation"),
            (earlier, [HELPER], ANSWER),
            ("  What are the packet fields?  ", [HELPER, "ls"], ANSWER),
        ],
    )
    code, out = record(capsys, catalog_file, path)
    assert code == 0 and out.startswith("noted ")
    notes = stored(library)
    assert len(notes) == 1
    note = notes[0]
    assert set(note) == {
        "id",
        "question",
        "context",
        "answer",
        "partial",
        "cites",
        "documents",
        "time",
    }
    assert re.fullmatch(r"[0-9a-f]{8}", note["id"])
    assert note["question"] == "What are the packet fields?"
    assert note["context"] == earlier[:200]
    assert note["answer"] == ANSWER.strip()
    assert note["partial"] is False
    assert note["cites"] == ["DSP0236 1.3.3 | 8.1 Overview | PDF page 1"]
    assert note["documents"] == [["DSP0236", "1.3.3"]]
    assert ISO.match(note["time"])
    assert out == f"noted {note['id']}: What are the packet fields?\n"


def test_the_same_question_about_the_same_versions_replaces_the_note(
    library, tmp_path, capsys, catalog_file
):
    on(library)
    first = transcript(tmp_path, [("packet fields?", [HELPER], ANSWER)], "a.jsonl")
    code, out = record(capsys, catalog_file, first)
    assert code == 0 and out.startswith("noted ")
    first_id = stored(library)[0]["id"]
    again = transcript(
        tmp_path,
        [("packet   fields?", [HELPER], "A better answer.\n" + CITE)],
        "b.jsonl",
    )
    code, out = record(capsys, catalog_file, again)
    assert code == 0 and out.startswith(f"replaced {first_id}")
    notes = stored(library)
    assert [n["id"] for n in notes] == [first_id]
    assert notes[0]["answer"] == "A better answer.\n" + CITE
    # another question is appended, the earlier one stays
    other = transcript(tmp_path, [("tag owner?", [HELPER], ANSWER)], "c.jsonl")
    code, out = record(capsys, catalog_file, other)
    assert code == 0 and out.startswith("noted ")
    assert [n["id"] for n in stored(library)][0] == first_id
    assert len(stored(library)) == 2
    assert stored(library)[1]["id"] != first_id
    # a different set of versions is a different Note, whatever the question
    cite_132 = CITE.replace("1.3.3", "1.3.2")
    another = transcript(tmp_path, [("packet fields?", [HELPER], cite_132)], "d.jsonl")
    code, out = record(capsys, catalog_file, another)
    assert code == 0 and out.startswith("noted ")
    assert len(stored(library)) == 3


def test_every_citation_form_is_found_and_a_mention_without_a_version_is_not(
    library, tmp_path, capsys, catalog_file
):
    on(library)
    answer = "\n".join(
        [
            "Inline (cite: spdm | DSP0274 1.4.1 | 3 Scope | PDF page 18 | lines 82 | u | p).",
            "In prose: DSP0274 1.4.1, §7 SPDM message exchanges, PDF p.27, line 99.",
            "Ranges: DSP0248 1.3.0, Table 30, PDF pages 107-108.",
            "A mention without a version: DSP0275 section 4.6, PDF page 9.",
            CITE,
        ]
    )
    path = transcript(tmp_path, [("what is SPDM for?", [HELPER], answer)])
    code, out = record(capsys, catalog_file, path)
    assert code == 0 and out.startswith("noted ")
    note = stored(library)[0]
    assert note["cites"] == [
        "DSP0274 1.4.1 | 3 Scope | PDF page 18",
        "DSP0274 1.4.1 | 7 SPDM message exchanges | PDF page 27",
        "DSP0248 1.3.0 | Table 30 | PDF pages 107-108",
        "DSP0236 1.3.3 | 8.1 Overview | PDF page 1",
    ]
    assert note["documents"] == [
        ["DSP0236", "1.3.3"],
        ["DSP0248", "1.3.0"],
        ["DSP0274", "1.4.1"],
    ]


def test_a_long_answer_is_stored_partial_with_its_first_paragraph(
    library, tmp_path, capsys, catalog_file
):
    on(library)
    first = "The fields.\n" + CITE
    answer = first + "\n\n" + "x" * 5000 + "\n"
    path = transcript(tmp_path, [("packet fields?", [HELPER], answer)])
    code, out = record(capsys, catalog_file, path)
    assert code == 0 and out.startswith("noted ")
    note = stored(library)[0]
    assert note["partial"] is True
    assert note["answer"] == first
    assert note["cites"] == ["DSP0236 1.3.3 | 8.1 Overview | PDF page 1"]
    # just under the limit is kept whole
    short = "y" * (4096 - len(CITE) - 1) + "\n" + CITE
    path = transcript(tmp_path, [("tag owner?", [HELPER], short)], "s.jsonl")
    code, out = record(capsys, catalog_file, path)
    assert code == 0 and out.startswith("noted ")
    assert stored(library)[1]["partial"] is False


def test_record_stores_nothing_without_a_helper_call_or_a_citation(
    library, tmp_path, capsys, catalog_file
):
    on(library)
    no_helper = transcript(tmp_path, [("q", ["ls", "git status"], ANSWER)], "a.jsonl")
    code, out = record(capsys, catalog_file, no_helper)
    assert code == 0 and out.startswith("nothing to note")
    no_cite = transcript(tmp_path, [("q", [HELPER], "plain answer")], "b.jsonl")
    code, out = record(capsys, catalog_file, no_cite)
    assert code == 0 and out.startswith("nothing to note")
    # a helper call in an earlier turn does not count for the last one
    earlier = transcript(
        tmp_path, [("q1", [HELPER], ANSWER), ("q2", ["ls"], ANSWER)], "c.jsonl"
    )
    code, out = record(capsys, catalog_file, earlier)
    assert code == 0 and out.startswith("nothing to note")
    assert stored(library) == []


def test_record_never_fails_the_hook(library, tmp_path, capsys, catalog_file):
    on(library)
    code, out = record(capsys, catalog_file, tmp_path / "missing.jsonl")
    assert code == 0 and len(out.splitlines()) == 1
    garbage = tmp_path / "garbage.jsonl"
    garbage.write_text("not json\n[1, 2]\n{\"type\": 3}\n", encoding="utf-8")
    code, out = record(capsys, catalog_file, garbage)
    assert code == 0 and len(out.splitlines()) == 1
    assert stored(library) == []


# ---------------------------------------------------------- AC-2, AC-3


def test_record_reads_the_stop_hook_json_from_stdin_as_utf8_bytes(
    library, tmp_path, capsys, catalog_file, monkeypatch
):
    on(library)
    question = "PLDM 的 SetNumericSensorEnable 命令有哪些 completion code？"
    answer = "答案如下。\n\n" + CITE + "\n"
    path = transcript(tmp_path, [(question, [HELPER], "text in the transcript " + CITE)])
    hook = json.dumps(
        {
            "session_id": "s",
            "transcript_path": str(path),
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "last_assistant_message": answer,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    # a piped stdin whose text decoding is not UTF-8: the bytes must be read
    stdin = io.TextIOWrapper(io.BytesIO(hook), encoding="ascii", errors="surrogateescape")
    monkeypatch.setattr("sys.stdin", stdin)
    code, out = run(capsys, "notes", "record", catalog_file=catalog_file)
    assert code == 0 and out.startswith("noted "), out
    note = stored(library)[0]
    assert note["question"] == question
    assert note["answer"] == answer.strip()  # the hook's message wins
    # no transcript_path, or no JSON at all: one line, exit 0
    for text in ("{}", "not json", ""):
        monkeypatch.setattr("sys.stdin", io.StringIO(text))
        code, out = run(capsys, "notes", "record", catalog_file=catalog_file)
        assert code == 0 and len(out.splitlines()) == 1, text
    assert len(stored(library)) == 1


def test_record_with_the_feature_off_exits_before_the_transcript(
    library, tmp_path, capsys, catalog_file, monkeypatch
):
    code, out = record(capsys, catalog_file, tmp_path / "never-read.jsonl")
    assert code == 0 and len(out.splitlines()) == 1 and "off" in out
    hook = json.dumps({"transcript_path": str(tmp_path / "never-read.jsonl")})
    monkeypatch.setattr("sys.stdin", io.StringIO(hook))
    code, out = run(capsys, "notes", "record", catalog_file=catalog_file)
    assert code == 0 and "off" in out
    assert not (library.root / "notes.jsonl").exists()
    # an existing file is left alone
    library.root.mkdir(parents=True, exist_ok=True)
    (library.root / "notes.jsonl").write_text("keep\n", encoding="utf-8")
    code, out = record(capsys, catalog_file, tmp_path / "never-read.jsonl")
    assert code == 0
    assert (library.root / "notes.jsonl").read_text("utf-8") == "keep\n"


def test_hooks_json_runs_notes_record_on_stop_through_the_plugin_root():
    data = json.loads((ROOT / "hooks" / "hooks.json").read_text("utf-8"))
    stop = data["hooks"]["Stop"]
    commands = [h["command"] for group in stop for h in group["hooks"]]
    assert len(commands) == 1
    assert "notes record" in commands[0]
    assert "${CLAUDE_PLUGIN_ROOT}" in commands[0]
    assert "bmcspec.py" in commands[0]


# --------------------------------------------------------------- AC-12


def test_the_notes_module_is_imported_by_cli_alone_inside_the_package():
    importer = re.compile(r"(import\s+|spec\.)notes\b")
    importers = {
        p.relative_to(ROOT).as_posix()
        for p in ROOT.glob("bmc_toolkit/**/*.py")
        if importer.search(p.read_text("utf-8"))
    }
    assert importers == {"bmc_toolkit/spec/cli.py"}
    assert (ROOT / "bmc_toolkit" / "spec" / "notes.py").is_file()

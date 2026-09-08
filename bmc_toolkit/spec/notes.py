"""Notes: answers remembered, served again while their versions hold.

A Note is one line of ``notes.jsonl`` at the Library root: the question of a
turn, the answer the Session gave, the ``cite:`` lines the answer carries,
the document/version pairs those name, and the time. The Stop hook records
one through ``notes record``; ``find`` and ``section`` list the Notes that
cite the document and print one whole when its versions are still the ones
held and the query's identifiers all occur in it; ``recall ID`` prints one
on request; ``notes list / forget / prune`` manage the file.

The module is an add-on: ``cli.main`` hands every command to :func:`run`,
which buffers the output of ``find`` and ``section`` and works on the
printed lines; the commands themselves only leave the loaded Version(s) on
``args.answered``. ``[library] notes`` (default false) turns it on; off,
every output is byte for byte that of a build without the module. Nothing
in here changes an exit code of another command: a failure is one
``note: notes: ...`` line. Standard library only.
"""

import argparse
import contextlib
import hashlib
import io
import json
import re
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from bmc_toolkit.spec.freshness import FreshnessError, _library_section
from bmc_toolkit.spec.library import (
    Library,
    atomic_write_text,
    now_iso,
    resolve_library,
)

NOTES_NAME = "notes.jsonl"
SERVING = frozenset({"find", "section"})
MAX_ANSWER = 4096  # characters; a longer answer is stored partial
MAX_TITLES = 10
MAX_CONTEXT = 200
DEFAULT_LIMIT = "5MB"
EXIT_OK, EXIT_ERROR, EXIT_ACTION = 0, 1, 2

# A Citation as the tool prints it, on its own line or quoted inline, with
# or without the ``cite:`` prefix the Session sometimes drops:
#   cite: spdm | DSP0274 1.4.1 | 3 Scope | PDF page 18 | lines 82-84 | ...
_CITE = re.compile(
    r"(?:cite: )?(?P<family>[A-Za-z][A-Za-z0-9-]*) \| (?P<label>[^|\n]+) \| "
    r"(?P<section>[^|\n]*) \| PDF pages? (?P<first>\d+)(?:-(?P<last>\d+))?"
)
# The prose form the Session also writes:
#   DSP0274 1.4.1, §3 Scope, PDF p.18, lines 82-84
_PROSE = re.compile(
    r"(?P<doc>\b[A-Z][A-Za-z0-9_-]{2,})\s+(?P<ver>\d+(?:\.\d+)+)[,，]\s*"
    r"(?:§\s*)?(?P<section>[^,，()（）\n]{1,80}?)[,，]\s*"
    r"PDF\s*(?:pages?|pp?\.?)\s*(?P<first>\d+)(?:\s*[-–]\s*(?P<last>\d+))?"
)
# The stored form: DOC V | section | PDF pages N-M
_NORM = re.compile(
    r"^(?P<doc>\S+) (?P<ver>.+?) \| (?P<section>.*?) \| "
    r"PDF pages? (?P<first>\d+)(?:-(?P<last>\d+))?$"
)
_PREAMBLE = re.compile(r"^(note: |fetched |extracted )")
_TOKEN = re.compile(r"[A-Za-z0-9_]{3,}")
_SIZE = re.compile(r"^(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>KB|MB)?$", re.IGNORECASE)


class NotesError(Exception):
    """config.toml or notes.jsonl cannot be used; the message says why."""


@dataclass(frozen=True)
class Note:
    id: str
    question: str
    context: str
    answer: str
    partial: bool
    cites: tuple[str, ...]
    documents: tuple[tuple[str, str], ...]  # (document, version), sorted
    time: str  # UTC, ISO 8601

    @property
    def date(self) -> str:
        return self.time[:10]

    def cites_document(self, document: str) -> bool:
        return any(d == document for d, _ in self.documents)

    def pages(self) -> str:
        """``DSP0248 1.3.0 pp.107-108; DSP0240 1.2.0 p.9``: the pages each
        cited version contributed, in Citation order."""
        seen: dict[str, list[str]] = {}
        for line in self.cites:
            m = _NORM.match(line)
            if not m:
                continue
            label = f"{m.group('doc')} {m.group('ver')}"
            pages = m.group("first") + (
                "-" + m.group("last") if m.group("last") else ""
            )
            seen.setdefault(label, [])
            if pages not in seen[label]:
                seen[label].append(pages)
        parts = []
        for label, pages in seen.items():
            prefix = "pp." if len(pages) > 1 or "-" in pages[0] else "p."
            parts.append(f"{label} {prefix}{','.join(pages)}")
        return "; ".join(parts)

    def sections(self) -> list[str]:
        out = []
        for line in self.cites:
            m = _NORM.match(line)
            if m:
                out.append(m.group("section").strip())
        return out

    def words(self) -> set[str]:
        text = " ".join([self.question, *self.sections()])
        return {t.lower() for t in _TOKEN.findall(text)}

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "question": self.question,
                "context": self.context,
                "answer": self.answer,
                "partial": self.partial,
                "cites": list(self.cites),
                "documents": [list(d) for d in self.documents],
                "time": self.time,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, line: str) -> "Note | None":
        """The Note a line holds, or None for a line that is not one (a
        partial last line, another Session's write cut short)."""
        try:
            data = json.loads(line)
            documents = tuple(sorted((str(d), str(v)) for d, v in data["documents"]))
            return cls(
                str(data["id"]),
                str(data["question"]),
                str(data.get("context", "")),
                str(data["answer"]),
                bool(data.get("partial", False)),
                tuple(str(c) for c in data.get("cites", [])),
                documents,
                str(data["time"]),
            )
        except (ValueError, KeyError, TypeError):
            return None


def note_id(question: str, documents: Iterable[tuple[str, str]]) -> str:
    text = " ".join(question.split()) + "\n" + json.dumps(sorted(documents))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def find_cites(text: str) -> list[str]:
    """Every Citation in an answer, in order, in the stored form ``DOC V |
    section | PDF pages N-M``: the ``cite:`` form wherever it stands and
    the prose form; duplicates dropped, a mention without a version is
    not one."""
    found: list[tuple[int, str]] = []
    for m in _CITE.finditer(text):
        document, _, version = " ".join(m.group("label").split()).partition(" ")
        if version:
            found.append((m.start(), _stored(document, version, m)))
    for m in _PROSE.finditer(text):
        found.append((m.start(), _stored(m.group("doc"), m.group("ver"), m)))
    out: list[str] = []
    for _, cite in sorted(found):
        if cite not in out:
            out.append(cite)
    return out


def _stored(document: str, version: str, m: re.Match) -> str:
    section = " ".join(m.group("section").split())
    first, last = m.group("first"), m.group("last")
    pages = f"pages {first}-{last}" if last and last != first else f"page {first}"
    return f"{document} {version} | {section} | PDF {pages}"


def make_note(question: str, context: str, answer: str, time: str) -> Note | None:
    """The Note of a turn, or None when the answer carries no Citation
    (nothing to key the Note to)."""
    cites = find_cites(answer)
    if not cites:
        return None
    documents = set()
    for line in cites:
        m = _NORM.match(line)
        documents.add((m.group("doc"), m.group("ver")))
    docs = tuple(sorted(documents))
    partial = len(answer) > MAX_ANSWER
    if partial:
        answer = answer.strip().split("\n\n", 1)[0][:MAX_ANSWER]
    return Note(
        note_id(question, docs),
        question.strip(),
        context.strip()[:MAX_CONTEXT],
        answer.strip(),
        partial,
        tuple(cites),
        docs,
        time,
    )


# ------------------------------------------------------------ config


def config_path(root: Path) -> Path:
    return root / "config.toml"


def enabled(root: Path) -> bool:
    """``[library] notes`` of config.toml, default false."""
    try:
        value = _library_section(root).get("notes", False)
    except FreshnessError as exc:
        raise NotesError(str(exc)) from exc
    if not isinstance(value, bool):
        raise NotesError(f"{config_path(root)}: library.notes must be true or false")
    return value


def limit_bytes(root: Path) -> int:
    """``[library] notes_limit``, a number with KB or MB (default 5MB);
    0 never reminds."""
    try:
        value = _library_section(root).get("notes_limit", DEFAULT_LIMIT)
    except FreshnessError as exc:
        raise NotesError(str(exc)) from exc
    m = _SIZE.match(str(value).strip()) if isinstance(value, (str, int)) else None
    if m is None or isinstance(value, bool):
        raise NotesError(
            f"{config_path(root)}: library.notes_limit must be a size such as "
            '"5MB", "512KB" or "0"'
        )
    unit = (m.group("unit") or "").upper()
    factor = {"KB": 1024, "MB": 1024 * 1024}.get(unit, 1)
    return int(float(m.group("n")) * factor)


# ------------------------------------------------------------ the file


def notes_path(root: Path) -> Path:
    return root / NOTES_NAME


def load(path: Path) -> list[Note]:
    """Every Note in the file, in file order; lines that are not a Note are
    skipped. No file: no Notes."""
    if not path.is_file():
        return []
    out = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            note = Note.from_json(line.strip())
            if note is not None:
                out.append(note)
    return out


def save(path: Path, notes: Iterable[Note]) -> None:
    """The whole file, written beside the target and renamed into place."""
    atomic_write_text(path, "".join(n.to_json() + "\n" for n in notes))


def upsert(path: Path, note: Note) -> bool:
    """Store one Note: a Note with the same id is replaced (the file is
    rewritten), a new one is appended in one write. True when replaced."""
    notes = load(path)
    if any(n.id == note.id for n in notes):
        save(path, [note if n.id == note.id else n for n in notes])
        return True
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(note.to_json() + "\n")
    return False


def size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _kb(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{max(1, round(size / 1024))} KB"


def reminder(root: Path) -> str | None:
    """The size reminder when notes.jsonl is over ``notes_limit``."""
    path = notes_path(root)
    limit = limit_bytes(root)
    size = size_of(path)
    if limit <= 0 or size <= limit:
        return None
    count = len(load(path))
    return (
        f"note: {NOTES_NAME} holds {count} Notes ({_kb(size)}), over notes_limit; "
        "run notes prune"
    )


def status_lines(root: Path) -> list[str]:
    """What ``status`` adds: the reminder and the count; nothing when off."""
    try:
        if not enabled(root):
            return []
        lines = []
        line = reminder(root)
        if line:
            lines.append(line)
        path = notes_path(root)
        if path.is_file():
            lines.append(f"notes: {len(load(path))} ({_kb(size_of(path))})")
        return lines
    except Exception as exc:  # noqa: BLE001 - status must not fail on this
        return [f"note: notes: {exc}"]


# ------------------------------------------------------------ serving


def held_versions(root: Path) -> set[tuple[str, str]]:
    return {(h.document, h.version) for h in Library(root).holdings()}


def is_current(note: Note, answering: dict[str, str], held: set) -> bool:
    """Every cited version is still the one answered from (the versions
    loaded for this call) or, for a document not loaded, still held."""
    for document, version in note.documents:
        if document in answering:
            if answering[document] != version:
                return False
        elif (document, version) not in held:
            return False
    return True


def title_line(note: Note, current: bool) -> str:
    state = "" if current else " superseded"
    question = " ".join(note.question.split())
    return f"{note.id} {note.date}{state} | {question} | {note.pages()}"


def matches(query: str, note: Note) -> bool:
    """Every identifier token of the query occurs in the Note's question or
    its cited section titles; a query without one matches nothing."""
    tokens = {t.lower() for t in _TOKEN.findall(query)}
    return bool(tokens) and tokens <= note.words()


def block(note: Note, first: str) -> list[str]:
    return [first, *note.answer.splitlines(), f"end of note {note.id}"]


def served_first_line(note: Note) -> str:
    return (
        f"note: answer from a Note of {note.date} ({note.id}); ask to re-read to verify"
    )


def serve(query: str, output: str, answered: list, notes: list[Note], held) -> str:
    """The output of ``find`` or ``section`` with the Notes that cite the
    document listed after the preamble, and one printed whole when current
    and matching; unchanged when no Note cites it."""
    if not answered:
        return output
    main = answered[0]
    answering = {v.document: v.version for v in answered}
    citing = [n for n in notes if n.cites_document(main.document)]
    if not citing:
        return output
    citing.sort(key=lambda n: n.time, reverse=True)
    current = {n.id: is_current(n, answering, held) for n in citing}
    added = [f"notes {main.document} {main.version}: {len(citing)}"]
    added.extend(title_line(n, current[n.id]) for n in citing[:MAX_TITLES])
    for n in citing:
        if current[n.id] and not n.partial and matches(query, n):
            added.extend(block(n, served_first_line(n)))
            break
    lines = output.splitlines()
    out: list[str] = []
    inserted = False
    for line in lines:
        if not inserted and not _PREAMBLE.match(line):
            out.extend(added)
            inserted = True
        out.append(line)
    if not inserted:
        out.extend(added)
    text = "\n".join(out)
    return text + "\n" if output.endswith("\n") or not output else text


# ---------------------------------------------------------- recording


def _prompt_text(content) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [b.get("text", "") for b in content if isinstance(b, dict)]
        texts = [t for t in texts if t]
        return "\n".join(texts) if texts else None
    return None


@dataclass
class Turn:
    question: str = ""
    context: str = ""
    answer: str = ""
    helper_calls: int = 0


def read_turn(transcript: Path) -> Turn:
    """The last turn of a Claude Code transcript: the user's prompt, the
    prompt before it, the assistant's final text, and how many tool calls
    of the turn ran ``bmcspec.py``."""
    prompts: list[str] = []
    turn = Turn()
    texts: list[str] = []
    with open(transcript, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            message = event.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            kind = event.get("type")
            if kind == "user":
                if isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in content
                ):
                    texts = []  # the answer is what comes after the last tool
                    continue
                if event.get("isMeta"):
                    continue
                text = _prompt_text(content)
                if text is None or text.lstrip().startswith("<"):
                    continue
                prompts.append(text)
                turn = Turn(
                    question=text, context=prompts[-2] if len(prompts) > 1 else ""
                )
                texts = []
            elif kind == "assistant" and isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text":
                        texts.append(b.get("text", ""))
                    elif b.get("type") == "tool_use":
                        command = str((b.get("input") or {}).get("command", ""))
                        if "bmcspec.py" in command:
                            turn.helper_calls += 1
    turn.answer = "\n".join(t for t in texts if t)
    return turn


def record(root: Path, transcript: Path, answer: str | None = None) -> str:
    """Store the Note of the transcript's last turn; the line to print."""
    turn = read_turn(transcript)
    if answer:
        turn.answer = answer
    if turn.helper_calls == 0:
        return "nothing to note: the turn ran no bmcspec command"
    if not turn.question:
        return "nothing to note: no prompt in the transcript"
    note = make_note(turn.question, turn.context, turn.answer, now_iso())
    if note is None:
        return "nothing to note: the answer carries no Citation"
    replaced = upsert(notes_path(root), note)
    verb = "replaced" if replaced else "noted"
    return f"{verb} {note.id}: {' '.join(note.question.split())[:60]}"


# ----------------------------------------------------------- commands


def _off_message(root: Path) -> str:
    return f"notes are off: set [library] notes = true in {config_path(root)}"


def cmd_recall(args: argparse.Namespace) -> int:
    root = resolve_library()
    if not enabled(root):
        print(_off_message(root))
        return EXIT_ACTION
    notes = [n for n in load(notes_path(root)) if n.id == args.id]
    if not notes:
        print(f"no Note {args.id}; notes list shows the ids")
        return EXIT_ACTION
    note = notes[0]
    held = held_versions(root)
    if is_current(note, {}, held):
        first = served_first_line(note)
    else:
        cited = ", ".join(f"{d} {v}" for d, v in note.documents if (d, v) not in held)
        first = (
            f"note: this Note cites {cited}, which the Library no longer holds; "
            "read the pages again"
        )
    print(f"{title_line(note, is_current(note, {}, held))}")
    for line in block(note, first):
        print(line)
    return EXIT_OK


def cmd_notes(args: argparse.Namespace) -> int:
    root = resolve_library()
    if args.action == "record":
        return _cmd_record(args, root)
    if not enabled(root):
        print(_off_message(root))
        return EXIT_ACTION
    path = notes_path(root)
    notes = load(path)
    if args.action == "list":
        held = held_versions(root)
        chosen = [
            n for n in notes if not args.document or n.cites_document(args.document)
        ]
        if not chosen:
            print("no Notes")
            return EXIT_OK
        for n in sorted(chosen, key=lambda n: n.time, reverse=True):
            print(title_line(n, is_current(n, {}, held)))
        return EXIT_OK
    if args.action == "forget":
        kept = [n for n in notes if n.id != args.id]
        if len(kept) == len(notes):
            print(f"no Note {args.id}")
            return EXIT_ACTION
        save(path, kept)
        print(f"forgot {args.id}")
        return EXIT_OK
    if args.action == "prune":
        held = held_versions(root)
        cutoff = None
        if args.days is not None:
            cutoff = datetime.now(UTC).timestamp() - args.days * 86400
        gone = []
        for n in notes:
            if args.all or not is_current(n, {}, held):
                gone.append(n)
            elif cutoff is not None and _timestamp(n.time) < cutoff:
                gone.append(n)
        if not gone:
            print("nothing to prune")
            return EXIT_OK
        save(path, [n for n in notes if n not in gone])
        for n in gone:
            print(f"pruned {title_line(n, is_current(n, {}, held))}")
        return EXIT_OK
    print(f"unknown notes action {args.action}")
    return EXIT_ACTION


def _timestamp(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return 0.0


def _read_stdin() -> str:
    """The hook JSON is UTF-8; a piped stdin on Windows is not (cp950 with
    surrogateescape turns CJK into lone surrogates), so read the bytes."""
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is None:
        return sys.stdin.read()
    return buffer.read().decode("utf-8", errors="replace")


def _cmd_record(args: argparse.Namespace, root: Path) -> int:
    """The Stop hook's command: always exits 0, one line says what happened."""
    try:
        if not enabled(root):
            print("notes are off")
            return EXIT_OK
        answer = None
        transcript = args.transcript
        if transcript is None:
            try:
                data = json.loads(_read_stdin() or "{}")
            except ValueError:
                data = {}
            if not isinstance(data, dict) or not data.get("transcript_path"):
                print("nothing to note: no transcript_path on stdin")
                return EXIT_OK
            transcript = Path(str(data["transcript_path"]))
            answer = data.get("last_assistant_message") or None
        print(record(root, Path(transcript), answer))
    except Exception as exc:  # noqa: BLE001 - a hook must never block the Session
        print(f"note: notes: {exc}")
    return EXIT_OK


COMMANDS: dict[str, Callable[..., int]] = {"recall": cmd_recall, "notes": cmd_notes}


def add_parsers(sub) -> None:
    p = sub.add_parser("recall", help="print a remembered answer (a Note) whole")
    p.add_argument("id", help="the Note id shown by find, section or notes list")
    p = sub.add_parser("notes", help="list, forget, prune or record Notes")
    actions = p.add_subparsers(dest="action", required=True)
    a = actions.add_parser("list", help="the Notes, latest first")
    a.add_argument("document", nargs="?", help="only Notes citing this document")
    a = actions.add_parser("forget", help="remove one Note")
    a.add_argument("id")
    a = actions.add_parser("prune", help="remove superseded Notes")
    a.add_argument("--days", type=int, help="also Notes older than this many days")
    a.add_argument("--all", action="store_true", help="remove every Note")
    a = actions.add_parser("record", help="store the last turn of a transcript")
    a.add_argument(
        "--transcript",
        type=Path,
        help="a transcript file (default: the Stop hook JSON on stdin)",
    )


# ---------------------------------------------------------- entry point


def after(args, output: str, code: int) -> str:
    """What to print for a buffered ``find`` / ``section``: its output plus
    the Notes; nothing added on a non-zero exit code or with the feature
    off. Never raises."""
    try:
        if code != 0:
            return output
        root = resolve_library()
        if not enabled(root):
            return output
        answered = getattr(args, "answered", None) or []
        query = args.pattern if args.command == "find" else args.query
        text = serve(
            query, output, answered, load(notes_path(root)), held_versions(root)
        )
        line = reminder(root)
        return f"{line}\n{text}" if line else text
    except Exception as exc:  # noqa: BLE001 - the note must not fail the answer
        return output + f"note: notes: {exc}\n"


def run(command: Callable[..., int], args) -> int:
    """Run a command; ``find`` and ``section`` print through :func:`after`,
    the others straight. Whatever a command printed before raising is
    printed before the exception goes on to ``main``."""
    if args.command not in SERVING:
        return command(args)
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            code = command(args)
    except BaseException:
        sys.stdout.write(buffer.getvalue())
        raise
    sys.stdout.write(after(args, buffer.getvalue(), code))
    return code

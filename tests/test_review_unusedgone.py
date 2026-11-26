"""Reviewer acceptance tests for T91 AC-4: ``extract.remove_derived`` and
``lock.wait_while_locked``, which no command calls, are removed, and what
stood beside them is still there. White-box by the criterion's nature: it
is about two names in two modules."""

from pathlib import Path

from bmc_toolkit.spec import extract, lock

ROOT = Path(__file__).resolve().parents[1]
GONE = ("remove_derived", "wait_while_locked")
SHIPPED = ("bmc_toolkit", "skills", "hooks")


def test_the_two_functions_are_gone_and_their_neighbours_stay():
    assert not hasattr(extract, "remove_derived")
    assert not hasattr(lock, "wait_while_locked")
    # what the commands do call, next to each of them
    for name in ("write_result", "is_current"):
        assert callable(getattr(extract, name)), name
    for name in ("Lock", "live_holder", "read_holder", "remove_stale_lock"):
        assert callable(getattr(lock, name)), name


def test_no_shipped_python_file_names_either_function():
    named = []
    for folder in SHIPPED:
        for path in sorted((ROOT / folder).rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="replace")
            named += [
                f"{path.relative_to(ROOT).as_posix()}: {name}"
                for name in GONE
                if name in text
            ]
    assert named == []

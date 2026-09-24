"""Review acceptance tests for the prune wording change: a stale lock its
holder released between the listing and the removal is reported as ``gone``
(AC-1, AC-3, AC-4), a lock taken over meanwhile stays ``kept`` (AC-2), and
the two unused removers are out of the package (AC-5).
"""

import json
import os
import time
from pathlib import Path

import pytest

from bmc_toolkit.spec import bundle as bundle_mod
from bmc_toolkit.spec import lock as lock_mod
from bmc_toolkit.spec import registry as registry_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import PDF_BYTES, ok

ROOT = Path(__file__).resolve().parents[1]
URL = "https://example.test/DSP0236_1.3.3.pdf"
STARTED = "2026-09-05T00:00:00+00:00"
STALE_AGE = lock_mod.STALE_SECONDS + 1
SUMMARY = "prune: 0 superseded tree(s), 0 leftover(s), 0 stale lock(s)"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def backdate(path, seconds):
    old = time.time() - seconds
    os.utime(path, (old, old))


def stale_lock(directory, command):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".lock"
    holder = {"pid": 4242, "host": "elsewhere", "command": command, "started": STARTED}
    path.write_text(json.dumps(holder), encoding="utf-8")
    backdate(path, STALE_AGE)
    return path


@pytest.fixture
def stored(catalog_file, library, scripted, capsys):
    """DSP0236 1.3.3 fetched (a fake PDF), not extracted."""
    scripted.responses[URL] = ok(PDF_BYTES)
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


def race_after_listing(monkeypatch, race):
    """Run ``race`` right after prune lists the locks, on every prune run."""
    from bmc_toolkit.spec import cli

    real = cli.lock_mod.locks_under

    def listing_then_race(root):
        holders = real(root)
        race()
        return holders

    monkeypatch.setattr(cli.lock_mod, "locks_under", listing_then_race)


# ------------------------------------------------------------ AC-1, AC-4


def test_released_stale_lock_is_gone_not_kept_and_exit_is_0(
    stored, catalog_file, monkeypatch, capsys
):
    # AC-1: the lock listed as stale is released by its holder before prune
    # removes it: a gone line, no kept line, a ", 1 gone" tail. AC-4: exit 0.
    path = stale_lock(stored, "extract DSP0236 1.3.3")
    race_after_listing(monkeypatch, lambda: path.unlink(missing_ok=True))
    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert f"gone {path} (released meanwhile)" in lines
    assert not any(ln.startswith("kept") for ln in lines)
    assert not any(ln.startswith(("removed", "failed")) for ln in lines)
    assert " kept" not in lines[-1]
    assert lines[-1] == f"{SUMMARY}, 1 gone"
    assert not path.exists()
    assert not (stored / ".lock.takeover").exists()
    assert (stored / "original.pdf").is_file()


def test_released_lock_gone_after_the_re_read_inside_the_gate(
    stored, catalog_file, monkeypatch, capsys
):
    # AC-1: remove_stale_lock also answers "gone" when the lock vanishes
    # between its re-read inside the gate and the unlink; prune reports that
    # the same way, with the gate cleaned up and exit 0.
    path = stale_lock(stored, "extract DSP0236 1.3.3")
    gate = stored / ".lock.takeover"
    real_read = lock_mod.read_holder

    def read_then_release(lock_path):
        holder = real_read(lock_path)
        if lock_path == path and holder is not None and gate.is_file():
            path.unlink()
        return holder

    monkeypatch.setattr(lock_mod, "read_holder", read_then_release)
    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    monkeypatch.undo()
    assert code == 0, out
    lines = out.splitlines()
    assert f"gone {path} (released meanwhile)" in lines
    assert not any(ln.startswith(("kept", "removed", "failed")) for ln in lines)
    assert lines[-1] == f"{SUMMARY}, 1 gone"
    assert not path.exists() and not gate.exists()


def test_dry_run_still_lists_a_released_lock_and_yes_reports_it_gone(
    stored, catalog_file, monkeypatch, capsys
):
    # AC-4: without --yes nothing is removed, so a lock released after the
    # listing is still a "would remove" line and the summary has no gone
    # tail; the same race under --yes gives the gone line.
    path = stale_lock(stored, "extract DSP0236 1.3.3")
    race_after_listing(monkeypatch, lambda: path.unlink(missing_ok=True))
    code, out = run(capsys, "prune", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert any(ln.startswith(f"would remove {path} (stale lock, ") for ln in lines)
    assert not any(ln.startswith(("gone", "kept", "removed")) for ln in lines)
    assert lines[-1] == (
        "prune: 0 superseded tree(s), 0 leftover(s), 1 stale lock(s)"
        " (dry run; --yes removes them)"
    )
    # the dry run touched nothing but the race did: put the lock back
    stale_lock(stored, "extract DSP0236 1.3.3")
    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert f"gone {path} (released meanwhile)" in lines
    assert lines[-1] == f"{SUMMARY}, 1 gone"


# ------------------------------------------------------------ AC-2, AC-3


def test_taken_over_lock_is_kept_and_released_lock_is_gone_counted_apart(
    stored, catalog_file, library, monkeypatch, capsys
):
    # AC-2: a lock refreshed meanwhile (a take-over) is still "kept" and
    # counted in ", N kept". AC-3: a released one is counted in ", N gone"
    # in the same summary, after the kept count.
    taken = stale_lock(stored, "extract DSP0236 1.3.3")
    released = stale_lock(
        library.specs / "mctp" / "DSP0236" / "1.3.2", "extract DSP0236 1.3.2"
    )

    def race():
        os.utime(taken, None)  # another Session takes it over
        released.unlink(missing_ok=True)  # its holder finished and released it

    race_after_listing(monkeypatch, race)
    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert f"kept {taken} (taken over meanwhile)" in lines
    assert f"gone {released} (released meanwhile)" in lines
    assert not any(ln.startswith(("removed", "failed")) for ln in lines)
    assert lines[-1] == f"{SUMMARY}, 1 kept, 1 gone"
    assert taken.exists()
    assert not released.exists()


def test_take_over_in_progress_is_kept_while_a_released_lock_is_gone(
    stored, catalog_file, library, monkeypatch, capsys
):
    # AC-2: a fresh take-over gate beside a stale lock keeps it, with its own
    # wording; AC-3: a released lock in the same run is gone, and the two
    # counts are separate.
    busy = stale_lock(stored, "extract DSP0236 1.3.3")
    gate = stored / ".lock.takeover"
    gate.write_bytes(b"")
    released = stale_lock(
        library.specs / "mctp" / "DSP0236" / "1.3.2", "extract DSP0236 1.3.2"
    )
    race_after_listing(monkeypatch, lambda: released.unlink(missing_ok=True))
    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert f"kept {busy} (take-over in progress)" in lines
    assert f"gone {released} (released meanwhile)" in lines
    assert lines[-1] == f"{SUMMARY}, 1 kept, 1 gone"
    assert busy.exists() and gate.exists()


def test_two_released_locks_are_counted_as_2_gone(
    stored, catalog_file, library, monkeypatch, capsys
):
    # AC-1 / AC-3: the gone count is a count, not a flag, and a run with no
    # kept lock has no kept tail before it.
    first = stale_lock(stored, "extract DSP0236 1.3.3")
    second = stale_lock(
        library.specs / "mctp" / "DSP0236" / "1.3.2", "extract DSP0236 1.3.2"
    )

    def race():
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)

    race_after_listing(monkeypatch, race)
    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert f"gone {first} (released meanwhile)" in lines
    assert f"gone {second} (released meanwhile)" in lines
    assert lines[-1] == f"{SUMMARY}, 2 gone"


# ------------------------------------------------------------------ AC-5


def test_the_unused_removers_are_gone_from_the_package():
    assert not hasattr(bundle_mod, "remove_schemas")
    assert "remove_schemas" not in bundle_mod.__all__
    assert not hasattr(registry_mod, "remove_registries")
    assert "remove_registries" not in registry_mod.__all__


def test_nothing_in_the_repository_refers_to_the_removers():
    me = Path(__file__).resolve()
    hits = []
    for top in ("bmc_toolkit", "skills", "hooks", "tests", "docs"):
        for path in (ROOT / top).rglob("*"):
            if not path.is_file() or path.resolve() == me:
                continue
            if path.suffix not in {".py", ".md", ".toml", ".txt"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "remove_schemas" in text or "remove_registries" in text:
                hits.append(path.relative_to(ROOT).as_posix())
    for name in ("README.md", "CONVENTIONS.md", "CLAUDE.md"):
        path = ROOT / name
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            if "remove_schemas" in text or "remove_registries" in text:
                hits.append(name)
    assert hits == []

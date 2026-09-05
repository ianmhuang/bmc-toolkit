"""Review acceptance tests for M13's maintenance side: status listing locks
(AC-9), prune removing stale locks and abandoned temp files (AC-10), the
SessionStart hook installing through a temp directory (AC-11), and the docs
and version (AC-14).
"""

import importlib.util
import json
import os
import re
import time
from pathlib import Path

import pytest

from bmc_toolkit.spec import lock as lock_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import PDF_BYTES, ok

ROOT = Path(__file__).resolve().parents[1]
URL = "https://example.test/DSP0236_1.3.3.pdf"
STARTED = "2026-09-05T00:00:00+00:00"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def backdate(path, seconds):
    old = time.time() - seconds
    os.utime(path, (old, old))


def other_lock(directory, command, pid=4242, age=0):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".lock"
    path.write_text(
        json.dumps(
            {"pid": pid, "host": "elsewhere", "command": command, "started": STARTED}
        ),
        encoding="utf-8",
    )
    if age:
        backdate(path, age)
    return path


def holder_text(command, pid=4242):
    return f"pid {pid} on host elsewhere ({command}, since {STARTED})"


@pytest.fixture
def stored(catalog_file, library, scripted, capsys):
    scripted.responses[URL] = ok(PDF_BYTES)
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "DSP0236" / "1.3.3"


# ----------------------------------------------------------------- AC-9


def test_status_without_locks_prints_no_lock_line(stored, catalog_file, capsys):
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0
    assert not any(ln.startswith("lock:") for ln in out.splitlines())


def test_status_lists_every_lock_after_the_holdings(
    stored, catalog_file, library, capsys
):
    live = other_lock(stored, "extract DSP0236 1.3.3")
    stale = other_lock(
        library.root / "code" / "bmcweb",
        "clone bmcweb main",
        pid=7,
        age=lock_mod.STALE_SECONDS + 1,
    )
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    holdings = [i for i, ln in enumerate(lines) if ln.startswith("mctp\tDSP0236")]
    locks = [i for i, ln in enumerate(lines) if ln.startswith("lock:")]
    assert len(holdings) == 1 and len(locks) == 2
    assert max(holdings) < min(locks)  # after the holdings
    assert lines[locks[0]] == (
        f"lock: {live} held by {holder_text('extract DSP0236 1.3.3')}, live"
    )
    assert lines[locks[1]] == (
        f"lock: {stale} held by {holder_text('clone bmcweb main', pid=7)}, stale"
    )
    # a status run never touches a lock, live or stale
    assert live.is_file() and stale.is_file()


def test_status_lists_a_lock_even_when_the_library_is_empty(
    catalog_file, library, capsys
):
    path = other_lock(library.root / "code" / "pldm", "clone pldm main")
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0
    lines = out.splitlines()
    assert lines[1] == "(empty)"
    assert lines[2] == f"lock: {path} held by {holder_text('clone pldm main')}, live"


# ---------------------------------------------------------------- AC-10


def test_prune_with_nothing_says_so_including_locks(stored, catalog_file, capsys):
    code, out = run(capsys, "prune", catalog_file=catalog_file)
    assert code == 0
    assert (
        out.strip()
        == "nothing to prune: no superseded Code Tree, no leftover, no stale lock"
    )


def test_prune_lists_then_removes_stale_locks_and_old_leftovers(
    stored, catalog_file, library, capsys
):
    stale_age = lock_mod.STALE_SECONDS + 1
    old_part = stored / "extract.json.999-deadbeef.part"
    old_part.write_bytes(b"x")
    backdate(old_part, stale_age)
    young_part = stored / "meta.json.999-cafe.part"
    young_part.write_bytes(b"x")  # a lock-free render may be writing one
    render_part = stored / "renders" / "page-3.png.1-2.part"
    render_part.parent.mkdir()
    render_part.write_bytes(b"x")
    backdate(render_part, stale_age)
    root_part = library.root / "freshness.json.5-6.part"
    root_part.write_bytes(b"x")
    backdate(root_part, stale_age)
    stale_lock = other_lock(
        library.root / "code" / "bmcweb", "clone bmcweb main", pid=7, age=stale_age
    )
    loose_tmp = library.root / "code" / "bmcweb" / ".tmp-2-ef01"
    loose_tmp.mkdir()
    live_dir = library.root / "code" / "pldm"
    live_lock = other_lock(live_dir, "clone pldm main")
    busy_tmp = live_dir / ".tmp-1-abcd"
    busy_tmp.mkdir()

    code, out = run(capsys, "prune", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    for path in (old_part, render_part, root_part, loose_tmp):
        assert f"would remove {path} (leftover)" in lines, path
    assert (
        f"would remove {stale_lock} (stale lock, "
        f"{holder_text('clone bmcweb main', pid=7)})"
    ) in lines
    for kept in (young_part, busy_tmp, live_lock):
        assert not any(str(kept) in ln for ln in lines), kept
    assert lines[-1] == (
        "prune: 0 superseded tree(s), 4 leftover(s), 1 stale lock(s) "
        "(dry run; --yes removes them)"
    )
    assert old_part.exists() and stale_lock.exists()  # a dry run

    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert f"removed {stale_lock} (stale lock, " in "\n".join(lines)
    assert lines[-1] == "prune: 0 superseded tree(s), 4 leftover(s), 1 stale lock(s)"
    for gone in (old_part, render_part, root_part, stale_lock, loose_tmp):
        assert not gone.exists(), gone
    for kept in (young_part, busy_tmp, live_lock, stored / "original.pdf"):
        assert kept.exists(), kept


def test_prune_finds_old_part_files_and_gate_files_under_code(
    stored, catalog_file, library, capsys
):
    # Round 2 (F3): AC-10 says "under specs/ and code/". A .bmc-tree.json
    # write that died between the temp file and the rename leaves a .part
    # inside a Code Tree; an abandoned take-over gate is a leftover too.
    # Both are skipped when the repository's lock is live.
    stale_age = lock_mod.STALE_SECONDS + 1
    tree = library.root / "code" / "bmcweb" / "0123456789abcdef"
    tree.mkdir(parents=True)
    old_part = tree / ".bmc-tree.json.7-abcd.part"
    old_part.write_bytes(b"x")
    backdate(old_part, stale_age)
    young_part = tree / ".bmc-tree.json.8-ef01.part"
    young_part.write_bytes(b"x")
    old_gate = library.root / "code" / "bmcweb" / ".lock.takeover"
    old_gate.write_bytes(b"")
    backdate(old_gate, stale_age)
    spec_gate = stored / ".lock.takeover"
    spec_gate.write_bytes(b"")
    backdate(spec_gate, stale_age)
    busy_repo = library.root / "code" / "pldm"
    busy_tree = busy_repo / "fedcba9876543210"
    busy_tree.mkdir(parents=True)
    busy_part = busy_tree / ".bmc-tree.json.9-beef.part"
    busy_part.write_bytes(b"x")
    backdate(busy_part, stale_age)
    busy_lock = other_lock(busy_repo, "clone pldm main")

    code, out = run(capsys, "prune", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    for path in (old_part, old_gate, spec_gate):
        assert f"would remove {path} (leftover)" in lines, path
    for kept in (young_part, busy_part, busy_lock):
        assert not any(str(kept) in ln for ln in lines), kept
    assert lines[-1] == (
        "prune: 0 superseded tree(s), 3 leftover(s), 0 stale lock(s) "
        "(dry run; --yes removes them)"
    )
    assert old_part.exists() and old_gate.exists()  # a dry run

    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[-1] == (
        "prune: 0 superseded tree(s), 3 leftover(s), 0 stale lock(s)"
    )
    for gone in (old_part, old_gate, spec_gate):
        assert not gone.exists(), gone
    for kept in (young_part, busy_part, busy_lock, tree, busy_tree):
        assert kept.exists(), kept


def test_prune_leaves_a_live_locked_version_alone(stored, catalog_file, capsys):
    part = stored / "extract.txt.1-2.part"
    part.write_bytes(b"x")
    backdate(part, lock_mod.STALE_SECONDS + 1)
    live = other_lock(stored, "extract DSP0236 1.3.3")
    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    assert (
        out.strip()
        == "nothing to prune: no superseded Code Tree, no leftover, no stale lock"
    )
    assert part.exists() and live.exists()


def test_prune_yes_keeps_a_stale_lock_taken_over_while_it_was_working(
    stored, catalog_file, library, capsys, monkeypatch
):
    # Round 3 (F1 of round 2): prune lists stale locks first and removes
    # trees and leftovers before it gets to them. A Session that took the
    # lock over in between holds a fresh lock under the same path; AC-10
    # says a live lock is never touched, so prune must re-read it and keep
    # it. The take-over is simulated while prune removes a leftover.
    from bmc_toolkit.spec import cli

    stale_age = lock_mod.STALE_SECONDS + 1
    stale = other_lock(stored, "extract DSP0236 1.3.3", age=stale_age)
    leftover = library.root / "freshness.json.5-6.part"
    leftover.write_bytes(b"x")
    backdate(leftover, stale_age)
    real_prune_path = cli._prune_path

    def prune_path_then_takeover(path, line, really):
        result = real_prune_path(path, line, really)
        if path == leftover:
            # another Session takes the stale lock over right now
            stale.write_text(
                json.dumps(
                    {
                        "pid": 9999,
                        "host": "elsewhere",
                        "command": "extract DSP0236 1.3.3",
                        "started": "2026-09-05T02:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
        return result

    monkeypatch.setattr(cli, "_prune_path", prune_path_then_takeover)
    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert f"removed {leftover} (leftover)" in lines
    assert f"kept {stale} (taken over meanwhile)" in lines
    assert not any(ln.startswith(f"removed {stale}") for ln in lines)
    assert stale.is_file()
    assert json.loads(stale.read_text(encoding="utf-8"))["pid"] == 9999
    assert not leftover.exists()


def test_prune_dry_run_lists_a_stale_lock_without_touching_it(
    stored, catalog_file, capsys
):
    stale = other_lock(stored, "extract DSP0236 1.3.3", age=lock_mod.STALE_SECONDS + 1)
    before = stale.stat().st_mtime
    code, out = run(capsys, "prune", catalog_file=catalog_file)
    assert code == 0, out
    assert (
        f"would remove {stale} (stale lock, {holder_text('extract DSP0236 1.3.3')})"
    ) in out.splitlines()
    assert stale.is_file() and stale.stat().st_mtime == before


# ---------------------------------------------------------------- AC-11


@pytest.fixture
def hook(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "review_install_deps", ROOT / "hooks" / "install_deps.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = tmp_path / "plugin-data"
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
    return module, data


def fake_pip(monkeypatch, module, *, during=None, returncode=0):
    """Replace pip: writes one file into --target, runs ``during`` (what a
    concurrent Session does meanwhile), returns ``returncode``."""
    targets = []

    def run(cmd, **_kwargs):
        target = Path(cmd[cmd.index("--target") + 1])
        targets.append(target)
        if returncode == 0:
            (target / "pkg.py").write_text("x = 1\n", encoding="utf-8")
        if during is not None:
            during(target)

        class Result:
            pass

        result = Result()
        result.returncode = returncode
        result.stderr = "boom" if returncode else ""
        return result

    monkeypatch.setattr(module.subprocess, "run", run)
    return targets


def digest_of(module):
    return module.hashlib.sha256(module.REQUIREMENTS.read_bytes()).hexdigest()


def test_hook_installs_into_a_pid_token_temp_and_renames_it(hook, monkeypatch, capsys):
    module, data = hook
    targets = fake_pip(monkeypatch, module)
    assert module.main() == 0
    assert len(targets) == 1
    tmp = targets[0]
    assert tmp.parent == data
    assert re.fullmatch(rf"site-packages\.tmp-{os.getpid()}-[0-9a-f]+", tmp.name), tmp
    final = data / "site-packages"
    assert (final / "pkg.py").is_file()
    marker = (final / module.MARKER_NAME).read_text(encoding="utf-8")
    assert marker.strip() == digest_of(module)
    assert [p.name for p in data.iterdir()] == ["site-packages"]
    assert capsys.readouterr().out.strip().endswith(f"installed into {final}")
    # second start: the marker matches, nothing runs
    assert module.main() == 0 and targets == [tmp]
    assert capsys.readouterr().out == ""


def test_hook_keeps_the_install_that_landed_first(hook, monkeypatch, capsys):
    module, data = hook
    final = data / "site-packages"
    digest = digest_of(module)

    def other_session_lands(_tmp):
        final.mkdir(parents=True)
        (final / "theirs.py").write_text("y = 2\n", encoding="utf-8")
        (final / module.MARKER_NAME).write_text(digest + "\n", encoding="utf-8")

    fake_pip(monkeypatch, module, during=other_session_lands)
    assert module.main() == 0
    assert (final / "theirs.py").is_file()
    assert not (final / "pkg.py").exists()
    assert [p.name for p in data.iterdir()] == ["site-packages"]  # ours discarded


def test_hook_failed_install_leaves_no_temp_directory(hook, monkeypatch, capsys):
    module, data = hook
    fake_pip(monkeypatch, module, returncode=1)
    assert module.main() == 0  # never blocks the session
    assert not (data / "site-packages").exists()
    assert [p.name for p in data.iterdir()] == []
    out = capsys.readouterr().out
    assert "dependency install failed" in out and "boom" in out


def test_hook_without_plugin_data_is_unchanged(hook, monkeypatch, capsys):
    module, data = hook
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA")
    called = fake_pip(monkeypatch, module)
    assert module.main() == 0
    assert called == []
    assert not data.exists()
    assert "CLAUDE_PLUGIN_DATA not set" in capsys.readouterr().out


# ---------------------------------------------------------------- AC-14


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_skill_md_documents_exit_3_wait_and_the_retry_rule():
    text = read("skills/bmc-spec/SKILL.md")
    assert "3 busy" in text
    assert "--wait SECONDS" in text
    assert "--wait 300" in text
    assert "Exit 3" in text and "busy:" in text
    assert "stop" in text.lower() and "half-written" in text
    assert "lock:" in text  # the status row
    assert "stale `.lock`" in text  # the prune row


def test_commands_md_has_the_sharing_section_and_the_disk_names():
    text = read("docs/COMMANDS.md")
    assert "## Sessions sharing a Library" in text
    assert "`--wait SECONDS`" in text
    assert "3 busy" in text
    assert "busy: <path> is held by pid P on host H" in text
    assert "note: took over a stale lock" in text
    assert "`.lock`" in text
    assert "<name>.<pid>-<token>.part" in text
    assert ".tmp-<pid>-<token>" in text
    assert "`status` lists every lock" in text
    assert "stale `.lock`" in text  # prune
    # Round 3 (F3 of round 2): the take-over gate is part of the layout
    assert "`.lock.takeover`" in text
    assert "taken over meanwhile" in text  # what prune --yes prints for a kept lock


def test_library_md_names_the_lock_and_the_temp_pattern():
    text = read("docs/LIBRARY.md")
    assert "`.lock`" in text
    assert "<name>.<pid>-<token>.part" in text
    assert "code/<repo>/.lock" in text
    assert "`.lock.takeover`" in text  # round 3 (F3 of round 2)


def test_readme_pointer_legend_and_catalog_link():
    text = read("README.md")
    assert "Exit codes: 0 done, 1 error, 2 you need to act" not in text
    assert "Exit codes" in text and "docs/COMMANDS.md" in text
    assert "Solid arrows are commands and Library access" in text
    assert "[docs/CATALOG.md](docs/CATALOG.md)" in text


def test_workflow_concurrency_comment():
    text = read(".github/workflows/test.yml")
    assert "never cancelled" in text
    assert "at most one pending" in text
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in text


def test_version_stays_1_0_0():
    from bmc_toolkit import __version__

    assert __version__ == "1.0.0"
    assert 'version = "1.0.0"' in read("pyproject.toml")
    plugin = json.loads(read(".claude-plugin/plugin.json"))
    assert plugin["version"] == "1.0.0"

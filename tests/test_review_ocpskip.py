"""Reviewer acceptance tests for the catalog workflow after the
``refresh --skip-source`` change (AC-3, AC-4, AC-5).

The workflow file is read as text (no YAML dependency). The ``refresh (dry
run)`` shell block is executed for real, as GitHub runs it (``bash
--noprofile --norc -eo pipefail``), with a stand-in ``python`` first on
PATH that records its arguments, prints canned ``refresh`` output and exits
with a chosen code. The block tests skip when no bash on PATH can read
this checkout (a WSL launcher first on a Windows PATH cannot).
"""

import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "catalog.yml"
LAUNCHER = "skills/bmc-spec/scripts/bmcspec.py"


# ------------------------------------------------------------ text helpers


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _steps(text: str) -> list[list[str]]:
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "steps:")
    steps: list[list[str]] = []
    for ln in lines[start + 1 :]:
        if ln.startswith("      - "):
            steps.append([ln])
        elif steps and ln.strip():
            steps[-1].append(ln)
    return steps


def _step_named(name: str) -> list[str]:
    for step in _steps(_text()):
        if f"- name: {name}" in step[0]:
            return step
    raise AssertionError(f"no step named {name!r}")


def _literal_block(step: list[str], key: str) -> str:
    start = next(i for i, ln in enumerate(step) if ln.strip() == f"{key}: |")
    indent = len(step[start]) - len(step[start].lstrip())
    body = []
    for ln in step[start + 1 :]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent:
            break
        body.append(ln)
    return textwrap.dedent("\n".join(body)) + "\n"


def _refresh_run() -> str:
    return _literal_block(_step_named("refresh (dry run)"), "run")


def _issue_script() -> str:
    return _literal_block(_step_named("open or comment on the catalog issue"), "script")


def _command_lines(script: str) -> list[str]:
    """The non-comment lines of the shell block that invoke the launcher."""
    return [
        ln.strip()
        for ln in script.splitlines()
        if LAUNCHER in ln and not ln.strip().startswith("#")
    ]


# ------------------------------------------------- the shell block, for real


def _bash() -> str:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on PATH")
    try:
        probe = subprocess.run(
            [bash, "-c", 'test -f "$1" && printf ok', "_", str(WORKFLOW)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("bash on PATH does not run")
    if probe.returncode != 0 or probe.stdout != "ok":
        pytest.skip("bash on PATH cannot read this checkout")
    return bash


def _run_step(tmp_path: Path, output: str, exit_code: int = 0):
    """Returns (process, summary text, outputs dict, launcher argv)."""
    bash = _bash()
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    canned = tmp_path / "canned.txt"
    canned.write_text(output, encoding="utf-8", newline="\n")
    args_file = tmp_path / "args.txt"
    shim = shim_dir / "python"
    shim.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$FAKE_ARGS"\n'
        'cat "$FAKE_OUTPUT"\nexit "$FAKE_EXIT"\n',
        encoding="utf-8",
        newline="\n",
    )
    shim.chmod(0o755)
    script = tmp_path / "step.sh"
    script.write_text(_refresh_run(), encoding="utf-8", newline="\n")
    summary = tmp_path / "summary.md"
    outputs = tmp_path / "outputs.txt"
    summary.touch()
    outputs.touch()
    env = dict(os.environ)
    env["PATH"] = str(shim_dir) + os.pathsep + env.get("PATH", "")
    env["GITHUB_STEP_SUMMARY"] = str(summary)
    env["GITHUB_OUTPUT"] = str(outputs)
    env["FAKE_OUTPUT"] = str(canned)
    env["FAKE_ARGS"] = str(args_file)
    env["FAKE_EXIT"] = str(exit_code)
    cwd = tmp_path / "work"
    cwd.mkdir()
    proc = subprocess.run(
        [bash, "--noprofile", "--norc", "-eo", "pipefail", str(script)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    argv = None
    if args_file.exists():
        argv = args_file.read_text(encoding="utf-8").split()
    outs = dict(
        ln.split("=", 1)
        for ln in outputs.read_text(encoding="utf-8").splitlines()
        if "=" in ln
    )
    return proc, summary.read_text(encoding="utf-8"), outs, argv


TAIL = " (dry run; --write adds them)"
PROPOSALS = (
    "confirm DSP0270 1.2.0-WIP (2025-11-03) (work in progress)\n"
    "changed DSP0266 1.20.2 (2024-08-19) url moved\n"
    "add NVME-MI 2.2 (2026-07-31) https://example.test/nvme-mi-2.2.pdf\n"
    "summary: add 1, confirm 1, changed 1, unreachable 0" + TAIL + "\n"
)
NOTHING = "summary: add 0, confirm 0, changed 0, unreachable 0" + TAIL + "\n"
BROKEN_CATALOG = "cannot read catalog: bad TOML on line 3\n"
PARTIAL_THEN_ERROR = (
    "add DSP0236 1.4.0 (2026-02-02) https://example.test/DSP0236_1.4.0.pdf\n"
    "cannot write DSP0236: permission denied\n"
)


# ----------------------------------------------------------------- AC-3


def test_ac3_the_runner_executes_refresh_skip_source_ocp_and_nothing_else(
    tmp_path,
):
    proc, _summary, _outs, argv = _run_step(tmp_path, PROPOSALS)
    assert proc.returncode == 0, proc.stderr
    assert argv == [LAUNCHER, "refresh", "--skip-source", "ocp"], argv


def test_ac3_one_launcher_line_skipping_ocp_only_and_never_writing():
    lines = _command_lines(_refresh_run())
    assert len(lines) == 1, lines
    line = lines[0]
    assert re.search(r"\brefresh\b", line)
    assert line.count("--skip-source") == 1
    assert re.search(r"--skip-source(=| +)ocp\b", line), line
    for other in ("dmtf", "nvme"):
        assert not re.search(rf"--skip-source(=| +){other}\b", line), line
    assert "--write" not in line
    # the launcher is run nowhere else in the workflow
    assert _text().count(LAUNCHER) == 1


def test_ac3_issue_step_gating_and_counting_are_as_pr25_left_them(tmp_path):
    issue = _step_named("open or comment on the catalog issue")
    cond = next(ln.split("if:", 1)[1].strip() for ln in issue if "if:" in ln)
    assert cond == "steps.refresh.outputs.proposals != '0'", cond
    run = _refresh_run()
    assert 'echo "proposals=$proposals" >> "$GITHUB_OUTPUT"' in run
    proc, _summary, outs, _argv = _run_step(tmp_path, PROPOSALS)
    assert proc.returncode == 0, proc.stderr
    assert outs.get("proposals") == "3", outs  # add 1 + confirm 1 + changed 1
    second = tmp_path / "second"
    second.mkdir()
    proc, _summary, outs, _argv = _run_step(
        second,
        "unreachable DSP0236: HTTP 503\n"
        "summary: add 0, confirm 0, changed 0, unreachable 1" + TAIL + "\n",
    )
    assert proc.returncode == 0, proc.stderr
    assert outs.get("proposals") == "0", outs


# ----------------------------------------------------------------- AC-4


def test_ac4_failing_refresh_still_puts_its_output_in_the_summary(tmp_path):
    proc, summary, outs, argv = _run_step(tmp_path, BROKEN_CATALOG, exit_code=1)
    assert argv is not None  # the launcher was run
    assert proc.returncode == 1, (proc.returncode, proc.stderr)
    assert "## refresh" in summary
    assert BROKEN_CATALOG.strip() in summary
    # the counting line copes with a missing summary: line
    assert outs.get("proposals") == "0", outs


@pytest.mark.parametrize("code", [1, 2, 3])
def test_ac4_the_step_fails_with_the_refresh_exit_code(tmp_path, code):
    proc, summary, _outs, _argv = _run_step(tmp_path, "some failure\n", exit_code=code)
    assert proc.returncode == code, (proc.returncode, proc.stderr)
    assert "some failure" in summary


def test_ac4_partial_output_before_a_failure_reaches_the_summary(tmp_path):
    proc, summary, outs, _argv = _run_step(tmp_path, PARTIAL_THEN_ERROR, exit_code=1)
    assert proc.returncode == 1, (proc.returncode, proc.stderr)
    for line in PARTIAL_THEN_ERROR.splitlines():
        assert line in summary, line
    assert outs.get("proposals") == "0", outs


def test_ac4_a_successful_run_still_exits_zero_with_its_summary(tmp_path):
    proc, summary, outs, _argv = _run_step(tmp_path, NOTHING)
    assert proc.returncode == 0, proc.stderr
    assert NOTHING.strip() in summary
    assert outs.get("proposals") == "0", outs


def test_ac4_empty_output_from_a_crashed_refresh_neither_hangs_nor_hides_it(
    tmp_path,
):
    proc, summary, outs, _argv = _run_step(tmp_path, "", exit_code=1)
    assert proc.returncode == 1, (proc.returncode, proc.stderr)
    assert "## refresh" in summary
    assert outs.get("proposals") == "0", outs


# ----------------------------------------------------------------- AC-5


def test_ac5_step_summary_wraps_the_output_in_a_four_backtick_fence(tmp_path):
    proc, summary, _outs, _argv = _run_step(tmp_path, PROPOSALS)
    assert proc.returncode == 0, proc.stderr
    lines = summary.splitlines()
    assert lines[0] == "## refresh", lines
    assert lines[1] == "````", lines
    assert lines[-1] == "````", lines
    assert lines[2:-1] == PROPOSALS.splitlines(), lines
    assert not any(ln == "```" for ln in lines), lines


def test_ac5_issue_body_wraps_the_output_in_a_four_backtick_fence():
    script = _issue_script()
    body_start = script.index("const body = [")
    body_end = script.index("].join(", body_start)
    body = script[body_start:body_end]
    fences = re.findall(r'^\s*"(`+)",\s*$', body, re.M)
    assert fences == ["````", "````"], fences
    read = body.index('readFileSync("refresh.txt"')
    assert body.index('"````",') < read < body.rindex('"````",')

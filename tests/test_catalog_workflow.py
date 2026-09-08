"""Catalog refresh workflow: a monthly GitHub Action runs ``refresh``
without writing and opens an issue when the publishers list something the
Source Catalog lacks (PR #25, AC-1 to AC-7), then leaves OCP out, keeps the
summary on failure and fences with four backticks (refresh --skip-source
change, AC-3 to AC-7). No YAML parser is a dependency, so the checks read
the text; the shell block runs through a bash that can read the checkout."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "catalog.yml"
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
CATALOG_DOC = ROOT / "docs" / "CATALOG.md"
README = ROOT / "README.md"

REFRESH = "python skills/bmc-spec/scripts/bmcspec.py refresh --skip-source ocp"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _block(text: str, key: str) -> str:
    """The lines of a top-level ``key:`` block, up to the next top-level key."""
    lines = text.splitlines()
    start = lines.index(f"{key}:")
    body = [lines[start]]
    for ln in lines[start + 1 :]:
        if re.match(r"\S", ln):
            break
        body.append(ln)
    return "\n".join(body)


def _step(text: str, name: str) -> str:
    """The lines of the step ``- name: <name>`` up to the next step."""
    lines = text.splitlines()
    start = lines.index(f"      - name: {name}")
    body = [lines[start]]
    for ln in lines[start + 1 :]:
        if ln.startswith("      - "):
            break
        body.append(ln)
    return "\n".join(body)


def _issue_step() -> str:
    return _step(_text(), "open or comment on the catalog issue")


def _refresh_step() -> str:
    return _step(_text(), "refresh (dry run)")


def _run_block(step: str) -> str:
    """The shell script under the step's ``run: |``."""
    lines = step.splitlines()
    start = lines.index("        run: |") + 1
    body = []
    for ln in lines[start:]:
        if ln.strip() and not ln.startswith("          "):
            break
        body.append(ln[10:])
    return "\n".join(body) + "\n"


def _bash() -> str:
    """A bash that can read this checkout, or skip: on a Windows PATH the
    first ``bash`` may be the WSL launcher, which sees no Windows path."""
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


def _run_refresh_block(tmp_path: Path, output: str, exit_code: int = 0):
    """Run the refresh step's script as GitHub does (``shell: bash`` is
    ``bash --noprofile --norc -eo pipefail``) with a stand-in ``python``
    that prints ``output`` and exits ``exit_code``. Returns the completed
    process, the step summary text and the ``proposals`` output."""
    bash = _bash()
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    canned = tmp_path / "canned.txt"
    canned.write_text(output, encoding="utf-8", newline="\n")
    shim = shim_dir / "python"
    shim.write_text(
        '#!/bin/sh\ncat "$FAKE_OUTPUT"\nexit "$FAKE_EXIT"\n',
        encoding="utf-8",
        newline="\n",
    )
    shim.chmod(0o755)
    script = tmp_path / "step.sh"
    script.write_text(_run_block(_refresh_step()), encoding="utf-8", newline="\n")
    summary = tmp_path / "summary.md"
    outputs = tmp_path / "outputs.txt"
    summary.touch()
    outputs.touch()
    env = dict(os.environ)
    env["PATH"] = str(shim_dir) + os.pathsep + env.get("PATH", "")
    env["GITHUB_STEP_SUMMARY"] = str(summary)
    env["GITHUB_OUTPUT"] = str(outputs)
    env["FAKE_OUTPUT"] = str(canned)
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
    outs = dict(
        ln.split("=", 1)
        for ln in outputs.read_text(encoding="utf-8").splitlines()
        if "=" in ln
    )
    return proc, summary.read_text(encoding="utf-8"), outs.get("proposals")


TAIL = " (dry run; --write adds them)"


# ---------------------------------------------------------------- AC-1


def test_ac1_triggers_monthly_and_on_dispatch_only():
    on = _block(_text(), "on")
    assert "schedule:" in on and "workflow_dispatch:" in on
    crons = re.findall(r"- cron: \"([^\"]+)\"", on)
    assert len(crons) == 1, crons
    minute, hour, day, month, weekday = crons[0].split()
    assert day.isdigit() and month == "*" and weekday == "*", crons[0]
    assert minute.isdigit() and hour.isdigit()
    assert "push" not in on and "pull_request" not in on


def test_ac1_test_workflow_still_has_no_schedule():
    on = _block(TEST_WORKFLOW.read_text(encoding="utf-8"), "on")
    assert "schedule" not in on and "workflow_dispatch" not in on


# ---------------------------------------------------------------- AC-2


def test_ac2_runs_upstream_only_on_ubuntu_python_313_with_requirements():
    jobs = _block(_text(), "jobs")
    assert "if: github.repository == 'ianmhuang/bmc-toolkit'" in jobs
    assert jobs.count("runs-on:") == 1 and "runs-on: ubuntu-latest" in jobs
    assert 'python-version: "3.13"' in jobs
    assert "python -m pip install -r requirements.txt" in jobs
    assert "requirements-dev.txt" not in jobs


# ---------------------------------------------------------------- AC-3


def test_ac3_runs_refresh_dry_skipping_ocp_and_writes_the_step_summary():
    step = _refresh_step()
    assert REFRESH in step
    assert "GITHUB_STEP_SUMMARY" in step
    assert "shell: bash" in step  # pipefail: a failing refresh fails the step


def test_ac3_nothing_is_committed_pushed_or_proposed():
    text = _text()
    for forbidden in ("git push", "git commit", "gh pr", "pulls.create"):
        assert forbidden not in text, forbidden
    # --write is named in the comment and the issue body (the maintainer's
    # job), never on the command line the runner executes.
    assert not re.search(r"bmcspec\.py refresh[^\n]*--write", text)
    assert text.count("bmcspec.py refresh") == 1


# ---------------------------------------------------------------- AC-4


def test_ac4_opens_a_labelled_issue_or_comments_on_the_open_one():
    step = _issue_step()
    assert "actions/github-script@" in step
    assert 'const label = "catalog";' in step
    assert "issues.create(" in step
    assert "`Catalog refresh ${month}`" in step
    assert "labels: [label]" in step
    assert "issues.createComment(" in step
    assert 'state: "open", labels: label' in step
    assert "!issue.pull_request" in step
    assert 'readFileSync("refresh.txt"' in step


def test_ac4_missing_label_is_created():
    step = _issue_step()
    assert "issues.getLabel(" in step and "issues.createLabel(" in step


# ---------------------------------------------------------------- AC-5


def test_ac5_issue_step_runs_only_when_there_are_proposals():
    step = _issue_step()
    assert "if: steps.refresh.outputs.proposals != '0'" in step
    assert 'echo "proposals=$proposals" >> "$GITHUB_OUTPUT"' in _refresh_step()


def _count_line() -> str:
    lines = [ln.strip() for ln in _refresh_step().splitlines()]
    matching = [ln for ln in lines if ln.startswith("proposals=$(")]
    assert len(matching) == 1, matching
    return matching[0]


def test_ac5_count_pattern_names_the_three_kinds_and_not_unreachable():
    line = _count_line()
    assert "(add|confirm|changed) [0-9]+" in line
    assert "unreachable" not in line
    assert "grep '^summary:'" in line


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ("add 0, confirm 0, changed 0, unreachable 0", "0"),
        ("add 0, confirm 0, changed 0, unreachable 7", "0"),
        ("add 0, confirm 1, changed 3, unreachable 0", "4"),
        ("add 2, confirm 0, changed 0, unreachable 1", "2"),
    ],
)
def test_ac5_step_sums_add_confirm_changed(tmp_path, counts, expected):
    output = (
        "unreachable DSP0236: HTTP 503\nchanged DSP0266 1.20.2 (2024-08-19) x\n"
        f"summary: {counts}{TAIL}\n"
    )
    proc, summary, proposals = _run_refresh_block(tmp_path, output)
    assert proc.returncode == 0, proc.stderr
    assert proposals == expected
    assert "unreachable DSP0236: HTTP 503" in summary


# --------------------------------------- summary on failure (skip-source AC-4)


def test_failing_refresh_still_reaches_the_summary_and_fails_the_step(tmp_path):
    output = "cannot read catalog: bad TOML on line 3\n"
    proc, summary, proposals = _run_refresh_block(tmp_path, output, exit_code=1)
    assert proc.returncode == 1, (proc.returncode, proc.stderr)
    assert "cannot read catalog: bad TOML on line 3" in summary
    assert proposals == "0"


def test_refresh_exit_code_is_the_steps_exit_code(tmp_path):
    proc, _summary, _proposals = _run_refresh_block(
        tmp_path, "unknown document 'NOPE'\n", exit_code=2
    )
    assert proc.returncode == 2, (proc.returncode, proc.stderr)


# -------------------------------------------- fences (skip-source AC-5)


def test_summary_and_issue_body_fence_with_four_backticks():
    run = _run_block(_refresh_step())
    assert run.count("echo '````'") == 2
    assert "echo '```'" not in run
    issue = _issue_step()
    assert issue.count('"````",') == 2
    assert '"```",' not in issue


# ---------------------------------------------------------------- AC-6


def test_ac6_permissions_are_contents_read_and_issues_write_only():
    perms = _block(_text(), "permissions")
    entries = [ln.strip() for ln in perms.splitlines()[1:] if ln.strip()]
    assert entries == ["contents: read", "issues: write"], entries
    assert _text().count("permissions:") == 1


# ---------------------------------------------------------------- AC-7


def test_ac7_catalog_doc_describes_the_workflow_and_keeps_writes_manual():
    text = CATALOG_DOC.read_text(encoding="utf-8")
    paragraphs = [p.replace("\n", " ") for p in text.split("\n\n")]
    about = [p for p in paragraphs if "catalog.yml" in p]
    assert len(about) == 1, about
    p = about[0]
    assert "Once a month" in p and "Run workflow" in p
    assert "`refresh --skip-source ocp`" in p and "without `--write`" in p
    assert "whether or not `refresh` succeeded" in p
    assert "HTTP 403" in p and "developer machine" in p
    assert "issue" in p and "`catalog`" in p
    assert "opens nothing" in p
    assert "pull request" in p and "`refresh --write`" in p
    assert "golden-questions.md" in p and "`plugin.json`" in p


def test_ac7_readme_does_not_mention_the_workflow():
    text = README.read_text(encoding="utf-8")
    assert "catalog.yml" not in text
    assert len(text.splitlines()) <= 200

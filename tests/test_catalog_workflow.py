"""Catalog refresh workflow (AC-1 to AC-7): a monthly GitHub Action runs
``refresh`` without writing and opens an issue when the publishers list
something the Source Catalog lacks. No YAML parser is a dependency, so the
checks read the text; the counting line is run through bash where one is
on PATH."""

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

REFRESH = "python skills/bmc-spec/scripts/bmcspec.py refresh"


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


def test_ac3_runs_refresh_dry_and_writes_the_step_summary():
    step = _refresh_step()
    assert REFRESH in step
    assert "--write" not in step
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


TAIL = " (dry run; --write adds them)"


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ("add 0, confirm 0, changed 0, unreachable 0", "0"),
        ("add 0, confirm 0, changed 0, unreachable 7", "0"),
        ("add 0, confirm 1, changed 3, unreachable 0", "4"),
        ("add 2, confirm 0, changed 0, unreachable 1", "2"),
    ],
)
def test_ac5_count_line_sums_add_confirm_changed(tmp_path, counts, expected):
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on PATH")
    (tmp_path / "refresh.txt").write_text(
        "unreachable DSP0236: HTTP 503\nchanged DSP0266 1.20.2 (2024-08-19) x\n"
        f"summary: {counts}{TAIL}\n",
        encoding="utf-8",
    )
    script = _count_line() + '; printf "%s" "$proposals"'
    out = subprocess.run(
        [bash, "-c", script], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert out.stdout == expected, out


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
    assert "without `--write`" in p
    assert "issue" in p and "`catalog`" in p
    assert "opens nothing" in p
    assert "pull request" in p and "`refresh --write`" in p
    assert "golden-questions.md" in p and "`plugin.json`" in p


def test_ac7_readme_does_not_mention_the_workflow():
    text = README.read_text(encoding="utf-8")
    assert "catalog.yml" not in text
    assert len(text.splitlines()) <= 200

"""Reviewer's acceptance tests for the monthly catalog refresh Action
(feature/catalog-refresh-action, AC-1 to AC-6).

The workflow file is read as text (no YAML dependency). The two steps that
carry behaviour are executed for real where the interpreters are on PATH:
the ``refresh (dry run)`` shell block runs under bash with a stand-in
``python`` that prints canned ``refresh`` output, and the github-script body
runs under node against a recording fake of the Octokit ``issues`` API with
the clock frozen. Either test skips when its interpreter is missing.
"""

import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "catalog.yml"
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
README = ROOT / "README.md"

UPSTREAM = "ianmhuang/bmc-toolkit"
LAUNCHER = "skills/bmc-spec/scripts/bmcspec.py"


# ------------------------------------------------------------ text helpers


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _top_block(text: str, key: str) -> list[str]:
    """Lines of the top-level ``key:`` block (the key line excluded)."""
    lines = text.splitlines()
    start = lines.index(f"{key}:")
    body = []
    for ln in lines[start + 1 :]:
        if ln and not ln[0].isspace():
            break
        body.append(ln)
    return body


def _child_keys(block: list[str], indent: int) -> list[str]:
    """Mapping keys at exactly ``indent`` spaces inside ``block``."""
    keys = []
    for ln in block:
        m = re.match(rf"^ {{{indent}}}([A-Za-z_][\w-]*):", ln)
        if m:
            keys.append(m.group(1))
    return keys


def _steps(text: str) -> list[list[str]]:
    """The steps of the single job, each as its list of lines."""
    jobs = _top_block(text, "jobs")
    start = next(i for i, ln in enumerate(jobs) if ln.strip() == "steps:")
    steps: list[list[str]] = []
    for ln in jobs[start + 1 :]:
        if ln.startswith("      - "):
            steps.append([ln])
        elif steps and ln.strip():
            steps[-1].append(ln)
    return steps


def _step_named(text: str, name: str) -> list[str]:
    for step in _steps(text):
        if f"- name: {name}" in step[0]:
            return step
    raise AssertionError(f"no step named {name!r}")


def _literal_block(step: list[str], key: str) -> str:
    """The dedented text of a ``key: |`` literal block inside a step."""
    start = next(i for i, ln in enumerate(step) if ln.strip() == f"{key}: |")
    indent = len(step[start]) - len(step[start].lstrip())
    body = []
    for ln in step[start + 1 :]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent:
            break
        body.append(ln)
    return textwrap.dedent("\n".join(body)) + "\n"


def _refresh_step() -> list[str]:
    return _step_named(_text(), "refresh (dry run)")


def _issue_step() -> list[str]:
    return _step_named(_text(), "open or comment on the catalog issue")


def _step_id(step: list[str]) -> str:
    return next(ln.split("id:", 1)[1].strip() for ln in step if "id:" in ln)


# ------------------------------------------------------------ AC-1 triggers


def test_ac1_only_schedule_and_workflow_dispatch_trigger_the_workflow():
    on = _top_block(_text(), "on")
    assert sorted(_child_keys(on, 2)) == ["schedule", "workflow_dispatch"]


def test_ac1_one_cron_line_that_fires_once_a_month():
    on = _top_block(_text(), "on")
    crons = re.findall(
        r"- cron:\s*[\"']?([^\"'\n]+?)[\"']?\s*$", "\n".join(on), re.M
    )
    assert len(crons) == 1, crons
    minute, hour, dom, month, dow = crons[0].split()
    assert minute.isdigit() and hour.isdigit()
    assert dom.isdigit() and 1 <= int(dom) <= 28, dom
    assert month == "*" and dow == "*", crons[0]


def test_ac1_test_workflow_gained_no_schedule():
    # The schedule lives in its own workflow file; test.yml keeps its triggers.
    assert WORKFLOW.is_file()
    text = TEST_WORKFLOW.read_text(encoding="utf-8")
    on = _top_block(text, "on")
    assert sorted(_child_keys(on, 2)) == ["pull_request", "push"]
    assert "schedule" not in text and "workflow_dispatch" not in text


# ------------------------------------------------------------ AC-2 runner


def test_ac2_single_job_gated_on_upstream_ubuntu_python_313_requirements():
    text = _text()
    jobs = _top_block(text, "jobs")
    assert len(_child_keys(jobs, 2)) == 1, _child_keys(jobs, 2)
    joined = "\n".join(jobs)
    gate = rf"^\s+if: github\.repository == '{UPSTREAM}'\s*$"
    assert re.search(gate, joined, re.M), joined
    assert re.search(r"^\s+runs-on: ubuntu-latest\s*$", joined, re.M)
    assert "matrix" not in joined
    assert re.search(r"^\s+python-version: [\"']?3\.13[\"']?\s*$", joined, re.M)
    installs = [ln for ln in jobs if "pip install" in ln]
    assert len(installs) == 1, installs
    assert "-r requirements.txt" in installs[0]
    assert "requirements-dev" not in installs[0]


# ------------------------------------------------------------ AC-3 dry run


def test_ac3_no_commit_push_or_pull_request_anywhere_in_the_workflow():
    text = _text()
    for forbidden in (
        "git push",
        "git commit",
        "git add",
        "gh pr",
        "pulls.create",
        "peter-evans/create-pull-request",
        "stefanzweifel/git-auto-commit",
    ):
        assert forbidden not in text, forbidden
    # Only the dry-run step may run the launcher, and never with --write.
    runs = [ln for ln in text.splitlines() if LAUNCHER in ln]
    assert len(runs) == 1, runs
    assert "--write" not in runs[0]


# ---------------------------------------------- the shell step, run for real


def _bash():
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on PATH")
    # The probe also proves this bash reads the host's paths (Git Bash does;
    # a WSL stub found first on a Windows PATH would not), so the shim, the
    # canned output and $GITHUB_OUTPUT below are reachable from the script.
    try:
        probe = subprocess.run(
            [bash, "-c", 'test -f "$P" && printf ok'],
            env={**os.environ, "P": str(WORKFLOW)},
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("bash on PATH does not run")
    if probe.returncode != 0 or probe.stdout != "ok":
        pytest.skip("bash on PATH cannot read this checkout")
    return bash


def _run_refresh_step(tmp_path: Path, output: str, exit_code: int = 0):
    """Run the ``refresh (dry run)`` block as GitHub does (``shell: bash``
    is ``bash --noprofile --norc -eo pipefail``) with a stand-in ``python``
    first on PATH that prints ``output`` and exits ``exit_code``."""
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
    script.write_text(
        _literal_block(_refresh_step(), "run"), encoding="utf-8", newline="\n"
    )
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
UNREACHABLE_ONLY = (
    "unreachable DSP0236: HTTP 503\n"
    "unreachable NVMe-Base: timed out\n"
    "summary: add 0, confirm 0, changed 0, unreachable 2" + TAIL + "\n"
)
PROPOSALS = (
    "confirm DSP0270 1.2.0-WIP (2025-11-03) (work in progress)\n"
    "changed DSP0266 1.20.2 (2024-08-19) url moved\n"
    "changed DSP0268 2024.4 (2024-12-17) url moved\n"
    "changed DSP0218 1.3.0 (2024-06-05) url moved\n"
    "summary: add 0, confirm 1, changed 3, unreachable 0" + TAIL + "\n"
)


def test_ac3_step_runs_refresh_without_write_and_publishes_the_output(tmp_path):
    proc, summary, outs, argv = _run_refresh_step(tmp_path, PROPOSALS)
    assert proc.returncode == 0, proc.stderr
    # Loosened by the refresh --skip-source change (declared in its
    # change.md): the workflow now leaves OCP out, nothing else changed.
    assert argv[:2] == [LAUNCHER, "refresh"], argv
    assert argv[2:] == ["--skip-source", "ocp"], argv
    for line in PROPOSALS.splitlines():
        assert line in summary, line
    assert "proposals" in outs, outs


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (PROPOSALS, "4"),
        (UNREACHABLE_ONLY, "0"),
        ("summary: add 0, confirm 0, changed 0, unreachable 0" + TAIL + "\n", "0"),
        (
            "add DSP0236 1.4.0 (2026-02-02)\n"
            "summary: add 1, confirm 0, changed 0, unreachable 1" + TAIL + "\n",
            "1",
        ),
        (
            "summary: add 12, confirm 0, changed 0, unreachable 0" + TAIL + "\n",
            "12",
        ),
    ],
)
def test_ac4_ac5_proposals_output_sums_add_confirm_changed_only(
    tmp_path, output, expected
):
    proc, _summary, outs, _argv = _run_refresh_step(tmp_path, output)
    assert proc.returncode == 0, proc.stderr
    assert outs.get("proposals") == expected, outs


def test_ac5_unreachable_lines_reach_the_summary_but_count_for_nothing(tmp_path):
    proc, summary, outs, _argv = _run_refresh_step(tmp_path, UNREACHABLE_ONLY)
    assert proc.returncode == 0, proc.stderr
    assert "unreachable DSP0236: HTTP 503" in summary
    assert "unreachable NVMe-Base: timed out" in summary
    assert outs.get("proposals") == "0", outs


def test_ac3_failing_refresh_fails_the_step(tmp_path):
    proc, _summary, _outs, _argv = _run_refresh_step(
        tmp_path, "cannot read catalog\n", exit_code=2
    )
    assert proc.returncode != 0


# ------------------------------------------------ AC-4 / AC-5 issue gating


def test_ac5_issue_step_is_gated_on_the_refresh_steps_proposals_output():
    refresh = _refresh_step()
    issue = _issue_step()
    cond = next(ln.split("if:", 1)[1].strip() for ln in issue if "if:" in ln)
    m = re.fullmatch(r"steps\.(\w+)\.outputs\.(\w+)\s*!=\s*'0'", cond)
    assert m, cond
    assert m.group(1) == _step_id(refresh)
    run = _literal_block(refresh, "run")
    assert re.search(rf"{m.group(2)}=.*GITHUB_OUTPUT", run), run


# ------------------------------------------- the github-script, run for real

HARNESS = r"""
"use strict";
const fs = require("fs");
const path = require("path");
const scenario = JSON.parse(process.env.SCENARIO);
const script = fs.readFileSync(process.env.SCRIPT, "utf8");
const calls = [];
const RealDate = Date;
global.Date = class extends RealDate {
    constructor(...args) {
        if (args.length === 0) super(scenario.now);
        else super(...args);
    }
    static now() { return new RealDate(scenario.now).getTime(); }
};
const issues = {
    async getLabel(a) {
        calls.push(["getLabel", a]);
        if (scenario.labelMissing) {
            const e = new Error("Not Found");
            e.status = 404;
            throw e;
        }
        return { data: { name: a.name } };
    },
    async createLabel(a) { calls.push(["createLabel", a]); return { data: a }; },
    async listForRepo(a) {
        calls.push(["listForRepo", a]);
        return { data: scenario.open };
    },
    async createComment(a) { calls.push(["createComment", a]); return { data: { id: 1 } }; },
    async create(a) { calls.push(["create", a]); return { data: { number: 77 } }; },
};
const github = { rest: { issues } };
const context = {
    repo: { owner: "acme", repo: "widgets" },
    serverUrl: "https://github.example",
    runId: 4242,
    eventName: "schedule",
};
const core = { info() {}, warning() {}, setFailed(m) { throw new Error(m); } };
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const fn = new AsyncFunction("require", "github", "context", "core", script);
fn(require, github, context, core)
    .then(() => process.stdout.write(JSON.stringify(calls)))
    .catch((e) => { console.error(e && e.stack || e); process.exit(3); });
"""


def _node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("no node on PATH")
    return node


def _run_issue_script(tmp_path: Path, refresh_output: str, scenario: dict):
    node = _node()
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    (work / "refresh.txt").write_text(refresh_output, encoding="utf-8", newline="\n")
    script = tmp_path / "script.js"
    script.write_text(
        _literal_block(_issue_step(), "script"), encoding="utf-8", newline="\n"
    )
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8", newline="\n")
    env = dict(os.environ)
    env["SCENARIO"] = json.dumps(scenario)
    env["SCRIPT"] = str(script)
    proc = subprocess.run(
        [node, str(harness)],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


NOW = "2026-03-01T06:00:00Z"


def _names(calls):
    return [name for name, _ in calls]


def test_ac4_issue_step_uses_github_script():
    assert any("uses: actions/github-script@" in ln for ln in _issue_step())


def test_ac4_opens_a_labelled_issue_named_after_the_month(tmp_path):
    calls = _run_issue_script(
        tmp_path, PROPOSALS, {"now": NOW, "labelMissing": False, "open": []}
    )
    names = _names(calls)
    assert names.count("create") == 1 and "createComment" not in names, names
    create = dict(calls)["create"]
    assert create["owner"] == "acme" and create["repo"] == "widgets"
    assert create["title"] == "Catalog refresh 2026-03", create["title"]
    assert create["labels"] == ["catalog"], create["labels"]
    for line in PROPOSALS.splitlines():
        assert line in create["body"], line
    assert "createLabel" not in names


def test_ac4_comments_on_the_open_labelled_issue_instead_of_opening_another(
    tmp_path,
):
    existing = [{"number": 31, "title": "Catalog refresh 2026-02", "state": "open"}]
    calls = _run_issue_script(
        tmp_path, PROPOSALS, {"now": NOW, "labelMissing": False, "open": existing}
    )
    names = _names(calls)
    assert "create" not in names, names
    assert names.count("createComment") == 1, names
    comment = dict(calls)["createComment"]
    assert comment["issue_number"] == 31
    for line in PROPOSALS.splitlines():
        assert line in comment["body"], line
    listing = dict(calls)["listForRepo"]
    assert listing["state"] == "open"
    assert listing["labels"] in ("catalog", ["catalog"]), listing


def test_ac4_a_pull_request_carrying_the_label_does_not_count_as_the_issue(
    tmp_path,
):
    only_pr = [
        {
            "number": 40,
            "title": "Some PR",
            "state": "open",
            "pull_request": {"url": "https://api.github.example/pulls/40"},
        }
    ]
    calls = _run_issue_script(
        tmp_path, PROPOSALS, {"now": NOW, "labelMissing": False, "open": only_pr}
    )
    names = _names(calls)
    assert "createComment" not in names, names
    assert names.count("create") == 1, names


def test_ac4_missing_label_is_created_before_the_issue(tmp_path):
    calls = _run_issue_script(
        tmp_path, PROPOSALS, {"now": NOW, "labelMissing": True, "open": []}
    )
    names = _names(calls)
    assert "createLabel" in names and "create" in names, names
    assert names.index("createLabel") < names.index("create")
    assert dict(calls)["createLabel"]["name"] == "catalog"


# ------------------------------------------------------------ AC-6 token


def test_ac6_token_has_contents_read_and_issues_write_only():
    text = _text()
    assert text.count("permissions:") == 1
    perms = [ln.strip() for ln in _top_block(text, "permissions") if ln.strip()]
    assert sorted(perms) == ["contents: read", "issues: write"], perms


# ------------------------------------------------------------ AC-7 README


def test_ac7_the_workflow_is_documented_in_catalog_md_and_not_in_readme():
    catalog_doc = (ROOT / "docs" / "CATALOG.md").read_text(encoding="utf-8")
    assert "catalog.yml" in catalog_doc
    assert "catalog.yml" not in README.read_text(encoding="utf-8")

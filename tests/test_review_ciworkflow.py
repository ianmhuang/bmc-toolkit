"""Acceptance tests for the CI workflow change (AC-1 to AC-7).

The workflow file is the public artefact, so the checks parse it into a
structure with a small indentation-based reader (the project has no YAML
dependency) and assert on the structure, not on line text. AC-8 is a manual
check on the pull request and is not covered here.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"

_KEY = re.compile(r"([\w.-]+):(?: (.*))?$")


# --- minimal reader for the YAML subset a workflow file uses -----------------


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _scalar(text):
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text == "true":
        return True
    if text == "false":
        return False
    if re.fullmatch(r"\d+", text):
        return int(text)
    return text


def _is_list_item(line):
    return line.lstrip().startswith("- ")


def _parse(lines, i, indent):
    if _is_list_item(lines[i]):
        return _parse_list(lines, i, indent)
    return _parse_map(lines, i, indent)


def _parse_map(lines, i, indent):
    out = {}
    while (
        i < len(lines) and _indent(lines[i]) == indent and not _is_list_item(lines[i])
    ):
        m = _KEY.match(lines[i].strip())
        assert m, f"unreadable workflow line: {lines[i]!r}"
        key, rest = m.group(1), m.group(2)
        i += 1
        if rest is not None and rest.strip():
            out[key] = _scalar(rest)
        elif i < len(lines) and (
            _indent(lines[i]) > indent
            or (_indent(lines[i]) == indent and _is_list_item(lines[i]))
        ):
            out[key], i = _parse(lines, i, _indent(lines[i]))
        else:
            out[key] = None
    return out, i


def _parse_list(lines, i, indent):
    out = []
    while i < len(lines) and _indent(lines[i]) == indent and _is_list_item(lines[i]):
        head = lines[i].strip()[2:]
        item_indent = indent + 2
        if _KEY.match(head):
            lines[i] = " " * item_indent + head
            item, i = _parse_map(lines, i, item_indent)
        else:
            item = _scalar(head)
            i += 1
        out.append(item)
    return out, i


def _load_workflow():
    text = WORKFLOW.read_text(encoding="utf-8")
    lines = [
        ln.rstrip()
        for ln in text.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    value, i = _parse(lines, 0, 0)
    assert i == len(lines), f"workflow not fully read; stopped at {lines[i]!r}"
    return value


def _jobs():
    wf = _load_workflow()
    assert isinstance(wf.get("jobs"), dict) and wf["jobs"], "no jobs defined"
    return wf["jobs"]


def _run_steps(job):
    return [s["run"] for s in job["steps"] if isinstance(s, dict) and "run" in s]


def _uses_steps(job):
    return [s["uses"] for s in job["steps"] if isinstance(s, dict) and "uses" in s]


def _matrix_entries(job):
    strategy = job.get("strategy") or {}
    matrix = strategy.get("matrix") or {}
    return matrix.get("include") or []


# --- AC-1 --------------------------------------------------------------------


def test_ac1_workflow_file_exists_at_the_documented_path():
    assert WORKFLOW.is_file()


def test_ac1_triggers_are_pull_request_any_base_and_push_to_main_only():
    wf = _load_workflow()
    on = wf["on"]
    assert isinstance(on, dict), on
    assert set(on) == {"pull_request", "push"}
    # No branch filter on pull_request: any base branch triggers it.
    assert on["pull_request"] is None or "branches" not in on["pull_request"]
    assert on["push"] == {"branches": ["main"]}


# --- AC-2 --------------------------------------------------------------------


def test_ac2_test_job_matrix_is_ubuntu_311_313_and_windows_313():
    jobs = _jobs()
    assert "test" in jobs
    job = jobs["test"]
    assert job["runs-on"] == "${{ matrix.os }}"
    combos = {(e["os"], str(e["python"])) for e in _matrix_entries(job)}
    assert combos == {
        ("ubuntu-latest", "3.11"),
        ("ubuntu-latest", "3.13"),
        ("windows-latest", "3.13"),
    }
    # The matrix value is what setup-python receives.
    setup = [
        s
        for s in job["steps"]
        if isinstance(s, dict) and str(s.get("uses", "")).startswith("actions/setup-python@")
    ]
    assert len(setup) == 1
    assert setup[0]["with"]["python-version"] == "${{ matrix.python }}"


def test_ac2_ubuntu_runs_the_python_floor_from_pyproject():
    floor = re.search(
        r'requires-python\s*=\s*">=\s*([\d.]+)"', PYPROJECT.read_text(encoding="utf-8")
    ).group(1)
    ubuntu_versions = {
        str(e["python"])
        for e in _matrix_entries(_jobs()["test"])
        if e["os"].startswith("ubuntu")
    }
    assert floor in ubuntu_versions, (floor, ubuntu_versions)


# --- AC-3 --------------------------------------------------------------------


def test_ac3_macos_job_is_separate_and_guarded_to_push_events():
    jobs = _jobs()
    assert "test-macos" in jobs
    job = jobs["test-macos"]
    assert job["runs-on"] == "macos-latest"
    guard = str(job.get("if", "")).replace('"', "'").replace(" ", "")
    assert guard == "github.event_name=='push'", job.get("if")
    setup = [
        s
        for s in job["steps"]
        if isinstance(s, dict) and str(s.get("uses", "")).startswith("actions/setup-python@")
    ]
    assert len(setup) == 1
    assert str(setup[0]["with"]["python-version"]) == "3.13"


def test_ac3_no_other_job_can_start_a_macos_runner_on_a_pull_request():
    for name, job in _jobs().items():
        if name == "test-macos":
            continue
        assert "macos" not in str(job.get("runs-on", "")).lower(), name
        for entry in _matrix_entries(job):
            assert "macos" not in str(entry.get("os", "")).lower(), (name, entry)


# --- AC-4 --------------------------------------------------------------------


def test_ac4_every_job_checks_out_sets_up_python_installs_lints_and_tests():
    for name, job in _jobs().items():
        uses = _uses_steps(job)
        assert uses[0].startswith("actions/checkout@"), (name, uses)
        assert any(u.startswith("actions/setup-python@") for u in uses), name
        runs = _run_steps(job)
        assert len(runs) >= 4, (name, runs)
        install, check, fmt, pytest_cmd = runs[-4:]
        assert "pip install" in install, install
        assert "-r requirements.txt" in install and "-r requirements-dev.txt" in install
        assert check.split() == ["ruff", "check", "."], check
        assert fmt.split() == ["ruff", "format", "--check", "."], fmt
        assert pytest_cmd.split()[:3] == ["python", "-m", "pytest"], pytest_cmd


def test_ac4_pdf_tests_are_not_deselected_and_pypdfium2_is_installed():
    for name, job in _jobs().items():
        args = _run_steps(job)[-1].split()
        pytest_args = args[args.index("pytest") + 1 :]
        for arg in pytest_args:
            for flag in ("-k", "-m", "--ignore", "--deselect"):
                assert not arg.startswith(flag), (name, arg)
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^pypdfium2\b", requirements, re.M)


# --- AC-5 --------------------------------------------------------------------


def test_ac5_pythonutf8_reaches_every_job():
    wf = _load_workflow()
    top = (wf.get("env") or {}).get("PYTHONUTF8")
    for name, job in wf["jobs"].items():
        own = (job.get("env") or {}).get("PYTHONUTF8")
        value = own if own is not None else top
        assert str(value) == "1", (name, value)


def test_ac5_every_job_has_a_timeout_of_at_most_30_minutes():
    for name, job in _jobs().items():
        assert "timeout-minutes" in job, name
        assert 0 < int(job["timeout-minutes"]) <= 30, (name, job["timeout-minutes"])


# --- AC-6 --------------------------------------------------------------------


def test_ac6_concurrency_group_is_workflow_and_ref_and_cancels_in_progress():
    wf = _load_workflow()
    conc = wf.get("concurrency")
    assert isinstance(conc, dict), conc
    group = str(conc.get("group", ""))
    assert "github.workflow" in group and "github.ref" in group, group
    # Round 1 F2: superseded pull-request runs are cancelled, pushes to main
    # are not (edited by the author as the finding asked).
    cancel = str(conc.get("cancel-in-progress", ""))
    assert "github.event_name == 'pull_request'" in cancel, conc


# --- AC-7 --------------------------------------------------------------------


def _development_section():
    text = README.read_text(encoding="utf-8")
    start = text.index("\n## Development")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_ac7_readme_development_says_the_commands_run_on_actions_for_three_os():
    dev = _development_section()
    paragraphs = [p.replace("\n", " ") for p in dev.split("\n\n")]
    mention = [p for p in paragraphs if "GitHub Actions" in p]
    assert len(mention) == 1, mention
    sentence = mention[0]
    for os_name in ("Linux", "Windows", "macOS"):
        assert os_name in sentence, (os_name, sentence)


def test_ac7_readme_development_has_no_badge():
    dev = _development_section()
    assert "![" not in dev
    assert "shields.io" not in dev and "badge" not in dev.lower()
    assert "actions/workflows" not in dev

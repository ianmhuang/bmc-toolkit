"""CI workflow (M12, AC-1 to AC-7): the GitHub Actions file lints and tests
on Linux and Windows for every pull request and adds macOS on pushes to
main or develop. No YAML parser is a dependency, so the checks read the
text."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
README = ROOT / "README.md"

INSTALL = "python -m pip install -r requirements.txt -r requirements-dev.txt"
STEPS = [INSTALL, "ruff check .", "ruff format --check .", "python -m pytest -q"]


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _job(name: str) -> str:
    """The lines of one job: from ``  <name>:`` to the next two-space key."""
    lines = _text().splitlines()
    start = lines.index(f"  {name}:")
    body = [lines[start]]
    for ln in lines[start + 1 :]:
        if re.match(r"  \S", ln):
            break
        body.append(ln)
    return "\n".join(body)


def test_ac1_triggers_on_pull_request_and_push_to_main_or_develop():
    text = _text()
    on = text[text.index("\non:") : text.index("\nconcurrency:")]
    assert "pull_request:" in on
    assert re.search(r"push:\n\s+branches: \[main, develop\]", on)
    assert "tags" not in on and "schedule" not in on


def test_ac2_test_job_matrix_is_ubuntu_and_windows():
    job = _job("test")
    combos = re.findall(r"- os: (\S+)\n\s+python: \"([\d.]+)\"", job)
    assert combos == [
        ("ubuntu-latest", "3.11"),
        ("ubuntu-latest", "3.13"),
        ("windows-latest", "3.13"),
    ]
    assert "runs-on: ${{ matrix.os }}" in job
    assert "fail-fast: false" in job


def test_ac2_python_floor_matches_pyproject():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    floor = re.search(r'requires-python = ">=([\d.]+)"', pyproject).group(1)
    assert f'python: "{floor}"' in _job("test")


def test_ac3_macos_job_only_on_push():
    job = _job("test-macos")
    assert "runs-on: macos-latest" in job
    assert "if: github.event_name == 'push'" in job
    assert 'python-version: "3.13"' in job
    assert "macos" not in _job("test")


def test_ac4_every_job_runs_the_same_steps_in_order():
    for name in ("test", "test-macos"):
        job = _job(name)
        assert "uses: actions/checkout@v4" in job
        assert "uses: actions/setup-python@v5" in job
        positions = [job.index(f"- run: {step}") for step in STEPS]
        assert positions == sorted(positions), name


def test_ac5_utf8_and_timeout():
    text = _text()
    assert re.search(r"^env:\n  PYTHONUTF8: \"1\"", text, re.M)
    timeouts = [int(m) for m in re.findall(r"timeout-minutes: (\d+)", text)]
    assert len(timeouts) == 2 and all(t <= 30 for t in timeouts)


def test_ac6_concurrency_cancels_superseded_runs():
    text = _text()
    assert re.search(
        r"concurrency:\n  group: \$\{\{ github.workflow \}\}-\$\{\{ github.ref \}\}\n"
        r"  cancel-in-progress: \$\{\{ github.event_name == 'pull_request' \}\}",
        text,
    )


def test_ac6_token_is_read_only():
    assert re.search(r"^permissions:\n  contents: read", _text(), re.M)


def test_ac7_readme_development_mentions_actions():
    text = README.read_text(encoding="utf-8")
    dev = text[text.index("## Development") : text.index("## License")]
    for step in STEPS[1:]:
        assert step in dev, step
    assert "GitHub Actions" in dev
    assert "Linux" in dev and "Windows" in dev and "macOS" in dev
    assert "badge" not in dev.lower() and "shields.io" not in dev

"""Reviewer acceptance tests for ``bmcspec grep -i`` / ``--ignore-case``:
the flag matches regardless of case while the default stays case-sensitive
(AC-1), it combines with ``--regex`` and ``--context``, where a line that
matches only case-insensitively is a hit and not a context line (AC-2), and
the output format, ``--max``, ``--glob`` and the not-held message are what
they were (AC-5). Black-box, through the CLI, against a local bare git
repository (no network). Skipped when git is not on PATH."""

import shutil

import pytest

from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import git, make_repo

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

# One spelling per line: "PowerState", "POWERSTATE" and "powerstate". No
# line holds "POWERstate", and only the last file holds the lower-case one.
FILES = {
    "README.md": "thing\n",
    "src/power.cpp": (
        "// chassis\n"
        "int PowerState = 0;\n"
        "int other;\n"
        "int unrelated;\n"
        "void setPOWERSTATE();\n"
    ),
    "src/state.hpp": "#pragma once\nint powerstate();\n",
}

MORE = "more hits not shown; narrow the pattern or raise --max"


def run(capsys, catalog_file, *argv):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def held(tmp_path, monkeypatch, capsys):
    """(catalog path, hit line maker): thing is held at its default branch."""
    work, bare, url = make_repo(tmp_path, "thing", FILES)
    commit7 = git("rev-parse", "HEAD", cwd=work)[:7]
    catalog_file = tmp_path / "catalog.toml"
    entry = f'\n[[repos]]\nid = "thing"\nurl = "{url}"\ntopics = ["power"]\n'
    catalog_file.write_text(MINI_CATALOG + entry, encoding="utf-8", newline="")
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path / "lib"))
    code, out = run(capsys, catalog_file, "clone", "thing")
    assert code == 0, out

    def hit(path, line, text):
        return f"thing@{commit7} {path}:{line} | {text}"

    return catalog_file, hit


def test_ignore_case_finds_what_the_default_misses(held, capsys):
    catalog_file, hit = held
    every_spelling = [
        hit("src/power.cpp", 2, "int PowerState = 0;"),
        hit("src/power.cpp", 5, "void setPOWERSTATE();"),
        hit("src/state.hpp", 2, "int powerstate();"),
    ]
    # AC-1: a pattern in a case no line has is not found without the flag
    code, out = run(capsys, catalog_file, "grep", "thing", "POWERstate")
    assert code == 0 and out.strip() == "no hits"
    # AC-1: both spellings of the flag find every line, in the hit format
    for flag in ("-i", "--ignore-case"):
        code, out = run(capsys, catalog_file, "grep", "thing", "POWERstate", flag)
        assert code == 0, out
        assert out.splitlines() == every_spelling, flag
    # AC-1 / AC-5: the default is still case-sensitive, one spelling only
    code, out = run(capsys, catalog_file, "grep", "thing", "powerstate")
    assert code == 0
    assert out.splitlines() == [hit("src/state.hpp", 2, "int powerstate();")]
    code, out = run(capsys, catalog_file, "grep", "thing", "powerstate", "-i")
    assert code == 0 and out.splitlines() == every_spelling


def test_ignore_case_with_regex(held, capsys):
    catalog_file, hit = held
    pattern = "^INT +power"
    # AC-2 / AC-5: the regex alone is case-sensitive
    code, out = run(capsys, catalog_file, "grep", "thing", pattern, "--regex")
    assert code == 0 and out.strip() == "no hits"
    # AC-2: -i applies to the regex
    for argv in (["--regex", "-i"], ["-i", "--regex"], ["--regex", "--ignore-case"]):
        code, out = run(capsys, catalog_file, "grep", "thing", pattern, *argv)
        assert code == 0, out
        assert out.splitlines() == [
            hit("src/power.cpp", 2, "int PowerState = 0;"),
            hit("src/state.hpp", 2, "int powerstate();"),
        ], argv
    # AC-5: -i does not turn the pattern into a regex
    code, out = run(capsys, catalog_file, "grep", "thing", pattern, "-i")
    assert code == 0 and out.strip() == "no hits"
    code, out = run(capsys, catalog_file, "grep", "thing", "INT POWERSTATE", "-i")
    assert code == 0
    assert out.splitlines() == [
        hit("src/power.cpp", 2, "int PowerState = 0;"),
        hit("src/state.hpp", 2, "int powerstate();"),
    ]


def test_ignore_case_with_context_prints_hits_as_hits(held, capsys):
    catalog_file, hit = held
    # AC-5: without the flag only the lower-case line is a hit
    argv = ["grep", "thing", "powerstate", "--context", "1"]
    code, out = run(capsys, catalog_file, *argv)
    assert code == 0
    assert out.splitlines() == [
        "    line 1: #pragma once",
        hit("src/state.hpp", 2, "int powerstate();"),
    ]
    # AC-2: lines 2 and 5 of power.cpp match only case-insensitively and are
    # hits; their neighbours are context lines
    for flag in ("-i", "--ignore-case"):
        code, out = run(capsys, catalog_file, *argv, flag)
        assert code == 0, out
        assert out.splitlines() == [
            "    line 1: // chassis",
            hit("src/power.cpp", 2, "int PowerState = 0;"),
            "    line 3: int other;",
            "    line 4: int unrelated;",
            hit("src/power.cpp", 5, "void setPOWERSTATE();"),
            "--",
            "    line 1: #pragma once",
            hit("src/state.hpp", 2, "int powerstate();"),
        ], flag
    # AC-2: --regex, --context and -i together
    argv = ["grep", "thing", "^VOID +setpowerstate", "--regex", "--context", "1", "-i"]
    code, out = run(capsys, catalog_file, *argv)
    assert code == 0, out
    assert out.splitlines() == [
        "    line 4: int unrelated;",
        hit("src/power.cpp", 5, "void setPOWERSTATE();"),
    ]


def test_ignore_case_keeps_max_glob_and_the_messages(held, capsys):
    catalog_file, hit = held
    # AC-5: the cap counts the case-insensitive hits and says what is left
    argv = ["grep", "thing", "POWERstate", "-i", "--max", "1"]
    code, out = run(capsys, catalog_file, *argv)
    assert code == 0, out
    assert out.splitlines() == [
        hit("src/power.cpp", 2, "int PowerState = 0;"),
        f"2 {MORE}",
    ]
    argv = ["grep", "thing", "POWERstate", "-i", "--max", "0"]
    code, out = run(capsys, catalog_file, *argv)
    assert code == 0 and len(out.splitlines()) == 3 and MORE not in out
    # AC-5: --glob still narrows the paths
    argv = ["grep", "thing", "POWERstate", "-i", "--glob", "src/*.cpp"]
    code, out = run(capsys, catalog_file, *argv)
    assert code == 0, out
    assert out.splitlines() == [
        hit("src/power.cpp", 2, "int PowerState = 0;"),
        hit("src/power.cpp", 5, "void setPOWERSTATE();"),
    ]
    # AC-5: nothing to find is still `no hits`, exit 0
    code, out = run(capsys, catalog_file, "grep", "thing", "ZZZ-absent", "-i")
    assert code == 0 and out.strip() == "no hits"
    # AC-5: the not-held message and exit code are the same with the flag
    argv = ["grep", "thing", "POWERstate", "-i", "--ref", "v9"]
    code, out = run(capsys, catalog_file, *argv)
    assert code == 2
    assert out.strip() == "thing is not held at v9; run: bmcspec clone thing --ref v9"

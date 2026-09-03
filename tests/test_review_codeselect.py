"""Independent acceptance tests for Code Tree selection, grep, and code
(AC-2 through AC-6 of the Code Trees change): user checkout precedence,
release resolution, the grep hit format and its --max cap, and the code
command's line-range rules. Black-box, through the ``bmcspec`` CLI, against
local bare git repositories (no network). Skipped when git is not on PATH.
"""

import shutil

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import RECIPE, commit, git, make_repo, push

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def remotes(tmp_path):
    """thing (a component, default branch main) and openbmc (the release
    source, with a recipe pinning thing's first commit at tag 1.0.0)."""
    files = {
        "src/main.cpp": "int main() {\n    return powerState();\n}\n",
        "src/state.hpp": "// CurrentPowerState\nint powerState();\n",
    }
    work, bare, url = make_repo(tmp_path, "thing", files)
    first = git("rev-parse", "HEAD", cwd=work)
    recipe = RECIPE.format(url=url.removeprefix("file://"), sha=first)
    ob_files = {
        "meta-phosphor/recipes-phosphor/things/thing_git.bb": recipe,
        "README.md": "distro\n",
    }
    ob_work, ob_bare, ob_url = make_repo(tmp_path, "openbmc", ob_files, branch="master")
    git("tag", "1.0.0", cwd=ob_work)
    push(ob_work, "1.0.0")
    return {"thing": (work, url, first), "openbmc": (ob_work, ob_url)}


@pytest.fixture
def catalog_file(tmp_path, remotes):
    text = (
        MINI_CATALOG
        + f"""
[[repos]]
id = "openbmc"
url = "{remotes['openbmc'][1]}"
topics = ["release"]
sparse = ["meta-phosphor"]

[[repos]]
id = "thing"
url = "{remotes['thing'][1]}"
topics = ["power"]
"""
    )
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


# --------------------------------------------------------------- AC-4


def test_user_checkout_outranks_the_library_and_is_cited(
    library, catalog_file, remotes, capsys
):
    work, url, first = remotes["thing"]
    run(capsys, "clone", "thing", catalog_file=catalog_file)  # a Library tree exists
    library.mkdir(exist_ok=True)
    (library / "config.toml").write_text(
        f'[code.checkouts]\nthing = "{work.as_posix()}"\n', encoding="utf-8"
    )
    code, out = run(
        capsys, "code", "thing", "src/state.hpp", "--ref", "main",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == f"note: using the user checkout {work} instead of main"
    cite = lines[1].split(" | ")
    assert cite[1] == f"thing {git('rev-parse', 'HEAD', cwd=work)[:7]}"
    assert cite[2] == "user checkout"


# --------------------------------------------------------------- AC-3


def test_release_pin_and_unknown_release_and_missing_recipe(
    library, catalog_file, remotes, capsys
):
    work, url, first = remotes["thing"]
    code, out = run(
        capsys, "clone", "thing", "--release", "1.0.0", catalog_file=catalog_file
    )
    assert code == 0, out
    assert f"cloned thing {first[:7]} (release 1.0.0)" in out
    code, out = run(
        capsys, "grep", "thing", "powerState", "--release", "1.0.0",
        catalog_file=catalog_file,
    )
    assert code == 0
    assert out.splitlines() == [
        f"thing@{first[:7]} src/main.cpp:2 |     return powerState();",
        f"thing@{first[:7]} src/state.hpp:2 | int powerState();",
    ]
    # an unknown release name
    code, out = run(
        capsys, "clone", "thing", "--release", "no-such-release",
        catalog_file=catalog_file,
    )
    assert code == 2
    # a repository whose recipes the release does not name is exit 2
    code, out = run(
        capsys, "clone", "thing2", "--release", "1.0.0", catalog_file=catalog_file
    )
    assert code == 2, out


# --------------------------------------------------------------- AC-5


def test_grep_hit_format_and_no_hits(library, catalog_file, remotes, capsys):
    work, url, first = remotes["thing"]
    run(capsys, "clone", "thing", catalog_file=catalog_file)
    code, out = run(capsys, "grep", "thing", "powerState", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines() == [
        f"thing@{first[:7]} src/main.cpp:2 |     return powerState();",
        f"thing@{first[:7]} src/state.hpp:2 | int powerState();",
    ]
    code, out = run(capsys, "grep", "thing", "zzzz", catalog_file=catalog_file)
    assert code == 0 and out.strip() == "no hits"
    code, out = run(
        capsys, "grep", "unheld-repo", "x", catalog_file=catalog_file
    )
    assert code == 2  # not in the catalog and never cloned


def test_grep_max_caps_hits_even_when_context_merges_matches(
    library, catalog_file, remotes, capsys
):
    """AC-5: 'at most 50 hits unless --max'. Three matches on consecutive
    lines, with --context 1, fall inside one merged git-grep block (no
    '--' separator, since their context ranges overlap). --max must still
    cap how many hit lines are printed, not just how many blocks are
    started.
    """
    work, url, first = remotes["thing"]
    commit(
        work,
        {"adjacent.txt": "foo\nbar foo\nbaz foo\nqux\n"},
        "adjacent matches",
    )
    push(work)
    run(capsys, "clone", "thing", "--force", catalog_file=catalog_file)
    code, out = run(
        capsys, "grep", "thing", "foo", "--context", "1", "--max", "1",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    hit_lines = [ln for ln in out.splitlines() if " | " in ln]
    assert len(hit_lines) == 1, (
        f"--max 1 must print at most 1 hit line, got {len(hit_lines)}: {out}"
    )


# --------------------------------------------------------------- AC-6


def test_code_two_hundred_line_boundary(library, catalog_file, remotes, capsys):
    work, url, first = remotes["thing"]
    exactly_200 = "\n".join(f"line {i}" for i in range(1, 201)) + "\n"
    commit(work, {"e.txt": exactly_200}, "two hundred")
    push(work)
    run(capsys, "clone", "thing", "--force", catalog_file=catalog_file)
    code, out = run(capsys, "code", "thing", "e.txt", catalog_file=catalog_file)
    assert code == 0, out  # 200 lines: the whole file, no --lines needed
    assert out.splitlines()[-1] == "200  line 200"
    commit(work, {"e.txt": exactly_200 + "line 201\n"}, "two oh one")
    push(work)
    run(capsys, "clone", "thing", "--force", catalog_file=catalog_file)
    code, out = run(capsys, "code", "thing", "e.txt", catalog_file=catalog_file)
    assert code == 2  # 201 lines: --lines is required
    assert "201" in out


def test_code_refuses_paths_outside_the_tree(library, catalog_file, remotes, capsys):
    work, url, first = remotes["thing"]
    run(capsys, "clone", "thing", catalog_file=catalog_file)
    for outside in ("../outside.txt", "/etc/passwd"):
        code, out = run(
            capsys, "code", "thing", outside, catalog_file=catalog_file
        )
        assert code == 2, outside

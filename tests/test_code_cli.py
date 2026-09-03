"""The repos, clone, grep and code commands through the CLI, against local
bare repositories; the fake openbmc/openbmc carries the recipe that pins
the component. Skipped when git is not on PATH."""

import shutil

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import RECIPE, THING_FILES, commit, git, make_repo, push

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def remotes(tmp_path):
    """thing (a component) and openbmc (the release source with a recipe
    pinning thing's first commit, tagged 1.0.0)."""
    work, bare, url = make_repo(tmp_path, "thing", THING_FILES)
    first = git("rev-parse", "HEAD", cwd=work)
    recipe = RECIPE.format(url=url.removeprefix("file://"), sha=first)
    ob_files = {
        "meta-phosphor/recipes-phosphor/things/thing_git.bb": recipe,
        "meta/unrelated.txt": "big\n",
        "README.md": "distro\n",
    }
    ob_work, ob_bare, ob_url = make_repo(tmp_path, "openbmc", ob_files, branch="master")
    git("tag", "1.0.0", cwd=ob_work)
    push(ob_work, "1.0.0")
    second = commit(work, {"src/main.cpp": "int main() { return 2; }\n"}, "second")
    push(work)
    return {
        "thing": (work, url, first, second),
        "openbmc": (ob_work, ob_url),
    }


@pytest.fixture
def catalog_file(tmp_path, remotes):
    thing_url = remotes["thing"][1]
    ob_url = remotes["openbmc"][1]
    text = (
        MINI_CATALOG
        + f"""
[[repos]]
id = "openbmc"
url = "{ob_url}"
topics = ["release", "recipes"]
sparse = ["meta-phosphor"]

[[repos]]
id = "thing"
url = "{thing_url}"
topics = ["power", "state"]

[[repos]]
id = "other"
url = "https://example.test/other.git"
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


# ------------------------------------------------------------ repos


def test_repos_lists_topics_and_held_trees(library, catalog_file, remotes, capsys):
    code, out = run(capsys, "repos", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines() == [
        "openbmc\t-\t-\trelease, recipes",
        "thing\t-\t-\tpower, state",
        "other\t-\t-\tpower",
    ]
    code, out = run(capsys, "repos", "--topic", "state", catalog_file=catalog_file)
    assert code == 0 and out.splitlines() == ["thing\t-\t-\tpower, state"]
    code, out = run(capsys, "repos", "--topic", "zzz", catalog_file=catalog_file)
    assert code == 2 and out.strip() == "no repository has the topic 'zzz'"
    run(capsys, "clone", "thing", catalog_file=catalog_file)
    code, out = run(capsys, "repos", "--topic", "state", catalog_file=catalog_file)
    second = remotes["thing"][3]
    line = out.strip()
    assert line.startswith(f"thing\t{second[:7]} main ")
    assert line.endswith("\t-\tpower, state")


def test_repos_search_needs_gh(library, catalog_file, capsys, monkeypatch):
    monkeypatch.setattr(code_mod.shutil, "which", lambda name: None)
    code, out = run(capsys, "repos", "--search", "x", catalog_file=catalog_file)
    assert code == 2 and out.strip().startswith("gh is not on PATH")


# ------------------------------------------------------------ clone


def test_clone_default_ref_and_commit(library, catalog_file, remotes, capsys):
    work, url, first, second = remotes["thing"]
    code, out = run(capsys, "clone", "thing", catalog_file=catalog_file)
    assert code == 0
    assert out.startswith(f"cloned thing {second[:7]} (main ")
    assert out.rstrip().endswith(str(library / "code" / "thing" / second))
    code, out = run(capsys, "clone", "thing", catalog_file=catalog_file)
    assert code == 0 and out.startswith(f"held thing {second[:7]} (main ")
    code, out = run(capsys, "clone", "thing", "--ref", first, catalog_file=catalog_file)
    assert code == 0 and out.startswith(f"cloned thing {first[:7]} ({first} ")
    code, out = run(
        capsys, "clone", "thing", "--ref", "nope", catalog_file=catalog_file
    )
    assert code == 2 and out.startswith("git clone failed: ")
    assert not (library / "code" / "thing" / ".tmp-").exists()
    argv = ["clone", "thing", "--ref", "a", "--release", "b"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 2 and out.strip() == "give --ref or --release, not both"


def test_clone_release_resolves_the_pin_through_openbmc(
    library, catalog_file, remotes, capsys
):
    work, url, first, second = remotes["thing"]
    code, out = run(
        capsys, "clone", "thing", "--release", "1.0.0", catalog_file=catalog_file
    )
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("cloned openbmc ") and "(release 1.0.0)" in lines[0]
    assert lines[1].startswith(f"cloned thing {first[:7]} (release 1.0.0)")
    ob = (library / "code" / "openbmc").iterdir()
    ob_tree = next(p for p in ob if p.is_dir())
    assert (ob_tree / "meta-phosphor").is_dir()
    assert not (ob_tree / "meta").exists()  # sparse
    code, out = run(
        capsys, "clone", "thing", "--release", "1.0.0", catalog_file=catalog_file
    )
    assert code == 0 and out.startswith(f"held thing {first[:7]} (release 1.0.0)")
    code, out = run(
        capsys, "clone", "other", "--release", "1.0.0", catalog_file=catalog_file
    )
    assert code == 2 and out.strip() == "no recipe in this release names other"
    code, out = run(
        capsys, "clone", "thing", "--release", "9.9.9", catalog_file=catalog_file
    )
    assert code == 2 and out.startswith("git clone failed: ")
    code, out = run(capsys, "repos", catalog_file=catalog_file)
    assert f"thing\t{first[:7]} release 1.0.0\t-\tpower, state" in out


def test_clone_uses_the_config_release_and_says_so(
    library, catalog_file, remotes, capsys
):
    work, url, first, second = remotes["thing"]
    library.mkdir()
    (library / "config.toml").write_text(
        '[code]\nrelease = "1.0.0"\n', encoding="utf-8"
    )
    code, out = run(capsys, "clone", "thing", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0] == "release: 1.0.0 (from config.toml)"
    assert f"cloned thing {first[:7]} (release 1.0.0)" in out
    code, out = run(capsys, "repos", catalog_file=catalog_file)
    assert out.splitlines()[0].startswith("release: 1.0.0 (config.toml) -> openbmc ")
    code, out = run(
        capsys, "clone", "thing", "--ref", "main", catalog_file=catalog_file
    )
    assert code == 0 and out.startswith(f"cloned thing {second[:7]} (main ")


def test_force_supersedes_and_repos_shows_it(library, catalog_file, remotes, capsys):
    work, url, first, second = remotes["thing"]
    run(capsys, "clone", "thing", catalog_file=catalog_file)
    third = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work)
    code, out = run(capsys, "clone", "thing", "--force", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[0].startswith(f"cloned thing {third[:7]} (main ")
    assert out.splitlines()[1].startswith(f"superseded thing {second[:7]} (main ")
    code, out = run(capsys, "repos", "--topic", "state", catalog_file=catalog_file)
    assert f"{third[:7]} main " in out and f"{second[:7]} main " in out
    assert out.count("superseded") == 1


# ------------------------------------------------------- grep and code


def test_grep_output_limits_and_selection(library, catalog_file, remotes, capsys):
    work, url, first, second = remotes["thing"]
    code, out = run(capsys, "grep", "thing", "powerState", catalog_file=catalog_file)
    assert code == 2
    assert out.strip() == "thing is not in the Library; run: bmcspec clone thing"
    run(capsys, "clone", "thing", catalog_file=catalog_file)
    code, out = run(capsys, "grep", "thing", "powerState", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines() == [
        f"thing@{second[:7]} src/state.hpp:2 | int powerState();"
    ]
    run(capsys, "clone", "thing", "--ref", first, catalog_file=catalog_file)
    argv = ["grep", "thing", "powerState", "--ref", first, "--context", "1"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert out.splitlines() == [
        "    line 1: int main() {",
        f"thing@{first[:7]} src/main.cpp:2 |     return powerState();",
        "    line 3: }",
        "--",
        "    line 1: // CurrentPowerState",
        f"thing@{first[:7]} src/state.hpp:2 | int powerState();",
    ]
    argv = ["grep", "thing", "powerState", "--ref", first, "--max", "1"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert (
        out.splitlines()[-1]
        == "1 more hits not shown; narrow the pattern or raise --max"
    )
    argv = ["grep", "thing", "int", "--ref", first, "--glob", "src/*.hpp", "--regex"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert [ln.split(" ")[1] for ln in out.splitlines()] == ["src/state.hpp:2"]
    code, out = run(capsys, "grep", "thing", "zzz", catalog_file=catalog_file)
    assert code == 0 and out.strip() == "no hits"
    code, out = run(
        capsys, "grep", "thing", "x", "--ref", "v9", catalog_file=catalog_file
    )
    assert code == 2
    assert out.strip() == "thing is not held at v9; run: bmcspec clone thing --ref v9"
    argv = ["grep", "thing", "x", "--release", "1.0.0"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 2
    assert out.strip() == (
        "thing is not held at release 1.0.0; run: bmcspec clone thing --release 1.0.0"
    )


def test_code_prints_cite_and_numbered_lines(library, catalog_file, remotes, capsys):
    work, url, first, second = remotes["thing"]
    run(capsys, "clone", "thing", catalog_file=catalog_file)
    code, out = run(capsys, "code", "thing", "src/state.hpp", catalog_file=catalog_file)
    assert code == 0
    lines = out.splitlines()
    fields = lines[0].split(" | ")
    assert fields[:2] == ["cite: code", f"thing {second[:7]}"]
    assert fields[2].startswith("main ") and fields[3] == "src/state.hpp lines 1-2"
    assert fields[4:6] == ["-", url]
    assert lines[1:] == ["1  // CurrentPowerState", "2  int powerState();"]
    argv = ["code", "thing", "src/main.cpp", "--lines", "1-1"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert out.splitlines()[1:] == ["1  int main() { return 2; }"]
    assert "src/main.cpp lines 1-1" in out.splitlines()[0]
    for bad in ("0-3", "3-1", "x", "9-12"):
        argv = ["code", "thing", "src/main.cpp", "--lines", bad]
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 2, bad
    code, out = run(capsys, "code", "thing", "../secret", catalog_file=catalog_file)
    assert code == 2 and out.strip() == "../secret is not a path inside the tree"
    code, out = run(capsys, "code", "thing", "src/nope.cpp", catalog_file=catalog_file)
    assert code == 2 and "is not a file in" in out


def test_code_requires_lines_for_long_files(library, catalog_file, remotes, capsys):
    work, url, first, second = remotes["thing"]
    long = "\n".join(f"line {i}" for i in range(1, 302)) + "\n"
    commit(work, {"long.txt": long}, "long")
    push(work)
    run(capsys, "clone", "thing", "--force", catalog_file=catalog_file)
    code, out = run(capsys, "code", "thing", "long.txt", catalog_file=catalog_file)
    assert code == 2
    assert out.strip() == (
        "long.txt has 301 lines; give --lines A-B "
        "(a whole file is printed only up to 200 lines)"
    )
    argv = ["code", "thing", "long.txt", "--lines", "300-400"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[1:] == ["300  line 300", "301  line 301"]
    assert "long.txt lines 300-301" in out.splitlines()[0]


def test_user_checkout_wins_and_is_cited(
    library, catalog_file, remotes, capsys, tmp_path
):
    work, url, first, second = remotes["thing"]
    library.mkdir()
    (library / "config.toml").write_text(
        f'[code.checkouts]\nthing = "{work.as_posix()}"\n', encoding="utf-8"
    )
    code, out = run(capsys, "grep", "thing", "powerState", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines() == [
        f"thing@{second[:7]} src/state.hpp:2 | int powerState();"
    ]
    argv = ["code", "thing", "src/state.hpp", "--ref", first]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == f"note: using the user checkout {work} instead of {first}"
    assert lines[1].split(" | ")[2] == "user checkout"
    assert lines[1].split(" | ")[6] == str(work)
    (library / "config.toml").write_text(
        f'[code.checkouts]\nthing = "{(tmp_path / "plain").as_posix()}"\n',
        encoding="utf-8",
    )
    (tmp_path / "plain").mkdir()
    code, out = run(capsys, "grep", "thing", "x", catalog_file=catalog_file)
    assert code == 2 and "not a git checkout" in out
    (library / "config.toml").write_text("[code\n", encoding="utf-8")
    code, out = run(capsys, "grep", "thing", "x", catalog_file=catalog_file)
    assert code == 1


def test_reading_commands_pick_the_config_release(
    library, catalog_file, remotes, capsys
):
    work, url, first, second = remotes["thing"]
    run(capsys, "clone", "thing", "--release", "1.0.0", catalog_file=catalog_file)
    run(capsys, "clone", "thing", catalog_file=catalog_file)
    (library / "config.toml").write_text(
        '[code]\nrelease = "1.0.0"\n', encoding="utf-8"
    )
    code, out = run(capsys, "grep", "thing", "powerState", catalog_file=catalog_file)
    assert out.splitlines()[0] == "note: release 1.0.0 from config.toml"
    assert out.splitlines()[1].startswith(f"thing@{first[:7]} src/main.cpp:2")
    argv = ["grep", "thing", "powerState", "--ref", "main"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert out.splitlines()[0].startswith(f"thing@{second[:7]} ")


def test_unlisted_repository_is_guessed_and_listed(
    library, catalog_file, remotes, capsys, monkeypatch, tmp_path
):
    (tmp_path / "guess").mkdir()
    work, bare, url = make_repo(tmp_path / "guess", "extra", {"a.txt": "hello\n"})
    base = (tmp_path / "guess").as_uri() + "/"
    monkeypatch.setattr(code_mod, "GUESS_BASE", base)
    code, out = run(capsys, "clone", "extra", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == f"note: extra is not in the catalog; trying {base}extra.git"
    assert lines[1].startswith("cloned extra ")
    tree = next(p for p in (library / "code" / "extra").iterdir() if p.is_dir())
    meta = (tree / code_mod.TREE_META).read_text("utf-8")
    assert '"catalog_known": false' in meta
    code, out = run(capsys, "grep", "extra", "hello", catalog_file=catalog_file)
    assert code == 0 and out.strip().endswith("a.txt:1 | hello")
    code, out = run(capsys, "repos", catalog_file=catalog_file)
    assert out.splitlines()[-1].startswith("extra\t") and out.strip().endswith(
        "\t-\t(not in catalog)"
    )
    code, out = run(capsys, "grep", "nowhere", "x", catalog_file=catalog_file)
    assert (
        code == 2
        and out.strip() == "unknown repository 'nowhere'; bmcspec repos lists them"
    )
    code, out = run(capsys, "clone", "../evil", catalog_file=catalog_file)
    assert (
        code == 2
        and out.strip() == "'../evil' is not a repository id; bmcspec repos lists them"
    )


def test_git_missing_is_an_exit_2_message(library, catalog_file, capsys, monkeypatch):
    monkeypatch.setattr(code_mod.shutil, "which", lambda name: None)
    code, out = run(capsys, "clone", "thing", catalog_file=catalog_file)
    assert code == 2 and out.strip().startswith("git is not on PATH")

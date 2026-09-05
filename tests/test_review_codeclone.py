"""Independent acceptance tests for the Code Trees change: the clone
command and the repos listing (AC-1, AC-2), GitHub search through gh
(AC-7), the no-network / standard-library / UTF-8 subprocess rules (AC-8)
and the README and SKILL.md documentation (AC-9).

Black-box through the ``bmcspec`` CLI against local bare git repositories.
``gh`` is replaced by a scripted subprocess: the sandbox has no network and
no credentials. Skipped when git is not on PATH, except for the parts that
need no git at all.
"""

import ast
import json
import shutil
import subprocess
import sys

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG, ROOT
from tests.test_code import RECIPE, commit, git, make_repo, push

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

TREE_META = ".bmc-tree.json"  # AC-11 names the file


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def remotes(tmp_path):
    """thing (default branch main, tag v1 on the first commit, a second
    commit on main) and openbmc (branch master, tag 1.0.0, a recipe that
    pins thing's first commit)."""
    files = {
        "src/main.cpp": "int main() {\n    return powerState();\n}\n",
        "src/state.hpp": "// CurrentPowerState\nint powerState();\n",
    }
    work, bare, url = make_repo(tmp_path, "thing", files)
    first = git("rev-parse", "HEAD", cwd=work)
    git("tag", "v1", cwd=work)
    push(work, "v1")
    second = commit(work, {"src/main.cpp": "int main() { return 2; }\n"}, "second")
    push(work)
    recipe = RECIPE.format(url=url.removeprefix("file://"), sha=first)
    ob_files = {
        "meta-phosphor/recipes-phosphor/things/thing_git.bb": recipe,
        "meta/unrelated.txt": "big\n",
    }
    ob_work, ob_bare, ob_url = make_repo(tmp_path, "openbmc", ob_files, branch="master")
    git("tag", "1.0.0", cwd=ob_work)
    push(ob_work, "1.0.0")
    return {
        "thing": {"work": work, "bare": bare, "url": url, "first": first, "second": second},
        "openbmc": {"work": ob_work, "url": ob_url},
    }


@pytest.fixture
def catalog_file(tmp_path, remotes):
    text = (
        MINI_CATALOG
        + f"""
[[repos]]
id = "openbmc"
url = "{remotes['openbmc']['url']}"
topics = ["release"]
sparse = ["meta-phosphor"]

[[repos]]
id = "thing"
url = "{remotes['thing']['url']}"
topics = ["power", "state"]
"""
    )
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


@pytest.fixture
def plain_catalog(tmp_path):
    """The document-only catalog: enough for repos --search and error paths."""
    path = tmp_path / "plain-catalog.toml"
    path.write_text(MINI_CATALOG, encoding="utf-8", newline="")
    return path


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


def _tree_dirs(library, repo):
    rdir = library / "code" / repo
    if not rdir.is_dir():
        return []
    return sorted(p for p in rdir.iterdir() if p.is_dir())


# ------------------------------------------------------------------ AC-2


@needs_git
def test_clone_default_branch_writes_tree_meta(library, catalog_file, remotes, capsys):
    thing = remotes["thing"]
    code, out = run(capsys, "clone", "thing", catalog_file=catalog_file)
    assert code == 0, out
    line = out.splitlines()[0]
    # `cloned <repo> <commit7> (<branch> <day>) -> <path>`; the default
    # branch of this remote is main, and it must be recorded by name.
    assert line.startswith(f"cloned thing {thing['second'][:7]} (main ")
    tree = library / "code" / "thing" / thing["second"]
    assert tree.is_dir(), out
    assert line.rstrip().endswith(str(tree))
    meta = json.loads((tree / TREE_META).read_text("utf-8"))
    assert meta["url"] == thing["url"]
    assert meta["commit"] == thing["second"]
    assert meta["provenance"]["kind"] == "default"
    assert meta["provenance"]["name"] == "main"
    assert meta["fetched_at"]
    assert "superseded_by" not in meta


@needs_git
def test_clone_held_tree_is_reported_without_touching_the_remote(
    library, catalog_file, remotes, capsys
):
    thing = remotes["thing"]
    code, out = run(capsys, "clone", "thing", catalog_file=catalog_file)
    assert code == 0, out
    # Take the remote away: a second clone of a held moving name must answer
    # from the Library (AC-2: "reported and not fetched again").
    gone = thing["bare"].with_name("thing.gone")
    shutil.move(str(thing["bare"]), str(gone))
    code, out = run(capsys, "clone", "thing", catalog_file=catalog_file)
    assert code == 0, out
    assert out.startswith(f"held thing {thing['second'][:7]} (main ")
    assert len(_tree_dirs(library, "thing")) == 1


@needs_git
def test_clone_ref_accepts_tag_and_full_commit(library, catalog_file, remotes, capsys):
    thing = remotes["thing"]
    code, out = run(capsys, "clone", "thing", "--ref", "v1", catalog_file=catalog_file)
    assert code == 0, out
    assert out.startswith(f"cloned thing {thing['first'][:7]} (v1 ")
    meta = json.loads(
        (library / "code" / "thing" / thing["first"] / TREE_META).read_text("utf-8")
    )
    assert meta["provenance"] == {"kind": "ref", "name": "v1"}
    # The same commit by its full id: already held, no new directory.
    code, out = run(
        capsys, "clone", "thing", "--ref", thing["first"], catalog_file=catalog_file
    )
    assert code == 0, out
    assert out.startswith(f"held thing {thing['first'][:7]}")
    assert len(_tree_dirs(library, "thing")) == 1
    # A different commit by its full id: a second directory.
    code, out = run(
        capsys, "clone", "thing", "--ref", thing["second"], catalog_file=catalog_file
    )
    assert code == 0, out
    assert out.startswith(f"cloned thing {thing['second'][:7]}")
    assert len(_tree_dirs(library, "thing")) == 2


@needs_git
def test_force_supersedes_the_older_tree_and_keeps_it(
    library, catalog_file, remotes, capsys
):
    thing = remotes["thing"]
    run(capsys, "clone", "thing", catalog_file=catalog_file)
    old_sha = thing["second"]
    # No --force: the moving name is not re-resolved even when it moved.
    third = commit(thing["work"], {"README.md": "v3\n"}, "third")
    push(thing["work"])
    code, out = run(capsys, "clone", "thing", catalog_file=catalog_file)
    assert code == 0 and out.startswith(f"held thing {old_sha[:7]}")
    # --force: a new directory, the older one marked superseded, never deleted.
    code, out = run(capsys, "clone", "thing", "--force", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"cloned thing {third[:7]} (main ")
    assert any(ln.startswith(f"superseded thing {old_sha[:7]}") for ln in lines), out
    old_dir = library / "code" / "thing" / old_sha
    new_dir = library / "code" / "thing" / third
    assert old_dir.is_dir() and (old_dir / "src" / "main.cpp").is_file()
    assert new_dir.is_dir() and (new_dir / "README.md").is_file()
    old_meta = json.loads((old_dir / TREE_META).read_text("utf-8"))
    new_meta = json.loads((new_dir / TREE_META).read_text("utf-8"))
    assert old_meta["superseded_by"] == third
    assert "superseded_by" not in new_meta
    # --force when the branch did not move: still exit 0, still two trees.
    code, out = run(capsys, "clone", "thing", "--force", catalog_file=catalog_file)
    assert code == 0, out
    assert len(_tree_dirs(library, "thing")) == 2


@needs_git
def test_failed_clone_is_exit_2_with_gits_last_line_and_no_half_directory(
    library, catalog_file, remotes, capsys
):
    code, out = run(capsys, "clone", "thing", "--ref", "no-such-ref", catalog_file=catalog_file)
    assert code == 2
    assert out.startswith("git clone failed: "), out
    assert len(out.strip().splitlines()) == 1  # one message line, not a traceback
    assert out.strip() != "git clone failed:"  # git's own last line follows
    assert _tree_dirs(library, "thing") == []
    # A remote that does not exist at all.
    code, out = run(capsys, "clone", "openbmc", "--ref", "zzz", catalog_file=catalog_file)
    assert code == 2 and "failed" in out
    assert _tree_dirs(library, "openbmc") == []


def test_git_missing_is_exit_2_for_clone_and_grep(library, plain_catalog, capsys, monkeypatch):
    monkeypatch.setattr(code_mod.shutil, "which", lambda name: None)
    # Repositories from a catalog that has no [[repos]] cannot be found; use
    # a catalog with one so the git check is what fails.
    path = plain_catalog.with_name("c.toml")
    path.write_text(
        MINI_CATALOG
        + '\n[[repos]]\nid = "thing"\nurl = "https://example.test/thing.git"\n'
        'topics = ["x"]\n',
        encoding="utf-8",
        newline="",
    )
    code, out = run(capsys, "clone", "thing", catalog_file=path)
    assert code == 2
    assert "git" in out.lower() and "path" in out.lower()


# ------------------------------------------------------------------ AC-1


@needs_git
def test_repos_lists_held_trees_user_checkout_and_config_release(
    library, catalog_file, remotes, capsys
):
    thing = remotes["thing"]
    code, out = run(capsys, "repos", catalog_file=catalog_file)
    assert code == 0
    lines = out.splitlines()
    assert len(lines) == 2  # one line per catalog repository, nothing else
    assert lines[0].startswith("openbmc") and lines[1].startswith("thing")
    for ln in lines:
        assert "\t-\t-\t" in ln  # no trees held, no user checkout
    assert lines[1].endswith("power, state")
    # Held trees appear as `<commit7> <provenance>`.
    run(capsys, "clone", "thing", catalog_file=catalog_file)
    run(capsys, "clone", "thing", "--release", "1.0.0", catalog_file=catalog_file)
    code, out = run(capsys, "repos", "--topic", "state", catalog_file=catalog_file)
    assert code == 0
    assert out.count("\n") == 1
    assert f"{thing['second'][:7]} main " in out
    assert f"{thing['first'][:7]} release 1.0.0" in out
    # A user checkout and a default Release from config.toml.
    library.mkdir(exist_ok=True)
    (library / "config.toml").write_text(
        '[code]\nrelease = "1.0.0"\n'
        f'[code.checkouts]\nthing = "{thing["work"].as_posix()}"\n',
        encoding="utf-8",
    )
    code, out = run(capsys, "repos", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    ob_dirs = _tree_dirs(library, "openbmc")
    assert len(ob_dirs) == 1
    assert lines[0] == f"release: 1.0.0 (config.toml) -> openbmc {ob_dirs[0].name[:7]}"
    thing_line = next(ln for ln in lines if ln.startswith("thing\t"))
    assert "user checkout: " in thing_line
    assert str(thing["work"]) in thing_line


# ------------------------------------------------------------------ AC-7


def _scripted_gh(monkeypatch, *, returncode=0, stdout="", stderr=""):
    """gh on PATH, answering every call with the given result; records argv."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((list(cmd), kwargs))
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

    monkeypatch.setattr(
        code_mod.shutil, "which", lambda name: "gh" if name == "gh" else None
    )
    monkeypatch.setattr(code_mod.subprocess, "run", fake_run)
    return calls


def test_repos_search_prints_repo_and_path_per_hit(
    library, plain_catalog, capsys, monkeypatch
):
    hits = [
        {
            "repository": {"nameWithOwner": "openbmc/bmcweb"},
            "path": "redfish-core/lib/chassis.hpp",
        },
        {"repository": {"nameWithOwner": "openbmc/pldm"}, "path": "src/a.cpp"},
    ]
    calls = _scripted_gh(monkeypatch, stdout=json.dumps(hits))
    code, out = run(
        capsys, "repos", "--search", "CurrentPowerState", catalog_file=plain_catalog
    )
    assert code == 0, out
    lines = out.splitlines()
    notes = [ln for ln in lines if ln.startswith("note:")]
    assert notes and "default branch" in notes[0]
    assert "openbmc/bmcweb redfish-core/lib/chassis.hpp" in lines
    assert "openbmc/pldm src/a.cpp" in lines
    # gh search code PATTERN --owner openbmc --limit 20
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[1:3] == ["search", "code"]
    assert "CurrentPowerState" in argv
    assert argv[argv.index("--owner") + 1] == "openbmc"
    assert argv[argv.index("--limit") + 1] == "20"
    assert kwargs.get("encoding", "").lower().replace("-", "") == "utf8"
    assert kwargs.get("errors") == "replace"


def test_repos_search_no_hits(library, plain_catalog, capsys, monkeypatch):
    _scripted_gh(monkeypatch, stdout="[]")
    code, out = run(capsys, "repos", "--search", "zzz", catalog_file=plain_catalog)
    assert code == 0
    assert "no hits" in out


def test_repos_search_without_gh_or_not_logged_in_is_exit_2(
    library, plain_catalog, capsys, monkeypatch
):
    monkeypatch.setattr(code_mod.shutil, "which", lambda name: None)
    code, out = run(capsys, "repos", "--search", "x", catalog_file=plain_catalog)
    assert code == 2
    assert "gh" in out
    # gh present but not logged in: gh exits non-zero and says to log in.
    _scripted_gh(
        monkeypatch,
        returncode=4,
        stderr="To get started with GitHub CLI, please run:  gh auth login\n",
    )
    code, out = run(capsys, "repos", "--search", "x", catalog_file=plain_catalog)
    assert code == 2
    assert "gh" in out and "auth login" in out


# ------------------------------------------------------------------ AC-8


def test_code_module_is_standard_library_only():
    src = (ROOT / "bmc_toolkit" / "spec" / "code.py").read_text("utf-8")
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    outside = {
        name
        for name in imported
        if name != "bmc_toolkit" and name not in sys.stdlib_module_names
    }
    assert not outside, f"third-party imports in code.py: {sorted(outside)}"


def test_git_subprocess_uses_utf8_replace_and_never_prompts(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = list(cmd)
        seen.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, "git version 2.x\n", "")

    monkeypatch.setattr(code_mod.shutil, "which", lambda name: "git")
    monkeypatch.setattr(code_mod.subprocess, "run", fake_run)
    code_mod.run_git(["--version"])
    assert seen["cmd"][-1] == "--version"
    assert seen["encoding"].lower().replace("-", "") == "utf8"
    assert seen["errors"] == "replace"
    assert seen["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_author_tests_skip_without_git():
    import tests.test_code as unit
    import tests.test_code_cli as cli_tests

    for module in (unit, cli_tests):
        marks = module.pytestmark
        marks = marks if isinstance(marks, list) else [marks]
        assert any(m.name == "skipif" for m in marks), module.__name__


def test_readme_lists_git_and_gh_as_subprocesses():
    text = (ROOT / "README.md").read_text("utf-8")
    start = text.index("## What the tool does on the network and on disk")
    end = text.find("\n## ", start + 1)
    section = text[start : end if end > 0 else None]
    assert "`git`" in section
    assert "gh" in section
    assert "subprocess" in section
    assert "code/" in section  # where clone writes


# ------------------------------------------------------------------ AC-9


def test_readme_documents_commands_layout_and_config():
    # since 1.0.0 the README keeps the command examples; the Library layout
    # is in docs/LIBRARY.md and config.toml in docs/COMMANDS.md
    readme = (ROOT / "README.md").read_text("utf-8")
    for cmd in ("bmcspec repos", "bmcspec clone", "bmcspec grep", "bmcspec code"):
        assert cmd in readme, cmd
    assert "code/<repo>/<commit>/" in readme
    layout = (ROOT / "docs" / "LIBRARY.md").read_text("utf-8")
    assert "code/<repo>/<commit>/" in layout
    assert ".bmc-tree.json" in layout
    commands = (ROOT / "docs" / "COMMANDS.md").read_text("utf-8")
    assert "[code]" in commands and "release =" in commands
    assert "[code.checkouts]" in commands
    assert "--release" in commands and "--ref" in commands and "--force" in commands


def test_skill_documents_vocabulary_commands_workflow_and_citation():
    text = (ROOT / "skills" / "bmc-spec" / "SKILL.md").read_text("utf-8")
    for term in ("**Code Tree**", "**Ref**", "**Release**", "**Pin**"):
        assert term in text, term
    for row in ("| `repos", "| `clone REPO", "| `grep REPO", "| `code REPO"):
        assert row in text, row
    assert "## Code workflow" in text
    assert "## Two-part answers" in text
    assert "cite: code" in text
    assert "user checkout" in text
    assert "release 2.18.0" in text
    # The old placeholder is gone.
    assert "arrive in a\nlater milestone" not in text
    assert "later milestone" not in text

"""Acceptance tests for the change that keeps the default-branch mark with
the branch it names. A ``--release`` tree marked ``default_branch`` and
superseded by a re-pin of a release that shares the branch's name becomes
the default tree instead of handing the mark to the new pin (AC-1); a newer
``--ref`` tree of the marked branch itself still takes the mark over
(AC-2). Everything goes through the CLI against local bare repositories;
skipped when git is not on PATH.

The repository's default branch and the openbmc release are both called
``master`` in every test here: that is the collision the change is about.
"""

import json
import shutil

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import RECIPE, RECIPE_URL, THING_FILES, commit, git, make_repo, push

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

RECIPE_PATH = "meta-phosphor/recipes-phosphor/things/thing_git.bb"
BRANCH = "master"  # thing's default branch and the release share this name


def run(capsys, catalog_file, *argv):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def _refuse(*args, **kwargs):
    raise AssertionError(f"git must not run: {args}")


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


@pytest.fixture
def repo(tmp_path):
    """thing, default branch master: c1 then c2."""
    (tmp_path / "remote").mkdir()
    work, bare, url = make_repo(tmp_path / "remote", "thing", THING_FILES, branch=BRANCH)
    c1 = git("rev-parse", "HEAD", cwd=work)
    c2 = commit(work, {"README.md": "thing 2\n"}, "second")
    push(work, BRANCH)
    return {"work": work, "bare": bare, "url": url, "c1": c1, "c2": c2}


@pytest.fixture
def openbmc(tmp_path, repo):
    """openbmc on branch master whose recipe pins thing at c1."""
    recipe = RECIPE.format(url=RECIPE_URL, sha=repo["c1"])
    files = {RECIPE_PATH: recipe, "README.md": "distro\n"}
    work, _bare, url = make_repo(tmp_path / "remote", "openbmc", files, branch="master")
    return {"work": work, "url": url}


def _repin(openbmc, sha):
    recipe = RECIPE.format(url=RECIPE_URL, sha=sha)
    commit(openbmc["work"], {RECIPE_PATH: recipe}, f"pin thing at {sha[:7]}")
    push(openbmc["work"], "master")


def _catalog(tmp_path, repo, openbmc=None):
    text = MINI_CATALOG + (
        f'\n[[repos]]\nid = "thing"\nurl = "{repo["url"]}"\ntopics = ["power"]\n'
    )
    if openbmc:
        text += (
            f'\n[[repos]]\nid = "openbmc"\nurl = "{openbmc["url"]}"\n'
            'topics = ["release"]\nsparse = ["meta-phosphor"]\n'
        )
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def _tree_dir(library, sha):
    return library / "code" / "thing" / sha


def _meta(library, sha):
    path = _tree_dir(library, sha) / code_mod.TREE_META
    return json.loads(path.read_text("utf-8"))


def _superseded_lines(out):
    return [ln for ln in out.splitlines() if ln.startswith("superseded ")]


def _would_remove(out, library):
    mine = str(library / "code" / "thing")
    return [
        ln
        for ln in out.splitlines()
        if ln.startswith("would remove ") and mine in ln
    ]


def _reset_branch(work, sha):
    git("reset", "-q", "--hard", sha, cwd=work)
    git("push", "-q", "-f", "origin", BRANCH, cwd=work)


def _branch_commit(work, name, files, message) -> str:
    """A commit on a new branch off the current HEAD, pushed; HEAD returns
    to the default branch afterwards."""
    git("checkout", "-q", "-b", name, cwd=work)
    sha = commit(work, files, message)
    push(work, name)
    git("checkout", "-q", BRANCH, cwd=work)
    return sha


def _mark_release_tree(capsys, catalog, library, repo):
    """The AC-1 setup: thing held at c2 (default) and at c1 (release
    master); master moves back to c1, so a plain --force lands on the
    release tree and marks it. Returns nothing; asserts the mark."""
    c1, c2 = repo["c1"], repo["c2"]
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} ({BRANCH} ")
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master")
    assert code == 0 and f"cloned thing {c1[:7]} (release master)" in out

    _reset_branch(repo["work"], c1)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"held thing {c1[:7]} (release master)"), out
    assert lines[1].startswith(f"superseded thing {c2[:7]} ({BRANCH} "), out
    meta = _meta(library, c1)
    assert meta["provenance"]["kind"] == "release"
    assert meta["provenance"]["name"] == "master"
    assert meta["default_branch"] == BRANCH
    assert _meta(library, c2)["superseded_by"] == c1


# ------------------------------------------------------------ AC-1


def test_ac1_a_repin_of_a_release_named_like_the_branch_leaves_the_default_tree(
    library, repo, openbmc, capsys, tmp_path, monkeypatch
):
    # release master re-pins to a commit on another branch while thing's
    # master stays at c1: the marked release tree is the tree master
    # resolved to, so it becomes the default tree; the new pin is a plain
    # release tree; nothing is superseded
    work, c1, c2 = repo["work"], repo["c1"], repo["c2"]
    catalog = _catalog(tmp_path, repo, openbmc)
    _mark_release_tree(capsys, catalog, library, repo)

    c3 = _branch_commit(work, "dev", {"README.md": "thing dev\n"}, "dev")
    _repin(openbmc, c3)
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master", "--force")
    assert code == 0, out
    assert f"cloned thing {c3[:7]} (release master)" in out
    assert _superseded_lines(out) == [], out

    meta = _meta(library, c1)
    assert meta["provenance"] == {"kind": "default", "name": BRANCH}
    assert "default_branch" not in meta
    assert "superseded_by" not in meta
    meta = _meta(library, c3)
    assert meta["provenance"]["kind"] == "release"
    assert meta["provenance"]["name"] == "master"
    assert "default_branch" not in meta
    assert "superseded_by" not in meta
    assert _meta(library, c2)["superseded_by"] == c1  # untouched by the re-pin

    # the next plain clone is answered by c1 without git, and prints nothing
    # else; reading commands without a flag use c1, with --release use c3
    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    assert out.startswith(f"held thing {c1[:7]} ({BRANCH} "), out
    assert len(out.splitlines()) == 1, out
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0, out
    assert out.startswith(f"cite: code | thing {c1[:7]} | {BRANCH} "), out
    assert out.splitlines()[1:] == ["1  thing"]
    code, out = run(capsys, catalog, "code", "thing", "README.md", "--release", "master")
    assert code == 0, out
    assert out.startswith(f"cite: code | thing {c3[:7]} | release master"), out
    assert out.splitlines()[1:] == ["1  thing dev"]
    code, out = run(capsys, catalog, "grep", "thing", "CurrentPowerState")
    assert code == 0, out
    assert out.startswith(f"thing@{c1[:7]} src/state.hpp:1 | // CurrentPowerState")

    # prune lists only the tree the plain --force superseded earlier
    code, out = run(capsys, catalog, "prune")
    assert code == 0, out
    listed = _would_remove(out, library)
    assert len(listed) == 1 and str(_tree_dir(library, c2)) in listed[0], out
    assert str(_tree_dir(library, c1)) not in out
    assert str(_tree_dir(library, c3)) not in out

    # repos shows c1 and c3 current, c2 superseded
    code, out = run(capsys, catalog, "repos", "--topic", "power")
    assert code == 0, out
    held = out.splitlines()[0].split("\t")[1].split("; ")
    by_commit = {h.split(" ", 1)[0]: h for h in held}
    assert not by_commit[c1[:7]].endswith(" superseded"), out
    assert not by_commit[c3[:7]].endswith(" superseded"), out
    assert by_commit[c2[:7]].endswith(" superseded"), out


def test_ac1_the_default_tree_the_repin_left_is_the_branch_tree_afterwards(
    library, repo, openbmc, capsys, tmp_path
):
    # after the AC-1 re-pin, master moves on: the plain --force fetches the
    # new commit and supersedes c1 as the ordinary default tree it now is,
    # and the release tree c3 stays current under its release
    work, c1 = repo["work"], repo["c1"]
    catalog = _catalog(tmp_path, repo, openbmc)
    _mark_release_tree(capsys, catalog, library, repo)
    c3 = _branch_commit(work, "dev", {"README.md": "thing dev\n"}, "dev")
    _repin(openbmc, c3)
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master", "--force")
    assert code == 0 and _superseded_lines(out) == [], out
    assert _meta(library, c1)["provenance"] == {"kind": "default", "name": BRANCH}

    c4 = commit(work, {"README.md": "thing 4\n"}, "fourth")
    push(work, BRANCH)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"cloned thing {c4[:7]} ({BRANCH} "), out
    assert lines[1].startswith(f"superseded thing {c1[:7]} ({BRANCH} "), out
    assert len(lines) == 2, out
    assert _meta(library, c1)["superseded_by"] == c4
    meta = _meta(library, c3)
    assert meta["provenance"]["kind"] == "release"
    assert "superseded_by" not in meta and "default_branch" not in meta
    code, out = run(capsys, catalog, "code", "thing", "README.md", "--release", "master")
    assert code == 0 and out.startswith(f"cite: code | thing {c3[:7]} | release master")


# ------------------------------------------------------------ AC-2


def test_ac2_a_newer_ref_tree_of_the_marked_branch_takes_the_mark_over(
    library, repo, capsys, tmp_path, monkeypatch
):
    # a --ref master tree the plain clone marked; master moves and
    # `--ref master --force` fetches the new commit: the older tree is
    # superseded and unmarked, the new one carries the mark and answers the
    # next plain clone without git (behaviour kept from PR #46)
    work, c2 = repo["work"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", BRANCH)
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} ({BRANCH} ")
    code, out = run(capsys, catalog, "clone", "thing")  # resolves online, marks c2
    assert code == 0 and out.startswith(f"held thing {c2[:7]} ({BRANCH} "), out
    meta = _meta(library, c2)
    assert meta["provenance"] == {"kind": "ref", "name": BRANCH}
    assert meta["default_branch"] == BRANCH

    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work, BRANCH)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", BRANCH, "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"cloned thing {c3[:7]} ({BRANCH} "), out
    assert lines[1].startswith(f"superseded thing {c2[:7]} ({BRANCH} "), out
    assert len(lines) == 2, out
    meta = _meta(library, c2)
    assert meta["superseded_by"] == c3
    assert "default_branch" not in meta
    meta = _meta(library, c3)
    assert meta["provenance"] == {"kind": "ref", "name": BRANCH}
    assert meta["default_branch"] == BRANCH
    assert "superseded_by" not in meta

    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    assert out.startswith(f"held thing {c3[:7]} ({BRANCH} "), out
    assert len(out.splitlines()) == 1, out
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c3[:7]} | {BRANCH} ")
    assert out.splitlines()[1:] == ["1  thing 3"]
    code, out = run(capsys, catalog, "prune")
    assert code == 0, out
    listed = _would_remove(out, library)
    assert len(listed) == 1 and str(_tree_dir(library, c2)) in listed[0], out


def test_ac2_a_plain_force_that_fetches_supersedes_the_marked_ref_tree(
    library, repo, capsys, tmp_path
):
    # the same from the default side: the marked --ref master tree is the
    # older tree of the branch a plain --force re-resolves, so it is
    # superseded, not turned into a second default tree
    work, c2 = repo["work"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", BRANCH)
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} ({BRANCH} ")
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"held thing {c2[:7]} ({BRANCH} "), out
    assert _meta(library, c2)["default_branch"] == BRANCH

    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work, BRANCH)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"cloned thing {c3[:7]} ({BRANCH} "), out
    assert lines[1].startswith(f"superseded thing {c2[:7]} ({BRANCH} "), out
    assert len(lines) == 2, out
    meta = _meta(library, c2)
    assert meta["superseded_by"] == c3
    assert "default_branch" not in meta
    assert _meta(library, c3)["provenance"] == {"kind": "default", "name": BRANCH}

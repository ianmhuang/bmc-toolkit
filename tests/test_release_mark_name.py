"""The default-branch mark follows the branch it names: a --release tree
marked with the default branch, superseded by a re-pin of a release that
shares the branch's name, becomes the default tree (AC-1); a newer tree of
the marked branch itself still takes the mark over (AC-2). Everything goes
through the CLI against local bare repositories; skipped when git is not on
PATH."""

import json
import shutil

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import (
    RECIPE,
    RECIPE_URL,
    THING_FILES,
    commit,
    git,
    make_repo,
    push,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

RECIPE_PATH = "meta-phosphor/recipes-phosphor/things/thing_git.bb"


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
    work, bare, url = make_repo(
        tmp_path / "remote", "thing", THING_FILES, branch="master"
    )
    c1 = git("rev-parse", "HEAD", cwd=work)
    c2 = commit(work, {"README.md": "thing 2\n"}, "second")
    push(work, "master")
    return {"work": work, "bare": bare, "url": url, "c1": c1, "c2": c2}


@pytest.fixture
def openbmc(tmp_path, repo):
    """openbmc on branch master, whose recipe pins thing at c1."""
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


def _meta(library, sha):
    path = library / "code" / "thing" / sha / code_mod.TREE_META
    return json.loads(path.read_text("utf-8"))


def _superseded_lines(out):
    return [ln for ln in out.splitlines() if ln.startswith("superseded ")]


# ------------------------------------------------------------ AC-1


def test_ac1_a_repinned_release_named_like_the_default_branch_leaves_the_default(
    library, repo, openbmc, capsys, tmp_path, monkeypatch
):
    # thing's default branch and the openbmc release are both called master;
    # a plain --force marks the release tree, then the release re-pins to a
    # commit on another branch while thing's master stays at c1
    work, c1, c2 = repo["work"], repo["c1"], repo["c2"]
    catalog = _catalog(tmp_path, repo, openbmc)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (master ")
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master")
    assert code == 0 and f"cloned thing {c1[:7]} (release master)" in out

    git("reset", "-q", "--hard", c1, cwd=work)
    git("push", "-q", "-f", "origin", "master", cwd=work)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    assert out.startswith(f"held thing {c1[:7]} (release master)")
    meta = _meta(library, c1)
    assert meta["provenance"]["kind"] == "release"
    assert meta["default_branch"] == "master"

    git("checkout", "-q", "-b", "dev", cwd=work)
    c3 = commit(work, {"README.md": "thing dev\n"}, "dev")
    push(work, "dev")
    _repin(openbmc, c3)
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master", "--force")
    assert code == 0, out
    assert f"cloned thing {c3[:7]} (release master)" in out
    assert _superseded_lines(out) == [], out
    meta = _meta(library, c1)
    assert meta["provenance"] == {"kind": "default", "name": "master"}
    assert "default_branch" not in meta and "superseded_by" not in meta
    meta = _meta(library, c3)
    assert meta["provenance"]["kind"] == "release"
    assert meta["provenance"]["name"] == "master"
    assert "default_branch" not in meta and "superseded_by" not in meta

    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    assert out.startswith(f"held thing {c1[:7]} (master ")
    assert len(out.splitlines()) == 1, out
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c1[:7]} | master ")
    assert out.splitlines()[1:] == ["1  thing"]


# ------------------------------------------------------------ AC-2


def test_ac2_a_newer_ref_tree_of_the_marked_branch_takes_the_mark(
    library, repo, capsys, tmp_path, monkeypatch
):
    # a --ref master tree a plain clone marked: master moves and
    # `--ref master --force` fetches it, so the mark moves with the branch
    work, c2 = repo["work"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "master")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (master ")
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"held thing {c2[:7]} (master ")
    assert _meta(library, c2)["default_branch"] == "master"

    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work, "master")
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "master", "--force")
    assert code == 0, out
    assert out.startswith(f"cloned thing {c3[:7]} (master ")
    meta = _meta(library, c2)
    assert meta["superseded_by"] == c3
    assert "default_branch" not in meta
    meta = _meta(library, c3)
    assert meta["provenance"] == {"kind": "ref", "name": "master"}
    assert meta["default_branch"] == "master"
    assert "superseded_by" not in meta

    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    assert out.startswith(f"held thing {c3[:7]} (master ")
    assert len(out.splitlines()) == 1, out

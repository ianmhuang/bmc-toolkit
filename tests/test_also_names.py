"""A --ref or --release that lands on a commit held under another name
records that name on the held tree (``also``): grep and code with the same
flag read it and cite the name asked (AC-1 to AC-4); a tree that still
answers a name is not superseded when another of its names moves (AC-5);
repos lists the names (AC-6). Everything goes through the CLI against local
bare repositories; skipped when git is not on PATH."""

import json
import shutil
from pathlib import Path

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
    make_scenario,
    push,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

RECIPE_PATH = "meta-phosphor/recipes-phosphor/things/thing_git.bb"


def run(capsys, catalog_file, *argv):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def _refuse(*args, **kwargs):
    raise AssertionError(f"git must not run: {args}")


def run_offline(capsys, monkeypatch, catalog_file, *argv):
    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        return run(capsys, catalog_file, *argv)


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


def _build_thing(root):
    (root / "remote").mkdir(exist_ok=True)
    work, bare, url = make_repo(root / "remote", "thing", THING_FILES, branch="master")
    c1 = git("rev-parse", "HEAD", cwd=work)
    c2 = commit(work, {"README.md": "thing 2\n"}, "second")
    push(work, "master")
    return {"work": work, "bare": bare, "url": url, "c1": c1, "c2": c2}


@pytest.fixture
def repo(tmp_path):
    """thing, default branch master: c1 then c2."""
    return make_scenario(tmp_path, "also-names-repo", _build_thing)


@pytest.fixture
def openbmc(tmp_path, repo):
    """openbmc on branch master, whose recipe pins thing at c1."""
    recipe = RECIPE.format(url=RECIPE_URL, sha=repo["c1"])
    files = {RECIPE_PATH: recipe, "README.md": "distro\n"}
    work, _bare, url = make_repo(tmp_path / "remote", "openbmc", files, branch="master")
    return {"work": work, "url": url}


@pytest.fixture
def catalog(tmp_path, repo, openbmc):
    text = MINI_CATALOG + (
        f'\n[[repos]]\nid = "thing"\nurl = "{repo["url"]}"\ntopics = ["power"]\n'
        f'\n[[repos]]\nid = "openbmc"\nurl = "{openbmc["url"]}"\n'
        'topics = ["release"]\nsparse = ["meta-phosphor"]\n'
    )
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def _repin(openbmc, sha):
    recipe = RECIPE.format(url=RECIPE_URL, sha=sha)
    commit(openbmc["work"], {RECIPE_PATH: recipe}, f"pin thing at {sha[:7]}")
    push(openbmc["work"], "master")


def _dev(repo, text="thing dev\n"):
    """A commit on branch dev of thing, pushed; its sha."""
    work = repo["work"]
    if git("branch", "--list", "dev", cwd=work):
        git("checkout", "-q", "dev", cwd=work)
    else:
        git("checkout", "-q", "-b", "dev", cwd=work)
    sha = commit(work, {"README.md": text}, "dev")
    push(work, "dev")
    return sha


def _tag(repo, name, sha):
    git("tag", name, sha, cwd=repo["work"])
    git("push", "-q", "origin", name, cwd=repo["work"])


def _meta(library, sha):
    path = library / "code" / "thing" / sha / code_mod.TREE_META
    return json.loads(path.read_text("utf-8"))


def _openbmc_head(openbmc):
    return git("rev-parse", "HEAD", cwd=openbmc["work"])


def _cite(out):
    """repository/commit and provenance fields of the cite: line."""
    fields = out.splitlines()[0].split(" | ")
    assert fields[0] == "cite: code", out
    return fields[1], fields[2]


def _superseded_lines(out):
    return [ln for ln in out.splitlines() if ln.startswith("superseded ")]


# ------------------------------------------------------------ AC-1


def test_ac1_a_release_landing_on_a_ref_tree_is_recorded_on_it(
    library, repo, openbmc, catalog, capsys, monkeypatch
):
    c3 = _dev(repo)
    _repin(openbmc, c3)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "dev")
    assert code == 0 and out.startswith(f"cloned thing {c3[:7]} (dev ")

    code, out = run(capsys, catalog, "clone", "thing", "--release", "master")
    assert code == 0, out
    assert f"held thing {c3[:7]} (dev " in out
    assert f"pin: {c3[:7]} from {RECIPE_PATH}" in out
    meta = _meta(library, c3)
    assert meta["provenance"] == {"kind": "ref", "name": "dev"}
    assert meta["also"] == [
        {"kind": "release", "name": "master", "openbmc_commit": _openbmc_head(openbmc)}
    ]

    code, out = run(
        capsys, catalog, "code", "thing", "README.md", "--release", "master"
    )
    assert code == 0, out
    assert _cite(out) == (f"thing {c3[:7]}", "release master")
    assert out.splitlines()[1:] == ["1  thing dev"]

    code, out = run_offline(
        capsys, monkeypatch, catalog, "clone", "thing", "--release", "master"
    )
    assert code == 0, out
    assert f"held thing {c3[:7]} (dev " in out
    assert _meta(library, c3)["also"] == meta["also"]


# ------------------------------------------------------------ AC-2


def test_ac2_a_release_landing_on_the_default_tree_keeps_it_the_default(
    library, repo, openbmc, catalog, capsys, monkeypatch
):
    c2 = repo["c2"]
    _repin(openbmc, c2)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (master ")

    code, out = run(capsys, catalog, "clone", "thing", "--release", "master")
    assert code == 0, out
    assert f"held thing {c2[:7]} (master " in out
    meta = _meta(library, c2)
    assert meta["provenance"] == {"kind": "default", "name": "master"}
    assert [(a["kind"], a["name"]) for a in meta["also"]] == [("release", "master")]

    code, out = run(
        capsys, catalog, "code", "thing", "README.md", "--release", "master"
    )
    assert code == 0, out
    assert _cite(out) == (f"thing {c2[:7]}", "release master")
    code, out = run_offline(
        capsys, monkeypatch, catalog, "clone", "thing", "--release", "master"
    )
    assert code == 0 and f"held thing {c2[:7]} (master " in out

    code, out = run_offline(capsys, monkeypatch, catalog, "clone", "thing")
    assert code == 0, out
    assert out.startswith(f"held thing {c2[:7]} (master ")
    assert len(out.splitlines()) == 1, out
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0, out
    who, how = _cite(out)
    assert who == f"thing {c2[:7]}" and how.startswith("master ")


# ------------------------------------------------------------ AC-3


def test_ac3_a_forced_repin_onto_a_held_tree_supersedes_the_old_release_tree(
    library, repo, openbmc, catalog, capsys
):
    c1 = repo["c1"]
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master")
    assert code == 0 and f"cloned thing {c1[:7]} (release master)" in out
    c3 = _dev(repo)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "dev")
    assert code == 0 and out.startswith(f"cloned thing {c3[:7]} (dev ")

    _repin(openbmc, c3)
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master", "--force")
    assert code == 0, out
    assert f"held thing {c3[:7]} (dev " in out
    assert _superseded_lines(out) == [f"superseded thing {c1[:7]} (release master)"]
    assert _meta(library, c1)["superseded_by"] == c3
    meta = _meta(library, c3)
    assert [(a["kind"], a["name"]) for a in meta["also"]] == [("release", "master")]
    assert meta["also"][0]["openbmc_commit"] == _openbmc_head(openbmc)
    assert "superseded_by" not in meta

    code, out = run(
        capsys, catalog, "code", "thing", "README.md", "--release", "master"
    )
    assert code == 0, out
    assert _cite(out) == (f"thing {c3[:7]}", "release master")


# ------------------------------------------------------------ AC-4


def test_ac4_a_ref_landing_on_a_release_tree_is_recorded_on_it(
    library, repo, openbmc, catalog, capsys, monkeypatch
):
    c1 = repo["c1"]
    _tag(repo, "v1", c1)
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master")
    assert code == 0 and f"cloned thing {c1[:7]} (release master)" in out

    code, out = run(capsys, catalog, "clone", "thing", "--ref", "v1")
    assert code == 0, out
    assert out.startswith(f"held thing {c1[:7]} (release master)")
    meta = _meta(library, c1)
    assert meta["provenance"]["kind"] == "release"
    assert meta["also"] == [{"kind": "ref", "name": "v1"}]

    code, out = run(capsys, catalog, "code", "thing", "README.md", "--ref", "v1")
    assert code == 0, out
    assert _cite(out) == (f"thing {c1[:7]}", f"v1 {meta['fetched_at'][:10]}")
    code, out = run_offline(
        capsys, monkeypatch, catalog, "clone", "thing", "--ref", "v1"
    )
    assert code == 0 and out.startswith(f"held thing {c1[:7]} (release master)")


def test_ac4_a_ref_landing_on_the_default_tree_is_recorded_on_it(
    library, repo, catalog, capsys, monkeypatch
):
    c2 = repo["c2"]
    _tag(repo, "v2", c2)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (master ")

    code, out = run(capsys, catalog, "clone", "thing", "--ref", "v2")
    assert code == 0, out
    assert out.startswith(f"held thing {c2[:7]} (master ")
    meta = _meta(library, c2)
    assert meta["provenance"] == {"kind": "default", "name": "master"}
    assert meta["also"] == [{"kind": "ref", "name": "v2"}]

    code, out = run(capsys, catalog, "code", "thing", "README.md", "--ref", "v2")
    assert code == 0, out
    assert _cite(out) == (f"thing {c2[:7]}", f"v2 {meta['fetched_at'][:10]}")
    code, out = run_offline(
        capsys, monkeypatch, catalog, "clone", "thing", "--ref", "v2"
    )
    assert code == 0 and out.startswith(f"held thing {c2[:7]} (master ")
    code, out = run_offline(capsys, monkeypatch, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"held thing {c2[:7]} (master ")


def test_ac4_the_tree_s_own_commit_as_ref_is_not_recorded(
    library, repo, catalog, capsys
):
    c2 = repo["c2"]
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0
    code, out = run(capsys, catalog, "clone", "thing", "--ref", c2)
    assert code == 0 and out.startswith(f"held thing {c2[:7]} (master ")
    code, out = run(capsys, catalog, "clone", "thing", "--ref", c2[:7])
    assert code == 0 and out.startswith(f"held thing {c2[:7]} (master ")
    assert "also" not in _meta(library, c2)


# ------------------------------------------------------------ AC-5


def _dev_with_release(library, repo, openbmc, catalog, capsys):
    """thing held at c3 under --ref dev, also release master; c3."""
    c3 = _dev(repo)
    _repin(openbmc, c3)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "dev")
    assert code == 0, out
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master")
    assert code == 0 and f"held thing {c3[:7]} (dev " in out
    also = _meta(library, c3).get("also", [])
    assert [(a["kind"], a["name"]) for a in also] == [("release", "master")]
    return c3


def test_ac5_a_moved_own_name_hands_the_tree_its_other_name(
    library, repo, openbmc, catalog, capsys
):
    c3 = _dev_with_release(library, repo, openbmc, catalog, capsys)
    c4 = _dev(repo, "thing dev 2\n")
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "dev", "--force")
    assert code == 0, out
    assert out.startswith(f"cloned thing {c4[:7]} (dev ")
    assert _superseded_lines(out) == [], out
    meta = _meta(library, c3)
    assert meta["provenance"]["kind"] == "release"
    assert meta["provenance"]["name"] == "master"
    assert "also" not in meta and "superseded_by" not in meta

    code, out = run(
        capsys, catalog, "code", "thing", "README.md", "--release", "master"
    )
    assert code == 0 and _cite(out) == (f"thing {c3[:7]}", "release master")
    code, out = run(capsys, catalog, "code", "thing", "README.md", "--ref", "dev")
    assert code == 0, out
    who, how = _cite(out)
    assert who == f"thing {c4[:7]}" and how.startswith("dev ")


def test_ac5_a_moved_also_name_leaves_the_tree_and_nothing_else(
    library, repo, openbmc, catalog, capsys
):
    c3 = _dev_with_release(library, repo, openbmc, catalog, capsys)
    c1 = repo["c1"]
    _repin(openbmc, c1)
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master", "--force")
    assert code == 0, out
    assert f"cloned thing {c1[:7]} (release master)" in out
    assert _superseded_lines(out) == [], out
    meta = _meta(library, c3)
    assert meta["provenance"] == {"kind": "ref", "name": "dev"}
    assert "also" not in meta and "superseded_by" not in meta

    code, out = run(
        capsys, catalog, "code", "thing", "README.md", "--release", "master"
    )
    assert code == 0 and _cite(out) == (f"thing {c1[:7]}", "release master")


def test_ac5_a_tree_with_no_name_left_is_superseded(
    library, repo, openbmc, catalog, capsys
):
    c3 = _dev_with_release(library, repo, openbmc, catalog, capsys)
    c1 = repo["c1"]
    _repin(openbmc, c1)
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master", "--force")
    assert code == 0, out
    c4 = _dev(repo, "thing dev 2\n")
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "dev", "--force")
    assert code == 0, out
    assert _superseded_lines(out) == [
        f"superseded thing {c3[:7]} (dev {_day(library, c3)})"
    ]
    assert _meta(library, c3)["superseded_by"] == c4


def test_ac5_a_moved_default_branch_hands_the_default_tree_its_other_name(
    library, repo, openbmc, catalog, capsys
):
    c2 = repo["c2"]
    _repin(openbmc, c2)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master")
    assert code == 0, out
    c5 = commit(repo["work"], {"README.md": "thing 5\n"}, "fifth")
    push(repo["work"], "master")
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    assert out.startswith(f"cloned thing {c5[:7]} (master ")
    assert _superseded_lines(out) == [], out
    meta = _meta(library, c2)
    assert meta["provenance"]["kind"] == "release"
    assert "also" not in meta and "superseded_by" not in meta
    code, out = run(
        capsys, catalog, "code", "thing", "README.md", "--release", "master"
    )
    assert code == 0 and _cite(out) == (f"thing {c2[:7]}", "release master")
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and _cite(out)[0] == f"thing {c5[:7]}"


def _day(library, sha):
    return _meta(library, sha)["fetched_at"][:10]


# ------------------------------------------------------------ AC-6


def test_ac6_repos_lists_the_also_names(library, repo, openbmc, catalog, capsys):
    c3 = _dev_with_release(library, repo, openbmc, catalog, capsys)
    _tag(repo, "v3", c3)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "v3")
    assert code == 0, out
    code, out = run(capsys, catalog, "repos")
    assert code == 0, out
    line = next(ln for ln in out.splitlines() if ln.startswith("thing\t"))
    held = line.split("\t")[1]
    assert held == f"{c3[:7]} dev {_day(library, c3)} (also release master, v3)"


# ------------------------------------------------------------ AC-7


def test_ac7_held_no_longer_means_no_network():
    # only the old claim is pinned; the new wording is left to review
    root = Path(__file__).resolve().parents[1]
    skill = (root / "skills" / "bmc-spec" / "SKILL.md").read_text("utf-8")
    assert "when already there (no network)" not in skill

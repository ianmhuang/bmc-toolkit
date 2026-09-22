"""Acceptance tests for the change that makes a plain ``clone`` retire the
default-branch trees another branch left behind: a changed catalog ``ref``
(AC-1, AC-2), a renamed remote default (AC-3), a ``--ref`` tree and a
catalog ``ref`` of the same branch answering each other without git
(AC-4, AC-5), ``--ref`` and ``--release`` trees left alone (AC-6), a branch
moved back to a held commit (AC-7) and a held plain clone superseding
nothing (AC-8). Everything goes through the CLI against local bare
repositories; skipped when git is not on PATH."""

import json
import shutil
from datetime import datetime, timedelta

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import RECIPE, THING_FILES, commit, git, make_repo, push

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


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
    """thing: main at c1 then c2, an sdk branch at cs (from c1)."""
    (tmp_path / "remote").mkdir()
    work, bare, url = make_repo(tmp_path / "remote", "thing", THING_FILES)
    c1 = git("rev-parse", "HEAD", cwd=work)
    git("checkout", "-q", "-b", "sdk", cwd=work)
    cs = commit(work, {"src/sdk.c": "int sdk;\n"}, "sdk")
    push(work, "sdk")
    git("checkout", "-q", "main", cwd=work)
    c2 = commit(work, {"README.md": "thing 2\n"}, "second")
    push(work)
    return {"work": work, "bare": bare, "url": url, "c1": c1, "cs": cs, "c2": c2}


@pytest.fixture
def release_source(tmp_path, repo):
    """openbmc, tag 1.0.0, whose recipe pins thing at c1."""
    recipe = RECIPE.format(url=repo["url"].removeprefix("file://"), sha=repo["c1"])
    files = {
        "meta-phosphor/recipes-phosphor/things/thing_git.bb": recipe,
        "README.md": "distro\n",
    }
    ob_work, ob_bare, ob_url = make_repo(
        tmp_path / "remote", "openbmc", files, branch="master"
    )
    git("tag", "1.0.0", cwd=ob_work)
    push(ob_work, "1.0.0")
    return ob_url


def _catalog(tmp_path, repo, *, ref=None, openbmc=None, name="catalog"):
    ref_line = f'ref = "{ref}"\n' if ref else ""
    text = MINI_CATALOG + (
        f'\n[[repos]]\nid = "thing"\nurl = "{repo["url"]}"\n'
        f'topics = ["power"]\n{ref_line}'
    )
    if openbmc:
        text += (
            f'\n[[repos]]\nid = "openbmc"\nurl = "{openbmc}"\n'
            'topics = ["release"]\nsparse = ["meta-phosphor"]\n'
        )
    path = tmp_path / f"{name}.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def _tree_dir(library, sha):
    return library / "code" / "thing" / sha


def _meta(library, sha):
    path = _tree_dir(library, sha) / code_mod.TREE_META
    return json.loads(path.read_text("utf-8"))


def _tree_dirs(library):
    return sorted(p.name for p in (library / "code" / "thing").iterdir() if p.is_dir())


# ------------------------------------------------------------ AC-1, AC-2


def test_ac1_ac2_changed_catalog_ref_supersedes_the_old_tree_and_prune_removes_it(
    library, repo, capsys, tmp_path
):
    c1, c2, cs = repo["c1"], repo["c2"], repo["cs"]
    old = _catalog(tmp_path, repo, ref="main", name="old")
    code, out = run(capsys, old, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    # a tree held under --ref (a commit id here) is not a default tree
    code, out = run(capsys, old, "clone", "thing", "--ref", c1)
    assert code == 0 and out.startswith(f"cloned thing {c1[:7]} ({c1} ")

    new = _catalog(tmp_path, repo, ref="sdk", name="new")
    code, out = run(capsys, new, "clone", "thing")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"cloned thing {cs[:7]} (sdk ")
    assert lines[1].startswith(f"superseded thing {c2[:7]} (main ")
    assert len(lines) == 2, out
    assert _meta(library, c2)["superseded_by"] == cs
    assert "superseded_by" not in _meta(library, cs)
    assert "superseded_by" not in _meta(library, c1)

    # AC-2: prune lists and removes the old tree, the reading commands use B
    old_dir = _tree_dir(library, c2)
    code, out = run(capsys, new, "prune")
    assert code == 0 and f"would remove {old_dir}" in out
    assert str(_tree_dir(library, cs)) not in out
    assert str(_tree_dir(library, c1)) not in out
    code, out = run(capsys, new, "prune", "--yes")
    assert code == 0, out
    assert f"removed {old_dir}" in out
    assert "prune: 1 superseded tree(s)" in out
    assert not old_dir.exists()
    assert _tree_dir(library, cs).is_dir() and _tree_dir(library, c1).is_dir()
    code, out = run(capsys, new, "grep", "thing", "int sdk")
    assert code == 0 and out.startswith(f"thing@{cs[:7]} src/sdk.c:1 | int sdk;")
    code, out = run(capsys, new, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {cs[:7]} | sdk ")


def test_ac1_a_ref_the_remote_lacks_leaves_the_held_tree_current(
    library, repo, capsys, tmp_path
):
    c2 = repo["c2"]
    old = _catalog(tmp_path, repo, ref="main", name="old")
    code, out = run(capsys, old, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    bad = _catalog(tmp_path, repo, ref="no-such-branch", name="bad")
    code, out = run(capsys, bad, "clone", "thing")
    assert code == 2, out
    assert "git clone failed" in out
    assert "superseded" not in out
    assert "superseded_by" not in _meta(library, c2)
    assert _tree_dirs(library) == [c2]


# ------------------------------------------------------------ AC-3


def test_ac3_a_renamed_remote_default_is_superseded_by_a_force_clone(
    library, repo, capsys, tmp_path
):
    work, bare, c2 = repo["work"], repo["bare"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")

    git("checkout", "-q", "-b", "trunk", cwd=work)
    c3 = commit(work, {"README.md": "thing on trunk\n"}, "trunk")
    push(work, "trunk")
    git("symbolic-ref", "HEAD", "refs/heads/trunk", cwd=bare)

    # without --force nothing moves
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"held thing {c2[:7]} (main ")
    assert "superseded" not in out
    assert "superseded_by" not in _meta(library, c2)

    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"cloned thing {c3[:7]} (trunk ")
    assert lines[1].startswith(f"superseded thing {c2[:7]} (main ")
    assert len(lines) == 2, out
    assert _meta(library, c2)["superseded_by"] == c3
    assert _meta(library, c3)["provenance"] == {"kind": "default", "name": "trunk"}
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c3[:7]} | trunk ")
    old_dir = _tree_dir(library, c2)
    code, out = run(capsys, catalog, "prune")
    assert code == 0 and f"would remove {old_dir}" in out


# ------------------------------------------------------------ AC-4, AC-5


def test_ac4_a_ref_tree_answers_the_catalog_ref_without_git(
    library, repo, capsys, tmp_path, monkeypatch
):
    cs = repo["cs"]
    catalog = _catalog(tmp_path, repo, ref="sdk")
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "sdk")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    assert out.startswith(f"held thing {cs[:7]} (sdk ")
    assert "superseded" not in out
    assert _tree_dirs(library) == [cs]
    assert _meta(library, cs)["provenance"] == {"kind": "ref", "name": "sdk"}
    assert "superseded_by" not in _meta(library, cs)
    code, out = run(capsys, catalog, "grep", "thing", "int sdk")
    assert code == 0 and out.startswith(f"thing@{cs[:7]} src/sdk.c:1 | int sdk;")
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {cs[:7]} | sdk ")
    assert "note:" not in out


def test_ac5_a_default_tree_answers_ref_of_the_same_branch_without_git(
    library, repo, capsys, tmp_path, monkeypatch
):
    cs = repo["cs"]
    catalog = _catalog(tmp_path, repo, ref="sdk")
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing", "--ref", "sdk")
    assert code == 0, out
    assert out.startswith(f"held thing {cs[:7]} (sdk ")
    assert "superseded" not in out
    assert _tree_dirs(library) == [cs]
    assert _meta(library, cs)["provenance"] == {"kind": "default", "name": "sdk"}
    code, out = run(capsys, catalog, "grep", "thing", "int sdk", "--ref", "sdk")
    assert code == 0 and out.startswith(f"thing@{cs[:7]} src/sdk.c:1 | int sdk;")


# ------------------------------------------------------------ AC-6


def test_ac6_a_default_clone_leaves_ref_and_release_trees_alone(
    library, repo, release_source, capsys, tmp_path
):
    work, c1, c2, cs = repo["work"], repo["c1"], repo["c2"], repo["cs"]
    git("checkout", "-q", "-b", "other", "main", cwd=work)
    co = commit(work, {"src/other.c": "int other;\n"}, "other")
    push(work, "other")
    git("checkout", "-q", "main", cwd=work)

    old = _catalog(tmp_path, repo, ref="main", openbmc=release_source, name="old")
    code, out = run(capsys, old, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    code, out = run(capsys, old, "clone", "thing", "--release", "1.0.0")
    assert code == 0 and f"cloned thing {c1[:7]} (release 1.0.0)" in out
    code, out = run(capsys, old, "clone", "thing", "--ref", "other")
    assert code == 0 and out.startswith(f"cloned thing {co[:7]} (other ")

    new = _catalog(tmp_path, repo, ref="sdk", openbmc=release_source, name="new")
    code, out = run(capsys, new, "clone", "thing")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"cloned thing {cs[:7]} (sdk ")
    superseded = [ln for ln in lines if ln.startswith("superseded ")]
    assert len(superseded) == 1 and superseded[0].startswith(
        f"superseded thing {c2[:7]} (main "
    )
    assert _meta(library, c2)["superseded_by"] == cs
    assert "superseded_by" not in _meta(library, c1)
    assert "superseded_by" not in _meta(library, co)
    assert "superseded_by" not in _meta(library, cs)
    code, out = run(capsys, new, "prune")
    assert code == 0, out
    listed = [ln for ln in out.splitlines() if ln.startswith("would remove ")]
    assert len(listed) == 1 and str(_tree_dir(library, c2)) in listed[0]
    # the ref and release trees still read
    code, out = run(capsys, new, "grep", "thing", "int other", "--ref", "other")
    assert code == 0 and out.startswith(f"thing@{co[:7]} src/other.c:1")
    argv = ["code", "thing", "README.md", "--release", "1.0.0"]
    code, out = run(capsys, new, *argv)
    assert code == 0 and out.startswith(f"cite: code | thing {c1[:7]} | release 1.0.0 ")


# ------------------------------------------------------------ AC-7


def test_ac7_a_branch_moved_back_makes_its_superseded_tree_current_again(
    library, repo, capsys, tmp_path
):
    work, c2 = repo["work"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0 and out.startswith(f"cloned thing {c3[:7]} (main ")
    assert _meta(library, c2)["superseded_by"] == c3

    git("reset", "-q", "--hard", c2, cwd=work)
    git("push", "-q", "-f", "origin", "main", cwd=work)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"held thing {c2[:7]} (main ")
    assert lines[1].startswith(f"superseded thing {c3[:7]} (main ")
    assert len(lines) == 2, out
    assert "superseded_by" not in _meta(library, c2)
    assert _meta(library, c3)["superseded_by"] == c2
    assert _tree_dirs(library) == sorted([c2, c3])
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c2[:7]} | main ")
    assert "thing 2" in out
    code, out = run(capsys, catalog, "prune")
    assert code == 0, out
    listed = [ln for ln in out.splitlines() if ln.startswith("would remove ")]
    assert len(listed) == 1 and str(_tree_dir(library, c3)) in listed[0]


# ------------------------------------------------------------ AC-8


def test_ac8_a_held_plain_clone_supersedes_nothing(library, repo, capsys, tmp_path):
    c2, cs = repo["c2"], repo["cs"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "sdk")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    assert out.startswith(f"held thing {c2[:7]} (main ")
    assert len(out.splitlines()) == 1 and "superseded" not in out
    assert "superseded_by" not in _meta(library, c2)
    assert "superseded_by" not in _meta(library, cs)
    code, out = run(capsys, catalog, "repos", "--topic", "power")
    assert code == 0 and out.startswith("thing\t") and "superseded" not in out
    code, out = run(capsys, catalog, "prune")
    assert code == 0 and out.startswith("nothing to prune")


def test_ac1_a_held_plain_clone_retires_a_default_tree_an_earlier_version_left(
    library, repo, capsys, tmp_path, monkeypatch
):
    # a Library written before this change holds two current default trees
    # (the old and the new catalog ref); the next plain clone, held, without
    # git, leaves the one it resolved to current and marks the other
    c2, cs = repo["c2"], repo["cs"]
    old = _catalog(tmp_path, repo, ref="main", name="old")
    code, out = run(capsys, old, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    new = _catalog(tmp_path, repo, ref="sdk", name="new")
    code, out = run(capsys, new, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    meta_path = _tree_dir(library, c2) / code_mod.TREE_META
    meta = json.loads(meta_path.read_text("utf-8"))
    del meta["superseded_by"]  # what the previous version left behind
    text = json.dumps(meta, sort_keys=True)
    meta_path.write_text(text, encoding="utf-8", newline="")
    assert "superseded_by" not in _meta(library, c2)

    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, new, "clone", "thing")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"held thing {cs[:7]} (sdk ")
    assert lines[1].startswith(f"superseded thing {c2[:7]} (main ")
    assert len(lines) == 2, out
    assert _meta(library, c2)["superseded_by"] == cs
    assert "superseded_by" not in _meta(library, cs)
    code, out = run(capsys, new, "prune")
    assert code == 0 and f"would remove {_tree_dir(library, c2)}" in out
    assert str(_tree_dir(library, cs)) not in out


# ------------------------------------------------------------ round 2


def test_ac7_ac2_a_ref_moved_to_a_superseded_default_tree_of_another_name_revives_it(
    library, repo, capsys, tmp_path
):
    # catalog ref main (c2), then sdk (cs, c2 superseded), then trunk which
    # points at c2: the clone lands on the superseded main tree. It must come
    # back as the one current default tree; the sdk tree is superseded in
    # turn, and prune never lists both (that would remove the held tree).
    work, c2, cs = repo["work"], repo["c2"], repo["cs"]
    first = _catalog(tmp_path, repo, ref="main", name="first")
    code, out = run(capsys, first, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    second = _catalog(tmp_path, repo, ref="sdk", name="second")
    code, out = run(capsys, second, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    assert _meta(library, c2)["superseded_by"] == cs

    git("branch", "trunk", c2, cwd=work)
    push(work, "trunk")
    third = _catalog(tmp_path, repo, ref="trunk", name="third")
    code, out = run(capsys, third, "clone", "thing")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"held thing {c2[:7]} (main ")
    assert lines[1].startswith(f"superseded thing {cs[:7]} (sdk ")
    assert len(lines) == 2, out
    assert "superseded_by" not in _meta(library, c2)
    assert _meta(library, cs)["superseded_by"] == c2
    assert _tree_dirs(library) == sorted([c2, cs])
    code, out = run(capsys, third, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c2[:7]} | main ")
    assert "thing 2" in out
    code, out = run(capsys, third, "prune")
    assert code == 0, out
    listed = [ln for ln in out.splitlines() if ln.startswith("would remove ")]
    assert len(listed) == 1 and str(_tree_dir(library, cs)) in listed[0]
    code, out = run(capsys, third, "prune", "--yes")
    assert code == 0, out
    assert _tree_dir(library, c2).is_dir()
    assert not _tree_dir(library, cs).exists()
    code, out = run(capsys, third, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c2[:7]} | main ")


def test_ac8_ac6_a_plain_clone_answered_by_a_ref_tree_retires_no_default_tree(
    library, repo, capsys, tmp_path, monkeypatch
):
    # catalog ref sdk held as a default tree; `--ref sdk --force` fetches a
    # newer sdk as a ref tree; the next plain clone is answered by that ref
    # tree, without git, and marks nothing: the default tree stays current
    work, cs = repo["work"], repo["cs"]
    catalog = _catalog(tmp_path, repo, ref="sdk")
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    git("checkout", "-q", "sdk", cwd=work)
    cs2 = commit(work, {"src/sdk.c": "int sdk2;\n"}, "sdk 2")
    push(work, "sdk")
    git("checkout", "-q", "main", cwd=work)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "sdk", "--force")
    assert code == 0 and out.startswith(f"cloned thing {cs2[:7]} (sdk ")
    assert "superseded" not in out
    assert _meta(library, cs2)["provenance"] == {"kind": "ref", "name": "sdk"}

    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    assert out.startswith(f"held thing {cs2[:7]} (sdk ")
    assert len(out.splitlines()) == 1 and "superseded" not in out
    assert "superseded_by" not in _meta(library, cs)
    assert "superseded_by" not in _meta(library, cs2)
    assert _tree_dirs(library) == sorted([cs, cs2])
    code, out = run(capsys, catalog, "prune")
    assert code == 0 and out.startswith("nothing to prune")
    code, out = run(capsys, catalog, "repos", "--topic", "power")
    assert code == 0 and out.startswith("thing\t") and "superseded" not in out


# ------------------------------------------------------------ round 3


def test_ac7_ac2_reading_after_a_force_lands_on_a_ref_tree_uses_that_tree(
    library, repo, capsys, tmp_path
):
    # `--ref main` held (older); a plain clone fetches main's next commit as
    # the default tree; main moves back and `clone --force` lands on the ref
    # tree, retiring the default tree. No current default tree is left, and
    # reading without --ref must use the tree clone reported, not the newer
    # superseded one prune is about to remove.
    work, c2 = repo["work"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "main")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    meta_path = _tree_dir(library, c2) / code_mod.TREE_META
    meta = json.loads(meta_path.read_text("utf-8"))
    meta["fetched_at"] = "2026-01-01T00:00:00+00:00"  # certainly the older tree
    text = json.dumps(meta, sort_keys=True)
    meta_path.write_text(text, encoding="utf-8", newline="")

    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c3[:7]} (main ")
    assert "superseded" not in out
    assert _meta(library, c3)["provenance"] == {"kind": "default", "name": "main"}

    git("reset", "-q", "--hard", c2, cwd=work)
    git("push", "-q", "-f", "origin", "main", cwd=work)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"held thing {c2[:7]} (main ")
    assert lines[1].startswith(f"superseded thing {c3[:7]} (main ")
    assert len(lines) == 2, out
    assert "superseded_by" not in _meta(library, c2)
    assert _meta(library, c2)["provenance"] == {"kind": "ref", "name": "main"}
    assert _meta(library, c3)["superseded_by"] == c2

    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c2[:7]} | main ")
    assert "thing 2" in out and "thing 3" not in out
    code, out = run(capsys, catalog, "grep", "thing", "thing 2")
    assert code == 0 and out.startswith(f"thing@{c2[:7]} README.md:1 | thing 2")
    code, out = run(capsys, catalog, "prune")
    assert code == 0, out
    listed = [ln for ln in out.splitlines() if ln.startswith("would remove ")]
    assert len(listed) == 1 and str(_tree_dir(library, c3)) in listed[0]
    code, out = run(capsys, catalog, "prune", "--yes")
    assert code == 0, out
    assert _tree_dir(library, c2).is_dir()
    assert not _tree_dir(library, c3).exists()
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c2[:7]} | main ")


# ------------------------------------------------------------ round 4


def test_ac4_ac8_two_trees_of_one_second_answer_with_the_newer_one(
    library, repo, capsys, tmp_path, monkeypatch
):
    # The round 3 flake, made certain: the default tree of the catalog ref
    # and a newer `--ref --force` tree of the same branch fetched inside one
    # second. The older tree gets the whole-second stamp an earlier version
    # wrote for that very second; the plain clone must still be answered by
    # the newer tree, without git, and the date the output shows is unchanged.
    work, cs = repo["work"], repo["cs"]
    catalog = _catalog(tmp_path, repo, ref="sdk")
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    git("checkout", "-q", "sdk", cwd=work)
    cs2 = commit(work, {"src/sdk.c": "int sdk2;\n"}, "sdk 2")
    push(work, "sdk")
    git("checkout", "-q", "main", cwd=work)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "sdk", "--force")
    assert code == 0 and out.startswith(f"cloned thing {cs2[:7]} (sdk ")

    newer = _meta(library, cs2)["fetched_at"]
    older = _meta(library, cs)["fetched_at"]
    parsed = datetime.fromisoformat(newer)
    assert parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)
    assert newer > older  # strictly: two clones never share a stamp
    assert out.startswith(f"cloned thing {cs2[:7]} (sdk {newer[:10]})")
    same_second = newer[:19] + "+00:00"
    meta_path = _tree_dir(library, cs) / code_mod.TREE_META
    meta = json.loads(meta_path.read_text("utf-8"))
    meta["fetched_at"] = same_second
    text = json.dumps(meta, sort_keys=True)
    meta_path.write_text(text, encoding="utf-8", newline="")

    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    assert out.startswith(f"held thing {cs2[:7]} (sdk {newer[:10]})")
    assert len(out.splitlines()) == 1 and "superseded" not in out
    assert "superseded_by" not in _meta(library, cs)
    assert "superseded_by" not in _meta(library, cs2)
    code, out = run(capsys, catalog, "repos", "--topic", "power")
    assert code == 0, out
    held = out.splitlines()[0].split("\t")[1]
    assert held.startswith(f"{cs2[:7]} sdk {newer[:10]}")
    assert "superseded" not in held

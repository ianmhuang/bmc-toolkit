"""Acceptance tests for the change that makes a ``--ref`` tree and a
default-branch tree of one branch one branch for superseding (AC-1, AC-2),
leaves ``--release`` trees and ``--ref`` trees of another branch alone
(AC-3), keeps a plain ``clone --force`` that lands on a ``--ref`` or
``--release`` tree answering the next plain clone without the network
(AC-4), adopts a superseded tree of another name or kind (AC-5), names a
default tree the clone lands on after the branch it resolved (AC-6) and
takes the clone's snapshot of current trees inside the lock (AC-7).
Everything goes through the CLI against local bare repositories; skipped
when git is not on PATH."""

import json
import shutil
import threading
import time

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec import lock as lock_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import RECIPE, RECIPE_URL, THING_FILES, commit, git, make_repo, push

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
    """thing: main at c1 then c2, an sdk branch at cs (from c1), a rel
    branch at c1."""
    (tmp_path / "remote").mkdir()
    work, bare, url = make_repo(tmp_path / "remote", "thing", THING_FILES)
    c1 = git("rev-parse", "HEAD", cwd=work)
    git("branch", "rel", c1, cwd=work)
    push(work, "rel")
    git("checkout", "-q", "-b", "sdk", cwd=work)
    cs = commit(work, {"src/sdk.c": "int sdk;\n"}, "sdk")
    push(work, "sdk")
    git("checkout", "-q", "main", cwd=work)
    c2 = commit(work, {"README.md": "thing 2\n"}, "second")
    push(work)
    return {"work": work, "bare": bare, "url": url, "c1": c1, "cs": cs, "c2": c2}


@pytest.fixture
def openbmc(tmp_path, repo):
    """openbmc on branch master, tag 1.0.0 at its first commit, whose recipe
    pins thing at c1; ``_repin`` moves master's recipe to another commit."""
    recipe = RECIPE.format(url=RECIPE_URL, sha=repo["c1"])
    files = {RECIPE_PATH: recipe, "README.md": "distro\n"}
    work, _bare, url = make_repo(tmp_path / "remote", "openbmc", files, branch="master")
    git("tag", "1.0.0", cwd=work)
    push(work, "1.0.0")
    return {"work": work, "url": url}


def _repin(openbmc, sha):
    recipe = RECIPE.format(url=RECIPE_URL, sha=sha)
    commit(openbmc["work"], {RECIPE_PATH: recipe}, f"pin thing at {sha[:7]}")
    push(openbmc["work"], "master")


def _catalog(tmp_path, repo, *, ref=None, openbmc=None):
    ref_line = f'ref = "{ref}"\n' if ref else ""
    text = MINI_CATALOG + (
        f'\n[[repos]]\nid = "thing"\nurl = "{repo["url"]}"\n'
        f'topics = ["power"]\n{ref_line}'
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


def _edit_meta(library, sha, **changes):
    path = _tree_dir(library, sha) / code_mod.TREE_META
    meta = json.loads(path.read_text("utf-8"))
    for key, value in changes.items():
        if value is None:
            meta.pop(key, None)
        else:
            meta[key] = value
    path.write_text(json.dumps(meta, sort_keys=True), encoding="utf-8", newline="")


def _move(work, branch, files, message) -> str:
    git("checkout", "-q", branch, cwd=work)
    sha = commit(work, files, message)
    push(work, branch)
    git("checkout", "-q", "main", cwd=work)
    return sha


def _reset_main(work, sha) -> None:
    git("reset", "-q", "--hard", sha, cwd=work)
    git("push", "-q", "-f", "origin", "main", cwd=work)


def _rename_default(work, bare, new, sha) -> None:
    git("branch", new, sha, cwd=work)
    push(work, new)
    git("symbolic-ref", "HEAD", f"refs/heads/{new}", cwd=bare)


def _superseded_lines(out):
    return [ln for ln in out.splitlines() if ln.startswith("superseded ")]


def _would_remove(out, library):
    """prune's lines for thing's trees (an openbmc tree a re-pin superseded
    is listed too, and is not what these tests look at)."""
    mine = str(library / "code" / "thing")
    return [
        ln
        for ln in out.splitlines()
        if ln.startswith("would remove ") and mine in ln
    ]


# ------------------------------------------------------------ AC-1


def test_ac1_a_plain_force_supersedes_the_ref_tree_of_the_catalog_branch(
    library, repo, capsys, tmp_path
):
    # sdk held under --ref; the catalog's ref is sdk; sdk moves; the plain
    # --force fetches the new commit and the --ref tree is the older tree
    # of the same branch: superseded, listed by repos, removed by prune
    work, cs = repo["work"], repo["cs"]
    catalog = _catalog(tmp_path, repo, ref="sdk")
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "sdk")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    cs2 = _move(work, "sdk", {"src/sdk.c": "int sdk2;\n"}, "sdk 2")

    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"cloned thing {cs2[:7]} (sdk ")
    assert lines[1].startswith(f"superseded thing {cs[:7]} (sdk ")
    assert len(lines) == 2, out
    assert _meta(library, cs)["superseded_by"] == cs2
    assert _meta(library, cs)["provenance"] == {"kind": "ref", "name": "sdk"}
    assert _meta(library, cs2)["provenance"] == {"kind": "default", "name": "sdk"}
    assert "superseded_by" not in _meta(library, cs2)

    code, out = run(capsys, catalog, "repos", "--topic", "power")
    assert code == 0, out
    held = out.splitlines()[0].split("\t")[1].split("; ")
    assert held[0].startswith(f"{cs2[:7]} sdk ") and "superseded" not in held[0]
    assert held[1].startswith(f"{cs[:7]} sdk ") and held[1].endswith(" superseded")

    code, out = run(capsys, catalog, "prune", "--yes")
    assert code == 0, out
    assert f"removed {_tree_dir(library, cs)}" in out
    assert "prune: 1 superseded tree(s)" in out
    assert not _tree_dir(library, cs).exists()
    assert _tree_dir(library, cs2).is_dir()
    code, out = run(capsys, catalog, "code", "thing", "src/sdk.c")
    assert code == 0 and out.startswith(f"cite: code | thing {cs2[:7]} | sdk ")
    assert out.splitlines()[1:] == ["1  int sdk2;"]


def test_ac1_a_ref_force_supersedes_the_default_tree_of_its_branch(
    library, repo, capsys, tmp_path
):
    # the reverse: the catalog ref held as a default tree, `--ref sdk --force`
    # fetches the newer sdk and the default tree is superseded
    work, cs = repo["work"], repo["cs"]
    catalog = _catalog(tmp_path, repo, ref="sdk")
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    assert _meta(library, cs)["provenance"] == {"kind": "default", "name": "sdk"}
    cs2 = _move(work, "sdk", {"src/sdk.c": "int sdk2;\n"}, "sdk 2")

    code, out = run(capsys, catalog, "clone", "thing", "--ref", "sdk", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"cloned thing {cs2[:7]} (sdk ")
    assert lines[1].startswith(f"superseded thing {cs[:7]} (sdk ")
    assert len(lines) == 2, out
    assert _meta(library, cs)["superseded_by"] == cs2
    assert _meta(library, cs2)["provenance"] == {"kind": "ref", "name": "sdk"}
    assert "superseded_by" not in _meta(library, cs2)

    code, out = run(capsys, catalog, "prune")
    assert code == 0, out
    listed = _would_remove(out, library)
    assert len(listed) == 1 and str(_tree_dir(library, cs)) in listed[0]
    code, out = run(capsys, catalog, "grep", "thing", "int sdk2")
    assert code == 0 and out.startswith(f"thing@{cs2[:7]} src/sdk.c:1 | int sdk2;")


# ------------------------------------------------------------ AC-2


def test_ac2_a_held_plain_clone_retires_the_older_current_tree_of_its_branch(
    library, repo, capsys, tmp_path, monkeypatch
):
    # a Library an earlier version wrote: two current trees of the catalog
    # branch, the older under --ref, the newer a default tree. The plain
    # clone is answered by the newer one without git and marks the older
    # one; a second plain clone has nothing left to mark.
    work, cs = repo["work"], repo["cs"]
    catalog = _catalog(tmp_path, repo, ref="sdk")
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "sdk")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    cs2 = _move(work, "sdk", {"src/sdk.c": "int sdk2;\n"}, "sdk 2")
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0 and out.startswith(f"cloned thing {cs2[:7]} (sdk ")
    assert _meta(library, cs)["superseded_by"] == cs2
    _edit_meta(library, cs, superseded_by=None)  # both current, as before

    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"held thing {cs2[:7]} (sdk ")
    assert lines[1].startswith(f"superseded thing {cs[:7]} (sdk ")
    assert len(lines) == 2, out
    assert _meta(library, cs)["superseded_by"] == cs2
    assert "superseded_by" not in _meta(library, cs2)

    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    assert out.startswith(f"held thing {cs2[:7]} (sdk ")
    assert len(out.splitlines()) == 1, out
    code, out = run(capsys, catalog, "prune")
    assert code == 0, out
    listed = _would_remove(out, library)
    assert len(listed) == 1 and str(_tree_dir(library, cs)) in listed[0]


# ------------------------------------------------------------ AC-3 (with AC-1)


def test_ac3_default_and_ref_forces_leave_release_and_other_ref_trees(
    library, repo, openbmc, capsys, tmp_path
):
    # a --ref sdk tree and a --release 1.0.0 tree (both at commits main
    # never had) stay current through a plain --force and a `--ref main
    # --force`; only the main trees supersede each other (AC-1 both ways)
    work, c1, c2, cs = repo["work"], repo["c1"], repo["c2"], repo["cs"]
    catalog = _catalog(tmp_path, repo, openbmc=openbmc)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "sdk")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    code, out = run(capsys, catalog, "clone", "thing", "--release", "1.0.0")
    assert code == 0 and f"cloned thing {c1[:7]} (release 1.0.0)" in out
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")

    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"cloned thing {c3[:7]} (main ")
    assert lines[1].startswith(f"superseded thing {c2[:7]} (main ")
    assert len(lines) == 2, out
    assert "superseded_by" not in _meta(library, cs)
    assert "superseded_by" not in _meta(library, c1)

    c4 = commit(work, {"README.md": "thing 4\n"}, "fourth")
    push(work)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "main", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"cloned thing {c4[:7]} (main ")
    assert lines[1].startswith(f"superseded thing {c3[:7]} (main ")
    assert len(lines) == 2, out
    assert _meta(library, c3)["superseded_by"] == c4
    assert "superseded_by" not in _meta(library, cs)
    assert "superseded_by" not in _meta(library, c1)
    assert "default_branch" not in _meta(library, cs)
    assert "default_branch" not in _meta(library, c1)

    code, out = run(capsys, catalog, "prune")
    assert code == 0, out
    listed = _would_remove(out, library)
    assert len(listed) == 2, out
    assert any(str(_tree_dir(library, c2)) in ln for ln in listed)
    assert any(str(_tree_dir(library, c3)) in ln for ln in listed)
    code, out = run(capsys, catalog, "code", "thing", "src/sdk.c", "--ref", "sdk")
    assert code == 0 and out.startswith(f"cite: code | thing {cs[:7]} | sdk ")
    code, out = run(capsys, catalog, "code", "thing", "README.md", "--release", "1.0.0")
    assert code == 0 and out.startswith(f"cite: code | thing {c1[:7]} | release 1.0.0")


# ------------------------------------------------------------ AC-4


def test_ac4_a_plain_force_landing_on_a_ref_tree_marks_it_and_answers_the_next(
    library, repo, capsys, tmp_path, monkeypatch
):
    work, c1, c2 = repo["work"], repo["c1"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "rel")
    assert code == 0 and out.startswith(f"cloned thing {c1[:7]} (rel ")

    _reset_main(work, c1)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"held thing {c1[:7]} (rel ")
    assert lines[1].startswith(f"superseded thing {c2[:7]} (main ")
    assert len(lines) == 2, out
    meta = _meta(library, c1)
    assert meta["provenance"] == {"kind": "ref", "name": "rel"}
    assert meta["default_branch"] == "main"
    assert "superseded_by" not in meta
    assert _meta(library, c2)["superseded_by"] == c1

    # the next plain clone is answered by the marked tree, without git;
    # reading commands without --ref use it; prune leaves it alone
    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    assert out.startswith(f"held thing {c1[:7]} (rel ")
    assert len(out.splitlines()) == 1, out
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c1[:7]} | rel ")
    assert out.splitlines()[1:] == ["1  thing"]
    code, out = run(capsys, catalog, "grep", "thing", "CurrentPowerState")
    assert code == 0, out
    assert out.startswith(f"thing@{c1[:7]} src/state.hpp:1 | // CurrentPowerState")
    code, out = run(capsys, catalog, "prune")
    assert code == 0, out
    listed = _would_remove(out, library)
    assert len(listed) == 1 and str(_tree_dir(library, c2)) in listed[0]

    # a later plain clone that resolves elsewhere takes the mark away and
    # leaves the ref tree current under its own name
    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    assert out.startswith(f"cloned thing {c3[:7]} (main ")
    assert _superseded_lines(out) == [], out
    meta = _meta(library, c1)
    assert meta["provenance"] == {"kind": "ref", "name": "rel"}
    assert "default_branch" not in meta and "superseded_by" not in meta
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c3[:7]} | main ")
    code, out = run(capsys, catalog, "code", "thing", "README.md", "--ref", "rel")
    assert code == 0 and out.startswith(f"cite: code | thing {c1[:7]} | rel ")


def test_ac4_a_marked_release_tree_superseded_under_its_release_becomes_default(
    library, repo, openbmc, capsys, tmp_path, monkeypatch
):
    # a --release tree marked by a plain --force; the release (a branch)
    # re-pins elsewhere and `--release master --force` fetches the new pin:
    # the marked tree is not superseded but becomes the default tree (AC-5)
    work, c1, c2 = repo["work"], repo["c1"], repo["c2"]
    catalog = _catalog(tmp_path, repo, openbmc=openbmc)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master")
    assert code == 0 and f"cloned thing {c1[:7]} (release master)" in out

    _reset_main(work, c1)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"held thing {c1[:7]} (release master)")
    assert lines[1].startswith(f"superseded thing {c2[:7]} (main ")
    assert len(lines) == 2, out
    meta = _meta(library, c1)
    assert meta["provenance"]["kind"] == "release"
    assert meta["default_branch"] == "main"

    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work)
    _repin(openbmc, c3)
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master", "--force")
    assert code == 0, out
    assert f"cloned thing {c3[:7]} (release master)" in out
    assert _superseded_lines(out) == [], out
    meta = _meta(library, c1)
    assert meta["provenance"] == {"kind": "default", "name": "main"}
    assert "default_branch" not in meta and "superseded_by" not in meta
    assert "superseded_by" not in _meta(library, c3)

    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    assert out.startswith(f"held thing {c1[:7]} (main ")
    assert len(out.splitlines()) == 1, out
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c1[:7]} | main ")
    assert out.splitlines()[1:] == ["1  thing"]
    code, out = run(capsys, catalog, "prune")
    assert code == 0, out
    listed = _would_remove(out, library)
    assert len(listed) == 1 and str(_tree_dir(library, c2)) in listed[0]


# ------------------------------------------------------------ AC-5


def test_ac5_a_plain_force_adopts_a_superseded_release_tree(
    library, repo, openbmc, capsys, tmp_path, monkeypatch
):
    # a --release tree superseded by a re-pin (another kind than the default
    # clone): landing on it makes it the current default tree, retiring the
    # default tree; the current release tree stays; prune lists neither
    work, c1, c2, cs = repo["work"], repo["c1"], repo["c2"], repo["cs"]
    catalog = _catalog(tmp_path, repo, openbmc=openbmc)
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master")
    assert code == 0 and f"cloned thing {c1[:7]} (release master)" in out
    _repin(openbmc, cs)
    code, out = run(capsys, catalog, "clone", "thing", "--release", "master", "--force")
    assert code == 0 and f"cloned thing {cs[:7]} (release master)" in out
    assert _meta(library, c1)["superseded_by"] == cs
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")

    _reset_main(work, c1)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"held thing {c1[:7]} (main ")
    assert lines[1].startswith(f"superseded thing {c2[:7]} (main ")
    assert len(lines) == 2, out
    meta = _meta(library, c1)
    assert meta["provenance"] == {"kind": "default", "name": "main"}
    assert "superseded_by" not in meta and "default_branch" not in meta
    assert _meta(library, c2)["superseded_by"] == c1
    assert "superseded_by" not in _meta(library, cs)

    code, out = run(capsys, catalog, "prune")
    assert code == 0, out
    listed = _would_remove(out, library)
    assert len(listed) == 1 and str(_tree_dir(library, c2)) in listed[0]
    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"held thing {c1[:7]} (main ")
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c1[:7]} | main ")
    code, out = run(capsys, catalog, "code", "thing", "README.md", "--release", "master")
    assert code == 0 and out.startswith(f"cite: code | thing {cs[:7]} | release master")


# ------------------------------------------------------------ AC-6


def test_ac6_a_current_default_tree_takes_the_renamed_default_branch(
    library, repo, capsys, tmp_path
):
    work, bare, c2 = repo["work"], repo["bare"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")

    _rename_default(work, bare, "trunk", c2)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    assert out.startswith(f"held thing {c2[:7]} (trunk ")
    assert len(out.splitlines()) == 1, out
    assert _meta(library, c2)["provenance"] == {"kind": "default", "name": "trunk"}
    assert "superseded_by" not in _meta(library, c2)
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c2[:7]} | trunk ")
    code, out = run(capsys, catalog, "repos", "--topic", "power")
    assert code == 0, out
    held = out.splitlines()[0].split("\t")[1]
    assert held.startswith(f"{c2[:7]} trunk ") and "superseded" not in held


def test_ac6_an_adopted_tree_takes_the_branch_the_clone_resolved(
    library, repo, capsys, tmp_path
):
    # AC-5 with AC-6: the remote's default is renamed to trunk and points at
    # a commit held only in a superseded --ref rel tree; that tree becomes
    # the default tree under trunk, not rel and not main
    work, bare, c1, c2 = repo["work"], repo["bare"], repo["c1"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "rel")
    assert code == 0 and out.startswith(f"cloned thing {c1[:7]} (rel ")
    c4 = _move(work, "rel", {"README.md": "thing rel\n"}, "rel moves")
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "rel", "--force")
    assert code == 0 and out.startswith(f"cloned thing {c4[:7]} (rel ")
    assert _meta(library, c1)["superseded_by"] == c4
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")

    _rename_default(work, bare, "trunk", c1)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"held thing {c1[:7]} (trunk ")
    assert lines[1].startswith(f"superseded thing {c2[:7]} (main ")
    assert len(lines) == 2, out
    meta = _meta(library, c1)
    assert meta["provenance"] == {"kind": "default", "name": "trunk"}
    assert "superseded_by" not in meta
    assert "superseded_by" not in _meta(library, c4)
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c1[:7]} | trunk ")
    assert out.splitlines()[1:] == ["1  thing"]
    code, out = run(capsys, catalog, "code", "thing", "README.md", "--ref", "rel")
    assert code == 0 and out.startswith(f"cite: code | thing {c4[:7]} | rel ")


# ------------------------------------------------------------ AC-7


def test_ac7_a_tree_superseded_while_waiting_for_the_lock_is_not_reported(
    library, repo, capsys, tmp_path
):
    # another Session holds the repository lock when this clone starts and,
    # before releasing it, supersedes the current default tree (as a clone
    # that fetched something newer would). This clone, once it has the
    # lock, must not report that tree: it was not current when this clone
    # took its snapshot.
    work, c2 = repo["work"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work)

    taken = threading.Event()
    other = "f" * 40

    def other_session():
        with lock_mod.Lock(library / "code" / "thing", "clone thing other", wait=0):
            taken.set()
            time.sleep(0.8)  # this clone has started and is waiting by now
            _edit_meta(library, c2, superseded_by=other)
            time.sleep(0.4)

    holder = threading.Thread(target=other_session)
    holder.start()
    try:
        assert taken.wait(10)
        code, out = run(capsys, catalog, "clone", "thing", "--force")
    finally:
        holder.join()
    assert code == 0, out
    assert out.startswith(f"cloned thing {c3[:7]} (main ")
    assert _superseded_lines(out) == [], out
    assert len(out.splitlines()) == 1, out
    assert _meta(library, c2)["superseded_by"] == other
    assert "superseded_by" not in _meta(library, c3)

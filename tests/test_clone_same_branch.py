"""A --ref tree and a default tree of one branch are one branch for
superseding; a default clone that lands on a tree held under another name
keeps the Library answering without the network, and a default tree it
lands on takes the branch name it resolved. Everything goes through the CLI
against local bare repositories; skipped when git is not on PATH."""

import contextlib
import json
import shutil

import pytest

from bmc_toolkit.spec import cli as cli_mod
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


def _catalog(tmp_path, repo, *, ref=None, openbmc=None):
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


def _superseded_lines(out):
    return [ln for ln in out.splitlines() if ln.startswith("superseded ")]


# ------------------------------------------------------------ AC-1


def test_ac1_a_plain_force_clone_supersedes_the_ref_tree_of_its_branch(
    library, repo, capsys, tmp_path
):
    work, cs = repo["work"], repo["cs"]
    catalog = _catalog(tmp_path, repo, ref="sdk")
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "sdk")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    cs2 = _move(work, "sdk", {"src/sdk.c": "int sdk2;\n"}, "sdk 2")

    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    assert out.startswith(f"cloned thing {cs2[:7]} (sdk ")
    superseded = _superseded_lines(out)
    assert len(superseded) == 1 and superseded[0].startswith(
        f"superseded thing {cs[:7]} (sdk "
    )
    assert _meta(library, cs)["superseded_by"] == cs2
    code, out = run(capsys, catalog, "prune", "--yes")
    assert code == 0 and f"removed {_tree_dir(library, cs)}" in out
    assert not _tree_dir(library, cs).exists()
    assert _tree_dir(library, cs2).is_dir()


def test_ac1_a_ref_force_clone_supersedes_the_default_tree_of_its_branch(
    library, repo, capsys, tmp_path
):
    work, cs = repo["work"], repo["cs"]
    catalog = _catalog(tmp_path, repo, ref="sdk")
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    cs2 = _move(work, "sdk", {"src/sdk.c": "int sdk2;\n"}, "sdk 2")

    code, out = run(capsys, catalog, "clone", "thing", "--ref", "sdk", "--force")
    assert code == 0, out
    assert out.startswith(f"cloned thing {cs2[:7]} (sdk ")
    superseded = _superseded_lines(out)
    assert len(superseded) == 1 and superseded[0].startswith(
        f"superseded thing {cs[:7]} (sdk "
    )
    assert _meta(library, cs)["superseded_by"] == cs2
    code, out = run(capsys, catalog, "code", "thing", "src/sdk.c")
    assert code == 0 and out.splitlines()[1:] == ["1  int sdk2;"]


# ------------------------------------------------------------ AC-2


def test_ac2_a_held_plain_clone_supersedes_the_older_tree_of_its_branch(
    library, repo, capsys, tmp_path, monkeypatch
):
    work, cs = repo["work"], repo["cs"]
    catalog = _catalog(tmp_path, repo, ref="sdk")
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    cs2 = _move(work, "sdk", {"src/sdk.c": "int sdk2;\n"}, "sdk 2")
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "sdk", "--force")
    assert code == 0 and out.startswith(f"cloned thing {cs2[:7]} (sdk ")
    _edit_meta(library, cs, superseded_by=None)  # what an earlier version left

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


# ------------------------------------------------------------ AC-3


def test_ac3_a_default_clone_leaves_a_ref_tree_of_another_branch(
    library, repo, capsys, tmp_path
):
    work, cs, c2 = repo["work"], repo["cs"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "sdk")
    assert code == 0 and out.startswith(f"cloned thing {cs[:7]} (sdk ")
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0 and out.startswith(f"cloned thing {c3[:7]} (main ")
    superseded = _superseded_lines(out)
    assert len(superseded) == 1 and superseded[0].startswith(
        f"superseded thing {c2[:7]} (main "
    )
    assert "superseded_by" not in _meta(library, cs)


# ------------------------------------------------------------ AC-4


@pytest.fixture
def release_source(tmp_path, repo):
    """openbmc, tag 1.0.0, whose recipe pins thing at c1."""
    recipe = RECIPE.format(url=RECIPE_URL, sha=repo["c1"])
    files = {
        "meta-phosphor/recipes-phosphor/things/thing_git.bb": recipe,
        "README.md": "distro\n",
    }
    ob_work, _ob_bare, ob_url = make_repo(
        tmp_path / "remote", "openbmc", files, branch="master"
    )
    git("tag", "1.0.0", cwd=ob_work)
    push(ob_work, "1.0.0")
    return ob_url


def test_ac4_a_default_clone_landing_on_a_release_tree_answers_without_git(
    library, repo, release_source, capsys, tmp_path, monkeypatch
):
    work, c1, c2 = repo["work"], repo["c1"], repo["c2"]
    catalog = _catalog(tmp_path, repo, openbmc=release_source)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    code, out = run(capsys, catalog, "clone", "thing", "--release", "1.0.0")
    assert code == 0 and f"cloned thing {c1[:7]} (release 1.0.0)" in out

    _reset_main(work, c1)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"held thing {c1[:7]} (release 1.0.0)")
    assert lines[1].startswith(f"superseded thing {c2[:7]} (main ")
    assert len(lines) == 2, out
    meta = _meta(library, c1)
    assert meta["provenance"]["kind"] == "release"
    assert meta["default_branch"] == "main"
    assert "superseded_by" not in meta

    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    assert out.startswith(f"held thing {c1[:7]} (release 1.0.0)")
    assert len(out.splitlines()) == 1, out
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c1[:7]} | release 1.0.0")
    assert out.splitlines()[1:] == ["1  thing"]
    code, out = run(capsys, catalog, "prune")
    assert code == 0, out
    assert str(_tree_dir(library, c1)) not in out

    # a later default clone that resolves elsewhere takes the mark away
    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0 and out.startswith(f"cloned thing {c3[:7]} (main ")
    assert "default_branch" not in _meta(library, c1)
    assert "superseded_by" not in _meta(library, c1)


def test_ac4_a_marked_ref_tree_superseded_under_its_name_stays_the_default(
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
    assert code == 0 and out.startswith(f"held thing {c1[:7]} (rel ")
    assert _meta(library, c1)["default_branch"] == "main"

    c4 = _move(work, "rel", {"README.md": "thing rel\n"}, "rel moves")
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "rel", "--force")
    assert code == 0 and out.startswith(f"cloned thing {c4[:7]} (rel ")
    assert _superseded_lines(out) == [], out
    meta = _meta(library, c1)
    assert meta["provenance"] == {"kind": "default", "name": "main"}
    assert "superseded_by" not in meta and "default_branch" not in meta

    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"held thing {c1[:7]} (main ")
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.splitlines()[1:] == ["1  thing"]


# ------------------------------------------------------------ AC-5


def test_ac5_a_default_clone_adopts_a_superseded_tree_of_another_branch(
    library, repo, capsys, tmp_path, monkeypatch
):
    work, c1, c2 = repo["work"], repo["c1"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "rel")
    assert code == 0 and out.startswith(f"cloned thing {c1[:7]} (rel ")
    c4 = _move(work, "rel", {"README.md": "thing rel\n"}, "rel moves")
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "rel", "--force")
    assert code == 0 and out.startswith(f"cloned thing {c4[:7]} (rel ")
    assert _meta(library, c1)["superseded_by"] == c4
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
    assert "superseded_by" not in meta
    assert "superseded_by" not in _meta(library, c4)
    code, out = run(capsys, catalog, "prune")
    assert code == 0, out
    listed = [ln for ln in out.splitlines() if ln.startswith("would remove ")]
    assert len(listed) == 1 and str(_tree_dir(library, c2)) in listed[0]
    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"held thing {c1[:7]} (main ")


# ------------------------------------------------------------ AC-6


def test_ac6_a_revived_default_tree_takes_the_renamed_branch(
    library, repo, capsys, tmp_path
):
    work, bare, c2 = repo["work"], repo["bare"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0 and out.startswith(f"cloned thing {c3[:7]} (main ")

    git("branch", "trunk", c2, cwd=work)
    push(work, "trunk")
    git("symbolic-ref", "HEAD", "refs/heads/trunk", cwd=bare)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"held thing {c2[:7]} (trunk ")
    assert lines[1].startswith(f"superseded thing {c3[:7]} (main ")
    assert _meta(library, c2)["provenance"] == {"kind": "default", "name": "trunk"}
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c2[:7]} | trunk ")


def test_ac6_a_current_default_tree_takes_the_renamed_branch(
    library, repo, capsys, tmp_path
):
    work, bare, c2 = repo["work"], repo["bare"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    git("branch", "trunk", c2, cwd=work)
    push(work, "trunk")
    git("symbolic-ref", "HEAD", "refs/heads/trunk", cwd=bare)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0, out
    assert out.startswith(f"held thing {c2[:7]} (trunk ")
    assert len(out.splitlines()) == 1, out
    assert _meta(library, c2)["provenance"] == {"kind": "default", "name": "trunk"}


# ------------------------------------------------------------ AC-7


def test_ac7_a_tree_superseded_while_waiting_for_the_lock_is_not_reported(
    library, repo, capsys, tmp_path, monkeypatch
):
    work, c2 = repo["work"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work)

    real = cli_mod._clone_lock

    @contextlib.contextmanager
    def other_clone_first(args, library_, repo_id, what):
        # another clone ran while this one waited: it fetched c3 and
        # superseded c2 before this one got the lock
        with real(args, library_, repo_id, what) as held:
            _edit_meta(library, c2, superseded_by="f" * 40)
            yield held

    monkeypatch.setattr(cli_mod, "_clone_lock", other_clone_first)
    code, out = run(capsys, catalog, "clone", "thing", "--force")
    assert code == 0 and out.startswith(f"cloned thing {c3[:7]} (main ")
    assert _superseded_lines(out) == [] and len(out.splitlines()) == 1, out

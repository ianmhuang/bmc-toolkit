"""AC-1 and AC-2 for a repository without a catalog ``ref``: the branch is
the remote's default, so a plain clone carries no branch name and the
Library has to find the branch's newest tree on its own.

The first test is AC-2 on a Library an earlier version left (round 1 F1,
fixed in round 2): the default tree and a newer ``--ref main --force``
tree both current; a plain clone must be answered by the newer tree,
without git, and mark the older one.

The second test is the state this change itself creates through AC-1's
reverse direction: ``--ref main --force`` supersedes the default main
tree, after which the branch's only current tree is the ``--ref`` one.
The next plain clone must be answered by it without the network (round 2
F5, fixed in round 3: the ``--ref`` tree takes over the default-branch
role of the tree it supersedes). On the base branch the older tree
answers, so the test fails there. Skipped when git is not on PATH."""

import json
import shutil

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import THING_FILES, commit, git, make_repo, push

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
    """thing: main at c1 then c2."""
    (tmp_path / "remote").mkdir()
    work, bare, url = make_repo(tmp_path / "remote", "thing", THING_FILES)
    c1 = git("rev-parse", "HEAD", cwd=work)
    c2 = commit(work, {"README.md": "thing 2\n"}, "second")
    push(work)
    return {"work": work, "bare": bare, "url": url, "c1": c1, "c2": c2}


def _catalog(tmp_path, repo):
    text = MINI_CATALOG + (
        f'\n[[repos]]\nid = "thing"\nurl = "{repo["url"]}"\ntopics = ["power"]\n'
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


def test_ac2_a_held_plain_clone_of_the_remote_default_keeps_the_newer_tree(
    library, repo, capsys, tmp_path, monkeypatch
):
    work, c2 = repo["work"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "main", "--force")
    assert code == 0 and out.startswith(f"cloned thing {c3[:7]} (main ")
    assert _meta(library, c3)["provenance"] == {"kind": "ref", "name": "main"}
    # what an earlier version left: both trees of main current
    _edit_meta(library, c2, superseded_by=None)
    assert _meta(library, c3)["fetched_at"] > _meta(library, c2)["fetched_at"]

    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"held thing {c3[:7]} (main "), out
    assert lines[1].startswith(f"superseded thing {c2[:7]} (main "), out
    assert len(lines) == 2, out
    assert _meta(library, c2)["superseded_by"] == c3
    assert "superseded_by" not in _meta(library, c3)
    code, out = run(capsys, catalog, "prune")
    assert code == 0, out
    listed = [ln for ln in out.splitlines() if ln.startswith("would remove ")]
    assert len(listed) == 1 and str(_tree_dir(library, c2)) in listed[0]
    assert str(_tree_dir(library, c3)) not in out

    # the newer tree now answers reading commands too, without git
    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"held thing {c3[:7]} (main "), out
    assert len(out.splitlines()) == 1, out
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c3[:7]} | main "), out
    assert out.splitlines()[1:] == ["1  thing 3"]


def test_ac1_a_plain_clone_after_a_ref_force_of_the_remote_default_needs_no_git(
    library, repo, capsys, tmp_path, monkeypatch
):
    # AC-1 reverse: `--ref main --force` supersedes the default main tree.
    # The branch's newest tree is then held under --ref, so the next plain
    # clone must be answered by it without the network (the same handover
    # the held path does for a legacy Library above; round 2 F5).
    work, c2 = repo["work"], repo["c2"]
    catalog = _catalog(tmp_path, repo)
    code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0 and out.startswith(f"cloned thing {c2[:7]} (main ")
    c3 = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work)
    code, out = run(capsys, catalog, "clone", "thing", "--ref", "main", "--force")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"cloned thing {c3[:7]} (main ")
    assert lines[1].startswith(f"superseded thing {c2[:7]} (main ")
    assert len(lines) == 2, out
    assert _meta(library, c2)["superseded_by"] == c3
    assert _meta(library, c3)["provenance"] == {"kind": "ref", "name": "main"}

    with monkeypatch.context() as m:
        m.setattr(code_mod, "run_git", _refuse)
        code, out = run(capsys, catalog, "clone", "thing")
    assert code == 0, out
    assert out.startswith(f"held thing {c3[:7]} (main "), out
    assert len(out.splitlines()) == 1, out
    assert "superseded_by" not in _meta(library, c3)
    code, out = run(capsys, catalog, "code", "thing", "README.md")
    assert code == 0 and out.startswith(f"cite: code | thing {c3[:7]} | main "), out
    assert out.splitlines()[1:] == ["1  thing 3"]
    code, out = run(capsys, catalog, "prune")
    assert code == 0, out
    listed = [ln for ln in out.splitlines() if ln.startswith("would remove ")]
    assert len(listed) == 1 and str(_tree_dir(library, c2)) in listed[0]

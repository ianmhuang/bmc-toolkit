"""AC-2 for a repository without a catalog ``ref``: the branch is the
remote's default, and the Library holds two current trees of it that an
earlier version left (the default tree, and a newer ``--ref main --force``
tree). A plain clone must be answered by the newer tree and mark the older
one. As of the branch under review it is answered by the older tree and
marks the newer one, which ``prune`` then removes (finding F1): this test
is expected to fail on the base branch (no ``superseded`` line) and on
this branch (the wrong tree is held) until F1 is fixed. Skipped when git
is not on PATH."""

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

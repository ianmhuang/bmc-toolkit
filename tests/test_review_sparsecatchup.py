"""Independent acceptance tests for a held Code Tree catching up with the
catalog's sparse set (T76.1: AC-4, AC-5).

Black-box, through the ``bmcspec`` CLI, against local bare git
repositories: a tree is cloned with one catalog, then the same Library is
used with a catalog whose ``sparse`` differs. No network. Skipped when git
is not on PATH.
"""

import json
import shutil

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import git, make_repo, push

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

OLD = ("/meta-*/**/*.bb", "/meta-*/**/*.inc")  # what a tree was fetched with
NEW = ("/**/*.bb", "/**/*.inc")  # what the catalog names now
UP_RECIPE = "upstream-layers/meta-openembedded/meta-oe/recipes-x/foo/foo_1.0.bb"
TOP_RECIPE = "meta-phosphor/recipes-phosphor/top/top_git.bb"


@pytest.fixture
def remotes(tmp_path):
    foo_work, _bare, foo_url = make_repo(tmp_path, "foo", {"foo.c": "int foo;\n"})
    foo = git("rev-parse", "HEAD", cwd=foo_work)
    files = {
        UP_RECIPE: (
            'SRC_URI = "git://github.com/acme/foo;branch=main;protocol=https"\n'
            f'SRCREV = "{foo}"\n'
        ),
        TOP_RECIPE: (
            'SRC_URI = "git://github.com/openbmc/top;branch=master"\n'
            f'SRCREV = "{"d" * 40}"\n'
        ),
        "README.md": "distro\n",
    }
    ob_work, ob_bare, ob_url = make_repo(tmp_path, "openbmc", files, branch="master")
    git("tag", "1.0.0", cwd=ob_work)
    push(ob_work, "1.0.0")
    thing_files = {
        "src/a.c": "int a;\n",
        "docs/guide.txt": "the guide\n",
        "extra/x.txt": "extra\n",
    }
    _work, _bare, thing_url = make_repo(tmp_path, "thing", thing_files)
    return {
        "ob_url": ob_url,
        "ob_bare": ob_bare,
        "foo_url": foo_url,
        "foo": foo,
        "thing_url": thing_url,
    }


def _catalog(tmp_path, name, remotes, *, openbmc=NEW, thing=()):
    def line(sparse):
        if not sparse:
            return ""
        return f"sparse = [{', '.join(json.dumps(entry) for entry in sparse)}]\n"

    text = (
        MINI_CATALOG
        + f"""
[[repos]]
id = "openbmc"
url = "{remotes["ob_url"]}"
topics = ["release"]
{line(openbmc)}
[[repos]]
id = "foo"
url = "{remotes["foo_url"]}"
topics = ["x"]

[[repos]]
id = "thing"
url = "{remotes["thing_url"]}"
topics = ["y"]
{line(thing)}"""
    )
    path = tmp_path / f"catalog-{name}.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


def run(capsys, catalog_file, *argv):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def _trees(library, repo):
    rdir = library / "code" / repo
    if not rdir.is_dir():
        return []
    return sorted(p for p in rdir.iterdir() if (p / code_mod.TREE_META).is_file())


def _meta(tree):
    return json.loads((tree / code_mod.TREE_META).read_text(encoding="utf-8"))


def _files(tree):
    """Every checked-out file of the tree, without git's own and the meta."""
    return sorted(
        p.relative_to(tree).as_posix()
        for p in tree.rglob("*")
        if p.is_file()
        and p.relative_to(tree).parts[0] != ".git"
        and p.name != code_mod.TREE_META
    )


def _notes(out, repo):
    return [ln for ln in out.splitlines() if ln.startswith(f"note: {repo} ")]


# --------------------------------------------------------------- AC-4


def test_the_tree_meta_records_the_sparse_set_and_none_for_a_full_checkout(
    tmp_path, library, remotes, capsys
):
    """AC-4: 'A Code Tree's .bmc-tree.json records the sparse set it was
    checked out with (none for a full checkout).' openbmc is cloned with
    two patterns, foo whole: the first meta lists the patterns, the second
    an empty list.
    """
    catalog = _catalog(tmp_path, "new", remotes)
    code, out = run(capsys, catalog, "clone", "openbmc", "--ref", "1.0.0")
    assert code == 0, out
    (tree,) = _trees(library, "openbmc")
    assert _meta(tree)["sparse"] == list(NEW)
    code, out = run(capsys, catalog, "clone", "foo")
    assert code == 0, out
    (foo,) = _trees(library, "foo")
    assert _meta(foo)["sparse"] == []


@pytest.mark.parametrize("recorded", [True, False], ids=["older-set", "unrecorded"])
def test_a_held_release_source_catches_up_in_place_then_costs_no_git_call(
    tmp_path, library, remotes, capsys, monkeypatch, recorded
):
    """AC-4: a tree 'held at the wanted commit whose recorded set differs
    from the catalog's, including a tree written before this change with
    no set recorded' gets the catalog's set applied: the commit is kept,
    the meta updated, one note: line says so, and the tree is not cloned
    again. Then 'a tree whose set already matches is left untouched, with
    no git call'.

    The openbmc tree is fetched with the older patterns, which leave out
    upstream-layers/; with the catalog's new patterns `clone foo --release`
    must find foo's recipe there.
    """
    old = _catalog(tmp_path, "old", remotes, openbmc=OLD)
    code, out = run(capsys, old, "clone", "openbmc", "--ref", "1.0.0")
    assert code == 0, out
    (tree,) = _trees(library, "openbmc")
    assert _files(tree) == [TOP_RECIPE]
    before = _meta(tree)
    if not recorded:  # a tree written before trees recorded their set
        before.pop("sparse", None)
        (tree / code_mod.TREE_META).write_text(
            json.dumps(before), encoding="utf-8", newline=""
        )

    new = _catalog(tmp_path, "new", remotes)
    code, out = run(capsys, new, "clone", "foo", "--release", "1.0.0")
    assert code == 0, out
    notes = _notes(out, "openbmc")
    assert len(notes) == 1, out
    assert notes[0].startswith(f"note: openbmc {tree.name[:7]} "), out
    assert "cloned openbmc" not in out  # not cloned again
    assert _trees(library, "openbmc") == [tree]  # the commit is kept
    after = _meta(tree)
    assert after["sparse"] == list(NEW)
    assert after["commit"] == before["commit"]
    assert after["fetched_at"] == before["fetched_at"]
    assert after["provenance"] == before["provenance"]
    assert _files(tree) == sorted([TOP_RECIPE, UP_RECIPE])
    (foo,) = _trees(library, "foo")
    assert foo.name == remotes["foo"]

    # caught up: the same command again says nothing and runs no git at all
    meta_bytes = (tree / code_mod.TREE_META).read_bytes()

    def no_git(*args, **kwargs):
        raise AssertionError(f"git ran for trees whose set matches: {args}")

    monkeypatch.setattr(code_mod, "run_git", no_git)
    code, out = run(capsys, new, "clone", "foo", "--release", "1.0.0")
    assert code == 0, out
    assert _notes(out, "openbmc") == []
    assert (tree / code_mod.TREE_META).read_bytes() == meta_bytes
    assert _files(tree) == sorted([TOP_RECIPE, UP_RECIPE])


def test_clone_of_the_held_ref_itself_catches_up(tmp_path, library, remotes, capsys):
    """AC-4: 'When clone ... finds a tree held at the wanted commit whose
    recorded set differs from the catalog's, it applies the catalog's set
    to that tree': the same holds for `clone openbmc --ref 1.0.0` on the
    tree it already holds under that ref.
    """
    old = _catalog(tmp_path, "old", remotes, openbmc=OLD)
    run(capsys, old, "clone", "openbmc", "--ref", "1.0.0")
    (tree,) = _trees(library, "openbmc")
    new = _catalog(tmp_path, "new", remotes)
    code, out = run(capsys, new, "clone", "openbmc", "--ref", "1.0.0")
    assert code == 0, out
    assert len(_notes(out, "openbmc")) == 1, out
    assert "held openbmc " in out and "cloned openbmc" not in out
    assert _trees(library, "openbmc") == [tree]
    assert _meta(tree)["sparse"] == list(NEW)
    assert (tree / UP_RECIPE).is_file()


def test_any_repository_catches_up_with_directories_and_with_no_set(
    tmp_path, library, remotes, capsys
):
    """AC-4 is not about openbmc alone: 'a Code Tree's .bmc-tree.json
    records the sparse set' and clone applies the catalog's to a held tree
    that differs. thing is held with the directory src; the catalog then
    names docs and src, and after that no set at all (a full checkout):
    each time the held tree takes the catalog's paths in place.
    """
    first = _catalog(tmp_path, "src", remotes, thing=("src",))
    code, out = run(capsys, first, "clone", "thing")
    assert code == 0, out
    (tree,) = _trees(library, "thing")
    assert _files(tree) == ["src/a.c"]
    assert _meta(tree)["sparse"] == ["src"]

    wider = _catalog(tmp_path, "docs-src", remotes, thing=("docs", "src"))
    code, out = run(capsys, wider, "clone", "thing")
    assert code == 0, out
    assert len(_notes(out, "thing")) == 1, out
    assert "cloned thing" not in out
    assert _trees(library, "thing") == [tree]
    assert _files(tree) == ["docs/guide.txt", "src/a.c"]
    assert _meta(tree)["sparse"] == ["docs", "src"]

    whole = _catalog(tmp_path, "whole", remotes)
    code, out = run(capsys, whole, "clone", "thing")
    assert code == 0, out
    assert len(_notes(out, "thing")) == 1, out
    assert _trees(library, "thing") == [tree]
    assert _files(tree) == ["docs/guide.txt", "extra/x.txt", "src/a.c"]
    assert _meta(tree)["sparse"] == []


# --------------------------------------------------------------- AC-5


def test_a_failed_catch_up_exits_1_leaves_the_tree_and_is_tried_again(
    tmp_path, library, remotes, capsys
):
    """AC-5: 'When applying the new set fails (no network to fetch the
    blobs ...), the command exits 1 with a message naming the repository
    and the commit, the tree's files and meta stay as they were, and the
    next command tries again.' The tree's origin is moved away while the
    command runs, then put back.
    """
    old = _catalog(tmp_path, "old", remotes, openbmc=OLD)
    run(capsys, old, "clone", "openbmc", "--ref", "1.0.0")
    (tree,) = _trees(library, "openbmc")
    files = _files(tree)
    meta_bytes = (tree / code_mod.TREE_META).read_bytes()
    assert files == [TOP_RECIPE]

    new = _catalog(tmp_path, "new", remotes)
    bare = remotes["ob_bare"]
    away = bare.with_name("openbmc-unreachable.git")
    bare.rename(away)  # the blobs of the new paths cannot be fetched
    try:
        code, out = run(capsys, new, "clone", "foo", "--release", "1.0.0")
    finally:
        away.rename(bare)
    assert code == 1, out
    assert "openbmc" in out and tree.name[:7] in out
    assert _files(tree) == files
    assert (tree / code_mod.TREE_META).read_bytes() == meta_bytes
    assert _trees(library, "openbmc") == [tree]
    assert _trees(library, "foo") == []

    # the next command tries again, and now the origin answers
    code, out = run(capsys, new, "clone", "foo", "--release", "1.0.0")
    assert code == 0, out
    assert len(_notes(out, "openbmc")) == 1, out
    assert _files(tree) == sorted([TOP_RECIPE, UP_RECIPE])
    assert _meta(tree)["sparse"] == list(NEW)
    (foo,) = _trees(library, "foo")
    assert foo.name == remotes["foo"]

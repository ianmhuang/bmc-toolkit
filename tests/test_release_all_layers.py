"""A Release resolves from the recipes of every layer of openbmc/openbmc
(top-level meta-*, upstream-layers/, poky/), and a Code Tree held with
another set of paths catches up with the catalog's. Skipped when git is
not on PATH."""

import json
import shutil

import pytest

from bmc_toolkit.spec import catalog as catalog_mod
from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import git, make_repo, make_scenario, push

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

SHIPPED_SPARSE = catalog_mod.load_catalog().get_repo("openbmc").sparse
OLD_SPARSE = ("/meta-*/**/*.bb", "/meta-*/**/*.inc")  # develop before T76.1

FOO_DIR = "upstream-layers/meta-openembedded/meta-oe/recipes-x/foo"
BAR_DIR = "poky/meta/recipes-y/bar"
THING_DIR = "meta-phosphor/recipes-phosphor/thing"


def _build(root):
    foo_work, _b, foo_url = make_repo(root, "foo", {"foo.c": "int foo;\n"})
    bar_work, _b, bar_url = make_repo(root, "bar", {"bar.c": "int bar;\n"})
    thing_work, _b, thing_url = make_repo(root, "thing", {"t.c": "int t;\n"})
    foo = git("rev-parse", "HEAD", cwd=foo_work)
    bar = git("rev-parse", "HEAD", cwd=bar_work)
    thing = git("rev-parse", "HEAD", cwd=thing_work)
    files = {
        # SRC_URI in the .inc, SRCREV in the recipe that requires it
        f"{FOO_DIR}/foo.inc": (
            'SUMMARY = "foo"\n'
            'SRC_URI = "git://github.com/acme/foo;branch=main;protocol=https"\n'
        ),
        f"{FOO_DIR}/foo_1.0.bb": f'require foo.inc\nSRCREV = "{foo}"\n',
        f"{FOO_DIR}/foo-1.0/fix.patch": "a patch, not a recipe\n",
        f"{BAR_DIR}/bar_2.0.bb": (
            f'SRC_URI = "git://example.org/pub/bar.git;branch=main"\nSRCREV = "{bar}"\n'
        ),
        f"{THING_DIR}/thing_git.bb": (
            'SRC_URI = "git://github.com/openbmc/thing;branch=main"\n'
            f'SRCREV = "{thing}"\n'
        ),
        "README.md": "distro\n",
    }
    ob_work, ob_bare, ob_url = make_repo(root, "openbmc", files, branch="master")
    git("tag", "1.0.0", cwd=ob_work)
    push(ob_work, "1.0.0")
    return {
        "urls": {"foo": foo_url, "bar": bar_url, "thing": thing_url, "ob": ob_url},
        "pins": {"foo": foo, "bar": bar, "thing": thing},
        "ob_bare": ob_bare,
    }


@pytest.fixture
def remotes(tmp_path):
    return make_scenario(tmp_path, "release-all-layers", _build)


def _catalog(tmp_path, remotes, sparse):
    urls = remotes["urls"]
    listed = ", ".join(json.dumps(s) for s in sparse)
    text = (
        MINI_CATALOG
        + f"""
[[repos]]
id = "openbmc"
url = "{urls["ob"]}"
topics = ["release"]
sparse = [{listed}]

[[repos]]
id = "foo"
url = "{urls["foo"]}"
topics = ["x"]

[[repos]]
id = "bar"
url = "{urls["bar"]}"
topics = ["y"]

[[repos]]
id = "thing"
url = "{urls["thing"]}"
topics = ["z"]
"""
    )
    path = tmp_path / "catalog.toml"
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


def _ob_trees(library):
    return [p for p in (library / "code" / "openbmc").iterdir() if p.is_dir()]


def _meta(tree_dir):
    return json.loads((tree_dir / code_mod.TREE_META).read_text("utf-8"))


# ------------------------------------------------------------- AC-1


def test_the_shipped_openbmc_entry_holds_every_recipe_file_and_nothing_else(
    tmp_path, library, remotes, capsys
):
    catalog_file = _catalog(tmp_path, remotes, SHIPPED_SPARSE)
    code, out = run(capsys, catalog_file, "clone", "openbmc", "--ref", "1.0.0")
    assert code == 0, out
    (tree,) = _ob_trees(library)
    assert (tree / FOO_DIR / "foo.inc").is_file()
    assert (tree / FOO_DIR / "foo_1.0.bb").is_file()
    assert (tree / BAR_DIR / "bar_2.0.bb").is_file()
    assert (tree / THING_DIR / "thing_git.bb").is_file()
    assert not (tree / FOO_DIR / "foo-1.0" / "fix.patch").exists()
    assert not (tree / "README.md").exists()


# ------------------------------------------------------------- AC-2


def test_a_release_resolves_pins_under_upstream_layers_and_poky(
    tmp_path, library, remotes, capsys
):
    catalog_file = _catalog(tmp_path, remotes, SHIPPED_SPARSE)
    pins = remotes["pins"]
    code, out = run(capsys, catalog_file, "clone", "foo", "--release", "1.0.0")
    assert code == 0, out
    assert f"cloned foo {pins['foo'][:7]} (release 1.0.0)" in out
    assert f"from {FOO_DIR}/foo_1.0.bb of openbmc" in out
    code, out = run(capsys, catalog_file, "clone", "bar", "--release", "1.0.0")
    assert code == 0, out
    assert f"from {BAR_DIR}/bar_2.0.bb of openbmc" in out
    code, out = run(capsys, catalog_file, "clone", "thing", "--release", "1.0.0")
    assert code == 0, out
    assert f"cloned thing {pins['thing'][:7]} (release 1.0.0)" in out
    argv = ["grep", "openbmc", "SRCREV", "--release", "1.0.0"]
    code, out = run(capsys, catalog_file, *argv)
    assert code == 0, out
    assert f"{FOO_DIR}/foo_1.0.bb:2 | SRCREV" in out
    assert f"{BAR_DIR}/bar_2.0.bb:2 | SRCREV" in out


def _recipes(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")


def test_a_required_inc_is_read_where_the_recipe_requires_it(tmp_path):
    a, b = "a" * 40, "b" * 40
    _recipes(
        tmp_path,
        {
            # mctp's shape: SRC_URI and SRCREV both in the .inc
            "upstream-layers/l/recipes/m/m.inc": (
                f'SRC_URI = "git://github.com/acme/m;branch=main"\nSRCREV = "{a}"\n'
            ),
            "upstream-layers/l/recipes/m/m_1.bb": "require m.inc\n",
            "upstream-layers/l/recipes/m/md_1.bb": "require m.inc\n",
            # ${BPN}.inc, and a SRCREV after the require overrides the .inc's
            "upstream-layers/l/recipes/n/n.inc": (
                f'SRC_URI = "git://github.com/acme/n;branch=main"\nSRCREV = "{a}"\n'
            ),
            "upstream-layers/l/recipes/n/n_2.bb": (
                f'require ${{BPN}}.inc\nSRCREV = "{b}"\n'
            ),
        },
    )
    rev, recipe = code_mod.find_pin_recipe(tmp_path, "m")
    assert rev == a and recipe.startswith("upstream-layers/l/recipes/m/")
    assert code_mod.find_pin_recipe(tmp_path, "n") == (
        b,
        "upstream-layers/l/recipes/n/n_2.bb",
    )


# ------------------------------------------------------------- AC-3


def test_layers_that_pin_one_repository_at_two_commits_still_stop(tmp_path):
    a, b = "a" * 40, "b" * 40
    _recipes(
        tmp_path,
        {
            "meta-phosphor/recipes/q/q_git.bb": (
                f'SRC_URI = "git://github.com/acme/q;branch=main"\nSRCREV = "{a}"\n'
            ),
            "upstream-layers/meta-oe/recipes/q/q_1.bb": (
                f'SRC_URI = "git://github.com/acme/q.git;branch=main"\nSRCREV = "{b}"\n'
            ),
        },
    )
    with pytest.raises(code_mod.CodeError) as err:
        code_mod.find_pin_recipe(tmp_path, "q")
    message = str(err.value)
    assert "at different commits" in message
    assert "meta-phosphor/recipes/q/q_git.bb" in message
    assert "upstream-layers/meta-oe/recipes/q/q_1.bb" in message


# ------------------------------------------------------------- AC-4


def test_a_tree_records_the_paths_it_was_checked_out_with(
    tmp_path, library, remotes, capsys
):
    catalog_file = _catalog(tmp_path, remotes, SHIPPED_SPARSE)
    run(capsys, catalog_file, "clone", "openbmc", "--ref", "1.0.0")
    (tree,) = _ob_trees(library)
    assert _meta(tree)["sparse"] == list(SHIPPED_SPARSE)
    run(capsys, catalog_file, "clone", "foo")
    (foo,) = [p for p in (library / "code" / "foo").iterdir() if p.is_dir()]
    assert _meta(foo)["sparse"] == []  # a full checkout


@pytest.mark.parametrize("recorded", [True, False], ids=["older-set", "unrecorded"])
def test_a_held_tree_catches_up_with_the_catalog_paths_in_place(
    tmp_path, library, remotes, capsys, recorded
):
    old = _catalog(tmp_path, remotes, OLD_SPARSE)
    code, out = run(capsys, old, "clone", "openbmc", "--ref", "1.0.0")
    assert code == 0, out
    (tree,) = _ob_trees(library)
    assert not (tree / FOO_DIR).exists()
    meta = _meta(tree)
    if not recorded:  # a tree written before trees recorded their paths
        meta.pop("sparse")
        (tree / code_mod.TREE_META).write_text(json.dumps(meta), encoding="utf-8")
    new = _catalog(tmp_path, remotes, SHIPPED_SPARSE)
    code, out = run(capsys, new, "clone", "foo", "--release", "1.0.0")
    assert code == 0, out
    notes = [ln for ln in out.splitlines() if ln.startswith("note: openbmc ")]
    assert len(notes) == 1, out
    assert tree.name[:7] in notes[0]
    assert "cloned openbmc" not in out
    assert f"cloned foo {remotes['pins']['foo'][:7]}" in out
    assert _ob_trees(library) == [tree]  # same commit, not cloned again
    after = _meta(tree)
    assert after["sparse"] == list(SHIPPED_SPARSE)
    assert after["fetched_at"] == meta["fetched_at"]
    assert (tree / FOO_DIR / "foo_1.0.bb").is_file()
    # caught up: the next command says nothing about it
    code, out = run(capsys, new, "clone", "bar", "--release", "1.0.0")
    assert code == 0 and "note: openbmc" not in out


def test_clone_of_the_held_openbmc_ref_catches_up_too(
    tmp_path, library, remotes, capsys
):
    old = _catalog(tmp_path, remotes, OLD_SPARSE)
    run(capsys, old, "clone", "openbmc", "--ref", "1.0.0")
    new = _catalog(tmp_path, remotes, SHIPPED_SPARSE)
    code, out = run(capsys, new, "clone", "openbmc", "--ref", "1.0.0")
    assert code == 0, out
    assert out.startswith("note: openbmc "), out
    assert "held openbmc " in out
    (tree,) = _ob_trees(library)
    assert (tree / BAR_DIR / "bar_2.0.bb").is_file()


def test_a_tree_whose_paths_match_is_left_alone_without_git(
    tmp_path, library, remotes, capsys, monkeypatch
):
    catalog_file = _catalog(tmp_path, remotes, SHIPPED_SPARSE)
    run(capsys, catalog_file, "clone", "openbmc", "--ref", "1.0.0")
    lib = code_mod.CodeLibrary(library)
    (tree,) = lib.trees("openbmc")

    def no_git(*args, **kwargs):
        raise AssertionError("git ran for a tree whose paths match")

    monkeypatch.setattr(code_mod, "run_git", no_git)
    assert lib.ensure_sparse(tree, SHIPPED_SPARSE) is None


# ------------------------------------------------------------- AC-5


def test_a_failed_catch_up_leaves_the_tree_and_the_next_command_retries(
    tmp_path, library, remotes, capsys
):
    old = _catalog(tmp_path, remotes, OLD_SPARSE)
    run(capsys, old, "clone", "openbmc", "--ref", "1.0.0")
    (tree,) = _ob_trees(library)
    before = sorted(p.relative_to(tree).as_posix() for p in tree.rglob("*.bb"))
    meta = _meta(tree)
    bare = remotes["ob_bare"]
    away = bare.with_name("openbmc-away.git")
    bare.rename(away)  # the blobs of the new paths cannot be fetched
    new = _catalog(tmp_path, remotes, SHIPPED_SPARSE)
    try:
        code, out = run(capsys, new, "clone", "foo", "--release", "1.0.0")
    finally:
        away.rename(bare)
    assert code == 1, out
    assert "openbmc" in out and tree.name[:7] in out
    assert sorted(p.relative_to(tree).as_posix() for p in tree.rglob("*.bb")) == before
    assert _meta(tree) == meta
    assert not (library / "code" / "foo").exists()
    code, out = run(capsys, new, "clone", "foo", "--release", "1.0.0")
    assert code == 0, out
    assert "note: openbmc " in out


# ------------------------------------------------------------- AC-9


def test_a_hosted_url_matches_owner_and_name_not_the_last_segment(tmp_path):
    a, b = "a" * 40, "b" * 40
    _recipes(
        tmp_path,
        {
            "meta-phosphor/recipes/t/telemetry_git.bb": (
                'SRC_URI = "git://github.com/openbmc/telemetry;branch=master"\n'
                f'SRCREV = "{a}"\n'
            ),
            # a Go recipe whose module list names another telemetry
            "upstream-layers/meta-oe/recipes/c/crucible_1.bb": (
                'SRC_URI = "git://example.org/crucible.git;branch=master"\n'
                "require ${BPN}-go-mods.inc\n"
                f'SRCREV = "{b}"\n'
            ),
            "upstream-layers/meta-oe/recipes/c/crucible-go-mods.inc": (
                'SRC_URI += "git://go.googlesource.com/telemetry;name=telemetry"\n'
                f'SRCREV_telemetry = "{"c" * 40}"\n'
            ),
        },
    )
    url = "https://github.com/openbmc/telemetry.git"
    assert code_mod.find_pin_recipe(tmp_path, "telemetry", url) == (
        a,
        "meta-phosphor/recipes/t/telemetry_git.bb",
    )
    # without a hosted URL (file://, tests) the last segment still decides,
    # and a named entry takes its own SRCREV_<name>, not the recipe's SRCREV
    with pytest.raises(code_mod.CodeError) as err:
        code_mod.find_pin_recipe(tmp_path, "telemetry", "file:///x/telemetry.git")
    assert "c" * 12 in str(err.value) and "b" * 12 not in str(err.value)


def test_the_recipe_reported_is_the_file_that_holds_the_srcrev(tmp_path):
    a = "a" * 40
    _recipes(
        tmp_path,
        {
            "meta-phosphor/recipes/p/p.inc": (
                'SRC_URI = "git://github.com/openbmc/p;branch=master"\n'
                f'SRCREV = "{a}"\n'
            ),
            "meta-phosphor/recipes/p/p-example-native_git.bb": "require p.inc\n",
            "meta-phosphor/recipes/p/p_git.bb": "require p.inc\n",
        },
    )
    url = "https://github.com/openbmc/p.git"
    assert code_mod.find_pin_recipe(tmp_path, "p", url) == (
        a,
        "meta-phosphor/recipes/p/p.inc",
    )


# ------------------------------------------------- round 1 findings


def test_cone_directories_listed_in_another_order_are_the_same_paths(
    tmp_path, monkeypatch
):
    # F1: git lists cone-mode directories sorted; the catalog need not
    files = {"src/a.c": "a\n", "docs/b.md": "b\n", "other/c": "c\n"}
    _work, _bare, url = make_repo(tmp_path, "cone", files)
    lib = code_mod.CodeLibrary(tmp_path / "lib")
    wanted = ("src", "docs")
    tree, _ = lib.clone(
        "cone", url, code_mod.Provenance("ref", "main"), ref="main", sparse=wanted
    )
    meta = _meta(tree.path)
    meta.pop("sparse")  # a tree from before trees recorded their paths
    (tree.path / code_mod.TREE_META).write_text(json.dumps(meta), encoding="utf-8")
    (tree,) = lib.trees("cone")
    calls = []
    real = code_mod.run_git

    def spy(args, **kwargs):
        calls.append(list(args))
        return real(args, **kwargs)

    monkeypatch.setattr(code_mod, "run_git", spy)
    assert lib.ensure_sparse(tree, wanted) is None
    assert not [c for c in calls if c[:2] == ["sparse-checkout", "set"]]
    assert _meta(tree.path)["sparse"] == list(wanted)
    calls.clear()
    (tree,) = lib.trees("cone")
    assert lib.ensure_sparse(tree, ("docs", "src")) is None
    assert calls == []  # recorded, in any order: no git at all


def test_a_named_entry_without_its_own_srcrev_takes_the_plain_one(tmp_path):
    # F2: bitbake falls back from SRCREV_<name> to SRCREV
    a = "a" * 40
    _recipes(
        tmp_path,
        {
            "upstream-layers/l/recipes/x/x_1.bb": (
                'SRC_URI = "git://github.com/acme/x;name=x;branch=main"\n'
                f'SRCREV = "{a}"\n'
            ),
        },
    )
    url = "https://github.com/acme/x.git"
    assert code_mod.find_pin_recipe(tmp_path, "x", url)[0] == a


def test_a_failed_restore_is_not_reported_as_an_unchanged_tree(
    tmp_path, library, remotes, capsys, monkeypatch
):
    # F3: when putting the old paths back fails too, the message says so
    old = _catalog(tmp_path, remotes, OLD_SPARSE)
    run(capsys, old, "clone", "openbmc", "--ref", "1.0.0")

    def fail(work, sparse):
        raise code_mod.CodeError(f"git sparse-checkout failed for {list(sparse)}")

    monkeypatch.setattr(code_mod, "_set_sparse", fail)
    new = _catalog(tmp_path, remotes, SHIPPED_SPARSE)
    code, out = run(capsys, new, "clone", "foo", "--release", "1.0.0")
    assert code == 1, out
    assert "putting the old paths back failed too" in out
    assert "the tree is as it was" not in out


def test_an_inc_required_through_a_parent_directory_is_read_once(tmp_path):
    # F4: require ../common/y.inc lands in pulled_in in rglob's form
    a, b = "a" * 40, "b" * 40
    _recipes(
        tmp_path,
        {
            "upstream-layers/l/recipes/common/y.inc": (
                f'SRC_URI = "git://github.com/acme/y;branch=main"\nSRCREV = "{a}"\n'
            ),
            "upstream-layers/l/recipes/y/y_1.bb": (
                f'require ../common/y.inc\nSRCREV = "{b}"\n'
            ),
        },
    )
    url = "https://github.com/acme/y.git"
    assert code_mod.find_pin_recipe(tmp_path, "y", url) == (
        b,
        "upstream-layers/l/recipes/y/y_1.bb",
    )


def test_a_weak_default_after_a_set_srcrev_does_not_override_it(tmp_path):
    # F5: ?= and ??= set a value only when nothing has
    a, b, c = "a" * 40, "b" * 40, "c" * 40
    _recipes(
        tmp_path,
        {
            "upstream-layers/l/recipes/z/z.inc": (
                f'SRCREV ?= "{a}"\nSRCREV ??= "{c}"\n'
            ),
            "upstream-layers/l/recipes/z/z_1.bb": (
                'SRC_URI = "git://github.com/acme/z;branch=main"\n'
                f'SRCREV = "{b}"\nrequire z.inc\n'
            ),
            "upstream-layers/l/recipes/w/w_1.bb": (
                'SRC_URI = "git://github.com/acme/w;branch=main"\n'
                f'SRCREV ??= "{c}"\nSRCREV ?= "{a}"\n'
            ),
        },
    )
    assert code_mod.find_pin_recipe(tmp_path, "z", "https://github.com/acme/z")[0] == b
    assert code_mod.find_pin_recipe(tmp_path, "w", "https://github.com/acme/w")[0] == a

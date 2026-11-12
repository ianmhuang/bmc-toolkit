"""Independent acceptance tests for release resolution from the recipes of
every layer of openbmc/openbmc (T76.1: AC-1, AC-2, AC-3, AC-9).

AC-1 to AC-3 go through the ``bmcspec`` CLI against local bare git
repositories, with the ``openbmc`` entry's ``sparse`` value taken from the
shipped catalog. AC-9 is about how one recipe's text is read, so it is
checked on ``find_pin_recipe`` with hand-written recipe files (a hosted
catalog URL cannot be cloned in the sandbox). No network. Skipped when git
is not on PATH.
"""

import json
import shutil

import pytest

from bmc_toolkit.spec import catalog as catalog_mod
from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import commit, git, make_repo, push

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

UP = "upstream-layers/meta-openembedded/meta-oe/recipes-x"
POKY = "poky/meta/recipes-y"
TOP = "meta-phosphor/recipes-phosphor"
A, B, C = "a" * 40, "b" * 40, "c" * 40


def _component(tmp_path, name):
    """A repository with two commits; (url, the first commit). A Release
    pins the first one, so resolving to the branch head would show."""
    work, _bare, url = make_repo(tmp_path, name, {f"{name}.c": f"int {name};\n"})
    pinned = git("rev-parse", "HEAD", cwd=work)
    commit(work, {f"{name}.c": f"int {name}_next;\n"}, "second")
    push(work)
    return url, pinned


def _openbmc_files(foo, bar):
    return {
        # AC-2's fixture: SRC_URI in foo.inc, the fixed SRCREV in the .bb
        f"{UP}/foo/foo.inc": (
            'SUMMARY = "foo"\n'
            'SRC_URI = "git://github.com/acme/foo;branch=main;protocol=https"\n'
        ),
        f"{UP}/foo/foo_1.0.bb": (
            f'require foo.inc\nSRCREV = "{foo}"\n# marker-upstream\n'
        ),
        f"{UP}/foo/foo/0001-fix.patch": "--- not a recipe\n",
        f"{UP}/foo/foo_1.0.bbappend": 'EXTRA_OEMESON = "-Dx=1"\n',
        "upstream-layers/meta-openembedded/meta-oe/conf/layer.conf": 'X = "1"\n',
        f"{POKY}/bar/bar_2.0.bb": (
            'SRC_URI = "git://example.org/pub/bar.git;branch=main"\n'
            f'SRCREV = "{bar}"\n# marker-poky\n'
        ),
        "poky/meta-poky/recipes-core/tiny/tiny.inc": 'SUMMARY = "tiny"\n',
        "poky/meta/classes/base.bbclass": "# a class, not a recipe\n",
        # AC-3: one repository pinned at two commits by two layers
        f"{TOP}/q/q_git.bb": (
            f'SRC_URI = "git://github.com/acme/q;branch=main"\nSRCREV = "{A}"\n'
        ),
        f"{UP}/q/q_1.bb": (
            f'SRC_URI = "git://github.com/acme/q.git;branch=main"\nSRCREV = "{B}"\n'
        ),
        "meta-phosphor/conf/layer.conf": 'Y = "1"\n',
        "README.md": "distro\n",
    }


@pytest.fixture
def release(tmp_path):
    foo_url, foo = _component(tmp_path, "foo")
    bar_url, bar = _component(tmp_path, "bar")
    files = _openbmc_files(foo, bar)
    ob_work, _ob_bare, ob_url = make_repo(tmp_path, "openbmc", files, branch="master")
    git("tag", "1.0.0", cwd=ob_work)
    push(ob_work, "1.0.0")
    shipped = catalog_mod.load_catalog().get_repo("openbmc").sparse
    listed = ", ".join(json.dumps(entry) for entry in shipped)
    text = (
        MINI_CATALOG
        + f"""
[[repos]]
id = "openbmc"
url = "{ob_url}"
topics = ["release"]
sparse = [{listed}]

[[repos]]
id = "foo"
url = "{foo_url}"
topics = ["x"]

[[repos]]
id = "bar"
url = "{bar_url}"
topics = ["y"]

[[repos]]
id = "q"
url = "{(tmp_path / "q.git").as_uri()}"
topics = ["z"]
"""
    )
    catalog_file = tmp_path / "catalog.toml"
    catalog_file.write_text(text, encoding="utf-8", newline="")
    return {"catalog": catalog_file, "foo": foo, "bar": bar, "files": files}


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


def _recipes(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")


# --------------------------------------------------------------- AC-1


def test_the_shipped_openbmc_paths_hold_the_recipe_files_of_every_layer_only(
    library, release, capsys
):
    """AC-1: the catalog's openbmc entry holds 'every .bb and .inc file of
    the repository wherever its layer sits (top-level meta-*,
    upstream-layers/<layer>/..., poky/meta*/...), and nothing else'. The
    fixture has recipe files in all three places beside a patch, a
    .bbappend, a .bbclass, layer.conf files and a README: the Code Tree
    must hold exactly the .bb and .inc files.
    """
    code, out = run(capsys, release["catalog"], "clone", "openbmc", "--ref", "1.0.0")
    assert code == 0, out
    (tree,) = _trees(library, "openbmc")
    held = sorted(
        p.relative_to(tree).as_posix()
        for p in tree.rglob("*")
        if p.is_file()
        and p.relative_to(tree).parts[0] != ".git"
        and p.name != code_mod.TREE_META
    )
    expected = sorted(f for f in release["files"] if f.endswith((".bb", ".inc")))
    assert f"{UP}/foo/foo_1.0.bb" in expected  # the fixture is what it says
    assert "poky/meta-poky/recipes-core/tiny/tiny.inc" in expected
    assert held == expected


# --------------------------------------------------------------- AC-2


def test_a_release_resolves_a_pin_held_only_under_upstream_layers(
    library, release, capsys
):
    """AC-2: 'clone REPO --release L resolves a component pinned only by a
    recipe under upstream-layers/ (fixture: upstream-layers/
    meta-openembedded/meta-oe/recipes-x/foo/foo_1.0.bb with a fixed SRCREV,
    SRC_URI in a foo.inc beside it) ... to that SRCREV', and 'grep openbmc
    PATTERN --release L finds text in those recipe files'. The pin is the
    repository's first commit, not its head. AC-9 names the recipe
    reported: the file holding the SRCREV, here the .bb.
    """
    foo = release["foo"]
    code, out = run(capsys, release["catalog"], "clone", "foo", "--release", "1.0.0")
    assert code == 0, out
    (tree,) = _trees(library, "foo")
    assert tree.name == foo
    assert (tree / "foo.c").read_text(encoding="utf-8") == "int foo;\n"
    assert f"cloned foo {foo[:7]} (release 1.0.0)" in out
    assert f"pin: {foo[:7]} from {UP}/foo/foo_1.0.bb of openbmc " in out
    code, out = run(
        capsys,
        release["catalog"],
        "grep",
        "openbmc",
        "marker-upstream",
        "--release",
        "1.0.0",
    )
    assert code == 0, out
    assert f" {UP}/foo/foo_1.0.bb:3 | # marker-upstream" in out


def test_a_release_resolves_a_pin_held_only_under_poky(library, release, capsys):
    """AC-2: '... and one pinned only under poky/meta/, to that SRCREV',
    and grep finds text in that recipe file.
    """
    bar = release["bar"]
    code, out = run(capsys, release["catalog"], "clone", "bar", "--release", "1.0.0")
    assert code == 0, out
    (tree,) = _trees(library, "bar")
    assert tree.name == bar
    assert (tree / "bar.c").read_text(encoding="utf-8") == "int bar;\n"
    assert f"pin: {bar[:7]} from {POKY}/bar/bar_2.0.bb of openbmc " in out
    code, out = run(
        capsys,
        release["catalog"],
        "grep",
        "openbmc",
        "marker-poky",
        "--release",
        "1.0.0",
    )
    assert code == 0, out
    assert f" {POKY}/bar/bar_2.0.bb:3 | # marker-poky" in out


# --------------------------------------------------------------- AC-3


def test_two_layers_pinning_two_commits_stop_when_one_is_under_upstream_layers(
    library, release, capsys
):
    """AC-3: two recipes in different layers that pin the same repository
    at different commits 'still stop with the existing "pin ... at
    different commits" error, now also when one of them is under
    upstream-layers/'. meta-phosphor pins q at aaaa, the upstream layer at
    bbbb: clone must name both recipes and fetch nothing (exit 2, the exit
    code of the existing error).
    """
    code, out = run(capsys, release["catalog"], "clone", "q", "--release", "1.0.0")
    assert code == 2, out
    assert "at different commits" in out
    assert f"{TOP}/q/q_git.bb" in out
    assert f"{UP}/q/q_1.bb" in out
    assert A[:12] in out and B[:12] in out
    assert _trees(library, "q") == []


# --------------------------------------------------------------- AC-9


def test_a_hosted_catalog_url_is_pinned_by_the_same_host_and_path_only(tmp_path):
    """AC-9: a catalog entry whose URL is hosted
    (https://github.com/openbmc/telemetry.git) 'is pinned only by a SRC_URI
    entry with the same host and path (git://github.com/openbmc/telemetry;
    ...), not by another project whose last path segment is the same; a
    file:// URL (tests) keeps the last-segment match'.
    """
    _recipes(
        tmp_path,
        {
            f"{TOP}/telemetry/telemetry_git.bb": (
                'SRC_URI = "git://github.com/openbmc/telemetry;branch=master;'
                'protocol=https"\n'
                f'SRCREV = "{A}"\n'
            ),
            # another host, the same last segment
            f"{UP}/gotele/gotele_1.0.bb": (
                'SRC_URI = "git://go.googlesource.com/telemetry;branch=master"\n'
                f'SRCREV = "{B}"\n'
            ),
            # the same host, another owner
            f"{UP}/fork/fork_1.0.bb": (
                'SRC_URI = "git://github.com/someone/telemetry.git;branch=main"\n'
                f'SRCREV = "{C}"\n'
            ),
        },
    )
    hosted = "https://github.com/openbmc/telemetry.git"
    assert code_mod.find_pin_recipe(tmp_path, "telemetry", hosted) == (
        A,
        f"{TOP}/telemetry/telemetry_git.bb",
    )
    with pytest.raises(code_mod.CodeError) as err:
        code_mod.find_pin_recipe(tmp_path, "telemetry", "file:///mirror/telemetry.git")
    message = str(err.value)
    assert "at different commits" in message
    assert A[:12] in message and B[:12] in message and C[:12] in message


def test_an_entry_with_a_name_takes_the_srcrev_of_that_name(tmp_path):
    """AC-9: 'A SRC_URI entry with name=X takes SRCREV_X, not the recipe's
    own SRCREV.' One recipe fetches its own project (unnamed, SRCREV) and
    widget (name=widget, SRCREV_widget): widget is pinned at SRCREV_widget
    and the project at SRCREV, whichever line comes last, for a hosted and
    for a file:// catalog URL.
    """
    recipe = f"{UP}/combo/combo_git.bb"
    _recipes(
        tmp_path,
        {
            recipe: (
                'SRC_URI = "git://github.com/acme/combo;branch=main;protocol=https \\\n'
                "           git://github.com/openbmc/widget;branch=master;"
                'name=widget;destsuffix=widget \\\n'
                '           file://0001-fix.patch"\n'
                f'SRCREV_widget = "{B}"\n'
                f'SRCREV = "{A}"\n'
                'SRCREV_FORMAT = "default_widget"\n'
            ),
        },
    )
    find = code_mod.find_pin_recipe
    assert find(tmp_path, "widget", "https://github.com/openbmc/widget.git") == (
        B,
        recipe,
    )
    assert find(tmp_path, "widget", "file:///mirror/widget.git") == (B, recipe)
    assert find(tmp_path, "combo", "https://github.com/acme/combo.git") == (A, recipe)


def test_the_recipe_reported_is_the_file_holding_the_srcrev(tmp_path):
    """AC-9: 'The recipe reported (pin: ... from <recipe>) is the file that
    holds the SRCREV assignment.' p: the .inc holds SRC_URI and SRCREV and
    two recipes require it, so the .inc is reported, not a recipe that only
    requires it. r: the .inc holds SRC_URI, the .bb the SRCREV, so the .bb
    is reported.
    """
    _recipes(
        tmp_path,
        {
            f"{TOP}/p/p.inc": (
                'SRC_URI = "git://github.com/openbmc/p;branch=master"\n'
                f'SRCREV = "{A}"\n'
            ),
            f"{TOP}/p/p-example-native_git.bb": "require p.inc\n",
            f"{TOP}/p/p_git.bb": "require p.inc\n",
            f"{TOP}/r/r.inc": 'SRC_URI = "git://github.com/openbmc/r;branch=master"\n',
            f"{TOP}/r/r_git.bb": f'require r.inc\nSRCREV = "{B}"\n',
        },
    )
    assert code_mod.find_pin_recipe(
        tmp_path, "p", "https://github.com/openbmc/p.git"
    ) == (A, f"{TOP}/p/p.inc")
    assert code_mod.find_pin_recipe(
        tmp_path, "r", "https://github.com/openbmc/r.git"
    ) == (B, f"{TOP}/r/r_git.bb")

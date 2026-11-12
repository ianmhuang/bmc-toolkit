"""T76.3: a component OpenBMC builds from a tarball (no SRCREV) is pinned by
the tag its recipe version names (catalog ``release_tag``), and a recipe
fetching a repository's earlier URL (``moved_from``) still pins it. Local
bare repositories stand in for the remotes."""

import shutil
import tomllib
from types import SimpleNamespace

import pytest

from bmc_toolkit.spec import catalog as catalog_mod
from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import _release_pin, main
from tests.conftest import MINI_CATALOG
from tests.test_code import commit, git, make_repo, make_scenario, push

SHIPPED = catalog_mod.load_catalog()
OE = "upstream-layers/openembedded-core/meta"
WIDGET_DIR = f"{OE}/recipes-x/widget"
LEGACY_DIR = "meta-oe/recipes-y/oldtool"


def _write(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")


def _tarball(name):
    return (
        f'SRC_URI = "${{KERNELORG_MIRROR}}/software/utils/{name}/${{BP}}.tar.gz"\n'
        'SRC_URI[sha256sum] = "00"\n'
    )


def _repo(**kw):
    fields = {"id": "widget", "url": "https://example.org/widget.git", "topics": ("x",)}
    fields.update(kw)
    return catalog_mod.Repo(
        fields["id"],
        fields["url"],
        fields["topics"],
        release_tag=fields.get("release_tag", ""),
        moved_from=fields.get("moved_from", ()),
    )


# ------------------------------------------------------- AC-1, AC-2 (offline)


def test_the_recipe_version_names_the_tag(tmp_path):
    _write(tmp_path, {f"{WIDGET_DIR}/widget_2.1.bb": _tarball("widget")})
    pin, recipe, tag = _release_pin(
        SimpleNamespace(path=tmp_path), _repo(release_tag="v{version}")
    )
    assert pin is None
    assert recipe == f"{WIDGET_DIR}/widget_2.1.bb"
    assert tag == ("v2.1", "2.1")


@pytest.mark.parametrize("where", ["bb", "inc"])
def test_pv_replaces_the_file_name_version(tmp_path, where):
    files = {f"{WIDGET_DIR}/widget_2.1.bb": "require widget.inc\n" + _tarball("widget")}
    pv = 'PV = "2.1.1"\n'
    if where == "bb":
        files[f"{WIDGET_DIR}/widget_2.1.bb"] += pv
        files[f"{WIDGET_DIR}/widget.inc"] = 'SUMMARY = "w"\n'
    else:
        files[f"{WIDGET_DIR}/widget.inc"] = pv
    _write(tmp_path, files)
    assert code_mod.find_recipe_version(tmp_path, "widget")[0] == "2.1.1"


def test_a_srcrev_recipe_still_wins(tmp_path):
    rev = "a" * 40
    _write(
        tmp_path,
        {
            f"{WIDGET_DIR}/widget_2.1.bb": _tarball("widget"),
            "meta-acme/recipes-x/widget/widget_git.bb": (
                'SRC_URI = "git://example.org/widget.git;branch=main"\n'
                f'SRCREV = "{rev}"\n'
            ),
        },
    )
    pin, recipe, tag = _release_pin(
        SimpleNamespace(path=tmp_path), _repo(release_tag="v{version}")
    )
    assert (pin, tag) == (rev, None)
    assert recipe == "meta-acme/recipes-x/widget/widget_git.bb"


def test_recipes_at_different_versions_are_listed(tmp_path):
    _write(
        tmp_path,
        {
            f"{WIDGET_DIR}/widget_2.1.bb": _tarball("widget"),
            "meta-acme/recipes-x/widget/widget_2.0.bb": _tarball("widget"),
        },
    )
    with pytest.raises(code_mod.CodeError) as exc:
        _release_pin(SimpleNamespace(path=tmp_path), _repo(release_tag="v{version}"))
    text = str(exc.value)
    assert "build widget at different versions" in text
    assert f"{WIDGET_DIR}/widget_2.1.bb is version 2.1" in text
    assert "meta-acme/recipes-x/widget/widget_2.0.bb is version 2.0" in text


def test_same_version_in_two_layers_is_one(tmp_path):
    _write(
        tmp_path,
        {
            f"{WIDGET_DIR}/widget_2.1.bb": _tarball("widget"),
            "meta-acme/recipes-x/widget/widget_2.1.bb": _tarball("widget"),
        },
    )
    assert code_mod.find_recipe_version(tmp_path, "widget")[0] == "2.1"


def test_a_longer_recipe_name_is_not_the_entry(tmp_path):
    _write(tmp_path, {f"{WIDGET_DIR}/widget-extra_9.0.bb": _tarball("widget-extra")})
    with pytest.raises(
        code_mod.NoRecipe, match="no recipe in this release names widget"
    ):
        _release_pin(SimpleNamespace(path=tmp_path), _repo(release_tag="v{version}"))


def test_without_release_tag_nothing_changes(tmp_path):
    _write(tmp_path, {f"{WIDGET_DIR}/widget_2.1.bb": _tarball("widget")})
    with pytest.raises(
        code_mod.NoRecipe, match="no recipe in this release names widget"
    ):
        _release_pin(SimpleNamespace(path=tmp_path), _repo())


# ---------------------------------------------------------- AC-5 (offline)


def test_a_recipe_fetching_an_earlier_url_pins_the_entry(tmp_path):
    rev = "b" * 40
    _write(
        tmp_path,
        {
            "meta-oe/recipes-kernel/ipmitool/ipmitool_1.8.19.bb": (
                'SRC_URI = "git://github.com/ipmitool/ipmitool;protocol=https;'
                f'branch=master"\nSRCREV = "{rev}"\n'
            )
        },
    )
    shipped = SHIPPED.get_repo("ipmitool")
    pin, _recipe = code_mod.find_pin_recipe(
        tmp_path, shipped.id, shipped.url, shipped.moved_from
    )
    assert pin == rev
    with pytest.raises(code_mod.NoRecipe):
        code_mod.find_pin_recipe(tmp_path, shipped.id, shipped.url)


# ------------------------------------------------------------------ AC-4


@pytest.mark.parametrize(
    ("repo_id", "url", "template"),
    [
        (
            "i2c-tools",
            "https://git.kernel.org/pub/scm/utils/i2c-tools/i2c-tools.git",
            "v{version}",
        ),
        (
            "ethtool",
            "https://git.kernel.org/pub/scm/network/ethtool/ethtool.git",
            "v{version}",
        ),
        ("tpm2-tss", "https://github.com/tpm2-software/tpm2-tss.git", "{version}"),
        ("tpm2-tools", "https://github.com/tpm2-software/tpm2-tools.git", "{version}"),
    ],
)
def test_shipped_tag_entries(repo_id, url, template):
    repo = SHIPPED.get_repo(repo_id)
    assert (repo.url, repo.release_tag, repo.owner, repo.ref) == (url, template, "", "")


@pytest.mark.parametrize(
    ("topic", "ids"),
    [
        ("i2c", {"i2c-tools"}),
        ("tpm", {"tpm2-tss", "tpm2-tools"}),
        ("ethtool", {"ethtool"}),
    ],
)
def test_shipped_topics(topic, ids):
    assert ids <= {r.id for r in SHIPPED.by_topic(topic)}


def test_shipped_ipmitool_names_its_former_home():
    assert SHIPPED.get_repo("ipmitool").moved_from == (
        "https://github.com/ipmitool/ipmitool.git",
    )


# ------------------------------------------------------------------ AC-6


def _parse(**extra):
    entry = {"id": "widget", "url": "https://example.org/widget.git", "topics": ["x"]}
    entry.update(extra)
    data = tomllib.loads(MINI_CATALOG)
    data["repos"] = [entry]
    return catalog_mod.parse_catalog(data)


@pytest.mark.parametrize(
    "template", ["v{version}", "{version}", "release-{version}-final"]
)
def test_release_tag_accepted(template):
    assert _parse(release_tag=template).repos[0].release_tag == template


@pytest.mark.parametrize(
    "template",
    ["v1.0", "{ver}", "{version}{version}", "v{version}-{n}", "v {version}", ""],
)
def test_release_tag_refused(template):
    with pytest.raises(catalog_mod.CatalogError, match="release_tag"):
        _parse(release_tag=template)


@pytest.mark.parametrize("old", ["git://github.com/x/y", "github.com/x/y", 3])
def test_moved_from_refused(old):
    with pytest.raises(catalog_mod.CatalogError, match="moved_from"):
        _parse(moved_from=[old])


@pytest.mark.parametrize(
    "extra",
    [{"release_tag": "v{version}"}, {"moved_from": ["https://example.org/old.git"]}],
)
def test_not_on_a_vendor_tree(extra):
    with pytest.raises(catalog_mod.CatalogError, match="vendor tree"):
        _parse(id="acme-widget", owner="acme", **extra)


# ------------------------------------------------- AC-1..AC-3, AC-5 (git)

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _build(root):
    work, bare, url = make_repo(root, "widget", {"src/widget.c": "int widget20;\n"})
    git("tag", "-a", "v2.0", "-m", "2.0", cwd=work)
    v21 = commit(work, {"src/widget.c": "int widget21;\n"}, "2.1")
    git("tag", "-a", "v2.1", "-m", "2.1", cwd=work)
    tip = commit(work, {"src/widget.c": "int widget22dev;\n"}, "dev")
    push(work, "main")
    push(work, "v2.0")
    push(work, "v2.1")
    lwork, _lb, lurl = make_repo(root, "oldtool", {"o.c": "int oldtool;\n"})
    legacy = git("rev-parse", "HEAD", cwd=lwork)
    files = {
        f"{WIDGET_DIR}/widget_2.1.bb": _tarball("widget"),
        f"{LEGACY_DIR}/oldtool_1.0.bb": (
            'SRC_URI = "git://github.com/old/legacy;protocol=https;branch=master"\n'
            f'SRCREV = "{legacy}"\n'
        ),
        "README.md": "distro\n",
    }
    ob_work, _ob, ob_url = make_repo(root, "openbmc", files, branch="master")
    git("tag", "1.0.0", cwd=ob_work)
    commit(ob_work, {"README.md": "distro 2\n"}, "same versions")
    git("tag", "2.0.0", cwd=ob_work)
    git("rm", "-q", f"{WIDGET_DIR}/widget_2.1.bb", cwd=ob_work)
    commit(ob_work, {f"{WIDGET_DIR}/widget_9.9.bb": _tarball("widget")}, "9.9")
    git("tag", "3.0.0", cwd=ob_work)
    for name in ("1.0.0", "2.0.0", "3.0.0"):
        push(ob_work, name)
    return {
        "widget": url,
        "widget_bare": bare,
        "oldtool": lurl,
        "ob": ob_url,
        "v21": v21,
        "tip": tip,
        "legacy": legacy,
    }


@pytest.fixture
def remotes(tmp_path):
    return make_scenario(tmp_path, "release-tags", _build)


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


def _catalog(tmp_path, remotes):
    sparse = ", ".join(f'"{s}"' for s in SHIPPED.get_repo("openbmc").sparse)
    text = (
        MINI_CATALOG
        + f"""
[[repos]]
id = "openbmc"
url = "{remotes["ob"]}"
topics = ["release"]
sparse = [{sparse}]

[[repos]]
id = "widget"
url = "{remotes["widget"]}"
topics = ["x"]
release_tag = "v{{version}}"

[[repos]]
id = "oldtool"
url = "{remotes["oldtool"]}"
topics = ["y"]
moved_from = ["https://github.com/old/legacy.git"]
"""
    )
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def run(capsys, catalog_file, *argv):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@needs_git
def test_release_clone_checks_out_the_tag(tmp_path, remotes, library, capsys):
    cat = _catalog(tmp_path, remotes)
    code, out = run(capsys, cat, "clone", "widget", "--release", "1.0.0")
    assert code == 0, out
    v21 = remotes["v21"]
    assert f"cloned widget {v21[:7]} (v2.1 " in out
    assert (
        f"pin: {v21[:7]} tag v2.1 (version 2.1) from {WIDGET_DIR}/widget_2.1.bb "
        "of openbmc " in out
    )
    assert (library / "code" / "widget" / v21).is_dir()


@needs_git
def test_a_held_tag_needs_no_remote(tmp_path, remotes, library, capsys):
    cat = _catalog(tmp_path, remotes)
    assert run(capsys, cat, "clone", "widget", "--release", "1.0.0")[0] == 0
    run(capsys, cat, "clone", "openbmc", "--ref", "2.0.0")
    bare = remotes["widget_bare"]
    away = tmp_path / "gone"
    bare.rename(away)  # nothing can be fetched from the widget remote now
    try:
        code, out = run(capsys, cat, "clone", "widget", "--release", "2.0.0")
    finally:
        away.rename(bare)
    assert code == 0, out
    assert f"held widget {remotes['v21'][:7]}" in out


@needs_git
def test_a_missing_tag_is_named(tmp_path, remotes, library, capsys):
    cat = _catalog(tmp_path, remotes)
    code, out = run(capsys, cat, "clone", "widget", "--release", "3.0.0")
    assert code == 2, out
    assert "the release builds widget 9.9, but" in out
    assert "has no tag v9.9" in out
    widget_dir = library / "code" / "widget"
    assert not widget_dir.exists() or not [
        p for p in widget_dir.iterdir() if p.is_dir() and not p.name.startswith(".")
    ]


@needs_git
def test_grep_reads_the_tag_tree_by_release(tmp_path, remotes, library, capsys):
    cat = _catalog(tmp_path, remotes)
    assert run(capsys, cat, "clone", "widget", "--release", "1.0.0")[0] == 0
    code, out = run(capsys, cat, "grep", "widget", "widget21", "--release", "1.0.0")
    assert code == 0, out
    assert f"widget@{remotes['v21'][:7]} src/widget.c:1 | int widget21;" in out
    (library / "config.toml").write_text(
        '[code]\nrelease = "1.0.0"\n', encoding="utf-8", newline=""
    )
    code, out = run(capsys, cat, "grep", "widget", "widget21")
    assert code == 0, out
    assert f"widget@{remotes['v21'][:7]}" in out


@needs_git
def test_plain_clone_is_unchanged(tmp_path, remotes, library, capsys):
    cat = _catalog(tmp_path, remotes)
    code, out = run(capsys, cat, "clone", "widget")
    assert code == 0, out
    assert f"cloned widget {remotes['tip'][:7]} (main " in out


@needs_git
def test_moved_from_pins_and_clones_from_url(tmp_path, remotes, library, capsys):
    cat = _catalog(tmp_path, remotes)
    code, out = run(capsys, cat, "clone", "oldtool", "--release", "1.0.0")
    assert code == 0, out
    legacy = remotes["legacy"]
    assert f"pin: {legacy[:7]} from {LEGACY_DIR}/oldtool_1.0.bb" in out
    tree = code_mod.CodeLibrary(library).trees("oldtool")[0]
    assert tree.url == remotes["oldtool"]

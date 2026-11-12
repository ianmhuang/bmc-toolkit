"""Independent acceptance tests for tarball recipes pinned by their version's
tag and for repositories that moved (T76.3: AC-1 to AC-6).

AC-1, AC-2, AC-3 and AC-5 go through the ``bmcspec`` CLI against local bare
git repositories: a component whose tags are ``v1.0`` and ``v1.1`` plus an
untagged tip, one whose tag is the bare version, one with a branch named
like its tag, one whose tag is a date, a repository a recipe still
fetches at its earlier URL, and an openbmc remote whose tags are releases
with different recipes. AC-4 reads the shipped catalog, asks ``repos
--topic`` for it, and runs each shipped ``release_tag`` against the recipe
file names and versions OpenBMC has (only the URL is swapped for a local
remote carrying the projects' tag names). AC-6 loads catalog files. No
network.
"""

import json
import re
import shutil

import pytest

from bmc_toolkit.spec import catalog as catalog_mod
from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import commit, git, make_repo, make_scenario, push

SHIPPED = catalog_mod.load_catalog()

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

# layers, kept short (Windows path length): 2.18.0 has poky/, master has
# upstream-layers/
POKY = "poky/meta/recipes"
UP = "upstream-layers/oe/recipes"
SEC = "meta-security/recipes"
ACME = "meta-acme/recipes"
OE = "meta-oe/recipes"

# where the "oldtool" repository used to live; its last path segment is not
# the entry id, so only moved_from can make a recipe fetching it a pin
FORMER = "github.com/old-org/former-name"

# AC-4: the projects' URLs and tag forms
TOOLS = {
    "i2c-tools": (
        "https://git.kernel.org/pub/scm/utils/i2c-tools/i2c-tools.git",
        "v{version}",
    ),
    "ethtool": (
        "https://git.kernel.org/pub/scm/network/ethtool/ethtool.git",
        "v{version}",
    ),
    "tpm2-tss": ("https://github.com/tpm2-software/tpm2-tss.git", "{version}"),
    "tpm2-tools": ("https://github.com/tpm2-software/tpm2-tools.git", "{version}"),
}
# the tags the description names for master and 2.18.0
TOOL_TAGS = ["v4.4", "v6.11", "v7.1", "4.1.3", "5.7"]


def _tarball(name, extra=""):
    """A recipe that fetches a release tarball: no git URL, no SRCREV."""
    return (
        f'SUMMARY = "{name}"\n'
        f'SRC_URI = "https://downloads.example.org/{name}/${{BP}}.tar.gz"\n'
        'SRC_URI[sha256sum] = "00"\n' + extra
    )


def _git_recipe(location, rev):
    return (
        f'SRC_URI = "git://{location};protocol=https;branch=master"\n'
        f'SRCREV = "{rev}"\n'
    )


def _build(root):
    # gizmo: v1.0 (annotated) on the first commit, v1.1 (lightweight) on the
    # second, an untagged tip on main
    work, _bare, gizmo_url = make_repo(
        root, "gizmo", {"src/gizmo.c": "int gizmo_v10;\n"}
    )
    c10 = git("rev-parse", "HEAD", cwd=work)
    git("tag", "-a", "v1.0", "-m", "1.0", cwd=work)
    c11 = commit(work, {"src/gizmo.c": "int gizmo_v11;\n"}, "1.1")
    git("tag", "v1.1", cwd=work)
    tip = commit(work, {"src/gizmo.c": "int gizmo_vnext;\n"}, "next")
    for name in ("main", "v1.0", "v1.1"):
        push(work, name)

    # plain: its tags are the bare version
    work, _bare, plain_url = make_repo(
        root, "plain", {"lib/plain.c": "int plain_321;\n"}
    )
    p321 = git("rev-parse", "HEAD", cwd=work)
    git("tag", "3.2.1", cwd=work)
    commit(work, {"lib/plain.c": "int plain_next;\n"}, "next")
    for name in ("main", "3.2.1"):
        push(work, name)

    # oldtool: pinned by SRCREV at its first commit
    work, _bare, old_url = make_repo(
        root, "oldtool", {"tool.c": "int oldtool_pinned;\n"}
    )
    pinned = git("rev-parse", "HEAD", cwd=work)
    commit(work, {"tool.c": "int oldtool_next;\n"}, "next")
    push(work, "main")

    # tools: one remote carrying the tag names of the four shipped projects
    work, _bare, tools_url = make_repo(root, "tools", {"tool.c": "int tool;\n"})
    tags = {}
    for name in TOOL_TAGS:
        tags[name] = commit(work, {"tool.c": f"int tool_at_{name};\n"}, name)
        git("tag", "-a", name, "-m", name, cwd=work)
    push(work, "main")
    for name in TOOL_TAGS:
        push(work, name)

    # twin: the tag v2.0 on the first commit and a branch of the same name
    # at the tip (review round 1 F3)
    work, _bare, twin_url = make_repo(root, "twin", {"twin.c": "int twin_v20;\n"})
    t20 = git("rev-parse", "HEAD", cwd=work)
    git("tag", "-a", "v2.0", "-m", "2.0", cwd=work)
    twin_tip = commit(work, {"twin.c": "int twin_next;\n"}, "next")
    push(work, "main")
    push(work, "refs/tags/v2.0")
    git("push", "-q", "origin", f"{twin_tip}:refs/heads/v2.0", cwd=work)

    # dated: its tag is a date, which reads like a commit id (round 1 F4)
    work, _bare, dated_url = make_repo(root, "dated", {"d.c": "int dated_tag;\n"})
    d1 = git("rev-parse", "HEAD", cwd=work)
    git("tag", "20240305", cwd=work)
    commit(work, {"d.c": "int dated_next;\n"}, "next")
    push(work, "main")
    push(work, "refs/tags/20240305")

    files = {
        f"{POKY}/gizmo/gizmo_1.0.bb": _tarball("gizmo"),
        f"{POKY}/twin/twin_2.0.bb": _tarball("twin"),
        f"{POKY}/dated/dated_20240305.bb": _tarball("dated"),
        f"{SEC}/plain/plain_3.2.1.bb": _tarball("plain"),
        f"{OE}/oldtool/oldtool_1.8.bb": _git_recipe(FORMER, pinned),
        f"{POKY}/i2c-tools/i2c-tools_4.4.bb": _tarball("i2c-tools"),
        f"{POKY}/ethtool/ethtool_6.11.bb": _tarball("ethtool"),
        f"{SEC}/tpm2-tss/tpm2-tss_4.1.3.bb": _tarball("tpm2-tss"),
        f"{SEC}/tpm2-tools/tpm2-tools_5.7.bb": _tarball("tpm2-tools"),
        "README.md": "distro\n",
    }
    ob, _ob_bare, ob_url = make_repo(root, "openbmc", files, branch="master")
    git("tag", "1.0.0", cwd=ob)
    push(ob, "1.0.0")

    def release(name, removed=(), added=None):
        for rel in removed:
            (ob / rel).unlink()
        commit(ob, added or {}, name)
        git("tag", name, cwd=ob)
        push(ob, name)

    # 1.5.0: the same recipes as 1.0.0, another openbmc commit
    release("1.5.0", added={"README.md": "distro, later\n"})
    # 2.0.0: the version comes from PV (an .inc for gizmo, the recipe itself
    # for plain); ethtool moves to 7.1 under upstream-layers/
    release(
        "2.0.0",
        removed=[
            f"{POKY}/gizmo/gizmo_1.0.bb",
            f"{SEC}/plain/plain_3.2.1.bb",
            f"{POKY}/ethtool/ethtool_6.11.bb",
        ],
        added={
            f"{UP}/gizmo/gizmo_1.x.bb": "require gizmo.inc\n" + _tarball("gizmo"),
            f"{UP}/gizmo/gizmo.inc": 'PV = "1.1"\n',
            f"{SEC}/plain/plain_3.x.bb": _tarball("plain", 'PV = "3.2.1"\n'),
            f"{UP}/ethtool/ethtool_7.1.bb": _tarball("ethtool"),
        },
    )
    # 3.0.0: two layers build gizmo at different versions
    release(
        "3.0.0",
        removed=[f"{UP}/gizmo/gizmo_1.x.bb", f"{UP}/gizmo/gizmo.inc"],
        added={
            f"{UP}/gizmo/gizmo_1.1.bb": _tarball("gizmo"),
            f"{ACME}/gizmo/gizmo_1.0.bb": _tarball("gizmo"),
        },
    )
    # 4.0.0: a version the remote has no tag for
    release(
        "4.0.0",
        removed=[f"{UP}/gizmo/gizmo_1.1.bb", f"{ACME}/gizmo/gizmo_1.0.bb"],
        added={f"{UP}/gizmo/gizmo_7.7.bb": _tarball("gizmo")},
    )
    # 5.0.0: no recipe named gizmo, only one with a longer name
    release(
        "5.0.0",
        removed=[f"{UP}/gizmo/gizmo_7.7.bb"],
        added={f"{UP}/gizmo-utils/gizmo-utils_2.0.bb": _tarball("gizmo-utils")},
    )
    # 6.0.0: a tarball recipe at 1.1 and a recipe pinning v1.0's commit by SRCREV
    release(
        "6.0.0",
        added={
            f"{UP}/gizmo/gizmo_1.1.bb": _tarball("gizmo"),
            f"{ACME}/gizmo/gizmo_git.bb": _git_recipe(
                "git.example.org/acme/gizmo", c10
            ),
        },
    )
    # 7.0.0: the only recipe named gizmo has no version to form a tag from
    release(
        "7.0.0",
        removed=[f"{UP}/gizmo/gizmo_1.1.bb", f"{ACME}/gizmo/gizmo_git.bb"],
        added={f"{UP}/gizmo/gizmo_git.bb": _tarball("gizmo")},
    )
    return {
        "gizmo": gizmo_url,
        "twin": twin_url,
        "dated": dated_url,
        "t20": t20,
        "d1": d1,
        "plain": plain_url,
        "oldtool": old_url,
        "tools": tools_url,
        "ob": ob_url,
        "c10": c10,
        "c11": c11,
        "tip": tip,
        "p321": p321,
        "pinned": pinned,
        "tags": tags,
    }


@pytest.fixture
def remotes(tmp_path):
    return make_scenario(tmp_path, "review-tarballtags", _build)


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


def _entry(repo_id, url, **keys):
    lines = ["[[repos]]", f'id = "{repo_id}"', f'url = "{url}"']
    keys.setdefault("topics", ["x"])
    lines += [f"{key} = {json.dumps(value)}" for key, value in keys.items()]
    return "\n".join(lines) + "\n"


def _catalog(
    tmp_path, remotes, *, tagged=True, moved=True, tools=False, name="catalog.toml"
):
    """A catalog over the local remotes. ``tagged`` and ``moved`` leave the
    key under test off the gizmo and oldtool entries; ``tools`` adds the four
    shipped entries with their shipped ``release_tag`` and a local URL."""
    gizmo = {"release_tag": "v{version}"} if tagged else {}
    old = {"moved_from": [f"https://{FORMER}.git"]} if moved else {}
    parts = [
        MINI_CATALOG,
        _entry(
            "openbmc", remotes["ob"], sparse=list(SHIPPED.get_repo("openbmc").sparse)
        ),
        _entry("gizmo", remotes["gizmo"], **gizmo),
        _entry("plain", remotes["plain"], release_tag="{version}"),
        _entry("twin", remotes["twin"], release_tag="v{version}"),
        _entry("dated", remotes["dated"], release_tag="{version}"),
        _entry("oldtool", remotes["oldtool"], **old),
    ]
    if tools:
        for repo_id in TOOLS:
            shipped = SHIPPED.get_repo(repo_id)
            assert shipped is not None, f"the shipped catalog has no '{repo_id}'"
            keys = {"release_tag": shipped.release_tag}
            if shipped.sparse:
                keys["sparse"] = list(shipped.sparse)
            parts.append(_entry(repo_id, remotes["tools"], **keys))
    path = tmp_path / name
    path.write_text("\n".join(parts), encoding="utf-8", newline="")
    # the keys under test are read from the file, not ignored
    loaded = catalog_mod.load_catalog(path)
    assert loaded.get_repo("plain").release_tag == "{version}"
    assert loaded.get_repo("gizmo").release_tag == ("v{version}" if tagged else "")
    assert list(loaded.get_repo("oldtool").moved_from) == old.get("moved_from", [])
    return path


def _run(capsys, catalog_file, *argv):
    args = ["--catalog", str(catalog_file)] if catalog_file else []
    code = main([*args, *argv])
    return code, capsys.readouterr().out


def _clone(capsys, cat, repo_id, release):
    return _run(capsys, cat, "clone", repo_id, "--release", release)


def _trees(library, repo_id):
    """commit -> the .bmc-tree.json of every Code Tree held of the repository."""
    rdir = library / "code" / repo_id
    out = {}
    if not rdir.is_dir():
        return out
    for tdir in rdir.iterdir():
        meta = tdir / code_mod.TREE_META
        if meta.is_file():
            out[tdir.name] = json.loads(meta.read_text(encoding="utf-8"))
    return out


def _nothing_held(library, repo_id):
    """No Code Tree of the repository in the Library: no tree record and no
    commit directory (a dot-named temporary directory is not a tree)."""
    rdir = library / "code" / repo_id
    if not rdir.is_dir():
        return True
    left = [p.name for p in rdir.iterdir() if p.is_dir() and p.name[:1] != "."]
    return not left and not _trees(library, repo_id)


def _pin_line(out):
    lines = [ln for ln in out.splitlines() if ln.startswith("pin:")]
    assert len(lines) == 1, out
    return lines[0]


def _message(out):
    """The last line printed: the failure message."""
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert lines, "nothing was printed"
    return lines[-1]


def _names_version(text, version):
    """The bare version appears on its own, not only inside a tag (v1.0) or
    a recipe file name (gizmo_1.0.bb)."""
    return re.search(rf"(?<![\w.]){re.escape(version)}(?![\w.])", text) is not None


def _hit(repo_id, commit_id, path, text):
    return f"{repo_id}@{commit_id[:7]} {path}:1 | {text}"


# --------------------------------------------------------------- AC-1


@needs_git
def test_ac1_release_checks_out_the_tag_the_recipe_version_names(
    tmp_path, remotes, library, capsys
):
    """AC-1: with ``release_tag = "v{version}"`` and no recipe pinning by
    SRCREV, ``--release`` takes 1.0 from ``gizmo_1.0.bb``, forms ``v1.0``
    and checks out that tag's commit (the first commit, not the branch tip);
    the ``pin:`` line carries the tag, the version and the recipe."""
    cat = _catalog(tmp_path, remotes)
    code, out = _clone(capsys, cat, "gizmo", "1.0.0")
    assert code == 0, out
    c10 = remotes["c10"]
    assert set(_trees(library, "gizmo")) == {c10}, out
    held = library / "code" / "gizmo" / c10 / "src" / "gizmo.c"
    assert held.read_text(encoding="utf-8") == "int gizmo_v10;\n"
    pin = _pin_line(out)
    assert c10[:7] in pin
    assert "v1.0" in pin
    assert _names_version(pin, "1.0"), pin
    assert f"{POKY}/gizmo/gizmo_1.0.bb" in pin


@needs_git
def test_ac1_a_bare_version_template_names_the_tag(tmp_path, remotes, library, capsys):
    """AC-1: the template is the project's tag form: ``"{version}"`` turns
    ``plain_3.2.1.bb`` into the tag ``3.2.1``, with no prefix."""
    cat = _catalog(tmp_path, remotes)
    code, out = _clone(capsys, cat, "plain", "1.0.0")
    assert code == 0, out
    p321 = remotes["p321"]
    assert set(_trees(library, "plain")) == {p321}, out
    pin = _pin_line(out)
    assert p321[:7] in pin
    assert _names_version(pin, "3.2.1"), pin
    assert "v3.2.1" not in pin
    assert f"{SEC}/plain/plain_3.2.1.bb" in pin


@needs_git
def test_ac1_pv_replaces_the_file_names_version(tmp_path, remotes, library, capsys):
    """AC-1: 'a ``PV = "..."`` in the recipe or an ``.inc`` it requires
    replaces the file name's version'. At 2.0.0 ``gizmo_1.x.bb`` requires
    ``gizmo.inc`` with ``PV = "1.1"`` (tag v1.1; v1.x does not exist) and
    ``plain_3.x.bb`` sets ``PV = "3.2.1"`` itself."""
    cat = _catalog(tmp_path, remotes)
    code, out = _clone(capsys, cat, "gizmo", "2.0.0")
    assert code == 0, out
    c11 = remotes["c11"]
    assert set(_trees(library, "gizmo")) == {c11}, out
    held = library / "code" / "gizmo" / c11 / "src" / "gizmo.c"
    assert held.read_text(encoding="utf-8") == "int gizmo_v11;\n"
    pin = _pin_line(out)
    assert c11[:7] in pin
    assert "v1.1" in pin
    assert _names_version(pin, "1.1"), pin
    assert f"{UP}/gizmo/gizmo" in pin

    code, out = _clone(capsys, cat, "plain", "2.0.0")
    assert code == 0, out
    assert set(_trees(library, "plain")) == {remotes["p321"]}, out
    assert _names_version(_pin_line(out), "3.2.1")


@needs_git
def test_ac1_a_recipe_pinning_by_srcrev_still_wins(tmp_path, remotes, library, capsys):
    """AC-1: 'A recipe that does pin it by SRCREV still wins'. At 6.0.0 a
    tarball recipe says 1.1 and ``gizmo_git.bb`` pins the first commit: the
    tree is the SRCREV, the pin line names that recipe and no tag. The tree
    2.0.0 reached through the tag v1.1 stays, and each release reads its
    own."""
    cat = _catalog(tmp_path, remotes)
    c10, c11 = remotes["c10"], remotes["c11"]
    code, out = _clone(capsys, cat, "gizmo", "2.0.0")
    assert code == 0, out
    assert set(_trees(library, "gizmo")) == {c11}, out

    code, out = _clone(capsys, cat, "gizmo", "6.0.0")
    assert code == 0, out
    assert set(_trees(library, "gizmo")) == {c10, c11}, out
    pin = _pin_line(out)
    assert c10[:7] in pin
    assert f"{ACME}/gizmo/gizmo_git.bb" in pin
    assert "v1.1" not in pin
    assert "gizmo_1.1.bb" not in pin

    code, out = _run(capsys, cat, "grep", "gizmo", "gizmo_v", "--release", "6.0.0")
    assert code == 0, out
    assert _hit("gizmo", c10, "src/gizmo.c", "int gizmo_v10;") in out
    code, out = _run(capsys, cat, "grep", "gizmo", "gizmo_v", "--release", "2.0.0")
    assert code == 0, out
    assert _hit("gizmo", c11, "src/gizmo.c", "int gizmo_v11;") in out


@needs_git
def test_ac1_two_releases_naming_one_tag_share_one_tree(
    tmp_path, remotes, library, capsys
):
    """AC-1 and AC-3: 1.0.0 and 1.5.0 both build gizmo 1.0, so both resolve
    to the commit of v1.0: one tree, read under either release."""
    cat = _catalog(tmp_path, remotes)
    c10 = remotes["c10"]
    for release in ("1.0.0", "1.5.0"):
        code, out = _clone(capsys, cat, "gizmo", release)
        assert code == 0, out
        pin = _pin_line(out)
        assert c10[:7] in pin
        assert "v1.0" in pin
    assert set(_trees(library, "gizmo")) == {c10}
    for release in ("1.0.0", "1.5.0"):
        code, out = _run(capsys, cat, "grep", "gizmo", "gizmo_v", "--release", release)
        assert code == 0, out
        assert _hit("gizmo", c10, "src/gizmo.c", "int gizmo_v10;") in out


@needs_git
def test_ac1_the_tag_is_checked_out_not_a_branch_of_its_name(
    tmp_path, remotes, library, capsys
):
    """AC-1: 'forms the tag, and checks out that tag's commit'. The remote
    has the tag ``v2.0`` on its first commit and a branch ``v2.0`` at the
    tip: the tree is the tag's commit, with the tag's source."""
    cat = _catalog(tmp_path, remotes)
    code, out = _clone(capsys, cat, "twin", "1.0.0")
    assert code == 0, out
    t20 = remotes["t20"]
    assert set(_trees(library, "twin")) == {t20}, out
    held = library / "code" / "twin" / t20 / "twin.c"
    assert held.read_text(encoding="utf-8") == "int twin_v20;\n"
    pin = _pin_line(out)
    assert t20[:7] in pin
    assert "v2.0" in pin


@needs_git
def test_ac1_a_version_that_reads_like_a_commit_id_is_a_tag(
    tmp_path, remotes, library, capsys
):
    """AC-1: with ``"{version}"`` the tag is the version itself, here a date
    (``dated_20240305.bb``, tag ``20240305``, all hex digits): it is checked
    out as a tag, and a second release building the same version finds the
    same tree and reads it."""
    cat = _catalog(tmp_path, remotes)
    d1 = remotes["d1"]
    for release in ("1.0.0", "1.5.0"):
        code, out = _clone(capsys, cat, "dated", release)
        assert code == 0, out
        pin = _pin_line(out)
        assert d1[:7] in pin
        assert "20240305" in pin
    assert set(_trees(library, "dated")) == {d1}
    code, out = _run(capsys, cat, "grep", "dated", "dated_", "--release", "1.5.0")
    assert code == 0, out
    assert _hit("dated", d1, "d.c", "int dated_tag;") in out


# --------------------------------------------------------------- AC-2


@needs_git
def test_ac2_a_recipe_of_that_name_without_a_usable_version(
    tmp_path, remotes, library, capsys
):
    """AC-2's shape for the failure path the documentation names beside the
    three: at 7.0.0 the only recipe named like the entry is ``gizmo_git.bb``,
    a tarball recipe with no SRCREV, so no version forms a tag. Exit 2, the
    repository and the recipe in the message, no tree."""
    cat = _catalog(tmp_path, remotes)
    code, out = _clone(capsys, cat, "gizmo", "7.0.0")
    assert code == 2, out
    message = _message(out)
    assert "gizmo" in message
    assert f"{UP}/gizmo/gizmo_git.bb" in message
    assert "pin:" not in out
    assert _nothing_held(library, "gizmo")


@needs_git
def test_ac2_no_recipe_of_that_name_in_the_release(tmp_path, remotes, library, capsys):
    """AC-2: 'no recipe of that name in the release': exit 2, the message
    names the repository, no tree. ``gizmo-utils_2.0.bb`` is another
    component, not a recipe named like the entry."""
    cat = _catalog(tmp_path, remotes)
    code, out = _clone(capsys, cat, "gizmo", "5.0.0")
    assert code == 2, out
    message = _message(out)
    assert "gizmo" in message
    assert "gizmo-utils" not in message
    assert "pin:" not in out
    assert _nothing_held(library, "gizmo")


@needs_git
def test_ac2_recipes_at_different_versions_are_each_listed(
    tmp_path, remotes, library, capsys
):
    """AC-2: 'recipes of that name at different versions in different layers
    (each listed, as for SRCREV conflicts)': exit 2, both recipes in the
    output, no tree."""
    cat = _catalog(tmp_path, remotes)
    code, out = _clone(capsys, cat, "gizmo", "3.0.0")
    assert code == 2, out
    assert "gizmo" in _message(out)
    assert f"{UP}/gizmo/gizmo_1.1.bb" in out
    assert f"{ACME}/gizmo/gizmo_1.0.bb" in out
    assert "pin:" not in out
    assert _nothing_held(library, "gizmo")


@needs_git
def test_ac2_a_version_the_remote_has_no_tag_for(tmp_path, remotes, library, capsys):
    """AC-2: 'the remote has no such tag (the message names the tag and the
    version)': 4.0.0 builds gizmo 7.7 and the remote has no v7.7. Exit 2,
    the repository, the tag and the version in the message, no tree."""
    cat = _catalog(tmp_path, remotes)
    code, out = _clone(capsys, cat, "gizmo", "4.0.0")
    assert code == 2, out
    message = _message(out)
    assert "gizmo" in message
    assert "v7.7" in message
    assert _names_version(message, "7.7"), message
    assert "pin:" not in out
    assert _nothing_held(library, "gizmo")


@needs_git
def test_ac2_an_entry_without_release_tag_behaves_as_before(
    tmp_path, remotes, library, capsys
):
    """AC-2: 'An entry without ``release_tag`` behaves as before': the same
    release and recipe, the key left off, give no release commit (exit 2,
    the repository named, no tree). And the key changes nothing outside
    ``--release``: a plain clone of the tagged entry is the default branch."""
    untagged = _catalog(tmp_path, remotes, tagged=False, name="untagged.toml")
    code, out = _clone(capsys, untagged, "gizmo", "1.0.0")
    assert code == 2, out
    assert "gizmo" in _message(out)
    assert "pin:" not in out
    assert _nothing_held(library, "gizmo")

    cat = _catalog(tmp_path, remotes)
    code, out = _run(capsys, cat, "clone", "gizmo")
    assert code == 0, out
    assert set(_trees(library, "gizmo")) == {remotes["tip"]}, out
    assert "pin:" not in out


# --------------------------------------------------------------- AC-3


def _cite_line(out):
    lines = [ln for ln in out.splitlines() if ln.startswith("cite:")]
    assert len(lines) == 1, out
    return lines[0]


@needs_git
def test_ac3_grep_and_code_read_the_tag_pinned_tree_by_release(
    tmp_path, remotes, library, capsys
):
    """AC-3: with trees held for 1.0.0 (v1.0), 2.0.0 (v1.1) and the default
    branch, ``grep`` and ``code`` with ``--release L`` read the tree that
    release's clone made and cite it as the release, a release that was not
    cloned is answered by no other tree, and the ``config.toml`` Release
    selects the tree with no flag."""
    cat = _catalog(tmp_path, remotes)
    c10, c11, tip = remotes["c10"], remotes["c11"], remotes["tip"]
    for extra in (["--release", "1.0.0"], ["--release", "2.0.0"], []):
        code, out = _run(capsys, cat, "clone", "gizmo", *extra)
        assert code == 0, out
    assert set(_trees(library, "gizmo")) == {c10, c11, tip}

    code, out = _run(capsys, cat, "grep", "gizmo", "gizmo_v", "--release", "1.0.0")
    assert code == 0, out
    assert _hit("gizmo", c10, "src/gizmo.c", "int gizmo_v10;") in out
    assert f"gizmo@{c11[:7]}" not in out
    assert f"gizmo@{tip[:7]}" not in out

    code, out = _run(capsys, cat, "code", "gizmo", "src/gizmo.c", "--release", "2.0.0")
    assert code == 0, out
    cite = _cite_line(out)
    assert f"gizmo {c11[:7]}" in cite
    assert "release 2.0.0" in cite
    assert "int gizmo_v11;" in out

    code, out = _run(capsys, cat, "grep", "gizmo", "gizmo_v", "--release", "1.5.0")
    assert code == 2, out
    assert "gizmo@" not in out

    config = library / "config.toml"
    config.write_text('[code]\nrelease = "1.0.0"\n', encoding="utf-8", newline="")
    code, out = _run(capsys, cat, "grep", "gizmo", "gizmo_v")
    assert code == 0, out
    assert _hit("gizmo", c10, "src/gizmo.c", "int gizmo_v10;") in out
    code, out = _run(capsys, cat, "code", "gizmo", "src/gizmo.c")
    assert code == 0, out
    cite = _cite_line(out)
    assert f"gizmo {c10[:7]}" in cite
    assert "release 1.0.0" in cite
    assert "int gizmo_v10;" in out


# --------------------------------------------------------------- AC-4


@pytest.mark.parametrize("repo_id", sorted(TOOLS))
def test_ac4_shipped_entry_has_the_projects_url_and_tag_form(repo_id):
    """AC-4: the four entries at their projects' URLs, with the tag form
    given, and no ``owner``."""
    repo = SHIPPED.get_repo(repo_id)
    assert repo is not None, f"the shipped catalog has no '{repo_id}' entry"
    url, template = TOOLS[repo_id]
    assert repo.id == repo_id
    assert repo.url.removesuffix(".git") == url.removesuffix(".git")
    assert repo.release_tag == template
    assert repo.owner == ""


@pytest.mark.parametrize(
    ("topic", "ids"),
    [
        ("i2c", {"i2c-tools"}),
        ("tpm", {"tpm2-tss", "tpm2-tools"}),
        ("ethtool", {"ethtool"}),
    ],
)
def test_ac4_repos_topic_lists_the_entries(library, capsys, topic, ids):
    """AC-4: '``--topic i2c`` lists i2c-tools, ``--topic tpm`` lists both
    tpm2 entries, ``--topic ethtool`` lists ethtool', asked of the shipped
    catalog through the CLI (the first tab-separated field is the id)."""
    code, out = _run(capsys, None, "repos", "--topic", topic)
    assert code == 0, out
    listed = {line.split("\t")[0] for line in out.splitlines() if "\t" in line}
    assert ids <= listed, out


SHIPS = [
    ("i2c-tools", "1.0.0", "v4.4", f"{POKY}/i2c-tools/i2c-tools_4.4.bb"),
    ("ethtool", "1.0.0", "v6.11", f"{POKY}/ethtool/ethtool_6.11.bb"),
    ("ethtool", "2.0.0", "v7.1", f"{UP}/ethtool/ethtool_7.1.bb"),
    ("tpm2-tss", "1.0.0", "4.1.3", f"{SEC}/tpm2-tss/tpm2-tss_4.1.3.bb"),
    ("tpm2-tools", "1.0.0", "5.7", f"{SEC}/tpm2-tools/tpm2-tools_5.7.bb"),
]


@needs_git
@pytest.mark.parametrize(
    ("repo_id", "release", "tag", "recipe"),
    SHIPS,
    ids=[f"{repo_id}-{tag}" for repo_id, _release, tag, _recipe in SHIPS],
)
def test_ac4_the_shipped_tag_form_names_the_projects_tag(
    tmp_path, remotes, library, capsys, repo_id, release, tag, recipe
):
    """AC-4 with AC-1: the shipped ``release_tag`` of each entry, applied to
    the recipe OpenBMC has (``i2c-tools_4.4.bb``, ``ethtool_6.11.bb`` and
    ``ethtool_7.1.bb``, ``tpm2-tss_4.1.3.bb``, ``tpm2-tools_5.7.bb``), gives
    the tag the project uses (v4.4, v6.11, v7.1, 4.1.3, 5.7): the tree is
    that tag's commit on a remote that has exactly those tag names."""
    cat = _catalog(tmp_path, remotes, tools=True)
    code, out = _clone(capsys, cat, repo_id, release)
    assert code == 0, out
    wanted = remotes["tags"][tag]
    assert set(_trees(library, repo_id)) == {wanted}, out
    pin = _pin_line(out)
    assert wanted[:7] in pin
    assert tag in pin
    assert recipe in pin


# --------------------------------------------------------------- AC-5


@needs_git
def test_ac5_a_recipe_fetching_an_earlier_url_pins_the_entry(
    tmp_path, remotes, library, capsys
):
    """AC-5: the recipe fetches ``git://github.com/old-org/former-name``.
    Without ``moved_from`` that is another repository (exit 2, no tree);
    with ``moved_from`` naming that URL the recipe pins the entry, and the
    pinned commit is fetched from the entry's ``url``."""
    without = _catalog(tmp_path, remotes, moved=False, name="unmoved.toml")
    code, out = _clone(capsys, without, "oldtool", "1.0.0")
    assert code == 2, out
    assert "oldtool" in _message(out)
    assert _nothing_held(library, "oldtool")

    cat = _catalog(tmp_path, remotes)
    code, out = _clone(capsys, cat, "oldtool", "1.0.0")
    assert code == 0, out
    pinned = remotes["pinned"]
    trees = _trees(library, "oldtool")
    assert set(trees) == {pinned}, out
    assert trees[pinned]["url"] == remotes["oldtool"]
    held = library / "code" / "oldtool" / pinned / "tool.c"
    assert held.read_text(encoding="utf-8") == "int oldtool_pinned;\n"
    pin = _pin_line(out)
    assert pinned[:7] in pin
    assert f"{OE}/oldtool/oldtool_1.8.bb" in pin


def test_ac5_shipped_ipmitool_lists_its_github_home():
    """AC-5: '``ipmitool`` lists ``https://github.com/ipmitool/ipmitool.git``'
    while its ``url`` stays the Codeberg repository."""
    repo = SHIPPED.get_repo("ipmitool")
    assert repo is not None
    assert "https://github.com/ipmitool/ipmitool.git" in repo.moved_from
    assert repo.url.removesuffix(".git") == "https://codeberg.org/IPMITool/ipmitool"


# --------------------------------------------------------------- AC-6


def _load(tmp_path, repo_id="gadget", **keys):
    """The entry as the catalog file gives it (CatalogError when refused)."""
    text = MINI_CATALOG + "\n" + _entry(repo_id, "https://example.org/g.git", **keys)
    path = tmp_path / "one.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return catalog_mod.load_catalog(path).get_repo(repo_id)


@pytest.mark.parametrize("template", ["v{version}", "{version}", "release-{version}"])
def test_ac6_release_tag_with_the_version_placeholder_is_taken(tmp_path, template):
    """AC-6: a template holding ``{version}`` and nothing else in braces."""
    assert _load(tmp_path, release_tag=template).release_tag == template


@pytest.mark.parametrize("template", ["v1.0", "{ver}", "v{tag}", "v{version}-{n}"])
def test_ac6_release_tag_without_it_or_with_other_braces_is_refused(
    tmp_path, template
):
    """AC-6: '``release_tag`` must contain ``{version}`` and nothing else in
    braces'. The same entry with a valid template loads."""
    assert _load(tmp_path, release_tag="v{version}").release_tag == "v{version}"
    with pytest.raises(catalog_mod.CatalogError):
        _load(tmp_path, release_tag=template)


@pytest.mark.parametrize(
    "old", ["https://github.com/acme/old-gadget.git", "file:///srv/git/old-gadget.git"]
)
def test_ac6_moved_from_takes_what_url_takes(tmp_path, old):
    """AC-6: '``moved_from`` URLs follow the ``url`` rules' (https:// or
    file://)."""
    assert list(_load(tmp_path, moved_from=[old]).moved_from) == [old]


@pytest.mark.parametrize(
    "old",
    [
        "git://github.com/acme/old-gadget.git",
        "http://github.com/acme/old-gadget.git",
        "ssh://git@github.com/acme/old-gadget.git",
        "github.com/acme/old-gadget",
    ],
)
def test_ac6_moved_from_refuses_what_url_refuses(tmp_path, old):
    """AC-6: the ``url`` rules refuse these, so ``moved_from`` does. The
    same entry with an https URL loads."""
    good = "https://github.com/acme/old-gadget.git"
    assert list(_load(tmp_path, moved_from=[good]).moved_from) == [good]
    with pytest.raises(catalog_mod.CatalogError):
        _load(tmp_path, moved_from=[old])


@pytest.mark.parametrize(
    "keys",
    [
        {"release_tag": "v{version}"},
        {"moved_from": ["https://github.com/acme/old-gadget.git"]},
    ],
    ids=["release_tag", "moved_from"],
)
def test_ac6_neither_key_goes_on_a_vendor_tree(tmp_path, keys):
    """AC-6: 'both are refused on an entry with ``owner``'. The vendor entry
    alone loads, and the key alone (no owner) loads."""
    assert _load(tmp_path, "acme-gadget", owner="acme").owner == "acme"
    assert _load(tmp_path, **keys) is not None
    with pytest.raises(catalog_mod.CatalogError):
        _load(tmp_path, "acme-gadget", owner="acme", **keys)

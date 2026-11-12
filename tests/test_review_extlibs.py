"""Independent acceptance tests for the libraries OpenBMC recipes fetch from
other projects, held as Code Trees (T76.2: AC-1, AC-2, AC-3).

AC-1 reads the shipped catalog and asks ``bmcspec repos --topic`` for it.
AC-2 is about how a recipe names a hosted repository, so it is checked on
``find_pin_recipe`` with the shipped entry's URL and hand-written recipe
files in the form meta-openembedded uses (a hosted URL cannot be cloned in
the sandbox). AC-3 goes through the ``bmcspec`` CLI against local bare git
repositories, with the shipped entry's keys (topics, sparse, owner, ref)
and only its URL swapped for the local remote. No network.
"""

import json
import shutil

import pytest

from bmc_toolkit.spec import catalog as catalog_mod
from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import commit, git, make_repo, make_scenario, push

SHIPPED = catalog_mod.load_catalog()

# AC-1: the projects' own https URLs
URLS = {
    "libspdm": "https://github.com/DMTF/libspdm",
    "spdm-emu": "https://github.com/DMTF/spdm-emu",
    "mctp": "https://github.com/CodeConstruct/mctp",
    "nvme-cli": "https://github.com/linux-nvme/nvme-cli",
    "libnvme": "https://github.com/linux-nvme/libnvme",
    "ipmitool": "https://codeberg.org/IPMITool/ipmitool",
}
IDS = sorted(URLS)

# host/path as a meta-openembedded SRC_URI spells it (ipmitool in lowercase)
FETCHED = {
    "libspdm": "github.com/DMTF/libspdm",
    "spdm-emu": "github.com/DMTF/spdm-emu",
    "mctp": "github.com/CodeConstruct/mctp",
    "nvme-cli": "github.com/linux-nvme/nvme-cli",
    "libnvme": "github.com/linux-nvme/libnvme",
    "ipmitool": "codeberg.org/ipmitool/ipmitool",
}

# master keeps the layer under upstream-layers/, 2.18.0 at the top level
TOPS = ["upstream-layers/meta-openembedded", "meta-openembedded"]
MCTP_DIR = "meta-networking/recipes-support/mctp"

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _shipped(repo_id):
    repo = SHIPPED.get_repo(repo_id)
    assert repo is not None, f"the shipped catalog has no '{repo_id}' entry"
    return repo


def _rev(n):
    return f"{n:040x}"


def _write(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")


def _recipe(location, rev, scheme="git"):
    lines = [
        'SUMMARY = "a library"',
        f'SRC_URI = "{scheme}://{location};branch=main;protocol=https \\',
        "           file://0001-fix.patch \\",
        '           "',
        f'SRCREV = "{rev}"',
        "",
    ]
    return "\n".join(lines)


def _recipe_path(top, repo_id):
    return f"{top}/meta-oe/recipes-support/{repo_id}/{repo_id}_1.0.bb"


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


def _run(capsys, catalog_file, *argv):
    args = ["--catalog", str(catalog_file)] if catalog_file else []
    code = main([*args, *argv])
    return code, capsys.readouterr().out


# --------------------------------------------------------------- AC-1


@pytest.mark.parametrize("repo_id", IDS)
def test_ac1_shipped_entry_has_the_projects_url_and_no_owner_or_ref(repo_id):
    """AC-1: 'six new [[repos]] entries ... with the projects' own https
    URLs ..., no owner, no ref'."""
    repo = _shipped(repo_id)
    assert repo.id == repo_id
    assert repo.url.removesuffix(".git") == URLS[repo_id]
    assert repo.owner == ""
    assert repo.ref == ""


def test_ac1_six_entries_are_added_to_the_108():
    """AC-1: 'The other 108 entries do not change': the six are additions,
    none replaces or removes an entry."""
    assert len(SHIPPED.repos) == 114
    assert len([r for r in SHIPPED.repos if r.id not in URLS]) == 108
    assert len({r.id.lower() for r in SHIPPED.repos}) == 114


@pytest.mark.parametrize(
    ("topic", "ids"),
    [
        ("spdm", {"libspdm", "spdm-emu"}),
        ("mctp", {"mctp"}),
        ("nvme", {"nvme-cli", "libnvme"}),
        ("ipmi", {"ipmitool"}),
    ],
)
def test_ac1_repos_topic_lists_the_libraries(library, capsys, topic, ids):
    """AC-1: '`repos --topic spdm` lists libspdm and spdm-emu, `--topic
    mctp` lists mctp, `--topic nvme` lists nvme-cli and libnvme, `--topic
    ipmi` lists ipmitool', asked of the shipped catalog through the CLI
    (the first tab-separated field of a line is the repository id)."""
    code, out = _run(capsys, None, "repos", "--topic", topic)
    assert code == 0, out
    listed = {line.split("\t")[0] for line in out.splitlines() if "\t" in line}
    assert ids <= listed, out


# --------------------------------------------------------------- AC-2


@pytest.mark.parametrize("top", TOPS)
@pytest.mark.parametrize("suffix", ["", ".git"])
@pytest.mark.parametrize("repo_id", IDS)
def test_ac2_a_meta_openembedded_recipe_pins_the_entry(tmp_path, repo_id, suffix, top):
    """AC-2: 'a recipe written the way meta-openembedded writes it (SRC_URI
    git://<host>/<path>;... or git://<host>/<path>.git;..., a fixed SRCREV)
    resolves that entry to that SRCREV with no network', with the layer
    under upstream-layers/ (master) and at the top level (2.18.0)."""
    url = _shipped(repo_id).url
    rel = _recipe_path(top, repo_id)
    _write(tmp_path, {rel: _recipe(FETCHED[repo_id] + suffix, _rev(1))})
    assert code_mod.find_pin_recipe(tmp_path, repo_id, url) == (_rev(1), rel)


def test_ac2_spdm_emu_fetched_with_its_submodules_is_pinned(tmp_path):
    """AC-2: spdm-emu's recipe fetches with gitsm:// (the repository has a
    libspdm submodule); the scheme does not change which repository it is."""
    url = _shipped("spdm-emu").url
    rel = f"{TOPS[0]}/meta-oe/recipes-security/spdm-emu/spdm-emu_git.bb"
    text = _recipe(FETCHED["spdm-emu"], _rev(5), scheme="gitsm")
    _write(tmp_path, {rel: text})
    assert code_mod.find_pin_recipe(tmp_path, "spdm-emu", url) == (_rev(5), rel)


def _decoys(repo_id):
    """Recipes whose SRC_URI ends in the same name: another organisation
    on the project's host, and the project's path on another host."""
    host, path = FETCHED[repo_id].split("/", 1)
    name = path.rsplit("/", 1)[-1]
    base = f"meta-acme/recipes-x/{name}/{name}"
    other_org = _recipe(f"{host}/acme/{name}", _rev(77))
    other_host = _recipe(f"git.example.org/{path}.git", _rev(78))
    return {f"{base}-org_git.bb": other_org, f"{base}-host_git.bb": other_host}


@pytest.mark.parametrize("repo_id", IDS)
def test_ac2_another_host_or_organisation_is_not_a_pin(tmp_path, repo_id):
    """AC-2: 'a recipe of another host or organisation with the same last
    path segment does not [resolve the entry]'. Alone, such recipes leave
    the entry without a pin (a CodeError that names neither of them);
    beside the project's own recipe they are not a second, conflicting
    pin."""
    url = _shipped(repo_id).url
    _write(tmp_path, _decoys(repo_id))
    with pytest.raises(code_mod.CodeError) as excinfo:
        code_mod.find_pin_recipe(tmp_path, repo_id, url)
    assert "meta-acme" not in str(excinfo.value)
    rel = _recipe_path(TOPS[0], repo_id)
    _write(tmp_path, {rel: _recipe(FETCHED[repo_id], _rev(1))})
    assert code_mod.find_pin_recipe(tmp_path, repo_id, url) == (_rev(1), rel)


@pytest.mark.parametrize("top", TOPS)
def test_ac2_mctp_and_mctpd_sharing_one_inc_are_one_pin(tmp_path, top):
    """AC-2: 'The mctp and mctpd recipes pinning the one repository at one
    commit give one pin, not a conflict': both .bb files require one
    mctp.inc that holds SRC_URI and SRCREV."""
    url = _shipped("mctp").url
    base = f"{top}/{MCTP_DIR}"
    files = {
        f"{base}/mctp.inc": _recipe(FETCHED["mctp"], _rev(9)),
        f"{base}/mctp_2.6.bb": 'require mctp.inc\nMESON_TARGET = "mctp"\n',
        f"{base}/mctpd_2.6.bb": "require mctp.inc\ninherit systemd\n",
    }
    _write(tmp_path, files)
    rev, recipe = code_mod.find_pin_recipe(tmp_path, "mctp", url)
    assert rev == _rev(9)
    assert recipe.startswith(f"{base}/")


def test_ac2_mctp_and_mctpd_naming_it_separately_are_one_pin(tmp_path):
    """AC-2, the same sentence with each recipe carrying its own SRC_URI
    and the same SRCREV."""
    url = _shipped("mctp").url
    base = f"{TOPS[0]}/{MCTP_DIR}"
    text = _recipe(FETCHED["mctp"], _rev(9))
    _write(tmp_path, {f"{base}/mctp_2.6.bb": text, f"{base}/mctpd_2.6.bb": text})
    rev, recipe = code_mod.find_pin_recipe(tmp_path, "mctp", url)
    assert rev == _rev(9)
    assert recipe.startswith(f"{base}/")


# --------------------------------------------------------------- AC-3

# the default branch each project uses; the clone must take the remote's
BRANCH = {
    "libspdm": "main",
    "spdm-emu": "main",
    "mctp": "main",
    "nvme-cli": "master",
    "libnvme": "master",
    "ipmitool": "master",
}
FILES = {
    "include/api.h": "int api(void);\n",
    "library/core.c": "int core;\n",
    "unit_test/vectors.txt": "vectors\n",
    "README.md": "a library\n",
}
NEWER = {
    "include/api.h": "int api_next(void);\n",
    "library/core.c": "int core_next;\n",
}


def _remotes(tmp_path, repo_id):
    """A local remote of the library with two commits (a Release pins the
    first, the default branch is at the second) and an openbmc remote whose
    tag 1.0.0 holds the library's recipe under upstream-layers/."""

    def build(root):
        branch = BRANCH[repo_id]
        work, _bare, url = make_repo(root, repo_id, FILES, branch=branch)
        pinned = git("rev-parse", "HEAD", cwd=work)
        tip = commit(work, NEWER, "newer")
        push(work, branch)
        files = {
            _recipe_path(TOPS[0], repo_id): _recipe(FETCHED[repo_id], pinned),
            "README.md": "distro\n",
        }
        ob_work, _ob_bare, ob_url = make_repo(root, "openbmc", files, branch="master")
        git("tag", "1.0.0", cwd=ob_work)
        push(ob_work, "1.0.0")
        return {"lib": url, "ob": ob_url, "pinned": pinned, "tip": tip}

    return make_scenario(tmp_path, f"review-extlibs-{repo_id}", build)


def _catalog_file(tmp_path, repo_id, remotes):
    """The shipped entry (topics, sparse, owner, ref) with its URL swapped
    for the local remote, beside an openbmc entry with the shipped paths."""
    shipped = _shipped(repo_id)
    ob_url, lib_url = remotes["ob"], remotes["lib"]
    ob_sparse = json.dumps(list(_shipped("openbmc").sparse))
    lines = [
        MINI_CATALOG,
        "[[repos]]",
        'id = "openbmc"',
        f'url = "{ob_url}"',
        'topics = ["release"]',
        f"sparse = {ob_sparse}",
        "",
        "[[repos]]",
        f'id = "{shipped.id}"',
        f'url = "{lib_url}"',
        f"topics = {json.dumps(list(shipped.topics))}",
    ]
    if shipped.sparse:
        lines.append(f"sparse = {json.dumps(list(shipped.sparse))}")
    if shipped.owner:
        lines.append(f'owner = "{shipped.owner}"')
    if shipped.ref:
        lines.append(f'ref = "{shipped.ref}"')
    path = tmp_path / "catalog.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    return path


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


def _check_paths(tree, sparse, files):
    """The tree holds the directories the shipped entry lists (all of them
    when it lists none) at the expected content, and no other directory."""
    for rel, text in files.items():
        if "/" not in rel:
            continue  # files at the root come with any directory list
        path = tree / rel
        if not sparse or rel.split("/", 1)[0] in sparse:
            assert path.read_text(encoding="utf-8") == text, rel
        else:
            assert not path.exists(), rel


@needs_git
@pytest.mark.parametrize("repo_id", IDS)
def test_ac3_release_pins_it_and_a_plain_clone_takes_the_default_branch(
    tmp_path, library, capsys, repo_id
):
    """AC-3: '`clone <id> --release L` is accepted' (exit 0, not the vendor
    refusal '<id> has no Release'; the tree is the recipe's SRCREV, the
    repository's first commit, recorded as reached by the release) and 'a
    plain `clone <id>` takes the remote's default branch' (the newer
    commit, recorded under the branch name the remote uses, main or
    master). The checkout follows the shipped entry's paths: libspdm is
    documented as held without unit_test/."""
    sparse = _shipped(repo_id).sparse
    remotes = _remotes(tmp_path, repo_id)
    cat = _catalog_file(tmp_path, repo_id, remotes)
    pinned, tip = remotes["pinned"], remotes["tip"]
    assert pinned != tip

    code, out = _run(capsys, cat, "clone", repo_id, "--release", "1.0.0")
    assert code == 0, out
    assert "has no Release" not in out
    trees = _trees(library, repo_id)
    assert list(trees) == [pinned], out
    assert trees[pinned]["provenance"]["kind"] == "release"
    assert trees[pinned]["provenance"]["name"] == "1.0.0"
    _check_paths(library / "code" / repo_id / pinned, sparse, FILES)

    code, out = _run(capsys, cat, "clone", repo_id)
    assert code == 0, out
    assert "has no Release" not in out
    trees = _trees(library, repo_id)
    assert set(trees) == {pinned, tip}, out
    assert trees[tip]["provenance"] == {"kind": "default", "name": BRANCH[repo_id]}
    _check_paths(library / "code" / repo_id / tip, sparse, {**FILES, **NEWER})


@needs_git
@pytest.mark.parametrize("repo_id", IDS)
def test_ac3_the_config_release_applies_to_it(tmp_path, library, capsys, repo_id):
    """AC-3: 'a config.toml release applies to them (the "has no Release"
    vendor note is not printed)': with release = "1.0.0" configured, a
    plain `clone <id>` announces the release and holds the pinned commit,
    not the default branch's."""
    _shipped(repo_id)
    remotes = _remotes(tmp_path, repo_id)
    cat = _catalog_file(tmp_path, repo_id, remotes)
    library.mkdir(parents=True, exist_ok=True)
    config = library / "config.toml"
    config.write_text('[code]\nrelease = "1.0.0"\n', encoding="utf-8", newline="")

    code, out = _run(capsys, cat, "clone", repo_id)
    assert code == 0, out
    assert "has no Release" not in out
    assert "release: 1.0.0 (from config.toml)" in out
    trees = _trees(library, repo_id)
    assert list(trees) == [remotes["pinned"]], out
    assert trees[remotes["pinned"]]["provenance"]["kind"] == "release"

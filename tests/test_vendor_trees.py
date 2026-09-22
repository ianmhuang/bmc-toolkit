"""Vendor Code Trees: the catalog's ``owner`` field, the vendor entries the
shipped catalog lists, and how clone, grep and code treat a vendor tree
(no Release, no guessing). Local bare repositories stand in for the vendor
remotes; skipped when git is not on PATH."""

import shutil

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.catalog import (
    DEFAULT_CATALOG,
    CatalogError,
    load_catalog,
    parse_catalog,
)
from tests.conftest import MINI_CATALOG
from tests.test_code import THING_FILES, git, make_repo

# library and remotes are pytest fixtures; a test naming them as parameters
# is not a redefinition
# ruff: noqa: F811
from tests.test_code_cli import library, remotes, run  # noqa: F401

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _catalog(repos):
    return {
        "schema_version": 1,
        "families": {"x": {"title": "X", "publisher": "P"}},
        "documents": [],
        "repos": repos,
    }


def _repo(repo_id, **extra):
    return {
        "id": repo_id,
        "url": f"https://github.com/acme/{repo_id}.git",
        "topics": ["kernel"],
        **extra,
    }


# ------------------------------------------------------------ owner field


def test_owner_is_optional_and_carried_on_the_repo():
    catalog = parse_catalog(
        _catalog([_repo("bmcweb"), _repo("acme-linux", owner="acme")])
    )
    assert catalog.get_repo("bmcweb").owner == ""
    assert catalog.get_repo("acme-linux").owner == "acme"
    assert catalog.owners == {"acme"}


@pytest.mark.parametrize("repo_id", ["linux", "acmelinux", "other-linux", "acme-"])
def test_an_owned_id_must_carry_the_owner_prefix(repo_id):
    with pytest.raises(CatalogError, match=r"repos\[0\]\.id"):
        parse_catalog(_catalog([_repo(repo_id, owner="acme")]))


@pytest.mark.parametrize("owner", ["", "  ", 3, "Acme", "ac me"])
def test_owner_must_be_a_lowercase_name(owner):
    with pytest.raises(CatalogError, match=r"repos\[0\]\.owner"):
        parse_catalog(_catalog([_repo("acme-linux", owner=owner)]))


# ------------------------------------------------------------ shipped catalog

VENDOR_TREES = {
    "aspeed-linux": "https://github.com/AspeedTech-BMC/linux.git",
    "aspeed-u-boot": "https://github.com/AspeedTech-BMC/u-boot.git",
    "aspeed-openbmc": "https://github.com/AspeedTech-BMC/openbmc.git",
    "aspeed-socsec": "https://github.com/AspeedTech-BMC/socsec.git",
    "nuvoton-linux": "https://github.com/Nuvoton-Israel/linux.git",
    "nuvoton-u-boot": "https://github.com/Nuvoton-Israel/u-boot.git",
    "nuvoton-openbmc": "https://github.com/Nuvoton-Israel/openbmc.git",
    "nuvoton-bootblock": "https://github.com/Nuvoton-Israel/bootblock.git",
    "nuvoton-npcm8xx-bootblock": "https://github.com/Nuvoton-Israel/npcm8xx-bootblock.git",
    "nuvoton-igps": "https://github.com/Nuvoton-Israel/igps-npcm8xx.git",
}

KERNEL_DIRS = {
    "aspeed": [
        "arch/arm/boot/dts/aspeed",
        "arch/arm64/boot/dts/aspeed",
        "arch/arm/mach-aspeed",
        "drivers/soc/aspeed",
        "drivers/jtag",
        "drivers/peci",
    ],
    "nuvoton": [
        "arch/arm/boot/dts/nuvoton",
        "arch/arm64/boot/dts/nuvoton",
        "arch/arm/mach-npcm",
        "drivers/soc/nuvoton",
    ],
}


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def test_shipped_catalog_lists_the_ten_vendor_trees(shipped):
    vendor = {r.id: r for r in shipped.repos if r.owner}
    assert {i: r.url for i, r in vendor.items()} == VENDOR_TREES
    for repo in vendor.values():
        assert repo.owner == repo.id.split("-", 1)[0]
        assert repo.owner in repo.topics
    assert shipped.owners == {"aspeed", "nuvoton"}
    for repo in shipped.repos:
        if not repo.owner:
            assert repo.url.startswith("https://github.com/openbmc/"), repo.id


def test_vendor_kernels_add_only_their_own_directories(shipped):
    upstream = list(shipped.get_repo("linux").sparse)
    for owner, other in (("aspeed", "nuvoton"), ("nuvoton", "aspeed")):
        sparse = list(shipped.get_repo(f"{owner}-linux").sparse)
        assert sparse == upstream + [d for d in KERNEL_DIRS[owner] if d not in upstream]
        assert not set(KERNEL_DIRS[other]) - set(upstream) & set(sparse)


def test_vendor_openbmc_layers_are_sparse(shipped):
    assert shipped.get_repo("aspeed-openbmc").sparse == ("/meta-aspeed*/", "/meta-evb/")
    assert shipped.get_repo("nuvoton-openbmc").sparse == (
        "/meta-nuvoton*/",
        "/meta-evb/",
    )
    for repo_id in VENDOR_TREES:
        if "linux" not in repo_id and "openbmc" not in repo_id:
            assert shipped.get_repo(repo_id).sparse == ()


def test_soc_topics_find_the_vendor_trees(shipped):
    def ids(topic):
        return {r.id for r in shipped.by_topic(topic)}

    assert {"aspeed-linux", "aspeed-u-boot", "aspeed-socsec"} <= ids("ast2600")
    assert "aspeed-linux" in ids("ast2700")
    assert {"nuvoton-linux", "nuvoton-bootblock"} <= ids("npcm7xx")
    assert {"nuvoton-linux", "nuvoton-npcm8xx-bootblock", "nuvoton-igps"} <= ids(
        "npcm8xx"
    )
    assert not {i for i in ids("ast2600") if i.startswith("nuvoton-")}
    assert not {i for i in ids("npcm8xx") if i.startswith("aspeed-")}


def test_repos_comment_no_longer_says_upstream_only():
    text = DEFAULT_CATALOG.read_text("utf-8")
    assert "Upstream OpenBMC only" not in text


# ------------------------------------------------------------ CLI


@pytest.fixture
def vendor(tmp_path):
    (tmp_path / "vendor").mkdir()
    return make_repo(tmp_path / "vendor", "acme-thing", THING_FILES)


@pytest.fixture
def catalog_file(tmp_path, remotes, vendor):
    text = (
        MINI_CATALOG
        + f"""
[[repos]]
id = "openbmc"
url = "{remotes["openbmc"][1]}"
topics = ["release", "recipes"]
sparse = ["meta-phosphor"]

[[repos]]
id = "thing"
url = "{remotes["thing"][1]}"
topics = ["power", "state"]

[[repos]]
id = "acme-thing"
owner = "acme"
url = "{vendor[2]}"
topics = ["acme", "power"]
"""
    )
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def _config_release(library):
    library.mkdir(exist_ok=True)
    (library / "config.toml").write_text(
        '[code]\nrelease = "1.0.0"\n', encoding="utf-8"
    )


def test_vendor_tree_clones_at_default_and_ref(
    library,
    catalog_file,
    vendor,
    capsys,
):
    head = git("rev-parse", "HEAD", cwd=vendor[0])
    code, out = run(capsys, "clone", "acme-thing", catalog_file=catalog_file)
    assert code == 0, out
    assert out.startswith(f"cloned acme-thing {head[:7]} (main ")
    argv = ["clone", "acme-thing", "--ref", "main", "--force"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0 and f"acme-thing {head[:7]} (main " in out
    code, out = run(
        capsys, "grep", "acme-thing", "powerState", catalog_file=catalog_file
    )
    assert code == 0 and out.splitlines()[0].startswith(f"acme-thing@{head[:7]} ")
    code, out = run(capsys, "repos", "--topic", "acme", catalog_file=catalog_file)
    assert code == 0 and out.startswith("acme-thing\t")


@pytest.mark.parametrize(
    "argv",
    [
        ["clone", "acme-thing", "--release", "1.0.0"],
        ["grep", "acme-thing", "x", "--release", "1.0.0"],
        ["code", "acme-thing", "README.md", "--release", "1.0.0"],
    ],
)
def test_release_on_a_vendor_tree_is_refused(
    library,
    catalog_file,
    capsys,
    monkeypatch,
    argv,
):
    def no_git(*a, **k):
        raise AssertionError("git must not run")

    monkeypatch.setattr(code_mod, "run_git", no_git)
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 2
    assert (
        out.strip() == "acme-thing has no Release; use --ref with an SDK branch or tag"
    )
    assert not (library / "code" / "acme-thing").exists()


def test_config_release_is_not_used_for_a_vendor_tree(
    library,
    catalog_file,
    remotes,
    vendor,
    capsys,
):
    _config_release(library)
    note = "note: acme-thing has no Release; config.toml release 1.0.0 not used"
    code, out = run(capsys, "clone", "acme-thing", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0] == note
    assert out.splitlines()[1].startswith("cloned acme-thing ")
    assert "(main " in out
    code, out = run(
        capsys, "grep", "acme-thing", "powerState", catalog_file=catalog_file
    )
    assert code == 0 and out.splitlines()[0] == note
    assert out.splitlines()[1].startswith("acme-thing@")
    argv = ["code", "acme-thing", "README.md"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0 and out.splitlines()[0] == note
    # an upstream tree still follows the configured Release
    code, out = run(capsys, "clone", "thing", catalog_file=catalog_file)
    assert code == 0 and out.splitlines()[0] == "release: 1.0.0 (from config.toml)"
    first = remotes["thing"][2]
    assert f"cloned thing {first[:7]} (release 1.0.0)" in out


def test_unlisted_vendor_id_is_not_guessed(
    library,
    catalog_file,
    capsys,
    monkeypatch,
    tmp_path,
):
    (tmp_path / "guess").mkdir()
    make_repo(tmp_path / "guess", "acme-zephyr", {"a.txt": "hello\n"})
    make_repo(tmp_path / "guess", "extra", {"a.txt": "hello\n"})
    monkeypatch.setattr(code_mod, "GUESS_BASE", (tmp_path / "guess").as_uri() + "/")
    code, out = run(capsys, "clone", "acme-zephyr", catalog_file=catalog_file)
    assert code == 2
    assert out.strip() == (
        "acme-zephyr is not in the catalog; vendor repositories are cloned "
        "only from catalog entries (bmcspec repos lists them)"
    )
    assert not (library / "code" / "acme-zephyr").exists()
    code, out = run(capsys, "clone", "ACME-Zephyr", catalog_file=catalog_file)
    assert code == 2 and "vendor repositories" in out
    # an id whose prefix is no owner is still guessed under openbmc
    code, out = run(capsys, "clone", "extra", catalog_file=catalog_file)
    assert code == 0 and out.splitlines()[1].startswith("cloned extra ")

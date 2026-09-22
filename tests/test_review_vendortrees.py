"""Acceptance tests for the vendor Code Trees change: the catalog's ``owner``
and ``ref`` keys (AC-1, AC-11), the shipped vendor entries (AC-2), and how
clone, grep and code treat a vendor tree: no guessing of a vendor-prefixed
id (AC-3), no ``--release`` (AC-4), the config Release skipped with a note
(AC-5), plain and ``--ref`` clones as on an upstream tree (AC-6), and a
catalog ``ref`` standing in for the remote's default branch (AC-11).
Local bare repositories stand in for the remotes; skipped when git is not
on PATH."""

import shutil

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.catalog import CatalogError, load_catalog, parse_catalog
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import RECIPE, THING_FILES, commit, git, make_repo, push

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

VENDOR_FILES = {
    "drivers/soc/acme/espi.c": '/* acme eSPI */\n.compatible = "acme,ast-espi",\n',
    "README.md": "acme sdk\n",
}


# ------------------------------------------------------------ catalog keys


def _catalog(*repos):
    return {
        "schema_version": 1,
        "families": {"x": {"title": "X", "publisher": "P"}},
        "documents": [],
        "repos": list(repos),
    }


def _entry(repo_id, **extra):
    return {
        "id": repo_id,
        "url": f"https://example.test/{repo_id}.git",
        "topics": ["t"],
        **extra,
    }


def test_ac1_owner_absent_means_upstream_and_present_is_carried():
    catalog = parse_catalog(
        _catalog(_entry("bmcweb"), _entry("acme-linux", owner="acme"))
    )
    assert catalog.get_repo("bmcweb").owner == ""
    assert catalog.get_repo("acme-linux").owner == "acme"


@pytest.mark.parametrize("repo_id", ["linux", "acme", "acme-", "acmelinux", "x-acme"])
def test_ac1_owned_id_must_start_with_the_owner_and_a_dash(repo_id):
    with pytest.raises(CatalogError, match=r"repos\[1\]\.id"):
        parse_catalog(_catalog(_entry("bmcweb"), _entry(repo_id, owner="acme")))


@pytest.mark.parametrize("owner", ["", 7, ["acme"], "Acme", "ac me"])
def test_ac1_owner_must_be_a_non_empty_lowercase_string(owner):
    with pytest.raises(CatalogError, match=r"repos\[0\]\.owner"):
        parse_catalog(_catalog(_entry("acme-linux", owner=owner)))


def test_ac11_ref_is_optional_and_must_be_a_non_empty_string():
    catalog = parse_catalog(_catalog(_entry("acme-linux", owner="acme", ref="sdk")))
    assert catalog.get_repo("acme-linux").ref == "sdk"
    assert parse_catalog(_catalog(_entry("bmcweb"))).get_repo("bmcweb").ref == ""
    for bad in ("", "   ", 4):
        with pytest.raises(CatalogError, match=r"repos\[0\]\.ref"):
            parse_catalog(_catalog(_entry("acme-linux", owner="acme", ref=bad)))


# ------------------------------------------------------------ shipped catalog

VENDOR_URLS = {
    "aspeed-linux": "https://github.com/AspeedTech-BMC/linux.git",
    "aspeed-u-boot": "https://github.com/AspeedTech-BMC/u-boot.git",
    "aspeed-openbmc": "https://github.com/AspeedTech-BMC/openbmc.git",
    "aspeed-socsec": "https://github.com/AspeedTech-BMC/socsec.git",
    "nuvoton-linux": "https://github.com/Nuvoton-Israel/linux.git",
    "nuvoton-u-boot": "https://github.com/Nuvoton-Israel/u-boot.git",
    "nuvoton-openbmc": "https://github.com/Nuvoton-Israel/openbmc.git",
    "nuvoton-bootblock": "https://github.com/Nuvoton-Israel/bootblock.git",
    "nuvoton-npcm8xx-bootblock": (
        "https://github.com/Nuvoton-Israel/npcm8xx-bootblock.git"
    ),
    "nuvoton-igps": "https://github.com/Nuvoton-Israel/igps-npcm8xx.git",
}


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def test_ac2_shipped_catalog_lists_the_ten_vendor_trees(shipped):
    owned = {r.id: r for r in shipped.repos if r.owner}
    assert {i: r.url for i, r in owned.items()} == VENDOR_URLS
    for repo in owned.values():
        assert repo.owner == repo.id.split("-", 1)[0]
        assert repo.owner in (t.lower() for t in repo.topics)
        assert repo.url.startswith("https://")
    # the upstream entries are untouched: no owner, no ref, openbmc URLs
    for repo in shipped.repos:
        if not repo.owner:
            assert repo.ref == "", repo.id
            assert repo.url.startswith("https://github.com/openbmc/"), repo.id


def test_ac2_kernel_sparse_lists_extend_upstream_with_own_directories(shipped):
    upstream = shipped.get_repo("linux").sparse
    foreign = {"aspeed": ("nuvoton", "npcm"), "nuvoton": ("aspeed", "ast2")}
    for owner in ("aspeed", "nuvoton"):
        sparse = shipped.get_repo(f"{owner}-linux").sparse
        assert sparse[: len(upstream)] == upstream
        extra = sparse[len(upstream) :]
        assert extra, owner
        for path in extra:
            assert path not in upstream, path
            for marker in foreign[owner]:
                assert marker not in path, path
        # its own dts and soc directories are there
        assert any(p.startswith("arch/arm/boot/dts/") for p in extra), owner
        assert any(p.startswith("drivers/soc/") for p in extra), owner
        # beyond arch, dts and soc, only Aspeed adds a driver directory, jtag
        others = [p for p in extra if not p.startswith(("arch/", "drivers/soc/"))]
        assert others == (["drivers/jtag"] if owner == "aspeed" else []), owner


def test_ac2_soc_topics_route_to_the_right_vendor(shipped):
    def ids(topic):
        return {r.id for r in shipped.by_topic(topic)}

    assert "aspeed-linux" in ids("ast2600") and "aspeed-u-boot" in ids("ast2600")
    assert "aspeed-linux" in ids("ast2700")
    assert "nuvoton-linux" in ids("npcm7xx") and "nuvoton-linux" in ids("npcm8xx")
    assert all(i.startswith("aspeed-") for i in ids("ast2600"))
    assert all(i.startswith("aspeed-") for i in ids("ast2700"))
    assert all(i.startswith("nuvoton-") for i in ids("npcm7xx"))
    assert all(i.startswith("nuvoton-") for i in ids("npcm8xx"))
    assert {r.id for r in shipped.by_topic("aspeed")} == {
        i for i in VENDOR_URLS if i.startswith("aspeed-")
    }
    assert {r.id for r in shipped.by_topic("nuvoton")} == {
        i for i in VENDOR_URLS if i.startswith("nuvoton-")
    }


def test_ac11_shipped_nuvoton_kernel_names_its_branch(shipped):
    assert shipped.get_repo("nuvoton-linux").ref == "NPCM-6.18-OpenBMC"


# ------------------------------------------------------------ CLI fixtures


def run(capsys, catalog_file, *argv):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


@pytest.fixture
def upstream(tmp_path):
    """thing (a component, two commits) and openbmc (the release source,
    tag 1.0.0 pinning thing's first commit)."""
    (tmp_path / "up").mkdir()
    work, bare, url = make_repo(tmp_path / "up", "thing", THING_FILES)
    first = git("rev-parse", "HEAD", cwd=work)
    recipe = RECIPE.format(url=url.removeprefix("file://"), sha=first)
    ob_files = {
        "meta-phosphor/recipes-phosphor/things/thing_git.bb": recipe,
        "README.md": "distro\n",
    }
    ob_work, ob_bare, ob_url = make_repo(
        tmp_path / "up", "openbmc", ob_files, branch="master"
    )
    git("tag", "1.0.0", cwd=ob_work)
    push(ob_work, "1.0.0")
    second = commit(work, {"src/main.cpp": "int main() { return 2; }\n"}, "second")
    push(work)
    return {"thing": (work, url, first, second), "openbmc": ob_url}


@pytest.fixture
def vendor(tmp_path):
    """acme-linux: a vendor fork with main and an sdk-2 branch."""
    (tmp_path / "vend").mkdir()
    work, bare, url = make_repo(tmp_path / "vend", "acme-linux", VENDOR_FILES)
    main_head = git("rev-parse", "HEAD", cwd=work)
    git("checkout", "-q", "-b", "sdk-2", cwd=work)
    sdk_head = commit(work, {"drivers/soc/acme/sdk2.c": "int sdk2;\n"}, "sdk 2")
    push(work, "sdk-2")
    git("checkout", "-q", "main", cwd=work)
    return {"url": url, "main": main_head, "sdk-2": sdk_head}


def _write_catalog(path, upstream, vendor, *, ref=None):
    ref_line = f'ref = "{ref}"\n' if ref else ""
    text = (
        MINI_CATALOG
        + f"""
[[repos]]
id = "openbmc"
url = "{upstream["openbmc"]}"
topics = ["release", "recipes"]
sparse = ["meta-phosphor"]

[[repos]]
id = "thing"
url = "{upstream["thing"][1]}"
topics = ["power"]

[[repos]]
id = "acme-linux"
owner = "acme"
url = "{vendor["url"]}"
topics = ["acme", "kernel"]
{ref_line}"""
    )
    path.write_text(text, encoding="utf-8", newline="")
    return path


@pytest.fixture
def catalog_file(tmp_path, upstream, vendor):
    return _write_catalog(tmp_path / "catalog.toml", upstream, vendor)


def _set_config_release(library, release="1.0.0"):
    library.mkdir(parents=True, exist_ok=True)
    (library / "config.toml").write_text(
        f'[code]\nrelease = "{release}"\n', encoding="utf-8", newline=""
    )


@pytest.fixture
def no_git(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError(f"git must not run: {args}")

    monkeypatch.setattr(code_mod, "run_git", refuse)


# ------------------------------------------------------------ AC-6


def test_ac6_plain_clone_of_a_vendor_tree_names_the_branch(
    library, catalog_file, vendor, capsys
):
    head = vendor["main"][:7]
    code, out = run(capsys, catalog_file, "clone", "acme-linux")
    assert code == 0, out
    assert out.startswith(f"cloned acme-linux {head} (main ")
    target = library / "code" / "acme-linux" / vendor["main"]
    assert out.rstrip().endswith(str(target)) and target.is_dir()
    code, out = run(capsys, catalog_file, "clone", "acme-linux")
    assert code == 0 and out.startswith(f"held acme-linux {head} (main ")
    code, out = run(capsys, catalog_file, "repos", "--topic", "acme")
    assert code == 0
    line = out.strip()
    assert line.startswith(f"acme-linux\t{head} main ")
    assert line.endswith("\t-\tacme, kernel")


def test_ac6_clone_with_ref_reaches_an_sdk_branch(library, catalog_file, vendor, capsys):
    sdk = vendor["sdk-2"][:7]
    code, out = run(capsys, catalog_file, "clone", "acme-linux", "--ref", "sdk-2")
    assert code == 0, out
    assert out.startswith(f"cloned acme-linux {sdk} (sdk-2 ")
    code, out = run(capsys, catalog_file, "grep", "acme-linux", "sdk2", "--ref", "sdk-2")
    assert code == 0
    assert out.startswith(f"acme-linux@{sdk} drivers/soc/acme/sdk2.c:1 | int sdk2;")
    argv = ["code", "acme-linux", "README.md", "--ref", "sdk-2"]
    code, out = run(capsys, catalog_file, *argv)
    assert code == 0
    cite = out.splitlines()[0]
    assert cite.startswith(f"cite: code | acme-linux {sdk} | sdk-2 ")
    assert vendor["url"] in cite


def test_ac6_reading_a_vendor_tree_not_held_says_how_to_clone(
    library, catalog_file, capsys
):
    code, out = run(capsys, catalog_file, "grep", "acme-linux", "espi")
    assert code == 2
    assert out.strip() == "acme-linux is not in the Library; run: bmcspec clone acme-linux"


# ------------------------------------------------------------ AC-4


@pytest.mark.parametrize(
    "argv",
    [
        ["clone", "acme-linux", "--release", "1.0.0"],
        ["grep", "acme-linux", "espi", "--release", "1.0.0"],
        ["code", "acme-linux", "README.md", "--release", "1.0.0"],
        ["code", "ACME-Linux", "README.md", "--release", "1.0.0"],
    ],
)
def test_ac4_release_on_a_vendor_tree_exits_2_without_git(
    library, catalog_file, capsys, no_git, argv
):
    code, out = run(capsys, catalog_file, *argv)
    assert code == 2
    assert out.strip() == "acme-linux has no Release; use --ref with an SDK branch or tag"
    assert not (library / "code").exists()


def test_ac4_release_on_an_upstream_tree_still_works(
    library, catalog_file, upstream, capsys
):
    first = upstream["thing"][2][:7]
    code, out = run(capsys, catalog_file, "clone", "thing", "--release", "1.0.0")
    assert code == 0, out
    assert f"cloned thing {first} (release 1.0.0)" in out


# ------------------------------------------------------------ AC-5


def test_ac5_config_release_is_skipped_with_a_note_on_a_vendor_tree(
    library, catalog_file, vendor, upstream, capsys
):
    _set_config_release(library)
    note = "note: acme-linux has no Release; config.toml release 1.0.0 not used"
    head = vendor["main"][:7]
    code, out = run(capsys, catalog_file, "clone", "acme-linux")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == note
    assert lines[1].startswith(f"cloned acme-linux {head} (main ")
    assert "release: 1.0.0" not in out
    # the release source was not fetched for it
    assert not (library / "code" / "openbmc").exists()

    code, out = run(capsys, catalog_file, "grep", "acme-linux", "ast-espi")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == note
    assert lines[1].startswith(f"acme-linux@{head} drivers/soc/acme/espi.c:2 ")
    assert "note: release" not in out

    code, out = run(capsys, catalog_file, "code", "acme-linux", "README.md")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == note
    assert lines[1].startswith(f"cite: code | acme-linux {head} | main ")

    # an upstream tree keeps following the configured Release
    first = upstream["thing"][2][:7]
    code, out = run(capsys, catalog_file, "clone", "thing")
    assert code == 0, out
    assert out.splitlines()[0] == "release: 1.0.0 (from config.toml)"
    assert f"cloned thing {first} (release 1.0.0)" in out
    code, out = run(capsys, catalog_file, "grep", "thing", "powerState")
    assert code == 0 and out.splitlines()[0] == "note: release 1.0.0 from config.toml"
    assert out.splitlines()[1].startswith(f"thing@{first} ")


def test_ac5_explicit_ref_on_a_vendor_tree_needs_no_note(
    library, catalog_file, vendor, capsys
):
    _set_config_release(library)
    sdk = vendor["sdk-2"][:7]
    code, out = run(capsys, catalog_file, "clone", "acme-linux", "--ref", "sdk-2")
    assert code == 0, out
    assert "note:" not in out and out.startswith(f"cloned acme-linux {sdk} (sdk-2 ")
    code, out = run(capsys, catalog_file, "grep", "acme-linux", "sdk2", "--ref", "sdk-2")
    assert code == 0 and "note:" not in out


# ------------------------------------------------------------ AC-3


def test_ac3_unlisted_vendor_prefixed_id_is_refused_not_guessed(
    library, catalog_file, capsys, monkeypatch, tmp_path
):
    (tmp_path / "guess").mkdir()
    make_repo(tmp_path / "guess", "acme-zephyr", {"a.txt": "hello\n"})
    make_repo(tmp_path / "guess", "extra", {"a.txt": "hello\n"})
    make_repo(tmp_path / "guess", "acme", {"a.txt": "hello\n"})
    monkeypatch.setattr(code_mod, "GUESS_BASE", (tmp_path / "guess").as_uri() + "/")
    message = (
        "acme-zephyr is not in the catalog; vendor repositories are cloned "
        "only from catalog entries (bmcspec repos lists them)"
    )
    for spelled in ("acme-zephyr", "ACME-zephyr", "Acme-Zephyr"):
        code, out = run(capsys, catalog_file, "clone", spelled)
        assert code == 2, spelled
        assert out.strip() == message.replace("acme-zephyr", spelled), spelled
        assert "trying" not in out
    assert not (library / "code").exists()
    # no dash, or a prefix that is no owner: still guessed as before
    for name in ("extra", "acme"):
        code, out = run(capsys, catalog_file, "clone", name)
        assert code == 0, out
        assert out.splitlines()[0].startswith(f"note: {name} is not in the catalog; trying ")
        assert out.splitlines()[1].startswith(f"cloned {name} ")


def test_ac3_vendor_prefix_refusal_runs_no_git(library, catalog_file, capsys, no_git):
    code, out = run(capsys, catalog_file, "clone", "acme-mcuboot")
    assert code == 2 and "vendor repositories are cloned only" in out


def test_ac3_prefix_check_uses_the_loaded_catalog(
    library, tmp_path, upstream, capsys, monkeypatch
):
    """Without any owned entry in the catalog nothing is a vendor prefix."""
    (tmp_path / "guess").mkdir()
    make_repo(tmp_path / "guess", "acme-zephyr", {"a.txt": "hello\n"})
    monkeypatch.setattr(code_mod, "GUESS_BASE", (tmp_path / "guess").as_uri() + "/")
    text = MINI_CATALOG + (
        f'\n[[repos]]\nid = "thing"\nurl = "{upstream["thing"][1]}"\n'
        'topics = ["power"]\n'
    )
    path = tmp_path / "plain.toml"
    path.write_text(text, encoding="utf-8", newline="")
    code, out = run(capsys, path, "clone", "acme-zephyr")
    assert code == 0, out
    assert out.splitlines()[0].startswith("note: acme-zephyr is not in the catalog")


# ------------------------------------------------------------ AC-11


def test_ac11_catalog_ref_replaces_the_default_branch(
    library, tmp_path, upstream, vendor, capsys
):
    sdk, main_head = vendor["sdk-2"][:7], vendor["main"][:7]
    pinned = _write_catalog(tmp_path / "pinned.toml", upstream, vendor, ref="sdk-2")
    code, out = run(capsys, pinned, "clone", "acme-linux")
    assert code == 0, out
    assert out.startswith(f"cloned acme-linux {sdk} (sdk-2 ")
    assert (library / "code" / "acme-linux" / vendor["sdk-2"]).is_dir()
    assert not (library / "code" / "acme-linux" / vendor["main"]).exists()
    # the reading commands find it without a flag, and cite the branch
    code, out = run(capsys, pinned, "grep", "acme-linux", "sdk2")
    assert code == 0 and out.startswith(f"acme-linux@{sdk} drivers/soc/acme/sdk2.c:1")
    code, out = run(capsys, pinned, "code", "acme-linux", "README.md")
    assert code == 0 and out.startswith(f"cite: code | acme-linux {sdk} | sdk-2 ")
    # --ref still reaches the real default branch
    code, out = run(capsys, pinned, "clone", "acme-linux", "--ref", "main")
    assert code == 0 and out.startswith(f"cloned acme-linux {main_head} (main ")


def test_ac11_second_plain_clone_is_held_without_the_network(
    library, tmp_path, upstream, vendor, capsys, monkeypatch
):
    sdk = vendor["sdk-2"][:7]
    pinned = _write_catalog(tmp_path / "pinned.toml", upstream, vendor, ref="sdk-2")
    code, out = run(capsys, pinned, "clone", "acme-linux")
    assert code == 0, out

    real = code_mod.run_git
    fetched = []

    def watch(args, **kwargs):
        if args and args[0] in ("clone", "fetch", "ls-remote"):
            fetched.append(args)
        return real(args, **kwargs)

    monkeypatch.setattr(code_mod, "run_git", watch)
    code, out = run(capsys, pinned, "clone", "acme-linux")
    assert code == 0 and out.startswith(f"held acme-linux {sdk} (sdk-2 ")
    assert fetched == []


def test_ac11_reading_prefers_the_tree_the_current_ref_names(
    library, tmp_path, upstream, vendor, capsys
):
    sdk, main_head = vendor["sdk-2"][:7], vendor["main"][:7]
    old = _write_catalog(tmp_path / "old.toml", upstream, vendor, ref="main")
    code, out = run(capsys, old, "clone", "acme-linux")
    assert code == 0 and out.startswith(f"cloned acme-linux {main_head} (main ")
    new = _write_catalog(tmp_path / "new.toml", upstream, vendor, ref="sdk-2")
    code, out = run(capsys, new, "clone", "acme-linux")
    assert code == 0 and out.startswith(f"cloned acme-linux {sdk} (sdk-2 ")
    # both default-kind trees are held; the catalog's ref decides
    code, out = run(capsys, new, "code", "acme-linux", "README.md")
    assert code == 0 and out.startswith(f"cite: code | acme-linux {sdk} | sdk-2 ")
    code, out = run(capsys, old, "code", "acme-linux", "README.md")
    assert code == 0 and out.startswith(f"cite: code | acme-linux {main_head} | main ")


def test_ac11_ref_and_config_release_together_on_a_vendor_tree(
    library, tmp_path, upstream, vendor, capsys
):
    _set_config_release(library)
    sdk = vendor["sdk-2"][:7]
    pinned = _write_catalog(tmp_path / "pinned.toml", upstream, vendor, ref="sdk-2")
    code, out = run(capsys, pinned, "clone", "acme-linux")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "note: acme-linux has no Release; config.toml release 1.0.0 not used"
    assert lines[1].startswith(f"cloned acme-linux {sdk} (sdk-2 ")

"""T76.2: the libraries OpenBMC recipes fetch from other projects (libspdm,
spdm-emu, mctp, nvme-cli, libnvme, ipmitool) are catalog Code Trees that a
Release pins like an upstream component. The recipes below are written the
way meta-openembedded writes them; no network is used."""

import shutil

import pytest

from bmc_toolkit.spec import catalog as catalog_mod
from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import commit, git, make_repo, make_scenario, push

SHIPPED = catalog_mod.load_catalog()

EXTERNAL = {
    "libspdm": "https://github.com/DMTF/libspdm.git",
    "spdm-emu": "https://github.com/DMTF/spdm-emu.git",
    "mctp": "https://github.com/CodeConstruct/mctp.git",
    "nvme-cli": "https://github.com/linux-nvme/nvme-cli.git",
    "libnvme": "https://github.com/linux-nvme/libnvme.git",
    "ipmitool": "https://codeberg.org/IPMITool/ipmitool.git",
}

OE_NAME = "meta-openembedded"
OE = f"upstream-layers/{OE_NAME}"  # master; 2.18.0 keeps it at the top level


def _rev(n: int) -> str:
    return f"{n:040x}"


# ------------------------------------------------------------- AC-1


def test_shipped_catalog_lists_the_six_libraries_without_owner_or_ref():
    for repo_id, url in EXTERNAL.items():
        repo = SHIPPED.get_repo(repo_id)
        assert repo is not None, repo_id
        assert repo.id == repo_id
        assert repo.url == url
        assert repo.owner == "" and repo.ref == "", repo_id
    # libspdm without unit_test/ (AC-6: 60 MB whole on main in 2026-11)
    spdm_paths = ("include", "library", "os_stub", "doc")
    assert SHIPPED.get_repo("libspdm").sparse == spdm_paths
    # one entry per id; the total is not pinned, so a later entry needs no edit
    assert len({r.id.lower() for r in SHIPPED.repos}) == len(SHIPPED.repos)


@pytest.mark.parametrize(
    ("topic", "ids"),
    [
        ("spdm", {"libspdm", "spdm-emu"}),
        ("mctp", {"mctp"}),
        ("nvme", {"nvme-cli", "libnvme"}),
        ("ipmi", {"ipmitool"}),
    ],
)
def test_a_topic_lists_the_libraries_for_it(topic, ids):
    listed = {r.id for r in SHIPPED.by_topic(topic)}
    assert ids <= listed


# ------------------------------------------------------------- AC-2


def _write(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")


RECIPES = {
    "libspdm": (
        f"{OE}/meta-oe/recipes-support/libspdm/libspdm_3.8.2.bb",
        'SRC_URI = "git://github.com/DMTF/libspdm.git;branch=release-3.8;'
        'protocol=https;tag=${PV}"\nSRCREV = "%s"\n',
    ),
    "spdm-emu": (
        f"{OE}/meta-oe/recipes-security/spdm-emu/spdm-emu_git.bb",
        'SRC_URI = "gitsm://github.com/DMTF/spdm-emu;protocol=https;branch=main"\n'
        'SRCREV = "%s"\n',
    ),
    "nvme-cli": (
        f"{OE}/meta-oe/recipes-bsp/nvme-cli/nvme-cli_2.16.bb",
        'SRCREV = "%s"\nSRC_URI = "git://github.com/linux-nvme/nvme-cli.git;'
        'branch=master;protocol=https;tag=v${PV}"\n',
    ),
    "libnvme": (
        f"{OE}/meta-oe/recipes-support/libnvme/libnvme_1.16.2.bb",
        'SRCREV = "%s"\nSRC_URI = "git://github.com/linux-nvme/libnvme;'
        'protocol=https;branch=master;tag=v${PV}"\n',
    ),
    "ipmitool": (
        f"{OE}/meta-oe/recipes-kernel/ipmitool/ipmitool_1.8.19.bb",
        'SRCREV = "%s"\nSRC_URI = "git://codeberg.org/ipmitool/ipmitool;'
        "protocol=https;branch=master \\\n"
        '           file://0001-fix.patch \\\n           "\n',
    ),
}
MCTP_DIR = f"{OE}/meta-networking/recipes-support/mctp"


def _layers(root, *, top="upstream-layers/meta-openembedded"):
    files = {}
    pins = {}
    for n, (repo_id, (rel, text)) in enumerate(RECIPES.items(), start=1):
        pins[repo_id] = _rev(n)
        files[rel.replace(OE, top)] = text % _rev(n)
    mctp_dir = MCTP_DIR.replace(OE, top)
    pins["mctp"] = _rev(9)
    files[f"{mctp_dir}/mctp.inc"] = (
        'SRC_URI = "git://github.com/CodeConstruct/mctp;branch=main;'
        f'protocol=https;tag=v${{PV}}"\nSRCREV = "{_rev(9)}"\n'
    )
    files[f"{mctp_dir}/mctp_2.6.bb"] = 'require mctp.inc\nMESON_TARGET = "mctp"\n'
    files[f"{mctp_dir}/mctpd_2.6.bb"] = "require mctp.inc\ninherit systemd\n"
    _write(root, files)
    return pins


@pytest.mark.parametrize("top", [f"upstream-layers/{OE_NAME}", OE_NAME])
@pytest.mark.parametrize("repo_id", sorted(EXTERNAL))
def test_each_library_resolves_to_its_recipe_srcrev(tmp_path, repo_id, top):
    pins = _layers(tmp_path, top=top)
    rev, recipe = code_mod.find_pin_recipe(tmp_path, repo_id, EXTERNAL[repo_id])
    assert rev == pins[repo_id]
    assert recipe.startswith(top + "/")


@pytest.mark.parametrize("repo_id", sorted(EXTERNAL))
def test_another_project_with_the_same_name_is_not_a_pin(tmp_path, repo_id):
    pins = _layers(tmp_path)
    _write(
        tmp_path,
        {
            f"meta-acme/recipes-x/{repo_id}/{repo_id}-fork_git.bb": (
                f'SRC_URI = "git://github.com/acme/{repo_id};branch=main"\n'
                f'SRCREV = "{_rev(77)}"\n'
            ),
            f"meta-acme/recipes-x/{repo_id}/{repo_id}-mirror_git.bb": (
                f'SRC_URI = "git://gitlab.example.com/DMTF/{repo_id}.git;branch=main"\n'
                f'SRCREV = "{_rev(78)}"\n'
            ),
        },
    )
    rev, _recipe = code_mod.find_pin_recipe(tmp_path, repo_id, EXTERNAL[repo_id])
    assert rev == pins[repo_id]


def test_mctp_and_mctpd_are_one_pin(tmp_path):
    pins = _layers(tmp_path)
    rev, recipe = code_mod.find_pin_recipe(tmp_path, "mctp", EXTERNAL["mctp"])
    assert rev == pins["mctp"]
    assert recipe == f"{MCTP_DIR}/mctp.inc"


# ------------------------------------------------------------- AC-3

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

LIB_DIR = "upstream-layers/meta-openembedded/meta-oe/recipes-support/libspdm"


def _build(root):
    work, _bare, url = make_repo(root, "libspdm", {"include/spdm.h": "int spdm;\n"})
    pinned = git("rev-parse", "HEAD", cwd=work)
    tip = commit(work, {"include/spdm.h": "int spdm2;\n"}, "newer")
    push(work, "main")
    files = {
        f"{LIB_DIR}/libspdm_3.8.2.bb": (
            'SRC_URI = "git://github.com/DMTF/libspdm.git;branch=main;protocol=https"\n'
            f'SRCREV = "{pinned}"\n'
        ),
        "README.md": "distro\n",
    }
    ob_work, _b, ob_url = make_repo(root, "openbmc", files, branch="master")
    git("tag", "1.0.0", cwd=ob_work)
    push(ob_work, "1.0.0")
    return {"lib": url, "ob": ob_url, "pinned": pinned, "tip": tip}


@pytest.fixture
def remotes(tmp_path):
    return make_scenario(tmp_path, "external-libspdm", _build)


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


def _catalog(tmp_path, remotes):
    """The shipped libspdm entry, its URL swapped for the local remote."""
    shipped = SHIPPED.get_repo("libspdm")
    topics = ", ".join(f'"{t}"' for t in shipped.topics)
    sparse = SHIPPED.get_repo("openbmc").sparse
    listed = ", ".join(f'"{s}"' for s in sparse)
    text = (
        MINI_CATALOG
        + f"""
[[repos]]
id = "openbmc"
url = "{remotes["ob"]}"
topics = ["release"]
sparse = [{listed}]

[[repos]]
id = "{shipped.id}"
url = "{remotes["lib"]}"
topics = [{topics}]
"""
    )
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def run(capsys, catalog_file, *argv):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@needs_git
def test_release_clone_takes_the_pin(tmp_path, remotes, library, capsys):
    cat = _catalog(tmp_path, remotes)
    code, out = run(capsys, cat, "clone", "libspdm", "--release", "1.0.0")
    assert code == 0, out
    assert "has no Release" not in out
    assert f"libspdm {remotes['pinned'][:7]}" in out


@needs_git
def test_config_release_applies(tmp_path, remotes, library, capsys):
    cat = _catalog(tmp_path, remotes)
    library.mkdir(parents=True, exist_ok=True)
    (library / "config.toml").write_text(
        '[code]\nrelease = "1.0.0"\n', encoding="utf-8", newline=""
    )
    code, out = run(capsys, cat, "clone", "libspdm")
    assert code == 0, out
    assert out.splitlines()[0] == "release: 1.0.0 (from config.toml)"
    assert "has no Release" not in out
    assert f"libspdm {remotes['pinned'][:7]}" in out


@needs_git
def test_plain_clone_takes_the_default_branch(tmp_path, remotes, library, capsys):
    cat = _catalog(tmp_path, remotes)
    code, out = run(capsys, cat, "clone", "libspdm")
    assert code == 0, out
    assert f"libspdm {remotes['tip'][:7]} (main " in out

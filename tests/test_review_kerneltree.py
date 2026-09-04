"""Reviewer acceptance tests for M10 AC-4: the kernel as a sparse Code
Tree. The shipped catalog lists ``linux`` with the ten directories, the
kernel topics list it, and a clone of a ``file://`` fixture repository with
the shipped sparse list checks out only those paths.

Black-box through the ``bmcspec`` CLI against a local bare repository;
skipped when git is not on PATH. No network.
"""

import shutil

import pytest

from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import make_repo

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

SPARSE = (
    "Documentation",
    "drivers/hwmon",
    "drivers/i2c",
    "drivers/gpio",
    "drivers/peci",
    "drivers/char/ipmi",
    "net/ncsi",
    "net/mctp",
    "drivers/net/mctp",
    "drivers/mtd/spi-nor",
)
TOPICS = ("hwmon", "ipmi", "mctp", "ncsi", "peci")

# One file under every directory of the sparse list ...
KEPT = {
    "Documentation/hwmon/index.rst": "hwmon_device_register is described here\n",
    "drivers/hwmon/lm75.c": "hwmon_device_register(dev);\n",
    "drivers/i2c/busses/i2c-aspeed.c": "i2c\n",
    "drivers/gpio/gpio-aspeed.c": "gpio\n",
    "drivers/peci/core.c": "peci\n",
    "drivers/char/ipmi/ipmi_msghandler.c": "ipmi\n",
    "net/ncsi/ncsi-manage.c": "ncsi\n",
    "net/mctp/route.c": "mctp\n",
    "drivers/net/mctp/mctp-i2c.c": "mctp i2c\n",
    "drivers/mtd/spi-nor/core.c": "spi-nor\n",
}
# ... and files in sibling directories that must not come along.
CUT = {
    "drivers/char/tpm/tpm.c": "hwmon_device_register must not be found here\n",
    "drivers/net/ethernet/e.c": "ethernet\n",
    "drivers/gpu/big.c": "hwmon_device_register must not be found here\n",
    "drivers/mtd/nand/n.c": "nand\n",
    "net/ipv4/y.c": "ipv4\n",
    "fs/ext4/f.c": "fs\n",
    "arch/arm/z.c": "arch\n",
    "kernel/k.c": "kernel\n",
}
TOP = {"Makefile": "all:\n", "MAINTAINERS": "list\n"}


def run(capsys, *argv, catalog_file=None):
    args = ["--catalog", str(catalog_file)] if catalog_file else []
    code = main([*args, *argv])
    return code, capsys.readouterr().out


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


@pytest.fixture
def kernel(tmp_path):
    work, bare, url = make_repo(tmp_path, "linux", {**KEPT, **CUT, **TOP})
    return url


@pytest.fixture
def catalog_file(tmp_path, kernel, shipped):
    sparse = ", ".join(f'"{p}"' for p in shipped.get_repo("linux").sparse)
    text = (
        MINI_CATALOG
        + f"""
[[repos]]
id = "linux"
url = "{kernel}"
topics = ["kernel", "hwmon"]
sparse = [{sparse}]
"""
    )
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def _tree_dirs(root, repo):
    rdir = root / "code" / repo
    if not rdir.is_dir():
        return []
    return sorted(p for p in rdir.iterdir() if p.is_dir() and not p.name.startswith("."))


# ------------------------------------------------------------- catalog


def test_ac4_shipped_catalog_lists_linux_as_a_sparse_code_tree(shipped):
    linux = shipped.get_repo("linux")
    assert linux is not None
    assert linux.id == "linux"
    assert linux.url == "https://github.com/openbmc/linux.git"
    assert linux.sparse == SPARSE
    lowered = {t.lower() for t in linux.topics}
    for topic in TOPICS:
        assert topic in lowered, topic
    # a directory list, so the clone uses cone mode (no glob in any entry)
    assert not any(ch in entry for entry in linux.sparse for ch in "*?[")


@pytest.mark.parametrize("topic", TOPICS)
def test_ac4_repos_topic_lists_linux(library, capsys, topic):
    code, out = run(capsys, "repos", "--topic", topic)
    assert code == 0, out
    lines = [ln for ln in out.splitlines() if ln.startswith("linux\t")]
    assert len(lines) == 1, out
    assert topic in lines[0].split("\t")[-1].lower()


def test_ac4_openbmc_component_repositories_stay_listed(shipped):
    for repo_id in ("openbmc", "bmcweb", "phosphor-host-ipmid", "pldm"):
        assert shipped.get_repo(repo_id) is not None, repo_id


# --------------------------------------------------------------- clone


@needs_git
def test_ac4_clone_with_the_shipped_sparse_list_checks_out_only_those_paths(
    library, catalog_file, capsys
):
    code, out = run(capsys, "clone", "linux", "--ref", "main", catalog_file=catalog_file)
    assert code == 0, out
    assert out.startswith("cloned linux "), out
    trees = _tree_dirs(library.root, "linux")
    assert len(trees) == 1, trees
    tree = trees[0]
    for rel in KEPT:
        assert (tree / rel).is_file(), f"{rel} missing from the sparse tree"
    for rel in CUT:
        assert not (tree / rel).exists(), f"{rel} should not be checked out"
    # the files of the top directory come along in cone mode
    for rel in TOP:
        assert (tree / rel).is_file(), rel
    # no leftover temporary directory
    assert not list((library.root / "code" / "linux").glob(".tmp-*"))


@needs_git
def test_ac4_grep_hits_under_hwmon_and_documentation_only(library, catalog_file, capsys):
    code, out = run(capsys, "clone", "linux", "--ref", "main", catalog_file=catalog_file)
    assert code == 0, out
    code, out = run(
        capsys,
        "grep",
        "linux",
        "hwmon_device_register",
        "--ref",
        "main",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    hits = [ln for ln in out.splitlines() if "hwmon_device_register" in ln]
    paths = {ln.split()[1].split(":")[0] for ln in hits if ln.startswith("linux@")}
    assert "drivers/hwmon/lm75.c" in paths, out
    assert "Documentation/hwmon/index.rst" in paths, out
    assert not any(p.startswith(("drivers/gpu", "drivers/char/tpm")) for p in paths), out

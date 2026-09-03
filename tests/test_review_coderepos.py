"""Independent acceptance tests for the Source Catalog's ``[[repos]]`` table
and for ``clone``/``repos`` handling of repositories the catalog does not
list (AC-1, AC-11, AC-12 of the Code Trees change).

Black-box: goes through ``parse_catalog`` and the ``bmcspec`` CLI, the same
way a user or the Skill would. Local bare git repositories stand in for
GitHub remotes; no network is used. Skipped when git is not on PATH.
"""

import shutil

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.catalog import CatalogError, load_catalog, parse_catalog
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import make_repo

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _minimal_catalog(repos):
    return {
        "schema_version": 1,
        "families": {"x": {"title": "X", "publisher": "P"}},
        "documents": [],
        "repos": repos,
    }


# ------------------------------------------------------- AC-1: validation


def test_repo_ids_must_be_unique():
    data = _minimal_catalog(
        [
            {"id": "bmcweb", "url": "https://github.com/openbmc/bmcweb.git",
             "topics": ["redfish"]},
            {"id": "BMCWeb", "url": "https://github.com/openbmc/bmcweb.git",
             "topics": ["web"]},
        ]
    )
    with pytest.raises(CatalogError, match="duplicate id"):
        parse_catalog(data)


def test_repo_url_must_be_https_or_file():
    data = _minimal_catalog(
        [{"id": "thing", "url": "git://github.com/openbmc/thing.git", "topics": ["x"]}]
    )
    with pytest.raises(CatalogError, match="https"):
        parse_catalog(data)


def test_repo_needs_at_least_one_non_empty_topic():
    data = _minimal_catalog(
        [{"id": "thing", "url": "https://github.com/openbmc/thing.git", "topics": []}]
    )
    with pytest.raises(CatalogError, match="topic"):
        parse_catalog(data)
    data = _minimal_catalog(
        [{"id": "thing", "url": "https://github.com/openbmc/thing.git",
          "topics": ["  "]}]
    )
    with pytest.raises(CatalogError, match="topic"):
        parse_catalog(data)


def test_repo_catalog_round_trips_get_repo_and_by_topic():
    data = _minimal_catalog(
        [
            {"id": "bmcweb", "url": "https://github.com/openbmc/bmcweb.git",
             "topics": ["redfish", "web"]},
            {"id": "pldm", "url": "https://github.com/openbmc/pldm.git",
             "topics": ["pldm"], "sparse": ["src"]},
        ]
    )
    catalog = parse_catalog(data)
    assert catalog.get_repo("BMCWEB").id == "bmcweb"  # case-insensitive
    assert catalog.get_repo("nope") is None
    assert [r.id for r in catalog.by_topic("redfish")] == ["bmcweb"]
    assert catalog.get_repo("pldm").sparse == ("src",)


# --------------------------------------------------- AC-12: shipped catalog


def test_shipped_catalog_covers_openbmc_components_and_excludes_tooling():
    catalog = load_catalog()  # the real bmc_toolkit/spec/catalog.toml
    ids = {r.id.lower() for r in catalog.repos}
    # About 95 upstream repositories per AC-12; well above the ~30 the
    # first cut shipped with and comfortably short of the openbmc org's
    # full repository count (164, per the change description).
    assert 60 <= len(ids) <= 164
    for expected in ("openbmc", "bmcweb", "phosphor-host-ipmid", "pldm"):
        assert expected in ids, f"{expected} should be in the catalog"
    # Forks and tooling are left out on purpose (AC-12).
    for excluded in (
        "linux",
        "qemu",
        "u-boot",
        "openbmc-build-scripts",
        "openbmc-test-automation",
    ):
        assert excluded not in ids, f"{excluded} should not be in the catalog"
    openbmc = catalog.get_repo("openbmc")
    assert openbmc is not None
    assert openbmc.sparse == ("/meta-*/**/*.bb", "/meta-*/**/*.inc")


# ------------------------------------------------- AC-11: unlisted repos


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def unlisted_remote(tmp_path):
    return make_repo(tmp_path, "extra", {"a.txt": "hello world\n"})


@pytest.fixture
def catalog_file(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(MINI_CATALOG, encoding="utf-8", newline="")
    return path


@pytest.fixture
def env_library(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


def test_clone_guesses_github_url_for_a_repo_the_catalog_does_not_list(
    catalog_file, env_library, unlisted_remote, capsys, monkeypatch
):
    work, bare, url = unlisted_remote
    base = url.rsplit("/", 1)[0] + "/"
    monkeypatch.setattr(code_mod, "GUESS_BASE", base)
    code, out = run(capsys, "clone", "extra", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == f"note: extra is not in the catalog; trying {base}extra.git"
    assert "cloned extra" in lines[1]
    tree_dirs = [p for p in (env_library / "code" / "extra").iterdir() if p.is_dir()]
    meta_text = (tree_dirs[0] / code_mod.TREE_META).read_text("utf-8")
    assert '"catalog_known": false' in meta_text
    # grep and code work on the guessed tree (AC-11).
    code, out = run(capsys, "grep", "extra", "hello", catalog_file=catalog_file)
    assert code == 0 and "a.txt:1 | hello world" in out
    # repos marks it after the catalog's entries, "(not in catalog)".
    code, out = run(capsys, "repos", catalog_file=catalog_file)
    last = out.strip().splitlines()[-1]
    assert last.startswith("extra\t") and last.endswith("(not in catalog)")


def test_clone_refuses_an_id_with_a_slash_or_a_leading_dot(
    catalog_file, env_library, capsys
):
    for bad in ("../evil", "a/b", ".hidden"):
        code, out = run(capsys, "clone", bad, catalog_file=catalog_file)
        assert code == 2, bad
        assert "not a repository id" in out

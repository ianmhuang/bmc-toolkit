"""Review acceptance tests for prune (AC-8) and the M5/M6 leftovers (AC-9).

The Code Tree parts run against local bare repositories and are skipped
when git is not on PATH; the bundle parts need no git.
"""

import json
import shutil
import sys

import pytest

from bmc_toolkit.spec import bundle as bundle_mod
from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import RECIPE, THING_FILES, commit, git, make_repo, push

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


@pytest.fixture
def remotes(tmp_path):
    """thing (two commits on main) and openbmc (a recipe under meta-phosphor
    pinning thing's first commit, tagged 1.0.0)."""
    work, bare, url = make_repo(tmp_path, "thing", THING_FILES)
    first = git("rev-parse", "HEAD", cwd=work)
    recipe = RECIPE.format(url=url.removeprefix("file://"), sha=first)
    ob_files = {
        "meta-phosphor/recipes-phosphor/things/thing_git.bb": recipe,
        "README.md": "distro\n",
    }
    ob_work, ob_bare, ob_url = make_repo(tmp_path, "openbmc", ob_files, branch="master")
    git("tag", "1.0.0", cwd=ob_work)
    push(ob_work, "1.0.0")
    second = commit(work, {"src/main.cpp": "int main() { return 2; }\n"}, "second")
    push(work)
    return {"thing": (work, url, first, second), "openbmc": (ob_work, ob_url)}


@pytest.fixture
def catalog_file(tmp_path, remotes):
    text = (
        MINI_CATALOG
        + f"""
[[repos]]
id = "openbmc"
url = "{remotes["openbmc"][1]}"
topics = ["release"]
sparse = ["meta-phosphor"]

[[repos]]
id = "thing"
url = "{remotes["thing"][1]}"
topics = ["state"]
"""
    )
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


@pytest.fixture
def lib_root(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


# ----------------------------------------------------------------- AC-8


@needs_git
def test_prune_lists_then_removes_only_superseded_trees_and_leftovers(
    lib_root, catalog_file, remotes, capsys, tmp_path
):
    work, url, first, second = remotes["thing"]
    code, out = run(capsys, "prune", catalog_file=catalog_file)
    assert code == 0 and "nothing to prune" in out
    # a tree reached by a commit: never superseded
    code, out = run(capsys, "clone", "thing", "--ref", first, catalog_file=catalog_file)
    assert code == 0, out
    # the default-branch tree, then a newer commit re-fetched with --force
    code, out = run(capsys, "clone", "thing", catalog_file=catalog_file)
    assert code == 0, out
    third = commit(work, {"README.md": "thing 3\n"}, "third")
    push(work)
    code, out = run(capsys, "clone", "thing", "--force", catalog_file=catalog_file)
    assert code == 0 and "superseded" in out, out
    by_ref = lib_root / "code" / "thing" / first
    old = lib_root / "code" / "thing" / second
    new = lib_root / "code" / "thing" / third
    assert by_ref.is_dir() and old.is_dir() and new.is_dir()
    leftover = lib_root / "code" / "thing" / ".tmp-4242"
    leftover.mkdir()
    (leftover / "half").write_text("x", encoding="utf-8")
    specs = lib_root / "specs" / "mctp" / "DSP0236" / "1.3.3"
    specs.mkdir(parents=True)
    (specs / "original.pdf").write_bytes(b"%PDF-1.7\n")
    checkout = tmp_path / "my-thing"
    checkout.mkdir()
    (checkout / "mine").write_text("keep\n", encoding="utf-8")
    lib_root.mkdir(exist_ok=True)
    (lib_root / "config.toml").write_text(
        f'[code.checkouts]\nthing = "{checkout.as_posix()}"\n', encoding="utf-8"
    )

    code, out = run(capsys, "prune", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    would = [ln for ln in lines if ln.startswith("would remove ")]
    assert len(would) == 2
    assert any(str(old) in ln and third[:7] in ln for ln in would)
    assert any(str(leftover) in ln for ln in would)
    assert not any(str(new) in ln or str(by_ref) in ln for ln in would)
    assert any(ln.startswith("prune: ") for ln in lines)
    assert old.is_dir() and leftover.is_dir()  # nothing removed

    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    removed = [ln for ln in lines if ln.startswith("removed ")]
    assert len(removed) == 2
    assert any(ln.startswith(f"removed {old}") for ln in removed)
    assert any(ln.startswith(f"removed {leftover}") for ln in removed)
    assert any(ln.startswith("prune: ") for ln in lines)
    assert not old.exists() and not leftover.exists()  # git objects included
    assert (new / "README.md").read_text("utf-8") == "thing 3\n"
    assert (by_ref / "README.md").is_file()
    assert (specs / "original.pdf").is_file()
    assert (checkout / "mine").is_file()
    code, out = run(capsys, "prune", catalog_file=catalog_file)
    assert code == 0 and "nothing to prune" in out
    # the remaining trees are still usable
    code, out = run(capsys, "repos", "--topic", "state", catalog_file=catalog_file)
    assert code == 0 and third[:7] in out and second[:7] not in out


@needs_git
def test_prune_leftovers_are_found_without_any_tree(lib_root, catalog_file, capsys):
    leftover = lib_root / "code" / "bmcweb" / ".tmp-17928"
    leftover.mkdir(parents=True)
    (leftover / "x").write_text("x", encoding="utf-8")
    code, out = run(capsys, "prune", catalog_file=catalog_file)
    assert code == 0 and f"would remove {leftover}" in out
    assert leftover.is_dir()
    code, out = run(capsys, "prune", "--yes", catalog_file=catalog_file)
    assert code == 0 and f"removed {leftover}" in out
    assert not leftover.exists()


# ----------------------------------------------------------------- AC-9


def test_find_pin_recipe_returns_the_recipe_and_refuses_disagreement(tmp_path):
    distro = tmp_path / "distro"
    phosphor = distro / "meta-phosphor" / "recipes-phosphor" / "things"
    vendor = distro / "meta-vendor" / "recipes-phosphor" / "things"
    phosphor.mkdir(parents=True)
    vendor.mkdir(parents=True)
    (phosphor / "thing_git.bb").write_text(
        RECIPE.format(url="github.com/openbmc/thing", sha="a" * 40), encoding="utf-8"
    )
    rev, recipe = code_mod.find_pin_recipe(distro, "thing")
    assert rev == "a" * 40
    assert recipe == "meta-phosphor/recipes-phosphor/things/thing_git.bb"
    assert code_mod.find_pin(distro, "thing") == "a" * 40
    (vendor / "thing_git.bb").write_text(
        RECIPE.format(url="github.com/openbmc/thing.git", sha="b" * 40),
        encoding="utf-8",
    )
    with pytest.raises(code_mod.CodeError) as exc:
        code_mod.find_pin_recipe(distro, "thing")
    message = str(exc.value)
    assert "meta-phosphor/recipes-phosphor/things/thing_git.bb" in message
    assert "meta-vendor/recipes-phosphor/things/thing_git.bb" in message
    with pytest.raises(code_mod.CodeError):
        code_mod.find_pin(distro, "thing")


@needs_git
def test_clone_release_prints_the_pinning_recipe(
    lib_root, catalog_file, remotes, capsys
):
    work, url, first, second = remotes["thing"]
    code, out = run(
        capsys, "clone", "thing", "--release", "1.0.0", catalog_file=catalog_file
    )
    assert code == 0, out
    pin = [ln for ln in out.splitlines() if ln.startswith("pin: ")]
    assert len(pin) == 1
    assert "meta-phosphor/recipes-phosphor/things/thing_git.bb" in pin[0]
    assert first[:7] in pin[0]


def test_code_docstrings_name_every_layer_not_meta_phosphor():
    assert "meta-phosphor" not in code_mod.__doc__
    assert "meta-*" in code_mod.__doc__
    assert "meta-phosphor" not in (code_mod.find_pin_recipe.__doc__ or "")
    assert "meta-phosphor" not in (code_mod.find_pin.__doc__ or "")


def test_rmtree_selects_onexc_by_interpreter_version(tmp_path, monkeypatch):
    target = tmp_path / "victim"
    target.mkdir()
    (target / "f").write_text("x", encoding="utf-8")
    seen = {}
    real = shutil.rmtree

    def spy(path, **kwargs):
        seen.update(kwargs)
        real(path)

    monkeypatch.setattr(code_mod.shutil, "rmtree", spy)
    code_mod._rmtree(target)
    assert not target.exists()
    assert ("onexc" in seen) == (sys.version_info >= (3, 12))
    assert ("onerror" in seen) == (sys.version_info < (3, 12))


@needs_git
def test_clone_ref_sha_fallback_removes_its_directory_with_the_aware_remover(
    tmp_path, monkeypatch
):
    work, bare, url = make_repo(tmp_path, "thing", THING_FILES)
    second = commit(work, {"README.md": "two\n"}, "second")
    push(work)
    removed = []
    real = code_mod._rmtree

    def spy(path):
        removed.append(path)
        real(path)

    monkeypatch.setattr(code_mod, "_rmtree", spy)
    tmp = tmp_path / "lib" / "code" / "thing" / ".tmp-x"
    tmp.mkdir(parents=True)
    (tmp / "stale").write_text("x", encoding="utf-8")
    code_mod._clone_ref(url, second, tmp, ())
    assert tmp in removed
    assert (tmp / "README.md").read_text("utf-8") == "two\n"
    assert not (tmp / "stale").exists()
    real(tmp)


def test_bundle_duplicates_count_only_names_that_shadow_a_kept_member():
    members = [
        "A/json-schema/X.json",
        "A/json-schema/X.v1_0_0.json",
        "A/json-schema/X.v1_1_0.json",
        "B/json-schema/X.v1_0_0.json",  # repeats a member that is not kept
    ]
    kept, refused, duplicates = bundle_mod.select_members(members)
    assert kept == ["A/json-schema/X.json", "A/json-schema/X.v1_1_0.json"]
    assert (refused, duplicates) == (0, 0)
    kept, refused, duplicates = bundle_mod.select_members(
        members + ["B/json-schema/X.v1_1_0.json"]  # repeats a kept member
    )
    assert (refused, duplicates) == (0, 1)


def test_bundle_single_ref_chain_onto_an_enum_is_typed_enum(tmp_path):
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    (schemas / "Resource.json").write_text(
        json.dumps(
            {
                "definitions": {
                    "PowerState": {"anyOf": [{"$ref": "#/definitions/PowerStateEnum"}]},
                    "PowerStateEnum": {"enum": ["On", "Off"], "type": "string"},
                    "Index": {
                        "anyOf": [
                            {"$ref": "#/definitions/IndexV1"},
                            {"$ref": "#/definitions/IndexV2"},
                        ]
                    },
                    "IndexV1": {"type": "object", "properties": {}},
                    "IndexV2": {"type": "object", "properties": {}},
                }
            }
        ),
        encoding="utf-8",
    )
    (schemas / "Chassis.json").write_text(
        json.dumps(
            {
                "definitions": {
                    "Chassis": {
                        "type": "object",
                        "properties": {
                            "PowerState": {
                                "anyOf": [
                                    {"$ref": "Resource.json#/definitions/PowerState"},
                                    {"type": "null"},
                                ]
                            },
                            "Links": {"$ref": "Resource.json#/definitions/Index"},
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    loaded = bundle_mod.Schemas(tmp_path)
    props = loaded.load("Chassis.json")["definitions"]["Chassis"]["properties"]
    assert loaded.type_of(props["PowerState"], "Chassis.json") == "enum PowerState"
    assert loaded.type_of(props["Links"], "Chassis.json") == "object Index"

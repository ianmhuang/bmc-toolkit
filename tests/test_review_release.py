"""Reviewer acceptance tests for the 1.0.0 release change (AC-1 to AC-3).

Black-box against the files a user or the plugin loader reads: the package
version, pyproject.toml, .claude-plugin/plugin.json, README.md and
.claude-plugin/marketplace.json. Every test here fails on main (0.9.0,
README "pre-release", marketplace manifest without a description).
"""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "1.0.0"


def _read(*parts):
    return (ROOT / Path(*parts)).read_text("utf-8")


# AC-1: one version, recorded in three places, all 1.0.0.


def test_package_version_is_the_release():
    import bmc_toolkit

    assert bmc_toolkit.__version__ == RELEASE


def test_pyproject_version_is_the_release():
    pyproject = tomllib.loads(_read("pyproject.toml"))
    assert pyproject["project"]["version"] == RELEASE


def test_plugin_manifest_version_is_the_release():
    plugin = json.loads(_read(".claude-plugin", "plugin.json"))
    assert plugin["version"] == RELEASE


def test_the_three_version_records_agree():
    """The AC asks for equality as well as the value; a future bump that
    touches two of the three files must fail here."""
    import bmc_toolkit

    pyproject = tomllib.loads(_read("pyproject.toml"))
    plugin = json.loads(_read(".claude-plugin", "plugin.json"))
    assert (
        bmc_toolkit.__version__
        == pyproject["project"]["version"]
        == plugin["version"]
        == RELEASE
    )


def test_no_file_still_records_the_previous_version():
    """The bump left no 0.9.0 behind in any version-bearing file."""
    for path in ("pyproject.toml", ".claude-plugin/plugin.json", "bmc_toolkit/__init__.py"):
        assert "0.9.0" not in _read(path), path


# AC-2: README status paragraph names 1.0.0 and drops "pre-release".


def test_readme_status_paragraph_names_the_release():
    readme = _read("README.md")
    match = re.search(r"^\*\*Status: ([^*]+)\*\*", readme, re.MULTILINE)
    assert match is not None, "README has no bold Status line"
    assert match.group(1).rstrip(".") == RELEASE


def test_readme_never_says_pre_release():
    readme = _read("README.md").lower()
    assert "pre-release" not in readme
    assert "prerelease" not in readme
    assert "pre release" not in readme


def test_readme_does_not_mention_the_previous_version():
    assert "0.9.0" not in _read("README.md")


# AC-3: marketplace.json carries a non-empty description.


def test_marketplace_manifest_has_a_non_empty_description():
    manifest = json.loads(_read(".claude-plugin", "marketplace.json"))
    assert "description" in manifest
    assert isinstance(manifest["description"], str)
    assert manifest["description"].strip() != ""


def test_marketplace_manifest_still_lists_this_plugin():
    """Adding the description must not disturb the rest of the manifest:
    the marketplace is named, has an owner, and lists exactly this plugin
    with a relative source."""
    manifest = json.loads(_read(".claude-plugin", "marketplace.json"))
    assert manifest["name"] == "bmc-toolkit"
    assert manifest["owner"]["name"].strip()
    plugins = manifest["plugins"]
    assert len(plugins) == 1
    assert plugins[0]["name"] == "bmc-toolkit"
    assert plugins[0]["source"] == "./"


def test_marketplace_and_plugin_manifests_are_strict_json():
    """Both manifests parse with the standard library and contain nothing
    but plain data; a trailing comma or a comment would break the loader."""
    for name in ("marketplace.json", "plugin.json"):
        data = json.loads(_read(".claude-plugin", name))
        assert isinstance(data, dict), name

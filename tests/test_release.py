"""Release metadata: one version everywhere, README status, marketplace
manifest (release 1.0.0 change, AC-1 to AC-3). The expected version is the
package's own, so a bump that forgets pyproject.toml, plugin.json or the
README status line fails here (CONVENTIONS.md, Versions)."""

import json
import re
import tomllib
from pathlib import Path

import bmc_toolkit

ROOT = Path(__file__).resolve().parents[1]
VERSION = bmc_toolkit.__version__


def test_version_is_a_release_number():
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION), VERSION


def test_version_recorded_once_everywhere():
    """AC-1: the package, pyproject.toml and plugin.json agree."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    versions = {
        "bmc_toolkit.__version__": bmc_toolkit.__version__,
        "pyproject.toml": pyproject["project"]["version"],
        "plugin.json": plugin["version"],
    }
    assert versions == dict.fromkeys(versions, VERSION)


def test_readme_status_is_the_release():
    """AC-2: the status paragraph names the package version and README no
    longer calls the plugin a pre-release."""
    readme = (ROOT / "README.md").read_text("utf-8")
    assert f"**Status: {VERSION}.**" in readme
    assert "pre-release" not in readme.lower()
    assert "0.9.0" not in readme


def test_marketplace_manifest_has_a_description():
    """AC-3: marketplace.json carries the description that
    `claude plugin validate --strict` warns about when missing, and names
    this plugin."""
    manifest = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text("utf-8")
    )
    assert manifest["description"].strip()
    assert [p["name"] for p in manifest["plugins"]] == ["bmc-toolkit"]

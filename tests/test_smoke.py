"""Skeleton checks: the plugin is well-formed and the launcher runs."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bmc_toolkit import __version__  # noqa: E402
from bmc_toolkit.spec import cli  # noqa: E402

LAUNCHER = ROOT / "skills" / "bmc-spec" / "scripts" / "bmcspec.py"


def run_launcher(*args, env=None):
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        capture_output=True,
        text=True,
        errors="replace",
        env=env,
    )


def test_plugin_manifest_is_valid():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    assert manifest["name"] == "bmc-toolkit"
    assert manifest["version"] == __version__


def test_marketplace_points_at_this_repo():
    market = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text("utf-8")
    )
    entries = {p["name"]: p for p in market["plugins"]}
    assert entries["bmc-toolkit"]["source"] == "./"


def test_skill_frontmatter_names_the_skill():
    head = (ROOT / "skills" / "bmc-spec" / "SKILL.md").read_text("utf-8")
    assert head.startswith("---\n")
    assert "\nname: bmc-spec\n" in head


def test_hooks_file_is_valid_json():
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text("utf-8"))
    assert "SessionStart" in hooks["hooks"]


def test_launcher_help_runs_from_another_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, str(LAUNCHER), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert "library" in result.stdout


def test_library_defaults_to_home_dot_bmc_specs():
    assert cli.resolve_library(env={}) == (Path.home() / ".bmc-specs").resolve()


def test_library_env_override(tmp_path):
    assert cli.resolve_library(env={"BMC_SPEC_LIBRARY": str(tmp_path)}) == tmp_path


def test_library_env_blank_is_ignored():
    assert cli.resolve_library(env={"BMC_SPEC_LIBRARY": "  "}) == (
        Path.home() / ".bmc-specs"
    ).resolve()


def test_library_command_prints_override(tmp_path, monkeypatch):
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path))
    result = run_launcher("library")
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == tmp_path


def test_unknown_command_is_an_error():
    with pytest.raises(SystemExit) as exc:
        cli.main(["no-such-command"])
    assert exc.value.code != 0

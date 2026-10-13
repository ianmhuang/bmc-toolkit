"""Reviewer acceptance tests for AC-6 of the ``invocation`` command: it needs
no Library, no network and no third-party package, and leaves nothing on
disk.

Each test starts a fresh interpreter, the way a Session runs the helper, with
the Library and the home directory pointed into ``tmp_path``. What exists
there afterwards is what the command wrote.

On develop the subcommand does not exist and the launcher ends with exit 2
and nothing on stdout, so every test fails there.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "skills" / "bmc-spec" / "scripts" / "bmcspec.py"

FIELDS = [
    "Header:1=0x80",
    "PLDM Type:1=0x02",
    "Command Code:1=0x11",
    "sensorID:2=<sensor id>",
    "rearmEventState:1=0",
]
CLIENT_LINE = (
    "mctp-client eid <eid> type pldm data 80 02 11 <sensor id 0> <sensor id 1> 00"
)
TOOL_LINE = "pldmtool raw -m <eid> -d 0x80 0x02 0x11 <sensor id 0> <sensor id 1> 0x00"

# The entry point with every import outside the standard library and the
# package itself refused, and every way onto the network closed.
BARE = """
import socket
import sys


def refuse(*args, **kwargs):
    raise AssertionError("the network was used")


socket.socket.connect = refuse
socket.create_connection = refuse
socket.getaddrinfo = refuse


class StandardLibraryOnly:
    def find_spec(self, name, path=None, target=None):
        top = name.partition(".")[0]
        if top in sys.stdlib_module_names or top.startswith("_"):
            return None
        if top == "bmc_toolkit":
            return None
        raise ImportError("third-party package imported: " + name)


sys.meta_path.insert(0, StandardLibraryOnly())
sys.path.insert(0, sys.argv[1])

from bmc_toolkit.spec.cli import main

sys.exit(main(sys.argv[2:]))
"""


def _env(tmp_path: Path, library: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = dict(os.environ)
    env.pop("CLAUDE_PLUGIN_DATA", None)
    env.update(
        BMC_SPEC_LIBRARY=str(library),
        HOME=str(home),
        USERPROFILE=str(home),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONIOENCODING="utf-8",
    )
    return env


def _run(command: list[str], tmp_path: Path, library: Path):
    cwd = tmp_path / "cwd"
    cwd.mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, *command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_env(tmp_path, library),
        cwd=cwd,
    )


def _launch(tmp_path: Path, library: Path, *args: str):
    return _run([str(LAUNCHER), *args], tmp_path, library)


def _written(tmp_path: Path) -> list[str]:
    """Everything under ``tmp_path`` but the two directories the test made."""
    made = {"cwd", "home"}
    return sorted(
        str(path.relative_to(tmp_path))
        for path in tmp_path.rglob("*")
        if str(path.relative_to(tmp_path)) not in made
    )


def test_it_runs_with_a_library_that_does_not_exist_and_creates_nothing(tmp_path):
    library = tmp_path / "no-such-library"
    result = _launch(tmp_path, library, "invocation", "pldm", *FIELDS)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "bytes: 6"
    assert CLIENT_LINE in lines
    assert not library.exists()
    assert _written(tmp_path) == []


def test_it_prints_the_same_with_a_library_and_leaves_no_lock_in_it(tmp_path):
    missing = tmp_path / "no-such-library"
    without = _launch(tmp_path, missing, "invocation", "pldm", *FIELDS)
    assert without.returncode == 0, without.stdout + without.stderr

    library = tmp_path / "library"
    library.mkdir()
    # --wait 0: a command that needed a lock would not wait for one
    held = _launch(tmp_path, library, "--wait", "0", "invocation", "pldm", *FIELDS)
    assert held.returncode == 0, held.stdout + held.stderr
    assert held.stdout == without.stdout
    assert CLIENT_LINE in held.stdout.splitlines()
    assert list(library.iterdir()) == []
    assert _written(tmp_path) == ["library"]


def test_a_refused_call_needs_no_library_either(tmp_path):
    library = tmp_path / "no-such-library"
    result = _launch(tmp_path, library, "invocation", "pldm", "sensorID:2=0x10000")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "sensorID" in result.stdout + result.stderr
    assert "mctp-client" not in result.stdout
    assert "pldmtool" not in result.stdout
    assert not library.exists()
    assert _written(tmp_path) == []


def test_it_runs_without_third_party_packages_and_without_the_network(tmp_path):
    library = tmp_path / "no-such-library"
    result = _run(
        ["-c", BARE, str(ROOT), "invocation", "pldm", *FIELDS], tmp_path, library
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "bytes: 6"
    assert CLIENT_LINE in lines
    assert TOOL_LINE in lines
    assert not library.exists()
    assert _written(tmp_path) == []

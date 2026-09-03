"""Launcher for the bmc-spec helper CLI.

Runs from any working directory: puts the plugin root on sys.path so the
``bmc_toolkit`` package imports, and prepends the plugin's persistent data
directory (where the SessionStart hook installs third-party packages) when
Claude Code provides it.
"""

import os
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]

data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
if data_dir:
    sys.path.insert(0, str(Path(data_dir) / "site-packages"))
sys.path.insert(0, str(PLUGIN_ROOT))

from bmc_toolkit.spec.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

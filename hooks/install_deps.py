"""SessionStart hook: install third-party packages once per requirements change.

Claude Code replaces the plugin directory on every update but keeps
``$CLAUDE_PLUGIN_DATA``. Packages go to ``$CLAUDE_PLUGIN_DATA/site-packages``
and a marker file records the hash of the requirements that produced them, so
the hook is a no-op on every session where nothing changed. Without
``$CLAUDE_PLUGIN_DATA`` (a development checkout) the hook does nothing and
says so; install with ``pip install -r requirements.txt`` by hand.

Always exits 0: a failed install must not block the session, the launcher
reports the missing package when a command actually needs it.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = PLUGIN_ROOT / "requirements.txt"
MARKER_NAME = ".requirements.sha256"


def main() -> int:
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data_dir:
        print("bmc-toolkit: CLAUDE_PLUGIN_DATA not set; skipping dependency install")
        return 0
    if not REQUIREMENTS.is_file():
        return 0

    digest = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    target = Path(data_dir) / "site-packages"
    marker = target / MARKER_NAME
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == digest:
        return 0

    target.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--quiet",
        "--upgrade",
        "--target",
        str(target),
        "-r",
        str(REQUIREMENTS),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        print("bmc-toolkit: dependency install failed; run by hand:")
        print("  " + " ".join(cmd))
        print(result.stderr.strip()[-2000:])
        return 0
    marker.write_text(digest + "\n", encoding="utf-8", newline="")
    print(f"bmc-toolkit: dependencies installed into {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

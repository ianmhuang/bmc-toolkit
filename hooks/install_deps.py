"""SessionStart hook: install third-party packages once per requirements change.

Claude Code replaces the plugin directory on every update but keeps
``$CLAUDE_PLUGIN_DATA``. Packages go to ``$CLAUDE_PLUGIN_DATA/site-packages``
and a marker file records the hash of the requirements that produced them, so
the hook is a no-op on every session where nothing changed. Without
``$CLAUDE_PLUGIN_DATA`` (a development checkout) the hook does nothing and
says so; install with ``pip install -r requirements.txt`` by hand.

Two Sessions starting at once must not corrupt one another's install: pip
writes into ``site-packages.tmp-<pid>-<token>``, the marker is written
there, and the directory is renamed into place in one step. When another
Session's install landed first with the same marker, ours is discarded.

Always exits 0: a failed install must not block the session, the launcher
reports the missing package when a command actually needs it.
"""

import hashlib
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = PLUGIN_ROOT / "requirements.txt"
MARKER_NAME = ".requirements.sha256"
TARGET_NAME = "site-packages"


def marker_matches(target: Path, digest: str) -> bool:
    marker = target / MARKER_NAME
    try:
        return marker.read_text(encoding="utf-8").strip() == digest
    except OSError:
        return False


def install(target: Path, digest: str) -> tuple[bool, str]:
    """Install into a temp directory beside ``target`` and rename it into
    place; (ok, message)."""
    tmp = target.with_name(f"{target.name}.tmp-{os.getpid()}-{secrets.token_hex(4)}")
    tmp.mkdir(parents=True)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--quiet",
        "--upgrade",
        "--target",
        str(tmp),
        "-r",
        str(REQUIREMENTS),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if result.returncode != 0:
            return False, (
                "bmc-toolkit: dependency install failed; run by hand:\n  "
                + " ".join(cmd).replace(str(tmp), str(target))
                + "\n"
                + result.stderr.strip()[-2000:]
            )
        (tmp / MARKER_NAME).write_text(digest + "\n", encoding="utf-8", newline="")
        return publish(tmp, target, digest)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def publish(tmp: Path, target: Path, digest: str) -> tuple[bool, str]:
    """Rename ``tmp`` to ``target``. An older install is moved aside first;
    if another Session's current install appears meanwhile, keep theirs."""
    if target.exists() and not marker_matches(target, digest):
        old = target.with_name(
            f"{target.name}.old-{os.getpid()}-{secrets.token_hex(4)}"
        )
        try:
            os.replace(target, old)
        except OSError:
            pass  # someone else moved or replaced it; decided below
        else:
            shutil.rmtree(old, ignore_errors=True)
    try:
        os.replace(tmp, target)
    except OSError:
        if marker_matches(target, digest):
            return True, f"bmc-toolkit: dependencies already installed into {target}"
        return False, f"bmc-toolkit: could not move {tmp} into {target}"
    return True, f"bmc-toolkit: dependencies installed into {target}"


def main() -> int:
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data_dir:
        print("bmc-toolkit: CLAUDE_PLUGIN_DATA not set; skipping dependency install")
        return 0
    if not REQUIREMENTS.is_file():
        return 0

    digest = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    target = Path(data_dir) / TARGET_NAME
    if marker_matches(target, digest):
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    _, message = install(target, digest)
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())

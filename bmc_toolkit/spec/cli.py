"""Command-line entry point for the bmc-spec skill.

Standard library only. Subcommands that need third-party packages import
them lazily so ``--help`` and ``library`` work on a bare interpreter.
"""

import argparse
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from bmc_toolkit import __version__

ENV_LIBRARY = "BMC_SPEC_LIBRARY"
DEFAULT_LIBRARY_DIRNAME = ".bmc-specs"


def resolve_library(env: Mapping[str, str] | None = None) -> Path:
    """Return the Library root: ``$BMC_SPEC_LIBRARY`` or ``~/.bmc-specs``.

    The path is expanded and made absolute but not created.
    """
    env = os.environ if env is None else env
    override = env.get(ENV_LIBRARY, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / DEFAULT_LIBRARY_DIRNAME).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bmcspec",
        description="Helper CLI for the bmc-spec Claude Code skill.",
    )
    parser.add_argument(
        "--version", action="version", version=f"bmc-toolkit {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("library", help="print the Library path")
    return parser


def cmd_library(_args: argparse.Namespace) -> int:
    print(resolve_library())
    return 0


COMMANDS = {
    "library": cmd_library,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())

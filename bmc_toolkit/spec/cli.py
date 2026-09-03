"""Command-line entry point for the bmc-spec skill.

Exit codes: 0 done, 1 error (bad catalog, unreadable file), 2 the user must
act (unknown document or version, download impossible, bad arguments).
Standard library only; the HTTP client is created lazily by ``fetch``.
"""

import argparse
import sys
from pathlib import Path

from bmc_toolkit import __version__
from bmc_toolkit.spec import fetch as fetch_mod
from bmc_toolkit.spec.catalog import Catalog, CatalogError, Document, load_catalog
from bmc_toolkit.spec.library import (
    DEFAULT_LIBRARY_DIRNAME,
    ENV_LIBRARY,
    Library,
    now_iso,
    resolve_library,
    safe_name,
    sha256_of,
)

__all__ = [
    "DEFAULT_LIBRARY_DIRNAME",
    "ENV_LIBRARY",
    "build_parser",
    "main",
    "resolve_library",
]

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ACTION = 2

# Tests replace this to keep the network out.
CLIENT_FACTORY = fetch_mod.default_client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bmcspec",
        description="Helper CLI for the bmc-spec Claude Code skill.",
    )
    parser.add_argument(
        "--version", action="version", version=f"bmc-toolkit {__version__}"
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help="alternative Source Catalog file (default: the shipped one)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("library", help="print the Library path")

    p = sub.add_parser("catalog", help="list documents in the Source Catalog")
    p.add_argument("document", nargs="?", help="show one document with its versions")
    p.add_argument("--family", help="only documents of this family")

    p = sub.add_parser("fetch", help="download a document version into the Library")
    p.add_argument("document", nargs="?", help="document id, e.g. DSP0236")
    p.add_argument("--version", dest="doc_version", help="exact version string")
    p.add_argument("--wip", action="store_true", help="let a WIP version be latest")
    p.add_argument("--force", action="store_true", help="re-download if present")
    p.add_argument("--all", action="store_true", help="latest of every document")

    p = sub.add_parser("add", help="place a file you obtained yourself (Drop-in)")
    p.add_argument("file", type=Path)
    p.add_argument("--document", required=True, help="document id")
    p.add_argument("--version", dest="doc_version", required=True)

    sub.add_parser("scan", help="register files placed into the Library by hand")
    sub.add_parser("status", help="what the Library holds")
    return parser


def _load(args: argparse.Namespace) -> Catalog:
    return load_catalog(args.catalog)


def _announce_library(library: Library) -> None:
    if library.ensure():
        print(f"Library created at {library.root}")


def cmd_library(_args: argparse.Namespace) -> int:
    print(resolve_library())
    return EXIT_OK


def _doc_line(catalog: Catalog, doc: Document) -> str:
    latest = doc.latest()
    return "\t".join(
        [
            doc.family,
            doc.id,
            doc.access,
            doc.fetch,
            latest.version if latest else "-",
            doc.title,
        ]
    )


def cmd_catalog(args: argparse.Namespace) -> int:
    catalog = _load(args)
    if args.document:
        doc = catalog.get(args.document)
        if doc is None:
            print(f"unknown document '{args.document}'; run: bmcspec catalog")
            return EXIT_ACTION
        fam = catalog.families[doc.family]
        latest = doc.latest()
        print(f"document: {doc.id}")
        print(f"title: {doc.title}")
        print(f"family: {doc.family} ({fam.publisher})")
        print(f"access: {doc.access}")
        print(f"fetch: {doc.fetch}")
        print(f"latest: {latest.version if latest else '-'}")
        if doc.notes:
            print(f"notes: {doc.notes}")
        print("versions:")
        for v in sorted(doc.versions, key=lambda v: v.published, reverse=True):
            flag = "wip" if v.wip else "published"
            print(f"\t{v.version}\t{v.published}\t{v.type}\t{flag}\t{v.url or '-'}")
        return EXIT_OK
    docs = catalog.by_family(args.family) if args.family else catalog.documents
    if args.family and args.family not in catalog.families:
        print(f"unknown family '{args.family}'")
        return EXIT_ACTION
    for doc in docs:
        print(_doc_line(catalog, doc))
    return EXIT_OK


def _resolve_version(doc: Document, requested: str | None, wip: bool):
    if requested:
        ver = doc.find_version(requested)
        if ver is None:
            known = ", ".join(v.version for v in doc.versions)
            return None, (
                f"{doc.id}: unknown version '{requested}'. Known: {known}.\n"
                f"If you have the file, place it under "
                f"specs/{doc.family}/{doc.id}/{safe_name(requested)}/ in the "
                f"Library and run: bmcspec scan"
            )
        return ver, ""
    ver = doc.latest(include_wip=wip)
    if ver is None:
        return None, f"{doc.id}: no published version (use --wip)"
    return ver, ""


def _report(outcome: fetch_mod.Outcome) -> None:
    for a in outcome.attempts:
        print(f"  {outcome.document} {outcome.version}: {a}")
    if outcome.status == "fetched":
        print(f"fetched {outcome.document} {outcome.version} via {outcome.method}")
    elif outcome.status == "skipped":
        print(f"skipped {outcome.document} {outcome.version}: {outcome.message}")
    else:
        print(f"failed {outcome.document} {outcome.version}")
        print(outcome.message)


def cmd_fetch(args: argparse.Namespace) -> int:
    catalog = _load(args)
    library = Library(resolve_library())
    if args.all == bool(args.document):
        print("give a document id or --all (not both)")
        return EXIT_ACTION
    _announce_library(library)
    client = CLIENT_FACTORY()

    if not args.all:
        doc = catalog.get(args.document)
        if doc is None:
            print(f"unknown document '{args.document}'; run: bmcspec catalog")
            return EXIT_ACTION
        ver, problem = _resolve_version(doc, args.doc_version, args.wip)
        if ver is None:
            print(problem)
            return EXIT_ACTION
        outcome = fetch_mod.fetch_version(
            library, doc, ver, force=args.force, client=client
        )
        _report(outcome)
        return EXIT_OK if outcome.status != "failed" else EXIT_ACTION

    counts = {"fetched": 0, "skipped": 0, "failed": 0}
    for doc in catalog.documents:
        if doc.fetch == "manual":
            continue
        ver = doc.latest(include_wip=args.wip)
        if ver is None:
            continue
        outcome = fetch_mod.fetch_version(
            library, doc, ver, force=args.force, client=client
        )
        _report(outcome)
        counts[outcome.status] += 1
    print(
        f"summary: fetched {counts['fetched']}, skipped {counts['skipped']}, "
        f"failed {counts['failed']}"
    )
    return EXIT_OK if counts["failed"] == 0 else EXIT_ACTION


def cmd_add(args: argparse.Namespace) -> int:
    catalog = _load(args)
    source: Path = args.file
    if not source.is_file():
        print(f"file not found: {source}")
        return EXIT_ACTION
    ext = source.suffix.lower().lstrip(".")
    if ext not in ("pdf", "zip"):
        print(f"unsupported file type '.{ext}': expected .pdf or .zip")
        return EXIT_ACTION
    doc = catalog.get(args.document)
    if doc is None:
        print(f"unknown document '{args.document}'; run: bmcspec catalog")
        return EXIT_ACTION
    library = Library(resolve_library())
    _announce_library(library)
    vdir = library.add_dropin(source, doc.family, doc.id, args.doc_version, ext)
    print(f"added {doc.id} {args.doc_version} as Drop-in at {vdir}")
    return EXIT_OK


def cmd_scan(args: argparse.Namespace) -> int:
    catalog = _load(args)
    library = Library(resolve_library())
    if not library.specs.is_dir():
        print(f"Library has no specs/ directory yet: {library.root}")
        return EXIT_OK
    registered = 0
    problems = 0
    for vdir, original in library.unregistered():
        family_dir = vdir.parents[1].name
        doc_dir = vdir.parent.name
        ext = original.suffix.lower().lstrip(".")
        doc = catalog.get(doc_dir)
        if ext not in ("pdf", "zip"):
            print(f"skipped {vdir}: unsupported file type '{original.name}'")
            problems += 1
            continue
        if doc is not None and doc.family != family_dir:
            print(
                f"skipped {vdir}: document {doc.id} belongs to family "
                f"'{doc.family}', not '{family_dir}'"
            )
            problems += 1
            continue
        version = vdir.name
        doc_id = doc_dir
        family = family_dir
        if doc is not None:
            doc_id = doc.id
            family = doc.family
            for v in doc.versions:
                if safe_name(v.version) == vdir.name:
                    version = v.version
                    break
        library.write_meta(
            vdir,
            {
                "family": family,
                "document": doc_id,
                "version": version,
                "file": original.name,
                "url": None,
                "fetch_method": "dropin",
                "sha256": sha256_of(original),
                "size": original.stat().st_size,
                "fetched_at": now_iso(),
                "dropin": True,
                "catalog_known": doc is not None,
            },
        )
        note = "" if doc is not None else " (not in catalog)"
        print(f"registered {doc_id} {version} as Drop-in{note}")
        registered += 1
    print(f"scan: registered {registered}, skipped {problems}")
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    library = Library(resolve_library())
    print(f"library: {library.root}")
    holdings = list(library.holdings())
    if not holdings:
        print("(empty)")
        return EXIT_OK
    for h in holdings:
        flag = "dropin" if h.dropin else h.meta.get("fetch_method", "")
        print(
            f"{h.family}\t{h.document}\t{h.version}\t{flag}\t{h.meta.get('size', '?')}"
        )
    return EXIT_OK


COMMANDS = {
    "library": cmd_library,
    "catalog": cmd_catalog,
    "fetch": cmd_fetch,
    "add": cmd_add,
    "scan": cmd_scan,
    "status": cmd_status,
}


def _utf8_stdout() -> None:
    """Print UTF-8 whatever the console code page; titles carry ® and ™."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except CatalogError as exc:
        print(f"catalog error: {exc}")
        return EXIT_ERROR
    except OSError as exc:
        print(f"error: {exc}")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())

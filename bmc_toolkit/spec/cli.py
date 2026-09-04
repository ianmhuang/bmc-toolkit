"""Command-line entry point for the bmc-spec skill.

Exit codes: 0 done, 1 error (bad catalog, unreadable file), 2 the user must
act (unknown document or version, download impossible, bad arguments).
Standard library only; the HTTP client is created lazily by ``fetch``.
"""

import argparse
import re
import sys
from pathlib import Path

from bmc_toolkit import __version__
from bmc_toolkit.spec import bundle as bundle_mod
from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec import extract as extract_mod
from bmc_toolkit.spec import fetch as fetch_mod
from bmc_toolkit.spec import freshness as fresh_mod
from bmc_toolkit.spec import listing as listing_mod
from bmc_toolkit.spec import refresh as refresh_mod
from bmc_toolkit.spec import render as render_mod
from bmc_toolkit.spec import search as search_mod
from bmc_toolkit.spec import support as support_mod
from bmc_toolkit.spec import tables as tables_mod
from bmc_toolkit.spec.catalog import (
    DEFAULT_CATALOG,
    Catalog,
    CatalogError,
    Document,
    Repo,
    load_catalog,
)
from bmc_toolkit.spec.library import (
    DEFAULT_LIBRARY_DIRNAME,
    ENV_LIBRARY,
    Library,
    LibraryError,
    file_matches_type,
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

MAX_HITS = 50  # find: hits printed per call unless --max says otherwise
MAX_PAGES = 10  # page: pages printed per call unless --max-pages says otherwise
OCP_NOTE_CHARS = 60  # check: how much of a wiki row's description is printed

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
    p.add_argument(
        "--table",
        action="store_true",
        help="print the Support Level table (Markdown) instead of the list",
    )
    p.add_argument(
        "--golden",
        type=Path,
        help="Golden Questions file whose Document column marks Verified rows",
    )

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
    p.add_argument(
        "--force", action="store_true", help="replace a version already present"
    )

    sub.add_parser("scan", help="register files placed into the Library by hand")
    sub.add_parser("status", help="what the Library holds")

    p = sub.add_parser(
        "check", help="ask the publishers whether the catalog is behind (no download)"
    )
    p.add_argument("document", nargs="?", help="one document id; none checks all")

    p = sub.add_parser(
        "refresh",
        help="maintainer: versions the publishers list that the catalog lacks",
    )
    p.add_argument("document", nargs="?", help="one document id; none does all")
    p.add_argument(
        "--write", action="store_true", help="append the new entries to the catalog"
    )

    p = sub.add_parser("extract", help="turn a PDF in the Library into text")
    p.add_argument("document", nargs="?", help="document id")
    p.add_argument("--version", dest="doc_version", help="exact version string")
    p.add_argument("--force", action="store_true", help="re-extract if present")
    p.add_argument("--all", action="store_true", help="every PDF in the Library")

    p = sub.add_parser("find", help="search the Extract of a document")
    p.add_argument("document", help="document id")
    p.add_argument("pattern", help="text to look for (a literal unless --regex)")
    p.add_argument("--version", dest="doc_version", help="exact version string")
    p.add_argument(
        "--regex", action="store_true", help="pattern is a regular expression"
    )
    p.add_argument("--case", action="store_true", help="match case")
    p.add_argument("--context", type=int, default=0, help="lines around each hit")
    p.add_argument(
        "--max",
        dest="max_hits",
        type=int,
        default=MAX_HITS,
        help="hits to print; 0 = all",
    )
    p.add_argument(
        "--only", action="store_true", help="skip the documents searched with this one"
    )

    p = sub.add_parser("section", help="find sections in a document's Outline")
    p.add_argument("document", help="document id")
    p.add_argument("query", help="a section number prefix or words of the title")
    p.add_argument("--version", dest="doc_version", help="exact version string")

    p = sub.add_parser("page", help="print pages of a document's Extract")
    p.add_argument("document", help="document id")
    p.add_argument("page", nargs="?", type=int, help="physical page (1-based)")
    p.add_argument("--to", type=int, help="last page of a range")
    p.add_argument("--section", help="the pages of the first section matching this")
    p.add_argument("--version", dest="doc_version", help="exact version string")
    p.add_argument("--max-pages", type=int, default=MAX_PAGES, help="pages per call")

    p = sub.add_parser("render", help="render a page of the original to PNG")
    p.add_argument("document", help="document id")
    p.add_argument("--page", type=int, required=True, help="physical page (1-based)")
    p.add_argument("--version", dest="doc_version", help="exact version string")
    p.add_argument("--scale", type=float, default=render_mod.DEFAULT_SCALE)
    p.add_argument("--force", action="store_true", help="re-render if present")

    p = sub.add_parser(
        "schema", help="Redfish resources, properties and enum values of a bundle"
    )
    p.add_argument("document", help="document id of a schema bundle")
    p.add_argument("resource", nargs="?", help="resource name (Chassis); none lists")
    p.add_argument("--property", help="one property of the resource")
    p.add_argument("--definition", help="one named definition of the resource's file")
    p.add_argument("--version", dest="doc_version", help="exact version string")

    p = sub.add_parser("repos", help="list the code repositories and held Code Trees")
    p.add_argument("--topic", help="only repositories about this topic")
    p.add_argument(
        "--search", metavar="PATTERN", help="GitHub code search over openbmc via gh"
    )

    p = sub.add_parser("clone", help="bring a repository into the Library")
    p.add_argument("repo", help="repository id (see repos)")
    p.add_argument("--ref", help="a branch, tag or commit of the repository")
    p.add_argument("--release", help="an OpenBMC release tag or branch (2.18.0)")
    p.add_argument("--force", action="store_true", help="resolve a moving name again")

    p = sub.add_parser("grep", help="search a held Code Tree with git grep")
    p.add_argument("repo", help="repository id")
    p.add_argument("pattern", help="text to look for (fixed string unless --regex)")
    p.add_argument("--ref", help="the Code Tree reached by this ref")
    p.add_argument("--release", help="the Code Tree pinned by this release")
    p.add_argument("--regex", action="store_true", help="pattern is an extended regex")
    p.add_argument("--glob", help="only paths matching this git pathspec")
    p.add_argument("--context", type=int, default=0, help="lines around each hit")
    p.add_argument(
        "--max", dest="max_hits", type=int, default=MAX_HITS, help="hits; 0 = all"
    )

    p = sub.add_parser("code", help="print a file of a held Code Tree with a cite")
    p.add_argument("repo", help="repository id")
    p.add_argument("path", help="path inside the repository")
    p.add_argument("--lines", help="A-B, required for files over 200 lines")
    p.add_argument("--ref", help="the Code Tree reached by this ref")
    p.add_argument("--release", help="the Code Tree pinned by this release")

    p = sub.add_parser("prune", help="remove superseded Code Trees and leftovers")
    p.add_argument(
        "--yes", action="store_true", help="really remove (the default only lists)"
    )

    p = sub.add_parser("table", help="print the ruled tables on a page, whole")
    p.add_argument("document", help="document id")
    p.add_argument("--page", type=int, required=True, help="physical page (1-based)")
    p.add_argument("--version", dest="doc_version", help="exact version string")
    p.add_argument(
        "--index", type=int, help="only the K-th table on the page (1-based)"
    )
    p.add_argument(
        "--force", action="store_true", help="read the PDF again instead of tables.json"
    )
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
            ";".join(v.version for v in doc.versions),
        ]
    )


def cmd_catalog(args: argparse.Namespace) -> int:
    catalog = _load(args)
    if args.table:
        if args.document or args.family:
            print("--table prints every document; drop the document id or --family")
            return EXIT_ACTION
        return _catalog_table(catalog, args.golden)
    if args.golden:
        print("--golden goes with --table")
        return EXIT_ACTION
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
        print(f"listing: {doc.listing or '- (hand-maintained)'}")
        if doc.notes:
            print(f"notes: {doc.notes}")
        if doc.limits:
            print(f"limits: {doc.limits}")
        if not doc.versions:
            print(
                "versions: (none listed; add any version with: bmcspec add FILE "
                f"--document {doc.id} --version V)"
            )
            return EXIT_OK
        print("versions:")
        for v in sorted(doc.versions, key=lambda v: v.published, reverse=True):
            flag = "wip" if v.wip else "published"
            print(
                f"\t{v.version}\t{v.published}\t{v.type}\t{flag}\t{v.url or '-'}"
                f"\t{v.access}"
            )
        return EXIT_OK
    docs = catalog.by_family(args.family) if args.family else catalog.documents
    if args.family and args.family not in catalog.families:
        print(f"unknown family '{args.family}'")
        return EXIT_ACTION
    for doc in docs:
        print(_doc_line(catalog, doc))
    return EXIT_OK


def _catalog_table(catalog: Catalog, golden: Path | None) -> int:
    """The Support Level table; Verified from the Golden Questions file."""
    verified: support_mod.Verified = {}
    if golden is not None:
        try:
            verified, problems = support_mod.read_golden(golden, catalog)
        except (OSError, UnicodeDecodeError) as exc:
            print(f"cannot read {golden}: {exc}")
            return EXIT_ERROR
        for problem in problems:
            print(f"{golden}: {problem}", file=sys.stderr)
    for line in support_mod.support_table(catalog, verified):
        print(line)
    return EXIT_OK


def _gated_message(library: Library, doc: Document, ver) -> str:
    """Why ``fetch`` will not download this version, and what to do."""
    lines = [
        f"{doc.id} {ver.version} is {ver.access}: the tool does not download it.",
        fetch_mod.manual_instruction(library, doc, ver),
    ]
    newest = doc.newest_open()
    if newest is not None:
        lines.append(
            f"newest open version: {newest.version}; fetch it with "
            f"--version {_shell_quote(newest.version)}"
        )
    else:
        lines.append("no open version is listed")
    return "\n".join(lines)


def _shell_quote(value: str) -> str:
    return f'"{value}"' if " " in value else value


def _held(library: Library, doc: Document, ver, force: bool) -> bool:
    """True when the version is already in the Library (a Drop-in, for a
    gated one) and ``fetch`` will report it skipped rather than refuse it;
    ``--force`` asks for a download, which a gated version cannot have."""
    return not force and library.find(doc.id, ver.version) is not None


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
    if args.all and args.doc_version:
        print("--version applies to one document; drop it with --all")
        return EXIT_ACTION

    if not args.all:
        doc = catalog.get(args.document)
        if doc is None:
            print(f"unknown document '{args.document}'; run: bmcspec catalog")
            return EXIT_ACTION
        if doc.fetch == "manual" and not doc.versions:
            # No version is listed at all: nothing to resolve, nothing to
            # download; the user places the file they obtained.
            print(
                f"{doc.id} is {doc.access} and lists no versions: the tool does "
                f"not download it. Register the file you obtained with: "
                f"bmcspec add FILE --document {doc.id} --version V"
            )
            return EXIT_ACTION
        ver, problem = _resolve_version(doc, args.doc_version, args.wip)
        if ver is None:
            print(problem)
            return EXIT_ACTION
        if not ver.open and not _held(library, doc, ver, args.force):
            print(_gated_message(library, doc, ver))
            return EXIT_ACTION
        _announce_library(library)
        client = CLIENT_FACTORY()
        outcome = fetch_mod.fetch_version(
            library, doc, ver, force=args.force, client=client
        )
        _report(outcome)
        _freshness_notes(catalog, library, [doc.id])
        return EXIT_OK if outcome.status != "failed" else EXIT_ACTION

    todo = []
    gated_notes = []
    for doc in catalog.documents:
        if doc.fetch == "manual":
            continue
        ver = doc.latest(include_wip=args.wip)
        if (
            ver is not None
            and not ver.open
            and not _held(library, doc, ver, args.force)
        ):
            # The latest is gated: take the newest open version instead and
            # say so once; a document with no open version is left alone. A
            # gated latest the user added by hand is held and reported as
            # skipped, except under --force, which re-downloads the open
            # versions and leaves the Drop-in alone (it has no URL to fetch).
            newest = doc.newest_open()
            gated_notes.append(
                f"note: {doc.id} latest {ver.version} is {ver.access}; "
                + (
                    f"fetching {newest.version} instead"
                    if newest is not None
                    else "no open version is listed, nothing fetched"
                )
            )
            ver = newest
        if ver is not None:
            todo.append((doc, ver))
    counts = {"fetched": 0, "skipped": 0, "failed": 0}
    if todo:
        _announce_library(library)
        client = CLIENT_FACTORY()
    for note in gated_notes:
        print(note)
    for doc, ver in todo:
        outcome = fetch_mod.fetch_version(
            library, doc, ver, force=args.force, client=client
        )
        _report(outcome)
        counts[outcome.status] += 1
    _freshness_notes(catalog, library, [doc.id for doc, _ in todo])
    print(
        f"summary: fetched {counts['fetched']}, skipped {counts['skipped']}, "
        f"failed {counts['failed']}"
    )
    return EXIT_OK if counts["failed"] == 0 else EXIT_ACTION


def _freshness_notes(catalog: Catalog, library: Library, doc_ids: list[str]) -> None:
    """Remind the user when documents have not been checked against their
    publishers lately: one line for a single document, one summary line
    for several; each document is reminded about once, until the next
    check. Reads the Library and writes freshness.json, never the network."""
    if not doc_ids:
        return
    try:
        max_age = fresh_mod.max_age_days(library.root)
    except fresh_mod.FreshnessError as exc:
        print(f"note: {exc}")
        return
    state = fresh_mod.Freshness(library.root)
    due = state.due_documents(catalog, doc_ids, max_age)
    if not due:
        return
    if len(doc_ids) == 1:
        print(state.note_for(due[0], max_age))
    else:
        print(
            f"note: {len(due)} of these documents have not been checked against "
            f"their publishers in the last {max_age} days; run: bmcspec check"
        )
    state.mark_reminded([doc.id for doc in due])
    try:
        state.save()
    except OSError:
        pass  # the reminder repeats next time; nothing else is lost


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
    if not file_matches_type(source, ext):
        print(f"{source} is not a {ext} (wrong leading bytes); not added")
        return EXIT_ACTION
    doc = catalog.get(args.document)
    if doc is None:
        print(f"unknown document '{args.document}'; run: bmcspec catalog")
        return EXIT_ACTION
    library = Library(resolve_library())
    existing = library.find(doc.id, args.doc_version)
    if existing is not None and not args.force:
        origin = "Drop-in" if existing.dropin else existing.meta.get("url", "?")
        print(
            f"{doc.id} {args.doc_version} is already in the Library at "
            f"{existing.path} (from {origin}); use --force to replace it"
        )
        return EXIT_ACTION
    _announce_library(library)
    vdir = library.add_dropin(source, doc.family, doc.id, args.doc_version, ext)
    verb = "replaced" if existing is not None else "added"
    print(f"{verb} {doc.id} {args.doc_version} as Drop-in at {vdir}")
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
        if not file_matches_type(original, ext):
            print(
                f"skipped {vdir}: '{original.name}' is not a {ext} "
                "(wrong leading bytes)"
            )
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
        em = h.extract_meta
        extracted = "-"
        if em:
            wanted = extract_mod.EXTRACTOR_VERSION
            if em.get("kind") == "schemas":
                wanted = bundle_mod.BUNDLE_VERSION
            current = em.get("extractor_version") == wanted
            extracted = "extracted" if current else "stale"
        outline = em.get("outline_source", "-") if em else "-"
        size = h.meta.get("size", "?")
        print(
            f"{h.family}\t{h.document}\t{h.version}\t{flag}\t{size}"
            f"\t{extracted}\t{outline}"
        )
    try:
        catalog = _load(args)
    except CatalogError as exc:
        print(f"note: freshness not checked, the catalog does not load: {exc}")
        return EXIT_OK
    _freshness_notes(catalog, library, sorted({h.document for h in holdings}))
    return EXIT_OK


# ---------------------------------------------------------- freshness


def _checkable(catalog: Catalog, requested: str | None):
    """(documents to check, exit code): one named document, or every one
    with a listing; a message and exit 2 when the request cannot be met."""
    if requested:
        doc = catalog.get(requested)
        if doc is None:
            print(f"unknown document '{requested}'; run: bmcspec catalog")
            return [], EXIT_ACTION
        if not doc.listing:
            print(
                f"{doc.id} has no publisher listing; its versions are maintained "
                f"by hand in the catalog"
            )
            return [], EXIT_ACTION
        return [doc], EXIT_OK
    return [d for d in catalog.documents if d.listing], EXIT_OK


def _seen_line(doc: Document, seen: listing_mod.Seen) -> str:
    when = f" ({seen.published})" if seen.published else ""
    if doc.listing_source == "ocp":
        link = seen.url or "no link"
        note = seen.note[:OCP_NOTE_CHARS].rstrip()
        if len(seen.note) > OCP_NOTE_CHARS:
            note += "..."
        note = f" [{note}]" if note else ""
        return f"{seen.version}{when} {link} (URL to confirm by hand){note}"
    note = f" [{seen.note}]" if seen.note else ""
    return f"{seen.version}{when} {seen.url}{note}"


def cmd_check(args: argparse.Namespace) -> int:
    catalog = _load(args)
    library = Library(resolve_library())
    docs, code = _checkable(catalog, args.document)
    if code != EXIT_OK:
        return code
    state = fresh_mod.Freshness(library.root)
    listings = listing_mod.Listings(CLIENT_FACTORY())
    counts = {"current": 0, "newer": 0, "unreachable": 0}
    for doc in docs:
        check = fresh_mod.check_document(doc, listings)
        state.record(check)
        counts[check.status] += 1
        if check.status == "current":
            print(f"current {doc.id} {check.catalog_latest}")
        elif check.status == "unreachable":
            print(f"unreachable {doc.id}: {check.problem}")
        else:
            listed = "; ".join(_seen_line(doc, s) for s in check.newer)
            print(
                f"newer {doc.id}: catalog latest {check.catalog_latest}, "
                f"{fresh_mod.publisher_name(doc)} lists {listed}"
            )
    # A manual document with a listing was checked above like any other;
    # the manual line is for those nobody can check.
    unchecked = [
        d.id for d in catalog.documents if not d.listing and d.fetch != "manual"
    ]
    manual = [d for d in catalog.documents if d.fetch == "manual" and not d.listing]
    if not args.document and unchecked:
        print(f"unchecked: {', '.join(unchecked)} (no publisher listing)")
    if not args.document and manual:
        listed = ", ".join(f"{d.id} ({d.access})" for d in manual)
        print(f"unchecked (manual): {listed} (never fetched by the tool)")
    unchecked += [d.id for d in manual]
    if not args.document:
        _check_release(catalog, library, state)
    state.save()
    if counts["newer"]:
        print(
            "nothing was downloaded: a newer version enters the Library only "
            "after the catalog lists it (bmcspec refresh, or a pull request) "
            "or as a Drop-in"
        )
    print(
        f"summary: current {counts['current']}, newer {counts['newer']}, "
        f"unreachable {counts['unreachable']}"
        + (f", unchecked {len(unchecked)}" if not args.document else "")
    )
    return EXIT_OK


def _check_release(catalog: Catalog, library: Library, state) -> None:
    """The OpenBMC release line of ``check``, when config.toml pins one."""
    try:
        config = code_mod.load_config(library.root)
    except code_mod.CodeError as exc:
        print(f"unreachable release: {exc}")
        return
    if not config.release:
        return
    source = catalog.get_repo(code_mod.OPENBMC_REPO)
    if source is None:
        print(f"unreachable release: the catalog has no '{code_mod.OPENBMC_REPO}'")
        return
    try:
        newest = fresh_mod.newest_release_tag(source.url)
    except code_mod.CodeError as exc:
        print(f"unreachable release: {exc}")
        state.record_release(config.release, None, str(exc))
        return
    state.record_release(config.release, newest, "")
    head = (
        f"release: {config.release} (config.toml); newest openbmc tag {newest or '-'}"
    )
    if newest is None:
        print(f"{head} (no X.Y.Z tag found)")
        return
    verdict = fresh_mod.release_is_newer(config.release, newest)
    if verdict is None:
        print(f"{head} ({config.release} is a branch, not compared)")
    elif verdict:
        print(f"{head} -> newer")
    else:
        print(f"{head} -> {config.release} is the newest")


def cmd_refresh(args: argparse.Namespace) -> int:
    catalog = _load(args)
    path = args.catalog or DEFAULT_CATALOG
    docs, code = _checkable(catalog, args.document)
    if code != EXIT_OK:
        return code
    listings = listing_mod.Listings(CLIENT_FACTORY())
    counts = {"add": 0, "confirm": 0, "changed": 0, "unreachable": 0}
    written = 0
    for doc in docs:
        found = refresh_mod.proposals(doc, listings)
        for prop in found:
            counts[prop.kind] += 1
            if prop.kind == "unreachable":
                print(f"unreachable {doc.id}: {prop.problem}")
            else:
                line = f"{prop.kind} {doc.id} {_seen_line(doc, prop.seen)}"
                if prop.why and doc.listing_source != "ocp":
                    line += f" ({prop.why})"
                print(line)
        to_write = [p.seen for p in found if p.writable]
        if args.write and to_write:
            try:
                refresh_mod.append_versions(path, doc.id, to_write)
            except refresh_mod.RefreshError as exc:
                print(f"cannot write {doc.id}: {exc}")
                return EXIT_ERROR
            written += len(to_write)
            print(f"wrote {len(to_write)} version(s) of {doc.id} to {path}")
    print(
        f"summary: add {counts['add']}, confirm {counts['confirm']}, "
        f"changed {counts['changed']}, unreachable {counts['unreachable']}"
        + (f", written {written}" if args.write else " (dry run; --write adds them)")
    )
    return EXIT_OK


def _extract_one(holding, force: bool) -> str:
    """Extract one holding; returns extracted | skipped | failed."""
    original = holding.original
    label = f"{holding.document} {holding.version}"
    if not original.is_file():
        print(f"failed {label}: {original} is missing")
        return "failed"
    if original.suffix.lower() == ".zip":
        return _unpack_one(holding, force, label)
    if original.suffix.lower() != ".pdf":
        print(f"skipped {label}: {original.name} is neither a PDF nor a ZIP")
        return "skipped"
    if not force and extract_mod.is_current(holding.path):
        print(f"skipped {label}: already extracted")
        return "skipped"
    try:
        result = extract_mod.extract_pdf(original)
    except ImportError as exc:
        print(f"failed {label}: {exc}; run: pip install -r requirements.txt")
        return "failed"
    except Exception as exc:  # noqa: BLE001 - a broken PDF must not stop --all
        print(f"failed {label}: {type(exc).__name__}: {exc}")
        return "failed"
    extract_mod.write_result(holding.path, result)
    meta = result.to_meta()
    numbers = ""
    if meta["line_numbers"]:
        numbers = f", line numbers on {meta['line_numbered_pages']} pages"
    figures = f", figures on {meta['figure_pages']} pages"
    if meta["figure_errors"]:
        figures += f" (figure pass failed on {meta['figure_errors']} pages)"
    print(
        f"extracted {label}: {meta['pages']} pages in {meta['seconds']}s, "
        f"outline {meta['outline_source']} ({meta['outline_entries']} entries)"
        f"{numbers}{figures}"
    )
    return "extracted"


def _unpack_one(holding, force: bool, label: str) -> str:
    """Unpack a schema bundle; returns extracted | skipped | failed."""
    if not force and bundle_mod.is_current(holding.path):
        print(f"skipped {label}: already extracted")
        return "skipped"
    try:
        result = bundle_mod.unpack(holding.original, holding.path)
    except bundle_mod.NoSchemas as exc:
        print(f"skipped {label}: {exc} (registries and profiles come later)")
        return "skipped"
    except bundle_mod.BundleError as exc:
        print(f"failed {label}: {exc}")
        return "failed"
    except OSError as exc:  # a write the platform refused must not stop --all
        print(f"failed {label}: cannot write schemas: {exc}")
        return "failed"
    refused = f", {result.refused} unsafe paths refused" if result.refused else ""
    if result.duplicates:
        refused += f", {result.duplicates} duplicate names dropped"
    print(
        f"extracted {label}: {result.files} schema files, {result.resources} "
        f"resources in {result.seconds:.2f}s{refused}"
    )
    return "extracted"


def _latest_held(doc, held):
    """The newest held version: the catalog's latest if held, else the held
    version the catalog dates newest, else the most recently fetched."""
    if not held:
        return None
    if doc is not None:
        latest = doc.latest()
        if latest is not None:
            for h in held:
                if h.version == latest.version:
                    return h
        dated = {v.version: v.published for v in doc.versions}
        known = [h for h in held if h.version in dated]
        if known:
            return max(known, key=lambda h: dated[h.version])
    return max(held, key=lambda h: h.meta.get("fetched_at", ""))


def cmd_extract(args: argparse.Namespace) -> int:
    library = Library(resolve_library())
    if args.all == bool(args.document):
        print("give a document id or --all (not both)")
        return EXIT_ACTION
    if args.all and args.doc_version:
        print("--version applies to one document; drop it with --all")
        return EXIT_ACTION
    if args.all:
        counts = {"extracted": 0, "skipped": 0, "failed": 0}
        for h in library.holdings():
            counts[_extract_one(h, args.force)] += 1
        print(
            f"summary: extracted {counts['extracted']}, skipped {counts['skipped']}, "
            f"failed {counts['failed']}"
        )
        return EXIT_OK if counts["failed"] == 0 else EXIT_ACTION
    catalog = _load(args)
    doc = catalog.get(args.document)
    doc_id = doc.id if doc else args.document
    held = [h for h in library.holdings() if h.document.lower() == doc_id.lower()]
    if args.doc_version:
        holding = next((h for h in held if h.version == args.doc_version), None)
        wanted = args.doc_version
    else:
        holding = _latest_held(doc, held)
        wanted = "latest"
    if holding is None:
        print(f"{doc_id} {wanted} is not in the Library; run: bmcspec fetch {doc_id}")
        return EXIT_ACTION
    outcome = _extract_one(holding, args.force)
    return EXIT_OK if outcome != "failed" else EXIT_ACTION


# ------------------------------------------------------------ reading


def _held_version(catalog: Catalog, library: Library, doc_id: str, requested):
    """(holding, document, problem): the held version to read, or why not.

    ``holding`` is None when ``problem`` (an exit-2 message) is set.
    """
    doc = catalog.get(doc_id)
    name = doc.id if doc else doc_id
    held = [h for h in library.holdings() if h.document.lower() == name.lower()]
    if not held:
        return None, doc, f"{name} is not in the Library; run: bmcspec fetch {name}"
    if requested:
        holding = next((h for h in held if h.version == requested), None)
        if holding is None:
            versions = ", ".join(h.version for h in held)
            return (
                None,
                doc,
                f"{name} {requested} is not in the Library; held: {versions}",
            )
        return holding, doc, ""
    return _latest_held(doc, held), doc, ""


def _unreadable(holding) -> str:
    """Why the holding cannot be searched ('' when it can)."""
    label = f"{holding.document} {holding.version}"
    ext = holding.original.suffix.lower().lstrip(".")
    if ext != "pdf":
        return (
            f"{label} is a {ext} bundle; its schemas are read with: "
            f"bmcspec schema {holding.document}"
        )
    if not extract_mod.is_current(holding.path):
        return (
            f"{label} is not extracted, or was extracted by an older version of "
            f'the extractor; run: bmcspec extract {holding.document} --version "'
            f'{holding.version}"'
        )
    return ""


def _open_version(args: argparse.Namespace):
    """(Version, document, exit code): a loaded version or the code to return."""
    catalog = _load(args)
    library = Library(resolve_library())
    holding, doc, problem = _held_version(
        catalog, library, args.document, args.doc_version
    )
    if holding is None:
        print(problem)
        return None, doc, EXIT_ACTION
    problem = _unreadable(holding)
    if problem:
        print(problem)
        return None, doc, EXIT_ACTION
    try:
        return search_mod.load_version(holding), doc, EXIT_OK
    except search_mod.SearchError as exc:
        print(f"cannot read {holding.document} {holding.version}: {exc}")
        return None, doc, EXIT_ERROR


def _hit_line(hit: search_mod.Hit, document: str) -> str:
    where = f"{document} p.{hit.page}"
    if hit.number is not None:
        where += f" line {hit.number}"
    section = hit.section.label if hit.section else "-"
    mark = "[figure] " if hit.figure else ""
    return f"{where} | {section} | {mark}{hit.text.strip()}"


def _context_lines(version: search_mod.Version, hit: search_mod.Hit, n: int):
    lines = version.lines(hit.page)
    for index in range(max(0, hit.index - n), min(len(lines), hit.index + n + 1)):
        if index == hit.index:
            continue
        number = version.line_number(hit.page, index)
        tag = f"line {number}" if number is not None else f"row {index}"
        yield f"    {tag}: {lines[index]}"


def cmd_find(args: argparse.Namespace) -> int:
    version, doc, code = _open_version(args)
    if version is None:
        return code
    targets: list[search_mod.Version] = []
    if doc is not None and doc.searched_with and not args.only:
        catalog = _load(args)
        library = Library(resolve_library())
        for other in doc.searched_with:
            holding, _, problem = _held_version(catalog, library, other, None)
            problem = problem or _unreadable(holding)
            if problem:
                print(f"note: {problem}")
                continue
            try:
                targets.append(search_mod.load_version(holding))
            except search_mod.SearchError as exc:
                print(f"note: cannot read {other}: {exc}")
    targets.append(version)
    try:
        hits = [
            (v, h)
            for v in targets
            for h in v.find(args.pattern, regex=args.regex, case=args.case)
        ]
    except re.error as exc:
        print(f"bad regular expression: {exc}")
        return EXIT_ACTION
    if not hits:
        print("no hits")
        return EXIT_OK
    limit = len(hits) if args.max_hits <= 0 else args.max_hits  # 0: no cap
    for v, hit in hits[:limit]:
        print(_hit_line(hit, v.document))
        if args.context > 0:
            for ln in _context_lines(v, hit, args.context):
                print(ln)
            print("--")
    if len(hits) > limit:
        print(
            f"{len(hits) - limit} more hits not shown; narrow the pattern or "
            "raise --max"
        )
    return EXIT_OK


def _section_line(level: int, sec: search_mod.Section, end: int) -> str:
    first = f"~{sec.page}" if sec.approximate else str(sec.page)
    return f"{level} | {sec.title} | pages {first}-{end}"


def cmd_section(args: argparse.Namespace) -> int:
    version, _, code = _open_version(args)
    if version is None:
        return code
    matches = version.match_sections(args.query)
    if not matches:
        print("no matching section")
        return EXIT_OK
    for level, sec, end in matches:
        print(_section_line(level, sec, end))
    return EXIT_OK


def cmd_page(args: argparse.Namespace) -> int:
    if (args.page is None) == (args.section is None):
        print("give a page number or --section (not both)")
        return EXIT_ACTION
    if args.section is not None and args.to is not None:
        print("--to goes with a page number, not with --section")
        return EXIT_ACTION
    version, _, code = _open_version(args)
    if version is None:
        return code
    if args.section is not None:
        matches = version.match_sections(args.section)
        if not matches:
            print("no matching section")
            return EXIT_ACTION
        _, sec, end = matches[0]
        first, last = sec.page, end
    else:
        first = args.page
        last = args.to if args.to is not None else args.page
    count = version.page_count
    for n in (first, last):
        if not 1 <= n <= count:
            print(f"page {n} is outside {version.label} (pages 1-{count})")
            return EXIT_ACTION
    if last < first:
        print("--to must not be before the first page")
        return EXIT_ACTION
    span = last - first + 1
    if span > args.max_pages:
        print(
            f"pages {first}-{last} are {span} pages; the limit is {args.max_pages} "
            "per call (--max-pages raises it, or read a narrower range)"
        )
        return EXIT_ACTION
    for n in range(first, last + 1):
        if n > first:
            print()
        print(version.cite(n))
        for ln in search_mod.format_page(version, n):
            print(ln)
    return EXIT_OK


def cmd_render(args: argparse.Namespace) -> int:
    version, _, code = _open_version(args)
    if version is None:
        return code
    n = args.page
    if not 1 <= n <= version.page_count:
        print(f"page {n} is outside {version.label} (pages 1-{version.page_count})")
        return EXIT_ACTION
    out = version.path / extract_mod.RENDERS_DIRNAME / f"page-{n}.png"
    if out.is_file() and not args.force:
        print(f"rendered {out} (existing; --force to redo)")
    else:
        original = version.original or version.path / "original.pdf"
        try:
            render_mod.render_page(original, n, out, scale=args.scale)
        except ImportError as exc:
            print(f"cannot render: {exc}; run: pip install -r requirements.txt")
            return EXIT_ACTION
        except (OSError, ValueError) as exc:
            print(f"cannot render page {n} of {version.label}: {exc}")
            return EXIT_ERROR
        print(f"rendered {out}")
    print(version.cite(n, lines="rendered page"))
    return EXIT_OK


# --------------------------------------------------------------- code


def _code_setup(args):
    """(catalog, CodeLibrary, Config) or an exit code after a message."""
    catalog = _load(args)
    root = resolve_library()
    try:
        config = code_mod.load_config(root)
    except code_mod.CodeError as exc:
        print(str(exc))
        return None, None, None, EXIT_ERROR
    return catalog, code_mod.CodeLibrary(root), config, EXIT_OK


def _repo_or_message(catalog, library, repo_id: str, *, guess: bool):
    """The catalog's Repo, or one built for an unlisted repository: from a
    held tree, or (``guess``, for clone) from the openbmc organisation.
    None after a message when nothing fits."""
    repo = catalog.get_repo(repo_id)
    if repo is not None:
        return repo
    name = repo_id.strip()
    if not name or "/" in name or "\\" in name or name.startswith("."):
        print(f"'{repo_id}' is not a repository id; bmcspec repos lists them")
        return None
    held = library.trees(name)
    if held:
        return Repo(name, held[0].url, (), ())
    if guess:
        url = code_mod.guess_url(name)
        print(f"note: {name} is not in the catalog; trying {url}")
        return Repo(name, url, (), ())
    print(f"unknown repository '{repo_id}'; bmcspec repos lists them")
    return None


def _tree_summary(tree: code_mod.Tree) -> str:
    text = f"{tree.short} {tree.provenance.label(tree.fetched_at)}"
    return text + (" superseded" if tree.superseded else "")


def cmd_repos(args: argparse.Namespace) -> int:
    catalog, library, config, code = _code_setup(args)
    if code != EXIT_OK:
        return code
    if args.search:
        try:
            hits = code_mod.gh_search(args.search)
        except code_mod.CodeError as exc:
            print(str(exc))
            return EXIT_ACTION
        print("note: GitHub code search covers default branches only")
        if not hits:
            print("no hits")
            return EXIT_OK
        for repo, path in hits:
            print(f"{repo} {path}")
        return EXIT_OK
    if config.release:
        held = [
            t
            for t in library.trees(code_mod.OPENBMC_REPO)
            if t.provenance.kind in ("ref", "default")
            and t.provenance.name == config.release
        ]
        resolved = f"openbmc {held[0].short}" if held else "not resolved yet"
        print(f"release: {config.release} (config.toml) -> {resolved}")
    repos = catalog.by_topic(args.topic) if args.topic else catalog.repos
    if args.topic and not repos:
        print(f"no repository has the topic '{args.topic}'")
        return EXIT_ACTION
    for repo in repos:
        trees = [t for t in library.trees(repo.id) if not t.superseded] + [
            t for t in library.trees(repo.id) if t.superseded
        ]
        held = "; ".join(_tree_summary(t) for t in trees) or "-"
        checkout = config.checkouts.get(repo.id.lower())
        mine = f"user checkout: {checkout}" if checkout else "-"
        print(f"{repo.id}\t{held}\t{mine}\t{', '.join(repo.topics)}")
    if not args.topic:  # held repositories the catalog does not list
        listed = {r.id.lower() for r in catalog.repos}
        extra = sorted(
            {t.repo for t in library.trees() if t.repo.lower() not in listed}
        )
        for name in extra:
            trees = library.trees(name)
            held = "; ".join(_tree_summary(t) for t in trees) or "-"
            checkout = config.checkouts.get(name.lower())
            mine = f"user checkout: {checkout}" if checkout else "-"
            print(f"{name}\t{held}\t{mine}\t(not in catalog)")
    return EXIT_OK


def _openbmc_tree(catalog, library, release: str, force: bool) -> code_mod.Tree:
    """The openbmc/openbmc Code Tree at the release, fetched if needed."""
    source = catalog.get_repo(code_mod.OPENBMC_REPO)
    if source is None:
        raise code_mod.CodeError(
            f"the catalog has no '{code_mod.OPENBMC_REPO}' repository to resolve "
            f"releases from"
        )
    if not force:
        for t in library.trees(source.id):
            if t.provenance.kind == "ref" and t.provenance.name == release:
                if not t.superseded:
                    return t
    tree, fetched = library.clone(
        source.id,
        source.url,
        code_mod.Provenance("ref", release),
        ref=release,
        sparse=source.sparse,
        force=force,
    )
    if fetched:
        print(f"cloned {tree.label} (release {release}) -> {tree.path}")
    return tree


def cmd_clone(args: argparse.Namespace) -> int:
    if args.ref and args.release:
        print("give --ref or --release, not both")
        return EXIT_ACTION
    catalog, library, config, code = _code_setup(args)
    if code != EXIT_OK:
        return code
    repo = _repo_or_message(catalog, library, args.repo, guess=True)
    if repo is None:
        return EXIT_ACTION
    known = catalog.get_repo(repo.id) is not None
    release = args.release
    if not args.ref and not release and config.release:
        release = config.release
        print(f"release: {release} (from config.toml)")
    if release and repo.id.lower() == code_mod.OPENBMC_REPO:
        args.ref, release = release, None  # the release source: the tag or branch
    try:
        if release:
            source = _openbmc_tree(catalog, library, release, args.force)
            pin, recipe = code_mod.find_pin_recipe(source.path, repo.id)
            prov = code_mod.Provenance("release", release, source.commit)
            tree, fetched = library.clone(
                repo.id,
                repo.url,
                prov,
                commit=pin,
                sparse=repo.sparse,
                force=args.force,
                catalog_known=known,
            )
        elif args.ref:
            prov = code_mod.Provenance("ref", args.ref)
            tree, fetched = library.clone(
                repo.id,
                repo.url,
                prov,
                ref=args.ref,
                sparse=repo.sparse,
                force=args.force,
                catalog_known=known,
            )
        else:
            prov = code_mod.Provenance("default", "")
            tree, fetched = library.clone(
                repo.id,
                repo.url,
                prov,
                sparse=repo.sparse,
                force=args.force,
                catalog_known=known,
            )
    except code_mod.CodeError as exc:
        print(str(exc))
        return EXIT_ACTION
    what = tree.provenance.label(tree.fetched_at)
    if fetched:
        print(f"cloned {tree.label} ({what}) -> {tree.path}")
        for old in library.trees(repo.id):
            if old.superseded_by == tree.commit:
                print(
                    f"superseded {old.label} ({old.provenance.label(old.fetched_at)})"
                )
    else:
        print(f"held {tree.label} ({what}) at {tree.path}")
    if release:
        print(f"pin: {tree.short} from {recipe} of openbmc {source.short}")
    return EXIT_OK


def cmd_prune(args: argparse.Namespace) -> int:
    root = resolve_library()
    library = code_mod.CodeLibrary(root)
    doomed = [t for t in library.trees() if t.superseded]
    leftovers = []
    if library.code.is_dir():
        for rdir in sorted(p for p in library.code.iterdir() if p.is_dir()):
            leftovers += sorted(
                p for p in rdir.iterdir() if p.is_dir() and p.name.startswith(".tmp-")
            )
    if not doomed and not leftovers:
        print("nothing to prune: no superseded Code Tree, no leftover")
        return EXIT_OK
    verb = "removed" if args.yes else "would remove"
    failed = 0
    for tree in doomed:
        why = (
            f"{tree.label}, {tree.provenance.label(tree.fetched_at)}, "
            f"superseded by {tree.superseded_by[:7]}"
        )
        failed += _prune_path(tree.path, f"{verb} {tree.path} ({why})", args.yes)
    for path in leftovers:
        failed += _prune_path(path, f"{verb} {path} (leftover)", args.yes)
    tail = "" if args.yes else " (dry run; --yes removes them)"
    print(
        f"prune: {len(doomed)} superseded tree(s), {len(leftovers)} leftover(s){tail}"
    )
    return EXIT_ERROR if failed else EXIT_OK


def _prune_path(path: Path, line: str, really: bool) -> int:
    """Print the line and, when ``really``, remove the directory; 1 on failure."""
    if really:
        try:
            code_mod._rmtree(path)
        except code_mod.CodeError as exc:
            print(f"failed {path}: {exc}")
            return 1
    print(line)
    return 0


def _select_tree(args, catalog, library, config, repo):
    """(tree, notes): the Code Tree a reading command works on.

    A user checkout wins; then the named ref or release; then the config
    release; then the newest default-branch tree. CodeError says what to
    run when nothing fits.
    """
    notes = []
    checkout = config.checkouts.get(repo.id.lower())
    if checkout is not None:
        tree = code_mod.checkout_tree(repo.id, repo.url, checkout)
        asked = args.ref or args.release
        if asked:
            notes.append(f"note: using the user checkout {checkout} instead of {asked}")
        return tree, notes
    trees = library.trees(repo.id)
    if args.ref:
        found = (
            library.held(repo.id, args.ref) if code_mod._SHA.match(args.ref) else None
        )
        if found is None:
            named = [
                t
                for t in trees
                if t.provenance.kind in ("ref", "default")
                and t.provenance.name == args.ref
            ]
            named.sort(key=lambda t: (t.superseded, ""))
            found = named[0] if named else None
        if found is None:
            raise code_mod.CodeError(
                f"{repo.id} is not held at {args.ref}; run: bmcspec clone {repo.id} "
                f"--ref {args.ref}"
            )
        return found, notes
    release = args.release or config.release
    if release:
        if not args.release:
            notes.append(f"note: release {release} from config.toml")
        if repo.id.lower() == code_mod.OPENBMC_REPO:
            kind = "ref"  # the release source is held at the tag or branch itself
        else:
            kind = "release"
        pinned = [
            t
            for t in trees
            if t.provenance.kind == kind and t.provenance.name == release
        ]
        pinned.sort(key=lambda t: (t.superseded, ""))
        if not pinned:
            raise code_mod.CodeError(
                f"{repo.id} is not held at release {release}; run: bmcspec clone "
                f"{repo.id} --release {release}"
            )
        return pinned[0], notes
    current = [t for t in trees if t.provenance.kind == "default" and not t.superseded]
    if current:
        return current[0], notes
    if trees:
        return trees[0], notes
    raise code_mod.CodeError(
        f"{repo.id} is not in the Library; run: bmcspec clone {repo.id}"
    )


def _reading_tree(args):
    """(tree, repo, notes, exit code) for grep and code."""
    if args.ref and args.release:
        print("give --ref or --release, not both")
        return None, None, [], EXIT_ACTION
    catalog, library, config, code = _code_setup(args)
    if code != EXIT_OK:
        return None, None, [], code
    repo = _repo_or_message(catalog, library, args.repo, guess=False)
    if repo is None:
        return None, None, [], EXIT_ACTION
    try:
        tree, notes = _select_tree(args, catalog, library, config, repo)
    except code_mod.CodeError as exc:
        print(str(exc))
        return None, None, [], EXIT_ACTION
    return tree, repo, notes, EXIT_OK


def cmd_grep(args: argparse.Namespace) -> int:
    tree, repo, notes, code = _reading_tree(args)
    if tree is None:
        return code
    if args.max_hits < 0:
        print("--max must be 0 or more")
        return EXIT_ACTION
    try:
        hits = code_mod.grep(
            tree,
            args.pattern,
            regex=args.regex,
            glob=args.glob,
            context=max(0, args.context),
        )
    except code_mod.CodeError as exc:
        print(str(exc))
        return EXIT_ACTION
    for note in notes:
        print(note)
    matches = [h for h in hits if not h.context and h.line]
    if not matches:
        print("no hits")
        return EXIT_OK
    limit = args.max_hits or len(matches)
    blocks: list[list[code_mod.Hit]] = [[]]
    for hit in hits:  # separators split blocks; context lines stay in theirs
        if hit.line == 0:
            blocks.append([])
        elif args.context:
            blocks[-1].append(hit)
        else:
            blocks.append([hit])  # no context: every hit stands alone
    shown = 0
    for i, block in enumerate(b for b in blocks if b):
        if shown >= limit:
            break
        if i and args.context:
            print("--")
        for hit in block:
            if shown >= limit:
                break  # the cap counts hits; trailing context goes with them
            if hit.context:
                print(f"    line {hit.line}: {hit.text}")
            else:
                print(f"{repo.id}@{tree.short} {hit.path}:{hit.line} | {hit.text}")
                shown += 1
    more = len(matches) - shown
    if more > 0:
        print(f"{more} more hits not shown; narrow the pattern or raise --max")
    return EXIT_OK


def cmd_code(args: argparse.Namespace) -> int:
    tree, repo, notes, code = _reading_tree(args)
    if tree is None:
        return code
    try:
        path, lines = code_mod.read_lines(tree, args.path)
    except code_mod.CodeError as exc:
        print(str(exc))
        return EXIT_ACTION
    if lines and lines[-1] == "":
        lines.pop()  # the file's final newline
    total = len(lines)
    first, last = 1, total
    if args.lines:
        m = re.match(r"^(\d+)-(\d+)$", args.lines.strip())
        if not m:
            print("--lines takes A-B (line numbers, 1-based)")
            return EXIT_ACTION
        first, last = int(m.group(1)), int(m.group(2))
        if first < 1 or last < first or first > total:
            print(f"{path} has {total} lines; --lines {args.lines} is outside it")
            return EXIT_ACTION
        last = min(last, total)
    elif total > code_mod.MAX_WHOLE_FILE:
        print(
            f"{path} has {total} lines; give --lines A-B "
            f"(a whole file is printed only up to {code_mod.MAX_WHOLE_FILE} lines)"
        )
        return EXIT_ACTION
    for note in notes:
        print(note)
    print(code_mod.cite(tree, path, first, last, repo.url))
    width = len(str(last))
    for n in range(first, last + 1):
        print(f"{str(n).rjust(width)}  {lines[n - 1]}".rstrip())
    return EXIT_OK


# ------------------------------------------------------------- schema


def _bundle_cite(holding, file: str, pointer: str) -> str:
    return " | ".join(
        [
            f"cite: {holding.family}",
            f"{holding.document} {holding.version}",
            bundle_mod.label_of(file),
            f"file {file}",
            pointer,
            search_mod.origin_of(holding.meta),
            str(holding.path),
        ]
    )


def cmd_schema(args: argparse.Namespace) -> int:
    if args.property and args.definition:
        print("give --property or --definition, not both")
        return EXIT_ACTION
    catalog = _load(args)
    library = Library(resolve_library())
    holding, _, problem = _held_version(
        catalog, library, args.document, args.doc_version
    )
    if holding is None:
        print(problem)
        return EXIT_ACTION
    label = f"{holding.document} {holding.version}"
    doc = holding.document
    if holding.original.suffix.lower() != ".zip":
        print(
            f"{label} is a PDF document, not a schema bundle; read it with: "
            f"bmcspec find {doc} PATTERN, or: bmcspec page {doc} N"
        )
        return EXIT_ACTION
    if not bundle_mod.is_current(holding.path):
        print(
            f"{label} is not extracted, or was unpacked by an older version; run: "
            f'bmcspec extract {doc} --version "{holding.version}"'
        )
        return EXIT_ACTION
    schemas = bundle_mod.Schemas(holding.path)
    try:
        return _schema_output(args, holding, schemas)
    except bundle_mod.SchemaError as exc:
        print(f"cannot read the schemas of {label}: {exc}")
        return EXIT_ERROR


def _schema_output(args, holding, schemas: bundle_mod.Schemas) -> int:
    if not args.resource:
        for res in schemas.resources():
            print(f"{res.name}\t{res.version or '-'}")
        return EXIT_OK
    res = schemas.resource(args.resource)
    if res is None:
        names = schemas.similar(args.resource)
        if names:
            found = ", ".join(names)
            print(f"no resource named {args.resource!r}; containing it: {found}")
        else:
            print(
                f"no resource named {args.resource!r}; "
                f"bmcspec schema {holding.document} lists them"
            )
        return EXIT_ACTION
    defs = schemas.load(res.file).get("definitions", {})
    names = ", ".join(sorted(defs)) if isinstance(defs, dict) and defs else "-"
    if args.definition:
        where = schemas.definition(res.file, args.definition)
        if where is None:
            print(
                f"{res.file} has no definition named {args.definition!r}; "
                f"bmcspec schema {holding.document} {res.name} lists them"
            )
            return EXIT_ACTION
        _print_node(holding, schemas, where, where.pointer.rsplit("/", 1)[-1])
        return EXIT_OK
    main = schemas.main_definition(res)
    if main is None:
        print(
            f"{res.file} has no definition named {res.name}; it defines: {names}; "
            f"read one with: bmcspec schema {holding.document} {res.name} "
            f"--definition NAME"
        )
        return EXIT_ACTION
    if args.property:
        where = schemas.property(main, args.property)
        if where is None:
            print(
                f"{res.label} has no property named {args.property!r}; "
                f"bmcspec schema {holding.document} {res.name} lists them"
            )
            return EXIT_ACTION
        name = where.pointer.rsplit("/", 1)[-1]
        _print_node(holding, schemas, where, name, is_property=True)
        return EXIT_OK
    print(_bundle_cite(holding, main.file, main.pointer))
    lines = bundle_mod.property_lines(schemas, main)
    print(f"schema: {res.label} | {len(lines)} properties | definitions: {names}")
    for ln in lines:
        print(ln)
    return EXIT_OK


def _print_node(
    holding, schemas, where, name: str, *, is_property: bool = False
) -> None:
    print(_bundle_cite(holding, where.file, where.pointer))
    node = where.node
    kind = schemas.type_of(node, where.file)
    if is_property:
        access = "readonly" if node.get("readonly") else "writable"
        added = node.get("versionAdded")
        added = f"added {bundle_mod.dotted(added)}" if added else "-"
        print(f"property: {name} | {kind} | {access} | {added}")
    else:
        print(f"definition: {name} | {kind}")
    for ln in bundle_mod.detail_lines(node):
        print(ln)
    if "enum" in node:
        for ln in bundle_mod.enum_lines(node):
            print(ln)
    else:
        enum = schemas.enum_of(node, where.file, where.pointer)
        if enum is not None:
            if (enum.file, enum.pointer) != (where.file, where.pointer):
                print(_bundle_cite(holding, enum.file, enum.pointer))
            for ln in bundle_mod.enum_lines(enum.node):
                print(ln)
    for ln in bundle_mod.parameter_lines(schemas, where):
        print(ln)
    if "properties" in node and not is_property:
        print("properties:")
        for ln in bundle_mod.property_lines(schemas, where):
            print("  " + ln)


def _section_lookup(version: search_mod.Version):
    """The Outline entry in force at a table's caption (or the page top)."""

    def lookup(page: int, caption: str | None):
        index = version.find_line(page, caption) if caption else 0
        return version.owning_section(page, index)

    return lookup


def _label(section) -> str | None:
    return section.label if section else None


def cmd_table(args: argparse.Namespace) -> int:
    version, _, code = _open_version(args)
    if version is None:
        return code
    n = args.page
    if not 1 <= n <= version.page_count:
        print(f"page {n} is outside {version.label} (pages 1-{version.page_count})")
        return EXIT_ACTION
    if args.index is not None and args.index < 1:
        print("--index counts from 1")
        return EXIT_ACTION
    lookup = _section_lookup(version)
    tables = None if args.force else tables_mod.stored_for_page(version.path, n)
    if tables is None:
        original = version.original or version.path / "original.pdf"
        try:
            with tables_mod.Reader(original) as reader:
                tables, found, done = reader.read_page(
                    n, section_of=lambda page, caption: _label(lookup(page, caption))
                )
        except ImportError as exc:
            print(f"cannot read tables: {exc}; run: pip install -r requirements.txt")
            return EXIT_ACTION
        except tables_mod.TableError as exc:
            print(f"cannot read tables of {version.label}: {exc}")
            return EXIT_ERROR
        tables_mod.store(version.path, done, found)
    if not tables:
        doc = version.document
        print(
            f"no ruled table on page {n} of {version.label}; read the page with: "
            f"bmcspec page {doc} {n}, or look at it with: "
            f"bmcspec render {doc} --page {n}"
        )
        return EXIT_ACTION
    if args.index is not None:
        if args.index > len(tables):
            print(
                f"page {n} has {len(tables)} table(s); "
                f"--index {args.index} is out of range"
            )
            return EXIT_ACTION
        tables = [tables[args.index - 1]]
    for i, table in enumerate(tables):
        if i:
            print()
        print(
            version.cite(
                table.first,
                lines=f"table {table.index}",
                last=table.last,
                section=table.section,
            )
        )
        print(tables_mod.describe(table))
        for ln in tables_mod.format_table(table):
            print(ln)
    return EXIT_OK


COMMANDS = {
    "library": cmd_library,
    "catalog": cmd_catalog,
    "fetch": cmd_fetch,
    "add": cmd_add,
    "scan": cmd_scan,
    "status": cmd_status,
    "check": cmd_check,
    "refresh": cmd_refresh,
    "prune": cmd_prune,
    "extract": cmd_extract,
    "find": cmd_find,
    "section": cmd_section,
    "page": cmd_page,
    "render": cmd_render,
    "table": cmd_table,
    "schema": cmd_schema,
    "repos": cmd_repos,
    "clone": cmd_clone,
    "grep": cmd_grep,
    "code": cmd_code,
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
    except LibraryError as exc:
        print(f"library: {exc}")
        return EXIT_ACTION
    except OSError as exc:
        print(f"error: {exc}")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())

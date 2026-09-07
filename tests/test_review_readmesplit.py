"""Reviewer acceptance tests for round 2 of the 1.0.0 release change: the
README split and the sequence diagram (AC-5 to AC-9).

Black-box against the Markdown files a reader opens: README.md and the
three new files under docs/. Every test here fails on main, where the
README still holds the moved sections, docs/LIBRARY.md, docs/COMMANDS.md
and docs/CATALOG.md do not exist, there is no Mermaid diagram and
tests/test_release.py is absent.

AC-6 asks for the moved text to be verbatim. Without git in the sandbox
the check is done with sentences copied from the README on main: each one
must appear unchanged in the file that now owns it, and must have left
the README.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DOCS = ROOT / "docs"
TESTS = ROOT / "tests"


def _read(path: Path) -> str:
    return path.read_text("utf-8")


def _headings(text: str) -> list[str]:
    return [ln[3:].strip() for ln in text.splitlines() if ln.startswith("## ")]


def _section(text: str, heading: str) -> str:
    """The body of a `## heading` up to the next `## `."""
    start = text.index(f"\n## {heading}\n")
    rest = text[start + 1 :]
    m = re.search(r"\n## ", rest)
    return rest[: m.start()] if m else rest


# ------------------------------------------------------------------ AC-5


def test_readme_has_the_eight_sections_in_order():
    assert _headings(_read(README)) == [
        "Install",
        "How a question is answered",
        "Library location",
        "Command line",
        "What the tool does on the network and on disk",
        "Further reading",
        "Development",
        "License",
    ]


def test_readme_is_at_most_200_lines():
    assert len(_read(README).splitlines()) <= 200


def test_readme_examples_define_one_alias_and_use_it():
    text = _read(README)
    block = _section(text, "Command line")
    alias_lines = [
        ln for ln in block.splitlines() if ln.startswith("alias bmcspec=")
    ]
    assert len(alias_lines) == 1, alias_lines
    assert "skills/bmc-spec/scripts/bmcspec.py" in alias_lines[0]
    # every example line in the fenced block goes through the alias
    fenced = re.search(r"```\n(.*?)\n```", block, re.S)
    assert fenced, "no fenced example block"
    examples = [
        ln for ln in fenced.group(1).splitlines() if ln and not ln.startswith("alias ")
    ]
    assert examples, "no examples"
    for ln in examples:
        assert ln.startswith("bmcspec "), ln
    # the long spelled-out form is gone from the examples
    assert "python skills/bmc-spec/scripts/bmcspec.py catalog" not in text


def test_readme_examples_show_fetch_of_a_named_version():
    block = _section(_read(README), "Command line")
    lines = [ln.strip() for ln in block.splitlines()]
    assert any(ln.startswith("bmcspec fetch DSP0236 --version 1.2.0") for ln in lines), lines


def test_readme_links_the_four_docs_files_and_they_exist():
    text = _read(README)
    for name in ("LIBRARY.md", "COMMANDS.md", "CATALOG.md", "SUPPORT.md"):
        assert f"](docs/{name})" in text, name
        assert (DOCS / name).is_file(), name


def test_readme_further_reading_names_each_docs_file_once_as_a_bullet():
    section = _section(_read(README), "Further reading")
    bullets = [ln for ln in section.splitlines() if ln.startswith("- [docs/")]
    names = [re.match(r"- \[docs/([A-Z]+\.md)\]", ln).group(1) for ln in bullets]
    assert sorted(names) == ["CATALOG.md", "COMMANDS.md", "LIBRARY.md", "SUPPORT.md"]


# ------------------------------------------------------------------ AC-6
# Sentences copied from the README on main, one per moved block.

LIBRARY_VERBATIM = [
    "Each document version sits at\n"
    "`specs/<family>/<document>/<version>/original.<pdf|zip>` next to a\n"
    "`meta.json` that records where it came from and its SHA-256.",
    "`linemap.json` (DMTF printed line numbers: per physical page, the first\n"
    "and last number and a map from each line's 0-based index within the page\n"
    "block to its printed number)",
    "Code Trees live beside `specs/`, under `code/<repo>/<commit>/`, each with\n"
    "a `.bmc-tree.json`.",
]

LIBRARY_FILE_NAMES = [
    "original.<pdf|zip>",
    "meta.json",
    "extract.txt",
    "outline.json",
    "linemap.json",
    "extract.json",
    "figures.json",
    "renders/page-N.png",
    "tables.json",
    "schemas/",
    "registries/",
    ".bmc-tree.json",
    '"approximate": true',
    '"kind": "schemas"',
    '"kind": "registries"',
]

COMMANDS_VERBATIM = [
    # The fewer round trips change reworded this sentence (the reading
    # commands read the catalog's latest, fetching it); the pinned text follows.
    "`find` searches the catalog's latest version (or `--version`),\n"
    "case-insensitively unless `--case`, as a literal unless `--regex`; `--max`\n"
    "(default 50) caps the hits.",
    "`table` prints every table touching the page as a Logical Table:",
    "`schema` reads a Redfish schema bundle (DSP8010): without a resource it\n"
    "lists the resources and their newest schema version;",
    "`registry` reads the Redfish message registries bundle (DSP8011): without\n"
    "a registry it lists the registries with their version and message count;",
    "`clone` brings a repository into the Library as a Code Tree (a catalog\n"
    "entry, or any `openbmc/<name>` when the catalog does not list it),",
    # M13 (locks) reworded this paragraph; the pinned text follows it.
    "`prune` lists every Code Tree marked superseded (an older commit of a\n"
    "moving name re-fetched with `--force`), every `.tmp-*` directory a failed\n"
    "clone left behind, every `.part` file or `.lock.takeover` gate older than\n"
    "five minutes that a failed write or take-over left behind, and every stale\n"
    "`.lock`, and removes nothing; `prune --yes` removes them,",
    "`config.toml` at the Library root (optional):",
    "[library]\nfreshness_days = 30",
    "[code.checkouts]\nbmcweb = \"/home/me/src/bmcweb\"",
    "Publishers add versions faster than a catalog is maintained. `check DOC`\n"
    "asks the publisher what it lists now and compares with the catalog:",
    "OCP versions are mostly Google Drive links on the wiki, so `check`\n"
    "reports them with `(URL to confirm by hand)`.",
]

NETWORK_VERBATIM = [
    "- Downloads only URLs listed in `bmc_toolkit/spec/catalog.toml`, in this\n"
    "  order: the publisher's URL (with a browser TLS fingerprint through\n"
    "  `curl_cffi`, which Intel's and OCP's CDNs require),",
    "- A response that is not the expected PDF or ZIP (an HTML block page, a\n"
    "  cut-off download) is discarded and never written to the Library.",
    "- Writes only under the Library. Files placed there by hand are registered\n"
    "  as Drop-ins and their origin is recorded as user-provided, never as a URL;",
    "- Replacing an original (`add --force`, `fetch --force`) removes the\n"
    "  previous original and everything extracted from it, `tables.json`,\n"
    "  `schemas/` and rendered pages included; so does `extract --force`.",
    "- From a schema bundle only the JSON Schema files an answer needs leave the\n"
    "  archive: every unversioned `<Name>.json` and the newest\n"
    "  `<Name>.vX_Y_Z.json` per resource (452 files, 7.4 MB on disk, out of\n"
    "  DSP8010 2026.1's 6890 JSON Schema files and 234 MB);",
    "- `check` and `refresh` read listing pages only: "
    "`https://www.dmtf.org/standards/published_documents` and "
    "`https://www.dmtf.org/dsp/<DSP>`, "
    "`https://nvmexpress.org/wp-json/vtm/v1/specifications`, and "
    "`https://www.opencompute.org/w/index.php?title=<page>` for the pages "
    "named in the catalog's `listing` keys. They download no document.",
    "- Runs `git` as a subprocess for `clone` (shallow, one commit; "
    "`--filter=blob:none --sparse` for the `openbmc` repository and for "
    "`linux`, which is held only for `Documentation/` and the BMC-facing "
    "driver directories), `grep` and `code` (reading `HEAD` of a user "
    "checkout), and `git ls-remote --tags` on the `openbmc` repository for "
    "`check`; `gh search code` for `repos --search`. Nothing else is "
    "executed, and nothing is re-uploaded or redistributed.",
    # M13 (locks) reworded this bullet; the pinned text follows it.
    "- `clone` writes only under the Library's `code/` directory: "
    "`code/<repo>/<commit>/` plus a temporary `.tmp-<pid>-<token>` directory "
    "that is removed on failure, and `code/<repo>/.lock` while it runs.",
    # The fewer round trips change added the reading commands to this
    # bullet (they run the due check themselves); the pinned text follows.
    "- `check` writes `freshness.json` at the Library root, and so does a "
    "reading command that ran the due check; `fetch` and `status` stamp the "
    "reminder there (`reminded_at`) when they print the "
    "note. `refresh --write` is the one command that writes outside the "
    "Library: it inserts version entries into the catalog file it was given "
    "(`--catalog`, or the shipped `bmc_toolkit/spec/catalog.toml`).",
]

CATALOG_VERBATIM = [
    "`bmc_toolkit/spec/catalog.toml` lists every family, document, version and\n"
    "URL; comments in the file record when a URL was last confirmed. How far\n"
    "back the versions go depends on the publisher. DMTF and NVM Express\n"
    "documents carry their full version history, kept current by `refresh`.",
    "A version may carry its own `access` when\n"
    "the publisher keeps the newest revisions behind a registration (PMBus 1.4\n"
    "and 1.5 are listed that way, with no URL): `fetch` refuses such a version,",
    "`--by-family` prints the reader's form\n"
    "kept in `docs/SUPPORT.md`: a heading and a table per family, without the\n"
    "Fetch column, Verified reduced to `PASS` or `-`, and documents marked\n"
    "`unlisted = true` in the catalog left out (the BMC SoC datasheets are).",
    "`refresh --write`\n"
    "inserts the `add` entries as `[[documents.versions]]` blocks at their\n"
    "place in the document's block (publication order, same-day versions by\n"
    "their numbers), leaving every other line and comment as it was, and\n"
    "refuses an edit the parser would not accept.",
]


def test_library_doc_holds_the_layout_verbatim():
    text = _read(DOCS / "LIBRARY.md")
    for sentence in LIBRARY_VERBATIM:
        assert sentence in text, sentence[:60]


def test_library_doc_names_every_file_the_old_library_section_listed():
    text = _read(DOCS / "LIBRARY.md")
    for name in LIBRARY_FILE_NAMES:
        assert name in text, name


def test_commands_doc_holds_the_command_paragraphs_config_and_freshness_verbatim():
    text = _read(DOCS / "COMMANDS.md")
    for sentence in COMMANDS_VERBATIM:
        assert sentence in text, sentence[:60]
    # the per-command paragraphs come in the README's original order
    starts = [
        "`find` searches",
        "`table` prints",
        "`schema` reads",
        "`registry` reads",
        "`clone` brings",
        "`prune` lists",
        "`config.toml` at the Library root",
    ]
    positions = [text.index(s) for s in starts]
    assert positions == sorted(positions)


def test_commands_doc_holds_the_full_network_and_disk_list_verbatim():
    text = _read(DOCS / "COMMANDS.md")
    section = _section(text, "What the tool does on the network and on disk")
    for bullet in NETWORK_VERBATIM:
        assert bullet in section, bullet[:60]
    # nine bullets, as on main
    assert sum(1 for ln in section.splitlines() if ln.startswith("- ")) == 9


def test_commands_doc_cross_reference_names_the_catalog_file():
    """The one edit AC-6 allows: 'see The Source Catalog below' pointed at a
    README section that no longer exists in that file."""
    text = _read(DOCS / "COMMANDS.md")
    assert "The Source Catalog below" not in text
    freshness = _section(text, "Freshness Check")
    assert "CATALOG.md" in freshness


def test_catalog_doc_holds_the_source_catalog_section_verbatim():
    text = _read(DOCS / "CATALOG.md")
    assert text.startswith("# The Source Catalog\n")
    for sentence in CATALOG_VERBATIM:
        assert sentence in text, sentence[:60]


def test_moved_text_has_left_the_readme():
    text = _read(README)
    for heading in ("## Freshness Check", "## The Source Catalog"):
        assert heading not in text, heading
    for sentence in (
        LIBRARY_VERBATIM + COMMANDS_VERBATIM + NETWORK_VERBATIM + CATALOG_VERBATIM
    ):
        assert sentence not in text, sentence[:60]


def test_readme_summary_still_names_the_subprocesses_and_the_code_directory():
    """The short network-and-disk summary the README keeps must still say
    what runs as a subprocess and where clone writes (CONVENTIONS.md)."""
    section = _section(_read(README), "What the tool does on the network and on disk")
    for word in ("`git`", "`gh search code`", "subprocess", "`code/`", "`refresh --write`"):
        assert word in section, word
    assert "](docs/COMMANDS.md)" in section


def test_docs_files_are_lf_only():
    for name in ("LIBRARY.md", "COMMANDS.md", "CATALOG.md"):
        assert b"\r" not in (DOCS / name).read_bytes(), name
    assert b"\r" not in README.read_bytes()


# ------------------------------------------------------------------ AC-7
# The tests that used to read the moved text from the README now read the
# file that holds it. Checked on the test sources, since that is what the
# AC is about.

RELOCATED = {
    "test_review_bundle.py": ["docs", "LIBRARY.md"],
    "test_review_codeclone.py": ["docs", "LIBRARY.md", "COMMANDS.md"],
    "test_review_doctrim.py": ["docs", "CATALOG.md"],
    "test_review_freshness.py": ["docs", "COMMANDS.md"],
    "test_review_m9catalog.py": ["docs", "COMMANDS.md", "LIBRARY.md"],
    "test_review_publishers.py": ["docs", "CATALOG.md"],
}


def test_relocated_assertions_read_the_new_files():
    for name, needles in RELOCATED.items():
        source = _read(TESTS / name)
        for needle in needles:
            assert needle in source, f"{name} does not read {needle}"


def test_relocated_assertions_no_longer_look_for_moved_headings_in_the_readme():
    for name in ("test_review_doctrim.py", "test_review_publishers.py"):
        source = _read(TESTS / name)
        assert '"## The Source Catalog"' not in source, name


# ------------------------------------------------------------------ AC-8


def _diagram() -> tuple[str, str]:
    """(mermaid block body, text after the block within the section)."""
    section = _section(_read(README), "How a question is answered")
    m = re.search(r"```mermaid\n(.*?)\n```", section, re.S)
    assert m, "no ```mermaid block under How a question is answered"
    return m.group(1), section[m.end() :]


def test_diagram_is_a_sequence_diagram_with_five_participants():
    diagram, _ = _diagram()
    assert diagram.lstrip().startswith("sequenceDiagram")
    declared = [
        ln.strip()
        for ln in diagram.splitlines()
        if ln.strip().startswith(("participant ", "actor "))
    ]
    assert len(declared) == 5, declared
    joined = "\n".join(declared)
    for name in ("User", "Claude", "bmcspec.py", "Library", "Publisher"):
        assert name in joined, name


def test_diagram_shows_fetch_extract_find_page_in_that_order():
    diagram, _ = _diagram()
    messages = [ln for ln in diagram.splitlines() if "->>" in ln]
    order = []
    for cmd in ("fetch", "extract", "find", "page"):
        idx = next(
            (i for i, ln in enumerate(messages) if re.search(rf":\s*{cmd} DSP0236", ln)),
            None,
        )
        assert idx is not None, f"no message running {cmd} DSP0236"
        order.append(idx)
    assert order == sorted(order), order


def test_diagram_names_the_version_flag_and_the_cite_line():
    diagram, note = _diagram()
    assert "--version" in diagram
    assert "cite:" in diagram
    # the reply to the user is built from the cite: line
    to_user = [ln for ln in diagram.splitlines() if "-->>User" in ln]
    assert to_user and "cite:" in to_user[0], to_user
    # the note below says the same about versions and cite:
    assert "--version" in note
    assert "latest" in note
    assert "cite:" in note


def test_diagram_only_contacts_the_publisher_when_the_library_lacks_the_version():
    diagram, note = _diagram()
    assert re.search(r"^\s*alt\b", diagram, re.M), "no alt block"
    assert re.search(r"^\s*end\b", diagram, re.M), "alt block not closed"
    alt = diagram[re.search(r"^\s*alt\b", diagram, re.M).start() :]
    alt = alt[: re.search(r"^\s*end\b", alt, re.M).start()]
    assert "Pub" in alt, alt
    assert "Publisher is contacted only when" in note or "only when the Library" in note


# ------------------------------------------------------------------ AC-9


def test_ac3_docstring_says_validate_strict_warns_not_requires():
    source = _read(TESTS / "test_release.py")
    start = source.index("def test_marketplace_manifest_has_a_description")
    body = source[start:]
    doc = re.search(r'"""(.*?)"""', body, re.S)
    assert doc, "AC-3 test has no docstring"
    text = doc.group(1)
    assert "validate --strict" in text
    assert "warn" in text
    assert "require" not in text

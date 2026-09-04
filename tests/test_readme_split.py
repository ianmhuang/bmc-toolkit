"""README split (release 1.0.0 change, AC-5 to AC-8): the README keeps the
overview, the install steps, the sequence diagram, the command examples and
a short network-and-disk section; the details live in docs/LIBRARY.md,
docs/COMMANDS.md and docs/CATALOG.md."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DOCS = ROOT / "docs"

README_SECTIONS = [
    "Install",
    "How a question is answered",
    "Library location",
    "Command line",
    "What the tool does on the network and on disk",
    "Further reading",
    "Development",
    "License",
]

ALIAS = "alias bmcspec='python skills/bmc-spec/scripts/bmcspec.py'"


def _headings(text: str) -> list[str]:
    return [ln[3:] for ln in text.splitlines() if ln.startswith("## ")]


def test_readme_keeps_only_the_overview_sections():
    """AC-5: eight sections in this order, at most 200 lines."""
    text = README.read_text("utf-8")
    assert _headings(text) == README_SECTIONS
    assert len(text.splitlines()) <= 200
    # the moved sections are gone from the README
    moved = (
        "## Freshness Check",
        "## The Source Catalog",
        "`table` prints every table",
    )
    for gone in moved:
        assert gone not in text, gone


def test_readme_links_every_docs_file():
    """AC-5: the README points at the three new files and at SUPPORT.md."""
    text = README.read_text("utf-8")
    for name in ("LIBRARY.md", "COMMANDS.md", "CATALOG.md", "SUPPORT.md"):
        assert f"[docs/{name}](docs/{name})" in text, name
        assert (DOCS / name).is_file(), name


def test_library_doc_holds_the_layout():
    """AC-6: docs/LIBRARY.md carries the on-disk format that left the README."""
    text = (DOCS / "LIBRARY.md").read_text("utf-8")
    for key in (
        "original.<pdf|zip>",
        "meta.json",
        "extract.txt",
        "outline.json",
        "linemap.json",
        "figures.json",
        "tables.json",
        "schemas/",
        "registries/",
        "code/<repo>/<commit>/",
        ".bmc-tree.json",
    ):
        assert key in text, key


def test_commands_doc_holds_the_command_details():
    """AC-6: docs/COMMANDS.md carries the per-command paragraphs, config.toml,
    the Freshness Check and the full network-and-disk list."""
    text = (DOCS / "COMMANDS.md").read_text("utf-8")
    for heading in (
        "## Reading commands",
        "## Freshness Check",
        "## What the tool does on the network and on disk",
    ):
        assert heading in text, heading
    for key in (
        "`find` searches",
        "`table` prints every table",
        "`schema` reads",
        "`registry` reads",
        "`clone` brings",
        "`prune` lists",
        "[library]",
        "freshness_days",
        "[code.checkouts]",
        "freshness.json",
        "reminded_at",
        "https://www.dmtf.org/standards/published_documents",
    ):
        assert key in text, key
    # the cross-reference that pointed at a README section now names the file
    assert "The Source Catalog below" not in text
    assert "[CATALOG.md](CATALOG.md)" in text


def test_catalog_doc_holds_the_source_catalog_section():
    """AC-6: docs/CATALOG.md is the maintainer's description of the catalog."""
    text = (DOCS / "CATALOG.md").read_text("utf-8")
    assert text.startswith("# The Source Catalog\n")
    for key in (
        "bmc_toolkit/spec/catalog.toml",
        "`searched_with`",
        "`listing`",
        "`refresh --write`",
        "`unlisted = true`",
        "docs/SUPPORT.md",
    ):
        assert key in text, key


def test_readme_has_the_sequence_diagram():
    """AC-8: a Mermaid sequence diagram under "How a question is answered",
    naming the five participants and the commands in the order the skill
    runs them, and saying that a version can be asked for."""
    text = README.read_text("utf-8")
    start = text.index("## How a question is answered")
    section = text[start : text.index("\n## ", start + 1)]
    m = re.search(r"```mermaid\n(.*?)\n```", section, re.S)
    assert m, "no mermaid block"
    diagram = m.group(1)
    assert diagram.startswith("sequenceDiagram")
    for participant in (
        "actor User",
        "participant Claude",
        "participant CLI",
        "participant Lib",
        "participant Pub",
    ):
        assert participant in diagram, participant
    commands = ["fetch DSP0236", "extract DSP0236", "find DSP0236", "page DSP0236"]
    positions = [diagram.index(c) for c in commands]
    assert positions == sorted(positions)
    assert "--version" in diagram
    assert "cite:" in diagram
    assert "--version" in section[m.end() :]


def test_readme_examples_use_the_alias_and_name_a_version():
    """AC-5: the examples define the alias once and show fetch --version."""
    text = README.read_text("utf-8")
    assert text.count(ALIAS) == 1
    assert "bmcspec fetch DSP0236 --version 1.2.0" in text
    assert "python skills/bmc-spec/scripts/bmcspec.py catalog" not in text

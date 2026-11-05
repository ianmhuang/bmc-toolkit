"""`searched_with_from`: a document's companions are searched only when
`find` reads that version or a later one (DSP0248 moved its PDR definitions
to DSP0251 in 1.4.0; 1.3.1 still holds its own). Black-box through the CLI
on a synthetic catalog and synthetic PDFs."""

import tomllib

import pytest

from bmc_toolkit.spec.catalog import CatalogError, load_catalog, parse_catalog
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")

BASE = "https://example.test/base_{}.pdf"
PDR_URL = "https://example.test/pdr_1.0.0.pdf"


def base_version(version, published):
    return f"""
[[documents.versions]]
version = "{version}"
url = "{BASE.format(version)}"
type = "pdf"
published = "{published}"
"""


def catalog_text(companion='searched_with = ["PDR"]\nsearched_with_from = "1.4.0"'):
    return (
        """
schema_version = 1

[families.pldm]
title = "PLDM"
publisher = "DMTF"

[[documents]]
id = "BASE"
family = "pldm"
title = "Base specification"
access = "open"
fetch = "direct"
"""
        + companion
        + base_version("1.3.1", "2023-01-01")
        + base_version("1.4.0", "2025-01-01")
        + base_version("1.5.0", "2026-01-01")
        + """
[[documents]]
id = "PDR"
family = "pldm"
title = "PDR specification"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0.0"
url = "https://example.test/pdr_1.0.0.pdf"
type = "pdf"
published = "2026-02-01"
"""
    )


def parse(text):
    return parse_catalog(tomllib.loads(text))


@pytest.fixture
def cat(tmp_path):
    path = tmp_path / "from.toml"
    path.write_text(catalog_text(), encoding="utf-8", newline="")
    return path


@pytest.fixture
def served(scripted, tmp_path):
    """Every BASE version and PDR served; both hold 'sensor formula'."""
    for version in ("1.3.1", "1.4.0", "1.5.0"):
        pdf = pdfgen.write_pdf(
            tmp_path / f"base_{version}.pdf",
            [pdfgen.plain_page([f"base {version} sensor formula"])],
        )
        scripted.responses[BASE.format(version)] = ok(pdf.read_bytes())
    pdf = pdfgen.write_pdf(
        tmp_path / "pdr.pdf", [pdfgen.plain_page(["pdr sensor formula"])]
    )
    scripted.responses[PDR_URL] = ok(pdf.read_bytes())
    return scripted


def run(capsys, cat, *argv):
    code = main(["--catalog", str(cat), *argv])
    return code, capsys.readouterr().out


def find(capsys, cat, *argv):
    """find after a fetch of the version read, so only notes and hits print."""
    version = argv[argv.index("--version") + 1] if "--version" in argv else "1.5.0"
    code, out = run(capsys, cat, "fetch", "BASE", "--version", version)
    assert code == 0, out
    return run(capsys, cat, "find", "BASE", "sensor formula", *argv)


SKIP_NOTE = "note: PDR not searched: it goes with BASE from 1.4.0"


# ------------------------------------------------------------- AC-1 catalog


def test_searched_with_from_is_optional_and_parsed():
    assert parse(catalog_text()).get("BASE").searched_with_from == "1.4.0"
    plain = parse(catalog_text('searched_with = ["PDR"]'))
    assert plain.get("BASE").searched_with_from == ""
    assert plain.get("PDR").searched_with_from == ""


@pytest.mark.parametrize(
    "companion",
    [
        'searched_with = ["PDR"]\nsearched_with_from = 140',
        'searched_with_from = "1.4.0"',
        'searched_with = ["PDR"]\nsearched_with_from = "1.9.9"',
    ],
    ids=["not-a-string", "no-searched-with", "unknown-version"],
)
def test_bad_searched_with_from_is_a_catalog_error(companion):
    with pytest.raises(CatalogError, match="searched_with_from"):
        parse(catalog_text(companion))


# ------------------------------------------------------------- AC-2 shipped


def test_shipped_catalog_gives_dsp0248_searched_with_from_1_4_0_only():
    shipped = load_catalog()
    assert shipped.get("DSP0248").searched_with_from == "1.4.0"
    assert shipped.get("DSP0248").searched_with == ("DSP0251",)
    others = [d.id for d in shipped.documents if d.searched_with_from]
    assert others == ["DSP0248"]


# ------------------------------------------------------------- AC-3, AC-4


@pytest.mark.parametrize("argv", [(), ("--version", "1.4.0")], ids=["latest", "1.4.0"])
def test_from_version_and_later_search_the_companion_first(
    library, served, cat, capsys, argv
):
    code, out = find(capsys, cat, *argv)
    assert code == 0, out
    lines = out.strip().splitlines()
    notes = [ln for ln in lines if ln.startswith("note: ")]
    hits = [ln for ln in lines if not ln.startswith("note: ")]
    assert any(n.startswith("note: fetched PDR 1.0.0") for n in notes), out
    assert SKIP_NOTE not in notes
    version = "1.4.0" if argv else "1.5.0"
    assert hits == [
        "PDR p.1 | - | pdr sensor formula",
        f"BASE p.1 | - | base {version} sensor formula",
    ], out


def test_an_earlier_version_searches_itself_only_and_says_why(
    library, served, cat, capsys
):
    code, out = find(capsys, cat, "--version", "1.3.1")
    assert code == 0, out
    assert out.strip().splitlines() == [
        SKIP_NOTE,
        "BASE p.1 | - | base 1.3.1 sensor formula",
    ]
    assert PDR_URL not in served.calls
    assert library.find("PDR", "1.0.0") is None


def test_the_note_comes_before_no_hits(library, served, cat, capsys):
    code, out = run(capsys, cat, "fetch", "BASE", "--version", "1.3.1")
    assert code == 0, out
    code, out = run(capsys, cat, "find", "BASE", "absent text", "--version", "1.3.1")
    assert code == 0, out
    assert out.strip().splitlines() == [SKIP_NOTE, "no hits"]


def test_only_prints_no_skip_note(library, served, cat, capsys):
    code, out = find(capsys, cat, "--version", "1.3.1", "--only")
    assert code == 0, out
    assert out.strip().splitlines() == ["BASE p.1 | - | base 1.3.1 sensor formula"]


# ------------------------------------------------------------- AC-5 offline


def test_offline_fallback_to_an_earlier_held_version_skips_the_companion(
    library, served, cat, capsys
):
    code, out = run(capsys, cat, "fetch", "BASE", "--version", "1.3.1")
    assert code == 0, out
    (library.root / "config.toml").write_text(
        "[library]\noffline = true\n", encoding="utf-8", newline=""
    )
    calls = len(served.calls)
    code, out = run(capsys, cat, "find", "BASE", "sensor formula")
    assert code == 0, out
    lines = out.strip().splitlines()
    assert any("answering from held 1.3.1" in ln for ln in lines), out
    assert SKIP_NOTE in lines, out
    assert lines[-1] == "BASE p.1 | - | base 1.3.1 sensor formula"
    assert served.calls[calls:] == []


# ------------------------------------------------------------- AC-6 unlisted


def test_a_held_version_the_catalog_does_not_list_searches_the_companion(
    library, served, cat, capsys, tmp_path
):
    pdf = pdfgen.write_pdf(
        tmp_path / "local.pdf", [pdfgen.plain_page(["local sensor formula"])]
    )
    library.store(
        "pldm",
        "BASE",
        "1.4.0-local",
        pdf.read_bytes(),
        "pdf",
        url=None,
        method="dropin",
        dropin=True,
    )
    code, out = run(
        capsys, cat, "find", "BASE", "sensor formula", "--version", "1.4.0-local"
    )
    assert code == 0, out
    lines = out.strip().splitlines()
    assert SKIP_NOTE not in lines
    # the drop-in is extracted by this find, so its "extracted" line comes first
    hits = [ln for ln in lines if " p.1 | " in ln]
    assert hits == [
        "PDR p.1 | - | pdr sensor formula",
        "BASE p.1 | - | local sensor formula",
    ], out


# ------------------------------------------------------------- AC-7 no key


def test_without_the_key_every_version_searches_the_companion(
    library, served, tmp_path, capsys
):
    cat = tmp_path / "plain.toml"
    cat.write_text(
        catalog_text('searched_with = ["PDR"]'), encoding="utf-8", newline=""
    )
    code, out = find(capsys, cat, "--version", "1.3.1")
    assert code == 0, out
    hits = [ln for ln in out.strip().splitlines() if not ln.startswith("note: ")]
    assert hits == [
        "PDR p.1 | - | pdr sensor formula",
        "BASE p.1 | - | base 1.3.1 sensor formula",
    ], out
    assert "not searched" not in out


# ------------------------------------------------------------- AC-8 docs


def test_docs_and_skill_describe_the_version_bound():
    from tests.conftest import ROOT

    catalog_doc = (ROOT / "docs" / "CATALOG.md").read_text("utf-8")
    commands = (ROOT / "docs" / "COMMANDS.md").read_text("utf-8")
    skill = (ROOT / "skills" / "bmc-spec" / "SKILL.md").read_text("utf-8")
    assert "`searched_with_from`" in catalog_doc
    assert "`searched_with_from`" in commands
    assert "not searched: it goes with" in commands
    find_row = next(ln for ln in skill.splitlines() if ln.startswith("| `find DOC"))
    assert "DSP0251 for DSP0248 from 1.4.0" in find_row
    assert "`note:` instead" in find_row

"""Reviewer acceptance tests for ``searched_with_from``: a companion is
searched only when ``find`` reads the version the catalog names or a later
one. Black-box through the CLI on a synthetic catalog whose base document
lists two versions before the bound, the bound, and one after it.

AC-1 the catalog key and its errors; AC-2 the shipped DSP0248 entry;
AC-3 the bound and later versions search the companion first; AC-4 an
earlier version searches alone with a note, also when the companion is
already held; AC-5 the version compared is the one actually read (offline
and failed-download fallbacks); AC-6 a hand-added version the catalog does
not list; AC-7 entries without the key keep every version's companions.
"""

import tomllib

import pytest

from bmc_toolkit.spec.catalog import CatalogError, load_catalog, parse_catalog
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")

BASE_VERSIONS = ("1.2.0", "1.3.0", "1.4.0", "1.5.0")
BASE_URL = "https://example.test/base_{}.pdf"
ADD_URL = "https://example.test/add_1.0.0.pdf"
WITH_FROM = 'searched_with = ["ADD"]\nsearched_with_from = "1.4.0"'
SKIP_NOTE = "note: ADD not searched: it goes with BASE from 1.4.0"


def base_hit(version):
    return f"BASE p.1 | - | base {version} shared token"


ADD_HIT = "ADD p.1 | - | add shared token"


def catalog_text(companion=WITH_FROM):
    text = f"""
schema_version = 1

[families.pldm]
title = "PLDM"
publisher = "DMTF"

[[documents]]
id = "BASE"
family = "pldm"
title = "Base document"
access = "open"
fetch = "direct"
{companion}
"""
    for index, version in enumerate(BASE_VERSIONS):
        text += f"""
[[documents.versions]]
version = "{version}"
url = "{BASE_URL.format(version)}"
type = "pdf"
published = "202{index + 2}-06-01"
"""
    text += f"""
[[documents]]
id = "ADD"
family = "pldm"
title = "Addendum"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0.0"
url = "{ADD_URL}"
type = "pdf"
published = "2026-03-01"
"""
    return text


def parse(text):
    return parse_catalog(tomllib.loads(text))


def write_catalog(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8", newline="")
    return path


@pytest.fixture
def cat(tmp_path):
    return write_catalog(tmp_path, "withfrom.toml", catalog_text())


@pytest.fixture
def served(scripted, tmp_path):
    """Every BASE version and ADD are served; all hold 'shared token'."""
    for version in BASE_VERSIONS:
        pdf = pdfgen.write_pdf(
            tmp_path / f"base_{version}.pdf",
            [pdfgen.plain_page([f"base {version} shared token", "filler"])],
        )
        scripted.responses[BASE_URL.format(version)] = ok(pdf.read_bytes())
    pdf = pdfgen.write_pdf(
        tmp_path / "add.pdf", [pdfgen.plain_page(["add shared token", "filler"])]
    )
    scripted.responses[ADD_URL] = ok(pdf.read_bytes())
    return scripted


def run(capsys, cat, *argv):
    code = main(["--catalog", str(cat), *argv])
    return code, capsys.readouterr().out


def ready(capsys, cat, document, version):
    """Fetch and extract one version so a later find prints only its answer."""
    code, out = run(capsys, cat, "fetch", document, "--version", version)
    assert code == 0, out


def split(out):
    lines = out.strip().splitlines()
    notes = [ln for ln in lines if ln.startswith("note: ")]
    rest = [ln for ln in lines if not ln.startswith("note: ")]
    return lines, notes, rest


# ------------------------------------------------------------ AC-1 catalog


def test_ac1_the_key_is_optional_and_read_as_a_string():
    assert parse(catalog_text()).get("BASE").searched_with_from == "1.4.0"
    assert parse(catalog_text()).get("BASE").searched_with == ("ADD",)
    plain = parse(catalog_text('searched_with = ["ADD"]'))
    assert plain.get("BASE").searched_with_from == ""
    assert parse(catalog_text("")).get("BASE").searched_with_from == ""


def test_ac1_the_bound_may_be_the_first_listed_version():
    text = catalog_text('searched_with = ["ADD"]\nsearched_with_from = "1.2.0"')
    assert parse(text).get("BASE").searched_with_from == "1.2.0"


@pytest.mark.parametrize(
    "companion, fragment",
    [
        ('searched_with = ["ADD"]\nsearched_with_from = 140', "expected str"),
        ('searched_with = ["ADD"]\nsearched_with_from = true', "expected str"),
        ('searched_with_from = "1.4.0"', "searched_with"),
        ('searched_with = []\nsearched_with_from = "1.4.0"', "searched_with"),
        ('searched_with = ["ADD"]\nsearched_with_from = "1.4"', "1.4"),
        ('searched_with = ["ADD"]\nsearched_with_from = "1.0.0"', "1.0.0"),
    ],
    ids=[
        "integer",
        "boolean",
        "no-searched-with",
        "empty-searched-with",
        "unknown-version",
        "companion-version-not-own",
    ],
)
def test_ac1_a_bad_key_is_a_catalog_error_naming_it(companion, fragment):
    with pytest.raises(CatalogError) as exc:
        parse(catalog_text(companion))
    message = str(exc.value)
    assert "searched_with_from" in message
    assert fragment in message


# ------------------------------------------------------------ AC-2 shipped


def test_ac2_only_dsp0248_carries_the_key_and_says_1_4_0():
    shipped = load_catalog()
    doc = shipped.get("DSP0248")
    assert doc.searched_with == ("DSP0251",)
    assert doc.searched_with_from == "1.4.0"
    assert doc.find_version("1.4.0") is not None
    assert [d.id for d in shipped.documents if d.searched_with_from] == ["DSP0248"]
    # every other companion list is as before this change
    assert shipped.get("IPMI").searched_with == ("IPMI-UPDATE",)
    assert shipped.get("SFF-8472").searched_with == ("SFF-8024",)
    assert shipped.get("DICE-HW").searched_with == ("DICE-ATT",)
    assert shipped.get("DSP0251").searched_with == ()


# -------------------------------------------------- AC-3 the bound and later


@pytest.mark.parametrize(
    "argv, version",
    [
        ((), "1.5.0"),
        (("--version", "1.5.0"), "1.5.0"),
        (("--version", "1.4.0"), "1.4.0"),
    ],
    ids=["latest", "after", "bound"],
)
def test_ac3_the_bound_and_later_versions_search_the_companion_first(
    library, served, cat, capsys, argv, version
):
    ready(capsys, cat, "BASE", version)
    code, out = run(capsys, cat, "find", "BASE", "shared token", *argv)
    assert code == 0, out
    lines, notes, hits = split(out)
    assert any(n.startswith("note: fetched ADD 1.0.0") for n in notes), out
    assert SKIP_NOTE not in lines
    assert hits == [ADD_HIT, base_hit(version)], out
    assert ADD_URL in served.calls
    assert library.find("ADD", "1.0.0") is not None


# --------------------------------------------------- AC-4 earlier versions


@pytest.mark.parametrize(
    "version", ["1.3.0", "1.2.0"], ids=["one-before", "two-before"]
)
def test_ac4_an_earlier_version_is_searched_alone_with_one_note_first(
    library, served, cat, capsys, version
):
    ready(capsys, cat, "BASE", version)
    code, out = run(capsys, cat, "find", "BASE", "shared token", "--version", version)
    assert code == 0, out
    assert out.strip().splitlines() == [SKIP_NOTE, base_hit(version)]
    # the companion was neither downloaded nor stored
    assert ADD_URL not in served.calls
    assert library.find("ADD", "1.0.0") is None


def test_ac4_a_held_companion_is_still_left_out_of_an_earlier_version(
    library, served, cat, capsys
):
    ready(capsys, cat, "ADD", "1.0.0")
    ready(capsys, cat, "BASE", "1.3.0")
    code, out = run(capsys, cat, "find", "BASE", "shared token", "--version", "1.3.0")
    assert code == 0, out
    assert out.strip().splitlines() == [SKIP_NOTE, base_hit("1.3.0")]
    # a pattern only the companion holds finds nothing from 1.3.0
    code, out = run(capsys, cat, "find", "BASE", "add shared", "--version", "1.3.0")
    assert code == 0, out
    assert out.strip().splitlines() == [SKIP_NOTE, "no hits"]
    # and the same pattern from the bound reaches it
    ready(capsys, cat, "BASE", "1.4.0")
    code, out = run(capsys, cat, "find", "BASE", "add shared", "--version", "1.4.0")
    assert code == 0, out
    assert out.strip().splitlines() == [ADD_HIT]


def test_ac4_only_prints_neither_the_note_nor_companion_hits(
    library, served, cat, capsys
):
    ready(capsys, cat, "BASE", "1.3.0")
    code, out = run(
        capsys, cat, "find", "BASE", "shared token", "--version", "1.3.0", "--only"
    )
    assert code == 0, out
    assert out.strip().splitlines() == [base_hit("1.3.0")]
    assert "not searched" not in out
    # --only on the bound still skips the companion without any note
    ready(capsys, cat, "BASE", "1.4.0")
    code, out = run(
        capsys, cat, "find", "BASE", "shared token", "--version", "1.4.0", "--only"
    )
    assert code == 0, out
    assert out.strip().splitlines() == [base_hit("1.4.0")]


# ------------------------------------------- AC-5 the version actually read


def test_ac5_offline_fallback_to_an_earlier_held_version_skips_the_companion(
    library, served, cat, capsys
):
    ready(capsys, cat, "BASE", "1.3.0")
    (library.root / "config.toml").write_text(
        "[library]\noffline = true\n", encoding="utf-8", newline=""
    )
    before = list(served.calls)
    code, out = run(capsys, cat, "find", "BASE", "shared token")
    assert code == 0, out
    lines, notes, hits = split(out)
    assert any("answering from held 1.3.0" in n for n in notes), out
    assert SKIP_NOTE in notes
    held = next(i for i, n in enumerate(notes) if "answering from held" in n)
    assert notes.index(SKIP_NOTE) > held
    assert hits == [base_hit("1.3.0")]
    assert served.calls == before


def test_ac5_failed_download_fallback_to_an_earlier_held_version_skips_it(
    library, served, cat, capsys
):
    ready(capsys, cat, "BASE", "1.3.0")
    served.responses.pop(BASE_URL.format("1.5.0"))  # the Latest is unreachable
    code, out = run(capsys, cat, "find", "BASE", "shared token")
    assert code == 0, out
    lines, notes, hits = split(out)
    assert any("answering from held 1.3.0" in n for n in notes), out
    assert SKIP_NOTE in notes
    assert hits == [base_hit("1.3.0")]
    assert ADD_URL not in served.calls


def test_ac5_offline_with_the_bound_held_still_searches_a_held_companion(
    library, served, cat, capsys
):
    ready(capsys, cat, "ADD", "1.0.0")
    ready(capsys, cat, "BASE", "1.4.0")
    (library.root / "config.toml").write_text(
        "[library]\noffline = true\n", encoding="utf-8", newline=""
    )
    code, out = run(capsys, cat, "find", "BASE", "shared token")
    assert code == 0, out
    lines, notes, hits = split(out)
    assert any("answering from held 1.4.0" in n for n in notes), out
    assert SKIP_NOTE not in lines
    assert hits == [ADD_HIT, base_hit("1.4.0")]


# ------------------------------------------------------ AC-6 unlisted held


def test_ac6_a_version_the_catalog_does_not_list_searches_the_companion(
    library, served, cat, capsys, tmp_path
):
    pdf = pdfgen.write_pdf(
        tmp_path / "local.pdf", [pdfgen.plain_page(["base local shared token"])]
    )
    library.store(
        "pldm",
        "BASE",
        "1.3.0-draft",
        pdf.read_bytes(),
        "pdf",
        url=None,
        method="dropin",
        dropin=True,
    )
    code, out = run(
        capsys, cat, "find", "BASE", "shared token", "--version", "1.3.0-draft"
    )
    assert code == 0, out
    lines, notes, rest = split(out)
    assert SKIP_NOTE not in lines
    assert any(n.startswith("note: fetched ADD 1.0.0") for n in notes), out
    hits = [ln for ln in rest if " p.1 | " in ln]
    assert hits == [ADD_HIT, "BASE p.1 | - | base local shared token"], out


# ------------------------------------------------------------ AC-7 no key


@pytest.mark.parametrize("version", ["1.2.0", "1.3.0", "1.5.0"])
def test_ac7_without_the_key_every_version_searches_the_companion(
    library, served, tmp_path, capsys, version
):
    text = catalog_text('searched_with = ["ADD"]')
    cat = write_catalog(tmp_path, "plain.toml", text)
    ready(capsys, cat, "BASE", version)
    code, out = run(capsys, cat, "find", "BASE", "shared token", "--version", version)
    assert code == 0, out
    lines, notes, hits = split(out)
    assert hits == [ADD_HIT, base_hit(version)], out
    assert "not searched" not in out

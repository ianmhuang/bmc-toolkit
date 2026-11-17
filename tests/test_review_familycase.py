"""Review tests for `catalog --family` in any case (T79): a family id is
matched whatever case and surrounding whitespace the caller writes (AC-1), a
miss exits 2 and names every family id in catalog order (AC-2), a catalog
whose family ids differ only in case does not load (AC-3), the lookup is a
`Catalog` method that `by_family` and `cmd_catalog` share (AC-4), and
`--table` with `--family` keeps its own message (AC-5). A hand-written
catalog with a mixed-case family id and a family without documents, plus the
shipped catalog; no network, no Library."""

import tomllib
from pathlib import Path

import pytest

from bmc_toolkit.spec.catalog import Catalog, CatalogError, load_catalog, parse_catalog
from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ROOT / "bmc_toolkit" / "spec" / "catalog.toml"
TABLE_MESSAGE = "--table prints every document; drop the document id or --family\n"
FAMILY_IDS = ["mctp", "Ocp-NIC", "empty"]

CATALOG = """
schema_version = 1

[families.mctp]
title = "MCTP"
publisher = "DMTF"

[families.Ocp-NIC]
title = "OCP NIC"
publisher = "OCP"

[families.empty]
title = "No documents yet"
publisher = "nobody"

[[documents]]
id = "DSP0236"
family = "mctp"
title = "MCTP Base Specification"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.3.3"
url = "https://example.test/DSP0236_1.3.3.pdf"
type = "pdf"
published = "2024-03-25"

[[documents]]
id = "NIC30"
family = "Ocp-NIC"
title = "NIC 3.0 Design Specification"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.4"
url = "https://example.test/nic30_1.4.pdf"
type = "pdf"
published = "2025-02-03"

[[documents]]
id = "DSP0237"
family = "mctp"
title = "MCTP SMBus/I2C Transport Binding"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.2.0"
url = "https://example.test/DSP0237_1.2.0.pdf"
type = "pdf"
published = "2020-05-01"
"""


@pytest.fixture
def cat_file(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(CATALOG, encoding="utf-8", newline="")
    return path


def run(capsys, *argv, catalog_file=None):
    prefix = ["--catalog", str(catalog_file)] if catalog_file else []
    code = main([*prefix, *argv])
    return code, capsys.readouterr().out


def doc_ids(out):
    return [line.split("\t")[1] for line in out.splitlines()]


def family_column(out):
    return {line.split("\t")[0] for line in out.splitlines()}


def listed(out, name):
    """The family ids a miss lists, after checking that it is one line that
    starts with the AC-2 wording for NAME."""
    head = f"unknown family '{name}'; families: "
    assert out.startswith(head), out
    assert out.endswith("\n") and out.count("\n") == 1, out
    return [fid.strip() for fid in out.removeprefix(head).split(",")]


def catalog_of(*family_ids):
    """A decoded catalog holding only these families, in this order."""
    return {
        "schema_version": 1,
        "families": {fid: {"title": "T", "publisher": "P"} for fid in family_ids},
        "documents": [],
    }


# ---------------------------------------------------------------- AC-1


@pytest.mark.parametrize("name", ["MCTP", "Mctp", "mCtP", " mctp ", "\tMCTP  "])
def test_a_family_answers_in_any_case_and_with_whitespace(capsys, cat_file, name):
    code, exact = run(capsys, "catalog", "--family", "mctp", catalog_file=cat_file)
    assert code == 0
    assert doc_ids(exact) == ["DSP0236", "DSP0237"]
    code, out = run(capsys, "catalog", "--family", name, catalog_file=cat_file)
    assert code == 0, out
    assert out == exact
    assert family_column(out) == {"mctp"}


@pytest.mark.parametrize("name", ["ocp-nic", "OCP-NIC", "Ocp-Nic", " ocp-NIC "])
def test_a_mixed_case_catalog_id_keeps_its_spelling(capsys, cat_file, name):
    code, exact = run(capsys, "catalog", "--family", "Ocp-NIC", catalog_file=cat_file)
    assert code == 0
    assert doc_ids(exact) == ["NIC30"]
    code, out = run(capsys, "catalog", "--family", name, catalog_file=cat_file)
    assert code == 0, out
    assert out == exact
    assert family_column(out) == {"Ocp-NIC"}


def test_a_family_without_documents_is_a_hit_that_prints_nothing(capsys, cat_file):
    for name in ("empty", "EMPTY", " Empty "):
        code, out = run(capsys, "catalog", "--family", name, catalog_file=cat_file)
        assert (code, out) == (0, ""), name


def test_the_shipped_catalog_answers_to_the_spellings_of_the_request(capsys):
    spellings = (
        ("OData", "odata"),
        ("ODATA", "odata"),
        (" odata ", "odata"),
        ("Redfish", "redfish"),
        ("PLDM", "pldm"),
    )
    for written, fid in spellings:
        code, exact = run(capsys, "catalog", "--family", fid)
        assert code == 0 and exact, fid
        assert family_column(exact) == {fid}
        assert run(capsys, "catalog", "--family", written) == (0, exact), written


# ---------------------------------------------------------------- AC-2


@pytest.mark.parametrize(
    "name", ["nope", "DMTF", "OCP", "OCP NIC", "mct", "mctp2", "ocp_nic", "m ctp"]
)
def test_a_miss_exits_2_and_lists_the_family_ids_in_catalog_order(
    capsys, cat_file, name
):
    code, out = run(capsys, "catalog", "--family", name, catalog_file=cat_file)
    assert code == 2, out
    assert listed(out, name) == FAMILY_IDS


@pytest.mark.parametrize("name", ["", "   ", "\t"])
def test_an_empty_family_is_a_miss_not_the_whole_catalog(capsys, cat_file, name):
    code, everything = run(capsys, "catalog", catalog_file=cat_file)
    assert code == 0
    assert doc_ids(everything) == ["DSP0236", "NIC30", "DSP0237"]
    code, out = run(capsys, "catalog", "--family", name, catalog_file=cat_file)
    assert code == 2, out
    assert listed(out, name) == FAMILY_IDS


def test_a_miss_on_the_shipped_catalog_lists_every_family_in_file_order(capsys):
    with open(SHIPPED, "rb") as fh:
        wanted = list(tomllib.load(fh)["families"])
    assert "odata" in wanted and "redfish" in wanted
    for name in ("DMTF", "oasis"):
        code, out = run(capsys, "catalog", "--family", name)
        assert code == 2, out
        assert listed(out, name) == wanted


# ---------------------------------------------------------------- AC-3


@pytest.mark.parametrize(
    ("first", "second"),
    [("mctp", "MCTP"), ("MCTP", "mctp"), ("Ocp-NIC", "ocp-nic"), ("odata", "OData")],
)
def test_family_ids_differing_only_in_case_do_not_load(first, second):
    near = parse_catalog(catalog_of(first, "other", first + "2"))
    assert list(near.families) == [first, "other", first + "2"]
    with pytest.raises(CatalogError) as err:
        parse_catalog(catalog_of(first, "other", second))
    assert second in str(err.value)
    assert "duplicate" in str(err.value)


def test_a_catalog_file_with_a_case_twin_is_refused(tmp_path, cat_file):
    assert list(load_catalog(cat_file).families) == FAMILY_IDS
    head, mark, tail = CATALOG.partition("[[documents]]")
    assert mark
    twin = '[families.MCTP]\ntitle = "Shadow"\npublisher = "x"\n\n'
    path = tmp_path / "twins.toml"
    path.write_text(head + twin + mark + tail, encoding="utf-8", newline="")
    with pytest.raises(CatalogError) as err:
        load_catalog(path)
    assert "MCTP" in str(err.value)
    assert "duplicate" in str(err.value)


def test_the_shipped_catalog_loads_and_every_family_answers_in_upper_case():
    shipped = load_catalog()
    assert len({fid.lower() for fid in shipped.families}) == len(shipped.families)
    for fid, fam in shipped.families.items():
        assert shipped.family(fid.upper()) == fam, fid
        assert shipped.by_family(fid.upper()) == shipped.by_family(fid), fid


# ---------------------------------------------------------------- AC-4


def test_the_lookup_is_a_catalog_method_that_by_family_shares(cat_file):
    catalog = load_catalog(cat_file)
    assert catalog.family("MCTP") == catalog.families["mctp"]
    assert catalog.family("mctp").id == "mctp"
    assert catalog.family(" ocp-nic\t") == catalog.families["Ocp-NIC"]
    assert catalog.family("OCP-NIC").id == "Ocp-NIC"
    assert catalog.family("EMPTY") == catalog.families["empty"]
    for name in ("nope", "DMTF", "mct", "m ctp", "", "  "):
        assert catalog.family(name) is None, name
        assert catalog.by_family(name) == [], name
    for name in ("mctp", "MCTP", " Mctp "):
        assert [d.id for d in catalog.by_family(name)] == ["DSP0236", "DSP0237"], name
    assert [d.id for d in catalog.by_family("ocp-nic")] == ["NIC30"]
    assert catalog.by_family("EMPTY") == []


def test_cmd_catalog_resolves_the_family_through_the_catalog(
    capsys, cat_file, monkeypatch
):
    asked = []
    real = Catalog.family

    def spy(self, name):
        asked.append(name)
        return real(self, name)

    monkeypatch.setattr(Catalog, "family", spy)
    code, out = run(capsys, "catalog", "--family", "MCTP", catalog_file=cat_file)
    assert code == 0, out
    assert doc_ids(out) == ["DSP0236", "DSP0237"]
    assert asked and asked[0].strip().lower() == "mctp"


# ---------------------------------------------------------------- AC-5


def test_table_with_family_keeps_its_message_whatever_the_family(capsys, cat_file):
    for name in ("mctp", "MCTP", " mctp ", "nope", ""):
        code, out = run(
            capsys, "catalog", "--table", "--family", name, catalog_file=cat_file
        )
        assert (code, out) == (2, TABLE_MESSAGE), repr(name)

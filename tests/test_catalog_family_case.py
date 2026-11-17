"""`catalog --family` matches a family id in any case, and a miss names the
family ids (T79). CLI on the mini catalog and on the shipped one; no
network, no Library."""

from pathlib import Path

import pytest

from bmc_toolkit.spec.catalog import CatalogError, load_catalog
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG


def run(capsys, *argv, catalog_file=None):
    prefix = ["--catalog", str(catalog_file)] if catalog_file else []
    code = main([*prefix, *argv])
    return code, capsys.readouterr().out


# ---------------------------------------------------------------- AC-1


@pytest.mark.parametrize("name", ["MCTP", "Mctp", " mctp ", "mctp\t"])
def test_any_case_prints_what_the_id_prints(capsys, catalog_file, name):
    code, exact = run(capsys, "catalog", "--family", "mctp", catalog_file=catalog_file)
    assert code == 0 and exact.strip(), exact
    code, out = run(capsys, "catalog", "--family", name, catalog_file=catalog_file)
    assert code == 0, out
    assert out == exact
    assert all(ln.split("\t")[0] == "mctp" for ln in out.splitlines())


def test_the_shipped_odata_family_answers_to_odata(capsys):
    code, exact = run(capsys, "catalog", "--family", "odata")
    assert code == 0
    ids = [ln.split("\t")[1] for ln in exact.splitlines()]
    assert ids == ["ODATA-PROTOCOL", "ODATA-URL", "ODATA-CSDL", "ODATA-JSON"]
    for name in ("OData", "ODATA"):
        assert run(capsys, "catalog", "--family", name) == (0, exact)
    code, out = run(capsys, "catalog", "--family", "Redfish")
    assert code == 0
    assert out.splitlines() and all(
        ln.startswith("redfish\t") for ln in out.splitlines()
    )


# ---------------------------------------------------------------- AC-2


@pytest.mark.parametrize("name", ["nope", "DMTF", "", "  "])
def test_a_miss_exits_2_and_names_every_family(capsys, catalog_file, name):
    code, out = run(capsys, "catalog", "--family", name, catalog_file=catalog_file)
    assert code == 2
    assert out == f"unknown family '{name}'; families: mctp, ipmi, vendor\n"


def test_the_shipped_miss_lists_the_families_in_catalog_order(capsys):
    code, out = run(capsys, "catalog", "--family", "oasis")
    assert code == 2
    (line,) = out.splitlines()
    head, listed = line.split("; families: ")
    assert head == "unknown family 'oasis'"
    assert listed.split(", ") == list(load_catalog().families)


# ---------------------------------------------------------------- AC-3


def test_family_ids_differing_only_in_case_are_refused(tmp_path):
    path = tmp_path / "catalog.toml"
    text = MINI_CATALOG.replace(
        '[families.ipmi]\ntitle = "IPMI"',
        '[families.MCTP]\ntitle = "Shadow"\npublisher = "x"\n\n'
        '[families.ipmi]\ntitle = "IPMI"',
    )
    assert text != MINI_CATALOG
    path.write_text(text, encoding="utf-8", newline="")
    with pytest.raises(CatalogError) as err:
        load_catalog(path)
    assert "families.MCTP" in str(err.value)
    assert "duplicate" in str(err.value)


def test_the_shipped_catalog_has_no_case_twins():
    families = list(load_catalog().families)
    assert len({f.lower() for f in families}) == len(families)


# ---------------------------------------------------------------- AC-4


def test_catalog_finds_a_family_in_any_case(catalog):
    assert catalog.family("MCTP").id == "mctp"
    assert catalog.family(" Ipmi ").id == "ipmi"
    assert catalog.family("nope") is None
    assert catalog.family("") is None
    assert [d.id for d in catalog.by_family("MCTP")] == [
        d.id for d in catalog.by_family("mctp")
    ]
    assert catalog.by_family("nope") == []


# ---------------------------------------------------------------- AC-5


@pytest.mark.parametrize("name", ["mctp", "MCTP", ""])
def test_table_with_family_keeps_its_message(capsys, catalog_file, name):
    code, out = run(
        capsys, "catalog", "--table", "--family", name, catalog_file=catalog_file
    )
    assert code == 2
    assert out == "--table prints every document; drop the document id or --family\n"


# ---------------------------------------------------------------- AC-6


def test_skill_and_commands_say_any_case():
    root = Path(__file__).resolve().parents[1]
    skill = (root / "skills" / "bmc-spec" / "SKILL.md").read_text("utf-8")
    (row,) = [ln for ln in skill.splitlines() if ln.startswith("| `catalog [DOC]")]
    assert "`--family` takes a family id in any case" in row
    assert "an unknown one exits 2 listing the ids" in row
    commands = (root / "docs" / "COMMANDS.md").read_text("utf-8")
    assert "bmcspec catalog --family pldm   # one family's documents" in commands

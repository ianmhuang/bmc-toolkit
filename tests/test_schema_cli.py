"""The schema command and bundle extraction through the CLI."""

import zipfile

import pytest

from bmc_toolkit.spec.cli import main
from tests.conftest import ok
from tests.test_bundle import MISSING_REF, bundle_bytes

pytest.importorskip("pypdfium2")

URL = "https://example.test/bundle_2026.1.zip"
PDF_URL = "https://example.test/DSP0236_1.3.3.pdf"
THING = "Thing.v1_10_0.json"
REFUSAL = (
    "BUNDLE 2026.1 is a zip bundle; its schemas are read with: bmcspec schema BUNDLE"
)


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def schema(capsys, catalog_file, *argv):
    return run(capsys, "schema", "BUNDLE", *argv, catalog_file=catalog_file)


@pytest.fixture
def fetched(catalog_file, library, scripted, capsys):
    scripted.responses[URL] = ok(bundle_bytes(), ctype="application/zip")
    code, out = run(capsys, "fetch", "BUNDLE", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "BUNDLE" / "2026.1"


@pytest.fixture
def held(fetched, catalog_file, capsys):
    code, out = run(capsys, "extract", "BUNDLE", catalog_file=catalog_file)
    assert code == 0, out
    return fetched


def cite(held, label, file, pointer):
    fields = [
        "cite: mctp",
        "BUNDLE 2026.1",
        label,
        f"file {file}",
        pointer,
        URL,
        str(held),
    ]
    return " | ".join(fields)


# --------------------------------------------------------------- extract


def test_extract_unpacks_and_status_shows_schemas(fetched, catalog_file, capsys):
    code, out = run(capsys, "extract", "BUNDLE", catalog_file=catalog_file)
    assert code == 0
    assert out.startswith("extracted BUNDLE 2026.1: 5 schema files, 4 resources in ")
    assert out.rstrip().endswith("s, 1 unsafe paths refused")
    assert sorted(p.name for p in (fetched / "schemas").iterdir()) == [
        "Common.json",
        "Thing.json",
        THING,
        "ThingCollection.json",
        "odata-v4.json",
    ]
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert "mctp\tBUNDLE\t2026.1\tdirect\t" in out
    assert out.strip().splitlines()[-1].endswith("\textracted\tschemas")
    code, out = run(capsys, "extract", "BUNDLE", catalog_file=catalog_file)
    assert code == 0 and out.strip() == "skipped BUNDLE 2026.1: already extracted"
    code, out = run(capsys, "extract", "BUNDLE", "--force", catalog_file=catalog_file)
    assert code == 0 and out.startswith("extracted BUNDLE 2026.1: 5 schema files")


def test_extract_all_skips_a_zip_without_schemas(held, catalog_file, tmp_path, capsys):
    plain = tmp_path / "registries.zip"
    with zipfile.ZipFile(plain, "w") as zf:
        zf.writestr("Base.1.0.0.json", "{}")
    argv = ["add", str(plain), "--document", "BUNDLE", "--version", "2026.2"]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0, out
    code, out = run(capsys, "extract", "--all", catalog_file=catalog_file)
    assert code == 0, out
    assert (
        "skipped BUNDLE 2026.2: no json-schema/ folder in the archive "
        "(registries and profiles come later)"
    ) in out
    assert "skipped BUNDLE 2026.1: already extracted" in out
    assert out.strip().splitlines()[-1].startswith("summary: ")


def test_a_new_original_removes_the_schemas(held, catalog_file, scripted, capsys):
    assert (held / "schemas").is_dir()
    code, out = run(capsys, "fetch", "BUNDLE", "--force", catalog_file=catalog_file)
    assert code == 0, out
    assert not (held / "schemas").exists()
    assert not (held / "extract.json").exists()


# ---------------------------------------------------------------- schema


def test_schema_lists_resources(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file)
    assert code == 0
    assert out.splitlines() == [
        "Common\t-",
        "odata-v4\t-",
        "Thing\tv1.10.0",
        "ThingCollection\t-",
    ]


def test_schema_resource_prints_cite_and_properties(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "thing")
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == cite(held, "Thing v1.10.0", THING, "#/definitions/Thing")
    assert lines[1] == (
        "schema: Thing v1.10.0 | 10 properties | "
        "definitions: Actions, Level, Reset, Thing"
    )
    assert lines[2] == "@odata.id | odata id | writable | - |"
    assert lines[4] == "Mode | enum Mode | readonly | added v1.2.0 | The mode."
    assert lines[9] == f"Missing | {MISSING_REF} | writable | - | Gone."
    assert len(lines) == 12


def test_schema_property_follows_an_enum_into_another_file(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "Thing", "--property", "mode")
    assert code == 0
    pointer = "#/definitions/Thing/properties/Mode"
    assert out.splitlines() == [
        cite(held, "Thing v1.10.0", THING, pointer),
        "property: Mode | enum Mode | readonly | added v1.2.0",
        "description: The mode.",
        "longDescription: This property shall contain the mode.",
        cite(held, "Common", "Common.json", "#/definitions/Mode"),
        "values:",
        "  Fast: Goes fast.",
        "  Slow: Goes slow. (added v1.2.0)",
    ]


def test_schema_property_with_an_inline_enum_and_notes(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "Thing", "--property", "Level")
    assert code == 0
    lines = out.splitlines()
    assert lines[1] == "property: Level | enum Level | writable | -"
    assert lines[3] == cite(held, "Thing v1.10.0", THING, "#/definitions/Level")
    assert lines[4:] == ["values:", "  Low: Low.", "  High: High."]
    code, out = schema(capsys, catalog_file, "Thing", "--property", "old")
    assert out.splitlines()[1:] == [
        "property: Old | string | writable | -",
        "description: Old name.",
        "deprecated (since v1.9.0): Use Name.",
    ]


def test_schema_definition_prints_enum_or_action(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "Thing", "--definition", "reset")
    assert code == 0
    assert out.splitlines() == [
        cite(held, "Thing v1.10.0", THING, "#/definitions/Reset"),
        "definition: Reset | object",
        "description: Resets the thing.",
        "parameters:",
        "  ResetType | enum Level | required | How.",
        "properties:",
        "  target | string | writable | - | Link",
    ]
    code, out = schema(capsys, catalog_file, "Thing", "--definition", "LEVEL")
    assert code == 0
    assert out.splitlines()[1:] == [
        "definition: Level | enum",
        "values:",
        "  Low: Low.",
        "  High: High.",
    ]


def test_schema_error_paths(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "thin")
    assert code == 2
    assert out.strip() == (
        "no resource named 'thin'; containing it: Thing, ThingCollection"
    )
    code, out = schema(capsys, catalog_file, "zzz")
    assert code == 2
    assert out.strip() == "no resource named 'zzz'; bmcspec schema BUNDLE lists them"
    code, out = schema(capsys, catalog_file, "Thing", "--property", "Nope")
    assert code == 2
    assert out.strip() == (
        "Thing v1.10.0 has no property named 'Nope'; "
        "bmcspec schema BUNDLE Thing lists them"
    )
    code, out = schema(capsys, catalog_file, "Thing", "--definition", "Nope")
    assert code == 2
    assert out.strip() == (
        f"{THING} has no definition named 'Nope'; "
        "bmcspec schema BUNDLE Thing lists them"
    )
    both = ["Thing", "--property", "a", "--definition", "b"]
    code, out = schema(capsys, catalog_file, *both)
    assert code == 2 and out.strip() == "give --property or --definition, not both"
    code, out = run(capsys, "schema", "IPMI", catalog_file=catalog_file)
    assert code == 2
    assert out.strip() == "IPMI is not in the Library; run: bmcspec fetch IPMI"


def test_schema_refuses_pdfs_and_unextracted_bundles(
    fetched, catalog_file, scripted, tmp_path, capsys
):
    code, out = schema(capsys, catalog_file)
    assert code == 2
    assert out.strip() == (
        "BUNDLE 2026.1 is not extracted, or was unpacked by an older version; "
        'run: bmcspec extract BUNDLE --version "2026.1"'
    )
    from tests import pdfgen

    page = pdfgen.plain_page(["one"])
    pdf = pdfgen.write_pdf(tmp_path / "a.pdf", [page]).read_bytes()
    scripted.responses[PDF_URL] = ok(pdf)
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "schema", "DSP0236", catalog_file=catalog_file)
    assert code == 2
    assert out.strip() == (
        "DSP0236 1.3.3 is a PDF document, not a schema bundle; read it with: "
        "bmcspec find DSP0236 PATTERN, or: bmcspec page DSP0236 N"
    )


def test_reading_commands_point_bundles_to_schema(held, catalog_file, capsys):
    for argv in (
        ["find", "BUNDLE", "x"],
        ["section", "BUNDLE", "1"],
        ["page", "BUNDLE", "1"],
        ["table", "BUNDLE", "--page", "1"],
        ["render", "BUNDLE", "--page", "1"],
    ):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 2, argv
        assert out.strip() == REFUSAL, argv


def test_corrupt_schema_file_is_an_error_not_a_traceback(held, catalog_file, capsys):
    (held / "schemas" / THING).write_text("{oops", encoding="utf-8")
    code, out = schema(capsys, catalog_file, "Thing")
    assert code == 1
    assert out.startswith("cannot read the schemas of BUNDLE 2026.1: ")

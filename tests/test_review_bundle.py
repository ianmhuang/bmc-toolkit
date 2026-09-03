"""Acceptance tests for M5 (Redfish schema bundle) through the CLI.

Black-box through ``bmc_toolkit.spec.cli.main``. Bundles enter the Library
with ``add`` (no network, no pypdfium2). The synthetic bundle below is
independent of the author's fixture: a resource with three versions where
numeric order (v1_10_0 > v1_9_0) differs from string order, an index-only
collection, enums in the same and in another file, an action with
parameters, a ``$ref`` to a file the unpack does not keep, junk outside
and inside ``json-schema/`` and two members whose path escapes.
"""

import io
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmc_toolkit.spec import cli  # noqa: E402
from bmc_toolkit.spec.search import USER_PROVIDED  # noqa: E402

FOLDER = "DSP8010_2026.1/json-schema"
BASE = "http://redfish.dmtf.org/schemas/v1/"
NEWEST = "Widget.v1_10_0.json"
ABSENT_REF = BASE + "Old.v1_0_0.json#/definitions/Old"
FAKE_PDF = b"%PDF-1.4\n%not really\n" + b"x" * 64


def ref(target):
    return {"$ref": BASE + target}


def old_widget(props):
    return {"definitions": {"Widget": {"type": "object", "properties": props}}}


SCHEMAS = {
    "Widget.json": {
        "definitions": {
            "Widget": {
                "anyOf": [
                    ref("Widget.v1_0_0.json#/definitions/Widget"),
                    ref("Widget.v1_9_0.json#/definitions/Widget"),
                    ref("Widget.v1_10_0.json#/definitions/Widget"),
                ]
            }
        }
    },
    "Widget.v1_0_0.json": old_widget({"Old": {"type": "string"}}),
    "Widget.v1_9_0.json": old_widget({"Old": {"type": "string"}}),
    NEWEST: {
        "definitions": {
            "Widget": {
                "type": "object",
                "properties": {
                    "@odata.id": ref("odata-v4.json#/definitions/id"),
                    "Id": {**ref("Resource.json#/definitions/Id"), "readonly": True},
                    "PowerState": {
                        "anyOf": [
                            ref("Resource.json#/definitions/PowerState"),
                            {"type": "null"},
                        ],
                        "readonly": True,
                        "versionAdded": "v1_2_0",
                        "description": "The power state.",
                        "longDescription": "This property shall contain the state.",
                    },
                    "Kind": {
                        "anyOf": [{"$ref": "#/definitions/WidgetType"}, {"type": "null"}],
                        "readonly": True,
                        "description": "The kind.",
                    },
                    "Count": {
                        "type": ["integer", "null"],
                        "readonly": True,
                        "description": "How many.",
                    },
                    "Ratio": {"type": "number", "description": "A ratio."},
                    "Enabled": {"type": "boolean", "description": "On or off."},
                    "Links": {
                        "type": "array",
                        "items": ref("Resource.json#/definitions/Status"),
                        "description": "Statuses.",
                    },
                    "Legacy": {"$ref": ABSENT_REF, "description": "Elsewhere."},
                    "Retired": {
                        "type": "string",
                        "deprecated": "Use Id.",
                        "versionDeprecated": "v1_5_0",
                        "description": "Old id.",
                    },
                    "Description": {
                        **ref("Resource.json#/definitions/Description"),
                        "readonly": True,
                    },
                },
            },
            "WidgetType": {
                "type": "string",
                "enum": ["Small", "Large"],
                "enumDescriptions": {"Small": "A small one.", "Large": "A large one."},
            },
            "Reset": {
                "type": "object",
                "description": "Resets the widget.",
                "parameters": {
                    "ResetType": {
                        **ref("Resource.json#/definitions/PowerState"),
                        "requiredParameter": True,
                        "description": "The new state.",
                    }
                },
            },
        }
    },
    "WidgetCollection.json": {"definitions": {"WidgetCollection": {"anyOf": []}}},
    "Resource.json": {
        "definitions": {
            "Id": {"type": "string", "description": "The identifier."},
            "Description": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "The description.",
            },
            "PowerState": {
                "type": "string",
                "enum": ["On", "Off", "Paused"],
                "enumDescriptions": {
                    "On": "Powered on.",
                    "Off": "Powered off.",
                    "Paused": "Paused.",
                },
                "enumVersionAdded": {"Paused": "v1_13_0"},
            },
            "Status": {"type": "object", "properties": {"Health": {"type": "string"}}},
        }
    },
    "odata-v4.json": {"definitions": {"id": {"type": "string"}}},
}

JUNK = {
    "DSP8010_2026.1/csdl/Widget_v1.xml": b"<xml/>",
    "DSP8010_2026.1/openapi/Widget.v1_10_0.yaml": b"openapi: 3",
    "DSP8010_2026.1/dictionaries/Widget.dict": b"\x00\x01",
    "DSP8010_2026.1/DSP8010_2026.1.pdf": b"%PDF-1.4 fake",
    "DSP8010_2026.1/DSP0268_2026.1.html": b"<html></html>",
    f"{FOLDER}/index.html": b"<html>listing</html>",
    f"{FOLDER}/README.txt": b"readme",
}

ESCAPES = {
    f"{FOLDER}/../../escape.json": b"{}",
    "/json-schema/abs.json": b"{}",
}

KEPT = ["Resource.json", "Widget.json", NEWEST, "WidgetCollection.json", "odata-v4.json"]


def bundle_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in SCHEMAS.items():
            zf.writestr(f"{FOLDER}/{name}", json.dumps(data))
        for name, data in JUNK.items():
            zf.writestr(name, data)
        for name, data in ESCAPES.items():
            zf.writestr(name, data)
    return buf.getvalue()


def registries_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("DSP8011_2026.1/Base.1.21.0.json", "{}")
        zf.writestr("DSP8011_2026.1/README.md", "registries")
    return buf.getvalue()


def run(capsys, catalog_file, *argv):
    code = cli.main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def add(capsys, catalog_file, path, doc, version, *extra):
    argv = ["add", str(path), "--document", doc, "--version", version, *extra]
    code, out = run(capsys, catalog_file, *argv)
    assert code == 0, out


def status_row(capsys, catalog_file, doc, version):
    code, out = run(capsys, catalog_file, "status")
    assert code == 0
    rows = [
        ln.split("\t")
        for ln in out.splitlines()
        if "\t" in ln and ln.split("\t")[1] == doc and ln.split("\t")[2] == version
    ]
    assert len(rows) == 1, out
    return rows[0]


@pytest.fixture
def fetched(catalog_file, library, tmp_path, capsys):
    """The bundle held as BUNDLE 2026.1, not yet extracted."""
    z = tmp_path / "bundle.zip"
    z.write_bytes(bundle_bytes())
    add(capsys, catalog_file, z, "BUNDLE", "2026.1")
    return (library.specs / "mctp" / "BUNDLE" / "2026.1").resolve()


@pytest.fixture
def held(fetched, catalog_file, capsys):
    """The bundle held and extracted."""
    code, out = run(capsys, catalog_file, "extract", "BUNDLE")
    assert code == 0, out
    return fetched


def schema(capsys, catalog_file, *argv):
    return run(capsys, catalog_file, "schema", "BUNDLE", *argv)


def cite(vdir, label, file, pointer):
    return " | ".join(
        [
            "cite: mctp",
            "BUNDLE 2026.1",
            label,
            f"file {file}",
            pointer,
            USER_PROVIDED,
            str(vdir),
        ]
    )


def property_lines(out):
    """The `name | type | ...` lines of a resource listing, keyed by name."""
    lines = out.splitlines()
    assert lines[0].startswith("cite: ")
    body = [ln for ln in lines[1:] if " | " in ln and not ln.startswith("schema:")]
    return {ln.split(" | ")[0]: ln.split(" | ") for ln in body}


# ------------------------------------------------------------------- AC-1


def test_extract_keeps_the_index_and_the_newest_version_only(
    fetched, catalog_file, capsys
):
    code, out = run(capsys, catalog_file, "extract", "BUNDLE")
    assert code == 0, out
    assert out.startswith("extracted BUNDLE 2026.1")
    schemas = fetched / "schemas"
    assert sorted(p.name for p in schemas.iterdir()) == KEPT
    # numeric order: v1_10_0 beat v1_9_0 and v1_0_0
    assert not (schemas / "Widget.v1_9_0.json").exists()
    assert (schemas / NEWEST).read_bytes() == json.dumps(SCHEMAS[NEWEST]).encode()
    # nothing else left the archive, anywhere under the version directory
    written = {p.name for p in fetched.rglob("*") if p.is_file()}
    for junk in JUNK:
        assert Path(junk).name not in written, junk
    assert written == {"meta.json", "original.zip", "extract.json", *KEPT}


def test_extract_json_records_version_counts_and_time(held):
    meta = json.loads((held / "extract.json").read_text("utf-8"))
    assert isinstance(meta["extractor_version"], int)
    assert meta["files"] == len(KEPT)
    assert meta["resources"] == 4  # Resource, Widget, WidgetCollection, odata-v4
    assert isinstance(meta["seconds"], (int, float)) and meta["seconds"] >= 0
    assert not (held / "extract.txt").exists()


def test_status_shows_extracted_with_schemas_in_the_outline_column(
    fetched, catalog_file, capsys
):
    row = status_row(capsys, catalog_file, "BUNDLE", "2026.1")
    assert "extracted" not in row and "schemas" not in row
    assert run(capsys, catalog_file, "extract", "BUNDLE")[0] == 0
    row = status_row(capsys, catalog_file, "BUNDLE", "2026.1")
    assert "extracted" in row
    assert row[-1] == "schemas"
    assert "stale" not in row


def test_second_extract_skips_and_force_redoes(held, catalog_file, capsys):
    newest = held / "schemas" / NEWEST
    old = 1_500_000_000
    os.utime(newest, (old, old))
    stamp = newest.stat().st_mtime_ns
    code, out = run(capsys, catalog_file, "extract", "BUNDLE")
    assert code == 0, out
    assert "skipped" in out.lower()
    assert newest.stat().st_mtime_ns == stamp
    code, out = run(capsys, catalog_file, "extract", "BUNDLE", "--force")
    assert code == 0, out
    assert out.startswith("extracted BUNDLE 2026.1")
    assert newest.stat().st_mtime_ns != stamp
    assert sorted(p.name for p in (held / "schemas").iterdir()) == KEPT


def test_extract_all_includes_bundles(fetched, catalog_file, capsys):
    code, out = run(capsys, catalog_file, "extract", "--all")
    assert code == 0, out
    assert out.strip().splitlines()[-1] == "summary: extracted 1, skipped 0, failed 0"
    assert (fetched / "schemas" / NEWEST).is_file()
    code, out = run(capsys, catalog_file, "extract", "--all")
    assert code == 0, out
    assert out.strip().splitlines()[-1] == "summary: extracted 0, skipped 1, failed 0"


# ------------------------------------------------------------------- AC-2


def test_a_zip_without_json_schema_is_skipped_with_the_reason(
    held, catalog_file, library, tmp_path, capsys
):
    z = tmp_path / "registries.zip"
    z.write_bytes(registries_bytes())
    add(capsys, catalog_file, z, "BUNDLE", "2026.2")
    code, out = run(capsys, catalog_file, "extract", "BUNDLE", "--version", "2026.2")
    assert code == 0, out
    assert out.startswith("skipped BUNDLE 2026.2")
    assert "json-schema" in out
    assert "later" in out.lower()
    vdir = library.specs / "mctp" / "BUNDLE" / "2026.2"
    assert not (vdir / "schemas").exists()
    assert not (vdir / "extract.json").exists()
    row = status_row(capsys, catalog_file, "BUNDLE", "2026.2")
    assert "extracted" not in row
    code, out = run(capsys, catalog_file, "extract", "--all")
    assert code == 0, out
    assert out.strip().splitlines()[-1] == "summary: extracted 0, skipped 2, failed 0"


# ------------------------------------------------------------------- AC-3


def test_schema_lists_resources_with_their_newest_version(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file)
    assert code == 0, out
    rows = dict(ln.split("\t") for ln in out.splitlines())
    assert rows == {
        "odata-v4": "-",
        "Resource": "-",
        "Widget": "v1.10.0",
        "WidgetCollection": "-",
    }
    code, out = schema(capsys, catalog_file, "--version", "2026.1")
    assert code == 0 and "Widget\tv1.10.0" in out


def test_schema_resource_prints_one_property_per_line_with_resolved_types(
    held, catalog_file, capsys
):
    code, out = schema(capsys, catalog_file, "Widget")
    assert code == 0, out
    props = property_lines(out)
    assert props["@odata.id"][1] == "odata id"
    assert props["Id"][1:3] == ["string", "readonly"]
    assert props["Id"][3].startswith("-")  # no versionAdded, no description
    assert props["PowerState"] == [
        "PowerState",
        "enum PowerState",
        "readonly",
        "added v1.2.0",
        "The power state.",
    ]
    assert props["Kind"][1:3] == ["enum WidgetType", "readonly"]
    assert props["Count"][1:3] == ["integer", "readonly"]
    assert props["Ratio"][1:3] == ["number", "writable"]
    assert props["Enabled"][1] == "boolean"
    assert props["Links"][1] == "array of object Status"
    assert props["Legacy"][1] == ABSENT_REF
    assert props["Retired"][1:] == ["string", "writable", "-", "Old id."]
    assert "Old" not in props  # that property exists only in older versions


@pytest.mark.xfail(
    strict=True,
    reason="finding F1: a $ref to a definition that is anyOf[string, null] "
    "reads 'object Description' instead of 'string'",
)
def test_schema_resolves_a_ref_to_a_nullable_primitive_as_the_primitive(
    held, catalog_file, capsys
):
    code, out = schema(capsys, catalog_file, "Widget")
    assert code == 0, out
    assert property_lines(out)["Description"][1] == "string"


# ------------------------------------------------------------------- AC-4


def test_schema_property_prints_notes_and_follows_the_enum_into_another_file(
    held, catalog_file, capsys
):
    code, out = schema(capsys, catalog_file, "Widget", "--property", "PowerState")
    assert code == 0, out
    lines = out.splitlines()
    pointer = "#/definitions/Widget/properties/PowerState"
    assert lines[0] == cite(held, "Widget v1.10.0", NEWEST, pointer)
    head = lines[1]
    assert "PowerState" in head and "readonly" in head and "v1.2.0" in head
    assert "description: The power state." in lines
    assert "longDescription: This property shall contain the state." in lines
    second = cite(held, "Resource", "Resource.json", "#/definitions/PowerState")
    assert second in lines
    values = lines[lines.index(second) + 1 :]
    assert values[0] == "values:"
    assert values[1] == "  On: Powered on."
    assert values[2] == "  Off: Powered off."
    assert values[3].startswith("  Paused: Paused.") and "v1.13.0" in values[3]
    assert len(values) == 4


def test_schema_property_with_an_enum_in_the_same_file_and_a_deprecation(
    held, catalog_file, capsys
):
    code, out = schema(capsys, catalog_file, "Widget", "--property", "Kind")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == cite(
        held, "Widget v1.10.0", NEWEST, "#/definitions/Widget/properties/Kind"
    )
    assert "  Small: A small one." in lines
    assert "  Large: A large one." in lines
    assert "Resource.json" not in out
    code, out = schema(capsys, catalog_file, "Widget", "--property", "Retired")
    assert code == 0, out
    assert "description: Old id." in out
    deprecated = [ln for ln in out.splitlines() if ln.startswith("deprecated")]
    assert len(deprecated) == 1
    assert "Use Id." in deprecated[0] and "v1.5.0" in deprecated[0]
    assert "values:" not in out


def test_schema_definition_prints_an_enum_or_an_action_with_parameters(
    held, catalog_file, capsys
):
    code, out = schema(capsys, catalog_file, "Widget", "--definition", "Reset")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == cite(held, "Widget v1.10.0", NEWEST, "#/definitions/Reset")
    assert "description: Resets the widget." in lines
    assert "parameters:" in lines
    param = lines[lines.index("parameters:") + 1]
    assert param.strip().startswith("ResetType")
    assert "enum PowerState" in param and "required" in param
    assert "The new state." in param
    code, out = schema(capsys, catalog_file, "Widget", "--definition", "WidgetType")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == cite(held, "Widget v1.10.0", NEWEST, "#/definitions/WidgetType")
    assert "values:" in lines
    assert lines[lines.index("values:") + 1 :] == [
        "  Small: A small one.",
        "  Large: A large one.",
    ]


# ------------------------------------------------------------------- AC-5


def test_names_match_case_insensitively(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "widget", "--property", "powerstate")
    assert code == 0, out
    assert "#/definitions/Widget/properties/PowerState" in out.splitlines()[0]
    code, out = schema(capsys, catalog_file, "WIDGET", "--definition", "widgettype")
    assert code == 0, out
    assert "#/definitions/WidgetType" in out.splitlines()[0]


def test_unknown_names_exit_2_with_help(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "widg")
    assert code == 2
    assert "Widget" in out and "WidgetCollection" in out
    code, out = schema(capsys, catalog_file, "zzz")
    assert code == 2
    assert "zzz" in out
    assert "Widget" not in out
    assert "schema BUNDLE" in out
    code, out = schema(capsys, catalog_file, "Widget", "--property", "Nope")
    assert code == 2
    assert "Nope" in out and "schema BUNDLE Widget" in out
    code, out = schema(capsys, catalog_file, "Widget", "--definition", "Nope")
    assert code == 2
    assert "Nope" in out and "schema BUNDLE Widget" in out


# ------------------------------------------------------------------- AC-6


def test_every_block_starts_with_a_cite_line_of_seven_fields(
    held, catalog_file, capsys
):
    for argv in (
        ["Widget"],
        ["Widget", "--property", "Ratio"],
        ["Widget", "--definition", "Reset"],
        ["WidgetCollection"],
    ):
        code, out = schema(capsys, catalog_file, *argv)
        assert code == 0, (argv, out)
        first = out.splitlines()[0]
        assert first.startswith("cite: mctp | BUNDLE 2026.1 | "), argv
        fields = first.split(" | ")
        assert len(fields) == 7, first
        assert fields[3].startswith("file ") and fields[3].endswith(".json")
        assert fields[4].startswith("#/definitions/")
        assert fields[5] == USER_PROVIDED
        assert fields[6] == str(held)
    code, out = schema(capsys, catalog_file, "WidgetCollection")
    assert out.splitlines()[0] == cite(
        held, "WidgetCollection", "WidgetCollection.json", "#/definitions/WidgetCollection"
    )
    code, out = schema(capsys, catalog_file, "Widget", "--property", "Ratio")
    assert out.count("cite: ") == 1  # no enum followed: one cite line only


# ------------------------------------------------------------------- AC-7


def test_reading_commands_refuse_a_bundle_and_point_to_schema(
    held, catalog_file, capsys
):
    for argv in (
        ["find", "BUNDLE", "x"],
        ["section", "BUNDLE", "1"],
        ["page", "BUNDLE", "1"],
        ["table", "BUNDLE", "--page", "1"],
        ["render", "BUNDLE", "--page", "1"],
    ):
        code, out = run(capsys, catalog_file, *argv)
        assert code == 2, (argv, out)
        assert "schema" in out and "BUNDLE" in out, argv
        assert "Traceback" not in out


def test_schema_refuses_a_pdf_and_an_unextracted_bundle(
    fetched, catalog_file, tmp_path, capsys
):
    code, out = schema(capsys, catalog_file, "Widget")
    assert code == 2, out
    assert "extract BUNDLE" in out
    assert "2026.1" in out
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(FAKE_PDF)
    add(capsys, catalog_file, pdf, "DSP0236", "1.3.3")
    code, out = run(capsys, catalog_file, "schema", "DSP0236")
    assert code == 2, out
    assert "find" in out and "page" in out
    code, out = run(capsys, catalog_file, "schema", "IPMI")
    assert code == 2
    assert "IPMI" in out and "fetch" in out


# ------------------------------------------------------------------- AC-8


def test_bundle_module_uses_the_standard_library_only():
    import ast

    source = (ROOT / "bmc_toolkit" / "spec" / "bundle.py").read_text("utf-8")
    tree = ast.parse(source)
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            modules.add((node.module or "").split(".")[0])
    foreign = modules - set(sys.stdlib_module_names) - {"bmc_toolkit"}
    assert not foreign, foreign
    requirements = (ROOT / "requirements.txt").read_text("utf-8").lower()
    assert "zipfile" not in requirements


def test_escaping_member_paths_are_refused(held, library, tmp_path):
    for name in ("escape.json", "abs.json"):
        assert not list(tmp_path.rglob(name)), name
        assert not list(library.root.rglob(name)), name
    assert (held / "schemas" / NEWEST).is_file()


def test_a_corrupt_zip_is_a_message_not_a_traceback(
    catalog_file, library, tmp_path, capsys
):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    add(capsys, catalog_file, bad, "BUNDLE", "2026.1")
    code, out = run(capsys, catalog_file, "extract", "BUNDLE")
    assert code != 0
    assert "failed" in out.lower()
    assert "Traceback" not in out
    vdir = library.specs / "mctp" / "BUNDLE" / "2026.1"
    assert not (vdir / "extract.json").exists()
    row = status_row(capsys, catalog_file, "BUNDLE", "2026.1")
    assert "extracted" not in row
    code, out = run(capsys, catalog_file, "extract", "--all")
    assert code != 0
    assert out.strip().splitlines()[-1].endswith("failed 1")


def test_a_corrupt_schema_file_is_an_exit_1_message(held, catalog_file, capsys):
    (held / "schemas" / NEWEST).write_text("{not json", encoding="utf-8")
    code, out = schema(capsys, catalog_file, "Widget")
    assert code == 1, out
    assert "Traceback" not in out
    assert NEWEST in out or "BUNDLE 2026.1" in out
    (held / "schemas" / "Resource.json").write_text("[]", encoding="utf-8")
    (held / "schemas" / NEWEST).write_text(json.dumps(SCHEMAS[NEWEST]), "utf-8")
    code, out = schema(capsys, catalog_file, "Widget", "--property", "PowerState")
    assert code == 1, out
    assert "Traceback" not in out


# ------------------------------------------------------------------- AC-9


def test_readme_and_skill_describe_the_command_and_the_schemas_directory():
    readme = (ROOT / "README.md").read_text("utf-8")
    assert "schemas/" in readme
    assert "bmcspec.py schema " in readme
    assert "json-schema" in readme.lower() or "JSON Schema" in readme
    skill = (ROOT / "skills" / "bmc-spec" / "SKILL.md").read_text("utf-8")
    rows = [ln for ln in skill.splitlines() if ln.startswith("| `schema ")]
    assert len(rows) == 1, "SKILL.md needs one command row for schema"
    assert "--property" in rows[0] and "--definition" in rows[0]
    assert "schemas/" in skill
    assert "Schema bundle" in skill
    assert "cite:" in skill

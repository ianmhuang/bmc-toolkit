"""Schema bundles: member selection, unpacking, reading resources,
resolving types and enums, the formatting helpers."""

import io
import json
import zipfile

import pytest

from bmc_toolkit.spec import bundle as B

FOLDER = "DSP8010_1.0.0/json-schema"
URL = "http://redfish.dmtf.org/schemas/v1/"


def ref(target: str) -> dict:
    return {"$ref": URL + target}


THING_NEWEST = {
    "$id": URL + "Thing.v1_10_0.json",
    "definitions": {
        "Thing": {
            "type": "object",
            "properties": {
                "@odata.id": ref("odata-v4.json#/definitions/id"),
                "Name": {
                    "type": "string",
                    "readonly": True,
                    "description": "The name.",
                },
                "Mode": {
                    "anyOf": [ref("Common.json#/definitions/Mode"), {"type": "null"}],
                    "readonly": True,
                    "versionAdded": "v1_2_0",
                    "description": "The mode.",
                    "longDescription": "This property shall contain the mode.",
                },
                "Level": {
                    "$ref": "#/definitions/Level",
                    "readonly": False,
                    "description": "The level.",
                },
                "Count": {
                    "type": ["integer", "null"],
                    "readonly": True,
                    "description": "How many.",
                    "units": "count",
                    "minimum": 0,
                },
                "Tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags.",
                },
                "Status": {
                    **ref("Common.json#/definitions/Status"),
                    "description": "Status.",
                },
                "Missing": {
                    **ref("Absent.json#/definitions/Thing"),
                    "description": "Gone.",
                },
                "Old": {
                    "type": "string",
                    "deprecated": "Use Name.",
                    "versionDeprecated": "v1_9_0",
                    "description": "Old name.",
                },
                "Actions": {"$ref": "#/definitions/Actions", "description": "Actions."},
            },
        },
        "Level": {
            "type": "string",
            "enum": ["Low", "High"],
            "enumDescriptions": {"Low": "Low.", "High": "High."},
        },
        "Actions": {
            "type": "object",
            "properties": {"#Thing.Reset": {"$ref": "#/definitions/Reset"}},
        },
        "Reset": {
            "type": "object",
            "description": "Resets the thing.",
            "parameters": {
                "ResetType": {
                    "$ref": "#/definitions/Level",
                    "requiredParameter": True,
                    "description": "How.",
                }
            },
            "properties": {"target": {"type": "string", "description": "Link"}},
        },
    },
}

FILES = {
    "Thing.json": {
        "definitions": {
            "Thing": {
                "anyOf": [
                    ref("Thing.v1_0_0.json#/definitions/Thing"),
                    ref("Thing.v1_10_0.json#/definitions/Thing"),
                ]
            }
        }
    },
    "Thing.v1_0_0.json": {
        "definitions": {"Thing": {"type": "object", "properties": {"Name": {}}}}
    },
    "Thing.v1_2_0.json": {
        "definitions": {"Thing": {"type": "object", "properties": {"Name": {}}}}
    },
    "Thing.v1_10_0.json": THING_NEWEST,
    "ThingCollection.json": {"definitions": {"ThingCollection": {"anyOf": []}}},
    "Common.json": {
        "definitions": {
            "Mode": {
                "type": "string",
                "enum": ["Fast", "Slow"],
                "enumDescriptions": {"Fast": "Goes fast.", "Slow": "Goes slow."},
                "enumVersionAdded": {"Slow": "v1_2_0"},
            },
            "Status": {
                "type": "object",
                "properties": {"Health": {"type": "string"}},
            },
        }
    },
    "odata-v4.json": {"definitions": {"id": {"type": "string"}}},
    "odata.4.0.0.json": {"definitions": {}},  # an odd name: not kept
}

JUNK = {
    "DSP8010_1.0.0/csdl/Thing_v1.xml": b"<xml/>",
    "DSP8010_1.0.0/openapi/Thing.v1_10_0.yaml": b"openapi: 3",
    "DSP8010_1.0.0/dictionaries/Thing.dict": b"\x00",
    "DSP8010_1.0.0/DSP8010_1.0.0.pdf": b"%PDF-1.4",
    "DSP8010_1.0.0/info.json": b"{}",
}

KEPT = [
    "Common.json",
    "Thing.json",
    "Thing.v1_10_0.json",
    "ThingCollection.json",
    "odata-v4.json",
]

MISSING_REF = URL + "Absent.json#/definitions/Thing"


def bundle_bytes(*, folder=FOLDER, escape=True, junk=True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in FILES.items():
            zf.writestr(f"{folder}/{name}", json.dumps(data))
        if junk:
            for name, data in JUNK.items():
                zf.writestr(name, data)
        if escape:
            zf.writestr(f"{folder}/../evil.json", "{}")
    return buf.getvalue()


def unpacked(tmp_path):
    z = tmp_path / "original.zip"
    z.write_bytes(bundle_bytes())
    result = B.unpack(z, tmp_path)
    return B.Schemas(tmp_path), result


def thing(schemas):
    return schemas.main_definition(schemas.resource("Thing"))


# ---------------------------------------------------------------- unpack


def test_versions_order_numerically():
    assert B.version_key("Thing.v1_10_0.json") > B.version_key("Thing.v1_2_0.json")
    assert B.version_key("Thing.json") is None
    assert B.version_label("Chassis.v1_28_0.json") == "v1.28.0"
    assert B.version_label("Chassis.json") is None
    assert B.resource_name("Chassis.v1_28_0.json") == "Chassis"
    assert B.resource_name("odata-v4.json") == "odata-v4"
    assert B.resource_name("odata.4.0.0.json") is None


def test_select_members_keeps_the_index_and_the_newest_version_only():
    with zipfile.ZipFile(io.BytesIO(bundle_bytes())) as zf:
        kept, refused = B.select_members(zf.namelist())
    assert sorted(k.split("/")[-1] for k in kept) == KEPT
    assert refused == 1
    with pytest.raises(B.NoSchemas):
        B.select_members(list(JUNK))


def test_unpack_writes_only_the_selected_files_and_the_meta(tmp_path):
    schemas, result = unpacked(tmp_path)
    assert (result.files, result.resources, result.refused) == (5, 4, 1)
    assert sorted(p.name for p in (tmp_path / "schemas").iterdir()) == KEPT
    assert not list(tmp_path.glob("**/*.xml"))
    assert not list(tmp_path.glob("**/*.pdf"))
    meta = json.loads((tmp_path / "extract.json").read_text("utf-8"))
    assert meta["kind"] == "schemas"
    assert meta["extractor_version"] == B.BUNDLE_VERSION
    assert meta["outline_source"] == "schemas"
    assert B.is_current(tmp_path)
    (tmp_path / "schemas" / "stale.json").write_text("{}", encoding="utf-8")
    B.unpack(tmp_path / "original.zip", tmp_path)  # replaces the directory
    assert not (tmp_path / "schemas" / "stale.json").exists()


def test_unpack_refuses_a_corrupt_archive_and_reports_no_schemas(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"PK\x03\x04 not really")
    with pytest.raises(B.BundleError):
        B.unpack(bad, tmp_path)
    assert not B.is_current(tmp_path)
    plain = tmp_path / "plain.zip"
    with zipfile.ZipFile(plain, "w") as zf:
        zf.writestr("Base.1.0.0.json", "{}")
    with pytest.raises(B.NoSchemas):
        B.unpack(plain, tmp_path)


def test_stale_or_foreign_meta_is_not_current(tmp_path):
    unpacked(tmp_path)
    meta_path = tmp_path / "extract.json"
    meta = json.loads(meta_path.read_text("utf-8"))
    meta["extractor_version"] = B.BUNDLE_VERSION + 1
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    assert not B.is_current(tmp_path)
    meta_path.write_text('{"extractor_version": 3}', encoding="utf-8")
    assert B.read_meta(tmp_path) is None  # a PDF extract's meta
    B.remove_schemas(tmp_path)
    assert not (tmp_path / "schemas").exists()


# --------------------------------------------------------------- reading


def test_resources_lookup_and_similar_names(tmp_path):
    schemas, _ = unpacked(tmp_path)
    assert [(r.name, r.version, r.file) for r in schemas.resources()] == [
        ("Common", None, "Common.json"),
        ("odata-v4", None, "odata-v4.json"),
        ("Thing", "v1.10.0", "Thing.v1_10_0.json"),
        ("ThingCollection", None, "ThingCollection.json"),
    ]
    assert schemas.resource("thing").label == "Thing v1.10.0"
    assert schemas.resource("Nope") is None
    assert schemas.similar("thing") == ["Thing", "ThingCollection"]
    assert schemas.similar("zzz") == []


def test_types_resolve_through_anyof_and_refs(tmp_path):
    schemas, _ = unpacked(tmp_path)
    main = thing(schemas)
    assert main.pointer == "#/definitions/Thing"
    assert B.property_lines(schemas, main) == [
        "@odata.id | odata id | writable | - |",
        "Name | string | readonly | - | The name.",
        "Mode | enum Mode | readonly | added v1.2.0 | The mode.",
        "Level | enum Level | writable | - | The level.",
        "Count | integer | readonly | - | How many.",
        "Tags | array of string | writable | - | Tags.",
        "Status | object Status | writable | - | Status.",
        f"Missing | {MISSING_REF} | writable | - | Gone.",
        "Old | string | writable | - | Old name.",
        "Actions | object Actions | writable | - | Actions.",
    ]


def test_enums_are_followed_across_files(tmp_path):
    schemas, _ = unpacked(tmp_path)
    main = thing(schemas)
    mode = schemas.property(main, "mode")
    assert mode.pointer == "#/definitions/Thing/properties/Mode"
    found = schemas.enum_of(mode.node, mode.file, mode.pointer)
    assert (found.file, found.pointer) == ("Common.json", "#/definitions/Mode")
    level = schemas.property(main, "Level")
    found = schemas.enum_of(level.node, level.file, level.pointer)
    assert (found.file, found.pointer) == (main.file, "#/definitions/Level")
    inline = schemas.definition(main.file, "Level")
    found = schemas.enum_of(inline.node, inline.file, inline.pointer)
    assert (found.file, found.pointer) == (main.file, "#/definitions/Level")
    name = schemas.property(main, "Name")
    assert schemas.enum_of(name.node, main.file) is None
    missing = schemas.property(main, "Missing")
    assert schemas.enum_of(missing.node, main.file) is None
    assert schemas.resolve("#/definitions/Nope", main.file) is None
    assert schemas.definition(main.file, "reset").pointer == "#/definitions/Reset"


def test_formatting_helpers(tmp_path):
    schemas, _ = unpacked(tmp_path)
    main = thing(schemas)
    old = schemas.property(main, "Old").node
    assert B.detail_lines(old) == [
        "description: Old name.",
        "deprecated (since v1.9.0): Use Name.",
    ]
    count = schemas.property(main, "Count").node
    assert B.detail_lines(count) == [
        "description: How many.",
        "units: count",
        "minimum: 0",
    ]
    mode = schemas.load("Common.json")["definitions"]["Mode"]
    assert B.enum_lines(mode) == [
        "values:",
        "  Fast: Goes fast.",
        "  Slow: Goes slow. (added v1.2.0)",
    ]
    reset = schemas.definition(main.file, "Reset")
    assert B.parameter_lines(schemas, reset) == [
        "parameters:",
        "  ResetType | enum Level | required | How.",
    ]
    assert B.parameter_lines(schemas, main) == []
    assert B.label_of("Chassis.v1_28_0.json") == "Chassis v1.28.0"
    assert B.label_of("Resource.json") == "Resource"
    assert B.dotted("v1_2_0") == "v1.2.0" and B.dotted(None) == "-"


def test_bad_json_is_a_schema_error(tmp_path):
    schemas, _ = unpacked(tmp_path)
    (tmp_path / "schemas" / "Common.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(B.SchemaError):
        schemas.load("Common.json")
    with pytest.raises(B.SchemaError):
        B.Schemas(tmp_path / "nowhere").files()

"""schema --definition beyond the newest versioned file, and the enum
values of an action's parameters (T35a).

The bundle mirrors DSP8010's shape: an action parameter's enum lives in
`Resource.json` (ResetType), a nested property's enum in the resource's
own unversioned file (`Gadget.json`, BootSource), and only the versioned
file refers to them."""

import io
import json
import zipfile

import pytest

from bmc_toolkit.spec.cli import main
from tests.conftest import ok

pytest.importorskip("pypdfium2")

URL = "https://example.test/bundle_2026.1.zip"
FOLDER = "DSP8010_1.0.0/json-schema"
BASE = "http://redfish.dmtf.org/schemas/v1/"
GADGET = "Gadget.v1_3_0.json"


def ref(target: str) -> dict:
    return {"$ref": BASE + target}


def enum(*values: str) -> dict:
    return {
        "type": "string",
        "enum": list(values),
        "enumDescriptions": {v: f"{v} it." for v in values},
    }


FILES = {
    "Resource.json": {
        "definitions": {
            "ResetType": enum("On", "ForceOff"),
            "Shared2": enum("FromResource"),
        }
    },
    "Resource.v1_2_0.json": {
        "definitions": {
            "Resource": {"type": "object", "properties": {"Id": {"type": "string"}}},
        }
    },
    "Gadget.json": {
        "definitions": {
            "Gadget": {"anyOf": [ref("Gadget.v1_3_0.json#/definitions/Gadget")]},
            "BootSource": enum("Pxe", "Hdd"),
            "Shared": enum("FromIndex"),
            "Shared2": enum("FromIndex"),
        }
    },
    GADGET: {
        "definitions": {
            "Gadget": {
                "type": "object",
                "properties": {
                    "Boot": {"$ref": "#/definitions/Boot", "description": "Boot."},
                    "Actions": {"$ref": "#/definitions/Actions"},
                    "Other": ref("Resource.json#/definitions/Shared2"),
                },
            },
            "Boot": {
                "type": "object",
                "properties": {
                    "BootSourceOverrideTarget": {
                        "anyOf": [
                            ref("Gadget.json#/definitions/BootSource"),
                            {"type": "null"},
                        ],
                        "description": "Where to boot.",
                    }
                },
            },
            "Shared": enum("FromVersioned"),
            "Level": enum("Low", "High"),
            "Actions": {
                "type": "object",
                "properties": {"#Gadget.Reset": {"$ref": "#/definitions/Reset"}},
            },
            "Reset": {
                "type": "object",
                "description": "Resets the gadget.",
                "parameters": {
                    "ResetType": {
                        **ref("Resource.json#/definitions/ResetType"),
                        "description": "The type of reset.",
                    },
                    "Level": {
                        "$ref": "#/definitions/Level",
                        "requiredParameter": True,
                        "description": "How hard.",
                    },
                    "Note": {"type": "string", "description": "A note."},
                    "Missing": {
                        **ref("Absent.json#/definitions/Kind"),
                        "description": "Gone.",
                    },
                },
                "properties": {"target": {"type": "string", "description": "Link"}},
            },
        }
    },
    "Widget.v1_0_0.json": {
        "definitions": {
            "Widget": {
                "type": "object",
                "properties": {
                    "A": ref("Alpha.json#/definitions/Kind"),
                    "B": ref("Beta.json#/definitions/Kind"),
                    "C": ref("Alpha.json#/definitions/Kind"),
                },
            }
        }
    },
    "Alpha.json": {"definitions": {"Kind": enum("A1")}},
    "Beta.json": {"definitions": {"Kind": enum("B1")}},
}


def bundle_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in FILES.items():
            zf.writestr(f"{FOLDER}/{name}", json.dumps(data))
    return buf.getvalue()


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def schema(capsys, catalog_file, *argv):
    return run(capsys, "schema", "BUNDLE", *argv, catalog_file=catalog_file)


@pytest.fixture
def held(catalog_file, library, scripted, capsys):
    scripted.responses[URL] = ok(bundle_bytes(), ctype="application/zip")
    code, out = run(
        capsys, "fetch", "BUNDLE", "--no-extract", catalog_file=catalog_file
    )
    assert code == 0, out
    code, out = run(capsys, "extract", "BUNDLE", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "BUNDLE" / "2026.1"


def cite(held, label, file, pointer):
    fields = ["cite: mctp", "BUNDLE 2026.1", label, f"file {file}", pointer, URL]
    return " | ".join([*fields, str(held)])


def values(*names: str) -> list[str]:
    return ["values:", *(f"  {n}: {n} it." for n in names)]


# ------------------------------------------------------------------ AC-1


def test_definition_in_the_resources_unversioned_file(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "Resource", "--definition", "ResetType")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "Resource", "Resource.json", "#/definitions/ResetType"),
        "definition: ResetType | enum",
        *values("On", "ForceOff"),
    ]
    code, out = schema(capsys, catalog_file, "Gadget", "--definition", "BootSource")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "Gadget", "Gadget.json", "#/definitions/BootSource"),
        "definition: BootSource | enum",
        *values("Pxe", "Hdd"),
    ]


def test_definition_through_a_ref_of_the_versioned_file(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "Gadget", "--definition", "ResetType")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "Resource", "Resource.json", "#/definitions/ResetType"),
        "definition: ResetType | enum",
        *values("On", "ForceOff"),
    ]


def test_lookup_is_case_insensitive(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "gadget", "--definition", "resettype")
    assert code == 0, out
    assert out.splitlines()[0] == cite(
        held, "Resource", "Resource.json", "#/definitions/ResetType"
    )
    code, out = schema(capsys, catalog_file, "GADGET", "--definition", "bootsource")
    assert code == 0, out
    assert out.splitlines()[0] == cite(
        held, "Gadget", "Gadget.json", "#/definitions/BootSource"
    )


def test_versioned_file_first_then_unversioned_then_refs(held, catalog_file, capsys):
    # Shared is in both Gadget files: the versioned one wins
    code, out = schema(capsys, catalog_file, "Gadget", "--definition", "Shared")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == cite(held, "Gadget v1.3.0", GADGET, "#/definitions/Shared")
    assert lines[2:] == values("FromVersioned")
    # Shared2 is in Gadget.json and in Resource.json (which Gadget refers
    # to): the unversioned file wins over the ref
    code, out = schema(capsys, catalog_file, "Gadget", "--definition", "Shared2")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == cite(held, "Gadget", "Gadget.json", "#/definitions/Shared2")
    assert lines[2:] == values("FromIndex")


# ------------------------------------------------------------------ AC-2


def test_two_ref_targets_are_listed_not_printed(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "Widget", "--definition", "kind")
    assert code == 2
    assert "values:" not in out and "cite:" not in out
    assert out.splitlines() == [
        "Widget.v1_0_0.json refers to more than one definition named 'kind'; "
        "read one with:",
        "  bmcspec schema BUNDLE Alpha --definition Kind",
        "  bmcspec schema BUNDLE Beta --definition Kind",
    ]


def test_unknown_definition_keeps_todays_message(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "Gadget", "--definition", "Nope")
    assert code == 2
    assert out.strip() == (
        f"{GADGET} has no definition named 'Nope'; "
        "bmcspec schema BUNDLE Gadget lists them"
    )
    # a ref whose file is not unpacked finds nothing either
    code, out = schema(capsys, catalog_file, "Gadget", "--definition", "Kind")
    assert code == 2
    assert out.strip() == (
        f"{GADGET} has no definition named 'Kind'; "
        "bmcspec schema BUNDLE Gadget lists them"
    )


# ------------------------------------------------------------------ AC-3


def test_action_prints_the_values_of_its_enum_parameters(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "Gadget", "--definition", "Reset")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "Gadget v1.3.0", GADGET, "#/definitions/Reset"),
        "definition: Reset | object",
        "description: Resets the gadget.",
        "parameters:",
        "  ResetType | enum ResetType | optional | The type of reset.",
        "  Level | enum Level | required | How hard.",
        "  Note | string | optional | A note.",
        f"  Missing | {BASE}Absent.json#/definitions/Kind | optional | Gone.",
        "parameter ResetType:",
        cite(held, "Resource", "Resource.json", "#/definitions/ResetType"),
        *values("On", "ForceOff"),
        "parameter Level:",
        cite(held, "Gadget v1.3.0", GADGET, "#/definitions/Level"),
        *values("Low", "High"),
        "properties:",
        "  target | string | writable | - | Link",
    ]


# ------------------------------------------------------------------ AC-4


def test_other_output_is_unchanged(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "Gadget", "--definition", "Boot")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "Gadget v1.3.0", GADGET, "#/definitions/Boot"),
        "definition: Boot | object",
        "properties:",
        "  BootSourceOverrideTarget | enum BootSource | writable | - | Where to boot.",
    ]
    code, out = schema(capsys, catalog_file, "Gadget", "--property", "Other")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "Gadget v1.3.0", GADGET, "#/definitions/Gadget/properties/Other"),
        "property: Other | enum Shared2 | writable | -",
        cite(held, "Resource", "Resource.json", "#/definitions/Shared2"),
        *values("FromResource"),
    ]
    code, out = schema(capsys, catalog_file, "Gadget", "--property", "Nope")
    assert code == 2
    assert out.strip() == (
        "Gadget v1.3.0 has no property named 'Nope'; "
        "bmcspec schema BUNDLE Gadget lists them"
    )

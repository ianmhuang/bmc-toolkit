"""Reviewer acceptance tests for `schema DOC RESOURCE --definition D`
beyond the newest versioned file (T35a AC-1 to AC-4): the unversioned
file, the files the versioned file refers to, the listing when more than
one file has the name, and the enum values printed after an action's
parameters. Hand-written bundle shaped like DSP8010; no network."""

import io
import json
import zipfile

import pytest

from bmc_toolkit.spec.cli import main
from tests.conftest import ok

pytest.importorskip("pypdfium2")

URL = "https://example.test/bundle_2026.1.zip"
FOLDER = "DSP8010_2026.1/json-schema"
BASE = "http://redfish.dmtf.org/schemas/v1/"
SYSTEM = "System.v1_2_0.json"
MANAGER = "Manager.v1_0_0.json"
PAIR = "Pair.v1_0_0.json"
TWIN = "Twin.v1_0_0.json"


def ref(target: str) -> dict:
    return {"$ref": BASE + target}


def enum(values: dict[str, str], **extra) -> dict:
    return {
        "type": "string",
        "enum": list(values),
        "enumDescriptions": dict(values),
        **extra,
    }


RESET_TYPE = enum(
    {"On": "Turn on.", "ForceOff": "Turn off now.", "GracefulRestart": "Restart."},
    enumVersionAdded={"GracefulRestart": "v1_1_0"},
)

FILES = {
    # the common file: an action parameter's enum lives here, as in DSP8010
    "Resource.json": {
        "definitions": {
            "ResetType": RESET_TYPE,
            "Tier": enum({"FromResource": "Resource.json has it."}),
        }
    },
    "Resource.v1_1_0.json": {
        "definitions": {
            "Resource": {"type": "object", "properties": {"Id": {"type": "string"}}}
        }
    },
    # the resource's unversioned file: a nested property's enum lives here
    "System.json": {
        "definitions": {
            "System": {"anyOf": [ref(f"{SYSTEM}#/definitions/System")]},
            "BootSource": enum({"None": "No override.", "Pxe": "PXE.", "Hdd": "Disk."}),
            "Both": enum({"FromIndex": "System.json has it."}),
            "Tier": enum({"FromIndex": "System.json has it."}),
        }
    },
    SYSTEM: {
        "definitions": {
            "System": {
                "type": "object",
                "properties": {
                    "Boot": {"$ref": "#/definitions/Boot", "description": "Boot."},
                    "Actions": {"$ref": "#/definitions/Actions"},
                    "Rank": {
                        **ref("Resource.json#/definitions/Tier"),
                        "readonly": True,
                    },
                },
            },
            "Boot": {
                "type": "object",
                "properties": {
                    "BootSourceOverrideTarget": {
                        "anyOf": [
                            ref("System.json#/definitions/BootSource"),
                            {"type": "null"},
                        ],
                        "description": "Where to boot.",
                    }
                },
            },
            "Both": enum({"FromVersioned": "The versioned file has it."}),
            "Actions": {
                "type": "object",
                "properties": {
                    "#System.Reset": {"$ref": "#/definitions/Reset"},
                    "#System.Noop": {"$ref": "#/definitions/Noop"},
                },
            },
            "Reset": {
                "type": "object",
                "description": "Resets the system.",
                "parameters": {
                    "ResetType": {
                        "anyOf": [
                            ref("Resource.json#/definitions/ResetType"),
                            {"type": "null"},
                        ],
                        "description": "The type of reset.",
                    },
                    "Delay": {"type": "integer", "description": "Seconds to wait."},
                    "Mode": {
                        **enum({"Fast": "Quick.", "Slow": "Careful."}),
                        "requiredParameter": True,
                        "description": "How.",
                    },
                    "Gone": {
                        **ref("Nowhere.json#/definitions/Kind"),
                        "description": "Not unpacked.",
                    },
                },
                "properties": {"target": {"type": "string", "description": "Link"}},
            },
            "Noop": {
                "type": "object",
                "description": "Does nothing.",
                "parameters": {"Note": {"type": "string", "description": "A note."}},
            },
        }
    },
    # a resource without an unversioned file
    MANAGER: {
        "definitions": {
            "Manager": {
                "type": "object",
                "properties": {"Actions": {"$ref": "#/definitions/Actions"}},
            },
            "Actions": {
                "type": "object",
                "properties": {"#Manager.Reset": {"$ref": "#/definitions/Reset"}},
            },
            "Reset": {
                "type": "object",
                "description": "Resets the manager.",
                "parameters": {
                    "ResetType": {
                        **ref("Resource.json#/definitions/ResetType"),
                        "description": "The type of reset.",
                    }
                },
            },
        }
    },
    # an index-only resource (a collection)
    "SystemCollection.json": {
        "definitions": {
            "SystemCollection": {
                "type": "object",
                "properties": {
                    "Members": {
                        "type": "array",
                        "items": ref("System.json#/definitions/System"),
                    }
                },
            }
        }
    },
    # three distinct files define Kind; one of them is referred to twice
    PAIR: {
        "definitions": {
            "Pair": {
                "type": "object",
                "properties": {
                    "A": ref("Left.json#/definitions/Kind"),
                    "B": ref("Right.json#/definitions/Kind"),
                    "C": ref("Left.json#/definitions/Kind"),
                    "D": ref("Middle.json#/definitions/Kind"),
                },
            }
        }
    },
    # two refs onto the same definition: one target, not a listing
    TWIN: {
        "definitions": {
            "Twin": {
                "type": "object",
                "properties": {
                    "A": ref("Left.json#/definitions/Kind"),
                    "B": ref("Left.json#/definitions/Kind"),
                },
            }
        }
    },
    "Left.json": {"definitions": {"Kind": enum({"L": "Left."})}},
    "Middle.json": {"definitions": {"Kind": enum({"M": "Middle."})}},
    "Right.json": {"definitions": {"Kind": enum({"R": "Right."})}},
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


RESET_VALUES = [
    "values:",
    "  On: Turn on.",
    "  ForceOff: Turn off now.",
    "  GracefulRestart: Restart. (added v1.1.0)",
]
RESET_CITE = ("Resource", "Resource.json", "#/definitions/ResetType")


# ------------------------------------------------------------------ AC-1


def test_the_unversioned_file_is_read_after_the_versioned_one(
    held, catalog_file, capsys
):
    # Resource has a versioned file without ResetType; Resource.json has it
    code, out = schema(capsys, catalog_file, "Resource", "--definition", "ResetType")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, *RESET_CITE),
        "definition: ResetType | enum",
        *RESET_VALUES,
    ]
    # a nested property's enum in the resource's own unversioned file
    code, out = schema(capsys, catalog_file, "System", "--definition", "BootSource")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "System", "System.json", "#/definitions/BootSource"),
        "definition: BootSource | enum",
        "values:",
        "  None: No override.",
        "  Pxe: PXE.",
        "  Hdd: Disk.",
    ]


def test_a_file_the_versioned_file_refers_to_is_read_last(held, catalog_file, capsys):
    expected = [cite(held, *RESET_CITE), "definition: ResetType | enum", *RESET_VALUES]
    # through the action parameter's $ref, with an unversioned file present
    code, out = schema(capsys, catalog_file, "System", "--definition", "ResetType")
    assert code == 0, out
    assert out.splitlines() == expected
    # and without one (Manager has no Manager.json)
    code, out = schema(capsys, catalog_file, "Manager", "--definition", "ResetType")
    assert code == 0, out
    assert out.splitlines() == expected


def test_an_index_only_resource_follows_its_refs_too(held, catalog_file, capsys):
    code, out = schema(
        capsys, catalog_file, "SystemCollection", "--definition", "System"
    )
    assert code == 0, out
    assert out.splitlines()[0] == cite(
        held, "System", "System.json", "#/definitions/System"
    )


def test_the_three_steps_are_tried_in_order(held, catalog_file, capsys):
    # Both: versioned file and System.json; the versioned file wins
    code, out = schema(capsys, catalog_file, "System", "--definition", "Both")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "System v1.2.0", SYSTEM, "#/definitions/Both"),
        "definition: Both | enum",
        "values:",
        "  FromVersioned: The versioned file has it.",
    ]
    # Tier: System.json and Resource.json (which the versioned file refers
    # to); the unversioned file wins over the ref
    code, out = schema(capsys, catalog_file, "System", "--definition", "Tier")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "System", "System.json", "#/definitions/Tier"),
        "definition: Tier | enum",
        "values:",
        "  FromIndex: System.json has it.",
    ]


def test_names_stay_case_insensitive_in_every_step(held, catalog_file, capsys):
    for resource, name, first in (
        ("resource", "RESETTYPE", cite(held, *RESET_CITE)),
        (
            "SYSTEM",
            "bootsource",
            cite(held, "System", "System.json", "#/definitions/BootSource"),
        ),
        ("manager", "resetTYPE", cite(held, *RESET_CITE)),
    ):
        code, out = schema(capsys, catalog_file, resource, "--definition", name)
        assert code == 0, (resource, name, out)
        assert out.splitlines()[0] == first, (resource, name)


# ------------------------------------------------------------------ AC-2


def test_several_ref_targets_are_listed_with_a_command_each(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "Pair", "--definition", "Kind")
    assert code == 2
    assert out.splitlines() == [
        f"{PAIR} refers to more than one definition named 'Kind'; read one with:",
        "  bmcspec schema BUNDLE Left --definition Kind",
        "  bmcspec schema BUNDLE Middle --definition Kind",
        "  bmcspec schema BUNDLE Right --definition Kind",
    ]
    assert "values:" not in out and "cite:" not in out
    # every listed command works
    for owner, value in (("Left", "L"), ("Middle", "M"), ("Right", "R")):
        code, out = schema(capsys, catalog_file, owner, "--definition", "Kind")
        assert code == 0, out
        assert out.splitlines()[0] == cite(
            held, owner, f"{owner}.json", "#/definitions/Kind"
        )
        assert out.splitlines()[-1] == f"  {value}: {owner}."


def test_two_refs_onto_one_definition_are_one_target(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "Twin", "--definition", "kind")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "Left", "Left.json", "#/definitions/Kind"),
        "definition: Kind | enum",
        "values:",
        "  L: Left.",
    ]


def test_a_name_no_step_finds_keeps_the_old_message(held, catalog_file, capsys):
    for resource, file in (
        ("System", SYSTEM),
        ("Manager", MANAGER),
        ("SystemCollection", "SystemCollection.json"),
    ):
        code, out = schema(capsys, catalog_file, resource, "--definition", "Nope")
        assert code == 2, resource
        expected = (
            f"{file} has no definition named 'Nope'; "
            f"bmcspec schema BUNDLE {resource} lists them"
        )
        assert out.strip() == expected, resource
    # a $ref whose pointer does not end /definitions/<name> is not a hit
    code, out = schema(capsys, catalog_file, "SystemCollection", "--definition", "Boot")
    assert code == 2
    assert out.strip().startswith(
        "SystemCollection.json has no definition named 'Boot'; "
    )
    # a $ref into a file that is not unpacked finds nothing
    code, out = schema(capsys, catalog_file, "System", "--definition", "Kind")
    assert code == 2
    assert out.strip() == (
        f"{SYSTEM} has no definition named 'Kind'; "
        "bmcspec schema BUNDLE System lists them"
    )


# ------------------------------------------------------------------ AC-3


def test_an_action_prints_the_values_of_each_enum_parameter(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "System", "--definition", "Reset")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "System v1.2.0", SYSTEM, "#/definitions/Reset"),
        "definition: Reset | object",
        "description: Resets the system.",
        "parameters:",
        "  ResetType | enum ResetType | optional | The type of reset.",
        "  Delay | integer | optional | Seconds to wait.",
        "  Mode | enum | required | How.",
        f"  Gone | {BASE}Nowhere.json#/definitions/Kind | optional | Not unpacked.",
        # ResetType: an enum in another file, cited there
        "parameter ResetType:",
        cite(held, *RESET_CITE),
        *RESET_VALUES,
        # Mode: an inline enum, cited at the parameter itself
        "parameter Mode:",
        cite(held, "System v1.2.0", SYSTEM, "#/definitions/Reset/parameters/Mode"),
        "values:",
        "  Fast: Quick.",
        "  Slow: Careful.",
        # Delay (not an enum) and Gone (file not unpacked) add nothing
        "properties:",
        "  target | string | writable | - | Link",
    ]


def test_an_action_without_enum_parameters_adds_nothing(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file, "System", "--definition", "Noop")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "System v1.2.0", SYSTEM, "#/definitions/Noop"),
        "definition: Noop | object",
        "description: Does nothing.",
        "parameters:",
        "  Note | string | optional | A note.",
    ]
    # an action with no `properties` of its own ends after the values
    code, out = schema(capsys, catalog_file, "Manager", "--definition", "Reset")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "Manager v1.0.0", MANAGER, "#/definitions/Reset"),
        "definition: Reset | object",
        "description: Resets the manager.",
        "parameters:",
        "  ResetType | enum ResetType | optional | The type of reset.",
        "parameter ResetType:",
        cite(held, *RESET_CITE),
        *RESET_VALUES,
    ]


# ------------------------------------------------------------------ AC-4


def test_the_rest_of_the_schema_output_is_unchanged(held, catalog_file, capsys):
    code, out = schema(capsys, catalog_file)
    assert code == 0, out
    assert out.splitlines() == [
        "Left\t-",
        "Manager\tv1.0.0",
        "Middle\t-",
        "Pair\tv1.0.0",
        "Resource\tv1.1.0",
        "Right\t-",
        "System\tv1.2.0",
        "SystemCollection\t-",
        "Twin\tv1.0.0",
    ]
    code, out = schema(capsys, catalog_file, "System")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "System v1.2.0", SYSTEM, "#/definitions/System"),
        "schema: System v1.2.0 | 3 properties | "
        "definitions: Actions, Boot, Both, Noop, Reset, System",
        "Boot | object Boot | writable | - | Boot.",
        "Actions | object Actions | writable | - |",
        "Rank | enum Tier | readonly | - |",
    ]
    # a definition of the versioned file that is not an action
    code, out = schema(capsys, catalog_file, "System", "--definition", "Boot")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "System v1.2.0", SYSTEM, "#/definitions/Boot"),
        "definition: Boot | object",
        "properties:",
        "  BootSourceOverrideTarget | enum BootSource | writable | - | Where to boot.",
    ]
    # --property still follows an enum into the file that defines it
    code, out = schema(capsys, catalog_file, "System", "--property", "rank")
    assert code == 0, out
    assert out.splitlines() == [
        cite(held, "System v1.2.0", SYSTEM, "#/definitions/System/properties/Rank"),
        "property: Rank | enum Tier | readonly | -",
        cite(held, "Resource", "Resource.json", "#/definitions/Tier"),
        "values:",
        "  FromResource: Resource.json has it.",
    ]
    # the error paths AC-2 does not name
    code, out = schema(capsys, catalog_file, "System", "--property", "Nope")
    assert code == 2
    assert out.strip() == (
        "System v1.2.0 has no property named 'Nope'; "
        "bmcspec schema BUNDLE System lists them"
    )
    code, out = schema(capsys, catalog_file, "Sys")
    assert code == 2
    assert out.strip() == (
        "no resource named 'Sys'; containing it: System, SystemCollection"
    )
    both = ["System", "--property", "a", "--definition", "b"]
    code, out = schema(capsys, catalog_file, *both)
    assert code == 2 and out.strip() == "give --property or --definition, not both"

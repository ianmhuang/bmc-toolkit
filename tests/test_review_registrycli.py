"""Reviewer acceptance tests for the registries bundle and the profile
bundle through the CLI (M9 AC-7 to AC-10): extract, status, the registry
command's three levels of output, its error paths, and a profile bundle
read as a schema bundle while a schema bundle is unchanged. Hand-written
archives; no network."""

import io
import json
import zipfile

import pytest

from bmc_toolkit.spec import bundle as bundle_mod
from bmc_toolkit.spec.cli import main
from tests.conftest import ok
from tests.test_bundle import KEPT, bundle_bytes

pytest.importorskip("pypdfium2")

BUNDLE_URL = "https://example.test/bundle_2026.1.zip"
PDF_URL = "https://example.test/DSP0236_1.3.3.pdf"

BASE_1_10 = {
    "@odata.type": "#MessageRegistry.v1_7_0.MessageRegistry",
    "Id": "Base.1.10.0",
    "RegistryPrefix": "Base",
    "RegistryVersion": "1.10.0",
    "Messages": {
        "Success": {
            "Description": "Indicates that all conditions of a successful operation "
            "were met.",
            "Message": "The request completed successfully.",
            "Severity": "OK",
            "MessageSeverity": "OK",
            "NumberOfArgs": 0,
            "Resolution": "None.",
        },
        "PropertyMissing": {
            "Description": "Indicates that a required property was not supplied.",
            "LongDescription": "This message shall indicate that a required "
            "property was not supplied as part of the request.",
            "Message": "The property '%1' is a required property and must be "
            "included in the request.",
            "Severity": "Warning",
            "MessageSeverity": "Warning",
            "NumberOfArgs": 1,
            "ParamTypes": ["string"],
            "ArgDescriptions": ["The name of the property."],
            "Resolution": "Ensure that the property is in the request body and "
            "has a valid value.",
        },
        "PropertyValueTypeError": {
            "Description": "Indicates that a property was given the wrong type.",
            "Message": "The value '%1' for the property %2 is not a type that the "
            "property can accept.",
            "Severity": "Warning",
            "MessageSeverity": "Warning",
            "NumberOfArgs": 2,
            "ParamTypes": ["string", "string"],
            "ArgDescriptions": ["The value provided.", "The name of the property."],
            "Resolution": "Correct the value for the property in the request body.",
            "VersionAdded": "1.0.0",
        },
        "CreateFailedMissingReqProperties": {
            "Description": "Indicates that a create was attempted without a "
            "required property.",
            "Message": "The create operation failed because the required property "
            "'%1' was missing.",
            "Severity": "Critical",
            "MessageSeverity": "Critical",
            "NumberOfArgs": 1,
            "ParamTypes": ["string"],
            "ArgDescriptions": ["The name of the required property."],
            "Resolution": "Correct the body to include the property.",
            "Deprecated": "This message was deprecated in favor of `PropertyMissing`.",
            "VersionDeprecated": "1.7.0",
        },
    },
}

BASE_1_11 = {
    "RegistryPrefix": "Base",
    "RegistryVersion": "1.11.0",
    "Messages": {
        "Success": {"Message": "OK.", "MessageSeverity": "OK", "NumberOfArgs": 0},
        "Newer": {"Message": "New in %1.", "MessageSeverity": "OK", "NumberOfArgs": 1},
    },
}

RESOURCE_EVENT = {
    "RegistryPrefix": "ResourceEvent",
    "RegistryVersion": "1.3.0",
    "Messages": {
        "ResourceCreated": {
            "Message": "The resource has been created successfully.",
            "MessageSeverity": "OK",
            "NumberOfArgs": 0,
        }
    },
}


def registries_zip(path, *, base=BASE_1_10):
    """A DSP8011-shaped archive: several versions of Base (1.9 sorts before
    1.10 numerically, after it textually), one ResourceEvent, a privilege
    registry, the HTML and the PDF; some members in a folder, some flat."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("DSP8011_2026.1/Base.1.2.0.json", json.dumps({"Messages": {}}))
        zf.writestr("DSP8011_2026.1/Base.1.9.0.json", json.dumps({"Messages": {}}))
        zf.writestr(f"DSP8011_2026.1/Base.{base['RegistryVersion']}.json", json.dumps(base))
        zf.writestr("ResourceEvent.1.3.0.json", json.dumps(RESOURCE_EVENT))
        zf.writestr("ResourceEvent.1.2.0.json", json.dumps({"Messages": {}}))
        zf.writestr("DSP8011_2026.1/Redfish_1.4.0_PrivilegeRegistry.json", "{}")
        zf.writestr("DSP8011_2026.1/DSP8011_2026.1.html", "<html/>")
        zf.writestr("DSP8011_2026.1/DSP8011_2026.1.pdf", "%PDF-1.4")
    return path


def neither_zip(path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("DSP8011_2026.1/Redfish_1.4.0_PrivilegeRegistry.json", "{}")
        zf.writestr("DSP8011_2026.1/README.md", "nothing to unpack")
    return path


PROFILE = {
    "$id": "http://redfish.dmtf.org/schemas/v1/RedfishInteroperabilityProfile.v1_10_0.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "#RedfishInteroperabilityProfile.v1_10_0",
    "type": "object",
    "properties": {
        "ProfileName": {"type": "string", "description": "The name of this profile."},
        "ProfileVersion": {"type": "string", "description": "The version."},
        "Resources": {"type": "object", "description": "The resources."},
    },
    "definitions": {
        "ReadRequirement": {
            "type": "string",
            "description": "The read requirement for a property.",
            "enum": [
                "Mandatory",
                "Supported",
                "Recommended",
                "IfImplemented",
                "IfPopulated",
                "Conditional",
                "None",
            ],
            "enumDescriptions": {"Mandatory": "Required in every instance."},
        },
        "PropertyProfile": {
            "type": "object",
            "properties": {
                "ReadRequirement": {"$ref": "#/definitions/ReadRequirement"},
            },
        },
    },
}


def profile_zip(path):
    with zipfile.ZipFile(path, "w") as zf:
        folder = "DSP8013_2026.1"
        zf.writestr(
            f"{folder}/RedfishInteroperabilityProfile.v1_10_0.json", json.dumps(PROFILE)
        )
        zf.writestr(f"{folder}/RedfishInteroperabilityProfile.v1_4_1.json", "{}")
        zf.writestr(f"{folder}/DSP8013_2026.1.pdf", "%PDF-1.4")
    return path


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def add(capsys, catalog_file, path, version, *extra):
    argv = ["add", str(path), "--document", "BUNDLE", "--version", version, *extra]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0, out


def registry(capsys, catalog_file, *argv):
    return run(capsys, "registry", "BUNDLE", *argv, catalog_file=catalog_file)


@pytest.fixture
def held(catalog_file, library, tmp_path, capsys):
    """BUNDLE 2026.2: the registries archive, added and extracted."""
    add(capsys, catalog_file, registries_zip(tmp_path / "reg.zip"), "2026.2")
    code, out = run(
        capsys, "extract", "BUNDLE", "--version", "2026.2", catalog_file=catalog_file
    )
    assert code == 0, out
    return library.specs / "mctp" / "BUNDLE" / "2026.2"


@pytest.fixture
def schemas_held(catalog_file, library, scripted, capsys):
    """BUNDLE 2026.1 (the catalog's latest): a schema bundle, extracted."""
    scripted.responses[BUNDLE_URL] = ok(bundle_bytes(), ctype="application/zip")
    for argv in (["fetch", "BUNDLE"], ["extract", "BUNDLE"]):
        code, out = run(capsys, *argv, catalog_file=catalog_file)
        assert code == 0, out
    return library.specs / "mctp" / "BUNDLE" / "2026.1"


def cite(vdir, label, file, pointer):
    return " | ".join(
        [
            "cite: mctp",
            "BUNDLE 2026.2",
            label,
            f"file {file}",
            pointer,
            "user-provided",
            str(vdir),
        ]
    )


# ------------------------------------------------------------------ AC-7


def test_ac7_extract_keeps_the_newest_file_per_registry_flat(
    catalog_file, library, tmp_path, capsys
):
    add(capsys, catalog_file, registries_zip(tmp_path / "reg.zip"), "2026.2")
    code, out = run(
        capsys, "extract", "BUNDLE", "--version", "2026.2", catalog_file=catalog_file
    )
    assert code == 0, out
    assert out.startswith("extracted BUNDLE 2026.2: 2 message registries in ")
    vdir = library.specs / "mctp" / "BUNDLE" / "2026.2"
    assert sorted(p.name for p in (vdir / "registries").iterdir()) == [
        "Base.1.10.0.json",  # 1.10 > 1.9 numerically
        "ResourceEvent.1.3.0.json",
    ]
    assert not (vdir / "schemas").exists()
    written = json.loads((vdir / "registries" / "Base.1.10.0.json").read_text("utf-8"))
    assert written == BASE_1_10  # copied whole, the original left in the ZIP
    meta = json.loads((vdir / "extract.json").read_text("utf-8"))
    assert meta["kind"] == "registries"
    assert meta["outline_source"] == "registries"
    assert meta["files"] == 2


def test_ac7_status_extract_all_and_a_second_extract(held, catalog_file, capsys):
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0, out
    (row,) = [ln for ln in out.splitlines() if "\tBUNDLE\t2026.2\t" in ln]
    assert row.split("\t")[5:7] == ["extracted", "registries"]
    code, out = run(
        capsys, "extract", "BUNDLE", "--version", "2026.2", catalog_file=catalog_file
    )
    assert code == 0
    assert out.strip() == "skipped BUNDLE 2026.2: already extracted"
    code, out = run(capsys, "extract", "--all", catalog_file=catalog_file)
    assert code == 0, out
    assert "skipped BUNDLE 2026.2: already extracted" in out
    assert out.strip().splitlines()[-1] == "summary: extracted 0, skipped 1, failed 0"
    code, out = run(
        capsys,
        "extract",
        "BUNDLE",
        "--version",
        "2026.2",
        "--force",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    assert out.startswith("extracted BUNDLE 2026.2: 2 message registries in ")


def test_ac7_extract_all_unpacks_a_registries_bundle_and_skips_a_zip_with_neither(
    catalog_file, library, tmp_path, capsys
):
    add(capsys, catalog_file, registries_zip(tmp_path / "reg.zip"), "2026.2")
    add(capsys, catalog_file, neither_zip(tmp_path / "plain.zip"), "2026.3")
    code, out = run(capsys, "extract", "--all", catalog_file=catalog_file)
    assert code == 0, out
    assert "extracted BUNDLE 2026.2: 2 message registries in " in out
    (skipped,) = [ln for ln in out.splitlines() if ln.startswith("skipped BUNDLE 2026.3")]
    assert "json-schema" in skipped and "registr" in skipped  # names both kinds
    assert out.strip().splitlines()[-1] == "summary: extracted 1, skipped 1, failed 0"
    plain = library.specs / "mctp" / "BUNDLE" / "2026.3"
    assert not (plain / "registries").exists()
    assert not (plain / "extract.json").exists()


# ------------------------------------------------------------------ AC-8


def test_ac8_registry_lists_the_registries(held, catalog_file, capsys):
    code, out = registry(capsys, catalog_file, "--version", "2026.2")
    assert code == 0, out
    assert out.splitlines() == [
        "Base\t1.10.0\t4 messages",
        "ResourceEvent\t1.3.0\t1 messages",
    ]


def test_ac8_registry_lists_the_messages_of_one_registry(held, catalog_file, capsys):
    code, out = registry(capsys, catalog_file, "BASE", "--version", "2026.2")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == cite(held, "Base 1.10.0", "Base.1.10.0.json", "#/Messages")
    assert lines[1] == "registry: Base 1.10.0 | 4 messages | ids Base.1.10.*"
    rows = [ln.split(" | ") for ln in lines[2:]]
    assert [r[0] for r in rows] == [
        "Success",
        "PropertyMissing",
        "PropertyValueTypeError",
        "CreateFailedMissingReqProperties",
    ]
    assert rows[1] == [
        "PropertyMissing",
        "Warning",
        "The property '%1' is a required property and must be included in the "
        "request.",
    ]
    assert rows[3][1] == "Critical"


def test_ac8_registry_prints_one_message_in_full(held, catalog_file, capsys):
    code, out = registry(
        capsys, catalog_file, "base", "propertymissing", "--version", "2026.2"
    )
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == cite(
        held, "Base 1.10.0", "Base.1.10.0.json", "#/Messages/PropertyMissing"
    )
    assert lines[1] == "message: Base.1.10.PropertyMissing | Warning | 1 arg"
    assert lines[2] == (
        "text: The property '%1' is a required property and must be included in "
        "the request."
    )
    assert "description: Indicates that a required property was not supplied." in lines
    assert (
        "resolution: Ensure that the property is in the request body and has a "
        "valid value."
    ) in lines
    assert lines.index("args:") == len(lines) - 2
    assert lines[-1] == "  %1 | string | The name of the property."
    assert not any(ln.startswith(("added", "deprecated")) for ln in lines)


def test_ac8_full_message_id_arguments_added_and_deprecated(held, catalog_file, capsys):
    code, out = registry(
        capsys,
        catalog_file,
        "Base",
        "Base.1.10.PropertyValueTypeError",
        "--version",
        "2026.2",
    )
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ")[4] == "#/Messages/PropertyValueTypeError"
    assert lines[1] == "message: Base.1.10.PropertyValueTypeError | Warning | 2 args"
    assert (
        "text: The value '%1' for the property %2 is not a type that the property "
        "can accept."
    ) in lines
    assert "  %1 | string | The value provided." in lines
    assert "  %2 | string | The name of the property." in lines
    assert lines[-1] == "added v1.0.0"
    code, out = registry(
        capsys,
        catalog_file,
        "Base",
        "createfailedmissingreqproperties",
        "--version",
        "2026.2",
    )
    assert code == 0, out
    assert out.splitlines()[-1] == (
        "deprecated (since v1.7.0): This message was deprecated in favor of "
        "`PropertyMissing`."
    )


def test_ac8_version_picks_the_bundle_and_the_default_is_the_latest_held(
    held, catalog_file, library, tmp_path, capsys
):
    # only 2026.2 is held: it is the default
    code, out = registry(capsys, catalog_file)
    assert code == 0, out
    assert out.splitlines()[0] == "Base\t1.10.0\t4 messages"
    add(
        capsys,
        catalog_file,
        registries_zip(tmp_path / "reg2.zip", base=BASE_1_11),
        "2026.4",
    )
    code, out = run(
        capsys, "extract", "BUNDLE", "--version", "2026.4", catalog_file=catalog_file
    )
    assert code == 0, out
    code, out = registry(capsys, catalog_file, "Base", "--version", "2026.4")
    assert code == 0, out
    assert out.splitlines()[1] == "registry: Base 1.11.0 | 2 messages | ids Base.1.11.*"
    code, out = registry(capsys, catalog_file, "Base", "--version", "2026.2")
    assert code == 0, out
    assert out.splitlines()[1] == "registry: Base 1.10.0 | 4 messages | ids Base.1.10.*"
    code, out = registry(capsys, catalog_file, "Base", "Newer", "--version", "2026.2")
    assert code == 2  # the older bundle does not know the newer message


# ------------------------------------------------------------------ AC-9


def test_ac9_unknown_registry_and_unknown_message(held, catalog_file, capsys):
    v = ("--version", "2026.2")
    code, out = registry(capsys, catalog_file, "event", *v)
    assert code == 2
    assert out.strip() == "no registry named 'event'; containing it: ResourceEvent"
    code, out = registry(capsys, catalog_file, "Nope", *v)
    assert code == 2
    assert out.strip() == "no registry named 'Nope'; bmcspec registry BUNDLE lists them"
    code, out = registry(capsys, catalog_file, "Base", "missing", *v)
    assert code == 2
    assert out.strip() == (
        "Base 1.10.0 has no message named 'missing'; containing it: "
        "PropertyMissing, CreateFailedMissingReqProperties"
    )
    code, out = registry(capsys, catalog_file, "Base", "Nope", *v)
    assert code == 2
    assert out.strip() == (
        "Base 1.10.0 has no message named 'Nope'; "
        "bmcspec registry BUNDLE Base lists them"
    )
    code, out = run(capsys, "registry", "NOPE", catalog_file=catalog_file)
    assert code == 2
    assert "NOPE is not in the Library" in out
    code, out = registry(capsys, catalog_file, "--version", "9.9")
    assert code == 2
    assert "BUNDLE 9.9 is not in the Library" in out


def test_ac9_schema_and_registry_refuse_each_others_bundle(
    schemas_held, held, catalog_file, capsys
):
    code, out = registry(capsys, catalog_file, "--version", "2026.1")
    assert code == 2
    assert out.strip() == (
        "BUNDLE 2026.1 is a schema bundle, not a registries bundle; read it with: "
        "bmcspec schema BUNDLE"
    )
    code, out = run(
        capsys, "schema", "BUNDLE", "--version", "2026.2", catalog_file=catalog_file
    )
    assert code == 2
    assert out.strip() == (
        "BUNDLE 2026.2 is a registries bundle, not a schema bundle; read it with: "
        "bmcspec registry BUNDLE"
    )
    # the text commands point a registries bundle at registry
    code, out = run(
        capsys, "find", "BUNDLE", "x", "--version", "2026.2", catalog_file=catalog_file
    )
    assert code == 2
    assert out.strip() == (
        "BUNDLE 2026.2 is a zip bundle; its registries are read with: "
        "bmcspec registry BUNDLE"
    )


def test_ac9_pdf_and_unextracted_bundle_get_the_pointers_schema_gives(
    catalog_file, library, scripted, tmp_path, capsys
):
    scripted.responses[PDF_URL] = ok(b"%PDF-1.7\n" + b"x" * 300)
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    code, out = run(capsys, "registry", "DSP0236", catalog_file=catalog_file)
    assert code == 2
    assert out.strip() == (
        "DSP0236 1.3.3 is a PDF document, not a registries bundle; read it with: "
        "bmcspec find DSP0236 PATTERN, or: bmcspec page DSP0236 N"
    )
    code, schema_out = run(capsys, "schema", "DSP0236", catalog_file=catalog_file)
    assert code == 2
    assert schema_out.replace("schema bundle", "registries bundle") == out
    add(capsys, catalog_file, registries_zip(tmp_path / "reg.zip"), "2026.5")
    code, out = registry(capsys, catalog_file, "--version", "2026.5")
    assert code == 2
    assert out.strip() == (
        "BUNDLE 2026.5 is not extracted, or was unpacked by an older version; run: "
        'bmcspec extract BUNDLE --version "2026.5"'
    )


def test_ac9_a_registry_file_that_is_not_json_is_exit_1_and_names_the_file(
    held, catalog_file, capsys
):
    (held / "registries" / "Base.1.10.0.json").write_text("{oops", "utf-8")
    code, out = registry(capsys, catalog_file, "Base", "Success", "--version", "2026.2")
    assert code == 1
    assert out.startswith("cannot read the registries of BUNDLE 2026.2: ")
    assert "Base.1.10.0.json" in out
    assert "Traceback" not in out


# ----------------------------------------------------------------- AC-10


@pytest.fixture
def profile_held(catalog_file, library, tmp_path, capsys):
    add(capsys, catalog_file, profile_zip(tmp_path / "profiles.zip"), "2026.6")
    code, out = run(
        capsys, "extract", "BUNDLE", "--version", "2026.6", catalog_file=catalog_file
    )
    assert code == 0, out
    assert out.startswith("extracted BUNDLE 2026.6: 1 schema files, 1 resources in ")
    return library.specs / "mctp" / "BUNDLE" / "2026.6"


def test_ac10_profile_bundle_keeps_the_newest_profile_schema(
    profile_held, catalog_file, capsys
):
    assert [p.name for p in (profile_held / "schemas").iterdir()] == [
        "RedfishInteroperabilityProfile.v1_10_0.json"
    ]
    assert not (profile_held / "registries").exists()
    meta = json.loads((profile_held / "extract.json").read_text("utf-8"))
    assert meta["kind"] == "schemas"
    code, out = run(
        capsys, "schema", "BUNDLE", "--version", "2026.6", catalog_file=catalog_file
    )
    assert code == 0, out
    assert out.strip() == "RedfishInteroperabilityProfile\tv1.10.0"
    code, out = run(capsys, "status", catalog_file=catalog_file)
    (row,) = [ln for ln in out.splitlines() if "\tBUNDLE\t2026.6\t" in ln]
    assert row.split("\t")[5:7] == ["extracted", "schemas"]


def test_ac10_root_defined_schema_lists_its_properties_and_definitions(
    profile_held, catalog_file, capsys
):
    v = ("--version", "2026.6")
    code, out = run(
        capsys,
        "schema",
        "BUNDLE",
        "redfishinteroperabilityprofile",
        *v,
        catalog_file=catalog_file,
    )
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ") == [
        "cite: mctp",
        "BUNDLE 2026.6",
        "RedfishInteroperabilityProfile v1.10.0",
        "file RedfishInteroperabilityProfile.v1_10_0.json",
        "#",
        "user-provided",
        str(profile_held),
    ]
    assert lines[1] == (
        "schema: RedfishInteroperabilityProfile v1.10.0 | 3 properties | "
        "definitions: PropertyProfile, ReadRequirement"
    )
    assert lines[2:] == [
        "ProfileName | string | writable | - | The name of this profile.",
        "ProfileVersion | string | writable | - | The version.",
        "Resources | object | writable | - | The resources.",
    ]
    code, out = run(
        capsys,
        "schema",
        "BUNDLE",
        "RedfishInteroperabilityProfile",
        "--definition",
        "ReadRequirement",
        *v,
        catalog_file=catalog_file,
    )
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ")[4] == "#/definitions/ReadRequirement"
    assert lines[1] == "definition: ReadRequirement | enum"
    values = [ln.strip().split(":")[0] for ln in lines[lines.index("values:") + 1 :]]
    assert values == [
        "Mandatory",
        "Supported",
        "Recommended",
        "IfImplemented",
        "IfPopulated",
        "Conditional",
        "None",
    ]


def test_ac10_a_schema_bundle_is_unpacked_and_read_as_before(
    schemas_held, catalog_file, capsys
):
    assert bundle_mod.BUNDLE_VERSION == 1
    meta = json.loads((schemas_held / "extract.json").read_text("utf-8"))
    assert meta["extractor_version"] == 1
    assert sorted(p.name for p in (schemas_held / "schemas").iterdir()) == KEPT
    code, out = run(capsys, "schema", "BUNDLE", "Thing", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ")[2:5] == [
        "Thing v1.10.0",
        "file Thing.v1_10_0.json",
        "#/definitions/Thing",
    ]
    assert lines[1].startswith("schema: Thing v1.10.0 | ")
    code, out = run(
        capsys,
        "schema",
        "BUNDLE",
        "Thing",
        "--property",
        "Mode",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    assert out.splitlines()[0].split(" | ")[4] == "#/definitions/Thing/properties/Mode"

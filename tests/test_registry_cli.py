"""The registry command and registries-bundle extraction through the CLI,
and the profile bundle read as a schema bundle."""

import io
import json
import zipfile

import pytest

from bmc_toolkit.spec.cli import main
from tests.conftest import ok
from tests.test_bundle import bundle_bytes
from tests.test_registry import registries_bytes

pytest.importorskip("pypdfium2")

URL = "https://example.test/bundle_2026.1.zip"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def add(capsys, catalog_file, path, version, *extra):
    argv = ["add", str(path), "--document", "BUNDLE", "--version", version, *extra]
    code, out = run(capsys, *argv, catalog_file=catalog_file)
    assert code == 0, out


@pytest.fixture
def schemas_held(catalog_file, library, scripted, capsys):
    """BUNDLE 2026.1: a schema bundle, fetched and extracted."""
    scripted.responses[URL] = ok(bundle_bytes(), ctype="application/zip")
    code, out = run(capsys, "fetch", "BUNDLE", catalog_file=catalog_file)
    assert code == 0, out
    code, out = run(capsys, "extract", "BUNDLE", catalog_file=catalog_file)
    assert code == 0, out
    return library.specs / "mctp" / "BUNDLE" / "2026.1"


@pytest.fixture
def registries_zip(tmp_path):
    z = tmp_path / "registries.zip"
    z.write_bytes(registries_bytes())
    return z


@pytest.fixture
def held(catalog_file, library, registries_zip, capsys):
    """BUNDLE 2026.2: a registries bundle, added and extracted."""
    add(capsys, catalog_file, registries_zip, "2026.2")
    code, out = run(
        capsys, "extract", "BUNDLE", "--version", "2026.2", catalog_file=catalog_file
    )
    assert code == 0, out
    return library.specs / "mctp" / "BUNDLE" / "2026.2"


def registry(capsys, catalog_file, *argv):
    return run(capsys, "registry", "BUNDLE", *argv, catalog_file=catalog_file)


def cite(held, label, file, pointer):
    return " | ".join(
        [
            "cite: mctp",
            "BUNDLE 2026.2",
            label,
            f"file {file}",
            pointer,
            "user-provided",
            str(held),
        ]
    )


# --------------------------------------------------------------- extract


def test_extract_unpacks_registries_and_status_shows_them(
    catalog_file, library, registries_zip, capsys
):
    add(capsys, catalog_file, registries_zip, "2026.2")
    code, out = run(
        capsys, "extract", "BUNDLE", "--version", "2026.2", catalog_file=catalog_file
    )
    assert code == 0, out
    assert out.startswith("extracted BUNDLE 2026.2: 2 message registries in ")
    assert "1 unsafe paths refused, 1 duplicate names dropped" in out
    vdir = library.specs / "mctp" / "BUNDLE" / "2026.2"
    assert sorted(p.name for p in (vdir / "registries").iterdir()) == [
        "Base.1.19.0.json",
        "Update.1.4.0.json",
    ]
    assert not (vdir / "schemas").exists()
    meta = json.loads((vdir / "extract.json").read_text("utf-8"))
    assert meta["kind"] == "registries"
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0
    (row,) = [ln for ln in out.splitlines() if "\tBUNDLE\t2026.2\t" in ln]
    assert row.split("\t")[5:] == ["extracted", "registries"]
    code, out = run(
        capsys, "extract", "BUNDLE", "--version", "2026.2", catalog_file=catalog_file
    )
    assert code == 0
    assert out.strip() == "skipped BUNDLE 2026.2: already extracted"
    code, out = run(
        capsys,
        "extract",
        "BUNDLE",
        "--version",
        "2026.2",
        "--force",
        catalog_file=catalog_file,
    )
    assert code == 0
    assert out.startswith("extracted BUNDLE 2026.2: 2 message registries")


def test_extract_all_skips_a_zip_with_neither_schemas_nor_registries(
    held, catalog_file, tmp_path, capsys
):
    plain = tmp_path / "plain.zip"
    with zipfile.ZipFile(plain, "w") as zf:
        zf.writestr("README.md", "nothing here")
        zf.writestr("Redfish_1.4.0_PrivilegeRegistry.json", "{}")
    add(capsys, catalog_file, plain, "2026.3")
    code, out = run(capsys, "extract", "--all", catalog_file=catalog_file)
    assert code == 0, out
    assert (
        "skipped BUNDLE 2026.3: no json-schema/ folder, no versioned schema files "
        "and no message registry files in the archive"
    ) in out
    assert "skipped BUNDLE 2026.2: already extracted" in out
    assert out.strip().splitlines()[-1] == "summary: extracted 0, skipped 2, failed 0"


def test_a_new_original_removes_the_registries(
    held, catalog_file, registries_zip, capsys
):
    assert (held / "registries").is_dir()
    add(capsys, catalog_file, registries_zip, "2026.2", "--force")
    assert not (held / "registries").exists()
    assert not (held / "extract.json").exists()


# --------------------------------------------------------------- registry


def test_registry_lists_registries(held, catalog_file, capsys):
    code, out = registry(capsys, catalog_file, "--version", "2026.2")
    assert code == 0
    assert out.splitlines() == ["Base\t1.19.0\t4 messages", "Update\t1.4.0\t1 messages"]


def test_registry_lists_the_messages_of_one_registry(held, catalog_file, capsys):
    code, out = registry(capsys, catalog_file, "base", "--version", "2026.2")
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == cite(held, "Base 1.19.0", "Base.1.19.0.json", "#/Messages")
    assert lines[1] == "registry: Base 1.19.0 | 4 messages | ids Base.1.19.*"
    assert lines[2] == "Success | OK | The request completed successfully."
    assert lines[3].startswith(
        "PropertyMissing | Warning | The property '%1' is a required"
    )
    assert len(lines) == 6


def test_registry_prints_one_message_with_its_cite(held, catalog_file, capsys):
    code, out = registry(
        capsys, catalog_file, "Base", "propertymissing", "--version", "2026.2"
    )
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == cite(
        held, "Base 1.19.0", "Base.1.19.0.json", "#/Messages/PropertyMissing"
    )
    assert lines[1] == "message: Base.1.19.PropertyMissing | Warning | 1 arg"
    assert lines[2] == (
        "text: The property '%1' is a required property and must be included in "
        "the request."
    )
    assert "resolution: Ensure that the property is in the request body." in lines
    assert lines[-2:] == ["args:", "  %1 | string | The name of the property."]
    code, out = registry(
        capsys,
        catalog_file,
        "Base",
        "Base.1.19.CreateFailedMissingReqProperties",
        "--version",
        "2026.2",
    )
    assert code == 0
    assert out.splitlines()[-1].startswith("deprecated (since v1.14.0): ")


def test_registry_defaults_to_the_latest_held_version(
    schemas_held, held, catalog_file, capsys
):
    # 2026.1 (schemas) is the catalog's latest, so it is the default
    code, out = registry(capsys, catalog_file)
    assert code == 2
    assert out.strip() == (
        "BUNDLE 2026.1 is a schema bundle, not a registries bundle; read it with: "
        "bmcspec schema BUNDLE"
    )
    code, out = registry(capsys, catalog_file, "--version", "2026.2")
    assert code == 0
    assert out.startswith("Base\t")


def test_registry_error_paths(held, catalog_file, capsys):
    v = ("--version", "2026.2")
    code, out = registry(capsys, catalog_file, "Nope", *v)
    assert code == 2
    assert out.strip() == "no registry named 'Nope'; bmcspec registry BUNDLE lists them"
    code, out = registry(capsys, catalog_file, "dat", *v)
    assert code == 2
    assert out.strip() == "no registry named 'dat'; containing it: Update"
    code, out = registry(capsys, catalog_file, "Base", "Nope", *v)
    assert code == 2
    assert out.strip() == (
        "Base 1.19.0 has no message named 'Nope'; "
        "bmcspec registry BUNDLE Base lists them"
    )
    code, out = registry(capsys, catalog_file, "Base", "missing", *v)
    assert code == 2
    assert out.strip() == (
        "Base 1.19.0 has no message named 'missing'; containing it: PropertyMissing, "
        "CreateFailedMissingReqProperties"
    )
    code, out = registry(capsys, catalog_file, "--version", "9.9")
    assert code == 2
    assert "BUNDLE 9.9 is not in the Library" in out
    code, out = run(capsys, "registry", "NOPE", catalog_file=catalog_file)
    assert code == 2
    assert "NOPE is not in the Library" in out


def test_registry_refuses_pdfs_schema_bundles_and_unextracted_bundles(
    held, catalog_file, library, scripted, registries_zip, capsys
):
    pdf_url = "https://example.test/DSP0236_1.3.3.pdf"
    scripted.responses[pdf_url] = ok(
        b"%PDF-1.7\n" + b"x" * 300, ctype="application/pdf"
    )
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    code, out = run(capsys, "registry", "DSP0236", catalog_file=catalog_file)
    assert code == 2
    assert out.strip() == (
        "DSP0236 1.3.3 is a PDF document, not a registries bundle; read it with: "
        "bmcspec find DSP0236 PATTERN, or: bmcspec page DSP0236 N"
    )
    add(capsys, catalog_file, registries_zip, "2026.4")
    code, out = registry(capsys, catalog_file, "--version", "2026.4")
    assert code == 2
    assert out.strip() == (
        "BUNDLE 2026.4 is not extracted, or was unpacked by an older version; run: "
        'bmcspec extract BUNDLE --version "2026.4"'
    )


def test_schema_and_reading_commands_point_a_registries_bundle_to_registry(
    held, catalog_file, capsys
):
    code, out = run(
        capsys, "schema", "BUNDLE", "--version", "2026.2", catalog_file=catalog_file
    )
    assert code == 2
    assert out.strip() == (
        "BUNDLE 2026.2 is a registries bundle, not a schema bundle; read it with: "
        "bmcspec registry BUNDLE"
    )
    code, out = run(
        capsys, "find", "BUNDLE", "x", "--version", "2026.2", catalog_file=catalog_file
    )
    assert code == 2
    assert out.strip() == (
        "BUNDLE 2026.2 is a zip bundle; its registries are read with: "
        "bmcspec registry BUNDLE"
    )


def test_corrupt_registry_file_is_an_error_not_a_traceback(held, catalog_file, capsys):
    (held / "registries" / "Base.1.19.0.json").write_text("{oops", "utf-8")
    code, out = registry(capsys, catalog_file, "Base", "--version", "2026.2")
    assert code == 1
    assert out.startswith("cannot read the registries of BUNDLE 2026.2: ")
    assert "Base.1.19.0.json" in out and "not valid JSON" in out


# --------------------------------------------------- the profile bundle


PROFILE = {
    "$id": "http://redfish.dmtf.org/schemas/v1/RedfishInteroperabilityProfile.v1_10_0.json",
    "type": "object",
    "properties": {
        "ProfileName": {"type": "string", "description": "The name of this profile."},
        "Resources": {"type": "object", "description": "The resources."},
    },
    "definitions": {
        "ReadRequirement": {
            "type": "string",
            "description": "The read requirements for this property.",
            "enum": ["Mandatory", "Supported", "None"],
            "enumDescriptions": {"Mandatory": "Required in all instances."},
        }
    },
}


def profile_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        folder = "DSP8013_2026.1"
        zf.writestr(
            f"{folder}/RedfishInteroperabilityProfile.v1_10_0.json", json.dumps(PROFILE)
        )
        zf.writestr(f"{folder}/RedfishInteroperabilityProfile.v1_4_1.json", "{}")
        zf.writestr(f"{folder}/DSP8013_2026.1.pdf", "%PDF-1.4")
        zf.writestr(f"{folder}/info.json", "{}")  # unversioned: not an index here
    return buf.getvalue()


@pytest.fixture
def profile_held(catalog_file, library, tmp_path, capsys):
    z = tmp_path / "profiles.zip"
    z.write_bytes(profile_bytes())
    add(capsys, catalog_file, z, "2026.5")
    code, out = run(
        capsys, "extract", "BUNDLE", "--version", "2026.5", catalog_file=catalog_file
    )
    assert code == 0, out
    assert out.startswith("extracted BUNDLE 2026.5: 1 schema files, 1 resources in ")
    return library.specs / "mctp" / "BUNDLE" / "2026.5"


def test_a_profile_bundle_is_unpacked_as_schemas(profile_held, catalog_file, capsys):
    assert sorted(p.name for p in (profile_held / "schemas").iterdir()) == [
        "RedfishInteroperabilityProfile.v1_10_0.json"
    ]
    code, out = run(
        capsys, "schema", "BUNDLE", "--version", "2026.5", catalog_file=catalog_file
    )
    assert code == 0
    assert out.strip() == "RedfishInteroperabilityProfile\tv1.10.0"


def test_a_root_defined_schema_lists_its_properties_and_definitions(
    profile_held, catalog_file, capsys
):
    v = ("--version", "2026.5")
    code, out = run(
        capsys,
        "schema",
        "BUNDLE",
        "RedfishInteroperabilityProfile",
        *v,
        catalog_file=catalog_file,
    )
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].split(" | ")[2:5] == [
        "RedfishInteroperabilityProfile v1.10.0",
        "file RedfishInteroperabilityProfile.v1_10_0.json",
        "#",
    ]
    assert lines[1] == (
        "schema: RedfishInteroperabilityProfile v1.10.0 | 2 properties | "
        "definitions: ReadRequirement"
    )
    assert lines[2] == "ProfileName | string | writable | - | The name of this profile."
    code, out = run(
        capsys,
        "schema",
        "BUNDLE",
        "RedfishInteroperabilityProfile",
        "--definition",
        "readrequirement",
        *v,
        catalog_file=catalog_file,
    )
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].endswith(
        f"#/definitions/ReadRequirement | user-provided | {profile_held}"
    )
    assert lines[1] == "definition: ReadRequirement | enum"
    assert "  Mandatory: Required in all instances." in lines
    assert "  None" in lines
    code, out = run(
        capsys,
        "schema",
        "BUNDLE",
        "RedfishInteroperabilityProfile",
        "--property",
        "ProfileName",
        *v,
        catalog_file=catalog_file,
    )
    assert code == 0, out
    assert out.splitlines()[0].split(" | ")[4] == "#/properties/ProfileName"


def test_force_extract_as_the_other_kind_leaves_one_directory(
    held, catalog_file, tmp_path, capsys
):
    # F3 of round 1: the same version re-added as a schema bundle must not
    # keep the registries/ tree of the earlier unpack (and the other way round)
    v = ("--version", "2026.2", "--force")
    z = tmp_path / "schemas.zip"
    z.write_bytes(bundle_bytes())
    add(capsys, catalog_file, z, "2026.2", "--force")
    (held / "registries").mkdir()  # a stale tree, as if add had not cleaned
    code, out = run(capsys, "extract", "BUNDLE", *v, catalog_file=catalog_file)
    assert code == 0, out
    assert (held / "schemas").is_dir() and not (held / "registries").exists()
    z2 = tmp_path / "registries2.zip"
    z2.write_bytes(registries_bytes())
    add(capsys, catalog_file, z2, "2026.2", "--force")
    (held / "schemas").mkdir()
    code, out = run(capsys, "extract", "BUNDLE", *v, catalog_file=catalog_file)
    assert code == 0, out
    assert (held / "registries").is_dir() and not (held / "schemas").exists()

"""Message registries: member selection, unpacking, reading registries and
messages, the formatting helpers."""

import io
import json
import zipfile

import pytest

from bmc_toolkit.spec import registry as R

BASE = {
    "@odata.type": "#MessageRegistry.v1_7_0.MessageRegistry",
    "Id": "Base.1.19.0",
    "RegistryPrefix": "Base",
    "RegistryVersion": "1.19.0",
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
            "LongDescription": "This message shall indicate that a required  property "
            "was not supplied.",
            "Message": "The property '%1' is a required property and must be "
            "included in the request.",
            "Severity": "Warning",
            "MessageSeverity": "Warning",
            "NumberOfArgs": 1,
            "ParamTypes": ["string"],
            "ArgDescriptions": ["The name of the property."],
            "Resolution": "Ensure that the property is in the request body.",
        },
        "CreateFailedMissingReqProperties": {
            "Description": "Indicates that a create operation was attempted without "
            "a required property.",
            "Message": "The create operation failed because the required property "
            "'%1' was missing.",
            "Severity": "Critical",
            "MessageSeverity": "Critical",
            "NumberOfArgs": 1,
            "ParamTypes": ["string"],
            "ArgDescriptions": ["The name of the required property."],
            "Deprecated": "This message was deprecated in favor of `PropertyMissing`.",
            "VersionDeprecated": "1.14.0",
            "Resolution": "Correct the body.",
        },
        "Odd": {
            "Message": "Two things: %1 and %2.",
            "Severity": "OK",
            "NumberOfArgs": "two",  # not a number: the arg count comes from ParamTypes
            "ParamTypes": ["string", "number"],
            "VersionAdded": "1.19.0",
        },
    },
}

UPDATE = {
    "RegistryPrefix": "Update",
    "RegistryVersion": "1.4.0",
    "Messages": {
        "TargetDetermined": {
            "Message": "The target '%1' will be updated with image '%2'.",
            "MessageSeverity": "OK",
            "NumberOfArgs": 2,
            "ParamTypes": ["string", "string"],
        }
    },
}

MEMBERS = {
    "Base.1.2.0.json": {"RegistryPrefix": "Base", "Messages": {}},
    "Base.1.19.0.json": BASE,
    "DSP8011_2026.1/Update.1.4.0.json": UPDATE,
    "DSP8011_2026.1/Update.1.3.0.json": {"Messages": {}},
}
OTHERS = {
    "Redfish_1.4.0_PrivilegeRegistry.json": "{}",
    "DSP8011_2026.1.pdf": "%PDF-1.4",
    "DSP8011_2026.1.html": "<html/>",
    "README.md": "registries",
}


def registries_bytes(*, escape=True, mirror=True, members=MEMBERS) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, json.dumps(data))
        for name, data in OTHERS.items():
            zf.writestr(name, data)
        if escape:
            zf.writestr("../Evil.1.0.0.json", "{}")
        if mirror:
            zf.writestr("mirror/Base.1.19.0.json", "{}")  # a duplicate name
    return buf.getvalue()


def unpacked(tmp_path, **kw):
    z = tmp_path / "original.zip"
    z.write_bytes(registries_bytes(**kw))
    result = R.unpack(z, tmp_path)
    return R.Registries(tmp_path), result


# ---------------------------------------------------------------- unpack


def test_names_are_parsed():
    assert R.version_key("Base.1.19.0.json") == (1, 19, 0)
    assert R.prefix_of("ResourceEvent.1.5.0.json") == "ResourceEvent"
    assert R.version_label("Base.1.19.0.json") == "1.19.0"
    assert R.version_key("Redfish_1.4.0_PrivilegeRegistry.json") is None
    assert R.version_key("Chassis.v1_28_0.json") is None
    assert R.version_key("Base.1.19.json") is None


def test_select_keeps_the_newest_per_prefix_wherever_it_lies():
    with zipfile.ZipFile(io.BytesIO(registries_bytes())) as zf:
        kept, refused, duplicates = R.select_members(zf.namelist())
    assert kept == ["Base.1.19.0.json", "DSP8011_2026.1/Update.1.4.0.json"]
    assert refused == 1  # ../Evil.1.0.0.json
    assert duplicates == 1  # mirror/Base.1.19.0.json


def test_select_orders_versions_numerically_not_textually():
    kept, _, _ = R.select_members(["Base.1.9.0.json", "Base.1.10.0.json"])
    assert kept == ["Base.1.10.0.json"]


def test_select_raises_when_there_is_no_registry_file():
    with pytest.raises(R.NoRegistries):
        R.select_members(["DSP8013_2026.1/Profile.v1_4_1.json", "README.md"])


def test_unpack_writes_the_files_and_the_meta(tmp_path):
    regs, result = unpacked(tmp_path)
    assert sorted(p.name for p in (tmp_path / "registries").iterdir()) == [
        "Base.1.19.0.json",
        "Update.1.4.0.json",
    ]
    assert (result.files, result.registries) == (2, 2)
    assert (result.refused, result.duplicates) == (1, 1)
    meta = json.loads((tmp_path / "extract.json").read_text("utf-8"))
    assert meta["kind"] == "registries"
    assert meta["extractor_version"] == R.REGISTRY_VERSION
    assert meta["outline_source"] == "registries"
    assert R.read_meta(tmp_path) == meta
    assert R.is_current(tmp_path)


def test_unpack_replaces_an_earlier_directory(tmp_path):
    (tmp_path / "registries").mkdir()
    (tmp_path / "registries" / "Stale.1.0.0.json").write_text("{}", "utf-8")
    unpacked(tmp_path)
    assert not (tmp_path / "registries" / "Stale.1.0.0.json").exists()
    R.remove_registries(tmp_path)
    assert not (tmp_path / "registries").exists()
    assert not R.is_current(tmp_path)


def test_unpack_refuses_a_broken_archive(tmp_path):
    z = tmp_path / "original.zip"
    z.write_bytes(b"PK\x03\x04 not really")
    with pytest.raises(R.RegistryError):
        R.unpack(z, tmp_path)


def test_a_schema_meta_is_not_a_registries_meta(tmp_path):
    (tmp_path / "extract.json").write_text(
        json.dumps({"kind": "schemas", "extractor_version": 1}), "utf-8"
    )
    (tmp_path / "registries").mkdir()
    assert R.read_meta(tmp_path) is None
    assert not R.is_current(tmp_path)


# --------------------------------------------------------------- reading


def test_registries_are_listed_with_their_version_and_count(tmp_path):
    regs, _ = unpacked(tmp_path)
    listed = regs.registries()
    assert [(r.prefix, r.version, r.count) for r in listed] == [
        ("Base", "1.19.0", 4),
        ("Update", "1.4.0", 1),
    ]
    assert listed[0].label == "Base 1.19.0"
    assert listed[0].id_prefix == "Base.1.19"
    assert regs.registry("base") == listed[0]
    assert regs.registry("Nope") is None
    assert regs.similar("DAT") == ["Update"]


def test_messages_and_lookup(tmp_path):
    regs, _ = unpacked(tmp_path)
    base = regs.registry("Base")
    keys = [m.key for m in regs.messages(base)]
    assert keys == [
        "Success",
        "PropertyMissing",
        "CreateFailedMissingReqProperties",
        "Odd",
    ]
    m = regs.message(base, "propertymissing")
    assert m.key == "PropertyMissing"
    assert m.id == "Base.1.19.PropertyMissing"
    assert m.pointer == "#/Messages/PropertyMissing"
    assert regs.message(base, "Base.1.19.PropertyMissing") == m  # a full MessageId
    assert regs.message(base, "Nope") is None
    assert regs.similar_messages(base, "missing") == [
        "PropertyMissing",
        "CreateFailedMissingReqProperties",
    ]


def test_a_file_without_messages_or_with_bad_json_is_an_error(tmp_path):
    regs, _ = unpacked(tmp_path)
    (tmp_path / "registries" / "Broken.1.0.0.json").write_text("{not json", "utf-8")
    with pytest.raises(R.RegistryError, match="not valid JSON"):
        regs.registries()
    (tmp_path / "registries" / "Broken.1.0.0.json").write_text('{"a": 1}', "utf-8")
    with pytest.raises(R.RegistryError, match="no Messages"):
        R.Registries(tmp_path).registries()


def test_missing_directory_is_an_error(tmp_path):
    with pytest.raises(R.RegistryError):
        R.Registries(tmp_path).files()


# ------------------------------------------------------------ formatting


def test_message_line_and_detail_lines(tmp_path):
    regs, _ = unpacked(tmp_path)
    base = regs.registry("Base")
    m = regs.message(base, "PropertyMissing")
    assert R.message_line(m) == (
        "PropertyMissing | Warning | The property '%1' is a required property "
        "and must be included in the request."
    )
    assert R.detail_lines(m) == [
        "message: Base.1.19.PropertyMissing | Warning | 1 arg",
        "text: The property '%1' is a required property and must be included in "
        "the request.",
        "description: Indicates that a required property was not supplied.",
        "longDescription: This message shall indicate that a required property was "
        "not supplied.",
        "resolution: Ensure that the property is in the request body.",
        "args:",
        "  %1 | string | The name of the property.",
    ]
    deprecated = regs.message(base, "CreateFailedMissingReqProperties")
    assert R.detail_lines(deprecated)[-1] == (
        "deprecated (since v1.14.0): This message was deprecated in favor of "
        "`PropertyMissing`."
    )
    success = regs.message(base, "Success")
    assert R.detail_lines(success)[0] == "message: Base.1.19.Success | OK | 0 args"
    odd = regs.message(base, "Odd")
    lines = R.detail_lines(odd)
    assert lines[0] == "message: Base.1.19.Odd | OK | 2 args"
    assert "  %1 | string" in lines and "  %2 | number" in lines
    assert lines[-1] == "added v1.19.0"

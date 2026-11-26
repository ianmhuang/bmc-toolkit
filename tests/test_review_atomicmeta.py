"""Reviewer acceptance tests for T91 AC-3: unpacking a schema bundle, a
profile bundle and a registries bundle writes ``extract.json`` to a
``<name>.<pid>-<token>.part`` file beside it and renames that into place,
with the bytes it always had; a rename that fails leaves neither file and
the next unpack writes the meta again. Hand-written archives; the only
thing replaced is ``os.replace``, the rename itself."""

import json
import os
import re
import zipfile

import pytest

from bmc_toolkit.spec import bundle, registry

META = "extract.json"


def schema_zip(path):
    """DSP8010-shaped: a json-schema folder with an index and two versions."""
    folder = "DSP8010_1.0.0/json-schema"
    thing = {"definitions": {"Thing": {"type": "object", "properties": {}}}}
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{folder}/Thing.json", json.dumps({"definitions": {}}))
        zf.writestr(f"{folder}/Thing.v1_2_0.json", json.dumps(thing))
        zf.writestr(f"{folder}/Thing.v1_10_0.json", json.dumps(thing))
        zf.writestr("DSP8010_1.0.0/csdl/Thing_v1.xml", "<xml/>")
    return path


def profile_zip(path):
    """DSP8013-shaped: no json-schema folder, versioned files beside a PDF."""
    folder = "DSP8013_1.0.0"
    profile = {"type": "object", "properties": {"ProfileName": {"type": "string"}}}
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{folder}/Profile.v1_4_1.json", "{}")
        zf.writestr(f"{folder}/Profile.v1_10_0.json", json.dumps(profile))
        zf.writestr(f"{folder}/DSP8013_1.0.0.pdf", "%PDF-1.4")
    return path


def registries_zip(path):
    """DSP8011-shaped: several versions of one registry, one of another."""
    base = {
        "RegistryPrefix": "Base",
        "RegistryVersion": "1.10.0",
        "Messages": {"Success": {"Message": "OK.", "NumberOfArgs": 0}},
    }
    event = {"RegistryPrefix": "ResourceEvent", "Messages": {}}
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("DSP8011_1.0.0/Base.1.9.0.json", json.dumps({"Messages": {}}))
        zf.writestr("DSP8011_1.0.0/Base.1.10.0.json", json.dumps(base))
        zf.writestr("ResourceEvent.1.3.0.json", json.dumps(event))
        zf.writestr("DSP8011_1.0.0/DSP8011_1.0.0.pdf", "%PDF-1.4")
    return path


BUNDLES = [
    pytest.param(schema_zip, bundle, "schemas", id="schema-bundle"),
    pytest.param(profile_zip, bundle, "schemas", id="profile-bundle"),
    pytest.param(registries_zip, registry, "registries", id="registries-bundle"),
]


def name_of(path) -> str:
    return os.path.basename(os.fspath(path))


def expected_bytes(result) -> bytes:
    """What the meta file has always held: indent 1, ASCII, one trailing LF."""
    return (json.dumps(result.to_meta(), indent=1) + "\n").encode("ascii")


@pytest.mark.parametrize(("make", "module", "kind"), BUNDLES)
def test_extract_json_is_renamed_into_place_from_a_part_file_beside_it(
    tmp_path, monkeypatch, make, module, kind
):
    vdir = tmp_path / "v"
    vdir.mkdir()
    archive = make(vdir / "original.zip")
    renames = []
    real_replace = os.replace

    def recording(src, dst, *args, **kwargs):
        # at the moment of the rename the target directory holds the .part
        # and no extract.json: nothing half-written was ever under the name
        renames.append((src, dst, (vdir / META).exists()))
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", recording)
    result = module.unpack(archive, vdir)

    onto_meta = [r for r in renames if name_of(r[1]) == META]
    assert len(onto_meta) == 1, renames
    src, dst, meta_existed = onto_meta[0]
    assert os.path.dirname(os.fspath(src)) == os.path.dirname(os.fspath(dst))
    assert os.path.dirname(os.fspath(dst)) == str(vdir)
    assert re.fullmatch(
        rf"{re.escape(META)}\.{os.getpid()}-\w+\.part", name_of(src)
    ), name_of(src)
    assert not meta_existed
    assert not list(vdir.rglob("*.part"))

    raw = (vdir / META).read_bytes()
    assert raw == expected_bytes(result)
    assert raw.endswith(b"}\n") and b"\r" not in raw
    assert raw.splitlines()[1].startswith(b' "')  # indent 1
    assert json.loads(raw)["kind"] == kind
    assert module.is_current(vdir)


@pytest.mark.parametrize(("make", "module", "kind"), BUNDLES)
def test_a_failed_rename_leaves_no_meta_and_no_part_and_the_next_unpack_recovers(
    tmp_path, monkeypatch, make, module, kind
):
    vdir = tmp_path / "v"
    vdir.mkdir()
    archive = make(vdir / "original.zip")
    module.unpack(archive, vdir)
    assert module.is_current(vdir)
    real_replace = os.replace

    def refusing(src, dst, *args, **kwargs):
        if name_of(dst) == META:
            raise OSError("disk full")
        return real_replace(src, dst, *args, **kwargs)

    with monkeypatch.context() as patched:
        patched.setattr(os, "replace", refusing)
        with pytest.raises(OSError, match="disk full"):
            module.unpack(archive, vdir)

    # the earlier meta went before the files were rewritten, so nothing
    # claims the version is current, and no temporary is left behind
    assert not (vdir / META).exists()
    assert not list(vdir.rglob("*.part"))
    assert not module.is_current(vdir)
    assert archive.is_file()

    result = module.unpack(archive, vdir)
    assert (vdir / META).read_bytes() == expected_bytes(result)
    assert json.loads((vdir / META).read_bytes())["kind"] == kind
    assert module.is_current(vdir)
    assert not list(vdir.rglob("*.part"))

"""`invocation pldm --subcommand NAME`: pldmtool's subcommand read from a
held openbmc/pldm Code Tree. The tree is synthetic: the shapes
of pldmtool 71b1b2b's registrations, classes and option calls, written by
the tests; never a copy of the real files."""

import shutil
from pathlib import Path

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec import invocation, pldmtool
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG

BASE_CMD = """\
#include "pldm_base_cmd.hpp"

namespace pldmtool
{
namespace base
{
const std::map<const char*, pldm_supported_types> pldmTypes{
    {"base", PLDM_BASE},         {"smbios", PLDM_SMBIOS},
    {"platform", PLDM_PLATFORM}, {"bios", PLDM_BIOS},
    {"fru", PLDM_FRU},           {"firmware update", PLDM_FWUP},
};

// the name map GetPLDMCommands labels its output with: not a subcommand
const std::map<const char*, pldm_platform_commands> pldmPlatformCmds{
    {"GetSensorReading", PLDM_GET_SENSOR_READING},
    {"GetSensorThresholds", PLDM_GET_SENSOR_THRESHOLDS},
};

class GetPLDMVersion : public CommandInterface
{
  public:
    ~GetPLDMVersion() override = default;
    GetPLDMVersion(const GetPLDMVersion&) = delete;

    explicit GetPLDMVersion(const char* type, const char* name, CLI::App* app) :
        CommandInterface(type, name, app)
    {
        app->add_option("-t,--type", pldmType, "pldm supported type")
            ->required()
            ->transform(CLI::CheckedTransformer(pldmTypes, CLI::ignore_case));
    }
    std::pair<int, std::vector<uint8_t>> createRequestMsg() override
    {
        auto rc = encode_get_version_req(instanceId, 0, PLDM_GET_FIRSTPART,
                                         pldmType, request);
        return {rc, requestMsg};
    }
};

class GetTID : public CommandInterface
{
  public:
    ~GetTID() override = default;
    using CommandInterface::CommandInterface;

    std::pair<int, std::vector<uint8_t>> createRequestMsg() override
    {
        auto rc = encode_get_tid_req(instanceId, request);
        return {rc, requestMsg};
    }
};

class Commands : public CommandInterface
{
  public:
    explicit Commands(const char* type, const char* name, CLI::App* app) :
        CommandInterface(type, name, app)
    {
        app->add_option("-t,--type", pldmType, "pldm supported type")
            ->required()
            ->transform(CLI::CheckedTransformer(pldmTypes, CLI::ignore_case));
        app->add_option(
            "-d,--data", inputVersion,
            "Set PLDM type version. Which is got from GetPLDMVersion\\n"
            "eg: version 1.1.0 then data will be `0x00 0xF0 0xF1 0xF1`\\n"
            "(format: alpha update minor major)");
    }
};

class Odd : public CommandInterface
{
  public:
    explicit Odd(const char* type, const char* name, CLI::App* app) :
        CommandInterface(type, name, app)
    {
        setupOptions(app);  // options added elsewhere: nothing to read
    }
};

void registerCommand(CLI::App& app)
{
    auto base = app.add_subcommand("base", "base type command");
    base->require_subcommand(1);

    auto getPLDMVersion =
        base->add_subcommand("GetPLDMVersion", "get version of a certain type");
    commands.push_back(std::make_unique<GetPLDMVersion>(
        "base", "GetPLDMVersion", getPLDMVersion));

    auto getPLDMTID = base->add_subcommand("GetTID", "get Terminus ID (TID)");
    commands.push_back(std::make_unique<GetTID>("base", "GetTID", getPLDMTID));

    auto getPLDMCommands = base->add_subcommand(
        "GetPLDMCommands", "get supported commands of pldm type");
    commands.push_back(std::make_unique<Commands>(
        "base", "GetPLDMCommands", getPLDMCommands));

    auto odd = base->add_subcommand("Odd", "options not in the constructor");
    commands.push_back(std::make_unique<Odd>("base", "Odd", odd));
}
} // namespace base
} // namespace pldmtool
"""

PLATFORM_CMD = """\
namespace pldmtool
{
namespace platform
{
class GetPDR : public CommandInterface
{
  public:
    explicit GetPDR(const char* type, const char* name, CLI::App* app) :
        CommandInterface(type, name, app)
    {
        auto pdrOptionGroup = app->add_option_group("Required Option");
        pdrOptionGroup->add_option("-d,--data", recordHandle,
                                   "retrieve individual PDRs from a PDR Repository");
        pdrOptionGroup->add_option("-t, --type", pdrRecType,
                                   "retrieve all PDRs of the requested type");
        pdrOptionGroup->add_flag("-a, --all", allPDRs, "retrieve all PDRs");
        pdrOptionGroup->require_option(1);
    }
};

class GetStateSensorReadings : public CommandInterface
{
  public:
    explicit GetStateSensorReadings(const char* type, const char* name,
                                    CLI::App* app) :
        CommandInterface(type, name, app)
    {
        app->add_option(
               "-i, --sensor_id", sensorId,
               "Sensor ID that is used to identify and access the sensor")
            ->required();
        app->add_option("-r, --rearm", sensorRearm,
                        "Each bit location in this field corresponds to a "
                        "particular sensor")
            ->required();
        app->add_option(
            "-s, --state_set_id", stateSetId,
            "State Set ID that should be used for data interpretation");
    }
};

void registerCommand(CLI::App& app)
{
    auto platform = app.add_subcommand("platform", "platform type command");
    platform->require_subcommand(1);

    auto getPDR =
        platform->add_subcommand("GetPDR", "get platform descriptor records");
    commands.push_back(std::make_unique<GetPDR>("platform", "getPDR", getPDR));

    auto getStateSensorReadings = platform->add_subcommand(
        "GetStateSensorReadings", "get the state sensor readings");
    commands.push_back(std::make_unique<GetStateSensorReadings>(
        "platform", "getStateSensorReadings", getStateSensorReadings));
}
} // namespace platform
} // namespace pldmtool
"""

OEM_CMD = """\
namespace pldmtool
{
namespace oem_ibm
{
class GetAlertStatus : public CommandInterface
{
  public:
    explicit GetAlertStatus(const char* type, const char* name, CLI::App* app) :
        CommandInterface(type, name, app)
    {
        app->add_option("-i, --id", versionId, "Version Id")->required();
    }
};

void registerCommand(CLI::App& app)
{
    auto oem_ibm = app.add_subcommand("oem-ibm", "oem type command");
    auto getAlertStatus = oem_ibm->add_subcommand(
        "GetAlertStatus", "get alert status descriptor");
    commands.push_back(std::make_unique<GetAlertStatus>(
        "oem_ibm", "getAlertStatus", getAlertStatus));
}
} // namespace oem_ibm
} // namespace pldmtool
"""

FILES = {
    "pldmtool/pldm_base_cmd.cpp": BASE_CMD,
    "pldmtool/pldm_platform_cmd.cpp": PLATFORM_CMD,
    "pldmtool/oem/ibm/pldm_oem_ibm.cpp": OEM_CMD,
    "pldmtool/README.md": "pldmtool\n",
}
ORIGIN = "https://github.com/openbmc/pldm.git"


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "pldm-tree"
    _write(root, FILES)
    return code_mod.Tree(
        "pldm",
        ORIGIN,
        "0123456789abcdef0123456789abcdef01234567",
        root,
        code_mod.Provenance("default", "master"),
        fetched_at="2026-10-19T01:02:03.000000+00:00",
    )


def _line(text: str, needle: str) -> int:
    return next(i for i, ln in enumerate(text.splitlines(), 1) if needle in ln)


# ------------------------------------------------------------ find


def test_find_matches_the_registration_case_insensitively(tree):
    for asked in (
        "GetStateSensorReadings",
        "getstatesensorreadings",
        "GETSTATESENSORREADINGS",
    ):
        m = pldmtool.find(tree, asked)
        assert m is not None
        assert (m.path, m.name, m.type_) == (
            "pldmtool/pldm_platform_cmd.cpp",
            "GetStateSensorReadings",
            "platform",
        )
        assert m.registration == _line(PLATFORM_CMD, "auto getStateSensorReadings = ")
        assert m.registration_end == m.registration + 1
        assert m.class_name == "GetStateSensorReadings"


def test_find_reads_the_options_from_the_constructor(tree):
    m = pldmtool.find(tree, "GetStateSensorReadings")
    assert m.first == _line(PLATFORM_CMD, "explicit GetStateSensorReadings(")
    assert PLATFORM_CMD.splitlines()[m.last - 1].strip() == "}"
    assert [(o.spellings, o.required, o.flag) for o in m.options] == [
        (["-i", "--sensor_id"], True, False),
        (["-r", "--rearm"], True, False),
        (["-s", "--state_set_id"], False, False),
    ]
    assert m.template() == (
        "pldmtool platform GetStateSensorReadings -m <eid> -i <sensor_id> "
        "-r <rearm> [-s <state_set_id>]"
    )


def test_find_takes_the_class_from_make_unique_not_the_name(tree):
    # the GetPLDMCommands subcommand is handed to a class called Commands
    m = pldmtool.find(tree, "GetPLDMCommands")
    assert m.class_name == "Commands"
    assert m.type_ == "base"
    assert [o.spellings for o in m.options] == [["-t", "--type"], ["-d", "--data"]]
    assert m.options[0].required and not m.options[1].required
    assert m.options[0].transform_map == "pldmTypes"
    assert (
        m.template() == "pldmtool base GetPLDMCommands -m <eid> -t <type> [-d <data>]"
    )
    first, last = m.map_lines["pldmTypes"]
    assert first == _line(BASE_CMD, "pldmTypes{")
    assert BASE_CMD.splitlines()[last - 1].strip() == "};"


def test_find_handles_a_flag_and_an_option_group(tree):
    m = pldmtool.find(tree, "getpdr")
    assert (
        m.template() == "pldmtool platform GetPDR -m <eid> [-d <data>] [-t <type>] [-a]"
    )


def test_find_handles_a_class_without_a_constructor(tree):
    m = pldmtool.find(tree, "GetTID")
    assert m.class_name == "GetTID"
    assert (
        m.first
        == m.last
        == _line(BASE_CMD, "using CommandInterface::CommandInterface;")
    )
    assert m.options == []
    assert m.template() == "pldmtool base GetTID -m <eid>"


def test_find_names_the_oem_type_from_its_registration(tree):
    m = pldmtool.find(tree, "GetAlertStatus")
    assert m.type_ == "oem-ibm"
    assert m.template() == "pldmtool oem-ibm GetAlertStatus -m <eid> -i <id>"


def test_find_ignores_the_name_map_that_labels_output(tree):
    # the GetSensorReading entry of pldmPlatformCmds is a name map, not a
    # registration: no subcommand
    assert pldmtool.find(tree, "GetSensorReading") is None
    assert pldmtool.find(tree, "GetSensorThresholds") is None


def test_find_without_the_pldmtool_directory(tmp_path):
    bare = code_mod.Tree(
        "pldm", ORIGIN, "f" * 40, tmp_path, code_mod.Provenance("default", "master")
    )
    assert pldmtool.cpp_files(bare) == []
    assert pldmtool.find(bare, "GetTID") is None


# ------------------------------------------------------------ describe


def test_describe_prints_registration_cite_lines_and_template(tree):
    out = pldmtool.describe(tree, "GetStateSensorReadings", ORIGIN)
    reg = _line(PLATFORM_CMD, "auto getStateSensorReadings = ")
    # the registration spans two lines: both, joined, with the line range
    assert out[0] == (
        f"pldm 0123456 pldmtool/pldm_platform_cmd.cpp:{reg}-{reg + 1} | "
        "auto getStateSensorReadings = platform->add_subcommand( "
        '"GetStateSensorReadings", "get the state sensor readings");'
    )
    first = _line(PLATFORM_CMD, "explicit GetStateSensorReadings(")
    assert out[1].startswith(
        "cite: code | pldm 0123456 | master 2026-10-19 | "
        f"pldmtool/pldm_platform_cmd.cpp lines {first}-"
    )
    assert out[1].endswith(f"| - | {ORIGIN} | {tree.path}")
    numbered = out[2:-2]
    assert numbered[0].split("  ", 1) == [
        str(first),
        "    explicit GetStateSensorReadings(const char* type, const char* name,",
    ]
    assert any('"-i, --sensor_id", sensorId,' in ln for ln in numbered)
    assert out[-2] == (
        "subcommand: pldmtool platform GetStateSensorReadings -m <eid> "
        "-i <sensor_id> -r <rearm> [-s <state_set_id>]"
    )
    # the target's pldmtool may be another version: the note names the
    # tree the spellings came from and the check to run there
    assert out[-1] == (
        "note: spellings of pldm 0123456 (master 2026-10-19); the target's "
        "pldmtool may differ: check with pldmtool platform "
        "GetStateSensorReadings --help"
    )


def test_note_names_a_release_or_checkout_tree_as_the_cite_does(tree):
    from dataclasses import replace

    match = pldmtool.find(tree, "GetTID")
    released = replace(tree, provenance=code_mod.Provenance("release", "2.17.0"))
    assert pldmtool.note(released, match).startswith(
        "note: spellings of pldm 0123456 (release 2.17.0); "
    )
    checkout = replace(tree, provenance=code_mod.Provenance("checkout", "/src/pldm"))
    assert pldmtool.note(checkout, match).startswith(
        "note: spellings of pldm 0123456 (user checkout); "
    )
    assert pldmtool.note(checkout, match).endswith("pldmtool base GetTID --help")


def test_describe_prints_the_name_map_an_option_is_checked_against(tree):
    out = pldmtool.describe(tree, "GetPLDMVersion", ORIGIN)
    first, last = pldmtool.find(tree, "GetPLDMVersion").map_lines["pldmTypes"]
    cites = [ln for ln in out if ln.startswith("cite: code")]
    assert len(cites) == 2
    assert f"pldmtool/pldm_base_cmd.cpp lines {first}-{last}" in cites[1]
    assert any('{"firmware update", PLDM_FWUP},' in ln for ln in out)
    assert out[-2] == "subcommand: pldmtool base GetPLDMVersion -m <eid> -t <type>"


def test_describe_prints_at_most_sixty_constructor_lines_but_reads_them_all(tmp_path):
    # a constructor longer than the cap (fw_update's RequestUpdate is 60
    # lines) keeps every option in the template; the printout stops at
    # the cap and says how much is left
    calls = "".join(
        f'        app->add_option("--opt{i}", v{i}, "o")\n            ->required();\n'
        for i in range(40)
    )
    text = (
        "class Long : public CommandInterface\n{\n  public:\n"
        "    explicit Long(const char* type, const char* name, CLI::App* app) :\n"
        "        CommandInterface(type, name, app)\n    {\n" + calls + "    }\n};\n"
        "void registerCommand(CLI::App& app)\n{\n"
        '    auto fw = app.add_subcommand("fw_update", "firmware update");\n'
        '    auto longOne = fw->add_subcommand("Long", "many options");\n'
        '    commands.push_back(std::make_unique<Long>("fw_update", "Long", '
        "longOne));\n}\n"
    )
    root = tmp_path / "t"
    _write(root, {"pldmtool/pldm_fw_update_cmd.cpp": text})
    tree = code_mod.Tree(
        "pldm", ORIGIN, "a" * 40, root, code_mod.Provenance("default", "master")
    )
    m = pldmtool.find(tree, "Long")
    # `explicit Long(`, the base call, `{`, 40 two-line calls, `}`
    assert len(m.options) == 40 and m.last - m.first + 1 == 84
    out = pldmtool.describe(tree, "long", ORIGIN)
    assert f"lines {m.first}-{m.first + 59}" in out[1]
    assert out[-3] == f"(24 more lines of the constructor, to line {m.last})"
    assert out[-2].endswith("--opt38 <opt38> --opt39 <opt39>")
    assert out[-1].endswith("check with pldmtool fw_update Long --help")


def test_describe_says_none_and_options_not_read(tree):
    assert pldmtool.describe(tree, "GetSensorThresholds", ORIGIN) == [
        "subcommand: none in pldmtool/"
    ]
    out = pldmtool.describe(tree, "Odd", ORIGIN)
    assert out[0].endswith(
        '| auto odd = base->add_subcommand("Odd", "options not in the constructor");'
    )
    assert out[1].startswith("cite: code | pldm 0123456 |")
    assert out[-3:-1] == [
        "subcommand: pldmtool base Odd -m <eid>",
        "subcommand: options not read; see the lines above",
    ]
    assert out[-1].startswith("note: spellings of pldm 0123456 ")


# ------------------------------------------------------------ the command


FIELDS = [
    "Rq:1=0x80",
    "Type:1=0x02",
    "Cmd:1=0x21",
    "SensorID:2=7",
    "Rearm:1=0",
    "Reserved:1=0",
]
RAW = [
    "bytes: 7",
    "mctp-client eid <eid> type pldm data 80 02 21 07 00 00 00",
    "pldmtool raw -m <eid> -d 0x80 0x02 0x21 0x07 0x00 0x00 0x00",
]


def _run(capsys, argv, tree_for=None):
    # as `cli.main` does: the option ahead of the positionals first, or
    # argparse before 3.12.7 (CI's 3.11) refuses the fields after it
    parser = __import__("argparse").ArgumentParser()
    invocation.add_parsers(parser.add_subparsers(dest="command"))
    args = parser.parse_args(invocation.reorder_argv(["invocation", *argv]))
    code = invocation.cmd_invocation(args, tree_for)
    return code, capsys.readouterr().out.splitlines()


def test_command_prints_the_bytes_first_then_the_subcommand_block(tree, capsys):
    code, out = _run(
        capsys,
        ["pldm", "--subcommand", "GetStateSensorReadings", *FIELDS],
        lambda a: (tree, ORIGIN),
    )
    assert code == 0
    assert out[:3] == RAW
    assert out[3] == "offset | size | field | bytes"
    assert out[10].startswith("pldm 0123456 pldmtool/pldm_platform_cmd.cpp:")
    assert out[-2].startswith(
        "subcommand: pldmtool platform GetStateSensorReadings -m <eid> "
    )
    assert out[-1].startswith("note: spellings of pldm 0123456 (master 2026-10-19)")
    # without the option, nothing after the table
    code, plain = _run(capsys, ["pldm", *FIELDS])
    assert code == 0 and plain == out[:10]


def test_command_refuses_the_option_for_other_protocols(capsys):
    code, out = _run(
        capsys, ["ipmi", "--subcommand", "GetTID", "NetFn:1=0x06", "Cmd:1=0x01"]
    )
    assert code == 2 and out == ["invocation: --subcommand is for pldm, not ipmi"]
    code, out = _run(capsys, ["spdm", "--subcommand", "GetTID", "V:1=0x10"])
    assert code == 2 and out == ["invocation: --subcommand is for pldm, not spdm"]
    # a bad field is still the first thing refused
    code, out = _run(capsys, ["pldm", "--subcommand", "GetTID"])
    assert code == 2 and out[0].startswith("invocation: no field given")


def test_command_without_a_held_tree_prints_the_clone_hint(tree, capsys):
    def nothing(args):
        raise code_mod.CodeError("pldm is not in the Library; run: bmcspec clone pldm")

    code, out = _run(capsys, ["pldm", "--subcommand", "GetTID", *FIELDS], nothing)
    assert code == 0 and out[:3] == RAW
    assert out[-1] == "subcommand: pldm Code Tree not held; clone pldm"
    code, out = _run(capsys, ["pldm", "--subcommand", "GetTID", *FIELDS])
    assert code == 0 and out[-1] == "subcommand: pldm Code Tree not held; clone pldm"


def test_command_says_none_for_a_command_without_a_subcommand(tree, capsys):
    code, out = _run(
        capsys,
        ["pldm", "--subcommand", "GetSensorThresholds", *FIELDS],
        lambda a: (tree, ORIGIN),
    )
    assert code == 0 and out[-1] == "subcommand: none in pldmtool/"


# ------------------------------------------------------------ through the CLI


pytestmark_git = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)


@pytestmark_git
def test_cli_reads_the_held_pldm_tree_and_the_clone_hint_without_one(
    tmp_path, monkeypatch, capsys
):
    from tests.test_code import make_repo

    _work, _bare, url = make_repo(tmp_path, "pldm", FILES)
    catalog = tmp_path / "catalog.toml"
    catalog.write_text(
        MINI_CATALOG + f'\n[[repos]]\nid = "pldm"\nurl = "{url}"\ntopics = ["pldm"]\n',
        encoding="utf-8",
        newline="",
    )
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path / "lib"))
    argv = [
        "--catalog",
        str(catalog),
        "invocation",
        "pldm",
        "--subcommand",
        "GetTID",
        *FIELDS,
    ]
    assert main(argv) == 0
    out = capsys.readouterr().out.splitlines()
    assert (
        out[:3] == RAW and out[-1] == "subcommand: pldm Code Tree not held; clone pldm"
    )
    assert main(["--catalog", str(catalog), "clone", "pldm"]) == 0
    capsys.readouterr()
    assert main(argv) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[:3] == RAW
    assert any(
        ln.startswith("cite: code | pldm ") and "pldm_base_cmd.cpp lines" in ln
        for ln in out
    )
    assert out[-2] == "subcommand: pldmtool base GetTID -m <eid>"
    assert out[-1].startswith("note: spellings of pldm ")


# Round 1 of the review.


def test_subcommand_option_is_moved_before_the_positionals():
    # argparse before 3.12.7 (3.11 has no fix) reads `invocation pldm
    # --subcommand NAME FIELD...` with an empty FIELD list and refuses the
    # fields; the option first parses the same on every version
    fields = ["a:1=1", "b:2=2"]
    want = ["invocation", "--subcommand", "GetTID", "pldm", *fields]
    assert (
        invocation.reorder_argv(
            ["invocation", "pldm", "--subcommand", "GetTID", *fields]
        )
        == want
    )
    assert (
        invocation.reorder_argv(
            ["invocation", "pldm", *fields, "--subcommand", "GetTID"]
        )
        == want
    )
    assert invocation.reorder_argv(want) == want
    assert invocation.reorder_argv(
        ["invocation", "pldm", *fields, "--subcommand=GetTID"]
    ) == [
        "invocation",
        "--subcommand=GetTID",
        "pldm",
        *fields,
    ]
    # global options before the command stay where they are
    assert invocation.reorder_argv(
        ["--wait", "0", "invocation", "pldm", "--subcommand", "X"]
    ) == [
        "--wait",
        "0",
        "invocation",
        "--subcommand",
        "X",
        "pldm",
    ]
    # other commands and a dangling option are left alone
    assert invocation.reorder_argv(["code", "pldm", "--subcommand", "X"]) == [
        "code",
        "pldm",
        "--subcommand",
        "X",
    ]
    assert invocation.reorder_argv(["invocation", "pldm", "--subcommand"]) == [
        "invocation",
        "pldm",
        "--subcommand",
    ]


def test_not_held_line_names_the_clone_the_selector_asked_for():
    # a config Release that is not held: a plain `clone pldm` would not
    # satisfy the next selection, so the hint keeps the release
    assert (
        invocation.not_held_line(
            "pldm is not held at release 2.17.0; "
            "run: bmcspec clone pldm --release 2.17.0"
        )
        == "subcommand: pldm Code Tree not held; clone pldm --release 2.17.0"
    )
    assert invocation.not_held_line(
        "pldm is not in the Library; run: bmcspec clone pldm"
    ) == (invocation.NOT_HELD)
    assert invocation.not_held_line("no Library") == invocation.NOT_HELD


def test_cli_not_held_hint_carries_the_release(capsys, tree):
    def selector(args):
        raise code_mod.CodeError(
            "pldm is not held at release 2.17.0; "
            "run: bmcspec clone pldm --release 2.17.0"
        )

    code, out = _run(capsys, ["pldm", "--subcommand", "GetTID", *FIELDS], selector)
    assert code == 0
    assert out[-1] == "subcommand: pldm Code Tree not held; clone pldm --release 2.17.0"


def test_a_type_or_raw_is_not_a_subcommand(tree):
    # `base` is registered on the application itself; it is a type, not a
    # subcommand of one, and `pldmtool app base` would not run
    assert pldmtool.find(tree, "base") is None
    assert pldmtool.describe(tree, "base", ORIGIN) == ["subcommand: none in pldmtool/"]


def test_constructor_search_stays_inside_the_class(tmp_path):
    # a constructor without `explicit`, followed by a class whose
    # constructor is a `using`: the first class's options are read, and
    # the second class's `using` line is not taken for the first
    text = (
        "class Plain : public CommandInterface\n{\n  public:\n"
        "    Plain(const char* type, const char* name, CLI::App* app) :\n"
        "        CommandInterface(type, name, app)\n    {\n"
        '        app->add_option("-i, --id", id, "the id")->required();\n'
        "    }\n};\n\n"
        "class Bare : public CommandInterface\n{\n  public:\n"
        "    using CommandInterface::CommandInterface;\n};\n\n"
        "void registerCommand(CLI::App& app)\n{\n"
        '    auto base = app.add_subcommand("base", "base type command");\n'
        '    auto plain = base->add_subcommand("Plain", "plain constructor");\n'
        '    commands.push_back(std::make_unique<Plain>("base", "Plain", plain));\n'
        '    auto bare = base->add_subcommand("Bare", "using constructor");\n'
        '    commands.push_back(std::make_unique<Bare>("base", "Bare", bare));\n'
        '    auto lost = base->add_subcommand("Lost", "class not in this tree");\n'
        '    commands.push_back(std::make_unique<Lost>("base", "Lost", lost));\n'
        "}\n"
    )
    root = tmp_path / "t"
    _write(root, {"pldmtool/pldm_base_cmd.cpp": text})
    tree = code_mod.Tree(
        "pldm", ORIGIN, "b" * 40, root, code_mod.Provenance("default", "master")
    )
    plain = pldmtool.find(tree, "Plain")
    assert plain.explicit and (plain.first, plain.last) == (4, 8)
    assert [o.item() for o in plain.options] == ["-i <id>"]
    bare = pldmtool.find(tree, "Bare")
    assert not bare.explicit and bare.first == 14 and bare.options == []
    out = pldmtool.describe(tree, "Bare", ORIGIN)
    assert out[-2] == "subcommand: pldmtool base Bare -m <eid>"
    assert out[-1].startswith("note:")  # a `using` constructor: no warning
    # a registration whose class is not in the tree: the template is
    # `-m <eid>` only, and the answer is told the options were not read
    out = pldmtool.describe(tree, "Lost", ORIGIN)
    assert out[0].endswith(
        '| auto lost = base->add_subcommand("Lost", "class not in this tree");'
    )
    assert out[1:] == [
        "subcommand: pldmtool base Lost -m <eid>",
        "subcommand: options not read; no constructor found",
        pldmtool.note(tree, pldmtool.find(tree, "Lost")),
    ]

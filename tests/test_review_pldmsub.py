"""Reviewer acceptance tests for ``invocation pldm --subcommand NAME``
(AC-1 to AC-4): pldmtool's subcommand line read from a held openbmc/pldm
Code Tree.

Black box: every test runs the CLI entry point against a Library the test
lays out by hand (``code/pldm/<commit>/.bmc-tree.json`` beside synthetic
``pldmtool/`` sources written here, in the shapes the criteria name, never
a copy of the real files) and reads what it prints. Expected line numbers
are found in the fixture text, the expected cite and numbered lines are
what ``code`` prints for the same range, and the raw lines are what the
same call prints without the option.

On develop ``--subcommand`` is not an option: argparse leaves through
SystemExit before anything is printed, so every test fails there.
"""

import json
import re
from pathlib import Path

import pytest

from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG

ORIGIN = "https://github.com/openbmc/pldm.git"
COMMIT = "9b7c3a1d5e2f4a6b8c0d1e2f3a4b5c6d7e8f9a0b"
SHORT = COMMIT[:7]
FETCHED = "2026-10-19T00:00:00.000000+00:00"
REPO_ENTRY = f'\n[[repos]]\nid = "pldm"\nurl = "{ORIGIN}"\ntopics = ["pldm"]\n'

NOT_HELD = "subcommand: pldm Code Tree not held; clone pldm"
NONE = "subcommand: none in pldmtool/"
NUMBERED = re.compile(r"^\s*(\d+)(?:  |$)")
TOOLS = ("ipmitool", "mctp-client", "pldmtool")

FIELDS = [
    "Rq:1=0x80",
    "Type:1=0x02",
    "Cmd:1=0x39",
    "Effecter ID:2=0x0105",
    "Count:1=1",
]
MCTP_LINE = "mctp-client eid <eid> type pldm data 80 02 39 05 01 01"
RAW_LINE = "pldmtool raw -m <eid> -d 0x80 0x02 0x39 0x05 0x01 0x01"

PLATFORM_CMD = """\
#include "pldm_platform_cmd.hpp"

namespace pldmtool
{
namespace platform
{
const std::map<const char*, pldm_effecter_types> effecterTypes{
    {"numeric", PLDM_NUMERIC_EFFECTER},
    {"state", PLDM_STATE_EFFECTER},
};

// the labels GetPLDMCommands prints its output with: not registrations
const std::map<const char*, pldm_platform_commands> platformCmdNames{
    {"GetSensorThresholds", PLDM_GET_SENSOR_THRESHOLDS},
    {"SetEffecterStates", PLDM_SET_STATE_EFFECTER_STATES},
};

class SetEffecterStates : public CommandInterface
{
  public:
    ~SetEffecterStates() override = default;
    SetEffecterStates(const SetEffecterStates&) = delete;

    explicit SetEffecterStates(const char* type, const char* name,
                               CLI::App* app) :
        CommandInterface(type, name, app)
    {
        app->add_option("-i, --id", effecterId, "Effecter ID")->required();
        app->add_option("-c, --count", effecterCount, "Composite effecter count")
            ->required();
        app->add_option("-d, --data", effecterData, "Set effecter state data");
        app->add_option("-t,--type", effecterType, "effecter type")
            ->transform(CLI::CheckedTransformer(effecterTypes, CLI::ignore_case));
        app->add_flag("-v, --verbose", verbose, "print the request too");
        app->add_option("--timeout", timeoutMs, "wait this many milliseconds");
    }

    std::pair<int, std::vector<uint8_t>> createRequestMsg() override
    {
        auto rc = encode_set_state_effecter_states_req(
            instanceId, effecterId, effecterCount, effecterData, request);
        return {rc, requestMsg};
    }
};

// the subcommand GetEffecterTable is handed to a class of another name
class EffecterHelper : public CommandInterface
{
  public:
    explicit EffecterHelper(const char* type, const char* name, CLI::App* app) :
        CommandInterface(type, name, app)
    {
        app->add_option("-i, --id", effecterId, "Effecter ID")->required();
    }
};

class GetEffecterValue : public CommandInterface
{
  public:
    explicit GetEffecterValue(const char* type, const char* name, CLI::App* app) :
        CommandInterface(type, name, app)
    {
        addOptions(app);
    }
};

class GetTerminusUID : public CommandInterface
{
  public:
    explicit GetTerminusUID(const char* type, const char* name, CLI::App* app) :
        CommandInterface(type, name, app)
    {
        app->add_option("-u, --uid", uid, "Terminus UID")->required();
    }
};

class GetPDRRepositoryInfo : public CommandInterface
{
  public:
    ~GetPDRRepositoryInfo() override = default;
    using CommandInterface::CommandInterface;

    std::pair<int, std::vector<uint8_t>> createRequestMsg() override
    {
        auto rc = encode_get_pdr_repository_info_req(instanceId, request);
        return {rc, requestMsg};
    }
};

void registerCommand(CLI::App& app)
{
    auto platform = app.add_subcommand("platform", "platform type command");
    platform->require_subcommand(1);

    auto setEffecterStates = platform->add_subcommand(
        "SetEffecterStates", "set the state of one or more effecters");
    commands.push_back(std::make_unique<SetEffecterStates>(
        "platform", "setEffecterStates", setEffecterStates));

    auto getEffecterTable =
        platform->add_subcommand("GetEffecterTable", "list the effecters");
    commands.push_back(std::make_unique<EffecterHelper>(
        "platform", "getEffecterTable", getEffecterTable));

    auto getEffecterValue =
        platform->add_subcommand("GetEffecterValue", "read one effecter");
    commands.push_back(std::make_unique<GetEffecterValue>(
        "platform", "getEffecterValue", getEffecterValue));

    auto getTerminusUID = platform->add_subcommand("GetTerminusUID", "get the UID");
    commands.emplace_back(new GetTerminusUID("platform", "getTerminusUID",
                                             getTerminusUID));

    auto getPDRRepositoryInfo = platform->add_subcommand(
        "GetPDRRepositoryInfo", "get the PDR repository info");
    commands.push_back(std::make_unique<GetPDRRepositoryInfo>(
        "platform", "getPDRRepositoryInfo", getPDRRepositoryInfo));
}
} // namespace platform
} // namespace pldmtool
"""

OEM_CMD = """\
namespace pldmtool
{
namespace oem_ibm
{
class GetFileTable : public CommandInterface
{
  public:
    explicit GetFileTable(const char* type, const char* name, CLI::App* app) :
        CommandInterface(type, name, app)
    {
        app->add_option("-t, --table", tableType, "table type")->required();
    }
};

void registerCommand(CLI::App& app)
{
    CLI::App* oem = app.add_subcommand("oem-ibm", "oem ibm type command");
    oem->require_subcommand(1);
    auto getFileTable = oem->add_subcommand("GetFileTable", "get the file table");
    commands.push_back(std::make_unique<GetFileTable>(
        "oem_ibm", "getFileTable", getFileTable));
}
} // namespace oem_ibm
} // namespace pldmtool
"""

# a constructor of 70 lines: the printout stops at 60, the template does not
LONG_OPTIONS = 33


def _fw_cmd() -> str:
    lines = [
        "namespace pldmtool",
        "{",
        "namespace fw_update",
        "{",
        "class RequestUpdate : public CommandInterface",
        "{",
        "  public:",
        "    explicit RequestUpdate(const char* type, const char* name, "
        "CLI::App* app) :",
        "        CommandInterface(type, name, app)",
        "    {",
    ]
    for i in range(LONG_OPTIONS):
        lines.append(f'        app->add_option("--opt{i:02}", v{i}, "o")')
        lines.append("            ->required();")
    lines += [
        "    }",
        "};",
        "",
        "void registerCommand(CLI::App& app)",
        "{",
        '    auto fwUpdate = app.add_subcommand("fw_update", "firmware update");',
        '    auto requestUpdate = fwUpdate->add_subcommand("RequestUpdate", "r");',
        "    commands.push_back(std::make_unique<RequestUpdate>(",
        '        "fw_update", "requestUpdate", requestUpdate));',
        "}",
        "} // namespace fw_update",
        "} // namespace pldmtool",
    ]
    return "\n".join(lines) + "\n"


FW_CMD = _fw_cmd()

HELPER_HPP = """\
namespace pldmtool
{
inline void registerDecoy(CLI::App& app)
{
    auto decoy = app.add_subcommand("Decoy", "declared in a header, not a source");
}
} // namespace pldmtool
"""

OUTSIDE_CPP = """\
void registerCommand(CLI::App& app)
{
    auto outside = app.add_subcommand("Outside", "not under pldmtool/");
}
"""

FILES = {
    "pldmtool/pldm_platform_cmd.cpp": PLATFORM_CMD,
    "pldmtool/pldm_fw_update_cmd.cpp": FW_CMD,
    "pldmtool/oem/ibm/pldm_oem_ibm.cpp": OEM_CMD,
    "pldmtool/pldm_cmd_helper.hpp": HELPER_HPP,
    "libpldmresponder/platform.cpp": OUTSIDE_CPP,
    "README.md": "pldm\n",
}


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")


def _catalog(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.toml"
    path.write_text(MINI_CATALOG + REPO_ENTRY, encoding="utf-8", newline="")
    return path


@pytest.fixture
def held(tmp_path, monkeypatch):
    """(catalog path, Library root): a Library holding one default-branch
    pldm tree, laid out as docs/LIBRARY.md describes."""
    library = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(library))
    tree = library / "code" / "pldm" / COMMIT
    _write(tree, FILES)
    meta = {
        "repo": "pldm",
        "url": ORIGIN,
        "commit": COMMIT,
        "provenance": {"kind": "default", "name": "master"},
        "fetched_at": FETCHED,
    }
    (tree / ".bmc-tree.json").write_text(
        json.dumps(meta), encoding="utf-8", newline=""
    )
    return _catalog(tmp_path), library


def _run(capsys, catalog: Path, *argv: str):
    """(exit code, stdout lines) of one CLI call."""
    code = main(["--catalog", str(catalog), *argv])
    return code, capsys.readouterr().out.splitlines()


def _invoke(capsys, catalog: Path, name: str, *fields: str, protocol: str = "pldm"):
    return _run(capsys, catalog, "invocation", protocol, "--subcommand", name, *fields)


def _code(capsys, catalog: Path, path: str, first: int, last: int):
    """What ``code`` prints for the range: the cite, then the numbered lines."""
    return _run(capsys, catalog, "code", "pldm", path, "--lines", f"{first}-{last}")


def _line(text: str, needle: str) -> int:
    """1-based number of the first line holding ``needle``."""
    return next(i for i, ln in enumerate(text.splitlines(), 1) if needle in ln)


def _line_after(text: str, first: int, exact: str) -> int:
    """1-based number of the first line after ``first`` that is ``exact``."""
    lines = text.splitlines()
    return next(i for i, ln in enumerate(lines, 1) if i > first and ln == exact)


def _cites(out: list[str]) -> list[int]:
    return [i for i, ln in enumerate(out) if ln.startswith("cite: code | ")]


def _registration(out: list[str]) -> str:
    return next(ln for ln in out if ln.startswith(f"pldm {SHORT} "))


def _numbers(lines: list[str]) -> list[int]:
    found = [NUMBERED.match(ln) for ln in lines]
    return [int(m.group(1)) for m in found if m]


def _snapshot(root: Path) -> list[tuple[str, int]]:
    return sorted(
        (str(p.relative_to(root)), p.stat().st_size if p.is_file() else -1)
        for p in root.rglob("*")
    )


# ------------------------------------------------------------------ AC-1


def test_the_raw_output_comes_first_and_unchanged_then_the_block(held, capsys):
    catalog, _library = held
    code, plain = _run(capsys, catalog, "invocation", "pldm", *FIELDS)
    assert code == 0, plain
    assert plain[1:3] == [MCTP_LINE, RAW_LINE]
    code, out = _invoke(capsys, catalog, "SetEffecterStates", *FIELDS)
    assert code == 0, out
    assert out[: len(plain)] == plain
    block = out[len(plain) :]
    assert block, "nothing printed after the field table"
    assert block[0].startswith(f"pldm {SHORT} pldmtool/pldm_platform_cmd.cpp:")
    assert block[-2].startswith("subcommand: pldmtool platform SetEffecterStates ")
    assert block[-1].startswith("note: ")


@pytest.mark.parametrize(
    ("protocol", "fields"),
    [
        ("ipmi", ["NetFn:1=0x06", "Cmd:1=0x01"]),
        ("mctp-control", ["Hdr:1=0x80", "Cmd:1=0x02"]),
        ("spdm", ["Version:1=0x10", "Code:1=0x84"]),
    ],
)
def test_the_option_is_refused_for_the_other_protocols(held, capsys, protocol, fields):
    catalog, _library = held
    code, out = _invoke(capsys, catalog, "GetTID", *fields, protocol=protocol)
    assert code == 2, out
    assert any("pldm" in ln for ln in out), out
    assert not any(ln.split(" ")[0] in TOOLS for ln in out), out


def test_without_fields_it_is_refused_as_before(held, capsys):
    catalog, _library = held
    code, out = _invoke(capsys, catalog, "SetEffecterStates")
    assert code == 2, out
    assert not any(ln.split(" ")[0] in TOOLS for ln in out), out
    assert not any(ln.startswith("subcommand:") for ln in out), out


# ------------------------------------------------------------------ AC-2


@pytest.mark.parametrize(
    "asked", ["SetEffecterStates", "seteffecterstates", "SETEFFECTERSTATES"]
)
def test_the_name_is_matched_case_insensitively_against_the_registration(
    held, capsys, asked
):
    catalog, _library = held
    code, out = _invoke(capsys, catalog, asked, *FIELDS)
    assert code == 0, out
    reg = _line(PLATFORM_CMD, "auto setEffecterStates = platform->add_subcommand(")
    registration = _registration(out)
    assert f"pldmtool/pldm_platform_cmd.cpp:{reg}" in registration
    assert '"SetEffecterStates"' in registration
    # the type is the parent variable's own registration, the name the
    # source's spelling whatever case was asked
    assert out[-2].startswith(
        "subcommand: pldmtool platform SetEffecterStates -m <eid>"
    )
    assert out[-1].endswith("check with pldmtool platform SetEffecterStates --help")


def test_the_type_of_a_file_under_oem_ibm_is_oem_ibm(held, capsys):
    catalog, _library = held
    code, out = _invoke(capsys, catalog, "GetFileTable", *FIELDS)
    assert code == 0, out
    assert "pldmtool/oem/ibm/pldm_oem_ibm.cpp:" in _registration(out)
    assert out[-2] == "subcommand: pldmtool oem-ibm GetFileTable -m <eid> -t <table>"
    assert out[-1].endswith("check with pldmtool oem-ibm GetFileTable --help")


def test_the_class_is_the_make_unique_argument_not_the_name(held, capsys):
    # GetEffecterTable is handed to EffecterHelper: its constructor is cited
    catalog, _library = held
    code, out = _invoke(capsys, catalog, "GetEffecterTable", *FIELDS)
    assert code == 0, out
    first = _line(PLATFORM_CMD, "explicit EffecterHelper(")
    last = _line_after(PLATFORM_CMD, first, "    }")
    cites = _cites(out)
    assert len(cites) == 1, cites
    assert f"pldmtool/pldm_platform_cmd.cpp lines {first}-{last}" in out[cites[0]]
    assert out[-2] == "subcommand: pldmtool platform GetEffecterTable -m <eid> -i <id>"


def test_without_make_unique_the_class_of_the_same_name_is_taken(held, capsys):
    catalog, _library = held
    code, out = _invoke(capsys, catalog, "getterminusuid", *FIELDS)
    assert code == 0, out
    first = _line(PLATFORM_CMD, "explicit GetTerminusUID(")
    last = _line_after(PLATFORM_CMD, first, "    }")
    cites = _cites(out)
    assert len(cites) == 1, cites
    assert f"pldmtool/pldm_platform_cmd.cpp lines {first}-{last}" in out[cites[0]]
    assert out[-2] == "subcommand: pldmtool platform GetTerminusUID -m <eid> -u <uid>"


@pytest.mark.parametrize("asked", ["Decoy", "Outside"])
def test_only_cpp_files_under_pldmtool_are_read(held, capsys, asked):
    # Decoy is registered in a .hpp under pldmtool/, Outside in a .cpp
    # elsewhere in the tree: neither is a pldmtool subcommand
    catalog, _library = held
    code, out = _invoke(capsys, catalog, asked, *FIELDS)
    assert code == 0, out
    assert out[1:3] == [MCTP_LINE, RAW_LINE]
    assert out[-1] == NONE
    assert not _cites(out)


# ------------------------------------------------------------------ AC-3


def test_the_cite_and_numbered_lines_are_what_code_prints_for_the_range(held, capsys):
    catalog, _library = held
    first = _line(PLATFORM_CMD, "explicit SetEffecterStates(")
    last = _line_after(PLATFORM_CMD, first, "    }")
    code, out = _invoke(capsys, catalog, "SetEffecterStates", *FIELDS)
    assert code == 0, out
    cites = _cites(out)
    assert len(cites) == 2, cites  # the constructor, then the checked map
    ctor = cites[0]
    assert out[ctor].startswith(f"cite: code | pldm {SHORT} | master 2026-10-19 | ")
    assert f"pldmtool/pldm_platform_cmd.cpp lines {first}-{last}" in out[ctor]
    assert f"| {ORIGIN} |" in out[ctor]
    # the same range through `code`: the cite and the numbered lines, word
    # for word, so the Session reads both the same way
    code, ref = _code(capsys, catalog, "pldmtool/pldm_platform_cmd.cpp", first, last)
    assert code == 0, ref
    assert out[ctor : ctor + 1 + (last - first + 1)] == ref
    assert any('"-i, --id", effecterId' in ln for ln in ref)


def test_the_checked_map_is_printed_under_its_own_cite(held, capsys):
    catalog, _library = held
    first = _line(PLATFORM_CMD, "effecterTypes{")
    last = _line_after(PLATFORM_CMD, first, "};")
    code, out = _invoke(capsys, catalog, "SetEffecterStates", *FIELDS)
    assert code == 0, out
    cites = _cites(out)
    assert len(cites) == 2, cites
    where = cites[1]
    assert f"pldmtool/pldm_platform_cmd.cpp lines {first}-{last}" in out[where]
    code, ref = _code(capsys, catalog, "pldmtool/pldm_platform_cmd.cpp", first, last)
    assert code == 0, ref
    assert out[where : where + 1 + (last - first + 1)] == ref
    assert any('{"numeric", PLDM_NUMERIC_EFFECTER},' in ln for ln in ref)
    # the map that labels output is no option's map: not printed
    assert not any("platformCmdNames" in ln for ln in out)


def test_the_template_follows_the_option_calls_in_source_order(held, capsys):
    catalog, _library = held
    code, out = _invoke(capsys, catalog, "SetEffecterStates", *FIELDS)
    assert code == 0, out
    # required: `-i <id>`; not required: brackets; a flag: `[-v]`; long only:
    # `[--timeout <timeout>]`; the placeholder is the long name without dashes
    assert out[-2] == (
        "subcommand: pldmtool platform SetEffecterStates -m <eid> -i <id> "
        "-c <count> [-d <data>] [-t <type>] [-v] [--timeout <timeout>]"
    )
    assert out[-1] == (
        f"note: spellings of pldm {SHORT} (master 2026-10-19); the target's "
        "pldmtool may differ: check with pldmtool platform SetEffecterStates --help"
    )


def test_at_most_sixty_constructor_lines_are_printed_but_every_option_is_read(
    held, capsys
):
    catalog, _library = held
    first = _line(FW_CMD, "explicit RequestUpdate(")
    assert _line_after(FW_CMD, first, "    }") == first + 69  # 70 lines long
    code, out = _invoke(capsys, catalog, "RequestUpdate", *FIELDS)
    assert code == 0, out
    cites = _cites(out)
    assert len(cites) == 1, cites
    shown = f"pldmtool/pldm_fw_update_cmd.cpp lines {first}-{first + 59}"
    assert shown in out[cites[0]]
    assert _numbers(out[cites[0] + 1 :]) == list(range(first, first + 60))
    template = out[-2]
    assert template.startswith(
        "subcommand: pldmtool fw_update RequestUpdate -m <eid> --opt00 <opt00> "
    )
    assert template.endswith("--opt32 <opt32>")
    assert template.count(" <opt") == LONG_OPTIONS
    assert out[-1].endswith("check with pldmtool fw_update RequestUpdate --help")


def test_a_using_constructor_gives_a_template_of_the_eid_only(held, capsys):
    catalog, _library = held
    code, out = _invoke(capsys, catalog, "GetPDRRepositoryInfo", *FIELDS)
    assert code == 0, out
    using = _line(PLATFORM_CMD, "using CommandInterface::CommandInterface;")
    cites = _cites(out)
    assert len(cites) == 1, cites
    assert f"pldmtool/pldm_platform_cmd.cpp lines {using}-{using}" in out[cites[0]]
    assert _numbers(out[cites[0] + 1 :]) == [using]
    assert "subcommand: pldmtool platform GetPDRRepositoryInfo -m <eid>" in out
    assert out[-1].endswith("check with pldmtool platform GetPDRRepositoryInfo --help")


# ------------------------------------------------------------------ AC-4


@pytest.mark.parametrize("asked", ["GetSensorThresholds", "SetEffecterStates2", "raw"])
def test_none_when_no_registration_carries_the_name(held, capsys, asked):
    # GetSensorThresholds sits in the name map only; the others nowhere
    catalog, _library = held
    code, out = _invoke(capsys, catalog, asked, *FIELDS)
    assert code == 0, out
    assert out[1:3] == [MCTP_LINE, RAW_LINE]
    assert out[-1] == NONE
    assert not _cites(out)
    assert sum(ln.startswith("subcommand:") for ln in out) == 1


@pytest.mark.parametrize("existing", [False, True])
def test_not_held_when_the_library_has_no_pldm_tree(
    tmp_path, monkeypatch, capsys, existing
):
    library = tmp_path / "lib"
    if existing:
        (library / "code" / "bmcweb").mkdir(parents=True)
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(library))
    catalog = _catalog(tmp_path)
    before = _snapshot(library) if existing else None
    code, out = _invoke(capsys, catalog, "SetEffecterStates", *FIELDS)
    assert code == 0, out
    assert out[1:3] == [MCTP_LINE, RAW_LINE]
    assert out[-1] == NOT_HELD
    assert not _cites(out)
    # nothing cloned, nothing written
    if existing:
        assert _snapshot(library) == before
    else:
        assert not library.exists()


def test_options_not_read_when_the_constructor_adds_them_elsewhere(held, capsys):
    catalog, _library = held
    code, out = _invoke(capsys, catalog, "GetEffecterValue", *FIELDS)
    assert code == 0, out
    assert out[1:3] == [MCTP_LINE, RAW_LINE]
    first = _line(PLATFORM_CMD, "explicit GetEffecterValue(")
    last = _line_after(PLATFORM_CMD, first, "    }")
    cites = _cites(out)
    assert len(cites) == 1, cites
    assert f"pldmtool/pldm_platform_cmd.cpp lines {first}-{last}" in out[cites[0]]
    assert any(NUMBERED.match(ln) and "addOptions(app);" in ln for ln in out)
    assert out[-3] == "subcommand: pldmtool platform GetEffecterValue -m <eid>"
    assert out[-2] == "subcommand: options not read; see the lines above"
    assert out[-1].startswith("note: ")


def test_the_lookup_writes_nothing_under_the_library(held, capsys):
    catalog, library = held
    before = _snapshot(library)
    for asked in ("SetEffecterStates", "GetSensorThresholds", "GetEffecterValue"):
        code, _out = _invoke(capsys, catalog, asked, *FIELDS)
        assert code == 0
    assert _snapshot(library) == before
    assert not list(library.rglob(".lock*"))

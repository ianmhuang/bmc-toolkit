"""Reviewer acceptance tests: `invocation pldm --subcommand oem-ibm` says
`none` instead of a template for the oem type itself (AC-1 to AC-3).

The trees are synthetic: the shapes of pldmtool's oem registrations written
by the tests, never a copy of the real files. Two shapes keep the oem type:
`auto oem_ibm = app.add_subcommand("oem-ibm", ...)` and
`CLI::App* oem = app.add_subcommand("oem-ibm", ...)`; a third tree holds a
made-up `pldmtool/oem/acme/` directory, so the rule is shown to follow the
directory's type name and not the string `ibm`.

On develop the oem directory fallback names every registration under
`pldmtool/oem/<vendor>/` after the directory, the type's own included, so
every AC-1 and AC-2 test about the type itself fails there.
"""

import argparse
from pathlib import Path

import pytest

from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec import invocation, pldmtool

ORIGIN = "https://github.com/openbmc/pldm.git"
NONE_LINE = "subcommand: none in pldmtool/"

BASE_CMD = """\
class GetTID : public CommandInterface
{
  public:
    using CommandInterface::CommandInterface;
};

void registerCommand(CLI::App& app)
{
    auto base = app.add_subcommand("base", "base type command");
    base->require_subcommand(1);
    auto getPLDMTID = base->add_subcommand("GetTID", "get Terminus ID (TID)");
    commands.push_back(std::make_unique<GetTID>("base", "GetTID", getPLDMTID));
}
"""

PLATFORM_CMD = """\
class GetPDR : public CommandInterface
{
  public:
    using CommandInterface::CommandInterface;
};

void registerCommand(CLI::App& app)
{
    auto platform = app.add_subcommand("platform", "platform type command");
    platform->require_subcommand(1);
    auto getPDR = platform->add_subcommand("GetPDR", "get PDRs");
    commands.push_back(std::make_unique<GetPDR>("platform", "getPDR", getPDR));
}
"""

# the oem type kept by `auto`, as 71b1b2b writes it
OEM_AUTO_CMD = """\
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
    oem_ibm->require_subcommand(1);
    auto getAlertStatus = oem_ibm->add_subcommand(
        "GetAlertStatus", "get alert status descriptor");
    commands.push_back(std::make_unique<GetAlertStatus>(
        "oem_ibm", "getAlertStatus", getAlertStatus));
}
"""

# the oem type kept by a `CLI::App*` pointer
OEM_POINTER_CMD = """\
class GetFileTable : public CommandInterface
{
  public:
    explicit GetFileTable(const char* type, const char* name, CLI::App* app) :
        CommandInterface(type, name, app)
    {
        app->add_option("-t, --table", table, "table type")->required();
    }
};

void registerCommand(CLI::App& app)
{
    CLI::App* oem = app.add_subcommand("oem-ibm", "oem type command");
    oem->require_subcommand(1);
    auto getFileTable = oem->add_subcommand("GetFileTable", "get file table");
    commands.push_back(std::make_unique<GetFileTable>(
        "oem_ibm", "getFileTable", getFileTable));
}
"""

# a made-up second oem directory: the rule follows the directory name
OEM_ACME_CMD = """\
class GetWidget : public CommandInterface
{
  public:
    explicit GetWidget(const char* type, const char* name, CLI::App* app) :
        CommandInterface(type, name, app)
    {
        app->add_option("-w, --widget", widgetId, "widget id")->required();
    }
};

void registerCommand(CLI::App& app)
{
    auto acme = app.add_subcommand("oem-acme", "oem acme type command");
    auto getWidget = acme->add_subcommand("GetWidget", "get a widget");
    commands.push_back(
        std::make_unique<GetWidget>("oem_acme", "getWidget", getWidget));
}
"""

COMMON = {
    "pldmtool/pldm_base_cmd.cpp": BASE_CMD,
    "pldmtool/pldm_platform_cmd.cpp": PLATFORM_CMD,
}
SHAPES = {
    "auto": {**COMMON, "pldmtool/oem/ibm/pldm_oem_ibm.cpp": OEM_AUTO_CMD},
    "pointer": {**COMMON, "pldmtool/oem/ibm/pldm_oem_ibm.cpp": OEM_POINTER_CMD},
}
# the subcommand each shape registers under the type and its template
UNDER_TYPE = {
    "auto": ("GetAlertStatus", "pldmtool oem-ibm GetAlertStatus -m <eid> -i <id>"),
    "pointer": (
        "GetFileTable",
        "pldmtool oem-ibm GetFileTable -m <eid> -t <table>",
    ),
}
SPELLINGS = ["oem-ibm", "OEM-IBM", "Oem-Ibm"]

FIELDS = [
    "Rq:1=0x80",
    "Type:1=0x3f",
    "Cmd:1=0x01",
    "Id:1=0x05",
]


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")


def _tree(root: Path, files: dict[str, str]) -> code_mod.Tree:
    _write(root, files)
    return code_mod.Tree(
        "pldm",
        ORIGIN,
        "abcdef0123456789abcdef0123456789abcdef01",
        root,
        code_mod.Provenance("default", "master"),
        fetched_at="2026-10-19T01:02:03.000000+00:00",
    )


@pytest.fixture(params=sorted(SHAPES))
def shape(request):
    return request.param


@pytest.fixture
def tree(tmp_path, shape):
    return _tree(tmp_path / shape, SHAPES[shape])


@pytest.fixture
def acme_tree(tmp_path):
    files = {**COMMON, "pldmtool/oem/acme/pldm_oem_acme.cpp": OEM_ACME_CMD}
    return _tree(tmp_path / "acme", files)


def _run(capsys, argv, tree_for=None):
    parser = argparse.ArgumentParser()
    invocation.add_parsers(parser.add_subparsers(dest="command"))
    args = parser.parse_args(invocation.reorder_argv(["invocation", *argv]))
    code = invocation.cmd_invocation(args, tree_for)
    return code, capsys.readouterr().out.splitlines()


def _subcommand_lines(out: list[str]) -> list[str]:
    return [ln for ln in out if ln.startswith("subcommand:")]


# ------------------------------------------------------------------ AC-1


@pytest.mark.parametrize("asked", SPELLINGS)
def test_find_gives_nothing_for_the_oem_type_itself(tree, asked):
    assert pldmtool.find(tree, asked) is None


@pytest.mark.parametrize("asked", SPELLINGS)
def test_describe_prints_only_the_none_line_for_the_oem_type(tree, asked):
    assert pldmtool.describe(tree, asked, ORIGIN) == [NONE_LINE]


@pytest.mark.parametrize("asked", SPELLINGS)
def test_command_prints_the_bytes_then_none_for_the_oem_type(tree, asked, capsys):
    code, out = _run(
        capsys, ["pldm", "--subcommand", asked, *FIELDS], lambda a: (tree, ORIGIN)
    )
    assert code == 0
    _plain_code, plain = _run(capsys, ["pldm", *FIELDS])
    assert _plain_code == 0
    # the raw lines and the table unchanged, then the one `none` line
    assert out == [*plain, NONE_LINE]
    assert _subcommand_lines(out) == [NONE_LINE]
    # no registration line, no cite, no template, no note
    assert not any("add_subcommand" in ln for ln in out), out
    assert not any(ln.startswith("cite:") for ln in out), out
    assert not any(ln.startswith("note:") for ln in out), out
    assert not any("pldmtool oem-ibm" in ln for ln in out), out


def test_the_oem_type_is_not_a_subcommand_when_two_oem_files_register_it(tmp_path):
    # the real tree registers `oem-ibm` on the application in more than one
    # file under oem/ibm/; every one of them is the type itself
    files = {
        **COMMON,
        "pldmtool/oem/ibm/pldm_oem_ibm.cpp": OEM_AUTO_CMD,
        "pldmtool/oem/ibm/pldm_host_cmd.cpp": OEM_POINTER_CMD,
    }
    tree = _tree(tmp_path / "two", files)
    assert pldmtool.find(tree, "oem-ibm") is None
    assert pldmtool.describe(tree, "oem-ibm", ORIGIN) == [NONE_LINE]
    # and the subcommands of both files still sit under the type
    assert pldmtool.find(tree, "GetAlertStatus").type_ == "oem-ibm"
    assert pldmtool.find(tree, "GetFileTable").type_ == "oem-ibm"


# ------------------------------------------------------------------ AC-2


@pytest.mark.parametrize("asked", ["oem-acme", "OEM-ACME", "Oem-Acme"])
def test_another_oem_directory_type_is_not_a_subcommand_either(acme_tree, asked):
    assert pldmtool.find(acme_tree, asked) is None
    assert pldmtool.describe(acme_tree, asked, ORIGIN) == [NONE_LINE]


def test_a_subcommand_under_another_oem_directory_takes_that_type(acme_tree):
    widget = pldmtool.find(acme_tree, "getwidget")
    assert widget is not None
    assert (widget.name, widget.type_) == ("GetWidget", "oem-acme")
    assert widget.template() == "pldmtool oem-acme GetWidget -m <eid> -w <widget>"
    out = pldmtool.describe(acme_tree, "GetWidget", ORIGIN)
    assert out[0].startswith("pldm abcdef0 pldmtool/oem/acme/pldm_oem_acme.cpp:")
    assert out[0].endswith(
        '| auto getWidget = acme->add_subcommand("GetWidget", "get a widget");'
    )
    assert out[-2] == "subcommand: pldmtool oem-acme GetWidget -m <eid> -w <widget>"
    assert out[-1].endswith("check with pldmtool oem-acme GetWidget --help")


def test_the_rule_is_the_directory_type_name_not_the_string_ibm(acme_tree, tmp_path):
    # `oem-ibm` is no registration of the acme tree: none, as for any
    # unknown name; and `oem-acme` asked of an ibm-only tree is none too
    assert pldmtool.find(acme_tree, "oem-ibm") is None
    ibm_only = _tree(tmp_path / "ibm-only", SHAPES["auto"])
    assert pldmtool.find(ibm_only, "oem-acme") is None
    assert pldmtool.find(ibm_only, "oem-ibm") is None


# ------------------------------------------------------------------ AC-3


def test_subcommands_under_the_oem_type_keep_their_type_and_lines(tree, shape):
    name, template = UNDER_TYPE[shape]
    match = pldmtool.find(tree, name)
    assert match is not None
    assert (match.name, match.type_) == (name, "oem-ibm")
    assert match.template() == template
    out = pldmtool.describe(tree, name.lower(), ORIGIN)
    # registration, cite, numbered lines, template, note
    assert out[0].startswith("pldm abcdef0 pldmtool/oem/ibm/pldm_oem_ibm.cpp:")
    # the registration may span two lines (joined with a space after `(`)
    assert "add_subcommand(" in out[0] and f'"{name}"' in out[0], out[0]
    assert out[1].startswith(
        "cite: code | pldm abcdef0 | master 2026-10-19 | "
        "pldmtool/oem/ibm/pldm_oem_ibm.cpp lines "
    )
    assert out[-2] == f"subcommand: {template}"
    assert out[-1] == (
        "note: spellings of pldm abcdef0 (master 2026-10-19); the target's "
        f"pldmtool may differ: check with pldmtool oem-ibm {name} --help"
    )
    assert not any(ln.startswith("subcommand: options not read") for ln in out)


def test_command_still_prints_the_block_for_a_subcommand_under_the_oem_type(
    tree, shape, capsys
):
    name, template = UNDER_TYPE[shape]
    code, out = _run(
        capsys, ["pldm", "--subcommand", name, *FIELDS], lambda a: (tree, ORIGIN)
    )
    assert code == 0
    _plain_code, plain = _run(capsys, ["pldm", *FIELDS])
    assert out[: len(plain)] == plain
    block = out[len(plain) :]
    assert block == pldmtool.describe(tree, name, ORIGIN)
    assert block[-2] == f"subcommand: {template}"
    assert block[-1].startswith("note: spellings of pldm abcdef0")


@pytest.mark.parametrize("asked", ["base", "platform", "raw", "BASE", "Platform"])
def test_other_types_and_raw_still_say_none(tree, asked, capsys):
    assert pldmtool.find(tree, asked) is None
    assert pldmtool.describe(tree, asked, ORIGIN) == [NONE_LINE]
    code, out = _run(
        capsys, ["pldm", "--subcommand", asked, *FIELDS], lambda a: (tree, ORIGIN)
    )
    assert code == 0
    assert _subcommand_lines(out) == [NONE_LINE]


def test_subcommands_of_other_types_are_untouched(tree):
    tid = pldmtool.find(tree, "GetTID")
    assert (tid.type_, tid.template()) == ("base", "pldmtool base GetTID -m <eid>")
    pdr = pldmtool.find(tree, "getpdr")
    assert (pdr.type_, pdr.template()) == (
        "platform",
        "pldmtool platform GetPDR -m <eid>",
    )

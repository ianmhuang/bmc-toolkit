"""The Command workflow block of SKILL.md: removable in one cut, kept short."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"

START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
MAX_LINES = 40


def block_lines():
    lines = SKILL.read_text("utf-8").splitlines()
    assert lines.count(START) == 1
    assert lines.count(END) == 1
    first, last = lines.index(START), lines.index(END)
    assert first < last
    return lines[first + 1 : last]


def test_block_sits_between_its_markers_and_holds_the_workflow():
    body = "\n".join(block_lines())
    assert "## Command workflow" in body
    for term in ("**Command**", "**Raw", "**Invocation**"):
        assert term in body


def test_block_stays_within_its_line_budget():
    assert len(block_lines()) <= MAX_LINES


def test_description_names_the_tools_the_workflow_writes_for():
    head = SKILL.read_text("utf-8").split("\n---\n", 1)[0]
    description = next(
        line for line in head.splitlines() if line.startswith("description:")
    )
    for tool in ("ipmitool raw", "mctp-client", "pldmtool raw"):
        assert tool in description

"""Reviewer acceptance tests for T52's AC-6, the parts that are not wording:
the Command workflow block grew past develop's 46 lines and stays within
52, and every test file that pinned the old cap pins the new one. The
block's sentences are documentation and are not pinned here.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
SKILL = ROOT / "skills" / "bmc-spec" / "SKILL.md"

START = "<!-- command-workflow:start -->"
END = "<!-- command-workflow:end -->"
DEVELOP_LINES = 46  # the cap before T52
MAX_LINES = 52  # 46 until T52 (NC-SI Invocation)

# the ten files the change description names as pinning the cap
CAPPED = (
    "test_command_workflow.py",
    "test_review_cmdblock.py",
    "test_review_cmdmemory.py",
    "test_review_cmdresponse.py",
    "test_review_cmdwording.py",
    "test_review_everyline.py",
    "test_review_placeholder0x.py",
    "test_review_pldmsubblock.py",
    "test_review_pldmtype.py",
    "test_review_spdmlayout.py",
)


def _block() -> list[str]:
    lines = SKILL.read_text("utf-8").splitlines()
    assert lines.count(START) == 1 and lines.count(END) == 1
    first, last = lines.index(START), lines.index(END)
    assert first < last
    return lines[first + 1 : last]


def test_the_block_grew_for_nc_si_and_stays_within_52_lines():
    body = _block()
    assert DEVELOP_LINES < len(body) <= MAX_LINES, len(body)


@pytest.mark.parametrize("name", CAPPED)
def test_every_file_that_pinned_46_pins_52(name):
    source = (TESTS / name).read_text("utf-8")
    pins = re.findall(r"^MAX_LINES\s*=\s*(\d+)", source, re.M)
    assert pins == [str(MAX_LINES)], (name, pins)
